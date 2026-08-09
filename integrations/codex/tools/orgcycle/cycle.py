"""Starting and completing a cycle — begin / complete / plan.

It holds the plumbing (claim → spec_delegated → phase_started → cycle_started → log → stage) and
the questions asked back at completion (the domain model, and any newly exposed surface)."""

import json
import os
import re
import sys

from ._core import (
    HERE,
    _admission_for,
    _branch_for,
    _candidate_id,
    _execute,
    _events_for,
    _gh_sync,
    _issue_body,
    _ledger,
    _plus_days,
    _raw,
    _refutation_for,
    _repo,
    _run,
    _sub,
    _today,
    resolve_integration_base,
    resolve_parent,
)


def _steps_begin(a, parent, cid):
    """The sequence of events begin types. A list of (label, function) — plan merely prints it."""
    phase = a.phase or "implement"
    agent = a.agent or a.role
    repo_args = []          # --repo is not passed: github_sync discovers it
    return [
        # 6: recording what was chosen is plumbing (choosing is a judgment, but leaving the result
        # of the choice is the machine's job). In the field six were started while only one
        # attention_allocated existed, so the history of the choices could not be followed.
        (f"attention_allocated (chose #{a.issue})",
         lambda: _ledger("append", "--actor", a.role, "--class", "attention_allocated",
                         "--natural-key", f"attn-{a.issue}-{cid}",
                         "--payload", json.dumps(
                             {"role": a.role, "ranking_id": f"issue-{a.issue}",
                              "selected": [{"candidate_id": cid, "objective": parent or "",
                                            "source": "mandate"}],
                              "deferred": [],
                              "reason": a.why or f"starting #{a.issue} (begin)"},
                             ensure_ascii=False))),
        (f"claim #{a.issue} as {agent}",
         lambda: _gh_sync("claim", "--issue", str(a.issue), "--agent", agent, *repo_args)),
        *([(f"prepare the worktree .orgforge/wt/issue-{a.issue} (physical separation for parallel "
            f"makers)",
            lambda: _gh_sync("branch", "--issue", str(a.issue), "--worktree",
                             *(["--base", a.base] if getattr(a, "base", None) else [])))]
          if not getattr(a, "no_worktree", False) else []),
        (f"spec_delegated (spec_ref=#{a.issue})",
         lambda: _ledger("append", "--actor", a.role, "--class", "spec_delegated",
                         "--natural-key", f"spec-{a.issue}",
                         "--payload", json.dumps({"supervisor": a.role, "subordinate": agent,
                                                  "spec_ref": str(a.issue),
                                                  "contract_ref": parent or str(a.issue),
                                                  "intent_basis_ref": "REQUIREMENTS.md"},
                                                 ensure_ascii=False))),
        (f"phase_started{{{phase}}} deliverable=#{a.issue} parent=#{parent or '-'}",
         lambda: _ledger("append", "--actor", a.role, "--class", "phase_started",
                         "--natural-key", f"phase-{phase}-{a.issue}",
                         "--payload", json.dumps({"deliverable": str(a.issue),
                                                  **({"parent": parent} if parent else {}),
                                                  "phase": phase, "role": agent},
                                                 ensure_ascii=False))),
        (f"cycle_started candidate_id={cid}",
         lambda: _ledger("append", "--actor", agent, "--class", "cycle_started",
                         "--natural-key", f"start-{cid}",
                         "--payload", json.dumps({"role": agent, "candidate_id": cid,
                                                  "pack_manifest_id": f"issue-{a.issue}"},
                                                 ensure_ascii=False))),
        # Never make a human write a fact the tool already knows (B). In the field the 276
        # characters I wrote carried neither the branch name nor the worktree path, while org_cycle
        # knew both.
        (f"log cycle_started → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "cycle_started",
                          "--phase", phase, "--event-id", f"start-{cid}",
                          "--detail",
                          f"{agent} started (inheriting parent #{parent or '-'} / "
                          f"candidate_id `{cid}` / phase `{phase}`）",
                          "--command",
                          f"python3 org_cycle.py begin --role {a.role} --issue {a.issue} "
                          f"--agent {agent}",
                          "--result",
                          f"claim: {agent}\n"
                          f"branch: {_branch_for(a.issue)}\n"
                          f"worktree: "
                          + ("(none — --no-worktree)" if getattr(a, "no_worktree", False)
                             else f".orgforge/wt/issue-{a.issue}/")
                          + f"\nparent: #{parent or '-'}\ncandidate_id: {cid}",
                          "--files", f".orgforge/wt/issue-{a.issue}/",
                          "--next-step",
                          f"The specification is the body of #{a.issue}. Once done, "
                          f"`org_cycle.py complete --issue {a.issue} ...` → handback → verify")),
        (f"stage #{a.issue} → in-progress",
         lambda: _gh_sync("stage", "--issue", str(a.issue), "--stage", "in-progress")),
    ]


