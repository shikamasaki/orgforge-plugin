import os
import stat
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "integrations" / "claude-code" / "scheduler-install.sh"


def _executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path: Path, *extra: str, dry_run: bool = True) -> tuple[subprocess.CompletedProcess[str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    _executable(fake_bin / "claude", "#!/bin/sh\nexit 0\n")

    state = tmp_path / "crontab"
    _executable(
        fake_bin / "crontab",
        """#!/usr/bin/env python3
import os
import pathlib
import sys

state = pathlib.Path(os.environ["FAKE_CRONTAB_STATE"])
if sys.argv[1:] == ["-l"]:
    if not state.exists():
        raise SystemExit(1)
    sys.stdout.write(state.read_text(encoding="utf-8"))
elif sys.argv[1:] == ["-"]:
    state.write_text(sys.stdin.read(), encoding="utf-8")
else:
    raise SystemExit(2)
""",
    )

    ledger = tmp_path / "ledger with ' quote % pct"
    ledger.mkdir(exist_ok=True)
    workdir = tmp_path / "work with ' quote % pct"
    workdir.mkdir(exist_ok=True)
    args = [
        str(SCRIPT),
        "--role",
        "supervisor",
        "--workdir",
        str(workdir),
        *extra,
    ]
    if dry_run:
        args.append("--dry-run")
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "ORG_LEDGER_ROOT": str(ledger),
        "FAKE_CRONTAB_STATE": str(state),
    }
    return subprocess.run(args, text=True, capture_output=True, env=env), state


def _scheduled_commands(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.endswith("# orgforge:supervisor")
    ]


def test_default_keeps_all_three_cycles(tmp_path):
    result, _ = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    lines = _scheduled_commands(result.stdout)
    assert len(lines) == 3
    assert any("-p '/org-tick'" in line for line in lines)
    assert any("-p '/org-work supervisor'" in line for line in lines)
    assert any("-p '/org-discover supervisor'" in line for line in lines)


def test_cycles_can_install_tick_only(tmp_path):
    result, _ = _run(tmp_path, "--cycles", "tick")
    assert result.returncode == 0, result.stderr
    lines = _scheduled_commands(result.stdout)
    assert len(lines) == 1
    assert "-p '/org-tick'" in lines[0]
    assert "/org-work" not in result.stdout
    assert "/org-discover" not in result.stdout


def test_cycles_can_stage_tick_and_discover_without_work(tmp_path):
    result, _ = _run(tmp_path, "--cycles", "tick,discover")
    assert result.returncode == 0, result.stderr
    lines = _scheduled_commands(result.stdout)
    assert len(lines) == 2
    assert any("-p '/org-tick'" in line for line in lines)
    assert any("-p '/org-discover supervisor'" in line for line in lines)
    assert "/org-work" not in result.stdout


def test_reinstall_removes_now_unselected_cycles_and_preserves_unrelated_entries(tmp_path):
    first, state = _run(tmp_path, dry_run=False)
    assert first.returncode == 0, first.stderr
    original = state.read_text(encoding="utf-8")
    state.write_text(
        "5 4 * * * unrelated-command # keep-me\n"
        "6 4 * * * other-role # orgforge:supervisor-old\n"
        + original,
        encoding="utf-8",
    )

    second, state = _run(tmp_path, "--cycles", "tick", dry_run=False)
    assert second.returncode == 0, second.stderr
    installed = state.read_text(encoding="utf-8")
    assert "unrelated-command # keep-me" in installed
    assert "other-role # orgforge:supervisor-old" in installed
    assert len(_scheduled_commands(installed)) == 1
    assert "/org-tick" in installed
    assert "/org-work" not in installed
    assert "/org-discover" not in installed


def test_dry_run_does_not_change_crontab(tmp_path):
    _, state = _run(tmp_path, dry_run=False)
    before = state.read_text(encoding="utf-8")
    result, state = _run(tmp_path, "--cycles", "tick", dry_run=True)
    assert result.returncode == 0, result.stderr
    assert state.read_text(encoding="utf-8") == before


def test_rejects_empty_unknown_and_duplicate_cycles(tmp_path):
    for cycles in ("", "tick,", ",tick", "tick,,work", "tick,unknown", "tick,tick"):
        result, _ = _run(tmp_path, "--cycles", cycles)
        assert result.returncode == 2
        assert "cycles" in result.stderr.lower()


def test_rejects_intervals_cron_cannot_represent_exactly(tmp_path):
    cases = [
        ("tick", "--tick-min", "0"),
        ("tick", "--tick-min", "08"),
        ("tick", "--tick-min", "90"),
        ("work", "--work-min", "90"),
        ("discover", "--discover-hours", "25"),
    ]
    for cycle, option, value in cases:
        result, _ = _run(tmp_path, "--cycles", cycle, option, value)
        assert result.returncode == 2
        assert "interval" in result.stderr.lower()


def test_daily_intervals_generate_valid_daily_cron(tmp_path):
    result, _ = _run(
        tmp_path,
        "--cycles",
        "work,discover",
        "--work-min",
        "1440",
        "--discover-hours",
        "24",
    )
    assert result.returncode == 0, result.stderr
    lines = _scheduled_commands(result.stdout)
    assert len(lines) == 2
    assert all(line.startswith("0 0 * * *") for line in lines)


def test_rejects_unsafe_role_and_quotes_paths_for_shell_and_cron(tmp_path):
    result, _ = _run(tmp_path, "--cycles", "tick")
    assert result.returncode == 0, result.stderr
    assert "work with '\\'' quote \\% pct" in result.stdout
    assert "ledger with '\\'' quote \\% pct" in result.stdout

    # Cron removes the escape that protects '%' before invoking /bin/sh. Simulate that handoff and
    # prove the generated command reaches the quoted workdir/log path rather than splitting it.
    line = _scheduled_commands(result.stdout)[0]
    command = line.split(maxsplit=5)[5].removesuffix("  # orgforge:supervisor").replace("\\%", "%")
    executed = subprocess.run(["/bin/sh", "-c", command], text=True, capture_output=True)
    assert executed.returncode == 0, executed.stderr
    assert (tmp_path / "ledger with ' quote % pct" / "cron.log").is_file()

    fake_bin = tmp_path / "unsafe-bin"
    fake_bin.mkdir()
    _executable(fake_bin / "claude", "#!/bin/sh\nexit 0\n")
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "ORG_LEDGER_ROOT": str(tmp_path / "ledger"),
    }
    unsafe = subprocess.run(
        [str(SCRIPT), "--role", "supervisor;touch-pwned", "--dry-run"],
        text=True,
        capture_output=True,
        env=env,
    )
    assert unsafe.returncode == 2
    assert "role" in unsafe.stderr.lower()
