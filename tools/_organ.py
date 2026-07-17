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


def ledger_path(root):
    return os.path.join(root, "ledger.jsonl")


class LedgerCorruption(Exception):
    """A ledger line is not valid JSON — tamper evidence, not a reason to crash. Carries the
    seq/line so callers (ledger.py verify) can report BROKEN instead of dying with a traceback."""
    def __init__(self, lineno, raw):
        self.lineno = lineno
        self.raw = raw
        super().__init__(f"malformed ledger line {lineno}: not valid JSON")


def read_events(root):
    """Read the append-only ledger into a list of event dicts (empty if it doesn't exist yet).
    A malformed line raises LedgerCorruption — a non-JSON line IS tamper evidence; integrity
    checkers catch it and report BROKEN rather than crashing (external review, 2026-07)."""
    log = ledger_path(root)
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
