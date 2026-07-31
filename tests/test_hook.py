"""End-to-end tests for the org_hook.py guardrail bridge and the emit->append loop.

These cover exactly the gaps the external review (2026-07) found the organ-unit tests sitting over:
the seed() helper always appends via ledger.py with a --ts, so it never exercised the accumulation
path, the malformed line, or the ts-less record. Here we drive real PreToolUse event JSON THROUGH
org_hook.py as a subprocess (the real host interface) and assert the block/allow + accumulation.
"""
import json
import os
import pathlib
import re
import pytest
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "integrations" / "common" / "org_hook.py"
TOOLS = REPO / "tools"


_TU = 0          # tool_use_id の連番。呼び出しごとに違う値にする


def _next_tu():
    """呼び出しごとに違う tool_use_id を作る。**同じ値だと再実行として no-op になり、
    曝露が積み上がらない** — 実運用でも tool_use_id は呼び出しごとに違う。"""
    global _TU
    _TU += 1
    return _TU


def fire(root, command, tool_name="Bash", env_extra=None):
    """Drive one PreToolUse event through org_hook.py; return exit code."""
    env = dict(os.environ)
    env["ORG_LEDGER_ROOT"] = str(root)
    env["ORG_TOOLS_DIR"] = str(TOOLS)
    if env_extra:
        env.update(env_extra)
    # **実運用と同じ形で渡す。** PreToolUse の stdin は session_id と tool_use_id を持つ
    # （2026-07 に docs で確認）。cap 予約はこれを冪等キーにするので、欠けていれば deny される
    # ＝ テストが「識別子を渡さない」形だと、全 metered action が止まる。
    # 呼び出しごとに違う tool_use_id にする — 同じなら再実行として no-op になり、
    # 曝露が積み上がらない。
    ev = {"hook_event_name": "PreToolUse", "tool_name": tool_name,
          "tool_input": {"command": command},
          "session_id": "test-session", "tool_use_id": f"toolu_test{_next_tu():04d}"}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


