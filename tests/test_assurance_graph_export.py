"""Contract tests for the export-only OrgForge → DR Assurance Graph adapter.

Expected values come from the committed consumer lock and from the DR repository at the
locked commit — never from the generated packet itself. A verified graph is deliberately
not a recovery-capability demonstration: every claim stays NOT_DEMONSTRATED.
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
EXPORTER = REPO / "tools" / "assurance_graph_export.py"
LOCK = REPO / "integrations" / "delegation-resilience" / "assurance-graph-v0alpha1.lock.json"
DR_ROOT = Path(os.environ.get("DR_ASSURANCE_GRAPH_ROOT")
               or os.environ.get("DR_V0ALPHA2_ROOT", "/missing/dr"))
OBSERVED_AT = "2026-08-02T00:00:00Z"
pytestmark = pytest.mark.skipif(
    not DR_ROOT.is_dir(),
    reason="DR_V0ALPHA2_ROOT (or DR_ASSURANCE_GRAPH_ROOT) is required for the "
           "cross-repository adapter contract",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _locked(lock: Path = LOCK) -> dict:
    return json.loads(lock.read_text())["delegationResilience"]


def _git_show(path: str, *, dr_root: Path = DR_ROOT) -> bytes:
    return subprocess.run(
        ["git", "--no-replace-objects", "-C", str(dr_root), "show",
         f"{_locked()['commit']}:{path}"],
        check=True, capture_output=True, timeout=60,
    ).stdout


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


def _export(source: Path, output: Path, *, lock: Path = LOCK, dr_root: Path = DR_ROOT,
            observed_at: str = OBSERVED_AT) -> subprocess.CompletedProcess[str]:
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
            "--observed-at", observed_at,
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=120,
    )


def _verify(packet: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(packet / "standalone-verifier" / "tools" / "verify_assurance_graph.py"),
         str(packet / "graph.json"), "--artifact-root", str(packet)],
        capture_output=True,
        timeout=60,
    )


def test_export_is_deterministic_source_preserving_and_non_demonstrative(tmp_path):
    source, before = _source(tmp_path)
    first, second = tmp_path / "first", tmp_path / "second"
    for output in (first, second):
        run = _export(source, output)
        assert run.returncode == 0, run.stderr

    assert before == {path.name: _sha256(path) for path in sorted(source.iterdir())}
    for name in ("graph.json", "verification-result.json", "orgforge-graph-mapping.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()

    graph = json.loads((first / "graph.json").read_text())
    assert graph["apiVersion"] == "delegation-resilience.org/assurance-graph/v0alpha1"
    assert {
        Path(item["uri"]).name: item["digest"].removeprefix("sha256:")
        for item in graph["sourceArtifacts"]
    } == before
    claims = [node for node in graph["nodes"] if node["type"] == "claim"]
    assert all(node["assurance"] == "derived" for node in claims)
    assert all(node["attributes"]["status"] == "NOT_DEMONSTRATED" for node in claims)
    claim_ids = {node["id"] for node in claims}
    for edge in graph["edges"]:
        if edge["to"] in claim_ids:
            assert edge["assurance"] == "derived", edge["id"]
            assert edge["provenance"]["mode"] == "derived", edge["id"]

    mapping = json.loads((first / "orgforge-graph-mapping.json").read_text())
    assert mapping["mappingVersion"] == "orgforge-assurance-graph/v0alpha1"
    assert mapping["capabilityDisposition"] == "not_demonstrated"
    assert mapping["claimMapping"].startswith("derived-only:")

    verify_first, verify_second = _verify(first), _verify(second)
    assert verify_first.returncode == 0, verify_first.stderr.decode()
    assert verify_first.stdout == verify_second.stdout
    result = json.loads(verify_first.stdout)
    assert result["graphVerificationOutcome"] == "GRAPH_VERIFIED"
    assert result == json.loads((first / "verification-result.json").read_text())
    assert result["claimResults"], "the recovery claim must appear in the verifier result"
    for claim in result["claimResults"]:
        assert claim["verifiedSupport"] == "NOT_DEMONSTRATED"
        assert claim["requestedStatus"] == "NOT_DEMONSTRATED"
        assert "support contains inferred or derived relations" in claim["reasons"]


def test_consumer_lock_matches_dr_release_lock_at_locked_commit():
    ours = _locked()
    for ref, expected in ((f"{ours['tag']}^{{}}", ours["commit"]),
                          (ours["tag"], ours["tagObject"])):
        actual = subprocess.run(["git", "--no-replace-objects", "-C", str(DR_ROOT),
                                 "rev-parse", ref],
                                check=True, capture_output=True, text=True,
                                timeout=60).stdout.strip()
        assert actual == expected, ref
    theirs = json.loads(_git_show("profiles/assurance-graph/v0alpha1.lock.json"))
    assert theirs["releaseTag"] == ours["tag"]
    assert theirs["schemaDigest"] == ours["schemaDigest"]
    assert theirs["verifierCodeDigest"] == ours["verifierCodeDigest"]
    assert theirs["schemaPath"] == ours["schemaPath"]
    assert theirs["verifierManifestPath"] == ours["verifierManifestPath"]
    schema_raw = _git_show(ours["schemaPath"])
    assert "sha256:" + hashlib.sha256(schema_raw).hexdigest() == ours["schemaDigest"]


def test_standalone_verifier_is_the_locked_dr_code(tmp_path):
    source, _ = _source(tmp_path)
    output = tmp_path / "packet"
    run = _export(source, output)
    assert run.returncode == 0, run.stderr
    verifier_root = output / "standalone-verifier"
    copied = sorted(path for path in verifier_root.rglob("*") if path.is_file())
    assert copied, "standalone verifier must be exported"
    for path in copied:
        relative = path.relative_to(verifier_root).as_posix()
        assert path.read_bytes() == _git_show(relative), relative
        if path.suffix == ".py":
            assert b"orgforge" not in path.read_bytes().lower(), relative
    assert (output / "graph-verifier-code-digest.txt").read_text().strip() \
        == _locked()["verifierCodeDigest"]
    assert (output / "graph-schema-digest.txt").read_text().strip() \
        == _locked()["schemaDigest"]


@pytest.mark.parametrize(
    "mutation",
    [
        ("report", "unknown scenario"),
        ("report", "missing assertion"),
        ("report", "contradictory outcome"),
        ("lock", "wrong commit"),
        ("lock", "wrong schema digest"),
        ("lock", "wrong verifier code digest"),
        ("lock", "wrong manifest path"),
        ("lock", "capability claimed"),
        ("observed-at", "not a UTC timestamp"),
    ],
)
def test_export_fails_closed_without_partial_output(tmp_path, mutation):
    source, _ = _source(tmp_path)
    lock = tmp_path / "lock.json"
    lock.write_bytes(LOCK.read_bytes())
    observed_at = OBSERVED_AT
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
    elif mutation[0] == "lock":
        lock_data = json.loads(lock.read_text())
        if mutation[1] == "wrong commit":
            lock_data["delegationResilience"]["commit"] = "0" * 40
        elif mutation[1] == "wrong schema digest":
            lock_data["delegationResilience"]["schemaDigest"] = "sha256:" + "0" * 64
        elif mutation[1] == "wrong verifier code digest":
            lock_data["delegationResilience"]["verifierCodeDigest"] = "sha256:" + "0" * 64
        elif mutation[1] == "wrong manifest path":
            lock_data["delegationResilience"]["verifierManifestPath"] = "tools/nonexistent.py"
        else:
            lock_data["recoveryCapability"] = "DEMONSTRATED"
        lock.write_text(json.dumps(lock_data, sort_keys=True), encoding="utf-8")
    else:
        observed_at = "yesterday"
    run = _export(source, tmp_path / "output", lock=lock, observed_at=observed_at)
    assert run.returncode != 0
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("raw", [b'{"protocol":"a","protocol":"b"}', b'{"protocol":NaN}'])
def test_export_rejects_non_strict_json(tmp_path, raw):
    source, _ = _source(tmp_path)
    (source / "exercise-report.json").write_bytes(raw)
    run = _export(source, tmp_path / "output")
    assert run.returncode != 0
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("tamper", ["source", "graph"])
def test_tampered_packet_fails_standalone_verification(tmp_path, tamper):
    source, _ = _source(tmp_path)
    output = tmp_path / "packet"
    run = _export(source, output)
    assert run.returncode == 0, run.stderr
    if tamper == "source":
        report = output / "sources" / "exercise-report.json"
        report.write_bytes(report.read_bytes() + b"\n")
    else:
        graph = json.loads((output / "graph.json").read_text())
        graph["edges"][0]["to"] = "claim:missing"
        (output / "graph.json").write_text(json.dumps(graph, sort_keys=True))
    verify = _verify(output)
    assert verify.returncode != 0
    result = json.loads(verify.stdout)
    assert result["graphVerificationOutcome"] == "GRAPH_REJECTED"


def test_export_ignores_wrong_head_and_dirty_checkout(tmp_path):
    source, _ = _source(tmp_path)
    clone = tmp_path / "dr-checkout"
    subprocess.run(["git", "clone", "--no-local", str(DR_ROOT), str(clone)],
                   check=True, capture_output=True, text=True, timeout=120)
    parent = subprocess.run(["git", "-C", str(clone), "rev-parse", f"{_locked()['commit']}^"],
                            check=True, capture_output=True, text=True,
                            timeout=60).stdout.strip()
    subprocess.run(["git", "-C", str(clone), "checkout", "--detach", parent],
                   check=True, capture_output=True, text=True, timeout=60)
    tracked = clone / "tools" / "data_loading.py"
    tracked.write_bytes(tracked.read_bytes() + b"\n# dirty\n")
    (clone / "tools" / "untracked_shadow.py").write_text("# shadow\n", encoding="utf-8")
    run = _export(source, tmp_path / "output", dr_root=clone)
    assert run.returncode == 0, run.stderr
    clean = tmp_path / "clean"
    assert _export(source, clean).returncode == 0
    for name in ("graph.json", "verification-result.json"):
        assert (tmp_path / "output" / name).read_bytes() == (clean / name).read_bytes()


def test_export_ignores_replace_refs(tmp_path):
    """A repo-local `git replace` ref must not swap the archived locked content."""
    source, _ = _source(tmp_path)
    clone = tmp_path / "dr-checkout"
    subprocess.run(["git", "clone", "--no-local", str(DR_ROOT), str(clone)],
                   check=True, capture_output=True, text=True, timeout=120)
    locked = _locked()["commit"]
    empty_tree = subprocess.run(["git", "-C", str(clone), "hash-object", "-t", "tree",
                                 os.devnull], check=True, capture_output=True, text=True,
                                timeout=60).stdout.strip()
    poison = subprocess.run(["git", "-C", str(clone), "commit-tree", empty_tree,
                             "-m", "poison"],
                            check=True, capture_output=True, text=True,
                            env={**os.environ,
                                 "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                 "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
                                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                                 "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"},
                            timeout=60).stdout.strip()
    subprocess.run(["git", "-C", str(clone), "replace", "-f", locked, poison],
                   check=True, capture_output=True, text=True, timeout=60)
    run = _export(source, tmp_path / "output", dr_root=clone)
    assert run.returncode == 0, run.stderr
    clean = tmp_path / "clean"
    assert _export(source, clean).returncode == 0
    for name in ("graph.json", "verification-result.json"):
        assert (tmp_path / "output" / name).read_bytes() == (clean / name).read_bytes()
