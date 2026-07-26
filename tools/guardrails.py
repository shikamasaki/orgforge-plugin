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

  cycles <root> --role R [--max-cycles N] [--max-tokens N] [--window-since TS]
      ITERATION/SPEND-CAP. The blast-radius cap meters irreversible ASSET effect; it cannot see a
      role's loop spinning on reversible reads/edits. This sums the role's cycle_started count and
      reported tokens in the window and HOLDs when either would exceed its cap — killing a runaway
      early ("$3-5, not $180") in the enforcement layer, not via a role-settings 'please stop at N'.

  stall <root> --candidate-id C [--role R] [--repeat-threshold N] [--stall-threshold N]
      CIRCUIT-BREAKER on non-progress. A wedged cycle burns its WIP slot and budget until a human
      notices. This reads a candidate's progress_recorded stream and TRIPS when the same next_step
      repeats N times (identical-output) or `fraction` fails to advance for N checkpoints — flag for
      a human and free the slot, don't respawn the wedged cycle. Silent while progressing.

  rollback <root> --action-ref R [--undo TXT]
      PROVEN-ROLLBACK. The silence-consent tier trusts "reversible" — but a reversibility claim with
      no declared undo is untested. Escalates a reversible action that declares no undo/compensation;
      silent when the undo is present (the host runs the undo dry-run to fully prove recovery).

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


def cmd_cycles(a):
    """ITERATION/SPEND-CAP: a role's loop cycles and cumulative tokens are a RUNAWAY dimension the
    blast-radius cap does not cover — a reversible read-think-edit loop touches no metered asset yet
    can spin forever ("endless file-reading loop"). This sums the role's cycle_started count and
    reported tokens in the window and HOLDS when either would exceed its cap, so a runaway is killed
    early ("$3-5, not $180"). docs/16 §1 / docs/17 §5 #2: a hard iteration/spend cap belongs in the
    enforcement layer, not a role-settings 'please stop at N' the host must honor."""
    events = read_events(a.root)
    cycles = 0
    tokens = 0.0
    for e in events:
        if a.window_since and e.get("ts", "") < a.window_since:
            continue
        p = e.get("payload", {})
        if e["class"] == "cycle_started" and p.get("role") == a.role:
            cycles += 1
        elif e["class"] == "cycle_completed" and p.get("role") == a.role:
            tk = p.get("tokens") or {}
            if isinstance(tk, dict):
                tokens += sum(float(v) for v in tk.values() if isinstance(v, (int, float)))
    over_cycles = a.max_cycles is not None and (cycles + 1) > a.max_cycles
    over_tokens = a.max_tokens is not None and tokens > a.max_tokens
    decision = "hold" if (over_cycles or over_tokens) else "allow"
    reason = ("cycle count" if over_cycles else "token spend") if decision == "hold" else ""
    payload = {"window_id": a.window_since or "all", "role": a.role,
               "cycles_so_far": cycles, "tokens_so_far": tokens,
               "max_cycles": a.max_cycles, "max_tokens": a.max_tokens,
               "decision": decision, "limiting": reason}
    emit_event("iteration_budget_checked", payload)
    if decision == "hold":
        detail = (f"{cycles} cycles >= max {a.max_cycles}" if over_cycles
                  else f"{tokens:.0f} tokens > max {a.max_tokens}")
        print(f"HOLD: role '{a.role}' hit its {reason} cap ({detail}) — the loop is killed at the "
              f"budget, not left to spin. Raise --max-cycles/--max-tokens or let a human intervene. "
              f"This is the runaway kill the blast-radius cap can't make (docs/17 §5).",
              file=sys.stderr)
        return ESCALATE
    print(f"allow: role '{a.role}' {cycles} cycles / {tokens:.0f} tokens — under budget.")
    return OK


