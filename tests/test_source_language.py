"""Source comments, docstrings and printed messages are written in English.

## Why this is a test and not just a note in AGENTS.md

A guardrail that blocks an action explains *why* in that message. A reader who cannot read the
explanation cannot comply. The PreToolUse hook alone carried 437 lines of Japanese, so an
English-speaking operator hit a wall of text they could not act on — the guardrail was technically
working and practically useless.

`constitution.yaml: output_language` is a **different surface**: it governs what an *org* writes
for its humans (Issue bodies, work-log comments, status boards), and `ja` is valid there. That
setting was repeatedly mistaken for permission to write this repository's own source in Japanese,
which is how the debt accumulated. A written rule did not stop it; a failing test does.

## Ratchet, not a cliff

~6,500 lines are still Japanese, and translating them in one pass would be a large, unreviewable
diff that risks dropping the measured findings the comments carry ("measured 1.90s → 0.24s",
"12 rounds on issue #170"). Those numbers are the reason those lines exist.

So this pins the CURRENT counts as a ceiling. Translating lowers a budget; adding new Japanese
raises it and fails. When a file reaches zero, delete its entry — the empty-dict end state is the
goal, and a file absent from the budget is not allowed to regress.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
JAPANESE = re.compile(r"[ぁ-んァ-ヶ一-龠]")

# Directories whose Python sources are subject to the rule. `integrations/*/tools` and
# `integrations/*/scripts` are build.sh copies of these, so checking the source is enough.
ROOTS = ("tools", "tests", "integrations/common")

# Remaining debt, measured 2026-08-08. Lower these as files are translated; never raise one.
# A file that is not listed here must contain no Japanese at all.
BUDGET = {
    "tools/ledger.py": 135,
    "tests/test_ledger.py": 670,
    "tests/test_orgcycle.py": 589,
    "tests/test_hook.py": 447,
    "tools/orgcycle/judge.py": 373,
    "integrations/common/org_hook.py": 1,
    "tools/writerd.py": 286,
    "tools/ghsync/record.py": 268,
    "tools/ghsync/backlog.py": 226,
    "tests/test_github_sync.py": 176,
    "tools/orgcycle/_core.py": 159,
    "tools/identity.py": 143,
    "tools/req_lint.py": 134,
    "tools/orgcycle/ship.py": 127,
    "tools/orgcycle/inspect.py": 109,
    "tools/orgcycle/cycle.py": 108,
    "tools/org_cycle.py": 99,
    "tools/orgcycle/lens.py": 79,
    "tools/github_sync.py": 70,
    "tools/drift.py": 69,
    "tools/orgcycle/rederivability.py": 67,
    "tools/learning.py": 66,
    "tests/test_learning.py": 63,
    "tests/test_req_lint.py": 61,
    "tools/orgcycle/mcp_judge.py": 55,
    "tests/test_organs.py": 54,
    "tools/ghsync/branch.py": 50,
    "tests/test_domain_surface.py": 46,
    "tools/status.py": 44,
    "tests/conftest.py": 30,
    "tests/test_rederivability.py": 29,
    "tools/repro_lint.py": 26,
    "tests/test_ears_acceptance.py": 26,
    "tools/org_lint.py": 24,
    "tools/doctrine.py": 20,
    "tools/orgcycle/preflight.py": 19,
    "tools/review_freshness.py": 18,
    "tests/test_repro_lint.py": 16,
    "tests/test_status.py": 15,
    "tools/ghsync/_core.py": 11,
    "tools/harness.py": 11,
    "tools/conventions.py": 10,
    "tools/organ_binding.py": 10,
    "tools/discover.py": 9,
    "tools/writer_client.py": 8,
    "tools/guardrails.py": 7,
    "tests/test_organ_binding.py": 6,
    "tools/handoff.py": 5,
    "tools/reconcile.py": 4,
    "tools/alignment.py": 3,
    "tools/resource.py": 3,
    "tools/resilience_exercise.py": 2,
    "tests/test_organ_unit.py": 2,
    "tests/test_review_freshness.py": 2,
    "tools/attention.py": 1,
    "tools/ghsync/coverage.py": 1,
    "tools/sensors.py": 1,
    "tools/tick.py": 1,
    "tests/test_proxy_recorded_verdict.py": 1,
    "tests/test_resilience_exercise.py": 1,
    "tests/test_source_language.py": 1,
    "tests/test_supersede_recovery.py": 1,
}


def _japanese_lines(path):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    return sum(1 for line in text.split("\n") if JAPANESE.search(line))


def _sources():
    for root in ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            yield path.relative_to(REPO).as_posix(), path


def test_no_new_japanese_in_source():
    """A file may hold no more Japanese than its recorded budget, and unlisted files hold none."""
    over = []
    for rel, path in _sources():
        count = _japanese_lines(path)
        allowed = BUDGET.get(rel, 0)
        if count > allowed:
            over.append(f"{rel}: {count} Japanese lines > budget {allowed}")
    assert not over, (
        "Japanese in source grew. Comments, docstrings and printed messages go in English "
        "(AGENTS.md): a guardrail's reason has to be readable by whoever it blocks.\n  "
        + "\n  ".join(over)
        + "\n\nNote: constitution.yaml's output_language governs what an ORG writes for its "
          "humans, not this repository's own source."
    )


def test_budget_entries_are_not_stale():
    """A budget far above the real count hides regressions; a file at zero should be removed."""
    stale = []
    for rel, allowed in sorted(BUDGET.items()):
        path = REPO / rel
        if not path.exists():
            stale.append(f"{rel}: listed in BUDGET but does not exist")
            continue
        count = _japanese_lines(path)
        if count == 0 and allowed > 0:
            stale.append(f"{rel}: fully translated — delete its BUDGET entry to lock it at zero")
    assert not stale, "\n  ".join(stale)


@pytest.mark.parametrize("doc", ["AGENTS.md", "CLAUDE.md"])
def test_the_rule_is_written_down_where_an_agent_will_read_it(doc):
    """The test enforces; the document explains. Both have to exist or the next contributor guesses."""
    text = (REPO / doc).read_text(encoding="utf-8")
    assert "English" in text
    assert "output_language" in text, (
        f"{doc} must name the distinction that caused the debt: output_language is the org's "
        "human-facing language, not this repository's source language."
    )