def _steps_complete(a, cid):
    dm = ({"updated": [a.domain_model_updated]} if a.domain_model_updated
          else {"none_asserted": a.domain_model_none})
    agent = a.agent or a.role
    return [
        (f"cycle_completed candidate_id={cid}",
         lambda: _ledger("append", "--actor", agent, "--class", "cycle_completed",
                         "--natural-key", f"done-{cid}",
                         "--payload", json.dumps({"role": agent, "candidate_id": cid,
                                                  "outputs": [a.outputs], "reused": [],
                                                  "domain_model": dm}, ensure_ascii=False))),
        (f"log cycle_completed → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "cycle_completed",
                          "--event-id", f"done-{cid}", "--detail", a.outputs,
                          "--command", a.command or "(pass the DoD command with --command)",
                          "--result", a.result or "(paste the real output into --result)",
                          *(["--files", a.files] if getattr(a, "files", None) else []),
                          "--next-step",
                          f"`org_cycle.py handback --issue {a.issue}` for the PR → "
                          f"verify（gate → skeptic）→ integrate")),
        (f"release claim on #{a.issue}",
         lambda: _gh_sync("release", "--issue", str(a.issue), "--agent", agent)),
    ]


def _readiness(issue):
    """Look, before starting, at whether it should really begin. **It does not stop — it shows.**

    begin used to start unconditionally. It starts even where a dependency is mid-rework, even where
    a prerequisite human task remains. github_sync ready reads only Issue-number dependencies and
    sees neither a dependency in rework nor needs-human. The judgment is a human's, but there is
    nothing to judge from without the material.
    """
    warns = []
    _, body = _issue_body(issue)
    for dep in sorted(set(re.findall(r"depends_on[^\n]*?#(\d+)", body or "", re.I))):
        av, _, _ = _admission_for(int(dep))
        code, out = _raw(["gh", "issue", "view", dep, "--json", "state,title,labels"]
                         + (["--repo", _repo()] if _repo() else []))
        state, title, labels = "", "", []
        if code == 0:
            try:
                d = json.loads(out)
                state, title = d.get("state", ""), d.get("title", "")
                labels = [l.get("name", "") for l in d.get("labels", [])]
            except Exception:
                pass
        if av == "reject":
            warns.append(f"#{dep} ({title[:34]}) was rejected by the gate and is in rework")
        elif state == "OPEN" and av != "admit":
            warns.append(f"#{dep} ({title[:34]}) is not finished yet")
        if "orgforge:needs-human" in labels:
            warns.append(f"#{dep} is waiting on a human (needs-human)")

    # Does this Issue itself carry needs-human, and is any human task still unresolved?
    code, out = _raw(["gh", "issue", "list", "--state", "open",
                      "--label", "orgforge:needs-human", "--json", "number,title", "--limit", "5"]
                     + (["--repo", _repo()] if _repo() else []))
    if code == 0:
        try:
            for h in json.loads(out or "[]"):
                warns.append(f"waiting on a human: #{h['number']} {h['title'][:44]}")
        except Exception:
            pass
    return warns


