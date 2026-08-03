#!/usr/bin/env python3
"""Project ledger evidence into GitHub Checks-shaped JSON.

The output is a display projection.  It is not an admission decision and does
not replace the ledger or an external verifier.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import read_events  # noqa: E402


def project(root):
    events = read_events(root)
    checks = []
    for event in events:
        payload = event.get("payload") or {}
        if event.get("class") not in {"phase_admitted", "gate_result", "admission_decided", "halt_tripped"}:
            continue
        verdict = payload.get("verdict") or payload.get("result")
        conclusion = "neutral"
        if verdict in {"pass", "survives"}:
            conclusion = "success"
        elif verdict in {"fail", "refuted", "reject", "blocked"}:
            conclusion = "failure"
        checks.append({
            "name": "OrgForge / " + str(payload.get("phase") or event.get("class")),
            "head_sha": payload.get("head_sha"),
            "status": "completed",
            "conclusion": conclusion,
            "details_url": payload.get("evidence_url"),
            "output": {"title": "Evidence projection",
                       "summary": "Observed ledger evidence; no admission or DR verdict is inferred.",
                       "text": json.dumps({"event_seq": event.get("seq"),
                                           "evidence_digest": payload.get("evidence_digest"),
                                           "missing": payload.get("missing", [])},
                                          sort_keys=True, ensure_ascii=False)},
            "orgforge_disposition": "projection_only",
        })
    checks.sort(key=lambda c: (c["name"], c["output"]["text"]))
    return {"checks": checks, "projection_only": True, "admission_decision": None,
            "dr_claim": None}


def main(argv=None):
    p = argparse.ArgumentParser(prog="github_checks_projection")
    sub = p.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("project")
    cmd.add_argument("root")
    args = p.parse_args(argv)
    print(json.dumps(project(args.root), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
