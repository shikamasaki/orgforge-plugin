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


def test_work_in_progress_view_resolves_started_not_completed(tmp_path):
    # the recovery source after a context wipe: a candidate STARTED with a progress checkpoint but not
    # completed must appear with its latest next_step; a COMPLETED one must drop out.
    seed(tmp_path, "eng", "cycle_started", {"role": "eng", "candidate_id": "X", "pack_manifest_id": "p"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "eng", "progress_recorded",
         {"role": "eng", "candidate_id": "X", "fraction": 0.6, "phase": "impl",
          "done_so_far": "parser done", "next_step": "wire into CLI", "blocked_by": None, "artifacts": []},
         ts="2026-07-16T02:00:00Z")
    # a second candidate that WAS completed — must not appear in WIP
    seed(tmp_path, "eng", "cycle_started", {"role": "eng", "candidate_id": "Y", "pack_manifest_id": "p"},
         ts="2026-07-16T03:00:00Z")
    seed(tmp_path, "eng", "cycle_completed", {"role": "eng", "candidate_id": "Y", "outputs": []},
         ts="2026-07-16T04:00:00Z")
    code, out = run("ledger.py", "view", str(tmp_path), "work_in_progress")
    assert code == 0, out
    data = json.loads(out)
    ids = [w["candidate_id"] for w in data["in_progress"]]
    assert ids == ["X"], f"expected only the unfinished X, got {ids}"
    wx = data["in_progress"][0]
    assert wx["progress"]["next_step"] == "wire into CLI"
    assert abs(wx["progress"]["fraction"] - 0.6) < 1e-9


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
    # the full chain: spec_delegated -> conformance_reviewed{conforms} -> report_up valid
    seed(tmp_path, "s", "spec_delegated",
         {"supervisor": "s", "subordinate": "sub", "spec_ref": "sp", "contract_ref": "c",
          "intent_basis_ref": "ib", "token_budget": 50000, "confirmed": True},
         ts="2026-07-16T00:01:00Z")
    seed(tmp_path, "s", "conformance_reviewed",
         {"supervisor": "s", "subordinate": "sub", "reviewed_ref": "r",
          "delegated_intent_ref": "sp", "verdict": "conforms", "evidence_ref": "e"},
         ts="2026-07-16T00:02:00Z")
    rp2 = dict(rp)
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "s",
                    "--class", "report_up", "--payload", json.dumps(rp2), "--ts",
                    "2026-07-16T00:03:00Z")
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


def _admitted_claim(tmp_path, role, claim, affects):
    """propose+admit one claim tagged for `affects`, return its id."""
    run("doctrine.py", "propose", str(tmp_path), role, "--claim", claim,
        "--source", "s", "--confidence", "0.9", "--retrieved-at", "2026-07-16",
        "--review-by", "2027-01-16", "--affects", affects)
    _, show = run("doctrine.py", "show", str(tmp_path), role)
    cid = [c for c in json.loads(show)["claims"] if c["claim"] == claim][0]["id"]
    run("doctrine.py", "admit", str(tmp_path), role, cid, "--by", "gate", "--at", "2026-07-16")
    return cid


def test_doctrine_remap_rename_preserves_brain(tmp_path):
    # refound rename: eng-manager -> platform-manager; the brain follows (asset intact).
    _admitted_claim(tmp_path, "eng-manager", "coupled unit: one agent", "eng-manager")
    dst = tmp_path / "new"
    code, out = run("doctrine.py", "remap", str(tmp_path),
                    "--map", json.dumps({"eng-manager": "platform-manager"}), "--into", str(dst))
    assert code == 0, out
    _, show = run("doctrine.py", "show", str(dst), "platform-manager")
    assert len(json.loads(show)["claims"]) == 1


def test_doctrine_remap_split_routes_by_affected_roles(tmp_path):
    # refound split: ui-worker -> {frontend-worker, mobile-worker}; each claim goes to the
    # target named in its affected_roles.
    _admitted_claim(tmp_path, "ui-worker", "single-file UI: do not split", "frontend-worker")
    _admitted_claim(tmp_path, "ui-worker", "touch targets >= 44px", "mobile-worker")
    dst = tmp_path / "new"
    code, out = run("doctrine.py", "remap", str(tmp_path),
                    "--map", json.dumps({"ui-worker": ["frontend-worker", "mobile-worker"]}),
                    "--into", str(dst))
    assert code == 0, out
    _, fe = run("doctrine.py", "show", str(dst), "frontend-worker")
    _, mo = run("doctrine.py", "show", str(dst), "mobile-worker")
    assert len(json.loads(fe)["claims"]) == 1 and len(json.loads(mo)["claims"]) == 1


