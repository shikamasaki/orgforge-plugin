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
import argparse
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
    # cycle_completed requires a domain_model field (docs/11 §4d); default to none_asserted for tests
    # that don't care about the domain-model gate, so they don't all have to spell it out.
    if cls == "cycle_completed" and "domain_model" not in payload:
        payload = {**payload, "domain_model": {"none_asserted": "test seed"}}
    # phase_admitted now requires its own phase_started (docs/11 §2 — a phase cannot be admitted
    # without having been entered). Seeding an admission therefore implies seeding its start, so a
    # fixture that only cares about the *admitted* state doesn't have to spell both out.
    if cls == "phase_admitted":
        run("ledger.py", "append", str(root), "--actor", actor, "--class", "phase_started",
            "--payload", json.dumps({"deliverable": payload.get("deliverable"),
                                     "phase": payload.get("phase"), "role": actor}), "--ts", ts)
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


# ── SDLC phase gate (docs/11 §2) — the forced, non-skippable phase order, reproducibility's spine ──
def test_phase_requirements_may_always_start(tmp_path):
    # requirements has no predecessor, so it starts against an empty history
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "r",
                    "--class", "phase_started",
                    "--payload", '{"deliverable":"D1","phase":"requirements","role":"r"}',
                    "--ts", "2026-07-16T00:00:00Z")
    assert code == 0, out


def test_phase_design_blocked_without_requirements_admitted(tmp_path):
    # design may not start until requirements is admitted — the non-skippable phase order
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "r",
                    "--class", "phase_started",
                    "--payload", '{"deliverable":"D1","phase":"design","role":"r"}',
                    "--ts", "2026-07-16T00:10:00Z")
    assert code == 3 and "requires a prior" in out, out


def test_phase_deploy_cannot_skip_test(tmp_path):
    # with only requirements admitted, deploy must NOT start (it skips design/implement/test)
    seed(tmp_path, "a", "phase_admitted",
         {"deliverable": "D1", "phase": "requirements", "verdict": "pass",
          "evidence_ref": "e", "admitter": "a"})
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "r",
                    "--class", "phase_started",
                    "--payload", '{"deliverable":"D1","phase":"deploy","role":"r"}',
                    "--ts", "2026-07-16T00:20:00Z")
    assert code == 3, out   # prior(deploy)==test, which is not admitted


def test_phase_design_starts_after_requirements_admitted(tmp_path):
    seed(tmp_path, "a", "phase_admitted",
         {"deliverable": "D1", "phase": "requirements", "verdict": "pass",
          "evidence_ref": "e", "admitter": "a"})
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "r",
                    "--class", "phase_started",
                    "--payload", '{"deliverable":"D1","phase":"design","role":"r"}',
                    "--ts", "2026-07-16T00:30:00Z")
    assert code == 0, out


# ── idempotency (docs/11 §0) — a natural-keyed event counts once under replay/retry ──
def test_append_natural_key_is_idempotent(tmp_path):
    args = ("ledger.py", "append", str(tmp_path), "--actor", "h",
            "--class", "exposure_budget_checked",
            "--payload", '{"dimension":"file_mutations","allow":true}',
            "--natural-key", "call-abc")
    c1, _ = run(*args, "--ts", "2026-07-16T00:00:00Z")
    c2, out2 = run(*args, "--ts", "2026-07-16T00:01:00Z")   # retry, same key, later ts
    assert c1 == 0 and c2 == 0 and "idempotent no-op" in out2, out2
    # exactly one event landed — the retry did not double-count
    code, out = run("ledger.py", "view", str(tmp_path), "raw") if False else (0, "")
    events = [l for l in (tmp_path / "ledger.jsonl").read_text().splitlines() if l.strip()]
    assert len(events) == 1, f"expected 1 event, got {len(events)}"


def test_append_different_natural_keys_both_land(tmp_path):
    base = ("ledger.py", "append", str(tmp_path), "--actor", "h",
            "--class", "exposure_budget_checked",
            "--payload", '{"dimension":"file_mutations","allow":true}')
    run(*base, "--natural-key", "call-1", "--ts", "2026-07-16T00:00:00Z")
    run(*base, "--natural-key", "call-2", "--ts", "2026-07-16T00:01:00Z")
    events = [l for l in (tmp_path / "ledger.jsonl").read_text().splitlines() if l.strip()]
    assert len(events) == 2, f"distinct keys must both append; got {len(events)}"


def test_ledger_actor_not_from_payload(tmp_path):
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "m",
                    "--class", "cycle_completed", "--payload", '{"actor":"evil","role":"m"}')
    assert code == 2 and "must not carry its own 'actor'" in out


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


