"""A judge is handed the Issue's contract; a maker is handed the org's doctrine.

Doctrine is standing organization-wide knowledge. A judge's bar is the Issue in front of it — its
acceptance criteria, the changed seam, the declared DoD, the submitted evidence, the recorded
residual risk. Handing a judge the org's accumulated lessons turns a bounded admission check into
open-ended research: the bar moves between rounds, and findings accumulate that no MUST in the
Issue asked for. Issue #181.

A maker keeps its brain. A maker BUILDS, and prior lessons are what stop it rebuilding a known
mistake — the field note behind doctrine is a failure repeated three times. Only the checking roles
are scoped down.

This bounds the judge's INPUT and never its judgment (docs/03 §6.5): it still decides the verdict,
it just decides against the contract it was handed.
"""
import subprocess
import sys

import pytest

from conftest import TOOLS

HANDOFF = str(TOOLS / "handoff.py")
BRAIN = "## Your brain (doctrine scoped to your slice)"
BAR = "## Your bar (this Issue only"


def _handoff(role):
    r = subprocess.run(
        [sys.executable, HANDOFF, role, "--slice", "the slice", "--inputs", "in",
         "--outputs", "out", "--owns", "src/", "--forbid", "elsewhere"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.mark.parametrize("role", ["gate", "skeptic"])
def test_a_judge_is_given_a_bar_not_a_brain(role):
    out = _handoff(role)
    assert BRAIN not in out, f"{role} was handed org-wide doctrine"
    assert BAR in out


@pytest.mark.parametrize("role", ["gate", "skeptic"])
def test_the_bar_names_what_may_and_may_not_block(role):
    """The scope has to be actionable, or the judge substitutes its own."""
    out = _handoff(role)
    for expected in ("acceptance criteria", "seam", "DoD", "evidence", "residual risk"):
        assert expected in out, f"{role}'s bar does not name {expected!r}"
    assert "out_of_scope" in out
    # Narrowing scope must not become a way to wave through a genuine defect.
    for escape in ("safety", "data-integrity", "security", "release-blocking"):
        assert escape in out, f"{role}'s bar drops the {escape!r} exception"


@pytest.mark.parametrize("role", ["flow-makers", "eng", "registrar"])
def test_a_non_judge_still_receives_its_doctrine(role):
    """Scoping down the checkers must not silently strip every role's accumulated lessons."""
    out = _handoff(role)
    assert BRAIN in out, f"{role} lost its doctrine"
    assert BAR not in out


def test_the_boundary_contract_survives_for_both_kinds():
    """Whatever changes above, the seam contract itself is what makes parallel work safe."""
    for role in ("gate", "flow-makers"):
        out = _handoff(role)
        assert "Boundary contract" in out
        assert "Inputs you receive" in out and "You own" in out
