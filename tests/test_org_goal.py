import concurrent.futures
import json
import os
import pathlib
import shutil
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "org_goal.py"
SCHEMA = REPO / "template" / "ledger-schema.yaml"


def _org(tmp_path):
    root = tmp_path / "product"
    root.mkdir()
    (root / "organization.yaml").write_text("purpose: test\n", encoding="utf-8")
    shutil.copy(SCHEMA, root / "ledger-schema.yaml")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "organization.yaml", "ledger-schema.yaml"], cwd=root, check=True)
    subprocess.run([
        "git", "-c", "user.name=test", "-c", "user.email=test@example.com",
        "commit", "-qm", "baseline",
    ], cwd=root, check=True)
    return root


def _run(root, session, *args, harness="source"):
    env = dict(os.environ, ORG_ORGAN_SESSION_ID=session, ORG_ORGAN_HARNESS=harness,
               ORG_ROLE="supervisor", ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"))
    return subprocess.run(
        [sys.executable, str(TOOL), *args, "--root", str(root / ".orgforge" / "ledger"),
         "--json"],
        cwd=root, env=env, capture_output=True, text=True,
    )


def _body(run):
    assert run.stdout, run.stderr
    return json.loads(run.stdout)


def test_goal_survives_processes_and_rejects_double_start(tmp_path):
    root = _org(tmp_path)
    first = _run(root, "session-a", "start", "ship the release")
    assert first.returncode == 0, first.stderr
    goal = _body(first)["goal"]
    assert goal["status"] == "active"
    assert goal["objective"] == "ship the release"

    status = _run(root, "session-a", "status")
    assert status.returncode == 0
    assert _body(status)["goal"]["goal_id"] == goal["goal_id"]

    duplicate = _run(root, "session-a", "start", "overwrite it")
    assert duplicate.returncode != 0
    assert "unfinished" in _body(duplicate)["error"]


def test_concurrent_double_start_allows_exactly_one_goal(tmp_path):
    root = _org(tmp_path)

    def start(objective):
        return _run(root, "session-a", "start", objective)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(start, ("first objective", "second objective")))
    assert sorted(run.returncode for run in runs) == [0, 3]
    assert len(_body(_run(root, "session-a", "status"))["goal"]["goal_id"]) > 5


def test_new_session_must_resume_before_progress_and_resume_is_compare_and_swap(tmp_path):
    root = _org(tmp_path)
    assert _run(root, "session-a", "start", "cross harness goal").returncode == 0
    stale = _run(root, "session-b", "progress", "--summary", "looked", "--next-step", "test")
    assert stale.returncode != 0
    assert "resume" in _body(stale)["error"]

    def resume(session):
        return _run(root, session, "resume", "--reason", "new host session")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(resume, ("session-b", "session-c")))
    assert sorted(run.returncode for run in runs) == [0, 3]
    current = _body(_run(root, "session-z", "status"))["goal"]
    assert current["session_id"] in {"session-b", "session-c"}
    assert current["resume_required"] is True


def test_block_requires_three_repeated_observations(tmp_path):
    root = _org(tmp_path)
    assert _run(root, "session-a", "start", "wait safely").returncode == 0
    for occurrence in (1, 2):
        run = _run(root, "session-a", "block", "--reason", "provider unavailable",
                   "--evidence", f"attempt-{occurrence}")
        assert run.returncode == 0, run.stderr
        result = _body(run)
        assert result["goal"]["status"] == "active"
        assert result["blocker"]["occurrences"] == occurrence
    third = _run(root, "session-a", "block", "--reason", "provider unavailable",
                 "--evidence", "attempt-3")
    assert third.returncode == 0, third.stderr
    assert _body(third)["goal"]["status"] == "blocked"


def test_paused_goal_can_resume_in_the_same_session(tmp_path):
    root = _org(tmp_path)
    assert _run(root, "session-a", "start", "pause safely").returncode == 0
    paused = _run(root, "session-a", "pause", "--reason", "user requested pause",
                  "--next-step", "continue validation")
    assert paused.returncode == 0, paused.stderr
    assert _body(paused)["goal"]["status"] == "paused"
    resumed = _run(root, "session-a", "resume", "--reason", "user requested continuation")
    assert resumed.returncode == 0, resumed.stderr
    assert _body(resumed)["goal"]["status"] == "active"


def test_completion_requires_resolvable_evidence(tmp_path):
    root = _org(tmp_path)
    assert _run(root, "session-a", "start", "prove it").returncode == 0
    absent = _run(root, "session-a", "complete", "--summary", "done",
                  "--evidence", "file:missing.txt")
    assert absent.returncode != 0
    assert "evidence" in _body(absent)["error"]

    (root / "proof.txt").write_text("tests passed\n", encoding="utf-8")
    done = _run(root, "session-a", "complete", "--summary", "done",
                "--evidence", "file:proof.txt")
    assert done.returncode == 0, done.stderr
    result = _body(done)
    assert result["goal"]["status"] == "complete"
    assert result["goal"]["evidence"] == ["file:proof.txt"]


