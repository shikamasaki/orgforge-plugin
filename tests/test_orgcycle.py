"""The cycle's plumbing — begin / complete / verify / integrate / worktree / public surface.

It fixes the line: the plumbing is automated, the judgment is not."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from conftest import (REPO, TOOLS, TEMPLATE, run, seed, _cycle_src, _gh_src,
                      _cycle_mod, _propose_full, _admitted_claim, _sched,
                      _ledger_with, _led, _append, _status, _write_ledger)


def test_work_in_progress_view_resolves_started_not_completed(tmp_path):
    # the recovery source after a context wipe: a candidate STARTED with a progress checkpoint but not
    # completed must appear with its latest next_step; a COMPLETED one must drop out.
    seed(tmp_path, "eng", "cycle_started", {"role": "eng", "candidate_id": "X", "pack_manifest_id": "p"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "eng", "progress_recorded",
         {"role": "eng", "candidate_id": "X", "fraction": 0.6, "phase": "impl",
          "done_so_far": "parser done", "next_step": "wire into CLI", "blocked_by": None, "artifacts": []},
         ts="2026-07-16T02:00:00Z")
    # a second candidate that WAS completed — must not appear in WIP
    seed(tmp_path, "eng", "cycle_started", {"role": "eng", "candidate_id": "Y", "pack_manifest_id": "p"},
         ts="2026-07-16T03:00:00Z")
    seed(tmp_path, "eng", "cycle_completed", {"role": "eng", "candidate_id": "Y", "outputs": []},
         ts="2026-07-16T04:00:00Z")
    code, out = run("ledger.py", "view", str(tmp_path), "work_in_progress")
    assert code == 0, out
    data = json.loads(out)
    ids = [w["candidate_id"] for w in data["in_progress"]]
    assert ids == ["X"], f"expected only the unfinished X, got {ids}"
    wx = data["in_progress"][0]
    assert wx["progress"]["next_step"] == "wire into CLI"
    assert abs(wx["progress"]["fraction"] - 0.6) < 1e-9


def test_doctrine_incomplete_provenance_blocked(tmp_path):
    code, out = run("doctrine.py", "propose", str(tmp_path), "role", "--claim", "c",
                    "--source", "s", "--confidence", "0.9", "--retrieved-at", "2026-07-16")
    assert code == 0, out   # no review-by
    _, show = run("doctrine.py", "show", str(tmp_path), "role")
    cid = json.loads(show)["claims"][0]["id"]
    code, out = run("doctrine.py", "admit", str(tmp_path), "role", cid, "--by", "gate")
    assert code == 2 and ("incomplete" in out or "provenance" in out)


def test_doctrine_remap_allow_orphans_surfaces_not_drops(tmp_path):
    # --allow-orphans routes orphans to UNROUTED (surfaced for a human), never dropped.
    _admitted_claim(tmp_path, "api-worker", "idempotency keys on POST", "api-worker")
    dst = tmp_path / "new"
    code, out = run("doctrine.py", "remap", str(tmp_path),
                    "--map", json.dumps({"api-worker": ["x-worker", "y-worker"]}),
                    "--into", str(dst), "--allow-orphans")
    assert code == 0, out
    _, un = run("doctrine.py", "show", str(dst), "UNROUTED")
    assert len(json.loads(un)["claims"]) == 1   # preserved, not lost


# ── handoff.py (seam contract + scoped brain at delegation) ───────────────────


def test_reconcile_mandate_integrate(tmp_path):
    code, out = run("reconcile.py", "mandate", str(tmp_path), "--subjects", "safety,growth",
                    "--decision", "ship", "--precedence", "safety>growth", "--satisfiable", "true")
    assert code == 0 and "integrate" in out


# ── org_cycle: automating the plumbing (docs/11 §0d) ────────────────────────
# In the field, two Issues took eleven hand-typed commands, which came to about ninety across 18.
# In particular, the parent was read off by eye and typed in, so the parent-inheritance
# implementation (§2) was never actually in play.
def test_org_cycle_plan_executes_nothing(tmp_path):
    """plan only prints — it touches neither the ledger nor GitHub."""
    code, out = run("org_cycle.py", "plan", "--role", "r", "--issue", "7")
    assert code == 0, out
    assert "phase_started" in out and "cycle_started" in out
    assert not (tmp_path / "ledger.jsonl").exists()


def test_org_cycle_complete_requires_domain_model(tmp_path):
    """docs/11 §4d: a cycle_completed that does not state what it did to the domain model is not
    accepted."""
    code, out = run("org_cycle.py", "complete", "--role", "r", "--issue", "7",
                    "--outputs", "something")
    assert code == 2
    assert "domain-model" in out


def test_org_cycle_resolves_parent_from_issue_body():
    """The parent is read from the Issue's `Parent: #N` — a person does not carry it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("org_cycle", TOOLS / "org_cycle.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    import re
    body = "## Deliverable\nsplit engine\n\nParent: #1\n\ncandidate_id: cand-abc\n"
    assert re.search(r"^\s*Parent:\s*#?(\d+)", body, flags=re.M | re.I).group(1) == "1"


# ── proposal 5: enforcing worktree separation (docs/11 §4c) ─────────────────
# In a parallel fan-out, #7's commit actually landed on feat/issue-8-settle.
# git checkout switches the whole tree, so it recurs for as long as makers run in parallel in one
# tree. The lesson from the field: a design premised on "judging correctly every time" breaks.


# ── proposal 5: enforcing worktree separation (docs/11 §4c) ─────────────────
# In a parallel fan-out, #7's commit actually landed on feat/issue-8-settle.
# git checkout switches the whole tree, so it recurs for as long as makers run in parallel in one
# tree. The lesson from the field: a design premised on "judging correctly every time" breaks.
def test_worktree_isolates_parallel_makers(tmp_path):
    """Two Issues get worktrees in separate directories on separate branches, and their commits do
    not mix."""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "seed.txt").write_text("x")
    g("add", "-A"); g("commit", "-qm", "seed")
    g("branch", "develop")

    made = []
    for issue in (7, 8):
        code, out = run("github_sync.py", "branch", "--issue", str(issue), "--worktree",
                        "--base", "develop", "--repo", "o/n", cwd=str(repo))
        assert code == 0, out
        made.append(repo / ".orgforge" / "wt" / f"issue-{issue}")

    assert all(d.is_dir() for d in made), "the worktrees were not created"
    # Committing separately in each worktree, neither appears in the other's tree
    for issue, d in zip((7, 8), made):
        (d / f"F{issue}.txt").write_text("x")
        g("add", "-A", cwd=d); g("commit", "-qm", f"i{issue}", cwd=d)
    for issue, d in zip((7, 8), made):
        other = 8 if issue == 7 else 7
        assert (d / f"F{issue}.txt").exists()
        assert not (d / f"F{other}.txt").exists(), \
            f"#{other}'s deliverable bled into #{issue}'s tree — the separation is not working"
    # The branches differ too
    b = [g("branch", "--show-current", cwd=d).stdout.strip() for d in made]
    assert b[0] != b[1] and all(b), b


# ── proposal 2: verify is plumbing only, and holds no judgment ──────────────
# If a person writes out the verification steps each time, the gate's strictness changes with each
# writing (18 Issues, 18 versions). The standard comes from one place: agents/gate.md. But the
# moment a verdict is filled in, the gate becomes a formality, so
# that line is not crossed — and the boundary is fixed here by test.


# ── proposal 2: verify is plumbing only, and holds no judgment ──────────────
# If a person writes out the verification steps each time, the gate's strictness changes with each
# writing (18 Issues, 18 versions). The standard comes from one place: agents/gate.md. But the
# moment a verdict is filled in, the gate becomes a formality, so
# that line is not crossed — and the boundary is fixed here by test.
def test_verify_injects_focused_contract_and_leaves_verdict_unfilled():
    """It emits the Issue-scoped contract and the decide template, but never pre-empts the
    verdict."""
    import subprocess, os
    env = dict(os.environ, ORG_GITHUB_REPO="")
    # Since #101 the subject is minted from the Issue's worktree. This development repository has
    # no worktree for issue-1, so the escape hatch is stated explicitly (what this test is about is
    # the charter injection).
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "gate", "--subject-root", "."],
                       capture_output=True, text=True, env=env, timeout=60)
    out = p.stdout + p.stderr
    # Where gh is missing or unauthenticated, failing with 3 because the Issue cannot be read is
    # the correct behaviour
    if p.returncode == 0:
        assert "Fixed review contract" in out, \
            "the Issue-scoped review contract was not injected"
        assert "Do not add unrelated review criteria" in out
        # 0.25.2: for the subagent it specifies what to return; for the supervisor it is a field
        # to fill in. **Neither decides the verdict** — the moment a tool decides it, the gate
        # becomes a formality.
        assert "admit|reject|park" in out, "the verdict options are not shown"
        for filled in ('--verdict admit', '--verdict "admit"', '--verdict reject'):
            assert filled not in out, f"the plumbing is deciding the verdict: {filled}"
    else:
        assert p.returncode in (2, 3), out


def test_verify_rejects_unknown_role():
    """For a role with no charter, verify does not hold — it never launches with no source for the
    standard."""
    import subprocess
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "maker"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0


def test_verify_finds_charter_in_every_layout():
    """Find the charter **whether or not CLAUDE_PLUGIN_ROOT is set**.

    The earlier test set env before calling, so it never checked **the path with no env — the way
    it is actually used**. As a result, the 0.22.0 split moved `_agents_dir`'s search one level and
    verify died for both gate and skeptic with "agents/*.md not found (looked in: None)" — while
    the test stayed green. **A test that does not verify where the thing breaks is no test at
    all** — the same shape caught by split() in #7, committed on the test side.
    """
    m = _cycle_mod("judge")
    bundled = TOOLS.parent / "integrations" / "claude-code"
    codex_bundled = TOOLS.parent / "integrations" / "codex"
    saved = os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
    try:
        # (1) no env — using the repo directly. This is the one that broke in the field
        for role in ("gate", "skeptic"):
            charter, path = m._role_charter(role)
            assert charter, f"lost sight of {role}'s charter with no env (looked in: {path})"
        # (2) with env — installed as a Claude plugin
        assert (bundled / "agents").is_dir(), \
            "the Claude projection holds no review charter"
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(bundled)
        for role in ("gate", "skeptic"):
            charter, path = m._role_charter(role)
            assert charter, \
                f"lost sight of {role}'s charter in the Claude bundle (looked in: {path})"

        # (3) with env — installed as a Codex plugin. It uses the PLUGIN_ROOT Codex itself
        # injects; trying only the compatibility variable departs from the real host contract.
        assert (codex_bundled / "agents").is_dir(), \
            "the Codex projection holds no review charter"
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        os.environ["PLUGIN_ROOT"] = str(codex_bundled)
        for role in ("gate", "skeptic"):
            charter, path = m._role_charter(role)
            assert charter, \
                f"lost sight of {role}'s charter in the Codex bundle (looked in: {path})"
    finally:
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        os.environ.pop("PLUGIN_ROOT", None)
        if saved is not None:
            os.environ["CLAUDE_PLUGIN_ROOT"] = saved


def test_verify_actually_injects_the_charter(tmp_path):
    """Check that **the charter reaches verify's output**, not that `_role_charter` works alone.

    A working helper means nothing if the assembling side drops it. The symptom in the field was
    "verify is unusable", not "_role_charter returns None".
    """
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "gate"],
                       capture_output=True, text=True, cwd=str(tmp_path), timeout=60)
    out = p.stdout + p.stderr
    # Where gh is missing or the Issue cannot be read, failing with exit 3 is correct.
    # But it **must not fail with "charter not found" (exit 2)** — that is a wiring defect.
    assert "agents/gate.md not found" not in out, \
        f"the charter search is broken: {out[:300]}"
    assert p.returncode != 2, out


def test_verify_allows_passing_by_file_reference():
    """State that it can be passed in the body or by file reference (since 0.19.0 the guard reads
    the file).

    It used to be body-only, so the guidance said "paste it into the body". Pasting 264 lines every
    time crowds the maker's context, so the guard was changed to read the file and verify it.
    """
    src = _cycle_src()
    seg = src[src.index("def cmd_verify"):]
    assert "write it to a " in seg and "file and reference that" in seg
    assert "HELD" not in seg, \
        "guidance premised on a file reference being rejected is still there"


# ── field report: the moment just before integration is the easiest to skip ──


def test_integrate_blocks_without_skeptic(tmp_path):
    """Even with the gate's admit, no integration without the skeptic's survives.

    In the field, #8 was integrated into develop with not one refutation_attempted in the ledger.
    The Issue carried a comment, so one side of the double record had gone missing.
    """
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"deliverable": "8", "issue": 8, "verdict": "admit"}},
    ])
    env = dict(os.environ, ORG_LEDGER_ROOT=str(led))
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "integrate", "--issue", "8"],
                       capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=60)
    assert p.returncode == 4, p.stdout + p.stderr
    err = p.stdout + p.stderr
    assert "skeptic" in err and "survives" in err
    assert "git merge" not in err, \
        "it enters the merge procedure without the preconditions being met"


def test_integrate_allows_when_both_recorded(tmp_path):
    """With admit + survives both present, the precondition check does not stop it (execution then
    enters git's world)."""
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"deliverable": "8", "issue": 8, "verdict": "admit"}},
        {"seq": 2, "class": "refutation_attempted",
         "payload": {"claim_id": "8", "issue": 8, "verdict": "survives"}},
    ])
    import importlib.util
    m = _cycle_mod("_core")
    os.environ["ORG_LEDGER_ROOT"] = str(led)
    try:
        assert m._admission_for(8)[0] == "admit"
        assert m._refutation_for(8)[0] == "survives"
    finally:
        os.environ.pop("ORG_LEDGER_ROOT", None)


def test_verify_gate_uses_the_stable_organ_for_repro_lint():
    """An installed prompt uses the binding launcher, not a cache path; HERE is used only when
    developing from source."""
    src = _cycle_src()
    assert '_organ_command(stable_organ, "repro-lint")' in src
    assert 'os.path.join(HERE, filename)' in src, \
        "there is no fallback for a source checkout"


def test_worktree_cleanup_keeps_dirty_tree(tmp_path):
    """A worktree with uncommitted changes is not removed — whether losing it would matter is not
    the plumbing's decision."""
    import importlib.util
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "s.txt").write_text("x"); g("add", "-A"); g("commit", "-qm", "s"); g("branch", "develop")
    wt = repo / ".orgforge" / "wt" / "issue-5"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-5", str(wt), "develop")
    (wt / "dirty.txt").write_text("uncommitted")

    m = _cycle_mod("cycle")
    cwd = os.getcwd(); os.chdir(repo)
    try:
        msg = m._cleanup_worktree(5)
        assert wt.is_dir(), "it removed the worktree along with uncommitted changes"
        assert "was kept" in msg, msg
        # Once clean, it is removed
        (wt / "dirty.txt").unlink()
        msg2 = m._cleanup_worktree(5)
        assert not wt.is_dir(), f"a clean worktree was not cleared away: {msg2}"
    finally:
        os.chdir(cwd)


def test_complete_requires_command_and_result():
    """The DoD's real output is not left to a person's free prose (B)."""
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "complete",
                        "--role", "r", "--issue", "1", "--outputs", "x",
                        "--domain-model-none", "a reason"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0
    assert "--command" in p.stderr and "--result" in p.stderr


def test_begin_log_carries_facts_the_tool_already_knows():
    """begin's log carries branch / worktree / parent / candidate_id automatically (B).

    In the field, 276 characters written by a person held neither the branch name nor the worktree
    path — while org_cycle knew both. A fact the tool knows is never left for a person to write.
    """
    src = _cycle_src()
    seg = src[src.index("def _steps_begin"):src.index("def _steps_complete")]
    for token in ("worktree:", "branch:", "parent:", "candidate_id:", "--command", "--result"):
        assert token in seg, f"begin's log does not carry {token}"


def test_handback_puts_closes_in_pr_body():
    """`Closes #N` in the PR body ties Issue ↔ PR ↔ commit and closes the Issue on integration
    (C)."""
    src = _cycle_src()
    seg = src[src.index("def cmd_handback"):]
    assert 'f"Closes #{a.issue}"' in seg, \
        "the PR body has no Closes — the Issue is left OPEN"
    assert "gh pr create" in seg


