#!/usr/bin/env python3
"""doctrine — the knowledge/guardrail store for org-first-agents (docs/07).

This is the running implementation of the doctrine organ: external information is
watched, admitted through the gate, distilled into per-role **doctrine** (each role's
current normative playbook — what it should currently believe about its domain and how it
should therefore work), version-and-TTL'd, and INJECTED into a role's working directory
before its harness launches. Doctrine is the guardrail: a role never acts on last
quarter's world, because its current doctrine is loaded every cycle.

It ships no runtime and no scheduler (docs/09): the curator/gate are agents a host harness
runs on a cadence; this tool is the file-backed store + the injection step + the admission
gate they call. Doctrine is a directory of per-role JSON files under a doctrine root:

    <root>/<role>.json  ->  { role, claims: [ {id, claim, provenance:{source,retrieved_at,
                              confidence,affected_roles}, review_by, admitted_at, version} ] }

Commands:
  propose  <root> <role> --claim TXT --source S --confidence C [--review-by DATE] [--affects R,R]
             curator step: file an intelligence item as a PENDING doctrine claim (not yet admitted)
  admit    <root> <role> <claim_id> --by gate                  gate step: admit a pending claim
  reject   <root> <role> <claim_id> --by gate --reason TXT     gate step: reject (provenance/standard fail)
  render   <root> <role> [--budget-tokens N] [--now DATE]      write the role's DOCTRINE.md for injection
  stale    <root> [--now DATE]                                 list claims past review_by (fires the curator)
  show     <root> <role>                                       print the role's doctrine (admitted + pending)

Guardrail invariants this tool enforces (docs/07 §3/§4):
  - Nothing external becomes loaded doctrine without passing `admit` (untrusted-until-admitted).
  - Every claim carries provenance {source, retrieved_at, confidence, affected_roles} — no
    anonymous doctrine (anti-poisoning).
  - Every claim carries a review_by TTL; `stale` surfaces expired claims so doctrine can't rot.
  - `render` only ever emits ADMITTED claims, within the context budget (over-budget = re-distill,
    never silent-truncate).
"""
import argparse
import hashlib
import json
import os
import sys


