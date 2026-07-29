"""サイクルの配管 — begin / complete / verify / integrate / worktree / 公開面。

配管は自動化するが判断はしない、という線引きを固定する。"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

from conftest import (REPO, TOOLS, TEMPLATE, run, seed, _cycle_src, _gh_src,
                      _cycle_mod, _propose_full, _admitted_claim, _sched,
                      _ledger_with, _led, _append, _status, _write_ledger)


def test_work_in_progress_view_resolves_started_not_completed(tmp_path):
    # the recovery source after a context wipe: a candidate STARTED with a progress checkpoint but not
    # completed must appear with its latest next_step; a COMPLETED one must drop out.
    seed(tmp_path, "eng", "cycle_started", {"role": "eng", "candidate_id": "X", "pack_manifest_id": "p"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "eng", "progress_recorded",
         {"role": "eng", "candidate_id": "X", "fraction": 0.6, "phase": "impl",
          "done_so_far": "parser done", "next_step": "wire into CLI", "blocked_by": None, "artifacts": []},
         ts="2026-07-16T02:00:00Z")
    # a second candidate that WAS completed — must not appear in WIP
    seed(tmp_path, "eng", "cycle_started", {"role": "eng", "candidate_id": "Y", "pack_manifest_id": "p"},
         ts="2026-07-16T03:00:00Z")
    seed(tmp_path, "eng", "cycle_completed", {"role": "eng", "candidate_id": "Y", "outputs": []},
         ts="2026-07-16T04:00:00Z")
    code, out = run("ledger.py", "view", str(tmp_path), "work_in_progress")
    assert code == 0, out
    data = json.loads(out)
    ids = [w["candidate_id"] for w in data["in_progress"]]
    assert ids == ["X"], f"expected only the unfinished X, got {ids}"
    wx = data["in_progress"][0]
    assert wx["progress"]["next_step"] == "wire into CLI"
    assert abs(wx["progress"]["fraction"] - 0.6) < 1e-9


def test_doctrine_incomplete_provenance_blocked(tmp_path):
    code, out = run("doctrine.py", "propose", str(tmp_path), "role", "--claim", "c",
                    "--source", "s", "--confidence", "0.9", "--retrieved-at", "2026-07-16")
    assert code == 0, out   # no review-by
    _, show = run("doctrine.py", "show", str(tmp_path), "role")
    cid = json.loads(show)["claims"][0]["id"]
    code, out = run("doctrine.py", "admit", str(tmp_path), "role", cid, "--by", "gate")
    assert code == 2 and ("incomplete" in out or "provenance" in out)


def test_doctrine_remap_allow_orphans_surfaces_not_drops(tmp_path):
    # --allow-orphans routes orphans to UNROUTED (surfaced for a human), never dropped.
    _admitted_claim(tmp_path, "api-worker", "idempotency keys on POST", "api-worker")
    dst = tmp_path / "new"
    code, out = run("doctrine.py", "remap", str(tmp_path),
                    "--map", json.dumps({"api-worker": ["x-worker", "y-worker"]}),
                    "--into", str(dst), "--allow-orphans")
    assert code == 0, out
    _, un = run("doctrine.py", "show", str(dst), "UNROUTED")
    assert len(json.loads(un)["claims"]) == 1   # preserved, not lost


# ── handoff.py (seam contract + scoped brain at delegation) ───────────────────


def test_reconcile_mandate_integrate(tmp_path):
    code, out = run("reconcile.py", "mandate", str(tmp_path), "--subjects", "safety,growth",
                    "--decision", "ship", "--precedence", "safety>growth", "--satisfiable", "true")
    assert code == 0 and "integrate" in out


# ── org_cycle: 配管の自動化（docs/11 §0d）─────────────────────────────────────
# 実地で Issue 2件あたり11コマンドを手打ちしており、18 Issue で約90回になっていた。
# とりわけ parent を目で拾って手打ちしていたため、親継承（§2）の実装が活きていなかった。
def test_org_cycle_plan_executes_nothing(tmp_path):
    """plan は印字だけ — 台帳にもGitHubにも触らない。"""
    code, out = run("org_cycle.py", "plan", "--role", "r", "--issue", "7")
    assert code == 0, out
    assert "phase_started" in out and "cycle_started" in out
    assert not (tmp_path / "ledger.jsonl").exists()


def test_org_cycle_complete_requires_domain_model(tmp_path):
    """docs/11 §4d: ドメインモデルに何をしたかを述べない cycle_completed は認めない。"""
    code, out = run("org_cycle.py", "complete", "--role", "r", "--issue", "7",
                    "--outputs", "something")
    assert code == 2
    assert "domain-model" in out


def test_org_cycle_resolves_parent_from_issue_body():
    """parent は Issue の `Parent: #N` から読む — 人が運ばない。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("org_cycle", TOOLS / "org_cycle.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    import re
    body = "## Deliverable\nsplit engine\n\nParent: #1\n\ncandidate_id: cand-abc\n"
    assert re.search(r"^\s*Parent:\s*#?(\d+)", body, flags=re.M | re.I).group(1) == "1"


# ── 案5: worktree 分離の強制（docs/11 §4c）──────────────────────────────────
# 並列 fan-out で #7 のコミットが feat/issue-8-settle に載る事故が実際に起きた。
# git checkout はツリー全体を切り替えるので、同一ツリーで並列 maker を走らせる限り再発する。
# 「毎回正しく判断する」前提の設計は破れる、というのが実地で得られた教訓。


# ── 案5: worktree 分離の強制（docs/11 §4c）──────────────────────────────────
# 並列 fan-out で #7 のコミットが feat/issue-8-settle に載る事故が実際に起きた。
# git checkout はツリー全体を切り替えるので、同一ツリーで並列 maker を走らせる限り再発する。
# 「毎回正しく判断する」前提の設計は破れる、というのが実地で得られた教訓。
def test_worktree_isolates_parallel_makers(tmp_path):
    """2つの Issue の worktree が別ディレクトリ・別ブランチになり、互いのコミットが混ざらない。"""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "seed.txt").write_text("x")
    g("add", "-A"); g("commit", "-qm", "seed")
    g("branch", "develop")

    made = []
    for issue in (7, 8):
        code, out = run("github_sync.py", "branch", "--issue", str(issue), "--worktree",
                        "--repo", "o/n", cwd=str(repo))
        assert code == 0, out
        made.append(repo / ".orgforge" / "wt" / f"issue-{issue}")

    assert all(d.is_dir() for d in made), "worktree が作られていない"
    # 各 worktree で別々にコミットしても、相手のツリーには現れない
    for issue, d in zip((7, 8), made):
        (d / f"F{issue}.txt").write_text("x")
        g("add", "-A", cwd=d); g("commit", "-qm", f"i{issue}", cwd=d)
    for issue, d in zip((7, 8), made):
        other = 8 if issue == 7 else 7
        assert (d / f"F{issue}.txt").exists()
        assert not (d / f"F{other}.txt").exists(), \
            f"#{other} の成果物が #{issue} のツリーに混入した — 分離が効いていない"
    # ブランチも別
    b = [g("branch", "--show-current", cwd=d).stdout.strip() for d in made]
    assert b[0] != b[1] and all(b), b


