#!/usr/bin/env python3
"""Compare reviewer shared-fate evidence as an axis-by-axis vector.

This tool does not infer independence from actor names or harness labels.  Each axis is compared
against an explicit task policy; missing values remain UNKNOWN and therefore cannot become
``different`` by default.  It is intentionally a pure projection over two JSON evidence records
and a JSON policy, so it can be used by a future joint-admission writer without changing the
ledger format in this first step.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


AXES = (
    "harness", "model", "provider", "prompt_lineage", "context_digest", "baseline",
    "workspace", "toolchain", "judge_identity", "test_oracle",
)
STATUSES = {"different", "shared", "matched", "unknown", "not_applicable"}


class SharedFateError(ValueError):
    pass


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SharedFateError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise SharedFateError(f"{label} must be a JSON object")
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _value(record: dict[str, Any], axis: str) -> Any:
    values = record.get("shared_fate", record)
    return values.get(axis) if isinstance(values, dict) else None


def compare(left: dict[str, Any], right: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise SharedFateError("policy must be an object")
    must_differ = set(policy.get("must_differ", []))
    may_share = set(policy.get("may_share", []))
    must_match = set(policy.get("must_match", []))
    unknown_policy = policy.get("unknown_policy", "needs-human")
    if unknown_policy not in {"fail", "needs-human", "degraded"}:
        raise SharedFateError("unknown_policy must be fail, needs-human, or degraded")
    declared = must_differ | may_share | must_match
    unknown_axes = declared - set(AXES)
    if unknown_axes:
        raise SharedFateError(f"unknown shared-fate axis: {sorted(unknown_axes)}")
    if (must_differ & must_match) or (must_differ & may_share) or (must_match & may_share):
        raise SharedFateError("shared-fate policy axes overlap")

    vector: dict[str, dict[str, Any]] = {}
    blocking: list[str] = []
    for axis in sorted(declared):
        left_value, right_value = _value(left, axis), _value(right, axis)
        if left_value is None or right_value is None:
            status = "unknown"
        elif axis in must_differ:
            status = "different" if left_value != right_value else "shared"
        elif axis in must_match:
            status = "matched" if left_value == right_value else "different"
        else:
            status = "shared" if left_value == right_value else "different"
        vector[axis] = {"status": status, "left_present": left_value is not None,
                        "right_present": right_value is not None}
        if axis in must_differ and status != "different":
            blocking.append(axis)
        if axis in must_match and status != "matched":
            blocking.append(axis)
        if status == "unknown" and axis in declared:
            blocking.append(axis)

    independent = not blocking
    disposition = "independent" if independent else unknown_policy
    return {"independent": independent, "disposition": disposition, "unknown_policy": unknown_policy,
            "vector": vector, "blocking_axes": sorted(set(blocking)),
            "must_differ": sorted(must_differ), "may_share": sorted(may_share),
            "must_match": sorted(must_match), "assurance": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shared-fate")
    command = parser.add_subparsers(dest="command", required=True).add_parser("compare")
    command.add_argument("--left", required=True, type=Path)
    command.add_argument("--right", required=True, type=Path)
    command.add_argument("--policy", required=True, type=Path)
    command.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = compare(_load(args.left, "left evidence"), _load(args.right, "right evidence"),
                         _load(args.policy, "shared-fate policy"))
    except SharedFateError as exc:
        print(json.dumps({"error": str(exc), "status": "INVALID"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":") if args.json else None))
    return 0 if result["independent"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
