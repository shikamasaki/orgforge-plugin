#!/usr/bin/env python3
"""Validate the two plugin manifests and emit release metadata."""

import argparse
import json
import re
import sys
from pathlib import Path


SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
CODEX_VERSION = re.compile(r"^(?P<base>[^+]+)\+codex\.(?P<cachebuster>[0-9A-Za-z.-]+)$")


class ReleaseConfigError(RuntimeError):
    pass


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseConfigError(f"cannot read valid JSON from {path}: {error}") from error


def inspect(root):
    root = Path(root).resolve()
    claude_path = root / "integrations/claude-code/.claude-plugin/plugin.json"
    codex_path = root / "integrations/codex/.codex-plugin/plugin.json"
    marketplace_path = root / ".claude-plugin/marketplace.json"
    claude = _load(claude_path)
    codex = _load(codex_path)
    marketplace = _load(marketplace_path)

    claude_version = str(claude.get("version") or "")
    if not SEMVER.fullmatch(claude_version):
        raise ReleaseConfigError(
            f"Claude plugin version must be stable semver or semver prerelease: {claude_version!r}"
        )

    codex_version = str(codex.get("version") or "")
    match = CODEX_VERSION.fullmatch(codex_version)
    if not match:
        raise ReleaseConfigError(
            "Codex plugin version must be <semver>+codex.<cachebuster>: "
            f"{codex_version!r}"
        )
    if match.group("base") != claude_version:
        raise ReleaseConfigError(
            "Claude and Codex release versions diverge: "
            f"{claude_version!r} != {match.group('base')!r}"
        )

    entries = marketplace.get("plugins")
    entry = next(
        (item for item in entries or [] if item.get("name") == claude.get("name")),
        None,
    )
    if not entry:
        raise ReleaseConfigError(
            f"Claude marketplace has no entry for plugin {claude.get('name')!r}"
        )
    if entry.get("source") != "./integrations/claude-code":
        raise ReleaseConfigError(
            "Claude marketplace source must be ./integrations/claude-code"
        )

    return {
        "version": claude_version,
        "tag": f"v{claude_version}",
        "claude_name": str(claude["name"]),
        "codex_name": str(codex["name"]),
        "claude_archive": f"orgforge-claude-code-{claude_version}.tar.gz",
        "codex_archive": f"orgforge-codex-{claude_version}.tar.gz",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--format", choices=("json", "github-output"), default="json"
    )
    args = parser.parse_args(argv)
    try:
        result = inspect(args.root)
    except ReleaseConfigError as error:
        print(f"release-check: {error}", file=sys.stderr)
        return 1
    if args.format == "github-output":
        for key, value in result.items():
            print(f"{key}={value}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
