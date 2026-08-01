#!/usr/bin/env python3
"""Run OrgForge's unattended machine tick without invoking an LLM or a slash command.

This is a host adapter, not an OrgForge runtime: the OS scheduler owns the clock and invokes this
process once.  The adapter executes the same deterministic observations used by ``/org-tick``,
persists the ``tick_planned`` receipt through ``tick_host.py``, and writes an atomic run-state file
so a process exit code cannot masquerade as a successful tick.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid


OK = 0
ESCALATE = 10
BROKEN = 12

_UNATTENDED = {
    "machine_sensors": ("sensors.py", "eval"),
    "chain_verify": ("ledger.py", "verify"),
}


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _events(root: Path) -> list[dict]:
    path = root / "ledger.jsonl"
    if not path.is_file():
        return []
    events = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def _receipt(events: list[dict], now_min: int) -> dict | None:
    matches = [event for event in events
               if event.get("class") == "tick_planned"
               and (event.get("payload") or {}).get("now_min") == now_min]
    return matches[-1] if matches else None


def _check_timeout() -> float:
    try:
        value = float(os.environ.get("ORGFORGE_TICK_CHECK_TIMEOUT", "60"))
    except ValueError:
        return 60.0
    return value if value > 0 else 60.0


def _run(name: str, command: list[str], results: list[dict]) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=_check_timeout())
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        message = f"scheduler_tick: {name} timed out after {_check_timeout():g}s"
        print(message, file=sys.stderr)
        completed = subprocess.CompletedProcess(command, BROKEN, stdout, stderr + message + "\n")
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    results.append({"name": name, "returncode": completed.returncode})
    return completed


def _payload_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _append_command(tools: Path, root: Path, append_args: list[str]) -> list[str]:
    if os.environ.get("ORG_WRITER_SOCKET"):
        return [sys.executable, str(tools / "writer_client.py"),
                "record-scheduled-check", "--", *append_args]
    return [sys.executable, str(tools / "ledger.py"), "record-scheduled-check", str(root),
            *append_args]


def _check_receipt(events: list[dict], check_id: str, now_min: int,
                   execution_id: str) -> dict | None:
    matches = [event for event in events
               if event.get("class") == "scheduled_check_completed"
               and (event.get("payload") or {}).get("check_id") == check_id
               and (event.get("payload") or {}).get("scheduled_for_min") == now_min
               and (event.get("payload") or {}).get("execution_id") == execution_id]
    return matches[-1] if matches else None


def _persist_check_receipt(*, tools: Path, root: Path, check_id: str, now_min: int,
                           command: list[str], returncode: int,
                           plugin_version: str) -> tuple[dict | None, str | None]:
    # Cache roots change on plugin update and tests deliberately relocate an otherwise identical
    # bundle. Hash the installed command shape, not its ephemeral absolute cache prefix.
    plugin_root = str(tools.parent)
    canonical_command = ["$PLUGIN_ROOT" + item[len(plugin_root):]
                         if item.startswith(plugin_root + os.sep) else item
                         for item in command]
    command_sha256 = _payload_digest(canonical_command)
    execution_id = _payload_digest({"check_id": check_id, "scheduled_for_min": now_min,
                                    "command_sha256": command_sha256})[:24]
    payload = {
        "check_id": check_id,
        "scheduled_for_min": now_min,
        "execution_id": execution_id,
        "result": "ok" if returncode == OK else "escalate",
        "exit_code": returncode,
        "command_sha256": command_sha256,
        "plugin_version": plugin_version,
    }
    append_args = ["--check-id", check_id, "--scheduled-for-min", str(now_min),
                   "--execution-id", execution_id, "--result", payload["result"],
                   "--exit-code", str(returncode), "--command-sha256", command_sha256,
                   "--plugin-version", plugin_version]
    appended = subprocess.run(_append_command(tools, root, append_args), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=_check_timeout())
    if appended.returncode != OK:
        detail = ((appended.stdout or "") + (appended.stderr or "")).strip()
        return None, (f"could not persist {check_id} receipt (exit {appended.returncode}): "
                      f"{detail[:500]}")
    receipt = _check_receipt(_events(root), check_id, now_min, execution_id)
    if receipt is None:
        return None, f"no exact {check_id} receipt readback for now_min={now_min}"
    return receipt, None


def _load_schedule(path: Path) -> dict:
    import yaml
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("checks"), list):
        raise ValueError(f"invalid schedule: {path}")
    return value


def _coverage(schedule: dict) -> tuple[list[str], list[str]]:
    clock = [str(check.get("id")) for check in schedule.get("checks", [])
             if isinstance(check, dict) and str(check.get("cadence") or "").startswith("every_")]
    return ([check_id for check_id in clock if check_id in _UNATTENDED],
            [check_id for check_id in clock if check_id not in _UNATTENDED])


def _overall(results: list[dict]) -> int:
    errors = [item["returncode"] for item in results
              if item["returncode"] not in (OK, ESCALATE)]
    if errors:
        return errors[0]
    if any(item["returncode"] == ESCALATE for item in results):
        return ESCALATE
    return OK


def _wip(stdout: str) -> list[dict]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    value = parsed.get("in_progress", []) if isinstance(parsed, dict) else []
    return [item for item in value if isinstance(item, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scheduler_tick", description=__doc__)
    parser.add_argument("--root", required=True, help="ledger root")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plugin-root", help="installed Claude Code plugin root (tests/manual use)")
    source.add_argument("--binding", help="stable installed-organ binding resolved on every run")
    parser.add_argument("--now-min", type=int)
    parser.add_argument("--now", help="UTC ISO timestamp for deterministic tests")
    parser.add_argument("--night", action="store_true")
    parser.add_argument("--state-file")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    binding_path = Path(args.binding).expanduser().resolve() if args.binding else None
    binding = None
    if binding_path:
        try:
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"scheduler_tick: installed-organ binding is unreadable: {binding_path}: {exc}",
                  file=sys.stderr)
            return BROKEN
        if not isinstance(binding, dict) or binding.get("schema") != "orgforge-installed-organ/v1":
            print(f"scheduler_tick: unsupported installed-organ binding: {binding_path}",
                  file=sys.stderr)
            return BROKEN
        plugin_root = Path(str(binding.get("plugin_root") or "")).expanduser().resolve()
    else:
        plugin_root = Path(args.plugin_root).expanduser().resolve()
    tools = plugin_root / "tools"
    scripts = plugin_root / "scripts"
    template = plugin_root / "template"
    state_file = (Path(args.state_file).expanduser().resolve() if args.state_file else
                  root / "scheduler-state.json")
    now = dt.datetime.now(dt.timezone.utc)
    now_min = args.now_min if args.now_min is not None else int(now.timestamp() // 60)
    # Bind repeated invocations in one scheduler minute to the same logical command.  Wall-clock
    # seconds are not part of the cadence identity and made an install smoke + immediate kick use
    # the same natural key with different payloads.
    scheduled_time = dt.datetime.fromtimestamp(now_min * 60, tz=dt.timezone.utc)
    now_iso = args.now or scheduled_time.isoformat().replace("+00:00", "Z")
    run_id = args.run_id or uuid.uuid4().hex

    def preflight_error(message: str) -> int:
        print(message, file=sys.stderr)
        _atomic_json(state_file, {
            "schema": "orgforge-scheduler-run/v1", "run_id": run_id, "status": "error",
            "started_at": now_iso, "finished_at": now_iso, "now_min": now_min,
            "exit_code": BROKEN, "pid": os.getpid(), "python": sys.executable,
            "plugin_root": str(plugin_root), "binding": str(binding_path) if binding_path else None,
            "checks": [
                {"name": "preflight", "returncode": BROKEN, "error": message}],
            "receipt_seq": None, "receipt_hash": None,
        })
        return BROKEN

    org_root = (Path(str(binding.get("org_root"))).expanduser().resolve()
                if binding and binding.get("org_root") else None)
    schedule_path = (org_root / "schedule.yaml" if org_root and
                     (org_root / "schedule.yaml").is_file() else template / "schedule.yaml")
    required = [scripts / "tick_host.py", tools / "sensors.py", tools / "ledger.py",
                tools / "guardrails.py", tools / "learning.py", tools / "conventions.py",
                schedule_path, template / "sensors.yaml"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return preflight_error(
            "scheduler_tick: installed plugin is incomplete: " + ", ".join(missing))
    try:
        import yaml  # noqa: F401  # ledger validation needs the same interpreter dependency
    except ImportError:
        return preflight_error(
            f"scheduler_tick: {sys.executable} cannot import PyYAML; refusing to misreport "
            "dependency failure as ledger corruption")
    try:
        schedule = _load_schedule(schedule_path)
        covered_checks, attended_only_checks = _coverage(schedule)
    except (OSError, ValueError) as exc:
        return preflight_error(f"scheduler_tick: schedule preflight failed: {exc}")
    if not covered_checks:
        return preflight_error(
            "scheduler_tick: schedule declares no clock check supported by the unattended "
            "adapter; refusing a scheduler that would prove no work")

    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    try:
        plugin_version = str(json.loads(manifest_path.read_text(encoding="utf-8"))["version"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return preflight_error(f"scheduler_tick: plugin version is unreadable: {exc}")

    started = now_iso
    _atomic_json(state_file, {
        "schema": "orgforge-scheduler-run/v1", "run_id": run_id, "status": "running",
        "started_at": started, "now_min": now_min, "pid": os.getpid(),
        "python": sys.executable, "plugin_root": str(plugin_root),
        "binding": str(binding_path) if binding_path else None,
    })

    results: list[dict] = []
    commands = {
        "machine_sensors": [sys.executable, str(tools / "sensors.py"), "eval", str(root),
                            str(template / "sensors.yaml"), "--now", now_iso],
        "chain_verify": [sys.executable, str(tools / "ledger.py"), "verify", str(root)],
    }
    check_receipts = []
    for check_id in covered_checks:
        command = commands[check_id]
        completed = _run(check_id, command, results)
        if completed.returncode not in (OK, ESCALATE):
            continue
        try:
            receipt, error = _persist_check_receipt(
                tools=tools, root=root, check_id=check_id, now_min=now_min,
                command=command, returncode=completed.returncode, plugin_version=plugin_version)
        except subprocess.TimeoutExpired:
            receipt, error = None, f"{check_id} receipt append timed out"
        if error:
            print(f"scheduler_tick: {error}", file=sys.stderr)
            results.append({"name": f"receipt:{check_id}", "returncode": BROKEN})
        elif receipt:
            check_receipts.append({"check_id": check_id, "seq": receipt.get("seq"),
                                   "hash": receipt.get("hash")})

    tick_command = [sys.executable, str(scripts / "tick_host.py"), str(schedule_path),
                    "--root", str(root), "--now-min", str(now_min), "--verbose"]
    for check_id in covered_checks:
        tick_command.extend(["--only-check", check_id, "--receipt-check", check_id])
    if args.night:
        tick_command.append("--night")
    _run("tick_plan", tick_command, results)
    view = _run("work_in_progress", [sys.executable, str(tools / "ledger.py"), "view",
                                      str(root), "work_in_progress"], results)
    if view.returncode == OK:
        for item in _wip(view.stdout):
            candidate_id = str(item.get("candidate_id") or "")
            if not candidate_id:
                continue
            command = [sys.executable, str(tools / "guardrails.py"), "stall", str(root),
                       "--candidate-id", candidate_id]
            role = str(item.get("role") or "")
            if role:
                command.extend(["--role", role])
            _run(f"stall:{candidate_id}", command, results)
    _run("learning_repeats", [sys.executable, str(tools / "learning.py"), "repeats",
                               str(root)], results)
    _run("conventions_growth", [sys.executable, str(tools / "conventions.py"), "growth",
                                 str(root)], results)

    receipt = _receipt(_events(root), now_min)
    if receipt is None:
        print(f"scheduler_tick: no tick_planned receipt for now_min={now_min}; exit status alone "
              "is not proof that the tick ran", file=sys.stderr)
        results.append({"name": "receipt", "returncode": BROKEN})
    code = _overall(results)
    finished = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")
    state = {
        "schema": "orgforge-scheduler-run/v1", "run_id": run_id,
        "status": "ok" if code == OK else ("escalate" if code == ESCALATE else "error"),
        "started_at": started, "finished_at": finished, "now_min": now_min,
        "exit_code": code, "pid": os.getpid(), "python": sys.executable,
        "plugin_root": str(plugin_root), "binding": str(binding_path) if binding_path else None,
        "checks": results,
        "coverage": {"unattended": covered_checks, "attended_only": attended_only_checks},
        "check_receipts": check_receipts,
        "receipt_seq": receipt.get("seq") if receipt else None,
        "receipt_hash": receipt.get("hash") if receipt else None,
    }
    _atomic_json(state_file, state)
    print("SCHEDULER-RESULT " + json.dumps(state, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
