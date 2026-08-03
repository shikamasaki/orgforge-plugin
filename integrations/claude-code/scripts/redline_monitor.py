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


def _instance_for(role, ledger_root=None):
    """Scope the logical identity to the org when a root is explicitly supplied."""
    base = f"redline-{_safe(role)}"
    if not ledger_root:
        return base
    digest = hashlib.sha256(str(Path(ledger_root).expanduser().resolve()).encode("utf-8")).hexdigest()[:12]
    return f"{base}-{digest}"


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


def process_table(runner=None):
    """Read (pid, command) rows from the process table; None means it could not be read."""
    run = runner or subprocess.run
    try:
        result = run(["ps", "-axo", "pid=,command="],
                     capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    rows = []
    for line in (result.stdout or "").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            rows.append((int(parts[0]), parts[1]))
    return rows


def _monitor_identity(command):
    """Return (role, instance) when a ps command line is a monitor WATCH loop, else None."""
    tokens = str(command or "").split()
    index = next((position for position, token in enumerate(tokens)
                  if Path(token).name.startswith("redline_monitor")), None)
    if index is None:
        return None
    if index > 0 and not Path(tokens[0]).name.lower().startswith("python"):
        return None                                   # grep/pkill/editor lines, not a monitor
    rest = tokens[index + 1:]
    if rest and rest[0] in {"status", "rearm-check", "stop"}:
        return None                                   # registry queries never own the instance
    role, instance, root = "", None, None
    if rest and not rest[0].startswith("-"):
        root = rest[0]
    position = 0
    while position < len(rest):
        token = rest[position]
        if token == "--role" and position + 1 < len(rest):
            role, position = rest[position + 1], position + 2
        elif token.startswith("--role="):
            role, position = token.split("=", 1)[1], position + 1
        elif token == "--instance" and position + 1 < len(rest):
            instance, position = rest[position + 1], position + 2
        elif token.startswith("--instance="):
            instance, position = token.split("=", 1)[1], position + 1
        else:
            position += 1
    role = role or "supervisor"
    return role, instance or _instance_for(role, root)


def unregistered_monitors(registry, role=None, instance=None, ps_rows=None, own_pid=None):
    """Live monitor processes matching this signature that have NO registry record (OBS-065)."""
    rows = process_table() if ps_rows is None else ps_rows
    if rows is None:
        return []
    recorded = set()
    for record in _load_records(registry):
        try:
            recorded.add(int(record.get("pid")))
        except (TypeError, ValueError):
            continue
    own = os.getpid() if own_pid is None else int(own_pid)
    found = []
    for pid, command in rows:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        if pid == own or pid in recorded:
            continue
        identity = _monitor_identity(command)
        if identity is None:
            continue
        process_role, process_instance = identity
        if (role and process_role != role) or (instance and process_instance != instance):
            continue
        found.append({"pid": pid, "role": process_role, "instance": process_instance,
                      "status": "unregistered", "command": str(command)})
    return sorted(found, key=lambda process: process["pid"])


_PS_UNCHECKED = object()  # library default: pure registry view (resilience_exercise, older callers)
_PS_NOTE = "process table unavailable — unregistered-monitor cross-check skipped"


def _cross_check(registry, role, instance, ps_rows):
    """Resolve the injected ps source into (unregistered rows, optional caveat note)."""
    if ps_rows is _PS_UNCHECKED:
        return [], None
    if ps_rows is None:
        return [], _PS_NOTE
    return unregistered_monitors(registry, role=role, instance=instance, ps_rows=ps_rows), None


def report_status(registry, current_version, now=None, stale_after=180, pid_alive=None,
                  role=None, instance=None, ps_rows=_PS_UNCHECKED):
    rows = _selected(monitor_status(registry, current_version, now, stale_after, pid_alive),
                     role, instance)
    unregistered, note = _cross_check(registry, role, instance, ps_rows)
    active = [row for row in rows if row["status"] in {"live", "stale"}]
    attention = [row for row in active
                 if row["status"] == "stale" or row["duplicate"] or row["old_version"]]
    if not active and unregistered:
        print("MONITOR ATTENTION — unregistered live monitor process; "
              "no registry record, so cooperative stop cannot reach it")
        code = 4
    elif not active:
        print("MONITOR ABSENT — no live heartbeat; rearm-check may authorize a new instance")
        code = 3
    elif attention or unregistered:
        print("MONITOR ATTENTION — stale, duplicate, orphaned, old-version, "
              "or unregistered instance detected")
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
    for process in unregistered:
        print(f"  pid={process['pid']} status=unregistered role={process['role']} "
              f"instance={process['instance']} — no registry record; token-bound stop "
              f"unavailable; command: {process['command']}")
    if note:
        print(f"  note: {note}")
    return code


def rearm_check(registry, current_version, now=None, stale_after=180, pid_alive=None,
                role=None, instance=None, ps_rows=_PS_UNCHECKED):
    rows = _selected(monitor_status(registry, current_version, now, stale_after, pid_alive),
                     role, instance)
    unregistered, note = _cross_check(registry, role, instance, ps_rows)
    active = [row for row in rows if row["status"] in {"live", "stale"}]
    if active or unregistered:
        print("DO NOT REARM — a live process still owns this logical monitor instance")
        for row in active:
            print(f"  {row['record_id']} status={row['status']} version={row.get('plugin_version')}"
                  f"; stop exactly this record with: redline_monitor.py stop {row['record_id']}")
        for process in unregistered:
            print(f"  pid={process['pid']} status=unregistered — live monitor with no registry "
                  f"record owns {process['instance']}; cooperative stop unavailable; "
                  f"command: {process['command']}")
        return 4
    print("READY TO ARM — no live process owns this logical monitor instance")
    if note:
        print(f"  note: {note}")
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
                                 role=args.role, instance=args.instance,
                                 ps_rows=process_table())
        return rearm_check(registry, version, stale_after=args.stale_after,
                           role=args.role, instance=args.instance,
                           ps_rows=process_table())

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
    instance = args.instance or _instance_for(role, args.root)
    try:
        # Fail closed (OBS-065): a monitor that cannot register would be invisible to
        # status/stop and would later trick rearm-check into authorizing a duplicate.
        record = register_heartbeat(
            registry, role=role, instance=instance, version=plugin_version(),
            ledger_root=args.root, interval=args.interval)
    except OSError as exc:
        print(f"REFUSING TO START — could not write the monitor registry record under "
              f"{registry} ({type(exc).__name__}: {exc}); an unregistered monitor cannot be "
              f"seen by status or stopped cooperatively", file=sys.stderr)
        return 3
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
