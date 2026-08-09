"""Branches and worktrees — deriving a feature branch deterministically, and a work tree per Issue.

Run makers in parallel in one tree and a commit for one Issue lands on another Issue's branch."""

import hashlib
import json
import os
import re
import subprocess
import sys

from ._core import (
    _slug,
    gh,
    issue_labels,
)


def derived_branch_name(issue, title):
    """The name derived as a pure function of (issue, title) — a convention for creation time, not
    a permanent identity (#107). If the title later changes it drifts from the branch that actually
    exists, so **wherever the answer must be a real branch**, do not use this directly; reconcile
    with resolve_issue_branch."""
    if not title:
        # With the title unknown (gh unreachable and so on) the derivation is **genuinely**
        # slug-less. _slug returns a hash (te3b0c442…) even for an empty string, so without
        # dropping it here we would announce "omitting the slug" while deriving a phantom
        # hash-bearing name — the announcement and the actual name disagreeing (#107 rework).
        return f"feat/issue-{issue}"
    slug = _slug(title)
    return f"feat/issue-{issue}-{slug}" if slug else f"feat/issue-{issue}"


def _make_worktree(name, base, issue):
    """Create a git worktree dedicated to a branch — the only safe shape for a parallel fan-out.

    **Why a checkout will not do.** `git checkout` *switches the tree*, so running two makers in
    parallel in one directory puts one's commits on the other's branch. That happened in the field
    (a commit landed on `feat/issue-8-settle`). The contents were separable so it was recoverable,
    but **it recurs for as long as they run in parallel in one tree**.

    Preventing it by an operating habit — "check you are on the right branch every time" — is a
    design that depends on judgment, and it will certainly break across 18 Issues in parallel. A
    worktree is **physically a separate directory**, so there is nothing to mix.

    R0: borrow git's worktree as it is. No ref store and no concurrency control of our own."""
    import os
    import subprocess
    roots = subprocess.run(["git", "worktree", "list", "--porcelain"],
                           capture_output=True, text=True, timeout=30)
    if roots.returncode != 0:
        print("we are outside a git repository.", file=sys.stderr)
        return 2
    primary = next((line[len("worktree "):].strip()
                    for line in roots.stdout.splitlines()
                    if line.startswith("worktree ")), None)
    if not primary:
        print("cannot resolve the primary worktree.", file=sys.stderr)
        return 2
    wt = os.path.join(primary, ".orgforge", "wt", f"issue-{issue}")
    if os.path.isdir(wt):
        print(f"the worktree already exists (idempotent): {wt}")
        print(f"\ncd {wt}    # work here. Do not touch the original tree")
        return 0
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    # Attach to the branch if it exists; otherwise create it from base
    p = subprocess.run(["git", "worktree", "add", "-b", name, wt, base],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        p = subprocess.run(["git", "worktree", "add", wt, name],
                           capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(f"cannot create the worktree: {(p.stderr or '').strip()[:200]}", file=sys.stderr)
        return 2
    print(f"worktree: {wt}  (branch {name} off {base})")
    print(f"\ncd {wt}    # work here. Do not touch the original tree")
    print("When it is done, open a PR and clear it away with `git worktree remove`.")
    return 0


def cmd_branch(a):
    """Print (and optionally create) the DETERMINISTIC feature branch for a task Issue:
    `feat/issue-<N>-<slug-of-title>` off `develop` (the org's branch policy, docs/11 §4c). The name is
    a pure function of (issue number, title), so two makers / a replay derive the SAME branch — the
    reproducibility rule that governs Issue creation, applied to branches. With --create it also runs
    `git checkout -b <name> develop` in the current repo (R0: borrow git; we build no ref store).

    Query mode (no --create/--worktree) answers "which branch IS this Issue's branch" and therefore
    reports only a branch that EXISTS: the Issue worktree's HEAD is authoritative, else the derived
    name if it is a real branch, else fail-closed (#107 — a derived name is a creation convention,
    not durable identity; the title can change after the branch was cut)."""
    labels, err = issue_labels(a.repo, a.issue)  # also validates the Issue exists
    code, out = gh(["issue", "view", str(a.issue), "--repo", a.repo, "--json", "title"])
    if code != 0:
        # The slug only makes the name readable; the identifier is the Issue number. Not reaching
        # GitHub (offline, expired auth, repo not created) is never a reason to be unable to
        # prepare a workspace — stop here and parallel makers get no separate trees, fall back into
        # one, and cross.
        # Query mode is not stopped either (#107): the answer lives in git (the worktree's HEAD, or
        # a branch that exists), so derive without a slug and leave it to the resolution below.
        print(f"warning: could not fetch the Issue title, so the slug is omitted "
              f"({out.strip()[:80]})",
              file=sys.stderr)
        title = ""
    else:
        try:
            title = json.loads(out).get("title", "")
        except Exception:
            title = ""
    name = derived_branch_name(a.issue, title)
    if not (getattr(a, "worktree", False) or getattr(a, "create", False)):
        # Query mode (#107): the answer to "which branch belongs to this Issue" has to be **a
        # branch that exists**. A derived name is a creation convention, not a permanent identity —
        # a retitle or a hand-picked name drifts from what exists (Tatekae OBS-012: derived
        # `feat/issue-15-google` against the real `feat/issue-15-login-redirect`, so gc misread an
        # already-integrated worktree as unintegrated).
        # The worktree's HEAD > a derived name that exists > fail-closed. A name that does not
        # exist is never printed silently.
        from orgcycle._core import resolve_issue_branch
        resolved, warn, err = resolve_issue_branch(a.issue, derived=name)
        if err:
            print(err, file=sys.stderr)
            return 2
        if warn:
            print(f"warning: {warn}", file=sys.stderr)
        print(resolved)
        return 0
    print(name)
    base = getattr(a, "base", None)
    if not base:
        from orgcycle._core import resolve_integration_base
        base, error = resolve_integration_base()
        if not base:
            print(error, file=sys.stderr)
            return 2
    # --worktree implies --create (creating a worktree yields the separate workspace).
    # For a parallel fan-out this is the right answer — checkout switches the tree, so it always
    # ends up mixed.
    if getattr(a, "worktree", False):
        return _make_worktree(name, base, a.issue)
    if getattr(a, "create", False):
        import subprocess
        # **In an org operating in parallel through worktrees, never switch the main repository's
        # branch.** In the field `--create` moved main off develop, and unnoticed, the integration
        # tests meant for develop were running on another Issue's branch. If `.orgforge/wt/`
        # already exists, treat it as worktree operation and create a worktree (the same path as
        # `--worktree`).
        wt_dir = os.path.join(os.getcwd(), ".orgforge", "wt")
        if (not getattr(a, "no_worktree", False)) and os.path.isdir(wt_dir) and any(
                n.startswith("issue-") for n in os.listdir(wt_dir)):
            print(f"note: this org operates in parallel through worktrees "
                  f"({len([n for n in os.listdir(wt_dir) if n.startswith('issue-')])} under "
                  f"{wt_dir}).\n"
                  f"  The main repository's branch is not switched; a worktree is created "
                  f"instead — once main moves off develop, the integration tests meant for develop "
                  f"run on another Issue's branch.\n"
                  f"  To switch on main anyway, add --no-worktree.", file=sys.stderr)
            return _make_worktree(name, base, a.issue)
        try:
            p = subprocess.run(["git", "checkout", "-b", name, base],
                               capture_output=True, text=True, timeout=30)
            if p.returncode != 0:
                # branch may already exist (idempotent) — try to switch to it
                p2 = subprocess.run(["git", "checkout", name], capture_output=True, text=True, timeout=30)
                if p2.returncode != 0:
                    print(f"git error creating/switching branch: {(p.stderr or '')+(p2.stderr or '')}",
                          file=sys.stderr)
                    return 2
                print(f"branch {name} already existed — switched to it (idempotent).", file=sys.stderr)
            else:
                print(f"created and switched to {name} off {base}.\n"
                      f"  ⚠ **The main repository's branch was switched.** Before running the "
                      f"integration tests meant for develop, return with `git checkout {base}` "
                      f"(for parallel operation, use --worktree).", file=sys.stderr)
        except Exception as e:
            print(f"git not available: {e}", file=sys.stderr)
            return 2
    return 0