def test_doctrine_remap_orphan_blocks_refound(tmp_path):
    # a live claim that maps to no target must BLOCK the refound — no silent brain loss.
    _admitted_claim(tmp_path, "api-worker", "idempotency keys on POST", "api-worker")
    dst = tmp_path / "new"
    code, out = run("doctrine.py", "remap", str(tmp_path),
                    "--map", json.dumps({"api-worker": ["x-worker", "y-worker"]}), "--into", str(dst))
    assert code == 2 and "orphan" in out.lower()


def test_doctrine_remap_allow_orphans_surfaces_not_drops(tmp_path):
    # --allow-orphans routes orphans to UNROUTED (surfaced for a human), never dropped.
    _admitted_claim(tmp_path, "api-worker", "idempotency keys on POST", "api-worker")
    dst = tmp_path / "new"
    code, out = run("doctrine.py", "remap", str(tmp_path),
                    "--map", json.dumps({"api-worker": ["x-worker", "y-worker"]}),
                    "--into", str(dst), "--allow-orphans")
    assert code == 0, out
    _, un = run("doctrine.py", "show", str(dst), "UNROUTED")
    assert len(json.loads(un)["claims"]) == 1   # preserved, not lost


# ── handoff.py (seam contract + scoped brain at delegation) ───────────────────
def test_handoff_requires_a_seam_contract(tmp_path):
    # a manager cannot delegate without fixing the boundary — inputs/outputs are required,
    # so no child is ever spawned with an un-owned seam (the integration-drift guard).
    code, out = run("handoff.py", str(tmp_path), "api-worker", "--slice", "s")
    assert code == 2 and "inputs" in out and "outputs" in out


def test_handoff_scopes_brain_and_fixes_seam(tmp_path):
    # the child's brain is scoped to ITS role; a sibling's doctrine does not leak in;
    # the seam contract (inputs/outputs) is present as a hard constraint.
    _admitted_claim(tmp_path, "api-worker", "idempotency keys on POST", "api-worker")
    _admitted_claim(tmp_path, "db-worker", "avoid N+1 queries", "db-worker")
    code, out = run("handoff.py", str(tmp_path), "api-worker",
                    "--slice", "build the auth API",
                    "--inputs", "user records", "--outputs", "POST /login -> {token}")
    assert code == 0, out
    assert "idempotency keys on POST" in out        # its own brain
    assert "N+1" not in out                          # sibling brain does NOT leak in
    assert "Boundary contract" in out and "POST /login -> {token}" in out   # seam fixed


def test_handoff_axis_is_local_advice_not_global(tmp_path):
    # the axis line is explicitly local ("your call"), never a global constraint —
    # the per-level-axis conclusion from the design review.
    code, out = run("handoff.py", str(tmp_path), "w",
                    "--slice", "s", "--inputs", "i", "--outputs", "o",
                    "--axis", "cut by endpoint")
    assert code == 0, out
    assert "do not inherit a global one" in out


# ── guardrails.py ─────────────────────────────────────────────────────────────
def test_guardrails_cap_holds(tmp_path):
    code, out = run("guardrails.py", "cap", str(tmp_path), "--dimension", "spend",
                    "--delta", "100", "--cap", "50", "--actor", "x")
    assert code == 10 and "HOLD" in out


def test_guardrails_cap_allows(tmp_path):
    code, out = run("guardrails.py", "cap", str(tmp_path), "--dimension", "spend",
                    "--delta", "10", "--cap", "50", "--actor", "x")
    assert code == 0 and "allow" in out and '"decision": "allow"' in out


# ── SILENCE-CONSENT (docs/06 §2.1): reversible flows, irreversible holds ───────
def test_consent_reversible_proceeds_on_silence(tmp_path):
    code, out = run("guardrails.py", "consent", str(tmp_path),
                    "--action-class", "reprioritize", "--item-ref", "i1")
    assert code == 0 and "silence=consent" in out and "silence_is_consent" in out


