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


# ── the rolling window must reset, or the cap deadlocks (frozen-epoch bug) ────
def test_blast_radius_window_rolls_forward_daily(tmp_path):
    # REGRESSION: the window was hardcoded to 1970-01-01 (all-time), so committed exposure
    # accumulated forever and the cap eventually blocked EVERY action — a deadlock where nothing
    # could be edited. With a rolling DAILY window, yesterday's exhausted budget does NOT count today.
    (tmp_path / "HEAD").write_text("x")
    # seed the ledger with a full day of file_mutations committed YESTERDAY (cap exhausted then)
    lines = [json.dumps({"id": f"e{i}", "seq": i, "ts": "2026-07-17T10:00:00Z", "actor": "x",
                         "class": "exposure_budget_checked",
                         "payload": {"dimension": "file_mutations", "decision": "allow",
                                     "delta_requested": 1.0}}) for i in range(200)]
    (tmp_path / "ledger.jsonl").write_text("\n".join(lines) + "\n")
    # a mutation TODAY (an existing file) must be allowed — yesterday's 200 fall outside today's window.
    existing = tmp_path / "ledger.jsonl"          # a path that exists → Write = file_mutation
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Write",
          "tool_input": {"command": "", "file_path": str(existing)}}
    env = dict(os.environ, ORG_LEDGER_ROOT=str(tmp_path), ORG_TOOLS_DIR=str(TOOLS))
    for k in ("ORG_WINDOW_SINCE", "ORG_WINDOW", "ORG_NOW_TS"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"rolling window did not reset — deadlock persists: {r.stdout + r.stderr}"


# ── the BLOCKER: the emit->append loop must accumulate ────────────────────────
def test_blast_radius_accumulates_and_blocks(tmp_path):
    # use a LIGHT destructive op (plain `rm file` = weight 1) so we can watch it accumulate;
    # heavy recursive deletes are weight 3 and trip a low cap in one shot (see next test).
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "2"}
    assert fire(tmp_path, "rm /tmp/a", env_extra=env)[0] == 0     # 1st: committed 0
    assert fire(tmp_path, "rm /tmp/b", env_extra=env)[0] == 0     # 2nd: committed 1
    code, out = fire(tmp_path, "rm /tmp/c", env_extra=env)        # 3rd: committed 2, +1 > cap 2
    assert code == 2 and "HELD" in out                           # BLOCK — accumulation works
    # and the ledger really grew (proves the write-back, not a fluke)
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "census", str(tmp_path)],
                       capture_output=True, text=True)
    assert '"exposure_budget_checked": 2' in r.stdout


# ── reversibility pricing (three-perspective review): create is free, destroy is metered ──
def test_new_file_write_is_not_metered(tmp_path):
    # a Write to a NON-existent path is a reversible creation — must NOT be blast radius, so a
    # long build of many new files proceeds. (cap set to 0 => anything metered would block.)
    env = {"ORG_CAP_FILE_MUTATIONS": "0"}
    for i in range(10):
        p = tmp_path / f"new_{i}.js"
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Write",
              "tool_input": {"file_path": str(p), "content": "x"}}
        e = dict(os.environ); e["ORG_LEDGER_ROOT"] = str(tmp_path)
        e["ORG_TOOLS_DIR"] = str(TOOLS); e.update(env)
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                           capture_output=True, text=True, env=e)
        assert r.returncode == 0, r.stdout + r.stderr        # every new-file create passes


def test_overwriting_existing_file_is_metered(tmp_path):
    # a Write to an EXISTING path is a mutation — metered. With cap 0 it blocks.
    existing = tmp_path / "exists.js"
    existing.write_text("original")
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Write",
          "tool_input": {"file_path": str(existing), "content": "new"}}
    e = dict(os.environ); e["ORG_LEDGER_ROOT"] = str(tmp_path)
    e["ORG_TOOLS_DIR"] = str(TOOLS); e["ORG_CAP_FILE_MUTATIONS"] = "0"
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=e)
    assert r.returncode == 2 and "HELD" in (r.stdout + r.stderr)