# ── field report: the budget cap was stopping everyday tidying up
# ──               (fired five times a day, zero real harm) ──────────────────


def test_begin_records_attention_allocated():
    """Six were started and only one record of the choice existed. Recording what was chosen is
    plumbing."""
    src = _cycle_src()
    seg = src[src.index("def _steps_begin"):src.index("def _steps_complete")]
    assert "attention_allocated" in seg


def test_doctrine_propose_warns_on_incomplete_provenance():
    """It always jammed on the inconsistency that propose may omit what admit requires."""
    root = None
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run([sys.executable, str(TOOLS / "doctrine.py"), "propose", d, "r",
                            "--claim", "x", "--source", "s", "--confidence", "0.5"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0
        assert "the gate cannot admit this" in p.stderr, \
        "it does not say at propose time that admit will jam"


def test_complete_proposes_learning_to_doctrine():
    """The intake for accumulated learning is wired into the cycle (as far as propose; the admit is
    the gate's)."""
    src = _cycle_src()
    seg = src[src.index("def cmd_complete"):src.index("def cmd_plan")]
    assert "doctrine.py" in seg and "propose" in seg
    assert "--retrieved-at" in seg and "--review-by" in seg, \
        "without provenance filled in the gate cannot admit, and the learning dies pending"


def test_gc_keeps_unmerged_and_dirty_worktrees(tmp_path):
    """gc removes only what is integrated. Unintegrated or uncommitted work is kept."""
    import importlib.util
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "s.txt").write_text("x"); g("add", "-A"); g("commit", "-qm", "s"); g("branch", "develop")
    wt = repo / ".orgforge" / "wt" / "issue-3"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-3", str(wt), "develop")
    (wt / "new.txt").write_text("work"); g("add", "-A", cwd=wt); g("commit", "-qm", "w", cwd=wt)

    m = _cycle_mod("inspect")
    cwd = os.getcwd(); os.chdir(repo)
    try:
        m.cmd_gc(argparse.Namespace(base="develop", all=False))
        assert wt.is_dir(), "it removed a worktree not yet integrated into develop"
    finally:
        os.chdir(cwd)


def test_decide_writes_the_receipt_itself():
    """decide writes the receipt itself (0.21.0).

    It used to print a template for a person to type, and one side went missing three times in the
    field (#8's refutation, #11's first reject, a progress_recorded). The actor arrives through
    --by, so there is no reason to separate them.
    """
    src = _gh_src()
    seg = src[src.index("def cmd_decide"):]
    assert "ledger.py" in seg and "--natural-key" in seg
    assert '"issue": a.issue' in seg
    assert "NEXT: type the ledger receipt as it stands" not in seg, \
        "a template for a person to type is still there"


# ── field report: the detector lied that "learning is being used" ───────────


def test_verify_template_has_no_undefined_shell_var():
    """A template must run as pasted. $P is undefined, and a template that cannot be typed is not
    typed."""
    src = _cycle_src()
    assert "$P/tools" not in src, "an undefined $P is still in the template"


# ── 0.19.0: things whose absence hurt in practice ───────────────────────────


def test_begin_warns_but_does_not_block_on_unready_deps():
    """A preflight check only shows. The judgment is a person's."""
    src = _cycle_src()
    seg = src[src.index("def _readiness"):src.index("def cmd_begin")]
    assert "needs-human" in seg and "rework" in seg
    body = src[src.index("def cmd_begin"):src.index("def _steps_complete")] \
        if "def _steps_complete" in src[src.index("def cmd_begin"):] else src[src.index("def cmd_begin"):]
    assert "It does not stop" in src, \
        "the warning has become a stop (begin does not judge)"


def test_seam_guard_accepts_a_referenced_file(tmp_path):
    """A seam contract can be passed as a file. The guard itself reads and verifies it."""
    import importlib.util
    hook = TOOLS.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_s", hook)
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    cwd = os.getcwd(); os.chdir(tmp_path)
    try:
        good = tmp_path / "seam.md"
        good.write_text("# HAND-OFF\n## Your slice\nX\nInputs you receive: A\n"
                        "Outputs you MUST produce: B\n", encoding="utf-8")
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": f"for the contract, read {good}"}) is None, \
        "a file carrying a seam was rejected"

        bad = tmp_path / "memo.md"
        bad.write_text("just a note", encoding="utf-8")
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": f"the procedure is {bad}"}) is not None, \
        "a file with no seam got through"
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": "the procedure is /etc/passwd"}) is not None, \
        "it read a file outside the org"
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": "just do something sensible"}) is not None, \
        "one with no contract got through"
    finally:
        os.chdir(cwd)


# ── 0.20.0: rework history / integration preflight / production assets /
# ──         the public surface ──────────────────────────────────────────────


# ── 0.20.0: rework history / integration preflight / production assets /
# ──         the public surface ──────────────────────────────────────────────
def test_verify_passes_rework_history_to_gate():
    """Hand the gate the past judgments. Without them it treats every round as a first
    judgment."""
    src = _cycle_src()
    seg = src[src.index("def cmd_verify"):]
    assert "Judgment history" in seg and "judgment number" in seg
    assert "re-derive" in seg, \
        "it would become a gate that only checks whether the previous findings were fixed"


def test_integrate_plan_executes_nothing_and_warns_on_overlap(tmp_path):
    """--plan executes nothing and forewarns of overlap with a parallel worktree."""
    src = _cycle_src("ship")
    seg = src[src.index("def _integrate_preview"):src.index("def cmd_integrate")]
    assert "is changing the same files" in seg
    body = src[src.index("def cmd_integrate"):]
    assert 'if getattr(a, "plan", False):' in body
    assert body.index('if getattr(a, "plan", False):') < body.index("git\", \"merge"), \
        "--plan comes after the merge steps (it would execute them)"


def _ship_module():
    import importlib
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    return importlib.import_module("orgcycle.ship")


def _branch_repo(tmp_path, *branches):
    repo = tmp_path / "branch-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    for branch in branches:
        subprocess.run(["git", "branch", branch], cwd=repo, check=True)
    return repo


def test_integrate_branch_resolution_uses_exact_existing_branch(tmp_path, monkeypatch):
    ship = _ship_module()
    exact = "feat/issue-51-current-title"
    repo = _branch_repo(tmp_path, exact)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: exact)
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch == exact and len(subject_sha) == 40 and error is None


def test_integrate_branch_resolution_uses_sole_real_candidate(tmp_path, monkeypatch):
    ship = _ship_module()
    actual = "feat/issue-51-original-name"
    repo = _branch_repo(tmp_path, actual)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: "feat/issue-51-renamed-title")
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch == actual and len(subject_sha) == 40 and error is None


def test_integrate_branch_resolution_stops_on_tracking_only_candidate(tmp_path, monkeypatch):
    ship = _ship_module()
    actual = "feat/issue-51-remote-name"
    repo = _branch_repo(tmp_path)
    subprocess.run(["git", "update-ref", f"refs/remotes/origin/{actual}", "main"],
                   cwd=repo, check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: "feat/issue-51-renamed-title")
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch is None and subject_sha is None and "exists only as a tracking ref" in error


def test_integrate_branch_resolution_stops_on_local_tracking_divergence(tmp_path, monkeypatch):
    ship = _ship_module()
    actual = "feat/issue-51-diverged"
    repo = _branch_repo(tmp_path, actual)
    (repo / "tracking.txt").write_text("new", encoding="utf-8")
    subprocess.run(["git", "add", "tracking.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "tracking"], cwd=repo, check=True)
    tracking_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "update-ref", f"refs/remotes/origin/{actual}", tracking_sha],
                   cwd=repo, check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: actual)
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch is None and subject_sha is None and "have diverged" in error
    assert "local=" in error and "tracking=" in error


def test_integrate_branch_resolution_accepts_matching_local_and_tracking(tmp_path, monkeypatch):
    ship = _ship_module()
    actual = "feat/issue-51-same"
    repo = _branch_repo(tmp_path, actual)
    sha = subprocess.run(
        ["git", "rev-parse", actual], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "update-ref", f"refs/remotes/origin/{actual}", sha],
                   cwd=repo, check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: actual)
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert (branch, subject_sha, error) == (actual, sha, None)


def test_integrate_branch_resolution_stops_when_missing(tmp_path, monkeypatch):
    ship = _ship_module()
    repo = _branch_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: "feat/issue-51-missing")
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch is None and subject_sha is None and "candidate among the local or tracking refs either" in error


def test_integrate_branch_resolution_stops_on_ambiguity(tmp_path, monkeypatch):
    ship = _ship_module()
    candidates = ("feat/issue-51-one", "feat/issue-51-two")
    repo = _branch_repo(tmp_path, *candidates)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: "feat/issue-51-missing")
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch is None and subject_sha is None and "there are several candidates" in error
    assert all(candidate in error for candidate in candidates)


def test_integrate_explicit_branch_is_checked_without_fallback(tmp_path, monkeypatch):
    ship = _ship_module()
    repo = _branch_repo(tmp_path, "feat/issue-51-other")
    monkeypatch.chdir(repo)
    branch, subject_sha, error = ship._resolve_integration_branch(
        51, "feat/issue-51-explicit-missing")
    assert branch is None and subject_sha is None and "--branch" in error and "other" in error


def test_integrate_explicit_nonstandard_branch_and_sha_are_supported(tmp_path, monkeypatch):
    ship = _ship_module()
    repo = _branch_repo(tmp_path, "hotfix/manual-review")
    sha = subprocess.run(
        ["git", "rev-parse", "main"], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    monkeypatch.chdir(repo)
    branch, subject_sha, error = ship._resolve_integration_branch(51, "hotfix/manual-review")
    assert branch == "hotfix/manual-review" and subject_sha == sha and error is None
    branch, subject_sha, error = ship._resolve_integration_branch(51, sha)
    assert branch == sha and subject_sha == sha and error is None


# ── #107 rework: integrate puts the worktree's real HEAD among the candidates ──
# The skeptic's refutation: re-running begin after a retitle cuts a branch under the new slug while
# the real work sits in the worktree on the old branch, and since _resolve_integration_branch's
# add() admits only `feat/issue-N*` as candidates, the worktree-resolved non-convention branch was
# discarded and the stray convention-named branch became the sole candidate — **merged at exit 0,
# unreviewed**.


def _worktree_repo(tmp_path, work_branch, *stray_branches):
    """A repo whose real work sits on the worktree's branch (plus a stray convention-named
    branch)."""
    repo = _branch_repo(tmp_path, *stray_branches)
    wt = repo / ".orgforge" / "wt" / "issue-42"
    subprocess.run(["git", "worktree", "add", "-q", "-b", work_branch, str(wt), "main"],
                   cwd=repo, check=True)
    (wt / "work.txt").write_text("real reviewed work", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-qm", "real work"], cwd=wt, check=True)
    return repo, wt


def test_integrate_plan_stops_on_worktree_vs_conventional_split_brain(
        tmp_path, monkeypatch, capsys):
    """(a) The skeptic's split-brain shape: the worktree's real branch and a stray convention-named
    branch coexist → integrate --plan does not silently pick the stray, but names both and
    stops."""
    ship = _ship_module()
    repo, _wt = _worktree_repo(tmp_path, "fix/login-redirect", "feat/issue-42-old-title")
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "main"],
                   cwd=repo, check=True)
    (repo / "organization.yaml").write_text("roles: []\n", encoding="utf-8")
    (repo / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    integration_ref: origin/main\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _i: "feat/issue-42-new-title")
    rc = ship.cmd_integrate(argparse.Namespace(issue=42, branch=None, plan=True,
                                               base=None, test=None))
    cap = capsys.readouterr()
    assert rc != 0, (
        "it picks the stray feat/issue-42-old-title as the sole candidate and integrates it "
        "straight through")
    assert "fix/login-redirect" in cap.err and "feat/issue-42-old-title" in cap.err, \
        f"it does not name both branches and stop: {cap.err!r}"


def test_integrate_branch_resolution_targets_worktree_head_without_stray(
        tmp_path, monkeypatch):
    """(b) Only the worktree's real branch exists (under a non-convention name) → that becomes what
    is integrated."""
    ship = _ship_module()
    repo, _wt = _worktree_repo(tmp_path, "fix/login-redirect")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _i: "feat/issue-42-new-title")
    branch, subject_sha, error = ship._resolve_integration_branch(42)
    assert error is None, (
        f"the worktree's real branch is not among the candidates: {error!r}")
    assert branch == "fix/login-redirect" and len(subject_sha) == 40


def test_integrate_explicit_branch_keeps_current_behavior_despite_worktree(
        tmp_path, monkeypatch):
    """An explicit --branch behaves as before — the worktree resolution does not override it (an
    operator override)."""
    ship = _ship_module()
    repo, _wt = _worktree_repo(tmp_path, "fix/login-redirect", "feat/issue-42-old-title")
    monkeypatch.chdir(repo)
    branch, subject_sha, error = ship._resolve_integration_branch(42, "feat/issue-42-old-title")
    assert (branch, error) == ("feat/issue-42-old-title", None)
    assert len(subject_sha) == 40


def test_integrate_preview_fails_instead_of_reporting_zero_for_missing_ref(tmp_path, monkeypatch):
    ship = _ship_module()
    repo = _branch_repo(tmp_path)
    monkeypatch.chdir(repo)
    body, overlaps, error = ship._integrate_preview(
        51, "feat/issue-51-missing", "0" * 40, "main", "true")
    assert error and overlaps == {}
    assert "0 files" not in body and "subject" in body