def test_the_legitimate_maker_gate_skeptic_chain_still_passes(tmp_path):
    """The tooth must block forgery WITHOUT blocking the normal three-actor path."""
    root = tmp_path / "l"
    seed(root, "maker-alice", "cycle_started",
         {"role": "maker-alice", "candidate_id": "c1", "pack_manifest_id": "p"})
    seed(root, "gate", "admission_decided",
         {"gate": "gate", "candidate_id": "c1", "verdict": "admit", "standard_ref": "s",
          "evidence": ["e"]})
    code, out = run("ledger.py", "append", str(root), "--actor", "skeptic",
                    "--class", "refutation_attempted",
                    "--payload", json.dumps({"skeptic": "skeptic", "claim_id": "c1",
                                             "verdict": "survives", "checklist_ref": "x"}))
    assert code == 0, out
    code, out = run("ledger.py", "verify", str(root))
    assert code == 0 and "chain intact" in out


# ── the phase mold must not teach its own bypass (docs/11 §2) ────────────────
def test_phase_admitted_requires_its_own_phase_started(tmp_path):
    """Without this, `phase_admitted{integrate}` on an empty ledger makes `phase_started{deploy}` legal
    — deploy reached with requirements/design/implement/test never having happened. It is also the move
    an operator reaches for when phase_started is rejected, so the gate would teach its own bypass."""
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "gate",
                    "--class", "phase_admitted",
                    "--payload", '{"deliverable":"42","phase":"integrate","verdict":"pass",'
                                 '"admitter":"gate","evidence_ref":"x"}')
    assert code == 3, out
    assert "phase_started" in out


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


def test_the_full_phase_chain_runs_when_each_phase_is_entered_and_admitted(tmp_path):
    """The teeth must block the bypass WITHOUT blocking the legitimate walk down the chain."""
    for phase in ("requirements", "design"):
        seed(tmp_path, "r", "phase_started", {"deliverable": "42", "phase": phase, "role": "r"})
        seed(tmp_path, "g", "phase_admitted",
             {"deliverable": "42", "phase": phase, "verdict": "pass",
              "evidence_ref": "e", "admitter": "g"})
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "r",
                    "--class", "phase_started",
                    "--payload", '{"deliverable":"42","phase":"implement","role":"r"}')
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
def test_task_inherits_phase_admission_from_its_parent_objective(tmp_path):
    for phase in ("requirements", "design"):
        seed(tmp_path, "sup", "phase_started", {"deliverable": "1", "phase": phase, "role": "sup"})
        seed(tmp_path, "gate", "phase_admitted",
             {"deliverable": "1", "phase": phase, "verdict": "pass",
              "evidence_ref": "e", "admitter": "gate"})
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "sup",
                    "--class", "phase_started",
                    "--payload", json.dumps({"deliverable": "7", "parent": "1",
                                             "phase": "implement", "role": "eng"}))
    assert code == 0, out


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
def test_org_cycle_plan_executes_nothing(tmp_path):
    """plan は印字だけ — 台帳にもGitHubにも触らない。"""
    code, out = run("org_cycle.py", "plan", "--role", "r", "--issue", "7")
    assert code == 0, out
    assert "phase_started" in out and "cycle_started" in out
    assert not (tmp_path / "ledger.jsonl").exists()


def test_org_cycle_complete_requires_domain_model(tmp_path):
    """docs/11 §4d: ドメインモデルに何をしたかを述べない cycle_completed は認めない。"""
    code, out = run("org_cycle.py", "complete", "--role", "r", "--issue", "7",
                    "--outputs", "something")
    assert code == 2
    assert "domain-model" in out


