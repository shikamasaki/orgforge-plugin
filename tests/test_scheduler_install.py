from __future__ import annotations

import datetime as dt
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "integrations" / "claude-code" / "scheduler-install.sh"
STATUS = REPO / "integrations" / "claude-code" / "scheduler-status.sh"
UNINSTALL = REPO / "integrations" / "claude-code" / "scheduler-uninstall.sh"
PLUGIN = REPO / "integrations" / "claude-code"
TICK = PLUGIN / "scripts" / "scheduler_tick.py"


def _executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fake_crontab(path: Path) -> None:
    _executable(
        path,
        """#!/usr/bin/env python3
import os
import pathlib
import sys
import time

state = pathlib.Path(os.environ["FAKE_CRONTAB_STATE"])
if os.environ.get("FAKE_CRONTAB_HANG") == "1" and sys.argv[1:] == ["-"]:
    time.sleep(30)
if sys.argv[1:] == ["-l"]:
    if not state.exists():
        raise SystemExit(1)
    sys.stdout.write(state.read_text(encoding="utf-8"))
elif sys.argv[1:] == ["-"]:
    if os.environ.get("FAKE_CRONTAB_IGNORE_WRITE") != "1":
        state.write_text(sys.stdin.read(), encoding="utf-8")
else:
    raise SystemExit(2)
""",
    )


def _fake_launchctl(path: Path) -> None:
    _executable(
        path,
        """#!/usr/bin/env python3
import json
import os
import pathlib
import plistlib
import subprocess
import sys

state = pathlib.Path(os.environ["FAKE_LAUNCHCTL_STATE"])
data = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
args = sys.argv[1:]
if args and args[0] == "bootout":
    data.pop(args[-1].split("/")[-1], None)
    state.write_text(json.dumps(data), encoding="utf-8")
    raise SystemExit(0)
if len(args) == 3 and args[0] == "bootstrap":
    plist_path = pathlib.Path(args[2])
    plist = plistlib.loads(plist_path.read_bytes())
    data[plist["Label"]] = str(plist_path)
    state.write_text(json.dumps(data), encoding="utf-8")
    raise SystemExit(0)
if len(args) == 3 and args[:2] == ["kickstart", "-k"]:
    if os.environ.get("FAKE_LAUNCHCTL_FAIL_KICKSTART") == "1":
        raise SystemExit(9)
    label = args[2].split("/")[-1]
    plist = plistlib.loads(pathlib.Path(data[label]).read_bytes())
    env = {**os.environ, **plist.get("EnvironmentVariables", {})}
    completed = subprocess.run(plist["ProgramArguments"], cwd=plist["WorkingDirectory"], env=env)
    raise SystemExit(completed.returncode if completed.returncode not in (0, 10) else 0)
if len(args) == 2 and args[0] == "print":
    label = args[1].split("/")[-1]
    if label in data:
        print("state = not running")
        print("runs = 1")
        print("last exit code = 0")
        raise SystemExit(0)
    raise SystemExit(3)
raise SystemExit(2)
""",
    )


def _fixture(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    _fake_crontab(fake_bin / "crontab")
    _fake_launchctl(fake_bin / "launchctl")
    ledger = tmp_path / "ledger with ' quote % pct"
    ledger.mkdir(exist_ok=True)
    workdir = tmp_path / "work with ' quote % pct"
    workdir.mkdir(exist_ok=True)
    binding = workdir / ".git" / "orgforge" / "runtime" / "claude-code" / "installed-organ.json"
    binding.parent.mkdir(parents=True, exist_ok=True)
    binding.write_text(json.dumps({
        "schema": "orgforge-installed-organ/v1",
        "version": "2.0.25",
        "plugin_root": str(PLUGIN),
        "org_root": str(workdir),
        "harness": "claude-code",
    }), encoding="utf-8")
    launcher = binding.parent / "bin" / "orgforge"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    _executable(launcher, """#!/usr/bin/env python3
import json
import os
import pathlib
import sys
binding = pathlib.Path(__file__).resolve().parents[1] / "installed-organ.json"
value = json.loads(binding.read_text(encoding="utf-8"))
organ = sys.argv[1].replace("-", "_")
    target = pathlib.Path(value["plugin_root"]) / "tools" / f"{organ}.py"
os.execv(sys.executable, [sys.executable, str(target), *sys.argv[2:]])
""")
    state = tmp_path / "crontab-state"
    launch_state = tmp_path / "launchctl-state"
    launch_agents = tmp_path / "LaunchAgents"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "ORG_PYTHON_BOOTSTRAP": sys.executable,
        "ORG_LEDGER_ROOT": str(ledger),
        "FAKE_CRONTAB_STATE": str(state),
        "FAKE_LAUNCHCTL_STATE": str(launch_state),
        "ORGFORGE_CRONTAB": str(fake_bin / "crontab"),
        "ORGFORGE_LAUNCHCTL": str(fake_bin / "launchctl"),
        "ORGFORGE_LAUNCH_AGENTS_DIR": str(launch_agents),
        "ORGFORGE_LAUNCH_DOMAIN": "gui/999",
    }
    return env, ledger, workdir, state


