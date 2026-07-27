#!/usr/bin/env python3
"""status — one glanceable health board for the org (docs/17 §5 Layer-3).

The user should be able to ask "how's my org?" and get one answer — green / amber / red — without
reading the ledger or knowing the words "tick", "sensor", or "chain". This reads the ledger and rolls
its state up into: what's done, what's in progress (with next steps), what needs the human, and an
overall light. It is READ-ONLY (like /org-tick) and speaks the user's language, not the organs'.

  status <root> [--role R]   print the health board (GREEN/AMBER/RED + the rollup)

Light:
  RED    — needs the human now: a broken ledger chain, a tripped halt, an unproven-rollback or a
           repeated death (the org re-made a known mistake), or a stalled cycle holding a slot.
  AMBER  — running but something to watch: work in progress past a while, a mandate awaiting, an
           empty domain model over many cycles.
  GREEN  — healthy: work draining, nothing escalating (fail-quiet is normal).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import OK, read_events   # noqa: E402


def cmd_status(a):
    try:
        events = read_events(a.root)
    except Exception as e:
        print(f"RED — the ledger could not be read ({e}). The org's state is unknown; a human must look.")
        return OK
    if not events:
        print("GREEN — no activity yet. The org is founded but has done nothing; drop work on the "
              "backlog (or wire an intake) and start it.")
        return OK

    counts = {}
    for e in events:
        counts[e["class"]] = counts.get(e["class"], 0) + 1

    # in-progress: started but not completed candidates
    started, completed, latest = {}, set(), {}
    for e in events:
        p = e.get("payload", {})
        cid = p.get("candidate_id")
        if not cid:
            continue
        if e["class"] == "cycle_started":
            started[cid] = p.get("role")
        elif e["class"] == "cycle_completed":
            completed.add(cid)
        elif e["class"] == "progress_recorded":
            latest[cid] = p.get("next_step")
    in_progress = {cid: r for cid, r in started.items() if cid not in completed}

    # red signals
    red = []
    if counts.get("halt_tripped"):
        red.append("a HALT has tripped — the org stopped itself")
    if counts.get("repeated_death_detected"):
        red.append("a known mistake was re-made (repeated death) — accumulated learning isn't landing")
    if counts.get("rollback_unproven"):
        red.append("an action claimed reversible has no proven undo")
    if counts.get("stall_breaker_checked"):
        trips = sum(1 for e in events if e["class"] == "stall_breaker_checked"
                    and e.get("payload", {}).get("decision") == "trip")
        if trips:
            red.append(f"{trips} cycle(s) wedged (stall breaker tripped) — holding a slot")

    # amber signals
    amber = []
    open_backlog = counts.get("candidate_submitted", 0) - counts.get("cycle_completed", 0)
    if in_progress:
        amber.append(f"{len(in_progress)} item(s) in progress")
    mandates = sum(1 for e in events if e["class"] == "candidate_submitted"
                   and e.get("payload", {}).get("source") == "mandate")
    open_mandates = mandates  # approximate; a completed one still counts here, kept simple
    if open_mandates and open_backlog > 0:
        amber.append(f"{open_mandates} mandate(s) submitted")

    done = counts.get("cycle_completed", 0)

    if red:
        light = "RED"
    elif amber:
        light = "AMBER"
    else:
        light = "GREEN"

    print(f"{light} — {'needs you' if light == 'RED' else 'running' if light == 'AMBER' else 'healthy'}")
    print(f"  done: {done} cycle(s) completed | backlog open: {max(0, open_backlog)} | "
          f"in progress: {len(in_progress)}")
    if red:
        print("  NEEDS YOU:")
        for r in red:
            print(f"    - {r}")
    if in_progress:
        print("  in progress:")
        for cid, role in list(in_progress.items())[:8]:
            ns = latest.get(cid)
            print(f"    - {cid} ({role})" + (f" — next: {ns}" if ns else ""))
    if amber and not red:
        print("  watch: " + "; ".join(amber))
    if light == "GREEN":
        print("  nothing escalating — fail-quiet is the normal state.")
    return OK


def cmd_redline(a):
    """One-line RED signal for a Monitor to consume (docs/17 §5 Layer-3, escalation transport). Prints a
    single line ONLY when the org is RED (needs the human) — nothing when GREEN/AMBER. A `Monitor` polling
    this turns each RED into a push the moment it appears, so "unattended" is not "unobservable": the
    exception reaches the user without them opening /org. Silent (no output) when healthy — fail-quiet."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_status(a)
    out = buf.getvalue()
    if out.startswith("RED"):
        first = out.splitlines()[0]
        needs = [ln.strip("- ").strip() for ln in out.splitlines() if ln.strip().startswith("-")]
        print(f"RED — org needs you: {'; '.join(needs) if needs else first}", flush=True)
    return OK


def main(argv):
    p = argparse.ArgumentParser(prog="status", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("status"); q.set_defaults(fn=cmd_status)
    q.add_argument("root")
    q.add_argument("--role", default="")
    q = sub.add_parser("redline"); q.set_defaults(fn=cmd_redline)
    q.add_argument("root")
    q.add_argument("--role", default="")
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
