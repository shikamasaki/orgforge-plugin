#!/usr/bin/env python3
"""reconcile — lateral, in-flight reconciliation between peers (docs/11 §2.4).

The one genuinely net-new information flow the operating-events sweep found: the horizontal
seam no other organ watches. The gate sees FINISHED outputs, doctrine is EXTERNAL, the digest
reports UPWARD — none look sideways at peer work while it is still in flight. Three siblings
share one shape, one fire rule, one escalation rule (docs/11 §2.4):

  collision <root> [--now-role R --now-territory T]   COLLISION-SCAN: reconcile the open
      work.claimed set. Two peers who picked up overlapping territory unaware of each other
      produce duplicate/contradictory outputs that only collide at merge. duplicate → peers
      self-resolve laterally (one yields), ZERO CEO traffic; contradiction (both mandates
      disagree) → escalate as a mandate-boundary dispute.

  stall <root> --freshness-cycles N                   DEPENDENCY-STALL: the mirror — a blocked
      dept in a meeting-free org is INVISIBLE (it just stops emitting; silence-as-block looks
      identical to silence-as-consent). Convert the ABSENCE of output on a depends_on edge into
      an explicit fact. First stall → the common owner's MOVE clears it; persists → escalate.

  contract <root> --seam S --producer R --breaking BOOL --dependents R,R [--deadline-tick T]
      CONTRACT-CHANGE-INTENT: a producer edits a depended-on seam; today divergence fires AFTER
      every dependent is broken. Move reconciliation BEFORE the mutation — the gate should
      refuse the seam-shape change unless this proposal exists upstream. Silence=consent after
      the deadline; objections route through the skeptic; escalate only unresolved objections or
      a breaking change to a charter-scoped dependency.

Every command obeys the fixed rule (docs/11 §0): silent when consistent (exit 0); lateral
self-heal before the CEO; escalate the true exception (exit 10). Each prints the ledger event
it would emit. This is a pure projection over tools/ledger.py; it ships no scheduler (R0) —
a host-run agent calls it, event-triggered (a peer's claim / edit / freshness-cross), never
on a clock (lateral collisions are created at claim/edit time, not on a cadence).
"""
import argparse
import json
import os
import sys

ESCALATE = 10
OK = 0