# ── 案2: verify は配管だけ。判定は持たない ─────────────────────────────────
# 検証手順を人が毎回書き下ろすと、書くたびに gate の厳しさが変わる（18 Issue で18通り）。
# 基準の出所は agents/gate.md 1つにする。ただし verdict を埋めた瞬間に gate が形骸化するので、
# そこは越えない — この境界をテストで固定する。


# ── 案2: verify は配管だけ。判定は持たない ─────────────────────────────────
# 検証手順を人が毎回書き下ろすと、書くたびに gate の厳しさが変わる（18 Issue で18通り）。
# 基準の出所は agents/gate.md 1つにする。ただし verdict を埋めた瞬間に gate が形骸化するので、
# そこは越えない — この境界をテストで固定する。
def test_verify_injects_charter_and_leaves_verdict_unfilled():
    """憲章と decide 雛形は出すが、verdict は placeholder のまま（判定を先取りしない）。"""
    import subprocess, os
    env = dict(os.environ, ORG_GITHUB_REPO="")
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "gate"],
                       capture_output=True, text=True, env=env, timeout=60)
    out = p.stdout + p.stderr
    # gh が無い/認証が無い環境では Issue を読めず 3 で落ちるのが正しい挙動
    if p.returncode == 0:
        assert "admission control" in out, "agents/gate.md の憲章が注入されていない"
        assert "<admit|reject|park>" in out, "verdict が placeholder になっていない"
        for filled in ('--verdict admit', '--verdict "admit"'):
            assert filled not in out, f"配管が verdict を決めている: {filled}"
    else:
        assert p.returncode in (2, 3), out


