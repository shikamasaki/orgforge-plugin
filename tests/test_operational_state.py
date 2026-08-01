import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "operational_state.py"
ADAPT = REPO / "tools" / "adaptation.py"
LEDGER = REPO / "tools" / "ledger.py"
HOOK = REPO / "integrations" / "common" / "org_hook.py"


def _org(tmp_path):
    root = tmp_path / "org"
    root.mkdir()
    (root / "organization.yaml").write_text("purpose: operational resilience test\n", encoding="utf-8")
    shutil.copy(REPO / "template" / "constitution.yaml", root / "constitution.yaml")
    shutil.copy(REPO / "template" / "ledger-schema.yaml", root / "ledger-schema.yaml")
    return root


def _run(root, tool, *arguments):
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"), ORG_ROLE="supervisor")
    return subprocess.run(
        [sys.executable, str(tool), *arguments,
         "--root", str(root / ".orgforge" / "ledger"), "--json"],
        cwd=root, env=env, capture_output=True, text=True, timeout=30)


def _json(run):
    assert run.stdout, run.stderr
    return json.loads(run.stdout)


def _activate(root):
    run = _run(
        root, ADAPT, "activate", "--envelope", "required-reviewer-outage",
        "--trigger", "required_reviewer_unavailable", "--source", "judge_preflight",
        "--baseline-ref", "constitution:review-required",
        "--evidence", "outage_receipt=probe:judge-exit-75",
        "--evidence", "affected_artifact_inventory=file:artifacts.json",
        "--confidence", "0.95")
    assert run.returncode == 0, run.stdout + run.stderr
    return _json(run)["activation"]


def _degrade(root, session="session-1"):
    run = _run(
        root, TOOL, "degrade", "--envelope", "required-reviewer-outage",
        "--circuit", "reviewer:gate", "--dependency", "required-reviewer",
        "--artifact", "src/service.py", "--reason", "reviewer probe failed",
        "--evidence", "probe:judge-exit-75", "--confidence", "0.95",
        "--session-id", session, "--by", "supervisor")
    assert run.returncode == 0, run.stdout + run.stderr
    return _json(run)


def _begin(root, session="session-1", result="pass"):
    return _run(
        root, TOOL, "begin-recovery", "--actor", "gate", "--circuit", "reviewer:gate",
        "--reason", "reviewer probe recovered", "--evidence", f"probe:{result}",
        "--confidence", "0.99", "--session-id", session, "--by", "gate",
        "--result", result)


def _fire(root, command, tool_name="Bash", tool_input=None):
    event = {
        "hook_event_name": "PreToolUse", "tool_name": tool_name,
        "tool_input": tool_input or {"command": command},
        "session_id": "session-1", "tool_use_id": "toolu-operational-1",
        "cwd": str(root),
    }
    env = dict(os.environ, ORG_LEDGER_ROOT=str(root / ".orgforge" / "ledger"),
               ORG_TOOLS_DIR=str(REPO / "tools"),
               ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"))
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), cwd=root,
                          env=env, capture_output=True, text=True, timeout=30)


def test_doctor_and_projection_targets_are_explicit(tmp_path):
    root = _org(tmp_path)
    run = _run(root, TOOL, "doctor")
    assert run.returncode == 0, run.stdout + run.stderr
    report = _json(run)
    assert report["ready"] is True
    assert report["states"] == ["NORMAL", "DEGRADED", "HALTED", "RECOVERING"]
    assert report["projection_targets"] == ["canonical", "otel", "github-checks"]
    assert report["resilience_score"] is None


