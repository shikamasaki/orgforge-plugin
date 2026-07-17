"""Regression net for the org organs (tools/*.py).

Written BEFORE the shared-module refactor to FREEZE current behavior. Every exit code below was
verified empirically against the tools this session; this suite must stay green through the
extraction of tools/_organ.py. It exercises the tools exactly as the real host does — as
SUBPROCESSES invoked by absolute path, keyed on exit code (the org_hook.py interface) plus a
stable output substring. Import-and-call would bypass sys.exit and miss the CLI dispatch, so we
never do that here.

Conventions:
- one tmp ledger root per test (append-only writes must not leak between tests),
- seed only through `ledger.py append` (hand-writing JSONL breaks the hash chain), except the two
  tamper tests that deliberately mutate the file on disk,
- assert exit code AND a substring of stdout+stderr combined (organs print verdicts to stderr,
  the allow path to stdout).
"""
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
TEMPLATE = REPO / "template"


def run(tool, *args, cwd=None):
    r = subprocess.run([sys.executable, str(TOOLS / tool), *args],
                       capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout + r.stderr


def seed(root, actor, cls, payload, ts="2026-07-16T00:00:00Z"):
    code, out = run("ledger.py", "append", str(root), "--actor", actor,
                    "--class", cls, "--payload", json.dumps(payload), "--ts", ts)
    assert code == 0, f"seed failed: {out}"


# ── ledger.py ────────────────────────────────────────────────────────────────
def test_ledger_chain_intact(tmp_path):
    seed(tmp_path, "a", "heartbeat", {"component": "x", "invariants_hold": True})
    code, out = run("ledger.py", "verify", str(tmp_path))
    assert code == 0 and "chain intact" in out


def test_ledger_requires_prior_orphan_deploy(tmp_path):
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "r",
                    "--class", "result_deployed",
                    "--payload", '{"candidate_id":"c1","net_effect_ref":"n"}',
                    "--ts", "2026-07-16T00:00:00Z")
    assert code == 3 and "requires a prior" in out


def test_ledger_requires_prior_refuted_not_enough(tmp_path):
    seed(tmp_path, "s", "refutation_attempted",
         {"skeptic": "s", "claim_id": "c1", "verdict": "refuted", "checklist_ref": "x"})
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "r",
                    "--class", "result_deployed",
                    "--payload", '{"candidate_id":"c1","net_effect_ref":"n"}',
                    "--ts", "2026-07-16T01:00:00Z")
    assert code == 3, out   # only verdict==survives satisfies requires_prior


def test_ledger_actor_not_from_payload(tmp_path):
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "m",
                    "--class", "cycle_completed", "--payload", '{"actor":"evil","role":"m"}')
    assert code == 2 and "must not carry its own 'actor'" in out


def test_report_up_requires_prior_conformance(tmp_path):
    # A4 (docs/14): a manager may not report subordinate work up without a prior A3 conforms —
    # the schema promised requires_prior; this pins it as actually enforced at write time.
    rp = {"supervisor": "s", "parent": "ceo", "window": "w", "basis_refs": [],
          "intent_status": "met", "exceptions": [], "exceptions_none_asserted": True,
          "decisions_needed": []}
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "s",
                    "--class", "report_up", "--payload", json.dumps(rp))
    assert code == 3 and "requires a prior" in out
    # after a conforms review by the same supervisor, report_up is valid
    seed(tmp_path, "s", "conformance_reviewed",
         {"supervisor": "s", "subordinate": "sub", "reviewed_ref": "r",
          "delegated_intent_ref": "i", "verdict": "conforms", "evidence_ref": "e"},
         ts="2026-07-16T00:01:00Z")
    rp2 = dict(rp)
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "s",
                    "--class", "report_up", "--payload", json.dumps(rp2), "--ts",
                    "2026-07-16T00:02:00Z")
    assert code == 0, out


def test_ledger_tamper_detected(tmp_path):
    seed(tmp_path, "a", "candidate_submitted",
         {"maker": "a", "candidate_id": "c1", "contract_ref": "r", "evidence": []})
    seed(tmp_path, "a", "candidate_submitted",
         {"maker": "a", "candidate_id": "c2", "contract_ref": "r", "evidence": []},
         ts="2026-07-16T00:01:00Z")
    log = tmp_path / "ledger.jsonl"
    lines = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    lines[0]["payload"]["candidate_id"] = "TAMPERED"
    log.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n")
    code, out = run("ledger.py", "verify", str(tmp_path))
    assert code == 1 and ("hash mismatch" in out or "edited" in out)