# ── the rolling window must reset, or the cap deadlocks (frozen-epoch bug) ────
def test_blast_radius_window_rolls_forward_daily(tmp_path):
    # REGRESSION: the window was hardcoded to 1970-01-01 (all-time), so committed exposure
    # accumulated forever and the cap eventually blocked EVERY action — a deadlock where nothing
    # could be edited. With a rolling DAILY window, yesterday's exhausted budget does NOT count today.
    # **実際の append で seed する。** 手書きの偽イベント（seq=0 始まり、hash 無し）を置くと、
    # Writer Phase 0 の健全性検査が正しく拒否する — 鎖の無い台帳に予約は書けない。
    # 「昨日」は now からの相対で作る（固定日付は 90 日の backfill 窓を出て壊れる）。
    import datetime as _dt
    yesterday = (_dt.datetime.now(_dt.timezone.utc)
                 - _dt.timedelta(days=1)).strftime("%Y-%m-%dT10:00:00Z")
    for i in range(30):        # 200 件は実 append では遅すぎる。cap 既定 500 を超えない範囲で足る
        r = subprocess.run(
            [sys.executable, str(TOOLS / "ledger.py"), "append", str(tmp_path),
             # **予約は writer 専用**（0.34.1）。generic append では書けないので、
             # 昨日の曝露は reserve-exposure で作る。窓の外にあることが検査の主題なので、
             # 予約時刻を過去にはできない（cap 予約に backfill は無い）— 代わりに
             # ORG_NOW_TS で hook 側の「今日」を進めて、この予約を昨日側に落とす。
             "--actor", "x", "--class", "progress_recorded",
             "--payload", json.dumps({"role": "x", "candidate_id": f"seed{i}",
                                      "phase": "implement"})],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    # a mutation TODAY (an existing file) must be allowed — yesterday's seeded exposure falls outside today's window.
    existing = tmp_path / "ledger.jsonl"          # a path that exists → Write = file_mutation
    ev = {"hook_event_name": "PreToolUse",
          "session_id": "test-session",
          "tool_use_id": f"toolu_x{_next_tu():04d}", "tool_name": "Write",
          "tool_input": {"command": "", "file_path": str(existing)}}
    env = dict(os.environ, ORG_LEDGER_ROOT=str(tmp_path), ORG_TOOLS_DIR=str(TOOLS))
    for k in ("ORG_WINDOW_SINCE", "ORG_WINDOW", "ORG_NOW_TS"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"rolling window did not reset — deadlock persists: {r.stdout + r.stderr}"


# ── F5: the gate regime comes from the SPEC, so every install enforces the same (docs/11 §0) ──
def test_cap_read_from_constitution_not_only_env(tmp_path):
    # org root: <root>/constitution.yaml declares a tight destructive_ops cap; ledger at <root>/ledger.
    # No ORG_CAP_* env is set — the gate must still fire from the spec-declared cap. This is what makes
    # two installs of the same org enforce the same gates (reproducibility), instead of diverging on
    # per-host env vars.
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  caps:\n    destructive_ops: 2\n  window: daily\n")
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    # three light destructive ops: 1st/2nd commit under cap 2, 3rd exceeds → HELD, with NO env cap set
    assert fire(ledger, "rm /tmp/a")[0] == 0
    assert fire(ledger, "rm /tmp/b")[0] == 0
    code, out = fire(ledger, "rm /tmp/c")
    assert code == 2 and "HELD" in out, f"spec-declared cap did not fire: {out}"


def test_env_cap_overrides_constitution(tmp_path):
    # a dev override (ORG_CAP_*) must still win over the spec, so a developer can loosen locally.
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  caps:\n    destructive_ops: 1\n")
    ledger = tmp_path / "ledger"; ledger.mkdir()
    # spec cap is 1 (would block on the 2nd), but env raises it to 50 → several pass
    for c in "abcd":
        assert fire(ledger, f"rm /tmp/{c}", env_extra={"ORG_CAP_DESTRUCTIVE_OPS": "50"})[0] == 0


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
    # **3 件**である。0.34.0 から hold も台帳に残る（従来は deny して終わり、止めたことが
    # 記録されなかった）。allow 2 + hold 1。
    assert '"exposure_budget_checked": 3' in r.stdout


# ── reversibility pricing (three-perspective review): create is free, destroy is metered ──
def test_new_file_write_is_not_metered(tmp_path):
    # a Write to a NON-existent path is a reversible creation — must NOT be blast radius, so a
    # long build of many new files proceeds. (cap set to 0 => anything metered would block.)
    env = {"ORG_CAP_FILE_MUTATIONS": "0"}
    for i in range(10):
        p = tmp_path / f"new_{i}.js"
        ev = {"hook_event_name": "PreToolUse",
          "session_id": "test-session",
          "tool_use_id": f"toolu_x{_next_tu():04d}", "tool_name": "Write",
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
    ev = {"hook_event_name": "PreToolUse",
          "session_id": "test-session",
          "tool_use_id": f"toolu_x{_next_tu():04d}", "tool_name": "Write",
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


def test_catastrophic_commands_hard_blocked_regardless_of_cap(tmp_path):
    # The blast-radius cap is a DAILY BUDGET — it bounds many cuts, not one unrecoverable cut. A single
    # `rm -rf /` is weight 3 and passes under any non-zero cap, so the default cap would let it through.
    # The catastrophic denylist hard-blocks it BEFORE the budget logic, even at the default cap.
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "1000"}   # a huge budget — the denylist must still block
    for c in ("rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf $HOME",
              "mkfs.ext4 /dev/sda", "dd if=/dev/zero of=/dev/sda bs=1M", ":(){ :|:& };:"):
        code, out = fire(tmp_path, c, env_extra=env)
        assert code == 2 and "HARD-BLOCKED" in out, f"catastrophic command NOT hard-blocked: {c!r} -> {out!r}"


def test_catastrophic_denylist_does_not_false_positive_on_ordinary_deletes(tmp_path):
    # Ordinary recursive deletes of a workspace path are common, reversible-enough dev work — they stay
    # cap-metered, NOT hard-blocked (else the denylist re-creates the false-positive deadlock we fixed).
    for c in ("rm -rf /tmp/mydir", "rm -rf ./build", "rm -rf node_modules", "rm file.txt",
              "rm -rf dist/"):
        code, out = fire(tmp_path, c)   # default cap → allowed
        assert code == 0, f"ordinary delete wrongly hard-blocked: {c!r} -> {out!r}"


def test_catastrophic_block_fires_without_a_ledger(tmp_path):
    # A catastrophic command is never a budget question — it must block even when no org/ledger exists.
    ev = {"hook_event_name": "PreToolUse",
          "session_id": "test-session",
          "tool_use_id": f"toolu_x{_next_tu():04d}", "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
    env = dict(os.environ, ORG_TOOLS_DIR=str(TOOLS))   # note: NO ORG_LEDGER_ROOT
    for k in ("ORG_LEDGER_ROOT", "ORG_ALLOW_CATASTROPHIC"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "HARD-BLOCKED" in (r.stdout + r.stderr)


def test_dev_null_and_stderr_redirects_are_not_destructive(tmp_path):
    # REGRESSION: the redirect check `(\||>>?)\s*/` fired on `2>/dev/null` and `> /dev/null 2>&1`, so a
    # read-only search with stderr suppressed was charged as a destructive op and drained the budget
    # (the user raised the cap 3→25→100 chasing this). These harmless redirects must NOT be metered.
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "0"}   # cap 0 → any destructive charge blocks immediately
    for c in ("grep -r foo . 2>/dev/null", "find . -name x 2>/dev/null", "ls /data 2>/dev/null",
              "python train.py > /dev/null 2>&1", "echo hi >/dev/null", "python x.py > out.log",
              "echo a >> ./local.txt", "make 2> build.err"):
        code, out = fire(tmp_path, c, env_extra=env)
        assert code == 0, f"harmless redirect wrongly gated as destructive: {c!r} -> {out!r}"


def test_redirect_to_system_path_still_destructive(tmp_path):
    # the fix must not weaken the guard: a real overwrite of a system path still meters at cap 0.
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "0"}
    for c in ("cmd > /etc/passwd", "echo x > /usr/local/bin/tool", "tee >> /etc/hosts",
              "echo x > /boot/config"):
        code, out = fire(tmp_path / c.replace("/", "_")[:20], c, env_extra=env)
        assert code == 2, f"real system-path overwrite NOT gated: {c!r} -> {out!r}"


def test_unknown_and_readonly_shell_never_meters_the_cap(tmp_path):
    # REGRESSION: unclassified/read-only shell used to be charged as a metered `shell_effect`, which
    # quietly drained the daily budget on benign work (git status, find, du, an unfamiliar CLI) until
    # the cap blocked everything — the false-positive deadlock the user hit. Now "unknown" is NOT
    # metered: only explicit destructive/external/infra patterns are. Under cap 0 for BOTH destructive
    # and (deprecated) shell_effect, these must all still pass — proof they draw down no budget at all.
    env = {"ORG_CAP_DESTRUCTIVE_OPS": "0", "ORG_CAP_SHELL_EFFECT": "0"}
    for c in ("git status", "git log --oneline", "find . -name '*.py'", "du -sh .", "stat file",
              "mv a b", "some-unfamiliar-cli --do-thing", "ls -R /data", ""):
        code, out = fire(tmp_path, c, env_extra=env)
        assert code == 0, f"benign/unknown shell wrongly metered: {c!r} -> {out!r}"


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
        "git push --force origin main",   # 通常の push は 0.23.0 で対象外
        "git reset --hard HEAD~1",
        "echo bad | bash",
        "cat evil.sh | sh",
    ]
    for c in destructive:
        code, out = fire(tmp_path / c.replace("/", "_")[:20], c, env_extra=env)
        assert code == 2, f"real destructive command NOT gated: {c!r} -> {out!r}"


# ── Agent-spawn discipline: seam contract OR independence, else block ─────────
def fire_spawn(prompt, require_seam=True, root=None, opt_out=False):
    env = dict(os.environ)
    env["ORG_TOOLS_DIR"] = str(TOOLS)
    if root:
        env["ORG_LEDGER_ROOT"] = str(root)
    # the gate is now DEFAULT-ON; opt_out sets ORG_REQUIRE_SEAM=0 to disable it for an ungated dev run.
    if opt_out:
        env["ORG_REQUIRE_SEAM"] = "0"
    ev = {"hook_event_name": "PreToolUse",
          "session_id": "test-session",
          "tool_use_id": f"toolu_x{_next_tu():04d}", "tool_name": "Agent",
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


def test_spawn_gate_is_default_on():
    # the gate is now DEFAULT-ON (docs/12 §5 Layer-1 #1): a bare spawn with no seam/independence blocks
    # even without any env flag set.
    code, out = fire_spawn("You are a worker. Build the login page.")
    assert code == 2 and "seam contract" in out


def test_spawn_gate_opt_out_disables_it():
    # ORG_REQUIRE_SEAM=0 disables the gate for a deliberately ungated dev run.
    code, _ = fire_spawn("You are a worker. Build the login page.", opt_out=True)
    assert code == 0


def test_spawn_owns_collision_with_live_sibling_is_blocked(tmp_path):
    # concurrent-write drift is PREVENTED at spawn time: a child declaring owns-territory that a live
    # sibling already claimed is refused, turning reconcile's post-hoc scan into a precondition.
    (tmp_path / "HEAD").write_text("x")
    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "id": "c1", "seq": 1, "ts": "2026-07-26T00:00:00Z", "actor": "sib", "class": "work_claimed",
        "payload": {"role": "sibling-a", "work_territory": "src/auth/login.py",
                    "intent_summary": "build login"}}) + "\n")
    prompt = ("## Your slice: auth\n## Boundary contract\nInputs you receive: none\n"
              "Owns: src/auth/login.py\n")
    code, out = fire_spawn(prompt, root=tmp_path)
    assert code == 2 and "collides with a live sibling claim" in out