def test_reviewer_failure_degrades_blocks_ship_and_requires_taint_revalidation(tmp_path):
    root = _org(tmp_path)
    _activate(root)
    degraded = _degrade(root)
    assert degraded["state"]["effective_state"] == "DEGRADED"
    assert degraded["state"]["unresolved_taints"] == ["src/service.py"]
    assert degraded["state"]["circuits"]["reviewer:gate"]["to_state"] == "OPEN"

    merge = _run(root, TOOL, "authorize", "--action", "merge")
    assert merge.returncode == 3
    assert "forbidden" in _json(merge)["reason"]
    failover = _run(
        root, TOOL, "authorize", "--action", "cross_harness_failover",
        "--envelope", "required-reviewer-outage", "--phase", "test",
        "--artifact", "src/service.py")
    assert failover.returncode == 0, failover.stdout + failover.stderr
    undeclared = _run(root, TOOL, "authorize", "--action", "same_harness_claimed_as_independent")
    assert undeclared.returncode == 3

    stale = _begin(root, session="old-session")
    assert stale.returncode == 3
    assert "stale session" in _json(stale)["error"]
    begun = _begin(root)
    assert begun.returncode == 0, begun.stdout + begun.stderr
    assert _json(begun)["state"]["effective_state"] == "RECOVERING"

    early = _run(
        root, TOOL, "recover", "--actor", "gate", "--circuit", "reviewer:gate",
        "--reason", "all recovery checks passed", "--evidence", "ci:green",
        "--confidence", "1.0", "--session-id", "session-1", "--by", "gate")
    assert early.returncode == 3
    assert _json(early)["unresolved_taints"] == ["src/service.py"]

    revalidated = _run(
        root, TOOL, "revalidate", "--actor", "gate", "--artifact", "src/service.py",
        "--check", "review_decision", "--check", "tainted_artifacts",
        "--check", "integration_gate", "--result", "pass",
        "--evidence", "review:alternate-gate", "--session-id", "session-1", "--by", "gate")
    assert revalidated.returncode == 0, revalidated.stdout + revalidated.stderr
    recovered = _run(
        root, TOOL, "recover", "--actor", "gate", "--circuit", "reviewer:gate",
        "--reason", "all recovery checks passed", "--evidence", "ci:green",
        "--confidence", "1.0", "--session-id", "session-1", "--by", "gate")
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    state = _json(recovered)["state"]
    assert state["effective_state"] == "NORMAL"
    assert state["unresolved_taints"] == []
    assert state["circuits"]["reviewer:gate"]["to_state"] == "CLOSED"
    assert [row["to_state"] for row in state["transitions"]] == [
        "NORMAL", "DEGRADED", "RECOVERING", "NORMAL"]


def test_failed_half_open_probe_reopens_circuit_and_escalates_at_budget(tmp_path):
    root = _org(tmp_path)
    _activate(root)
    _degrade(root)
    failed = _begin(root, result="fail")
    assert failed.returncode == 3
    report = _json(failed)
    assert report["state"]["recorded_state"] == "DEGRADED"
    assert report["state"]["circuits"]["reviewer:gate"]["to_state"] == "OPEN"
    assert report["state"]["circuits"]["reviewer:gate"]["retry_count"] == 2
    assert report["escalation"]["route_to"] == "human"
    exhausted = _begin(root, result="pass")
    assert exhausted.returncode == 3
    assert "human handback" in _json(exhausted)["error"]


def test_artifacts_created_during_degraded_are_tainted_and_join_recovery_scope(tmp_path):
    root = _org(tmp_path)
    _activate(root)
    _degrade(root)
    deviation = _run(
        root, ADAPT, "deviate", "--envelope", "required-reviewer-outage",
        "--action", "cross_harness_failover", "--phase", "test",
        "--artifact", "generated/review.json", "--wai-baseline", "primary reviewer required",
        "--reason", "alternate reviewer used", "--result", "review generated",
        "--tainted-artifact", "generated/review.json")
    assert deviation.returncode == 0, deviation.stdout + deviation.stderr
    state = _json(_run(root, TOOL, "status"))["state"]
    assert state["taints"]["generated/review.json"]["source"] == "adaptive_deviation_recorded"
    assert state["taints"]["generated/review.json"]["cause_seq"] > 0
    assert state["taints"]["generated/review.json"]["revalidation_scope"] == [
        "review_decision", "tainted_artifacts", "integration_gate"]
    assert state["unresolved_taints"] == ["generated/review.json", "src/service.py"]


def test_expired_envelope_derives_halted_and_preserves_safe_actions(tmp_path):
    root = _org(tmp_path)
    _activate(root)
    _degrade(root)
    status = _run(root, TOOL, "status", "--now", "2099-01-01T00:00:00Z")
    assert status.returncode == 0
    assert _json(status)["state"]["effective_state"] == "HALTED"
    mutation = _run(root, TOOL, "authorize", "--action", "scope_reduction",
                    "--now", "2099-01-01T00:00:00Z")
    assert mutation.returncode == 3
    safe = _run(root, TOOL, "authorize", "--action", "safe_stop",
                "--now", "2099-01-01T00:00:00Z")
    assert safe.returncode == 0


