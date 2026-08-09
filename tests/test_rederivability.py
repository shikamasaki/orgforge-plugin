"""Detect the MUSTs a read-only judge cannot re-derive, before the judge is launched.

Two things are being protected:
  1. kill a wasted park **before** the judgment (one judge run measured 102 seconds, and a park
     produces no judgment at all)
  2. **do not judge** (docs/03 §6.5 — a forced invariant is fine; a forced judgment is the
     disappearance of judgment)
Break 2 and the tool turns the gate into a formality, so 2 is constrained structurally.
"""
import ast
import pathlib
import sys

import pytest

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from orgcycle.rederivability import advisory, unmeasurable_musts  # noqa: E402


# ── 1. collect the MUSTs that cannot be re-derived ───────────────────────────
@pytest.mark.parametrize("must, expected_reason_fragment", [
    # a genuinely mixed Japanese/English MUST, as this repo's SPECs actually are
    ("- The suite MUST pass 100回連続 green", "measuring repeated execution"),
    ("- The suite MUST pass 100 times in a row.", "measuring repeated execution"),
    # A different word order. Only the number-first form was matched, and this was missed in the
    # field (a cross-harness judge raised it on the second round as grounds for reject).
    ("- MUST run 100 times consecutively", "measuring repeated execution"),
    ("- MUST be run consecutively 100 times", "measuring repeated execution"),
    ("- MUST survive 50 consecutive runs", "measuring repeated execution"),
    ("- CI MUST be green from a clean clone", "CI"),
    ("- The implementation MUST have p99 latency under 10 ms", "measuring performance"),
    ("- The migration MUST apply to the real DB without loss", "reaching a real database"),
    ("- Every mutation test MUST be proven active", "observing a mutation"),
])
def test_musts_needing_execution_are_flagged(must, expected_reason_fragment):
    spec = "## MUST — acceptance criteria\n" + must + "\n"
    found = unmeasurable_musts(spec)
    assert len(found) == 1, f"not collected: {must}"
    assert expected_reason_fragment in found[0][1]


# ── 2. a MUST that CAN be settled statically is **not** collected (a false positive is itself
# ──    a harm) ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("must", [
    "- The identifier MUST be kebab-case",
    "- The function MUST return None on an empty input",
    "- The module MUST NOT import yaml at module level",
    "- WHEN the cap is reached, the 11th join MUST be rejected",
])
def test_statically_checkable_musts_are_not_flagged(must):
    spec = "## MUST — acceptance criteria\n" + must + "\n"
    assert unmeasurable_musts(spec) == [], f"false positive: {must}"


def test_empty_and_missing_spec_are_safe():
    assert unmeasurable_musts("") == []
    assert unmeasurable_musts(None) == []
    assert advisory([], "gate") is None


def test_advisory_names_the_cost_and_stays_advisory():
    """The advice names the time that is lost, and **never claims a verdict**."""
    found = unmeasurable_musts("## MUST\n- MUST pass 100 times in a row\n")
    text = advisory(found, "gate")
    assert "park" in text and "produces no judgment" in text   # it names what is lost
    assert "--strict-rederivability" in text                    # it shows the way out
    # The advice must not declare a verdict — the gate's verdict words are never used
    # assertively here.
    assert "the judge was not launched" not in text
    for verdict in ("admit", "reject"):
        assert f"verdict: {verdict}" not in text.lower()


# ── 3. the line not crossed: this module holds no judgment ──────────────────
def test_module_returns_no_verdict_anywhere():
    """Constrain syntactically that `admit` / `reject` are never produced **as a return value**.

    A string grep would also hit the prose in a docstring, so the AST is used to look only at what
    is actually returned. Break this and the tool starts judging in the gate's place (docs/03
    §6.5).
    """
    src = (pathlib.Path(TOOLS) / "orgcycle" / "rederivability.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    returned = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Return) and n.value is not None]
    literals = [n.value for n in ast.walk(ast.Module(body=returned, type_ignores=[]))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for lit in literals:
        assert lit.strip().lower() not in {"admit", "reject", "park", "survives", "refuted"}, \
            f"it returns a verdict word: {lit!r}"
