"""Look, clean up, leave a record — show / gc / touched.

The whole picture of one Issue, sweeping up accumulated worktrees, and recording changes to
production assets."""

import json
import os
import re
import sys

from ._core import (
    _admission_for,
    _branch_for,
    _events_for,
    _execute,
    _gh_sync,
    _issue_body,
    _ledger,
    _raw,
    _refutation_for,
    _repo,
    resolve_integration_base,
    resolve_issue_branch,
)



def _issue_reasons(issue):
    """Return every admission_decided reason on the Issue, **oldest first**.

    The ledger holds only the digest (by design), so the reasons are on the Issue. Fetching one makes
    every round read the same latest comment, which makes every round look alike (the first
    implementation did exactly that). The point is to see something different per round, so they are
    taken as a sequence.
    """
    args = ["gh", "issue", "view", str(issue), "--json", "comments"]
    r = _repo()
    if r:
        args += ["--repo", r]
    code, out = _raw(args)
    if code != 0:
        return []
    try:
        cs = json.loads(out).get("comments", [])
    except Exception:
        return []
    out_r = []
    for c in cs:
        b = c.get("body") or ""
        if "admission_decided" not in b:
            continue
        m = re.search(r"\*\*Why \(the reasoning\):\*\*\s*\n(.+)", b)
        out_r.append(" ".join(m.group(1).split())[:600] if m else "")
    return out_r


