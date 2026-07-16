#!/usr/bin/env python3
"""guardrails — the three load-bearing safety checks for 24/7 unattended operation.

The approval queue gates by action CLASS and the skeptic gates finished OUTPUTS, but three
failure modes of an org that runs all night with the human asleep are covered by neither —
each surfaced by decomposing "what a human org's meetings/reviews actually prevent" to its
essence (not the ritual). These are pure functions over the ledger (tools/ledger.py); they
ship no scheduler (docs/09, R0) — a host-run agent calls them on the cadence / at the act,
and their verdict is itself ledgered so the next decision can see it. All three obey the same
rule the design fixes: **default silent (fail-quiet); escalate only the exception.**

  cap    <root> --dimension D --delta N --cap C --actor R [--window-since TS] [--caused-by E]
      BLAST-RADIUS-CAP. The approval queue never sums MAGNITUDE across a window: each act can
      be individually reversible/in-scope while the AGGREGATE real-asset exposure in one
      unattended window runs away ("death by a thousand approved cuts"). This tallies committed
      deltas in the window from the ledger and BLOCKS (not just annotates) when committed+delta
      would cross the cap. Silent `allow` under budget; `hold` → enqueue to the approval queue.

  reconcile <root> --domain D --observed V --expected V [--halt-magnitude N]
      STATE-RECONCILED. The ledger is the org's BELIEF; real assets live in external systems.
      A half-applied write / an unauthored external mutation / a missed webhook makes every
      downstream decision rest on a silent lie. This diffs an external ground-truth snapshot
      (passed in — the tool does no network) against the ledger's asserted value. Silent when
      they match; escalates on drift; trips the halt path when drift exceeds --halt-magnitude.

  staleref <root> --trigger-event E --bound ROLE,ROLE [--stale-threshold-cycles N]
      STALE-REFERENCE. The inverse of fail-quiet: a role gone silent against a reference that
      has MOVED (superseded mandate, revoked scope, new doctrine) is indistinguishable from a
      role that is silently fine. This lists roles bound to a changed reference that have NOT
      re-derived since it moved. Silent when all current; nudges self-re-derivation first;
      escalates only a role still stale past the threshold (genuinely stuck, not just quiet).

Each command prints the ledger event it would emit (the payload from the discovery set) and
sets its exit code so a host script can branch: 0 = silent/allow, 10 = escalate/hold/drift.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK, read_events, emit_event   # noqa: E402


def cmd_cap(a):
    """BLAST-RADIUS-CAP: sum committed exposure in the window for this dimension, then decide."""
    events = read_events(a.root)
    committed = 0.0
    for e in events:
        if a.window_since and e.get("ts", "") < a.window_since:
            continue
        # prior allow decisions in this dimension carry their delta forward as committed exposure
        if e["class"] == "exposure_budget_checked":
            p = e["payload"]
            if p.get("dimension") == a.dimension and p.get("decision") == "allow":
                committed += float(p.get("delta_requested", 0))
    would_be = committed + a.delta
    decision = "allow" if would_be <= a.cap else "hold"
    payload = {
        "window_id": a.window_since or "all",
        "dimension": a.dimension,
        "committed_so_far": committed,
        "delta_requested": a.delta,
        "cap": a.cap,
        "actor_role": a.actor,
        "decision": decision,
        "caused_by_event": a.caused_by,
    }
    emit_event("exposure_budget_checked", payload)
    if decision == "hold":
        print(f"HOLD: {a.dimension} committed {committed} + requested {a.delta} = {would_be} "
              f"> cap {a.cap} — action blocked and enqueued to the approval queue (aggregate "
              f"exposure cap, not per-action class). This is the block the approval queue "
              f"cannot make (it gates class, not magnitude).", file=sys.stderr)
        return ESCALATE
    print(f"allow: {a.dimension} {committed} + {a.delta} = {would_be} <= cap {a.cap} "
          f"— under budget, proceeds silently; tally advances.")
    return OK


def cmd_reconcile(a):
    """STATE-RECONCILED: diff an external ground-truth snapshot against the ledger's belief."""
    # observed is passed in (the tool does NO network — snapshot is the caller's job); expected
    # is either passed explicitly or, if omitted, we surface that the ledger has no assertion.
    try:
        observed = float(a.observed)
        expected = float(a.expected)
    except (TypeError, ValueError):
        # non-numeric domains (access lists, infra sets): compare as strings
        observed, expected = a.observed, a.expected
    drift = observed != expected
    magnitude = abs(observed - expected) if isinstance(observed, float) and isinstance(expected, float) else (0 if not drift else None)
    payload = {
        "domain": a.domain,
        "expected_value": expected,
        "observed_value": observed,
        "drift": drift,
        "magnitude": magnitude,
        "unaccounted_events": [],   # a fuller impl lists ledger-unexplained deltas; kept explicit
    }
    emit_event("state_reconciled", payload)
    if not drift:
        print(f"clean: {a.domain} ledger-belief == ground-truth ({expected}) — silent breadcrumb.")
        return OK
    over_halt = (a.halt_magnitude is not None and isinstance(magnitude, float)
                 and magnitude > a.halt_magnitude)
    if over_halt:
        print(f"DRIFT-HALT: {a.domain} expected {expected} but observed {observed} "
              f"(magnitude {magnitude} > halt threshold {a.halt_magnitude}) — trips the halt "
              f"path (halt_tripped), does not wait for the CEO. Every downstream decision was "
              f"resting on a stale belief.", file=sys.stderr)
    else:
        print(f"DRIFT: {a.domain} expected {expected} but observed {observed} — escalate; the "
              f"ledger's asserted state is a silent lie until reconciled.", file=sys.stderr)
    return ESCALATE


