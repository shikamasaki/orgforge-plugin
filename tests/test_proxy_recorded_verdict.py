"""Proxy-recording a verdict does not make the recorder its decision principal.

When a judge is unavailable, a supervisor records the outcome on its behalf. `decision_by` used to
fall back to the RECORDER, so that supervisor became the decision principal of a verdict it did not
make. The ledger then refused the same supervisor's correction of it as self-correction — correct
in itself — and in an org whose constitution declares a single correction authority there was
nobody else to ask. The recovery path documented in #186 existed and could not complete.

Measured on tatekae: `verdict_provisional` seq 3706, issue 168, role gate, lineage cross-harness,
`decision_by: supervisor`, correction refused with "the judgment's decision principal 'supervisor'
cannot correct".

The judging ROLE is the right fallback: `gate` judged it, the supervisor only wrote it down.
`recorded_by` still carries who typed the command, and an unreceipted verdict stays
`identity_assurance: claimed` — nothing is upgraded by this.
"""
import re

from conftest import TOOLS

SOURCE = (TOOLS / "ghsync" / "record.py").read_text(encoding="utf-8")


def _fallback_expression():
    m = re.search(r'"decision_by":\s*(.+?),\n', SOURCE)
    assert m, "the decision_by assignment moved; this test needs updating"
    return m.group(1)


def test_the_fallback_is_the_judging_role_not_the_recorder():
    """`a.by` is the recorder. Falling back to it is what created the deadlock."""
    expr = _fallback_expression()
    assert "a.role" in expr
    assert "a.by" not in expr, (
        "decision_by must not fall back to the recorder: a supervisor proxy-recording an "
        "unavailable judge would become the decision principal and could no longer correct it."
    )


def test_a_receipt_still_wins_over_the_fallback():
    """The verified principal is authoritative; the fallback only fills an unreceipted record."""
    expr = _fallback_expression()
    assert expr.startswith("decision_by or"), (
        "a verified receipt must take precedence over any fallback"
    )


def test_the_recorder_is_still_captured_separately():
    """Losing the proxy recorder's identity would trade one gap for another."""
    assert '"recorded_by": recorded_by' in SOURCE
    assert "observed_recorder()" in SOURCE


def test_an_unreceipted_verdict_is_not_upgraded():
    """The fallback fills a name, not a level of assurance."""
    assert '"identity_assurance": ident.get("identity_assurance", "claimed")' in SOURCE


def test_the_separation_the_ledger_depends_on_is_documented_here():
    """The next reader has to know why this line is not simply `a.by or a.role`."""
    block = SOURCE[:SOURCE.index('"decision_by": decision_by')]
    block = block[block.rindex("# **Three principals, kept apart (H1)."):]
    assert "self-correction" in block
    assert "#186" in block
