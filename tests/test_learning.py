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
    assert "root" in out and "許された値ではない" in out, out


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
