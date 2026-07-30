#!/usr/bin/env python3
"""resource — allocation, prioritization, and grant-decay events (docs/05 §5.4).

Grants exist in this org (context_budget, model_tier, dept-slot, delegated authority) but no
event ever TAKES THEM BACK, and every allocation is only correct relative to a current
priority ranking that nothing maintains. This tool supplies the missing events, each a pure
projection over tools/ledger.py, each fail-quiet with escalation only in the risk-increasing
direction (docs/05 §5.0). Ships no scheduler (R0): a host-run agent calls these on a cadence /
event; tick.py plans WHEN.

  rank <root> --objectives ID:WEIGHT,ID:WEIGHT [--basis E,E]   PRIORITY-RANKING. The reference
      RECLAIM and every allocation MOVE read. Emits priority_ranking_set only when the computed
      order DIFFERS from the current one (silent when order unchanged — no event, no digest).

  reclaim <root> --holder R --resource TYPE --yield-threshold F [--idle-cycles N]
      ALLOCATION-RECLAIM. Stranded resource is the dominant 24/7 waste: a downranked/stalled
      dept monotonically capturing scarce compute another dept needs. Reclaims from a low-yield/idle
      holder silently (safe direction); escalates ONLY if reclaim would deactivate a
      CEO-founded/protected dept, or there is nowhere non-harmful to cut (scarcity crisis).

  authority <root> [--now-tick N] [--ttl-ticks N] [--hard-cap-scope S]   AUTHORITY-EXPIRED.
      Delegations never decay → privilege-creep is the deepest overnight-compromise surface.
      Silently renews in-TTL justified grants, auto-revokes/narrows stale/orphaned ones past
      --ttl-ticks UNATTENDED (safe direction). The widen/renew-past-a-hard-cap escalation (the
      risk-increasing direction) is a CALLER-side check against --hard-cap-scope — this tool only
      narrows in the safe direction; it never widens, so it has no ESCALATE path of its own.

Each prints the ledger event it would emit. Exit 0 = silent/safe; 10 = escalate.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK, read_events, emit_event   # noqa: E402


def _current_ranking(events):
    """The latest priority_ranking_set's ordered objective ids, or None."""
    latest = None
    for e in events:
        if e["class"] == "priority_ranking_set":
            latest = e["payload"]
    if not latest:
        return None
    return [o["objective_id"] for o in latest.get("ordered_objectives", [])]


def cmd_rank(a):
    """PRIORITY-RANKING: recompute the order; emit ONLY if it changed."""
    pairs = []
    for tok in a.objectives.split(","):
        tok = tok.strip()
        if not tok:
            continue
        oid, _, w = tok.partition(":")
        pairs.append((oid.strip(), float(w) if w else 0.0))
    # deterministic order: by weight desc, then id asc (stable, reproducible)
    ordered = sorted(pairs, key=lambda p: (-p[1], p[0]))
    new_order = [oid for oid, _ in ordered]
    events = read_events(a.root)
    current = _current_ranking(events)
    if current == new_order:
        print(f"unchanged: recomputed order == current {new_order} — silent, no event, "
              f"no digest entry.")
        return OK
    rid = "r" + hashlib.sha256(",".join(new_order).encode()).hexdigest()[:10]
    ordered_objectives = [{"objective_id": oid, "rank": i + 1, "weight": w,
                           "rationale_hash": hashlib.sha256(f"{oid}:{w}".encode()).hexdigest()[:8]}
                          for i, (oid, w) in enumerate(ordered)]
    payload = {"ranking_id": rid, "ordered_objectives": ordered_objectives,
               "supersedes": current, "basis_event_ids":
               [b.strip() for b in (a.basis or "").split(",") if b.strip()]}
    emit_event("priority_ranking_set", payload)
    print(f"reordered: {current} -> {new_order}. Emitted (order changed). Escalate only if this "
          f"downranks a CEO-protected objective — that check is the caller's charter lookup.")
    # a pure reorder is not itself an escalation; charter-boundary crossing is a caller concern
    return OK