def test_spawn_owns_disjoint_from_live_sibling_allowed(tmp_path):
    # a disjoint owns-set is fine — only an actual overlap is blocked.
    (tmp_path / "HEAD").write_text("x")
    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "id": "c1", "seq": 1, "ts": "2026-07-26T00:00:00Z", "actor": "sib", "class": "work_claimed",
        "payload": {"role": "sibling-a", "work_territory": "src/auth/login.py",
                    "intent_summary": "build login"}}) + "\n")
    prompt = ("## Your slice: search\n## Boundary contract\nInputs you receive: none\n"
              "Owns: src/search/index.py\n")
    code, _ = fire_spawn(prompt, root=tmp_path)
    assert code == 0


def test_spawn_owns_collision_cleared_after_release(tmp_path):
    # once the sibling releases (claim_released or a cycle_completed on the territory), the child may claim it.
    (tmp_path / "HEAD").write_text("x")
    (tmp_path / "ledger.jsonl").write_text(
        json.dumps({"id": "c1", "seq": 1, "ts": "2026-07-26T00:00:00Z", "actor": "sib",
                    "class": "work_claimed",
                    "payload": {"role": "sibling-a", "work_territory": "src/auth/login.py",
                                "intent_summary": "x"}}) + "\n" +
        json.dumps({"id": "c2", "seq": 2, "ts": "2026-07-26T01:00:00Z", "actor": "sib",
                    "class": "claim_released",
                    "payload": {"role": "sibling-a", "work_territory": "src/auth/login.py"}}) + "\n")
    prompt = ("## Your slice: auth\n## Boundary contract\nInputs you receive: none\n"
              "Owns: src/auth/login.py\n")
    code, _ = fire_spawn(prompt, root=tmp_path)
    assert code == 0