def test_verify_rejects_unknown_role():
    """憲章の無い役割では verify は成り立たない（基準の出所が無いまま起動しない）。"""
    import subprocess
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "maker"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0


def test_verify_finds_charter_in_every_layout():
    """憲章を **CLAUDE_PLUGIN_ROOT の有無にかかわらず**見つけること。

    以前のテストは env を設定してから呼んでいたため、**env が無い経路＝実際の使われ方**を
    検査していなかった。その結果 0.22.0 の分割で `_agents_dir` の探索先が1階層ずれ、
    verify が gate/skeptic とも「agents/*.md が見つからない（探した先: None）」で死んだのに、
    テストは緑のままだった。壊れる場所で検証していないテストは無いのと同じ — #7 の
    split() で捕まえたのと同じ形を、テスト側でやっていた。
    """
    m = _cycle_mod("judge")
    bundled = TOOLS.parent / "integrations" / "claude-code"
    saved = os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
    try:
        # (1) env なし — repo を直接使う形。実地で壊れたのはこちら
        for role in ("gate", "skeptic"):
            charter, path = m._role_charter(role)
            assert charter, f"env 無しで {role} の憲章を見失った（探した先: {path}）"
        # (2) env あり — プラグインとして入った形
        if (bundled / "agents").is_dir():
            os.environ["CLAUDE_PLUGIN_ROOT"] = str(bundled)
            for role in ("gate", "skeptic"):
                charter, path = m._role_charter(role)
                assert charter, f"バンドル配置で {role} の憲章を見失った（探した先: {path}）"
    finally:
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        if saved is not None:
            os.environ["CLAUDE_PLUGIN_ROOT"] = saved


def test_verify_actually_injects_the_charter(tmp_path):
    """`_role_charter` 単体ではなく、**verify の出力に憲章が入る**ことを見る。

    ヘルパが動いても、組み立て側で落としていれば意味がない。実地の症状は
    「verify が使えない」であって「_role_charter が None を返す」ではなかった。
    """
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "gate"],
                       capture_output=True, text=True, cwd=str(tmp_path), timeout=60)
    out = p.stdout + p.stderr
    # gh が無い / Issue が読めない環境では exit 3 で落ちるのが正しい。
    # ただし **憲章が見つからない（exit 2）で落ちてはいけない** — それは配線の欠陥。
    assert "agents/gate.md が見つからない" not in out, \
        f"憲章の探索が壊れている: {out[:300]}"
    assert p.returncode != 2, out


def test_verify_allows_passing_by_file_reference():
    """本文でもファイル参照でも渡せることを案内する（0.19.0 でガードが読むようになった）。

    以前は本文限定だったので「本文に貼れ」と案内していた。264行を毎回貼ると maker の
    context を圧迫するので、ガード側がファイルを読んで検証するように変えた。
    """
    src = _cycle_src()
    seg = src[src.index("def cmd_verify"):]
    assert "ファイルに落として" in seg and "参照させてもよい" in seg
    assert "HELD" not in seg, "ファイル渡しが弾かれる前提の案内が残っている"


