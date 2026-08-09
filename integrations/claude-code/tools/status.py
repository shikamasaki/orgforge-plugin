#!/usr/bin/env python3
"""status — one glanceable health board for the org (docs/12 §5 Layer-3).

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
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import OK, read_events   # noqa: E402



def _reject_reason(issue):
    """The reason for this Issue's latest reject, in one line.

    decide writes the reason at length into an Issue comment (the ledger holds only a digest — by
    design). If the board cannot read it, the one screen a CEO looks at carries not a line of
    "what is wrong". Returns None quietly when GitHub cannot be reached (the board does not fall
    over).
    """
    import subprocess
    try:
        p = subprocess.run(["gh", "issue", "view", str(issue), "--json", "comments"],
                           capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            return None
        cs = json.loads(p.stdout).get("comments", [])
    except Exception:
        return None
    for c in reversed(cs):
        b = c.get("body") or ""
        if "admission_decided" not in b or "`reject`" not in b:
            continue
        m = re.search(r"\*\*Why \(the reasoning\):\*\*\s*\n(.+)", b)
        if m:
            s = " ".join(m.group(1).split())
            # The board is a screen you take in at a glance, and one item spanning several lines
            # ends that. The full text is on the Issue and in `org_cycle show --issue N`.
            return s[:70] + ("…" if len(s) > 70 else "")
    return None


def _needs_human_issues():
    """Return open Issues labelled orgforge:needs-human as "waiting on you".

    Without this the board lies: it counts only the work the org can produce, reports GREEN, and
    hides a state where nothing can start because a human precondition is outstanding (an account
    to create, a key to issue, a store review, branch protection). A request to a human is exactly
    what stalls longest when forgotten, so it goes at the top of the board.

    Where GitHub cannot be reached (a ledger-only org, gh unauthenticated, offline) it returns
    empty quietly — the board itself does not fall over."""
    import subprocess
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        import discover
        repo = discover.backlog_repo()
        if not repo:
            return []
        p = subprocess.run(["gh", "issue", "list", "--repo", repo, "--state", "open",
                            "--label", "orgforge:needs-human", "--json", "number,title"],
                           capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            return []
        items = json.loads(p.stdout or "[]")
    except Exception:
        return []
    out = []
    for it in items[:5]:
        out.append(f"waiting on you: #{it['number']} {it['title']}")
    if len(items) > 5:
        out.append(f"waiting on you: and {len(items) - 5} more")
    return out


def _governance_divergence_notice():
    """Return an AMBER notice when this linked worktree embeds stale governance."""
    try:
        import discover
        rows = discover.governance_divergences()
    except Exception:
        return None
    if not rows:
        return None
    names = ", ".join(r["path"] for r in rows[:5])
    if len(rows) > 5:
        names += f", +{len(rows) - 5} more"
    return (f"governance divergence: {len(rows)} file(s) differ in the subject worktree "
            f"({names}); enforcement uses the authoritative primary checkout")


def cmd_status(a):
    try:
        events = read_events(a.root)
    except Exception as e:
        print(f"RED — the ledger could not be read ({e}). The org's state is unknown; a human must look.")
        return OK
    governance_notice = _governance_divergence_notice()
    if not events and governance_notice:
        print("AMBER — running")
        print(f"  watch: {governance_notice}")
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
    operational = None
    try:
        from operational_state import fold as fold_operational
        operational = fold_operational(events)
        if operational["effective_state"] == "HALTED":
            detail = operational.get("derived_reason") or "an operational HALT is active"
            red.append(f"operational state HALTED — {detail}")
    except Exception:
        # Older bundles without the operational projection retain the original conservative signal.
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
    adaptive_rows = []
    try:
        from adaptation import fold as fold_adaptation, load_contract
        contract, _, _ = load_contract(a.root)
        adaptive = fold_adaptation(events, contract=contract)
        if operational is not None:
            operational = fold_operational(events, contract=contract)
            if operational["effective_state"] == "DEGRADED":
                amber.append("operational state DEGRADED — only the active adaptive envelope is allowed")
            elif operational["effective_state"] == "RECOVERING":
                amber.append("operational state RECOVERING — ship remains blocked until revalidation completes")
        envelope_specs = {row.get("id"): row for row in contract.get("adaptive_envelopes", [])}
        for row in adaptive["activations"]:
            spec = envelope_specs.get(row.get("envelope_id"), {})
            row = {**row, "forbidden_actions": spec.get("forbidden_actions") or [],
                   "revalidation_scope": spec.get("revalidation_scope") or []}
            adaptive_rows.append(row)
            if row.get("status") == "expired":
                red.append(f"adaptive envelope {row['envelope_id']} expired — only safe diagnosis/stop remains")
            elif row.get("status") == "active":
                amber.append(f"adaptive envelope active: {row['envelope_id']} until {row.get('expires_at')}")
            elif row.get("status") == "reverted" and row.get("tainted_artifacts"):
                amber.append(f"adaptive envelope reverted with {len(row['tainted_artifacts'])} tainted "
                             "artifact(s) awaiting declared revalidation")
    except Exception:
        adaptive_rows = []
    if governance_notice:
        amber.append(governance_notice)
    open_backlog = counts.get("candidate_submitted", 0) - counts.get("cycle_completed", 0)
    if in_progress:
        amber.append(f"{len(in_progress)} item(s) in progress")
    mandates = sum(1 for e in events if e["class"] == "candidate_submitted"
                   and e.get("payload", {}).get("source") == "mandate")
    open_mandates = mandates  # approximate; a completed one still counts here, kept simple
    if open_mandates and open_backlog > 0:
        amber.append(f"{open_mandates} mandate(s) submitted")

    done = counts.get("cycle_completed", 0)

    # Surface admits carrying a risk. The gate can admit as long as it writes --risk, so the
    # structure rewards writing honestly. **That is the right way round** — far better than a hole
    # nobody wrote down — but so that it is not a free pass, how many have accumulated has to be
    # visible.
    # **For one deliverable, the latest judgment is what holds.** Kept as a set, an admit survives
    # a later reject and work in rework counts as "admitted". In operation, admit then reject was
    # recorded and the board went on showing RED. The ledger is append-only, so "there was an admit
    # at some point" and "it is admitted now" are different things.
    # Records voided by correction{effect:voids} are not counted. Interpret kind per organ and
    # status and derive-admission derive different present values from the same ledger (OBS-042).
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from ledger import voided_seqs
        voided = voided_seqs(events)
    except Exception:
        voided = set()

    latest_admission = {}
    for e in events:
        if e["class"] != "admission_decided" or e.get("seq") in voided:
            continue
        pl = e.get("payload", {}) or {}
        key = str(pl.get("issue") or pl.get("deliverable") or "")
        if not key:
            continue
        prev = latest_admission.get(key)
        if prev is None or (e.get("seq") or 0) >= prev[0]:
            latest_admission[key] = ((e.get("seq") or 0), pl.get("verdict"))
    admits = {k for k, (_, v) in latest_admission.items() if v == "admit"}

    # An admit carrying a risk is likewise not counted once later rejected
    risky = []
    for e in events:
        if e["class"] != "admission_decided" or e.get("seq") in voided:
            continue
        pl = e.get("payload", {}) or {}
        if pl.get("verdict") != "admit" or pl.get("risk_accepted") is not True:
            continue
        key = str(pl.get("issue") or pl.get("deliverable") or "")
        cur = latest_admission.get(key)
        if cur and cur[0] == (e.get("seq") or 0):
            risky.append(e)
    if risky:
        amber.append(f"admits carrying a risk: {len(risky)} (holes left open knowingly)")

    # Detect drift between the two records. A judgment is meant to be written both as a receipt in
    # the ledger and as a reason on the Issue, but in the field a skeptic wrote only to the Issue
    # and the work came close to being integrated with nothing in the ledger. One side going
    # missing is the failure that actually happens, so the missing side is what is counted.
    refutes = {str((e.get("payload", {}) or {}).get("issue") or
                   (e.get("payload", {}) or {}).get("claim_id") or
                   (e.get("payload", {}) or {}).get("deliverable") or "")
               for e in events if e["class"] == "refutation_attempted"
               and e.get("seq") not in voided}
    # In a strict cross-harness org, a negative verdict is recorded provisionally before any joint
    # event exists.  Calling that "no skeptic record" is observably false.  It is not a positive
    # joint decision either, so surface the pending rework/materialization as AMBER.
    provisional_refutes = {
        str((e.get("payload", {}) or {}).get("issue") or
            (e.get("payload", {}) or {}).get("claim_id") or
            (e.get("payload", {}) or {}).get("deliverable") or "")
        for e in events
        if e["class"] == "verdict_provisional" and e.get("seq") not in voided
        and (e.get("payload", {}) or {}).get("role") == "skeptic"
        and (e.get("payload", {}) or {}).get("for_event") == "refutation_attempted"
        and (e.get("payload", {}) or {}).get("verdict") == "refuted"
    }
    provisional_refutes.discard("")
    pending_refuted = sorted(admits & provisional_refutes - refutes)
    for issue in pending_refuted[:5]:
        amber.append(f"#{issue} the skeptic refuted it — awaiting the joint record or the rework")
    # Surface anything left sitting in reject. AMBER (turning, but keep an eye on it) rather than
    # RED (waiting on you) — a send-back is a normal part of the process, not a fault. But let it
    # disappear quietly and nobody notices the rework has stalled.
    rejected = sorted(k for k, (_, v) in latest_admission.items() if v == "reject")
    if rejected:
        # **Emit one line of what was wrong.** A count alone tells a CEO nothing. The reason is
        # written at length by decide, and its being unreadable from the board means the one screen
        # there is carries no summary.
        why_of = {}
        for e in events:
            if e["class"] != "admission_decided" or e.get("seq") in voided:
                continue
            pl = e.get("payload", {}) or {}
            if pl.get("verdict") != "reject":
                continue
            k = str(pl.get("issue") or pl.get("deliverable") or "")
            cur = latest_admission.get(k)
            if cur and cur[0] == (e.get("seq") or 0):
                w = (pl.get("why") or pl.get("reason") or "").strip().replace("\n", " ")
                if w:
                    why_of[k] = w[:80] + ("…" if len(w) > 80 else "")
        for k in rejected[:5]:
            reason = why_of.get(k) or _reject_reason(k)
            amber.append(f"#{k} awaiting rework" + (f" — {reason}" if reason else ""))
        amber.append("for detail: `org_cycle.py show --issue N`")

    unrefuted = {a for a in admits if a and a not in refutes and a not in provisional_refutes}
    if unrefuted:
        red.append(f"admitted but no skeptic record: {len(unrefuted)} "
                   f"({', '.join('#' + x for x in sorted(unrefuted)[:5])}) — "
                   f"one step away from being integrated without facing refutation")

    # An Issue waiting on a human is RED by definition — "waiting on you" is what the board is
    # for. It does not appear in the ledger, so GitHub is consulted (and skipped quietly when
    # unreachable; the board does not fall over).
    for line in _needs_human_issues():
        red.append(line)

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
    if adaptive_rows:
        print("  adaptive envelopes:")
        for row in adaptive_rows[-5:]:
            print(f"    - {row['envelope_id']}: {row['status']} | critical: "
                  f"{','.join(row.get('affected_critical_functions') or [])} | taint: "
                  f"{len(row.get('tainted_artifacts') or [])} | revalidate: "
                  f"{','.join(row.get('revalidation_scope') or [])}")
            if row.get("forbidden_actions"):
                print(f"      forbidden: {','.join(row['forbidden_actions'])}")
    if operational and (operational["effective_state"] != "NORMAL" or
                        operational.get("circuits") or operational.get("taints")):
        print("  operational state:")
        print(f"    - effective: {operational['effective_state']} | recorded: "
              f"{operational['recorded_state']} | owner-session: "
              f"{operational.get('owner_session_id') or '-'}")
        for circuit_id, circuit in sorted(operational.get("circuits", {}).items()):
            print(f"    - circuit {circuit_id}: {circuit.get('to_state')} | dependency: "
                  f"{circuit.get('dependency')} | retries: {circuit.get('retry_count')}/"
                  f"{circuit.get('retry_budget')}")
        if operational.get("unresolved_taints"):
            print("    - unresolved taint: " + ", ".join(operational["unresolved_taints"]))
    if amber and not red:
        print("  watch: " + "; ".join(amber))
    if light == "GREEN":
        print("  nothing escalating — fail-quiet is the normal state.")
    return OK


def cmd_redline(a):
    """One-line RED signal for a Monitor to consume (docs/12 §5 Layer-3, escalation transport). Prints a
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
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)")
    q.add_argument("--role", default="")
    q = sub.add_parser("redline"); q.set_defaults(fn=cmd_redline)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)")
    q.add_argument("--role", default="")
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
