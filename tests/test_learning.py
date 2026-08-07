"""learning.py repeats — 死因再発の検出（Issue #104 / OBS-052）。

実地（Tatekae）では、同じ根の失敗が別の言葉で記録され、文字列完全一致の検出器が
3回連続で clean を出した。修正: 記録時に閉じた語彙 `root` で分類し、再発は root の
一致で数える。root の無いレガシー記録は従来どおり文字列完全一致（後方互換）。
"""
import json
import sys

import yaml

from conftest import TOOLS, TEMPLATE, run, seed

sys.path.insert(0, str(TOOLS))
import learning  # noqa: E402


# ── MUST 3(a): 別の文言・同じ root → 再発として検出（clean と言わない）──────────
def test_same_root_different_wording_detected(tmp_path):
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "端数の偏りを検証していない",
          "root": "placebo_test"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "テスト硬化（fixtureが本番経路を迂回）",
          "root": "placebo_test"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 10, f"同根2件（別文言）を見逃した: {out}"
    assert "REPEATED DEATH" in out and "placebo_test" in out
    assert "clean" not in out


def test_distinct_roots_stay_clean_with_basis(tmp_path):
    # 根が違えば再発ではない。clean は判定基準（root 分類 n 件 / 文字列一致 m 件）を明示する。
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "x", "root": "placebo_test"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "y", "root": "declaration_drift"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, out
    assert "判定基準" in out and "2 件" in out, out


# ── MUST 3(b) / MUST 2: root の無いレガシー記録は文字列一致 + 基準の明示 ─────────
def test_legacy_unclassified_falls_back_to_exact_string(tmp_path):
    # 同一文字列は従来どおり検出される
    for cid, ts in (("A", "2026-07-16T01:00:00Z"), ("B", "2026-07-16T02:00:00Z")):
        seed(tmp_path, "gate", "result_retired",
             {"candidate_id": cid, "cause": "null hypothesis not rejected"}, ts=ts)
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 10 and "REPEATED DEATH" in out, out


def test_legacy_unclassified_clean_states_basis_and_limitation(tmp_path):
    # 別文言・root 無し → 従来どおり素通り（後方互換）だが、clean は
    # (1) 判定基準と未分類の件数、(2) 文字列一致の限界、を明示する。
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "端数の偏り"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "テスト硬化"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, out
    assert "判定基準" in out and "未分類" in out and "2 件" in out, out
    assert "文字列" in out, f"文字列一致の限界の明示が消えた: {out}"


def test_mixed_clean_reports_unclassified_count(tmp_path):
    # 分類済み1件 + 未分類1件、再発なし → clean だが未分類件数が読める
    # （root=other は判別する根ではないため「分類済み」に数えない — 判別根を使う）
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "x", "root": "declaration_drift"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "y"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, out
    assert "根分類（root）1 件" in out and "1 件" in out, out


# ── MUST 3(c): 不正な root は記録時に拒否される（schema enum、ledger.py append）──
def test_invalid_root_rejected_at_record_time(tmp_path):
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "gate",
                    "--class", "result_retired",
                    "--payload", json.dumps({"candidate_id": "A", "cause": "x",
                                             "root": "test_flaky"}))
    assert code != 0, "不正な root が記録できてしまった"
    assert "root" in out and "is not an allowed value" in out, out


def test_valid_root_accepted_and_stored(tmp_path):
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "x", "root": "integration_base_moved"})
    text = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    rec = [json.loads(l) for l in text.splitlines() if l][-1]
    assert rec["payload"]["root"] == "integration_base_moved"