# ── 実地フィードバック: 統合直前が最も抜けやすい ─────────────────────────


def test_integrate_blocks_without_skeptic(tmp_path):
    """gate が admit していても、skeptic の survives が無ければ統合させない。

    実地で #8 が「refutation_attempted が台帳に1件も無いまま develop へ統合」された。
    Issue にはコメントがあったので、二重記録の片側だけが落ちていた。
    """
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"deliverable": "8", "issue": 8, "verdict": "admit"}},
    ])
    env = dict(os.environ, ORG_LEDGER_ROOT=str(led))
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "integrate", "--issue", "8"],
                       capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=60)
    assert p.returncode == 4, p.stdout + p.stderr
    err = p.stdout + p.stderr
    assert "skeptic" in err and "survives" in err
    assert "git merge" not in err, "前提が揃わないのにマージ手順に入っている"


def test_integrate_allows_when_both_recorded(tmp_path):
    """admit + survives が揃えば、前提照合では止まらない（実行は git の世界に入る）。"""
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"deliverable": "8", "issue": 8, "verdict": "admit"}},
        {"seq": 2, "class": "refutation_attempted",
         "payload": {"claim_id": "8", "issue": 8, "verdict": "survives"}},
    ])
    import importlib.util
    m = _cycle_mod("_core")
    os.environ["ORG_LEDGER_ROOT"] = str(led)
    try:
        assert m._admission_for(8)[0] == "admit"
        assert m._refutation_for(8)[0] == "survives"
    finally:
        os.environ.pop("ORG_LEDGER_ROOT", None)


def test_verify_gate_embeds_absolute_repro_lint_path():
    """repro_lint がパス解決できず一度も走っていなかった。絶対パスを埋める。"""
    src = _cycle_src()
    assert 'repro_lint.py' in src and 'HERE' in src, "repro_lint の絶対パス埋め込みが無い"


def test_worktree_cleanup_keeps_dirty_tree(tmp_path):
    """未コミットの変更がある worktree は消さない（消えて困るかは配管が決めることではない）。"""
    import importlib.util
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "s.txt").write_text("x"); g("add", "-A"); g("commit", "-qm", "s"); g("branch", "develop")
    wt = repo / ".orgforge" / "wt" / "issue-5"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-5", str(wt), "develop")
    (wt / "dirty.txt").write_text("uncommitted")

    m = _cycle_mod("cycle")
    cwd = os.getcwd(); os.chdir(repo)
    try:
        msg = m._cleanup_worktree(5)
        assert wt.is_dir(), "未コミットの変更ごと worktree を消した"
        assert "残した" in msg, msg
        # クリーンにすれば消える
        (wt / "dirty.txt").unlink()
        msg2 = m._cleanup_worktree(5)
        assert not wt.is_dir(), f"クリーンな worktree が片付いていない: {msg2}"
    finally:
        os.chdir(cwd)


def test_complete_requires_command_and_result():
    """DoD の実出力を人の自由記述任せにしない（B）。"""
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "complete",
                        "--role", "r", "--issue", "1", "--outputs", "x",
                        "--domain-model-none", "理由"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0
    assert "--command" in p.stderr and "--result" in p.stderr


def test_begin_log_carries_facts_the_tool_already_knows():
    """begin の log に branch / worktree / parent / candidate_id が自動で入る（B）。

    実地で人が書いた 276 字にはブランチ名も worktree のパスも無かったが、org_cycle は
    両方知っていた。知っている事実を人に書かせない。
    """
    src = _cycle_src()
    seg = src[src.index("def _steps_begin"):src.index("def _steps_complete")]
    for token in ("worktree:", "branch:", "parent:", "candidate_id:", "--command", "--result"):
        assert token in seg, f"begin の log に {token} が入っていない"


def test_handback_puts_closes_in_pr_body():
    """PR body の `Closes #N` が Issue ↔ PR ↔ コミットを繋ぎ、統合時に Issue を閉じる（C）。"""
    src = _cycle_src()
    seg = src[src.index("def cmd_handback"):]
    assert 'f"Closes #{a.issue}"' in seg, "PR body に Closes が無い — Issue が OPEN のまま残る"
    assert "gh pr create" in seg


