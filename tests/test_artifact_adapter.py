import hashlib
import json
from pathlib import Path

import pytest

from tools.artifact_adapter import ArtifactImportError, build_envelope, main


def _fixture(tmp_path: Path):
    source = tmp_path / "spec.md"
    source.write_text("# spec\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {
        "source_kind": "spec-kit", "source_version": "d1e86f6",
        "source_run_id": "run-1", "producer": "spec-kit",
        "artifacts": [{"path": "spec.md", "sha256": digest, "stable_id": "REQ-1",
                        "source_phase": "specify", "source_verdict": "ready"}],
    }
    (tmp_path / "artifact-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_deterministic_opaque_envelope(tmp_path):
    root = _fixture(tmp_path)
    assert build_envelope(root, "artifact-manifest.json", "spec-kit") == build_envelope(root, "artifact-manifest.json", "spec-kit")
    result = build_envelope(root, "artifact-manifest.json", "spec-kit")
    assert result["semantic_disposition"] == "opaque_provenance_only"
    assert result["orgforge_decision"] is None
    assert result["dr_claim"] is None


def test_source_digest_mismatch_fails_closed(tmp_path):
    root = _fixture(tmp_path)
    manifest = json.loads((root / "artifact-manifest.json").read_text())
    manifest["artifacts"][0]["sha256"] = "sha256:" + "0" * 64
    (root / "artifact-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ArtifactImportError):
        build_envelope(root, "artifact-manifest.json", "spec-kit")


def test_duplicate_id_and_duplicate_json_key_fail_closed(tmp_path):
    root = _fixture(tmp_path)
    manifest = json.loads((root / "artifact-manifest.json").read_text())
    manifest["artifacts"].append(dict(manifest["artifacts"][0], path="spec.md"))
    (root / "artifact-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ArtifactImportError):
        build_envelope(root, "artifact-manifest.json", "spec-kit")
    (root / "artifact-manifest.json").write_text('{"source_kind":"x","source_kind":"y"}')
    assert main(["import", "--adapter", "bmad", "--root", str(root)]) == 2


def test_outside_path_is_rejected(tmp_path):
    root = _fixture(tmp_path)
    manifest = json.loads((root / "artifact-manifest.json").read_text())
    manifest["artifacts"][0]["path"] = "../secret"
    (root / "artifact-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ArtifactImportError):
        build_envelope(root, "artifact-manifest.json", "bmad")