def test_integrate_preview_is_pinned_to_resolved_subject_sha(tmp_path, monkeypatch):
    ship = _ship_module()
    branch = "feat/issue-51-moving"
    repo = _branch_repo(tmp_path, branch)
    subprocess.run(["git", "checkout", "-q", branch], cwd=repo, check=True)
    (repo / "first.txt").write_text("first", encoding="utf-8")
    subprocess.run(["git", "add", "first.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=repo, check=True)
    first_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    (repo / "later.txt").write_text("later", encoding="utf-8")
    subprocess.run(["git", "add", "later.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "later"], cwd=repo, check=True)
    monkeypatch.chdir(repo)

    body, overlaps, error = ship._integrate_preview(51, branch, first_sha, "main", "true")
    assert error is None and overlaps == {}
    assert "first.txt" in body and "later.txt" not in body and first_sha[:12] in body


def test_integrate_records_and_merges_immutable_subject_sha():
    src = _cycle_src("ship")
    assert '["git", "merge", "--no-ff", subject_sha' in src
    assert '"integration_subject_sha": subject_sha' in src
    assert "integration_subject_sha" in (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")


def test_surface_detection_ranks_security_definer_first():
    """SECURITY DEFINER is decided per function. Per file, the one that matters sinks."""
    src = _cycle_src()
    seg = src[src.index("def _new_public_surfaces"):]
    assert "per function" in seg, "it has gone back to a file-level flag"
    assert "granted" in seg


def test_surface_detection_skips_test_files():
    """Picking up too many test helpers buries the one that needs looking at."""
    src = _cycle_src()
    seg = src[src.index("def _new_public_surfaces"):]
    assert "tests?" in seg and "spec" in seg


def test_complete_blocks_until_surfaces_declared(tmp_path):
    """Where public surface grows, complete is withheld until it is declared (the entrance to an
    authorization hole)."""
    src = _cycle_src()
    seg = src[src.index("def cmd_complete"):src.index("def cmd_plan")]
    assert "--new-surface" in seg and "return 2" in seg
    assert "authorization hole" in seg


# ── 0.22.0: close the holes the split brought in ───────────────────────────
def test_core_HERE_points_at_tools_not_the_package():
    """HERE must point at tools/.

    Forgetting to fix this during the split made _gh_sync lose sight of github_sync.py and
    _branch_for return a branch name with no slug. Assembly-style tools walk past "not found"
    quietly, so show's implementation lines and integrate --plan's change list **silently went
    empty**.
    The base of a path is the first thing a split breaks.
    """
    m = _cycle_mod("_core")
    assert os.path.isfile(os.path.join(m.HERE, "github_sync.py")), \
        f"github_sync.py is not visible from HERE={m.HERE}"
    assert os.path.isfile(os.path.join(m.HERE, "ledger.py"))


def test_bundle_includes_subpackages():
    """build.sh must sync tools/'s subpackages too.

    Reading only `tools/*.py` leaves the split-out modules out of the bundle, and it dies with an
    ImportError the moment it is installed as a plugin.
    """
    bundled = TOOLS.parent / "integrations" / "claude-code" / "tools"
    if not bundled.is_dir():
        return
    for src in (TOOLS / "orgcycle").glob("*.py"):
        dst = bundled / "orgcycle" / src.name
        assert dst.is_file(), (
            f"the bundle has no {src.name} (build.sh missed it)")
        assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8"), \
            f"{src.name} diverges from the bundle"


def test_every_subcommand_still_dispatches():
    """Every subcommand must still start after the split (detecting a missed import)."""
    for c in ("begin", "complete", "plan", "verify", "handback",
              "integrate", "gc", "record", "show", "touched"):
        p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), c, "--help"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"{c} does not start: {p.stderr[:200]}"


def test_ghsync_core_HERE_points_at_tools():
    """ghsync must take tools/ as its base too (the same hole org_cycle stepped on).

    Where record.py loses sight of ledger.py, a judgment stays on the Issue alone and the ledger
    goes missing — exactly the one-sided loss 0.21.0 closed, recurring through the split.
    """
    src = _gh_src("_core")
    assert "HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))" in src, \
        "it does not take tools/ as its base (it loses sight of ledger.py)"
    # record.py must use HERE (rather than resolving it itself)
    assert "HERE" in _gh_src("record")


def test_ghsync_every_subcommand_still_dispatches():
    """Every subcommand must still start after the split."""
    for c in ("claim", "release", "create", "stage", "log", "decide", "branch",
              "split-check", "candidate-id", "coverage-check", "needs-human", "ready"):
        p = subprocess.run([sys.executable, str(TOOLS / "github_sync.py"), c, "--help"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"{c} does not start: {p.stderr[:200]}"


def test_bundle_includes_ghsync():
    """build.sh must sync ghsync/ too."""
    bundled = TOOLS.parent / "integrations" / "claude-code" / "tools" / "ghsync"
    if not (TOOLS / "ghsync").is_dir():
        return
    for src in (TOOLS / "ghsync").glob("*.py"):
        dst = bundled / src.name
        assert dst.is_file(), f"the bundle has no {src.name}"
        assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_path_base_is_resolved_in_exactly_one_place():
    """Resolving a path from `__file__` must live in one place per package (HERE).

    When the 0.22.0 split took `tools/` one level deeper to `tools/orgcycle/`, two of the scattered
    `os.path.dirname(os.path.abspath(__file__))` calls went unfixed: `_agents_dir` (losing the
    charters, so verify died for both gate and skeptic) and `_seam` (losing handoff.py, so no seam
    contract could be generated). **With the base scattered, something is missed every time the
    hierarchy changes.**
    """
    for pkg in ("orgcycle", "ghsync"):
        d = TOOLS / pkg
        if not d.is_dir():
            continue
        hits = []
        for f in sorted(d.glob("*.py")):
            for i, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
                if "__file__" in line and not line.lstrip().startswith("#"):
                    hits.append(f"{f.name}:{i}")
        assert len(hits) == 1, \
            f"{pkg}: __file__ is resolved in {len(hits)} places (keep it in HERE): {hits}"


def test_verify_finds_handoff_for_the_seam_contract(tmp_path):
    """Generating the seam contract (handoff.py) must not be lost either.

    _seam had stepped on the same hole as the charters. This reads it through the Boundary contract
    appearing in verify's output, rather than through the helper alone.
    """
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "gate"],
                       capture_output=True, text=True, cwd=str(tmp_path), timeout=60)
    out = p.stdout + p.stderr
    assert "could not generate the seam contract" not in out, (
        f"it has lost sight of handoff.py: {out[:300]}")


# ── 0.23.0: a worktree's stray ledger / the character of the rounds / handing over the unfired
#    areas ──
def test_worktree_is_not_mistaken_for_the_org_root(tmp_path):
    """From inside a worktree, follow the parent.

    Putting doctrine and evidence under git made `.orgforge/` restore into the worktree too, that
    matched ORG_MARKERS, and the search stopped there. A subagent typing a ledger append then wrote
    to the worktree's empty ledger and got back `appended seq=1` — **the real judgment disappears
    from the main tree**.
    It happened three times in one day in the field, and four real judgments went astray. A design
    that prevents it with a warning breaks (a gate stepped on it).
    """
    import importlib, sys as _s
    if str(TOOLS) not in _s.path:
        _s.path.insert(0, str(TOOLS))
    disc = importlib.import_module("discover")

    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / ".orgforge").mkdir(); (repo / ".orgforge" / "doctrine").mkdir()
    (repo / ".orgforge" / "doctrine" / "x.json").write_text("{}")
    g("add", "-A"); g("commit", "-qm", "seed"); g("branch", "develop")

    wt = repo / ".orgforge" / "wt" / "issue-3"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-3", str(wt), "develop")
    assert (wt / ".orgforge").is_dir(), (
        "premise: .orgforge is restored into the worktree")

    saved = os.environ.pop("ORG_LEDGER_ROOT", None)
    try:
        assert disc.org_root(str(wt)) == str(repo.resolve()), \
            "it mistook the worktree for the org root (a stray ledger appears)"
        assert disc.ledger_root(str(wt)) == os.path.join(str(repo.resolve()),
                                                         ".orgforge", "ledger")
    finally:
        if saved is not None:
            os.environ["ORG_LEDGER_ROOT"] = saved


def test_external_worktree_uses_primary_governance_but_keeps_its_subject(tmp_path, monkeypatch):
    """Host-created worktrees need one governance root even when they live outside the repo.

    The older regression only covered ``<repo>/.orgforge/wt``. Claude Code/Codex may create a
    linked worktree as a sibling or under a host temp directory, where walking parents can never
    reach the primary checkout. Governance must come from the primary worktree while the commit
    under review remains the external worktree's commit.
    """
    import importlib, sys as _s
    if str(TOOLS) not in _s.path:
        _s.path.insert(0, str(TOOLS))
    disc = importlib.import_module("discover")
    ledger = importlib.import_module("ledger")

    repo = tmp_path / "primary"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / ".orgforge").mkdir()
    (repo / "organization.yaml").write_text("name: test\n", encoding="utf-8")
    (repo / "ledger-schema.yaml").write_text("schema_version: old\n", encoding="utf-8")
    (repo / "constitution.yaml").write_text("version: old\n", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "seed")

    wt = tmp_path / "host-worktrees" / "issue-34"
    wt.parent.mkdir()
    g("worktree", "add", "-q", "-b", "feat/issue-34", str(wt), "HEAD")
    (repo / "ledger-schema.yaml").write_text("schema_version: authoritative\n", encoding="utf-8")
    (repo / "constitution.yaml").write_text("version: authoritative\n", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "governance update")
    subdir = wt / "src"; subdir.mkdir()

    monkeypatch.delenv("ORG_LEDGER_ROOT", raising=False)
    monkeypatch.delenv("ORG_LEDGER_SCHEMA", raising=False)
    assert disc.org_root(str(subdir)) == str(repo.resolve())
    assert disc.subject_root(str(subdir)) == str(wt.resolve())

    core = importlib.import_module("orgcycle._core")
    _, subject = core.review_subject(34, "gate", cwd=str(wt))
    wt_tree = g("rev-parse", "HEAD^{tree}", cwd=wt).stdout.strip()
    primary_tree = g("rev-parse", "HEAD^{tree}").stdout.strip()
    assert subject["head_tree_sha"] == wt_tree
    assert subject["head_tree_sha"] != primary_tree, \
        "governance resolution must not switch the commit/tree being reviewed"

    old_cwd = os.getcwd()
    try:
        os.chdir(subdir)
        assert ledger._schema_path() == str(repo / "ledger-schema.yaml")
        divergences = disc.governance_divergences()
    finally:
        os.chdir(old_cwd)
    assert {d["path"] for d in divergences} >= {"ledger-schema.yaml", "constitution.yaml"}

    status = subprocess.run(
        [sys.executable, str(TOOLS / "status.py"), "status", str(repo / ".orgforge" / "ledger")],
        cwd=str(subdir), capture_output=True, text=True, timeout=60)
    assert status.returncode == 0
    assert "AMBER" in status.stdout and "governance" in status.stdout.lower(), status.stdout


def test_integrate_passes_its_own_test_output_to_the_log():
    """integrate was itself tripping log's mandatory check.

    A milestone log requires --command/--result and integrate passed neither, so the integration
    completed while only the log to the Issue went missing. It holds the result of what it ran
    itself, so there is no reason to make a human write it.
    """
    src = _cycle_src("ship")
    seg = src[src.index("def cmd_integrate"):]
    assert '"--command", a.test' in seg and 'test_out["text"]' in seg


def test_show_reports_what_the_rounds_are_about():
    """Print not only the number of rounds but what the latest ones take issue with."""
    src = _cycle_src("inspect")
    assert "rounds:" in src and "last 3" in src
    # Read a different reason per round (fetching one makes them all look alike)
    assert "_issue_reasons" in src
    assert "material for a judgment, not a" in src, (
        "the board must never judge \"cut it\"")


def test_verify_hands_the_unshot_areas_to_skeptic():
    """Hand the skeptic, as targets, the areas the gate wrote it had not fired at this time."""
    src = _cycle_src("judge")
    assert "not probed this round" in src and "Known risk accepted" in src
    assert "candidate targets" in src


# ── 0.25.2: resolve the mismatch between instructions and permissions (a subagent does not
#    record) ──
def test_verify_does_not_tell_subagent_to_record():
    """Do not hand a subagent a command it cannot type.

    In the field gate and skeptic together did this seven times: a judgment was produced, then "I
    leave the recording to the supervisor", and once the judgment itself never entered the ledger
    and came close to being lost. A subagent is given neither ORG_GITHUB_REPO nor the ledger path,
    and it was still being told to "record it in both places" — **a mismatch between the
    instructions and the permissions**.
    """
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    # The section for the subagent (stdout) carries no recording command
    assert "What to return (**you decide the judgment; the supervisor records it**)" in seg
    assert "You do not need to run any recording command" in seg
    # The supervisor side (stderr) gets the command with the values fed in — plumbing that cannot
    # carry the judgment defeats the purpose
    assert "The command you (the supervisor) run" in seg
    assert "file=sys.stderr" in seg


def test_agent_charters_do_not_demand_recording():
    """The agents/*.md side must agree on "as far as returning the judgment" too (fixing one side
    leaves the mismatch)."""
    d = _cycle_mod("_core")._agents_dir()
    if not d:
        return
    for role in ("gate", "skeptic"):
        body = pathlib.Path(d, f"{role}.md").read_text(encoding="utf-8")
        assert "The supervisor does the recording" in body, (
            f"{role}.md still asks the subagent to record")
        assert "$ORG_GITHUB_REPO" not in body, \
            f"{role}.md references an environment variable it is not given"


def test_repro_lint_admits_it_has_no_baseline():
    """Where the baseline was not read, say "it has not been decided".

    In the field a gate took this assertion ("not in the baseline = newly broken by this change")
    at face value, read pre-existing debt as a new regression, and stopped the judgment — while the
    Issue in question was the work of turning that very item green. About a region the tool has not
    looked at, the tool should say "I have not looked".
    """
    src = (TOOLS / "repro_lint.py").read_text(encoding="utf-8")
    seg = src[src.index("HELD: {len(failed)} required artifact"):]
    assert "There is no baseline" in seg and "has not been " in seg
    assert "if baseline is None:" in src


# ── 0.26.0: do not pile out-of-scope findings onto an Issue ────────────────
def test_skeptic_charter_splits_in_scope_from_out_of_scope():
    """A skeptic always finds something — it is its work. Without cutting the scope an Issue never
    ends.

    In the field, **every finding from the fourth round onward** of an Issue that reworked eight
    times **was absent from the spec's MUSTs**. A real defect it may be, but it is the next
    Issue's work.
    """
    d = _cycle_mod("_core")._agents_dir()
    if not d:
        return
    body = pathlib.Path(d, "skeptic.md").read_text(encoding="utf-8")
    assert "recommended as its own Issue" in body, (
        "how an out-of-scope finding is handled is not written")
    assert "grounds for `refuted`" in body
    # What is hard to place is not left for the skeptic to decide
    assert "return them to the supervisor" in body


def test_verify_asks_skeptic_for_out_of_scope_separately():
    """out_of_scope goes into "what to return" as well (fixing only the charter leaves it at odds
    with the prompt)."""
    src = _cycle_src("judge")
    assert "out_of_scope" in src
    assert "do not count towards " in src


def test_verify_scopes_blockers_and_repeated_findings():
    """The gate's runtime material explicitly prevents an endless rally outside the change
    contract."""
    src = _cycle_src("judge")
    assert "The scope of judgment, and the discipline of a review rally" in src
    assert "handoff seam contract" in src
    assert "put its id in `prior_finding` and state which " in src
    assert "recommend a follow-up Issue" in src


def test_spec_template_states_when_done():
    """The judgment of done is written on the spec side — maker, gate, and skeptic all read the
    same condition."""
    body = (TOOLS.parent / "template" / "SPEC.md").read_text(encoding="utf-8")
    assert "The judgment of done" in body
    assert "becomes another one" in body


def test_show_warns_on_repeated_rework_but_not_on_many_rounds():
    """Read it by the number of reworks. Stacking up judgments is not itself bad (#7 converged in
    seven rounds and two reworks)."""
    src = _cycle_src("inspect")
    seg = src[src.index("rounds:"):]
    assert "len(reworks) > 3" in seg, "it does not decide by the number of reworks"
    assert "len(rounds) > 5" not in seg, (
        "warning by the number of judgments warns even on an Issue that was looked at carefully")


# ── 0.27.0: close the supervisor's gaps in recording ───────────────────────
def test_rework_has_a_dedicated_command():
    """Part of why the records went missing was that no dedicated command recorded
    rework_requested.

    In the field there was no rework_requested in the ledger against twenty-eight rejects and
    refutations (#32 had four rejects and zero records). A supervisor had to assemble
    `ledger.py append --payload '{...}'` by hand, and commissioning runs "judge → verify → decide →
    **commission** → record", so the record gets washed away when the commissioned subagent's
    notification arrives.
    As a side effect, show's rework warning (0.26.0) had gone silent.
    """
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "rework", "--help"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    for flag in ("--after", "--reason", "--by"):
        assert flag in p.stdout, f"{flag} is missing"


def _rework_args():
    return argparse.Namespace(issue=32, after="refuted", by="supervisor", reason="fix the proof",
                              to="maker", round=2)


def test_rework_returns_issue_to_ready_before_recording_ledger(monkeypatch):
    m = _cycle_mod("judge")
    calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: (calls.append(("gh",) + a) or (0, "ok")))
    monkeypatch.setattr(m, "_ledger", lambda *a: (calls.append(("ledger",) + a) or (0, "ok")))

    assert m.cmd_rework(_rework_args()) == 0

    assert calls[0] == ("gh", "stage", "--issue", "32", "--stage", "ready")
    assert calls[1][0:3] == ("ledger", "append", "--actor")
    assert calls[2][0:3] == ("gh", "log", "--issue")


def test_rework_does_not_advance_ledger_when_reopen_fails(monkeypatch):
    m = _cycle_mod("judge")
    ledger_calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: ((2, "reopen denied")
                                                    if a[0] == "stage" else (0, "ok")))
    monkeypatch.setattr(m, "_ledger", lambda *a: (ledger_calls.append(a) or (0, "ok")))

    assert m.cmd_rework(_rework_args()) == 3
    assert ledger_calls == []


def test_verify_offers_the_rework_command_on_reject():
    """The rework command sits in **the same place** as the judgment's record (the order otherwise
    inverts)."""
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    assert "rework --issue" in seg
    assert "rework warning falls silent" in seg