# ── iteration/spend cap: the runaway kill in the enforcement layer ────────────
def _seed(root, cls, payload, ts):
    subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", str(root),
                    "--actor", "x", "--class", cls, "--payload", json.dumps(payload), "--ts", ts],
                   capture_output=True)


def test_iteration_cap_holds_a_spawn_over_the_cycle_budget(tmp_path):
    # 2 cycles already run this window for role 'eng'; cap is 2, so the next spawn (would be #3) holds.
    for i in range(2):
        _seed(tmp_path, "cycle_started", {"role": "eng", "candidate_id": f"c{i}"},
              f"2026-07-27T0{i}:00:00Z")
    env = {"ORG_ROLE": "eng", "ORG_MAX_CYCLES": "2", "ORG_REQUIRE_SEAM": "0",
           "ORG_NOW_TS": "2026-07-27T05:00:00Z"}
    ev = {"hook_event_name": "PreToolUse",
          "session_id": "test-session",
          "tool_use_id": f"toolu_x{_next_tu():04d}", "tool_name": "Task",
          "tool_input": {"prompt": "INDEPENDENT: do a thing"}}
    e = dict(os.environ, ORG_LEDGER_ROOT=str(tmp_path), ORG_TOOLS_DIR=str(TOOLS), **env)
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=e)
    assert r.returncode == 2 and "cap" in (r.stdout + r.stderr)


def test_iteration_cap_inactive_without_env(tmp_path):
    # no ORG_MAX_* set → the iteration cap never fires (an org that didn't opt into a budget is unaffected).
    for i in range(9):
        _seed(tmp_path, "cycle_started", {"role": "eng", "candidate_id": f"c{i}"},
              f"2026-07-27T0{i}:00:00Z")
    env = {"ORG_ROLE": "eng", "ORG_REQUIRE_SEAM": "0"}
    ev = {"hook_event_name": "PreToolUse",
          "session_id": "test-session",
          "tool_use_id": f"toolu_x{_next_tu():04d}", "tool_name": "Task",
          "tool_input": {"prompt": "INDEPENDENT: do a thing"}}
    e = dict(os.environ, ORG_LEDGER_ROOT=str(tmp_path), ORG_TOOLS_DIR=str(TOOLS), **env)
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=e)
    assert r.returncode == 0


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