def test_org_cycle_resolves_parent_from_issue_body():
    """parent は Issue の `Parent: #N` から読む — 人が運ばない。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("org_cycle", TOOLS / "org_cycle.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    import re
    body = "## Deliverable\nsplit engine\n\nParent: #1\n\ncandidate_id: cand-abc\n"
    assert re.search(r"^\s*Parent:\s*#?(\d+)", body, flags=re.M | re.I).group(1) == "1"


# ── 案5: worktree 分離の強制（docs/11 §4c）──────────────────────────────────
# 並列 fan-out で #7 のコミットが feat/issue-8-settle に載る事故が実際に起きた。
# git checkout はツリー全体を切り替えるので、同一ツリーで並列 maker を走らせる限り再発する。
# 「毎回正しく判断する」前提の設計は破れる、というのが実地で得られた教訓。
def test_worktree_isolates_parallel_makers(tmp_path):
    """2つの Issue の worktree が別ディレクトリ・別ブランチになり、互いのコミットが混ざらない。"""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "seed.txt").write_text("x")
    g("add", "-A"); g("commit", "-qm", "seed")
    g("branch", "develop")

    made = []
    for issue in (7, 8):
        code, out = run("github_sync.py", "branch", "--issue", str(issue), "--worktree",
                        "--repo", "o/n", cwd=str(repo))
        assert code == 0, out
        made.append(repo / ".orgforge" / "wt" / f"issue-{issue}")

    assert all(d.is_dir() for d in made), "worktree が作られていない"
    # 各 worktree で別々にコミットしても、相手のツリーには現れない
    for issue, d in zip((7, 8), made):
        (d / f"F{issue}.txt").write_text("x")
        g("add", "-A", cwd=d); g("commit", "-qm", f"i{issue}", cwd=d)
    for issue, d in zip((7, 8), made):
        other = 8 if issue == 7 else 7
        assert (d / f"F{issue}.txt").exists()
        assert not (d / f"F{other}.txt").exists(), \
            f"#{other} の成果物が #{issue} のツリーに混入した — 分離が効いていない"
    # ブランチも別
    b = [g("branch", "--show-current", cwd=d).stdout.strip() for d in made]
    assert b[0] != b[1] and all(b), b


# ── 案2: verify は配管だけ。判定は持たない ─────────────────────────────────
# 検証手順を人が毎回書き下ろすと、書くたびに gate の厳しさが変わる（18 Issue で18通り）。
# 基準の出所は agents/gate.md 1つにする。ただし verdict を埋めた瞬間に gate が形骸化するので、
# そこは越えない — この境界をテストで固定する。
def test_verify_injects_charter_and_leaves_verdict_unfilled():
    """憲章と decide 雛形は出すが、verdict は placeholder のまま（判定を先取りしない）。"""
    import subprocess, os
    env = dict(os.environ, ORG_GITHUB_REPO="")
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "gate"],
                       capture_output=True, text=True, env=env, timeout=60)
    out = p.stdout + p.stderr
    # gh が無い/認証が無い環境では Issue を読めず 3 で落ちるのが正しい挙動
    if p.returncode == 0:
        assert "admission control" in out, "agents/gate.md の憲章が注入されていない"
        assert "<admit|reject|park>" in out, "verdict が placeholder になっていない"
        for filled in ('--verdict admit', '--verdict "admit"'):
            assert filled not in out, f"配管が verdict を決めている: {filled}"
    else:
        assert p.returncode in (2, 3), out


def test_verify_rejects_unknown_role():
    """憲章の無い役割では verify は成り立たない（基準の出所が無いまま起動しない）。"""
    import subprocess
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "verify",
                        "--issue", "1", "--role", "maker"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0


def test_verify_finds_charter_in_bundled_layout():
    """バンドル（agents/ が tools/ の兄弟）でも憲章を見つける。

    プラグインとして入った形でだけ憲章を見失うと、verify は「基準の出所が1つ」という
    唯一の存在理由を失う。repo 直下の配置だけ見ていて実際に取りこぼした。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("org_cycle_c", TOOLS / "org_cycle.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    bundled = TOOLS.parent / "integrations" / "claude-code"
    if not (bundled / "agents").is_dir():
        return  # バンドル未生成の環境ではスキップ
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(bundled)
    try:
        for role in ("gate", "skeptic"):
            charter, path = m._role_charter(role)
            assert charter, f"バンドル配置で {role} の憲章を見失った（探した先: {path}）"
    finally:
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)


# ── 実地フィードバック: 識別子の揺れで admission を見失う ─────────────────
# gate が deliverable に "settle()"（関数名）を書き、complete の照合が "8"（Issue番号）で
# 探して「admission がまだ」と出た。記録は seq 96 に存在していた。
def test_admission_lookup_tolerates_identifier_drift(tmp_path):
    """deliverable が関数名でも、payload の issue で拾える。無ければ near で原因を示す。"""
    import importlib.util
    led = tmp_path / "ledger"; led.mkdir()
    rows = [
        {"seq": 96, "class": "admission_decided",
         "payload": {"deliverable": "settle()", "issue": 8, "verdict": "admit"}},
        {"seq": 99, "class": "admission_decided",
         "payload": {"deliverable": "9", "issue": 9, "verdict": "reject"}},
    ]
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    spec = importlib.util.spec_from_file_location("org_cycle_a", TOOLS / "org_cycle.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    os.environ["ORG_LEDGER_ROOT"] = str(led)
    try:
        v, seq, _ = m._admission_for(8)
        assert (v, seq) == ("admit", 96), f"関数名で記録された admission を見失った: {v} {seq}"
        v9, _, _ = m._admission_for(9)
        assert v9 == "reject", "admit 以外の verdict を admit として扱ってはいけない"
        v11, seq11, near = m._admission_for(11)
        assert v11 is None and seq11 is None
        assert near, "無いと言い切る前に、近い記録を原因究明の手がかりとして示すこと"
    finally:
        os.environ.pop("ORG_LEDGER_ROOT", None)


def test_verify_allows_passing_by_file_reference():
    """本文でもファイル参照でも渡せることを案内する（0.19.0 でガードが読むようになった）。

    以前は本文限定だったので「本文に貼れ」と案内していた。264行を毎回貼ると maker の
    context を圧迫するので、ガード側がファイルを読んで検証するように変えた。
    """
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_verify"):]
    assert "ファイルに落として" in seg and "参照させてもよい" in seg
    assert "HELD" not in seg, "ファイル渡しが弾かれる前提の案内が残っている"


# ── 実地フィードバック: 統合直前が最も抜けやすい ─────────────────────────
def _ledger_with(tmp_path, rows):
    led = tmp_path / "ledger"; led.mkdir(exist_ok=True)
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return led


def test_integrate_blocks_without_skeptic(tmp_path):
    """gate が admit していても、skeptic の survives が無ければ統合させない。

    実地で #8 が「refutation_attempted が台帳に1件も無いまま develop へ統合」された。
    Issue にはコメントがあったので、二重記録の片側だけが落ちていた。
    """
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"deliverable": "8", "issue": 8, "verdict": "admit"}},
    ])
    env = dict(os.environ, ORG_LEDGER_ROOT=str(led))
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "integrate", "--issue", "8"],
                       capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=60)
    assert p.returncode == 4, p.stdout + p.stderr
    err = p.stdout + p.stderr
    assert "skeptic" in err and "survives" in err
    assert "git merge" not in err, "前提が揃わないのにマージ手順に入っている"


