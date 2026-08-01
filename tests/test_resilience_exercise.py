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
