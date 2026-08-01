#!/usr/bin/env python3
"""Emit Claude Monitor notifications only when the org's RED signal changes.

``status.py redline`` intentionally remains a stateless probe. This long-lived adapter retains the
previous probe output in memory: the first RED and each changed RED are emitted, identical REDs are
quiet, and GREEN resets the state so a later recurrence is emitted again.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid


_RECORD_SUFFIX = ".json"
_STOP_SUFFIX = ".stop.json"


def _now():
    return time.time()


def _safe(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "monitor")).strip("-.") or "monitor"


def _atomic_json(path, value):
    """Write one registry fact atomically so status never observes a partial heartbeat."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def plugin_version(script_path=None):
    """Read the version of the installed projection executing this monitor."""
    override = os.environ.get("ORGFORGE_PLUGIN_VERSION")
    if override:
        return override
    start = Path(script_path or __file__).resolve()
    for parent in (start.parent, *start.parents):
        for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            manifest = parent / relative
            try:
                value = json.loads(manifest.read_text(encoding="utf-8")).get("version")
                if value:
                    return str(value)
            except (OSError, ValueError, TypeError):
                continue
    return "development"


def registry_root(root=None, status_script=None):
    """Resolve host-independent monitor state next to the authoritative ledger."""
    override = os.environ.get("ORG_MONITOR_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    ledger = Path(root).expanduser().resolve() if root else None
    if ledger is None:
        tools = Path(status_script or __file__).resolve().parent
        if tools.name == "scripts":
            tools = tools.parent / "tools"
        try:
            sys.path.insert(0, str(tools))
            import discover
            found = discover.ledger_root()
            ledger = Path(found).resolve() if found else None
        except Exception:
            ledger = None
    if ledger is None:
        return None
    if ledger.name == "ledger" and ledger.parent.name == ".orgforge":
        return ledger.parent / "runtime" / "monitors"
    digest = hashlib.sha256(str(ledger).encode("utf-8")).hexdigest()[:12]
    return ledger.parent / f".orgforge-monitors-{digest}"


def _record_path(registry, record_id):
    return Path(registry) / f"{_safe(record_id)}{_RECORD_SUFFIX}"


def _stop_path(registry, record_id):
    return Path(registry) / f"{_safe(record_id)}{_STOP_SUFFIX}"


def register_heartbeat(registry, role, instance, version, pid=None, now=None, token=None,
                       ledger_root=None, interval=60):
    """Create a process-unique record while retaining a stable logical instance identity."""
    now = _now() if now is None else float(now)
    pid = os.getpid() if pid is None else int(pid)
    token = str(token or uuid.uuid4().hex)
    record_id = f"{_safe(instance)}-{pid}-{_safe(token)}"
    record = {
        "schema": 1,
        "record_id": record_id,
        "token": token,
        "role": str(role or "supervisor"),
        "instance": str(instance),
        "pid": pid,
        "plugin_version": str(version),
        "ledger_root": str(ledger_root or ""),
        "interval_seconds": float(interval),
        "started_at_unix": now,
        "heartbeat_at_unix": now,
        "poll_count": 0,
        "last_signal": "starting",
        "state": "running",
    }
    _atomic_json(_record_path(registry, record_id), record)
    return record


def touch_heartbeat(registry, record, signal, now=None):
    now = _now() if now is None else float(now)
    record.update({
        "heartbeat_at_unix": now,
        "poll_count": int(record.get("poll_count", 0)) + 1,
        "last_signal": "red" if str(signal or "").strip() else "healthy-silence",
        "state": "running",
    })
    _atomic_json(_record_path(registry, record["record_id"]), record)
    return record


def mark_stopped(registry, record, now=None):
    record.update({"heartbeat_at_unix": _now() if now is None else float(now),
                   "state": "stopped"})
    _atomic_json(_record_path(registry, record["record_id"]), record)
    try:
        _stop_path(registry, record["record_id"]).unlink()
    except OSError:
        pass
    return record


def _load_records(registry):
    out = []
    directory = Path(registry)
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob(f"*{_RECORD_SUFFIX}")):
        if path.name.endswith(_STOP_SUFFIX):
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(row, dict) and row.get("record_id"):
                out.append(row)
        except (OSError, ValueError, TypeError):
            continue
    return out


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False