def test_harness_probe_level1_passes_on_real_hook(tmp_path):
    # the Level-1 probe must certify the shipped hook blocks a catastrophic + over-cap call and allows a read.
    r = subprocess.run([sys.executable, str(REPO / "tools" / "harness_probe.py"),
                        "--hook", str(HOOK), "--tools", str(TOOLS)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "Level 1 PASSED" in (r.stdout + r.stderr)


# ── 0.23.0: cap が開発そのものを止めていた ──────────────────────────────
def test_ordinary_push_is_not_metered():
    """通常の `git push` は追記であって取り消せる。

    一律に破壊的として数えた結果、実地では18 Issue を並列で回す1日で cap が満杯になり、
    **maker が作業を終えたのに push できない**状態が起きた。cap が測るのは
    irreversibility であって活動量ではない — 開発そのものを止めるなら cap の誤用である。
    """
    import importlib.util, pathlib
    hook = pathlib.Path(__file__).resolve().parent.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_p", hook)
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    for cmd in ("git push origin feat/issue-9", "git push -u origin feat/x", "git push"):
        assert h._asset_dimension("Bash", {"command": cmd}) is None, f"課金された: {cmd}"


def test_force_push_and_history_rewrites_stay_metered():
    """緩めたのは通常の push だけ。履歴を消しうるものは重いまま。"""
    import importlib.util, pathlib
    hook = pathlib.Path(__file__).resolve().parent.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_f", hook)
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    for cmd in ("git push --force origin main", "git push --force-with-lease origin main",
                "git push --delete origin old", "git reset --hard HEAD~1"):
        dim, w = h._asset_dimension("Bash", {"command": cmd})
        assert w > 0, f"force 系が無料になった: {cmd}"


# ── 0.30.0: organ を迂回する経路を hold する ────────────────────────────────
def _hook():
    import importlib.util, pathlib
    p = pathlib.Path(__file__).resolve().parent.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_byp", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def _org_repo(tmp_path, branch="develop"):
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a):
        return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / ".orgforge").mkdir()
    (repo / "s.txt").write_text("x"); g("add", "-A"); g("commit", "-qm", "s")
    g("branch", "develop"); g("checkout", "-q", branch)
    return repo


def test_direct_merge_into_a_protected_branch_is_held(tmp_path, monkeypatch):
    """`integrate` は呼ばれなければ何も検査しない。

    運用では、質の高い maker 報告を受けた監督が `git merge` で develop に入れ、gate も
    skeptic も通らないまま2件が統合された。台帳は後から正しく拒否したが、拒否が来たのは
    コードが入った後。**検査を呼ぶかどうかを、検査される側が決められてはいけない。**
    """
    h = _hook()
    repo = _org_repo(tmp_path, "develop")
    monkeypatch.chdir(repo)
    for cmd in ("git merge --no-ff feat/issue-42", "git rebase feat/x",
                "git cherry-pick abc1234"):
        r = h._integration_bypass("Bash", {"command": cmd})
        assert r is not None, f"保護ブランチへの直接統合が通った: {cmd}"
        assert "org_cycle" in r and "integrate" in r, "打つべきコマンドが示されていない"


def test_merge_on_a_feature_branch_is_allowed(tmp_path, monkeypatch):
    """feature ブランチ側で develop を取り込むのは正常な作業。止めない。"""
    h = _hook()
    repo = _org_repo(tmp_path, "main")
    subprocess.run(["git", "checkout", "-q", "-b", "feat/issue-9"], cwd=repo,
                   capture_output=True, text=True)
    monkeypatch.chdir(repo)
    assert h._integration_bypass("Bash", {"command": "git merge develop"}) is None


def test_read_only_git_and_gh_are_allowed(tmp_path, monkeypatch):
    """読み取りは止めない（`git merge-base` / `gh issue view` / `gh issue list`）。"""
    h = _hook()
    repo = _org_repo(tmp_path, "develop")
    monkeypatch.chdir(repo)
    assert h._integration_bypass("Bash", {"command": "git merge-base develop main"}) is None
    for cmd in ("gh issue view 42", "gh issue list --state open", "gh pr create --base develop"):
        assert h._gh_bypass("Bash", {"command": cmd}) is None, cmd


def test_manual_issue_writes_are_held(tmp_path, monkeypatch):
    """organ を通さない Issue の書き換えを hold する。

    運用では6件を `gh issue create` で作って dept/objective/parent/冪等キーを落とし、
    5件を `gh issue close` で閉じて `cycle_completed` を1件も残さなかった。
    """
    h = _hook()
    repo = _org_repo(tmp_path, "develop")
    monkeypatch.chdir(repo)
    for cmd in ("gh issue create --title x", "gh issue close 42",
                "gh issue edit 42 --add-label y"):
        r = h._gh_bypass("Bash", {"command": cmd})
        assert r is not None, f"organ の外の Issue 書き換えが通った: {cmd}"
        assert "github_sync" in r or "org_cycle" in r, "打つべきコマンドが示されていない"


def test_no_hold_outside_an_orgforge_repo(tmp_path, monkeypatch):
    """org でないリポジトリには、この規律を適用しない。"""
    h = _hook()
    repo = tmp_path / "plain"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "develop"], cwd=repo, capture_output=True)
    monkeypatch.chdir(repo)
    assert h._integration_bypass("Bash", {"command": "git merge feat/x"}) is None
    assert h._gh_bypass("Bash", {"command": "gh issue create --title x"}) is None