def test_generic_append_cannot_forge_operational_transition(tmp_path):
    root = _org(tmp_path)
    payload = {
        "transition_id": "forged", "from_state": "NORMAL", "to_state": "DEGRADED",
        "circuit_id": "missing", "reason": "skip observation", "evidence": ["none"],
        "confidence": 1.0, "session_id": "attacker", "transitioned_by": "attacker",
        "envelope_id": "required-reviewer-outage", "activation_id": "forged",
    }
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"))
    run = subprocess.run(
        [sys.executable, str(LEDGER), "append", str(root / ".orgforge" / "ledger"),
         "--actor", "attacker", "--class", "operational_state_transitioned",
         "--payload", json.dumps(payload)], cwd=root, env=env,
        capture_output=True, text=True, timeout=30)
    assert run.returncode == 3
    assert "no observed circuit" in run.stderr


def test_canonical_otel_and_github_checks_preserve_identical_state_semantics(tmp_path):
    root = _org(tmp_path)
    _activate(root)
    _degrade(root)
    canonical = _json(_run(root, TOOL, "project", "--target", "canonical"))
    otel = _json(_run(root, TOOL, "project", "--target", "otel"))
    checks = _json(_run(root, TOOL, "project", "--target", "github-checks"))
    assert canonical == otel["body"] == checks["orgforge"]
    assert canonical["effective_state"] == "DEGRADED"
    assert otel["attributes"]["orgforge.operational_state.effective"] == "DEGRADED"
    assert checks["conclusion"] == "neutral"
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"))
    view = subprocess.run(
        [sys.executable, str(LEDGER), "view", str(root / ".orgforge" / "ledger"),
         "operational_state"], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert view.returncode == 0, view.stdout + view.stderr
    assert json.loads(view.stdout)["effective_state"] == canonical["effective_state"]


def test_existing_halt_events_fold_into_the_same_state_machine():
    spec = importlib.util.spec_from_file_location("operational_state_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    events = [
        {"seq": 1, "class": "halt_tripped", "payload": {"reason": "unsafe"}},
        {"seq": 2, "class": "halt_released", "payload": {"releases_seq": 1}},
    ]
    state = module.fold(events)
    assert state["effective_state"] == "NORMAL"
    assert [row["to_state"] for row in state["transitions"]] == ["NORMAL", "HALTED", "NORMAL"]


def test_halt_release_restores_underlying_degraded_state_instead_of_clearing_taint():
    spec = importlib.util.spec_from_file_location("operational_state_halt_overlay", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    events = [
        {"seq": 1, "class": "adaptive_envelope_activated", "payload": {
            "activation_id": "adapt-1", "envelope_id": "required-reviewer-outage",
            "expires_at": "2099-01-01T00:00:00Z"}},
        {"seq": 2, "class": "operational_state_transitioned", "payload": {
            "from_state": "NORMAL", "to_state": "DEGRADED", "session_id": "session-1",
            "envelope_id": "required-reviewer-outage", "activation_id": "adapt-1",
            "circuit_id": "reviewer:gate"}},
        {"seq": 3, "class": "artifact_tainted", "payload": {
            "artifact": "src/service.py", "activation_id": "adapt-1",
            "revalidation_scope": ["review_decision"]}},
        {"seq": 4, "class": "halt_tripped", "payload": {"reason": "unsafe"}},
        {"seq": 5, "class": "halt_released", "payload": {"releases_seq": 4}},
    ]
    state = module.fold(events)
    assert state["recorded_state"] == state["effective_state"] == "DEGRADED"
    assert state["unresolved_taints"] == ["src/service.py"]
    assert state["transitions"][-1]["to_state"] == "DEGRADED"


def test_mutating_commands_cannot_supply_a_future_clock_to_skip_cooldown(tmp_path):
    root = _org(tmp_path)
    _activate(root)
    _degrade(root)
    run = _run(
        root, TOOL, "begin-recovery", "--actor", "gate", "--circuit", "reviewer:gate",
        "--reason", "pretend cooldown elapsed", "--evidence", "probe:future",
        "--confidence", "1.0", "--session-id", "session-1", "--by", "gate",
        "--result", "pass", "--now", "2099-01-01T00:00:00Z")
    assert run.returncode == 2
    assert "writer clock" in _json(run)["error"]


def test_recovery_actor_and_installed_session_cannot_be_self_asserted(tmp_path):
    root = _org(tmp_path)
    _activate(root)
    _degrade(root)
    wrong_actor = _run(
        root, TOOL, "begin-recovery", "--circuit", "reviewer:gate",
        "--reason", "impersonate gate", "--evidence", "probe:pass", "--confidence", "1.0",
        "--session-id", "session-1", "--by", "gate", "--result", "pass")
    assert wrong_actor.returncode == 3
    assert "ledger actor" in _json(wrong_actor)["error"]

    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"), ORG_ROLE="gate",
               ORG_ORGAN_SESSION_ID="bound-session")
    stale = subprocess.run(
        [sys.executable, str(TOOL), "begin-recovery", "--actor", "gate",
         "--circuit", "reviewer:gate", "--reason", "stale host", "--evidence", "probe:pass",
         "--confidence", "1.0", "--session-id", "session-1", "--by", "gate",
         "--result", "pass", "--root", str(root / ".orgforge" / "ledger"), "--json"],
        cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert stale.returncode == 3
    assert "installed-organ session" in _json(stale)["error"]


def test_status_board_and_hook_enforce_the_same_degraded_semantics(tmp_path):
    root = _org(tmp_path)
    _activate(root)
    _degrade(root)
    status = subprocess.run(
        [sys.executable, str(REPO / "tools" / "status.py"), "status",
         str(root / ".orgforge" / "ledger")], cwd=root,
        env={**os.environ, "ORG_CONSTITUTION": str(root / "constitution.yaml")},
        capture_output=True, text=True, timeout=30)
    assert status.returncode == 0
    assert "AMBER" in status.stdout and "effective: DEGRADED" in status.stdout
    assert "circuit reviewer:gate: OPEN" in status.stdout
    assert "unresolved taint: src/service.py" in status.stdout

    observed = _fire(root, "git status")
    assert observed.returncode == 0, observed.stdout + observed.stderr
    merge = _fire(root, "git merge feature")
    assert merge.returncode == 2
    assert "merge is forbidden" in merge.stdout + merge.stderr
    undeclared = _fire(root, "claude -p review")
    assert undeclared.returncode == 2
    assert "one-shot adaptive declaration" in undeclared.stdout + undeclared.stderr
    declared = _fire(
        root,
        "ORG_ADAPTIVE_ACTION=cross_harness_failover "
        "ORG_ADAPTIVE_ENVELOPE=required-reviewer-outage "
        "ORG_ADAPTIVE_PHASE=test ORG_ADAPTIVE_ARTIFACT=src/service.py claude -p review")
    assert declared.returncode == 0, declared.stdout + declared.stderr
    mislabeled = _fire(
        root,
        "ORG_ADAPTIVE_ACTION=cross_harness_failover "
        "ORG_ADAPTIVE_ENVELOPE=required-reviewer-outage "
        "ORG_ADAPTIVE_PHASE=test ORG_ADAPTIVE_ARTIFACT=src/service.py rm src/service.py")
    assert mislabeled.returncode == 2
    assert "does not match the command shape" in mislabeled.stdout + mislabeled.stderr
    push = _fire(root, "git push origin main")
    assert push.returncode == 2
    assert "ship is forbidden" in push.stdout + push.stderr


def test_hook_recovering_allows_only_observation_and_recovery_commands(tmp_path):
    root = _org(tmp_path)
    _activate(root)
    _degrade(root)
    assert _begin(root).returncode == 0
    observed = _fire(root, "git status")
    assert observed.returncode == 0, observed.stdout + observed.stderr
    mutation = _fire(
        root,
        "ORG_ADAPTIVE_ACTION=cross_harness_failover "
        "ORG_ADAPTIVE_ENVELOPE=required-reviewer-outage "
        "ORG_ADAPTIVE_PHASE=test ORG_ADAPTIVE_ARTIFACT=src/service.py claude -p review")
    assert mutation.returncode == 2
    assert "RECOVERING" in mutation.stdout + mutation.stderr
    recovery = _fire(root, "python3 tools/operational_state.py status --root .orgforge/ledger --json")
    assert recovery.returncode == 0, recovery.stdout + recovery.stderr