def _new_exports(issue, base="develop"):
    """List the public types / exports that newly grew in this cycle.

    3: domain_model is required, but `--domain-model-none "<reason>"` always passes, so it becomes a
    formality the moment the writer picks none. In the field a cycle written up as "only pure
    functions added" had actually created the types Balance / Transfer / SettleResult — that is,
    ubiquitous language. **It does not judge** — it merely puts the refuting material in front of
    whoever writes, so nothing walks past. Killing it or explaining it is the role's call.
    """
    br = _branch_for(issue)
    code, out = _raw(["git", "diff", f"{base}...{br}", "--unified=0"])
    if code != 0:
        code, out = _raw(["git", "diff", base, "--unified=0"])
        if code != 0:
            return []
    pat = re.compile(
        r"^\+.*?\bexport\s+(?:default\s+)?"
        r"(type|interface|enum|class|const|function)\s+([A-Za-z_][A-Za-z0-9_]*)")
    seen, hits = set(), []
    for line in out.split("\n"):
        m = pat.match(line)
        if m and m.group(2) not in seen:
            seen.add(m.group(2))
            hits.append((m.group(1), m.group(2)))
    return hits


# Patterns for a surface exposed outward. Only the representative public shapes of SQL, TS, and
# Python are read. Complete detection is not the aim — the aim is **to ask a human back about an
# oversight**, so being able to ask "isn't this a public surface?" is enough, and picking up too much
# is worse.
_SURFACE_PATTERNS = (
    (r"create\s+(?:or\s+replace\s+)?function\s+([\w.]+)", "db_function"),
    (r"grant\s+[\w\s,]+\s+on\s+[\w.]*\s*([\w.]+)\s+to\s+(\w+)", "grant"),
    (r"create\s+policy\s+\"?([\w_]+)", "rls_policy"),
    (r"^\+?\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", "export"),
    (r"app\.(?:get|post|put|delete|patch)\(\s*[\"']([^\"']+)", "endpoint"),
)


def _new_public_surfaces(issue, base="develop"):
    """The public surface newly added in this cycle. **It does not judge — it asks back.**

    An authorization hole is born where "one function was added". join_group in the field was exactly
    that: nothing made it mechanically visible to anyone that one more SECURITY DEFINER had
    appeared.
    """
    br = _branch_for(issue)
    code, out = _raw(["git", "diff", f"{base}...{br}", "--unified=0"])
    if code != 0:
        return []
    # **The worktree's uncommitted content is read too.** In the field add_member_by_creator (a
    # SECURITY DEFINER) had been applied to the production DB while remaining uncommitted, so it did
    # not appear in the `base...branch` diff.
    # "It is not a public surface because it is not committed yet" does not hold — it is already in
    # production.
    wt = os.path.join(os.getcwd(), ".orgforge", "wt", f"issue-{issue}")
    if os.path.isdir(wt):
        c2, o2 = _raw(["git", "-C", wt, "diff", base, "--unified=0"])
        if c2 == 0:
            out += "\n" + o2
        c3, untracked = _raw(["git", "-C", wt, "ls-files", "--others",
                              "--exclude-standard"])
        for rel in (untracked or "").split("\n"):
            rel = rel.strip()
            if not rel or not rel.endswith((".sql", ".ts", ".js", ".py")):
                continue
            try:
                path = os.path.join(wt, rel)
                if os.path.getsize(path) > 256 * 1024:
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    body = f.read()
                out += f"\n+++ b/{rel}\n" + "\n".join("+" + l for l in body.split("\n"))
            except Exception:
                continue
    found, seen = [], set()
    definer_ctx = False
    skip = False
    for line in out.split("\n"):
        # Track which file each diff belongs to. Tests, type definitions, and configuration are not
        # public surface — picking up too much **buries the one that matters** (in the field
        # add_member_by_creator was buried under ten test helpers, which defeats the point of asking
        # back).
        if line.startswith("+++ "):
            f = line[4:].strip().lstrip("b/")
            skip = bool(re.search(r"(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.|"
                                  r"\.d\.ts$|(^|/)(scripts|tools)/", f, re.I))
            definer_ctx = False
            continue
        if skip or not line.startswith("+"):
            continue
        low = line.lower()
        if "security definer" in low:
            definer_ctx = True
        for pat, kind in _SURFACE_PATTERNS:
            m = re.search(pat, low, re.I | re.M)
            if not m:
                continue
            name = m.group(1) if m.groups() else m.group(0)
            key = (kind, name)
            if key in seen:
                continue
            seen.add(key)
            found.append({"kind": kind, "name": name, "note": ""})

    # SECURITY DEFINER is decided **per function**. A file-level flag leaves a function defined
    # later (add_member_by_creator in the field) unmarked, so it sinks down the list and the very one
    # that needs looking at is buried.
    added = "\n".join(l for l in out.split("\n") if l.startswith("+"))
    for s in found:
        if s["kind"] != "db_function":
            continue
        m = re.search(re.escape(s["name"]) + r"[\s\S]{0,600}?security\s+definer",
                      added, re.I)
        if m:
            s["note"] = "SECURITY DEFINER"
        if re.search(r"grant\s+execute\s+on\s+function\s+" + re.escape(s["name"]),
                     added, re.I):
            s["note"] = (s["note"] + " / granted").strip(" /")

    # In order of danger. SECURITY DEFINER and grant exceed the caller's privileges, so they come
    # first.
    rank = {"db_function": 0, "grant": 1, "rls_policy": 2, "endpoint": 3, "export": 4}
    found.sort(key=lambda s: (0 if s["note"] else 1, rank.get(s["kind"], 9)))
    return found


