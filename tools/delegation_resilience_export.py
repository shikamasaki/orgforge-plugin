#!/usr/bin/env python3
"""Export OrgForge evidence as a bounded DR v0alpha2 transport packet.

This adapter is deliberately export-only.  It does not interpret a completed OrgForge
exercise as a demonstrated recovery capability: OrgForge inputs are bound as opaque packet
subjects and the fixed reference claim remains ``not_demonstrated``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


class ExportError(ValueError):
    pass


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExportError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ExportError(f"{label} must be a JSON object")
    return value


def _dr_modules(root: Path, lock: dict[str, Any]) -> dict[str, Any]:
    expected = lock.get("delegationResilience", {})
    if not root.is_dir():
        raise ExportError("DR v0alpha2 root is unavailable")
    checks = {"v0alpha2^{}": expected.get("commit"), "v0alpha2": expected.get("tagObject")}
    for ref, digest in checks.items():
        actual = subprocess.run(["git", "-C", str(root), "rev-parse", ref], text=True,
                                capture_output=True).stdout.strip()
        if not digest or actual != digest:
            raise ExportError(f"DR lock mismatch for {ref}")
    sys.path.insert(0, str(root))
    return {
        "builder": importlib.import_module("game_days.refund.portable_bundle"),
        "data": importlib.import_module("tools.data_loading"),
        "trust": importlib.import_module("tools.trust"),
        "export_verifier": importlib.import_module("tools.export_verifier"),
        "manifest": importlib.import_module("tools.verifier_manifest"),
    }


def _validate_inputs(report: dict[str, Any], scenario: bytes, constitution: bytes) -> None:
    if report.get("protocol") != "orgforge.resilience-exercise-report/v1":
        raise ExportError("unknown OrgForge evidence protocol")
    if report.get("scenario") != "reviewer-outage-minimal":
        raise ExportError("unknown OrgForge scenario mapping")
    if report.get("exercise_status") != "GREEN":
        raise ExportError("OrgForge exercise is not a completed deterministic report")
    if report.get("outcome") != {"observed": "safe_stop", "acceptable": True}:
        raise ExportError("OrgForge report has a contradictory or unmapped outcome")
    assertions = report.get("assertions")
    if not isinstance(assertions, dict) or not all(
        assertions.get(name) is True for name in (
            "fault_reached_production_preflight", "recovery_probe_reached_production_preflight"
        )
    ):
        raise ExportError("OrgForge report lacks required boundary observations")
    if not scenario or not constitution:
        raise ExportError("OrgForge mapping inputs are missing")


def export(*, report_path: Path, constitution_path: Path, scenario_path: Path,
           lock_path: Path, dr_root: Path, output: Path) -> None:
    if output.exists():
        raise ExportError("output directory must not already exist")
    report_raw, constitution_raw, scenario_raw, lock_raw = (
        report_path.read_bytes(), constitution_path.read_bytes(), scenario_path.read_bytes(), lock_path.read_bytes()
    )
    report, lock = _json(report_raw, "exercise report"), _json(lock_raw, "adapter lock")
    if lock.get("apiVersion") != "orgforge.delegation-resilience-adapter/v1":
        raise ExportError("unknown adapter lock version")
    _validate_inputs(report, scenario_raw, constitution_raw)
    modules = _dr_modules(dr_root, lock)
    builder, data, trust = modules["builder"], modules["data"], modules["trust"]
    artifacts: dict[str, bytes] = dict(builder.build_artifacts())
    mapping = {
        "apiVersion": lock["apiVersion"], "kind": "OrgForgeDelegationResilienceMapping",
        "mappingVersion": lock["mappingVersion"], "delegationResilience": lock["delegationResilience"],
        "sourceArtifacts": [
            {"uri": "orgforge-inputs/exercise-report.json", "digest": _digest(report_raw)},
            {"uri": "orgforge-inputs/constitution.yaml", "digest": _digest(constitution_raw)},
            {"uri": "orgforge-inputs/reviewer-outage.yaml", "digest": _digest(scenario_raw)},
        ],
        "claimMapping": "none: v0alpha2 Transactional Action has no software-delivery claim semantics",
        "capabilityDisposition": "not_demonstrated",
    }
    mapping_raw = data.canonical_json_bytes(mapping)
    artifacts.update({
        "orgforge-mapping.json": mapping_raw,
        "orgforge-inputs/exercise-report.json": report_raw,
        "orgforge-inputs/constitution.yaml": constitution_raw,
        "orgforge-inputs/reviewer-outage.yaml": scenario_raw,
    })
    envelope = _json(artifacts["bundle.dsse.json"], "reference bundle envelope")
    statement = _json(base64.b64decode(envelope["payload"]), "reference bundle statement")
    for uri in ["orgforge-mapping.json", *[item["uri"] for item in mapping["sourceArtifacts"]]]:
        ref = {"uri": uri, "digest": _digest(artifacts[uri])}
        statement["predicate"]["opaqueArtifacts"].append(ref)
        statement["subject"].append({"name": uri, "digest": {"sha256": ref["digest"][7:]}})
    seed = base64.b64decode((dr_root / "tests" / "fixtures" / "trust" / "keys" / "bundle-assembler.seed").read_text().strip())
    artifacts["bundle.dsse.json"] = data.canonical_json_bytes(trust.create_dsse_envelope(
        statement, payload_type="application/vnd.in-toto+json", key_id=envelope["signatures"][0]["keyid"], private_key=seed
    ))
    output.mkdir(parents=True)
    for relative, raw in artifacts.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    modules["export_verifier"].export(output / "standalone-verifier")
    (output / "verifier-code-digest.txt").write_text(modules["manifest"].verifier_code_digest() + "\n")
    (output / "verifier-environment-digest.txt").write_text(modules["manifest"].verifier_environment_digest() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest="command", required=True).add_parser("export")
    for name in ("exercise-report", "constitution", "scenario", "lock", "dr-root", "output"):
        command.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    try:
        export(report_path=args.exercise_report, constitution_path=args.constitution,
               scenario_path=args.scenario, lock_path=args.lock, dr_root=args.dr_root, output=args.output)
    except (OSError, ExportError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
