#!/usr/bin/env python3
"""Stable installed-organ scheduler bootstrap.

The OS definition points here instead of into a versioned plugin cache.  Every run resolves the
current installed-organ binding, then execs that version's ``scheduler_tick`` organ.  Binding
failures replace stale success state with an explicit error before exiting.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid


BROKEN = 12


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


def _fail(root: Path, binding: Path, message: str) -> int:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    print(message, file=sys.stderr)
    _atomic_json(root / "scheduler-state.json", {
        "schema": "orgforge-scheduler-run/v1", "run_id": f"bootstrap-{uuid.uuid4().hex}",
        "status": "error", "started_at": now, "finished_at": now,
        "now_min": int(time.time() // 60), "exit_code": BROKEN, "pid": os.getpid(),
        "python": sys.executable, "plugin_root": None, "binding": str(binding),
        "checks": [{"name": "binding_preflight", "returncode": BROKEN, "error": message}],
        "receipt_seq": None, "receipt_hash": None,
    })
    return BROKEN


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orgforge-scheduler-bootstrap", description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--binding", required=True)
    args, remainder = parser.parse_known_args(argv)
    root = Path(args.root).expanduser().resolve()
    binding_path = Path(args.binding).expanduser().resolve()
    try:
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _fail(root, binding_path,
                     f"scheduler bootstrap: installed-organ binding is unreadable: {exc}")
    if not isinstance(binding, dict) or binding.get("schema") != "orgforge-installed-organ/v1":
        return _fail(root, binding_path, "scheduler bootstrap: unsupported installed-organ binding")
    plugin_root = Path(str(binding.get("plugin_root") or "")).expanduser().resolve()
    target = plugin_root / "scripts" / "scheduler_tick.py"
    if not target.is_file():
        return _fail(root, binding_path,
                     f"scheduler bootstrap: current scheduler_tick organ is unavailable: {target}")
    os.execv(sys.executable, [sys.executable, str(target), "--root", str(root),
                              "--binding", str(binding_path), *remainder])
    return BROKEN


if __name__ == "__main__":
    raise SystemExit(main())