def test_heavy_recursive_delete_costs_more_than_a_light_one(tmp_path):
    # rm -rf is weight 3 (scope-weighted): one trips a cap of 2 in a single shot, where a light
    # `rm file` (weight 1) would have passed — the reviewers' "one catastrophic command alone
    # can exceed the cap" property that the old flat delta-1 model couldn't express.
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "2"}
    code, out = fire(tmp_path, "rm -rf /tmp/whole-dir", env_extra=env)   # 0 + 3 > 2 -> block
    assert code == 2 and "HELD" in out
    # a light delete under the same cap passes (weight 1: 0 + 1 <= 2)
    env2 = {"ORG_CAP_DESTRUCTIVE_OPS": "2"}
    assert fire(tmp_path / "b", "rm /tmp/one.tmp", env_extra=env2)[0] == 0


def test_build_tooling_not_metered(tmp_path):
    # npm install / node / pytest are benign build tooling — not blast radius.
    for c in ("npm install", "node build.js", "pytest -q", "git commit -m x"):
        assert fire(tmp_path, c)[0] == 0, c


# ── word-boundary destructive classification (regression: substring false positives) ──────────
# The old classifier tested `"rm " in cmd` / `"-f " in cmd` as SUBSTRINGS, so a command that merely
# CONTAINED those bytes — e.g. any path under `.../fx-ml-platform/...`, or `grep -f`, or `--info`
# collapsing to `-f` — was miscounted as a destructive op, accumulated against the low cap, and
# eventually blocked every command. These pin that benign commands containing those bytes are NOT
# metered, under a cap of 0 (any destructive charge would block immediately).
def test_benign_commands_are_not_misread_as_destructive(tmp_path):
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "0"}   # cap 0 => any destructive charge blocks on the spot
    benign = [
        "ls /Volumes/192.168.1.6/fx-ml-platform",   # path contains 'form' — must not read as 'rm'
        "cat /Volumes/nas/fx-ml-platform/README.md",
        "grep -f patterns.txt data.log",            # '-f' as a real flag, not 'rm -f'
        "python train.py --info",                   # no destructive token at all
        "cd /srv/platform && pytest -q",            # 'platform' contains 'form'
        "git diff --stat",
    ]
    for c in benign:
        code, out = fire(tmp_path, c, env_extra=env)
        assert code == 0, f"benign command wrongly gated as destructive: {c!r} -> {out!r}"


def test_real_destructive_still_caught_by_word_boundary(tmp_path):
    # The fix must NOT weaken the guardrail: real destructive ops still charge and block at cap 0.
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "0"}
    destructive = [
        "rm /tmp/a",
        "rm -rf /tmp/dir",
        "dd if=/dev/zero of=/tmp/x",
        "find . -name '*.tmp' -delete",
        "git push origin main",
        "git reset --hard HEAD~1",
        "echo bad | bash",
        "cat evil.sh | sh",
    ]
    for c in destructive:
        code, out = fire(tmp_path / c.replace("/", "_")[:20], c, env_extra=env)
        assert code == 2, f"real destructive command NOT gated: {c!r} -> {out!r}"


# ── Agent-spawn discipline: seam contract OR independence, else block ─────────
def fire_spawn(prompt, require_seam=True, root=None):
    env = dict(os.environ)
    env["ORG_TOOLS_DIR"] = str(TOOLS)
    if root:
        env["ORG_LEDGER_ROOT"] = str(root)
    if require_seam:
        env["ORG_REQUIRE_SEAM"] = "1"
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Agent",
          "tool_input": {"prompt": prompt}}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def test_spawn_without_seam_or_independence_is_blocked():
    code, out = fire_spawn("You are a worker. Build the login page.")
    assert code == 2 and "HELD" in out and "seam contract" in out


def test_spawn_with_seam_contract_allowed():
    code, _ = fire_spawn("## Your slice: login\n## Boundary contract\n"
                         "- Outputs you MUST produce: a LoginForm component")
    assert code == 0


def test_spawn_declared_independent_allowed():
    code, _ = fire_spawn("INDEPENDENT: enumerate features; output not merged with siblings.")
    assert code == 0


def test_spawn_gate_is_opt_in():
    # without ORG_REQUIRE_SEAM the bare spawn passes (the gate is opt-in)
    code, _ = fire_spawn("You are a worker. Build the login page.", require_seam=False)
    assert code == 0


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