def test_banner_shows_version_and_cwd():
    """Without seeing which copy is running, reusing an old path goes unnoticed.

    In the field the 0.25.2 path was still being typed after 0.26.0 shipped, and an exit=1 from a
    command that assumed `cd` persists came close to being read as "evidence it is blocked".
    """
    for tool in ("org_cycle.py", "github_sync.py", "ledger.py"):
        src = (TOOLS / tool).read_text(encoding="utf-8")
        assert "banner" in src.lower(), f"{tool} does not print the version and the cwd"
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "plan",
                        "--role", "r", "--issue", "1"],
                       capture_output=True, text=True, timeout=60)
    assert "[orgforge " in p.stderr, p.stderr[:200]
    assert os.getcwd() in p.stderr or "@" in p.stderr


def test_banner_never_pollutes_machine_readable_output(tmp_path):
    """A line for humans must not break output a machine reads.

    Right after the banner went in it mixed into `ledger view`'s output (which returns JSON) and a
    test failed with JSONDecodeError. Writing to stderr changes nothing where the consumer mixes
    the streams with 2>&1.
    **Breaking it for convenience does not hold up** — it stays quiet for view, census, and
    digest.
    """
    led = tmp_path / "l"; led.mkdir()
    subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append",
                    "--actor", "e", "--class", "cycle_started",
                    "--payload", json.dumps({"role": "e", "candidate_id": "X"})],
                   capture_output=True, text=True,
                   env=dict(os.environ, ORG_LEDGER_ROOT=str(led)), timeout=60)
    for sub in ("view", "census"):
        args = [sys.executable, str(TOOLS / "ledger.py"), sub, str(led)]
        if sub == "view":
            args.append("work_in_progress")
        p = subprocess.run(args, capture_output=True, text=True, timeout=60)
        merged = p.stdout + p.stderr
        assert "[orgforge " not in merged, f"the banner mixed into {sub}'s output"
        json.loads(p.stdout)          # this raises if anything mixed in


def test_internal_calls_suppress_the_banner():
    """An internal call (_run) returns stdout and stderr mixed, so no banner is printed.

    `_branch_for` takes the first line and is safe for now, but the structure that allows the
    mixing is removed outright (0.22.1 had just stepped on one "breaks quietly" path).
    """
    src = _cycle_src("_core")
    seg = src[src.index("def _run("):src.index("def _raw(")]
    assert "ORG_QUIET" in seg, "_run does not suppress the banner"


# ── 0.27.1: cut the duplication in the prompt (measured: 21% of the total time was one wait) ──
def test_verify_does_not_repeat_the_prior_judgment_twice():
    """The judgment history and "what the gate already looked at" printed the same body twice.

    Measured: of the skeptic's 457-line prompt, the full text of the gate's latest judgment
    appeared in two places (the same 26 lines, and over 20 more). A prompt's length translates
    directly into reading time.
    """
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    assert "if prior and not (history or issue_rounds):" in seg, \
        "printing the history and then prior as well lines the same body up twice"


def test_verify_still_hands_over_the_unshot_areas():
    """Cutting the duplication must keep handing over "the areas the gate did not fire at".

    In the field a real bug came out of an area the gate had written it "had not hit once". This
    extracts the Known risk section from prior, so fetching prior itself must not be removed.
    """
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    assert 'if role == "skeptic" and prior:' in seg
    assert "candidate targets" in seg


# ── 0.28.0: a truncated report / --create under worktree operation / the seam guidance ──
def test_intake_catches_a_truncated_report():
    """A subagent's turn sometimes ends mid-work (three times in one night in the field).

    status returns completed and result holds a single declarative sentence like "Now the key
    attack:".
    **The dangerous shape is the one you cannot notice** — a report cut off at "MUST 2 is defended"
    could be read as a verdict and admitted.
    """
    for report, role in (("I verified MUST 1 and 2. Now the key attack:", "skeptic"),
                         ("MUST 2 で要求されている防御は実装されており、防がれました。", "skeptic"),
                         ("Now update the call sites.", "maker")):
        p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                            "--issue", "27", "--role", role, "--report", report],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 10, f"an incomplete report passed: {report!r}"
        assert "the report is incomplete" in p.stderr


def test_intake_passes_a_complete_report():
    """It passes where the required elements are all present. Writing 'Now ...' partway still
    counts as having run to completion."""
    for report, role in (
            (json.dumps({"verdict": "survives",
                         "why": "静的な境界分析と実テストの結果から、反例が成立しないことを確認した。",
                         "evidence": "npm test → 60 passed; relevant branches were inspected",
                         "mutations": [], "out_of_scope": [], "risk": "なし"},
                        ensure_ascii=False), "skeptic"),
            ("実装完了。コミット 7550451。npm test → Tests 60 passed (60)。", "maker"),
            ("verdict: reject。npm ci が失敗し exit=1。MUST 3 が満たされていない。", "gate")):
        p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                            "--issue", "27", "--role", role, "--report", report],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, (
            f"a complete report was rejected: {report!r} / {p.stderr[:200]}")


def test_branch_create_does_not_move_main_in_a_worktree_org(tmp_path):
    """In an org running in parallel over worktrees, the main branch is not switched.

    In the field --create moved main off develop, and unnoticed, the integration tests for develop
    would have run on another Issue's branch.
    """
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "s.txt").write_text("x"); g("add", "-A"); g("commit", "-qm", "s"); g("branch", "develop")
    g("checkout", "-q", "develop")
    wt = repo / ".orgforge" / "wt" / "issue-1"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-1", str(wt), "develop")

    r = subprocess.run([sys.executable, str(TOOLS / "github_sync.py"), "branch",
                        "--issue", "9", "--create", "--base", "develop", "--repo", "o/n"],
                       capture_output=True, text=True, cwd=str(repo), timeout=60)
    cur = g("branch", "--show-current").stdout.strip()
    assert cur == "develop", (
        f"main switched to {cur} (an org that operates over worktrees)")
    assert (repo / ".orgforge" / "wt" / "issue-9").is_dir(), "no worktree was created"


def test_seam_gate_message_leads_with_the_shortest_path():
    """Write the ways through in the order they are actually shortest (in the field INDEPENDENT:
    alone got it through)."""
    src = (TOOLS.parent / "integrations" / "common" / "org_hook.py").read_text(encoding="utf-8")
    i = src.index("carries no seam contract")
    seg = src[i:i + 1600]
    assert seg.index("INDEPENDENT") < seg.index("handoff.py"), \
        "handoff.py reads as the first option (while INDEPENDENT: is the shorter way through)"
    assert "waives the `owns` declaration" in seg, \
        "does not say that INDEPENDENT: waives the owns check"


# ── 0.28.1: a declaration only at the start of a line / decidable through a pipe too ──
def _spawn_verdict(prompt):
    import importlib.util, pathlib as _p
    hook = TOOLS.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_i2", hook)
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    return h.spawn_needs_seam_or_independence("Task", {"prompt": prompt})


def test_negation_is_not_read_as_a_declaration():
    """A substring match over the whole text lets **a negation pass as a declaration**.

    A probe in the field: 「contract も INDEPENDENT: も付けていません」 ("I attached neither a
    contract nor INDEPENDENT:") matched as (A) verbatim. The harmful shape is a spawn written as (B)
    — 「この作業は independent ではないので contract を付ける」 ("this work is not independent, so I
    attach a contract") — being misjudged as (A): **(A) exempts the `owns` declaration**, so a
    chance match takes the exemption. The guard's own wording says "write one line at the top", so
    the check is matched to the wording.
    """
    for prompt in ("contract も INDEPENDENT: も付けていません",
                   "この作業は independent ではないので contract を付ける",
                   "no seam contract is attached",
                   "seam contract を書き忘れました"):
        assert _spawn_verdict(prompt) is not None, (
            f"a negation passed as a declaration: {prompt!r}")


def test_declaration_at_the_start_of_a_line_passes():
    """A declaration at the start of a line passes (leading spaces and a second line are fine)."""
    for prompt in ("INDEPENDENT: 調査のみ。出力はマージされない",
                   "independent: research only",
                   "  INDEPENDENT: 前に空白があってもよい",
                   "前置き\nINDEPENDENT: 2行目の行頭でもよい"):
        assert _spawn_verdict(prompt) is None, (
            f"a legitimate declaration was rejected: {prompt!r}")


def test_seam_contract_structure_still_passes():
    """The seam side reads **structure** (not a bare word), so handoff.py's output passes."""
    assert _spawn_verdict("## Your slice\nX\nInputs you receive: A\n"
                          "Outputs you MUST produce: B") is None


def test_intake_emits_a_machine_readable_verdict_line():
    """Through `| tail` the shell's exit code becomes the last command's, and the 10 disappears.

    That is what was observed in the field (the implementation returned 10 while the observation
    path showed 0).
    INCOMPLETE is put in the output so the decision can also be made through a pipe.
    """
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                        "--issue", "30", "--role", "skeptic",
                        "--report", "MUST 2 は防がれました。"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 10
    assert "INCOMPLETE" in p.stderr, p.stderr
    q = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                        "--issue", "30", "--role", "skeptic",
                        "--report", json.dumps({
                            "verdict": "survives",
                            "why": "静的な境界分析と実テストの結果から、反例が成立しないことを確認した。",
                            "evidence": "npm test → 60 passed; relevant branches were inspected",
                            "mutations": [], "out_of_scope": [], "risk": "なし"},
                            ensure_ascii=False)],
                       capture_output=True, text=True, timeout=60)
    assert q.returncode == 0 and "INCOMPLETE" not in q.stderr


@pytest.mark.parametrize("claim", [
    "mutations: []",
    "mutations: none attempted",
    "mutations: trigger disabled, detected=true",
    "applied: true\npostcondition: changed\nrestore_postcondition: restored",
    "mutations: []\n撃った変異: trigger削除 → detected=false",
])
def test_intake_rejects_prose_mutation_claims(claim):
    result = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                             "--issue", "30", "--role", "skeptic", "--report",
                             "verdict: survives。npm test → 60 passed。\n" + claim],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 10
    assert "structured JSON" in result.stderr


# ── 0.29.0: show the job structure for an integration that touches CI ──────
def _ci_repo(tmp_path, ci_yaml):
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text(ci_yaml, encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "seed"); g("branch", "develop")
    g("checkout", "-q", "-b", "feat/issue-42")
    (repo / ".github" / "workflows" / "ci.yml").write_text(ci_yaml + "\n# added\n", encoding="utf-8")
    g("commit", "-qam", "ci: add")
    return repo


_CI_CONDITIONAL = """name: CI
on:
  push:
    branches: [develop]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm test
  db-test:
    runs-on: ubuntu-latest
    steps:
      - id: probe
        run: echo present=true >> $GITHUB_OUTPUT
      - if: steps.probe.outputs.present == 'true'
        run: git diff --exit-code -- public docs
"""

_CI_PLAIN = """name: CI
on:
  push:
    branches: [develop]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm test
"""


def test_integrate_plan_flags_a_conditional_ci_job(tmp_path):
    """Valid YAML and green tests notwithstanding, a step that lands in a conditional job does not
    run.

    In operation a union merge put its result at the end of a conditional job, and while the Issue
    it depended on stayed unintegrated the added check never ran once. A step's `if:` can also be
    written as `- if:`, so missing the hyphen drops **exactly the shape this means to catch**.
    """
    repo = _ci_repo(tmp_path, _CI_CONDITIONAL)
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "integrate",
                        "--issue", "42", "--plan", "--base", "develop"],   # #106: stated (the fixture declares none)
                       capture_output=True, text=True, cwd=str(repo), timeout=60)
    out = p.stdout + p.stderr
    assert "it touches CI" in out, out
    assert "db-test (if: conditional)" in out, out
    assert "that check never runs once while the condition is unmet" in out


def test_integrate_plan_lists_only_real_jobs(tmp_path):
    """A child of `on:` (pull_request / push) must not be mistaken for a job. With no condition it
    stays quiet."""
    repo = _ci_repo(tmp_path, _CI_PLAIN)
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "integrate",
                        "--issue", "42", "--plan", "--base", "develop"],   # #106: stated (the fixture declares none)
                       capture_output=True, text=True, cwd=str(repo), timeout=60)
    out = p.stdout + p.stderr
    assert "job: test" in out, out
    for wrong in ("pull_request", "push", "permissions"):
        assert wrong not in out.split("job:")[1].split("\n")[0], (
            f"{wrong} was mistaken for a job")
    assert "a conditional job" not in out, "it warned although there is no condition"


# ── 0.31.0: use another harness as the judge (actually separating the lineage) ──
def test_verdict_schemas_satisfy_structured_outputs():
    """Under `additionalProperties: false`, Structured Outputs requires every key in required.

    Measured as 400 invalid_json_schema: "'required' is required to be supplied and to be an array
    including every key in properties. Missing 'note'." An optional field is expressed as
    `"type": ["string", "null"]` rather than by dropping it from required.
    """
    base = TOOLS.parent / "template" / "schemas"
    assert base.is_dir(), "there are no verdict schemas"

    def check(node, path="root"):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, (
                    f"{path}: it allows additional properties")
                assert set(node.get("required", [])) == set(node["properties"]), \
                    f"{path}: required does not contain every key in properties"
            for k, v in node.items():
                check(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                check(v, f"{path}[{i}]")

    for role in ("gate", "skeptic"):
        d = json.loads((base / f"{role}-verdict.json").read_text(encoding="utf-8"))
        check(d, role)
        assert "verdict" in d["properties"], role
        assert d["properties"]["verdict"].get("enum"), f"{role}: verdict is not an enum"


def test_intake_reads_a_structured_verdict():
    """A structured return is read by its structure, not by a regex.

    Required in the schema or not, an empty string is not filled in. It is layered in two: the shape
    (the schema) and the content (intake).
    """
    ok = json.dumps({
        "verdict": "survives",
        "why": "3経路で試し、いずれも security definer を経由して拒否された。詳細は以下。",
        "evidence": "psql -c \"update …\" → ERROR: violates row-level security / npm test → 78 passed",
        "mutations": [{"what": "is_group_member を select true に", "applied": True,
                       "postcondition": "select prosrc → true を返した", "detected": True,
                       "restore_postcondition": "select prosrc → original body を返した",
                       "note": None}],
        "out_of_scope": [], "risk": "中間積の上限チェックが無い"}, ensure_ascii=False)
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                        "--issue", "11", "--role", "skeptic", "--report", "-"],
                       input=ok, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr

    empty = json.dumps({"verdict": "survives", "why": "", "evidence": "",
                        "mutations": [], "out_of_scope": [], "risk": ""})
    q = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                        "--issue", "11", "--role", "skeptic", "--report", "-"],
                       input=empty, capture_output=True, text=True, timeout=60)
    assert q.returncode == 10, "a structured return with an empty field passed"


@pytest.mark.parametrize("mutation", [
    {"what": "trigger disable", "applied": False,
     "postcondition": "select tgenabled → O", "restore_postcondition": "select → O",
     "detected": False, "note": "変化なし"},
    {"what": "trigger disable", "applied": True,
     "postcondition": "", "restore_postcondition": "select → O",
     "detected": False, "note": "読取なし"},
    {"what": "trigger disable", "applied": True,
     "postcondition": 1234567890123, "restore_postcondition": "select → O",
     "detected": False, "note": "型が不正"},
    {"what": "trigger disable", "applied": True,
     "postcondition": "select tgenabled → D", "restore_postcondition": "",
     "detected": False, "note": "復元未確認"},
    {"what": "trigger disable", "detected": False, "note": "旧形式"},
])
def test_intake_rejects_unproven_mutations(mutation):
    report = json.dumps({
        "verdict": "survives",
        "why": "MUSTの防御を変異検査で確認したという主張だが、適用成立の証拠を検査する。",
        "evidence": "mutation command and test output were captured for independent review",
        "mutations": [mutation], "out_of_scope": [], "risk": "適用不能なら未測定"},
        ensure_ascii=False)
    result = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                             "--issue", "11", "--role", "skeptic", "--report", "-"],
                            input=report, capture_output=True, text=True, timeout=60)
    assert result.returncode == 10, result.stdout + result.stderr
    assert any(word in (result.stdout + result.stderr)
               for word in ("post-apply", "post-restore", "confirmed to have applied"))


