"""The board — what shows up as RED / AMBER.

In an append-only ledger, "there was an admit at some point" and "it is admitted now" are different
things."""
import argparse
import json
import os
import pathlib
import subprocess
import sys

from conftest import (REPO, TOOLS, TEMPLATE, run, seed, _cycle_src, _gh_src,
                      _cycle_mod, _propose_full, _admitted_claim, _sched,
                      _ledger_with, _led, _append, _status, _write_ledger)


def test_status_board_green_when_work_drains(tmp_path):
    seed(tmp_path, "m", "candidate_submitted",
         {"candidate_id": "A", "maker": "m", "contract_ref": "c"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "eng", "cycle_completed", {"candidate_id": "A", "role": "eng"},
         ts="2026-07-16T02:00:00Z")
    code, out = run("status.py", "status", str(tmp_path))
    assert code == 0 and out.startswith("GREEN")


def test_status_board_red_on_repeated_death(tmp_path):
    seed(tmp_path, "x", "repeated_death_detected",
         {"cause": "y", "occurrences": 2, "candidate_ids": ["A", "B"]}, ts="2026-07-16T01:00:00Z")
    code, out = run("status.py", "status", str(tmp_path))
    assert code == 0 and out.startswith("RED") and "needs you" in out


def test_status_redline_silent_on_green(tmp_path):
    seed(tmp_path, "e", "cycle_completed", {"candidate_id": "A", "role": "e"}, ts="2026-07-16T01:00:00Z")
    code, out = run("status.py", "redline", str(tmp_path))
    assert code == 0 and out.strip() == ""          # healthy → no line for the Monitor


def test_status_redline_emits_on_red(tmp_path):
    seed(tmp_path, "x", "repeated_death_detected",
         {"cause": "null", "occurrences": 2, "candidate_ids": ["A", "B"]}, ts="2026-07-16T01:00:00Z")
    code, out = run("status.py", "redline", str(tmp_path))
    assert code == 0 and out.startswith("RED — org needs you")


# ── runtime separation of duties (docs/03 §3.1, docs/11 §4f) ─────────────────
# REQUIRES_PRIOR asks whether the right events happened in the right order; it never asked WHO wrote
# them. That was survivable while a human read the diff. With human review retired the gate and skeptic
# are the only judges left, so an actor able to write its own admission IS the entire judgment layer —
# and the hash chain then LAUNDERS the forgery, since a forged verdict verifies clean.


def test_status_counts_risk_accepted_admits(tmp_path):
    """An admit carrying a risk shows on the board (so writing one is not a free pass)."""
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 8, "verdict": "admit", "risk_accepted": True}},
        {"seq": 2, "class": "refutation_attempted",
         "payload": {"issue": 8, "verdict": "survives"}},
    ])
    p = subprocess.run([sys.executable, str(TOOLS / "status.py"), "status", str(led)],
                       capture_output=True, text=True, timeout=60)
    assert "admits carrying a risk: 1" in p.stdout + p.stderr


def test_reject_after_admit_clears_the_admit(tmp_path):
    """With admit then reject, the reject holds. Never counted as "there was an admit at some
    point"."""
    led = _write_ledger(tmp_path, "s1", [
        {"seq": 216, "class": "admission_decided",
         "payload": {"issue": 11, "verdict": "admit"}},
        {"seq": 218, "class": "admission_decided",
         "payload": {"issue": 11, "verdict": "reject"}},
    ])
    out = _status(led).stdout
    assert "no skeptic record" not in out, f"still treated as admitted after the reject: {out}"
    assert "awaiting rework" in out, f"being left sitting in reject is not visible: {out}"


def test_admit_after_reject_counts_as_admit(tmp_path):
    """In the other order (reject then admit), the admit holds — the happy path where rework
    passed."""
    led = _write_ledger(tmp_path, "s2", [
        {"seq": 1, "class": "admission_decided", "payload": {"issue": 11, "verdict": "reject"}},
        {"seq": 2, "class": "admission_decided", "payload": {"issue": 11, "verdict": "admit"}},
    ])
    out = _status(led).stdout
    assert "no skeptic record" in out, f"the re-admit is not being counted as an admit: {out}"


def test_risk_accepted_admit_not_counted_after_reject(tmp_path):
    """An admit carrying a risk that was later rejected is not counted as a hole still open."""
    led = _write_ledger(tmp_path, "s3", [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 5, "verdict": "admit", "risk_accepted": True}},
        {"seq": 2, "class": "admission_decided", "payload": {"issue": 5, "verdict": "reject"}},
    ])
    out = _status(led).stdout
    assert "admits carrying a risk" not in out, out


def test_voiding_superseded_correction_removes_admit_from_redline(tmp_path):
    """The effective-event projection must honor the writer's effect, not a local kind list."""
    led = _write_ledger(tmp_path, "superseded-effect", [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 63, "verdict": "admit"}},
        {"seq": 2, "class": "correction",
         "payload": {"corrects": [1], "kind": "superseded", "effect": "voids",
                     "reason": "skeptic refuted the admitted revision"}},
    ])
    out = _status(led).stdout
    assert "no skeptic record" not in out, out


def test_legacy_superseded_correction_remains_voiding_after_schema_migration(tmp_path):
    """A v2.0.22 ledger has no effect field and must not regain a superseded admission."""
    led = _write_ledger(tmp_path, "legacy-superseded", [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 63, "verdict": "admit"}},
        {"seq": 2, "class": "correction",
         "payload": {"corrects": [1], "kind": "superseded", "reason": "legacy correction"}},
    ])
    out = _status(led).stdout
    assert "no skeptic record" not in out, out


def test_provisional_skeptic_refutation_is_not_reported_as_missing(tmp_path):
    """One strict cross-harness negative is evidence, even before a joint event exists."""
    led = _write_ledger(tmp_path, "provisional-refuted", [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 63, "verdict": "admit"}},
        {"seq": 2, "class": "verdict_provisional",
         "payload": {"issue": 63, "role": "skeptic", "lineage": "cross-harness",
                     "verdict": "refuted", "for_event": "refutation_attempted",
                     "review_subject_id": "subject-63", "reasoning_sha256": "digest-63"}},
    ])
    out = _status(led).stdout
    assert "no skeptic record" not in out, out
    assert "the skeptic refuted it" in out, out