def cmd_show(a):
    """See at a glance, for one Issue, who judged what and what it now waits on.

    In the field gh issue view, a grep of the ledger, and status.py had to be run separately, and
    once something had gone three rounds it became impossible to tell which round's judgment was
    being read. Both the missing refutation record on one Issue and a missing reject would have been
    found immediately from this vantage point.
    """
    # The reference for attributing irreversible changes. Guessing develop misattributes another
    # Issue's output as "this Issue's irreversible change" (OBS-054 / #106). show, however, is
    # read-only orientation, so the absence of a reference is no reason to hide even the state that
    # comes from the ledger (rework #106) — only the attribution block is omitted, with a warning,
    # and it continues (the same warn-don't-stop shape as cmd_plan).
    attribution_base, base_err = resolve_integration_base(getattr(a, "base", None))
    if base_err:
        print(f"  ! not attributing irreversible changes — no baseline (#{a.issue}):\n{base_err}",
              file=sys.stderr)
        attribution_base = None
    title, _ = _issue_body(a.issue)
    av, aseq, _ = _admission_for(a.issue)
    rv, rseq, _ = _refutation_for(a.issue)
    evs, voided = _events_for(a.issue)

    provisional = [e for e in evs if e["class"] == "verdict_provisional"]
    state = ("waiting on rework" if av == "reject" else
             "can be integrated" if av == "admit" and rv == "survives" else
             "sent back by a refutation" if rv == "refuted" else
             "cross-harness provisional judgment present (waiting on the joint)" if provisional else
             "waiting on the skeptic" if av == "admit" else
             "waiting on the gate" if any(e["class"] == "cycle_completed" for e in evs) else
             "being implemented" if any(e["class"] == "cycle_started" for e in evs)
             else "not started")

    print(f"#{a.issue} {title or ''} — {state}")
    if provisional and not (av or rv):
        print("  ! the provisional verdict is recorded in the ledger, but it is not final."
              "Settle the cross-harness agreement with the dedicated derive-admission.")

    br = _branch_for(a.issue)
    code, log = _raw(["git", "log", "--oneline", "-3", br])
    if code == 0 and log.strip():
        print(f"  built:    {' / '.join(l.split(' ',1)[0] for l in log.strip().splitlines())}"
              f"  ({br})")
    wt = os.path.join(os.getcwd(), ".orgforge", "wt", f"issue-{a.issue}")
    print(f"  worktree: {'.orgforge/wt/issue-%d/' % a.issue if os.path.isdir(wt) else '(none)'}")

    # The history of judgments — all of it, so which judgment of which round is clear
    judged = [e for e in evs if e["class"] in
              ("admission_decided", "refutation_attempted", "rework_requested",
               "integration_admitted", "result_deployed", "correction")]
    if judged:
        print("  verdicts:")
        for e in judged:
            pl = e.get("payload", {}) or {}
            if e["class"] == "correction":
                print(f"     seq {e.get('seq')}: correction kind={pl.get('kind')} "
                      f"effect={pl.get('effect', '-')} targets={pl.get('corrects')} "
                      f"by {pl.get('authority_role') or e.get('actor')} "
                      f"principal={pl.get('authority_principal', '-')} "
                      f"assurance={pl.get('authority_assurance', 'legacy')}")
                continue
            mark = "✗" if e.get("seq") in voided else " "
            why = (pl.get("why") or pl.get("reason") or "")[:70]
            note = " ⟨corrected⟩" if e.get("seq") in voided else ""
            bf = " ⟨backfill⟩" if pl.get("backfilled") else ""
            print(f"   {mark} seq {e.get('seq')}: {e['class']} = {pl.get('verdict', '-')}"
                  f" by {e.get('actor')}{note}{bf}"
                  + (f"\n        {why}" if why else ""))
    else:
        print("  verdicts: none yet")

    # 4: what the rounds mean. One went nine rounds, another ten. The controls work — each round
    # found a defect with real harm — but **there is no view of when it converges**. Seeing not just
    # the count but "what the latest judgments take issue with" gives material for deciding whether
    # to cut it.
    # **It does not judge** — it never says "cut it now". It merely lays out how the character
    # changed.
    rounds = [e for e in judged if e["class"] == "admission_decided"]
    if len(rounds) >= 3:
        reasons = _issue_reasons(a.issue)
        kinds = []
        for idx, e in enumerate(rounds[-3:]):
            pl = e.get("payload", {}) or {}
            txt = " ".join(str(pl.get(k, "")) for k in ("why", "reason", "note"))
            if not txt.strip():
                # Line the ledger's sequence up with the Issue's from the end (both are
                # chronological)
                j = len(reasons) - 3 + idx
                txt = reasons[j] if 0 <= j < len(reasons) else ""
            # The classification is a coarse keyword guess. **It is material for a judgment, not a
            # judgment** — "a test defect three rounds running" can be a reason to cut, but whether
            # to cut is the CEO's call.
            # It can misclassify, so the original text stays readable on the Issue and in the
            # `judged` list.
            k = ("テストの欠陥" if re.search(r"テスト|警報|検出できな|placebo|ミューテーション", txt)
                 else "実装の欠陥" if txt else "不明")
            kinds.append(k)
        print(f"  rounds:   {len(rounds)} — last 3: {' / '.join(kinds)}")
        # ③ rework piling up = the signal that "what needs fixing keeps growing".
        # In operation it reworked eight times, and **every finding from the fourth onward was
        # absent from the spec's MUSTs**.
        # Treated like "N irreversible changes" — **it does not stop; it puts out material.**
        reworks = [e for e in judged
                   if e["class"] == "rework_requested" and e.get("seq") not in voided]
        # Read by **the number of reworks**, not the number of judgments. One took seven rounds yet
        # converged in two reworks — stacking up judgments is not itself bad (it can be the result of
        # a gate looking carefully). The problem is "fix it, and fix it again" piling up, so that is
        # what is counted.
        if len(reworks) > 3:
            print(f"            ⚠ {len(reworks)} rework(s) / {len(rounds)} judgment(s) — over "
                  f"three. **How the Issue is cut, or the definition of done, is worth "
                  f"revisiting.**\n"
                  f"              In operation it reworked eight times, and every finding from the "
                  f"fourth onward was absent from the spec's MUSTs (an out-of-scope defect becomes "
                  f"its own Issue — see \"the judgment of done\" in template/SPEC.md)")
        # As for 4 (proposal 4 of the request), **implementation was declined.**
        # Deciding "which MUST the latest rework answers" by vocabulary overlap was tried and
        # produced false results on real data: it warned "out of scope" on a finished Issue (work
        # exactly per its MUSTs), while one that genuinely was out of scope walked past because
        # `expenses` happened to match.
        # Deciding correspondence is out of reach for vocabulary matching — a false warning voids the
        # correct warnings too (in the field, complete crying wolf led to Issue comments being
        # integrated by eye).
        # The proposal's aim (detecting out-of-scope work) is served from other angles by
        # split-check's (d) and (e) and by "N irreversible changes" above.
        if kinds.count("テストの欠陥") == 3:
            print(f"            all three latest rounds are of the \"satisfies the MUSTs but the "
                  f"checking is thin\" kind. The defects continue in the checking, not the "
                  f"implementation")

    # 3: the number of **irreversible changes** this Issue produced. In operation it produced five
    # migrations and they interfered with each other (0010 broke what 0009 fixed, and 0011 turned two
    # others RED).
    # **By the time the third was written, "this is not one Issue" could have been noticed.** It does
    # not stop — it puts out material.
    if attribution_base is not None:
        irreversible = []
        for ev in evs:
            if ev["class"] != "asset_touched" or ev.get("seq") in voided:
                continue
            pl = ev.get("payload", {}) or {}
            irreversible.append(pl.get("name") or pl.get("op") or "?")
        br = _branch_for(a.issue)
        code, mig = _raw(["git", "diff", "--name-only", f"{attribution_base}...{br}"])
        migrations = [f for f in (mig or "").split("\n")
                      if re.search(r"(^|/)(migrations?|db/migrate)/", f)]
        total = sorted(set(irreversible) | set(os.path.basename(m) for m in migrations))
        if len(total) >= 3:
            print(f"  irrev.:   {len(total)} — {', '.join(t[:34] for t in total[:5])}"
                  + (" …" if len(total) > 5 else ""))
            print(f"            one deliverable has produced three or more irreversible changes. "
                  f"How the Issue is cut is worth revisiting (it produces migrations that interfere "
                  f"with each other)")

    nxt = ("gate re-judges → skeptic → integrate" if av == "reject" else
           f"integrate --issue {a.issue}" if av == "admit" and rv == "survives" else
           f"verify --issue {a.issue} --role skeptic" if av == "admit" else
           f"verify --issue {a.issue} --role gate")
    print(f"  next:     {nxt}")
    return 0