def monitor_status(registry, current_version, now=None, stale_after=180, pid_alive=None):
    """Classify registry records without consulting Claude/Codex host task metadata."""
    now = _now() if now is None else float(now)
    alive = pid_alive or _pid_alive
    rows = []
    for record in _load_records(registry):
        row = dict(record)
        if row.get("state") == "stopped":
            status = "stopped"
        elif not alive(row.get("pid")):
            status = "dead"
        elif now - float(row.get("heartbeat_at_unix", 0)) > max(
                float(stale_after), float(row.get("interval_seconds", 0)) * 3):
            status = "stale"
        else:
            status = "live"
        row["status"] = status
        row["old_version"] = str(row.get("plugin_version")) != str(current_version)
        row["duplicate"] = False
        row["orphaned"] = False
        rows.append(row)

    groups = {}
    for row in rows:
        if row["status"] in {"live", "stale"}:
            groups.setdefault((row.get("role"), row.get("instance")), []).append(row)
    for members in groups.values():
        current = [row for row in members if not row["old_version"]]
        primary = max(current or members, key=lambda row: float(row.get("heartbeat_at_unix", 0)))
        duplicate = len(members) > 1
        for row in members:
            row["duplicate"] = duplicate
            row["orphaned"] = row["old_version"] or (duplicate and row is not primary)
    return sorted(rows, key=lambda row: (str(row.get("role")), str(row.get("instance")),
                                         str(row.get("record_id"))))


def request_stop(registry, record_id):
    """Request cooperative stop for exactly one token; never signal an arbitrary PID."""
    record = next((row for row in _load_records(registry)
                   if row.get("record_id") == record_id), None)
    if record is None:
        return False
    _atomic_json(_stop_path(registry, record_id), {
        "record_id": record_id, "token": record.get("token"), "requested_at_unix": _now()})
    return True


def stop_requested(registry, record):
    try:
        request = json.loads(_stop_path(registry, record["record_id"]).read_text(encoding="utf-8"))
        return (request.get("record_id") == record.get("record_id")
                and request.get("token") == record.get("token"))
    except (OSError, ValueError, TypeError):
        return False


def _selected(rows, role=None, instance=None):
    return [row for row in rows
            if (not role or row.get("role") == role)
            and (not instance or row.get("instance") == instance)]


def report_status(registry, current_version, now=None, stale_after=180, pid_alive=None,
                  role=None, instance=None):
    rows = _selected(monitor_status(registry, current_version, now, stale_after, pid_alive),
                     role, instance)
    active = [row for row in rows if row["status"] in {"live", "stale"}]
    attention = [row for row in active
                 if row["status"] == "stale" or row["duplicate"] or row["old_version"]]
    if not active:
        print("MONITOR ABSENT — no live heartbeat; rearm-check may authorize a new instance")
        code = 3
    elif attention:
        print("MONITOR ATTENTION — stale, duplicate, orphaned, or old-version instance detected")
        code = 4
    else:
        print("MONITOR READY — one current live instance")
        code = 0
    for row in rows:
        flags = [name for name in ("duplicate", "orphaned", "old_version") if row.get(name)]
        suffix = f" flags={','.join(flags)}" if flags else ""
        print(f"  {row['record_id']} status={row['status']} pid={row.get('pid')} "
              f"version={row.get('plugin_version')} role={row.get('role')} "
              f"instance={row.get('instance')}{suffix}")
    return code


def rearm_check(registry, current_version, now=None, stale_after=180, pid_alive=None,
                role=None, instance=None):
    rows = _selected(monitor_status(registry, current_version, now, stale_after, pid_alive),
                     role, instance)
    active = [row for row in rows if row["status"] in {"live", "stale"}]
    if active:
        print("DO NOT REARM — a live/stale process still owns this logical monitor instance")
        for row in active:
            print(f"  {row['record_id']} status={row['status']} version={row.get('plugin_version')}"
                  f"; stop exactly this record with: redline_monitor.py stop {row['record_id']}")
        return 4
    print("READY TO ARM — no live process owns this logical monitor instance")
    return 0