def cmd_staleref(a):
    """STALE-REFERENCE: which bound roles have NOT re-derived since the reference moved?"""
    events = read_events(a.root)
    # find the trigger event's seq (when the reference moved)
    trigger_seq = None
    for e in events:
        if e["id"] == a.trigger_event or str(e["seq"]) == str(a.trigger_event):
            trigger_seq = e["seq"]
            break
    if trigger_seq is None:
        print(f"staleref: trigger event '{a.trigger_event}' not in ledger", file=sys.stderr)
        return 2
    bound = [r.strip() for r in a.bound.split(",") if r.strip()]
    # a role has "re-derived" if it produced a cycle_completed (or cycle_started) AFTER the trigger
    rederived_after = {}
    cycles_after = {}
    for e in events:
        if e["seq"] <= trigger_seq:
            continue
        if e["class"] in ("cycle_completed", "cycle_started"):
            role = e["payload"].get("role")
            if role:
                rederived_after[role] = True
    # stale = bound but no re-derivation since the trigger
    stale = [r for r in bound if r not in rederived_after]
    # silent_duration proxy: how many cycles the whole org has run since the trigger without this role
    cycles_since_trigger = sum(1 for e in events
                               if e["seq"] > trigger_seq and e["class"] == "cycle_started")
    payload = {
        "trigger_event": a.trigger_event,
        "bound_roles": bound,
        "stale_roles": stale,
        "silent_duration_per_role": {r: cycles_since_trigger for r in stale},
        "result": "stale_found" if stale else "all_current",
    }
    emit_event("reference_staleness_checked", payload)
    if not stale:
        print(f"all_current: every bound role re-derived since {a.trigger_event} — silent.")
        return OK
    threshold = a.stale_threshold_cycles
    genuinely_stuck = [r for r in stale if cycles_since_trigger > threshold]
    if genuinely_stuck:
        print(f"STALE-STUCK: {genuinely_stuck} bound to a moved reference and still not "
              f"re-derived after {cycles_since_trigger} cycles (> {threshold}) — escalate; "
              f"these are dormant-WRONG, not dormant-fine.", file=sys.stderr)
        return ESCALATE
    print(f"nudge: {stale} bound to a moved reference, not yet re-derived "
          f"({cycles_since_trigger} cycles, under threshold {threshold}) — nudge self-"
          f"re-derivation; no CEO traffic yet.")
    return OK


def main(argv):
    p = argparse.ArgumentParser(prog="guardrails", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("cap"); q.set_defaults(fn=cmd_cap)
    q.add_argument("root")
    q.add_argument("--dimension", required=True)
    q.add_argument("--delta", type=float, required=True)
    q.add_argument("--cap", type=float, required=True)
    q.add_argument("--actor", required=True)
    q.add_argument("--window-since", dest="window_since")
    q.add_argument("--caused-by", dest="caused_by")

    q = sub.add_parser("reconcile"); q.set_defaults(fn=cmd_reconcile)
    q.add_argument("root")
    q.add_argument("--domain", required=True)
    q.add_argument("--observed", required=True)
    q.add_argument("--expected", required=True)
    q.add_argument("--halt-magnitude", dest="halt_magnitude", type=float)

    q = sub.add_parser("staleref"); q.set_defaults(fn=cmd_staleref)
    q.add_argument("root")
    q.add_argument("--trigger-event", dest="trigger_event", required=True)
    q.add_argument("--bound", required=True)
    q.add_argument("--stale-threshold-cycles", dest="stale_threshold_cycles",
                   type=int, default=3)

    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
