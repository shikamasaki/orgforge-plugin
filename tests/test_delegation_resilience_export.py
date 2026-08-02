"""Contract tests for the export-only OrgForge → DR v0alpha2 adapter.

The adapter may read a completed OrgForge exercise, but must never mutate its source state.
It creates a packet that is independently checked by the fixed DR v0alpha2 verifier; passing
that packet check is deliberately not a recovery-capability demonstration.
"""

from __future__ import annotations

import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest


REPO = Path(__file__).resolve().parents[1]
EXPORTER = REPO / "tools" / "delegation_resilience_export.py"
LOCK = REPO / "integrations" / "delegation-resilience" / "v0alpha2.lock.json"
DR_ROOT = Path(os.environ.get("DR_V0ALPHA2_ROOT", "/missing/dr-v0alpha2"))
_EXPORT_MODULE_SPEC = importlib.util.spec_from_file_location("orgforge_exporter", EXPORTER)
assert _EXPORT_MODULE_SPEC and _EXPORT_MODULE_SPEC.loader
_EXPORT_MODULE = importlib.util.module_from_spec(_EXPORT_MODULE_SPEC)
_EXPORT_MODULE_SPEC.loader.exec_module(_EXPORT_MODULE)
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
        "observed_at": "2026-08-03T00:00:00Z",
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


def _export(source: Path, output: Path, *, lock: Path = LOCK,
            dr_root: Path = DR_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(EXPORTER),
            "export",
            "--exercise-report", str(source / "exercise-report.json"),
            "--constitution", str(source / "constitution.yaml"),
            "--scenario", str(source / "reviewer-outage.yaml"),
            "--lock", str(lock),
            "--dr-root", str(dr_root),
            "--output", str(output),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=60,
    )


def _verify(packet: Path) -> bytes:
    verifier = packet / "standalone-verifier" / "tools" / "verify_bundle.py"
    lock_data = json.loads(LOCK.read_text())
    locked_code_digest = lock_data["delegationResilience"]["verifierCodeDigest"]
    result = subprocess.run(
        [sys.executable, str(verifier), str(packet / "bundle.dsse.json"),
         "--trust-policy", str(packet / "trust-policy.json"),
         "--artifact-root", str(packet), "--as-of", "2026-08-03T00:00:00Z",
         "--min-policy-sequence", "1",
         "--expected-verifier-code-digest", locked_code_digest,
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


def _clone_dr(tmp_path: Path) -> Path:
    clone = tmp_path / "dr-checkout"
    subprocess.run(["git", "clone", "--no-local", str(DR_ROOT), str(clone)],
                   check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(clone), "checkout", "--detach", "67960e093217d6d2512b1d55d5d9afba658198f8"],
                   check=True, capture_output=True, text=True)
    return clone


def _clone_graph_dr(tmp_path: Path) -> Path:
    clone = tmp_path / "dr-graph-checkout"
    subprocess.run(["git", "-C", str(DR_ROOT), "worktree", "add", "--detach", str(clone),
                    "e098ed6f04a4af12e564f102276f15cbc4b9ed2f"],
                   check=True, capture_output=True, text=True)
    return clone


def _assert_locked_archive_output(source: Path, output: Path, tmp_path: Path) -> None:
    clean = tmp_path / "clean"
    run = _export(source, clean)
    assert run.returncode == 0, run.stderr
    assert (output / "bundle.dsse.json").read_bytes() == (clean / "bundle.dsse.json").read_bytes()


def test_export_ignores_wrong_head(tmp_path):
    source, _ = _source(tmp_path)
    clone = _clone_dr(tmp_path)
    parent = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD^"],
                            check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(clone), "checkout", "--detach", parent],
                   check=True, capture_output=True, text=True)
    run = _export(source, tmp_path / "output", dr_root=clone)
    assert run.returncode == 0, run.stderr
    _assert_locked_archive_output(source, tmp_path / "output", tmp_path)