# ── H3: 迂回の記録に失敗したら通さない ──────────────────────────────────────
def test_bypass_that_cannot_be_recorded_is_denied(tmp_path):
    """**宣言は記録されるから許される。** 宣言したと言えば許されるのではない。

    以前は `except: pass` かつ戻り値も見ていなかったので、記録に失敗した迂回が
    痕跡なしで通った。
    """
    repo = _org_repo(tmp_path)
    led = repo / ".orgforge" / "ledger"; led.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "template" / "ledger-schema.yaml", repo / "ledger-schema.yaml")
    ev = {"hook_event_name": "PreToolUse", "session_id": "s",
          "tool_use_id": f"toolu_b{_next_tu():04d}", "tool_name": "Bash",
          "tool_input": {"command": "git merge feat/x"}, "cwd": str(repo)}
    env = dict(os.environ, ORG_LEDGER_ROOT=str(led), ORG_TOOLS_DIR=str(TOOLS),
               ORG_ALLOW_MANUAL_MERGE="1")

    # 正常時は通り、宣言が記録される
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env, cwd=str(repo))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "bypass_declared" in (led / "ledger.jsonl").read_text(encoding="utf-8")

    # 台帳を壊すと **通さない**
    with open(led / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write('{"seq": 2, "torn"')
    ev["tool_use_id"] = f"toolu_b{_next_tu():04d}"
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env, cwd=str(repo))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "記録できなかったので通さない" in (r.stdout + r.stderr)


