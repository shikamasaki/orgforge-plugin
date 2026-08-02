#!/usr/bin/env python3
"""Export OrgForge evidence through an archived, pinned DR v0alpha2 checkout."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import io
import json
from pathlib import Path, PurePosixPath
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any


class ExportError(ValueError):
    pass


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value}")

    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=reject_duplicate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ExportError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ExportError(f"{label} must be a JSON object")
    return value


def _locked_archive(root: Path, expected: dict[str, Any]) -> bytes:
    if not root.is_dir():
        raise ExportError("DR v0alpha2 root is unavailable")
    commit = expected.get("commit")
    tag_object = expected.get("tagObject")
    if not commit or not tag_object or not expected.get("verifierCodeDigest"):
        raise ExportError("DR lock is incomplete")
    for ref, digest in (("v0alpha2^{}", commit), ("v0alpha2", tag_object)):
        result = subprocess.run(["git", "-C", str(root), "rev-parse", ref], text=True,
                                capture_output=True)
        if result.returncode != 0 or result.stdout.strip() != digest:
            raise ExportError(f"DR lock mismatch for {ref}")
    archive = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", commit],
                             capture_output=True)
    if archive.returncode != 0:
        raise ExportError("unable to archive locked DR commit")
    return archive.stdout


def _extract_archive(raw: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive.getmembers():
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts or not name.parts:
                    raise ExportError("DR archive contains an unsafe path")
                target = (root / Path(*name.parts)).resolve()
                if not target.is_relative_to(root):
                    raise ExportError("DR archive escapes its extraction root")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        raise ExportError("DR archive contains an unreadable file")
                    target.write_bytes(source.read())
                else:
                    raise ExportError("DR archive contains a link or special file")
    except (tarfile.TarError, OSError) as exc:
        raise ExportError("DR archive cannot be safely extracted") from exc


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


def _run_dr_child(*, archive_root: Path, report_path: Path, constitution_path: Path,
                  scenario_path: Path, mapping_path: Path, output: Path) -> None:
    """Run only in a fresh subprocess whose import root is the extracted archive."""
    sys.path.insert(0, str(archive_root))
    modules = {
        "builder": importlib.import_module("game_days.refund.portable_bundle"),
        "data": importlib.import_module("tools.data_loading"),
        "trust": importlib.import_module("tools.trust"),
        "export_verifier": importlib.import_module("tools.export_verifier"),
        "manifest": importlib.import_module("tools.verifier_manifest"),
    }
    for name, module in modules.items():
        module_file = getattr(module, "__file__", None)
        if not module_file or not Path(module_file).resolve().is_relative_to(archive_root.resolve()):
            raise ExportError(f"DR module {name} is outside the archive root")
    mapping = _json(mapping_path.read_bytes(), "mapping")
    lock = mapping.get("delegationResilience", {})
    actual_code_digest = modules["manifest"].verifier_code_digest()
    if actual_code_digest != lock.get("verifierCodeDigest"):
        raise ExportError("DR verifier code digest does not match lock")
    report_raw, constitution_raw, scenario_raw = (
        report_path.read_bytes(), constitution_path.read_bytes(), scenario_path.read_bytes()
    )
    artifacts: dict[str, bytes] = dict(modules["builder"].build_artifacts())
    mapping_raw = modules["data"].canonical_json_bytes(mapping)
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
    seed = base64.b64decode((archive_root / "tests" / "fixtures" / "trust" / "keys" / "bundle-assembler.seed").read_text().strip())
    artifacts["bundle.dsse.json"] = modules["data"].canonical_json_bytes(modules["trust"].create_dsse_envelope(
        statement, payload_type="application/vnd.in-toto+json", key_id=envelope["signatures"][0]["keyid"], private_key=seed
    ))
    output.mkdir(parents=True, exist_ok=False)
    for relative, raw in artifacts.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    modules["export_verifier"].export(output / "standalone-verifier")
    (output / "verifier-code-digest.txt").write_text(actual_code_digest + "\n")
    (output / "verifier-environment-digest.txt").write_text(modules["manifest"].verifier_environment_digest() + "\n")


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
    expected = lock.get("delegationResilience", {})
    archive_raw = _locked_archive(dr_root, expected)
    mapping = {
        "apiVersion": lock["apiVersion"], "kind": "OrgForgeDelegationResilienceMapping",
        "mappingVersion": lock["mappingVersion"], "delegationResilience": expected,
        "sourceArtifacts": [
            {"uri": "orgforge-inputs/exercise-report.json", "digest": _digest(report_raw)},
            {"uri": "orgforge-inputs/constitution.yaml", "digest": _digest(constitution_raw)},
            {"uri": "orgforge-inputs/reviewer-outage.yaml", "digest": _digest(scenario_raw)},
        ],
        "claimMapping": "none: v0alpha2 Transactional Action has no software-delivery claim semantics",
        "capabilityDisposition": "not_demonstrated",
    }
    with tempfile.TemporaryDirectory(prefix="orgforge-dr-") as temp:
        temp_root = Path(temp)
        archive_root = temp_root / "dr"
        _extract_archive(archive_raw, archive_root)
        mapping_path = temp_root / "mapping.json"
        mapping_path.write_text(json.dumps(mapping, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        child_output = temp_root / "packet"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(archive_root)
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "run-dr", "--archive-root", str(archive_root),
             "--exercise-report", str(report_path), "--constitution", str(constitution_path),
             "--scenario", str(scenario_path), "--mapping", str(mapping_path), "--output", str(child_output)],
            cwd=archive_root, env=env, text=True, capture_output=True,
        )
        if result.returncode != 0:
            raise ExportError(result.stderr.strip() or "DR archive subprocess failed")
        shutil.copytree(child_output, output)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("export")
    for name in ("exercise-report", "constitution", "scenario", "lock", "dr-root", "output"):
        command.add_argument(f"--{name}", required=True, type=Path)
    child = sub.add_parser("run-dr")
    for name in ("archive-root", "exercise-report", "constitution", "scenario", "mapping", "output"):
        child.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "run-dr":
            _run_dr_child(archive_root=args.archive_root, report_path=args.exercise_report,
                          constitution_path=args.constitution, scenario_path=args.scenario,
                          mapping_path=args.mapping, output=args.output)
        else:
            export(report_path=args.exercise_report, constitution_path=args.constitution,
                   scenario_path=args.scenario, lock_path=args.lock, dr_root=args.dr_root, output=args.output)
    except (OSError, ExportError, ValueError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