def cmd_stall(a):
    """CIRCUIT-BREAKER on non-progress (docs/17 §5 #3). A wedged cycle consumes its WIP slot and budget
    until a human notices — the most common real failure (wrong-solution loops). This reads a candidate's
    progress_recorded stream and TRIPS (escalate) when it is not advancing: either the same next_step/
    done_so_far repeated `--repeat-threshold` times in a row (AgentMesh's identical-output heuristic), or
    `--stall-threshold` consecutive checkpoints with no increase in `fraction`. Trips OPEN → the cycle is
    flagged for a human and its slot should be freed, rather than left to spin. Silent while progressing."""
    events = read_events(a.root)
    checkpoints = [e["payload"] for e in events
                   if e["class"] == "progress_recorded"
                   and e["payload"].get("candidate_id") == a.candidate_id]
    if len(checkpoints) < 2:
        print(f"progressing: candidate '{a.candidate_id}' has <2 checkpoints — nothing to judge, silent.")
        return OK
    # identical-output run: how many trailing checkpoints share the same (next_step, done_so_far)?
    def sig(p):
        return (str(p.get("next_step", "")).strip(), str(p.get("done_so_far", "")).strip())
    last_sig = sig(checkpoints[-1])
    repeat = 0
    for p in reversed(checkpoints):
        if sig(p) == last_sig:
            repeat += 1
        else:
            break
    # fraction non-advance: trailing checkpoints whose fraction did not increase
    def frac(p):
        try:
            return float(p.get("fraction"))
        except (TypeError, ValueError):
            return None
    no_advance = 0
    peak = -1.0
    for p in checkpoints:
        f = frac(p)
        if f is None:
            continue
        if f > peak:
            peak = f
            no_advance = 0
        else:
            no_advance += 1
    tripped = repeat >= a.repeat_threshold or no_advance >= a.stall_threshold
    why = ("identical output ×%d" % repeat if repeat >= a.repeat_threshold
           else "fraction flat ×%d" % no_advance) if tripped else ""
    emit_event("stall_breaker_checked", {
        "candidate_id": a.candidate_id, "role": a.role, "checkpoints": len(checkpoints),
        "repeat_run": repeat, "no_advance_run": no_advance,
        "decision": "trip" if tripped else "ok", "reason": why})
    if tripped:
        print(f"TRIP: candidate '{a.candidate_id}' is not progressing ({why}). The circuit breaker "
              f"opened — flag for a human and FREE its WIP slot; do not respawn the same wedged cycle. "
              f"Its last next_step: {checkpoints[-1].get('next_step','(none)')!r} (docs/17 §5).",
              file=sys.stderr)
        return ESCALATE
    print(f"progressing: candidate '{a.candidate_id}' advancing "
          f"({len(checkpoints)} checkpoints, repeat {repeat}, flat {no_advance}) — silent.")
    return OK


def cmd_rollback(a):
    """PROVEN-ROLLBACK (docs/11 §4, docs/17 §5). The silence-is-consent tier lets a REVERSIBLE action
    proceed unattended — but "reversible" claimed and never tested is not reversibility, it is a latent
    lie. This asserts a reversible-classified action carries a declared, non-empty undo (its rollback
    command / compensation ref). It does NOT execute the undo (R0 — the host runs commands); it makes an
    UNTESTED reversibility claim a hard error at the point it would be trusted, so an org can't lean on
    silence-consent for an action whose rollback it never named. Escalates a reversible action with no
    undo declared; silent when the undo is present."""
    if not (a.undo or "").strip():
        emit_event("rollback_unproven", {"action_ref": a.action_ref, "reason": "no undo declared"})
        print(f"UNPROVEN: reversible action '{a.action_ref}' declares no undo/compensation — a "
              f"reversibility claim with no rollback is untested and must not ride silence-as-consent. "
              f"Declare its undo (--undo) or treat it as IRREVERSIBLE (full approval). (docs/11 §4)",
              file=sys.stderr)
        return ESCALATE
    emit_event("rollback_declared", {"action_ref": a.action_ref, "undo": a.undo})
    print(f"proven: reversible action '{a.action_ref}' carries a declared undo — the silence-consent "
          f"tier may trust it. (Run the undo dry-run in the host to fully prove recovery.)")
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


# event classes that MOVE a reference roles are bound to — the auto-trigger set (docs/11 §2.3,
# docs/12 §3.1). When one lands, the roles bound to that reference must re-derive.
REFERENCE_CHANGE_CLASSES = ("priority_ranking_set", "doctrine_diff_admitted",
                            "scope_grant_changed", "intent_revised")


def _auto_trigger_and_bound(events):
    """Derive (trigger_event_id, bound_roles) from the ledger instead of taking them as args —
    the wiring docs/11 §2.3/§12 §3.1 imply. The trigger is the latest reference-change event;
    the bound roles are those the change affects, read from the event payload where the schema
    carries them (doctrine_diff_admitted.role; scope_grant_changed via grantor's scope; a
    priority/intent change binds every role that has run a cycle — all of them re-rank)."""
    latest = None
    for e in events:
        if e["class"] in REFERENCE_CHANGE_CLASSES:
            latest = e
    if latest is None:
        return None, []
    cls, p = latest["class"], latest.get("payload", {})
    if cls == "doctrine_diff_admitted":
        bound = [p["role"]] if p.get("role") else []
    else:
        # a ranking/intent/scope change binds every role that has been active (produced a cycle)
        bound = sorted({e["payload"].get("role") for e in events
                        if e["class"] in ("cycle_started", "cycle_completed")
                        and e["payload"].get("role")})
    return latest["id"], bound