@pytest.mark.parametrize("bad_mutations", [None, "all applied", {"applied": False}])
def test_intake_rejects_non_array_or_missing_mutations(bad_mutations):
    report = {
        "verdict": "survives",
        "why": "MUSTの防御を独立に確認したという主張だが、構造化された変異一覧の型を検査する。",
        "evidence": "mutation command and test output were captured for independent review",
        "out_of_scope": [], "risk": "不正な構造は判定成果物にしない"}
    if bad_mutations is not None:
        report["mutations"] = bad_mutations
    result = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                             "--issue", "11", "--role", "skeptic", "--report", "-"],
                            input=json.dumps(report, ensure_ascii=False),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 10, result.stdout + result.stderr
    assert "array" in (result.stdout + result.stderr)


def test_intake_accepts_static_skeptic_report_without_mutations():
    """A static proof can be complete without pretending a mutation was attempted."""
    report = json.dumps({
        "verdict": "survives",
        "why": "仕様の不変条件を実装と境界条件から独立に再導出し、反例が成立しないことを確認した。",
        "evidence": "対象コードと既存テストの具体的な分岐を読み、境界入力の結果を照合した。",
        "mutations": [], "out_of_scope": [], "risk": "動的変異は不要な静的判定"},
        ensure_ascii=False)
    result = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                             "--issue", "11", "--role", "skeptic", "--report", "-"],
                            input=report, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_prompt_requires_mutation_postconditions_and_restore():
    src = _cycle_src("judge")
    segment = src[src.index("def cmd_verify"):src.index("def _judge_lineage")]
    for phrase in ("baseline → mutate → postcondition → test → restore",
                   "A GREEN from a mutation that never landed is not ", "post-apply state", "unmeasured"):
        assert phrase in segment


def test_cross_harness_verdict_schemas_are_bundled_and_resolved():
    """OBS-009: source and both installed projections must carry the same contracts."""
    judge = _cycle_mod("judge")
    roots = [TEMPLATE / "schemas",
             REPO / "integrations" / "claude-code" / "template" / "schemas",
             REPO / "integrations" / "codex" / "template" / "schemas"]
    for role in ("gate", "skeptic"):
        copies = [root / f"{role}-verdict.json" for root in roots]
        assert all(path.is_file() for path in copies), copies
        contents = [path.read_bytes() for path in copies]
        assert contents[0] == contents[1] == contents[2]
        assert pathlib.Path(judge._verdict_schema(role)).resolve() == copies[0].resolve()


def test_verify_offers_the_headless_route():
    """Print the shape for running a judge in another harness in a form that can be typed as-is."""
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    assert "--output-schema" in seg and "intake" in seg
    assert "other harness" in seg or "another harness" in seg


def test_claude_judge_receives_the_declared_effort():
    """Claude Code projects the constitution's model/effort onto its run arguments too."""
    src = _cycle_src("judge")
    branch = src[src.index('elif cli == "claude":'):src.index('else:', src.index('elif cli == "claude":'))]
    assert '["--model", str(model)]' in branch
    assert '["--effort", str(effort)]' in branch


# ── judges.lineage (the Swiss-cheese layers) ────────────────────────────────
# **First, pin that the default does not change.** Presupposing another harness's subscription,
# CLI, and credentials stops the org from running anywhere that lacks them. Adding a layer is a
# choice, not a premise.

def test_judge_lineage_defaults_to_same_harness(tmp_path, monkeypatch):
    """Where the constitution declares no judges, it is same-harness."""
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _judge_lineage
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)   # org_root is decided by .orgforge/
    (tmp_path / "constitution.yaml").write_text("enforcement:\n  caps: {}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert _judge_lineage("gate") == ("same-harness", None)


_HARNESS_CFG = (
    "      claude:\n"
    "        gate: { cli: claude, model: sonnet, effort: medium }\n"
    "        skeptic: { cli: claude, model: sonnet, effort: medium }\n"
    "      codex:\n"
    "        gate: { cli: codex, model: gpt-5.6-terra, effort: medium }\n"
    "        skeptic: { cli: codex, model: gpt-5.6-terra, effort: medium }"
)


@pytest.mark.parametrize(
    "primary,secondary",
    [("claude", "codex"), ("codex", "claude")],
)
def test_judge_lineage_selects_the_opposite_harness(tmp_path, monkeypatch, primary, secondary):
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _judge_lineage
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: adaptive\n"
        f"    harness:\n{_HARNESS_CFG}\n",
        encoding="utf-8")
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    monkeypatch.setenv("ORGFORGE_ACTIVE_HARNESS", primary)
    monkeypatch.setenv(f"ORGFORGE_{secondary.upper()}_AVAILABLE", "true")
    monkeypatch.chdir(tmp_path)
    lineage, cfg = _judge_lineage("skeptic")
    assert lineage == "cross-harness"
    assert cfg["cli"] == secondary
    if secondary == "codex":
        assert cfg["model"] == "gpt-5.6-terra"
        assert cfg["effort"] == "medium"
    else:
        assert cfg["model"] == "sonnet"
        assert cfg["effort"] == "medium"
    assert _judge_lineage("gate")[1]["cli"] == secondary


@pytest.mark.parametrize("primary,secondary", [("claude", "codex"), ("codex", "claude")])
def test_adaptive_lineage_falls_back_honestly_with_one_subscription(
        tmp_path, monkeypatch, primary, secondary):
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _judge_lineage
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: adaptive\n"
        f"    harness:\n{_HARNESS_CFG}\n", encoding="utf-8")
    monkeypatch.setenv("ORGFORGE_ACTIVE_HARNESS", primary)
    monkeypatch.setenv(f"ORGFORGE_{secondary.upper()}_AVAILABLE", "false")
    monkeypatch.chdir(tmp_path)
    assert _judge_lineage("gate") == ("same-harness", None)


@pytest.mark.parametrize("available,expected", [("true", "cross-harness"),
                                                   ("false", "same-harness")])
def test_recording_uses_the_same_adaptive_lineage_resolution(
        tmp_path, monkeypatch, available, expected):
    sys.path.insert(0, str(TOOLS))
    from ghsync.record import _org_lineage
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: adaptive\n", encoding="utf-8")
    monkeypatch.setenv("ORGFORGE_ACTIVE_HARNESS", "codex")
    monkeypatch.setenv("ORGFORGE_CLAUDE_AVAILABLE", available)
    monkeypatch.chdir(tmp_path)
    assert _org_lineage() == expected


@pytest.mark.parametrize(
    "harness,expected",
    [
        ("      gate: { cli: codex }", "a map for both claude and codex"),
        (_HARNESS_CFG.replace("cli: claude", "cli: codex"),
         "Running the same harness twice"),
    ],
)
def test_judge_lineage_fails_closed_on_invalid_cross_routing(
        tmp_path, monkeypatch, harness, expected):
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _judge_lineage
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n"
        f"    harness:\n{harness}\n", encoding="utf-8")
    monkeypatch.setenv("ORGFORGE_ACTIVE_HARNESS", "codex")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match=expected):
        _judge_lineage("gate")


def test_active_harness_rejects_ambiguous_nested_signals(monkeypatch):
    sys.path.insert(0, str(TOOLS))
    from harness import active_harness
    monkeypatch.delenv("ORGFORGE_ACTIVE_HARNESS", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    with pytest.raises(SystemExit, match="both Claude Code and Codex signals"):
        active_harness()


def test_headless_reports_missing_cli_instead_of_falling_back(tmp_path, monkeypatch):
    """With no CLI, **it does not fall back to same-harness silently**.

    Believing "it was checked under a different lineage" while the lineage was in fact the same is
    the worst state there is
    (nobody can tell the signal is broken). Return non-zero and say so.
    """
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _run_headless
    schema = TEMPLATE / "schemas" / "gate-verdict.json"
    rc = _run_headless("gate", 1, "the material", {"cli": "no-such-cli-xyz"}, str(schema))
    assert rc != 0


def test_headless_empty_output_is_fail_closed_and_diagnosable(tmp_path, monkeypatch, capsys):
    """An empty return stays fail-closed while leaving **material that separates the causes**
    (Issue #166).

    In the field `claude -p` returned exit 0 with both stdout and stderr empty, and there was no
    telling whether the CLI had died, the credentials had expired, or it had quietly ended midway
    through a tool use. No judgment was obtained, so no admission is generated (that does not
    change) — but what to try next can still be said.
    Do not print the material itself (what is being judged) — state only its length.
    """
    sys.path.insert(0, str(TOOLS))
    from orgcycle import judge as J

    class _Empty:
        returncode, stdout, stderr = 0, "", ""
    monkeypatch.setattr(J.shutil, "which", lambda c: "/usr/bin/true")
    monkeypatch.setattr(J.subprocess, "run", lambda *a, **k: _Empty())
    schema = TEMPLATE / "schemas" / "gate-verdict.json"
    material = "SECRET-MATERIAL-" + "x" * 200
    rc = J._run_headless("gate", 1, material, {"cli": "claude"}, str(schema))
    err = capsys.readouterr().err
    assert rc == 7, "it must not return 0 with no judgment"
    assert "exit=0" in err and "stdout=0B" in err          # material for separating the causes
    assert "material=" in err
    assert "SECRET-MATERIAL" not in err, (
        "what is being judged must not leak into the diagnostics")
    assert "Reply with exactly: OK" in err                 # it says what to try next


def test_decide_requires_both_lineages_for_admit(tmp_path, monkeypatch):
    """In a cross-harness org, a one-sided admit cannot be recorded.

    If verify merely lined both judgments up for a supervisor to read, the supervisor could take
    whichever suited — more checking, and yet looser. So **decide holds it**.
    """
    sys.path.insert(0, str(TOOLS))
    import importlib
    rec = importlib.import_module("ghsync.record")
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n", encoding="utf-8")
    led = tmp_path / ".orgforge" / "ledger"
    led.mkdir(parents=True)
    (led / "ledger.jsonl").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    assert rec._org_lineage() == "cross-harness"
    # An empty ledger → there is no admit from either lineage
    assert rec._has_lineage_verdict(7, "admission_decided", "same-harness") is False
    # A reject demands no agreement (one side is enough for a negative)
    assert rec._has_lineage_verdict(7, "admission_decided", "cross-harness") is False


def test_drift_reads_only_the_why_section(monkeypatch):
    """Read only the judgment's Why section. Searching the whole comment loses the distribution
    (measured)."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    drift = importlib.import_module("drift")
    body = ("## ⛔ admission_decided — `reject`\n"
            "**Why (the reasoning):**\n未測定のまま断定していた。\n\n"
            "**Evidence consulted:**\n回帰テストは緑だった。\n")
    monkeypatch.setattr(drift, "_sh", lambda cmd: json.dumps({"comments": [{"body": body}]}))
    got = drift._issue_reasons(1)
    assert len(got) == 1
    assert "未測定" in got[0]
    # The Evidence section is not the reason — it must not be picked up
    assert "回帰" not in got[0]


def test_drift_skips_non_judgment_comments(monkeypatch):
    """A maker's report or a rework instruction is not a cause."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    drift = importlib.import_module("drift")
    body = "**cycle_completed** — 実装完了。\n**Why:**\n未測定のまま断定した。\n"
    monkeypatch.setattr(drift, "_sh", lambda cmd: json.dumps({"comments": [{"body": body}]}))
    assert drift._issue_reasons(1) == []


# ══ 0.32.1: take a full cross-harness round through the real CLI from an empty ledger ══
# **Acceptance criterion 7.** 0.32.0 lacked this: it confirmed only that one side is refused and
# never confirmed that anything could get through, so it pushed a deadlock where an admit could
# never be produced.
# A unit test of the deciding function cannot catch this — run the real CLI from an empty ledger.

def _xh_org(tmp_path, lineage="cross-harness"):
    """Create an empty org that declares cross-harness."""
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    (tmp_path / "constitution.yaml").write_text(
        f"enforcement:\n  judges:\n    lineage: {lineage}\n"
        "    integration_ref: origin/main\n"     # #106: show and friends require the declaration
        "    judgment_corrections:\n      authority_roles: [supervisor]\n",
        encoding="utf-8")
    (tmp_path / "organization.yaml").write_text(
        "roles:\n"
        "  - {id: supervisor, active: true, functions: [organize, operate]}\n"
        "  - {id: gate, active: true, functions: [judge, review]}\n"
        "  - {id: skeptic, active: true, functions: [judge, review]}\n",
        encoding="utf-8")
    return tmp_path


def _xh_authority_receipt(org, target, reason, issue="7", kind="superseded"):
    key = org / "supervisor-correction.pem"
    code, out = run("identity.py", "keygen", "--key-id", "supervisor-correction",
                    "--signer-id", "supervisor-principal", "--private-out", str(key),
                    "--authorized-roles", "supervisor", "--authorized-lineages", "authority",
                    cwd=str(org))
    assert code == 0, out
    oid = hashlib.sha256(str(org.resolve()).encode()).hexdigest()[:16]
    ledger = org / ".orgforge" / "ledger"
    lid = hashlib.sha256(str(ledger.resolve()).encode()).hexdigest()[:16]
    subject = f"correction:{kind}:{int(target)}"
    code, out = run(
        "identity.py", "receipt", "--org-id", oid, "--ledger-id", lid,
        "--subject", subject, "--issue", str(issue), "--role", "supervisor",
        "--phase", "govern", "--lineage", "authority", "--verdict", kind,
        "--event-class", "correction", "--requirements-digest",
        "judgment-correction-authority-v1", "--reasoning-sha256",
        hashlib.sha256(reason.encode("utf-8")).hexdigest(), "--issued-at",
        "2026-08-02T00:00:00Z", "--key-id", "supervisor-correction",
        "--private-key", str(key), cwd=str(org))
    assert code == 0, out
    receipt = org / "supervisor-correction.json"
    receipt.write_text(out.strip(), encoding="utf-8")
    return receipt


def _prov(tmp_path, lineage, verdict, issue=7, role="gate", why=None, extra=(),
          subject="subject-A"):
    return run("github_sync.py", "provisional",
               "--issue", str(issue), "--role", role, "--lineage", lineage,
               "--verdict", verdict, "--subject", subject,
               "--why", why or f"{lineage} の {role} として実際に見て決めた。"
                               f"再導出した範囲と、決め手になった箇所を書いている。",
               "--evidence", "the commands run and a summary of the output", *extra,
               cwd=str(tmp_path))


def _events(tmp_path, cls):
    p = tmp_path / ".orgforge" / "ledger" / "ledger.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("class") == cls:
            out.append(e)
    return out


@pytest.mark.parametrize("first,second", [("same-harness", "cross-harness"),
                                          ("cross-harness", "same-harness")])
def test_xh_admission_from_empty_ledger_either_order(tmp_path, first, second):
    """Acceptance criteria 1 and 3: it passes from an empty ledger **in either order**, and
    agreement produces the admission."""
    org = _xh_org(tmp_path)
    c1, o1 = _prov(org, first, "admit")
    assert c1 == 0, o1
    # After the first there is still no admission (acceptance criterion 2)
    assert _events(org, "admission_decided") == []
    c2, o2 = _prov(org, second, "admit")
    assert c2 == 0, o2
    adm = _events(org, "admission_decided")
    assert len(adm) == 1, f"they agree and no admission was generated: {o2}"
    pl = adm[0]["payload"]
    assert pl["verdict"] == "admit" and pl["lineage"] == "joint"
    assert sorted(pl["agreed_by"]) == ["cross-harness", "same-harness"]
    assert len(pl["from_seqs"]) == 2


def test_xh_single_lineage_does_not_admit(tmp_path):
    """Acceptance criterion 2: one side alone is not admitted."""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit")[0] == 0
    assert _events(org, "admission_decided") == []
    assert len(_events(org, "verdict_provisional")) == 1


def test_xh_disagreement_blocks_admission_and_is_recorded(tmp_path):
    """Acceptance criterion 4: a disagreement produces no admission, and the disagreement itself is
    recorded."""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit")[0] == 0
    c, o = _prov(org, "cross-harness", "reject")
    assert c == 5, o
    assert _events(org, "admission_decided") == []
    dis = _events(org, "judges_disagreed")
    assert len(dis) == 1
    assert dis[0]["payload"]["same_harness"] == "admit"
    assert dis[0]["payload"]["cross_harness"] == "reject"


def test_xh_lineage_cannot_rewrite_its_own_verdict(tmp_path):
    """Acceptance criterion 4: one lineage cannot rewrite its verdict to manufacture agreement."""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "reject")[0] == 0
    c, o = _prov(org, "same-harness", "admit")        # attempt the flip
    assert c == 4, o
    assert "correction" in o
    assert _events(org, "admission_decided") == []