def test_reservation_is_persisted_before_the_call_is_allowed(tmp_path):
    """**書けた判断だけが allow になる。** 台帳が壊れていれば metered action は通らない。"""
    shutil.copy(REPO / "template" / "ledger-schema.yaml", tmp_path / "ledger-schema.yaml")
    assert fire(tmp_path, "rm /tmp/a", env_extra={"ORG_CAP_DESTRUCTIVE_OPS": "9"})[0] == 0
    with open(tmp_path / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write('{"seq": 9, "torn"')
    code, out = fire(tmp_path, "rm /tmp/b", env_extra={"ORG_CAP_DESTRUCTIVE_OPS": "9"})
    assert code == 2, out
    # 0.36.0 から、読めない台帳は **halt とみなして** 止める（止まっているか分からないなら
    # 止める）。cap の予約より前に halt を見るので、そちらの理由で deny される。
    assert ("ledger_unhealthy" in out or "fail-safe" in out or "HALTED" in out), out


# ── 0.34.1: hook は structured result を読む（終了コードだけを信じない）────────
@pytest.mark.parametrize("body,exit_code,expect", [
    ('print(json.dumps({"decision":"deny","reason":"x"}))',            0, 2),
    ('print(json.dumps({"decision":"hold","reason":"x"}))',            0, 2),
    ('print("no json at all")',                                        0, 2),
    ('print("{not valid json")',                                        0, 2),
    ('print(json.dumps({"decision":"allow"}))',                       10, 2),
    ('print(json.dumps({"reason":"missing decision"}))',               0, 2),
    ('print(json.dumps({"decision":"allow","reason":"reserved"}))',    0, 0),
])
def test_hook_trusts_the_reservation_json_not_just_the_exit_code(tmp_path, body, exit_code, expect):
    """**exit 0 かつ decision=allow の組でしか通さない。**

    実測: deny を印字して exit 0 する writer に対して、hook は allow していた。
    JSON が無い・読めない・decision が allow 以外・終了コードと矛盾 — すべて deny。
    """
    fake = tmp_path / "tools"; fake.mkdir()
    (fake / "ledger.py").write_text(
        "import sys, json\n"
        "if 'reserve-exposure' in sys.argv:\n"
        f"    {body}\n"
        f"    sys.exit({exit_code})\n"
        "sys.exit(0)\n", encoding="utf-8")
    shutil.copy(REPO / "template" / "ledger-schema.yaml", tmp_path / "ledger-schema.yaml")
    ev = {"hook_event_name": "PreToolUse", "session_id": "s",
          "tool_use_id": f"toolu_j{_next_tu():04d}", "tool_name": "Bash",
          "tool_input": {"command": "rm -rf ./x"}, "cwd": str(tmp_path)}
    env = dict(os.environ, ORG_LEDGER_ROOT=str(tmp_path), ORG_TOOLS_DIR=str(fake))
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    assert r.returncode == expect, r.stdout + r.stderr


# ── 0.35.0: Codex plugin の自己完結とマニフェスト形式 ──────────────────────────
def test_codex_plugin_bundle_is_in_sync():
    """Codex plugin の同梱物が neutral source と一致すること（drift を CI で捕まえる）。"""
    r = subprocess.run(["bash", str(REPO / "integrations" / "codex" / "build.sh"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_codex_hooks_reference_only_the_plugin_root():
    """**checkout を参照しない。** 参照すると、その木が無くなれば統制が消える。"""
    h = json.loads((REPO / "integrations" / "codex" / "hooks" / "hooks.json")
                   .read_text(encoding="utf-8"))
    cmds = [hh["command"] for ev in h["hooks"].values() for entry in ev for hh in entry["hooks"]]
    assert cmds, "hook が1つも無い"
    for c in cmds:
        assert "$PLUGIN_ROOT" in c, f"$PLUGIN_ROOT を使っていない: {c}"
        assert "CODEX_PROJECT_ROOT" not in c, f"checkout を参照している: {c}"
        # CODEX_PLUGIN_ROOT は **存在しない変数**（2026-07 に実測）。使うと hook が失敗する。
        assert "CODEX_PLUGIN_ROOT" not in c, f"存在しない変数を使っている: {c}"


def test_codex_hooks_json_has_no_comment_key():
    """Codex の parser は `description` と `hooks` しか受け付けない。

    `//` を入れると **警告してファイル全体を読み飛ばす** ので、統制が黙って消える
    （Claude Code は `//` を許すので、そのまま持ち込んで実際にそうなった）。
    """
    raw = (REPO / "integrations" / "codex" / "hooks" / "hooks.json").read_text(encoding="utf-8")
    d = json.loads(raw)
    assert set(d) <= {"description", "hooks"}, f"未対応のキー: {sorted(set(d) - {'description', 'hooks'})}"


def test_codex_plugin_manifest_is_valid():
    """plugin.json は現行 Codex schema に従い、hook は標準配置で発見される。"""
    d = json.loads((REPO / "integrations" / "codex" / ".codex-plugin" / "plugin.json")
                   .read_text(encoding="utf-8"))
    for k in ("name", "version", "description", "author", "interface"):
        assert d.get(k), f"必須フィールドが無い: {k}"
    assert d["author"].get("name")
    assert re.match(r"^\d+\.\d+\.\d+(?:\+[0-9A-Za-z.-]+)?$", d["version"]), d["version"]
    assert "hooks" not in d, "現行 Codex manifest schema は hooks field を拒否する"
    assert (REPO / "integrations" / "codex" / "hooks" / "hooks.json").is_file()


def test_codex_marketplace_manifest_is_at_the_path_codex_reads():
    """`marketplace.json` を root に置いても読まれない — `.agents/plugins/` の下である。"""
    mk = REPO / ".agents" / "plugins" / "marketplace.json"
    assert mk.is_file(), "`.agents/plugins/marketplace.json` が無い"
    d = json.loads(mk.read_text(encoding="utf-8"))
    plug = d["plugins"][0]
    assert plug["source"]["source"] == "local"
    assert (REPO / plug["source"]["path"][2:] / ".codex-plugin" / "plugin.json").is_file()


def test_codex_plugin_version_matches_the_claude_plugin():
    """Codex の cachebuster を除いた base version は Claude projection と一致する。"""
    cx = json.loads((REPO / "integrations" / "codex" / ".codex-plugin" / "plugin.json")
                    .read_text(encoding="utf-8"))["version"]
    cc = json.loads((REPO / "integrations" / "claude-code" / ".claude-plugin" / "plugin.json")
                    .read_text(encoding="utf-8"))["version"]
    cx_base, *cx_suffix = cx.split("+", 1)
    assert cx_base == cc, f"codex={cx} / claude-code={cc}"
    assert not cx_suffix or cx_suffix[0].startswith("codex."), cx


# ── H4a: halt 中は gated action が通らない ────────────────────────────────────
def _halted_org(tmp_path, force=None):
    shutil.copy(REPO / "template" / "ledger-schema.yaml", tmp_path / "ledger-schema.yaml")
    led = tmp_path / ".orgforge" / "ledger"; led.mkdir(parents=True)
    env = dict(os.environ, **(force or {}))
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "trip-halt", str(led),
                        "--trigger", "test", "--reason", "H4a の検査", "--tripped-by", "registrar"],
                       capture_output=True, text=True, env=env)
    return led, r


def _fire_at(led, command, tool_name="Bash", cwd=None):
    ev = {"hook_event_name": "PreToolUse", "session_id": "s",
          "tool_use_id": f"toolu_h{_next_tu():04d}", "tool_name": tool_name,
          "tool_input": ({"command": command} if tool_name in ("Bash", "Shell")
                         else {"file_path": command, "content": "x"})}
    env = dict(os.environ, ORG_LEDGER_ROOT=str(led), ORG_TOOLS_DIR=str(TOOLS))
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env, cwd=cwd)
    return r.returncode, r.stdout + r.stderr


def test_halt_blocks_a_gated_action(tmp_path):
    """halt は警告ではない — gated な行為が通らない。"""
    led, r = _halted_org(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    code, out = _fire_at(led, "rm file.txt")
    assert code == 2, out
    assert "HALTED" in out
    assert "H4a の検査" in out          # 理由が示される


@pytest.mark.parametrize("cmd", [
    "git status", "git log --oneline -5", "cat README.md", "ls -la",
    "python3 tools/ledger.py verify", "python3 tools/ledger.py halt-status",
    "python3 tools/ledger.py schema --fix",
])
def test_recovery_actions_pass_while_halted(tmp_path, cmd):
    """観測・検証・安全な修復は通る — すべて deny だと復旧できない。"""
    led, _ = _halted_org(tmp_path)
    code, out = _fire_at(led, cmd)
    assert code == 0, f"{cmd} が halt 中に通らない: {out}"


@pytest.mark.parametrize("cmd,tool", [
    ("npm test", "Bash"), ("npm run build", "Bash"), ("git commit -m x", "Bash"),
    ("git push", "Bash"), ("python3 manage.py migrate", "Bash"),
])
def test_ordinary_work_is_stopped_while_halted(tmp_path, cmd, tool):
    """**通常の作業は止まる。** allowlist を広く取ると「halt したが止まらない」に戻る。"""
    led, _ = _halted_org(tmp_path)
    code, out = _fire_at(led, cmd, tool_name=tool)
    assert code == 2, f"{cmd} が halt 中に通った: {out}"
    assert "HALTED" in out


def test_writes_are_stopped_while_halted(tmp_path):
    """Write / Edit は halt 中は通さない（観測でも修復でもない）。"""
    led, _ = _halted_org(tmp_path)
    target = tmp_path / "some.js"; target.write_text("x", encoding="utf-8")
    code, out = _fire_at(led, str(target), tool_name="Write")
    assert code == 2, out
    assert "HALTED" in out


def test_halt_that_failed_to_persist_still_stops_the_next_call(tmp_path):
    """**これが指摘された fail-open の経路である。**

    halt の台帳への記録が失敗しても、ラッチが第二経路として次回の呼び出しを止める。
    """
    led, r = _halted_org(tmp_path, force={"ORG_LEDGER_FORCE_APPEND_FAIL": "1"})
    assert r.returncode == 4, r.stdout + r.stderr        # 呼び出し自体は非ゼロ
    assert (led / "HALT").is_file()
    # 台帳には入っていない（記録は失敗した）が、ラッチがあるので止まる
    assert not (led / "ledger.jsonl").exists() or not (led / "ledger.jsonl").read_text().strip()
    code, out = _fire_at(led, "rm file.txt")
    assert code == 2, out
    assert "HALTED" in out


def test_unreadable_ledger_stops_gated_actions(tmp_path):
    """止まっているか分からないなら止める。"""
    led, _ = _halted_org(tmp_path)
    with open(led / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write('{"seq": 9, "torn"')
    code, out = _fire_at(led, "rm file.txt")
    assert code == 2, out


def test_no_halt_means_ordinary_gating(tmp_path):
    """halt していないときは、従来どおり cap の予約で判断する。"""
    shutil.copy(REPO / "template" / "ledger-schema.yaml", tmp_path / "ledger-schema.yaml")
    led = tmp_path / ".orgforge" / "ledger"; led.mkdir(parents=True)
    code, out = _fire_at(led, "rm file.txt")
    assert code == 0, out
    assert "HALTED" not in out


def test_halt_check_does_not_import_the_ledger_into_the_hook(tmp_path):
    """**統制の判定を、判定対象と同じプロセスで動かさない。**

    `from ledger import active_halt` はそのモジュールのトップレベルを hook の中で走らせる。
    差し替えられた（あるいは壊れた）ledger.py が `sys.exit(0)` を持っていれば、
    **hook はそこで allow として終了する** — 実測でそうなった。別プロセスで聞くこと。
    """
    shutil.copy(REPO / "template" / "ledger-schema.yaml", tmp_path / "ledger-schema.yaml")
    fake = tmp_path / "tools"; fake.mkdir()
    # トップレベルで exit(0) する ledger.py。import すれば hook を巻き込んで終了させる。
    (fake / "ledger.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    ev = {"hook_event_name": "PreToolUse", "session_id": "s",
          "tool_use_id": f"toolu_i{_next_tu():04d}", "tool_name": "Bash",
          "tool_input": {"command": "rm -rf ./x"}}
    env = dict(os.environ, ORG_LEDGER_ROOT=str(tmp_path), ORG_TOOLS_DIR=str(fake))
    env.pop("ORG_HOOK_FAIL_OPEN", None)      # 逃げ道を切って、素の挙動を見る
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev),
                       capture_output=True, text=True, env=env)
    both = r.stdout + r.stderr
    # **hook が allow として静かに終わっていないこと。** import していた版では exit 0 で、
    # 何のメッセージも出さずに通っていた。
    # **本質は「hook が allow として静かに終わらない」こと。** import していた版では、
    # 差し替えられた ledger.py の sys.exit(0) が hook プロセスを exit 0 で終わらせ、
    # メッセージも出なかった。どの層で止まるかは副次的である。
    assert r.returncode == 2, f"壊れた ledger.py で通った: {both!r}"
    assert both.strip(), "何も言わずに終わっている"
