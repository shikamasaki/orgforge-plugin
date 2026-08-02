import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import yaml


REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "resilience_exercise.py"
SCENARIO = REPO / "template" / "exercises" / "reviewer-outage.yaml"
FALSE_GREEN_SCENARIO = REPO / "template" / "exercises" / "false-green-mutation.yaml"
PROVIDER_OUTAGE_SCENARIO = REPO / "template" / "exercises" / "provider-outage.yaml"
HEARTBEAT_SCENARIO = REPO / "template" / "exercises" / "heartbeat-correlation.yaml"


def _run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=REPO,
                          capture_output=True, text=True, timeout=30)


def test_reviewer_outage_deterministically_degrades_revalidates_and_recovers():
    run = _run("reviewer-outage", "--expect", "GREEN", "--json")
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads(run.stdout)
    assert report["exercise_status"] == "GREEN"
    assert report["gaps"] == []
    assert report["gaps"] == report["expected_gaps"]
    assert report["fault_injection"]["reached"] is True
    assert report["fault_injection"]["boundary"] == "orgcycle.preflight.run_probe"
    assert report["assertions"]["fault_was_not_noop"] is True
    assert report["outcome"] == {"observed": "safe_stop", "acceptable": True}
    assert report["resilience_score"] is None
    assert report["human_judgment"]
    assert report["decision_path"]["missing_evidence"] == ["required_reviewer_response"]
    assert report["decision_path"]["tainted_artifact_count"] == 1
    assert report["operational_state"]["observed"] == "NORMAL"
    assert report["operational_state"]["transition_sequence"] == [
        "NORMAL", "DEGRADED", "RECOVERING", "NORMAL"]
    assert report["operational_state"]["circuit"]["to_state"] == "CLOSED"
    assert report["operational_state"]["unresolved_taints"] == []
    assert report["recovery"]["probe_reached"] is True