def test_ledger_seq_gap_detected(tmp_path):
    seed(tmp_path, "a", "heartbeat", {"component": "x", "invariants_hold": True})
    seed(tmp_path, "a", "heartbeat", {"component": "y", "invariants_hold": True},
         ts="2026-07-16T00:01:00Z")
    log = tmp_path / "ledger.jsonl"
    lines = log.read_text().splitlines()
    log.write_text(lines[1] + "\n")   # drop line 1 -> seq starts at 2
    code, out = run("ledger.py", "verify", str(tmp_path))
    assert code == 1 and ("seq" in out or "BROKEN" in out)


def test_ledger_malformed_line_is_broken_not_crash(tmp_path):
    # a non-JSON line IS tamper evidence; verify must report BROKEN + exit 1, never traceback
    seed(tmp_path, "a", "heartbeat", {"component": "x", "invariants_hold": True})
    (tmp_path / "ledger.jsonl").open("a").write("THIS-IS-NOT-JSON\n")
    code, out = run("ledger.py", "verify", str(tmp_path))
    assert code == 1 and "BROKEN" in out and "Traceback" not in out


def test_guardrails_cap_tolerates_ts_less_event(tmp_path):
    # an event with no 'ts' (as emit_event writes) must not KeyError when a window is set
    (tmp_path / "ledger.jsonl").write_text(json.dumps(
        {"id": "e1", "seq": 1, "class": "exposure_budget_checked",
         "payload": {"dimension": "spend", "decision": "allow", "delta_requested": 1}}) + "\n")
    code, out = run("guardrails.py", "cap", str(tmp_path), "--dimension", "spend",
                    "--delta", "1", "--cap", "5", "--actor", "x", "--window-since", "1970-01-01")
    assert code == 0 and "Traceback" not in out


def test_ledger_digest_deterministic(tmp_path):
    seed(tmp_path, "a", "candidate_submitted",
         {"maker": "a", "candidate_id": "c1", "contract_ref": "r", "evidence": []})
    args = ("digest", str(tmp_path), "--window-since", "2026-07-16T00:00:00Z",
            "--window-until", "2026-07-17T00:00:00Z")
    _, out1 = run("ledger.py", *args)
    _, out2 = run("ledger.py", *args)
    assert out1 == out2 and out1.strip().startswith("{")


# ── doctrine.py (anti-poisoning gate) ─────────────────────────────────────────
def test_doctrine_no_anonymous(tmp_path):
    code, out = run("doctrine.py", "propose", str(tmp_path), "role",
                    "--claim", "x", "--confidence", "0.9")
    assert code == 2 and "anonymous doctrine" in out


def _propose_full(tmp_path, role="role"):
    code, out = run("doctrine.py", "propose", str(tmp_path), role, "--claim", "c",
                    "--source", "s", "--confidence", "0.9",
                    "--retrieved-at", "2026-07-16", "--review-by", "2027-01-16")
    assert code == 0, out
    code, show = run("doctrine.py", "show", str(tmp_path), role)
    return json.loads(show)["claims"][0]["id"]


def test_doctrine_maker_cannot_admit(tmp_path):
    cid = _propose_full(tmp_path)
    code, out = run("doctrine.py", "admit", str(tmp_path), "role", cid, "--by", "maker")
    assert code == 2 and "may not admit its own doctrine" in out


def test_doctrine_incomplete_provenance_blocked(tmp_path):
    code, out = run("doctrine.py", "propose", str(tmp_path), "role", "--claim", "c",
                    "--source", "s", "--confidence", "0.9", "--retrieved-at", "2026-07-16")
    assert code == 0, out   # no review-by
    _, show = run("doctrine.py", "show", str(tmp_path), "role")
    cid = json.loads(show)["claims"][0]["id"]
    code, out = run("doctrine.py", "admit", str(tmp_path), "role", cid, "--by", "gate")
    assert code == 2 and ("incomplete" in out or "provenance" in out)


def test_doctrine_gate_admits(tmp_path):
    cid = _propose_full(tmp_path)
    code, out = run("doctrine.py", "admit", str(tmp_path), "role", cid,
                    "--by", "gate", "--at", "2026-07-16")
    assert code == 0 and "admitted" in out


