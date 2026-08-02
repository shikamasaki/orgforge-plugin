"""Claude Monitor adapter — notify on RED transitions, not on every poll."""

import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from conftest import REPO, seed


SOURCE = REPO / "integrations" / "common" / "redline_monitor.py"
BUNDLE = REPO / "integrations" / "claude-code" / "scripts" / "redline_monitor.py"
CODEX_BUNDLE = REPO / "integrations" / "codex" / "scripts" / "redline_monitor.py"
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


def test_watch_updates_heartbeat_on_every_probe_and_stops_cooperatively():
    output = io.StringIO()
    beats = []
    stop_checks = iter([False, False, True])

    polls = MONITOR.watch(
        _sequence(["", "RED one"]), interval=1, output=output,
        sleeper=lambda _: None, on_poll=beats.append,
        should_stop=lambda: next(stop_checks))

    assert polls == 2
    assert beats == ["", "RED one"]
    assert output.getvalue().splitlines() == ["RED one"]


def test_registry_classifies_live_stale_dead_duplicate_orphan_and_old_version(tmp_path):
    registry = tmp_path / "monitors"
    current = MONITOR.register_heartbeat(
        registry, role="supervisor", instance="redline-supervisor",
        version="2.0.14", pid=101, now=1000, token="current")
    old = MONITOR.register_heartbeat(
        registry, role="supervisor", instance="redline-supervisor",
        version="2.0.13", pid=102, now=1001, token="old")
    MONITOR.register_heartbeat(
        registry, role="gate", instance="gate-watch",
        version="2.0.14", pid=103, now=800, token="stale")
    MONITOR.register_heartbeat(
        registry, role="skeptic", instance="skeptic-watch",
        version="2.0.14", pid=104, now=1002, token="dead")

    rows = MONITOR.monitor_status(
        registry, current_version="2.0.14", now=1010, stale_after=60,
        pid_alive=lambda pid: pid in {101, 102, 103})
    by_token = {row["token"]: row for row in rows}

    assert by_token["current"]["status"] == "live"
    assert by_token["current"]["duplicate"] is True
    assert by_token["old"]["status"] == "live"
    assert by_token["old"]["old_version"] is True
    assert by_token["old"]["orphaned"] is True
    assert by_token["stale"]["status"] == "stale"
    assert by_token["dead"]["status"] == "dead"
    assert current["record_id"] != old["record_id"]


def test_stop_request_targets_one_record_without_signalling_a_pid(tmp_path):
    registry = tmp_path / "monitors"
    first = MONITOR.register_heartbeat(
        registry, role="supervisor", instance="redline-supervisor",
        version="2.0.14", pid=201, now=1000, token="first")
    second = MONITOR.register_heartbeat(
        registry, role="supervisor", instance="redline-supervisor",
        version="2.0.13", pid=202, now=1000, token="second")

    assert MONITOR.request_stop(registry, second["record_id"]) is True
    assert MONITOR.stop_requested(registry, second) is True
    assert MONITOR.stop_requested(registry, first) is False


def test_status_and_rearm_guidance_do_not_duplicate_a_live_monitor(tmp_path, capsys):
    registry = tmp_path / "monitors"
    record = MONITOR.register_heartbeat(
        registry, role="supervisor", instance="redline-supervisor",
        version="2.0.14", pid=301, now=1000, token="live")
    alive = lambda pid: pid == 301

    rc = MONITOR.report_status(
        registry, current_version="2.0.14", now=1010, stale_after=60,
        pid_alive=alive, role="supervisor", instance="redline-supervisor")
    assert rc == 0
    assert record["record_id"] in capsys.readouterr().out

    rc = MONITOR.rearm_check(
        registry, current_version="2.0.14", now=1010, stale_after=60,
        pid_alive=alive, role="supervisor", instance="redline-supervisor")
    out = capsys.readouterr().out
    assert rc != 0 and "DO NOT REARM" in out


def test_rearm_guidance_allows_arm_when_only_dead_or_stopped_records_remain(tmp_path, capsys):
    registry = tmp_path / "monitors"
    dead = MONITOR.register_heartbeat(
        registry, role="supervisor", instance="redline-supervisor",
        version="2.0.14", pid=401, now=1000, token="dead")
    MONITOR.mark_stopped(registry, dead, now=1001)

    rc = MONITOR.rearm_check(
        registry, current_version="2.0.14", now=1010, stale_after=60,
        pid_alive=lambda _pid: False, role="supervisor", instance="redline-supervisor")
    assert rc == 0
    assert "READY TO ARM" in capsys.readouterr().out


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


def test_both_harnesses_bundle_the_same_monitor_registry_contract():
    assert CODEX_BUNDLE.read_bytes() == SOURCE.read_bytes()
    assert (CODEX_BUNDLE.resolve().parents[1] / "tools" / "status.py").is_file()
    claude_version = MONITOR.plugin_version(BUNDLE)
    codex_version = MONITOR.plugin_version(CODEX_BUNDLE)
    assert codex_version.split("+", 1)[0] == claude_version
    assert "+codex." in codex_version