def _cleanup_worktree(issue):
    """4: clean up the worktree begin created. Run eighteen Issues and eighteen are left behind, and
    touching the same Issue next time grabs the stale tree. **Nothing with uncommitted changes is
    removed** — whether something would be missed is not this side's call to make."""
    root = os.getcwd()
    wt = os.path.join(root, ".orgforge", "wt", f"issue-{issue}")
    if not os.path.isdir(wt):
        return None
    code, out = _raw(["git", "-C", wt, "status", "--porcelain"])
    if code == 0 and out.strip():
        return (f"the worktree was kept: {wt}\n"
                f"  it carries uncommitted changes ({len(out.strip().split(chr(10)))}). "
                f"Look at them, then `git worktree remove`.")
    code, out = _raw(["git", "worktree", "remove", wt])
    if code != 0:
        return f"could not remove the worktree: {wt} ({out.strip()[:80]})"
    return f"cleaned up the worktree: .orgforge/wt/issue-{issue}"


def cmd_begin(a):
    # The worktree's base resolves from the constitution's integration_ref (OBS-053 / #106).
    # It is decided before anything is written to the ledger — stacking claims while it stays
    # undecided leaves the fail-closed half-done.
    if not getattr(a, "no_worktree", False):
        base, base_err = resolve_integration_base(getattr(a, "base", None))
        if base_err:
            print(f"cannot determine the worktree base for begin (#{a.issue}):\n{base_err}",
                  file=sys.stderr)
            return 2
        a.base = base
    warns = [] if getattr(a, "no_check", False) else _readiness(a.issue)
    if warns:
        print(f"pre-start checks (#{a.issue}):", file=sys.stderr)
        for w in warns:
            print(f"  ⚠ {w}", file=sys.stderr)
        print("  — these do NOT stop you. Proceed knowingly and it runs as-is.\n"
              "     What is built on a broken premise ends up on the side the gate rejects "
              "later.\n",
              file=sys.stderr)
    parent = a.parent or resolve_parent(a.issue)
    cid = a.candidate_id or _candidate_id(a.issue)
    if not a.candidate_id:
        events, _ = _events_for(a.issue)
        rounds = []
        for event in events:
            if event.get("class") != "rework_requested":
                continue
            try:
                rounds.append(int((event.get("payload") or {}).get("round")))
            except (TypeError, ValueError):
                continue
        if rounds:
            cid = f"{cid}-rework-{max(rounds)}"
    if parent is None:
        print(f"note: could not resolve the parent objective of #{a.issue}. The phase chain will look "
              f"only at its own admission (no inheritance from a parent). If there is an "
              f"intended parent, pass it with --parent.", file=sys.stderr)
    return _execute(_steps_begin(a, parent, cid), f"begin #{a.issue} ({a.role})")


