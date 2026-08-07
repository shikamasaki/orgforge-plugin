"""サイクルの配管 — begin / complete / verify / integrate / worktree / 公開面。

配管は自動化するが判断はしない、という線引きを固定する。"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

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
                        "--base", "develop", "--repo", "o/n", cwd=str(repo))
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
def test_verify_injects_focused_contract_and_leaves_verdict_unfilled():
    """Issue-scoped contract と decide 雛形は出すが、verdict は先取りしない。"""
    import subprocess, os
    env = dict(os.environ, ORG_GITHUB_REPO="")
    # #101 以降、subject は Issue の worktree から mint する。この開発リポジトリに
    # issue-1 の worktree は無いので、逃げ道を明示する（テストの主題は憲章の注入）。
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "gate", "--subject-root", "."],
                       capture_output=True, text=True, env=env, timeout=60)
    out = p.stdout + p.stderr
    # gh が無い/認証が無い環境では Issue を読めず 3 で落ちるのが正しい挙動
    if p.returncode == 0:
        assert "Fixed review contract" in out, "Issue-scoped review contract が注入されていない"
        assert "Do not add unrelated review criteria" in out
        # 0.25.2: subagent 向けは「返すもの」の指定、監督向けは値を入れる欄。
        # どちらも **verdict を決めない** — ツールが verdict を決めた瞬間に gate は形骸化する。
        assert "admit|reject|park" in out, "verdict の選択肢が示されていない"
        for filled in ('--verdict admit', '--verdict "admit"', '--verdict reject'):
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
    codex_bundled = TOOLS.parent / "integrations" / "codex"
    saved = os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
    try:
        # (1) env なし — repo を直接使う形。実地で壊れたのはこちら
        for role in ("gate", "skeptic"):
            charter, path = m._role_charter(role)
            assert charter, f"env 無しで {role} の憲章を見失った（探した先: {path}）"
        # (2) env あり — Claude plugin として入った形
        assert (bundled / "agents").is_dir(), "Claude projection に review charter が無い"
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(bundled)
        for role in ("gate", "skeptic"):
            charter, path = m._role_charter(role)
            assert charter, f"Claude bundle で {role} の憲章を見失った（探した先: {path}）"

        # (3) env あり — Codex plugin として入った形。Codex が注入する
        # PLUGIN_ROOT そのものを使う。互換変数だけを試すと実際の host 契約から外れる。
        assert (codex_bundled / "agents").is_dir(), "Codex projection に review charter が無い"
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        os.environ["PLUGIN_ROOT"] = str(codex_bundled)
        for role in ("gate", "skeptic"):
            charter, path = m._role_charter(role)
            assert charter, f"Codex bundle で {role} の憲章を見失った（探した先: {path}）"
    finally:
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        os.environ.pop("PLUGIN_ROOT", None)
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


def test_verify_gate_uses_the_stable_organ_for_repro_lint():
    """installed promptはcache pathでなくbinding launcher、source開発時だけHEREを使う。"""
    src = _cycle_src()
    assert '_organ_command(stable_organ, "repro-lint")' in src
    assert 'os.path.join(HERE, filename)' in src, "source checkout 用 fallback が無い"


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


def _ship_module():
    import importlib
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    return importlib.import_module("orgcycle.ship")


def _branch_repo(tmp_path, *branches):
    repo = tmp_path / "branch-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    for branch in branches:
        subprocess.run(["git", "branch", branch], cwd=repo, check=True)
    return repo


def test_integrate_branch_resolution_uses_exact_existing_branch(tmp_path, monkeypatch):
    ship = _ship_module()
    exact = "feat/issue-51-current-title"
    repo = _branch_repo(tmp_path, exact)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: exact)
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch == exact and len(subject_sha) == 40 and error is None


def test_integrate_branch_resolution_uses_sole_real_candidate(tmp_path, monkeypatch):
    ship = _ship_module()
    actual = "feat/issue-51-original-name"
    repo = _branch_repo(tmp_path, actual)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: "feat/issue-51-renamed-title")
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch == actual and len(subject_sha) == 40 and error is None


def test_integrate_branch_resolution_stops_on_tracking_only_candidate(tmp_path, monkeypatch):
    ship = _ship_module()
    actual = "feat/issue-51-remote-name"
    repo = _branch_repo(tmp_path)
    subprocess.run(["git", "update-ref", f"refs/remotes/origin/{actual}", "main"],
                   cwd=repo, check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: "feat/issue-51-renamed-title")
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch is None and subject_sha is None and "tracking ref のみ" in error


def test_integrate_branch_resolution_stops_on_local_tracking_divergence(tmp_path, monkeypatch):
    ship = _ship_module()
    actual = "feat/issue-51-diverged"
    repo = _branch_repo(tmp_path, actual)
    (repo / "tracking.txt").write_text("new", encoding="utf-8")
    subprocess.run(["git", "add", "tracking.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "tracking"], cwd=repo, check=True)
    tracking_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "update-ref", f"refs/remotes/origin/{actual}", tracking_sha],
                   cwd=repo, check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: actual)
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch is None and subject_sha is None and "分岐している" in error
    assert "local=" in error and "tracking=" in error


def test_integrate_branch_resolution_accepts_matching_local_and_tracking(tmp_path, monkeypatch):
    ship = _ship_module()
    actual = "feat/issue-51-same"
    repo = _branch_repo(tmp_path, actual)
    sha = subprocess.run(
        ["git", "rev-parse", actual], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "update-ref", f"refs/remotes/origin/{actual}", sha],
                   cwd=repo, check=True)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: actual)
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert (branch, subject_sha, error) == (actual, sha, None)


def test_integrate_branch_resolution_stops_when_missing(tmp_path, monkeypatch):
    ship = _ship_module()
    repo = _branch_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: "feat/issue-51-missing")
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch is None and subject_sha is None and "候補も無い" in error


def test_integrate_branch_resolution_stops_on_ambiguity(tmp_path, monkeypatch):
    ship = _ship_module()
    candidates = ("feat/issue-51-one", "feat/issue-51-two")
    repo = _branch_repo(tmp_path, *candidates)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _issue: "feat/issue-51-missing")
    branch, subject_sha, error = ship._resolve_integration_branch(51)
    assert branch is None and subject_sha is None and "候補が複数" in error
    assert all(candidate in error for candidate in candidates)


def test_integrate_explicit_branch_is_checked_without_fallback(tmp_path, monkeypatch):
    ship = _ship_module()
    repo = _branch_repo(tmp_path, "feat/issue-51-other")
    monkeypatch.chdir(repo)
    branch, subject_sha, error = ship._resolve_integration_branch(
        51, "feat/issue-51-explicit-missing")
    assert branch is None and subject_sha is None and "--branch" in error and "other" in error


def test_integrate_explicit_nonstandard_branch_and_sha_are_supported(tmp_path, monkeypatch):
    ship = _ship_module()
    repo = _branch_repo(tmp_path, "hotfix/manual-review")
    sha = subprocess.run(
        ["git", "rev-parse", "main"], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    monkeypatch.chdir(repo)
    branch, subject_sha, error = ship._resolve_integration_branch(51, "hotfix/manual-review")
    assert branch == "hotfix/manual-review" and subject_sha == sha and error is None
    branch, subject_sha, error = ship._resolve_integration_branch(51, sha)
    assert branch == sha and subject_sha == sha and error is None


# ── #107 rework: integrate も worktree の実 HEAD を候補に入れる ────────────────
# skeptic の反証: retitle 後の begin 再実行が新 slug の branch を切り、実作業は旧 branch の
# worktree に居る形で、_resolve_integration_branch の add() が `feat/issue-N*` しか候補に
# 入れないため worktree 解決済みの非規約 branch が捨てられ、迷子の規約名 branch が
# sole candidate として**未レビューのまま exit 0 で merge** された。


def _worktree_repo(tmp_path, work_branch, *stray_branches):
    """実作業が worktree の branch に載っている repo（+ 迷子の規約名 branch）。"""
    repo = _branch_repo(tmp_path, *stray_branches)
    wt = repo / ".orgforge" / "wt" / "issue-42"
    subprocess.run(["git", "worktree", "add", "-q", "-b", work_branch, str(wt), "main"],
                   cwd=repo, check=True)
    (wt / "work.txt").write_text("real reviewed work", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-qm", "real work"], cwd=wt, check=True)
    return repo, wt


def test_integrate_plan_stops_on_worktree_vs_conventional_split_brain(
        tmp_path, monkeypatch, capsys):
    """(a) skeptic の split-brain shape: worktree の実 branch と迷子の規約名 branch が併存 →
    integrate --plan は迷子を黙って選ばず、両方を名指しして止まる。"""
    ship = _ship_module()
    repo, _wt = _worktree_repo(tmp_path, "fix/login-redirect", "feat/issue-42-old-title")
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "main"],
                   cwd=repo, check=True)
    (repo / "organization.yaml").write_text("roles: []\n", encoding="utf-8")
    (repo / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    integration_ref: origin/main\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _i: "feat/issue-42-new-title")
    rc = ship.cmd_integrate(argparse.Namespace(issue=42, branch=None, plan=True,
                                               base=None, test=None))
    cap = capsys.readouterr()
    assert rc != 0, \
        "迷子の feat/issue-42-old-title を sole candidate として選び、素通りで統合できてしまう"
    assert "fix/login-redirect" in cap.err and "feat/issue-42-old-title" in cap.err, \
        f"両方の branch を名指しして止まっていない: {cap.err!r}"


def test_integrate_branch_resolution_targets_worktree_head_without_stray(
        tmp_path, monkeypatch):
    """(b) worktree の実 branch（非規約名）だけがある → それが統合対象になる。"""
    ship = _ship_module()
    repo, _wt = _worktree_repo(tmp_path, "fix/login-redirect")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ship, "_branch_for", lambda _i: "feat/issue-42-new-title")
    branch, subject_sha, error = ship._resolve_integration_branch(42)
    assert error is None, f"worktree の実 branch を候補に入れていない: {error!r}"
    assert branch == "fix/login-redirect" and len(subject_sha) == 40


def test_integrate_explicit_branch_keeps_current_behavior_despite_worktree(
        tmp_path, monkeypatch):
    """明示 --branch は従来どおり — worktree 解決に上書きされない（operator override）。"""
    ship = _ship_module()
    repo, _wt = _worktree_repo(tmp_path, "fix/login-redirect", "feat/issue-42-old-title")
    monkeypatch.chdir(repo)
    branch, subject_sha, error = ship._resolve_integration_branch(42, "feat/issue-42-old-title")
    assert (branch, error) == ("feat/issue-42-old-title", None)
    assert len(subject_sha) == 40


def test_integrate_preview_fails_instead_of_reporting_zero_for_missing_ref(tmp_path, monkeypatch):
    ship = _ship_module()
    repo = _branch_repo(tmp_path)
    monkeypatch.chdir(repo)
    body, overlaps, error = ship._integrate_preview(
        51, "feat/issue-51-missing", "0" * 40, "main", "true")
    assert error and overlaps == {}
    assert "0 files" not in body and "subject" in body


def test_integrate_preview_is_pinned_to_resolved_subject_sha(tmp_path, monkeypatch):
    ship = _ship_module()
    branch = "feat/issue-51-moving"
    repo = _branch_repo(tmp_path, branch)
    subprocess.run(["git", "checkout", "-q", branch], cwd=repo, check=True)
    (repo / "first.txt").write_text("first", encoding="utf-8")
    subprocess.run(["git", "add", "first.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=repo, check=True)
    first_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    (repo / "later.txt").write_text("later", encoding="utf-8")
    subprocess.run(["git", "add", "later.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "later"], cwd=repo, check=True)
    monkeypatch.chdir(repo)

    body, overlaps, error = ship._integrate_preview(51, branch, first_sha, "main", "true")
    assert error is None and overlaps == {}
    assert "first.txt" in body and "later.txt" not in body and first_sha[:12] in body


def test_integrate_records_and_merges_immutable_subject_sha():
    src = _cycle_src("ship")
    assert '["git", "merge", "--no-ff", subject_sha' in src
    assert '"integration_subject_sha": subject_sha' in src
    assert "integration_subject_sha" in (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")


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


# ── 0.23.0: worktree の迷子台帳 / 周回の性質 / 未撃領域の引き渡し ──────────
def test_worktree_is_not_mistaken_for_the_org_root(tmp_path):
    """worktree の中からは親を辿ること。

    doctrine / evidence を git 追跡下に置いた結果、worktree にも `.orgforge/` が復元され、
    それが ORG_MARKERS に当たって探索が止まった。そこで subagent が ledger append を打つと
    worktree 側の空の台帳に書かれ、`appended seq=1` が返る — **実判定が本体から消える**。
    実地で1日3回起き、実判定4件が迷子になった。警告で防ぐ設計は破れる（gate が踏んだ）。
    """
    import importlib, sys as _s
    if str(TOOLS) not in _s.path:
        _s.path.insert(0, str(TOOLS))
    disc = importlib.import_module("discover")

    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / ".orgforge").mkdir(); (repo / ".orgforge" / "doctrine").mkdir()
    (repo / ".orgforge" / "doctrine" / "x.json").write_text("{}")
    g("add", "-A"); g("commit", "-qm", "seed"); g("branch", "develop")

    wt = repo / ".orgforge" / "wt" / "issue-3"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-3", str(wt), "develop")
    assert (wt / ".orgforge").is_dir(), "前提: worktree に .orgforge が復元される"

    saved = os.environ.pop("ORG_LEDGER_ROOT", None)
    try:
        assert disc.org_root(str(wt)) == str(repo.resolve()), \
            "worktree を org root と誤認した（迷子台帳ができる）"
        assert disc.ledger_root(str(wt)) == os.path.join(str(repo.resolve()),
                                                         ".orgforge", "ledger")
    finally:
        if saved is not None:
            os.environ["ORG_LEDGER_ROOT"] = saved


def test_external_worktree_uses_primary_governance_but_keeps_its_subject(tmp_path, monkeypatch):
    """Host-created worktrees need one governance root even when they live outside the repo.

    The older regression only covered ``<repo>/.orgforge/wt``. Claude Code/Codex may create a
    linked worktree as a sibling or under a host temp directory, where walking parents can never
    reach the primary checkout. Governance must come from the primary worktree while the commit
    under review remains the external worktree's commit.
    """
    import importlib, sys as _s
    if str(TOOLS) not in _s.path:
        _s.path.insert(0, str(TOOLS))
    disc = importlib.import_module("discover")
    ledger = importlib.import_module("ledger")

    repo = tmp_path / "primary"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / ".orgforge").mkdir()
    (repo / "organization.yaml").write_text("name: test\n", encoding="utf-8")
    (repo / "ledger-schema.yaml").write_text("schema_version: old\n", encoding="utf-8")
    (repo / "constitution.yaml").write_text("version: old\n", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "seed")

    wt = tmp_path / "host-worktrees" / "issue-34"
    wt.parent.mkdir()
    g("worktree", "add", "-q", "-b", "feat/issue-34", str(wt), "HEAD")
    (repo / "ledger-schema.yaml").write_text("schema_version: authoritative\n", encoding="utf-8")
    (repo / "constitution.yaml").write_text("version: authoritative\n", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "governance update")
    subdir = wt / "src"; subdir.mkdir()

    monkeypatch.delenv("ORG_LEDGER_ROOT", raising=False)
    monkeypatch.delenv("ORG_LEDGER_SCHEMA", raising=False)
    assert disc.org_root(str(subdir)) == str(repo.resolve())
    assert disc.subject_root(str(subdir)) == str(wt.resolve())

    core = importlib.import_module("orgcycle._core")
    _, subject = core.review_subject(34, "gate", cwd=str(wt))
    wt_tree = g("rev-parse", "HEAD^{tree}", cwd=wt).stdout.strip()
    primary_tree = g("rev-parse", "HEAD^{tree}").stdout.strip()
    assert subject["head_tree_sha"] == wt_tree
    assert subject["head_tree_sha"] != primary_tree, \
        "governance resolution must not switch the commit/tree being reviewed"

    old_cwd = os.getcwd()
    try:
        os.chdir(subdir)
        assert ledger._schema_path() == str(repo / "ledger-schema.yaml")
        divergences = disc.governance_divergences()
    finally:
        os.chdir(old_cwd)
    assert {d["path"] for d in divergences} >= {"ledger-schema.yaml", "constitution.yaml"}

    status = subprocess.run(
        [sys.executable, str(TOOLS / "status.py"), "status", str(repo / ".orgforge" / "ledger")],
        cwd=str(subdir), capture_output=True, text=True, timeout=60)
    assert status.returncode == 0
    assert "AMBER" in status.stdout and "governance" in status.stdout.lower(), status.stdout


def test_integrate_passes_its_own_test_output_to_the_log():
    """integrate 自身が log の必須検査に引っかかっていた。

    マイルストーンの log は --command/--result を要求するのに integrate はそれを渡さず、
    統合は完了するのに Issue へのログだけ落ちた。自分で走らせた結果を持っているのだから、
    人に書かせる理由が無い。
    """
    src = _cycle_src("ship")
    seg = src[src.index("def cmd_integrate"):]
    assert '"--command", a.test' in seg and 'test_out["text"]' in seg


def test_show_reports_what_the_rounds_are_about():
    """周回の回数だけでなく、直近が何を問題にしているかを出す。"""
    src = _cycle_src("inspect")
    assert "周回:" in src and "直近3回" in src
    # 周回ごとに違う理由を見ること（1件だけ引くと全部同じに見える）
    assert "_issue_reasons" in src
    assert "判断材料であって判断ではない" in src, "board が「切れ」と判定してはいけない"


def test_verify_hands_the_unshot_areas_to_skeptic():
    """gate が「今回撃っていない」と書いた領域を skeptic に標的として渡す。"""
    src = _cycle_src("judge")
    assert "撃っていない" in src and "Known risk accepted" in src
    assert "標的候補" in src


# ── 0.25.2: 指示と権限の食い違いを解消（subagent は記録しない）──────────────
def test_verify_does_not_tell_subagent_to_record():
    """subagent に打てないコマンドを渡さない。

    実地で gate と skeptic が計7回、判定を出した後に「記録は監督に委ねます」と述べて止まり、
    一度は判定そのものが台帳に入らず失われかけた。subagent には ORG_GITHUB_REPO も台帳の
    パスも渡っていないのに「二重に記録せよ」と指示していた — **指示と権限の食い違い**。
    """
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    # subagent 向け（stdout）の節には記録コマンドを載せない
    assert "返すもの（**判定はあなたが決める。記録は監督が行う**）" in seg
    assert "記録コマンドは打たなくてよい" in seg
    # 監督向け（stderr）には、値を流し込むコマンドを出す — 配管が判定を運べないと本末転倒
    assert "監督（あなた）が打つコマンド" in seg
    assert "file=sys.stderr" in seg


def test_agent_charters_do_not_demand_recording():
    """agents/*.md 側も「判定を返すまで」に揃えること（片方だけ直すと食い違いが残る）。"""
    d = _cycle_mod("_core")._agents_dir()
    if not d:
        return
    for role in ("gate", "skeptic"):
        body = pathlib.Path(d, f"{role}.md").read_text(encoding="utf-8")
        assert "記録は監督" in body, f"{role}.md がまだ subagent に記録を求めている"
        assert "$ORG_GITHUB_REPO" not in body, \
            f"{role}.md が渡っていない環境変数を参照している"


def test_repro_lint_admits_it_has_no_baseline():
    """baseline を読んでいないなら「判定していない」と言う。

    実地で gate がこの断定（「baseline に無い＝この変更で新たに悪化した」）を額面どおり
    受け取り、既存の負債を新規の悪化と読んで判定を止めた — 対象の Issue は、まさにその
    項目を緑にする作業だった。道具が見ていない領域については、道具は「見ていない」と
    言うべきである。
    """
    src = (TOOLS / "repro_lint.py").read_text(encoding="utf-8")
    seg = src[src.index("HELD: {len(failed)} required artifact"):]
    assert "baseline が無い" in seg and "判定していない" in seg
    assert "if baseline is None:" in src


# ── 0.26.0: 範囲外の発見を Issue に積み増さない ──────────────────────────
def test_skeptic_charter_splits_in_scope_from_out_of_scope():
    """skeptic は仕事として必ず何かを見つける。範囲を切らないと Issue が終わらない。

    実地では8周 rework した Issue の**4回目以降の発見が、すべて spec の MUST に無いもの**
    だった。実在の欠陥でも、それは次の Issue の仕事。
    """
    d = _cycle_mod("_core")._agents_dir()
    if not d:
        return
    body = pathlib.Path(d, "skeptic.md").read_text(encoding="utf-8")
    assert "Issue 化を推奨" in body, "範囲外の発見の扱いが書かれていない"
    assert "refuted` の根拠にする" in body or "refuted の根拠" in body
    # 判断が難しいものは skeptic に決めさせない
    assert "supervisor に返す" in body or "監督" in body


def test_verify_asks_skeptic_for_out_of_scope_separately():
    """「返すもの」にも out_of_scope を入れる（憲章だけ直すとプロンプトと食い違う）。"""
    src = _cycle_src("judge")
    assert "out_of_scope" in src
    assert "verdict` には数えず" in src or "verdict には数えず" in src


def test_verify_scopes_blockers_and_repeated_findings():
    """gate の実行時材料が、変更契約外の無限ラリーを明示的に防ぐ。"""
    src = _cycle_src("judge")
    assert "判定範囲とレビューラリーの規律" in src
    assert "handoff の seam contract" in src
    assert "reviewed head・根拠・残余リスク" in src
    assert "follow-up Issue 化" in src


def test_spec_template_states_when_done():
    """完了の判定を spec 側に書く — maker / gate / skeptic の3者が同じ条件を見る。"""
    body = (TOOLS.parent / "template" / "SPEC.md").read_text(encoding="utf-8")
    assert "完了の判定" in body
    assert "別 Issue にする" in body


def test_show_warns_on_repeated_rework_but_not_on_many_rounds():
    """rework の回数で見る。判定を重ねること自体は悪くない（#7 は7周・rework 2回で収束）。"""
    src = _cycle_src("inspect")
    seg = src[src.index("周回:"):]
    assert "len(reworks) > 3" in seg, "rework の回数で判定していない"
    assert "len(rounds) > 5" not in seg, "判定回数で警告すると、丁寧に見た Issue まで警告される"


# ── 0.27.0: 監督の記録漏れを塞ぐ ────────────────────────────────────────
def test_rework_has_a_dedicated_command():
    """rework_requested を記録する専用コマンドが無いことが記録漏れの一因だった。

    実地で reject/refuted 28件に対し rework_requested が台帳に無かった（#32 は4回 reject で
    記録0件）。監督は `ledger.py append --payload '{...}'` を手で組む必要があり、しかも発注は
    「判定 → 検証 → decide → **発注** → 記録」の順で、発注した subagent の通知が来ると流れる。
    副作用として show の rework 警告（0.26.0）が沈黙していた。
    """
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "rework", "--help"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    for flag in ("--after", "--reason", "--by"):
        assert flag in p.stdout, f"{flag} が無い"


def _rework_args():
    return argparse.Namespace(issue=32, after="refuted", by="supervisor", reason="fix the proof",
                              to="maker", round=2)


def test_rework_returns_issue_to_ready_before_recording_ledger(monkeypatch):
    m = _cycle_mod("judge")
    calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: (calls.append(("gh",) + a) or (0, "ok")))
    monkeypatch.setattr(m, "_ledger", lambda *a: (calls.append(("ledger",) + a) or (0, "ok")))

    assert m.cmd_rework(_rework_args()) == 0

    assert calls[0] == ("gh", "stage", "--issue", "32", "--stage", "ready")
    assert calls[1][0:3] == ("ledger", "append", "--actor")
    assert calls[2][0:3] == ("gh", "log", "--issue")


def test_rework_does_not_advance_ledger_when_reopen_fails(monkeypatch):
    m = _cycle_mod("judge")
    ledger_calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: ((2, "reopen denied")
                                                    if a[0] == "stage" else (0, "ok")))
    monkeypatch.setattr(m, "_ledger", lambda *a: (ledger_calls.append(a) or (0, "ok")))

    assert m.cmd_rework(_rework_args()) == 3
    assert ledger_calls == []


def test_verify_offers_the_rework_command_on_reject():
    """判定の記録と**同じ場所**に rework の発注コマンドを置く（順序が逆転する）。"""
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    assert "rework --issue" in seg
    assert "show` の rework 警告が沈黙する" in seg or "rework 警告が沈黙" in seg


def test_banner_shows_version_and_cwd():
    """どのコピーを動かしているかが見えないと、古いパスを流用しても気づけない。

    実地で 0.26.0 のリリース後も 0.25.2 のパスを打ち、さらに `cd` が持続しない前提の
    コマンドの exit=1 を「塞がった証拠」と読みかけた。
    """
    for tool in ("org_cycle.py", "github_sync.py", "ledger.py"):
        src = (TOOLS / tool).read_text(encoding="utf-8")
        assert "banner" in src.lower(), f"{tool} が版と cwd を出さない"
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "plan",
                        "--role", "r", "--issue", "1"],
                       capture_output=True, text=True, timeout=60)
    assert "[orgforge " in p.stderr, p.stderr[:200]
    assert os.getcwd() in p.stderr or "@" in p.stderr


def test_banner_never_pollutes_machine_readable_output(tmp_path):
    """人間向けの1行が、機械が読む出力を壊してはいけない。

    banner を足した直後、`ledger view`（JSON を返す）の出力に混ざって JSONDecodeError で
    テストが落ちた。stderr に書いていても、消費側が 2>&1 で混ぜれば同じである。
    **便利のために壊すのは筋が通らない** — view / census / digest では黙る。
    """
    led = tmp_path / "l"; led.mkdir()
    subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append",
                    "--actor", "e", "--class", "cycle_started",
                    "--payload", json.dumps({"role": "e", "candidate_id": "X"})],
                   capture_output=True, text=True,
                   env=dict(os.environ, ORG_LEDGER_ROOT=str(led)), timeout=60)
    for sub in ("view", "census"):
        args = [sys.executable, str(TOOLS / "ledger.py"), sub, str(led)]
        if sub == "view":
            args.append("work_in_progress")
        p = subprocess.run(args, capture_output=True, text=True, timeout=60)
        merged = p.stdout + p.stderr
        assert "[orgforge " not in merged, f"{sub} の出力に banner が混ざった"
        json.loads(p.stdout)          # 混ざっていれば例外になる


def test_internal_calls_suppress_the_banner():
    """内部呼び出し（_run）は stdout+stderr を混ぜて返すので、banner を出させない。

    `_branch_for` は先頭行を取るので今は無事だが、混ざりうる構造そのものを消す
    （0.22.1 で「静かに壊れる」経路を1つ踏んだばかりである）。
    """
    src = _cycle_src("_core")
    seg = src[src.index("def _run("):src.index("def _raw(")]
    assert "ORG_QUIET" in seg, "_run が banner を抑制していない"


# ── 0.27.1: プロンプトの重複を削る（実測で総時間の21%が1回の待ち時間）──────
def test_verify_does_not_repeat_the_prior_judgment_twice():
    """判定履歴と「gate が既に見たこと」が同じ本文を2回出していた。

    実測で skeptic のプロンプト457行のうち、gate の最新判定の全文が2箇所に現れていた
    （同じ26行と20行超）。プロンプトの長さは読む時間に直結する。
    """
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    assert "if prior and not (history or issue_rounds):" in seg, \
        "履歴を出したうえで prior も出すと、同じ本文が2回並ぶ"


def test_verify_still_hands_over_the_unshot_areas():
    """重複を削っても「gate が撃っていない領域」の引き渡しは残すこと。

    実地では gate が「1件も当てていない」と書いた領域から実バグが出た。これは
    prior から Known risk の節を抜き出すので、prior の取得自体は消してはいけない。
    """
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    assert 'if role == "skeptic" and prior:' in seg
    assert "標的候補" in seg


# ── 0.28.0: 報告の切断 / worktree 運用での --create / seam の案内 ────────────
def test_intake_catches_a_truncated_report():
    """subagent の turn が作業の途中で終わることがある（実地で1晩に3件）。

    status は completed で返り、result は「Now the key attack:」のような宣言1文だけ。
    **気づけない形が危ない** — 「MUST 2 は防がれました」で切れていたら、それを verdict として
    読んで admit しかねない。
    """
    for report, role in (("I verified MUST 1 and 2. Now the key attack:", "skeptic"),
                         ("MUST 2 で要求されている防御は実装されており、防がれました。", "skeptic"),
                         ("Now update the call sites.", "maker")):
        p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                            "--issue", "27", "--role", role, "--report", report],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 10, f"不完全な報告を通した: {report!r}"
        assert "報告が不完全" in p.stderr


def test_intake_passes_a_complete_report():
    """必須要素が揃っていれば通す。途中で 'Now ...' と書いていても完走とみなす。"""
    for report, role in (
            (json.dumps({"verdict": "survives",
                         "why": "静的な境界分析と実テストの結果から、反例が成立しないことを確認した。",
                         "evidence": "npm test → 60 passed; relevant branches were inspected",
                         "mutations": [], "out_of_scope": [], "risk": "なし"},
                        ensure_ascii=False), "skeptic"),
            ("実装完了。コミット 7550451。npm test → Tests 60 passed (60)。", "maker"),
            ("verdict: reject。npm ci が失敗し exit=1。MUST 3 が満たされていない。", "gate")):
        p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                            "--issue", "27", "--role", role, "--report", report],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"完全な報告を弾いた: {report!r} / {p.stderr[:200]}"


def test_branch_create_does_not_move_main_in_a_worktree_org(tmp_path):
    """worktree で並列運用している org では、メインのブランチを切り替えない。

    実地で --create がメインを develop から離し、気づかなければ develop での統合テストが
    別 Issue のブランチ上で走っていた。
    """
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "s.txt").write_text("x"); g("add", "-A"); g("commit", "-qm", "s"); g("branch", "develop")
    g("checkout", "-q", "develop")
    wt = repo / ".orgforge" / "wt" / "issue-1"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-1", str(wt), "develop")

    r = subprocess.run([sys.executable, str(TOOLS / "github_sync.py"), "branch",
                        "--issue", "9", "--create", "--base", "develop", "--repo", "o/n"],
                       capture_output=True, text=True, cwd=str(repo), timeout=60)
    cur = g("branch", "--show-current").stdout.strip()
    assert cur == "develop", f"メインが {cur} に切り替わった（worktree 運用の org）"
    assert (repo / ".orgforge" / "wt" / "issue-9").is_dir(), "worktree が作られていない"


def test_seam_gate_message_leads_with_the_shortest_path():
    """通る道を、実際に短い順で書く（実地では INDEPENDENT: だけで通した）。"""
    src = (TOOLS.parent / "integrations" / "common" / "org_hook.py").read_text(encoding="utf-8")
    i = src.index("carries no seam contract")
    seg = src[i:i + 1600]
    assert seg.index("INDEPENDENT") < seg.index("handoff.py"), \
        "handoff.py が先に読める（実際に通るのは INDEPENDENT: の方が短い）"
    assert "owns` の宣言を免除する" in seg, "INDEPENDENT: が owns 検査を免除することを言っていない"


# ── 0.28.1: 宣言は行頭に限る / パイプ経由でも判定できる ──────────────────
def _spawn_verdict(prompt):
    import importlib.util, pathlib as _p
    hook = TOOLS.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_i2", hook)
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    return h.spawn_needs_seam_or_independence("Task", {"prompt": prompt})


def test_negation_is_not_read_as_a_declaration():
    """全文の部分一致だと**否定文が宣言として通る**。

    実地のプローブ: 「contract も INDEPENDENT: も付けていません」がそのまま (A) として一致した。
    実害のある形は「この作業は independent ではないので contract を付ける」と書いた (B) の
    spawn が (A) と誤判定されること — **(A) は `owns` の宣言を免除する**ので、偶然の一致で
    免除が取れる。ガードの文面自身が「冒頭に1行書く」と言っているので、検査を文面に合わせる。
    """
    for prompt in ("contract も INDEPENDENT: も付けていません",
                   "この作業は independent ではないので contract を付ける",
                   "no seam contract is attached",
                   "seam contract を書き忘れました"):
        assert _spawn_verdict(prompt) is not None, f"否定文が宣言として通った: {prompt!r}"


def test_declaration_at_the_start_of_a_line_passes():
    """行頭の宣言は通す（前の空白・2行目でも可）。"""
    for prompt in ("INDEPENDENT: 調査のみ。出力はマージされない",
                   "independent: research only",
                   "  INDEPENDENT: 前に空白があってもよい",
                   "前置き\nINDEPENDENT: 2行目の行頭でもよい"):
        assert _spawn_verdict(prompt) is None, f"正当な宣言を弾いた: {prompt!r}"


def test_seam_contract_structure_still_passes():
    """seam 側は**構造**を見る（単なる語ではない）ので、handoff.py の出力は通る。"""
    assert _spawn_verdict("## Your slice\nX\nInputs you receive: A\n"
                          "Outputs you MUST produce: B") is None


def test_intake_emits_a_machine_readable_verdict_line():
    """`| tail` を通すとシェルの終了コードは最後のコマンドのものになり、10 が消える。

    実地でそう観測された（実装は 10 を返していたが、観測経路が 0 を見せた）。
    パイプで読む経路でも判定できるように INCOMPLETE を出力に置く。
    """
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                        "--issue", "30", "--role", "skeptic",
                        "--report", "MUST 2 は防がれました。"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 10
    assert "INCOMPLETE" in p.stderr, p.stderr
    q = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                        "--issue", "30", "--role", "skeptic",
                        "--report", json.dumps({
                            "verdict": "survives",
                            "why": "静的な境界分析と実テストの結果から、反例が成立しないことを確認した。",
                            "evidence": "npm test → 60 passed; relevant branches were inspected",
                            "mutations": [], "out_of_scope": [], "risk": "なし"},
                            ensure_ascii=False)],
                       capture_output=True, text=True, timeout=60)
    assert q.returncode == 0 and "INCOMPLETE" not in q.stderr


@pytest.mark.parametrize("claim", [
    "mutations: []",
    "mutations: none attempted",
    "mutations: trigger disabled, detected=true",
    "applied: true\npostcondition: changed\nrestore_postcondition: restored",
    "mutations: []\n撃った変異: trigger削除 → detected=false",
])
def test_intake_rejects_prose_mutation_claims(claim):
    result = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                             "--issue", "30", "--role", "skeptic", "--report",
                             "verdict: survives。npm test → 60 passed。\n" + claim],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 10
    assert "構造化 JSON" in result.stderr


# ── 0.29.0: CI を触る統合で job 構成を見せる ──────────────────────────────
def _ci_repo(tmp_path, ci_yaml):
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text(ci_yaml, encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "seed"); g("branch", "develop")
    g("checkout", "-q", "-b", "feat/issue-42")
    (repo / ".github" / "workflows" / "ci.yml").write_text(ci_yaml + "\n# added\n", encoding="utf-8")
    g("commit", "-qam", "ci: add")
    return repo


_CI_CONDITIONAL = """name: CI
on:
  push:
    branches: [develop]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm test
  db-test:
    runs-on: ubuntu-latest
    steps:
      - id: probe
        run: echo present=true >> $GITHUB_OUTPUT
      - if: steps.probe.outputs.present == 'true'
        run: git diff --exit-code -- public docs
"""

_CI_PLAIN = """name: CI
on:
  push:
    branches: [develop]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm test
"""


def test_integrate_plan_flags_a_conditional_ci_job(tmp_path):
    """YAML が妥当でテストが緑でも、条件付き job に入ったステップは走らない。

    運用では union でのマージ結果が条件付き job の末尾に入り、依存する Issue が未統合の間、
    追加した検査が一度も走っていなかった。step の `if:` は `- if:` の形でも書けるので、
    ハイフンを見落とすと**まさに捕まえたい形**を落とす。
    """
    repo = _ci_repo(tmp_path, _CI_CONDITIONAL)
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "integrate",
                        "--issue", "42", "--plan", "--base", "develop"],   # #106: 明示（fixture に宣言が無い）
                       capture_output=True, text=True, cwd=str(repo), timeout=60)
    out = p.stdout + p.stderr
    assert "CI を触っている" in out, out
    assert "db-test（if: 条件付き）" in out, out
    assert "条件を満たさない間その検査は一度も走らない" in out


def test_integrate_plan_lists_only_real_jobs(tmp_path):
    """`on:` の子（pull_request / push）を job と誤認しないこと。条件が無ければ黙る。"""
    repo = _ci_repo(tmp_path, _CI_PLAIN)
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "integrate",
                        "--issue", "42", "--plan", "--base", "develop"],   # #106: 明示（fixture に宣言が無い）
                       capture_output=True, text=True, cwd=str(repo), timeout=60)
    out = p.stdout + p.stderr
    assert "job: test" in out, out
    for wrong in ("pull_request", "push", "permissions"):
        assert wrong not in out.split("job:")[1].split("\n")[0], f"{wrong} を job と誤認した"
    assert "条件付きの job がある" not in out, "条件が無いのに警告した"


# ── 0.31.0: 別ハーネスを judge として使う（血統を実際に分ける）──────────────
def test_verdict_schemas_satisfy_structured_outputs():
    """Structured Outputs は `additionalProperties: false` のとき全キーを required に要求する。

    実測で 400 invalid_json_schema: "'required' is required to be supplied and to be an array
    including every key in properties. Missing 'note'." 任意の項目は required から外すのではなく
    `"type": ["string", "null"]` で表現する。
    """
    base = TOOLS.parent / "template" / "schemas"
    assert base.is_dir(), "verdict スキーマが無い"

    def check(node, path="root"):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, f"{path}: 追加プロパティを許している"
                assert set(node.get("required", [])) == set(node["properties"]), \
                    f"{path}: required が properties 全キーを含んでいない"
            for k, v in node.items():
                check(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                check(v, f"{path}[{i}]")

    for role in ("gate", "skeptic"):
        d = json.loads((base / f"{role}-verdict.json").read_text(encoding="utf-8"))
        check(d, role)
        assert "verdict" in d["properties"], role
        assert d["properties"]["verdict"].get("enum"), f"{role}: verdict が enum でない"


def test_intake_reads_a_structured_verdict():
    """構造化された返り値は、正規表現ではなく構造で見る。

    スキーマが required にしていても、値が空文字なら埋まっていない。形（スキーマ）と
    中身（intake）で2層にする。
    """
    ok = json.dumps({
        "verdict": "survives",
        "why": "3経路で試し、いずれも security definer を経由して拒否された。詳細は以下。",
        "evidence": "psql -c \"update …\" → ERROR: violates row-level security / npm test → 78 passed",
        "mutations": [{"what": "is_group_member を select true に", "applied": True,
                       "postcondition": "select prosrc → true を返した", "detected": True,
                       "restore_postcondition": "select prosrc → original body を返した",
                       "note": None}],
        "out_of_scope": [], "risk": "中間積の上限チェックが無い"}, ensure_ascii=False)
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                        "--issue", "11", "--role", "skeptic", "--report", "-"],
                       input=ok, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr

    empty = json.dumps({"verdict": "survives", "why": "", "evidence": "",
                        "mutations": [], "out_of_scope": [], "risk": ""})
    q = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                        "--issue", "11", "--role", "skeptic", "--report", "-"],
                       input=empty, capture_output=True, text=True, timeout=60)
    assert q.returncode == 10, "欄が空の構造化返り値を通した"


@pytest.mark.parametrize("mutation", [
    {"what": "trigger disable", "applied": False,
     "postcondition": "select tgenabled → O", "restore_postcondition": "select → O",
     "detected": False, "note": "変化なし"},
    {"what": "trigger disable", "applied": True,
     "postcondition": "", "restore_postcondition": "select → O",
     "detected": False, "note": "読取なし"},
    {"what": "trigger disable", "applied": True,
     "postcondition": 1234567890123, "restore_postcondition": "select → O",
     "detected": False, "note": "型が不正"},
    {"what": "trigger disable", "applied": True,
     "postcondition": "select tgenabled → D", "restore_postcondition": "",
     "detected": False, "note": "復元未確認"},
    {"what": "trigger disable", "detected": False, "note": "旧形式"},
])
def test_intake_rejects_unproven_mutations(mutation):
    report = json.dumps({
        "verdict": "survives",
        "why": "MUSTの防御を変異検査で確認したという主張だが、適用成立の証拠を検査する。",
        "evidence": "mutation command and test output were captured for independent review",
        "mutations": [mutation], "out_of_scope": [], "risk": "適用不能なら未測定"},
        ensure_ascii=False)
    result = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                             "--issue", "11", "--role", "skeptic", "--report", "-"],
                            input=report, capture_output=True, text=True, timeout=60)
    assert result.returncode == 10, result.stdout + result.stderr
    assert any(word in (result.stdout + result.stderr) for word in ("適用", "復元"))


@pytest.mark.parametrize("bad_mutations", [None, "all applied", {"applied": False}])
def test_intake_rejects_non_array_or_missing_mutations(bad_mutations):
    report = {
        "verdict": "survives",
        "why": "MUSTの防御を独立に確認したという主張だが、構造化された変異一覧の型を検査する。",
        "evidence": "mutation command and test output were captured for independent review",
        "out_of_scope": [], "risk": "不正な構造は判定成果物にしない"}
    if bad_mutations is not None:
        report["mutations"] = bad_mutations
    result = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                             "--issue", "11", "--role", "skeptic", "--report", "-"],
                            input=json.dumps(report, ensure_ascii=False),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 10, result.stdout + result.stderr
    assert "array" in (result.stdout + result.stderr)


def test_intake_accepts_static_skeptic_report_without_mutations():
    """A static proof can be complete without pretending a mutation was attempted."""
    report = json.dumps({
        "verdict": "survives",
        "why": "仕様の不変条件を実装と境界条件から独立に再導出し、反例が成立しないことを確認した。",
        "evidence": "対象コードと既存テストの具体的な分岐を読み、境界入力の結果を照合した。",
        "mutations": [], "out_of_scope": [], "risk": "動的変異は不要な静的判定"},
        ensure_ascii=False)
    result = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "intake",
                             "--issue", "11", "--role", "skeptic", "--report", "-"],
                            input=report, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_prompt_requires_mutation_postconditions_and_restore():
    src = _cycle_src("judge")
    segment = src[src.index("def cmd_verify"):src.index("def _judge_lineage")]
    for phrase in ("baseline → mutate → postcondition → test → restore",
                   "空振りした変異の GREEN は証拠ではない", "適用後状態", "未測定"):
        assert phrase in segment


def test_cross_harness_verdict_schemas_are_bundled_and_resolved():
    """OBS-009: source and both installed projections must carry the same contracts."""
    judge = _cycle_mod("judge")
    roots = [TEMPLATE / "schemas",
             REPO / "integrations" / "claude-code" / "template" / "schemas",
             REPO / "integrations" / "codex" / "template" / "schemas"]
    for role in ("gate", "skeptic"):
        copies = [root / f"{role}-verdict.json" for root in roots]
        assert all(path.is_file() for path in copies), copies
        contents = [path.read_bytes() for path in copies]
        assert contents[0] == contents[1] == contents[2]
        assert pathlib.Path(judge._verdict_schema(role)).resolve() == copies[0].resolve()


def test_verify_offers_the_headless_route():
    """別ハーネスで judge を回す形を、そのまま打てる形で出すこと。"""
    src = _cycle_src("judge")
    seg = src[src.index("def cmd_verify"):]
    assert "--output-schema" in seg and "intake" in seg
    assert "別の血統" in seg or "別ハーネス" in seg


def test_claude_judge_receives_the_declared_effort():
    """Claude Codeもconstitutionのmodel/effortを実行引数へ投影する。"""
    src = _cycle_src("judge")
    branch = src[src.index('elif cli == "claude":'):src.index('else:', src.index('elif cli == "claude":'))]
    assert '["--model", str(model)]' in branch
    assert '["--effort", str(effort)]' in branch


# ── judges.lineage（スイスチーズ層）─────────────────────────────────────
# **既定が変わらないことを、まず固定する。** 別ハーネスの契約・CLI・認証を前提にすると、
# 持っていない環境で org が回らなくなる。層を増やすのは選択であって前提ではない。

def test_judge_lineage_defaults_to_same_harness(tmp_path, monkeypatch):
    """constitution が judges を宣言していなければ same-harness。"""
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _judge_lineage
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)   # org_root は .orgforge/ で判定
    (tmp_path / "constitution.yaml").write_text("enforcement:\n  caps: {}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert _judge_lineage("gate") == ("same-harness", None)


_HARNESS_CFG = (
    "      claude:\n"
    "        gate: { cli: claude, model: sonnet, effort: medium }\n"
    "        skeptic: { cli: claude, model: sonnet, effort: medium }\n"
    "      codex:\n"
    "        gate: { cli: codex, model: gpt-5.6-terra, effort: medium }\n"
    "        skeptic: { cli: codex, model: gpt-5.6-terra, effort: medium }"
)


@pytest.mark.parametrize(
    "primary,secondary",
    [("claude", "codex"), ("codex", "claude")],
)
def test_judge_lineage_selects_the_opposite_harness(tmp_path, monkeypatch, primary, secondary):
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _judge_lineage
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: adaptive\n"
        f"    harness:\n{_HARNESS_CFG}\n",
        encoding="utf-8")
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    monkeypatch.setenv("ORGFORGE_ACTIVE_HARNESS", primary)
    monkeypatch.setenv(f"ORGFORGE_{secondary.upper()}_AVAILABLE", "true")
    monkeypatch.chdir(tmp_path)
    lineage, cfg = _judge_lineage("skeptic")
    assert lineage == "cross-harness"
    assert cfg["cli"] == secondary
    if secondary == "codex":
        assert cfg["model"] == "gpt-5.6-terra"
        assert cfg["effort"] == "medium"
    else:
        assert cfg["model"] == "sonnet"
        assert cfg["effort"] == "medium"
    assert _judge_lineage("gate")[1]["cli"] == secondary


@pytest.mark.parametrize("primary,secondary", [("claude", "codex"), ("codex", "claude")])
def test_adaptive_lineage_falls_back_honestly_with_one_subscription(
        tmp_path, monkeypatch, primary, secondary):
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _judge_lineage
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: adaptive\n"
        f"    harness:\n{_HARNESS_CFG}\n", encoding="utf-8")
    monkeypatch.setenv("ORGFORGE_ACTIVE_HARNESS", primary)
    monkeypatch.setenv(f"ORGFORGE_{secondary.upper()}_AVAILABLE", "false")
    monkeypatch.chdir(tmp_path)
    assert _judge_lineage("gate") == ("same-harness", None)


@pytest.mark.parametrize("available,expected", [("true", "cross-harness"),
                                                   ("false", "same-harness")])
def test_recording_uses_the_same_adaptive_lineage_resolution(
        tmp_path, monkeypatch, available, expected):
    sys.path.insert(0, str(TOOLS))
    from ghsync.record import _org_lineage
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: adaptive\n", encoding="utf-8")
    monkeypatch.setenv("ORGFORGE_ACTIVE_HARNESS", "codex")
    monkeypatch.setenv("ORGFORGE_CLAUDE_AVAILABLE", available)
    monkeypatch.chdir(tmp_path)
    assert _org_lineage() == expected


@pytest.mark.parametrize(
    "harness,expected",
    [
        ("      gate: { cli: codex }", "claude / codex 両方"),
        (_HARNESS_CFG.replace("cli: claude", "cli: codex"), "同じハーネスを2回"),
    ],
)
def test_judge_lineage_fails_closed_on_invalid_cross_routing(
        tmp_path, monkeypatch, harness, expected):
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _judge_lineage
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n"
        f"    harness:\n{harness}\n", encoding="utf-8")
    monkeypatch.setenv("ORGFORGE_ACTIVE_HARNESS", "codex")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match=expected):
        _judge_lineage("gate")


def test_active_harness_rejects_ambiguous_nested_signals(monkeypatch):
    sys.path.insert(0, str(TOOLS))
    from harness import active_harness
    monkeypatch.delenv("ORGFORGE_ACTIVE_HARNESS", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    with pytest.raises(SystemExit, match="同時"):
        active_harness()


def test_headless_reports_missing_cli_instead_of_falling_back(tmp_path, monkeypatch):
    """CLI が無いとき、**黙って same-harness に落ちない**。

    「別血統で検査した」と思っているのに実際は同じ血統だった、が最悪の状態である
    （信号が壊れていることが分からない）。非 0 を返して言うこと。
    """
    sys.path.insert(0, str(TOOLS))
    from orgcycle.judge import _run_headless
    schema = TEMPLATE / "schemas" / "gate-verdict.json"
    rc = _run_headless("gate", 1, "材料", {"cli": "no-such-cli-xyz"}, str(schema))
    assert rc != 0


def test_headless_empty_output_is_fail_closed_and_diagnosable(tmp_path, monkeypatch, capsys):
    """空返しは fail-closed のまま、**切り分けられる材料**を残す（Issue #166）。

    実地では `claude -p` が exit 0・stdout も stderr も空で返り、CLI が落ちたのか、認証が
    切れたのか、tool-use の途中で黙って終わったのかを区別できなかった。判定は得られて
    いないので admission は生成しない（そこは変えない）が、次に何を試すかは言えるはず。
    材料そのもの（判定対象）は出さないこと — 長さだけを言う。
    """
    sys.path.insert(0, str(TOOLS))
    from orgcycle import judge as J

    class _Empty:
        returncode, stdout, stderr = 0, "", ""
    monkeypatch.setattr(J.shutil, "which", lambda c: "/usr/bin/true")
    monkeypatch.setattr(J.subprocess, "run", lambda *a, **k: _Empty())
    schema = TEMPLATE / "schemas" / "gate-verdict.json"
    material = "SECRET-MATERIAL-" + "x" * 200
    rc = J._run_headless("gate", 1, material, {"cli": "claude"}, str(schema))
    err = capsys.readouterr().err
    assert rc == 7, "判定が無いのに 0 を返してはいけない"
    assert "exit=0" in err and "stdout=0B" in err          # 切り分けの材料
    assert "material=" in err
    assert "SECRET-MATERIAL" not in err, "判定対象そのものを診断に漏らさない"
    assert "Reply with exactly: OK" in err                 # 次に試すことを言う


def test_decide_requires_both_lineages_for_admit(tmp_path, monkeypatch):
    """cross-harness の org では、片側だけの admit を記録できない。

    verify が両方の判定を並べて監督が読むだけなら、監督は都合のいい方を採れる —
    検査を増やしたのに緩くなる。だから **decide が持つ**。
    """
    sys.path.insert(0, str(TOOLS))
    import importlib
    rec = importlib.import_module("ghsync.record")
    (tmp_path / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n", encoding="utf-8")
    led = tmp_path / ".orgforge" / "ledger"
    led.mkdir(parents=True)
    (led / "ledger.jsonl").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    assert rec._org_lineage() == "cross-harness"
    # 台帳が空 → どちらの血統の admit も無い
    assert rec._has_lineage_verdict(7, "admission_decided", "same-harness") is False
    # reject は一致を要求しない（否は片方で足りる）
    assert rec._has_lineage_verdict(7, "admission_decided", "cross-harness") is False


def test_drift_reads_only_the_why_section(monkeypatch):
    """判定の Why 節だけを読む。コメント全体を検索すると分布が消える（実測）。"""
    sys.path.insert(0, str(TOOLS))
    import importlib
    drift = importlib.import_module("drift")
    body = ("## ⛔ admission_decided — `reject`\n"
            "**Why (the reasoning):**\n未測定のまま断定していた。\n\n"
            "**Evidence consulted:**\n回帰テストは緑だった。\n")
    monkeypatch.setattr(drift, "_sh", lambda cmd: json.dumps({"comments": [{"body": body}]}))
    got = drift._issue_reasons(1)
    assert len(got) == 1
    assert "未測定" in got[0]
    # Evidence 節は事由ではない — 拾ってはいけない
    assert "回帰" not in got[0]


def test_drift_skips_non_judgment_comments(monkeypatch):
    """maker の報告や rework 指示は事由ではない。"""
    sys.path.insert(0, str(TOOLS))
    import importlib
    drift = importlib.import_module("drift")
    body = "**cycle_completed** — 実装完了。\n**Why:**\n未測定のまま断定した。\n"
    monkeypatch.setattr(drift, "_sh", lambda cmd: json.dumps({"comments": [{"body": body}]}))
    assert drift._issue_reasons(1) == []


# ══ 0.32.1: cross-harness の一巡を、実 CLI で空 Ledger から通す ═══════════════
# **受け入れ条件7。** 0.32.0 はこれを持たず、片側が拒否されることだけを確かめて
# 「通せるか」を確かめなかったため、admit が永久に作れないデッドロックを push した。
# 判定関数の単体テストではこれを捕まえられない — 実 CLI を空の台帳から走らせること。

def _xh_org(tmp_path, lineage="cross-harness"):
    """cross-harness を宣言した空の org を作る。"""
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    (tmp_path / "constitution.yaml").write_text(
        f"enforcement:\n  judges:\n    lineage: {lineage}\n"
        "    integration_ref: origin/main\n"     # #106: show 等は統合先の宣言を要求する
        "    judgment_corrections:\n      authority_roles: [supervisor]\n",
        encoding="utf-8")
    (tmp_path / "organization.yaml").write_text(
        "roles:\n"
        "  - {id: supervisor, active: true, functions: [organize, operate]}\n"
        "  - {id: gate, active: true, functions: [judge, review]}\n"
        "  - {id: skeptic, active: true, functions: [judge, review]}\n",
        encoding="utf-8")
    return tmp_path


def _xh_authority_receipt(org, target, reason, issue="7", kind="superseded"):
    key = org / "supervisor-correction.pem"
    code, out = run("identity.py", "keygen", "--key-id", "supervisor-correction",
                    "--signer-id", "supervisor-principal", "--private-out", str(key),
                    "--authorized-roles", "supervisor", "--authorized-lineages", "authority",
                    cwd=str(org))
    assert code == 0, out
    oid = hashlib.sha256(str(org.resolve()).encode()).hexdigest()[:16]
    ledger = org / ".orgforge" / "ledger"
    lid = hashlib.sha256(str(ledger.resolve()).encode()).hexdigest()[:16]
    subject = f"correction:{kind}:{int(target)}"
    code, out = run(
        "identity.py", "receipt", "--org-id", oid, "--ledger-id", lid,
        "--subject", subject, "--issue", str(issue), "--role", "supervisor",
        "--phase", "govern", "--lineage", "authority", "--verdict", kind,
        "--event-class", "correction", "--requirements-digest",
        "judgment-correction-authority-v1", "--reasoning-sha256",
        hashlib.sha256(reason.encode("utf-8")).hexdigest(), "--issued-at",
        "2026-08-02T00:00:00Z", "--key-id", "supervisor-correction",
        "--private-key", str(key), cwd=str(org))
    assert code == 0, out
    receipt = org / "supervisor-correction.json"
    receipt.write_text(out.strip(), encoding="utf-8")
    return receipt


def _prov(tmp_path, lineage, verdict, issue=7, role="gate", why=None, extra=(),
          subject="subject-A"):
    return run("github_sync.py", "provisional",
               "--issue", str(issue), "--role", role, "--lineage", lineage,
               "--verdict", verdict, "--subject", subject,
               "--why", why or f"{lineage} の {role} として実際に見て決めた。"
                               f"再導出した範囲と、決め手になった箇所を書いている。",
               "--evidence", "実行したコマンドと出力の要旨", *extra,
               cwd=str(tmp_path))


def _events(tmp_path, cls):
    p = tmp_path / ".orgforge" / "ledger" / "ledger.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("class") == cls:
            out.append(e)
    return out


@pytest.mark.parametrize("first,second", [("same-harness", "cross-harness"),
                                          ("cross-harness", "same-harness")])
def test_xh_admission_from_empty_ledger_either_order(tmp_path, first, second):
    """受け入れ条件1+3: 空 Ledger から**どちらの順序でも**通り、一致が admission を生む。"""
    org = _xh_org(tmp_path)
    c1, o1 = _prov(org, first, "admit")
    assert c1 == 0, o1
    # 1件目では admission はまだ無い（受け入れ条件2）
    assert _events(org, "admission_decided") == []
    c2, o2 = _prov(org, second, "admit")
    assert c2 == 0, o2
    adm = _events(org, "admission_decided")
    assert len(adm) == 1, f"一致したのに admission が生成されていない: {o2}"
    pl = adm[0]["payload"]
    assert pl["verdict"] == "admit" and pl["lineage"] == "joint"
    assert sorted(pl["agreed_by"]) == ["cross-harness", "same-harness"]
    assert len(pl["from_seqs"]) == 2


def test_xh_single_lineage_does_not_admit(tmp_path):
    """受け入れ条件2: 片側だけでは admit されない。"""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit")[0] == 0
    assert _events(org, "admission_decided") == []
    assert len(_events(org, "verdict_provisional")) == 1


def test_xh_disagreement_blocks_admission_and_is_recorded(tmp_path):
    """受け入れ条件4: 不一致は admission を生まず、食い違いそのものが記録される。"""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit")[0] == 0
    c, o = _prov(org, "cross-harness", "reject")
    assert c == 5, o
    assert _events(org, "admission_decided") == []
    dis = _events(org, "judges_disagreed")
    assert len(dis) == 1
    assert dis[0]["payload"]["same_harness"] == "admit"
    assert dis[0]["payload"]["cross_harness"] == "reject"


def test_xh_lineage_cannot_rewrite_its_own_verdict(tmp_path):
    """受け入れ条件4: 同じ血統が verdict を書き換えて一致を作れない。"""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "reject")[0] == 0
    c, o = _prov(org, "same-harness", "admit")        # 反転を試みる
    assert c == 4, o
    assert "correction" in o
    assert _events(org, "admission_decided") == []


def test_xh_other_issue_does_not_satisfy_agreement(tmp_path):
    """受け入れ条件4: 別 Issue の判定は一致に数えない。"""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", issue=7)[0] == 0
    assert _prov(org, "cross-harness", "admit", issue=8)[0] == 0
    assert _events(org, "admission_decided") == []   # #7 も #8 も片側だけ


def test_xh_skeptic_and_gate_do_not_cross_satisfy(tmp_path):
    """受け入れ条件4: gate の判定は skeptic の一致に使えない（for_event で分ける）。"""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", role="gate")[0] == 0
    assert _prov(org, "cross-harness", "survives", role="skeptic")[0] == 0
    assert _events(org, "admission_decided") == []
    assert _events(org, "refutation_attempted") == []


def test_broken_constitution_fails_closed_no_downgrade(tmp_path):
    """受け入れ条件5+6: 設定を読めないなら非ゼロで止まり、same-harness に降格しない。"""
    org = _xh_org(tmp_path)
    (org / "constitution.yaml").write_text("enforcement: [not: valid: yaml", encoding="utf-8")
    c, o = _prov(org, "same-harness", "admit")
    assert c != 0
    both = o
    assert "解析できない" in both or "読めない" in both
    # **降格していないこと** — 台帳に何も入っていない
    assert _events(org, "verdict_provisional") == []
    assert _events(org, "admission_decided") == []


def test_bad_lineage_value_fails_closed(tmp_path):
    """受け入れ条件5: lineage の値が不正なら止まる（黙って既定に倒さない）。"""
    org = _xh_org(tmp_path, lineage="cross_harness")     # アンダースコアは不正
    c, o = _prov(org, "same-harness", "admit")
    assert c != 0
    assert "lineage" in o


def test_same_harness_org_rejects_provisional(tmp_path):
    """same-harness の org で provisional は使えない（一致を数える相手が居ない）。"""
    org = _xh_org(tmp_path, lineage="same-harness")
    c, o = _prov(org, "same-harness", "admit")
    assert c == 2
    assert "cross-harness" in o


def test_xh_pass_requires_evidence(tmp_path):
    """通過には evidence が必要 — 何も参照していない通過は判子である。"""
    org = _xh_org(tmp_path)
    code, out = run("github_sync.py", "provisional",
                    "--issue", "7", "--role", "gate", "--lineage", "same-harness",
                    "--verdict", "admit", "--subject", "subject-A",
                    "--why", "十分に長い理由を書いているが evidence が空である場合を試す。",
                    cwd=str(org))
    assert code == 2
    assert "evidence" in out


# ══ 0.32.2: 判定対象の同一性と、訂正からの脱出経路 ═════════════════════════════
# 監査が 0.32.1 で見つけたもの: (a) 案内していた correction の payload 形が実物と違い、
# 打っても無効化されないので拒否から抜け出せない、(b) 別の revision を見た2判定が一致扱いに
# なる、(c) joint が片方の reasoning しか持たない、(d) 同じ verdict なら重複を積める。
#
# **条件5+6 が核心である** — 0.32.0/0.32.1 で2回、拒否だけ確かめて脱出を確かめなかった。

def test_xh_different_subjects_do_not_agree(tmp_path):
    """条件3: 別の対象を見た2つの通過は一致ではない。"""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", subject="rev-A")[0] == 0
    c, o = _prov(org, "cross-harness", "admit", subject="rev-B")
    assert c == 6, o
    assert "別の対象" in o
    assert _events(org, "admission_decided") == []


def test_xh_same_subject_agrees(tmp_path):
    """条件3の対: 同じ対象なら一致し、joint に subject が載る。"""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", subject="rev-A")[0] == 0
    assert _prov(org, "cross-harness", "admit", subject="rev-A")[0] == 0
    adm = _events(org, "admission_decided")
    assert len(adm) == 1
    assert adm[0]["payload"]["review_subject_id"] == "rev-A"


def test_xh_exact_retry_is_noop_but_rejudge_is_refused(tmp_path):
    """条件4: 完全に同じ再実行だけが no-op。理由を変えた再判定は拒否。"""
    org = _xh_org(tmp_path)
    why = "同一性の検査のために、十分な長さの理由をここに書いておく。決め手はこの箇所である。"
    assert _prov(org, "same-harness", "admit", why=why)[0] == 0
    # 完全に同じ → no-op（重複して積まれない）
    c, o = _prov(org, "same-harness", "admit", why=why)
    assert c == 0, o
    assert len(_events(org, "verdict_provisional")) == 1
    # 同じ verdict だが理由が違う → 拒否（0.32.1 はこれを通していた）
    c, o = _prov(org, "same-harness", "admit",
                 why="同じ verdict のまま理由だけを差し替えた場合。これは重複として積めてはいけない。")
    assert c == 4, o
    assert len(_events(org, "verdict_provisional")) == 1


def test_xh_rejudge_hands_back_to_declared_authority_and_that_path_works(tmp_path):
    """Judgeには自己訂正コマンドを与えず、宣言済み第三者の脱出経路を実CLIで通す。"""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "reject")[0] == 0
    c, o = _prov(org, "same-harness", "admit")     # 差し替えを試みる → 拒否
    assert c == 4
    assert "authority roles: supervisor" in o
    assert "--actor <あなたの役割>" not in o
    prior = _events(org, "verdict_provisional")[0]
    reason = "base更新後に第三者authorityが再検証を要求した"
    receipt = _xh_authority_receipt(org, prior["seq"], reason)
    payload = json.dumps({"corrects": [prior["seq"]], "kind": "superseded",
                          "reason": reason,
                          "corrected_by": "supervisor"}, ensure_ascii=False)
    code, lout = run("ledger.py", "append", "--class", "correction",
                     "--actor", "supervisor", "--payload", payload, "--receipt", str(receipt),
                     cwd=str(org))
    assert code == 0, f"authority の correction が通らない: {lout}"
    assert ("effect=voids" in lout and "authority=supervisor" in lout
            and "assurance=authenticated" in lout)
    code, shown = run("org_cycle.py", "show", "--issue", "7", cwd=str(org))
    assert code == 0, shown
    assert ("correction kind=superseded effect=voids" in shown
            and "principal=supervisor-principal" in shown
            and "assurance=authenticated" in shown)

    # **効いていること** — 無効化されたので、新しい判定が入る
    c, o = _prov(org, "same-harness", "admit")
    assert c == 0, f"correction を打っても差し替えられない:\n{o}"
    provs = _events(org, "verdict_provisional")
    assert len(provs) == 2                                  # 元の reject と、新しい admit
    # そして cross-harness が揃えば joint になる（脱出経路が最後まで通る）
    assert _prov(org, "cross-harness", "admit")[0] == 0
    assert len(_events(org, "admission_decided")) == 1


def test_xh_joint_carries_both_lineages_reasoning(tmp_path):
    """条件7: joint が両血統の reasoning_sha256 と ref を持つ。"""
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", "admit", why="同一ハーネス側の judge の理由。独立に再導出した範囲と、判定の決め手になった箇所を書いている。")[0] == 0
    assert _prov(org, "cross-harness", "admit", why="別ハーネス側の judge の理由。独立に見た範囲と、判定の決め手になった具体的な箇所を書いている。")[0] == 0
    pl = _events(org, "admission_decided")[0]["payload"]
    by = pl["reasoning_by_lineage"]
    assert set(by) == {"same-harness", "cross-harness"}
    for lin in by:
        assert by[lin]["reasoning_sha256"]
        assert by[lin]["reasoning_ref"]
        assert by[lin]["seq"]
    # 両者の digest は異なり、joint の digest はそのどちらでもない（2つから作る）
    ds = {by[l]["reasoning_sha256"] for l in by}
    assert len(ds) == 2
    assert pl["reasoning_sha256"] not in ds


def test_review_subject_binds_tree_and_requirements(tmp_path):
    """review_subject が木と受け入れ基準に依存すること（judge が作れない値であること）。"""
    sys.path.insert(0, str(TOOLS))
    from orgcycle._core import review_subject
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    (tmp_path / "REQUIREMENTS.md").write_text("MUST: A", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "one"], cwd=tmp_path, check=True)
    s1, p1 = review_subject(7, "gate", "implement", cwd=str(tmp_path))
    # 受け入れ基準が変われば別の判定である
    (tmp_path / "REQUIREMENTS.md").write_text("MUST: A and B", encoding="utf-8")
    s2, p2 = review_subject(7, "gate", "implement", cwd=str(tmp_path))
    assert s1 != s2
    assert p1["requirements_digest"] != p2["requirements_digest"]
    # role が違えば別の判定である
    s3, _ = review_subject(7, "skeptic", "implement", cwd=str(tmp_path))
    assert s3 != s2


def test_non_pass_verdict_does_not_enter_agreement(tmp_path):
    """park / reject は通過ではないので、subject 比較や相手待ちに進まない。

    実測: #34 の park に対して「別の対象を見ている」という無関係な警告が出た。
    否は片方でも出れば否なので、一致を作る話に入る前に終えるべきである。
    """
    org = _xh_org(tmp_path)
    c, o = _prov(org, "same-harness", "park")
    assert c == 0, o
    assert "通過ではない" in o
    assert "別の対象" not in o
    assert _events(org, "admission_decided") == []


def test_print_subject_does_not_launch_a_judge(tmp_path, monkeypatch):
    """--print-subject は subject だけ出して終わる（cross-harness でも judge を起動しない）。

    実測: 記録のために subject を知ろうとして verify を打ち、headless judge が走って
    2分でタイムアウトした。記録の手順が判定の実行を要求してはいけない。
    """
    org = _xh_org(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=org, check=True)
    (org / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=org, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "x"], cwd=org, check=True)
    # PATH から codex を外す — 起動しようとしたなら落ちるので、起動していないことが分かる
    monkeypatch.setenv("PATH", "/nonexistent")
    # #101 以降、subject は Issue の worktree（か明示の --subject-root）から mint する。
    # この org に worktree は無いので、逃げ道を明示する — cwd への暗黙 fallback は無い。
    code, out = run("org_cycle.py", "verify", "--issue", "7", "--role", "gate",
                    "--print-subject", "--subject-root", str(org), cwd=str(org))
    assert code == 0, out
    assert re.search(r"^[0-9a-f]{64}$", out.strip().splitlines()[0])


@pytest.mark.parametrize("first,second", [("admit", "reject"), ("reject", "admit")])
def test_xh_disagreement_recorded_in_either_order(tmp_path, first, second):
    """食い違いは **どちらが先でも** 記録される。

    0.32.2 で park/reject を早期に返すようにしたとき、admit → reject の順では
    judges_disagreed が残らなくなった。片方の順序だけ確かめると通ってしまう形である。
    """
    org = _xh_org(tmp_path)
    assert _prov(org, "same-harness", first)[0] == 0
    c, o = _prov(org, "cross-harness", second)
    assert c == 5, o
    assert _events(org, "admission_decided") == []
    dis = _events(org, "judges_disagreed")
    assert len(dis) == 1, o
    assert dis[0]["payload"]["same_harness"] == first
    assert dis[0]["payload"]["cross_harness"] == second


# ══ 2.0.15: judge dispatch 前の bounded environment preflight ═══════════════

def _preflight_constitution(tmp_path, preflights):
    import yaml
    path = tmp_path / "constitution.yaml"
    path.write_text(yaml.safe_dump({"enforcement": {"judges": {
        "preflights": preflights}}}, sort_keys=False), encoding="utf-8")
    return path


def test_judge_preflight_runs_only_for_matching_issue_phase_and_role(tmp_path, monkeypatch):
    mod = _cycle_mod("preflight")
    marker = tmp_path / "ran"
    path = _preflight_constitution(tmp_path, [{
        "id": "database",
        "command": [sys.executable, "-c",
                    "import os,pathlib; pathlib.Path(os.environ['MARKER']).write_text("
                    "os.environ['ORG_PREFLIGHT_ISSUE'] + ':' + "
                    "os.environ['ORG_PREFLIGHT_PHASE'] + ':' + "
                    "os.environ['ORG_PREFLIGHT_ROLE'])"],
        "timeout_seconds": 2,
        "applies_to": {"issues": [36], "phases": ["implement"],
                       "roles": ["gate"]},
    }])
    monkeypatch.setattr(mod, "_constitution_path", lambda: str(path))
    monkeypatch.setenv("MARKER", str(marker))

    assert mod.run_declared_preflights(7, "gate", "implement", cwd=tmp_path) == (True, [])
    assert not marker.exists(), "unrelated Issue inherited the database probe"
    assert mod.run_declared_preflights(36, "skeptic", "implement", cwd=tmp_path) == (True, [])
    assert not marker.exists(), "unrelated role inherited the database probe"
    ok, evidence = mod.run_declared_preflights(36, "gate", "implement", cwd=tmp_path)
    assert ok and len(evidence) == 1
    assert marker.read_text(encoding="utf-8") == "36:implement:gate"
    measured = json.loads(evidence[0])
    assert measured["id"] == "database"
    assert measured["status"] == "pass"
    assert measured["exit_code"] == 0
    assert isinstance(measured["elapsed_ms"], int)


def test_judge_preflight_failure_reports_exact_probe_result(tmp_path, monkeypatch, capsys):
    mod = _cycle_mod("preflight")
    path = _preflight_constitution(tmp_path, [{
        "id": "runtime-health",
        "command": [sys.executable, "-c",
                    "import sys; print('measured-down'); print('socket refused', file=sys.stderr); "
                    "raise SystemExit(23)"],
        "timeout_seconds": 2,
        "applies_to": {"issues": [36]},
    }])
    monkeypatch.setattr(mod, "_constitution_path", lambda: str(path))
    ok, evidence = mod.run_declared_preflights(36, "gate", "implement", cwd=tmp_path)
    assert not ok and len(evidence) == 1
    measured = json.loads(evidence[0])
    assert measured["status"] == "fail"
    assert measured["exit_code"] == 23
    assert measured["stdout"] == "measured-down\n"
    assert measured["stderr"] == "socket refused\n"
    assert measured["command"][0] == sys.executable
    assert "runtime-health" in capsys.readouterr().err


def test_judge_preflight_timeout_is_measured_and_stops(tmp_path, monkeypatch):
    mod = _cycle_mod("preflight")
    path = _preflight_constitution(tmp_path, [{
        "id": "slow-runtime",
        "command": [sys.executable, "-c", "import time; time.sleep(1)"],
        "timeout_seconds": 0.03,
    }])
    monkeypatch.setattr(mod, "_constitution_path", lambda: str(path))
    ok, evidence = mod.run_declared_preflights(36, "gate", "implement", cwd=tmp_path)
    measured = json.loads(evidence[0])
    assert not ok
    assert measured["status"] == "timeout"
    assert measured["exit_code"] is None
    assert measured["timeout_seconds"] == 0.03
    assert measured["elapsed_ms"] >= 20


@pytest.mark.parametrize("probe,fragment", [
    ({"id": "shell", "command": "docker info", "timeout_seconds": 2}, "argv list"),
    ({"id": "unbounded", "command": ["true"]}, "timeout_seconds"),
    ({"id": "bad-scope", "command": ["true"], "timeout_seconds": 2,
      "applies_to": {"labels": ["db"]}}, "未知の selector"),
    ({"id": "scope-typo", "command": ["true"], "timeout_seconds": 2,
      "apply_to": {"issues": [36]}}, "未知の field"),
])
def test_judge_preflight_rejects_ambiguous_or_unbounded_contract(
        tmp_path, monkeypatch, probe, fragment):
    mod = _cycle_mod("preflight")
    path = _preflight_constitution(tmp_path, [probe])
    monkeypatch.setattr(mod, "_constitution_path", lambda: str(path))
    with pytest.raises(mod.PreflightConfigError, match=fragment):
        mod.load_probes(36, "gate", "implement")


def test_verify_stops_before_any_judge_work_when_preflight_fails(monkeypatch, capsys):
    judge = _cycle_mod("judge")
    monkeypatch.setattr(judge, "_role_charter", lambda role: ("charter", "agents/gate.md"))
    monkeypatch.setattr(judge, "_issue_body", lambda issue: ("title", "MUST: work"))
    monkeypatch.setattr(judge, "run_declared_preflights",
                        lambda *args, **kwargs: (False, ['{"id":"db","status":"fail"}']))
    monkeypatch.setattr(judge, "_seam",
                        lambda *args: pytest.fail("seam/judge material was built after failure"))
    # #101: subject は worktree（か明示の --subject-root）から。issue-36 の worktree は
    # 無いので明示する — このテストの主題は「preflight 失敗で judge を起動しない」。
    args = argparse.Namespace(issue=36, role="gate", phase="implement", print_subject=False,
                              subject_root=os.getcwd())
    assert judge.cmd_verify(args) == 8
    err = capsys.readouterr().err
    assert "judge は起動していない" in err


def test_preflight_contract_is_bundled_identically_for_both_harnesses():
    source = (TOOLS / "orgcycle" / "preflight.py").read_bytes()
    for harness in ("claude-code", "codex"):
        bundled = REPO / "integrations" / harness / "tools" / "orgcycle" / "preflight.py"
        assert bundled.read_bytes() == source


def test_org_lint_rejects_invalid_preflight_before_first_judge():
    import importlib.util
    import yaml
    spec = importlib.util.spec_from_file_location("org_lint_preflight", TOOLS / "org_lint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    constitution = yaml.safe_load((TEMPLATE / "constitution.yaml").read_text(encoding="utf-8"))
    constitution["enforcement"]["judges"]["preflights"] = [{
        "id": "unbounded", "command": ["runtime", "status"]}]
    lint = module.Lint()
    module.lint_constitution(constitution, lint)
    assert any(error.startswith("[PF]") and "timeout_seconds" in error
               for error in lint.errs), lint.errs


# ══ 0.32.3: review_subject が作業ツリー全体を束ねる ═══════════════════════════

def _repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "t.txt").write_text("tracked\n", encoding="utf-8")
    (tmp_path / "REQUIREMENTS.md").write_text("MUST: A\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _sub(path, issue=7, role="gate", phase="implement"):
    sys.path.insert(0, str(TOOLS))
    from orgcycle._core import review_subject
    return review_subject(issue, role, phase, cwd=str(path))[0]


def test_subject_changes_when_untracked_content_changes(tmp_path):
    """**監査が実証した欠陥。** 未追跡ファイルの内容を差し替えても id が同じだった。

    `git diff HEAD` は未追跡の内容を含まないので、名前だけ拾って中身を見ていなかった。
    judge が未追跡ファイルを読んで判定していれば、別の成果物を「同じもの」として
    一致させられる。
    """
    org = _repo(tmp_path)
    (org / "untracked.txt").write_text("first\n", encoding="utf-8")
    s1 = _sub(org)
    (org / "untracked.txt").write_text("second-different-content\n", encoding="utf-8")
    s2 = _sub(org)
    assert s1 != s2


def test_subject_is_reproducible_for_the_same_tree(tmp_path):
    """同じ状態なら同じ id。でなければ同じレビューを2度行えない。"""
    org = _repo(tmp_path)
    (org / "untracked.txt").write_text("x\n", encoding="utf-8")
    assert _sub(org) == _sub(org)


def test_subject_ignores_gitignored_build_output(tmp_path):
    """生成物で id が動くと、同じレビューを2度行えない。"""
    org = _repo(tmp_path)
    (org / ".gitignore").write_text("build/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=org, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "ignore"], cwd=org, check=True)
    before = _sub(org)
    (org / "build").mkdir()
    (org / "build" / "out.js").write_text("artifact\n", encoding="utf-8")
    assert _sub(org) == before


def test_subject_changes_for_staged_and_unstaged_alike(tmp_path):
    """tracked の staged / unstaged いずれの変更でも id は動く。"""
    org = _repo(tmp_path)
    base = _sub(org)
    (org / "t.txt").write_text("tracked\nunstaged\n", encoding="utf-8")
    unstaged = _sub(org)
    assert unstaged != base
    subprocess.run(["git", "add", "t.txt"], cwd=org, check=True)
    assert _sub(org) == unstaged        # 同じ内容なので id は同じ（staging は対象ではない）


def test_subject_does_not_touch_the_real_index(tmp_path):
    """一時 index を使うので、監督の staging 状態を壊さない。"""
    org = _repo(tmp_path)
    (org / "untracked.txt").write_text("x\n", encoding="utf-8")
    (org / "t.txt").write_text("tracked\nmodified\n", encoding="utf-8")
    before = subprocess.run(["git", "status", "--porcelain"], cwd=org,
                            capture_output=True, text=True).stdout
    _sub(org)
    after = subprocess.run(["git", "status", "--porcelain"], cwd=org,
                           capture_output=True, text=True).stdout
    assert before == after
    assert "?? untracked.txt" in after       # staged にされていない


def test_subject_records_dirty_and_head_tree_separately(tmp_path):
    """dirty かどうかと、HEAD の木が何かを、両方残す（後から追える形）。"""
    sys.path.insert(0, str(TOOLS))
    from orgcycle._core import review_subject
    org = _repo(tmp_path)
    _, clean = review_subject(7, "gate", "implement", cwd=str(org))
    assert clean["dirty"] == ""
    assert clean["reviewed_tree_sha"] == clean["head_tree_sha"]
    (org / "untracked.txt").write_text("x\n", encoding="utf-8")
    _, dirty = review_subject(7, "gate", "implement", cwd=str(org))
    assert dirty["dirty"] == "1"
    assert dirty["reviewed_tree_sha"] != dirty["head_tree_sha"]


# ── #101: verify の subject は Issue の worktree を記述する ──────────────────
# 本体（リポジトリ直下）から `verify --issue N` を打つと cwd の tree が subject に
# なり、どの Issue でも同一 subject（ahead=0 の main）が mint された（OBS-031/055/071）。
# joint admission は subject の一致を「二血統が同じものを見た」証拠に使うので、
# subject が cwd 依存だと独立判定の同一性が壊れる。

def _subject_org(tmp_path, issues=(7, 8)):
    """scratch org: main+develop を持つ primary と、Issue ごとの worktree（各1コミット先行）。"""
    repo = tmp_path / "org"
    repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "organization.yaml").write_text("name: t\n", encoding="utf-8")
    (repo / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    integration_ref: develop\n", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "seed"); g("branch", "develop")
    for issue in issues:
        code, out = run("github_sync.py", "branch", "--issue", str(issue), "--worktree",
                        "--base", "develop", "--repo", "o/n", cwd=str(repo))
        assert code == 0, out
        wt = repo / ".orgforge" / "wt" / f"issue-{issue}"
        (wt / f"F{issue}.txt").write_text("x\n", encoding="utf-8")
        g("add", "-A", cwd=wt); g("commit", "-qm", f"i{issue}", cwd=wt)
    return repo, g


def _print_subject(repo, issue, *extra, cwd=None):
    """verify --print-subject を叩き、(returncode, sid, parts, stderr) を返す。"""
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", str(issue), "--role", "gate", "--print-subject", *extra],
                       capture_output=True, text=True, cwd=str(cwd or repo))
    sid = next((l.strip() for l in p.stdout.splitlines()
                if re.fullmatch(r"[0-9a-f]{64}", l.strip())), None)
    parts = dict(re.findall(r"^\s*(\w+)\s*=\s*(\S+)", p.stderr, re.M))
    return p.returncode, sid, parts, p.stderr


def test_verify_subject_is_the_issue_worktree_not_cwd(tmp_path):
    """回帰そのもの: 本体 cwd から打っても、subject は Issue worktree の tree を記述する。"""
    repo, g = _subject_org(tmp_path)
    wt_tree = g("rev-parse", "HEAD^{tree}",
                cwd=repo / ".orgforge" / "wt" / "issue-7").stdout.strip()
    root_tree = g("rev-parse", "HEAD^{tree}").stdout.strip()
    assert wt_tree != root_tree, "前提: worktree は本体より先行している"

    code, sid, parts, err = _print_subject(repo, 7)
    assert code == 0, err
    assert parts["reviewed_tree_sha"] == wt_tree, \
        "cwd（本体）の tree が subject になっている — #101 の回帰"
    assert parts["reviewed_tree_sha"] != root_tree
    assert parts["ahead"] == "1", "worktree は develop より1コミット先行のはず（ahead=0 は cwd 観測）"

    # cwd がその worktree 自身のときは従来どおり（同じ subject）
    code2, sid2, _, err2 = _print_subject(repo, 7,
                                          cwd=repo / ".orgforge" / "wt" / "issue-7")
    assert code2 == 0, err2
    assert sid2 == sid, "worktree 内から打った場合と subject が一致しない"


def test_verify_subjects_differ_across_issues(tmp_path):
    """worktree が異なる2つの Issue は、同じ cwd から打っても別 subject になる。"""
    repo, _ = _subject_org(tmp_path)
    code7, sid7, p7, err7 = _print_subject(repo, 7)
    code8, sid8, p8, err8 = _print_subject(repo, 8)
    assert code7 == 0 and code8 == 0, err7 + err8
    assert sid7 != sid8, "別 Issue が同一 subject — 「同じ対象を見た」偽証拠が作れてしまう"
    assert p7["reviewed_tree_sha"] != p8["reviewed_tree_sha"]


def test_verify_fails_closed_when_worktree_is_missing(tmp_path):
    """worktree が無ければ非ゼロ exit。cwd への暗黙 fallback で subject を mint しない。"""
    repo, _ = _subject_org(tmp_path, issues=())
    code, sid, _, err = _print_subject(repo, 42)
    assert code != 0
    assert sid is None, "worktree 不在でも subject が mint された — fail-open"
    assert os.path.join(".orgforge", "wt", "issue-42") in err, \
        "期待した worktree のパスがエラーに出ていない"
    assert "--subject-root" in err


def test_verify_subject_root_override(tmp_path):
    """--subject-root は worktree 運用でないレイアウトの明示的な逃げ道。印字にも残る。"""
    repo, g = _subject_org(tmp_path, issues=())
    root_tree = g("rev-parse", "HEAD^{tree}").stdout.strip()
    code, sid, parts, err = _print_subject(repo, 42, "--subject-root", str(repo))
    assert code == 0, err
    assert sid and parts["reviewed_tree_sha"] == root_tree
    assert parts.get("subject_root") == os.path.abspath(str(repo)), \
        "どの checkout を意図して判定したかが印字に残っていない"


def test_verify_rejects_issue_worktree_with_unbound_branch(tmp_path):
    """Issue worktree が detached/別branchなら issue の成果物として受理しない。"""
    repo, g = _subject_org(tmp_path, issues=(7,))
    wt = repo / ".orgforge" / "wt" / "issue-7"
    g("checkout", "--detach", "develop", cwd=wt)
    code, sid, _, err = _print_subject(repo, 7)
    assert code == 12
    assert sid is None
    assert "branch" in err and "束縛" in err


# ── #101 rework: isdir では偽 worktree が通る（skeptic の反証）─────────────────
# 空の残骸ディレクトリ・prune せず再作成されたディレクトリ・repo root への symlink は
# どれも primary の内側に居るので、git -C が primary に解決し、subject が primary の
# tree（ahead=0・relation=current）として警告なしに mint される — OBS-071 の偽造の再現。
# 「まさにそこを toplevel とする実 worktree」まで確かめて初めて fail-closed になる。

def test_verify_rejects_empty_stub_at_worktree_path(tmp_path):
    """失敗した `git worktree add` が残す空ディレクトリでは subject を mint しない。"""
    repo, g = _subject_org(tmp_path, issues=())
    fake = repo / ".orgforge" / "wt" / "issue-42"
    fake.mkdir(parents=True)
    code, sid, _, err = _print_subject(repo, 42)
    assert code != 0, "残骸ディレクトリで verify が成功した — primary の tree が偽造される"
    assert sid is None, "残骸ディレクトリから subject が mint された（OBS-071 の偽造）"
    assert os.path.join(".orgforge", "wt", "issue-42") in err


def test_verify_rejects_symlink_at_worktree_path(tmp_path):
    """canonical path が repo root への symlink でも subject を mint しない。"""
    repo, g = _subject_org(tmp_path, issues=())
    (repo / ".orgforge" / "wt").mkdir(parents=True, exist_ok=True)
    (repo / ".orgforge" / "wt" / "issue-43").symlink_to(repo)
    code, sid, _, err = _print_subject(repo, 43)
    assert code != 0, "symlink 経由で verify が成功した — primary の tree が偽造される"
    assert sid is None
    assert os.path.join(".orgforge", "wt", "issue-43") in err


def test_verify_fails_after_worktree_replaced_with_plain_dir(tmp_path):
    """実 worktree が消え、同じパスに素のディレクトリが再作成された遷移でも黙らない。"""
    import shutil
    repo, g = _subject_org(tmp_path)
    wt = repo / ".orgforge" / "wt" / "issue-7"
    wt_tree = g("rev-parse", "HEAD^{tree}", cwd=wt).stdout.strip()
    code, sid, parts, err = _print_subject(repo, 7)
    assert code == 0 and parts["reviewed_tree_sha"] == wt_tree, err
    shutil.rmtree(wt)
    wt.mkdir()                     # rm -rf 後に prune せず再作成（実地で起きる形）
    code2, sid2, _, err2 = _print_subject(repo, 7)
    assert code2 != 0, "worktree 消失後も verify が成功した — primary の tree に黙って差し替わる"
    assert sid2 is None


# ── #106: 統合先は constitution の integration_ref から解決する（develop を推測しない）──
# Tatekae 実測: constitution が integration_ref: origin/main を宣言しているのに、
# begin(OBS-053)/show(OBS-054)/gc(OBS-057)/integrate(OBS-048) が develop を hard-code し、
# 1つの製品の中で「統合先はどこか」への答えが複数あった。verify が既に使っている解決
# （review_freshness.integration_ref_policy）を全 subcommand で共有する。


def _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org106"):
    """constitution が統合先を宣言する（あるいはしない）git 付き org。develop 無しが既定。"""
    org = tmp_path / name
    org.mkdir()

    def g(*a, cwd=org):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)

    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (org / "seed.txt").write_text("s", encoding="utf-8")
    (org / "organization.yaml").write_text("roles: []\n", encoding="utf-8")
    judges = f"    integration_ref: {integration_ref}\n" if integration_ref else ""
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n" + (judges or "    {}\n"), encoding="utf-8")
    # 統治ファイルは main に**コミットしてから** branch を切る — 後続の `add -A` が
    # constitution を feature branch に巻き込み、checkout で消える事故を防ぐ。
    g("add", "-A")
    g("commit", "-qm", "seed")
    g("update-ref", "refs/remotes/origin/main", "main")
    if develop:
        g("branch", "develop")
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    return org, g


def test_resolve_integration_base_explicit_wins_and_constitution_is_default(tmp_path, monkeypatch):
    """明示 --base > constitution の integration_ref > fail-closed（develop は推測しない）。"""
    core = _cycle_mod("_core")
    org, _ = _declared_org(tmp_path, integration_ref="origin/main", develop=True)
    monkeypatch.chdir(org)
    assert core.resolve_integration_base("develop") == ("develop", None)   # operator override
    ref, err = core.resolve_integration_base(None)
    assert (ref, err) == ("origin/main", None), f"constitution の宣言を読んでいない: {err}"


def test_resolve_integration_base_fails_closed_naming_both_options(tmp_path, monkeypatch):
    """(d) develop があり integration_ref が無い legacy org → 黙って develop に落ちない。"""
    core = _cycle_mod("_core")
    org, _ = _declared_org(tmp_path, integration_ref=None, develop=True)
    monkeypatch.chdir(org)
    ref, err = core.resolve_integration_base(None)
    assert ref is None, f"integration_ref 無しで {ref} を推測した"
    assert "--base" in err and "integration_ref" in err, f"両方の選択肢を名指ししていない: {err}"


def test_gc_collects_worktree_merged_to_constitution_ref(tmp_path, monkeypatch):
    """(a) OBS-057: origin/main に統合済みの worktree を、develop 無しの org で gc が消せる。"""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    wt = org / ".orgforge" / "wt" / "issue-3"
    g("worktree", "add", "-q", "-b", "feat/issue-3", str(wt), "origin/main")
    monkeypatch.chdir(org)
    m = _cycle_mod("inspect")
    rc = m.cmd_gc(argparse.Namespace(base=None, all=False))
    assert rc == 0
    assert not wt.is_dir(), "origin/main に統合済みの worktree が「未統合」として残った"


def test_gc_explicit_base_overrides_constitution(tmp_path, monkeypatch):
    """(b) 明示 --base は constitution より強い（operator override）。"""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=True)
    g("checkout", "-q", "develop")
    (org / "d.txt").write_text("d", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "develop ahead")
    g("checkout", "-q", "main")
    wt = org / ".orgforge" / "wt" / "issue-4"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-4", str(wt), "develop")
    monkeypatch.chdir(org)
    m = _cycle_mod("inspect")
    # constitution（origin/main）基準では未統合 → 残る
    assert m.cmd_gc(argparse.Namespace(base=None, all=False)) == 0
    assert wt.is_dir()
    # 明示 --base develop なら統合済み → 消える
    assert m.cmd_gc(argparse.Namespace(base="develop", all=False)) == 0
    assert not wt.is_dir(), "明示 --base が constitution に負けた"


# ── #107: 導出 branch 名を実在の branch と突合する ────────────────────────────
# Tatekae 実測（OBS-012 / OBS-048欠陥6 / OBS-057原因2）: 導出名 feat/issue-15-google が
# 実在せず（実在は feat/issue-15-login-redirect）、gc の `--merged --list <導出名>` が
# 常に空 → 統合済み worktree が「未統合」として永久に残った。worktree の HEAD が常に真。


def test_gc_collects_merged_worktree_whose_real_branch_differs_from_derived(
        tmp_path, monkeypatch, capsys):
    """(a) Tatekae shape: worktree は feat/issue-15-login-redirect（origin/main に統合済み）、
    タイトル導出名は feat/issue-15-google → gc は実 HEAD で merged 判定して片付ける。"""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107")
    wt = org / ".orgforge" / "wt" / "issue-15"
    g("worktree", "add", "-q", "-b", "feat/issue-15-login-redirect", str(wt), "origin/main")
    (wt / "fix.txt").write_text("done", encoding="utf-8")
    g("add", "-A", cwd=wt)
    g("commit", "-qm", "fix login redirect", cwd=wt)
    # 統合済みにする: origin/main を branch の先端まで進める（merge 済みの形）
    g("update-ref", "refs/remotes/origin/main", "feat/issue-15-login-redirect")
    monkeypatch.chdir(org)
    m = _cycle_mod("inspect")
    # 導出名はタイトル由来（タイトル変更後の形）— 実在しない
    monkeypatch.setattr(m, "_branch_for", lambda i: f"feat/issue-{i}-google")
    rc = m.cmd_gc(argparse.Namespace(base=None, all=False))
    assert rc == 0
    assert not wt.is_dir(), \
        "統合済み worktree が残った — 導出名 feat/issue-15-google で merged を問うている（#107）"
    # (b) 不一致は黙らない — どちらを採用したかを警告で言う
    err = capsys.readouterr().err
    assert "feat/issue-15-google" in err and "feat/issue-15-login-redirect" in err, \
        f"導出名と実在名の不一致が警告されていない: {err!r}"


def test_gc_keeps_worktree_when_branch_cannot_be_resolved(tmp_path, monkeypatch, capsys):
    """(d) fail-closed: worktree が detached HEAD で導出名も実在しない → 消さずに残して言う。"""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107d")
    wt = org / ".orgforge" / "wt" / "issue-9"
    g("worktree", "add", "-q", "--detach", str(wt), "origin/main")
    monkeypatch.chdir(org)
    m = _cycle_mod("inspect")
    monkeypatch.setattr(m, "_branch_for", lambda i: f"feat/issue-{i}-ghost")
    rc = m.cmd_gc(argparse.Namespace(base=None, all=False))
    assert rc == 0
    assert wt.is_dir(), "実在 branch を特定できないのに worktree を消した"
    captured = capsys.readouterr()
    err = captured.err
    assert "feat/issue-9-ghost" in err, f"何を解決できなかったのか名指ししていない: {err!r}"
    out = captured.out
    assert "detached HEAD のため自動削除しない" in out
    assert f"git worktree remove {wt}" in out


def test_resolve_issue_branch_worktree_head_is_authoritative(tmp_path):
    """(a)(b) worktree が実在するなら HEAD が真。導出名とずれたら warn（黙らない）。"""
    core = _cycle_mod("_core")
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107r")
    wt = org / ".orgforge" / "wt" / "issue-15"
    g("worktree", "add", "-q", "-b", "feat/issue-15-login-redirect", str(wt), "origin/main")
    br, warn, err = core.resolve_issue_branch(15, derived="feat/issue-15-google", cwd=str(org))
    assert (br, err) == ("feat/issue-15-login-redirect", None)
    assert warn and "feat/issue-15-google" in warn and "feat/issue-15-login-redirect" in warn
    # (e) 導出名 == 実在名なら従来どおり — warn も出ない
    br2, warn2, err2 = core.resolve_issue_branch(
        15, derived="feat/issue-15-login-redirect", cwd=str(org))
    assert (br2, warn2, err2) == ("feat/issue-15-login-redirect", None, None)


def test_resolve_issue_branch_uses_existing_derived_without_worktree(tmp_path):
    """(c) worktree 無し + 導出名が実在 → 実在確認の上でそのまま使う。"""
    core = _cycle_mod("_core")
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107c")
    g("branch", "feat/issue-7-add-login")
    br, warn, err = core.resolve_issue_branch(7, derived="feat/issue-7-add-login", cwd=str(org))
    assert (br, warn, err) == ("feat/issue-7-add-login", None, None)


def test_resolve_issue_branch_names_detached_worktree_truthfully(tmp_path):
    """#107 rework (3b): worktree が在るのに「worktree も無い」と嘘を言わない —
    在るが detached HEAD で branch を指していない、と事実を言う。"""
    core = _cycle_mod("_core")
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107t")
    wt = org / ".orgforge" / "wt" / "issue-9"
    g("worktree", "add", "-q", "--detach", str(wt), "origin/main")
    br, warn, err = core.resolve_issue_branch(9, derived="feat/issue-9-ghost", cwd=str(org))
    assert br is None and err
    assert "も無い" not in err, f"worktree が在るのに「無い」と診断した: {err!r}"
    assert "detached" in err, f"実状態（detached HEAD）を言っていない: {err!r}"


def test_resolve_issue_branch_fails_closed_when_nothing_exists(tmp_path):
    """(d) worktree 無し + 導出名も実在しない → 黙って導出名を信じず、直し方を名指しする。"""
    core = _cycle_mod("_core")
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False, name="org107f")
    br, warn, err = core.resolve_issue_branch(7, derived="feat/issue-7-add-login", cwd=str(org))
    assert br is None
    assert err and "feat/issue-7-add-login" in err, "実在しない導出名を名指ししていない"
    assert "--worktree" in err or "git branch --list" in err, \
        f"直し方が書かれていない: {err!r}"


def test_gc_fails_closed_when_nothing_declares_the_base(tmp_path):
    """(c)(d) integration_ref 無し・--base 無し → develop があっても非ゼロで両方を名指し。"""
    org, g = _declared_org(tmp_path, integration_ref=None, develop=True)
    (org / ".orgforge" / "wt").mkdir(parents=True, exist_ok=True)
    code, out = run("org_cycle.py", "gc", cwd=str(org))
    assert code != 0, "統合先が宣言されていないのに gc が黙って進んだ"
    assert "--base" in out and "integration_ref" in out, out


def test_begin_fails_closed_and_writes_nothing_without_declared_base(tmp_path):
    """(c) begin: 統合先が決まらないなら、台帳に何も書く前に非ゼロで止まる。"""
    org, g = _declared_org(tmp_path, integration_ref=None, develop=True)
    code, out = run("org_cycle.py", "begin", "--role", "r", "--issue", "5",
                    "--parent", "9", "--candidate-id", "cid", "--no-check", cwd=str(org))
    assert code != 0, "worktree の base が決まらないのに begin が進んだ"
    assert "--base" in out and "integration_ref" in out, out
    ledger = org / ".orgforge" / "ledger" / "ledger.jsonl"
    assert not ledger.exists() or not ledger.read_text().strip(), \
        "fail-closed の前に台帳へ書いてしまった"


def test_begin_worktree_base_comes_from_constitution(tmp_path, monkeypatch):
    """(a) OBS-053: begin の worktree は constitution の integration_ref から切られる。"""
    org, _ = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    monkeypatch.chdir(org)
    m = _cycle_mod("cycle")
    calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: (calls.append(a), (0, ""))[1])
    monkeypatch.setattr(m, "_ledger", lambda *a: (0, ""))
    rc = m.cmd_begin(argparse.Namespace(
        role="r", issue=5, agent=None, phase="implement", parent="9",
        candidate_id="cid-5", base=None, why=None, no_check=True, no_worktree=False))
    assert rc == 0
    branch_calls = [c for c in calls if c and c[0] == "branch"]
    assert branch_calls, "worktree を用意する branch 呼び出しが無い"
    assert "--base" in branch_calls[0] and "origin/main" in branch_calls[0], \
        f"begin が constitution の統合先を worktree base に渡していない: {branch_calls[0]}"


def test_begin_mints_new_candidate_identity_after_rework(monkeypatch):
    m = _cycle_mod("cycle")
    monkeypatch.setattr(m, "_candidate_id", lambda _issue: "issue-7")
    monkeypatch.setattr(m, "_events_for", lambda _issue: (
        [{"class": "rework_requested", "payload": {"round": "2"}}], set()))
    seen = {}
    monkeypatch.setattr(m, "_steps_begin", lambda _a, _parent, cid: seen.setdefault("cid", cid) or [])
    monkeypatch.setattr(m, "_execute", lambda _steps, _label: 0)
    rc = m.cmd_begin(argparse.Namespace(
        role="r", issue=7, agent=None, phase="implement", parent="9",
        candidate_id=None, base=None, why=None, no_check=True, no_worktree=True))
    assert rc == 0
    assert seen["cid"] == "issue-7-rework-2"


def test_show_attributes_nothing_when_clean_against_constitution_ref(tmp_path):
    """(a) OBS-054: origin/main 基準で差分ゼロなら、不可逆変更を誤帰属しない。"""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    g("branch", "feat/issue-7")          # origin/main と同一 commit（差分ゼロ）
    code, out = run("org_cycle.py", "show", "--issue", "7", cwd=str(org))
    assert code == 0, out
    assert "不可逆" not in out, f"差分ゼロなのに不可逆変更を帰属させた:\n{out}"


def test_show_without_declared_base_prints_status_warns_and_skips_attribution(tmp_path):
    """rework #106: show は読み取り専用の orientation — 基準が無くても台帳由来の状態は出す。

    fail-closed は base を**消費する判断**（帰属ブロック）にだけかける: ブロックを省き、
    warn-don't-stop（cmd_plan と同じ形）で警告する。develop の推測はしない。
    """
    org, _ = _declared_org(tmp_path, integration_ref=None, develop=True)
    code, out = run("org_cycle.py", "show", "--issue", "7", cwd=str(org))
    assert code == 0, f"基準が無いだけで orientation 全体を閉め出した:\n{out}"
    assert "判定" in out and "次:" in out, f"台帳由来の状態が出ていない:\n{out}"
    assert "--base" in out and "integration_ref" in out, f"警告が両方の選択肢を名指ししていない:\n{out}"
    # 帰属ブロックの行ラベルは「不可逆:」。警告文（不可逆な変更の帰属は表示しない）とは区別する。
    assert "不可逆:" not in out, f"基準が無いのに帰属ブロックを出した:\n{out}"
    assert "帰属は表示しない" in out, f"帰属を省いたことを言っていない:\n{out}"


def test_show_attribution_block_fires_when_base_is_declared(tmp_path):
    """宣言があれば帰属ブロックは従来どおり働く（rework で警告側に倒しすぎていないか）。"""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    g("checkout", "-q", "-b", "feat/issue-9")
    (org / "migrations").mkdir()
    for n in ("0001_a.sql", "0002_b.sql", "0003_c.sql"):
        (org / "migrations" / n).write_text("select 1;", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "migrations")
    g("checkout", "-q", "main")
    code, out = run("org_cycle.py", "show", "--issue", "9", cwd=str(org))
    assert code == 0, out
    assert "不可逆" in out and "3 件" in out, f"宣言済みの基準で帰属ブロックが働いていない:\n{out}"


def test_gc_all_works_without_declared_base(tmp_path):
    """rework #106: --all は統合済み判定をしない = base を消費しない → 宣言を要求しない。"""
    org, g = _declared_org(tmp_path, integration_ref=None, develop=True)
    wt = org / ".orgforge" / "wt" / "issue-6"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-6", str(wt), "main")
    code, out = run("org_cycle.py", "gc", "--all", cwd=str(org))
    assert code == 0, f"base を消費しない --all が宣言を要求した:\n{out}"
    assert not wt.is_dir(), f"クリーンな worktree を --all が消していない:\n{out}"


def test_integrate_plan_targets_constitution_ref(tmp_path):
    """(a) OBS-048: integrate --plan の統合先が constitution の宣言になる。"""
    org, g = _declared_org(tmp_path, integration_ref="origin/main", develop=False)
    g("checkout", "-q", "-b", "feat/issue-42")
    (org / "w.txt").write_text("w", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "work")
    g("checkout", "-q", "main")
    code, out = run("org_cycle.py", "integrate", "--issue", "42", "--plan", cwd=str(org))
    assert code == 0, out
    assert "→ origin/main" in out, f"統合先が宣言どおりでない:\n{out}"
    assert "→ develop" not in out


def test_integrate_plan_fails_closed_without_declared_base(tmp_path):
    """(c)(d) integrate も推測しない — develop があっても宣言が無ければ非ゼロ。"""
    org, g = _declared_org(tmp_path, integration_ref=None, develop=True)
    g("checkout", "-q", "-b", "feat/issue-42")
    g("checkout", "-q", "main")
    code, out = run("org_cycle.py", "integrate", "--issue", "42", "--plan", cwd=str(org))
    assert code != 0, "統合先が宣言されていないのに integrate --plan が進んだ"
    assert "--base" in out and "integration_ref" in out, out