def probe(status_script, root=None, role=""):
    """Run one stateless redline probe and turn probe failures into a deduplicated RED signal."""
    command = [sys.executable, str(status_script), "redline"]
    if root:
        command.append(str(root))
    if role:
        command.extend(["--role", role])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "RED — org monitor probe timed out after 30 seconds"
    except OSError as exc:
        return f"RED — org monitor probe could not start ({type(exc).__name__}): {exc}"
    output = (result.stdout or "").strip()
    if result.returncode == 0:
        return output
    detail = " ".join(((result.stderr or output or "no diagnostic").strip()).split())[:300]
    return f"RED — org monitor probe failed (exit {result.returncode}): {detail}"


def watch(run_probe, interval=60, max_polls=None, output=None, sleeper=time.sleep,
          on_poll=None, should_stop=None):
    """Poll until stopped, emitting only non-empty transitions. Returns the number of polls."""
    output = output or sys.stdout
    previous = None
    polls = 0
    while max_polls is None or polls < max_polls:
        if should_stop and should_stop():
            break
        current = (run_probe() or "").strip()
        if on_poll:
            on_poll(current)
        if current and current != previous:
            print(current, file=output, flush=True)
        previous = current
        polls += 1
        if max_polls is None or polls < max_polls:
            sleeper(interval)
    return polls


def _registry_parser(command):
    parser = argparse.ArgumentParser(prog=f"redline_monitor.py {command}")
    if command == "stop":
        parser.add_argument("record_id")
        parser.add_argument("--root", help="ledger root (when cwd cannot discover the org)")
    else:
        parser.add_argument("root", nargs="?", help="ledger root")
        parser.add_argument("--role")
        parser.add_argument("--instance")
        parser.add_argument("--stale-after", type=float, default=180)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--status-script", type=Path,
                        default=Path(__file__).resolve().parents[1] / "tools" / "status.py",
                        help=argparse.SUPPRESS)
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"status", "rearm-check", "stop"}:
        command = argv.pop(0)
        parser = _registry_parser(command)
        args = parser.parse_args(argv)
        root = getattr(args, "root", None)
        registry = args.registry or registry_root(root, args.status_script)
        if registry is None:
            parser.error("could not discover the monitor registry; pass a ledger root or --registry")
        version = plugin_version()
        if command == "stop":
            if not request_stop(registry, args.record_id):
                print(f"monitor record not found: {args.record_id}", file=sys.stderr)
                return 3
            print(f"stop requested for {args.record_id}; no PID signal was sent")
            return 0
        if args.stale_after <= 0:
            parser.error("--stale-after must be greater than zero")
        if command == "status":
            return report_status(registry, version, stale_after=args.stale_after,
                                 role=args.role, instance=args.instance)
        return rearm_check(registry, version, stale_after=args.stale_after,
                           role=args.role, instance=args.instance)

    parser = argparse.ArgumentParser(
        description="Watch status.py redline and emit only RED transitions/changes.")
    parser.add_argument("root", nargs="?", help="ledger root (status.py auto-discovers when omitted)")
    parser.add_argument("--role", default="")
    parser.add_argument("--instance", help="stable logical identity (default: redline-ROLE)")
    parser.add_argument("--registry", type=Path, help="monitor heartbeat registry")
    parser.add_argument("--interval", type=float, default=60, help="poll interval in seconds")
    parser.add_argument("--max-polls", type=int, help="stop after N polls (diagnostics/tests)")
    parser.add_argument(
        "--status-script", type=Path,
        default=Path(__file__).resolve().parents[1] / "tools" / "status.py",
        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.interval <= 0:
        parser.error("--interval must be greater than zero")
    if args.max_polls is not None and args.max_polls <= 0:
        parser.error("--max-polls must be greater than zero")
    registry = args.registry or registry_root(args.root, args.status_script)
    if registry is None:
        parser.error("could not discover the monitor registry; pass a ledger root or --registry")
    role = args.role or "supervisor"
    instance = args.instance or f"redline-{_safe(role)}"
    record = register_heartbeat(
        registry, role=role, instance=instance, version=plugin_version(),
        ledger_root=args.root, interval=args.interval)
    try:
        watch(lambda: probe(args.status_script, args.root, args.role),
              interval=args.interval, max_polls=args.max_polls,
              on_poll=lambda signal: touch_heartbeat(registry, record, signal),
              should_stop=lambda: stop_requested(registry, record))
    except KeyboardInterrupt:
        mark_stopped(registry, record)
        return 130
    finally:
        if record.get("state") != "stopped":
            mark_stopped(registry, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
