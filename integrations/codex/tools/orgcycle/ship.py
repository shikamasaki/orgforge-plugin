"""Send a deliverable outward — handback / integrate.

It opens a PR and fans in to develop. Whether to merge is not judged — it only reconciles that the
preconditions (the gate's admit and the skeptic's survives) are both present in the ledger."""

import json
import os
import re
import sys

from ._core import (
    _admission_for,
    _branch_for,
    _candidate_id,
    _execute,
    _gh_sync,
    _issue_body,
    _ledger,
    _raw,
    _refutation_for,
    _repo,
    issue_worktree_head,
    local_branch_for,
    resolve_integration_base,
)


def _resolve_integration_branch(issue, requested=None):
    """Resolve one durable local branch + commit for an Issue, or return an actionable error.

    The deterministic title slug is a creation convention, not durable identity: a branch can be
    renamed or recreated after the Issue title changes. Never turn a missing ref into a zero-change
    preview. Exact explicit ``--branch`` values are existence-checked; implicit resolution may use a
    sole ``feat/issue-N[-…]`` candidate, but ambiguity and local/tracking divergence always stop.
    A tracking-only ref is diagnostic, not a merge target: without a local branch we cannot know
    whether the last fetch is fresh, so the operator must fetch/checkout explicitly.

    Implicit resolution (no ``requested``) consults the Issue worktree FIRST (#107): the worktree's
    HEAD branch is authoritative even when it does not match the `feat/issue-N*` convention — a
    retitle + re-run of begin cuts a fresh slug branch while the real work sits in the old
    worktree, and admitting only conventional names would merge that stray branch's unreviewed
    content with exit 0. If both the worktree's branch and a conventional candidate exist and
    disagree, we STOP and name both — auto-picking either would hide the split-brain.
    """
    derived = requested or _branch_for(issue)
    # #107: with no explicit --branch, the worktree's real HEAD is the first candidate for
    # integration. A derived name is a creation convention, not a permanent identity — admit only
    # convention-shaped names as candidates and the worktree's non-conventional branch is discarded
    # while a stray `feat/issue-N-*` becomes the sole candidate and **is merged unreviewed, with no
    # warning** (demonstrated by the skeptic's refutation).
    wt_head = None if requested else issue_worktree_head(issue)
    if wt_head:
        derived = wt_head
    prefix = f"feat/issue-{issue}"
    requested_logical = derived[len("origin/"):] if derived.startswith("origin/") else derived
    code, out = _raw([
        "git", "for-each-ref", "--format=%(refname:short)",
        "refs/heads", "refs/remotes/origin",
    ])
    if code != 0:
        return None, None, ("cannot enumerate the git branch refs, so the integration target "
                            "cannot be confirmed.")

    entries = {}

    def add(logical, ref, available):
        is_issue_candidate = logical == prefix or logical.startswith(prefix + "-")
        if not is_issue_candidate and not ((requested or wt_head)
                                           and logical == requested_logical):
            return
        entry = entries.setdefault(logical, {"local": None, "tracking": None})
        if available == "local":
            entry["local"] = ref
        elif available == "tracking":
            entry["tracking"] = ref

    for ref in (out or "").splitlines():
        ref = ref.strip()
        if not ref:
            continue
        if ref.startswith("origin/"):
            add(ref[len("origin/"):], ref, "tracking")
        else:
            add(ref, ref, "local")

    def resolve(logical):
        entry = entries.get(logical) or {}
        local, tracking = entry.get("local"), entry.get("tracking")

        def sha(ref):
            if not ref:
                return None
            rc, value = _raw(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"])
            return value.strip() if rc == 0 and value.strip() else None

        local_sha, tracking_sha = sha(local), sha(tracking)
        if local and not local_sha:
            return None, None, f"cannot resolve the commit of the local ref {local}."
        if tracking and not tracking_sha:
            return None, None, f"cannot resolve the commit of the tracking ref {tracking}."
        if local_sha and tracking_sha and local_sha != tracking_sha:
            return None, None, (f"the local and tracking refs of {logical} have diverged: "
                                f"local={local_sha[:12]}, tracking={tracking_sha[:12]}。"
                                "bring them into agreement with fetch/rebase/merge, or state a "
                                "commit SHA you have verified with --branch before integrating.")
        if local_sha:
            return local, local_sha, None
        if tracking_sha:
            return None, None, (f"the candidate {tracking} exists only as a tracking ref. Run "
                                f"`git fetch --prune origin` and check it out, confirm the "
                                f"contents as a local branch, and only then integrate.")
        return None, None, None

    if wt_head:
        # Where the real HEAD and a convention-shaped candidate both exist and disagree, **stop
        # rather than choose** (#107 rework). Choose one silently and the other's contents are
        # either lost or merged, unreviewed.
        strays = [n for n in sorted(entries)
                  if n != requested_logical and (n == prefix or n.startswith(prefix + "-"))]
        if strays:
            return None, None, (
                f"the real branch of worktree .orgforge/wt/issue-{issue} ({wt_head}) and the "
                f"convention-shaped candidate(s) {', '.join(strays)} both exist and disagree. "
                f"Which is the integration target is not judged here — inspect the contents and "
                f"state it with --branch (if the convention-shaped one is a stray, clear it with "
                f"`git branch -D` and run again).")

    exact_ref, exact_sha, exact_error = resolve(requested_logical)
    if exact_error:
        return None, None, exact_error
    if exact_ref:
        return exact_ref, exact_sha, None

    candidate_names = sorted(entries)
    candidate_text = ", ".join(candidate_names) if candidate_names else "none"
    if requested:
        # An immutable commit SHA (or tag) is a valid explicit override even when it is not an Issue
        # branch. The merge below uses this resolved SHA, so a later ref move cannot change subject.
        rc, explicit_sha = _raw(["git", "rev-parse", "--verify", f"{derived}^{{commit}}"])
        if rc == 0 and explicit_sha.strip():
            return derived, explicit_sha.strip(), None
        return None, None, (f"--branch {derived} exists in neither the local nor the tracking "
                            f"refs. Candidates for this Issue: {candidate_text}. If needed, run "
                            f"`git fetch --prune origin` and try again.")

    if len(candidate_names) == 1:
        only = candidate_names[0]
        ref, subject_sha, error = resolve(only)
        if error:
            return None, None, error
        if ref:
            return ref, subject_sha, None
    if not candidate_names:
        return None, None, (f"the derived branch {derived} does not exist, and there is no "
                            f"{prefix}* candidate among the local or tracking refs either. Run "
                            f"`git fetch --prune origin` and try again, run begin/handback first, "
                            f"or pass --branch.")
    return None, None, (f"the derived branch {derived} does not exist and there are several "
                        f"candidates: {candidate_text}. State the integration target with "
                        f"--branch.")


def _integrate_preview(issue, branch, subject_sha, base, test):
    """Show what is about to be integrated. **Its main purpose is forewarning where a clash is
    likely.**

    Failures after an integration are largely false positives from the worktree scan, and telling
    them apart takes time. Knowing beforehand is faster. If another worktree running in parallel
    touches the same files, that is shown too — where several Issues are touching one manifest at
    once, seeing it first is cheaper than finding out later.
    """
    code, base_sha = _raw(["git", "rev-parse", "--verify", f"{base}^{{commit}}"])
    if code != 0 or not base_sha.strip():
        return (f"{branch} → {base}\n  ✗ the base ref {base} does not exist.",
                {}, "base ref missing")
    code, verified_subject = _raw([
        "git", "rev-parse", "--verify", f"{subject_sha}^{{commit}}",
    ])
    if code != 0 or verified_subject.strip() != subject_sha:
        return (f"{branch} → {base}\n  ✗ the resolved subject {subject_sha[:12]} is "
                f"unavailable.",
                {}, "subject commit missing")

    L = [f"{branch} @ {subject_sha[:12]} → {base}"]
    code, files = _raw(["git", "diff", "--name-only", f"{base_sha.strip()}...{subject_sha}"])
    if code != 0:
        return ("\n".join(L + ["  ✗ the refs exist but git diff failed."]),
                {}, "git diff failed")
    changed = [f for f in (files or "").split("\n") if f.strip()]
    L.append(f"  changed: {len(changed)} files")
    for f in changed[:12]:
        L.append(f"    {f}")
    if len(changed) > 12:
        L.append(f"    … and {len(changed) - 12} more")

    code, ahead = _raw(["git", "log", "--oneline", f"{base_sha.strip()}..{subject_sha}"])
    if code != 0:
        return ("\n".join(L + ["  ✗ cannot read the commit range. Re-confirm the branch "
                                "exists."]),
                {}, "git log failed")
    n = len([x for x in (ahead or "").split("\n") if x.strip()])
    L.append(f"  commits: {n}")

    # Whether it touches the same files as another worktree running in parallel
    wt_base = os.path.join(os.getcwd(), ".orgforge", "wt")
    overlaps = {}
    if os.path.isdir(wt_base):
        for name in sorted(os.listdir(wt_base)):
            if not name.startswith("issue-") or name == f"issue-{issue}":
                continue
            other = name[len("issue-"):]
            ob = _branch_for(other)
            c2, of = _raw(["git", "diff", "--name-only", f"{base}...{ob}"])
            if c2 != 0:
                continue
            shared = sorted(set(changed) & {x for x in (of or "").split("\n") if x.strip()})
            if shared:
                overlaps[other] = shared
    for other, shared in overlaps.items():
        L.append(f"  ⚠ #{other} is changing the same files: {', '.join(shared[:5])}")

    # An integration touching a CI workflow shows **which job the step landed in**.
    # Even with valid YAML and green tests, **a step landing in a job that only runs conditionally
    # means that check never runs once**. In operation, a union merge put the result at the end of
    # a conditional job, and while the Issue it depended on stayed unintegrated, the check that had
    # been added was not running.
    # **The YAML's meaning is not interpreted** — only job names and the presence of `if:` are
    # emitted. The judgment is a person's.
    for f in changed:
        if not re.search(r"\.github/workflows/.+\.ya?ml$", f):
            continue
        code, ci = _raw(["git", "show", f"{subject_sha}:{f}"])
        if code != 0:
            continue
        # **Look only under `jobs:`.** The top level also holds `on:`, `permissions:` and the
        # like, whose children (`pull_request:`, `push:`) get mistaken for jobs — which is what the
        # first implementation did.
        jobs, cur, conditional = [], None, set()
        in_jobs = False
        for line in (ci or "").split("\n"):
            if re.match(r"^jobs:\s*$", line):
                in_jobs = True
                continue
            if in_jobs and re.match(r"^\S", line):
                in_jobs = False          # leave at the next top-level key
            if not in_jobs:
                continue
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if m:
                cur = m.group(1)
                jobs.append(cur)
                continue
            # Count both the job's own `if:` and an `if:` on any of its steps — either way, "the
            # check does not run while the condition is unmet" holds.
            # A step's `if:` can also be written as `- if: …` (the first element of a list). Miss
            # the hyphen and you drop **exactly the shape you are trying to catch**: conditional
            # execution at step level.
            if cur and re.match(r"^\s{4,}(?:-\s+)?if:\s*\S", line):
                conditional.add(cur)
        if jobs:
            L.append(f"  ⚠ it touches CI: {f}")
            L.append(f"      job: {', '.join(j + ' (if: conditional)' if j in conditional else j for j in jobs)}")
            if conditional:
                L.append(f"      **There is a conditional job.** If the step you added landed "
                         f"there, that check never runs once while the condition is unmet — with "
                         f"valid YAML and green tests, there is no way to notice it is not "
                         f"checking. Confirm where it landed.")

    # The current state of develop (whether the integration target is already broken)
    L.append(f"  what runs after integration: {test}")
    return "\n".join(L), overlaps, None


def _plan_integrate(a, branch, subject_sha, base):
    body, overlaps, preview_error = _integrate_preview(
        a.issue, branch, subject_sha, base, a.test)
    print(body)
    if preview_error:
        return 3
    av, aseq, _ = _admission_for(a.issue)
    rv, rseq, _ = _refutation_for(a.issue)
    print(f"  gate: {av or 'not recorded'}" + (f" (seq {aseq})" if aseq else "")
          + f" · skeptic: {rv or 'not recorded'}" + (f" (seq {rseq})" if rseq else ""))
    if not (av == "admit" and rv == "survives"):
        print("  -> the preconditions are not met; integrating now would be stopped anyway.")
    elif overlaps:
        print("  -> integrable, but look at the overlap above first"
              "(learning of a clash beforehand is cheaper than after the integration).")
    else:
        print("  -> integrable.")
    return 0


def cmd_handback(a):
    """C: push the feature branch, open a PR against develop, and tie it to the Issue.

    /org-work §4 said "each child's feature branch → PR → develop", but no tool opened the PR. In
    the field that produced zero PRs, direct integration by `git merge`, and integrated Issues left
    OPEN. **The premise of operating through GitHub did not hold.**

    The body carries `Closes #N`, so merging into develop closes the Issue automatically.
    Whether to merge is not judged — the plumbing ends at opening the PR.
    """
    branch, subject_sha, branch_error = _resolve_integration_branch(a.issue, a.branch)
    if branch_error:
        print(f"cannot resolve the handback branch (#{a.issue}): {branch_error}", file=sys.stderr)
        return 3
    local_code, _ = _raw(["git", "show-ref", "--verify", f"refs/heads/{branch}"])
    if local_code != 0:
        print(f"handback needs a pushable local branch, but {branch} is not one.\n"
              "  Check the branch out, then re-run.", file=sys.stderr)
        return 3
    # The PR's integration target is resolved from the constitution's integration_ref (#106).
    # `gh pr create --base` takes a branch name, so a declaration shaped origin/main maps to main.
    resolved_base, base_err = resolve_integration_base(getattr(a, "base", None))
    if base_err:
        print(f"cannot determine handback's integration target (#{a.issue}):\n{base_err}",
              file=sys.stderr)
        return 2
    base = local_branch_for(resolved_base)

    # Precondition: the gate's admit (a PR is for showing, so it may be opened before the skeptic)
    av, aseq, _ = _admission_for(a.issue)

    title, body = _issue_body(a.issue)
    if title is None:
        title = f"Issue #{a.issue}"

    # If a PR already exists, do not open another (idempotent)
    code, out = _raw(["gh", "pr", "list", "--head", branch, "--json", "number,url", "--limit", "1"]
                     + (["--repo", _repo()] if _repo() else []))
    existing = None
    if code == 0:
        try:
            arr = json.loads(out or "[]")
            existing = arr[0] if arr else None
        except Exception:
            pass

    pr_body = [
        f"Closes #{a.issue}",
        "",
        f"## What was built",
        a.summary or "(one line via --summary)",
        "",
        "## The DoD's real output",
        "```",
        (a.result or "(paste the actual output into --result)").strip(),
        "```",
        "",
        f"## Judgment",
        (f"gate: `{av}`（ledger seq {aseq}）" if av else
         "the gate's admission is still pending. `org_cycle.py verify --issue %d --role gate`"
         % a.issue),
        "",
        f"The spec is the body of #{a.issue}. The reasoning behind each judgment is recorded in "
        f"that Issue's comments (human diff review is retired — docs/11 §4f).",
    ]

    steps = [
        (f"push {branch}",
         lambda: _raw(["git", "push", "-u", "origin", branch])),
    ]
    if existing:
        print(f"a PR already exists: {existing.get('url')} — not reopened (only the push is "
              f"updated)")
    else:
        steps.append(
            (f"open the PR ({branch} → {base})",
             lambda: _raw(["gh", "pr", "create", "--base", base, "--head", branch,
                           "--title", f"{title} (#{a.issue})",
                           "--body", "\n".join(pr_body)]
                          + (["--repo", _repo()] if _repo() else []))))
    rc = _execute(steps, f"handback #{a.issue} → {base}")
    if rc != 0:
        return rc

    code, out = _raw(["gh", "pr", "list", "--head", branch, "--json", "url", "--limit", "1"]
                     + (["--repo", _repo()] if _repo() else []))
    url = ""
    try:
        arr = json.loads(out or "[]")
        url = arr[0]["url"] if arr else ""
    except Exception:
        pass

    # B: a fact the tool knows goes in automatically. All a person writes is the summary.
    return _execute([
        (f"log handback_opened → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "handback_opened",
                          "--event-id", f"handback-{a.issue}",
                          "--detail", f"opened the PR {branch} → {base}: "
                                      f"{url or '(URL not obtained)'}",
                          "--command", f"gh pr create --base {base} --head {branch}",
                          "--result", (a.result or out or "PR created").strip()[:4000],
                          "--files", a.files or branch,
                          "--next-step", f"skeptic → `org_cycle.py integrate --issue {a.issue}`")),
    ], f"record handback #{a.issue}")