def _load(root, role):
    path = os.path.join(root, f"{role}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"role": role, "claims": []}


def _save(root, role, data):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, f"{role}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _claim_id(role, claim):
    return "c" + hashlib.sha256(f"{role}:{claim}".encode()).hexdigest()[:10]


def _find(data, cid):
    for c in data["claims"]:
        if c["id"] == cid:
            return c
    return None


def cmd_propose(a):
    """curator: file an intelligence item as a PENDING claim. Never admitted here —
    the curator proposes; only the gate admits (docs/07 §1)."""
    if not (a.source and a.confidence is not None):
        print("propose: --source and --confidence are required — no anonymous doctrine "
              "(provenance is the anti-poisoning guard, docs/07 §3)", file=sys.stderr)
        return 2
    data = _load(a.root, a.role)
    cid = _claim_id(a.role, a.claim)
    if _find(data, cid):
        print(f"claim {cid} already exists for {a.role}")
        return 0
    data["claims"].append({
        "id": cid,
        "claim": a.claim,
        "status": "pending",              # pending -> admitted | rejected (gate decides)
        "provenance": {
            "source": a.source,
            "retrieved_at": a.retrieved_at or "UNSET",
            "confidence": a.confidence,
            "affected_roles": [r.strip() for r in (a.affects or a.role).split(",")],
        },
        "review_by": a.review_by or "UNSET",   # TTL — stale doctrine must be re-checked
        "version": 1,
    })
    _save(a.root, a.role, data)
    print(f"proposed pending claim {cid} for {a.role} (awaits gate admission)")
    return 0


def cmd_admit(a):
    """gate: admit a pending claim. External content is untrusted until this step."""
    data = _load(a.root, a.role)
    c = _find(data, a.claim_id)
    if c is None:
        print(f"admit: no claim {a.claim_id} for {a.role}", file=sys.stderr)
        return 2
    if a.by != "gate":
        print("admit: --by must be 'gate' — only the authorization holder admits doctrine "
              "(a maker may not admit its own doctrine, docs/07 §4)", file=sys.stderr)
        return 2
    if c["provenance"]["retrieved_at"] == "UNSET" or c["review_by"] == "UNSET":
        print(f"admit: claim {a.claim_id} lacks retrieved_at or review_by — incomplete "
              f"provenance cannot be admitted (docs/07 §3)", file=sys.stderr)
        return 2
    c["status"] = "admitted"
    c["admitted_at"] = a.at or "UNSET"
    _save(a.root, a.role, data)
    print(f"admitted {a.claim_id} for {a.role} — now guardrail doctrine, loaded next cycle")
    return 0


def cmd_reject(a):
    data = _load(a.root, a.role)
    c = _find(data, a.claim_id)
    if c is None:
        print(f"reject: no claim {a.claim_id} for {a.role}", file=sys.stderr)
        return 2
    c["status"] = "rejected"
    c["reject_reason"] = a.reason
    _save(a.root, a.role, data)
    print(f"rejected {a.claim_id} for {a.role}: {a.reason}")
    return 0


def cmd_render(a):
    """Write the role's DOCTRINE.md — the guardrail loaded into its working dir before
    launch. Only ADMITTED claims; over budget => re-distill, never silent-truncate."""
    data = _load(a.root, a.role)
    admitted = [c for c in data["claims"] if c.get("status") == "admitted"]
    lines = [f"# DOCTRINE — {a.role}", "",
             "Your current normative playbook — what to believe about your domain now, and how",
             "to work given it. Admitted from watched external sources; each claim carries its",
             "provenance and a review-by date. This is a guardrail: act on the current world.",
             ""]
    stale_now = a.now
    for c in admitted:
        exp = ""
        if stale_now and c["review_by"] != "UNSET" and c["review_by"] < stale_now:
            exp = "  ⟨REVIEW OVERDUE⟩"
        prov = c["provenance"]
        lines.append(f"- {c['claim']}{exp}")
        lines.append(f"    (source: {prov['source']}; confidence: {prov['confidence']}; "
                     f"review by {c['review_by']})")
    body = "\n".join(lines) + "\n"
    # budget: doctrine that outgrows the pack budget must be re-distilled, not truncated
    approx_tokens = len(body) // 4
    if a.budget_tokens and approx_tokens > a.budget_tokens:
        print(f"render: doctrine for {a.role} is ~{approx_tokens} tokens > budget "
              f"{a.budget_tokens} — re-distill (fewer, sharper claims); not truncating "
              f"silently (docs/07 §3)", file=sys.stderr)
        return 1
    out = a.out or os.path.join(a.root, f"{a.role}.DOCTRINE.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"rendered {len(admitted)} admitted claim(s) -> {out}")
    return 0


def cmd_stale(a):
    """List admitted claims past their review_by — the doctrine_stale signal that fires
    the curator to re-check the world (docs/07 §3, sensors.yaml)."""
    if not a.now:
        print("stale: --now DATE required to compare against review_by", file=sys.stderr)
        return 2
    found = 0
    for fn in sorted(os.listdir(a.root)) if os.path.isdir(a.root) else []:
        if not fn.endswith(".json"):
            continue
        role = fn[:-5]
        data = _load(a.root, role)
        for c in data["claims"]:
            if c.get("status") == "admitted" and c["review_by"] != "UNSET" \
                    and c["review_by"] < a.now:
                print(f"STALE {role} {c['id']}: review_by {c['review_by']} < {a.now} — "
                      f"{c['claim'][:70]}")
                found += 1
    if not found:
        print("no stale doctrine")
    return 0


def cmd_show(a):
    data = _load(a.root, a.role)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="doctrine", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("propose"); q.set_defaults(fn=cmd_propose)
    q.add_argument("root"); q.add_argument("role")
    q.add_argument("--claim", required=True)
    q.add_argument("--source"); q.add_argument("--confidence", type=float)
    q.add_argument("--retrieved-at", dest="retrieved_at")
    q.add_argument("--review-by", dest="review_by")
    q.add_argument("--affects")

    q = sub.add_parser("admit"); q.set_defaults(fn=cmd_admit)
    q.add_argument("root"); q.add_argument("role"); q.add_argument("claim_id")
    q.add_argument("--by", required=True); q.add_argument("--at")

    q = sub.add_parser("reject"); q.set_defaults(fn=cmd_reject)
    q.add_argument("root"); q.add_argument("role"); q.add_argument("claim_id")
    q.add_argument("--by", required=True); q.add_argument("--reason", required=True)

    q = sub.add_parser("render"); q.set_defaults(fn=cmd_render)
    q.add_argument("root"); q.add_argument("role")
    q.add_argument("--budget-tokens", dest="budget_tokens", type=int)
    q.add_argument("--now"); q.add_argument("--out")

    q = sub.add_parser("stale"); q.set_defaults(fn=cmd_stale)
    q.add_argument("root"); q.add_argument("--now")

    q = sub.add_parser("show"); q.set_defaults(fn=cmd_show)
    q.add_argument("root"); q.add_argument("role")

    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