def cmd_staleref(a):
    """STALE-REFERENCE: which bound roles have NOT re-derived since the reference moved?
    With --auto, the trigger event and bound roles are DERIVED from the ledger (the latest
    reference-change event + the roles it affects) instead of passed in — closing the
    manual-input gap the docs' 'event-triggered by any reference change' implied."""
    events = read_events(a.root)
    if getattr(a, "auto", False):
        a.trigger_event, auto_bound = _auto_trigger_and_bound(events)
        if a.trigger_event is None:
            print("staleref --auto: no reference-change event in the ledger yet — nothing bound.")
            return OK
        a.bound = a.bound or ",".join(auto_bound)
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


# action classes whose effect is IRREVERSIBLE — a backlog item that triggers one of these
# cannot ride "silence = consent"; it drops to the irreversible-hold tier (docs/06 §2.1). The
# reversible default (re-ordering, in-workspace work) flows silently. This mirrors the blast-
# radius classifier's reversibility split (docs/11 §2.1), applied to priority instead of tools.
IRREVERSIBLE_ACTION_CLASSES = {
    "deploy", "production_deploy", "release", "publish", "spend", "payment", "transfer",
    "external_write", "destructive_migration", "drop", "delete_data", "send_external",
    "credential_use", "force_push",
}


def cmd_consent(a):
    """SILENCE-CONSENT: may this backlog action proceed on silence, or must it hold for an
    explicit human ack? Reversible actions (re-prioritization, in-workspace work) ride the
    delegated tier — silence is consent, they proceed (OK). An irreversible action_class drops
    to the irreversible-hold tier and REQUIRES an explicit ack — silence is NOT consent for it
    (ESCALATE). This is docs/06 §2.1 as code: 'no meeting' never means 'no gate on the few
    actions that can't be undone'."""
    ac = (a.action_class or "").strip().lower()
    reversible = ac not in IRREVERSIBLE_ACTION_CLASSES
    tier = "delegated" if reversible else "irreversible"
    payload = {"action_class": ac or "(unspecified)", "item_ref": a.item_ref,
               "reversible": reversible, "tier": tier,
               "decision": "silence_is_consent" if reversible else "explicit_ack_required"}
    emit_event("consent_decided", payload)
    if reversible:
        print(f"silence=consent: '{ac or 'unspecified'}' is reversible ({a.item_ref}) — "
              f"proceeds on the delegated tier, no ack needed.")
        return OK
    print(f"HOLD: '{ac}' is irreversible ({a.item_ref}) — silence is NOT consent; requires an "
          f"explicit human ack (irreversible-hold tier, docs/06 §2.1).", file=sys.stderr)
    return ESCALATE


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

    q = sub.add_parser("cycles"); q.set_defaults(fn=cmd_cycles)
    q.add_argument("root")
    q.add_argument("--role", required=True)
    q.add_argument("--max-cycles", dest="max_cycles", type=int)
    q.add_argument("--max-tokens", dest="max_tokens", type=float)
    q.add_argument("--window-since", dest="window_since")

    q = sub.add_parser("stall"); q.set_defaults(fn=cmd_stall)
    q.add_argument("root")
    q.add_argument("--candidate-id", dest="candidate_id", required=True)
    q.add_argument("--role", default="")
    q.add_argument("--repeat-threshold", dest="repeat_threshold", type=int, default=2)
    q.add_argument("--stall-threshold", dest="stall_threshold", type=int, default=3)

    q = sub.add_parser("rollback"); q.set_defaults(fn=cmd_rollback)
    q.add_argument("root")
    q.add_argument("--action-ref", dest="action_ref", required=True)
    q.add_argument("--undo", default="")

    q = sub.add_parser("reconcile"); q.set_defaults(fn=cmd_reconcile)
    q.add_argument("root")
    q.add_argument("--domain", required=True)
    q.add_argument("--observed", required=True)
    q.add_argument("--expected", required=True)
    q.add_argument("--halt-magnitude", dest="halt_magnitude", type=float)

    q = sub.add_parser("staleref"); q.set_defaults(fn=cmd_staleref)
    q.add_argument("root")
    q.add_argument("--trigger-event", dest="trigger_event")   # not required when --auto derives it
    q.add_argument("--bound")                                 # not required when --auto derives it
    q.add_argument("--auto", action="store_true",
                   help="derive the trigger event + bound roles from the ledger's latest "
                        "reference-change event (docs/11 §2.3) instead of passing them in")
    q.add_argument("--stale-threshold-cycles", dest="stale_threshold_cycles",
                   type=int, default=3)

    q = sub.add_parser("consent"); q.set_defaults(fn=cmd_consent)
    q.add_argument("root")
    q.add_argument("--action-class", dest="action_class", required=True,
                   help="the downstream action a backlog item would trigger (deploy/spend/... "
                        "are irreversible; everything else rides silence=consent)")
    q.add_argument("--item-ref", dest="item_ref", default="(unspecified)")

    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