def test_cross_harness_reads_and_resumes_the_same_goal(tmp_path):
    root = _org(tmp_path)
    started = _run(root, "claude-session", "start", "portable goal", harness="claude-code")
    assert started.returncode == 0
    codex_status = _body(_run(root, "codex-session", "status", harness="codex"))["goal"]
    assert codex_status["objective"] == "portable goal"
    assert codex_status["resume_required"] is True
    resumed = _run(root, "codex-session", "resume", "--reason", "continue in Codex",
                   harness="codex")
    assert resumed.returncode == 0, resumed.stderr
    assert _body(resumed)["goal"]["harness"] == "codex"


def test_codex_native_sync_is_explicitly_recorded_as_projection(tmp_path):
    root = _org(tmp_path)
    started = _run(root, "codex-session", "start", "native mirror", harness="codex")
    assert _body(started)["host_action"]["action"] == "ensure_native_goal"
    synced = _run(root, "codex-session", "host-sync", "--state", "active",
                  "--assurance", "observed", "--native-ref", "thread-1", harness="codex")
    assert synced.returncode == 0, synced.stderr
    host = _body(synced)["goal"]["host_sync"]["codex"]
    assert host == {"assurance": "observed", "detail": None, "native_ref": "thread-1",
                    "seq": 2, "state": "active"}
    (root / "proof.txt").write_text("ok\n", encoding="utf-8")
    complete = _run(root, "codex-session", "complete", "--summary", "verified",
                    "--evidence", "file:proof.txt", harness="codex")
    assert complete.returncode == 0, complete.stderr
    final_sync = _run(root, "codex-session", "host-sync", "--state", "complete",
                      "--assurance", "observed", harness="codex")
    assert final_sync.returncode == 0, final_sync.stderr
    assert _body(final_sync)["goal"]["host_sync"]["codex"]["state"] == "complete"


def test_session_start_reinjects_goal_and_cross_harness_resume_command(tmp_path):
    root = _org(tmp_path)
    ledger = root / ".orgforge" / "ledger"

    def session_start(harness, session):
        bundle = REPO / "integrations" / harness
        env = dict(os.environ, ORG_LEDGER_ROOT=str(ledger), ORG_ROLE="supervisor",
                   ORG_TOOLS_DIR=str(bundle / "tools"))
        return subprocess.run(
            [sys.executable, str(bundle / "scripts" / "org_session_start.py")],
            input=json.dumps({"session_id": session}), cwd=root, env=env,
            capture_output=True, text=True,
        )

    claude = session_start("claude-code", "claude-session")
    assert claude.returncode == 0, claude.stderr
    claude_binding = json.loads(
        (root / ".git" / "orgforge" / "runtime" / "claude-code" /
         "installed-organ.json").read_text(encoding="utf-8"))
    start = subprocess.run(
        [claude_binding["launcher"], "org-goal", "start", "restart-safe goal", "--json"],
        cwd=root, capture_output=True, text=True)
    assert start.returncode == 0, start.stderr

    codex = session_start("codex", "codex-session")
    assert codex.returncode == 0, codex.stderr
    context = json.loads(codex.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Persistent OrgForge Goal" in context
    assert "restart-safe goal" in context
    assert "org-goal resume" in context
    assert "Codex's native Goal" in context
    codex_binding = json.loads(
        (root / ".git" / "orgforge" / "runtime" / "codex" /
         "installed-organ.json").read_text(encoding="utf-8"))
    resume = subprocess.run(
        [codex_binding["launcher"], "org-goal", "resume", "--reason", "new session", "--json"],
        cwd=root, capture_output=True, text=True)
    assert resume.returncode == 0, resume.stderr
    assert json.loads(resume.stdout)["goal"]["session_id"] == "codex-session"


def test_doctor_describes_real_host_capabilities(tmp_path):
    root = _org(tmp_path)
    run = _run(root, "session-a", "doctor", "--harness", "all")
    assert run.returncode == 0, run.stderr
    report = _body(run)
    assert report["ready"] is True
    assert report["adapters"]["codex"]["native_goal"] == "skill-mediated"
    assert report["adapters"]["claude-code"]["periodic_resume"] == "session-scoped /loop"
    assert report["guarantees"]["background_without_host"] is False


def test_goal_tool_and_adapters_are_projected_to_both_harnesses():
    source = TOOL.read_bytes()
    for harness in ("claude-code", "codex"):
        assert (REPO / "integrations" / harness / "tools" / "org_goal.py").read_bytes() == source
    assert (REPO / "integrations" / "claude-code" / "commands" / "org-goal.md").is_file()
    assert (REPO / "integrations" / "codex" / "skills" / "org-goal" / "SKILL.md").is_file()
