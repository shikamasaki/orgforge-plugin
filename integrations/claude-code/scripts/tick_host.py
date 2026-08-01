#!/usr/bin/env python3
"""Run the pure tick planner and persist its emitted ``tick_planned`` receipt.

``tick.py`` computes and emits an event without writing the ledger. This adapter is the host half
of that contract for Claude Code's ``/org-tick`` command. Persisting the receipt makes first-run
baselining one-shot, so later ticks can detect a real scheduler gap.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
_BUNDLED_TOOLS = os.path.join(HERE, "..", "tools")
_REPO_TOOLS = os.path.join(HERE, "..", "..", "tools")
TOOLS_DIR = os.environ.get(
    "ORG_TOOLS_DIR",
    _BUNDLED_TOOLS if os.path.isdir(_BUNDLED_TOOLS) else _REPO_TOOLS,
)


def _ledger_root(explicit=None):
    if explicit:
        return explicit
    if os.environ.get("ORG_LEDGER_ROOT"):
        return os.environ["ORG_LEDGER_ROOT"]
    sys.path.insert(0, TOOLS_DIR)
    import discover
    return discover.ledger_root()


def _emitted_events(output):
    events = []
    for line in output.splitlines():
        if not line.startswith("LEDGER-EVENT "):
            continue
        try:
            event = json.loads(line[len("LEDGER-EVENT "):])
            if event.get("class") == "tick_planned" and isinstance(event.get("payload"), dict):
                events.append(event)
        except (json.JSONDecodeError, TypeError):
            continue
    return events


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tick_host", description=__doc__)
    parser.add_argument("schedule_yaml")
    parser.add_argument("--root")
    parser.add_argument("--now-min", type=int, required=True)
    parser.add_argument("--night", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--only-check", action="append", default=[])
    parser.add_argument("--receipt-check", action="append", default=[])
    args = parser.parse_args(argv)

    root = _ledger_root(args.root)
    if not root:
        print("tick_host: no ledger root is configured or discoverable", file=sys.stderr)
        return 2

    command = [sys.executable, os.path.join(TOOLS_DIR, "tick.py"), "plan", root,
               args.schedule_yaml, "--now-min", str(args.now_min)]
    if args.night:
        command.append("--night")
    if args.verbose:
        command.append("--verbose")
    for check_id in args.only_check:
        command.extend(["--only-check", check_id])
    for check_id in args.receipt_check:
        command.extend(["--receipt-check", check_id])
    planned = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                             errors="replace")
    if planned.stdout:
        print(planned.stdout, end="")
    if planned.stderr:
        print(planned.stderr, end="", file=sys.stderr)

    if planned.returncode not in (0, 10):
        return planned.returncode

    emitted = _emitted_events(planned.stdout)
    if len(emitted) != 1:
        print(f"tick_host: expected exactly one tick_planned event, got {len(emitted)}",
              file=sys.stderr)
        return 10

    event = emitted[0]
    payload_json = json.dumps(event["payload"], ensure_ascii=False)
    payload_identity = hashlib.sha256(json.dumps(
        event["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()[:16]
    append_args = ["--actor", "system:tick_host", "--class", event["class"],
                   "--natural-key", f"tick-plan-{args.now_min}-{payload_identity}",
                   "--payload", payload_json]
    if os.environ.get("ORG_WRITER_SOCKET"):
        append_command = [sys.executable, os.path.join(TOOLS_DIR, "writer_client.py"),
                          "append", "--", *append_args]
    else:
        append_command = [sys.executable, os.path.join(TOOLS_DIR, "ledger.py"),
                          "append", root, *append_args]
    appended = subprocess.run(
        append_command,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if appended.returncode != 0:
        detail = ((appended.stdout or "") + (appended.stderr or "")).strip()
        print(f"tick_host: could not persist tick_planned (exit {appended.returncode}): "
              f"{detail[:500]}", file=sys.stderr)
        return 10
    return planned.returncode


if __name__ == "__main__":
    raise SystemExit(main())
