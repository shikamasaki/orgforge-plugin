"""Contract tests for the export-only OrgForge → DR v0alpha2 adapter.

The adapter may read a completed OrgForge exercise, but must never mutate its source state.
It creates a packet that is independently checked by the fixed DR v0alpha2 verifier; passing
that packet check is deliberately not a recovery-capability demonstration.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[1]
EXPORTER = REPO / "tools" / "delegation_resilience_export.py"
LOCK = REPO / "integrations" / "delegation-resilience" / "v0alpha2.lock.json"
DR_ROOT = Path(os.environ.get("DR_V0ALPHA2_ROOT", "/missing/dr-v0alpha2"))
pytestmark = pytest.mark.skipif(
    not DR_ROOT.is_dir(),
    reason="DR_V0ALPHA2_ROOT is required for the cross-repository adapter contract",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    source = tmp_path / "orgforge-evidence"
    source.mkdir()
    report = {
        "protocol": "orgforge.resilience-exercise-report/v1",
        "scenario": "reviewer-outage-minimal",
        "exercise_status": "GREEN",
        "outcome": {"observed": "safe_stop", "acceptable": True},
        "assertions": {
            "fault_reached_production_preflight": True,
            "recovery_probe_reached_production_preflight": True,
        },
        "human_judgment": ["whether safe_stop remains acceptable"],
        "resilience_score": None,
    }
    (source / "exercise-report.json").write_text(
        json.dumps(report, sort_keys=True), encoding="utf-8"
    )
    shutil.copy(REPO / "template" / "constitution.yaml", source / "constitution.yaml")
    shutil.copy(
        REPO / "template" / "exercises" / "reviewer-outage.yaml",
        source / "reviewer-outage.yaml",
    )
    return source, {path.name: _sha256(path) for path in sorted(source.iterdir())}


def _export(source: Path, output: Path, *, lock: Path = LOCK) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(EXPORTER),
            "export",
            "--exercise-report", str(source / "exercise-report.json"),
            "--constitution", str(source / "constitution.yaml"),
            "--scenario", str(source / "reviewer-outage.yaml"),
            "--lock", str(lock),
            "--dr-root", str(DR_ROOT),
            "--output", str(output),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=60,
    )


def _verify(packet: Path) -> bytes:
    verifier = packet / "standalone-verifier" / "tools" / "verify_bundle.py"
    result = subprocess.run(
        [sys.executable, str(verifier), str(packet / "bundle.dsse.json"),
         "--trust-policy", str(packet / "trust-policy.json"),
         "--artifact-root", str(packet), "--as-of", "2026-08-03T00:00:00Z",
         "--min-policy-sequence", "1",
         "--expected-verifier-code-digest", (packet / "verifier-code-digest.txt").read_text().strip(),
         "--expected-verifier-environment-digest", (packet / "verifier-environment-digest.txt").read_text().strip()],
        text=False,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()
    assert b"orgforge" not in verifier.read_bytes().lower()
    return result.stdout


def test_export_contract_is_deterministic_independent_and_non_demonstrative(tmp_path):
    source, before = _source(tmp_path)
    first, second = tmp_path / "first", tmp_path / "second"
    for output in (first, second):
        run = _export(source, output)
        assert run.returncode == 0, run.stderr

    assert before == {path.name: _sha256(path) for path in sorted(source.iterdir())}
    assert (first / "bundle.dsse.json").read_bytes() == (second / "bundle.dsse.json").read_bytes()
    mapping = json.loads((first / "orgforge-mapping.json").read_text())
    assert mapping["mappingVersion"] == "orgforge-reviewer-outage/v0alpha1"
    assert {
        Path(artifact["uri"]).name: artifact["digest"].removeprefix("sha256:")
        for artifact in mapping["sourceArtifacts"]
    } == before
    assert mapping["claimMapping"].startswith("none:")
    assert mapping["capabilityDisposition"] == "not_demonstrated"
    assert _verify(first) == _verify(second)
    result = json.loads(_verify(first))
    assert result["packetVerificationOutcome"] == "PACKET_VERIFIED"
    assert result["decisionBoundary"]["deploymentDisposition"] == "NOT_EVALUATED"
    assert {claim["verifiedSupport"] for claim in result["claimResults"]} <= {"UNKNOWN"}


@pytest.mark.parametrize(
    "mutation",
    [
        ("report", "unknown scenario"),
        ("report", "missing assertion"),
        ("report", "contradictory outcome"),
        ("lock", "wrong commit"),
    ],
)
def test_export_contract_fails_closed_for_unmappable_or_unpinned_input(tmp_path, mutation):
    source, _ = _source(tmp_path)
    lock = tmp_path / "lock.json"
    lock.write_bytes(LOCK.read_bytes())
    if mutation[0] == "report":
        report_path = source / "exercise-report.json"
        report = json.loads(report_path.read_text())
        if mutation[1] == "unknown scenario":
            report["scenario"] = "unknown"
        elif mutation[1] == "contradictory outcome":
            report["outcome"] = {"observed": "verified_delivery", "acceptable": False}
        else:
            report["assertions"].pop("fault_reached_production_preflight")
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    else:
        lock_data = json.loads(lock.read_text())
        lock_data["delegationResilience"]["commit"] = "0" * 40
        lock.write_text(json.dumps(lock_data, sort_keys=True), encoding="utf-8")
    run = _export(source, tmp_path / "output", lock=lock)
    assert run.returncode != 0
    assert not (tmp_path / "output" / "bundle.dsse.json").exists()