def test_export_ignores_dirty_tracked_checkout(tmp_path):
    source, _ = _source(tmp_path)
    clone = _clone_dr(tmp_path)
    tracked = clone / "tools" / "data_loading.py"
    tracked.write_bytes(tracked.read_bytes() + b"\n# dirty\n")
    run = _export(source, tmp_path / "output", dr_root=clone)
    assert run.returncode == 0, run.stderr
    _assert_locked_archive_output(source, tmp_path / "output", tmp_path)


def test_export_ignores_untracked_module_shadow(tmp_path):
    source, _ = _source(tmp_path)
    clone = _clone_dr(tmp_path)
    (clone / "tools" / "untracked_shadow.py").write_text("# shadow\n", encoding="utf-8")
    run = _export(source, tmp_path / "output", dr_root=clone)
    assert run.returncode == 0, run.stderr
    _assert_locked_archive_output(source, tmp_path / "output", tmp_path)


def test_export_ignores_ignored_module_shadow(tmp_path):
    source, _ = _source(tmp_path)
    clone = _clone_dr(tmp_path)
    (clone / ".git" / "info" / "exclude").write_text("tools/ignored_shadow.py\n", encoding="utf-8")
    (clone / "tools" / "ignored_shadow.py").write_text("# shadow\n", encoding="utf-8")
    run = _export(source, tmp_path / "output", dr_root=clone)
    assert run.returncode == 0, run.stderr
    _assert_locked_archive_output(source, tmp_path / "output", tmp_path)


def test_export_ignores_stale_pycache(tmp_path):
    source, _ = _source(tmp_path)
    clone = _clone_dr(tmp_path)
    cache = clone / "tools" / "__pycache__"
    cache.mkdir()
    (cache / "data_loading.cpython-312.pyc").write_bytes(b"stale shadow bytecode")
    run = _export(source, tmp_path / "output", dr_root=clone)
    assert run.returncode == 0, run.stderr
    _assert_locked_archive_output(source, tmp_path / "output", tmp_path)


