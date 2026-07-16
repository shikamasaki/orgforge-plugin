#!/usr/bin/env python3
"""alignment — the proxy-stack guards: is the org still solving the right problem? (docs/13)

Three gaps a theory-coverage audit found, all of one family: a local optimizer perfecting a lossy
proxy while the real thing drifts, at three altitudes of the metric→goal→purpose→world stack. Prior
lenses looked at execution *seams*; none looked *up the proxy stack*. Each is a pure projection over
tools/ledger.py, fail-quiet, and preserves C3 — it SURFACES, the human DECIDES (telos/frame revision
is human-only). Ships no scheduler (R0).

  premise <root> --premise-id P --asserted V --observed V [--halt-on broken]
      PREMISE / TELOS-VALIDITY (the highest gap): nothing watches for the environmental shift that
      makes the PURPOSE itself obsolete — the market vanished, the problem got solved elsewhere. Every
      organ stays green while the org executes flawlessly against a dead telos ("correct machine, wrong
      problem"). The environment-side twin of guardrails.py reconcile (which checks belief-vs-assets;
      this checks belief-about-purpose-validity vs the world). The design assigns the human "revise
      purpose when the world changes" but gave no sensor to KNOW when — this is that sensor.
      Anchor: Weick (enactment), Aguilar (environmental scanning). Silent when premises hold; escalate
      weakened; charter-hold (not auto-anything) on broken — the human decides pivot/sunset.

  sunk <root> --course-id C --attempt-cap N [--cost-cap F]
      ESCALATION-OF-COMMITMENT / SUNK-COURSE (peer to BLAST-RADIUS-CAP): a running course of action
      never gets killed — a dept re-issues work against a failing approach, pouring compute into a
      branch whose outcomes aren't converging. OUTCOME-DELTA fires only on CLOSED decisions and only on
      recurrence; ALLOCATION-RECLAIM reclaims IDLE grants; DEPENDENCY-STALL catches a dept that STOPPED.
      This catches the opposite: a dept that WON'T stop. Anchor: Staw (1976, "Knee-deep in the Big
      Muddy"). Self-halt is the SAFE direction (abandoning is reversible — the ledger keeps the work);
      escalate only if the course is charter-scoped.

  frame <root> [--near-target-band F] [--min-decisions N]
      DOUBLE-LOOP / FRAME-REVIEW: OUTCOME-DELTA is single-loop — it joins predicted vs realized within
      a FIXED goal frame and never questions the goal/threshold itself. An org whose predictions are
      individually accurate against a target that is itself wrong drives confidently off a cliff (every
      delta small, nothing recurs). This SURFACES a candidate double-loop question — "assumption X
      generated N near-target decisions, yet the result it proxies is diverging" — and escalates
      charter-tier; it NEVER revises the frame (that's the human's, C3). Anchor: Argyris & Schön (1978).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK, read_events, emit_event   # noqa: E402


def cmd_premise(a):
    """PREMISE: diff an asserted founding premise against an observed ground-truth snapshot."""
    # observed is supplied by the calling agent (the tool does NO scanning itself — enactment is
    # the agent's job; this records and judges). status: holds | weakened | broken.
    asserted, observed = a.asserted, a.observed
    try:
        af, of = float(asserted), float(observed)
        drift = abs(of - af) / (abs(af) if af else 1)
        status = "holds" if drift < 0.1 else "weakened" if drift < 0.5 else "broken"
    except (TypeError, ValueError):
        status = "holds" if asserted == observed else "broken"
    payload = {"premise_id": a.premise_id, "asserted": asserted, "observed": observed,
               "status": status}
    emit_event("premise_reconciled", payload)
    if status == "holds":
        print(f"holds: premise '{a.premise_id}' still matches the world ({observed}) — silent. "
              f"The telos rests on a live premise.")
        return OK
    if status == "broken":
        print(f"BROKEN: premise '{a.premise_id}' asserted {asserted} but the world shows "
              f"{observed} — the PURPOSE may be obsolete ('correct machine, wrong problem'). This "
              f"is charter-hold: the org does NOT auto-pivot; it surfaces the one essential "
              f"decision (pivot / sunset — moves.yaml) to the human, with the evidence. Every "
              f"other organ can be green and this still fires.", file=sys.stderr)
        return ESCALATE
    print(f"WEAKENED: premise '{a.premise_id}' drifting ({asserted} -> {observed}) — escalate a "
          f"watch, not yet a pivot. The founding premise is eroding.", file=sys.stderr)
    return ESCALATE


def cmd_sunk(a):
    """SUNK-COURSE: count accumulated attempts + outcome trend for an OPEN course."""
    events = read_events(a.root)
    attempts = 0
    outcomes = []
    still_open = True
    cost = 0.0
    for e in events:
        p = e.get("payload", {})
        cid = p.get("candidate_id") or p.get("claim_id") or p.get("course_id")
        if cid != a.course_id:
            continue
        if e["class"] in ("candidate_submitted", "refutation_attempted", "cycle_completed"):
            attempts += 1
            t = p.get("tokens", {})
            if isinstance(t, dict):
                cost += sum(v for v in t.values() if isinstance(v, (int, float)))
        if e["class"] in ("result_deployed", "result_retired"):
            still_open = False        # the course closed — sunk-course is about OPEN courses
        oo = p.get("observed_outcome")
        if oo is not None:
            try:
                outcomes.append(float(oo))
            except (TypeError, ValueError):
                pass
    # converging? outcomes trending up = making progress; flat/down while attempts pile = sunk
    improving = len(outcomes) >= 2 and outcomes[-1] > outcomes[0]
    over_attempts = attempts > a.attempt_cap
    over_cost = a.cost_cap is not None and cost > a.cost_cap
    payload = {"course_id": a.course_id, "attempts": attempts, "cost": cost,
               "outcome_trend": ("improving" if improving else "flat_or_worse"),
               "still_open": still_open,
               "decision": "continue" if (improving or not (over_attempts or over_cost)) else "abandon"}
    emit_event("sunk_course_reviewed", payload)
    if not still_open:
        print(f"closed: course '{a.course_id}' already closed — not a sunk-course concern.")
        return OK
    if improving or not (over_attempts or over_cost):
        print(f"continue: course '{a.course_id}' — {attempts} attempts, "
              f"{'improving' if improving else 'within caps'} — no runaway, silent.")
        return OK
    print(f"ABANDON: course '{a.course_id}' has {attempts} attempts (cap {a.attempt_cap}), cost "
          f"{cost} — outcomes flat-or-worse while still consuming. Self-halt in the SAFE direction "
          f"(abandon is reversible — the ledger keeps the work); escalate only if charter-scoped. "
          f"This is the runaway BLAST-RADIUS-CAP can't see (that's aggregate; this is one course "
          f"outrunning its own progress).", file=sys.stderr)
    return ESCALATE


def cmd_frame(a):
    """FRAME-REVIEW: surface a double-loop question — accurate predictions against a drifting target."""
    events = read_events(a.root)
    # a "near-target" decision: admission_decided(admit) whose predicted ~= observed (small delta),
    # i.e. single-loop is HAPPY. But if the aggregate RESULT those decisions proxy is trending away,
    # the frame itself may be wrong. We approximate "the result" as the mean observed_outcome trend.
    near_target = 0
    observed_series = []
    for e in events:
        if e["class"] == "admission_decided" and e["payload"].get("verdict") == "admit":
            po = e["payload"].get("predicted_outcome")
            # find the matching realized outcome
            cid = e["payload"].get("candidate_id")
            for e2 in events:
                if e2["class"] in ("result_deployed", "result_retired") \
                        and e2["payload"].get("candidate_id") == cid:
                    oo = e2["payload"].get("observed_outcome")
                    try:
                        if po is not None and oo is not None and abs(float(oo) - float(po)) <= a.near_target_band:
                            near_target += 1
                            observed_series.append(float(oo))
                    except (TypeError, ValueError):
                        pass
    if near_target < a.min_decisions:
        print(f"insufficient: only {near_target} near-target decisions (< {a.min_decisions}) — "
              f"no frame-review signal yet, silent.")
        return OK
    # the frame is suspect if predictions are ACCURATE (near_target high) but the RESULT they
    # proxy is DRIFTING (observed series trending down despite hitting predictions)
    drifting = len(observed_series) >= 2 and observed_series[-1] < observed_series[0]
    payload = {"near_target_decisions": near_target,
               "result_trend": "drifting" if drifting else "stable",
               "question": "predictions accurate against a target that may itself be wrong"
                           if drifting else None}
    emit_event("frame_review_raised", payload)
    if not drifting:
        print(f"stable: {near_target} accurate predictions AND the result they proxy is stable "
              f"— the frame holds, silent.")
        return OK
    print(f"FRAME-REVIEW: {near_target} predictions were ACCURATE, yet the result they proxy is "
          f"DRIFTING down — the error may be in the GOAL FRAME, not the execution (single-loop is "
          f"happy; double-loop is not). Surfaces a charter-tier question to the human; does NOT "
          f"revise the frame itself (C3). This is the failure OUTCOME-DELTA is structurally blind "
          f"to.", file=sys.stderr)
    return ESCALATE


def main(argv):
    p = argparse.ArgumentParser(prog="alignment", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("premise"); q.set_defaults(fn=cmd_premise)
    q.add_argument("root"); q.add_argument("--premise-id", dest="premise_id", required=True)
    q.add_argument("--asserted", required=True); q.add_argument("--observed", required=True)
    q.add_argument("--halt-on")

    q = sub.add_parser("sunk"); q.set_defaults(fn=cmd_sunk)
    q.add_argument("root"); q.add_argument("--course-id", dest="course_id", required=True)
    q.add_argument("--attempt-cap", dest="attempt_cap", type=int, default=5)
    q.add_argument("--cost-cap", dest="cost_cap", type=float)

    q = sub.add_parser("frame"); q.set_defaults(fn=cmd_frame)
    q.add_argument("root")
    q.add_argument("--near-target-band", dest="near_target_band", type=float, default=0.1)
    q.add_argument("--min-decisions", dest="min_decisions", type=int, default=3)

    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