# ── 語彙の単一性: learning.DEATH_ROOTS と schema enum が同一（乖離＝検査の嘘）────
def test_vocabulary_matches_schema_enum():
    doc = yaml.safe_load((TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"))
    enums = doc["validation"]["enums"]
    expected = set(learning.DEATH_ROOTS)
    assert {"placebo_test", "declaration_drift", "integration_base_moved",
            "self_written_premise", "other"} == expected
    for cls in ("result_retired", "rework_requested", "refutation_attempted"):
        assert set(enums[cls]["root"]) == expected, \
            f"{cls} の root enum が learning.DEATH_ROOTS と乖離: {enums.get(cls)}"


def test_death_roots_have_ja_descriptions():
    for k, v in learning.DEATH_ROOTS.items():
        assert isinstance(v, str) and v.strip(), f"{k} に説明が無い"


# ── REWORK（gate指摘）: `other` は「根の同一性」を主張できない ─────────────────────
def test_two_unrelated_other_records_do_not_escalate_as_same_root(tmp_path):
    """`other` は判別する根ではない — 無関係な2つの死が両方 `other` なだけで
    「文言は違っても根は同じ」と主張して escalate してはならない（それは記録されて
    いない意味一致の捏造で、escalation チャネルを無視する訓練になる）。
    選択(a): `other` は文字列一致にフォールバックし、単独で root 再発グループを作らない。"""
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "依存パッケージのライセンス問題",
          "root": "other"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "顧客要件の撤回",
          "root": "other"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, \
        f"無関係な other 2件を『根は同じ』として escalate した: {out}"
    assert "REPEATED DEATH" not in out


def test_same_string_other_records_still_detected(tmp_path):
    # フォールバック先の文字列一致は生きている: other + 同一文言 → 検出
    for cid, ts in (("A", "2026-07-16T01:00:00Z"), ("B", "2026-07-16T02:00:00Z")):
        seed(tmp_path, "gate", "result_retired",
             {"candidate_id": cid, "cause": "同じ死因", "root": "other"}, ts=ts)
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 10 and "REPEATED DEATH" in out, out


# ═══ REWORK #2（skeptic指摘: 修正が休眠 — 本番の書き手が root を運べない）═══════════
import argparse
import importlib
import os
import subprocess


def _mod(name):
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    return importlib.import_module(name)


# ── 変更1a: org_cycle rework が --root を台帳 payload まで運ぶ ─────────────────────
def test_org_cycle_rework_carries_root_into_payload(monkeypatch):
    m = _mod("orgcycle.judge")
    calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: (calls.append(("gh",) + a) or (0, "ok")))
    monkeypatch.setattr(m, "_ledger", lambda *a: (calls.append(("ledger",) + a) or (0, "ok")))
    ns = argparse.Namespace(issue=32, after="refuted", by="supervisor",
                            reason="placebo テストを直す", to="maker", round=2,
                            root="placebo_test")
    assert m.cmd_rework(ns) == 0
    led = [c for c in calls if c[0] == "ledger"][0]
    payload = json.loads(led[led.index("--payload") + 1])
    assert payload.get("root") == "placebo_test", payload


def test_org_cycle_rework_rejects_unknown_root(monkeypatch, capsys):
    m = _mod("orgcycle.judge")
    calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: (calls.append(("gh",) + a) or (0, "ok")))
    monkeypatch.setattr(m, "_ledger", lambda *a: (calls.append(("ledger",) + a) or (0, "ok")))
    ns = argparse.Namespace(issue=32, after="refuted", by="supervisor",
                            reason="x", to="maker", round=2, root="totally_made_up_root")
    rc = m.cmd_rework(ns)
    out = capsys.readouterr()
    assert rc == 2, f"未知の root が拒否されなかった (rc={rc})"
    assert not calls, "拒否したのに副作用（gh/ledger）が走った"
    assert "placebo_test" in out.err + out.out, "許される値の一覧が出ていない"


def test_org_cycle_rework_help_offers_root():
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "rework", "--help"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and "--root" in p.stdout, p.stdout + p.stderr


# ── 変更1b: github_sync decide が --root を台帳 payload まで運ぶ ────────────────────
def _decide_ns(**kw):
    base = dict(repo="o/r", issue=5, event="refutation_attempted", verdict="refuted",
                why="スケルトンの検査は fixture 経由で本番経路を迂回しており、性質が壊れる場所を測っていない。",
                by="skeptic", phase=None, evidence=None, alternatives=None,
                standard=None, risk=None, event_id="ev-r1", lineage=None,
                claimed=None, verified=None, root=None)
    base.update(kw)
    return argparse.Namespace(**base)


def _fake_gh(posted):
    def gh(args, check=True):
        if args[:2] == ["issue", "view"]:
            return 0, json.dumps({"comments": [{"body": b} for b in posted]})
        if args[:2] == ["issue", "comment"]:
            posted.append(args[args.index("--body") + 1])
            return 0, "ok"
        return 0, ""
    return gh