def test_xh_other_issue_does_not_satisfy_agreement(tmp_path):
    """Acceptance criterion 4: a judgment on another Issue does not count toward agreement."""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", issue=7)[0] == 0
    assert _prov(org, "cross-harness", "admit", issue=8)[0] == 0
    assert _events(org, "admission_decided") == []   # both #7 and #8 have only one side


def test_xh_skeptic_and_gate_do_not_cross_satisfy(tmp_path):
    """Acceptance criterion 4: the gate's judgment cannot serve the skeptic's agreement (they are
    kept apart by for_event)."""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", role="gate")[0] == 0
    assert _prov(org, "cross-harness", "survives", role="skeptic")[0] == 0
    assert _events(org, "admission_decided") == []
    assert _events(org, "refutation_attempted") == []


def test_broken_constitution_fails_closed_no_downgrade(tmp_path):
    """Acceptance criteria 5 and 6: where the configuration cannot be read it stops non-zero and
    does not degrade to same-harness."""
    org = _xh_org(tmp_path)
    (org / "constitution.yaml").write_text("enforcement: [not: valid: yaml", encoding="utf-8")
    c, o = _prov(org, "same-harness", "admit")
    assert c != 0
    both = o
    assert "cannot parse constitution.yaml" in both or "cannot be read" in both
    # **It did not degrade** — nothing entered the ledger
    assert _events(org, "verdict_provisional") == []
    assert _events(org, "admission_decided") == []


def test_bad_lineage_value_fails_closed(tmp_path):
    """Acceptance criterion 5: an invalid lineage value stops it (it does not fall to the default
    silently)."""
    org = _xh_org(tmp_path, lineage="cross_harness")     # an underscore is invalid
    c, o = _prov(org, "same-harness", "admit")
    assert c != 0
    assert "lineage" in o


def test_same_harness_org_rejects_provisional(tmp_path):
    """A provisional cannot be used in a same-harness org (there is nobody to count agreement
    with)."""
    org = _xh_org(tmp_path, lineage="same-harness")
    c, o = _prov(org, "same-harness", "admit")
    assert c == 2
    assert "cross-harness" in o


def test_xh_pass_requires_evidence(tmp_path):
    """A pass needs evidence — a pass that referred to nothing is a rubber stamp."""
    org = _xh_org(tmp_path)
    code, out = run("github_sync.py", "provisional",
                    "--issue", "7", "--role", "gate", "--lineage", "same-harness",
                    "--verdict", "admit", "--subject", "subject-A",
                    "--why", "十分に長い理由を書いているが evidence が空である場合を試す。",
                    cwd=str(org))
    assert code == 2
    assert "evidence" in out


# ══ 0.32.2: the identity of what is judged, and the way out of a correction ══
# What the audit found in 0.32.1: (a) the correction payload shape being advised differed from the
# real one, so typing it voided nothing and there was no way out of a refusal; (b) two judgments of
# different revisions counted as agreement; (c) a joint held only one side's reasoning; (d)
# duplicates could be stacked as long as the verdict matched.
#
# **Criteria 5 and 6 are the crux** — twice, in 0.32.0 and 0.32.1, the refusal was confirmed and
# the way out was not.

def test_xh_different_subjects_do_not_agree(tmp_path):
    """Criterion 3: two passes that looked at different subjects are not agreement."""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", subject="rev-A")[0] == 0
    c, o = _prov(org, "cross-harness", "admit", subject="rev-B")
    assert c == 6, o
    assert "different subjects" in o
    assert _events(org, "admission_decided") == []


def test_xh_same_subject_agrees(tmp_path):
    """The counterpart to criterion 3: the same subject agrees, and the joint carries it."""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", subject="rev-A")[0] == 0
    assert _prov(org, "cross-harness", "admit", subject="rev-A")[0] == 0
    adm = _events(org, "admission_decided")
    assert len(adm) == 1
    assert adm[0]["payload"]["review_subject_id"] == "rev-A"


def test_xh_exact_retry_is_noop_but_rejudge_is_refused(tmp_path):
    """Criterion 4: only an exactly identical re-run is a no-op. A re-judgment with a changed reason
    is refused."""
    org = _xh_org(tmp_path)
    why = "同一性の検査のために、十分な長さの理由をここに書いておく。決め手はこの箇所である。"
    assert _prov(org, "same-harness", "admit", why=why)[0] == 0
    # Exactly identical → a no-op (no duplicate is stacked)
    c, o = _prov(org, "same-harness", "admit", why=why)
    assert c == 0, o
    assert len(_events(org, "verdict_provisional")) == 1
    # The same verdict with a different reason → refused (0.32.1 let this through)
    c, o = _prov(org, "same-harness", "admit",
                 why="同じ verdict のまま理由だけを差し替えた場合。これは重複として積めてはいけない。")
    assert c == 4, o
    assert len(_events(org, "verdict_provisional")) == 1


def test_xh_rejudge_hands_back_to_declared_authority_and_that_path_works(tmp_path):
    """No self-correction command is given to a judge; the declared third party's way out is taken
    through the real CLI."""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "reject")[0] == 0
    c, o = _prov(org, "same-harness", "admit")     # attempt the swap → refused
    assert c == 4
    assert "Authority roles declared by the constitution: supervisor" in o
    assert "--actor <あなたの役割>" not in o
    prior = _events(org, "verdict_provisional")[0]
    reason = "base更新後に第三者authorityが再検証を要求した"
    receipt = _xh_authority_receipt(org, prior["seq"], reason)
    payload = json.dumps({"corrects": [prior["seq"]], "kind": "superseded",
                          "reason": reason,
                          "corrected_by": "supervisor"}, ensure_ascii=False)
    code, lout = run("ledger.py", "append", "--class", "correction",
                     "--actor", "supervisor", "--payload", payload, "--receipt", str(receipt),
                     cwd=str(org))
    assert code == 0, f"the authority's correction does not pass: {lout}"
    assert ("effect=voids" in lout and "authority=supervisor" in lout
            and "assurance=authenticated" in lout)
    code, shown = run("org_cycle.py", "show", "--issue", "7", cwd=str(org))
    assert code == 0, shown
    assert ("correction kind=superseded effect=voids" in shown
            and "principal=supervisor-principal" in shown
            and "assurance=authenticated" in shown)

    # **It took effect** — the old one is void, so a new judgment enters
    c, o = _prov(org, "same-harness", "admit")
    assert c == 0, f"it cannot be replaced even after a correction:\n{o}"
    provs = _events(org, "verdict_provisional")
    assert len(provs) == 2                                  # the original reject and the new admit
    # And once cross-harness is complete it becomes a joint (the way out runs to the end)
    assert _prov(org, "cross-harness", "admit")[0] == 0
    assert len(_events(org, "admission_decided")) == 1


def test_xh_joint_carries_both_lineages_reasoning(tmp_path):
    """Criterion 7: the joint carries both lineages' reasoning_sha256 and ref."""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", why="同一ハーネス側の judge の理由。独立に再導出した範囲と、判定の決め手になった箇所を書いている。")[0] == 0
    assert _prov(org, "cross-harness", "admit", why="別ハーネス側の judge の理由。独立に見た範囲と、判定の決め手になった具体的な箇所を書いている。")[0] == 0
    pl = _events(org, "admission_decided")[0]["payload"]
    by = pl["reasoning_by_lineage"]
    assert set(by) == {"same-harness", "cross-harness"}
    for lin in by:
        assert by[lin]["reasoning_sha256"]
        assert by[lin]["reasoning_ref"]
        assert by[lin]["seq"]
    # The two digests differ, and the joint's is neither of them (it is built from both)
    ds = {by[l]["reasoning_sha256"] for l in by}
    assert len(ds) == 2
    assert pl["reasoning_sha256"] not in ds


def test_review_subject_binds_tree_and_requirements(tmp_path):
    """review_subject must depend on the tree and the acceptance criteria (a value no judge can
    produce)."""
    sys.path.insert(0, str(TOOLS))
    from orgcycle._core import review_subject
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    (tmp_path / "REQUIREMENTS.md").write_text("MUST: A", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "one"], cwd=tmp_path, check=True)
    s1, p1 = review_subject(7, "gate", "implement", cwd=str(tmp_path))
    # Different acceptance criteria make it a different judgment
    (tmp_path / "REQUIREMENTS.md").write_text("MUST: A and B", encoding="utf-8")
    s2, p2 = review_subject(7, "gate", "implement", cwd=str(tmp_path))
    assert s1 != s2
    assert p1["requirements_digest"] != p2["requirements_digest"]
    # A different role makes it a different judgment
    s3, _ = review_subject(7, "skeptic", "implement", cwd=str(tmp_path))
    assert s3 != s2


def test_non_pass_verdict_does_not_enter_agreement(tmp_path):
    """park and reject are not passes, so they proceed to neither a subject comparison nor waiting
    on a peer.

    Measured: a park on #34 drew the irrelevant warning "they are looking at different subjects".
    A negative from either side is negative, so it should end before the question of agreement
    arises.
    """
    org = _xh_org(tmp_path)
    c, o = _prov(org, "same-harness", "park")
    assert c == 0, o
    assert "is not a pass" in o
    assert "different subjects" not in o
    assert _events(org, "admission_decided") == []


def test_print_subject_does_not_launch_a_judge(tmp_path, monkeypatch):
    """--print-subject prints the subject and stops (it starts no judge, even under
    cross-harness).

    Measured: verify was typed to learn the subject for a record, a headless judge ran, and it
    timed out after two minutes. A recording procedure must not require a judgment to be run.
    """
    org = _xh_org(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=org, check=True)
    (org / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=org, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "x"], cwd=org, check=True)
    # Take codex off PATH — an attempt to start it would fail, so success proves it did not
    monkeypatch.setenv("PATH", "/nonexistent")
    # From #101 the subject is minted from the Issue's worktree (or an explicit --subject-root).
    # This org has no worktree, so the escape hatch is stated — there is no implicit fallback to
    # the cwd.
    code, out = run("org_cycle.py", "verify", "--issue", "7", "--role", "gate",
                    "--print-subject", "--subject-root", str(org), cwd=str(org))
    assert code == 0, out
    assert re.search(r"^[0-9a-f]{64}$", out.strip().splitlines()[0])


@pytest.mark.parametrize("first,second", [("admit", "reject"), ("reject", "admit")])
def test_xh_disagreement_recorded_in_either_order(tmp_path, first, second):
    """A disagreement is recorded **whichever comes first**.

    When 0.32.2 made park/reject return early, the admit → reject order stopped leaving a
    judges_disagreed. It is the shape that passes when only one order is checked.
    """
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", first)[0] == 0
    c, o = _prov(org, "cross-harness", second)
    assert c == 5, o
    assert _events(org, "admission_decided") == []
    dis = _events(org, "judges_disagreed")
    assert len(dis) == 1, o
    assert dis[0]["payload"]["same_harness"] == first
    assert dis[0]["payload"]["cross_harness"] == second


# ══ 2.0.15: a bounded environment preflight before judge dispatch ══════════

def _preflight_constitution(tmp_path, preflights):
    import yaml
    path = tmp_path / "constitution.yaml"
    path.write_text(yaml.safe_dump({"enforcement": {"judges": {
        "preflights": preflights}}}, sort_keys=False), encoding="utf-8")
    return path


def test_judge_preflight_runs_only_for_matching_issue_phase_and_role(tmp_path, monkeypatch):
    mod = _cycle_mod("preflight")
    marker = tmp_path / "ran"
    path = _preflight_constitution(tmp_path, [{
        "id": "database",
        "command": [sys.executable, "-c",
                    "import os,pathlib; pathlib.Path(os.environ['MARKER']).write_text("
                    "os.environ['ORG_PREFLIGHT_ISSUE'] + ':' + "
                    "os.environ['ORG_PREFLIGHT_PHASE'] + ':' + "
                    "os.environ['ORG_PREFLIGHT_ROLE'])"],
        "timeout_seconds": 2,
        "applies_to": {"issues": [36], "phases": ["implement"],
                       "roles": ["gate"]},
    }])
    monkeypatch.setattr(mod, "_constitution_path", lambda: str(path))
    monkeypatch.setenv("MARKER", str(marker))

    assert mod.run_declared_preflights(7, "gate", "implement", cwd=tmp_path) == (True, [])
    assert not marker.exists(), "unrelated Issue inherited the database probe"
    assert mod.run_declared_preflights(36, "skeptic", "implement", cwd=tmp_path) == (True, [])
    assert not marker.exists(), "unrelated role inherited the database probe"
    ok, evidence = mod.run_declared_preflights(36, "gate", "implement", cwd=tmp_path)
    assert ok and len(evidence) == 1
    assert marker.read_text(encoding="utf-8") == "36:implement:gate"
    measured = json.loads(evidence[0])
    assert measured["id"] == "database"
    assert measured["status"] == "pass"
    assert measured["exit_code"] == 0
    assert isinstance(measured["elapsed_ms"], int)


def test_judge_preflight_failure_reports_exact_probe_result(tmp_path, monkeypatch, capsys):
    mod = _cycle_mod("preflight")
    path = _preflight_constitution(tmp_path, [{
        "id": "runtime-health",
        "command": [sys.executable, "-c",
                    "import sys; print('measured-down'); print('socket refused', file=sys.stderr); "
                    "raise SystemExit(23)"],
        "timeout_seconds": 2,
        "applies_to": {"issues": [36]},
    }])
    monkeypatch.setattr(mod, "_constitution_path", lambda: str(path))
    ok, evidence = mod.run_declared_preflights(36, "gate", "implement", cwd=tmp_path)
    assert not ok and len(evidence) == 1
    measured = json.loads(evidence[0])
    assert measured["status"] == "fail"
    assert measured["exit_code"] == 23
    assert measured["stdout"] == "measured-down\n"
    assert measured["stderr"] == "socket refused\n"
    assert measured["command"][0] == sys.executable
    assert "runtime-health" in capsys.readouterr().err


def test_judge_preflight_timeout_is_measured_and_stops(tmp_path, monkeypatch):
    mod = _cycle_mod("preflight")
    path = _preflight_constitution(tmp_path, [{
        "id": "slow-runtime",
        "command": [sys.executable, "-c", "import time; time.sleep(1)"],
        "timeout_seconds": 0.03,
    }])
    monkeypatch.setattr(mod, "_constitution_path", lambda: str(path))
    ok, evidence = mod.run_declared_preflights(36, "gate", "implement", cwd=tmp_path)
    measured = json.loads(evidence[0])
    assert not ok
    assert measured["status"] == "timeout"
    assert measured["exit_code"] is None
    assert measured["timeout_seconds"] == 0.03
    assert measured["elapsed_ms"] >= 20


@pytest.mark.parametrize("probe,fragment", [
    ({"id": "shell", "command": "docker info", "timeout_seconds": 2}, "argv list"),
    ({"id": "unbounded", "command": ["true"]}, "timeout_seconds"),
    ({"id": "bad-scope", "command": ["true"], "timeout_seconds": 2,
      "applies_to": {"labels": ["db"]}}, "unknown selector"),
    ({"id": "scope-typo", "command": ["true"], "timeout_seconds": 2,
      "apply_to": {"issues": [36]}}, "unknown field"),
])
def test_judge_preflight_rejects_ambiguous_or_unbounded_contract(
        tmp_path, monkeypatch, probe, fragment):
    mod = _cycle_mod("preflight")
    path = _preflight_constitution(tmp_path, [probe])
    monkeypatch.setattr(mod, "_constitution_path", lambda: str(path))
    with pytest.raises(mod.PreflightConfigError, match=fragment):
        mod.load_probes(36, "gate", "implement")


def test_verify_stops_before_any_judge_work_when_preflight_fails(monkeypatch, capsys):
    judge = _cycle_mod("judge")
    monkeypatch.setattr(judge, "_role_charter", lambda role: ("charter", "agents/gate.md"))
    monkeypatch.setattr(judge, "_issue_body", lambda issue: ("title", "MUST: work"))
    monkeypatch.setattr(judge, "run_declared_preflights",
                        lambda *args, **kwargs: (False, ['{"id":"db","status":"fail"}']))
    monkeypatch.setattr(judge, "_seam",
                        lambda *args: pytest.fail("seam/judge material was built after failure"))
    # #101: the subject comes from the worktree (or an explicit --subject-root). issue-36 has no
    # worktree, so it is stated — this test's subject is "a failed preflight starts no judge".
    args = argparse.Namespace(issue=36, role="gate", phase="implement", print_subject=False,
                              subject_root=os.getcwd())
    assert judge.cmd_verify(args) == 8
    err = capsys.readouterr().err
    assert "the judge was not started" in err


