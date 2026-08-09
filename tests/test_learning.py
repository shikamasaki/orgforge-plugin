"""learning.py repeats — detecting a recurring cause of death (Issue #104 / OBS-052).

In the field (Tatekae) failures with the same root were recorded in different words, and a detector
matching whole strings reported clean three times running. The fix: classify with the closed
vocabulary `root` at recording time, and count recurrence by matching roots. A legacy record with no
root still matches whole strings as before (backward compatible).
"""
import json
import sys

import yaml

from conftest import TOOLS, TEMPLATE, run, seed

sys.path.insert(0, str(TOOLS))
import learning  # noqa: E402


# ── MUST 3(a): different wording, same root → detected as a recurrence (never called clean) ──
def test_same_root_different_wording_detected(tmp_path):
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "the rounding bias is not verified",
          "root": "placebo_test"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "test hardening (the fixture bypasses the real path)",
          "root": "placebo_test"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 10, f"it missed two same-root deaths worded differently: {out}"
    assert "REPEATED DEATH" in out and "placebo_test" in out
    assert "clean" not in out


def test_distinct_roots_stay_clean_with_basis(tmp_path):
    # Different roots are not a recurrence. clean states the basis (n classified by root, m by
    # string match).
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "x", "root": "placebo_test"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "y", "root": "declaration_drift"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, out
    assert "decided on:" in out and "2 by" in out, out


# ── MUST 3(b) / MUST 2: a legacy record with no root matches strings, and states the basis ──
def test_legacy_unclassified_falls_back_to_exact_string(tmp_path):
    # An identical string is still detected, as before
    for cid, ts in (("A", "2026-07-16T01:00:00Z"), ("B", "2026-07-16T02:00:00Z")):
        seed(tmp_path, "gate", "result_retired",
             {"candidate_id": cid, "cause": "null hypothesis not rejected"}, ts=ts)
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 10 and "REPEATED DEATH" in out, out


def test_legacy_unclassified_clean_states_basis_and_limitation(tmp_path):
    # Different wording with no root → it walks past as before (backward compatible), but clean
    # states (1) the basis and how many are unclassified, and (2) the limits of string matching.
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "rounding bias"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "test hardening"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, out
    assert "decided on:" in out and "unclassified" in out and "2 by" in out, out
    assert "**string**" in out, f"the statement of the string-match limit is gone: {out}"


def test_mixed_clean_reports_unclassified_count(tmp_path):
    # One classified, one unclassified, no recurrence → clean, but the unclassified count is
    # readable (root=other is not a discriminating root, so it does not count as "classified" —
    # a discriminating root is used)
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "x", "root": "declaration_drift"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "y"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, out
    assert "1 by root classification" in out and "1 by" in out, out


# ── MUST 3(c): an invalid root is refused at recording time (the schema enum, ledger.py append) ──
def test_invalid_root_rejected_at_record_time(tmp_path):
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "gate",
                    "--class", "result_retired",
                    "--payload", json.dumps({"candidate_id": "A", "cause": "x",
                                             "root": "test_flaky"}))
    assert code != 0, "an invalid root could be recorded"
    assert "root" in out and "is not an allowed value" in out, out


def test_valid_root_accepted_and_stored(tmp_path):
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "x", "root": "integration_base_moved"})
    text = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    rec = [json.loads(l) for l in text.splitlines() if l][-1]
    assert rec["payload"]["root"] == "integration_base_moved"