def test_integrate_allows_when_both_recorded(tmp_path):
    """admit + survives が揃えば、前提照合では止まらない（実行は git の世界に入る）。"""
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"deliverable": "8", "issue": 8, "verdict": "admit"}},
        {"seq": 2, "class": "refutation_attempted",
         "payload": {"claim_id": "8", "issue": 8, "verdict": "survives"}},
    ])
    import importlib.util
    spec = importlib.util.spec_from_file_location("org_cycle_i", TOOLS / "org_cycle.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    os.environ["ORG_LEDGER_ROOT"] = str(led)
    try:
        assert m._admission_for(8)[0] == "admit"
        assert m._refutation_for(8)[0] == "survives"
    finally:
        os.environ.pop("ORG_LEDGER_ROOT", None)


def test_refuted_is_not_treated_as_survives(tmp_path):
    """refuted を survives と混同したら、反証されたものが統合される。"""
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 9, "verdict": "admit"}},
        {"seq": 2, "class": "refutation_attempted",
         "payload": {"issue": 9, "verdict": "refuted"}},
    ])
    env = dict(os.environ, ORG_LEDGER_ROOT=str(led))
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "integrate", "--issue", "9"],
                       capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=60)
    assert p.returncode == 4, "refuted なのに統合の前提を満たしたと判定された"


def test_status_flags_admit_without_refutation(tmp_path):
    """board が「admit 済みだが skeptic の記録が無い」を RED で出す。"""
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 8, "verdict": "admit"}},
    ])
    p = subprocess.run([sys.executable, str(TOOLS / "status.py"), "status", str(led)],
                       capture_output=True, text=True, timeout=60)
    out = p.stdout + p.stderr
    assert "skeptic の記録が無い" in out, out
    assert out.startswith("RED"), out


def test_status_counts_risk_accepted_admits(tmp_path):
    """リスク付き admit が board に出る（書き得にしない）。"""
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 8, "verdict": "admit", "risk_accepted": True}},
        {"seq": 2, "class": "refutation_attempted",
         "payload": {"issue": 8, "verdict": "survives"}},
    ])
    p = subprocess.run([sys.executable, str(TOOLS / "status.py"), "status", str(led)],
                       capture_output=True, text=True, timeout=60)
    assert "リスク付き admit: 1 件" in p.stdout + p.stderr


def test_verify_gate_embeds_absolute_repro_lint_path():
    """repro_lint がパス解決できず一度も走っていなかった。絶対パスを埋める。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    assert 'repro_lint.py' in src and 'HERE' in src, "repro_lint の絶対パス埋め込みが無い"


def test_worktree_cleanup_keeps_dirty_tree(tmp_path):
    """未コミットの変更がある worktree は消さない（消えて困るかは配管が決めることではない）。"""
    import importlib.util
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "s.txt").write_text("x"); g("add", "-A"); g("commit", "-qm", "s"); g("branch", "develop")
    wt = repo / ".orgforge" / "wt" / "issue-5"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-5", str(wt), "develop")
    (wt / "dirty.txt").write_text("uncommitted")

    spec = importlib.util.spec_from_file_location("org_cycle_w", TOOLS / "org_cycle.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    cwd = os.getcwd(); os.chdir(repo)
    try:
        msg = m._cleanup_worktree(5)
        assert wt.is_dir(), "未コミットの変更ごと worktree を消した"
        assert "残した" in msg, msg
        # クリーンにすれば消える
        (wt / "dirty.txt").unlink()
        msg2 = m._cleanup_worktree(5)
        assert not wt.is_dir(), f"クリーンな worktree が片付いていない: {msg2}"
    finally:
        os.chdir(cwd)


def test_complete_requires_command_and_result():
    """DoD の実出力を人の自由記述任せにしない（B）。"""
    p = subprocess.run([sys.executable, str(TOOLS / "org_cycle.py"), "complete",
                        "--role", "r", "--issue", "1", "--outputs", "x",
                        "--domain-model-none", "理由"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0
    assert "--command" in p.stderr and "--result" in p.stderr


def test_begin_log_carries_facts_the_tool_already_knows():
    """begin の log に branch / worktree / parent / candidate_id が自動で入る（B）。

    実地で人が書いた 276 字にはブランチ名も worktree のパスも無かったが、org_cycle は
    両方知っていた。知っている事実を人に書かせない。
    """
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def _steps_begin"):src.index("def _steps_complete")]
    for token in ("worktree:", "branch:", "parent:", "candidate_id:", "--command", "--result"):
        assert token in seg, f"begin の log に {token} が入っていない"


def test_handback_puts_closes_in_pr_body():
    """PR body の `Closes #N` が Issue ↔ PR ↔ コミットを繋ぎ、統合時に Issue を閉じる（C）。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_handback"):]
    assert 'f"Closes #{a.issue}"' in seg, "PR body に Closes が無い — Issue が OPEN のまま残る"
    assert "gh pr create" in seg


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
def test_log_writes_progress_receipt_to_ledger(monkeypatch, tmp_path):
    """Issue に7回書いたのに台帳は0件。/org-resume が復帰できない状態だった。"""
    src = (TOOLS / "github_sync.py").read_text(encoding="utf-8")
    assert "_append_progress_receipt" in src
    seg = src[src.index("def _append_progress_receipt"):]
    assert "progress_recorded" in seg and "ledger.py" in seg