def test_preflight_contract_is_bundled_identically_for_both_harnesses():
    source = (TOOLS / "orgcycle" / "preflight.py").read_bytes()
    for harness in ("claude-code", "codex"):
        bundled = REPO / "integrations" / harness / "tools" / "orgcycle" / "preflight.py"
        assert bundled.read_bytes() == source


def test_org_lint_rejects_invalid_preflight_before_first_judge():
    import importlib.util
    import yaml
    spec = importlib.util.spec_from_file_location("org_lint_preflight", TOOLS / "org_lint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    constitution = yaml.safe_load((TEMPLATE / "constitution.yaml").read_text(encoding="utf-8"))
    constitution["enforcement"]["judges"]["preflights"] = [{
        "id": "unbounded", "command": ["runtime", "status"]}]
    lint = module.Lint()
    module.lint_constitution(constitution, lint)
    assert any(error.startswith("[PF]") and "timeout_seconds" in error
               for error in lint.errs), lint.errs


# ══ 0.32.3: review_subject bundles the whole working tree ══════════════════

def _repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "t.txt").write_text("tracked\n", encoding="utf-8")
    (tmp_path / "REQUIREMENTS.md").write_text("MUST: A\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _sub(path, issue=7, role="gate", phase="implement"):
    sys.path.insert(0, str(TOOLS))
    from orgcycle._core import review_subject
    return review_subject(issue, role, phase, cwd=str(path))[0]


def test_subject_changes_when_untracked_content_changes(tmp_path):
    """**A defect the audit demonstrated.** Replacing an untracked file's content left the id
    unchanged.

    `git diff HEAD` does not include untracked content, so names were picked up without reading
    what was in them. Where a judge read untracked files to judge, two different deliverables could
    be made to agree as "the same thing".
    """
    org = _repo(tmp_path)
    (org / "untracked.txt").write_text("first\n", encoding="utf-8")
    s1 = _sub(org)
    (org / "untracked.txt").write_text("second-different-content\n", encoding="utf-8")
    s2 = _sub(org)
    assert s1 != s2


def test_subject_is_reproducible_for_the_same_tree(tmp_path):
    """The same state gives the same id. Otherwise the same review cannot be performed twice."""
    org = _repo(tmp_path)
    (org / "untracked.txt").write_text("x\n", encoding="utf-8")
    assert _sub(org) == _sub(org)


def test_subject_ignores_gitignored_build_output(tmp_path):
    """An id that moves with build output makes the same review impossible to perform twice."""
    org = _repo(tmp_path)
    (org / ".gitignore").write_text("build/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=org, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "ignore"], cwd=org, check=True)
    before = _sub(org)
    (org / "build").mkdir()
    (org / "build" / "out.js").write_text("artifact\n", encoding="utf-8")
    assert _sub(org) == before


def test_subject_changes_for_staged_and_unstaged_alike(tmp_path):
    """The id moves for a tracked change whether it is staged or unstaged."""
    org = _repo(tmp_path)
    base = _sub(org)
    (org / "t.txt").write_text("tracked\nunstaged\n", encoding="utf-8")
    unstaged = _sub(org)
    assert unstaged != base
    subprocess.run(["git", "add", "t.txt"], cwd=org, check=True)
    assert _sub(org) == unstaged        # the same content gives the same id (staging is not the
                                        # subject)


def test_subject_does_not_touch_the_real_index(tmp_path):
    """It uses a temporary index, so the supervisor's staging state is not broken."""
    org = _repo(tmp_path)
    (org / "untracked.txt").write_text("x\n", encoding="utf-8")
    (org / "t.txt").write_text("tracked\nmodified\n", encoding="utf-8")
    before = subprocess.run(["git", "status", "--porcelain"], cwd=org,
                            capture_output=True, text=True).stdout
    _sub(org)
    after = subprocess.run(["git", "status", "--porcelain"], cwd=org,
                           capture_output=True, text=True).stdout
    assert before == after
    assert "?? untracked.txt" in after       # it was not staged


def test_subject_records_dirty_and_head_tree_separately(tmp_path):
    """Both whether it is dirty and what HEAD's tree is are kept (in a form traceable later)."""
    sys.path.insert(0, str(TOOLS))
    from orgcycle._core import review_subject
    org = _repo(tmp_path)
    _, clean = review_subject(7, "gate", "implement", cwd=str(org))
    assert clean["dirty"] == ""
    assert clean["reviewed_tree_sha"] == clean["head_tree_sha"]
    (org / "untracked.txt").write_text("x\n", encoding="utf-8")
    _, dirty = review_subject(7, "gate", "implement", cwd=str(org))
    assert dirty["dirty"] == "1"
    assert dirty["reviewed_tree_sha"] != dirty["head_tree_sha"]


# ── #101: verify's subject describes the Issue's worktree ──────────────────
# Typing `verify --issue N` from the main tree (the repository root) made the cwd's tree the
# subject, and every Issue minted the same one (main at ahead=0) (OBS-031/055/071).
# A joint admission uses matching subjects as evidence that "the two lineages looked at the same
# thing", so a cwd-dependent subject breaks the identity of an independent judgment.

def _subject_org(tmp_path, issues=(7, 8)):
    """A scratch org: a primary holding main and develop, plus a worktree per Issue (each one
    commit ahead)."""
    repo = tmp_path / "org"
    repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "organization.yaml").write_text("name: t\n", encoding="utf-8")
    (repo / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    integration_ref: develop\n", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "seed"); g("branch", "develop")
    for issue in issues:
        code, out = run("github_sync.py", "branch", "--issue", str(issue), "--worktree",
                        "--base", "develop", "--repo", "o/n", cwd=str(repo))
        assert code == 0, out
        wt = repo / ".orgforge" / "wt" / f"issue-{issue}"
        (wt / f"F{issue}.txt").write_text("x\n", encoding="utf-8")
        g("add", "-A", cwd=wt); g("commit", "-qm", f"i{issue}", cwd=wt)
    return repo, g


def _print_subject(repo, issue, *extra, cwd=None):
    """Run verify --print-subject and return (returncode, sid, parts, stderr)."""
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", str(issue), "--role", "gate", "--print-subject", *extra],
                       capture_output=True, text=True, cwd=str(cwd or repo))
    sid = next((l.strip() for l in p.stdout.splitlines()
                if re.fullmatch(r"[0-9a-f]{64}", l.strip())), None)
    parts = dict(re.findall(r"^\s*(\w+)\s*=\s*(\S+)", p.stderr, re.M))
    return p.returncode, sid, parts, p.stderr


def test_verify_subject_is_the_issue_worktree_not_cwd(tmp_path):
    """The regression itself: typed from the main tree's cwd, the subject still describes the Issue
    worktree's tree."""
    repo, g = _subject_org(tmp_path)
    wt_tree = g("rev-parse", "HEAD^{tree}",
                cwd=repo / ".orgforge" / "wt" / "issue-7").stdout.strip()
    root_tree = g("rev-parse", "HEAD^{tree}").stdout.strip()
    assert wt_tree != root_tree, "premise: the worktree is ahead of the main tree"

    code, sid, parts, err = _print_subject(repo, 7)
    assert code == 0, err
    assert parts["reviewed_tree_sha"] == wt_tree, \
        "the cwd's (the main tree's) tree became the subject — the #101 regression"
    assert parts["reviewed_tree_sha"] != root_tree
    assert parts["ahead"] == "1", (
        "the worktree should be one commit ahead of develop (ahead=0 means it observed the cwd)")

    # With the cwd inside that worktree it behaves as before (the same subject)
    code2, sid2, _, err2 = _print_subject(repo, 7,
                                          cwd=repo / ".orgforge" / "wt" / "issue-7")
    assert code2 == 0, err2
    assert sid2 == sid, "the subject differs from the one typed inside the worktree"


def test_verify_subjects_differ_across_issues(tmp_path):
    """Two Issues with different worktrees give different subjects, even typed from the same
    cwd."""
    repo, _ = _subject_org(tmp_path)
    code7, sid7, p7, err7 = _print_subject(repo, 7)
    code8, sid8, p8, err8 = _print_subject(repo, 8)
    assert code7 == 0 and code8 == 0, err7 + err8
    assert sid7 != sid8, (
        "different Issues share a subject — false evidence of \"they looked at the same thing\" "
        "could be manufactured")
    assert p7["reviewed_tree_sha"] != p8["reviewed_tree_sha"]


def test_verify_fails_closed_when_worktree_is_missing(tmp_path):
    """With no worktree it exits non-zero. It does not mint a subject through an implicit fallback
    to the cwd."""
    repo, _ = _subject_org(tmp_path, issues=())
    code, sid, _, err = _print_subject(repo, 42)
    assert code != 0
    assert sid is None, "a subject was minted with no worktree present — fail-open"
    assert os.path.join(".orgforge", "wt", "issue-42") in err, \
        "the expected worktree path does not appear in the error"
    assert "--subject-root" in err


def test_verify_subject_root_override(tmp_path):
    """--subject-root is the explicit escape hatch for a layout that does not use worktrees. It
    stays in what is printed."""
    repo, g = _subject_org(tmp_path, issues=())
    root_tree = g("rev-parse", "HEAD^{tree}").stdout.strip()
    code, sid, parts, err = _print_subject(repo, 42, "--subject-root", str(repo))
    assert code == 0, err
    assert sid and parts["reviewed_tree_sha"] == root_tree
    assert parts.get("subject_root") == os.path.abspath(str(repo)), \
        "which checkout the judgment was intended for does not appear in what is printed"


def test_verify_rejects_issue_worktree_with_unbound_branch(tmp_path):
    """A detached, or differently-branched, Issue worktree is not accepted as that Issue's
    deliverable."""
    repo, g = _subject_org(tmp_path, issues=(7,))
    wt = repo / ".orgforge" / "wt" / "issue-7"
    g("checkout", "--detach", "develop", cwd=wt)
    code, sid, _, err = _print_subject(repo, 7)
    assert code == 12
    assert sid is None
    assert "branch" in err and "binding convention" in err


# ── #101 rework: isdir lets a fake worktree through (the skeptic's refutation) ──
# An empty leftover directory, a directory recreated without pruning, and a symlink to the repo
# root all sit inside the primary, so `git -C` resolves to the primary and the subject is minted
# without warning as the primary's tree (ahead=0, relation=current) — reproducing the OBS-071
# forgery.
# Only confirming "a real worktree whose own toplevel is exactly there" makes it fail-closed.

def test_verify_rejects_empty_stub_at_worktree_path(tmp_path):
    """No subject is minted from the empty directory a failed `git worktree add` leaves behind."""
    repo, g = _subject_org(tmp_path, issues=())
    fake = repo / ".orgforge" / "wt" / "issue-42"
    fake.mkdir(parents=True)
    code, sid, _, err = _print_subject(repo, 42)
    assert code != 0, (
        "verify succeeded on a leftover directory — the primary's tree gets forged")
    assert sid is None, (
        "a subject was minted from a leftover directory (the OBS-071 forgery)")
    assert os.path.join(".orgforge", "wt", "issue-42") in err


def test_verify_rejects_symlink_at_worktree_path(tmp_path):
    """No subject is minted where the canonical path is a symlink to the repo root either."""
    repo, g = _subject_org(tmp_path, issues=())
    (repo / ".orgforge" / "wt").mkdir(parents=True, exist_ok=True)
    (repo / ".orgforge" / "wt" / "issue-43").symlink_to(repo)
    code, sid, _, err = _print_subject(repo, 43)
    assert code != 0, (
        "verify succeeded through a symlink — the primary's tree gets forged")
    assert sid is None
    assert os.path.join(".orgforge", "wt", "issue-43") in err


def test_verify_fails_after_worktree_replaced_with_plain_dir(tmp_path):
    """It does not stay quiet through the transition where a real worktree vanishes and a plain
    directory is recreated at the same path."""
    import shutil
    repo, g = _subject_org(tmp_path)
    wt = repo / ".orgforge" / "wt" / "issue-7"
    wt_tree = g("rev-parse", "HEAD^{tree}", cwd=wt).stdout.strip()
    code, sid, parts, err = _print_subject(repo, 7)
    assert code == 0 and parts["reviewed_tree_sha"] == wt_tree, err
    shutil.rmtree(wt)
    wt.mkdir()                     # recreated after rm -rf without pruning (the shape that happens
                                   # in the field)
    code2, sid2, _, err2 = _print_subject(repo, 7)
    assert code2 != 0, (
        "verify still succeeded after the worktree vanished — it silently swaps to the primary's "
        "tree")
    assert sid2 is None


# ── #106: the integration target resolves from the constitution's integration_ref (develop is not
#    guessed) ──
# Measured on Tatekae: the constitution declared integration_ref: origin/main while begin
# (OBS-053), show (OBS-054), gc (OBS-057), and integrate (OBS-048) hard-coded develop, so one
# product held several answers to "where does this integrate". The resolution verify already uses
# (review_freshness.integration_ref_policy) is shared across every subcommand.


def _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org106"):
    """A git-backed org whose constitution declares the integration target (or does not). No develop
    by default."""
    org = tmp_path / name
    org.mkdir()

    def g(*a, cwd=org):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)

    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (org / "seed.txt").write_text("s", encoding="utf-8")
    (org / "organization.yaml").write_text("roles: []\n", encoding="utf-8")
    judges = f"    integration_ref: {integration_ref}\n" if integration_ref else ""
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n" + (judges or "    {}\n"), encoding="utf-8")
    # The governing files are **committed to main before** any branch is cut — this prevents the
    # accident where a later `add -A` sweeps the constitution onto a feature branch and a checkout
    # makes it disappear.
    g("add", "-A")
    g("commit", "-qm", "seed")
    g("update-ref", "refs/remotes/origin/main", "main")
    if develop:
        g("branch", "develop")
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    return org, g


def test_resolve_integration_base_explicit_wins_and_constitution_is_default(tmp_path, monkeypatch):
    """An explicit --base beats the constitution's integration_ref, which beats fail-closed (develop
    is not guessed)."""
    core = _cycle_mod("_core")
    org, _ = _declared_org(tmp_path, integration_ref="origin/main", develop=True)
    monkeypatch.chdir(org)
    assert core.resolve_integration_base("develop") == ("develop", None)   # operator override
    ref, err = core.resolve_integration_base(None)
    assert (ref, err) == ("origin/main", None), (
        f"it is not reading the constitution's declaration: {err}")


def test_resolve_integration_base_fails_closed_naming_both_options(tmp_path, monkeypatch):
    """(d) A legacy org with a develop and no integration_ref → it does not fall to develop
    silently."""
    core = _cycle_mod("_core")
    org, _ = _declared_org(tmp_path, integration_ref=None, develop=True)
    monkeypatch.chdir(org)
    ref, err = core.resolve_integration_base(None)
    assert ref is None, f"it guessed {ref} with no integration_ref"
    assert "--base" in err and "integration_ref" in err, (
        f"it does not name both options: {err}")


def test_gc_collects_worktree_merged_to_constitution_ref(tmp_path, monkeypatch):
    """(a) OBS-057: gc can remove a worktree already integrated into origin/main, in an org with no
    develop."""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    wt = org / ".orgforge" / "wt" / "issue-3"
    g("worktree", "add", "-q", "-b", "feat/issue-3", str(wt), "origin/main")
    monkeypatch.chdir(org)
    m = _cycle_mod("inspect")
    rc = m.cmd_gc(argparse.Namespace(base=None, all=False))
    assert rc == 0
    assert not wt.is_dir(), (
        "a worktree already integrated into origin/main was left as \"unintegrated\"")


