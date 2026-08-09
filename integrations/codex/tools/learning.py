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

  profile <root>   emit an observation-only WAI/WAR/WAD profile. It never infers WAD,
                   promotes doctrine, or assigns a resilience score.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK, read_events, emit_event   # noqa: E402

# ── the closed vocabulary for the "root" of a death (Issue #104 / OBS-052) ──────────
# In the field (Tatekae), failures with the same root were recorded in different words and a
# detector matching whole strings reported clean three times running. **Never make a machine guess
# that two pieces of free prose mean the same thing** — whoever records classifies at record time.
# The vocabulary must be identical to `root` in ledger-schema.yaml's validation.enums
# (tests/test_learning.py reconciles them).
DEATH_ROOTS = {
    "placebo_test":          "the check does not measure the path used in production (a hardened "
                             "or placebo test)",
    "declaration_drift":     "the declaration and the implementation drifted apart",
    "integration_base_moved": "the integration target moved and the premise collapsed",
    "self_written_premise":  "the party being checked can write the premise of the check",
    "other":                 "none of the above (add the root in the free-prose cause. This is not "
                             "a root that discriminates, so a recurrence is visible only by string "
                             "match — it forms no root group)",
}


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


def cmd_profile(a):
    """Project partial work observations and explicit unknowns without learning claims."""
    events = read_events(a.root)
    taxonomy = {
        "failure": ("refutation_attempted", "result_retired", "rework_requested"),
        "near_miss": ("rollback_unproven", "halt_tripped", "judges_disagreed"),
        "adaptation": ("adaptive_envelope_activated", "adaptive_deviation_recorded",
                       "adaptive_envelope_reverted", "microexperiment_concluded"),
        "everyday_success": ("acceptable_outcome_recorded", "result_deployed",
                              "phase_admitted", "cycle_completed"),
        "control_false_positive": ("correction",),
    }
    counts = {name: 0 for name in taxonomy}
    classified = []
    for event in events:
        for name, source in taxonomy.items():
            if event.get("class") in source:
                counts[name] += 1
                classified.append({"seq": event.get("seq"), "taxonomy": name,
                                   "event_class": event.get("class")})
    reported_classes = {"progress_recorded", "cycle_completed", "acceptable_outcome_recorded"}
    report = {
        "observation_taxonomy": counts, "observations": classified,
        "wai": {"sources": ["constitution", "workflow", "doctrine"],
                "status": "reference_only", "confidence": "unknown"},
        "work_as_recorded": {"event_count": len(events), "coverage": "ledger_only",
                              "confidence": "unknown"},
        "work_as_reported": {"event_count": sum(1 for event in events
                                                   if event.get("class") in reported_classes),
                              "confidence": "unknown"},
        "inferred_wad": {"status": "not_inferred", "confidence": "unknown",
                          "missingness": ["external tool actions", "unreported actions",
                                          "human internal judgment"], "conflicts": []},
        "learning_candidates": [], "doctrine_mutated": False, "resilience_score": None,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return OK


def cmd_repeats(a):
    """REPEATED-DEATH detector — the direct measure of whether accumulated learning is actually USED.
    A death (a result_retired / a refutation that failed) carries a `cause`. If the SAME cause reappears
    on a LATER candidate, the org failed to feed its own lesson forward — it re-made a mistake it had
    already recorded (the org's core purpose, missed). This escalates a cause that recurs >= --recurrence
    times, naming the deaths, so "learning lifts quality" is a checked fact, not a hope. Silent when every
    death cause is distinct (no lesson was ignored).

    A recurrence is counted by the `root` classified at record time (DEATH_ROOTS); only legacy
    records with no root fall back to matching whole strings (Issue #104: whole-string matching let
    a rewording of the same root straight through)."""
    events = read_events(a.root)
    by_key = {}
    # The field carrying "the cause of death" varies by writer. Reading only `cause`, and not
    # treating rework_requested as a subject at all, meant **reporting "learning is being used" to
    # an org that had made the same mistake three times**. The keys the detector reads are matched
    # to the keys actually written.
    _CAUSE_KEYS = ("cause", "hypothesized_cause", "reason", "why", "checklist_ref")
    _DEATH_CLASSES = ("result_retired", "rework_requested", "refutation_attempted")

    def _cause_text_of(p):
        for k in _CAUSE_KEYS:
            v = p.get(k)
            if v and str(v).strip():
                return v
        return None

    # A recurrence is counted by **the root classified at record time** (`root`, DEATH_ROOTS).
    # String matching is a backward-compatible fallback for legacy records with no root (Issue
    # #104: whole-string matching let a rewording of the same root straight through).
    classified = 0        # deaths carrying a root
    unclassified = 0      # deaths with only free prose (visible solely by whole-string match)
    for e in events:
        p = e.get("payload", {})
        if e["class"] not in _DEATH_CLASSES:
            continue
        if e["class"] == "refutation_attempted" and p.get("verdict") != "refuted":
            continue      # a survives is not a death
        root = str(p.get("root") or "").strip()
        cause = _cause_text_of(p)
        # `other` is not a root that discriminates — two records of "none of the above" record
        # nothing about their roots being the same. Made into a root group, it would escalate two
        # unrelated deaths as "different wording, same root" (a fabricated semantic match; caught by
        # the gate through measurement). `other` falls back to string matching, as **marked
        # unclassified**.
        # For the same reason **a string outside the vocabulary (DEATH_ROOTS) forms no root group
        # either** — it can only be written through an older schema without the enum, and sharing
        # it records nothing about roots being identical (caught by the skeptic through
        # measurement). It falls back to string matching.
        if root and root != "other" and root in DEATH_ROOTS:
            classified += 1
            key = ("root", root)
        elif cause:
            unclassified += 1
            key = ("cause", str(cause).strip().lower())
        else:
            continue      # the cause cannot be read (counted in the unknown branch below)
        by_key.setdefault(key, []).append({"seq": e["seq"], "cause": cause, "root": root or None,
                                           "candidate_id": p.get("candidate_id")})
    readable = classified + unclassified
    repeated = {k: hits for k, hits in by_key.items() if len(hits) >= a.recurrence}
    deaths = sum(1 for e in events if e["class"] in _DEATH_CLASSES
                 and not (e["class"] == "refutation_attempted"
                          and e.get("payload", {}).get("verdict") != "refuted"))
    if not repeated:
        if deaths and not readable:
            # **Never say clean when not one record could be read.** "It has not recurred" and
            # "we cannot see" are different things, and conflating them manufactures false comfort
            # — a detector that lies is worse than no detector, which is exactly what happened in
            # the field.
            print(f"unknown: there are {deaths} send-back(s)/refutation(s), and the cause could "
                  f"be read for none of them. Whether anything recurred has not been decided.\n"
                  f"  Write the cause into the payload under one of "
                  f"{' / '.join(_CAUSE_KEYS)}, and classify the root alongside it with `root` "
                  f"({'/'.join(DEATH_ROOTS)}).\n"
                  f"  Until that is written, this detector cannot notice the same failure however "
                  f"many times it repeats.")
            return OK
        print(f"clean: no death cause recurred >= {a.recurrence} times — accumulated learning is being "
              f"used, no known mistake re-made. Silent."
              + (f" (read the cause of {readable})" if readable else ""))
        if readable:
            # State what clean was decided on — the count seen by root classification and the
            # unclassified count seen only by string match, said separately (they do not carry the
            # same guarantee).
            print(f"  decided on: {classified} by root classification / {unclassified} by "
                  f"whole-string match (root unclassified).")
        if unclassified >= 1:
            # **The warning does not disappear during migration either** (it is emitted for even
            # one unclassified record). If it vanished the moment the classified count rose and the
            # unclassified fell below the recurrence threshold, a single remaining unclassified
            # record would look clean even when it is a recurrence of the same root (caught by the
            # skeptic through measurement).
            # A record with no root is only seen by whole-string match. In the field, two records
            # written as "skew in the remainder" and "hardened test" had the same root — nothing
            # verified where the property actually breaks. The limit is stated so that clean is
            # never read as proof that the same mistake was not made.
            print(f"  note: the {unclassified} record(s) with no root are seen only by the "
                  f"**string** of their cause. A failure with the same root written in different "
                  f"words goes straight past this detector. It is worth reading them side by side "
                  f"and recording them again with a `root` ({'/'.join(DEATH_ROOTS)}) attached "
                  f"(`ledger.py view` / the Issue comments).")
        return OK
    for key, hits in sorted(repeated.items(), key=lambda kv: -len(kv[1])):
        emit_event("repeated_death_detected", {
            "cause": hits[0]["cause"] or hits[0]["root"], "occurrences": len(hits),
            "root": hits[0]["root"], "basis": key[0],
            "candidate_ids": [h["candidate_id"] for h in hits]})
    worst = max(repeated.items(), key=lambda kv: len(kv[1]))
    wkey, whits = worst
    if wkey[0] == "root":
        root = wkey[1]
        cause = whits[0]["cause"] or DEATH_ROOTS.get(root, root)
        wordings = sorted({str(h["cause"]) for h in whits if h["cause"]})
        print(f"REPEATED DEATH: root {root!r} ({DEATH_ROOTS.get(root, 'an unknown class')}) "
              f"recurred {len(whits)} times (candidates {[h['candidate_id'] for h in whits]}) — "
              f"different wording, same root: {wordings}. The org re-made a mistake it had already "
              f"recorded. "
              f"Accumulated learning was NOT fed forward; strengthen the death into doctrine and "
              f"inject it before the next attempt (docs/06). This is the org's core purpose "
              f"failing — escalate.", file=sys.stderr)
    else:
        cause = whits[0]["cause"]
        print(f"REPEATED DEATH: cause {cause!r} recurred {len(whits)} times "
              f"(candidates {[h['candidate_id'] for h in whits]}) — the org re-made a mistake it had "
              f"already recorded. Accumulated learning was NOT fed forward; strengthen the death into "
              f"doctrine and inject it before the next attempt (docs/06). This is the org's core purpose "
              f"failing — escalate.", file=sys.stderr)
    # Saying "harden this into doctrine" in prose does not harden anything. In the field, neither
    # detection nor accumulation nor distribution moved, and the same failure repeated three times.
    # **Emit the command to run** — an instruction with no route is a wish, not an instruction.
    # What becomes doctrine (the wording, the roles it applies to) is a person's decision.
    here = os.path.dirname(os.path.abspath(__file__))
    droot = os.path.join(os.path.dirname(a.root.rstrip("/")), "doctrine")
    print(f"\nNEXT: raise this cause into doctrine (handoff.py distributes it per role):\n"
          f'  python3 "{os.path.join(here, "doctrine.py")}" propose "{droot}" <role> \\\n'
          f'      --claim "{str(cause)[:80]}" --source "repeated-death" --confidence 0.9 \\\n'
          f'      --retrieved-at $(date -u +%Y-%m-%d) --review-by $(date -u -v+180d +%Y-%m-%d) \\\n'
          f'      --affects <the roles this failure bears on, comma-separated>\n'
          f'  Then the gate admits it: doctrine.py admit "{droot}" <role> <claim-id> --by gate\n'
          f"  Until it is admitted, it does not reach the next cycle.", file=sys.stderr)
    return ESCALATE


def main(argv):
    p = argparse.ArgumentParser(prog="learning", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("delta"); q.set_defaults(fn=cmd_delta)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)")
    q.add_argument("--threshold", type=float, default=0.2)
    q.add_argument("--recurrence", type=int, default=3)
    q = sub.add_parser("repeats"); q.set_defaults(fn=cmd_repeats)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)")
    q.add_argument("--recurrence", type=int, default=2)
    q = sub.add_parser("profile"); q.set_defaults(fn=cmd_profile)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)")
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
