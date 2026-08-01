#!/usr/bin/env python3
"""Emit Claude Monitor notifications only when the org's RED signal changes.

``status.py redline`` intentionally remains a stateless probe. This long-lived adapter retains the
previous probe output in memory: the first RED and each changed RED are emitted, identical REDs are
quiet, and GREEN resets the state so a later recurrence is emitted again.
"""

import argparse
from pathlib import Path
import subprocess
import sys
import time


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


def watch(run_probe, interval=60, max_polls=None, output=None, sleeper=time.sleep):
    """Poll until stopped, emitting only non-empty transitions. Returns the number of polls."""
    output = output or sys.stdout
    previous = None
    polls = 0
    while max_polls is None or polls < max_polls:
        current = (run_probe() or "").strip()
        if current and current != previous:
            print(current, file=output, flush=True)
        previous = current
        polls += 1
        if max_polls is None or polls < max_polls:
            sleeper(interval)
    return polls


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Watch status.py redline and emit only RED transitions/changes.")
    parser.add_argument("root", nargs="?", help="ledger root (status.py auto-discovers when omitted)")
    parser.add_argument("--role", default="")
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
    try:
        watch(lambda: probe(args.status_script, args.root, args.role),
              interval=args.interval, max_polls=args.max_polls)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
