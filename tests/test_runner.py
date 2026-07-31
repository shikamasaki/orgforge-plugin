import importlib.util
import json
import pathlib
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parent.parent
RUNNER_PATH = REPO / "integrations" / "runner" / "run_department.py"
CODEX_CONFIG = REPO / "integrations" / "codex" / "config.toml"
PROJECT_CODEX_CONFIG = REPO / ".codex" / "config.toml"
PROJECT_CLAUDE_SETTINGS = REPO / ".claude" / "settings.json"


def _runner_module():
    spec = importlib.util.spec_from_file_location("run_department", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_projection_uses_trusted_developer_mode_without_prompts():
    runner = _runner_module()
    command = runner.build_codex(
        role="maker",
        task="implement the accepted change",
        profile="",
        model="test-model",
        workdir="/tmp/example",
    )
    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--dangerously-bypass-hook-trust" in command
    assert "--sandbox" not in command


def test_legacy_tier_flag_is_rejected():
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--harness",
            "codex",
            "--role",
            "maker",
            "--task",
            "inspect",
            "--tier",
            "B",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: --tier B" in result.stderr


def test_codex_default_is_trusted_developer_mode():
    for path in (CODEX_CONFIG, PROJECT_CODEX_CONFIG):
        config = path.read_text(encoding="utf-8")
        assert 'approval_policy = "never"' in config
        assert 'sandbox_mode = "danger-full-access"' in config
        assert "network_access = true" in config


def test_claude_projection_skips_permissions_by_default():
    runner = _runner_module()
    command = runner.build_claude(
        role="maker",
        task="implement the accepted change",
        profile="",
        tools=["read", "write", "edit", "run_tests", "network"],
        mode=None,
        workdir="/tmp/example",
        plugin_dir=None,
    )
    assert "--dangerously-skip-permissions" in command
    assert "--permission-mode" not in command


def test_claude_commands_preapprove_normal_development_tools():
    command_dir = REPO / "integrations" / "claude-code" / "commands"
    for path in command_dir.glob("*.md"):
        frontmatter = path.read_text(encoding="utf-8").split("---", 2)[1]
        assert "allowed-tools: Bash(*)" in frontmatter, path.name


def test_claude_project_default_is_bypass_permissions():
    settings = json.loads(PROJECT_CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    assert settings["permissions"]["defaultMode"] == "bypassPermissions"
    assert settings["skipDangerousModePermissionPrompt"] is True
