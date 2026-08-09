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

~6,500 lines were Japanese when this test went in, and translating them in one pass would have been
a large, unreviewable diff that risked dropping the measured findings the comments carry ("measured
1.90s → 0.24s", "12 rounds on issue #170"). Those numbers are the reason those lines exist.

So this pins the CURRENT counts as a ceiling. Translating lowers a budget; adding new Japanese
raises it and fails. When a file reaches zero, delete its entry — a file absent from the budget is
not allowed to regress.

## What the remaining budget is

The prose is done. What is left is **input**, not output: patterns and fixtures the tools MATCH
against, where Japanese is the thing being recognised.

  - `drift.py`, `rederivability.py`, `judge.py`, `lens.py`, `inspect.py`, `record.py` — regexes and
    vocabularies that read an agent's or a supervisor's own Japanese prose. `record.py`'s qualifier
    table is the clearest case: it exists to notice that a maker wrote 「存在せず」 and the
    supervisor's summary dropped it.
  - `req_lint.py`, `backlog.py`, `template/REQUIREMENTS.md` — the banned-word and EARS vocabularies,
    and the SPEC headings, that read requirements written in Japanese.
  - `org_hook.py` — the `独立:` spawn declaration, alongside `INDEPENDENT:`.
  - the test files — fixtures feeding those matchers. An English fixture there tests nothing.
  - `template/SPEC.md` — the fill-in examples, which exist to show content written in an org's own
    `output_language`.

An empty dict is therefore NOT the end state. Translating any of these would delete a capability.
If one of these counts drops, check that a matcher was not removed with it.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
JAPANESE = re.compile(r"[ぁ-んァ-ヶ一-龠]")

# Directories subject to the rule. `integrations/*/tools`, `integrations/*/scripts`,
# `integrations/*/template` and `integrations/*/commands` are build.sh copies of these, so checking
# the source is enough — test_bundle_* already fails on drift between them.
#
# `template/` and the Claude commands are in scope because they ship WITH the plugin: a slash
# command is this repository's own instruction to an agent, and a template's comments explain to a
# founder why a field exists. Neither is what an org writes for its humans, which is the surface
# output_language governs. The commands are authored under integrations/claude-code/, not generated.
ROOTS = ("tools", "tests", "integrations/common", "template",
         "integrations/claude-code/commands")

# The remaining floor, measured 2026-08-09. Every entry is a matcher or a fixture (see the module
# docstring), not untranslated prose. Never raise one; lowering one means a pattern was removed, so
# check that on purpose. A file that is not listed here must contain no Japanese at all.
BUDGET = {
    "integrations/common/org_hook.py": 1,
    "template/REQUIREMENTS.md": 9,
    "template/SPEC.md": 15,
    "tests/test_domain_surface.py": 18,
    "tests/test_ears_acceptance.py": 6,
    "tests/test_github_sync.py": 62,
    "tests/test_hook.py": 1,
    "tests/test_ledger.py": 1,
    "tests/test_organ_unit.py": 2,
    "tests/test_orgcycle.py": 48,
    "tests/test_rederivability.py": 1,
    "tests/test_req_lint.py": 30,
    "tests/test_source_language.py": 3,
    "tests/test_supersede_recovery.py": 1,
    "tools/drift.py": 11,
    "tools/ghsync/backlog.py": 20,
    "tools/ghsync/record.py": 9,
    "tools/orgcycle/inspect.py": 3,
    "tools/orgcycle/judge.py": 2,
    "tools/orgcycle/lens.py": 1,
    "tools/orgcycle/rederivability.py": 9,
    "tools/req_lint.py": 28,
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
        # Shell is source too. The ratchet scanned only *.py, so 369 Japanese lines in the writer
        # installer and verifier went uncounted while the budget read as though they did not exist.
        # The same held for the shipped templates and slash commands (*.md, *.yaml, *.json).
        for pattern in ("*.py", "*.sh", "*.md", "*.yaml", "*.json"):
            for path in sorted(base.rglob(pattern)):
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