# ── guardrails.py ─────────────────────────────────────────────────────────────
def test_guardrails_cap_holds(tmp_path):
    code, out = run("guardrails.py", "cap", str(tmp_path), "--dimension", "spend",
                    "--delta", "100", "--cap", "50", "--actor", "x")
    assert code == 10 and "HOLD" in out


def test_guardrails_cap_allows(tmp_path):
    code, out = run("guardrails.py", "cap", str(tmp_path), "--dimension", "spend",
                    "--delta", "10", "--cap", "50", "--actor", "x")
    assert code == 0 and "allow" in out and '"decision": "allow"' in out


# ── reconcile.py ──────────────────────────────────────────────────────────────
def test_reconcile_mandate_precedence(tmp_path):
    code, out = run("reconcile.py", "mandate", str(tmp_path), "--subjects", "safety,growth",
                    "--decision", "ship", "--precedence", "safety>growth")
    assert code == 0 and "precedence_applies" in out


def test_reconcile_mandate_integrate(tmp_path):
    code, out = run("reconcile.py", "mandate", str(tmp_path), "--subjects", "safety,growth",
                    "--decision", "ship", "--precedence", "safety>growth", "--satisfiable", "true")
    assert code == 0 and "integrate" in out


def test_reconcile_mandate_absent_escalates(tmp_path):
    code, out = run("reconcile.py", "mandate", str(tmp_path), "--subjects", "a,b",
                    "--decision", "d", "--precedence", "a")
    assert code == 10 and "absent from the declared" in out


def test_reconcile_collision_duplicate_self_heals(tmp_path):
    # two peers on one territory -> OVERLAP but exit 0 (lateral self-heal, NOT escalate)
    seed(tmp_path, "m", "work_claimed",
         {"role": "m", "work_territory": "T", "intent_summary": "a"})
    seed(tmp_path, "n", "work_claimed",
         {"role": "n", "work_territory": "T", "intent_summary": "b"},
         ts="2026-07-16T00:01:00Z")
    code, out = run("reconcile.py", "collision", str(tmp_path))
    assert code == 0 and "OVERLAP" in out


def test_reconcile_stall_escalates(tmp_path):
    seed(tmp_path, "m", "cycle_started", {"role": "m", "pack_manifest_id": "x"})
    for i in range(3):
        seed(tmp_path, "n", "cycle_started", {"role": "n", "pack_manifest_id": f"a{i}"},
             ts=f"2026-07-16T0{i+1}:00:00Z")
    code, out = run("reconcile.py", "stall", str(tmp_path), "--freshness-cycles", "2")
    assert code == 10 and "STALL" in out


# ── alignment.py ──────────────────────────────────────────────────────────────
def test_alignment_premise_broken(tmp_path):
    code, out = run("alignment.py", "premise", str(tmp_path), "--premise-id", "p",
                    "--asserted", "100", "--observed", "10")
    assert code == 10 and "BROKEN" in out


def test_alignment_premise_holds(tmp_path):
    code, out = run("alignment.py", "premise", str(tmp_path), "--premise-id", "p",
                    "--asserted", "100", "--observed", "100")
    assert code == 0 and "holds" in out


def test_alignment_sunk_abandons(tmp_path):
    for i in range(6):
        seed(tmp_path, "m", "candidate_submitted",
             {"maker": "m", "candidate_id": "course", "contract_ref": "r", "evidence": []},
             ts=f"2026-07-16T0{i}:00:00Z")
    code, out = run("alignment.py", "sunk", str(tmp_path), "--course-id", "course",
                    "--attempt-cap", "4")
    assert code == 10 and "ABANDON" in out


# ── tick.py (missed-detection boundary) ───────────────────────────────────────
def _sched():
    return str(TEMPLATE / "schedule.yaml")


def test_tick_no_miss_when_fresh(tmp_path):
    # a low now-min: nothing is overdue enough to miss yet
    code, out = run("tick.py", "plan", str(tmp_path), _sched(), "--now-min", "5")
    assert code == 0


