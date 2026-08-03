import importlib.util
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

import yaml


REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "adaptation.py"
LEDGER = REPO / "tools" / "ledger.py"


def _org(tmp_path):
    root = tmp_path / "org"
    root.mkdir()
    (root / "organization.yaml").write_text("purpose: test\n", encoding="utf-8")
    shutil.copy(REPO / "template" / "constitution.yaml", root / "constitution.yaml")
    shutil.copy(REPO / "template" / "ledger-schema.yaml", root / "ledger-schema.yaml")
    return root


def _run(root, *args):
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"), ORG_ROLE="supervisor")
    return subprocess.run(
        [sys.executable, str(TOOL), *args, "--root", str(root / ".orgforge" / "ledger"), "--json"],
        cwd=root, env=env, capture_output=True, text=True,
    )


def _json(run):
    assert run.stdout, run.stderr
    return json.loads(run.stdout)


def _activate(root):
    return _run(
        root, "activate", "--envelope", "required-reviewer-outage",
        "--trigger", "required_reviewer_unavailable", "--source", "judge_preflight",
        "--baseline-ref", "constitution:review-required",
        "--evidence", "outage_receipt=probe:judge-exit-7",
        "--evidence", "affected_artifact_inventory=file:artifacts.json",
        "--confidence", "0.95",
    )


