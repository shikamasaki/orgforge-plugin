#!/usr/bin/env python3
"""Deterministic, vendor-neutral ledger/trace correlation export.

This is correlation data, not an evaluator.  It emits no resilience score or
DR decision and never mutates the ledger.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import read_events  # noqa: E402


def _stable_id(event):
    raw = json.dumps({"seq": event.get("seq"), "id": event.get("id"),
                      "hash": event.get("hash")}, sort_keys=True,
                     separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def export(root):
    spans = []
    for event in read_events(root):
        payload = event.get("payload") or {}
        attrs = {
            "orgforge.event_class": event.get("class"),
            "orgforge.ledger_seq": event.get("seq"),
            "orgforge.ledger_hash": event.get("hash"),
            "orgforge.source_digest": payload.get("evidence_digest") or payload.get("request_digest"),
            "orgforge.issue": payload.get("issue") or payload.get("candidate_id"),
            "orgforge.phase": payload.get("phase"),
            "orgforge.role": payload.get("role") or payload.get("gate"),
            "orgforge.harness": payload.get("harness"),
            "orgforge.session_id": payload.get("session_id"),
            "orgforge.trace_id": payload.get("trace_id"),
            "orgforge.span_id": payload.get("span_id"),
        }
        attrs = {key: value for key, value in attrs.items() if value is not None}
        spans.append({
            "name": "orgforge." + str(event.get("class", "event")),
            "spanId": _stable_id(event),
            "traceId": payload.get("trace_id"),
            "parentSpanId": payload.get("parent_span_id"),
            "startTimeUnixNano": event.get("ts"),
            "attributes": attrs,
            "status": {"code": "UNSET"},
            "missingCorrelation": payload.get("trace_id") is None,
        })
    return {
        "resource": {"attributes": {
            "service.name": "orgforge",
            "orgforge.export": "ledger-correlation",
            "orgforge.semantic_disposition": "observation_only",
        }},
        "scopeSpans": [{"scope": {"name": "orgforge.otel_export", "version": "1"},
                        "spans": spans}],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="otel_export")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("export")
    cmd.add_argument("root")
    args = parser.parse_args(argv)
    if args.command == "export":
        print(json.dumps(export(args.root), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