def test_tick_detects_miss(tmp_path):
    # now-min must land on a check's interval boundary for it to be DUE and thus miss-checkable.
    # 180 is a multiple of the 30-min machine_sensors/chain_verify cadence; an empty ledger has
    # produced 0 of an expected 6 -> shortfall 6 > grace 2 and >= esc_after 3 -> MISS + escalate.
    code, out = run("tick.py", "plan", str(tmp_path), _sched(), "--now-min", "180")
    assert code == 10 and ("MISS" in out or "ESCALATE" in out)


def test_tick_night_suspends_unsafe(tmp_path):
    code, out = run("tick.py", "plan", str(tmp_path), _sched(), "--now-min", "5", "--night")
    assert "SUSPENDED" in out and ("mandate_conflict" in out or "contract_change" in out)


# ── sensors.py ────────────────────────────────────────────────────────────────
def test_sensors_eval_defers_llm(tmp_path):
    code, out = run("sensors.py", "eval", str(tmp_path), str(TEMPLATE / "sensors.yaml"),
                    "--now", "2026-07-16T12:00:00Z")
    assert code == 0 and "deferred" in out and "red_tape_ratio" in out


# ── the otherwise-uncovered _events sharers: attention / learning / resource / conventions ──
def test_attention_silent_when_empty_backlog(tmp_path):
    code, out = run("attention.py", "select", str(tmp_path), "--role", "miner")
    assert code == 0 and ("empty" in out or "silent" in out.lower())


def test_attention_escalates_on_coverage_gap(tmp_path):
    seed(tmp_path, "registrar", "priority_ranking_set",
         {"ranking_id": "r1", "ordered_objectives": [{"objective_id": "growth", "rank": 1, "weight": 0.9}]})
    seed(tmp_path, "analyst", "candidate_submitted",
         {"maker": "analyst", "candidate_id": "w1", "contract_ref": "cost", "evidence": []},
         ts="2026-07-16T00:01:00Z")
    code, out = run("attention.py", "select", str(tmp_path), "--role", "analyst", "--wip-limit", "2")
    assert code == 10 and ("ESCALATE" in out or "cannot serve" in out)


def test_learning_silent_when_matched(tmp_path):
    code, out = run("learning.py", "delta", str(tmp_path))
    assert code == 0 and "matched" in out


def test_learning_systemic_escalates(tmp_path):
    for i in range(3):
        seed(tmp_path, "gate", "admission_decided",
             {"gate": "gate", "candidate_id": f"c{i}", "verdict": "admit",
              "predicted_outcome": 1.0, "standard_ref": "s", "evidence": []},
             ts=f"2026-07-16T0{i}:00:00Z")
        seed(tmp_path, "r", "refutation_attempted",
             {"skeptic": "s", "claim_id": f"c{i}", "verdict": "survives", "checklist_ref": "x"},
             ts=f"2026-07-16T0{i}:10:00Z")
        seed(tmp_path, "r", "result_deployed",
             {"candidate_id": f"c{i}", "net_effect_ref": "n", "observed_outcome": 0.3},
             ts=f"2026-07-16T0{i}:30:00Z")
    code, out = run("learning.py", "delta", str(tmp_path), "--threshold", "0.2", "--recurrence", "3")
    assert code == 10 and "SYSTEMIC" in out


def test_resource_rank_emits_on_change(tmp_path):
    code, out = run("resource.py", "rank", str(tmp_path), "--objectives", "a:0.9,b:0.5")
    assert code == 0 and ("reordered" in out or "LEDGER-EVENT" in out)


def test_resource_reclaim_idle_safe(tmp_path):
    code, out = run("resource.py", "reclaim", str(tmp_path), "--holder", "dormant",
                    "--resource", "context", "--yield-threshold", "0.5", "--idle-cycles", "1")
    assert code == 0 and "reclaim" in out


def test_conventions_maker_cannot_adopt(tmp_path):
    code, out = run("conventions.py", "adopt", str(tmp_path), "--scope", "s",
                    "--choice", "c", "--owner", "o", "--by", "maker")
    assert code == 2 and "must be 'checker'" in out


def test_conventions_conflict_escalates(tmp_path):
    code, _ = run("conventions.py", "adopt", str(tmp_path), "--scope", "tone",
                  "--choice", "soft", "--owner", "o", "--by", "checker", "--review-by", "2027-01-16")
    assert code == 0
    code, out = run("conventions.py", "conflict", str(tmp_path), "--scope", "tone",
                    "--choice", "aggressive")
    assert code == 10 and "CONVENTION-CONFLICT" in out
