"""ドメインに触れる仕事は、人と AI が合意する面を持ってから maker に渡す。

## なぜここが人の見る面なのか

diff レビューは「間違いを探す」作業で、見落としは黙って通る。しかもコード量に比例して
コストが上がるので、AI が生成量を増やすほど破綻する。ドメインモデル / ユースケース /
認可規則の照合は「両者が同じものを述べているか」なので、**不一致が見える**し、読む量は
ドメインの複雑さにしか比例しない。

認可をここに含めるのは、それが技術的セキュリティではなく**ドメインの一部**だから。実地では
12件の MUST のうち認可を定めたのが2件で、その1件が「あだ名」（装飾的なテキスト列）だった —
金額・支払者・債務の向き・グループ所有権は無防備のまま通っていた。

## 誤検知が一番の敵

宣言されたパスにしか効かせない。ドメイン層を `src/domain/` に置くか `app/models/` に置くかは
プロジェクトの選択で、プラグインが当てにいくと別レイアウトの org で誤検知する（稼働中の org
だけでも src/domain/ · src/usecase/ · src/db/ · supabase/migrations/ が併存していた）。
"""
import sys

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from ghsync.backlog import (_missing_domain_sections,  # noqa: E402
                            _touches_domain_surface)

PATHS = ["src/domain/", "src/usecase/", "src/db/", "supabase/migrations/"]
REQUIRE = ["domain_model", "use_case", "authorization"]

FILLED = ("## ドメインモデル\n- **Entity:** `Expense(id, payer: UserId, amount: Money)`\n"
          "- **不変条件:** `sum(shares.amount) == amount`\n"
          "## ユースケースシナリオ\n- **主:** 支出者が¥100を3人で均等割り → 34/33/33\n"
          "## 認可規則\n- **守る資産:** 金額 / 支払者 / 債務の向き / グループ所有権\n")


# ── どの Issue に効かせるか ────────────────────────────────────────────────
def test_domain_paths_are_matched_only_when_declared():
    body = "- **owns:** `src/domain/split.ts`\n"
    assert _touches_domain_surface(body, PATHS)
    # 宣言が無い org では検査そのものが動かない（黙って全 Issue を止めない）
    assert not _touches_domain_surface(body, [])


def test_non_domain_work_is_not_asked_for_a_domain_model():
    """CI 修正や画面調整にドメインモデルを要求しない（狼少年にしない）。"""
    for owns in ("`.github/workflows/ci.yml`", "`src/app/page.tsx`", "`package.json`"):
        assert not _touches_domain_surface(f"- **owns:** {owns}\n", PATHS), owns


def test_migrations_count_as_domain_surface():
    assert _touches_domain_surface("- **owns:** `supabase/migrations/`\n", PATHS)


# ── 何をもって「書かれている」とするか ────────────────────────────────────
def test_filled_sections_pass():
    assert _missing_domain_sections(FILLED, REQUIRE) == []


def test_template_placeholders_do_not_count_as_written():
    """テンプレを貼っただけの SPEC が一番危ない — 書いた気になるが合意の実体が無い。"""
    tmpl = ("## ドメインモデル\n- **Entity:** `<Entity(field: type)>`\n"
            "## ユースケースシナリオ\n- **主:** `<誰が何をして何が起きるか>`\n"
            "## 認可規則\n- **守る資産:** `<...>`\n")
    assert _missing_domain_sections(tmpl, REQUIRE) == REQUIRE


def test_missing_sections_are_reported_individually():
    partial = ("## ドメインモデル\n- **Entity:** `Expense(id)`\n"
               "## ユースケースシナリオ\n- **主:** 支出を登録する → 保存される\n")
    assert _missing_domain_sections(partial, REQUIRE) == ["authorization"]


def test_heading_alone_is_not_enough():
    """見出しだけで中身が無いものを通さない。"""
    assert "domain_model" in _missing_domain_sections(
        "## ドメインモデル\n\n## ユースケースシナリオ\n- **主:** x が y する\n"
        "## 認可規則\n- **守る資産:** 金額\n", REQUIRE)


def test_english_headings_are_recognized_too():
    """SPEC.md は日英を併記する。どちらの書き方でも拾う。"""
    en = ("## Domain model\n- **Entity:** `Expense(id)`\n"
          "## Use-case scenarios\n- **main:** a payer splits ¥100 three ways\n"
          "## Authorization\n- **assets protected:** amount, payer, direction of debt\n")
    assert _missing_domain_sections(en, REQUIRE) == []


def test_empty_body_reports_everything_required():
    assert _missing_domain_sections("", REQUIRE) == REQUIRE
    assert _missing_domain_sections(None, REQUIRE) == REQUIRE
