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

  mandate <root> --subjects R,R --decision D --precedence R>R>R [--satisfiable BOOL]
      MANDATE-CONFLICT (docs/13): two depts each acting INSIDE their granted authority reach
      decisions that cannot both stand (growth says "ship", safety says "hold") — not a resource
      grab, not a file collision. `collision` resolves by "one yields", legitimate only for a
      DUPLICATE; a genuine CONTRADICTION it correctly refuses and dead-ends at "escalate". This
      adjudicates it against a DECLARED mandate-precedence ordering (constitution.yaml, human-
      written, agent-unwritable — passed here as --precedence): precedence-applies (silent) /
      co-equal-both-satisfiable (integrate laterally) / co-equal-mutually-exclusive (escalate —
      the true exception). Anchor: Follett (constructive conflict), Lawrence & Lorsch. Belongs to
      Organ 6 — the repo ranked OBJECTIVES by weight but never precedence BETWEEN MANDATES.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK, read_events, emit_event   # noqa: E402


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
    events = read_events(a.root)
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
        emit_event("lateral_reconciled", {"observer_role": "collision-scan", "subjects": [],
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
    emit_event("lateral_reconciled", {"observer_role": "collision-scan", "subjects": roles,
                                 "reference": terr, "result": "divergent",
                                 "divergence_kind": "duplicate",
                                 "evidence_event_ids": []})
    print(f"OVERLAP: peers {roles} both hold territory '{terr}'. If duplicate → they self-"
          f"resolve laterally (one yields), NO CEO traffic. Escalate ONLY if a semantic check "
          f"finds a contradiction (both mandates disagree). Other overlaps: "
          f"{ {t: r for t, r in overlaps.items() if t != terr} }", file=sys.stderr)
    # duplicate is peer-resolvable → this is the lateral-self-heal path, not a CEO escalation
    return OK


def _latest_depends_on(events, role):
    """The most recent depends_on edge set a role declared via work_claimed."""
    edges = []
    for e in events:
        if e["class"] == "work_claimed" and e["payload"].get("role") == role:
            edges = e["payload"].get("depends_on") or []
    return edges


def _lowest_common_owner(events, roles):
    """Route a stall to the lowest role that supervises all of `roles`. Derived from the
    supervises edges the ledger records (profile_edited/cycle payloads carry no chart, so we
    read the org's supervises map if present in a work_claimed 'supervisor' hint; absent that,
    route to the CEO sentinel). Kept simple: the common owner is the shared supervisor if every
    role names the same one, else 'ceo' (the top)."""
    sups = set()
    for e in events:
        if e["class"] == "cycle_completed":
            p = e["payload"]
            if p.get("role") in roles and p.get("accountable_supervisor"):
                sups.add(p["accountable_supervisor"])
    return sups.pop() if len(sups) == 1 else "ceo"


def cmd_stall(a):
    """Convert the ABSENCE of output on a depends_on edge into an explicit stall fact. Reads the
    actual depends_on edges a consumer declared (work_claimed.depends_on) and reports WHO it is
    waiting on and WHAT the downstream impact is — not just that a cycle didn't complete."""
    events = read_events(a.root)
    started, completed = {}, {}
    for e in events:
        if e["class"] == "cycle_started":
            started[e["payload"].get("role")] = e["seq"]
        elif e["class"] == "cycle_completed":
            completed[e["payload"].get("role")] = e["seq"]
    stalled = []
    for role, sseq in started.items():
        cseq = completed.get(role, -1)
        if cseq < sseq:
            elapsed = sum(1 for e in events
                          if e["class"] == "cycle_started" and e["seq"] > sseq)
            if elapsed >= a.freshness_cycles:
                # read this role's declared dependency edges; a stall is a TRUE blocked-on
                # stall if a producer it awaits has not completed since the consumer started.
                edges = _latest_depends_on(events, role)
                awaiting = [ed for ed in edges
                            if completed.get(ed.get("producer_role"), -1) < sseq]
                stalled.append({"role": role, "started_seq": sseq, "stalled_cycles": elapsed,
                                "awaiting": awaiting})
    if not stalled:
        emit_event("dependency_stall_raised", {"blocked_role": None, "result": "no_stall"})
        print(f"no stall: every started cycle completed within {a.freshness_cycles} cycles "
              f"— silent.")
        return OK
    worst = max(stalled, key=lambda s: s["stalled_cycles"])
    awaiting = worst["awaiting"]
    awaited_producer = awaiting[0]["producer_role"] if awaiting else None
    awaited_seam = awaiting[0].get("seam_id") if awaiting else None
    # downstream impact: everyone else whose depends_on names the blocked role as a producer
    downstream = sorted({s["role"] for s in stalled
                         if any(ed.get("producer_role") == worst["role"]
                                for ed in _latest_depends_on(events, s["role"]))})
    owner = _lowest_common_owner(events, [worst["role"]] +
                                 ([awaited_producer] if awaited_producer else []))
    emit_event("dependency_stall_raised", {"blocked_role": worst["role"],
                                      "awaited_seam_id": awaited_seam,
                                      "awaited_producer_role": awaited_producer,
                                      "stalled_ticks": worst["stalled_cycles"],
                                      "downstream_impact": downstream,
                                      "route_to": owner})
    waiting_on = (f" waiting on {awaited_producer}"
                  f"{' for ' + awaited_seam if awaited_seam else ''}" if awaited_producer
                  else " (no declared producer — stalled in place)")
    print(f"STALL: {worst['role']}{waiting_on}, {worst['stalled_cycles']} cycles "
          f"(>= freshness {a.freshness_cycles}) — routes to {owner}. Downstream: {downstream}. "
          f"Escalate only if it persists after a self-heal MOVE.", file=sys.stderr)
    return ESCALATE


def cmd_contract(a):
    """Announce a seam-shape change to bound dependents BEFORE the mutation lands."""
    dependents = [r.strip() for r in a.dependents.split(",") if r.strip()]
    breaking = a.breaking.lower() in ("true", "1", "yes")
    payload = {"seam_id": a.seam, "producer_role": a.producer, "current_hash": None,
               "proposed_shape": a.proposed_shape or "(shape omitted)",
               "is_breaking": breaking, "dependents": dependents,
               "objection_deadline_tick": a.deadline_tick}
    emit_event("contract_change_proposed", payload)
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


def cmd_mandate(a):
    """Adjudicate a genuine mandate contradiction against a DECLARED precedence ordering."""
    subjects = [r.strip() for r in a.subjects.split(",") if r.strip()]
    # precedence: "safety>growth>cost" — earlier = governs. Human-written in constitution.yaml.
    order = [r.strip() for r in a.precedence.split(">") if r.strip()]
    rank = {r: i for i, r in enumerate(order)}
    # does declared precedence resolve it? the subject with the lowest rank governs.
    ranked_subjects = [s for s in subjects if s in rank]
    satisfiable = str(a.satisfiable).lower() in ("true", "1", "yes")
    if len(ranked_subjects) < len(subjects):
        # a subject not in the precedence ordering — cannot adjudicate deterministically
        resolution = "escalate"
        note = (f"a subject {[s for s in subjects if s not in rank]} is absent from the declared "
                f"mandate precedence — the org never declared who governs; the human must, and "
                f"add it to constitution.yaml mandate_precedence")
    elif satisfiable:
        resolution = "integrate"
        note = ("co-equal but BOTH satisfiable — integrate laterally (Follett's integration: find "
                "the option honoring both mandates); no CEO traffic")
    elif len(set(rank[s] for s in ranked_subjects)) == len(ranked_subjects):
        # distinct precedence ranks → precedence applies, highest governs
        governs = min(ranked_subjects, key=lambda s: rank[s])
        resolution = "precedence_applies"
        note = (f"declared precedence resolves it: '{governs}' governs (rank {rank[governs]}); "
                f"the contested decision follows its mandate — silent, no CEO traffic")
    else:
        resolution = "escalate"
        note = ("co-equal mandates AND mutually exclusive — neither can yield without violating "
                "its own mandate; this is the true exception the human must adjudicate")
    payload = {"subjects": subjects, "contested_decision": a.decision,
               "mandate_refs": order, "resolution": resolution, "evidence_ids": []}
    emit_event("mandate_conflict_raised", payload)
    if resolution in ("precedence_applies", "integrate"):
        print(f"{resolution}: {note}")
        return OK
    print(f"ESCALATE: mandate conflict on '{a.decision}' between {subjects} — {note}",
          file=sys.stderr)
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

    q = sub.add_parser("mandate"); q.set_defaults(fn=cmd_mandate)
    q.add_argument("root")
    q.add_argument("--subjects", required=True)
    q.add_argument("--decision", required=True)
    q.add_argument("--precedence", required=True)
    q.add_argument("--satisfiable", default="false")

    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
