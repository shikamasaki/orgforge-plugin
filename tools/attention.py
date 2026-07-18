#!/usr/bin/env python3
"""attention — a department's INTERNAL work selection (docs/12, the attention-allocation organ).

The org-wide priority ranking (resource.py rank) says which OBJECTIVES matter; nothing said how
a single department, given its own backlog, decides WHAT TO WORK ON NEXT. That decision was left
implicit — the LLM picked, unrecorded, unaudited, and unconnected to the org-wide ranking. That
is exactly the tacit-left-tacit failure this repo exists to remove: an AI department can only act
on what is written down, so its internal triage must be articulated too. The organizational-theory
anchor is attention allocation under bounded rationality — the Carnegie School (March & Simon 1958;
Cyert & March 1963) and Ocasio's Attention-Based View (1997) — plus the operations-side flow limit
(Theory of Constraints; Kanban WIP). See docs/sources.md.

This tool makes the four intra-unit decisions explicit and auditable, as a pure projection over
tools/ledger.py (ships no scheduler; a host-run department calls it at the start of its cycle):

  select <root> --role R [--priority-ref] [--wip-limit N] [--aspiration F]
      Score the role's backlog (open_experiments view) and choose the next item(s), applying:
        • SITUATED ATTENTION (Ocasio): score each backlog item by its alignment to the current
          org-wide priority_ranking_set — the department's local choice is anchored to the global
          order, so local optima cannot silently drift from the telos (the user's 4th ask).
        • PROBLEMISTIC SEARCH (Cyert & March): an item whose latest outcome fell BELOW aspiration
          gets a search boost — a department works on what is failing against expectations, not on
          whatever is salient (defends against the garbage-can pathology).
        • SEQUENTIAL ATTENTION (March & Simon): items are chosen in RANK ORDER, one line at a time,
          not jointly "optimized" — the chosen set is a prefix, and the reason is recorded.
        • WIP LIMIT (ToC/Kanban): never select more concurrent work than the limit; capacity that
          is already in flight (started-not-completed) is subtracted first — pull, don't push.
      Emits attention_allocated with the ranked scores and the reason each item was picked/deferred
      — so "why did this dept do X before Y" is a ledger fact, and a choice that ignores the org
      ranking is visible (an auditable drift signal), not a silent local optimum.

Fail-quiet like the rest (docs/11 §0): a normal selection is a silent breadcrumb (exit 0); it
ESCALATES (exit 10) only when the department CANNOT serve the org's top priority from its backlog
at all (a coverage gap the CEO/registrar must close), or when WIP is saturated by stalled work.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK, read_events   # noqa: E402


def _current_ranking(events):
    """Return (objectives_by_id, ranking_id) for the latest priority_ranking_set, or ({}, None)."""
    latest = None
    for e in events:
        if e["class"] == "priority_ranking_set":
            latest = e["payload"]
    if not latest:
        return {}, None
    return ({o["objective_id"]: o for o in latest.get("ordered_objectives", [])},
            latest.get("ranking_id"))


def _backlog(events, role):
    """The role's open backlog: candidate_submitted items by this role not yet completed.
    Each item carries a contract_ref we read as its objective tag (contract -> objective)."""
    submitted = {}
    for e in events:
        if e["class"] == "candidate_submitted" and e["payload"].get("maker") == role:
            cid = e["payload"].get("candidate_id")
            submitted[cid] = {"candidate_id": cid,
                              "objective": e["payload"].get("contract_ref"),
                              "source": e["payload"].get("source", "self"),
                              "seq": e["seq"]}
    # remove items whose outcome already landed (deployed/retired) — they're done, not backlog
    done = set()
    for e in events:
        if e["class"] in ("result_deployed", "result_retired"):
            done.add(e["payload"].get("candidate_id"))
    return [it for cid, it in submitted.items() if cid not in done]


def _in_flight(events, role):
    """WIP already in flight: this role's cycle_started without a later cycle_completed."""
    started = completed = 0
    last_start = -1
    for e in events:
        if e["class"] == "cycle_started" and e["payload"].get("role") == role:
            started += 1; last_start = e["seq"]
        elif e["class"] == "cycle_completed" and e["payload"].get("role") == role:
            completed += 1
    return max(0, started - completed)


def _aspiration_gap(events, item, aspiration):
    """PROBLEMISTIC SEARCH: has this item's objective recently under-performed aspiration?
    We look for an outcome_delta or a below-aspiration observed_outcome tied to its objective."""
    boost = 0.0
    for e in events:
        if e["class"] == "outcome_delta" and e["payload"].get("department"):
            # a negative delta on this dept's work raises search priority near the problem
            if e["payload"].get("delta_sign", 0) < 0:
                boost = max(boost, 0.3)
        if e["class"] in ("result_deployed", "result_retired"):
            oo = e["payload"].get("observed_outcome")
            try:
                if oo is not None and float(oo) < aspiration:
                    boost = max(boost, 0.2)
            except (TypeError, ValueError):
                pass
    return boost


