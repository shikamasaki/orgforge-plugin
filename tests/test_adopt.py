import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("orgforge_adopt", REPO / "tools" / "adopt.py")
ADOPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADOPT)


def test_prepare_is_local_idempotent_and_preserves_existing_files(tmp_path):
    first = ADOPT.prepare(tmp_path, "en")
    assert "constitution.yaml" in first["created"]
    assert (tmp_path / ".orgforge/ledger").is_dir()
    assert "output_language: en" in (tmp_path / "constitution.yaml").read_text(encoding="utf-8")

    constitution = tmp_path / "constitution.yaml"
    constitution.write_text("output_language: ja\ncustom: keep-me\n", encoding="utf-8")
    second = ADOPT.prepare(tmp_path, "en")

    assert "constitution.yaml" in second["kept"]
    assert constitution.read_text(encoding="utf-8") == "output_language: ja\ncustom: keep-me\n"
    assert second["created"] == []


def test_prepare_refuses_the_plugin_development_repository(tmp_path):
    (tmp_path / "integrations/claude-code/commands").mkdir(parents=True)
    try:
        ADOPT.prepare(tmp_path, "ja")
    except ADOPT.AdoptionError as error:
        assert "plugin development repository" in str(error)
    else:
        raise AssertionError("plugin development repository was adopted")
    assert not (tmp_path / ".orgforge").exists()


def test_inspect_reports_repository_facts_without_writing(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    result = ADOPT.inspect(tmp_path)

    assert result["tracked_files"] == 2
    assert result["manifests"] == ["pyproject.toml"]
    assert result["test_files"] == 1
    assert result["existing_org"] is False
    assert not (tmp_path / ".orgforge").exists()


def test_inspect_non_git_fallback_ignores_only_paths_inside_the_root(tmp_path):
    root = tmp_path / "build" / "sample"
    (root / "tests").mkdir(parents=True)
    (root / "README.md").write_text("sample\n", encoding="utf-8")
    (root / "tests/test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    result = ADOPT.inspect(root)

    assert result["tracked_files"] == 2
    assert result["test_files"] == 1


def test_doctor_requires_design_and_baseline_after_prepare(tmp_path):
    ADOPT.prepare(tmp_path, "ja")
    incomplete = ADOPT.doctor(tmp_path)
    assert incomplete["ready"] is False
    assert {item["name"] for item in incomplete["checks"] if not item["ok"]} == {
        "organization",
        "architecture",
        "remaining_work",
        "baseline",
        "organization_lint",
    }

    shutil.copy2(REPO / "template" / "organization.yaml", tmp_path / "organization.yaml")
    for name in ("ARCHITECTURE.md", "coverage-manifest.md"):
        (tmp_path / name).write_text("ready\n", encoding="utf-8")
    baseline = tmp_path / ".orgforge/repro-baseline.json"
    baseline.write_text(json.dumps({"version": 1}), encoding="utf-8")

    assert ADOPT.doctor(tmp_path)["ready"] is True


def test_doctor_rejects_invalid_baseline_and_organization(tmp_path):
    ADOPT.prepare(tmp_path, "ja")
    (tmp_path / "organization.yaml").write_text("roles: []\n", encoding="utf-8")
    (tmp_path / "ARCHITECTURE.md").write_text("architecture\n", encoding="utf-8")
    (tmp_path / "coverage-manifest.md").write_text("remaining work\n", encoding="utf-8")
    (tmp_path / ".orgforge/repro-baseline.json").write_text("{broken", encoding="utf-8")

    result = ADOPT.doctor(tmp_path)
    failed = {item["name"] for item in result["checks"] if not item["ok"]}

    assert result["ready"] is False
    assert "baseline" in failed
    assert "organization_lint" in failed


def test_doctor_rejects_whitespace_only_design_artifacts(tmp_path):
    ADOPT.prepare(tmp_path, "ja")
    shutil.copy2(REPO / "template" / "organization.yaml", tmp_path / "organization.yaml")
    (tmp_path / "ARCHITECTURE.md").write_text(" \n\t\n", encoding="utf-8")
    (tmp_path / "coverage-manifest.md").write_text("\n", encoding="utf-8")
    (tmp_path / ".orgforge/repro-baseline.json").write_text(
        json.dumps({"version": 1}), encoding="utf-8"
    )

    result = ADOPT.doctor(tmp_path)
    failed = {item["name"] for item in result["checks"] if not item["ok"]}

    assert "architecture" in failed
    assert "remaining_work" in failed


def test_adoption_surfaces_validate_neutral_role_settings():
    claude = (REPO / "integrations/claude-code/commands/org-adopt.md").read_text(encoding="utf-8")
    codex = (REPO / "integrations/codex/skills/org-adopt/SKILL.md").read_text(encoding="utf-8")

    assert "sensors.yaml role-settings.yaml" in claude
    assert "sensors.yaml role-settings.yaml" in codex


def test_cli_doctor_exit_code_tracks_readiness(tmp_path):
    command = [sys.executable, str(REPO / "tools/adopt.py"), "doctor", str(tmp_path), "--json"]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)["ready"] is False
