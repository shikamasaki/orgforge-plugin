"""Claude Monitor adapter — notify on RED transitions, not on every poll."""

import importlib.util
import io
from pathlib import Path
import subprocess
import sys

import pytest

from conftest import REPO, seed


SOURCE = REPO / "integrations" / "common" / "redline_monitor.py"
BUNDLE = REPO / "integrations" / "claude-code" / "scripts" / "redline_monitor.py"
SPEC = importlib.util.spec_from_file_location("redline_monitor", SOURCE)
MONITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MONITOR)


def _sequence(values):
    iterator = iter(values)
    return lambda: next(iterator)


def test_watch_emits_first_changed_and_recurrent_red_after_green():
    output = io.StringIO()
    sleeps = []
    values = ["", "RED one", "RED one", "RED two", "", "RED one"]

    polls = MONITOR.watch(_sequence(values), interval=7, max_polls=len(values),
                          output=output, sleeper=sleeps.append)

    assert polls == 6
    assert output.getvalue().splitlines() == ["RED one", "RED two", "RED one"]
    assert sleeps == [7, 7, 7, 7, 7]


def test_watch_stays_silent_while_green():
    output = io.StringIO()
    MONITOR.watch(_sequence(["", "", ""]), max_polls=3,
                  output=output, sleeper=lambda _: None)
    assert output.getvalue() == ""


def test_probe_failure_becomes_a_red_signal(tmp_path):
    status = tmp_path / "status.py"
    status.write_text("import sys\nprint('ledger unavailable', file=sys.stderr)\nsys.exit(7)\n",
                      encoding="utf-8")
    assert MONITOR.probe(status) == "RED — org monitor probe failed (exit 7): ledger unavailable"


def test_probe_forwards_root_and_role(tmp_path):
    status = tmp_path / "status.py"
    status.write_text(
        "import sys\nprint('RED ' + '|'.join(sys.argv[1:]))\n", encoding="utf-8")
    assert MONITOR.probe(status, Path("/tmp/ledger"), "supervisor") == (
        "RED redline|/tmp/ledger|--role|supervisor")


def test_claude_bundle_is_generated_and_default_status_path_exists():
    assert BUNDLE.read_bytes() == SOURCE.read_bytes()
    assert (BUNDLE.resolve().parents[1] / "tools" / "status.py").is_file()


def test_shipped_entry_point_deduplicates_a_real_subprocess(tmp_path):
    status = tmp_path / "status.py"
    status.write_text("print('RED stable')\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(BUNDLE), "--status-script", str(status),
         "--interval", "0.001", "--max-polls", "2"],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["RED stable"]


def test_shipped_entry_point_uses_real_status_probe(tmp_path):
    green = tmp_path / "green"
    red = tmp_path / "red"
    green.mkdir()
    red.mkdir()
    seed(green, "e", "cycle_completed", {"candidate_id": "A", "role": "e"},
         ts="2026-07-16T01:00:00Z")
    seed(red, "x", "repeated_death_detected",
         {"cause": "null", "occurrences": 2, "candidate_ids": ["A", "B"]},
         ts="2026-07-16T01:00:00Z")

    green_result = subprocess.run(
        [sys.executable, str(BUNDLE), str(green), "--max-polls", "1"],
        capture_output=True, text=True, timeout=10)
    red_result = subprocess.run(
        [sys.executable, str(BUNDLE), str(red), "--max-polls", "1"],
        capture_output=True, text=True, timeout=10)

    assert green_result.returncode == 0 and green_result.stdout == ""
    assert red_result.returncode == 0 and red_result.stdout.startswith("RED — org needs you")


def test_timeout_signal_is_stable_for_deduplication(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["status.py", "redline"], 30)

    monkeypatch.setattr(MONITOR.subprocess, "run", timeout)
    assert MONITOR.probe("status.py") == "RED — org monitor probe timed out after 30 seconds"


def test_main_returns_130_on_keyboard_interrupt(monkeypatch):
    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(MONITOR, "watch", interrupt)
    assert MONITOR.main(["--max-polls", "1"]) == 130


@pytest.mark.parametrize("args", [["--interval", "0"], ["--max-polls", "0"]])
def test_main_rejects_non_positive_limits(args):
    with pytest.raises(SystemExit) as exc:
        MONITOR.main(args)
    assert exc.value.code == 2
