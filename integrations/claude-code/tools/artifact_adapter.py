#!/usr/bin/env python3
"""Import Spec Kit/BMAD output as immutable, opaque OrgForge evidence.

The adapter records provenance only.  It never interprets a source verdict as
an OrgForge admission, DR claim, or ownership decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys
from typing import Any


class ArtifactImportError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise ArtifactImportError(f"non-finite JSON constant: {value}")


def _load(path: pathlib.Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text, parse_constant=_reject_constant,
                          object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactImportError(f"invalid manifest: {path}: {exc}") from exc


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ArtifactImportError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _required(obj: dict, keys: tuple[str, ...], where: str) -> None:
    missing = [key for key in keys if not obj.get(key)]
    if missing:
        raise ArtifactImportError(f"{where}: missing {', '.join(missing)}")


def build_envelope(root: pathlib.Path, manifest_name: str, adapter: str) -> dict:
    manifest_path = (root / manifest_name).resolve()
    if not manifest_path.is_file() or root.resolve() not in manifest_path.parents:
        raise ArtifactImportError("manifest must be a file below --root")
    manifest = _load(manifest_path)
    if not isinstance(manifest, dict):
        raise ArtifactImportError("manifest must be an object")
    _required(manifest, ("source_kind", "source_version", "source_run_id", "producer", "artifacts"), "manifest")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list):
        raise ArtifactImportError("manifest.artifacts must be an array")
    entries = []
    seen_ids = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            raise ArtifactImportError(f"artifacts[{index}] must be an object")
        _required(item, ("path", "sha256", "stable_id"), f"artifacts[{index}]")
        stable_id = str(item["stable_id"])
        if stable_id in seen_ids:
            raise ArtifactImportError(f"duplicate stable_id: {stable_id}")
        seen_ids.add(stable_id)
        path = (root / str(item["path"])).resolve()
        if root.resolve() not in path.parents or not path.is_file():
            raise ArtifactImportError(f"artifact path outside root or missing: {item['path']}")
        actual = _digest(path)
        expected = str(item["sha256"])
        if actual != expected:
            raise ArtifactImportError(f"source digest mismatch for {item['path']}")
        entries.append({
            "stable_id": stable_id,
            "source_ref": str(path.relative_to(root.resolve())),
            "artifact_digest": actual,
            "parent_artifact_digests": sorted(str(x) for x in item.get("parent_artifact_digests", [])),
            "source_phase": item.get("source_phase"),
            "source_verdict": item.get("source_verdict"),
        })
    entries.sort(key=lambda x: (x["stable_id"], x["source_ref"]))
    return {
        "api_version": "orgforge.org/artifact-envelope/v1",
        "adapter": adapter,
        "mapping_version": "1",
        "source": {
            "kind": str(manifest["source_kind"]),
            "version": str(manifest["source_version"]),
            "run_id": str(manifest["source_run_id"]),
            "producer": str(manifest["producer"]),
            "manifest_ref": str(manifest_path.relative_to(root.resolve())),
            "manifest_digest": _digest(manifest_path),
        },
        "artifacts": entries,
        "semantic_disposition": "opaque_provenance_only",
        "orgforge_decision": None,
        "dr_claim": None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="artifact_adapter")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--adapter", choices=("spec-kit", "bmad"), required=True)
    imp.add_argument("--root", type=pathlib.Path, required=True)
    imp.add_argument("--manifest", default="artifact-manifest.json")
    args = parser.parse_args(argv)
    try:
        result = build_envelope(args.root, args.manifest, args.adapter)
    except ArtifactImportError as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
