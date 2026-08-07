"""read-only judge が再導出できない MUST を、judge を起動する前に検出する。

守りたいのは2つ:
  1. 空振りの park を判定の**前**に潰す（judge 1回は実測 102秒。park は判定を1つも生まない）
  2. **判定はしない**（docs/03 §6.5 — forced invariant は正しいが forced judgment は判定の消滅）
2 が壊れると道具が gate を形骸化させるので、そちらを構造で縛る。
"""
import ast
import pathlib
import sys

import pytest

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from orgcycle.rederivability import advisory, unmeasurable_musts  # noqa: E402


# ── 1. 再導出できない MUST を拾う ─────────────────────────────────────────────
@pytest.mark.parametrize("must, expected_reason_fragment", [
    ("- The suite MUST pass 100回連続 green", "反復実行"),
    ("- The suite MUST pass 100 times in a row.", "反復実行"),
    # 語順違い。数字が前に来る形だけを見ていて取りこぼしていた実地の漏れ
    # （cross-harness judge が 2周目に reject の根拠として指摘した）。
    ("- MUST run 100 times consecutively", "反復実行"),
    ("- MUST be run consecutively 100 times", "反復実行"),
    ("- MUST survive 50 consecutive runs", "反復実行"),
    ("- CI MUST be green from a clean clone", "CI"),
    ("- The implementation MUST have p99 latency under 10 ms", "性能"),
    ("- The migration MUST apply to the real DB without loss", "データベース"),
    ("- Every mutation test MUST be proven active", "ミューテーション"),
])
def test_musts_needing_execution_are_flagged(must, expected_reason_fragment):
    spec = "## MUST — acceptance criteria\n" + must + "\n"
    found = unmeasurable_musts(spec)
    assert len(found) == 1, f"拾えていない: {must}"
    assert expected_reason_fragment in found[0][1]


# ── 2. 静的に確かめられる MUST は**拾わない**（誤検知はそれ自体が害）─────────────
@pytest.mark.parametrize("must", [
    "- The identifier MUST be kebab-case",
    "- The function MUST return None on an empty input",
    "- The module MUST NOT import yaml at module level",
    "- WHEN the cap is reached, the 11th join MUST be rejected",
])
def test_statically_checkable_musts_are_not_flagged(must):
    spec = "## MUST — acceptance criteria\n" + must + "\n"
    assert unmeasurable_musts(spec) == [], f"誤検知: {must}"


def test_empty_and_missing_spec_are_safe():
    assert unmeasurable_musts("") == []
    assert unmeasurable_musts(None) == []
    assert advisory([], "gate") is None


def test_advisory_names_the_cost_and_stays_advisory():
    """助言は「時間を失う」ことを言い、かつ **verdict を名乗らない**。"""
    found = unmeasurable_musts("## MUST\n- MUST pass 100 times in a row\n")
    text = advisory(found, "gate")
    assert "park" in text and "判定を生まない" in text          # 何を失うかを言う
    assert "--strict-rederivability" in text                    # 逃げ道を示す
    # 助言が verdict を宣言してはいけない。gate の判定語を「断定」として使わない。
    assert "judge は起動していない" not in text
    for verdict in ("admit", "reject"):
        assert f"verdict: {verdict}" not in text.lower()


# ── 3. 越えない線: この module は判定を持たない ─────────────────────────────
def test_module_returns_no_verdict_anywhere():
    """`admit` / `reject` を **返り値として** 作らないことを構文で縛る。

    文字列 grep だと docstring の説明文にも当たるので、AST で「return される値」だけを見る。
    ここが破られると道具が gate の代わりに判定し始める（docs/03 §6.5）。
    """
    src = (pathlib.Path(TOOLS) / "orgcycle" / "rederivability.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    returned = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Return) and n.value is not None]
    literals = [n.value for n in ast.walk(ast.Module(body=returned, type_ignores=[]))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for lit in literals:
        assert lit.strip().lower() not in {"admit", "reject", "park", "survives", "refuted"}, \
            f"判定語を返している: {lit!r}"
