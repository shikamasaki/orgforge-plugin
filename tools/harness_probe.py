#!/usr/bin/env python3
"""harness_probe — verify the enforcement layer actually blocks, at two levels (docs/17 §5 #5).

The org's whole safety story rests on one assumption: the PreToolUse hook fires and blocks a gated
tool call — INCLUDING a spawned subagent's call, which is exactly where multi-agent risk is highest
(a subagent inherits thin context and discards the parent's prompt constraints, docs/16 §2). But
whether the child's tool call actually reaches the hook is a property of the HARNESS, not this repo.
If a harness does not fire PreToolUse for subagents, the blast-radius cap, catastrophic denylist, and
seam gate all silently regress to top-level-only.

This tool probes LEVEL 1 (does the hook script itself block a gated call, given a hook-event JSON?).
It cannot, by itself, prove LEVEL 2 (does the live harness fire PreToolUse for a subagent) — that
requires the harness to actually spawn a child and route its call through the hook, which only the
running harness can do. `/org-verify-guards` wraps this Level-1 probe and then walks the operator
through the Level-2 live check. This script exits 0 only if Level 1 passes (the hook blocks a
catastrophic command and an over-cap destructive op); non-zero means the enforcement layer is broken
at the script level and the org must not be trusted to run unattended.

Usage:  harness_probe.py --hook <path/to/org_hook.py> [--tools <tools-dir>]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile


def _fire(hook, tools_dir, ledger_root, tool_name, tool_input, extra_env=None):
    env = dict(os.environ, ORG_LEDGER_ROOT=ledger_root, ORG_TOOLS_DIR=tools_dir)
    if extra_env:
        env.update(extra_env)
    ev = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    r = subprocess.run([sys.executable, hook], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    return r.returncode, (r.stdout + r.stderr)


def main(argv):
    p = argparse.ArgumentParser(prog="harness_probe", description=__doc__)
    p.add_argument("--hook", required=True, help="path to org_hook.py")
    p.add_argument("--tools", default=None, help="tools dir (default: alongside the hook)")
    a = p.parse_args(argv[1:])
    hook = os.path.abspath(a.hook)
    tools_dir = a.tools or os.path.dirname(hook)
    ledger = tempfile.mkdtemp()

    checks = []
    # 1. catastrophic command must HARD-BLOCK regardless of budget
    code, out = _fire(hook, tools_dir, ledger, "Bash", {"command": "rm -rf /"})
    checks.append(("catastrophic rm -rf / hard-blocked", code == 2 and "HARD-BLOCKED" in out))
    # 2. an over-cap destructive op must block
    code, out = _fire(hook, tools_dir, ledger, "Bash", {"command": "rm -rf /tmp/probe"},
                      {"ORG_CAP_DESTRUCTIVE_OPS": "0"})
    checks.append(("over-cap destructive op held", code == 2))
    # 3. a benign read must pass
    code, out = _fire(hook, tools_dir, ledger, "Bash", {"command": "ls -la"})
    checks.append(("benign read allowed", code == 0))

    print("harness probe — Level 1 (hook script blocks a gated call):")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    if not ok:
        print("\nLEVEL 1 FAILED — the hook script does not block as expected. The enforcement layer is "
              "broken at the script level; do NOT run this org unattended until fixed.", file=sys.stderr)
        return 1
    print("\nLevel 1 PASSED. The hook script blocks a gated call.\n"
          "LEVEL 2 (live harness): only the running harness can prove it fires PreToolUse for a "
          "SUBAGENT's tool call. Run the Level-2 check in /org-verify-guards: spawn a trivial subagent, "
          "have it attempt a gated command, and confirm the hook fired (the ledger shows the block / the "
          "call was denied). If it did not, this harness does not gate subagents — do not certify the org "
          "as fan-out-safe (docs/17 §5).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
