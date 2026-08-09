"""その他の器官 — doctrine / handoff / reconcile / alignment / tick / sensors。"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

from conftest import (REPO, TOOLS, TEMPLATE, run, seed, _cycle_src, _gh_src,
                      _cycle_mod, _propose_full, _admitted_claim, _sched,
                      _ledger_with, _led, _append, _status, _write_ledger)

TICK_HOST = REPO / "integrations" / "common" / "tick_host.py"


def test_report_up_requires_prior_conformance(tmp_path):
    # A4 (docs/09): a manager may not report subordinate work up without a prior A3 conforms —
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


def test_guardrails_cap_tolerates_ts_less_event(tmp_path):
    # an event with no 'ts' (as emit_event writes) must not KeyError when a window is set
    (tmp_path / "ledger.jsonl").write_text(json.dumps(
        {"id": "e1", "seq": 1, "class": "exposure_budget_checked",
         "payload": {"dimension": "spend", "decision": "allow", "delta_requested": 1}}) + "\n")
    code, out = run("guardrails.py", "cap", str(tmp_path), "--dimension", "spend",
                    "--delta", "1", "--cap", "5", "--actor", "x", "--window-since", "1970-01-01")
    assert code == 0 and "Traceback" not in out


# ── doctrine.py (anti-poisoning gate) ─────────────────────────────────────────
def test_doctrine_no_anonymous(tmp_path):
    code, out = run("doctrine.py", "propose", str(tmp_path), "role",
                    "--claim", "x", "--confidence", "0.9")
    assert code == 2 and "anonymous doctrine" in out


def test_doctrine_maker_cannot_admit(tmp_path):
    cid = _propose_full(tmp_path)
    code, out = run("doctrine.py", "admit", str(tmp_path), "role", cid, "--by", "maker")
    assert code == 2 and "may not admit its own doctrine" in out


def test_doctrine_gate_admits(tmp_path):
    cid = _propose_full(tmp_path)
    code, out = run("doctrine.py", "admit", str(tmp_path), "role", cid,
                    "--by", "gate", "--at", "2026-07-16")
    assert code == 0 and "admitted" in out


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


# ── guardrails.py ─────────────────────────────────────────────────────────────
def test_guardrails_cap_holds(tmp_path):
    code, out = run("guardrails.py", "cap", str(tmp_path), "--dimension", "spend",
                    "--delta", "100", "--cap", "50", "--actor", "x")
    assert code == 10 and "HOLD" in out


def test_guardrails_cap_allows(tmp_path):
    code, out = run("guardrails.py", "cap", str(tmp_path), "--dimension", "spend",
                    "--delta", "10", "--cap", "50", "--actor", "x")
    assert code == 0 and "allow" in out and '"decision": "allow"' in out


# ── SILENCE-CONSENT (docs/05 §2.1): reversible flows, irreversible holds ───────


# ── SILENCE-CONSENT (docs/05 §2.1): reversible flows, irreversible holds ───────
def test_consent_reversible_proceeds_on_silence(tmp_path):
    code, out = run("guardrails.py", "consent", str(tmp_path),
                    "--action-class", "reprioritize", "--item-ref", "i1")
    assert code == 0 and "silence=consent" in out and "silence_is_consent" in out


def test_consent_irreversible_holds_for_ack(tmp_path):
    code, out = run("guardrails.py", "consent", str(tmp_path),
                    "--action-class", "production_deploy", "--item-ref", "i2")
    assert code == 10 and "HOLD" in out and "explicit_ack_required" in out


# ── STALE-REFERENCE --auto: derive trigger + bound roles from the ledger ───────


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


# ── reconcile.py ──────────────────────────────────────────────────────────────
def test_reconcile_mandate_precedence(tmp_path):
    code, out = run("reconcile.py", "mandate", str(tmp_path), "--subjects", "safety,growth",
                    "--decision", "ship", "--precedence", "safety>growth")
    assert code == 0 and "precedence_applies" in out


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


def test_tick_no_miss_when_fresh(tmp_path):
    # The first tick establishes the monitoring baseline.  A host passing Unix-epoch minutes
    # must not make a newly enabled schedule look as though it has been missing since 1970.
    code, out = run("tick.py", "plan", str(tmp_path), _sched(),
                    "--now-min", "29759222")
    assert code == 0 and "495987" not in out


def test_tick_uses_first_planned_tick_as_monitoring_origin(tmp_path):
    seed(tmp_path, "registrar", "tick_planned",
         {"now_min": 29759220, "night": False, "due": [], "suspended": [], "missed": []})

    # Only two minutes have elapsed since monitoring started, regardless of the absolute epoch.
    code, out = run("tick.py", "plan", str(tmp_path), _sched(),
                    "--now-min", "29759222")
    assert code == 0 and "495987" not in out


def _host_tick(root, now, *extra, env=None):
    return subprocess.run(
        [sys.executable, str(TICK_HOST), _sched(), "--root", str(root),
         "--now-min", str(now), *extra], capture_output=True, text=True, env=env)


def _tick_host_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("orgforge_tick_host_test", TICK_HOST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tick_host_persists_origin_and_detects_later_real_miss(tmp_path):
    origin = 29759220
    first = _host_tick(tmp_path, origin)
    assert first.returncode == 0, first.stdout + first.stderr
    event = json.loads((tmp_path / "ledger.jsonl").read_text(
        encoding="utf-8").splitlines()[0])
    assert event["class"] == "tick_planned"
    assert event["payload"]["now_min"] == origin

    missed = _host_tick(tmp_path, origin + 180)
    assert missed.returncode == 10
    assert "MISS" in missed.stdout + missed.stderr


def test_tick_rejects_backwards_clock_domain(tmp_path):
    seed(tmp_path, "registrar", "tick_planned",
         {"now_min": 29759220, "night": False, "due": [], "suspended": [], "missed": []})
    code, out = run("tick.py", "plan", str(tmp_path), _sched(), "--now-min", "100")
    assert code == 10 and "clock domain moved backwards" in out


def test_tick_rejects_malformed_monitoring_origin(tmp_path):
    seed(tmp_path, "registrar", "tick_planned",
         {"now_min": "180", "night": False, "due": [], "suspended": [], "missed": []})
    code, out = run("tick.py", "plan", str(tmp_path), _sched(), "--now-min", "180")
    assert code == 10 and "origin is malformed" in out


def test_tick_host_repairs_malformed_origin_on_next_receipt(tmp_path):
    seed(tmp_path, "registrar", "tick_planned",
         {"now_min": "broken", "night": False, "due": [], "suspended": [], "missed": []})
    repair = _host_tick(tmp_path, 180)
    assert repair.returncode == 10 and "origin is malformed" in repair.stdout + repair.stderr

    # A retry inside the same minute emits a repaired payload. Its natural key must not collide
    # with the first (clock-error) payload merely because ``now_min`` is unchanged.
    recovered = _host_tick(tmp_path, 180)
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    assert "origin is malformed" not in recovered.stdout + recovered.stderr
    assert "could not persist tick_planned" not in recovered.stdout + recovered.stderr


def test_tick_malformed_later_receipt_keeps_real_miss_accounting(tmp_path):
    seed(tmp_path, "registrar", "tick_planned",
         {"now_min": 0, "night": False, "due": [], "suspended": [], "missed": []})
    seed(tmp_path, "registrar", "tick_planned",
         {"now_min": "broken", "night": False, "due": [], "suspended": [], "missed": []})

    code, out = run("tick.py", "plan", str(tmp_path), _sched(), "--now-min", "180")
    assert code == 10
    assert "origin is malformed" in out
    assert "machine_sensors" in out and "chain_verify" in out


def test_tick_backwards_clock_without_compatible_origin_is_globally_visible(tmp_path):
    seed(tmp_path, "registrar", "tick_planned",
         {"now_min": 29759220, "night": False, "due": [], "suspended": [], "missed": []})
    code, out = run("tick.py", "plan", str(tmp_path), _sched(), "--now-min", "100")
    assert code == 10
    assert "tick_clock" in out and "cannot prove scheduled checks ran" in out


def test_tick_host_routes_receipt_through_writer_client(monkeypatch, tmp_path):
    from types import SimpleNamespace
    module = _tick_host_module()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1].endswith("tick.py"):
            return SimpleNamespace(
                returncode=0,
                stdout=('LEDGER-EVENT {"class":"tick_planned","payload":'
                        '{"now_min":180,"night":false,"due":[],"suspended":[],"missed":[]}}\n'),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout='{"ok":true}\n', stderr="")

    monkeypatch.setenv("ORG_WRITER_SOCKET", str(tmp_path / "writer.sock"))
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    code = module.main([_sched(), "--root", str(tmp_path), "--now-min", "180"])
    assert code == 0
    assert any(command[1].endswith("writer_client.py") and command[2:4] == ["append", "--"]
               for command in calls)
    assert not any(command[1].endswith("ledger.py") for command in calls)


def test_tick_host_append_failure_is_visible(monkeypatch, tmp_path, capsys):
    from types import SimpleNamespace
    module = _tick_host_module()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            return SimpleNamespace(
                returncode=0,
                stdout=('LEDGER-EVENT {"class":"tick_planned","payload":'
                        '{"now_min":180,"night":false,"due":[],"suspended":[],"missed":[]}}\n'),
                stderr="",
            )
        return SimpleNamespace(returncode=4, stdout="", stderr="writer unavailable")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    code = module.main([_sched(), "--root", str(tmp_path), "--now-min", "180"])
    captured = capsys.readouterr()
    assert code == 10
    assert "could not persist tick_planned" in captured.err
    assert "writer unavailable" in captured.err


def test_night_tick_persists_origin_without_resetting_it(tmp_path):
    origin = 29759220
    first = _host_tick(tmp_path, origin, "--night")
    assert first.returncode == 0, first.stdout + first.stderr

    missed = _host_tick(tmp_path, origin + 180)
    assert missed.returncode == 10
    assert "MISS" in missed.stdout + missed.stderr


def test_shipped_claude_tick_paths_use_persisting_host_adapter():
    command = (REPO / "integrations/claude-code/commands/org-tick.md").read_text(encoding="utf-8")
    registrar = (REPO / "integrations/claude-code/agents/registrar.md").read_text(encoding="utf-8")
    assert "scripts/tick_host.py" in command
    assert "scripts/tick_host.py" in registrar
    shipped = list((REPO / "integrations/claude-code/commands").glob("*.md"))
    shipped += list((REPO / "integrations/claude-code/agents").glob("*.md"))
    assert not [path for path in shipped if "tools/tick.py plan" in path.read_text(encoding="utf-8")]


def test_tick_detects_miss(tmp_path):
    # Miss accounting begins when the host first planned a tick, not at Unix epoch zero.
    seed(tmp_path, "registrar", "tick_planned",
         {"now_min": 0, "night": False, "due": [], "suspended": [], "missed": []})
    # 180 is a multiple of the 30-min machine_sensors/chain_verify cadence. Since monitoring
    # began at t=0, six runs were expected and none were verified, so this is a real MISS.
    code, out = run("tick.py", "plan", str(tmp_path), _sched(), "--now-min", "180")
    assert code == 10 and ("MISS" in out or "ESCALATE" in out)


def test_tick_detects_missing_scheduler_receipt_without_domain_event_forgery(tmp_path):
    seed(tmp_path, "system:tick_host", "tick_planned",
         {"now_min": 100, "night": False, "due": [], "suspended": [], "missed": []})
    code, out = run(
        "tick.py", "plan", str(tmp_path), _sched(), "--now-min", "280",
        "--only-check", "machine_sensors", "--receipt-check", "machine_sensors")
    assert code == 10
    assert "scheduled-check receipt" in out and "machine_sensors" in out


def test_tick_relative_phase_follows_host_start_not_unix_boundary(tmp_path):
    seed(tmp_path, "system:tick_host", "tick_planned",
         {"now_min": 101, "night": False, "due": [], "suspended": [], "missed": []})
    receipt_code, receipt_out = run(
        "ledger.py", "record-scheduled-check", str(tmp_path),
        "--check-id", "machine_sensors", "--scheduled-for-min", "131",
        "--execution-id", "relative-131", "--result", "ok", "--exit-code", "0",
        "--command-sha256", "a" * 64, "--plugin-version", "test")
    assert receipt_code == 0, receipt_out
    code, out = run(
        "tick.py", "plan", str(tmp_path), _sched(), "--now-min", "131",
        "--only-check", "machine_sensors", "--receipt-check", "machine_sensors")
    assert code == 0
    assert "machine_sensors" in out and "DUE (1)" in out


def test_tick_night_suspends_unsafe(tmp_path):
    code, out = run("tick.py", "plan", str(tmp_path), _sched(), "--now-min", "5", "--night")
    assert "SUSPENDED" in out and ("mandate_conflict" in out or "contract_change" in out)


# ── sensors.py ────────────────────────────────────────────────────────────────


# ── sensors.py ────────────────────────────────────────────────────────────────
def test_sensors_eval_defers_llm(tmp_path):
    code, out = run("sensors.py", "eval", str(tmp_path), str(TEMPLATE / "sensors.yaml"),
                    "--now", "2026-07-16T12:00:00Z")
    assert code == 0 and "deferred" in out and "red_tape_ratio" in out


# ── the otherwise-uncovered _events sharers: attention / learning / resource / conventions ──


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
    # zone of acceptance (docs/09): a top-down mandate on an in-ranking objective is floored so a live
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
    # a visible drift signal (docs/09). Only the in-ranking self item is picked.
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


# ── runtime separation of duties (docs/03 §3.1, docs/11 §4f) ─────────────────
# REQUIRES_PRIOR asks whether the right events happened in the right order; it never asked WHO wrote
# them. That was survivable while a human read the diff. With human review retired the gate and skeptic
# are the only judges left, so an actor able to write its own admission IS the entire judgment layer —
# and the hash chain then LAUNDERS the forgery, since a forged verdict verifies clean.
def test_maker_cannot_admit_its_own_work(tmp_path):
    root = tmp_path / "l"
    seed(root, "maker-alice", "cycle_started",
         {"role": "maker-alice", "candidate_id": "c1", "pack_manifest_id": "p"})
    code, out = run("ledger.py", "append", str(root), "--actor", "maker-alice",
                    "--class", "admission_decided",
                    "--payload", json.dumps({"gate": "gate", "candidate_id": "c1",
                                             "verdict": "admit", "standard_ref": "s",
                                             "evidence": ["e"]}))
    assert code == 3, out
    assert "already acted as cycle_started" in out


def test_maker_cannot_forge_the_skeptics_survives(tmp_path):
    root = tmp_path / "l"
    seed(root, "maker-alice", "cycle_started",
         {"role": "maker-alice", "candidate_id": "c1", "pack_manifest_id": "p"})
    code, out = run("ledger.py", "append", str(root), "--actor", "maker-alice",
                    "--class", "refutation_attempted",
                    "--payload", json.dumps({"skeptic": "skeptic", "claim_id": "c1",
                                             "verdict": "survives", "checklist_ref": "x"}))
    assert code == 3, out


def test_the_gate_may_not_also_be_the_skeptic(tmp_path):
    """Adversarial review decorrelates blind spots only if the reviewer is a DIFFERENT actor."""
    root = tmp_path / "l"
    seed(root, "maker-alice", "cycle_started",
         {"role": "maker-alice", "candidate_id": "c1", "pack_manifest_id": "p"})
    seed(root, "gate", "admission_decided",
         {"gate": "gate", "candidate_id": "c1", "verdict": "admit", "standard_ref": "s",
          "evidence": ["e"]})
    code, out = run("ledger.py", "append", str(root), "--actor", "gate",
                    "--class", "refutation_attempted",
                    "--payload", json.dumps({"skeptic": "gate", "claim_id": "c1",
                                             "verdict": "survives", "checklist_ref": "y"}))
    assert code == 3, out


def test_deliverable_int_and_string_are_the_same_deliverable(tmp_path):
    """The deliverable is an Issue number agents write as 42, "42", or "#42". Raw == made the chain
    reject a phase whose predecessor is visibly present — an unreproducible failure in an unattended run."""
    seed(tmp_path, "r", "phase_started", {"deliverable": 42, "phase": "requirements", "role": "r"})
    seed(tmp_path, "g", "phase_admitted",
         {"deliverable": 42, "phase": "requirements", "verdict": "pass",
          "evidence_ref": "e", "admitter": "g"})
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "r",
                    "--class", "phase_started",
                    "--payload", '{"deliverable":"#42","phase":"design","role":"r"}')
    assert code == 0, out


# ── views はスキーマを単一の情報源とする（docs/11 §0c の申し送り A-1）─────────
# 以前は ledger.py に13件をハードコードしていたが、スキーマは26件を宣言していた。実害:
# /org-work が parts_inventory を引けず起動せず、gate の context_pack 3件と skeptic の 2件が
# すべて未実装で、SoD の checker が判断材料を取得できないのに org_lint は pass していた。
def test_every_schema_view_is_resolvable(tmp_path):
    """スキーマが定義するビューは、すべて ledger.py が引けること。"""
    import yaml
    schema = yaml.safe_load((TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"))
    for vid in (schema.get("views") or {}):
        code, out = run("ledger.py", "view", str(tmp_path), vid)
        assert code == 0, f"view '{vid}' が引けない: {out}"


def test_gate_and_skeptic_context_packs_are_resolvable(tmp_path):
    """SoD の checker が判断材料を引けること — これが引けないなら maker≠checker は空文。"""
    import yaml
    org = yaml.safe_load((TEMPLATE / "organization.yaml").read_text(encoding="utf-8"))
    universal = {"intent_block", "doctrine"}
    for r in org["roles"]:
        if r["id"] not in ("gate", "skeptic"):
            continue
        for v in r.get("context_pack", []):
            if v in universal:
                continue
            code, out = run("ledger.py", "view", str(tmp_path), v)
            assert code == 0, f"{r['id']} の context_pack '{v}' が引けない: {out}"


def test_unknown_view_is_still_rejected(tmp_path):
    code, out = run("ledger.py", "view", str(tmp_path), "no_such_view")
    assert code == 2 and "unknown view" in out


# ── phase の親継承（申し送り B-2）────────────────────────────────────────────
# founding は objective 単位で requirements/design を admit するが、/org-work は task Issue 番号を
# deliverable にする。別の文字列なので連鎖せず、指示どおり進めても task #1 が弾かれた。


def test_a_task_without_a_parent_is_still_gated(tmp_path):
    """継承は親を明示した場合だけ。無関係な task が素通りしてはならない。"""
    seed(tmp_path, "sup", "phase_started", {"deliverable": "1", "phase": "requirements", "role": "s"})
    seed(tmp_path, "gate", "phase_admitted",
         {"deliverable": "1", "phase": "requirements", "verdict": "pass",
          "evidence_ref": "e", "admitter": "gate"})
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "sup",
                    "--class", "phase_started",
                    "--payload", json.dumps({"deliverable": "9", "phase": "design", "role": "eng"}))
    assert code == 3, out


# ── org_cycle: 配管の自動化（docs/11 §0d）─────────────────────────────────────
# 実地で Issue 2件あたり11コマンドを手打ちしており、18 Issue で約90回になっていた。
# とりわけ parent を目で拾って手打ちしていたため、親継承（§2）の実装が活きていなかった。


# ── 実地: 予算 cap が日常の後片付けを止めていた（1日5回発火・実害ゼロ）───────
def test_regenerable_cleanup_is_not_metered():
    """cap は irreversibility を測る。作り直せる対象は「取り消せない影響」ではない。"""
    import importlib.util
    hook = TOOLS.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_c", hook)
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    for cmd in ("rm -rf .orgforge/wt/issue-7", "rm -rf node_modules",
                "rm -rf dist/", "rm -rf __pycache__"):
        dim, w = h._asset_dimension("Bash", {"command": cmd})
        assert w == 0, f"後片付けが課金されている: {cmd} -> {w}"


def test_irreversible_deletes_stay_metered():
    """緩めたのは再生成できるものだけ。実ソースも / も遡上も重いまま。"""
    import importlib.util
    hook = TOOLS.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_i", hook)
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    for cmd in ("rm -rf src/", "rm -rf /", "rm -rf ~",
                "rm -rf .orgforge/wt/../../", "DROP TABLE users"):
        dim, w = h._asset_dimension("Bash", {"command": cmd})
        assert w > 0, f"取り消せない操作が無料になった: {cmd}"


# ── 実地: log が Issue にだけ書き、台帳の progress_recorded が0件だった ──────


# ── 実地: 検出器が「学習が使われている」と嘘をついた ─────────────────────
def test_learning_reads_reason_and_rework(tmp_path):
    """rework_requested の `reason` を死因として読む（以前は対象ですらなかった）。"""
    led = tmp_path / "l2"; led.mkdir()
    rows = [{"seq": i, "class": "rework_requested",
             "payload": {"issue": 7, "reason": "同じ死因"}} for i in (1, 2)]
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    p = subprocess.run([sys.executable, str(TOOLS / "learning.py"), "repeats", str(led)],
                       capture_output=True, text=True, timeout=60)
    out = p.stdout + p.stderr
    assert "clean" not in out, f"同じ死因が2回あるのに clean と報告した: {out}"


def test_learning_says_unknown_not_clean_when_causes_unreadable(tmp_path):
    """死因が読めないとき「繰り返していない」と言わない。

    「繰り返していない」と「見えていない」は別。混同すると誤った安心になり、
    検出器が無いより悪い（実地でこれが起きた）。
    """
    led = tmp_path / "l3"; led.mkdir()
    rows = [{"seq": 1, "class": "rework_requested", "payload": {"issue": 7}},
            {"seq": 2, "class": "rework_requested", "payload": {"issue": 7}}]
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    p = subprocess.run([sys.executable, str(TOOLS / "learning.py"), "repeats", str(led)],
                       capture_output=True, text=True, timeout=60)
    out = p.stdout + p.stderr
    assert "unknown" in out and "clean" not in out, out


def test_learning_warns_that_matching_is_by_string(tmp_path):
    """clean を「同じ失敗をしていない」証明として読ませない（文字列一致の限界を明示）。"""
    led = tmp_path / "l4"; led.mkdir()
    rows = [{"seq": 1, "class": "rework_requested", "payload": {"issue": 7, "reason": "端数の偏り"}},
            {"seq": 2, "class": "rework_requested", "payload": {"issue": 7, "reason": "テスト硬化"}}]
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    p = subprocess.run([sys.executable, str(TOOLS / "learning.py"), "repeats", str(led)],
                       capture_output=True, text=True, timeout=60)
    assert "**string**" in p.stdout + p.stderr


# ── 0.17.0: 識別子の別名を台帳から推移的に解決する ──────────────────────


def test_gate_cannot_also_be_skeptic(tmp_path):
    """admit した gate が同じ成果物を refute できない（skeptic ≠ gate）。"""
    env = _led(tmp_path)
    _append(env, "gate", "admission_decided", {"verdict": "admit", "deliverable": "5", "issue": 5})
    p = _append(env, "gate", "refutation_attempted",
                {"verdict": "survives", "deliverable": "5", "issue": 5})
    assert p.returncode != 0, "gate が自分の admit を自分で refute できた"
    q = _append(env, "skeptic", "refutation_attempted",
                {"verdict": "survives", "deliverable": "5", "issue": 5})
    assert q.returncode == 0, f"独立した skeptic まで止めた: {q.stderr}"


def test_report_up_requires_conformance_review(tmp_path):
    """一度も使っていなかった層。委譲→検証→報告の順序が強制されること。"""
    env = _led(tmp_path)
    p = _append(env, "sup", "conformance_reviewed",
                {"supervisor": "sup", "subordinate": "sub", "verdict": "conforms"})
    assert p.returncode != 0, "委譲していない仕事を conformance_reviewed できた"
    q = _append(env, "sup", "report_up", {"supervisor": "sup"})
    assert q.returncode != 0, "検証していない仕事を report_up できた"
    _append(env, "sup", "spec_delegated",
            {"supervisor": "sup", "subordinate": "sub", "spec_ref": "5",
             "contract_ref": "5", "intent_basis_ref": "R.md"})
    r = _append(env, "sup", "conformance_reviewed",
                {"supervisor": "sup", "subordinate": "sub", "verdict": "conforms"})
    assert r.returncode == 0, f"正しい順序が通らない: {r.stderr}"


def test_learning_prints_the_doctrine_command(tmp_path):
    """「doctrine に強化せよ」と言うだけでは強化されない。打つコマンドを出す。"""
    led = tmp_path / "l5" / "ledger"; led.mkdir(parents=True)
    rows = [{"seq": i, "class": "rework_requested",
             "payload": {"issue": 7, "reason": "同じ死因"}} for i in (1, 2)]
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    p = subprocess.run([sys.executable, str(TOOLS / "learning.py"), "repeats", str(led)],
                       capture_output=True, text=True, timeout=60)
    out = p.stdout + p.stderr
    assert "doctrine.py" in out and "propose" in out, "蓄積の経路が示されていない"
    assert "admit" in out, "admit されるまで配られないことが伝わっていない"


# ── 0.18.0: 判定は最新が有効（追記型の台帳で reject が後から来る）─────────


# ── 0.19.0: 実務で「無くて困った」もの ──────────────────────────────────
def test_correction_voids_a_probe(tmp_path):
    """correction{kind: probe} で無効化した記録は board が数えない。

    追記型なので過去は消せない。自由記述の note では機械が読めず、実地では検証用プローブ
    4件が実判定として数えられ board が現実と食い違った。
    """
    led = _write_ledger(tmp_path, "c1", [
        {"seq": 1, "class": "admission_decided", "payload": {"issue": 11, "verdict": "admit"}},
        {"seq": 2, "class": "correction",
         "payload": {"corrects": [1], "kind": "probe", "reason": "仕様検証",
                     "corrected_by": "supervisor"}},
    ])
    out = _status(led).stdout
    assert "skeptic の記録が無い" not in out, f"訂正済みのプローブを実判定として数えた: {out}"


def test_asset_touched_records_authority():
    """本番資産の変更は「誰の権限で入れたか」ごと残す。"""
    src = _cycle_src()
    seg = src[src.index("def cmd_touched"):]
    assert "authority" in seg and "reversible" in seg and "rollback" in seg


# ── 0.21.0: 二重管理をやめる / 冪等キーによる統制の迂回 ────────────────