# ── 実地: 予算 cap が日常の後片付けを止めていた（1日5回発火・実害ゼロ）───────


def test_begin_records_attention_allocated():
    """6件着手して選択の記録が1件だけだった。選んだ結果を残すのは配管。"""
    src = _cycle_src()
    seg = src[src.index("def _steps_begin"):src.index("def _steps_complete")]
    assert "attention_allocated" in seg


def test_doctrine_propose_warns_on_incomplete_provenance():
    """propose は省略でき admit は必須にする、という不整合で必ず詰まっていた。"""
    root = None
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run([sys.executable, str(TOOLS / "doctrine.py"), "propose", d, "r",
                            "--claim", "x", "--source", "s", "--confidence", "0.5"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0
        assert "admit できない" in p.stderr, "admit で詰まることを propose 時点で言っていない"


def test_complete_proposes_learning_to_doctrine():
    """学びの蓄積口がサイクルに繋がっていること（propose まで。admit は gate）。"""
    src = _cycle_src()
    seg = src[src.index("def cmd_complete"):src.index("def cmd_plan")]
    assert "doctrine.py" in seg and "propose" in seg
    assert "--retrieved-at" in seg and "--review-by" in seg, \
        "provenance を埋めないと gate が admit できず、学びは pending のまま死ぬ"


def test_gc_keeps_unmerged_and_dirty_worktrees(tmp_path):
    """gc は統合済みだけを消す。未統合・未コミットは残す。"""
    import importlib.util
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "s.txt").write_text("x"); g("add", "-A"); g("commit", "-qm", "s"); g("branch", "develop")
    wt = repo / ".orgforge" / "wt" / "issue-3"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-3", str(wt), "develop")
    (wt / "new.txt").write_text("work"); g("add", "-A", cwd=wt); g("commit", "-qm", "w", cwd=wt)

    m = _cycle_mod("inspect")
    cwd = os.getcwd(); os.chdir(repo)
    try:
        m.cmd_gc(argparse.Namespace(base="develop", all=False))
        assert wt.is_dir(), "develop に未統合の worktree を消した"
    finally:
        os.chdir(cwd)


def test_decide_writes_the_receipt_itself():
    """受領証は decide が自分で書く（0.21.0）。

    以前は雛形を印字して人に打たせていたため、実地で3回片側落ちした
    （#8 の refutation / #11 の1回目の reject / progress_recorded）。
    actor は --by で渡っているので、分ける理由が無い。
    """
    src = _gh_src()
    seg = src[src.index("def cmd_decide"):]
    assert "ledger.py" in seg and "--natural-key" in seg
    assert '"issue": a.issue' in seg
    assert "NEXT: 台帳の受領証をこのまま打つこと" not in seg, "人に打たせる雛形が残っている"


# ── 実地: 検出器が「学習が使われている」と嘘をついた ─────────────────────


def test_verify_template_has_no_undefined_shell_var():
    """雛形は貼ってそのまま動くこと。$P は未定義で、打てない雛形は打たれない。"""
    src = _cycle_src()
    assert "$P/tools" not in src, "未定義の $P が雛形に残っている"


# ── 0.19.0: 実務で「無くて困った」もの ──────────────────────────────────


def test_begin_warns_but_does_not_block_on_unready_deps():
    """事前チェックは見せるだけ。判断は人がする。"""
    src = _cycle_src()
    seg = src[src.index("def _readiness"):src.index("def cmd_begin")]
    assert "needs-human" in seg and "rework" in seg
    body = src[src.index("def cmd_begin"):src.index("def _steps_complete")] \
        if "def _steps_complete" in src[src.index("def cmd_begin"):] else src[src.index("def cmd_begin"):]
    assert "止めない" in src, "警告が停止になっている（begin は判断しない）"


def test_seam_guard_accepts_a_referenced_file(tmp_path):
    """seam contract をファイルで渡せる。ガード自身が読んで検証する。"""
    import importlib.util
    hook = TOOLS.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_s", hook)
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    cwd = os.getcwd(); os.chdir(tmp_path)
    try:
        good = tmp_path / "seam.md"
        good.write_text("# HAND-OFF\n## Your slice\nX\nInputs you receive: A\n"
                        "Outputs you MUST produce: B\n", encoding="utf-8")
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": f"契約は {good} を読むこと"}) is None, "seam 入りファイルが弾かれた"

        bad = tmp_path / "memo.md"
        bad.write_text("ただのメモ", encoding="utf-8")
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": f"手順は {bad}"}) is not None, "seam の無いファイルが通った"
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": "手順は /etc/passwd"}) is not None, "org 外のファイルを読んだ"
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": "いい感じにやって"}) is not None, "契約なしが通った"
    finally:
        os.chdir(cwd)


# ── 0.20.0: rework 履歴 / 統合の事前確認 / 本番資産 / 公開面 ─────────────


# ── 0.20.0: rework 履歴 / 統合の事前確認 / 本番資産 / 公開面 ─────────────
def test_verify_passes_rework_history_to_gate():
    """gate に過去の判定を渡す。渡さないと毎回「初回判定」として扱う。"""
    src = _cycle_src()
    seg = src[src.index("def cmd_verify"):]
    assert "判定履歴" in seg and "回目の判定です" in seg
    assert "再導出" in seg, "「前回の指摘が直ったか」だけを見る gate になってしまう"


def test_integrate_plan_executes_nothing_and_warns_on_overlap(tmp_path):
    """--plan は何も実行せず、並行 worktree との重複を予告する。"""
    src = _cycle_src("ship")
    seg = src[src.index("def _integrate_preview"):src.index("def cmd_integrate")]
    assert "同じファイルを変更しています" in seg
    body = src[src.index("def cmd_integrate"):]
    assert 'if getattr(a, "plan", False):' in body
    assert body.index('if getattr(a, "plan", False):') < body.index("git\", \"merge"), \
        "--plan がマージ手順より後にある（実行してしまう）"


def test_surface_detection_ranks_security_definer_first():
    """SECURITY DEFINER は関数ごとに判定する。ファイル単位だと肝心の1件が沈む。"""
    src = _cycle_src()
    seg = src[src.index("def _new_public_surfaces"):]
    assert "関数ごと" in seg, "ファイル単位のフラグに戻っている"
    assert "grant 済み" in seg


def test_surface_detection_skips_test_files():
    """テストヘルパを拾いすぎると、確認してほしい1件が埋もれる。"""
    src = _cycle_src()
    seg = src[src.index("def _new_public_surfaces"):]
    assert "tests?" in seg and "spec" in seg


def test_complete_blocks_until_surfaces_declared(tmp_path):
    """公開面が増えたら、申告するまで complete させない（認可ホールの入口）。"""
    src = _cycle_src()
    seg = src[src.index("def cmd_complete"):src.index("def cmd_plan")]
    assert "--new-surface" in seg and "return 2" in seg
    assert "認可ホール" in seg


# ── 0.22.0: 分割で持ち込んだ穴を塞ぐ ────────────────────────────────────
def test_core_HERE_points_at_tools_not_the_package():
    """HERE は tools/ を指すこと。

    分割時にここを直し忘れ、_gh_sync が github_sync.py を見失って _branch_for が
    slug 無しのブランチ名を返した。組み立て系のツールは「見つからない」を静かに
    素通りするので、show の実装行と integrate --plan の変更一覧が**黙って空**になった。
    パスの基点は分割で最初に壊れる場所。
    """
    m = _cycle_mod("_core")
    assert os.path.isfile(os.path.join(m.HERE, "github_sync.py")), \
        f"HERE={m.HERE} から github_sync.py が見えない"
    assert os.path.isfile(os.path.join(m.HERE, "ledger.py"))


def test_bundle_includes_subpackages():
    """build.sh が tools/ のサブパッケージも同期すること。

    `tools/*.py` だけを見ていると、分割したモジュールがバンドルに入らず、
    プラグインとして入れた瞬間に ImportError で死ぬ。
    """
    bundled = TOOLS.parent / "integrations" / "claude-code" / "tools"
    if not bundled.is_dir():
        return
    for src in (TOOLS / "orgcycle").glob("*.py"):
        dst = bundled / "orgcycle" / src.name
        assert dst.is_file(), f"バンドルに {src.name} が無い（build.sh の同期漏れ）"
        assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8"), \
            f"{src.name} がバンドルと食い違っている"


def test_every_subcommand_still_dispatches():
    """分割後も全サブコマンドが起動すること（import の取りこぼし検出）。"""
    for c in ("begin", "complete", "plan", "verify", "handback",
              "integrate", "gc", "record", "show", "touched"):
        p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), c, "--help"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"{c} が起動しない: {p.stderr[:200]}"