def cmd_gc(a):
    """5: sweep up accumulated worktrees. **Anything with uncommitted changes is left alone.**

    complete/integrate now clean up, but what had already accumulated — and what a budget cap left
    unremovable — was nobody's job. One left standing after integration means the stale tree is
    grabbed when the same Issue is touched next.
    """
    # The reference for "is it integrated". Guessing develop leaves a worktree already integrated
    # into origin/main standing forever as "unintegrated" (OBS-057 / #106). --all **does not** decide
    # integration, so it demands no reference — fail-closed applies only to judgments that actually
    # consume the base (rework #106).
    merged_base = None
    if not a.all:
        merged_base, base_err = resolve_integration_base(getattr(a, "base", None))
        if base_err:
            print(f"gc's reference for deciding integration is undecided:\n{base_err}",
                  file=sys.stderr)
            return 2
    base = os.path.join(os.getcwd(), ".orgforge", "wt")
    if not os.path.isdir(base):
        print("there are no worktrees.")
        return 0
    kept, removed = [], []
    for name in sorted(os.listdir(base)):
        if not name.startswith("issue-"):
            continue
        issue = name[len("issue-"):]
        wt = os.path.join(base, name)
        code, out = _raw(["git", "-C", wt, "status", "--porcelain"])
        if code == 0 and out.strip():
            kept.append((name, f"{len(out.strip().splitlines())} uncommitted change(s)"))
            continue
        if not a.all:
            # By default only what is integrated is removed. Work not yet taken in is not removed.
            # "Which branch do we ask about" is **the branch that exists**, not the derived name
            # (#107). Asking by the derived name makes `--merged --list <derived name>` always empty
            # after a retitling, so an integrated worktree stands forever as "unintegrated" (Tatekae
            # OBS-012 / OBS-057 cause 2).
            br, warn, err = resolve_issue_branch(issue, derived=_branch_for(issue))
            if err:
                # Without identifying the branch that exists, removal cannot be decided — it is
                # left standing and the reason is stated.
                print(err, file=sys.stderr)
                if "detached HEAD" in err:
                    kept.append((name, ("a detached HEAD, so it is not removed automatically. "
                                        f"After looking at the content, run git -C {wt} switch "
                                        f"<an existing branch> if needed, or run "
                                        f"git worktree remove {wt} explicitly")))
                else:
                    kept.append((name, "the branch cannot be resolved (see the stderr above)"))
                continue
            if warn:
                print(f"  ⚠ {warn}", file=sys.stderr)
            code, merged = _raw(["git", "branch", "--merged", merged_base, "--list", br])
            if code != 0 or not (merged or "").strip():
                kept.append((name, f"not integrated into {merged_base} (branch {br})"))
                continue
        code, out = _raw(["git", "worktree", "remove", wt])
        (removed if code == 0 else kept).append(
            (name, "cleaned up" if code == 0 else out.strip()[:60]))
    # git also knows about verification worktrees created outside .orgforge/wt/ (in a scratchpad and
    # the like). In the field an sk7 a skeptic made in a scratchpad was left standing, unremovable
    # under a budget cap.
    # Reading only "where the plumbing creates them" leaves orphans like that forever.
    code, out = _raw(["git", "worktree", "list", "--porcelain"])
    if code == 0:
        for block in (out or "").split("\n\n"):
            m = re.search(r"^worktree (.+)$", block, re.M)
            if not m:
                continue
            wt = m.group(1)
            if wt == os.getcwd() or base in wt:
                continue
            if not any(k in wt for k in ("/scratchpad/", "/tmp/")):
                continue      # a place of unknown provenance is not touched
            name = os.path.basename(wt)
            code2, st = _raw(["git", "-C", wt, "status", "--porcelain"])
            if code2 == 0 and st.strip():
                kept.append((name, f"{len(st.strip().splitlines())} uncommitted change(s) ({wt})"))
                continue
            if not os.path.isdir(wt):
                code3, o3 = _raw(["git", "worktree", "prune"])
                removed.append((name, "it was gone, so pruned"))
                continue
            code3, o3 = _raw(["git", "worktree", "remove", wt])
            (removed if code3 == 0 else kept).append(
                (name, f"cleaned up ({wt})" if code3 == 0 else o3.strip()[:60]))

    for n, why in removed:
        print(f"  ✓ {n} — {why}")
    for n, why in kept:
        print(f"  · {n} — kept ({why})")
    print(f"\ncleared {len(removed)}, kept {len(kept)}.")
    if kept:
        print("Inspect the contents of what was kept — whether losing it would matter is not "
              "ours to decide.")
    return 0


