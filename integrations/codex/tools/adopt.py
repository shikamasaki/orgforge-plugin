#!/usr/bin/env python3
"""Prepare and diagnose orgforge adoption without replacing the host runtime.

This tool owns only deterministic local setup. The host agent still reads the repository and drafts
its organization, architecture, and remaining-work manifest.

    adopt.py inspect [ROOT] [--json]
    adopt.py prepare [ROOT] [--language ja|en] [--json]
    adopt.py doctor  [ROOT] [--json]

`prepare` is idempotent and never overwrites an existing org file. It performs no network access,
creates no branch or Issue, installs no daemon, and requires no sudo.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path


STATE_DIRS = (
    ".orgforge/ledger",
    ".orgforge/doctrine",
    ".orgforge/conventions",
)
SPEC_FILES = (
    "constitution.yaml",
    "sensors.yaml",
    "schedule.yaml",
    "moves.yaml",
    "ledger-schema.yaml",
    "role-settings.yaml",
)
DESIGN_FILES = (
    "organization.yaml",
    "ARCHITECTURE.md",
    "coverage-manifest.md",
)
PLUGIN_MARKERS = (
    ".claude-plugin/marketplace.json",
    "integrations/claude-code/commands",
)
IGNORED_DIRS = {
    ".git",
    ".orgforge",
    ".venv",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "__pycache__",
}


class AdoptionError(RuntimeError):
    pass


def _run(root, *args):
    try:
        return subprocess.run(
            args,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git(root, *args):
    result = _run(root, "git", *args)
    if result is None or result.returncode != 0:
        return None
    return (result.stdout or "").strip()


def _root(value):
    root = Path(value or ".").expanduser().resolve()
    if not root.is_dir():
        raise AdoptionError(f"adoption root is not a directory: {root}")
    return root


def _template_root():
    root = Path(__file__).resolve().parent.parent / "template"
    if not root.is_dir():
        raise AdoptionError(f"orgforge templates are missing: {root}")
    return root


def _is_plugin_repo(root):
    return any((root / marker).exists() for marker in PLUGIN_MARKERS)


def _tracked_files(root):
    output = _git(root, "ls-files")
    if output is not None:
        return [line for line in output.splitlines() if line]
    files = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in IGNORED_DIRS for part in relative.parts):
            continue
        files.append(str(relative))
    return sorted(files)


def _has_non_whitespace_text(path):
    if not path.is_file():
        return False
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except (OSError, UnicodeError):
        return False


def _legacy_runtime_tier(path):
    """Return an obsolete org-wide A/B tier declared under ``defaults``, if any."""
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None

    in_defaults = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_defaults = stripped == "defaults:"
            continue
        if in_defaults:
            match = re.match(r"^\s+tier:\s*([AB])(?:\s*(?:#.*)?)?$", line)
            if match:
                return match.group(1)
    return None


def _language_counts(files):
    counts = Counter()
    for name in files:
        suffix = Path(name).suffix.lower()
        if suffix:
            counts[suffix] += 1
    return [
        {"extension": extension, "files": count}
        for extension, count in counts.most_common(8)
    ]


def inspect(root):
    files = _tracked_files(root)
    remote = _git(root, "remote", "get-url", "origin")
    commit_count = _git(root, "rev-list", "--count", "HEAD")
    manifests = [
        name
        for name in (
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            "go.mod",
            "Cargo.toml",
            "Gemfile",
            "pom.xml",
            "build.gradle",
        )
        if (root / name).is_file()
    ]
    tests = [
        name
        for name in files
        if name.startswith(("test/", "tests/", "spec/"))
        or Path(name).name.startswith(("test_", "spec_"))
        or ".test." in name
        or ".spec." in name
    ]
    return {
        "root": str(root),
        "plugin_repo": _is_plugin_repo(root),
        "existing_org": (root / ".orgforge").is_dir() or (root / "organization.yaml").is_file(),
        "remote": remote,
        "commits": int(commit_count) if commit_count and commit_count.isdigit() else 0,
        "tracked_files": len(files),
        "languages": _language_counts(files),
        "manifests": manifests,
        "test_files": len(tests),
    }


def _set_output_language(path, language):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("output_language:"):
            lines[index] = f"output_language: {language}"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise AdoptionError(f"output_language is missing from template: {path}")


def prepare(root, language):
    if _is_plugin_repo(root):
        raise AdoptionError(
            "refusing to adopt the orgforge plugin development repository; "
            "run this in the product repository you want to govern"
        )

    templates = _template_root()
    created = []
    kept = []

    for relative in STATE_DIRS:
        path = root / relative
        if path.is_dir():
            kept.append(relative)
        else:
            path.mkdir(parents=True, exist_ok=True)
            created.append(relative)

    for name in SPEC_FILES:
        destination = root / name
        if destination.exists():
            kept.append(name)
            continue
        source = templates / name
        if not source.is_file():
            raise AdoptionError(f"required template is missing: {source}")
        shutil.copy2(source, destination)
        if name == "constitution.yaml":
            _set_output_language(destination, language)
        created.append(name)

    organization = root / "organization.yaml"
    skeleton = root / "organization.SKELETON.yaml"
    if organization.exists():
        kept.append("organization.yaml")
    elif skeleton.exists():
        kept.append("organization.SKELETON.yaml")
    else:
        source = templates / "organization.SKELETON.yaml"
        if not source.is_file():
            raise AdoptionError(f"required template is missing: {source}")
        shutil.copy2(source, skeleton)
        created.append("organization.SKELETON.yaml")

    return {
        "root": str(root),
        "created": created,
        "kept": kept,
        "network_access": False,
        "privileged_actions": False,
        "next": [
            "describe the existing repository in ARCHITECTURE.md",
            "write the minimal organization.yaml from real repository boundaries",
            "record only remaining work in coverage-manifest.md",
            "run org_lint and record the repro_lint baseline",
        ],
    }


def doctor(root):
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("org_state", all((root / path).is_dir() for path in STATE_DIRS),
        "ledger, doctrine, and conventions directories exist")
    add("core_specs", all((root / name).is_file() for name in SPEC_FILES),
        "constitution, sensors, schedule, moves, ledger schema, and role settings exist")
    freshness_declared = False
    freshness_value = None
    freshness_error = None
    constitution_path = root / "constitution.yaml"
    if constitution_path.is_file():
        try:
            import yaml
            document = yaml.safe_load(constitution_path.read_text(encoding="utf-8")) or {}
            judges = ((document.get("enforcement") or {}).get("judges") or {})
            if not isinstance(judges, dict):
                freshness_error = "enforcement.judges is not a map"
            elif "require_current_integration_head" in judges:
                freshness_declared = True
                freshness_value = judges["require_current_integration_head"]
                if not isinstance(freshness_value, bool):
                    freshness_error = "require_current_integration_head is not boolean"
        except Exception as exc:
            freshness_error = f"constitution could not be parsed: {exc}"
    freshness_ok = freshness_declared and freshness_error is None
    if freshness_error:
        freshness_detail = freshness_error
    elif not freshness_declared:
        freshness_detail = ("declare enforcement.judges.require_current_integration_head: true "
                            "(strict) or false (explicit compatibility); old review subjects cannot "
                            "prove integration-base freshness")
    elif freshness_value:
        freshness_detail = "strict review subjects must match the current integration head"
    else:
        freshness_detail = ("compatibility mode explicitly selected; stale integration bases are "
                            "not blocked")
    add("review_freshness", freshness_ok, freshness_detail)
    legacy_tier = _legacy_runtime_tier(root / "role-settings.yaml")
    add("runtime_mode", legacy_tier is None,
        "role settings use the current capability model"
        if legacy_tier is None else
        f"role-settings.yaml still declares obsolete defaults.tier: {legacy_tier}; remove the "
        "org-wide A/B mode and articulate maker/checker capabilities")
    organization = root / "organization.yaml"
    architecture = root / "ARCHITECTURE.md"
    remaining_work = root / "coverage-manifest.md"
    baseline = root / ".orgforge/repro-baseline.json"

    add("organization", organization.is_file(),
        "organization.yaml exists and the skeleton has been resolved")
    add("architecture", _has_non_whitespace_text(architecture),
        "ARCHITECTURE.md describes the repository as it exists")
    add("remaining_work", _has_non_whitespace_text(remaining_work),
        "coverage-manifest.md records only remaining work")

    baseline_ok = False
    if baseline.is_file():
        try:
            baseline_ok = isinstance(json.loads(baseline.read_text(encoding="utf-8")), dict)
        except (OSError, json.JSONDecodeError):
            baseline_ok = False
    add("baseline", baseline_ok, "the current mechanical debt baseline is valid JSON")

    schema_result = None
    if (root / "ledger-schema.yaml").is_file():
        schema_result = _run(
            root,
            sys.executable,
            str(Path(__file__).resolve().parent / "ledger.py"),
            "schema",
        )
    schema_ok = schema_result is not None and schema_result.returncode == 0
    schema_detail = "ledger schema matches the installed orgforge validation rules"
    if schema_result is not None and not schema_ok:
        output = ((schema_result.stdout or "") + (schema_result.stderr or "")).strip().splitlines()
        if output:
            schema_detail += f" ({output[-1]})"
    add("ledger_schema", schema_ok, schema_detail)

    lint_result = None
    if organization.is_file() and all((root / name).is_file() for name in SPEC_FILES):
        lint_result = _run(
            root,
            sys.executable,
            str(Path(__file__).resolve().parent / "org_lint.py"),
            "organization.yaml",
            "constitution.yaml",
            "moves.yaml",
            "ledger-schema.yaml",
            "sensors.yaml",
            "role-settings.yaml",
        )
    lint_ok = lint_result is not None and lint_result.returncode == 0
    lint_detail = "organization and governance specs pass org_lint"
    if lint_result is not None and not lint_ok:
        output = ((lint_result.stdout or "") + (lint_result.stderr or "")).strip().splitlines()
        if output:
            lint_detail += f" ({output[-1]})"
    add("organization_lint", lint_ok, lint_detail)

    ready = all(item["ok"] for item in checks)
    return {
        "root": str(root),
        "ready": ready,
        "checks": checks,
        "optional": {
            "github_remote": bool(_git(root, "remote", "get-url", "origin")),
            "note": "a GitHub remote is optional; without one the org is ledger-only",
        },
    }


def _print_human(command, result):
    if command == "inspect":
        print(f"Repository: {result['root']}")
        print(f"  tracked files: {result['tracked_files']} · commits: {result['commits']}")
        print(f"  remote: {result['remote'] or '(none — ledger-only is supported)'}")
        print(f"  manifests: {', '.join(result['manifests']) or '(none detected)'}")
        langs = ", ".join(
            f"{item['extension']}={item['files']}" for item in result["languages"]
        )
        print(f"  languages: {langs or '(none detected)'}")
        print(f"  test files: {result['test_files']}")
        print(f"  existing org: {'yes' if result['existing_org'] else 'no'}")
        print(f"  plugin development repo: {'yes' if result['plugin_repo'] else 'no'}")
        return
    if command == "prepare":
        print(f"Prepared orgforge adoption in {result['root']}")
        print(f"  created: {', '.join(result['created']) or '(nothing)'}")
        print(f"  kept: {', '.join(result['kept']) or '(nothing)'}")
        print("  no network, branch, Issue, daemon, sudo, or credential changes")
        print("Next:")
        for item in result["next"]:
            print(f"  - {item}")
        return

    print(f"Adoption doctor: {'READY' if result['ready'] else 'INCOMPLETE'}")
    for item in result["checks"]:
        mark = "✓" if item["ok"] else "✗"
        print(f"  {mark} {item['name']}: {item['detail']}")
    print(
        "  · GitHub remote: "
        + ("available" if result["optional"]["github_remote"] else "not configured (optional)")
    )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="adopt.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "doctor"):
        command = sub.add_parser(name)
        command.add_argument("root", nargs="?", default=".")
        command.add_argument("--json", action="store_true")
    command = sub.add_parser("prepare")
    command.add_argument("root", nargs="?", default=".")
    command.add_argument("--language", choices=("ja", "en"), default="ja")
    command.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        root = _root(args.root)
        if args.command == "inspect":
            result = inspect(root)
        elif args.command == "prepare":
            result = prepare(root, args.language)
        else:
            result = doctor(root)
    except AdoptionError as error:
        print(f"adopt: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(args.command, result)
    return 0 if args.command != "doctor" or result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