def test_reviewer_outage_uses_the_installed_organ_session_binding():
    env = dict(os.environ, ORG_ORGAN_SESSION_ID="installed-session-73")
    run = subprocess.run(
        [sys.executable, str(TOOL), "reviewer-outage", "--expect", "GREEN", "--json"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads(run.stdout)
    assert report["exercise_status"] == "GREEN"
    assert report["operational_state"]["observed"] == "NORMAL"


def test_fault_noop_is_invalid_not_green(tmp_path):
    scenario = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    scenario["fault"]["mode"] = "noop"
    path = tmp_path / "noop.yaml"
    path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    run = _run("reviewer-outage", "--scenario", str(path), "--json")
    assert run.returncode == 10
    report = json.loads(run.stdout)
    assert report["exercise_status"] == "INVALID"
    assert "no-op" in report["error"]


def test_expected_red_does_not_hide_an_unexpected_second_gap(tmp_path):
    scenario = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    scenario["expected"]["allowed_actions"].append("undeclared_action")
    path = tmp_path / "extra-gap.yaml"
    path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    run = _run("reviewer-outage", "--scenario", str(path), "--expect", "RED", "--json")
    assert run.returncode == 1
    report = json.loads(run.stdout)
    assert report["exercise_status"] == "RED"
    assert report["gaps"] != report["expected_gaps"]


def test_fixture_maps_steps_to_multiple_potentials_and_has_bounded_runtime():
    scenario = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    assert scenario["time_budget_seconds"] <= 180
    assert any(len(potentials) > 1 for potentials in scenario["potentials"].values())
    assert scenario["blast_radius"] == {
        "faults": 1,
        "workspace": "temporary_directory",
        "network": "forbidden",
        "real_repository_mutation": "forbidden",
        "production_credentials": "forbidden",
    }


def test_exercise_uses_production_preflight_and_adaptation_modules():
    spec = importlib.util.spec_from_file_location("exercise_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = TOOL.read_text(encoding="utf-8")
    assert "from orgcycle.preflight import Probe, result_evidence, run_probe" in source
    assert 'str(HERE / "adaptation.py")' in source
    assert 'str(HERE / "operational_state.py")' in source


def test_false_green_mutation_is_rejected_by_the_production_skeptic_intake():
    run = _run("false-green-mutation", "--expect", "GREEN", "--json")
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads(run.stdout)
    assert report["exercise_status"] == "GREEN"
    assert report["gaps"] == []
    assert report["test"]["green"] is True
    assert report["mutation"]["applied"] is False
    assert report["intake"]["returncode"] == 10
    assert "mutation[0] の適用成立が確認されていない" in report["intake"]["rejection"]
    assert report["outcome"] == {"observed": "safe_stop", "acceptable": True}
    assert report["resilience_score"] is None


def test_false_green_scenario_has_the_same_bounded_blast_radius():
    scenario = yaml.safe_load(FALSE_GREEN_SCENARIO.read_text(encoding="utf-8"))
    assert scenario["time_budget_seconds"] <= 180
    assert scenario["blast_radius"] == {
        "faults": 1,
        "workspace": "temporary_directory",
        "network": "forbidden",
        "real_repository_mutation": "forbidden",
        "production_credentials": "forbidden",
    }
    assert any(len(potentials) > 1 for potentials in scenario["potentials"].values())


def test_provider_outage_contains_work_without_duplicate_claim_or_provider_substitution():
    run = _run("provider-outage", "--expect", "GREEN", "--json")
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads(run.stdout)
    assert report["exercise_status"] == "GREEN"
    assert report["gaps"] == []
    assert report["fault_injection"]["reached"] is True
    assert report["decision_path"]["duplicate_degrade"] is True
    assert report["operational_state"]["observed"] == "DEGRADED"
    assert report["operational_state"]["transition_sequence"] == ["NORMAL", "DEGRADED"]
    assert report["operational_state"]["circuit"]["to_state"] == "OPEN"
    assert report["recovery"]["returncode"] == 3
    assert "human handback" in report["recovery"]["result"]["error"]
    assert report["outcome"] == {"observed": "safe_stop", "acceptable": True}
    assert report["resilience_score"] is None


def test_provider_outage_scenario_has_a_bounded_runtime_and_blast_radius():
    scenario = yaml.safe_load(PROVIDER_OUTAGE_SCENARIO.read_text(encoding="utf-8"))
    assert scenario["time_budget_seconds"] <= 180
    assert scenario["blast_radius"] == {
        "faults": 1,
        "workspace": "temporary_directory",
        "network": "forbidden",
        "real_repository_mutation": "forbidden",
        "production_credentials": "forbidden",
    }
    assert any(len(potentials) > 1 for potentials in scenario["potentials"].values())


def test_provider_outage_noop_fault_is_invalid_not_green(tmp_path):
    scenario = yaml.safe_load(PROVIDER_OUTAGE_SCENARIO.read_text(encoding="utf-8"))
    scenario["fault"]["mode"] = "noop"
    path = tmp_path / "provider-noop.yaml"
    path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    run = _run("provider-outage", "--scenario", str(path), "--json")
    assert run.returncode == 10
    report = json.loads(run.stdout)
    assert report["exercise_status"] == "INVALID"
    assert "no-op" in report["error"]


def test_heartbeat_correlation_keeps_duplicate_and_stale_signals_as_attention():
    run = _run("heartbeat-correlation", "--expect", "GREEN", "--json")
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads(run.stdout)
    assert report["exercise_status"] == "GREEN"
    assert report["gaps"] == []
    assert report["correlation"] == {
        "red_case_exit": 4, "green_case_exit": 4, "observed": "ATTENTION", "healthy_claim": False}
    assert report["outcome"] == {"observed": "observe_only", "acceptable": True}
    assert report["resilience_score"] is None


def test_heartbeat_correlation_scenario_has_bounded_inputs():
    scenario = yaml.safe_load(HEARTBEAT_SCENARIO.read_text(encoding="utf-8"))
    assert scenario["time_budget_seconds"] <= 180
    assert scenario["blast_radius"] == {
        "faults": 0,
        "workspace": "temporary_directory",
        "network": "forbidden",
        "real_repository_mutation": "forbidden",
        "production_credentials": "forbidden",
    }
    assert set(scenario["signals"]["required"]) == {"heartbeat", "pid_liveness", "ledger_probe"}
