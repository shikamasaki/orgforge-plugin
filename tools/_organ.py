#!/usr/bin/env python3
"""_organ — the shared substrate every ledger-reading organ imports.

Centralizes the byte-identical primitives that were copied across the tools: the ledger.jsonl
reader, the LEDGER-EVENT emitter, the ledger-path resolver, and the exit-code contract
(0 = fail-quiet, 10 = escalate). Behavior is UNCHANGED — each body already existed verbatim in
the tools; this only removes the copies. R0 / harness-neutral: no scheduler, no network, no
clock — pure functions over a file.

Imported by a flat same-dir idiom so it resolves in all three invocation modes (repo-root CLI,
org_hook subprocess by absolute path, bundled-in-plugin copy):

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _organ import ESCALATE, OK, read_events, emit_event
"""
import json
import os
import sys as _sys
# cp932 fix: organ messages contain em-dashes; force UTF-8 on captured pipes so
# a print() never crashes the PreToolUse guardrail on a non-UTF-8 console locale.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

ESCALATE = 10   # exit: the exception surfaced — host enqueues / pages / halts
OK = 0          # exit: fail-quiet — nothing surfaces


def resolve_root(root=None):
    """Resolve a ledger root: the explicit argument wins, else DISCOVER it from the working directory.

    Every organ takes `root` as a positional argument, and until now the only way to fill it was to
    know the path — which pushed the knowledge into `.envrc`, into absolute paths, and therefore into
    one machine. Since an org is a place on disk (`.orgforge/ledger` beside `organization.yaml`), the
    organs can find it themselves; passing `root` explicitly stays supported and still wins, for a
    ledger deliberately kept elsewhere or pinned in CI.

    Raises SystemExit(2) with an actionable message when there is no org to find, rather than
    silently operating on a wrong or empty path."""
    if root:
        return root
    try:
        import discover
    except ImportError:
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import discover
    found = discover.ledger_root()
    if not found:
        print("no ledger root given and none discoverable from "
              f"{os.getcwd()} — run this inside an org (a directory with organization.yaml or "
              ".orgforge/), or pass the root explicitly.", file=_sys.stderr)
        raise SystemExit(2)
    return found


def ledger_path(root):
    return os.path.join(root, "ledger.jsonl")


class LedgerCorruption(Exception):
    """A ledger line is not valid JSON — tamper evidence, not a reason to crash. Carries the
    seq/line so callers (ledger.py verify) can report BROKEN instead of dying with a traceback."""
    def __init__(self, lineno, raw):
        self.lineno = lineno
        self.raw = raw
        super().__init__(f"malformed ledger line {lineno}: not valid JSON")


def read_events(root=None):
    """Read the append-only ledger into a list of event dicts (empty if it doesn't exist yet).
    A malformed line raises LedgerCorruption — a non-JSON line IS tamper evidence; integrity
    checkers catch it and report BROKEN rather than crashing (external review, 2026-07).

    `root` may be omitted: every organ funnels its reads through here, so resolving it in one place
    makes the whole tool surface work from inside an org with no environment set up."""
    log = ledger_path(resolve_root(root))
    if not os.path.exists(log):
        return []
    out = []
    with open(log, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    raise LedgerCorruption(i, line)
    return out


def emit_event(cls, payload):
    """Print the ledger event this organ would append. The host parser keys on the
    'LEDGER-EVENT ' prefix; the organ COMPUTES, the host APPENDS (docs/08)."""
    print("LEDGER-EVENT " + json.dumps({"class": cls, "payload": payload}, ensure_ascii=False))