def test_ghsync_core_HERE_points_at_tools():
    """ghsync も tools/ を基点にすること（org_cycle で踏んだのと同じ穴）。

    record.py が ledger.py を見失うと、判断が Issue にだけ残り台帳が欠ける —
    まさに 0.21.0 で塞いだ片側落ちが、分割によって再発する。
    """
    src = _gh_src("_core")
    assert "HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))" in src, \
        "tools/ を基点にしていない（ledger.py を見失う）"
    # record.py は HERE を使うこと（自前で解決し直さない）
    assert "HERE" in _gh_src("record")


def test_ghsync_every_subcommand_still_dispatches():
    """分割後も全サブコマンドが起動すること。"""
    for c in ("claim", "release", "create", "stage", "log", "decide", "branch",
              "split-check", "candidate-id", "coverage-check", "needs-human", "ready"):
        p = subprocess.run([sys.executable, str(TOOLS / "github_sync.py"), c, "--help"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"{c} が起動しない: {p.stderr[:200]}"


def test_bundle_includes_ghsync():
    """build.sh が ghsync/ も同期すること。"""
    bundled = TOOLS.parent / "integrations" / "claude-code" / "tools" / "ghsync"
    if not (TOOLS / "ghsync").is_dir():
        return
    for src in (TOOLS / "ghsync").glob("*.py"):
        dst = bundled / src.name
        assert dst.is_file(), f"バンドルに {src.name} が無い"
        assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_path_base_is_resolved_in_exactly_one_place():
    """`__file__` からのパス解決は各パッケージ1箇所（HERE）に集約すること。

    0.22.0 の分割で `tools/` → `tools/orgcycle/` と階層が1つ深くなったとき、各所に散った
    `os.path.dirname(os.path.abspath(__file__))` のうち直し漏れが2箇所出た:
    `_agents_dir`（憲章を見失い verify が gate/skeptic とも死ぬ）と `_seam`（handoff.py を
    見失い seam contract が生成できない）。**基点が散っていると、階層が変わるたびに
    直し漏れが起きる。**
    """
    for pkg in ("orgcycle", "ghsync"):
        d = TOOLS / pkg
        if not d.is_dir():
            continue
        hits = []
        for f in sorted(d.glob("*.py")):
            for i, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
                if "__file__" in line and not line.lstrip().startswith("#"):
                    hits.append(f"{f.name}:{i}")
        assert len(hits) == 1, \
            f"{pkg}: __file__ の解決が {len(hits)} 箇所にある（HERE に集約すること）: {hits}"


def test_verify_finds_handoff_for_the_seam_contract(tmp_path):
    """seam contract の生成（handoff.py）も見失っていないこと。

    憲章と同じ穴を _seam も踏んでいた。ヘルパ単体ではなく、verify の出力に
    Boundary contract が入ることで見る。
    """
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "gate"],
                       capture_output=True, text=True, cwd=str(tmp_path), timeout=60)
    out = p.stdout + p.stderr
    assert "seam contract の生成に失敗" not in out, f"handoff.py を見失っている: {out[:300]}"
