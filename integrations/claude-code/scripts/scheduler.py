#!/usr/bin/env python3
"""Install, inspect, and remove OrgForge's host-owned unattended machine tick."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


OK = 0
ESCALATE = 10
BROKEN = 12
SCHEMA = "orgforge-scheduler-installation/v1"


class SchedulerError(RuntimeError):
    pass


def _timeout() -> float:
    try:
        value = float(os.environ.get("ORGFORGE_SCHEDULER_TIMEOUT", "15"))
    except ValueError as exc:
        raise SchedulerError("ORGFORGE_SCHEDULER_TIMEOUT must be numeric") from exc
    if value <= 0:
        raise SchedulerError("scheduler timeout must be positive")
    return value


def _run(command: list[str], *, input_text: str | None = None,
         check: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, input=input_text, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=_timeout())
    except subprocess.TimeoutExpired as exc:
        raise SchedulerError(f"command timed out after {_timeout():g}s: {shlex.join(command)}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SchedulerError(f"command failed ({result.returncode}): {shlex.join(command)}"
                             + (f"\n{detail}" if detail else ""))
    return result


def _atomic_bytes(path: Path, content: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _atomic_json(path: Path, value: dict) -> None:
    _atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
                         + "\n").encode("utf-8"))


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _last_tick_receipt(root: Path) -> dict | None:
    path = root / "ledger.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") if isinstance(event, dict) else None
        if event.get("class") == "tick_planned" and isinstance(payload, dict):
            return {"seq": event.get("seq"), "hash": event.get("hash"),
                    "now_min": payload.get("now_min"), "ts": event.get("ts")}
    return None


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _role(value: str) -> str:
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
                        for char in value):
        raise argparse.ArgumentTypeError(
            "role must contain only letters, digits, dot, underscore, or hyphen")
    return value


def _positive_int(value: str) -> int:
    if not value.isdigit() or value.startswith("0"):
        raise argparse.ArgumentTypeError("interval must be a positive base-10 integer")
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("interval must be positive")
    return parsed


def _backend(value: str) -> str:
    if value not in {"auto", "cron", "launchd"}:
        raise argparse.ArgumentTypeError("backend must be auto, cron, or launchd")
    return value


def _resolve_backend(requested: str) -> str:
    if requested != "auto":
        return requested
    platform = os.environ.get("ORGFORGE_PLATFORM", sys.platform)
    return "launchd" if platform == "darwin" else "cron"


def _cycles(value: str) -> list[str]:
    requested = value.split(",")
    if not value or any(not item for item in requested):
        raise SchedulerError("cycles must not contain an empty item")
    if len(set(requested)) != len(requested):
        raise SchedulerError("cycles contains a duplicate item")
    unknown = [item for item in requested if item not in {"tick", "work", "discover"}]
    if unknown:
        raise SchedulerError(f"unknown cycles item: {', '.join(unknown)}")
    acting = [item for item in requested if item != "tick"]
    if acting:
        raise SchedulerError(
            "persistent headless cycles currently support only 'tick'; "
            f"{','.join(acting)} requires an attended harness loop. Refusing a silent no-op.")
    return requested


def _python(explicit: str | None) -> str:
    candidates = [explicit, os.environ.get("ORG_PYTHON"), sys.executable,
                  "/usr/bin/python3", shutil.which("python3")]
    seen = set()
    failures = []
    for candidate in candidates:
        if not candidate:
            continue
        resolved = str(Path(candidate).expanduser())
        if resolved in seen or not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
            continue
        seen.add(resolved)
        result = _run([resolved, "-c", "import yaml; print(yaml.__version__)"])
        if result.returncode == 0:
            return resolved
        failures.append(f"{resolved}: {(result.stderr or result.stdout).strip() or 'PyYAML unavailable'}")
    raise SchedulerError("no Python interpreter with PyYAML is available; set --python or ORG_PYTHON"
                         + ("\n" + "\n".join(failures) if failures else ""))


def _slug(workdir: Path) -> str:
    raw = workdir.name.lower()
    cleaned = "".join(char if char.isalnum() else "-" for char in raw).strip("-")
    return cleaned[:32] or "org"


def _safe_path(path: Path, name: str) -> Path:
    value = str(path)
    if "\n" in value or "\r" in value:
        raise SchedulerError(f"{name} must not contain a newline")
    return path


def _label(workdir: Path, role: str) -> str:
    digest = hashlib.sha256(str(workdir).encode("utf-8")).hexdigest()[:8]
    return f"com.orgforge.{_slug(workdir)}.{role}.tick.{digest}"


def _paths(root: Path) -> tuple[Path, Path, Path]:
    return (root / "scheduler.log", root / "scheduler.err.log",
            root / "scheduler-state.json")


def _binding(workdir: Path, plugin_root: Path) -> Path:
    override = os.environ.get("ORG_INSTALLED_ORGAN_BINDING")
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(workdir / ".git" / "orgforge" / "runtime" / "claude-code"
                      / "installed-organ.json")
    git = shutil.which("git")
    if git:
        result = _run([git, "-C", str(workdir), "rev-parse", "--git-common-dir"])
        if result.returncode == 0 and result.stdout.strip():
            common = Path(result.stdout.strip())
            if not common.is_absolute():
                common = workdir / common
            candidates.append(common / "orgforge" / "runtime" / "claude-code"
                              / "installed-organ.json")
    expected_version = None
    manifest = _read_json(plugin_root / ".claude-plugin" / "plugin.json")
    if manifest:
        expected_version = manifest.get("version")
    for candidate in candidates:
        path = candidate.resolve()
        value = _read_json(path)
        if not value or value.get("schema") != "orgforge-installed-organ/v1":
            continue
        bound_root = Path(str(value.get("plugin_root") or "")).expanduser().resolve()
        if not bound_root.is_dir():
            continue
        if expected_version and value.get("version") != expected_version:
            raise SchedulerError(
                f"installed-organ binding is version {value.get('version')!r}, expected "
                f"{expected_version!r}; restart the host session after updating the plugin")
        launcher = path.parent / "bin" / "orgforge"
        if not launcher.is_file():
            raise SchedulerError(f"installed-organ launcher is unavailable: {launcher}")
        return path
    raise SchedulerError(
        "installed-organ binding is unavailable; restart a Claude Code session in the org before "
        "installing the scheduler")


def _runner_command(python: str, binding: Path, root: Path,
                    state_file: Path | None = None, run_id: str | None = None) -> list[str]:
    bootstrap = binding.parent / "bin" / "orgforge-scheduler-tick"
    command = [python, str(bootstrap), "--root", str(root), "--binding", str(binding)]
    if state_file:
        command.extend(["--state-file", str(state_file)])
    if run_id:
        command.extend(["--run-id", run_id])
    return command


def _smoke(python: str, binding: Path, root: Path) -> dict:
    smoke_state = root / "scheduler-state.json"
    run_id = f"smoke-{uuid.uuid4().hex}"
    result = _run(_runner_command(python, binding, root, smoke_state, run_id))
    state = _read_json(smoke_state)
    if result.returncode not in (OK, ESCALATE) or not state:
        detail = (result.stderr or result.stdout).strip()
        raise SchedulerError("machine tick smoke test failed"
                             + (f": {detail[-1000:]}" if detail else ""))
    if state.get("run_id") != run_id or state.get("receipt_seq") is None:
        raise SchedulerError("machine tick smoke test produced no bound tick receipt")
    return state


def _cron_command(python: str, binding: Path, root: Path, workdir: Path,
                  role: str) -> str:
    stdout, stderr, _ = _paths(root)
    env = f"ORG_LEDGER_ROOT={shlex.quote(str(root))} ORG_ROLE={shlex.quote(role)}"
    runner = " ".join(shlex.quote(item) for item in _runner_command(python, binding, root))
    command = (f"cd {shlex.quote(str(workdir))} && {env} {runner} "
               f">> {shlex.quote(str(stdout))} 2>> {shlex.quote(str(stderr))}")
    # Vixie cron treats '%' as a newline even inside shell quotes. Protect every literal percent;
    # cron removes this escape before handing the command to /bin/sh.
    return command.replace("%", "\\%")


def _minute_cron(interval: int) -> str:
    if interval < 60 and 60 % interval == 0:
        return f"*/{interval} * * * *"
    if interval == 1440:
        return "0 0 * * *"
    if 60 <= interval < 1440 and interval % 60 == 0 and 24 % (interval // 60) == 0:
        return f"0 */{interval // 60} * * *"
    raise SchedulerError(f"tick interval {interval}m is not exactly representable by wall-clock cron")


def _cron_binary() -> str:
    value = os.environ.get("ORGFORGE_CRONTAB") or shutil.which("crontab")
    if not value:
        raise SchedulerError("crontab is unavailable")
    return value


def _cron_read(binary: str) -> str:
    result = _run([binary, "-l"])
    if result.returncode not in (0, 1):
        raise SchedulerError((result.stderr or result.stdout).strip() or "cannot read crontab")
    return result.stdout if result.returncode == 0 else ""


def _install_cron(args, python: str, binding: Path, root: Path,
                  workdir: Path, role: str, dry_run: bool) -> dict:
    binary = _cron_binary()
    tag = f"# orgforge:{role}"
    entry = f"{_minute_cron(args.tick_min)}  {_cron_command(python, binding, root, workdir, role)}  {tag}"
    print(f"backend: cron\n{entry}")
    if dry_run:
        print("(dry run — preflight complete; no scheduler or ledger state changed.)")
        return {"backend": "cron", "entry": entry, "tag": tag}

    smoke = _smoke(python, binding, root)
    before = _cron_read(binary)
    kept = [line for line in before.splitlines() if not line.endswith(tag)]
    installed = "\n".join([*kept, entry]).strip() + "\n"
    try:
        _run([binary, "-"], input_text=installed, check=True)
        after = _cron_read(binary)
        if [line for line in after.splitlines() if line.endswith(tag)] != [entry]:
            raise SchedulerError("crontab readback did not contain exactly the installed entry")
    except SchedulerError as exc:
        try:
            _run([binary, "-"], input_text=before, check=True)
            restored = _cron_read(binary)
            if restored != before:
                raise SchedulerError("rollback readback differs from the prior crontab")
        except SchedulerError as rollback_exc:
            raise SchedulerError(f"{exc}; rollback also failed: {rollback_exc}") from exc
        raise SchedulerError(f"{exc}; prior crontab restored") from exc
    return {"backend": "cron", "entry": entry, "tag": tag, "smoke": smoke}


def _launchctl() -> str:
    value = os.environ.get("ORGFORGE_LAUNCHCTL") or shutil.which("launchctl")
    if not value:
        raise SchedulerError("launchctl is unavailable")
    return value


def _launch_agents_dir() -> Path:
    override = os.environ.get("ORGFORGE_LAUNCH_AGENTS_DIR")
    return Path(override).expanduser().resolve() if override else Path.home() / "Library" / "LaunchAgents"


def _launch_domain() -> str:
    return os.environ.get("ORGFORGE_LAUNCH_DOMAIN") or f"gui/{os.getuid()}"


def _plist(binding: Path, python: str, root: Path, workdir: Path, role: str,
           interval: int, label: str) -> bytes:
    stdout, stderr, _ = _paths(root)
    value = {
        "Label": label,
        "ProgramArguments": _runner_command(python, binding, root),
        "WorkingDirectory": str(workdir),
        "EnvironmentVariables": {"ORG_LEDGER_ROOT": str(root), "ORG_ROLE": role},
        "RunAtLoad": True,
        "StartInterval": interval * 60,
        "ProcessType": "Background",
        "StandardOutPath": str(stdout),
        "StandardErrorPath": str(stderr),
    }
    return plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=False)


def _install_launchd(args, python: str, binding: Path, root: Path,
                     workdir: Path, role: str, dry_run: bool) -> dict:
    launchctl = _launchctl()
    label = _label(workdir, role)
    domain = _launch_domain()
    plist_path = _launch_agents_dir() / f"{label}.plist"
    content = _plist(binding, python, root, workdir, role, args.tick_min, label)
    print(f"backend: launchd\nlabel: {label}\nplist: {plist_path}")
    if dry_run:
        print(content.decode("utf-8"), end="")
        print("(dry run — preflight complete; no scheduler or ledger state changed.)")
        return {"backend": "launchd", "label": label, "plist": str(plist_path)}

    smoke = _smoke(python, binding, root)
    _, _, state_file = _paths(root)
    prior_state = _read_json(state_file) or {}
    prior_run = prior_state.get("run_id")
    old_content = plist_path.read_bytes() if plist_path.is_file() else None
    was_loaded = _run([launchctl, "print", f"{domain}/{label}"]).returncode == 0
    _run([launchctl, "bootout", f"{domain}/{label}"])
    _atomic_bytes(plist_path, content)
    try:
        _run([launchctl, "bootstrap", domain, str(plist_path)], check=True)
        _run([launchctl, "kickstart", "-k", f"{domain}/{label}"], check=True)
        deadline = time.monotonic() + _timeout()
        state = None
        while time.monotonic() < deadline:
            state = _read_json(state_file)
            if state and state.get("run_id") != prior_run and state.get("status") != "running":
                break
            time.sleep(0.1)
        else:
            raise SchedulerError("launchd job produced no completed scheduler-state receipt")
        if state.get("exit_code") not in (OK, ESCALATE) or state.get("receipt_seq") is None:
            raise SchedulerError("launchd job completed without a valid tick receipt")
        if _run([launchctl, "print", f"{domain}/{label}"]).returncode != 0:
            raise SchedulerError("launchd readback cannot find the loaded service")
    except BaseException:
        _run([launchctl, "bootout", f"{domain}/{label}"])
        if old_content is None:
            try:
                plist_path.unlink()
            except FileNotFoundError:
                pass
        else:
            _atomic_bytes(plist_path, old_content)
            if was_loaded:
                _run([launchctl, "bootstrap", domain, str(plist_path)])
        raise
    return {"backend": "launchd", "label": label, "plist": str(plist_path),
            "domain": domain, "smoke": smoke, "run": state}


def _registry(root: Path) -> Path:
    return root / "scheduler-installation.json"


def _install_bootstrap(plugin_root: Path, binding: Path) -> Path:
    source = plugin_root / "scripts" / "scheduler_bootstrap.py"
    if not source.is_file():
        raise SchedulerError(f"scheduler bootstrap is missing: {source}")
    target = binding.parent / "bin" / "orgforge-scheduler-tick"
    _atomic_bytes(target, source.read_bytes(), mode=0o755)
    return target


def _base_record(args, backend: str, python: str, plugin_root: Path, root: Path,
                 workdir: Path, role: str, binding: Path) -> dict:
    return {
        "schema": SCHEMA, "backend": backend, "role": role, "cycles": ["tick"],
        "tick_min": args.tick_min, "python": python, "plugin_root": str(plugin_root),
        "binding": str(binding),
        "ledger_root": str(root), "workdir": str(workdir),
        "installed_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"),
    }


def cmd_install(args) -> int:
    role = _role(args.role or os.environ.get("ORG_ROLE", ""))
    _cycles(args.cycles)
    root_value = args.root or os.environ.get("ORG_LEDGER_ROOT")
    if not root_value:
        raise SchedulerError("--root or ORG_LEDGER_ROOT is required")
    root = _safe_path(Path(root_value).expanduser().resolve(), "ledger root")
    workdir = _safe_path(Path(args.workdir).expanduser().resolve(), "workdir")
    if not root.is_dir():
        raise SchedulerError(f"ledger root does not exist: {root}")
    if not workdir.is_dir():
        raise SchedulerError(f"workdir does not exist: {workdir}")
    backend = _resolve_backend(args.backend)
    python = _python(args.python)
    plugin_root = _plugin_root()
    runner = plugin_root / "scripts" / "scheduler_tick.py"
    if not runner.is_file():
        raise SchedulerError(f"deterministic scheduler entrypoint is missing: {runner}")
    binding = _binding(workdir, plugin_root)
    if not args.dry_run:
        _install_bootstrap(plugin_root, binding)

    if backend == "launchd":
        detail = _install_launchd(args, python, binding, root, workdir, role, args.dry_run)
    else:
        detail = _install_cron(args, python, binding, root, workdir, role, args.dry_run)
    if args.dry_run:
        return OK
    record = _base_record(args, backend, python, plugin_root, root, workdir, role, binding)
    record.update({key: value for key, value in detail.items() if key not in {"smoke", "run"}})
    proof = detail.get("run") or detail.get("smoke") or {}
    coverage = proof.get("coverage") if isinstance(proof, dict) else None
    if isinstance(coverage, dict):
        record["coverage"] = coverage
    _atomic_json(_registry(root), record)
    print(f"installed: {backend} tick every {args.tick_min}m for role {role}")
    if isinstance(coverage, dict):
        print("unattended coverage: " + ", ".join(coverage.get("unattended") or []))
        attended = coverage.get("attended_only") or []
        if attended:
            print("attended-only schedule checks (not claimed by this scheduler): "
                  + ", ".join(attended))
    print(f"verify: {Path(__file__).resolve()} status --root {shlex.quote(str(root))}")
    return OK


def _cron_uninstall(record: dict) -> bool:
    binary = _cron_binary()
    tag = str(record.get("tag") or f"# orgforge:{record.get('role', '')}")
    before = _cron_read(binary)
    kept = [line for line in before.splitlines() if not line.endswith(tag)]
    after = ("\n".join(kept).strip() + "\n") if kept else ""
    _run([binary, "-"], input_text=after, check=True)
    return not any(line.endswith(tag) for line in _cron_read(binary).splitlines())


def _launchd_uninstall(record: dict) -> bool:
    launchctl = _launchctl()
    label = str(record.get("label") or "")
    domain = str(record.get("domain") or _launch_domain())
    if not label:
        raise SchedulerError("launchd installation record has no label")
    _run([launchctl, "bootout", f"{domain}/{label}"])
    path = Path(str(record.get("plist") or _launch_agents_dir() / f"{label}.plist"))
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return _run([launchctl, "print", f"{domain}/{label}"]).returncode != 0 and not path.exists()


def cmd_uninstall(args) -> int:
    root_value = args.root or os.environ.get("ORG_LEDGER_ROOT")
    if not root_value:
        raise SchedulerError("--root or ORG_LEDGER_ROOT is required")
    root = Path(root_value).expanduser().resolve()
    path = _registry(root)
    record = _read_json(path)
    if not record or record.get("schema") != SCHEMA:
        raise SchedulerError(f"no supported scheduler installation record: {path}")
    if args.role and record.get("role") != args.role:
        raise SchedulerError(
            f"installed scheduler belongs to role {record.get('role')!r}, not {args.role!r}")
    removed = (_launchd_uninstall(record) if record.get("backend") == "launchd"
               else _cron_uninstall(record))
    if not removed:
        raise SchedulerError("scheduler backend still reports the target definition")
    path.unlink(missing_ok=True)
    print(f"removed: {record.get('backend')} scheduler for role {record.get('role')}")
    return OK


def cmd_status(args) -> int:
    root_value = args.root or os.environ.get("ORG_LEDGER_ROOT")
    if not root_value:
        raise SchedulerError("--root or ORG_LEDGER_ROOT is required")
    root = Path(root_value).expanduser().resolve()
    record = _read_json(_registry(root))
    state = _read_json(root / "scheduler-state.json")
    definition_present = False
    if record and record.get("backend") == "launchd":
        label = str(record.get("label") or "")
        domain = str(record.get("domain") or _launch_domain())
        definition_present = bool(label) and _run(
            [_launchctl(), "print", f"{domain}/{label}"]).returncode == 0
    elif record and record.get("backend") == "cron":
        tag = str(record.get("tag") or "")
        definition_present = bool(tag) and sum(
            line.endswith(tag) for line in _cron_read(_cron_binary()).splitlines()) == 1
    now_min = int(time.time() // 60)
    receipt = _last_tick_receipt(root)
    last_min = receipt.get("now_min") if receipt else None
    age = now_min - last_min if isinstance(last_min, int) else None
    interval = record.get("tick_min") if record else None
    fresh = (isinstance(age, int) and age >= 0 and isinstance(interval, int)
             and age <= interval * 2)
    healthy_run = bool(state and state.get("status") in {"ok", "escalate"}
                       and state.get("receipt_seq") is not None)
    result = {
        "installed": bool(record), "definition_present": definition_present,
        "backend": record.get("backend") if record else None,
        "role": record.get("role") if record else None,
        "last_run": state, "last_receipt": receipt, "last_receipt_age_min": age, "fresh": fresh,
        "healthy_run": healthy_run,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return OK if record and definition_present and healthy_run and fresh else ESCALATE


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orgforge-scheduler", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install")
    install.add_argument("--role", type=_role)
    install.add_argument("--cycles", default="tick")
    install.add_argument("--tick-min", type=_positive_int, default=30)
    install.add_argument("--work-min", type=_positive_int, default=60,
                         help=argparse.SUPPRESS)
    install.add_argument("--discover-hours", type=_positive_int, default=24,
                         help=argparse.SUPPRESS)
    install.add_argument("--root")
    install.add_argument("--workdir", default=os.getcwd())
    install.add_argument("--backend", type=_backend, default="auto")
    install.add_argument("--python")
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(fn=cmd_install)
    for name, fn in (("status", cmd_status), ("uninstall", cmd_uninstall)):
        command = sub.add_parser(name)
        command.add_argument("--root")
        if name == "uninstall":
            command.add_argument("--role", type=_role)
        command.set_defaults(fn=fn)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except (SchedulerError, argparse.ArgumentTypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
