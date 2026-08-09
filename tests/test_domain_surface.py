"""Work that touches the domain reaches a maker only once it carries the surface a human and the AI
agree on.

## Why this is the surface a human reads

A diff review is the work of "looking for mistakes", and an oversight passes silently. Its cost also
rises with the volume of code, so the more an AI generates, the worse it breaks down. Reconciling the
domain model, the use cases, and the authorization rules asks "do the two state the same thing", so
**a mismatch is visible**, and the reading scales only with the complexity of the domain.

Authorization belongs here because it is **part of the domain**, not technical security. In the
field, two of twelve MUSTs set authorization and one of those two was about the nickname (a
decorative text column) — the amount, the payer, the direction of the debt, and group ownership all
passed undefended.

## False positives are the worst enemy

It applies only to declared paths. Whether the domain layer sits in `src/domain/` or `app/models/` is
the project's choice, and a plugin that guesses produces false positives in an org with a different
layout (among running orgs alone, src/domain/, src/usecase/, src/db/, and supabase/migrations/
coexisted).
"""
import sys

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from ghsync.backlog import (_missing_counterexamples,  # noqa: E402
                            _missing_domain_sections,
                            _touches_domain_surface)

PATHS = ["src/domain/", "src/usecase/", "src/db/", "supabase/migrations/"]
REQUIRE = ["domain_model", "use_case", "authorization"]

FILLED = ("## ドメインモデル\n- **Entity:** `Expense(id, payer: UserId, amount: Money)`\n"
          "- **不変条件:** `sum(shares.amount) == amount`\n"
          "## ユースケースシナリオ\n- **主:** 支出者が¥100を3人で均等割り → 34/33/33\n"
          "## 認可規則\n- **守る資産:** 金額 / 支払者 / 債務の向き / グループ所有権\n")


# ── which Issues it applies to ──────────────────────────────────────────────
def test_domain_paths_are_matched_only_when_declared():
    body = "- **owns:** `src/domain/split.ts`\n"
    assert _touches_domain_surface(body, PATHS)
    # In an org with no declaration the check does not run at all (it does not silently stop every
    # Issue)
    assert not _touches_domain_surface(body, [])


def test_non_domain_work_is_not_asked_for_a_domain_model():
    """A domain model is not demanded of a CI fix or a screen adjustment (no crying wolf)."""
    for owns in ("`.github/workflows/ci.yml`", "`src/app/page.tsx`", "`package.json`"):
        assert not _touches_domain_surface(f"- **owns:** {owns}\n", PATHS), owns


def test_migrations_count_as_domain_surface():
    assert _touches_domain_surface("- **owns:** `supabase/migrations/`\n", PATHS)


# ── what counts as "written" ────────────────────────────────────────────────
def test_filled_sections_pass():
    assert _missing_domain_sections(FILLED, REQUIRE) == []


def test_template_placeholders_do_not_count_as_written():
    """A SPEC that merely pastes the template is the most dangerous — it feels written while
    nothing agreed on is there."""
    tmpl = ("## ドメインモデル\n- **Entity:** `<Entity(field: type)>`\n"
            "## ユースケースシナリオ\n- **主:** `<誰が何をして何が起きるか>`\n"
            "## 認可規則\n- **守る資産:** `<...>`\n")
    assert _missing_domain_sections(tmpl, REQUIRE) == REQUIRE


def test_missing_sections_are_reported_individually():
    partial = ("## ドメインモデル\n- **Entity:** `Expense(id)`\n"
               "## ユースケースシナリオ\n- **主:** 支出を登録する → 保存される\n")
    assert _missing_domain_sections(partial, REQUIRE) == ["authorization"]


def test_heading_alone_is_not_enough():
    """A heading with no content does not pass."""
    assert "domain_model" in _missing_domain_sections(
        "## ドメインモデル\n\n## ユースケースシナリオ\n- **主:** x が y する\n"
        "## 認可規則\n- **守る資産:** 金額\n", REQUIRE)


def test_english_headings_are_recognized_too():
    """SPEC.md carries both Japanese and English. Either wording is picked up."""
    en = ("## Domain model\n- **Entity:** `Expense(id)`\n"
          "## Use-case scenarios\n- **main:** a payer splits ¥100 three ways\n"
          "## Authorization\n- **assets protected:** amount, payer, direction of debt\n")
    assert _missing_domain_sections(en, REQUIRE) == []


def test_empty_body_reports_everything_required():
    assert _missing_domain_sections("", REQUIRE) == REQUIRE
    assert _missing_domain_sections(None, REQUIRE) == REQUIRE


# ── the counterexamples (placebo / null) ────────────────────────────────────
# Intent itself cannot be written whole, but an example of "this is not it" can be. Given a
# counterexample the gate can actually try "does the test go red if I put that placebo in".
#
# This became load-bearing from 2.3.1 onward. Injecting the role charter in full was stopped, and
# with it the placebo/null instruction disappeared from what reaches a judge
# (_focused_review_contract does not carry the word).
# What can no longer rest on a judge's memory has to sit as a fact in the specification.
def test_both_counterexamples_present_passes():
    body = ("- **placebo（意図を裏切る実装）:** `remainder_recipients を常に空配列で返す`\n"
            "- **null（利用者が拒否する出力）:** `余りが2円出たのに受領者が1件`\n")
    assert _missing_counterexamples(body) == []


def test_prose_counterexamples_count_too():
    """Backticks or not, it passes where the substance is written."""
    body = ("- **placebo:** 常に空配列を返す実装\n"
            "- **null:** 余りの行方が記録されない出力\n")
    assert _missing_counterexamples(body) == []


def test_template_counterexamples_do_not_count():
    body = "- **placebo:** `<例: ...>`\n- **null:** `<例: ...>`\n"
    assert _missing_counterexamples(body) == ["placebo", "null"]


def test_one_sided_counterexample_reports_the_other():
    assert _missing_counterexamples("- **placebo:** `常に空配列を返す`\n") == ["null"]


def test_explanatory_quote_block_is_not_an_instance():
    """The template's own commentary (`> - **placebo:** …`) does not count as substance."""
    assert _missing_counterexamples("> - **placebo:** これは説明であって実体ではない\n") == [
        "placebo", "null"]


def test_missing_counterexamples_on_empty_body():
    assert sorted(_missing_counterexamples("")) == ["null", "placebo"]
    assert sorted(_missing_counterexamples(None)) == ["null", "placebo"]