def test_consent_irreversible_holds_for_ack(tmp_path):
    code, out = run("guardrails.py", "consent", str(tmp_path),
                    "--action-class", "production_deploy", "--item-ref", "i2")
    assert code == 10 and "HOLD" in out and "explicit_ack_required" in out


# ── STALE-REFERENCE --auto: derive trigger + bound roles from the ledger ───────
def test_staleref_auto_finds_role_stale_after_ranking_change(tmp_path):
    seed(tmp_path, "s", "cycle_completed", {"role": "fe", "tokens": {}, "outputs": []},
         ts="2026-07-17T10:00:00Z")
    seed(tmp_path, "s", "cycle_completed", {"role": "be", "tokens": {}, "outputs": []},
         ts="2026-07-17T10:01:00Z")
    seed(tmp_path, "r", "priority_ranking_set", {"ranking_id": "r1", "ordered_objectives": []},
         ts="2026-07-17T11:00:00Z")
    seed(tmp_path, "s", "cycle_started", {"role": "fe"}, ts="2026-07-17T11:05:00Z")
    code, out = run("guardrails.py", "staleref", str(tmp_path), "--auto")
    # fe re-derived after the ranking change; be did not -> be is stale (nudge, under threshold)
    assert code == 0 and '"stale_roles": ["be"]' in out


# ── DEPENDENCY-STALL reads depends_on edges (not just cycle timing) ────────────
def test_stall_reports_downstream_from_depends_on(tmp_path):
    seed(tmp_path, "s", "work_claimed",
         {"role": "fe", "work_territory": "ui", "intent_summary": "x",
          "depends_on": [{"producer_role": "be", "seam_id": "auth-api"}]},
         ts="2026-07-17T10:00:00Z")
    seed(tmp_path, "s", "cycle_started", {"role": "be"}, ts="2026-07-17T10:01:00Z")
    seed(tmp_path, "s", "cycle_started", {"role": "fe"}, ts="2026-07-17T10:02:00Z")
    for i in range(3):
        seed(tmp_path, "s", "cycle_started", {"role": "data"},
             ts=f"2026-07-17T10:0{3+i}:00Z")
    code, out = run("reconcile.py", "stall", str(tmp_path), "--freshness-cycles", "2")
    # the blocked-on edge means fe is downstream of the be stall — read from depends_on, not None
    assert code == 10 and '"downstream_impact": ["fe"]' in out


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


def test_attention_mandate_rides_a_floor_over_self_work(tmp_path):
    # zone of acceptance (docs/12): a top-down mandate on an in-ranking objective is floored so a live
    # instruction is not starved by low-priority self work. Both serve in-ranking objectives ranked
    # low (rank 3 → rank_score 0.33, weight 0.2 → base 0.53 each). The self item's base 0.53 loses to
    # the mandate floored to 1.0. With --wip-limit 1 the floor must select the mandate.
    seed(tmp_path, "registrar", "priority_ranking_set",
         {"ranking_id": "r1", "ordered_objectives": [
             {"objective_id": "minor_a", "rank": 3, "weight": 0.2},
             {"objective_id": "minor_b", "rank": 3, "weight": 0.2}]})
    seed(tmp_path, "eng", "candidate_submitted",
         {"maker": "eng", "candidate_id": "self1", "contract_ref": "minor_a", "source": "self",
          "evidence": []}, ts="2026-07-16T00:01:00Z")
    seed(tmp_path, "eng", "candidate_submitted",
         {"maker": "eng", "candidate_id": "mand1", "contract_ref": "minor_b", "source": "mandate",
          "evidence": []}, ts="2026-07-16T00:02:00Z")
    code, out = run("attention.py", "select", str(tmp_path), "--role", "eng",
                    "--wip-limit", "1", "--mandate-floor", "1.0")
    # the mandate is selected (floored to 1.0, above the self item's base ~0.53); the emitted event
    # carries source + the floor marker.
    assert code == 0, out
    sel = out.split('"selected"')[1].split('"deferred"')[0]
    assert '"candidate_id": "mand1"' in sel and '"source": "mandate"' in sel
    assert '"candidate_id": "self1"' not in sel