def test_shipped_entry_point_deduplicates_a_real_subprocess(tmp_path):
    status = tmp_path / "status.py"
    status.write_text("print('RED stable')\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(BUNDLE), "--status-script", str(status),
         "--registry", str(tmp_path / "registry"),
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


def test_live_process_status_rearm_and_cooperative_stop_end_to_end(tmp_path):
    status_script = tmp_path / "status.py"
    status_script.write_text("# healthy silence\n", encoding="utf-8")
    registry = tmp_path / "registry"
    base = [sys.executable, str(BUNDLE)]
    # Hermetic ps: status/rearm-check now cross-check the process table, and a real
    # monitor running on the host machine must not leak into this registry lifecycle test.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "ps").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake_bin / "ps").chmod(0o755)
    env = dict(os.environ, PATH=f"{fake_bin}:{os.environ.get('PATH', '')}")
    process = subprocess.Popen(
        base + ["--status-script", str(status_script), "--registry", str(registry),
                "--role", "supervisor", "--instance", "redline-supervisor",
                "--interval", "0.02", "--max-polls", "200"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.time() + 5
        records = []
        while time.time() < deadline:
            records = [path for path in registry.glob("*.json")
                       if not path.name.endswith(".stop.json")]
            if records:
                break
            time.sleep(0.02)
        assert len(records) == 1
        record_id = records[0].stem

        status = subprocess.run(
            base + ["status", "--registry", str(registry), "--role", "supervisor",
                    "--instance", "redline-supervisor"],
            capture_output=True, text=True, timeout=10, env=env)
        assert status.returncode == 0 and "MONITOR READY" in status.stdout
        assert record_id in status.stdout

        rearm = subprocess.run(
            base + ["rearm-check", "--registry", str(registry), "--role", "supervisor",
                    "--instance", "redline-supervisor"],
            capture_output=True, text=True, timeout=10, env=env)
        assert rearm.returncode == 4 and "DO NOT REARM" in rearm.stdout

        stop = subprocess.run(
            base + ["stop", record_id, "--registry", str(registry)],
            capture_output=True, text=True, timeout=10, env=env)
        assert stop.returncode == 0 and "no PID signal was sent" in stop.stdout
        assert process.wait(timeout=5) == 0
        assert process.stdout.read() == ""       # healthy silence remains silent

        after = subprocess.run(
            base + ["rearm-check", "--registry", str(registry), "--role", "supervisor",
                    "--instance", "redline-supervisor"],
            capture_output=True, text=True, timeout=10, env=env)
        assert after.returncode == 0 and "READY TO ARM" in after.stdout
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_timeout_signal_is_stable_for_deduplication(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["status.py", "redline"], 30)

    monkeypatch.setattr(MONITOR.subprocess, "run", timeout)
    assert MONITOR.probe("status.py") == "RED — org monitor probe timed out after 30 seconds"


def test_main_returns_130_on_keyboard_interrupt(monkeypatch, tmp_path):
    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(MONITOR, "watch", interrupt)
    assert MONITOR.main(["--registry", str(tmp_path / "registry"), "--max-polls", "1"]) == 130


@pytest.mark.parametrize("args", [["--interval", "0"], ["--max-polls", "0"]])
def test_main_rejects_non_positive_limits(args):
    with pytest.raises(SystemExit) as exc:
        MONITOR.main(args)
    assert exc.value.code == 2


def test_registration_failure_refuses_to_monitor(tmp_path, monkeypatch, capsys):
    """OBS-065 (a): if the registry record cannot be written, the monitor must not start."""
    blocked = tmp_path / "registry"
    blocked.write_text("a file where the registry directory should be", encoding="utf-8")
    probes = []
    monkeypatch.setattr(MONITOR, "probe", lambda *args, **kwargs: probes.append(args) or "")

    rc = MONITOR.main(["--registry", str(blocked), "--max-polls", "1"])

    assert rc == 3
    assert probes == []                      # never entered the watch loop
    assert "REFUSING TO START" in capsys.readouterr().err


def test_shipped_entry_point_fails_closed_without_registry_write(tmp_path):
    blocked = tmp_path / "registry"
    blocked.write_text("not a directory", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(BUNDLE), "--registry", str(blocked), "--max-polls", "1"],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 3
    assert result.stdout == ""
    assert "REFUSING TO START" in result.stderr


def test_status_reports_unregistered_same_instance_process(tmp_path, capsys):
    """OBS-065 (b): status must cross-check ps and flag same-instance processes with no record."""
    registry = tmp_path / "monitors"
    MONITOR.register_heartbeat(registry, role="supervisor", instance="redline-supervisor",
                               version="2.0.30", pid=222, now=1000, token="seen")
    ps_rows = [
        (222, "python3 /plug/scripts/redline_monitor.py /ledger --role supervisor"),
        (97836, "python3 /plug/scripts/redline_monitor.py /ledger --role supervisor "
                "--instance redline-supervisor --interval 60"),
        (500, "python3 /plug/scripts/redline_monitor.py status --registry /somewhere"),
        (501, "grep redline_monitor"),
        (502, "python3 /plug/scripts/redline_monitor.py /ledger --role gate"),
    ]

    rc = MONITOR.report_status(
        registry, current_version="2.0.30", now=1010, stale_after=60,
        pid_alive=lambda pid: pid == 222, role="supervisor",
        instance="redline-supervisor", ps_rows=ps_rows)
    out = capsys.readouterr().out

    assert rc == 4
    assert "MONITOR ATTENTION" in out
    assert "pid=97836" in out and "unregistered" in out
    assert "pid=500" not in out              # subcommand invocation is not a watch loop
    assert "pid=501" not in out              # grep is not a monitor
    assert "pid=502" not in out              # different logical instance


def test_status_flags_unregistered_process_even_with_empty_registry(tmp_path, capsys):
    registry = tmp_path / "monitors"
    ps_rows = [(97836, "python3 /plug/scripts/redline_monitor.py /ledger "
                       "--role supervisor --instance redline-supervisor")]

    rc = MONITOR.report_status(
        registry, current_version="2.0.30", now=1010, stale_after=60,
        pid_alive=lambda _pid: False, role="supervisor",
        instance="redline-supervisor", ps_rows=ps_rows)
    out = capsys.readouterr().out

    assert rc == 4
    assert "MONITOR ABSENT" not in out       # a live-but-invisible monitor is not absence
    assert "pid=97836" in out and "unregistered" in out


def test_status_notes_unavailable_process_table_without_crashing(tmp_path, capsys):
    registry = tmp_path / "monitors"
    MONITOR.register_heartbeat(registry, role="supervisor", instance="redline-supervisor",
                               version="2.0.30", pid=222, now=1000, token="seen")

    rc = MONITOR.report_status(
        registry, current_version="2.0.30", now=1010, stale_after=60,
        pid_alive=lambda pid: pid == 222, role="supervisor",
        instance="redline-supervisor", ps_rows=None)
    out = capsys.readouterr().out

    assert rc == 0                           # registry itself is healthy
    assert "process table unavailable" in out


def test_rearm_check_refuses_when_unregistered_live_process_owns_instance(tmp_path, capsys):
    """OBS-065 (c): an unregistered live process for the instance means DO NOT REARM."""
    registry = tmp_path / "monitors"         # registry looks empty — the Tatekae trap
    ps_rows = [(97836, "python3 /plug/scripts/redline_monitor.py /ledger "
                       "--role supervisor --instance redline-supervisor")]

    rc = MONITOR.rearm_check(
        registry, current_version="2.0.30", now=1010, stale_after=60,
        pid_alive=lambda _pid: False, role="supervisor",
        instance="redline-supervisor", ps_rows=ps_rows)
    out = capsys.readouterr().out

    assert rc == 4
    assert "DO NOT REARM" in out and "unregistered" in out
    assert "READY TO ARM" not in out


def test_rearm_check_notes_unavailable_process_table(tmp_path, capsys):
    registry = tmp_path / "monitors"

    rc = MONITOR.rearm_check(
        registry, current_version="2.0.30", now=1010, stale_after=60,
        pid_alive=lambda _pid: False, role="supervisor",
        instance="redline-supervisor", ps_rows=None)
    out = capsys.readouterr().out

    assert rc == 0
    assert "READY TO ARM" in out and "process table unavailable" in out


def test_process_table_reads_pid_and_command_defensively():
    class Result:
        returncode = 0
        stdout = "  12 python3 monitor.py\ngarbage line\n 13 ps -axo pid=,command=\n"

    rows = MONITOR.process_table(runner=lambda *a, **k: Result())
    assert rows == [(12, "python3 monitor.py"), (13, "ps -axo pid=,command=")]

    def broken(*_args, **_kwargs):
        raise OSError("no ps on this host")
    assert MONITOR.process_table(runner=broken) is None


def test_cli_status_consults_the_process_table_via_ps(tmp_path):
    """End-to-end: the shipped status subcommand actually reads ps, not only the registry."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ps = fake_bin / "ps"
    fake_ps.write_text(
        "#!/bin/sh\n"
        "echo ' 97836 python3 /plug/scripts/redline_monitor.py /ledger"
        " --role supervisor --instance redline-supervisor'\n", encoding="utf-8")
    fake_ps.chmod(0o755)
    registry = tmp_path / "registry"
    registry.mkdir()
    env = dict(os.environ, PATH=f"{fake_bin}:{os.environ.get('PATH', '')}")

    result = subprocess.run(
        [sys.executable, str(BUNDLE), "status", "--registry", str(registry),
         "--role", "supervisor", "--instance", "redline-supervisor"],
        capture_output=True, text=True, timeout=10, env=env)

    assert result.returncode == 4
    assert "pid=97836" in result.stdout and "unregistered" in result.stdout


def test_org_start_checks_liveness_before_rearming_monitor():
    command = (REPO / "integrations" / "claude-code" / "commands" / "org-start.md").read_text(
        encoding="utf-8")
    assert "rearm-check" in command
    assert "--instance" in command
    assert command.index("rearm-check") < command.index("Monitor (persistent)")
