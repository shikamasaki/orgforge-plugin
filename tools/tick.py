#!/usr/bin/env python3
"""tick — the pure schedule PLANNER (docs/05 §5, docs/08 R0).

This is NOT a scheduler. It ships no loop, no daemon, no clock of its own (R0: "the system
never ships a scheduler", docs/08 §4). It is a pure function the host's cron/CI/harness loop
invokes once per base interval: given schedule.yaml + the current time + the ledger, it computes

  (1) which operating-event checks are DUE this tick,
  (2) with the night fail-safe applied (checks not night_safe are SUSPENDED overnight —
      constitution delegated.night; the tighter of schedule.night_safe and the sensor's
      preregistered_for_night wins), and
  (3) — the guardrail the whole layer exists for — which due checks DID NOT RUN: a check that
      was due but whose verify_event is ABSENT from the ledger in its window is a MISS. A miss
      is reported, and consecutive misses of one check ESCALATE. "It was supposed to run" is
      thereby made a detected, escalated fact, never a silent excuse (docs/05 §5.6).

The host then actually invokes the due tools (tick.py only PLANS; it does not run them — that
would be the bespoke runtime R0 forbids). tick.py's own run is itself ledgered (tick_planned),
so a gap in tick_planned events proves the host cron itself stopped — the outermost dead-man's
switch.

  plan <root> <schedule_yaml> --now-min N [--night] [--verbose]
      N = minutes since an epoch the host defines (a monotonic tick counter). --night forces
      the night fail-safe (the host passes it based on the operator's away-window / constitution
      delegated.night.hours). Prints the DUE list, the SUSPENDED list, and any MISSES; exit 10
      if any check must escalate (a miss past the consecutive threshold, or a due escalation).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK, read_events   # noqa: E402


def _load_schedule(path):
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        pass
    # tiny fallback: parse the flat checks list + base_interval + missed_tick we ship. Good
    # enough for the shipped schedule.yaml; a real host has pyyaml.
    doc = {"checks": [], "missed_tick": {}}
    cur = None
    section = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            s = line.strip()
            if s.startswith("#") or not s:
                continue
            if s.startswith("base_interval:"):
                doc["base_interval"] = s.split(":", 1)[1].strip()
            elif s.startswith("- id:"):
                section = "checks"
                if cur:
                    doc["checks"].append(cur)
                cur = {"id": s.split("id:", 1)[1].strip()}
            elif s.startswith("missed_tick:"):
                if cur:
                    doc["checks"].append(cur); cur = None
                section = "missed"
            elif section == "checks" and cur is not None and ":" in s:
                k, v = s.split(":", 1)
                v = v.strip().strip('"')
                if v in ("true", "false"):
                    v = v == "true"
                cur[k.strip()] = v
            elif section == "missed" and ":" in s:
                k, v = s.split(":", 1)
                v = v.strip()
                doc["missed_tick"][k.strip()] = int(v) if v.isdigit() else v
    if cur:
        doc["checks"].append(cur)
    return doc


def _interval_min(cadence):
    """Minutes for an every_<n>_min|hours cadence; None for on_<event> (edge-triggered)."""
    m = re.match(r"every_(\d+)_min$", cadence)
    if m:
        return int(m.group(1))
    m = re.match(r"every_(\d+)_hours$", cadence)
    if m:
        return int(m.group(1)) * 60
    return None   # on_<event> — not clock-driven; the host fires it on the event, not the tick


def _monitoring_origin(events, now):
    """Return the first host-planned tick in this clock domain.

    ``--now-min`` is an absolute or monotonic counter chosen by the host.  It is not an org-age
    counter, so dividing it directly by a cadence counts imaginary runs before monitoring was
    enabled (Unix-epoch minutes made a new org appear roughly 56 years overdue).

    ``tick_planned`` already records that same counter.  Its first occurrence is therefore the
    only ledger fact that proves when schedule monitoring began.  Before one exists, this run is
    the baseline: it may report what is due, but cannot truthfully claim an earlier run was missed.
    The sequence boundary also keeps verification events from before monitoring started from
    masking later misses.
    """
    planned = [event for event in events if event.get("class") == "tick_planned"]
    compatible = []
    barriers = []
    for event in planned:
        seq = int(event.get("seq", 0))
        value = (event.get("payload") or {}).get("now_min")
        if isinstance(value, int) and not isinstance(value, bool) and value <= now:
            compatible.append((value, seq))
        else:
            barriers.append((seq, value))

    # A later well-formed receipt repairs a malformed origin or explicitly starts the host's new
    # clock domain. Until that receipt exists, fail visibly instead of silently re-baselining.
    barrier_seq = max((seq for seq, _ in barriers), default=0)
    repaired = [(value, seq) for value, seq in compatible if seq > barrier_seq]
    if repaired:
        value, seq = repaired[0]
        return value, seq, None
    if barriers:
        detail = [f"seq {seq}: now_min={value!r}" for seq, value in barriers]
        error = (f"recorded tick origin is incompatible with now_min {now} "
                 f"({'; '.join(detail)}) — the host clock domain moved backwards or the origin "
                 "is malformed")
        # A malformed later receipt must not erase an earlier trustworthy origin: retain that
        # accounting while also escalating the corrupted barrier. If every recorded clock value
        # is ahead of ``now``, elapsed intervals are unknowable; the global clock MISS is the only
        # truthful result until the host persists a receipt in its new domain.
        prior = [(value, seq) for value, seq in compatible if seq < barrier_seq]
        if prior:
            value, seq = prior[0]
            return value, seq, error
        return now, max((int(event.get("seq", 0)) for event in events), default=0), error
    if compatible:
        value, seq = compatible[0]
        return value, seq, None
    return now, max((int(event.get("seq", 0)) for event in events), default=0), None


def cmd_plan(a):
    sched = _load_schedule(a.schedule_yaml)
    base = _interval_min(sched.get("base_interval", "every_5_min")) or 5
    now = a.now_min
    events = read_events(a.root)
    mt = sched.get("missed_tick", {})
    grace = int(mt.get("grace_intervals", 2))
    esc_after = int(mt.get("escalate_after_consecutive", 3))
    monitoring_origin, monitoring_origin_seq, clock_error = _monitoring_origin(events, now)

    selected = set(a.only_check or [])
    receipt_checks = set(a.receipt_check or [])
    declared_ids = {str(c.get("id")) for c in sched.get("checks", []) if c.get("id")}
    unknown = sorted((selected | receipt_checks) - declared_ids)
    if unknown:
        print("tick: scheduler coverage names undeclared check(s): " + ", ".join(unknown),
              file=sys.stderr)
        return 12

    # A clock check with interval M is DUE relative to the first tick in this clock domain.
    # Host schedulers such as launchd use StartInterval (relative), not wall-clock boundaries;
    # absolute ``now % interval`` therefore made a healthy job permanently miss its due phase.
    due, suspended, missed, escalate = [], [], [], False
    if clock_error:
        missed.append(("tick_clock", f"{clock_error}: MISS (cannot prove scheduled checks ran)"))
        escalate = True

    for c in sched.get("checks", []):
        cid = c.get("id")
        if selected and cid not in selected:
            continue
        cadence = c.get("cadence", "")
        night_safe = c.get("night_safe", False)
        interval = _interval_min(cadence)

        # night fail-safe: a non-night_safe check is SUSPENDED while humans are away
        if a.night and not night_safe:
            suspended.append((cid, "night: not night_safe — fail-safe suspend"))
            continue

        if interval is None:
            # edge-triggered (on_<event>): tick.py does not schedule it; the host fires it on the
            # event. We still MONITOR it for misses if its triggering events exist unanswered.
            if a.verbose:
                due.append((cid, f"edge ({cadence}) — host fires on event, not this tick"))
            continue

        # is it due now? due when elapsed monitoring time falls on an interval boundary,
        # within base slack. This follows both relative OS timers and monotonic test clocks.
        if interval < base:
            escalate = True
            missed.append((cid, f"cadence {cadence} ({interval}m) is FINER than base_interval "
                                f"{base}m — the host cron can never fire it; schedule is unsatisfiable"))
            continue
        phase = (now - monitoring_origin) % interval
        is_due = phase < base
        if not is_due:
            continue

        due.append((cid, f"{cadence} due at t={now}m"))

        # ── MISSED-TICK GUARD: was the PREVIOUS due window actually served? ──
        # the check should have produced its verify_event since (now - interval). If the ledger
        # holds no such event within (grace) base intervals of when it was due, it's a MISS.
        verify_class = c.get("verify_event")
        if cid in receipt_checks:
            # The unattended adapter records proof that the CHECK ran.  It must not forge the
            # check's domain output (for example sensor_reading or heartbeat). Count unique
            # cadence opportunities, not raw events, so retrying one scheduler minute cannot
            # make up for a skipped later window.
            served = set()
            for event in events:
                if event.get("class") != "scheduled_check_completed":
                    continue
                if int(event.get("seq", 0)) <= monitoring_origin_seq:
                    continue
                payload = event.get("payload") or {}
                if payload.get("check_id") != cid:
                    continue
                scheduled_for = payload.get("scheduled_for_min")
                if (not isinstance(scheduled_for, int) or isinstance(scheduled_for, bool)
                        or scheduled_for < monitoring_origin or scheduled_for > now):
                    continue
                elapsed = scheduled_for - monitoring_origin
                if elapsed % interval < base:
                    served.add(elapsed // interval)
            expected_ticks = max(0, (now - monitoring_origin) // interval)
            produced = len(served)
            shortfall = expected_ticks - produced
            if shortfall > grace:
                missed.append((cid, f"due {expected_ticks}x but only {produced} "
                                    "scheduled-check receipt window(s) in ledger — shortfall "
                                    f"{shortfall} > grace {grace}: MISS (the check did not run "
                                    "when scheduled)"))
                if shortfall >= esc_after:
                    escalate = True
        elif verify_class:
            # Count only the cadence opportunities since this host first planned a tick.  The
            # host counter may be Unix-epoch minutes, so epoch zero is not a valid org origin.
            produced = sum(1 for e in events
                           if e["class"] == verify_class
                           and int(e.get("seq", 0)) > monitoring_origin_seq)
            expected_ticks = max(0, (now - monitoring_origin) // interval)
            shortfall = expected_ticks - produced
            if shortfall > grace:
                missed.append((cid, f"due {expected_ticks}x but only {produced} {verify_class} "
                                    f"event(s) in ledger — shortfall {shortfall} > grace {grace}: "
                                    f"MISS (the check did not run when scheduled)"))
                if shortfall >= esc_after:
                    escalate = True

    # tick.py's own run is ledgered so a GAP in tick_planned proves the host cron itself died
    print("LEDGER-EVENT " + json.dumps(
        {"class": "tick_planned",
         "payload": {"now_min": now, "night": a.night,
                     "due": [d[0] for d in due], "suspended": [s[0] for s in suspended],
                     "missed": [m[0] for m in missed]}}, ensure_ascii=False))

    print(f"\n== tick t={now}m  (base {base}m, {'NIGHT' if a.night else 'day'}) ==")
    print(f"DUE ({len(due)}):")
    for cid, why in due:
        print(f"  ▶ {cid:22} {why}")
    if suspended:
        print(f"SUSPENDED overnight ({len(suspended)}):")
        for cid, why in suspended:
            print(f"  ⏸ {cid:22} {why}")
    if missed:
        print(f"MISSED ({len(missed)}) — the guardrail: a due check that did NOT run:")
        for cid, why in missed:
            print(f"  ✗ {cid:22} {why}", file=sys.stderr)
    if escalate:
        print("\nESCALATE: a scheduled check missed past threshold (or an unsatisfiable "
              "cadence). A schedule the host silently stopped firing is a page, not a shrug "
              "(wake_up_push). This is 'it was supposed to run' made a detected fact.",
              file=sys.stderr)
        return ESCALATE
    print("\nall due checks are accounted for; no missed ticks.")
    return OK


def main(argv):
    p = argparse.ArgumentParser(prog="tick", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("plan"); q.set_defaults(fn=cmd_plan)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)"); q.add_argument("schedule_yaml")
    q.add_argument("--now-min", dest="now_min", type=int, required=True)
    q.add_argument("--night", action="store_true")
    q.add_argument("--verbose", action="store_true")
    q.add_argument("--only-check", action="append", default=[],
                   help="plan/monitor only this declared check (repeatable; host adapter use)")
    q.add_argument("--receipt-check", action="append", default=[],
                   help="use scheduled_check_completed receipts for this check (repeatable)")
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