def cmd_complete(a):
    if not (a.domain_model_updated or a.domain_model_none):
        print("either --domain-model-updated or --domain-model-none is required.\n"
              "docs/11 §4d: the ledger refuses cycle_completed unless it states what this cycle "
              "did to the domain model. Where nothing was established, write why (it becomes a "
              "claim the skeptic can refute).", file=sys.stderr)
        return 2
    # Detecting public surface and vocabulary is an **advisory** path — where the constitution
    # declares the integration target it is used, and in a legacy org with no declaration develop is
    # tried as before (staying silent as before where no diff can be taken).
    # complete itself is not made fail-closed (what #106 requires are the four paths that consume the
    # integration target).
    _diff_base, _ = resolve_integration_base(None)
    surfaces = _new_public_surfaces(a.issue, base=_diff_base or "develop")
    if surfaces and not (a.new_surface or a.new_surface_none):
        print(f"⚠ this change newly exposes a surface (#{a.issue}):", file=sys.stderr)
        for s in surfaces[:10]:
            print(f"    {s['kind']}: {s['name']}"
                  + (f"  ⟨{s['note']}⟩" if s["note"] else ""), file=sys.stderr)
        print("  **An authorization hole is born where \"one function was added\".**\n"
              "  Confirm who can call it and what can be done once it is called, then\n"
              "  declare it with --new-surface \"<surface>: <who can call it / what it can do>\".\n"
              "  If you judge it not to be a public surface, --new-surface-none \"<reason>\".\n"
              "  The declaration reaches the gate and stays in the ledger.", file=sys.stderr)
        return 2

    if a.domain_model_none:
        # Let nothing walk past: has a cycle written up as "it settled no rule" in fact created
        # vocabulary?
        ex = _new_exports(a.issue, base=_diff_base or "develop")
        if ex:
            print(f"check: none_asserted, yet this cycle added {len(ex)} public symbol(s):",
                  file=sys.stderr)
            for kind, name in ex[:12]:
                print(f"    {kind} {name}", file=sys.stderr)
            print("Are these the domain's vocabulary (ubiquitous language)? If they are, record "
                  "them with --domain-model-updated.\n"
                  "If you judge that they are not, carry on — **the judgment is yours**, and this is "
                  "only a question asked back so nothing walks past.\n", file=sys.stderr)

    cid = a.candidate_id or _candidate_id(a.issue)
    if a.new_surface or a.new_surface_none:
        _ledger("append", "--actor", a.agent or a.role, "--class", "public_surface_declared",
                "--natural-key", f"surface-{a.issue}",
                "--payload", json.dumps(
                    {"role": a.agent or a.role, "issue": a.issue,
                     "surfaces": [{"kind": "declared", "name": s, "exposure": "", "authz": ""}
                                  for s in (a.new_surface or [])],
                     "none_asserted": a.new_surface_none or ""}, ensure_ascii=False))
    rc = _execute(_steps_complete(a, cid), f"complete #{a.issue} ({a.role})")
    if rc == 0 and a.learned:
        # 3: the path by which doctrine accumulates was not connected to the cycle, and both
        # doctrine/ and conventions/ were empty. In the field a learning from repeating the same
        # failure three times ("a property test is meaningless unless it verifies at the place that
        # breaks") existed and would have stopped it had it been in doctrine. docs/06 writes that
        # accumulated failure is the most valuable context there is, yet no mouth for accumulating it
        # was open anywhere.
        # **Only as far as propose. The admit is the gate's job** (nobody canonises their own
        # learning).
        code, out = _run([os.path.join(HERE, "doctrine.py"), "propose",
                          _sub("doctrine"), a.agent or a.role,
                          "--claim", a.learned,
                          "--source", f"issue-{a.issue}",
                          "--confidence", str(a.confidence),
                          # Without provenance filled in, the gate cannot admit and the learning
                          # dies pending. The plumbing knows the date, so no human types it.
                          "--retrieved-at", _today(),
                          "--review-by", _plus_days(a.review_days),
                          *(["--affects", a.affects] if a.affects else [])])
        if code == 0:
            print(f"  proposed to doctrine (the admit is the gate's): {out.strip()[:100]}")
        else:
            print(f"  the propose to doctrine failed: {out.strip()[:120]}", file=sys.stderr)
    elif rc == 0:
        print(f"\n  hint: where this cycle produced a learning that will hold next time, leave it "
              f"with --learned. A learning that never enters doctrine does not reach the next Issue "
              f"(in the field the same failure was repeated three times).")
    if rc == 0:
        msg = _cleanup_worktree(a.issue)
        if msg:
            print(f"  {msg}")
        verdict, seq, near = _admission_for(a.issue)
        rv, rseq, _ = _refutation_for(a.issue)
        if verdict == "admit" and rv == "survives":
            print(f"\nNEXT: gate admit (seq {seq}) · skeptic survives (seq {rseq}). It can be "
                  f"integrated:\n"
                  f"  python3 org_cycle.py integrate --issue {a.issue}")
        elif verdict == "admit" and rv == "refuted":
            print(f"\nNEXT: the skeptic refuted it (seq {rseq}). It must not be integrated — answer "
                  f"the refutation, then put it through verify again.")
        elif verdict == "admit":
            print(f"\nNEXT: the gate has admitted #{a.issue} (seq {seq}). The skeptic is next:\n"
                  f"  python3 org_cycle.py verify --issue {a.issue} --role skeptic")
        elif verdict:
            print(f"\nNEXT: the gate's verdict is `{verdict}` (seq {seq}). It is not an admit, so "
                  f"answer what it raised and put it through verify again.")
        else:
            print(f"\nNEXT: the gate's admission is still missing:\n"
                  f"  python3 org_cycle.py verify --issue {a.issue} --role gate\n"
                  f"A maker cannot admit its own work (the ledger refuses it).")
            # Before declaring "there is none", show that it may have been mistaken for something
            # else. In the field a function name sat in deliverable, so it printed "still missing"
            # while the record existed. This prints it in a form where the cause is immediate.
            if near:
                s, d, i = near[-1]
                print(f"(a close record: seq {s} holds an admission_decided, but with "
                      f"deliverable={d!r} / issue={i!r} it does not match #{a.issue}. The gate may "
                      f"have recorded it under an identifier other than the Issue number)",
                      file=sys.stderr)
    return rc


def cmd_plan(a):
    """Run nothing; print only the sequence of events that would be typed."""
    # plan is precisely the place for "look before you type", so the pre-start checks appear here
    # too.
    for w in ([] if getattr(a, "no_check", False) else _readiness(a.issue)):
        print(f"  ⚠ {w}", file=sys.stderr)
    # plan runs nothing, so it does not stop. It does forewarn that begin will fail closed (#106).
    base, base_err = resolve_integration_base(getattr(a, "base", None))
    if base_err:
        print(f"  ⚠ begin cannot decide the worktree base and will fail:\n{base_err}",
              file=sys.stderr)
    else:
        a.base = base
    parent = a.parent or resolve_parent(a.issue)
    cid = a.candidate_id or _candidate_id(a.issue)
    print(f"# begin #{a.issue} ({a.role}) — parent=#{parent or '(unresolved)'} "
          f"candidate_id={cid}")
    for i, (desc, _) in enumerate(_steps_begin(a, parent, cid), 1):
        print(f"  {i}. {desc}")
    print(f"\n# complete #{a.issue} — running it needs --outputs and domain_model")
    return 0