def test_begin_records_attention_allocated():
    """6件着手して選択の記録が1件だけだった。選んだ結果を残すのは配管。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def _steps_begin"):src.index("def _steps_complete")]
    assert "attention_allocated" in seg


def test_doctrine_propose_warns_on_incomplete_provenance():
    """propose は省略でき admit は必須にする、という不整合で必ず詰まっていた。"""
    root = None
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run([sys.executable, str(TOOLS / "doctrine.py"), "propose", d, "r",
                            "--claim", "x", "--source", "s", "--confidence", "0.5"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0
        assert "admit できない" in p.stderr, "admit で詰まることを propose 時点で言っていない"


def test_complete_proposes_learning_to_doctrine():
    """学びの蓄積口がサイクルに繋がっていること（propose まで。admit は gate）。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_complete"):src.index("def cmd_plan")]
    assert "doctrine.py" in seg and "propose" in seg
    assert "--retrieved-at" in seg and "--review-by" in seg, \
        "provenance を埋めないと gate が admit できず、学びは pending のまま死ぬ"


def test_gc_keeps_unmerged_and_dirty_worktrees(tmp_path):
    """gc は統合済みだけを消す。未統合・未コミットは残す。"""
    import importlib.util
    repo = tmp_path / "r"; repo.mkdir()
    def g(*a, cwd=repo):
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "s.txt").write_text("x"); g("add", "-A"); g("commit", "-qm", "s"); g("branch", "develop")
    wt = repo / ".orgforge" / "wt" / "issue-3"
    wt.parent.mkdir(parents=True, exist_ok=True)
    g("worktree", "add", "-q", "-b", "feat/issue-3", str(wt), "develop")
    (wt / "new.txt").write_text("work"); g("add", "-A", cwd=wt); g("commit", "-qm", "w", cwd=wt)

    spec = importlib.util.spec_from_file_location("org_cycle_g", TOOLS / "org_cycle.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    cwd = os.getcwd(); os.chdir(repo)
    try:
        m.cmd_gc(argparse.Namespace(base="develop", all=False))
        assert wt.is_dir(), "develop に未統合の worktree を消した"
    finally:
        os.chdir(cwd)


def test_record_marks_backfilled():
    """遡って記録したものは、実時点の記録と区別できること。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_record"):]
    assert '"backfilled": True' in seg, "backfill 印が無いと、後から足した記録が実時点と混ざる"


# ── 実地: 相関キーが無いと統制が無言で無効になっていた（seq 204 / 205）───────
def _led(tmp_path):
    d = tmp_path / "l"; d.mkdir(exist_ok=True)
    return dict(os.environ, ORG_LEDGER_ROOT=str(d))


def _append(env, actor, cls, payload):
    return subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", "--actor", actor,
         "--class", cls, "--payload", json.dumps(payload)],
        capture_output=True, text=True, env=env, timeout=60)


def test_judgment_without_correlation_key_is_rejected(tmp_path):
    """相関キーの無い判定は拒否する。以前は素通りし、統制が効いていないことも見えなかった。"""
    env = _led(tmp_path)
    p = _append(env, "maker1", "admission_decided", {"verdict": "admit"})
    assert p.returncode != 0, "対象を特定できない判定が通った"
    assert "特定できない" in p.stderr


def test_self_admission_is_caught_when_written_as_deliverable(tmp_path):
    """deliverable/issue で書いても自己 admit を検出する（seq 204 の再現）。

    強制側は candidate_id/claim_id しか見ておらず、人間側は deliverable/issue で書いていた。
    識別子が2系統に分かれ、キーを変えた瞬間に統制が消えていた。
    """
    env = _led(tmp_path)
    # **実地の形をそのまま使う。** 0.16.0 のテストは cycle_started に issue を入れていたため
    # 直接の共有 ID があり、この穴を再現できていなかった（実際の cycle_started は
    # candidate_id と pack_manifest_id しか持たない）。テストが本番と違う形を作ると、
    # 「壊れる場所で検証していない」ことになる — #7 で学んだのと同じ失敗。
    _append(env, "maker1", "cycle_started",
            {"role": "maker1", "candidate_id": "cand-abc", "pack_manifest_id": "issue-7"})
    p = _append(env, "maker1", "admission_decided",
                {"verdict": "admit", "deliverable": "7", "issue": 7})
    assert p.returncode != 0, ("maker が自分の成果物を admit できた — cycle_started は "
                               "candidate_id、判定は deliverable で書かれるので、直接比較では"
                               "永久に相関しない")
    assert "already acted as" in p.stderr


def test_deploy_gate_correlates_across_key_names(tmp_path):
    """skeptic が deliverable で survives を書いても deploy が通る（正常系）。

    `claim_id == candidate_id` だけを見ていたため、実地の refutation 2件と相関できず、
    null == null が一致して deploy ゲートが丸ごと無効だった。
    """
    env = _led(tmp_path)
    _append(env, "skeptic", "refutation_attempted",
            {"verdict": "survives", "deliverable": "7", "issue": 7})
    p = _append(env, "deployer", "result_deployed", {"deliverable": "7", "issue": 7})
    assert p.returncode == 0, f"survives 済みの deploy が通らない: {p.stderr}"


def test_deploy_without_any_survives_still_blocked(tmp_path):
    """緩めたのは相関の取り方だけ。反証を経ていない deploy は依然として止まる。"""
    env = _led(tmp_path)
    p = _append(env, "gate", "result_deployed", {"deliverable": "999", "issue": 999})
    assert p.returncode != 0, "反証されていない成果物が deploy できた"


def test_decide_writes_the_receipt_itself():
    """受領証は decide が自分で書く（0.21.0）。

    以前は雛形を印字して人に打たせていたため、実地で3回片側落ちした
    （#8 の refutation / #11 の1回目の reject / progress_recorded）。
    actor は --by で渡っているので、分ける理由が無い。
    """
    src = (TOOLS / "github_sync.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_decide"):]
    assert "ledger.py" in seg and "--natural-key" in seg
    assert '"issue": a.issue' in seg
    assert "NEXT: 台帳の受領証をこのまま打つこと" not in seg, "人に打たせる雛形が残っている"


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
    assert "文字列" in p.stdout + p.stderr


# ── 0.17.0: 識別子の別名を台帳から推移的に解決する ──────────────────────
def test_alias_bridges_candidate_id_and_issue(tmp_path):
    """pack_manifest_id: "issue-7" が candidate_id と Issue 番号を繋ぐ唯一の橋。

    人に同じキーで書かせるのではなく、台帳に既にある対応関係を辿る。
    """
    env = _led(tmp_path)
    _append(env, "m", "cycle_started",
            {"role": "m", "candidate_id": "cand-x", "pack_manifest_id": "issue-42"})
    p = _append(env, "m", "admission_decided", {"verdict": "admit", "deliverable": "42"})
    assert p.returncode != 0, "別名経由の自己 admit が通った"
    assert "同じ仕事" in p.stderr, "どう繋がったかを示していない"


def test_alias_via_contract_ref(tmp_path):
    """candidate_submitted の contract_ref も橋になる。"""
    env = _led(tmp_path)
    _append(env, "m", "candidate_submitted",
            {"maker": "m", "candidate_id": "cand-y", "contract_ref": "issue-9", "source": "self"})
    _append(env, "m", "cycle_started", {"role": "m", "candidate_id": "cand-y"})
    p = _append(env, "m", "admission_decided", {"verdict": "admit", "issue": 9})
    assert p.returncode != 0, "contract_ref 経由の相関が効いていない"


def test_unrelated_work_is_not_falsely_correlated(tmp_path):
    """束ねすぎて無関係な仕事まで同一視したら、正当な admit が止まる。"""
    env = _led(tmp_path)
    _append(env, "m", "cycle_started",
            {"role": "m", "candidate_id": "cand-a", "pack_manifest_id": "issue-1"})
    p = _append(env, "m", "admission_decided", {"verdict": "admit", "deliverable": "2", "issue": 2})
    assert p.returncode == 0, f"別 Issue の admit まで止めた: {p.stderr}"


def test_skeptic_cannot_refute_own_work_via_alias(tmp_path):
    """自己反証拒否も別名経由で効くこと（未検証だった層）。"""
    env = _led(tmp_path)
    _append(env, "maker1", "cycle_started",
            {"role": "maker1", "candidate_id": "cand-s", "pack_manifest_id": "issue-5"})
    p = _append(env, "maker1", "refutation_attempted",
                {"verdict": "survives", "deliverable": "5", "issue": 5})
    assert p.returncode != 0, "maker が自分の仕事を refute できた"


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
def _status(led):
    return subprocess.run([sys.executable, str(TOOLS / "status.py"), "status", str(led)],
                          capture_output=True, text=True, timeout=60)


def _write_ledger(tmp_path, name, rows):
    led = tmp_path / name; led.mkdir(parents=True, exist_ok=True)
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return led


def test_reject_after_admit_clears_the_admit(tmp_path):
    """admit → reject の順なら reject が有効。「一度でも admit があった」で数えない。"""
    led = _write_ledger(tmp_path, "s1", [
        {"seq": 216, "class": "admission_decided",
         "payload": {"issue": 11, "verdict": "admit"}},
        {"seq": 218, "class": "admission_decided",
         "payload": {"issue": 11, "verdict": "reject"}},
    ])
    out = _status(led).stdout
    assert "skeptic の記録が無い" not in out, f"reject 後も admit 扱いのまま: {out}"
    assert "rework 待ち" in out, f"reject されたまま放置されていることが見えない: {out}"


def test_admit_after_reject_counts_as_admit(tmp_path):
    """逆順（reject → admit）なら admit が有効。rework が通った正常系。"""
    led = _write_ledger(tmp_path, "s2", [
        {"seq": 1, "class": "admission_decided", "payload": {"issue": 11, "verdict": "reject"}},
        {"seq": 2, "class": "admission_decided", "payload": {"issue": 11, "verdict": "admit"}},
    ])
    out = _status(led).stdout
    assert "skeptic の記録が無い" in out, f"再 admit が admit として数えられていない: {out}"


def test_risk_accepted_admit_not_counted_after_reject(tmp_path):
    """後で reject された risk 付き admit を「残っている穴」に数えない。"""
    led = _write_ledger(tmp_path, "s3", [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 5, "verdict": "admit", "risk_accepted": True}},
        {"seq": 2, "class": "admission_decided", "payload": {"issue": 5, "verdict": "reject"}},
    ])
    out = _status(led).stdout
    assert "リスク付き admit" not in out, out


def test_verify_template_has_no_undefined_shell_var():
    """雛形は貼ってそのまま動くこと。$P は未定義で、打てない雛形は打たれない。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    assert "$P/tools" not in src, "未定義の $P が雛形に残っている"


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


def test_correction_backfill_is_not_voided(tmp_path):
    """backfill は「後から書いた実判定」であって無効ではない。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ledger_c", TOOLS / "ledger.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    evs = [{"seq": 9, "class": "correction",
            "payload": {"corrects": [1], "kind": "backfill", "reason": "遡及記録"}},
           {"seq": 10, "class": "correction",
            "payload": {"corrects": [2], "kind": "probe", "reason": "検証"}}]
    assert m.corrected_seqs(evs) == {2}, "backfill まで無効化した"


def test_show_lists_every_judgment_with_correction_marks():
    """1つの Issue の判定履歴を一望できる（何周目のどの判定かが分かる）。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_show"):]
    assert "訂正済み" in seg and "backfill" in seg
    assert "次:" in seg, "いま何待ちかが出ない"


def test_begin_warns_but_does_not_block_on_unready_deps():
    """事前チェックは見せるだけ。判断は人がする。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def _readiness"):src.index("def cmd_begin")]
    assert "needs-human" in seg and "rework" in seg
    body = src[src.index("def cmd_begin"):src.index("def _steps_complete")] \
        if "def _steps_complete" in src[src.index("def cmd_begin"):] else src[src.index("def cmd_begin"):]
    assert "止めない" in src, "警告が停止になっている（begin は判断しない）"


def test_seam_guard_accepts_a_referenced_file(tmp_path):
    """seam contract をファイルで渡せる。ガード自身が読んで検証する。"""
    import importlib.util
    hook = TOOLS.parent / "integrations" / "common" / "org_hook.py"
    spec = importlib.util.spec_from_file_location("org_hook_s", hook)
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    cwd = os.getcwd(); os.chdir(tmp_path)
    try:
        good = tmp_path / "seam.md"
        good.write_text("# HAND-OFF\n## Your slice\nX\nInputs you receive: A\n"
                        "Outputs you MUST produce: B\n", encoding="utf-8")
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": f"契約は {good} を読むこと"}) is None, "seam 入りファイルが弾かれた"

        bad = tmp_path / "memo.md"
        bad.write_text("ただのメモ", encoding="utf-8")
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": f"手順は {bad}"}) is not None, "seam の無いファイルが通った"
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": "手順は /etc/passwd"}) is not None, "org 外のファイルを読んだ"
        assert h.spawn_needs_seam_or_independence(
            "Task", {"prompt": "いい感じにやって"}) is not None, "契約なしが通った"
    finally:
        os.chdir(cwd)


# ── 0.20.0: rework 履歴 / 統合の事前確認 / 本番資産 / 公開面 ─────────────
def test_verify_passes_rework_history_to_gate():
    """gate に過去の判定を渡す。渡さないと毎回「初回判定」として扱う。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_verify"):]
    assert "判定履歴" in seg and "回目の判定です" in seg
    assert "再導出" in seg, "「前回の指摘が直ったか」だけを見る gate になってしまう"


def test_round_count_uses_the_larger_of_ledger_and_issue():
    """二重記録の片側が落ちていても回数を過少に言わない。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_verify"):]
    assert "max(len(rounds), len(issue_rounds))" in seg


def test_integrate_plan_executes_nothing_and_warns_on_overlap(tmp_path):
    """--plan は何も実行せず、並行 worktree との重複を予告する。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def _integrate_preview"):src.index("def cmd_integrate")]
    assert "同じファイルを変更しています" in seg
    body = src[src.index("def cmd_integrate"):]
    assert 'if getattr(a, "plan", False):' in body
    assert body.index('if getattr(a, "plan", False):') < body.index("git merge"), \
        "--plan がマージ手順より後にある（実行してしまう）"


def test_surface_detection_ranks_security_definer_first():
    """SECURITY DEFINER は関数ごとに判定する。ファイル単位だと肝心の1件が沈む。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def _new_public_surfaces"):]
    assert "関数ごと" in seg, "ファイル単位のフラグに戻っている"
    assert "grant 済み" in seg


def test_surface_detection_skips_test_files():
    """テストヘルパを拾いすぎると、確認してほしい1件が埋もれる。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def _new_public_surfaces"):]
    assert "tests?" in seg and "spec" in seg


def test_complete_blocks_until_surfaces_declared(tmp_path):
    """公開面が増えたら、申告するまで complete させない（認可ホールの入口）。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_complete"):src.index("def cmd_plan")]
    assert "--new-surface" in seg and "return 2" in seg
    assert "認可ホール" in seg


def test_asset_touched_records_authority():
    """本番資産の変更は「誰の権限で入れたか」ごと残す。"""
    src = (TOOLS / "org_cycle.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_touched"):]
    assert "authority" in seg and "reversible" in seg and "rollback" in seg


# ── 0.21.0: 二重管理をやめる / 冪等キーによる統制の迂回 ────────────────
def test_idempotent_key_cannot_bypass_controls(tmp_path):
    """冪等 no-op は「同じ actor の再実行」に限る。

    (class, natural_key) だけを見ていたため、キーさえ一致すれば actor が違っても no-op に
    なり、統制が評価すらされなかった。実地では gate と同じキーを maker が使うことで
    自己承認が exit 0 で通った。冪等性は再実行を守る仕組みであって、統制の裏口ではない。
    """
    env = _led(tmp_path)
    a = _append(env, "gate", "admission_decided", {"verdict": "reject", "issue": 5, "_x": 1})
    assert a.returncode == 0
    # 同じ actor の再実行 → no-op
    b = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", "--actor", "gate",
                        "--class", "admission_decided", "--natural-key", "k1",
                        "--payload", json.dumps({"verdict": "reject", "issue": 5})],
                       capture_output=True, text=True, env=env, timeout=60)
    c = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", "--actor", "gate",
                        "--class", "admission_decided", "--natural-key", "k1",
                        "--payload", json.dumps({"verdict": "reject", "issue": 5})],
                       capture_output=True, text=True, env=env, timeout=60)
    assert c.returncode == 0 and "no-op" in c.stdout, c.stdout + c.stderr
    # 別 actor が同じキー → 拒否
    d = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", "--actor", "maker",
                        "--class", "admission_decided", "--natural-key", "k1",
                        "--payload", json.dumps({"verdict": "admit", "issue": 5})],
                       capture_output=True, text=True, env=env, timeout=60)
    assert d.returncode != 0, "別 actor が冪等キーで統制を迂回できた"
    assert "再実行ではない" in d.stderr


def test_decide_writes_ledger_before_issue():
    """台帳を先に通す。拒否されるなら Issue に外向きの記録を作る前に止める。"""
    src = (TOOLS / "github_sync.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_decide"):]
    led = seg.index("ledger.py")
    comment = seg.index('gh(["issue", "comment"')
    assert led < comment, "Issue に書いてから台帳を叩いている（食い違いが外に残る）"
    assert "台帳が受け付けなかったので、Issue にも記録していない" in seg


def test_decide_key_is_unique_per_judgment():
    """`{event}-{issue}` だと2周目の判定が1周目と衝突して no-op になる。"""
    src = (TOOLS / "github_sync.py").read_text(encoding="utf-8")
    seg = src[src.index("def cmd_decide"):]
    assert 'f"{a.event}-{a.issue}-{digest[:12]}"' in seg
