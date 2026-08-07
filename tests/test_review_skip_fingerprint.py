"""A re-review is earned by new evidence or a changed residual risk, not only by a new commit.

2.7.0 suppressed a repeat when `review_subject_id` matched, and its refusal told the caller that
changing the head, the cited evidence, or the stated residual risk would earn another review. Only
the first was true: `SUBJECT_FIELDS` digests the revision (tree, head, integration ref) and carries
neither evidence nor risk, so re-submitting with real DoD output against an unchanged tree was
silently skipped (#193).

That is worse than a missing feature — the tool gave instructions that did not work, the same
failure shape as #186.

The case this protects is ordinary: the fix was already committed, so the tree is unchanged, and
what changed is that the claim is now evidenced by a command that was actually run. The earlier
verdict was reached without that evidence and must not stand in for a review of it.
"""
import sys

import pytest

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from orgcycle import judge as J  # noqa: E402

SID = "subject-abc123"
EV = ["npx vitest run: 41 passed"]
RISK = "the offline path is untested"


def _events(monkeypatch, rows, voided=()):
    monkeypatch.setattr(J, "_events_for", lambda issue: (rows, set(voided)))


def _decision(sid=SID, evidence=EV, risk=RISK, seq=7, verdict="reject"):
    return {"seq": seq, "class": "admission_decided", "actor": "gate",
            "payload": {"review_subject_id": sid, "verdict": verdict, "why": "w",
                        "evidence": evidence, "risk": risk}}


# ── the fingerprint itself ───────────────────────────────────────────────────
def test_identical_evidence_and_risk_produce_the_same_fingerprint():
    assert J._round_fingerprint(EV, RISK) == J._round_fingerprint(list(EV), RISK)


def test_whitespace_and_order_do_not_manufacture_a_difference():
    """Otherwise a reformatted paste would look like new evidence and cost a judge run."""
    assert J._round_fingerprint(["a  b", "c"], " r ") == J._round_fingerprint(["c", "a b"], "r")


@pytest.mark.parametrize("evidence, risk", [
    (["npx vitest run: 42 passed"], RISK),        # evidence changed
    (EV, "none remaining"),                        # risk changed
    (EV + ["and the e2e suite"], RISK),            # evidence added
])
def test_a_change_in_either_field_changes_the_fingerprint(evidence, risk):
    assert J._round_fingerprint(evidence, risk) != J._round_fingerprint(EV, RISK)


def test_absent_and_empty_are_not_silently_equal_to_content():
    assert J._round_fingerprint(None, None) != J._round_fingerprint(EV, RISK)


# ── what the prior-verdict lookup reports ────────────────────────────────────
def test_the_recorded_round_carries_its_fingerprint(monkeypatch):
    _events(monkeypatch, [_decision()])
    prior = J._prior_verdict_for_subject(1, "gate", SID)
    assert prior["fingerprint"] == J._round_fingerprint(EV, RISK)


def test_a_round_recorded_without_evidence_is_distinguishable(monkeypatch):
    """The exact regression: a verdict reached with no evidence must not absorb an evidenced one."""
    _events(monkeypatch, [_decision(evidence=None, risk=None)])
    prior = J._prior_verdict_for_subject(1, "gate", SID)
    assert prior["fingerprint"] != J._round_fingerprint(EV, RISK)


# ── the property the skip depends on ─────────────────────────────────────────
def test_same_revision_and_same_round_still_matches(monkeypatch):
    """2.7.0's case has to keep working — this is what stops the 12-round rally."""
    _events(monkeypatch, [_decision()])
    prior = J._prior_verdict_for_subject(1, "gate", SID)
    assert prior["fingerprint"] == J._round_fingerprint(EV, RISK)


def test_the_refusal_message_matches_what_the_code_compares():
    """The message promises head / evidence / risk. All three must be real, or it lies again."""
    src = (TOOLS / "orgcycle" / "judge.py").read_text(encoding="utf-8")
    block = src[src.index("already judged this exact subject"):]
    block = block[:block.index("return 0")]
    for promised in ("reviewed head", "cited evidence", "residual risk"):
        assert promised in block
    assert "_round_fingerprint" in src
    # and the skip must actually consult it
    skip = src[src.index('if not getattr(a, "force", False):'):]
    skip = skip[:skip.index("charter, cpath")]
    assert 'fingerprint' in skip and "_now_fp" in skip