# ── one vocabulary: learning.DEATH_ROOTS and the schema enum are identical (drift = the check
#    lying) ──
def test_vocabulary_matches_schema_enum():
    doc = yaml.safe_load((TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"))
    enums = doc["validation"]["enums"]
    expected = set(learning.DEATH_ROOTS)
    assert {"placebo_test", "declaration_drift", "integration_base_moved",
            "self_written_premise", "other"} == expected
    for cls in ("result_retired", "rework_requested", "refutation_attempted"):
        assert set(enums[cls]["root"]) == expected, \
            f"{cls}'s root enum has drifted from learning.DEATH_ROOTS: {enums.get(cls)}"


def test_death_roots_have_ja_descriptions():
    for k, v in learning.DEATH_ROOTS.items():
        assert isinstance(v, str) and v.strip(), f"{k} has no explanation"


# ── REWORK (raised by the gate): `other` cannot claim "the roots are the same" ──────────
def test_two_unrelated_other_records_do_not_escalate_as_same_root(tmp_path):
    """`other` is not a discriminating root — two unrelated deaths both being `other` must never
    escalate as "the wording differs but the root is the same" (that fabricates a semantic match
    nobody recorded, and trains people to ignore the escalation channel).
    Choice (a): `other` falls back to string matching and never forms a root recurrence group on its
    own."""
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "a licensing problem in a dependency",
          "root": "other"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "the customer withdrew the requirement",
          "root": "other"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, \
        f"it escalated two unrelated others as \"the same root\": {out}"
    assert "REPEATED DEATH" not in out


def test_same_string_other_records_still_detected(tmp_path):
    # The string match it falls back to is alive: other + identical wording → detected
    for cid, ts in (("A", "2026-07-16T01:00:00Z"), ("B", "2026-07-16T02:00:00Z")):
        seed(tmp_path, "gate", "result_retired",
             {"candidate_id": cid, "cause": "the same cause of death", "root": "other"}, ts=ts)
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 10 and "REPEATED DEATH" in out, out


# ═══ REWORK #2 (raised by the skeptic: the fix lay dormant — the real writers could not carry
#     root) ═══
import argparse
import importlib
import os
import subprocess


def _mod(name):
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    return importlib.import_module(name)


# ── change 1a: org_cycle rework carries --root through to the ledger payload ────────────
def test_org_cycle_rework_carries_root_into_payload(monkeypatch):
    m = _mod("orgcycle.judge")
    calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: (calls.append(("gh",) + a) or (0, "ok")))
    monkeypatch.setattr(m, "_ledger", lambda *a: (calls.append(("ledger",) + a) or (0, "ok")))
    ns = argparse.Namespace(issue=32, after="refuted", by="supervisor",
                            reason="fix the placebo test", to="maker", round=2,
                            root="placebo_test")
    assert m.cmd_rework(ns) == 0
    led = [c for c in calls if c[0] == "ledger"][0]
    payload = json.loads(led[led.index("--payload") + 1])
    assert payload.get("root") == "placebo_test", payload


def test_org_cycle_rework_rejects_unknown_root(monkeypatch, capsys):
    m = _mod("orgcycle.judge")
    calls = []
    monkeypatch.setattr(m, "_gh_sync", lambda *a: (calls.append(("gh",) + a) or (0, "ok")))
    monkeypatch.setattr(m, "_ledger", lambda *a: (calls.append(("ledger",) + a) or (0, "ok")))
    ns = argparse.Namespace(issue=32, after="refuted", by="supervisor",
                            reason="x", to="maker", round=2, root="totally_made_up_root")
    rc = m.cmd_rework(ns)
    out = capsys.readouterr()
    assert rc == 2, f"an unknown root was not refused (rc={rc})"
    assert not calls, "it refused, yet a side effect (gh/ledger) ran"
    assert "placebo_test" in out.err + out.out, "the list of permitted values is not printed"


def test_org_cycle_rework_help_offers_root():
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "rework", "--help"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and "--root" in p.stdout, p.stdout + p.stderr


# ── change 1b: github_sync decide carries --root through to the ledger payload ───────────
def _decide_ns(**kw):
    base = dict(repo="o/r", issue=5, event="refutation_attempted", verdict="refuted",
                why="the skeleton's check goes through a fixture and bypasses the real path, so it "
                    "does not measure where the property breaks.",
                by="skeptic", phase=None, evidence=None, alternatives=None,
                standard=None, risk=None, event_id="ev-r1", lineage=None,
                claimed=None, verified=None, root=None)
    base.update(kw)
    return argparse.Namespace(**base)


def _fake_gh(posted):
    def gh(args, check=True):
        if args[:2] == ["issue", "view"]:
            return 0, json.dumps({"comments": [{"body": b} for b in posted]})
        if args[:2] == ["issue", "comment"]:
            posted.append(args[args.index("--body") + 1])
            return 0, "ok"
        return 0, ""
    return gh


def test_github_sync_decide_carries_root_into_payload(monkeypatch, tmp_path):
    rec = _mod("ghsync.record")
    posted = []
    monkeypatch.setattr(rec, "gh", _fake_gh(posted))
    led = tmp_path / "led"
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    rc = rec.cmd_decide(_decide_ns(root="placebo_test"))
    assert rc == 0, rc
    rows = [json.loads(l) for l in
            (led / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if l]
    ev = [r for r in rows if r["class"] == "refutation_attempted"][-1]
    assert ev["payload"].get("root") == "placebo_test", ev["payload"]


def test_github_sync_decide_rejects_unknown_root(monkeypatch, tmp_path, capsys):
    rec = _mod("ghsync.record")
    posted = []
    monkeypatch.setattr(rec, "gh", _fake_gh(posted))
    led = tmp_path / "led"
    monkeypatch.setenv("ORG_LEDGER_ROOT", str(led))
    rc = rec.cmd_decide(_decide_ns(root="totally_made_up_root"))
    out = capsys.readouterr()
    assert rc == 2, f"an unknown root was not refused (rc={rc})"
    assert not posted and not (led / "ledger.jsonl").exists(), \
        "it refused, yet wrote to the Issue / the ledger"
    assert "placebo_test" in out.err + out.out, "the list of permitted values is not printed"


def test_github_sync_decide_help_offers_root():
    p = subprocess.run([sys.executable, str(TOOLS / "github_sync.py"), "decide", "--help"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and "--root" in p.stdout, p.stdout + p.stderr


# ── change 2 (M4): the limits warning does not vanish during migration (printed at
#    unclassified >= 1) ──
def test_limitation_warning_survives_migration_mix(tmp_path):
    """skeptic lab2: one classified and one unclassified (the same root, but one carries no root) →
    it stays clean, yet the warning about the limits of string matching **must keep appearing**. If
    the warning vanishes during migration, an unclassified death silently looks clean even when it
    is a recurrence of the same root."""
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "the check does not measure the real path",
          "root": "placebo_test"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "test hardening (same root, no root field)"},
         ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, out
    assert "note:" in out and "**string**" in out, \
        f"the limits warning vanished during migration (one unclassified): {out}"


# ── change 3 (M5): a root outside the vocabulary does not fabricate a recurrence (a value
#    writable only through the old schema) ──
def test_unknown_root_string_does_not_fabricate_recurrence(tmp_path):
    """skeptic lab4: an unknown root string, writable only under the old schema that has no enum
    (equivalent to main), must never form a root group — escalating "the root is the same" merely
    because two unrelated deaths share `totally_made_up_root` fabricates a recurrence. It falls back
    to string matching."""
    old_schema = tmp_path / "old-schema.yaml"
    # The shape on main (before #104): result_retired is declared, but there is no root enum
    old_schema.write_text(
        "event_classes:\n"
        "  result_retired: {candidate_id, cause, observed_outcome, root}\n"
        "validation: {}\n", encoding="utf-8")
    env = {**os.environ, "ORG_LEDGER_SCHEMA": str(old_schema)}
    for cid, cause, ts in (("A", "a dependency licensing problem", "2026-07-16T01:00:00Z"),
                           ("B", "the customer withdrew the requirement",
                            "2026-07-16T02:00:00Z")):
        p = subprocess.run(
            [sys.executable, str(TOOLS / "ledger.py"), "append", str(tmp_path),
             "--actor", "gate", "--class", "result_retired", "--ts", ts,
             "--payload", json.dumps({"candidate_id": cid, "cause": cause,
                                      "root": "totally_made_up_root"})],
            capture_output=True, text=True, timeout=60, env=env)
        assert p.returncode == 0, p.stdout + p.stderr
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out, \
        f"it escalated a recurrence from a shared out-of-vocabulary root string: {out}"
    assert "REPEATED DEATH" not in out


def test_profile_preserves_everyday_success_and_wad_unknowns(tmp_path):
    seed(tmp_path, "gate", "cycle_completed",
         {"candidate_id": "A", "role": "gate", "outputs": []},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "rework_requested",
         {"candidate_id": "A", "reason": "near miss"},
         ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "profile", str(tmp_path))
    assert code == 0, out
    profile = json.loads(out)
    assert profile["observation_taxonomy"]["everyday_success"] == 1
    assert profile["observation_taxonomy"]["failure"] == 1
    assert profile["inferred_wad"]["status"] == "not_inferred"
    assert profile["inferred_wad"]["confidence"] == "unknown"
    assert profile["learning_candidates"] == []
    assert profile["doctrine_mutated"] is False
    assert profile["resilience_score"] is None