def _events(root):
    log = os.path.join(root, "ledger.jsonl")
    if not os.path.exists(log):
        return []
    out = []
    with open(log, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _emit(cls, payload):
    print("LEDGER-EVENT " + json.dumps({"class": cls, "payload": payload}, ensure_ascii=False))


def _open_claims(events):
    """work.claimed still open = claimed and not yet closed by a cycle_completed / result for it.
    We treat a claim as open until the same role emits a cycle_completed after the claim."""
    claims = []           # (seq, role, territory, intent)
    for e in events:
        if e["class"] == "work_claimed":
            p = e["payload"]
            claims.append({"seq": e["seq"], "role": p.get("role"),
                           "territory": p.get("work_territory"),
                           "intent": p.get("intent_summary", "")})
    # drop claims whose role completed a cycle after claiming (work landed → no longer in flight)
    closed_after = {}
    for e in events:
        if e["class"] == "cycle_completed":
            role = e["payload"].get("role")
            closed_after.setdefault(role, []).append(e["seq"])
    open_claims = []
    for c in claims:
        later = [s for s in closed_after.get(c["role"], []) if s > c["seq"]]
        if not later:
            open_claims.append(c)
    return open_claims


def cmd_collision(a):
    """Reconcile the open claim set for overlapping territory among DIFFERENT peers."""
    events = _events(a.root)
    open_claims = _open_claims(events)
    if a.now_role and a.now_territory:
        open_claims = open_claims + [{"seq": 10**9, "role": a.now_role,
                                      "territory": a.now_territory, "intent": "(incoming)"}]
    # group by territory; an overlap is >1 DISTINCT role on the same territory
    by_terr = {}
    for c in open_claims:
        by_terr.setdefault(c["territory"], set()).add(c["role"])
    overlaps = {t: sorted(roles) for t, roles in by_terr.items() if len(roles) > 1}
    if not overlaps:
        _emit("lateral_reconciled", {"observer_role": "collision-scan", "subjects": [],
                                     "reference": "open_claims", "result": "consistent",
                                     "divergence_kind": None, "evidence_event_ids": []})
        print(f"clear: {len(open_claims)} open claim(s), no two peers on the same territory "
              f"— silent.")
        return OK
    # duplicate vs contradiction: without semantics we report OVERLAP and let the caller (an
    # agent) classify; but we escalate ONLY if the intents are marked contradictory. Here we
    # surface every overlap as divergent and default kind=duplicate (peer-resolvable); a true
    # contradiction is a semantic judgment the calling agent stamps.
    terr, roles = next(iter(overlaps.items()))
    _emit("lateral_reconciled", {"observer_role": "collision-scan", "subjects": roles,
                                 "reference": terr, "result": "divergent",
                                 "divergence_kind": "duplicate",
                                 "evidence_event_ids": []})
    print(f"OVERLAP: peers {roles} both hold territory '{terr}'. If duplicate → they self-"
          f"resolve laterally (one yields), NO CEO traffic. Escalate ONLY if a semantic check "
          f"finds a contradiction (both mandates disagree). Other overlaps: "
          f"{ {t: r for t, r in overlaps.items() if t != terr} }", file=sys.stderr)
    # duplicate is peer-resolvable → this is the lateral-self-heal path, not a CEO escalation
    return OK


def cmd_stall(a):
    """Convert the ABSENCE of output on a depends_on edge into an explicit stall fact."""
    events = _events(a.root)
    # a dependency edge: a consumer role has bound work awaiting a producer's output. We detect
    # a stall as: a role emitted cycle_started but no cycle_completed within N subsequent cycles
    # of the whole org (a freshness window) — its work is in flight but not landing.
    started = {}   # role -> last cycle_started seq
    completed = {} # role -> last cycle_completed seq
    total_cycles = 0
    for e in events:
        if e["class"] == "cycle_started":
            started[e["payload"].get("role")] = e["seq"]
            total_cycles += 1
        elif e["class"] == "cycle_completed":
            completed[e["payload"].get("role")] = e["seq"]
    stalled = []
    for role, sseq in started.items():
        cseq = completed.get(role, -1)
        if cseq < sseq:
            # count org cycles that elapsed since this role started without completing
            elapsed = sum(1 for e in events
                          if e["class"] == "cycle_started" and e["seq"] > sseq)
            if elapsed >= a.freshness_cycles:
                stalled.append({"role": role, "started_seq": sseq, "stalled_cycles": elapsed})
    if not stalled:
        _emit("dependency_stall_raised", {"blocked_role": None, "result": "no_stall"})
        print(f"no stall: every started cycle completed within {a.freshness_cycles} cycles "
              f"— silent.")
        return OK
    worst = max(stalled, key=lambda s: s["stalled_cycles"])
    _emit("dependency_stall_raised", {"blocked_role": worst["role"], "awaited_seam_id": None,
                                      "awaited_producer_role": None,
                                      "stalled_ticks": worst["stalled_cycles"],
                                      "downstream_impact": []})
    print(f"STALL: {worst['role']} started but has not completed in {worst['stalled_cycles']} "
          f"cycles (>= freshness {a.freshness_cycles}) — silence-as-block, now explicit. "
          f"First stall routes to the common owner's MOVE; escalate only if it persists after "
          f"a self-heal MOVE. All stalled: {[s['role'] for s in stalled]}", file=sys.stderr)
    return ESCALATE


def cmd_contract(a):
    """Announce a seam-shape change to bound dependents BEFORE the mutation lands."""
    dependents = [r.strip() for r in a.dependents.split(",") if r.strip()]
    breaking = a.breaking.lower() in ("true", "1", "yes")
    payload = {"seam_id": a.seam, "producer_role": a.producer, "current_hash": None,
               "proposed_shape": a.proposed_shape or "(shape omitted)",
               "is_breaking": breaking, "dependents": dependents,
               "objection_deadline_tick": a.deadline_tick}
    _emit("contract_change_proposed", payload)
    if not breaking:
        print(f"non-breaking: seam '{a.seam}' change announced to {dependents}. Silence=consent "
              f"after deadline {a.deadline_tick}; the change then proceeds. No CEO traffic.")
        return OK
    # a breaking change to a charter-scoped dependency is the escalation case; we can't know
    # charter-scope from here, so we surface breaking loudly and let the gate/registrar decide.
    print(f"BREAKING: seam '{a.seam}' change is breaking for dependents {dependents}. The gate "
          f"must not admit the seam-shape edit until objections resolve; objections route "
          f"through the skeptic. Escalate to CEO only if a dependent is charter-scoped or an "
          f"objection stays unresolved.", file=sys.stderr)
    return ESCALATE


def main(argv):
    p = argparse.ArgumentParser(prog="reconcile", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("collision"); q.set_defaults(fn=cmd_collision)
    q.add_argument("root")
    q.add_argument("--now-role", dest="now_role")
    q.add_argument("--now-territory", dest="now_territory")

    q = sub.add_parser("stall"); q.set_defaults(fn=cmd_stall)
    q.add_argument("root")
    q.add_argument("--freshness-cycles", dest="freshness_cycles", type=int, default=2)

    q = sub.add_parser("contract"); q.set_defaults(fn=cmd_contract)
    q.add_argument("root")
    q.add_argument("--seam", required=True)
    q.add_argument("--producer", required=True)
    q.add_argument("--breaking", required=True)
    q.add_argument("--dependents", required=True)
    q.add_argument("--proposed-shape", dest="proposed_shape")
    q.add_argument("--deadline-tick", dest="deadline_tick")

    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
