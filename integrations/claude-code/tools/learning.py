#!/usr/bin/env python3
"""learning — the org learning from its OWN outcomes (docs/05 §5.4, OUTCOME-DELTA).

The doctrine organ (docs/06) imports EXTERNAL best-practice and is, by explicit design,
structurally blind to THIS org's own miscalibration. Without a self-outcome event the org
repeats its own mistakes forever — nothing converts "our prediction was wrong" into a durable,
injectable fact. This tool joins closed decisions to their realized outcomes and emits an
outcome_delta ONLY when the miss is large or recurrent; it escalates to the CEO only when the
SAME delta class recurs past a systemic threshold ("how we operate is wrong"), never on a
single miss. It is distinct from doctrine: doctrine is the outside world, this is the org's
own track record. Pure projection over tools/ledger.py; ships no scheduler (R0).

  delta <root> [--threshold F] [--recurrence N]   join decisions to outcomes; emit deltas past
      threshold; escalate only a delta CLASS that recurs >= N times (systemic).

  repeats <root> [--recurrence N]   REPEATED-DEATH detector: escalate a death cause that reappears
      on a later candidate (>= N times) — the org re-made a mistake it had already recorded, i.e.
      accumulated learning was NOT fed forward. The direct measure of "learning lifts quality."

A "decision" is an admission_decided (verdict admit) carrying a predicted_outcome in its
payload; its "realized outcome" is a later result_deployed / result_retired for the same
candidate_id carrying an observed_outcome. The delta is |predicted - observed|. Silent when
predictions matched (the default — no event at all).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK, read_events, emit_event   # noqa: E402


def cmd_delta(a):
    events = read_events(a.root)
    # index predictions by candidate_id, from admission_decided(admit) with a predicted_outcome
    predicted = {}
    for e in events:
        if e["class"] == "admission_decided" and e["payload"].get("verdict") == "admit":
            cid = e["payload"].get("candidate_id")
            po = e["payload"].get("predicted_outcome")
            if cid is not None and po is not None:
                predicted[cid] = {"value": po, "seq": e["seq"],
                                  "dept": e["payload"].get("gate")}
    # realized outcomes from result_deployed / result_retired carrying observed_outcome
    deltas = []
    for e in events:
        if e["class"] in ("result_deployed", "result_retired"):
            cid = e["payload"].get("candidate_id")
            oo = e["payload"].get("observed_outcome")
            if cid in predicted and oo is not None:
                pred = predicted[cid]["value"]
                try:
                    mag = abs(float(oo) - float(pred))
                    sign = 1 if float(oo) > float(pred) else -1 if float(oo) < float(pred) else 0
                except (TypeError, ValueError):
                    mag = 0 if oo == pred else 1
                    sign = 0
                if mag > a.threshold:
                    deltas.append({"decision_event_id": predicted[cid]["seq"],
                                   "candidate_id": cid,
                                   "predicted_outcome": pred, "observed_outcome": oo,
                                   "delta_magnitude": mag, "delta_sign": sign,
                                   "department": predicted[cid]["dept"],
                                   "hypothesized_cause": e["payload"].get("cause")})
    if not deltas:
        print("matched: every closed decision's outcome matched its prediction within "
              f"threshold {a.threshold} — silent, no event.")
        return OK
    # recurrence: same department + same sign is a "delta class"; count occurrences
    klass = {}
    for d in deltas:
        k = (d["department"], d["delta_sign"])
        klass.setdefault(k, []).append(d)
    escalate = False
    for d in deltas:
        rc = len(klass[(d["department"], d["delta_sign"])])
        d["recurrence_count"] = rc
        emit_event("outcome_delta", d)
        if rc >= a.recurrence:
            escalate = True
    if escalate:
        systemic = [k for k, v in klass.items() if len(v) >= a.recurrence]
        print(f"SYSTEMIC: {len(deltas)} outcome delta(s); classes {systemic} recurred >= "
              f"{a.recurrence} times — 'how we operate is wrong', escalate to the CEO. This is "
              f"the org learning from ITS OWN track record, not the outside world (that's "
              f"doctrine).", file=sys.stderr)
        return ESCALATE
    print(f"noted: {len(deltas)} outcome delta(s) past threshold, none recurring >= "
          f"{a.recurrence} — recorded as injectable facts, no CEO traffic yet.")
    return OK


def cmd_repeats(a):
    """REPEATED-DEATH detector — the direct measure of whether accumulated learning is actually USED.
    A death (a result_retired / a refutation that failed) carries a `cause`. If the SAME cause reappears
    on a LATER candidate, the org failed to feed its own lesson forward — it re-made a mistake it had
    already recorded (the org's core purpose, missed). This escalates a cause that recurs >= --recurrence
    times, naming the deaths, so "learning lifts quality" is a checked fact, not a hope. Silent when every
    death cause is distinct (no lesson was ignored)."""
    events = read_events(a.root)
    by_cause = {}
    for e in events:
        p = e.get("payload", {})
        cause = None
        if e["class"] == "result_retired":
            cause = p.get("cause") or p.get("hypothesized_cause")
        elif e["class"] == "refutation_attempted" and p.get("verdict") == "refuted":
            cause = p.get("cause") or p.get("checklist_ref")
        if cause:
            key = str(cause).strip().lower()
            by_cause.setdefault(key, []).append({"seq": e["seq"], "cause": cause,
                                                 "candidate_id": p.get("candidate_id")})
    repeated = {c: hits for c, hits in by_cause.items() if len(hits) >= a.recurrence}
    if not repeated:
        print(f"clean: no death cause recurred >= {a.recurrence} times — accumulated learning is being "
              f"used, no known mistake re-made. Silent.")
        return OK
    for cause, hits in sorted(repeated.items(), key=lambda kv: -len(kv[1])):
        emit_event("repeated_death_detected", {
            "cause": hits[0]["cause"], "occurrences": len(hits),
            "candidate_ids": [h["candidate_id"] for h in hits]})
    worst = max(repeated.items(), key=lambda kv: len(kv[1]))
    print(f"REPEATED DEATH: cause {worst[1][0]['cause']!r} recurred {len(worst[1])} times "
          f"(candidates {[h['candidate_id'] for h in worst[1]]}) — the org re-made a mistake it had "
          f"already recorded. Accumulated learning was NOT fed forward; strengthen the death into "
          f"doctrine and inject it before the next attempt (docs/06). This is the org's core purpose "
          f"failing — escalate.", file=sys.stderr)
    return ESCALATE


def main(argv):
    p = argparse.ArgumentParser(prog="learning", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("delta"); q.set_defaults(fn=cmd_delta)
    q.add_argument("root")
    q.add_argument("--threshold", type=float, default=0.2)
    q.add_argument("--recurrence", type=int, default=3)
    q = sub.add_parser("repeats"); q.set_defaults(fn=cmd_repeats)
    q.add_argument("root")
    q.add_argument("--recurrence", type=int, default=2)
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
