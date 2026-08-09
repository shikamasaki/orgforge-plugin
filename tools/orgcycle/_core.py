"""org_cycle's shared parts — execution, the ledger, GitHub, and resolving identifiers.

Only what every subcommand uses belongs here. A helper for one particular subcommand goes in that
subcommand's module (a bloated core makes the split pointless)."""

import hashlib
import json
import os
import re
import subprocess
import sys


# Points at tools/. **This file lives in tools/orgcycle/, so go up one parent.**
# Forgetting to fix this during the split made _gh_sync lose sight of github_sync.py and
# `_branch_for` return a branch name with no slug (in the field, show's implementation lines and
# integrate --plan's change list silently went empty). Assembly-style tools walk past "not found"
# quietly, which makes the base of a path the first thing a split breaks.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def _run(args, capture=True):
    """Run python3 <tool> ... and return (code, out).

    The return value mixes stdout and stderr, so **the callee's banner mixes in**. `_branch_for`
    takes the first line and is safe for now, but the structure that allows the mixing is removed
    outright (0.22.1 had just stepped on one "breaks quietly" path).
    """
    env = dict(os.environ, ORG_QUIET="1")
    p = subprocess.run([sys.executable] + args, capture_output=capture, text=True,
                       timeout=60, env=env)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")) if capture else ""