def test_github_sync_decide_carries_root_into_payload(monkeypatch, tmp_path):
    rec = _mod("ghsync.record")
    posted = []
    monkeypatch.setattr(rec, "gh", _fake_gh(posted))
    led = tmp_path / "led"
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    rc = rec.cmd_decide(_decide_ns(root="placebo_test"))
    assert rc == 0, rc
    rows = [json.loads(l) for l in
            (led / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if l]
    ev = [r for r in rows if r["class"] == "refutation_attempted"][-1]
    assert ev["payload"].get("root") == "placebo_test", ev["payload"]


def test_github_sync_decide_rejects_unknown_root(monkeypatch, tmp_path, capsys):
    rec = _mod("ghsync.record")
    posted = []
    monkeypatch.setattr(rec, "gh", _fake_gh(posted))
    led = tmp_path / "led"
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    rc = rec.cmd_decide(_decide_ns(root="totally_made_up_root"))
    out = capsys.readouterr()
    assert rc == 2, f"未知の root が拒否されなかった (rc={rc})"
    assert not posted and not (led / "ledger.jsonl").exists(), \
        "拒否したのに Issue / 台帳に書いた"
    assert "placebo_test" in out.err + out.out, "許される値の一覧が出ていない"


def test_github_sync_decide_help_offers_root():
    p = subprocess.run([sys.executable, str(TOOLS / "github_sync.py"), "decide", "--help"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and "--root" in p.stdout, p.stdout + p.stderr


# ── 変更2 (M4): 移行期でも限界警告は消えない（unclassified >= 1 で出す）──────────────
def test_limitation_warning_survives_migration_mix(tmp_path):
    """skeptic lab2: 分類済み1 + 未分類1（根は同じだが片方に root が無い）→ clean のまま
    だが、文字列一致の限界警告は**出続けなければならない**。移行期に警告が消えると、
    未分類の1件が同根の再発でも黙って clean に見える。"""
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "検査が本番経路を測っていない",
          "root": "placebo_test"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "テスト硬化（同じ根、root 無し）"},
         ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, out
    assert "注意" in out and "文字列" in out, \
        f"移行期（未分類1件）で限界警告が消えた: {out}"


# ── 変更3 (M5): 語彙の外の root で再発を捏造しない（旧 schema 経由でしか書けない値）────
def test_unknown_root_string_does_not_fabricate_recurrence(tmp_path):
    """skeptic lab4: enum の無い旧 schema（main 相当）の下でだけ書ける未知の root 文字列は、
    root グループを形成してはならない — 無関係な死2件が `totally_made_up_root` を共有する
    だけで「根は同じ」と escalate するのは再発の捏造。文字列一致にフォールバックする。"""
    old_schema = tmp_path / "old-schema.yaml"
    # main（#104 以前）の形: result_retired は宣言されているが root の enum が無い
    old_schema.write_text(
        "event_classes:\n"
        "  result_retired: {candidate_id, cause, observed_outcome, root}\n"
        "validation: {}\n", encoding="utf-8")
    env = {**os.environ, "ORG_LEDGER_SCHEMA": str(old_schema)}
    for cid, cause, ts in (("A", "依存ライセンス問題", "2026-07-16T01:00:00Z"),
                           ("B", "顧客要件の撤回", "2026-07-16T02:00:00Z")):
        p = subprocess.run(
            [sys.executable, str(TOOLS / "ledger.py"), "append", str(tmp_path),
             "--actor", "gate", "--class", "result_retired", "--ts", ts,
             "--payload", json.dumps({"candidate_id": cid, "cause": cause,
                                      "root": "totally_made_up_root"})],
            capture_output=True, text=True, timeout=60, env=env)
        assert p.returncode == 0, p.stdout + p.stderr
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, \
        f"語彙に無い root 文字列の共有だけで再発を escalate した: {out}"
    assert "REPEATED DEATH" not in out


def test_profile_preserves_everyday_success_and_wad_unknowns(tmp_path):
    seed(tmp_path, "gate", "cycle_completed",
         {"candidate_id": "A", "role": "gate", "outputs": []},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "rework_requested",
         {"candidate_id": "A", "reason": "near miss"},
         ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "profile", str(tmp_path))
    assert code == 0, out
    profile = json.loads(out)
    assert profile["observation_taxonomy"]["everyday_success"] == 1
    assert profile["observation_taxonomy"]["failure"] == 1
    assert profile["inferred_wad"]["status"] == "not_inferred"
    assert profile["inferred_wad"]["confidence"] == "unknown"
    assert profile["learning_candidates"] == []
    assert profile["doctrine_mutated"] is False
    assert profile["resilience_score"] is None