def cmd_select(a):
    events = read_events(a.root)
    role = a.role
    ranking, ranking_id = _current_ranking(events)
    backlog = _backlog(events, role)
    if not backlog:
        print(f"empty: {role} has no open backlog — nothing to select, silent.")
        print("LEDGER-EVENT " + json.dumps(
            {"class": "attention_allocated",
             "payload": {"role": role, "selected": [], "deferred": [],
                         "reason": "empty backlog"}}, ensure_ascii=False))
        return OK

    # SITUATED ATTENTION: score each item by the rank/weight of the objective it serves.
    # An item whose objective is NOT in the current ranking scores 0 on alignment — visible.
    scored = []
    for it in backlog:
        obj = it["objective"]
        r = ranking.get(obj)
        align = (r["weight"] if r and "weight" in r else 0.0)
        # lower rank number = higher priority; convert to a positive score component
        rank_score = (1.0 / r["rank"]) if r and r.get("rank") else 0.0
        boost = _aspiration_gap(events, it, a.aspiration)   # PROBLEMISTIC SEARCH
        base = align + rank_score + boost
        # ZONE OF ACCEPTANCE: a mandate whose objective IS in the ranking (inside the zone) is floored
        # to ride above self-generated work; a mandate off the ranking gets NO floor — it stays a
        # visible drift signal, never silently promoted (docs/12, Simon zone of acceptance).
        in_ranking = obj in ranking
        floored = (it.get("source") == "mandate" and in_ranking and base < a.mandate_floor)
        score = round(max(base, a.mandate_floor) if floored else base, 4)
        scored.append({**it, "align": align, "rank_score": round(rank_score, 4),
                       "problemistic_boost": boost, "score": score,
                       "mandate_floored": floored, "in_ranking": in_ranking})
    # SEQUENTIAL ATTENTION: rank order, pick a PREFIX up to the WIP limit (pull, don't push).
    scored.sort(key=lambda s: (-s["score"], s["seq"]))
    in_flight = _in_flight(events, role)
    room = max(0, a.wip_limit - in_flight)
    selected = scored[:room]
    deferred = scored[room:]

    payload = {"role": role, "wip_limit": a.wip_limit, "in_flight": in_flight,
               "ranking_id": ranking_id,
               "selected": [{"candidate_id": s["candidate_id"], "objective": s["objective"],
                             "score": s["score"], "in_ranking": s["in_ranking"],
                             "source": s.get("source", "self")} for s in selected],
               "deferred": [{"candidate_id": s["candidate_id"], "score": s["score"]}
                            for s in deferred],
               "reason": "situated-attention(align to org ranking) + problemistic-search boost + "
                         "mandate zone-of-acceptance floor, sequential prefix within WIP limit"}
    print("LEDGER-EVENT " + json.dumps({"class": "attention_allocated", "payload": payload},
                                       ensure_ascii=False))

    # report + escalation logic
    print(f"\n{role}: backlog {len(backlog)}, in-flight {in_flight}, WIP limit {a.wip_limit} "
          f"→ room {room}")
    for s in scored:
        tag = "▶ pick" if s in selected else "· defer"
        flag = "" if s["in_ranking"] else "  ⚠NOT IN ORG RANKING (drift signal)"
        print(f"  {tag} {s['candidate_id']:12} obj={str(s['objective'])[:16]:16} "
              f"score={s['score']:.3f} (align {s['align']:.2f} + rank {s['rank_score']:.2f} "
              f"+ problemistic {s['problemistic_boost']:.2f}){flag}")

    # ESCALATE: the dept cannot serve the org's TOP objective from its backlog at all
    top_obj = None
    if ranking:
        top_obj = min(ranking.values(), key=lambda o: o.get("rank", 1e9)).get("objective_id")
    serves_top = any(s["objective"] == top_obj for s in backlog) if top_obj else True
    if ranking and not serves_top:
        print(f"\nESCALATE: {role}'s backlog cannot serve the org's TOP objective "
              f"'{top_obj}' — a coverage gap only the registrar/CEO can close (activate work "
              f"or re-scope this dept). Local backlog is off the global priority.", file=sys.stderr)
        return ESCALATE
    if room == 0 and in_flight >= a.wip_limit:
        print(f"\nESCALATE: WIP saturated ({in_flight} in flight >= limit {a.wip_limit}) and "
              f"nothing completing — the dept is stuck, not choosing. Route to the common owner "
              f"(reconcile.py stall territory).", file=sys.stderr)
        return ESCALATE
    print("\nselected within WIP, anchored to the org ranking — silent breadcrumb.")
    return OK


def main(argv):
    p = argparse.ArgumentParser(prog="attention", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("select"); q.set_defaults(fn=cmd_select)
    q.add_argument("root"); q.add_argument("--role", required=True)
    q.add_argument("--wip-limit", dest="wip_limit", type=int, default=2)
    q.add_argument("--aspiration", type=float, default=0.5)
    # zone of acceptance (Simon 1947 / Barnard inducement-contribution, docs/12): a top-down MANDATE
    # rides above self-generated work at a floor score — but only INSIDE the acceptance zone. A
    # mandate whose objective is off the org ranking is OUTSIDE the zone and is NOT auto-floored; it
    # surfaces as a drift signal (and, if it is the sole coverage of the top objective, ESCALATEs).
    q.add_argument("--mandate-floor", dest="mandate_floor", type=float, default=1.0)
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