def _raw(args):
    """Run an external command as-is. (code, out) — _run prefixes python3, so it cannot be used for
    gh."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout or "")
    except Exception as e:
        return 1, str(e)


def _ledger(*args):
    return _run([os.path.join(HERE, "ledger.py")] + list(args))


def _gh_sync(*args):
    return _run([os.path.join(HERE, "github_sync.py")] + list(args))


def _repo():
    import discover
    return discover.backlog_repo()


def resolve_integration_base(explicit=None, start=None):
    """Decide the integration ref. An explicit --base beats the constitution's
    enforcement.judges.integration_ref.

    With neither, return ``(None, reason)`` — **develop is not guessed** (#106). Measured on Tatekae,
    the constitution declared `integration_ref: origin/main` while begin/show/gc/integrate hard-coded
    develop, so one product held several answers to "where does this integrate"
    (OBS-048/053/054/057). The resolution verify uses (review_freshness.integration_ref_policy — #81)
    is shared as-is; no second parser is written.
    """
    if explicit:
        return str(explicit), None
    try:
        from discover import constitution
        path = constitution(start)
    except Exception:
        path = None
    from review_freshness import integration_ref_policy
    declared, ref, err = integration_ref_policy(path)
    if err:
        return None, f"the integration ref policy is invalid: {err}"
    if declared and ref:
        return ref, None
    return None, ("the integration target is undecided. The mere existence of develop is not a "
                  "reason to guess (#106).\n"
                  "  Either declare it in constitution.yaml, as "
                  "`enforcement.judges.integration_ref: origin/main`,\n"
                  "  or state `--base <ref>` explicitly for this run.")


def local_branch_for(ref, cwd=None):
    """A branch name usable for checkout / a PR base. A remote-tracking ref (origin/X) maps to X.

    integration_ref declares where work integrates, so it is written in remote-tracking form like
    origin/main. `git checkout origin/main` gives a detached HEAD and
    `gh pr create --base origin/main` errors, so only the contexts that actually check out or open a
    PR map it to a branch name (judgments and diffs keep the ref)."""
    code, _ = _raw(["git"] + (["-C", cwd] if cwd else [])
                   + ["rev-parse", "--verify", "--quiet", f"refs/remotes/{ref}"])
    if code == 0 and "/" in ref:
        return ref.split("/", 1)[1]
    return ref


def _execute(steps, label):
    """Run in order and stop at the first failure. **Never proceed quietly half-applied** — the
    worst outcome is reporting a ledger left inconsistent as "success", so it says where it
    stopped."""
    print(f"— {label} —")
    for i, (desc, fn) in enumerate(steps, 1):
        code, out = fn()
        tail = (out or "").strip().split("\n")[-1][:110]
        if code == 0:
            print(f"  {i}. ✓ {desc}")
        elif code == 10:
            print(f"  {i}. ⚠ {desc} — contended: {tail}", file=sys.stderr)
            print(f"\nstopped (ran through {i}/{len(steps)}). Another session holds it.",
                  file=sys.stderr)
            return 10
        else:
            print(f"  {i}. ✗ {desc}\n      {tail}", file=sys.stderr)
            print(f"\nstopped ({i-1}/{len(steps)} already ran). Nothing beyond this was typed.\n"
                  f"A refusal from the ledger means an order violation (docs/11 §2) — satisfy the "
                  f"precondition and run it again.\n"
                  f"Re-running is safe: each event is idempotent by natural key, so what is done "
                  f"becomes a no-op.",
                  file=sys.stderr)
            return 3
    print(f"  done ({len(steps)} step(s))")
    return 0



# ── verify (design 2): it takes on the plumbing only ────────────────────────
# All this may hold is "start gate/skeptic with the right material".
# It decides nothing about verdict, why, risk, or which mutation to try.
# The moment a tool judges, the gate becomes a formality, so that line is not crossed.


def _today():
    code, out = _raw(["date", "-u", "+%Y-%m-%d"])
    return (out or "").strip() or "UNSET"


def _plus_days(n):
    """The doctrine TTL. The default is 180 days — doctrine with no "how long may this be believed"
    lingers on old premises and does harm (docs/06 §3)."""
    for fmt in (["date", "-u", "-v", f"+{n}d", "+%Y-%m-%d"],
                ["date", "-u", "-d", f"+{n} days", "+%Y-%m-%d"]):
        code, out = _raw(fmt)
        if code == 0 and (out or "").strip():
            return out.strip()
    return "UNSET"


def _sub(kind):
    """The doctrine / conventions root. Left to discovery (it demands no environment variable)."""
    try:
        sys.path.insert(0, HERE)
        from discover import _sub_root
        return _sub_root(kind) or os.path.join(os.getcwd(), ".orgforge", kind)
    except Exception:
        return os.path.join(os.getcwd(), ".orgforge", kind)


def _issue_body(issue, repo=None):
    """A task Issue's title/body (= the SPEC / MUSTs). This is the specification under
    verification."""
    args = ["gh", "issue", "view", str(issue), "--json", "title,body"]
    r = repo or _repo()
    if r:
        args += ["--repo", r]
    code, out = _raw(args)
    if code != 0:
        return None, None
    try:
        d = json.loads(out)
        return d.get("title", ""), d.get("body", "")
    except Exception:
        return None, None


def _branch_for(issue):
    """That Issue's branch name. github_sync derives it deterministically, so borrow that."""
    code, out = _gh_sync("branch", "--issue", str(issue))
    if code == 0 and out.strip():
        return out.strip().split("\n")[0]
    return f"feat/issue-{issue}"


def _events_for(issue):
    """Return the ledger events relating to #issue in chronological order (excluding those voided by
    a correction)."""
    root = None
    try:
        sys.path.insert(0, HERE)
        from discover import ledger_root
        from ledger import voided_seqs
        root = ledger_root()
    except Exception:
        return [], set()
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return [], set()
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = voided_seqs(evs)
    want = str(issue).lstrip("#")
    mine = []
    for e in evs:
        pl = e.get("payload", {}) or {}
        ids = {str(pl.get(k, "")).lstrip("#") for k in
               ("deliverable", "issue", "claim_id", "candidate_id", "spec_ref") if pl.get(k)}
        alias = str(pl.get("pack_manifest_id") or pl.get("contract_ref") or "")
        if want in ids or alias in (f"issue-{want}", want):
            mine.append(e)
    return mine, voided


def _decision_for(issue, cls):
    """Find the `cls` judgment for #issue in the ledger.

    identity is the Issue number, but in the field a record was produced with "settle()" (a function
    name) in deliverable. **The Issue number is also in the payload's `issue`**, so reading one and
    declaring "there is none" merely drops information that was there. Both are read.

    Returns: (verdict, seq, near) — near is "a close record whose number does not match" (for
    identifying the cause).
    """
    root = None
    try:
        sys.path.insert(0, HERE)
        from discover import ledger_root
        root = ledger_root()
    except Exception:
        pass
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return None, None, []
    want = str(issue).lstrip("#")
    hit, near = None, []
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("class") != cls:
            continue
        pl = e.get("payload", {}) or {}
        # claim_id is refutation_attempted's identifier (it points at candidate_id)
        ids = [str(pl.get(k, "")).lstrip("#")
               for k in ("deliverable", "issue", "claim_id") if pl.get(k) is not None]
        if want in ids:
            hit = (pl.get("verdict"), e.get("seq"))
        elif any(ids):
            near.append((e.get("seq"), ids[0], pl.get("verdict")))
    return (hit[0], hit[1], near) if hit else (None, None, near)


def _admission_for(issue):
    """The gate's admission. See _decision_for for the details."""
    return _decision_for(issue, "admission_decided")


def _refutation_for(issue):
    """The skeptic's refutation attempt. **Reconciled with the same strength as an admission.**

    docs/11 and agents/gate.md set that only what survives the skeptic's refutation may deploy, and
    the ledger's requires_prior imposes that on `result_deployed`. Integration, however, sits ahead
    of that, and in the field work came close to being integrated into develop with not one
    refutation_attempted in the ledger (the Issue carried a comment, so only one side of the double
    record had gone missing).
    The likeliest place for it to slip is just before integration, so that is where it reconciles.
    """
    return _decision_for(issue, "refutation_attempted")


def resolve_parent(issue, repo=None):
    """Resolve a task Issue's parent objective number **automatically**.

    This is what a human used to pick out by eye and type in. `github_sync create --parent` writes
    `Parent: #N` into the body, so it can be read from there. GitHub's native sub-issue API is used
    alongside it (either one succeeding is enough).
    None where neither works — a deliverable with no parent reads only its own admit, as before."""
    repo = repo or _repo()
    if not repo:
        return None
    # 1) the native parent/child relation (the most certain, where it exists)
    code, out = _run(["-c", "import subprocess,sys,json;"
                      "p=subprocess.run(['gh','api',f'repos/{sys.argv[1]}/issues/{sys.argv[2]}',"
                      "'--jq','.sub_issue_of.number // empty'],capture_output=True,text=True);"
                      "print(p.stdout.strip())", repo, str(issue)])
    if code == 0 and out.strip().isdigit():
        return out.strip()
    # 2) the body's `Parent: #N` (written by github_sync create)
    p = subprocess.run(["gh", "issue", "view", str(issue), "--repo", repo, "--json", "body",
                        "-q", ".body"], capture_output=True, text=True, timeout=30)
    if p.returncode == 0:
        m = re.search(r"^\s*Parent:\s*#?(\d+)", p.stdout or "", flags=re.M | re.I)
        if m:
            return m.group(1)
    return None


def _candidate_id(issue, repo=None):
    """Read the Issue body's `candidate_id:` trailer. Where there is none, use the Issue number."""
    repo = repo or _repo()
    if repo:
        p = subprocess.run(["gh", "issue", "view", str(issue), "--repo", repo, "--json", "body",
                            "-q", ".body"], capture_output=True, text=True, timeout=30)
        if p.returncode == 0:
            m = re.search(r"^\s*[*`\-\s]*candidate_id:\s*([^\s*`]+)", p.stdout or "",
                          flags=re.M | re.I)
            if m:
                return m.group(1)
    return f"issue-{issue}"


# ── verify (design 2): it takes on the plumbing only ────────────────────────
# All this may hold is "start gate/skeptic with the right material".
# It decides nothing about verdict, why, risk, or which mutation to try.
# The moment a tool judges, the gate becomes a formality, so that line is not crossed.

def _agents_dir():
    """Where agents/*.md live — both installed as a plugin and using this repo directly."""
    # Codex injects PLUGIN_ROOT; Claude Code injects CLAUDE_PLUGIN_ROOT.  The
    # launcher can also invoke a bundled tool without either host variable, so
    # retain the tool-relative root as a final fallback.
    plugin_roots = [os.environ[name] for name in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")
                    if os.environ.get(name)]
    # HERE points at tools/ (this file lives in tools/orgcycle/). Its parent is the plugin root /
    # repo root. **During the split `__file__` went one level deeper and this was not fixed, so every
    # search location shifted by one level and the charters were lost** (the real harm of 0.22.0).
    # The base point is kept in HERE alone — re-resolving `__file__` all over digs the same hole
    # again.
    bases = plugin_roots + [os.path.dirname(HERE)]
    for base in bases:
        # Both the installed-plugin shape (agents/ is a sibling of tools/) and using this repo
        # directly. Reading only one loses the charters on the bundle side and verify stops
        # holding.
        for d in (os.path.join(base, "agents"),
                  os.path.join(base, "integrations", "claude-code", "agents")):
            if os.path.isdir(d):
                return d
    return None


def banner():
    """Print one line to stderr with the running version and the cwd.

    **Without seeing which copy is running, reusing an old path goes unnoticed.**
    In the field the 0.25.2 path was still being typed after 0.26.0 shipped (reused from what was
    last used), and an exit=1 from a command that assumed `cd` persists came close to being read as
    "evidence it is blocked".
    This puts material on the next line that makes reusing a variable value noticeable.
    """
    ver = "?"
    for c in (os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json"),
              os.path.join(HERE, "..", ".claude-plugin", "plugin.json"),
              os.path.join(HERE, "..", "integrations", "claude-code",
                           ".claude-plugin", "plugin.json")):
        try:
            with open(c, encoding="utf-8") as f:
                ver = json.load(f).get("version", "?")
            break
        except Exception:
            continue
    # **Do not dirty machine-readable output.** Written to stderr or not, a consumer mixing streams
    # with 2>&1 breaks the JSON (in the field a test failed with JSONDecodeError). This is a
    # convenience for humans, so it stays quiet under --json or ORG_QUIET — "break it for
    # convenience" does not hold up.
    if "--json" in sys.argv or os.environ.get("ORG_QUIET"):
        return
    print(f"[orgforge {ver} @ {os.getcwd()}]", file=sys.stderr)


def _worktree_tree_sha(cwd=None):
    """Bundle the whole working tree (tracked / staged / unstaged / **untracked**) into one tree SHA.

    `git diff HEAD` does not include the content of untracked files. Picking up names without reading
    content means **replacing an untracked file's content entirely still yields the same id**
    (demonstrated in an audit). Where a judge read untracked files to judge, two different
    deliverables could be made to agree as "the same thing".

    So the working tree is read into a **temporary index** and `git write-tree` run over it. Since
    `GIT_INDEX_FILE` points at a separate file, **the real index is not modified** — the supervisor's
    staging state is not broken.

    Artifacts excluded by .gitignore are left out (`--exclude-standard`). If build output and module
    trees changed the id every time, the same review could never be performed twice.
    """
    import tempfile as _tf
    def _git(*args, env=None):
        try:
            e = dict(os.environ)
            if env:
                e.update(env)
            r = subprocess.run(["git", *args], capture_output=True, text=True,
                               timeout=60, cwd=cwd, env=e)
            return r.returncode, r.stdout.strip()
        except Exception:
            return 1, ""

    fd, idx = _tf.mkstemp(prefix="orgforge-index-")
    os.close(fd)
    os.unlink(idx)                       # git creates a fresh index at a path that does not exist
    env = {"GIT_INDEX_FILE": idx}
    try:
        # Take HEAD's content as the base and lay the working tree's real state over it
        _git("read-tree", "HEAD", env=env)
        _git("add", "-A", "--", ".", env=env)
        code, tree = _git("write-tree", env=env)
        return tree if code == 0 else ""
    finally:
        for p_ in (idx, idx + ".lock"):
            try:
                os.unlink(p_)
            except OSError:
                pass


def issue_worktree(issue, cwd=None):
    """Resolve the canonical path `.orgforge/wt/issue-<N>` of the Issue worktree `begin` creates.

    The layout originates in `ghsync.branch._make_worktree` (directly under the primary checkout's
    toplevel). No second layout is invented — this reproduces **the resolution only**. Called from
    inside a linked worktree it still resolves to the primary (`git worktree list --porcelain` always
    lists the primary first).
    None where it cannot be resolved (the caller fails closed — the cwd is not used as a
    substitute).
    """
    d = os.path.abspath(cwd or os.getcwd())
    try:
        r = subprocess.run(["git", "-C", d, "worktree", "list", "--porcelain"],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    for line in (r.stdout or "").splitlines():
        if line.startswith("worktree "):
            primary = os.path.abspath(line[len("worktree "):])
            return os.path.join(primary, ".orgforge", "wt", f"issue-{int(issue)}")
    return None


def resolve_issue_branch(issue, derived=None, cwd=None):
    """Resolve the Issue's **actually existing** branch in two stages (#107). Returns
    ``(branch, warn, err)``.

    A name derived from the title slug is **a convention at creation time**, not a permanent identity
    — a retitling or a manual name puts it out of step with the real one. Measured on Tatekae
    (OBS-012 / OBS-048 defect 6 / OBS-057 cause 2), the derived name `feat/issue-15-google` did not
    exist (the real one was `feat/issue-15-login-redirect`),
    `git branch --merged --list <derived name>` was therefore always empty, and gc left an integrated
    worktree standing forever as "unintegrated".

    (a) Where the Issue worktree (`.orgforge/wt/issue-N`, resolved by issue_worktree) exists, its
        HEAD branch is **always true** — that is where the work actually happened.
        Where it differs from the derived name, say so with a warn (never pick one silently).
    (b) Otherwise use the derived name, **only where it actually exists**
        (`git rev-parse --verify`).
    (c) Where neither exists, err — **a derived name that does not exist is not silently believed**
        (fail-closed).
    """
    try:
        wt = issue_worktree(issue, cwd)
    except Exception:
        wt = None
    wt_exists = bool(wt and worktree_rooted_at(wt))
    head = issue_worktree_head(issue, cwd) if wt_exists else None
    if head:
        warn = None
        if derived and derived != head:
            warn = (f"the derived name `{derived}` does not match the worktree's real branch "
                    f"`{head}` (a retitling or a manual name). The HEAD of the worktree "
                    f".orgforge/wt/issue-{issue} is taken (#107).")
        return head, warn, None
    if derived:
        code, _out = _raw(["git"] + (["-C", cwd] if cwd else [])
                          + ["rev-parse", "--verify", "--quiet", f"refs/heads/{derived}"])
        if code == 0:
            return derived, None, None
    # State the facts alone: "there is no worktree" and "there is one but it points at no branch (a
    # detached HEAD)" are different states with different fixes. A false diagnosis misdirects the fix
    # as well.
    wt_state = (f"the worktree .orgforge/wt/issue-{issue} exists but is a detached HEAD "
                f"(it points at no branch)" if wt_exists
                else f"there is no worktree .orgforge/wt/issue-{issue} either")
    return None, None, (
        f"cannot resolve the branch for Issue #{issue}: the derived name "
        f"`{derived or '(could not be derived)'}` is not a branch that exists, and {wt_state}.\n"
        f"  Existing candidates can be found with `git branch --list 'feat/issue-{issue}*'`.\n"
        f"  To create one now, use `github_sync branch --issue {issue} --worktree`, which makes the "
        f"worktree together with the branch.")


def issue_worktree_head(issue, cwd=None):
    """The HEAD branch name of the Issue worktree (.orgforge/wt/issue-N) where it exists.

    None where there is none, where it is a fake worktree, or where it is a detached HEAD. The HEAD
    of an Issue worktree that exists is **the true value** of that Issue's branch (#107) — because
    that is where the work actually happened."""
    try:
        wt = issue_worktree(issue, cwd)
    except Exception:
        return None
    if not (wt and worktree_rooted_at(wt)):
        return None
    code, head = _raw(["git", "-C", wt, "symbolic-ref", "--short", "-q", "HEAD"])
    head = (head or "").strip()
    return head if code == 0 and head else None


def worktree_rooted_at(path):
    """Confirm by substance that `path` is a real worktree **whose own toplevel is exactly there**.

    `os.path.isdir` alone lets a fake worktree through (demonstrated by a skeptic): the empty
    directory a failed `git worktree add` leaves behind, a directory recreated without pruning, and a
    symlink to the repo root all sit **inside** the primary repo, so `git -C` resolves to the primary
    and the subject is minted without warning as the primary's tree (ahead=0, relation=current) —
    reproducing the OBS-071 forgery exactly.

    The check has two stages: (1) a canonical path that is itself a symlink is fake (a worktree
    whose substance lives elsewhere is not a worktree). (2) only once the substance of
    `git rev-parse --show-toplevel` matches the substance of path is there "a worktree there" — an
    empty directory or leftovers resolve their toplevel to the primary root and fail here. A symlink
    among the ancestors (/var → /private/var and the like) produces no false positive, since both
    sides are realpath'd.
    """
    if not path or os.path.islink(path) or not os.path.isdir(path):
        return False
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return False
    top = (r.stdout or "").strip()
    if r.returncode != 0 or not top:
        return False
    return os.path.realpath(top) == os.path.realpath(path)


def review_subject(issue, role, phase=None, cwd=None, integration_ref=None):
    """Bundle **the identity of what is judged** into one digest. `verify` generates it exactly once.

    0.32.1's agreement requirement decided agreement from (issue, role, lineage, verdict) alone. So
    **a joint was generated even where one harness admitted revision A and another admitted revision
    B** (demonstrated in an audit). Where the judges looked at different deliverables, that is not
    agreement.

    What is bundled:

        issue                that Issue
        role                 gate or skeptic (the kind of judgment)
        phase                which phase the judgment belongs to
        integration_ref      the integration ref
        integration_head_sha the integration target's head at judgment time
        base_sha             where it branched from (a difference from what?)
        reviewed_tree_sha    **the tree actually reviewed**. A tree rather than a commit — rebuilding
                             a commit with the same content does not change the subject
        requirements_digest  the content of the acceptance criteria. **Different criteria make it a
                             different judgment**

    `dirty` is not hidden. Where the working tree carries uncommitted changes, reviewed_tree_sha
    should point at **the index/worktree as it stands**, never pretending it was clean.

    A judge does not produce this value. If a judge could write the subject, two judgments that
    looked at different deliverables could be declared as "having looked at the same thing" and made
    to agree. **verify observes it; the judge only carries it.**
    """
    def _git(*args):
        try:
            r = subprocess.run(["git", *args], capture_output=True, text=True,
                               timeout=30, cwd=cwd)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    head_tree = _git("rev-parse", "HEAD^{tree}")
    # **The tree actually reviewed.** A tree rather than a commit, because rebuilding a commit with
    # the same content does not change the subject. Uncommitted and untracked content is bundled into
    # the one id as well (`git diff HEAD` does not include untracked content, so it is not enough).
    tree = _worktree_tree_sha(cwd) or head_tree
    dirty = "1" if tree != head_tree else ""
    from review_freshness import integration_observation, subject_digest
    integration = integration_observation(cwd or os.getcwd(), integration_ref)

    req_digest = ""
    for name in ("REQUIREMENTS.md",):
        p = os.path.join(cwd or ".", name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                req_digest = hashlib.sha256(f.read()).hexdigest()[:16]
            break

    parts = {"issue": str(issue), "role": role, "phase": phase or "",
             **integration, "reviewed_tree_sha": tree,
             "dirty": dirty, "head_tree_sha": head_tree,
             "requirements_digest": req_digest}
    sid = subject_digest(parts)
    return sid, parts
