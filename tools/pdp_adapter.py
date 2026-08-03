#!/usr/bin/env python3
"""Prepare and record an external OPA/Cedar PDP exchange.

Policy semantics stay in the PDP.  This module only binds request/response
bytes, issuer, and policy digest for auditability.
"""
import argparse
import hashlib
import json
import os
import sys


def _digest(value):
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def prepare(policy, subject):
    if not isinstance(subject, dict) or not policy:
        raise ValueError("policy and object subject are required")
    request = {"api_version": "orgforge.external-pdp/v1", "policy_ref": policy,
               "input": subject, "orgforge_semantics": "delegated_only"}
    return {"request": request, "request_digest": _digest(json.dumps(request, sort_keys=True,
                                                               separators=(",", ":"), ensure_ascii=False))}


def record(request, response, issuer, policy_digest):
    if not issuer or not policy_digest or not isinstance(response, dict):
        raise ValueError("issuer, policy_digest, and response are required")
    return {"request": request, "response": response, "issuer": issuer,
            "policy_digest": policy_digest, "disposition": "external_decision_recorded",
            "orgforge_decision": None, "dr_claim": None}


def main(argv=None):
    p = argparse.ArgumentParser(prog="pdp_adapter")
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("prepare"); q.add_argument("--policy", required=True); q.add_argument("--input", required=True)
    r = sub.add_parser("record"); r.add_argument("--request", required=True); r.add_argument("--response", required=True); r.add_argument("--issuer", required=True); r.add_argument("--policy-digest", required=True)
    a = p.parse_args(argv)
    if a.command == "prepare":
        result = prepare(a.policy, json.loads(a.input))
    else:
        result = record(json.loads(a.request), json.loads(a.response), a.issuer, a.policy_digest)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
