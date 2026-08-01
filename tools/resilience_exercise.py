#!/usr/bin/env python3
"""Deterministic resilience exercises over the real OrgForge protocol boundaries.

The fixture owns only the outside world: dependency response, tracker artifact, clock label, and
temporary workspace. Judge preflight, adaptive-envelope authorization, ledger validation, and
status folding are the production implementations. A fault counts only when its receipt proves
that the injected marker reached that boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import yaml

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent
TEMPLATE = BUNDLE / "template"
DEFAULT_SCENARIO = TEMPLATE / "exercises" / "reviewer-outage.yaml"


class ExerciseError(RuntimeError):
    pass


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fake_dependency(args):
    payload = {
        "protocol": "orgforge.exercise.dependency/v1",
        "injection_id": args.injection_id,
        "mode": args.mode,
        "observed_context": {
            "issue": os.environ.get("ORG_PREFLIGHT_ISSUE"),
            "role": os.environ.get("ORG_PREFLIGHT_ROLE"),
            "phase": os.environ.get("ORG_PREFLIGHT_PHASE"),
        },
    }
    print(json.dumps(payload, sort_keys=True))
    return args.exit_code if args.mode == "exit" else 0


def _load_scenario(path):
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    required = {"schema_version", "id", "critical_functions", "acceptable_outcomes", "fault",
                "expected", "blast_radius", "potentials", "human_judgment"}
    missing = sorted(required - set(document))
    if missing:
        raise ExerciseError(f"scenario is missing fields: {', '.join(missing)}")
    if document.get("schema_version") != 1:
        raise ExerciseError("scenario schema_version must be 1")
    radius = document.get("blast_radius") or {}
    bounded = {"faults": 1, "workspace": "temporary_directory", "network": "forbidden",
               "real_repository_mutation": "forbidden", "production_credentials": "forbidden"}
    if radius != bounded:
        raise ExerciseError("scenario blast radius must prohibit network, credentials, and real repo mutation")
    expected = document.get("expected") or {}
    if expected.get("outcome") not in set(document.get("acceptable_outcomes") or []):
        raise ExerciseError("expected outcome is not declared acceptable")
    return document


def _prepare_org(root):
    root.mkdir(parents=True)
    (root / "organization.yaml").write_text("purpose: resilience exercise\n", encoding="utf-8")
    shutil.copy(TEMPLATE / "constitution.yaml", root / "constitution.yaml")
    shutil.copy(TEMPLATE / "ledger-schema.yaml", root / "ledger-schema.yaml")
    maker = root / "maker-evidence.txt"
    maker.write_text("candidate revision: fixture-A\nchecks: green\n", encoding="utf-8")
    tracker = root / "tracker.json"
    tracker.write_text(json.dumps({"issue": "exercise-1", "state": "review_required",
                                   "maker_evidence_sha256": _sha(maker)}, sort_keys=True),
                       encoding="utf-8")
    inventory = root / "affected-artifacts.json"
    inventory.write_text(json.dumps({"artifacts": [str(maker)], "count": 1}, sort_keys=True),
                         encoding="utf-8")
    return maker, tracker, inventory


def _adapt(root, *arguments):
    ledger = root / ".orgforge" / "ledger"
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"), ORG_ROLE="supervisor")
    completed = subprocess.run(
        [sys.executable, str(HERE / "adaptation.py"), *arguments,
         "--root", str(ledger), "--json"], cwd=root, env=env,
        capture_output=True, text=True, timeout=30)
    try:
        body = json.loads(completed.stdout) if completed.stdout else {"error": completed.stderr.strip()}
    except json.JSONDecodeError as exc:
        raise ExerciseError(f"adaptation returned non-JSON output: {completed.stdout!r}") from exc
    return completed.returncode, body


def _operate(root, *arguments):
    ledger = root / ".orgforge" / "ledger"
    env = dict(os.environ, ORG_CONSTITUTION=str(root / "constitution.yaml"),
               ORG_LEDGER_SCHEMA=str(root / "ledger-schema.yaml"), ORG_ROLE="supervisor")
    completed = subprocess.run(
        [sys.executable, str(HERE / "operational_state.py"), *arguments,
         "--root", str(ledger), "--json"], cwd=root, env=env,
        capture_output=True, text=True, timeout=30)
    try:
        body = json.loads(completed.stdout) if completed.stdout else {"error": completed.stderr.strip()}
    except json.JSONDecodeError as exc:
        raise ExerciseError(f"operational state returned non-JSON output: {completed.stdout!r}") from exc
    return completed.returncode, body


def run_reviewer_outage(scenario_path=DEFAULT_SCENARIO):
    scenario = _load_scenario(scenario_path)
    fault = scenario["fault"]
    expected = scenario["expected"]
    with tempfile.TemporaryDirectory(prefix="orgforge-exercise-") as temporary:
        root = Path(temporary) / "org"
        maker, tracker, inventory = _prepare_org(root)

        # This is the same protocol function called by orgcycle.judge before dispatch. The fake is
        # the dependency executable only; timeout/capture/context/decision evidence stay production.
        from orgcycle.preflight import Probe, result_evidence, run_probe
        probe = Probe(
            "exercise-required-reviewer",
            (sys.executable, str(Path(__file__).resolve()), "_fake-dependency",
             "--mode", str(fault["mode"]), "--exit-code", str(fault["exit_code"]),
             "--injection-id", str(fault["injection_id"])),
            2.0,
        )
        measured = run_probe(probe, issue="exercise-1", role=fault["expected_role"],
                             phase=fault["expected_phase"], cwd=root)
        evidence = json.loads(result_evidence(measured))
        try:
            dependency_receipt = json.loads(measured.stdout)
        except json.JSONDecodeError as exc:
            raise ExerciseError("fault did not return its protocol receipt") from exc
        reached = (
            not measured.ok and measured.returncode == fault["exit_code"] and
            dependency_receipt.get("injection_id") == fault["injection_id"] and
            dependency_receipt.get("observed_context", {}).get("role") == fault["expected_role"] and
            dependency_receipt.get("observed_context", {}).get("phase") == fault["expected_phase"]
        )
        if not reached:
            raise ExerciseError("fault injection was a no-op or did not reach judge preflight")
        receipt_path = root / "fault-receipt.json"
        receipt = {
            "protocol": "orgforge.exercise.fault-receipt/v1",
            "boundary": "orgcycle.preflight.run_probe",
            "injection_id": fault["injection_id"],
            "reached": True,
            "measurement": evidence,
            "dependency_receipt": dependency_receipt,
        }
        receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")

        code, activated = _adapt(
            root, "activate", "--envelope", "required-reviewer-outage",
            "--trigger", "required_reviewer_unavailable", "--source", "judge_preflight",
            "--baseline-ref", f"file:{tracker}",
            "--evidence", f"outage_receipt=file:{receipt_path}",
            "--evidence", f"affected_artifact_inventory=file:{inventory}",
            "--confidence", "1.0")
        if code:
            raise ExerciseError(f"production adaptation activation failed: {activated}")
        activation = activated["activation"]

        # The stable installed-organ launcher binds every state mutation to the current host
        # session.  Keep that protection active inside the exercise instead of inventing a second
        # owner that operational_state must (correctly) reject.  Standalone/CI execution has no
        # binding and retains the deterministic fixture identity.
        session_id = (os.environ.get("ORG_ORGAN_SESSION_ID") or
                      "exercise-reviewer-outage-session")
        code, degraded = _operate(
            root, "degrade", "--envelope", "required-reviewer-outage",
            "--circuit", "reviewer:gate", "--dependency", "required-reviewer",
            "--artifact", str(maker),
            "--reason", "fault receipt proves the required reviewer is unavailable",
            "--evidence", f"file:{receipt_path}", "--confidence", "1.0",
            "--session-id", session_id, "--by", "supervisor")
        if code:
            raise ExerciseError(f"production DEGRADED transition failed: {degraded}")
        degraded_state = degraded["state"]

        decisions = {}
        for action in expected["allowed_actions"] + expected["forbidden_actions"]:
            action_code, decision = _operate(
                root, "authorize", "--envelope", "required-reviewer-outage",
                "--action", action, "--phase", "test", "--artifact", str(maker))
            decisions[action] = {"allowed": action_code == 0 and bool(decision.get("allowed")),
                                 "reason": decision.get("reason")}

        code, deviation = _adapt(
            root, "deviate", "--envelope", "required-reviewer-outage",
            "--action", "cross_harness_failover", "--phase", "test",
            "--artifact", str(maker), "--wai-baseline", "required reviewer: primary harness",
            "--reason", "fault receipt proves the declared reviewer is unavailable",
            "--result", "failover authorized but not claimed complete",
            "--missing-evidence", "required_reviewer_response",
            "--tainted-artifact", str(maker))
        if code:
            raise ExerciseError(f"production deviation record failed: {deviation}")
        code, outcome = _adapt(
            root, "outcome", "--critical-function", "governed_delivery",
            "--outcome", expected["outcome"], "--evidence", f"file:{receipt_path}",
            "--judged-by", "exercise:declared-scenario")
        if code:
            raise ExerciseError(f"production safe outcome record failed: {outcome}")

        # The dependency fixture recovers. The production preflight boundary measures it again;
        # recovery does not trust a scenario flag or the first successful process exit alone.
        recovery_injection_id = f"{fault['injection_id']}-recovery"
        recovery_probe = Probe(
            "exercise-required-reviewer-recovery",
            (sys.executable, str(Path(__file__).resolve()), "_fake-dependency",
             "--mode", "noop", "--exit-code", "0",
             "--injection-id", recovery_injection_id),
            2.0,
        )
        recovered_measurement = run_probe(
            recovery_probe, issue="exercise-1", role=fault["expected_role"],
            phase=fault["expected_phase"], cwd=root)
        try:
            recovered_receipt = json.loads(recovered_measurement.stdout)
        except json.JSONDecodeError as exc:
            raise ExerciseError("recovery probe did not return its protocol receipt") from exc
        recovery_reached = (
            recovered_measurement.ok and
            recovered_receipt.get("injection_id") == recovery_injection_id and
            recovered_receipt.get("observed_context", {}).get("role") == fault["expected_role"] and
            recovered_receipt.get("observed_context", {}).get("phase") == fault["expected_phase"]
        )
        if not recovery_reached:
            raise ExerciseError("recovery probe did not reach judge preflight")
        recovery_receipt_path = root / "recovery-receipt.json"
        recovery_receipt_path.write_text(json.dumps({
            "protocol": "orgforge.exercise.recovery-receipt/v1",
            "boundary": "orgcycle.preflight.run_probe",
            "injection_id": recovery_injection_id,
            "reached": recovery_reached,
            "measurement": json.loads(result_evidence(recovered_measurement)),
            "dependency_receipt": recovered_receipt,
        }, sort_keys=True), encoding="utf-8")

        code, recovering = _operate(
            root, "begin-recovery", "--actor", "gate", "--circuit", "reviewer:gate",
            "--reason", "required reviewer is available through the independent failover route",
            "--evidence", f"file:{recovery_receipt_path}", "--confidence", "1.0",
            "--session-id", session_id, "--by", "gate", "--result", "pass")
        if code:
            raise ExerciseError(f"production RECOVERING transition failed: {recovering}")
        code, revalidated = _operate(
            root, "revalidate", "--actor", "gate", "--artifact", str(maker),
            "--check", "review_decision", "--check", "tainted_artifacts",
            "--check", "integration_gate", "--result", "pass",
            "--evidence", f"file:{recovery_receipt_path}",
            "--session-id", session_id, "--by", "gate")
        if code:
            raise ExerciseError(f"production artifact revalidation failed: {revalidated}")
        code, recovered = _operate(
            root, "recover", "--actor", "gate", "--circuit", "reviewer:gate",
            "--reason", "probe and declared taint revalidation completed",
            "--evidence", f"file:{recovery_receipt_path}", "--confidence", "1.0",
            "--session-id", session_id, "--by", "gate")
        if code:
            raise ExerciseError(f"production NORMAL recovery failed: {recovered}")

        code, status = _adapt(root, "status")
        if code:
            raise ExerciseError(f"production adaptation status failed: {status}")
        code, operational = _operate(root, "status")
        if code:
            raise ExerciseError(f"production operational status failed: {operational}")
        operational_state = operational["state"]
        observed_state = operational_state["effective_state"]
        active = next(row for row in status["state"]["activations"]
                      if row["envelope_id"] == "required-reviewer-outage")
        sequence = [row["to_state"] for row in operational_state["transitions"]]

        assertions = {
            "maker_evidence_exists": maker.is_file() and bool(_sha(maker)),
            "fault_reached_production_preflight": reached,
            "fault_was_not_noop": measured.returncode == fault["exit_code"],
            "allowed_actions_match": all(decisions[action]["allowed"]
                                         for action in expected["allowed_actions"]),
            "forbidden_actions_match": all(not decisions[action]["allowed"]
                                           for action in expected["forbidden_actions"]),
            "critical_functions_exposed": active["affected_critical_functions"] ==
                                          scenario["critical_functions"],
            "missingness_recorded": active["missing_evidence"] == expected["missing_evidence"],
            "taint_recorded": active["tainted_artifacts"] == [str(maker)],
            "safe_stop_is_acceptable": outcome["outcome"]["outcome"] in
                                       scenario["acceptable_outcomes"],
            "operational_state_matches": observed_state == expected["operational_state"],
            "degraded_was_explicit": degraded_state["effective_state"] == "DEGRADED",
            "recovery_probe_reached_production_preflight": recovery_reached,
            "recovery_sequence_matches": sequence == expected["transition_sequence"],
            "taint_revalidated_before_normal": not operational_state["unresolved_taints"],
            "circuit_closed": operational_state["circuits"]["reviewer:gate"]["to_state"] == "CLOSED",
            "temporary_envelope_reverted": active["status"] == "reverted",
        }
        gaps = [name for name, passed in assertions.items() if not passed]
        return {
            "scenario": scenario["id"],
            "exercise_status": "GREEN" if not gaps else "RED",
            "assertions": assertions,
            "gaps": gaps,
            "expected_gaps": expected.get("gaps") or [],
            "fault_injection": {"receipt_sha256": _sha(receipt_path), "reached": reached,
                                "boundary": receipt["boundary"], "measurement": evidence},
            "decision_path": {"actions": decisions, "envelope_status": active["status"],
                              "activation_id": activation["activation_id"],
                              "critical_functions": active["affected_critical_functions"],
                              "missing_evidence": active["missing_evidence"],
                              "tainted_artifact_count": len(active["tainted_artifacts"])},
            "operational_state": {"expected": expected["operational_state"],
                                  "observed": observed_state,
                                  "transition_sequence": sequence,
                                  "circuit": operational_state["circuits"]["reviewer:gate"],
                                  "unresolved_taints": operational_state["unresolved_taints"]},
            "recovery": {"receipt_sha256": _sha(recovery_receipt_path),
                         "probe_reached": recovery_reached,
                         "revalidation": revalidated["revalidation"]},
            "outcome": {"observed": outcome["outcome"]["outcome"], "acceptable": True},
            "potentials": scenario["potentials"],
            "human_judgment": scenario["human_judgment"],
            "resilience_score": None,
            "blast_radius": scenario["blast_radius"],
        }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="resilience-exercise")
    sub = parser.add_subparsers(dest="command", required=True)
    fake = sub.add_parser("_fake-dependency")
    fake.add_argument("--mode", choices=("exit", "noop"), required=True)
    fake.add_argument("--exit-code", type=int, required=True)
    fake.add_argument("--injection-id", required=True)
    run = sub.add_parser("reviewer-outage")
    run.add_argument("--scenario", default=str(DEFAULT_SCENARIO))
    run.add_argument("--expect", choices=("RED", "GREEN"))
    run.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "_fake-dependency":
        return _fake_dependency(args)
    try:
        report = run_reviewer_outage(args.scenario)
    except ExerciseError as exc:
        report = {"scenario": "reviewer-outage-minimal", "exercise_status": "INVALID",
                  "error": str(exc), "resilience_score": None}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True,
                     indent=None if args.json else 2))
    if args.expect:
        expected_gaps = report.get("expected_gaps") or []
        matched = report.get("exercise_status") == args.expect
        if args.expect == "RED":
            matched = matched and report.get("gaps") == expected_gaps and bool(expected_gaps)
        elif args.expect == "GREEN":
            matched = matched and not report.get("gaps") and not expected_gaps
        return 0 if matched else 1
    return 0 if report.get("exercise_status") == "GREEN" else 10


if __name__ == "__main__":
    raise SystemExit(main())