def cmd_integrate(a):
    """Run the fan-in to develop. **Whether to merge is not judged** — it reconciles that the
    preconditions are present, and where they are, executes the mechanical steps (merge →
    post-integration test → record).

    If fan-out is half of it, fan-in is the other half, and left as a prose runbook it gets skipped.
    In the field, work was "integrated with no refutation in the ledger, and no
    integration_admitted recorded either". The moment just before integration is the easiest to
    skip, so that is what becomes plumbing.
    """
    if getattr(a, "plan", False):
        plan_base, base_err = resolve_integration_base(getattr(a, "base", None))
        if base_err:
            print(f"cannot determine the integration target (#{a.issue}):\n{base_err}",
              file=sys.stderr)
            return 2
        branch, subject_sha, branch_error = _resolve_integration_branch(a.issue, a.branch)
        if branch_error:
            print(f"cannot resolve the branch to integrate (#{a.issue}): {branch_error}",
                  file=sys.stderr)
            return 3
        return _plan_integrate(a, branch, subject_sha, plan_base)
    av, aseq, _ = _admission_for(a.issue)
    rv, rseq, _ = _refutation_for(a.issue)
    problems = []
    if av != "admit":
        problems.append(f"there is no admit from the gate (verdict={av or 'not recorded'}) — "
                        f"`org_cycle.py verify --issue {a.issue} --role gate`")
    if rv != "survives":
        problems.append(f"there is no survives from the skeptic "
                        f"(verdict={rv or 'not recorded'}) — "
                        f"`org_cycle.py verify --issue {a.issue} --role skeptic`")
    if problems and not a.force:
        print(f"the preconditions for integration are not met (#{a.issue}):", file=sys.stderr)
        for x in problems:
            print(f"  ✗ {x}", file=sys.stderr)
        print("\ndocs/11 / agents/gate.md: only what survived the skeptic's refutation moves "
              "on.\n"
              "A comment on the Issue with nothing in the ledger is \"not recorded\" — one side "
              "of the double record going missing is the failure that actually happens, so this "
              "looks at the ledger.\n"
              "To proceed knowing the preconditions are unmet, use --force (state why in --why).",
              file=sys.stderr)
        return 4

    branch, subject_sha, branch_error = _resolve_integration_branch(a.issue, a.branch)
    if branch_error:
        print(f"cannot resolve the branch to integrate (#{a.issue}): {branch_error}",
                  file=sys.stderr)
        return 3
    # The integration target is resolved from the constitution's integration_ref (OBS-048, #106).
    # checkout needs a branch name, so a form like origin/main maps to main. The record keeps the
    # ref exactly as declared — the answer to "where was it integrated" is written in the
    # constitution's vocabulary.
    base, base_err = resolve_integration_base(getattr(a, "base", None))
    if base_err:
        print(f"cannot determine the integration target (#{a.issue}):\n{base_err}",
              file=sys.stderr)
        return 2
    checkout_base = local_branch_for(base)
    # Hold on to the integration test's real output. **integrate was itself tripping the log's
    # mandatory check** — a milestone log requires --command/--result, integrate passed neither,
    # and the integration completed while only the log to the Issue went missing (a person filled
    # it in by hand in the field).
    # It holds the result of a run it performed itself, so there is no reason for a person to write
    # it.
    test_out = {"text": ""}

    def _run_test():
        code, out = _raw(a.test.split())
        test_out["text"] = (out or "").strip()
        return code, out

    steps = [
        (f"switch to {checkout_base}",
         lambda: _raw(["git", "checkout", checkout_base])),
        (f"merge {branch} @ {subject_sha[:12]} with --no-ff",
         lambda: _raw(["git", "merge", "--no-ff", subject_sha,
                       "-m", f"Merge {branch} into {checkout_base} (#{a.issue})"])),
        (f"the whole suite after integration: {a.test}", _run_test),
    ]
    rc = _execute(steps, f"integrate #{a.issue} → {base}")
    if rc != 0:
        print(f"\nthe integration was stopped. Check the state of {base} (if it merged and the "
              f"tests then failed, whether to revert or to fix is a judgment).", file=sys.stderr)
        return rc

    # Reaching here means "the combined suite is green" — the mechanical form of the integrate
    # gate (docs/11 §4c).
    # candidate_id: which candidate was integrated is recorded by the same derivation as cycle (the
    # trailer in the Issue body, or issue-N). With only the issue, the WIP side has to fall back on
    # alias correlation, and a parallel sibling of the same Issue or a backfilled integration takes
    # a live candidate down with it (#102 rework #2).
    rec = [
        (f"record integration_admitted",
         lambda: _ledger("append", "--actor", a.role, "--class", "integration_admitted",
                         "--natural-key", f"integrate-{a.issue}",
                         "--payload", json.dumps({"integration_branch": base,
                                                  "deliverables": [str(a.issue)],
                                                  "issue": a.issue,
                                                  "candidate_id": _candidate_id(a.issue),
                                                  "integration_subject_sha": subject_sha,
                                                  "combined_ci_ref": a.test,
                                                  "verdict": "pass"}, ensure_ascii=False))),
        (f"log → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "integration_admitted",
                          "--event-id", f"integrate-{a.issue}",
                          "--detail", (f"integrated {branch} @ {subject_sha[:12]} → {base}; "
                                       f"`{a.test}` green afterwards"),
                          "--command", a.test,
                          "--result", (test_out["text"]
                                       or "(the integration test's output was empty)")[-4000:],
                          "--files", f"{branch}@{subject_sha}")),
    ]
    return _execute(rec, f"record integrate #{a.issue}")