@pytest.mark.parametrize("shadow", ["untracked", "ignored", "pycache"])
def test_graph_export_ignores_checkout_shadowing(tmp_path, shadow):
    source, _ = _source(tmp_path)
    baseline = tmp_path / "baseline"
    baseline_run = subprocess.run(
        [sys.executable, str(EXPORTER), "graph", "--exercise-report", str(source / "exercise-report.json"),
         "--constitution", str(source / "constitution.yaml"), "--scenario", str(source / "reviewer-outage.yaml"),
         "--lock", str(LOCK), "--dr-root", str(DR_ROOT), "--output", str(baseline)],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert baseline_run.returncode == 0, baseline_run.stderr
    clone = _clone_graph_dr(tmp_path)
    if shadow == "untracked":
        (clone / "tools" / "assurance_graph.py").with_name("assurance_graph_shadow.py").write_text(
            "raise RuntimeError('shadow')\n", encoding="utf-8")
    elif shadow == "ignored":
        (clone / ".git" / "info" / "exclude").write_text("tools/ignored_graph.py\n", encoding="utf-8")
        (clone / "tools" / "ignored_graph.py").write_text("raise RuntimeError('shadow')\n", encoding="utf-8")
    else:
        cache = clone / "tools" / "__pycache__"
        cache.mkdir()
        (cache / "assurance_graph.cpython-312.pyc").write_bytes(b"stale shadow")
    clean = tmp_path / "clean"
    run = subprocess.run(
        [sys.executable, str(EXPORTER), "graph", "--exercise-report", str(source / "exercise-report.json"),
         "--constitution", str(source / "constitution.yaml"), "--scenario", str(source / "reviewer-outage.yaml"),
         "--lock", str(LOCK), "--dr-root", str(clone), "--output", str(clean)],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    try:
        assert run.returncode == 0, run.stderr
        assert (clean / "assurance-graph.json").is_file()
        assert (clean / "assurance-graph.json").read_bytes() == (baseline / "assurance-graph.json").read_bytes()
    finally:
        subprocess.run(["git", "-C", str(DR_ROOT), "worktree", "remove", "--force", str(clone)],
                       check=False, capture_output=True, text=True)


def test_export_rejects_code_digest_mismatch(tmp_path):
    source, _ = _source(tmp_path)
    lock = tmp_path / "lock.json"
    lock_data = json.loads(LOCK.read_text())
    lock_data["delegationResilience"]["verifierCodeDigest"] = "sha256:" + "0" * 64
    lock.write_text(json.dumps(lock_data, sort_keys=True), encoding="utf-8")
    run = _export(source, tmp_path / "output", lock=lock)
    assert run.returncode != 0


@pytest.mark.parametrize("raw", [b'{"protocol":"a","protocol":"b"}', b'{"protocol":NaN}'])
def test_export_rejects_non_strict_json(tmp_path, raw):
    source, _ = _source(tmp_path)
    (source / "exercise-report.json").write_bytes(raw)
    run = _export(source, tmp_path / "output")
    assert run.returncode != 0


def test_graph_export_fails_closed_until_dr_declares_graph_schema(tmp_path):
    source, _ = _source(tmp_path)
    lock = json.loads(LOCK.read_text())
    lock.pop("assuranceGraph", None)
    (tmp_path / "lock.json").write_text(json.dumps(lock), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(EXPORTER), "graph", "--exercise-report", str(source / "exercise-report.json"),
         "--constitution", str(source / "constitution.yaml"), "--scenario", str(source / "reviewer-outage.yaml"),
         "--lock", str(tmp_path / "lock.json"), "--dr-root", str(DR_ROOT), "--output", str(tmp_path / "graph")],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert run.returncode != 0
    assert "no Assurance Graph schema/verifier contract" in run.stderr
    assert not (tmp_path / "graph").exists()


def test_graph_lock_requires_consumer_held_schema_and_verifier_digest(tmp_path):
    source, _ = _source(tmp_path)
    lock = tmp_path / "lock.json"
    lock_data = json.loads(LOCK.read_text())
    lock_data["assuranceGraph"]["verifierCodeDigest"] = "sha256:" + "0" * 64
    lock.write_text(json.dumps(lock_data, sort_keys=True), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(EXPORTER), "graph", "--exercise-report", str(source / "exercise-report.json"),
         "--constitution", str(source / "constitution.yaml"), "--scenario", str(source / "reviewer-outage.yaml"),
         "--lock", str(lock), "--dr-root", str(DR_ROOT), "--output", str(tmp_path / "graph")],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert run.returncode != 0
    assert "verifier code digest does not match lock" in run.stderr
    assert not (tmp_path / "graph").exists()


def test_graph_export_is_deterministic_and_stays_not_demonstrated(tmp_path):
    source, _ = _source(tmp_path)
    outputs = []
    for name in ("one", "two"):
        output = tmp_path / name
        run = subprocess.run(
            [sys.executable, str(EXPORTER), "graph", "--exercise-report", str(source / "exercise-report.json"),
             "--constitution", str(source / "constitution.yaml"), "--scenario", str(source / "reviewer-outage.yaml"),
             "--lock", str(LOCK), "--dr-root", str(DR_ROOT), "--output", str(output)],
            cwd=REPO, text=True, capture_output=True, timeout=30,
        )
        assert run.returncode == 0, run.stderr
        outputs.append(output)
    assert (outputs[0] / "assurance-graph.json").read_bytes() == (outputs[1] / "assurance-graph.json").read_bytes()
    result = json.loads((outputs[0] / "verification-result.json").read_text())
    assert result["graphVerificationOutcome"] == "GRAPH_VERIFIED"
    assert result["claimResults"] == []
    assert (outputs[0] / "graph-verifier-code-digest.txt").read_text().startswith("sha256:")
    standalone = subprocess.run(
        [sys.executable, str(outputs[0] / "standalone-verifier" / "tools" / "verify_assurance_graph.py"),
         str(outputs[0] / "assurance-graph.json"), "--artifact-root", str(outputs[0])],
        cwd=outputs[0], env={**os.environ, "PYTHONPATH": str(outputs[0] / "standalone-verifier")},
        text=True, capture_output=True, timeout=30,
    )
    assert standalone.returncode == 0, standalone.stderr
    assert json.loads(standalone.stdout) == result


@pytest.mark.parametrize("mutation", ["duplicate_node", "duplicate_edge", "dangling", "source_digest"])
def test_graph_verifier_rejects_structural_and_source_mutations(tmp_path, mutation):
    source, _ = _source(tmp_path)
    output = tmp_path / "graph"
    run = subprocess.run(
        [sys.executable, str(EXPORTER), "graph", "--exercise-report", str(source / "exercise-report.json"),
         "--constitution", str(source / "constitution.yaml"), "--scenario", str(source / "reviewer-outage.yaml"),
         "--lock", str(LOCK), "--dr-root", str(DR_ROOT), "--output", str(output)],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert run.returncode == 0, run.stderr
    graph_path = output / "assurance-graph.json"
    graph = json.loads(graph_path.read_text())
    if mutation == "duplicate_node":
        graph["nodes"].append(dict(graph["nodes"][0]))
    elif mutation == "duplicate_edge":
        graph["edges"].append(dict(graph["edges"][0]))
    elif mutation == "dangling":
        graph["edges"][0]["to"] = "artifact:missing"
    else:
        source_file = output / "orgforge-inputs" / "exercise-report.json"
        source_file.write_bytes(source_file.read_bytes() + b"\n")
    graph_path.write_text(json.dumps(graph, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    verifier = subprocess.run(
        [sys.executable, str(output / "standalone-verifier" / "tools" / "verify_assurance_graph.py"),
         str(graph_path), "--artifact-root", str(output)],
        cwd=output, env={**os.environ, "PYTHONPATH": str(output / "standalone-verifier")},
        text=True, capture_output=True, timeout=30,
    )
    assert verifier.returncode != 0
    result = json.loads(verifier.stdout)
    assert result["graphVerificationOutcome"] == "GRAPH_REJECTED"
    assert result["errors"]


def test_graph_digest_changes_after_graph_mutation(tmp_path):
    source, _ = _source(tmp_path)
    output = tmp_path / "graph"
    run = subprocess.run(
        [sys.executable, str(EXPORTER), "graph", "--exercise-report", str(source / "exercise-report.json"),
         "--constitution", str(source / "constitution.yaml"), "--scenario", str(source / "reviewer-outage.yaml"),
         "--lock", str(LOCK), "--dr-root", str(DR_ROOT), "--output", str(output)],
        cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert run.returncode == 0, run.stderr
    original = json.loads((output / "verification-result.json").read_text())
    graph_path = output / "assurance-graph.json"
    graph = json.loads(graph_path.read_text())
    graph["metadata"]["graphId"] += "-mutated"
    graph_path.write_text(json.dumps(graph, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    verifier = subprocess.run(
        [sys.executable, str(output / "standalone-verifier" / "tools" / "verify_assurance_graph.py"),
         str(graph_path), "--artifact-root", str(output)],
        cwd=output, env={**os.environ, "PYTHONPATH": str(output / "standalone-verifier")},
        text=True, capture_output=True, timeout=30,
    )
    mutated = json.loads(verifier.stdout)
    assert mutated["graphDigest"] != original["graphDigest"]


def test_archive_extraction_rejects_path_traversal(tmp_path):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        member = tarfile.TarInfo("../escape.txt")
        member.size = 4
        archive.addfile(member, io.BytesIO(b"boom"))
    with pytest.raises(ValueError):
        _EXPORT_MODULE._extract_archive(raw.getvalue(), tmp_path / "archive")