def test_gc_explicit_base_overrides_constitution(tmp_path, monkeypatch):
    """(b) An explicit --base beats the constitution (an operator override)."""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=True)
    g("checkout", "-q", "develop")
    (org / "d.txt").write_text("d", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "develop ahead")
    g("checkout", "-q", "main")
    wt = org / ".orgforge" / "wt" / "issue-4"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-4", str(wt), "develop")
    monkeypatch.chdir(org)
    m = _cycle_mod("inspect")
    # Unintegrated against the constitution (origin/main) → it stays
    assert m.cmd_gc(argparse.Namespace(base=None, all=False)) == 0
    assert wt.is_dir()
    # Integrated under an explicit --base develop → it is removed
    assert m.cmd_gc(argparse.Namespace(base="develop", all=False)) == 0
    assert not wt.is_dir(), "an explicit --base lost to the constitution"


# ── #107: reconcile the derived branch name against the branch that exists ──
# Measured on Tatekae (OBS-012 / OBS-048 defect 6 / OBS-057 cause 2): the derived name
# feat/issue-15-google did not exist (the real one was feat/issue-15-login-redirect), so gc's
# `--merged --list <derived name>` was always empty → an integrated worktree stood forever as
# "unintegrated". The worktree's HEAD is always true.


def test_gc_collects_merged_worktree_whose_real_branch_differs_from_derived(
        tmp_path, monkeypatch, capsys):
    """(a) The Tatekae shape: the worktree is on feat/issue-15-login-redirect (already integrated
    into origin/main) while the title-derived name is feat/issue-15-google → gc decides merged from
    the real HEAD and cleans it up."""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107")
    wt = org / ".orgforge" / "wt" / "issue-15"
    g("worktree", "add", "-q", "-b", "feat/issue-15-login-redirect", str(wt), "origin/main")
    (wt / "fix.txt").write_text("done", encoding="utf-8")
    g("add", "-A", cwd=wt)
    g("commit", "-qm", "fix login redirect", cwd=wt)
    # Make it integrated: advance origin/main to the branch tip (the shape of a completed merge)
    g("update-ref", "refs/remotes/origin/main", "feat/issue-15-login-redirect")
    monkeypatch.chdir(org)
    m = _cycle_mod("inspect")
    # The derived name comes from the title (the shape after a retitle) — it does not exist
    monkeypatch.setattr(m, "_branch_for", lambda i: f"feat/issue-{i}-google")
    rc = m.cmd_gc(argparse.Namespace(base=None, all=False))
    assert rc == 0
    assert not wt.is_dir(), (
        "an integrated worktree was left — it asks about merged under the derived name "
        "feat/issue-15-google (#107)")
    # (b) A mismatch is not passed over quietly — a warning says which was taken
    err = capsys.readouterr().err
    assert "feat/issue-15-google" in err and "feat/issue-15-login-redirect" in err, \
        f"the mismatch between the derived and the real name is not warned about: {err!r}"


def test_gc_keeps_worktree_when_branch_cannot_be_resolved(tmp_path, monkeypatch, capsys):
    """(d) fail-closed: a detached-HEAD worktree with a derived name that does not exist → it is
    left standing and said so."""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107d")
    wt = org / ".orgforge" / "wt" / "issue-9"
    g("worktree", "add", "-q", "--detach", str(wt), "origin/main")
    monkeypatch.chdir(org)
    m = _cycle_mod("inspect")
    monkeypatch.setattr(m, "_branch_for", lambda i: f"feat/issue-{i}-ghost")
    rc = m.cmd_gc(argparse.Namespace(base=None, all=False))
    assert rc == 0
    assert wt.is_dir(), (
        "it removed the worktree without identifying the branch that exists")
    captured = capsys.readouterr()
    err = captured.err
    assert "feat/issue-9-ghost" in err, (
        f"it does not name what could not be resolved: {err!r}")
    out = captured.out
    assert "a detached HEAD, so it is not removed automatically" in out
    assert f"git worktree remove {wt}" in out


def test_resolve_issue_branch_worktree_head_is_authoritative(tmp_path):
    """(a)(b) Where the worktree exists its HEAD is true. A divergence from the derived name warns
    (it is not passed over quietly)."""
    core = _cycle_mod("_core")
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107r")
    wt = org / ".orgforge" / "wt" / "issue-15"
    g("worktree", "add", "-q", "-b", "feat/issue-15-login-redirect", str(wt), "origin/main")
    br, warn, err = core.resolve_issue_branch(15, derived="feat/issue-15-google", cwd=str(org))
    assert (br, err) == ("feat/issue-15-login-redirect", None)
    assert warn and "feat/issue-15-google" in warn and "feat/issue-15-login-redirect" in warn
    # (e) Where the derived name equals the real one it behaves as before — no warn either
    br2, warn2, err2 = core.resolve_issue_branch(
        15, derived="feat/issue-15-login-redirect", cwd=str(org))
    assert (br2, warn2, err2) == ("feat/issue-15-login-redirect", None, None)


def test_resolve_issue_branch_uses_existing_derived_without_worktree(tmp_path):
    """(c) No worktree, and the derived name exists → it is used, once confirmed to exist."""
    core = _cycle_mod("_core")
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107c")
    g("branch", "feat/issue-7-add-login")
    br, warn, err = core.resolve_issue_branch(7, derived="feat/issue-7-add-login", cwd=str(org))
    assert (br, warn, err) == ("feat/issue-7-add-login", None, None)


def test_resolve_issue_branch_names_detached_worktree_truthfully(tmp_path):
    """#107 rework (3b): with a worktree present it does not lie that "there is no worktree either"
    — it states the fact that one exists but is a detached HEAD pointing at no branch."""
    core = _cycle_mod("_core")
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107t")
    wt = org / ".orgforge" / "wt" / "issue-9"
    g("worktree", "add", "-q", "--detach", str(wt), "origin/main")
    br, warn, err = core.resolve_issue_branch(9, derived="feat/issue-9-ghost", cwd=str(org))
    assert br is None and err
    assert "either" not in err, (
        f"it diagnosed \"there is none\" while a worktree exists: {err!r}")
    assert "detached" in err, f"it does not state the real state (a detached HEAD): {err!r}"


def test_resolve_issue_branch_fails_closed_when_nothing_exists(tmp_path):
    """(d) No worktree, and the derived name does not exist either → it does not silently believe
    the derived name, and it names the fix."""
    core = _cycle_mod("_core")
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107f")
    br, warn, err = core.resolve_issue_branch(7, derived="feat/issue-7-add-login", cwd=str(org))
    assert br is None
    assert err and "feat/issue-7-add-login" in err, (
        "it does not name the derived name that does not exist")
    assert "--worktree" in err or "git branch --list" in err, \
        f"the fix is not written: {err!r}"


def test_gc_fails_closed_when_nothing_declares_the_base(tmp_path):
    """(c)(d) No integration_ref and no --base → non-zero, naming both, even with a develop
    present."""
    org, g = _declared_org(tmp_path, integration_ref=None, develop=True)
    (org / ".orgforge" / "wt").mkdir(parents=True, exist_ok=True)
    code, out = run("org_cycle.py", "gc", cwd=str(org))
    assert code != 0, (
        "gc proceeded quietly although no integration target is declared")
    assert "--base" in out and "integration_ref" in out, out


def test_begin_fails_closed_and_writes_nothing_without_declared_base(tmp_path):
    """(c) begin: where the integration target is undecided, it stops non-zero before writing
    anything to the ledger."""
    org, g = _declared_org(tmp_path, integration_ref=None, develop=True)
    code, out = run("org_cycle.py", "begin", "--role", "r", "--issue", "5",
                    "--parent", "9", "--candidate-id", "cid", "--no-check", cwd=str(org))
    assert code != 0, "begin proceeded although the worktree base is undecided"
    assert "--base" in out and "integration_ref" in out, out
    ledger = org / ".orgforge" / "ledger" / "ledger.jsonl"
    assert not ledger.exists() or not ledger.read_text().strip(), \
        "it wrote to the ledger before failing closed"


def test_begin_worktree_base_comes_from_constitution(tmp_path, monkeypatch):
    """(a) OBS-053: begin's worktree is cut from the constitution's integration_ref."""
    org, _ = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    monkeypatch.chdir(org)
    m = _cycle_mod("cycle")
    calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: (calls.append(a), (0, ""))[1])
    monkeypatch.setattr(m, "_ledger", lambda *a: (0, ""))
    rc = m.cmd_begin(argparse.Namespace(
        role="r", issue=5, agent=None, phase="implement", parent="9",
        candidate_id="cid-5", base=None, why=None, no_check=True, no_worktree=False))
    assert rc == 0
    branch_calls = [c for c in calls if c and c[0] == "branch"]
    assert branch_calls, "there is no branch call preparing a worktree"
    assert "--base" in branch_calls[0] and "origin/main" in branch_calls[0], (
        f"begin does not pass the constitution's integration target as the worktree base: "
        f"{branch_calls[0]}")


def test_begin_mints_new_candidate_identity_after_rework(monkeypatch):
    m = _cycle_mod("cycle")
    monkeypatch.setattr(m, "_candidate_id", lambda _issue: "issue-7")
    monkeypatch.setattr(m, "_events_for", lambda _issue: (
        [{"class": "rework_requested", "payload": {"round": "2"}}], set()))
    seen = {}
    monkeypatch.setattr(m, "_steps_begin", lambda _a, _parent, cid: seen.setdefault("cid", cid) or [])
    monkeypatch.setattr(m, "_execute", lambda _steps, _label: 0)
    rc = m.cmd_begin(argparse.Namespace(
        role="r", issue=7, agent=None, phase="implement", parent="9",
        candidate_id=None, base=None, why=None, no_check=True, no_worktree=True))
    assert rc == 0
    assert seen["cid"] == "issue-7-rework-2"


def test_show_attributes_nothing_when_clean_against_constitution_ref(tmp_path):
    """(a) OBS-054: with a zero diff against origin/main, no irreversible change is
    misattributed."""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    g("branch", "feat/issue-7")          # the same commit as origin/main (a zero diff)
    code, out = run("org_cycle.py", "show", "--issue", "7", cwd=str(org))
    assert code == 0, out
    assert "irrev." not in out, (
        f"it attributed an irreversible change with a zero diff:\n{out}")


def test_show_without_declared_base_prints_status_warns_and_skips_attribution(tmp_path):
    """rework #106: show is read-only orientation — it prints the state from the ledger even with no
    reference.

    fail-closed applies only to a judgment that **consumes** the base (the attribution block): the
    block is omitted and a warning follows warn-don't-stop (the same shape as cmd_plan). develop is
    not guessed.
    """
    org, _ = _declared_org(tmp_path, integration_ref=None, develop=True)
    code, out = run("org_cycle.py", "show", "--issue", "7", cwd=str(org))
    assert code == 0, (
        f"a missing reference shut out the whole orientation:\n{out}")
    assert "verdicts" in out and "next:" in out, (
        f"the state that comes from the ledger is not printed:\n{out}")
    assert "--base" in out and "integration_ref" in out, (
        f"the warning does not name both options:\n{out}")
    # The attribution block's row label is "irrev.:". Keep it distinct from the warning text.
    assert "irrev.:" not in out, (
        f"it printed the attribution block with no reference:\n{out}")
    assert "not attributing irreversible changes" in out, (
        f"it does not say that the attribution was omitted:\n{out}")


def test_show_attribution_block_fires_when_base_is_declared(tmp_path):
    """With a declaration the attribution block works as before (checking the rework did not lean
    too far toward warning)."""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    g("checkout", "-q", "-b", "feat/issue-9")
    (org / "migrations").mkdir()
    for n in ("0001_a.sql", "0002_b.sql", "0003_c.sql"):
        (org / "migrations" / n).write_text("select 1;", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "migrations")
    g("checkout", "-q", "main")
    code, out = run("org_cycle.py", "show", "--issue", "9", cwd=str(org))
    assert code == 0, out
    assert "irrev." in out and "3 —" in out, (
        f"the attribution block is not working with a declared reference:\n{out}")


def test_gc_all_works_without_declared_base(tmp_path):
    """rework #106: --all decides no integration = it consumes no base → it demands no
    declaration."""
    org, g = _declared_org(tmp_path, integration_ref=None, develop=True)
    wt = org / ".orgforge" / "wt" / "issue-6"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-6", str(wt), "main")
    code, out = run("org_cycle.py", "gc", "--all", cwd=str(org))
    assert code == 0, (
        f"--all, which consumes no base, demanded a declaration:\n{out}")
    assert not wt.is_dir(), f"--all did not remove a clean worktree:\n{out}"


def test_integrate_plan_targets_constitution_ref(tmp_path):
    """(a) OBS-048: integrate --plan's integration target becomes the constitution's
    declaration."""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    g("checkout", "-q", "-b", "feat/issue-42")
    (org / "w.txt").write_text("w", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "work")
    g("checkout", "-q", "main")
    code, out = run("org_cycle.py", "integrate", "--issue", "42", "--plan", cwd=str(org))
    assert code == 0, out
    assert "→ origin/main" in out, (
        f"the integration target does not follow the declaration:\n{out}")
    assert "→ develop" not in out


def test_integrate_plan_fails_closed_without_declared_base(tmp_path):
    """(c)(d) integrate does not guess either — with no declaration it is non-zero, develop or
    not."""
    org, g = _declared_org(tmp_path, integration_ref=None, develop=True)
    g("checkout", "-q", "-b", "feat/issue-42")
    g("checkout", "-q", "main")
    code, out = run("org_cycle.py", "integrate", "--issue", "42", "--plan", cwd=str(org))
    assert code != 0, (
        "integrate --plan proceeded although no integration target is declared")
    assert "--base" in out and "integration_ref" in out, out


# ── findings are first-class: a withholding verdict owes an itemised reason ──────────────────
# The id in the prose ("GATE-001") used to be the judge's own numbering, invisible to the tools —
# so nothing could count the findings, answer them in one pass, or tell a re-raised finding from
# a new one. On domain-spec-notes #67, GATE-001..005 existed only inside `why`.

def _gate_report(**kw):
    base = {"verdict": "reject", "why": "The MUSTs are not met; see the findings below in full.",
            "evidence": "make test: 10 passed; rg required_relations -> 0 hits",
            "standard": "the four EARS on the Issue", "alternatives": None,
            "risk": "none", "out_of_scope": []}
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


def _finding(**kw):
    base = {"id": "GATE-001", "claim": "required relations are not expressible in the template",
            "evidence": "rg required_relations -> 0 hits", "blocks_admission": True,
            "prior_finding": None}
    base.update(kw)
    return base


def _intake(report, role="gate"):
    return subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                           "--issue", "11", "--role", role, "--report", "-"],
                          input=report, capture_output=True, text=True, timeout=60)


def test_intake_requires_findings_when_the_verdict_withholds():
    """**A verdict that holds work back has to say what for, item by item.** Otherwise the next
    round has only prose to work from, and re-raises whatever it re-reads."""
    r = _intake(_gate_report())
    assert r.returncode == 10, r.stdout + r.stderr
    assert "findings" in r.stdout + r.stderr


def test_intake_accepts_a_withholding_verdict_that_itemises():
    assert _intake(_gate_report(findings=[_finding()])).returncode == 0


def test_intake_does_not_demand_findings_from_an_admit():
    """An admit withholds nothing, so it owes no itemisation — the check must not turn into
    ceremony on the happy path."""
    assert _intake(_gate_report(verdict="admit")).returncode == 0


def test_intake_rejects_duplicate_finding_ids():
    """A duplicate id makes a response ambiguous about which finding it answered."""
    r = _intake(_gate_report(findings=[_finding(), _finding()]))
    assert r.returncode == 10
    assert "GATE-001" in r.stdout + r.stderr


def test_intake_rejects_a_withholding_verdict_where_nothing_blocks():
    """Otherwise the verdict holds the work while every finding says it is not the reason."""
    r = _intake(_gate_report(findings=[_finding(blocks_admission=False)]))
    assert r.returncode == 10
    assert "blocks_admission" in r.stdout + r.stderr


@pytest.mark.parametrize("bad", [{"id": "gate-1"}, {"claim": "too short"}, {"evidence": ""}])
def test_intake_rejects_findings_that_cannot_be_acted_on(bad):
    """An id that cannot be cited, a claim nobody can check, or a finding with no evidence is not
    something the next round can answer."""
    assert _intake(_gate_report(findings=[_finding(**bad)])).returncode == 10