def cmd_touched(a):
    """Leave a change to a production asset in the ledger.

    exposure_budget_checked counts local file operations but counts neither DDL against a remote DB
    nor a privilege change in production. The latter is in fact the more dangerous, and costs more to
    undo. In the field two migrations and a privilege revoke went into the production DB while
    nothing was left in the ledger, so "under whose authority did that revoke go in" could not be
    traced.
    """
    payload = {"target": a.target, "op": a.op, "name": a.name or "",
               "reversible": bool(a.reversible), "authority": a.authority,
               "issue": a.issue, "rollback": a.rollback or ""}
    rc = _execute([
        (f"asset_touched: {a.op} on {a.target}",
         lambda: _ledger("append", "--actor", a.by, "--class", "asset_touched",
                         "--natural-key", f"asset-{a.target}-{a.op}-{a.name or a.issue}",
                         "--payload", json.dumps(payload, ensure_ascii=False))),
    ], f"record asset_touched ({a.target})")
    if rc == 0 and a.issue:
        _gh_sync("log", "--issue", str(a.issue), "--event", "progress_recorded",
                 "--detail", f"changed a production asset: {a.op} {a.name or ''} on {a.target}"
                             f"({'reversible' if a.reversible else '**irreversible**'} / "
                             f"authority: {a.authority})",
                 "--command", f"{a.op} {a.name or ''}".strip(),
                 "--result", a.rollback or "(the rollback procedure is unrecorded)")
    if not a.reversible:
        print("  ⚠ reversible=false — this is now a record that it went in knowing it cannot be "
              "undone.", file=sys.stderr)
    return rc


# Patterns for a surface exposed outward. Only the representative public shapes of SQL, TS, and
# Python are read. Complete detection is not the aim — the aim is **to ask a human back about an
# oversight**, so being able to ask "isn't this a public surface?" is enough, and picking up too much
# is worse.