def test_attention_off_ranking_mandate_is_not_floored(tmp_path):
    # a mandate whose objective is OFF the ranking is OUTSIDE the acceptance zone — no floor, it stays
    # a visible drift signal (docs/12). Only the in-ranking self item is picked.
    seed(tmp_path, "registrar", "priority_ranking_set",
         {"ranking_id": "r1", "ordered_objectives": [{"objective_id": "growth", "rank": 1, "weight": 0.9}]})
    seed(tmp_path, "eng", "candidate_submitted",
         {"maker": "eng", "candidate_id": "self1", "contract_ref": "growth", "source": "self",
          "evidence": []}, ts="2026-07-16T00:01:00Z")
    seed(tmp_path, "eng", "candidate_submitted",
         {"maker": "eng", "candidate_id": "offmand", "contract_ref": "unlisted", "source": "mandate",
          "evidence": []}, ts="2026-07-16T00:02:00Z")
    code, out = run("attention.py", "select", str(tmp_path), "--role", "eng",
                    "--wip-limit", "1", "--mandate-floor", "1.0")
    assert code == 0, out
    assert '"candidate_id": "self1"' in out          # in-ranking self wins
    assert '"candidate_id": "offmand", "objective"' not in out.split('"selected"')[1].split('"deferred"')[0]


def test_stall_breaker_trips_on_identical_output(tmp_path):
    # circuit breaker: the same next_step twice in a row → trip (AgentMesh identical-output heuristic).
    seed(tmp_path, "eng", "progress_recorded",
         {"candidate_id": "X", "role": "eng", "fraction": 0.3, "next_step": "wire CLI"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "eng", "progress_recorded",
         {"candidate_id": "X", "role": "eng", "fraction": 0.3, "next_step": "wire CLI"},
         ts="2026-07-16T02:00:00Z")
    code, out = run("guardrails.py", "stall", str(tmp_path), "--candidate-id", "X")
    assert code == 10 and "TRIP" in out


def test_stall_breaker_silent_while_progressing(tmp_path):
    for i, f in enumerate((0.2, 0.5, 0.8)):
        seed(tmp_path, "eng", "progress_recorded",
             {"candidate_id": "X", "role": "eng", "fraction": f, "next_step": f"step{i}"},
             ts=f"2026-07-16T0{i+1}:00:00Z")
    code, out = run("guardrails.py", "stall", str(tmp_path), "--candidate-id", "X")
    assert code == 0 and "progressing" in out


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


def test_repeated_death_escalates(tmp_path):
    # the direct measure of "learning lifts quality": the same death cause on a later candidate escalates.
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "A", "cause": "null hypothesis not rejected"}, ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired",
         {"candidate_id": "B", "cause": "null hypothesis not rejected"}, ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 10 and "REPEATED DEATH" in out


def test_distinct_deaths_are_silent(tmp_path):
    seed(tmp_path, "gate", "result_retired", {"candidate_id": "A", "cause": "cause one"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired", {"candidate_id": "B", "cause": "cause two"},
         ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out


def test_domain_model_growth_reports_scopes(tmp_path):
    # the SSoT/domain model must grow during operation; growth reports the settled-convention base.
    code, out = run("conventions.py", "growth", str(tmp_path))
    assert code == 0 and "EMPTY" in out          # nothing settled yet
    for scope, choice in (("auth", "use JWT"), ("naming", "snake_case")):
        run("conventions.py", "adopt", str(tmp_path), "--scope", scope, "--choice", choice,
            "--owner", "eng", "--by", "checker")
    code, out = run("conventions.py", "growth", str(tmp_path))
    assert code == 0 and "2 active convention" in out and "auth" in out


def test_rollback_unproven_without_undo(tmp_path):
    # a reversible action with no declared undo escalates (untested reversibility is a latent lie).
    code, out = run("guardrails.py", "rollback", str(tmp_path), "--action-ref", "deploy-x")
    assert code == 10 and "UNPROVEN" in out


def test_rollback_proven_with_undo(tmp_path):
    code, out = run("guardrails.py", "rollback", str(tmp_path), "--action-ref", "deploy-x",
                    "--undo", "git revert abc123")
    assert code == 0 and "proven" in out
