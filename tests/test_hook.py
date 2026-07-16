"""End-to-end tests for the org_hook.py guardrail bridge and the emit->append loop.

These cover exactly the gaps the external review (2026-07) found the organ-unit tests sitting over:
the seed() helper always appends via ledger.py with a --ts, so it never exercised the accumulation
path, the malformed line, or the ts-less record. Here we drive real PreToolUse event JSON THROUGH
org_hook.py as a subprocess (the real host interface) and assert the block/allow + accumulation.
"""
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "integrations" / "common" / "org_hook.py"
TOOLS = REPO / "tools"


def fire(root, command, tool_name="Bash", env_extra=None):
    """Drive one PreToolUse event through org_hook.py; return exit code."""
    env = dict(os.environ)
    env["ORG_LEDGER_ROOT"] = str(root)
    env["ORG_TOOLS_DIR"] = str(TOOLS)
    if env_extra:
        env.update(env_extra)
    ev = {"hook_event_name": "PreToolUse", "tool_name": tool_name,
          "tool_input": {"command": command}}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


# ── the BLOCKER: the emit->append loop must accumulate ────────────────────────
def test_blast_radius_accumulates_and_blocks(tmp_path):
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "2"}
    assert fire(tmp_path, "rm -rf /tmp/a", env_extra=env)[0] == 0     # 1st: committed 0
    assert fire(tmp_path, "rm -rf /tmp/b", env_extra=env)[0] == 0     # 2nd: committed 1
    code, out = fire(tmp_path, "rm -rf /tmp/c", env_extra=env)        # 3rd: committed 2, +1 > cap 2
    assert code == 2 and "HELD" in out                               # BLOCK — accumulation works
    # and the ledger really grew (proves the write-back, not a fluke)
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "census", str(tmp_path)],
                       capture_output=True, text=True)
    assert '"exposure_budget_checked": 2' in r.stdout


# ── the classifier fail-open: unknown destructive commands must be gated ──────
def test_classifier_gates_unknown_destructive(tmp_path):
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "0"}   # cap 0 => any gated destructive op blocks
    assert fire(tmp_path, "find /tmp -delete", env_extra=env)[0] == 2
    assert fire(tmp_path, "dd if=/dev/zero of=/tmp/x", env_extra=env)[0] == 2


def test_classifier_allows_readonly(tmp_path):
    assert fire(tmp_path, "ls -la")[0] == 0
    assert fire(tmp_path, "cat /etc/hostname")[0] == 0
    assert fire(tmp_path, "git status")[0] == 0


def test_hook_non_pretooluse_passes(tmp_path):
    env = dict(os.environ)
    env["ORG_LEDGER_ROOT"] = str(tmp_path)
    env["ORG_TOOLS_DIR"] = str(TOOLS)
    r = subprocess.run([sys.executable, str(HOOK)],
                       input=json.dumps({"hook_event_name": "Stop"}),
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0


def test_hook_fail_safe_on_broken_organ(tmp_path):
    # a missing tools dir must BLOCK a gated call, never silently allow (fail-safe)
    env = {"ORG_TOOLS_DIR": "/nonexistent", "ORG_CAP_DESTRUCTIVE_OPS": "5"}
    code, out = fire(tmp_path, "rm -rf /tmp/x", env_extra=env)
    assert code == 2


def test_hook_fail_open_opt_out(tmp_path):
    env = {"ORG_TOOLS_DIR": "/nonexistent", "ORG_HOOK_FAIL_OPEN": "1",
           "ORG_CAP_DESTRUCTIVE_OPS": "5"}
    code, _ = fire(tmp_path, "rm -rf /tmp/x", env_extra=env)
    assert code == 0   # dev opt-out allows