def test_resilience_contract_doctor_and_lint_reject_invariant_weakening(tmp_path):
    root = _org(tmp_path)
    doctor = _run(root, "doctor")
    assert doctor.returncode == 0, doctor.stderr
    report = _json(doctor)
    assert report["ready"] is True
    assert report["resilience_score"] is None
    assert set(report["evidence_profile"]) == {"Respond", "Monitor", "Learn", "Anticipate"}
    assert all(row["confidence"] == "unknown" for row in report["evidence_profile"].values())
    assert all(item["value"] is None for item in report["outcome_indicators"].values())
    assert report["work_observation_model"]["work_as_recorded"] == ["ledger", "git", "ci", "trace"]
    assert "inferred work-as-done" in report["human_judgment_remains"]
    assert report["human_judgment_remains"]

    spec = importlib.util.spec_from_file_location("org_lint_adaptation", REPO / "tools" / "org_lint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    constitution = yaml.safe_load((root / "constitution.yaml").read_text(encoding="utf-8"))
    constitution["resilience"]["adaptive_envelopes"][0]["preserves_invariants"].remove(
        "no_self_approval")
    lint = module.Lint()
    invariants = {}
    for item in constitution["invariants"]:
        invariants.update(item)
    module.lint_resilience(
        constitution, invariants, constitution["charter"]["items"],
        constitution["irreversible"]["held_actions"], lint)
    assert any("does not preserve every constitutional invariant" in error for error in lint.errs)


def test_reviewer_outage_activation_authorization_and_deviation_are_ledger_backed(tmp_path):
    root = _org(tmp_path)
    activated = _activate(root)
    assert activated.returncode == 0, activated.stderr
    activation = _json(activated)["activation"]
    assert activation["affected_critical_functions"] == ["governed_delivery", "human_control"]
    assert activation["source"] == "judge_preflight"

    allowed = _run(root, "authorize", "--envelope", "required-reviewer-outage",
                   "--action", "cross_harness_failover", "--phase", "test",
                   "--artifact", "src/service.py")
    assert allowed.returncode == 0
    assert _json(allowed)["preserves_invariants"] == [
        "human_decision_line", "production_credential_custody", "no_self_approval",
        "evidence_integrity"]

    deviation = _run(root, "deviate", "--envelope", "required-reviewer-outage",
                     "--action", "cross_harness_failover", "--phase", "test",
                     "--artifact", "src/service.py", "--wai-baseline", "required reviewer: claude",
                     "--reason", "declared reviewer unavailable", "--result", "Codex review requested",
                     "--missing-evidence", "claude_session_trace",
                     "--tainted-artifact", "src/service.py")
    assert deviation.returncode == 0, deviation.stderr
    payload = _json(deviation)["deviation"]
    assert payload["revalidation_scope"] == ["review_decision", "tainted_artifacts", "integration_gate"]

    status = _json(_run(root, "status"))["state"]["activations"][0]
    assert status["status"] == "active"
    assert status["tainted_artifacts"] == ["src/service.py"]
    assert status["missing_evidence"] == ["claude_session_trace"]
    assert len(status["deviations"]) == 1


def test_undeclared_expired_scope_and_forbidden_deviations_fail_closed(tmp_path):
    root = _org(tmp_path)
    assert _activate(root).returncode == 0
    forbidden = _run(root, "authorize", "--envelope", "required-reviewer-outage",
                     "--action", "silent_skip_required_review", "--phase", "test")
    assert forbidden.returncode == 3
    assert "forbidden" in _json(forbidden)["reason"]
    scope = _run(root, "authorize", "--envelope", "required-reviewer-outage",
                 "--action", "cross_harness_failover", "--phase", "deploy")
    assert scope.returncode == 3 and "outside" in _json(scope)["reason"]
    undeclared = _run(root, "authorize", "--envelope", "made-up",
                      "--action", "cross_harness_failover", "--phase", "test")
    assert undeclared.returncode == 3
    expired = _run(root, "authorize", "--envelope", "required-reviewer-outage",
                   "--action", "cross_harness_failover", "--phase", "test",
                   "--now", "2099-01-01T00:00:00Z")
    assert expired.returncode == 3 and "expired" in _json(expired)["reason"]

    expired_safe = _run(root, "authorize", "--envelope", "required-reviewer-outage",
                        "--action", "safe_stop", "--now", "2099-01-01T00:00:00Z")
    assert expired_safe.returncode == 0
    assert _json(expired_safe)["mode"] == "safe-diagnostic"

    diagnosis = _run(root, "authorize", "--action", "observe_only")
    assert diagnosis.returncode == 0
    assert _json(diagnosis)["mode"] == "safe-diagnostic"


def test_generic_ledger_append_cannot_extend_or_retarget_an_envelope(tmp_path):
    root = _org(tmp_path)
    payload = {
        "envelope_id": "required-reviewer-outage", "envelope_version": 1,
        "trigger": "required_reviewer_unavailable", "source": "judge_preflight",
        "activation_id": "adapt-forged", "baseline_ref": "constitution:review-required",
        "evidence": {"outage_receipt": "probe:failed",
                     "affected_artifact_inventory": "file:artifacts.json"},
        "confidence": 0.95, "expires_at": "2099-01-01T00:00:00Z",
        "affected_critical_functions": ["governed_delivery", "human_control"],
    }
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"))
    forged = subprocess.run(
        [sys.executable, str(LEDGER), "append", str(root / ".orgforge" / "ledger"),
         "--actor", "supervisor", "--class", "adaptive_envelope_activated",
         "--payload", json.dumps(payload)], cwd=root, env=env, capture_output=True, text=True)
    assert forged.returncode == 3
    assert "expiry exceeds" in forged.stderr


def test_declared_envelopes_are_proposed_and_provider_outage_can_only_degrade_safely(tmp_path):
    root = _org(tmp_path)
    proposed = {row["envelope_id"]: row for row in _json(_run(root, "status"))["state"]["activations"]}
    assert proposed["required-reviewer-outage"]["status"] == "proposed"
    assert proposed["required-provider-outage"]["status"] == "proposed"
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"))
    view = subprocess.run(
        [sys.executable, str(LEDGER), "view", str(root / ".orgforge" / "ledger"),
         "adaptive_envelope_status"], cwd=root, env=env, capture_output=True, text=True)
    assert view.returncode == 0, view.stderr
    assert {row["status"] for row in json.loads(view.stdout)["activations"]} == {"proposed"}

    activated = _run(
        root, "activate", "--envelope", "required-provider-outage",
        "--trigger", "required_provider_unavailable", "--source", "dependency_preflight",
        "--baseline-ref", "dependency:required-provider",
        "--evidence", "outage_receipt=probe:provider-exit-7",
        "--evidence", "affected_artifact_inventory=file:artifacts.json",
        "--confidence", "0.95",
    )
    assert activated.returncode == 0, activated.stderr
    safe = _run(root, "authorize", "--envelope", "required-provider-outage",
                "--action", "scope_reduction", "--phase", "implement",
                "--artifact", "src/service.py")
    assert safe.returncode == 0
    substitution = _run(root, "authorize", "--envelope", "required-provider-outage",
                        "--action", "unverified_provider_substitution", "--phase", "implement")
    assert substitution.returncode == 3


def test_safe_stop_and_goal_abandonment_are_valid_outcomes_not_automatic_failures(tmp_path):
    root = _org(tmp_path)
    safe = _run(root, "outcome", "--critical-function", "governed_delivery",
                "--outcome", "safe_stop", "--evidence", "ledger:reviewer-outage",
                "--judged-by", "human:ceo", "--judgment-required")
    assert safe.returncode == 0, safe.stderr
    abandon = _run(root, "outcome", "--critical-function", "human_control",
                   "--outcome", "goal_abandonment", "--evidence", "decision:ceo-1",
                   "--judged-by", "human:ceo", "--judgment-required")
    assert abandon.returncode == 0, abandon.stderr
    events = [json.loads(line) for line in
              (root / ".orgforge" / "ledger" / "ledger.jsonl").read_text().splitlines()]
    assert [event["payload"]["outcome"] for event in events] == ["safe_stop", "goal_abandonment"]


def test_permanent_adoption_rejects_claimed_human_without_attestation(tmp_path):
    root = _org(tmp_path)
    activated = _activate(root)
    activation = _json(activated)["activation"]
    reverted = _run(root, "revert", "--envelope", "required-reviewer-outage",
                    "--reason", "reviewer recovered", "--evidence", "probe:healthy")
    assert reverted.returncode == 0, reverted.stderr
    experiment = _run(root, "experiment", "--envelope", "required-reviewer-outage",
                      "--experiment-id", "exp-1", "--hypothesis", "failover preserves review",
                      "--result", "supported", "--evidence", "file:exercise.json",
                      "--judged-by", "human:ceo")
    assert experiment.returncode == 0, experiment.stderr
    events = [json.loads(line) for line in
              (root / ".orgforge" / "ledger" / "ledger.jsonl").read_text().splitlines()]
    exp_seq = events[-1]["seq"]
    payload = json.dumps({"envelope_id": "required-reviewer-outage",
                          "activation_id": activation["activation_id"],
                          "human_decision_ref": "adaptive_practice_revision",
                          "microexperiment_ref": f"ledger:{exp_seq}",
                          "practice_change_ref": "git:change-review-route"})
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"))
    claimed = subprocess.run(
        [sys.executable, str(LEDGER), "append", str(root / ".orgforge" / "ledger"),
         "--actor", "human:ceo", "--class", "adaptive_envelope_adopted", "--payload", payload],
        cwd=root, env=env, capture_output=True, text=True)
    assert claimed.returncode == 3
    assert "attested human-held decision" in claimed.stderr


def test_permanent_adoption_accepts_receipt_bound_to_experiment_and_human_decision(tmp_path):
    root = _org(tmp_path)
    activation = _json(_activate(root))["activation"]
    assert _run(root, "revert", "--envelope", "required-reviewer-outage",
                "--reason", "reviewer recovered", "--evidence", "probe:healthy").returncode == 0
    assert _run(root, "experiment", "--envelope", "required-reviewer-outage",
                "--experiment-id", "exp-adopt", "--hypothesis", "failover preserves review",
                "--result", "supported", "--evidence", "file:exercise.json",
                "--judged-by", "human:ceo").returncode == 0
    events = [json.loads(line) for line in
              (root / ".orgforge" / "ledger" / "ledger.jsonl").read_text().splitlines()]
    experiment_ref = f"ledger:{events[-1]['seq']}"
    trust = root / ".orgforge" / "trust" / "keys.json"
    env = dict(os.environ, ORG_TRUST_STORE=str(trust))
    keygen = subprocess.run(
        [sys.executable, str(REPO / "tools" / "identity.py"), "keygen",
         "--key-id", "human-ceo", "--signer-id", "human:ceo", "--shared-secret",
         "--store", str(trust)], cwd=root, env=env, capture_output=True, text=True)
    assert keygen.returncode == 0, keygen.stderr
    ledger_root = root / ".orgforge" / "ledger"
    org_id = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    ledger_id = hashlib.sha256(str(ledger_root.resolve()).encode()).hexdigest()[:16]
    receipt_path = root / "adoption-receipt.json"
    receipt = subprocess.run(
        [sys.executable, str(REPO / "tools" / "identity.py"), "receipt",
         "--org-id", org_id, "--ledger-id", ledger_id, "--subject", activation["activation_id"],
         "--issue", "51", "--role", "human", "--phase", "adapt", "--lineage", "human-held",
         "--verdict", "adopt", "--event-class", "adaptive_envelope_adopted",
         "--requirements-digest", "adaptive-practice-v1", "--reasoning-sha256", "decision-1",
         "--issued-at", "2026-08-01T00:00:00Z", "--key-id", "human-ceo",
         "--envelope-id", "required-reviewer-outage",
         "--human-decision-ref", "adaptive_practice_revision",
         "--microexperiment-ref", experiment_ref,
         "--practice-change-ref", "git:change-review-route"], cwd=root, env=env,
        capture_output=True, text=True)
    assert receipt.returncode == 0, receipt.stderr
    receipt_path.write_text(receipt.stdout, encoding="utf-8")

    tampered_path = root / "tampered-adoption-receipt.json"
    tampered = json.loads(receipt.stdout)
    tampered["microexperiment_ref"] = "ledger:999999"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    rejected = _run(root, "adopt", "--envelope", "required-reviewer-outage",
                    "--human-decision-ref", "adaptive_practice_revision",
                    "--microexperiment-ref", experiment_ref,
                    "--practice-change-ref", "git:change-review-route",
                    "--receipt", str(tampered_path))
    assert rejected.returncode != 0

    adopted = _run(root, "adopt", "--envelope", "required-reviewer-outage",
                   "--human-decision-ref", "adaptive_practice_revision",
                   "--microexperiment-ref", experiment_ref,
                   "--practice-change-ref", "git:change-review-route",
                   "--receipt", str(receipt_path))
    assert adopted.returncode == 0, adopted.stderr
    status = {row["envelope_id"]: row for row in _json(_run(root, "status"))["state"]["activations"]}
    assert status["required-reviewer-outage"]["status"] == "adopted"


def test_status_board_surfaces_active_envelope_and_forbidden_actions(tmp_path):
    root = _org(tmp_path)
    assert _activate(root).returncode == 0
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"))
    board = subprocess.run(
        [sys.executable, str(REPO / "tools" / "status.py"), "status",
         str(root / ".orgforge" / "ledger")], cwd=root, env=env,
        capture_output=True, text=True)
    assert board.returncode == 0
    assert "adaptive envelopes:" in board.stdout
    assert "required-reviewer-outage: active" in board.stdout
    assert "merge_without_required_review" in board.stdout