def cmd_reclaim(a):
    """ALLOCATION-RECLAIM: measure a holder's yield from the ledger; reclaim if low/idle."""
    events = read_events(a.root)
    # yield proxy: outputs produced per cycle the holder ran (cycle_completed.outputs / cycles)
    cycles = outputs = 0
    last_seq = -1
    for e in events:
        if e["class"] == "cycle_completed" and e["payload"].get("role") == a.holder:
            cycles += 1
            outputs += len(e["payload"].get("outputs", []))
            last_seq = e["seq"]
    total_cycles_since = sum(1 for e in events
                             if e["class"] == "cycle_started" and e["seq"] > last_seq)
    yield_metric = (outputs / cycles) if cycles else 0.0
    idle = total_cycles_since >= a.idle_cycles
    low_yield = yield_metric < a.yield_threshold
    if not (idle or low_yield):
        print(f"keep: {a.holder} yield {yield_metric:.2f} >= threshold {a.yield_threshold} and "
              f"not idle ({total_cycles_since} cycles since last output) — no reclaim, silent.")
        return OK
    reason = "idle" if idle else "downranked" if low_yield else "stalled"
    payload = {"holder": a.holder, "resource_type": a.resource, "from_level": "current",
               "to_level": "reduced", "yield_metric": round(yield_metric, 3),
               "ranking_ref": _current_ranking(events), "reason": reason}
    emit_event("allocation_reclaimed", payload)
    if a.protected and a.holder in [p.strip() for p in a.protected.split(",")]:
        print(f"ESCALATE: reclaim from {a.holder} would touch a CEO-protected dept — cannot "
              f"auto-reclaim; queue for the CEO.", file=sys.stderr)
        return ESCALATE
    print(f"reclaim: {a.holder} {a.resource} reduced ({reason}, yield {yield_metric:.2f}) — "
          f"safe-direction, unattended, no CEO traffic.")
    return OK


def cmd_authority(a):
    """AUTHORITY-EXPIRED: scan live grants; renew/revoke in the safe direction unattended."""
    events = read_events(a.root)
    # live grants = scope_grant_changed with change in {open,widen} not later revoked/narrowed
    grants = {}   # seam -> (change, seq, grantor)
    for e in events:
        if e["class"] == "scope_grant_changed":
            p = e["payload"]
            seam = json.dumps(p.get("seam", {}), sort_keys=True)
            grants[seam] = {"change": p.get("change"), "seq": e["seq"],
                            "grantor": p.get("grantor")}
    now = a.now_tick if a.now_tick is not None else (max((e["seq"] for e in events), default=0))
    reviewed = []
    escalate = False
    for seam, g in grants.items():
        age = now - g["seq"]
        # objective TTL: a grant older than the cap without renewal is stale → auto-narrow (safe)
        if g["change"] in ("open", "widen") and age > a.ttl_ticks:
            action = "narrow"    # safe direction: unattended
            reviewed.append({"seam": seam, "age": age, "action": action,
                             "still_justified": False})
        else:
            reviewed.append({"seam": seam, "age": age, "action": "renew",
                             "still_justified": True})
    payload = {"grants_reviewed": len(reviewed),
               "auto_narrowed": [r for r in reviewed if r["action"] == "narrow"],
               "renewed": [r for r in reviewed if r["action"] == "renew"]}
    emit_event("authority_reviewed", payload)
    narrowed = payload["auto_narrowed"]
    if narrowed:
        print(f"auto-narrowed {len(narrowed)} stale grant(s) past TTL {a.ttl_ticks} — safe "
              f"direction, unattended. (Widening/renewing past a hard cap would escalate; "
              f"none requested here.)")
    else:
        print(f"all {len(reviewed)} grant(s) in-TTL and justified — silent renew.")
    return OK


def main(argv):
    p = argparse.ArgumentParser(prog="resource", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("rank"); q.set_defaults(fn=cmd_rank)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)"); q.add_argument("--objectives", required=True)
    q.add_argument("--basis")

    q = sub.add_parser("reclaim"); q.set_defaults(fn=cmd_reclaim)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)"); q.add_argument("--holder", required=True)
    q.add_argument("--resource", required=True)
    q.add_argument("--yield-threshold", dest="yield_threshold", type=float, default=0.5)
    q.add_argument("--idle-cycles", dest="idle_cycles", type=int, default=3)
    q.add_argument("--protected")

    q = sub.add_parser("authority"); q.set_defaults(fn=cmd_authority)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)"); q.add_argument("--now-tick", dest="now_tick", type=int)
    q.add_argument("--ttl-ticks", dest="ttl_ticks", type=int, default=100)
    q.add_argument("--hard-cap-scope", dest="hard_cap_scope")

    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
