"""An unchanged review subject is not judged twice.

`review_subject_id` is a digest of (issue, role, phase, integration_ref, tree). An equal id means
the judge would be looking at the revision it already judged, so re-dispatching spends a judge run
(~100s measured) and, on the maker side, a CI round, to re-derive a verdict that is already
recorded. Issue #170 ran 12 CI rounds at a ~5.7 min median — roughly 68 minutes on one Issue.

What this must NOT do is suppress the independent review itself (Issue #182). A different
revision, a different role, or a first-ever review all still dispatch, and `--force` overrides
deliberately. The suppression is of repetition, not of scrutiny.
"""
import sys

import pytest

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from orgcycle import judge as J  # noqa: E402

SID = "subject-abc123"
OTHER = "subject-def456"


def _events(monkeypatch, rows, voided=()):
    monkeypatch.setattr(J, "_events_for", lambda issue: (rows, set(voided)))


def _decision(sid, verdict="reject", seq=7, cls="admission_decided", actor="gate"):
    return {"seq": seq, "class": cls, "actor": actor,
            "payload": {"review_subject_id": sid, "verdict": verdict,
                        "why": "the DoD command was never run", "risk": "none stated"}}


# ── suppress: the same subject already has a verdict ─────────────────────────
def test_a_recorded_verdict_for_the_same_subject_is_returned(monkeypatch):
    _events(monkeypatch, [_decision(SID)])
    prior = J._prior_verdict_for_subject(1, "gate", SID)
    assert prior and prior["verdict"] == "reject" and prior["seq"] == 7


def test_the_latest_verdict_wins_when_a_subject_was_judged_more_than_once(monkeypatch):
    _events(monkeypatch, [_decision(SID, "reject", 7), _decision(SID, "admit", 9)])
    assert J._prior_verdict_for_subject(1, "gate", SID)["verdict"] == "admit"


# ── do not suppress: anything a verdict could depend on differs ──────────────
def test_a_different_subject_still_dispatches(monkeypatch):
    """A new revision is a new question, however similar it looks."""
    _events(monkeypatch, [_decision(OTHER)])
    assert J._prior_verdict_for_subject(1, "gate", SID) is None


def test_the_other_role_still_dispatches(monkeypatch):
    """A gate admission must never stand in for the skeptic's refutation attempt."""
    _events(monkeypatch, [_decision(SID, "admit", 7, "admission_decided", "gate")])
    assert J._prior_verdict_for_subject(1, "skeptic", SID) is None


def test_a_first_review_dispatches(monkeypatch):
    _events(monkeypatch, [])
    assert J._prior_verdict_for_subject(1, "gate", SID) is None


def test_a_voided_verdict_does_not_suppress(monkeypatch):
    """A corrected judgment was withdrawn; it cannot stand in for a review."""
    _events(monkeypatch, [_decision(SID, "admit", 7)], voided=[7])
    assert J._prior_verdict_for_subject(1, "gate", SID) is None


def test_unreadable_history_does_not_suppress(monkeypatch):
    """If the ledger cannot be read, review — never skip on an unknown."""
    def _boom(_issue):
        raise OSError("ledger unreadable")
    monkeypatch.setattr(J, "_events_for", _boom)
    assert J._prior_verdict_for_subject(1, "gate", SID) is None


@pytest.mark.parametrize("sid", [None, ""])
def test_a_missing_subject_id_does_not_suppress(monkeypatch, sid):
    _events(monkeypatch, [_decision(SID)])
    assert J._prior_verdict_for_subject(1, "gate", sid) is None


def test_an_unknown_role_does_not_suppress(monkeypatch):
    _events(monkeypatch, [_decision(SID)])
    assert J._prior_verdict_for_subject(1, "maker", SID) is None


def test_the_skeptic_reads_its_own_event_class(monkeypatch):
    _events(monkeypatch, [_decision(SID, "survives", 11, "refutation_attempted", "skeptic")])
    prior = J._prior_verdict_for_subject(1, "skeptic", SID)
    assert prior and prior["verdict"] == "survives"


def test_force_is_declared_on_the_cli():
    """The override has to exist, or a deliberate re-review is impossible."""
    import subprocess
    r = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify", "--help"],
                       capture_output=True, text=True, timeout=60)
    assert "--force" in r.stdout
