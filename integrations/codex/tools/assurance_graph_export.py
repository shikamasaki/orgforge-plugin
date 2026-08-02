#!/usr/bin/env python3
"""Export an Assurance Graph through an archived, pinned DR graph-profile checkout.

Separate from tools/delegation_resilience_export.py on purpose: the v0alpha2 packet
adapter, its lock, and its CLI are frozen contract surface. This exporter reads the
same OrgForge evidence, but is pinned by its own lock
(integrations/delegation-resilience/assurance-graph-v0alpha1.lock.json) and never
touches the v0alpha2 packet flow.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


def _v0alpha2_adapter():
    spec = importlib.util.spec_from_file_location(
        "_orgforge_dr_v0alpha2_adapter",
        Path(__file__).resolve().with_name("delegation_resilience_export.py"),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("v0alpha2 adapter module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_V2 = _v0alpha2_adapter()
ExportError = _V2.ExportError
_digest = _V2._digest
_json = _V2._json
_extract_archive = _V2._extract_archive
_validate_inputs = _V2._validate_inputs

LOCK_API_VERSION = "orgforge.delegation-resilience-assurance-graph-lock/v1"
MAPPING_VERSION = "orgforge-assurance-graph/v0alpha1"
GRAPH_API_VERSION = "delegation-resilience.org/assurance-graph/v0alpha1"
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

SOURCE_URIS = {
    "report": "sources/exercise-report.json",
    "constitution": "sources/constitution.yaml",
    "scenario": "sources/reviewer-outage.yaml",
}


def _validate_lock(lock: dict[str, Any]) -> dict[str, Any]:
    if lock.get("apiVersion") != LOCK_API_VERSION:
        raise ExportError("unknown Assurance Graph adapter lock version")
    if lock.get("mappingVersion") != MAPPING_VERSION:
        raise ExportError("unknown Assurance Graph mapping version")
    if lock.get("recoveryCapability") != "NOT_DEMONSTRATED":
        raise ExportError("Assurance Graph lock must record NOT_DEMONSTRATED recovery capability")
    expected = lock.get("delegationResilience")
    if not isinstance(expected, dict):
        raise ExportError("Assurance Graph lock is incomplete")
    for field in ("tag", "tagObject", "commit", "schemaPath", "schemaDigest",
                  "verifierManifestPath", "verifierCodeDigest"):
        if not expected.get(field):
            raise ExportError(f"Assurance Graph lock is missing {field}")
    return expected


def _locked_archive(root: Path, expected: dict[str, Any]) -> bytes:
    if not root.is_dir():
        raise ExportError("DR checkout root is unavailable")
    tag = expected["tag"]
    for ref, digest in ((f"{tag}^{{}}", expected["commit"]), (tag, expected["tagObject"])):
        result = subprocess.run(["git", "-C", str(root), "rev-parse", ref], text=True,
                                capture_output=True)
        if result.returncode != 0 or result.stdout.strip() != digest:
            raise ExportError(f"DR graph lock mismatch for {ref}")
    archive = subprocess.run(["git", "-C", str(root), "archive", "--format=tar",
                              expected["commit"]], capture_output=True)
    if archive.returncode != 0:
        raise ExportError("unable to archive locked DR commit")
    return archive.stdout


def _observed_at(value: str) -> str:
    if not _TIMESTAMP.fullmatch(value):
        raise ExportError("observed-at must be an RFC 3339 UTC timestamp like 2026-08-03T00:00:00Z")
    return value


def _build_graph(*, report_raw: bytes, constitution_raw: bytes, scenario_raw: bytes,
                 observed_at: str) -> dict[str, Any]:
    """Map only what the OrgForge evidence records.

    Nodes and edges read directly from a source artifact are `observed`; every
    relation this adapter itself introduces (the supports/depends_on links to the
    recovery claim, and the claim node) is `derived` so the locked DR verifier
    keeps the claim at NOT_DEMONSTRATED.
    """
    digests = {
        "report": _digest(report_raw),
        "constitution": _digest(constitution_raw),
        "scenario": _digest(scenario_raw),
    }
    src = {name: f"src:orgforge/{name}" for name in SOURCE_URIS}
    source_artifacts = [
        {"id": src[name], "uri": SOURCE_URIS[name], "digest": digests[name],
         "observedAt": observed_at}
        for name in ("report", "constitution", "scenario")
    ]

    def observed(refs: list[str]) -> dict[str, Any]:
        return {"mode": "observed", "sourceRefs": refs, "observedAt": observed_at}

    def derived(refs: list[str]) -> dict[str, Any]:
        return {"mode": "derived", "sourceRefs": refs,
                "method": f"{MAPPING_VERSION} adapter mapping"}

    nodes = [
        {"id": "exercise:orgforge/reviewer-outage-minimal", "type": "exercise",
         "sourceRefs": [src["report"], src["scenario"]], "observedAt": observed_at,
         "assurance": "observed", "provenance": observed([src["report"], src["scenario"]])},
        {"id": "evidence:orgforge/exercise-report", "type": "evidence",
         "sourceRefs": [src["report"]], "artifactDigest": digests["report"],
         "observedAt": observed_at, "assurance": "observed",
         "provenance": observed([src["report"]])},
        {"id": "artifact:orgforge/constitution", "type": "artifact",
         "sourceRefs": [src["constitution"]], "artifactDigest": digests["constitution"],
         "observedAt": observed_at, "assurance": "observed",
         "provenance": observed([src["constitution"]])},
        {"id": "dependency:orgforge/required-reviewer", "type": "dependency",
         "sourceRefs": [src["scenario"]], "observedAt": observed_at,
         "assurance": "observed", "provenance": observed([src["scenario"]])},
        {"id": "dependency:orgforge/review-harness", "type": "dependency",
         "sourceRefs": [src["scenario"]], "observedAt": observed_at,
         "assurance": "observed", "provenance": observed([src["scenario"]])},
        {"id": "claim:orgforge/reviewer-outage-recovery", "type": "claim",
         "sourceRefs": [src["report"], src["scenario"]], "assurance": "derived",
         "provenance": derived([src["report"], src["scenario"]]),
         "attributes": {"status": "NOT_DEMONSTRATED"}},
    ]
    edges = [
        {"id": "edge:orgforge/exercise-observes-report", "type": "observes",
         "from": "exercise:orgforge/reviewer-outage-minimal",
         "to": "evidence:orgforge/exercise-report",
         "sourceRefs": [src["report"]], "observedAt": observed_at,
         "assurance": "observed", "provenance": observed([src["report"]])},
        {"id": "edge:orgforge/exercise-depends-on-reviewer", "type": "depends_on",
         "from": "exercise:orgforge/reviewer-outage-minimal",
         "to": "dependency:orgforge/required-reviewer",
         "sourceRefs": [src["scenario"]], "observedAt": observed_at,
         "assurance": "observed", "provenance": observed([src["scenario"]])},
        {"id": "edge:orgforge/reviewer-shares-fate-with-harness", "type": "shares_fate_with",
         "from": "dependency:orgforge/required-reviewer",
         "to": "dependency:orgforge/review-harness",
         "sourceRefs": [src["scenario"]], "observedAt": observed_at,
         "assurance": "observed", "provenance": observed([src["scenario"]])},
        {"id": "edge:orgforge/report-supports-claim", "type": "supports",
         "from": "evidence:orgforge/exercise-report",
         "to": "claim:orgforge/reviewer-outage-recovery",
         "sourceRefs": [src["report"]], "assurance": "derived",
         "provenance": derived([src["report"]])},
        {"id": "edge:orgforge/constitution-supports-claim", "type": "supports",
         "from": "artifact:orgforge/constitution",
         "to": "claim:orgforge/reviewer-outage-recovery",
         "sourceRefs": [src["constitution"]], "assurance": "derived",
         "provenance": derived([src["constitution"]])},
        {"id": "edge:orgforge/claim-depends-on-reviewer", "type": "depends_on",
         "from": "claim:orgforge/reviewer-outage-recovery",
         "to": "dependency:orgforge/required-reviewer",
         "sourceRefs": [src["scenario"]], "assurance": "derived",
         "provenance": derived([src["scenario"]])},
    ]
    seed = json.dumps([observed_at, *sorted(digests.values())], separators=(",", ":"))
    graph_id = "graph:orgforge/reviewer-outage/" + hashlib.sha256(seed.encode()).hexdigest()[:16]
    return {
        "apiVersion": GRAPH_API_VERSION, "kind": "AssuranceGraph",
        "metadata": {"graphId": graph_id, "createdAt": observed_at,
                     "canonicalization": "RFC8785-JCS"},
        "sourceArtifacts": source_artifacts, "nodes": nodes, "edges": edges,
    }


def _run_graph_child(*, archive_root: Path, graph_path: Path, mapping_path: Path,
                     output: Path) -> None:
    """Run only in a fresh subprocess whose import root is the extracted archive."""
    sys.path.insert(0, str(archive_root))
    modules = {
        "graph": importlib.import_module("tools.assurance_graph"),
        "manifest": importlib.import_module("tools.assurance_graph_manifest"),
        "data": importlib.import_module("tools.data_loading"),
    }
    root = archive_root.resolve()
    for name, module in modules.items():
        module_file = getattr(module, "__file__", None)
        if not module_file or not Path(module_file).resolve().is_relative_to(root):
            raise ExportError(f"DR graph module {name} is outside the archive root")
    mapping = _json(mapping_path.read_bytes(), "graph mapping")
    expected = mapping["delegationResilience"]
    schema_path = (root / expected["schemaPath"]).resolve()
    if not schema_path.is_relative_to(root) or not schema_path.is_file():
        raise ExportError("locked schema path escapes or is missing from the archive")
    if _digest(schema_path.read_bytes()) != expected["schemaDigest"]:
        raise ExportError("DR graph schema digest does not match lock")
    if modules["manifest"].assurance_graph_code_digest() != expected["verifierCodeDigest"]:
        raise ExportError("DR graph verifier code digest does not match lock")

    graph = _json(graph_path.read_bytes(), "assurance graph")
    output.mkdir(parents=True, exist_ok=False)
    for artifact in mapping["sourceArtifacts"]:
        target = output / artifact["uri"]
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = Path(artifact["localPath"]).read_bytes()
        if _digest(raw) != artifact["digest"]:
            raise ExportError(f"source artifact changed during export: {artifact['uri']}")
        target.write_bytes(raw)
    result = modules["graph"].validate_graph(graph, artifact_root=output)
    if result.get("graphVerificationOutcome") != "GRAPH_VERIFIED":
        raise ExportError("locked DR verifier rejected the generated graph: "
                          + "; ".join(result.get("errors", [])))
    for claim in result.get("claimResults", []):
        if claim.get("verifiedSupport") != "NOT_DEMONSTRATED" \
                or claim.get("requestedStatus") != "NOT_DEMONSTRATED":
            raise ExportError("graph export may never request or verify recovery support")

    (output / "graph.json").write_bytes(modules["graph"].canonical_graph_bytes(graph))
    (output / "verification-result.json").write_bytes(modules["data"].canonical_json_bytes(result))
    (output / "orgforge-graph-mapping.json").write_bytes(
        modules["data"].canonical_json_bytes({
            key: value for key, value in mapping.items() if key != "sourceArtifacts"
        } | {"sourceArtifacts": [
            {"uri": item["uri"], "digest": item["digest"]} for item in mapping["sourceArtifacts"]
        ]})
    )
    verifier_root = output / "standalone-verifier"
    for relative in modules["manifest"].GRAPH_VERIFIER_FILES:
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ExportError(f"locked verifier file is missing from the archive: {relative}")
        target = verifier_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    (output / "graph-verifier-code-digest.txt").write_text(expected["verifierCodeDigest"] + "\n")
    (output / "graph-schema-digest.txt").write_text(expected["schemaDigest"] + "\n")


def export(*, report_path: Path, constitution_path: Path, scenario_path: Path,
           lock_path: Path, dr_root: Path, output: Path, observed_at: str) -> None:
    if output.exists():
        raise ExportError("output directory must not already exist")
    observed_at = _observed_at(observed_at)
    report_raw, constitution_raw, scenario_raw, lock_raw = (
        report_path.read_bytes(), constitution_path.read_bytes(),
        scenario_path.read_bytes(), lock_path.read_bytes(),
    )
    report, lock = _json(report_raw, "exercise report"), _json(lock_raw, "adapter lock")
    expected = _validate_lock(lock)
    _validate_inputs(report, scenario_raw, constitution_raw)
    graph = _build_graph(report_raw=report_raw, constitution_raw=constitution_raw,
                         scenario_raw=scenario_raw, observed_at=observed_at)
    archive_raw = _locked_archive(dr_root, expected)
    with tempfile.TemporaryDirectory(prefix="orgforge-graph-") as temp:
        temp_root = Path(temp)
        archive_root = temp_root / "dr"
        _extract_archive(archive_raw, archive_root)
        mapping = {
            "apiVersion": lock["apiVersion"], "kind": "OrgForgeAssuranceGraphMapping",
            "mappingVersion": lock["mappingVersion"], "observedAt": observed_at,
            "delegationResilience": expected,
            "sourceArtifacts": [
                {"uri": SOURCE_URIS["report"], "digest": _digest(report_raw),
                 "localPath": str(report_path.resolve())},
                {"uri": SOURCE_URIS["constitution"], "digest": _digest(constitution_raw),
                 "localPath": str(constitution_path.resolve())},
                {"uri": SOURCE_URIS["scenario"], "digest": _digest(scenario_raw),
                 "localPath": str(scenario_path.resolve())},
            ],
            "claimMapping": "derived-only: the recovery claim and its support edges are "
                            "adapter-derived and are never observed evidence",
            "capabilityDisposition": "not_demonstrated",
        }
        mapping_path = temp_root / "mapping.json"
        mapping_path.write_text(json.dumps(mapping, sort_keys=True, separators=(",", ":")),
                                encoding="utf-8")
        graph_path = temp_root / "graph.json"
        graph_path.write_text(json.dumps(graph, sort_keys=True, separators=(",", ":")),
                              encoding="utf-8")
        child_output = temp_root / "packet"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(archive_root)
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "run-graph",
             "--archive-root", str(archive_root), "--graph", str(graph_path),
             "--mapping", str(mapping_path), "--output", str(child_output)],
            cwd=archive_root, env=env, text=True, capture_output=True,
        )
        if result.returncode != 0:
            raise ExportError(result.stderr.strip() or "DR graph archive subprocess failed")
        shutil.copytree(child_output, output)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("export")
    for name in ("exercise-report", "constitution", "scenario", "lock", "dr-root", "output"):
        command.add_argument(f"--{name}", required=True, type=Path)
    command.add_argument("--observed-at", required=True)
    child = sub.add_parser("run-graph")
    for name in ("archive-root", "graph", "mapping", "output"):
        child.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "run-graph":
            _run_graph_child(archive_root=args.archive_root, graph_path=args.graph,
                             mapping_path=args.mapping, output=args.output)
        else:
            export(report_path=args.exercise_report, constitution_path=args.constitution,
                   scenario_path=args.scenario, lock_path=args.lock, dr_root=args.dr_root,
                   output=args.output, observed_at=args.observed_at)
    except (OSError, ExportError, ValueError, ImportError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