def _install(tmp_path: Path, *extra: str, dry_run: bool = True,
             env_update: dict[str, str] | None = None):
    env, ledger, workdir, state = _fixture(tmp_path)
    if env_update:
        env.update(env_update)
    args = [str(SCRIPT), "--role", "supervisor", "--root", str(ledger),
            "--workdir", str(workdir), "--python", sys.executable, *extra]
    if dry_run:
        args.append("--dry-run")
    result = subprocess.run(args, text=True, capture_output=True, env=env)
    return result, env, ledger, workdir, state


def test_default_is_verified_machine_tick_not_headless_claude(tmp_path):
    result, _, ledger, _, _ = _install(tmp_path, "--backend", "cron")
    assert result.returncode == 0, result.stderr
    assert "orgforge-scheduler-tick" in result.stdout
    assert "claude -p" not in result.stdout
    assert "backend: cron" in result.stdout
    assert not (ledger / "ledger.jsonl").exists(), "dry-run must not write a smoke receipt"


def test_persistent_acting_cycles_fail_closed(tmp_path):
    for cycles in ("work", "discover", "tick,work", "tick,discover"):
        result, *_ = _install(tmp_path, "--backend", "cron", "--cycles", cycles)
        assert result.returncode == 2
        assert "Refusing a silent no-op" in result.stderr


def test_rejects_empty_unknown_duplicate_and_inexact_interval(tmp_path):
    cases = [
        ("--cycles", ""), ("--cycles", "tick,"), ("--cycles", "tick,tick"),
        ("--cycles", "unknown"), ("--tick-min", "90"), ("--tick-min", "08"),
    ]
    for option, value in cases:
        result, *_ = _install(tmp_path, "--backend", "cron", option, value)
        assert result.returncode == 2
        assert "error:" in result.stderr.lower()


def test_cron_install_smokes_receipt_and_verifies_exact_readback(tmp_path):
    result, env, ledger, workdir, state = _install(
        tmp_path, "--backend", "cron", "--tick-min", "30", dry_run=False)
    assert result.returncode == 0, result.stdout + result.stderr
    installed = state.read_text(encoding="utf-8")
    assert installed.count("# orgforge:supervisor") == 1
    assert "orgforge-scheduler-tick" in installed
    assert "\\%" in installed, "cron-significant percent literals must remain protected"
    line = next(line for line in installed.splitlines() if line.endswith("# orgforge:supervisor"))
    command = line.split(maxsplit=5)[5].removesuffix("  # orgforge:supervisor").replace("\\%", "%")
    executed = subprocess.run(["/bin/sh", "-c", command], text=True, capture_output=True, env=env)
    assert executed.returncode in (0, 10), executed.stdout + executed.stderr
    receipt = [json.loads(line) for line in (ledger / "ledger.jsonl").read_text(
        encoding="utf-8").splitlines() if line]
    assert receipt[-1]["class"] == "tick_planned"
    assert [event["class"] for event in receipt].count("scheduled_check_completed") == 2
    run = json.loads((ledger / "scheduler-state.json").read_text(encoding="utf-8"))
    assert run["receipt_seq"] == receipt[-1]["seq"]
    registry = json.loads((ledger / "scheduler-installation.json").read_text(encoding="utf-8"))
    assert registry["backend"] == "cron" and registry["cycles"] == ["tick"]
    assert registry["coverage"]["unattended"] == ["machine_sensors", "chain_verify"]
    assert "attended-only schedule checks" in result.stdout

    status = subprocess.run([str(STATUS), "--root", str(ledger)], text=True,
                            capture_output=True, env=env)
    assert status.returncode == 0, status.stdout + status.stderr
    status_value = json.loads(status.stdout)
    assert status_value["definition_present"] is True
    assert status_value["last_receipt"]["seq"] == receipt[-1]["seq"]
    assert status_value["last_receipt_age_min"] >= 0


