"""split-check's EARS check — stop prose acceptance criteria at the moment the Issue is raised.

## Why this is load-bearing (from the field)

With prose acceptance criteria, the gate starts each round by designing how to confirm them, and
the standard drifts round to round. In the field, #170 was raised with 9 of 10 acceptance criteria
in prose and ran **12 rounds** (12 CI runs, 12 judgments). `org-decompose.md` also records that
"the rework of the last six rounds became work corresponding to no MUST on the Issue".
**A check that let it through was the entrance to a loop that would not converge.**

The old implementation looked for `"IF "` and the like anywhere in the body, so a wholly prose set
of acceptance criteria still slipped past on an "IF ANY" in another section, an `if` in a code
block, or a SQL `WHERE`. This guards against that regression.
"""
import sys

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from ghsync.backlog import _has_dod_command, _non_ears_acceptance  # noqa: E402


# ── the shapes that used to slip through (the old implementation's bug) ─────
def test_prose_acceptance_is_flagged_even_when_body_mentions_if_elsewhere():
    """The acceptance criteria are prose. An "IF ANY" in another section must not let it pass."""
    body = ("## Acceptance\n"
            "1. The trace is derivable from the domain decision.\n"
            "2. Zero recipients are retained faithfully.\n\n"
            "## Notes\nSee RFC IF ANY are pending.\n")
    assert len(_non_ears_acceptance(body)) == 2


def test_prose_acceptance_is_flagged_even_when_code_block_has_where():
    """A SQL `WHERE` inside a code block is never evidence of EARS."""
    body = ("## Acceptance\n- auth works\n- it should be fast\n"
            "```sql\nWHERE id = 1\n```\n")
    assert len(_non_ears_acceptance(body)) == 2


# ── do not false-positive on something written correctly (a false positive is
# ── itself a harm) ──────────────────────────────────────────────────────────
def test_ears_english_passes():
    body = ("## Acceptance\n"
            "- WHEN a user submits the invite link twice THE system SHALL create exactly one membership\n"
            "- IF an 11th member joins THEN THE system SHALL reject with a cap error\n")
    assert _non_ears_acceptance(body) == []


def test_ears_japanese_passes():
    """A Japanese equivalent of shall (〜こと / しなければならない) passes as EARS too.

    The body below is a fixture, not source language: it exists to prove the Japanese form is
    recognised, so translating it would delete the thing under test."""
    body = ("## 受け入れ基準\n"
            "- 招待リンクを二度押したとき、メンバーシップを1件だけ作成すること\n"
            "- 11人目が参加した場合、上限エラーで拒否すること\n")
    assert _non_ears_acceptance(body) == []


# ── boundaries ──────────────────────────────────────────────────────────────
def test_no_acceptance_section_is_not_flagged():
    """An Issue with no acceptance section is not rejected here (that is another check's job)."""
    assert _non_ears_acceptance("## Goal\nMake it better.\n") == []
    assert _non_ears_acceptance("") == []
    assert _non_ears_acceptance(None) == []


def test_seam_contract_metadata_is_not_treated_as_acceptance():
    """`owns:` / `depends_on:` are the seam contract's metadata lines, not requirement statements.

    Count them as requirements and **the better-written a SPEC is, the more violations it has** (it
    actually broke three existing tests). In SPEC.md they sit in the same bullet list as the MUST
    section.
    """
    body = ("## MUST\n- [ ] WHEN login THE system SHALL validate\n"
            "- **owns:** `app/auth/`\n"
            "- **depends_on:** なし。実装コードは1行も入らない\n")
    assert _non_ears_acceptance(body) == []


def test_dod_command_detected_in_both_languages():
    """The target the gate runs. With one, no method of confirmation has to be designed: the
    judgment is faster and the standard is fixed."""
    assert _has_dod_command(
        "- **DoD command (run this to know you're done):** `cd app && npm test -- expense`\n")
    assert _has_dod_command("- **完了の判定:** `python3 -m pytest tests/ -q` が緑なら完了\n")


def test_unfilled_template_placeholder_is_not_a_dod_command():
    """An unfilled template blank is never counted as "present" — that is the most dangerous
    misreading of the lot."""
    assert not _has_dod_command(
        "- **DoD command:** `<the exact command whose green output = these MUSTs>`\n")


def test_missing_dod_section_is_reported():
    assert not _has_dod_command("## Acceptance\n- WHEN x THE system SHALL y\n")
    assert not _has_dod_command("")


def test_mixed_section_reports_only_the_prose_lines():
    """Where EARS and prose are mixed, return **only the prose lines**."""
    body = ("## Acceptance\n"
            "- WHEN the cap is reached THE system SHALL reject the 11th join\n"
            "- it should be fast\n")
    bad = _non_ears_acceptance(body)
    assert len(bad) == 1 and "fast" in bad[0]
