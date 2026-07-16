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

ESCALATE = 10   # exit: the exception surfaced — host enqueues / pages / halts
OK = 0          # exit: fail-quiet — nothing surfaces


def ledger_path(root):
    return os.path.join(root, "ledger.jsonl")


def read_events(root):
    """Read the append-only ledger into a list of event dicts (empty if it doesn't exist yet)."""
    log = ledger_path(root)
    if not os.path.exists(log):
        return []
    out = []
    with open(log, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def emit_event(cls, payload):
    """Print the ledger event this organ would append. The host parser keys on the
    'LEDGER-EVENT ' prefix; the organ COMPUTES, the host APPENDS (docs/09)."""
    print("LEDGER-EVENT " + json.dumps({"class": cls, "payload": payload}, ensure_ascii=False))
