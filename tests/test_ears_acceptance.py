"""split-check の EARS 検査 — 散文の acceptance を起票時に止める。

## なぜここが load-bearing か（実地）

acceptance が散文だと gate は毎回「どう確かめるか」の設計から始め、周回ごとに基準がブレる。
実地の #170 は acceptance 10件中9件が散文のまま起票され、**12周**した（CI 12回・判定12回）。
`org-decompose.md` にも「後半6周の rework は Issue のどの MUST にも対応しない作業になった」
という記録がある。**検査の素通りが、収束しないループの入口だった。**

旧実装は本文全体に `"IF "` 等が含まれるかを見ていたため、acceptance が全部散文でも別の節の
"IF ANY" やコードブロックの `if` / SQL の `WHERE` に当たって素通りした。ここはその回帰を防ぐ。
"""
import sys

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from ghsync.backlog import _has_dod_command, _non_ears_acceptance  # noqa: E402


# ── 素通りしていた形（旧実装のバグ）────────────────────────────────────────
def test_prose_acceptance_is_flagged_even_when_body_mentions_if_elsewhere():
    """acceptance は散文。別の節に "IF ANY" があるだけで通してはいけない。"""
    body = ("## Acceptance\n"
            "1. The trace is derivable from the domain decision.\n"
            "2. Zero recipients are retained faithfully.\n\n"
            "## Notes\nSee RFC IF ANY are pending.\n")
    assert len(_non_ears_acceptance(body)) == 2


def test_prose_acceptance_is_flagged_even_when_code_block_has_where():
    """コードブロックの SQL `WHERE` を EARS の証拠にしてはいけない。"""
    body = ("## Acceptance\n- auth works\n- it should be fast\n"
            "```sql\nWHERE id = 1\n```\n")
    assert len(_non_ears_acceptance(body)) == 2


# ── 正しく書かれたものを誤検知しない（誤検知はそれ自体が害）────────────────
def test_ears_english_passes():
    body = ("## Acceptance\n"
            "- WHEN a user submits the invite link twice THE system SHALL create exactly one membership\n"
            "- IF an 11th member joins THEN THE system SHALL reject with a cap error\n")
    assert _non_ears_acceptance(body) == []


def test_ears_japanese_passes():
    """日本語の shall 相当（〜こと / しなければならない）も EARS として通す。"""
    body = ("## 受け入れ基準\n"
            "- 招待リンクを二度押したとき、メンバーシップを1件だけ作成すること\n"
            "- 11人目が参加した場合、上限エラーで拒否すること\n")
    assert _non_ears_acceptance(body) == []


# ── 境界 ────────────────────────────────────────────────────────────────
def test_no_acceptance_section_is_not_flagged():
    """acceptance 節が無い Issue をここで弾かない（別の検査の仕事）。"""
    assert _non_ears_acceptance("## Goal\nMake it better.\n") == []
    assert _non_ears_acceptance("") == []
    assert _non_ears_acceptance(None) == []


def test_seam_contract_metadata_is_not_treated_as_acceptance():
    """`owns:` / `depends_on:` は seam contract のメタ行であって要求文ではない。

    ここを要求文と数えると **正しく書かれた SPEC ほど違反が多くなる**（実際に既存テスト3件が
    それで落ちた）。SPEC.md ではこれらが MUST 節と同じ箇条書きで並ぶ。
    """
    body = ("## MUST\n- [ ] WHEN login THE system SHALL validate\n"
            "- **owns:** `app/auth/`\n"
            "- **depends_on:** なし。実装コードは1行も入らない\n")
    assert _non_ears_acceptance(body) == []


def test_dod_command_detected_in_both_languages():
    """gate が走らせる的。あれば確認方法の設計が要らず、判定が速く・基準が固定される。"""
    assert _has_dod_command(
        "- **DoD command (run this to know you're done):** `cd app && npm test -- expense`\n")
    assert _has_dod_command("- **完了の判定:** `python3 -m pytest tests/ -q` が緑なら完了\n")


def test_unfilled_template_placeholder_is_not_a_dod_command():
    """テンプレの穴が埋まっていないものを「ある」と数えない（それが一番危ない誤判定）。"""
    assert not _has_dod_command(
        "- **DoD command:** `<the exact command whose green output = these MUSTs>`\n")


def test_missing_dod_section_is_reported():
    assert not _has_dod_command("## Acceptance\n- WHEN x THE system SHALL y\n")
    assert not _has_dod_command("")


def test_mixed_section_reports_only_the_prose_lines():
    """EARS と散文が混在するとき、**散文の行だけ**を返す。"""
    body = ("## Acceptance\n"
            "- WHEN the cap is reached THE system SHALL reject the 11th join\n"
            "- it should be fast\n")
    bad = _non_ears_acceptance(body)
    assert len(bad) == 1 and "fast" in bad[0]