def test_cron_reinstall_preserves_unrelated_entries_and_uninstall_removes_only_role(tmp_path):
    env, ledger, workdir, state = _fixture(tmp_path)
    state.write_text(
        "5 4 * * * unrelated-command # keep-me\n"
        "6 4 * * * old-command # orgforge:supervisor\n",
        encoding="utf-8",
    )
    installed = subprocess.run(
        [str(SCRIPT), "--role", "supervisor", "--root", str(ledger),
         "--workdir", str(workdir), "--python", sys.executable, "--backend", "cron"],
        text=True, capture_output=True, env=env,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    value = state.read_text(encoding="utf-8")
    assert "unrelated-command # keep-me" in value
    assert "old-command" not in value
    assert value.count("# orgforge:supervisor") == 1

    removed = subprocess.run(
        [str(UNINSTALL), "--root", str(ledger), "--role", "supervisor"],
        text=True, capture_output=True, env=env,
    )
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert state.read_text(encoding="utf-8").strip() == "5 4 * * * unrelated-command # keep-me"


def test_crontab_write_is_bounded_and_does_not_claim_installation(tmp_path):
    result, _, ledger, _, state = _install(
        tmp_path, "--backend", "cron", dry_run=False,
        env_update={"FAKE_CRONTAB_HANG": "1", "ORGFORGE_SCHEDULER_TIMEOUT": "0.2"})
    assert result.returncode == 2
    assert "timed out" in result.stderr
    assert not state.exists()
    assert not (ledger / "scheduler-installation.json").exists()


def test_cron_readback_mismatch_rolls_back_and_fails(tmp_path):
    result, _, ledger, _, state = _install(
        tmp_path, "--backend", "cron", dry_run=False,
        env_update={"FAKE_CRONTAB_IGNORE_WRITE": "1"})
    assert result.returncode == 2
    assert "readback" in result.stderr
    assert not state.exists()
    assert not (ledger / "scheduler-installation.json").exists()


def test_launchd_auto_renders_loads_executes_and_uninstalls_exact_label(tmp_path):
    result, env, ledger, _, _ = _install(
        tmp_path, "--backend", "auto", dry_run=False,
        env_update={"ORGFORGE_PLATFORM": "darwin"})
    assert result.returncode == 0, result.stdout + result.stderr
    registry = json.loads((ledger / "scheduler-installation.json").read_text(encoding="utf-8"))
    assert registry["backend"] == "launchd"
    plist_path = Path(registry["plist"])
    plist = plistlib.loads(plist_path.read_bytes())
    assert plist["StartInterval"] == 1800
    assert plist["ProgramArguments"][1].endswith("orgforge-scheduler-tick")
    assert "--binding" in plist["ProgramArguments"]
    assert "--plugin-root" not in plist["ProgramArguments"]
    assert plist["EnvironmentVariables"]["ORG_ROLE"] == "supervisor"
    run = json.loads((ledger / "scheduler-state.json").read_text(encoding="utf-8"))
    assert run["status"] in {"ok", "escalate"} and run["receipt_seq"] is not None

    status = subprocess.run([str(STATUS), "--root", str(ledger)], text=True,
                            capture_output=True, env=env)
    assert status.returncode == 0, status.stdout + status.stderr
    assert json.loads(status.stdout)["definition_present"] is True

    unrelated = Path(env["ORGFORGE_LAUNCH_AGENTS_DIR"]) / "unrelated.plist"
    unrelated.write_text("keep", encoding="utf-8")
    removed = subprocess.run([str(UNINSTALL), "--root", str(ledger)], text=True,
                             capture_output=True, env=env)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert not plist_path.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert not (ledger / "scheduler-installation.json").exists()


def test_launchd_failed_reinstall_restores_prior_plist_and_loaded_service(tmp_path):
    first, env, ledger, _, _ = _install(
        tmp_path, "--backend", "launchd", dry_run=False)
    assert first.returncode == 0, first.stdout + first.stderr
    registry = json.loads((ledger / "scheduler-installation.json").read_text(encoding="utf-8"))
    plist_path = Path(registry["plist"])
    before = plist_path.read_bytes()
    second, _, _, _, _ = _install(
        tmp_path, "--backend", "launchd", "--tick-min", "15", dry_run=False,
        env_update={"FAKE_LAUNCHCTL_FAIL_KICKSTART": "1"})
    assert second.returncode == 2
    assert plist_path.read_bytes() == before
    launch_state = json.loads(Path(env["FAKE_LAUNCHCTL_STATE"]).read_text(encoding="utf-8"))
    assert registry["label"] in launch_state


def test_installed_command_follows_stable_binding_after_plugin_update(tmp_path):
    result, env, ledger, _, state = _install(
        tmp_path, "--backend", "cron", dry_run=False)
    assert result.returncode == 0, result.stdout + result.stderr
    registry = json.loads((ledger / "scheduler-installation.json").read_text(encoding="utf-8"))
    binding_path = Path(registry["binding"])
    binding = json.loads(binding_path.read_text(encoding="utf-8"))

    next_plugin = tmp_path / "plugin-v-next"
    shutil.copytree(PLUGIN, next_plugin)
    marker = tmp_path / "used-v-next"
    wrapper = next_plugin / "scripts" / "scheduler_tick.py"
    _executable(wrapper, f"""#!/usr/bin/env python3
import os
import pathlib
import sys
pathlib.Path({str(marker)!r}).write_text("yes", encoding="utf-8")
os.execv(sys.executable, [sys.executable, {str(TICK)!r}, *sys.argv[1:]])
""")
    binding["plugin_root"] = str(next_plugin)
    binding_path.write_text(json.dumps(binding), encoding="utf-8")

    line = next(line for line in state.read_text(encoding="utf-8").splitlines()
                if line.endswith("# orgforge:supervisor"))
    command = line.split(maxsplit=5)[5].removesuffix("  # orgforge:supervisor").replace("\\%", "%")
    executed = subprocess.run(["/bin/sh", "-c", command], text=True, capture_output=True, env=env)
    assert executed.returncode in (0, 10), executed.stdout + executed.stderr
    assert marker.read_text(encoding="utf-8") == "yes"


def test_stable_bootstrap_records_binding_failure_instead_of_leaving_stale_success(tmp_path):
    result, env, ledger, _, state = _install(
        tmp_path, "--backend", "cron", dry_run=False)
    assert result.returncode == 0, result.stdout + result.stderr
    registry = json.loads((ledger / "scheduler-installation.json").read_text(encoding="utf-8"))
    Path(registry["binding"]).write_text("{}", encoding="utf-8")
    line = next(line for line in state.read_text(encoding="utf-8").splitlines()
                if line.endswith("# orgforge:supervisor"))
    command = line.split(maxsplit=5)[5].removesuffix("  # orgforge:supervisor").replace("\\%", "%")
    executed = subprocess.run(["/bin/sh", "-c", command], text=True, capture_output=True, env=env)
    assert executed.returncode == 12
    run = json.loads((ledger / "scheduler-state.json").read_text(encoding="utf-8"))
    assert run["status"] == "error" and run["receipt_seq"] is None
    assert run["checks"][0]["name"] == "binding_preflight"
    status = subprocess.run([str(STATUS), "--root", str(ledger)], text=True,
                            capture_output=True, env=env)
    assert status.returncode == 10
    status_value = json.loads(status.stdout)
    assert status_value["healthy_run"] is False
    assert status_value["last_receipt"] is not None


def test_scheduler_tick_requires_receipt_even_when_commands_exit_zero(tmp_path):
    plugin = tmp_path / "plugin"
    shutil.copytree(PLUGIN, plugin)
    fake_host = plugin / "scripts" / "tick_host.py"
    _executable(fake_host, "#!/usr/bin/env python3\nraise SystemExit(0)\n")
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    result = subprocess.run(
        [sys.executable, str(plugin / "scripts" / "scheduler_tick.py"),
         "--root", str(ledger), "--plugin-root", str(plugin), "--now-min", "100",
         "--now", "2026-08-02T00:00:00Z"],
        text=True, capture_output=True,
    )
    assert result.returncode == 12
    assert "no tick_planned receipt" in result.stderr
    state = json.loads((ledger / "scheduler-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "error" and state["receipt_seq"] is None


def test_scheduler_tick_preflight_failure_overwrites_stale_success_state(tmp_path):
    plugin = tmp_path / "incomplete-plugin"
    plugin.mkdir()
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    state_path = ledger / "scheduler-state.json"
    state_path.write_text(json.dumps({"status": "ok", "receipt_seq": 99}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(TICK), "--root", str(ledger), "--plugin-root", str(plugin),
         "--now-min", "100", "--now", "2026-08-02T00:00:00Z"],
        text=True, capture_output=True,
    )
    assert result.returncode == 12
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "error" and state["receipt_seq"] is None
    assert state["checks"][0]["name"] == "preflight"


def test_scheduler_tick_bounds_a_hung_machine_check(tmp_path):
    plugin = tmp_path / "plugin"
    shutil.copytree(PLUGIN, plugin)
    fake_host = plugin / "scripts" / "tick_host.py"
    _executable(fake_host, "#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n")
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    env = {**os.environ, "ORGFORGE_TICK_CHECK_TIMEOUT": "0.1"}
    result = subprocess.run(
        [sys.executable, str(plugin / "scripts" / "scheduler_tick.py"),
         "--root", str(ledger), "--plugin-root", str(plugin), "--now-min", "100",
         "--now", "2026-08-02T00:00:00Z"],
        text=True, capture_output=True, env=env,
    )
    assert result.returncode == 12
    assert "tick_plan timed out" in result.stderr
    state = json.loads((ledger / "scheduler-state.json").read_text(encoding="utf-8"))
    assert any(check["name"] == "tick_plan" and check["returncode"] == 12
               for check in state["checks"])


def test_scheduler_tick_duplicate_minute_is_receipt_backed_and_idempotent(tmp_path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    command = [sys.executable, str(TICK), "--root", str(ledger), "--plugin-root", str(PLUGIN),
               "--now-min", "100", "--now", "2026-08-02T00:00:00Z"]
    first = subprocess.run(command, text=True, capture_output=True)
    second = subprocess.run(command, text=True, capture_output=True)
    assert first.returncode == second.returncode == 0
    events = [json.loads(line) for line in (ledger / "ledger.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert [event["class"] for event in events].count("tick_planned") == 1
    state = json.loads((ledger / "scheduler-state.json").read_text(encoding="utf-8"))
    assert state["receipt_seq"] == 3
    assert state["coverage"]["unattended"] == ["machine_sensors", "chain_verify"]
    assert len(state["check_receipts"]) == 2


def test_scheduler_check_receipts_keep_repeated_relative_cadence_healthy(tmp_path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    for now_min in (100, 130, 160, 190, 220):
        timestamp = dt.datetime.fromtimestamp(
            now_min * 60, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
        result = subprocess.run(
            [sys.executable, str(TICK), "--root", str(ledger), "--plugin-root", str(PLUGIN),
             "--now-min", str(now_min), "--now", timestamp],
            text=True, capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    events = [json.loads(line) for line in (ledger / "ledger.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert [event["class"] for event in events].count("scheduled_check_completed") == 10
    assert [event["class"] for event in events].count("tick_planned") == 5
    assert not [event for event in events if event["class"] in {"sensor_reading", "heartbeat"}]
    assert all(not (event.get("payload") or {}).get("missed")
               for event in events if event["class"] == "tick_planned")


def test_scheduler_gap_eventually_escalates_despite_current_run_receipts(tmp_path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    base = [sys.executable, str(TICK), "--root", str(ledger),
            "--plugin-root", str(PLUGIN)]
    first = subprocess.run(
        [*base, "--now-min", "100", "--now", "1970-01-01T01:40:00Z"],
        text=True, capture_output=True,
    )
    assert first.returncode == 0, first.stdout + first.stderr

    # Five 30-minute opportunities were skipped. The current run is receipted before planning,
    # but that one success cannot erase the missing windows.
    resumed = subprocess.run(
        [*base, "--now-min", "280", "--now", "1970-01-01T04:40:00Z"],
        text=True, capture_output=True,
    )
    assert resumed.returncode == 10
    assert "scheduled-check receipt window(s)" in resumed.stdout + resumed.stderr
    state = json.loads((ledger / "scheduler-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "escalate"
