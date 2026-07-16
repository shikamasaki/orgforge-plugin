#!/usr/bin/env python3
"""conventions — internally-originated reusable precedent (docs/13 §5).

Human orgs coordinate massively through routines and precedent — "how we do X here," settled once
and silently reused. An AI org that cold-starts each cycle from profile + doctrine + ledger has no
shared memory of its OWN established conventions, so peer depts independently re-derive how to do a
recurring cross-cutting thing (a naming scheme, an interface shape, an escalation format, "we
settled on approach B last week") and diverge — the exact tacit-not-articulated failure the whole
repo exists to prevent, reappearing one level down. This is a THIRD box distinct from the others:
  - not doctrine (docs/07): doctrine is EXTERNAL world-knowledge; a convention is INTERNAL precedent.
  - not the constitution: the constitution says WHO decides, not the CONTENT of a settled non-charter
    operational choice.
  - not reconcile.py: that catches a LIVE collision; a convention is the upstream shared prior so the
    collision never forms.
Anchor: Nelson & Winter (1982), routines as organizational memory. It reuses the doctrine machinery
almost verbatim (adopt through a checker, project into the workspace, TTL) — honestly, this may be a
second MODE of the knowledge organ rather than a new one; the concept (internal reusable precedent)
is what was missing, wherever it is housed. Pure store over a directory; ships no scheduler (R0).

  adopt   <root> --scope S --choice TXT --owner R --by checker [--review-by DATE]
      Record a settled convention (only a checker adopts — not the dept that proposed it, same
      maker/checker split as doctrine admission).
  conflict <root> --scope S --choice TXT
      CONVENTION-CONFLICT: a new settled choice contradicts an existing convention on the same scope
      → escalate (the org is about to fork its own precedent).
  render  <root> --role R [--out FILE]
      Project the conventions this role should follow into its workspace (like doctrine render).
  stale   <root> --now DATE
      CONVENTION-STALE: conventions past their review_by (routines rot too).
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK   # noqa: E402


def _path(root):
    return os.path.join(root, "conventions.json")


def _load(root):
    p = _path(root)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"conventions": []}


def _save(root, data):
    os.makedirs(root, exist_ok=True)
    with open(_path(root), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def cmd_adopt(a):
    if a.by != "checker":
        print("adopt: --by must be 'checker' — the dept that proposed a convention may not adopt "
              "its own (same maker/checker split as doctrine, docs/07 §4)", file=sys.stderr)
        return 2
    data = _load(a.root)
    # conflict guard: a different settled choice already exists for this scope
    for c in data["conventions"]:
        if c["scope"] == a.scope and c["choice"] != a.choice and c.get("status") == "active":
            print(f"adopt: scope '{a.scope}' already has an active convention '{c['choice']}' — "
                  f"use `conflict` to adjudicate before forking precedent", file=sys.stderr)
            return ESCALATE
    cid = "v" + hashlib.sha256(f"{a.scope}:{a.choice}".encode()).hexdigest()[:10]
    data["conventions"].append({
        "id": cid, "scope": a.scope, "choice": a.choice, "owner": a.owner,
        "provenance": {"adopted_by": a.by}, "review_by": a.review_by or "UNSET",
        "status": "active"})
    _save(a.root, data)
    print("LEDGER-EVENT " + json.dumps(
        {"class": "convention_adopted",
         "payload": {"scope": a.scope, "settled_choice": a.choice, "owner": a.owner,
                     "review_by": a.review_by or "UNSET"}}, ensure_ascii=False))
    print(f"adopted convention {cid} for scope '{a.scope}': {a.choice}")
    return OK


def cmd_conflict(a):
    data = _load(a.root)
    for c in data["conventions"]:
        if c["scope"] == a.scope and c.get("status") == "active" and c["choice"] != a.choice:
            print(f"CONVENTION-CONFLICT: scope '{a.scope}' already settled as '{c['choice']}', "
                  f"new '{a.choice}' contradicts it — the org is about to fork its own precedent. "
                  f"Escalate to the owner ({c['owner']}) to reconcile before both spread.",
                  file=sys.stderr)
            return ESCALATE
    print(f"clear: no active convention on '{a.scope}' contradicts '{a.choice}' — safe to adopt.")
    return OK


def cmd_render(a):
    data = _load(a.root)
    active = [c for c in data["conventions"] if c.get("status") == "active"]
    lines = [f"# CONVENTIONS — {a.role}", "",
             "How this org has settled on doing recurring things. Internal precedent (not external",
             "doctrine): reuse these instead of re-deriving, so peers don't diverge.", ""]
    for c in active:
        lines.append(f"- [{c['scope']}] {c['choice']}  (owner: {c['owner']}; review by "
                     f"{c['review_by']})")
    body = "\n".join(lines) + "\n"
    out = a.out or os.path.join(a.root, f"{a.role}.CONVENTIONS.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"rendered {len(active)} convention(s) -> {out}")
    return OK


def cmd_stale(a):
    data = _load(a.root)
    stale = [c for c in data["conventions"]
             if c.get("status") == "active" and c["review_by"] != "UNSET"
             and c["review_by"] < a.now]
    for c in stale:
        print(f"STALE {c['id']} [{c['scope']}]: review_by {c['review_by']} < {a.now} — routines "
              f"rot; re-confirm or retire.")
    if not stale:
        print("no stale conventions")
    return OK


def main(argv):
    p = argparse.ArgumentParser(prog="conventions", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("adopt"); q.set_defaults(fn=cmd_adopt)
    q.add_argument("root"); q.add_argument("--scope", required=True)
    q.add_argument("--choice", required=True); q.add_argument("--owner", required=True)
    q.add_argument("--by", required=True); q.add_argument("--review-by", dest="review_by")

    q = sub.add_parser("conflict"); q.set_defaults(fn=cmd_conflict)
    q.add_argument("root"); q.add_argument("--scope", required=True)
    q.add_argument("--choice", required=True)

    q = sub.add_parser("render"); q.set_defaults(fn=cmd_render)
    q.add_argument("root"); q.add_argument("--role", required=True); q.add_argument("--out")

    q = sub.add_parser("stale"); q.set_defaults(fn=cmd_stale)
    q.add_argument("root"); q.add_argument("--now", required=True)

    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
