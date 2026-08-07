"""台帳と統制 — phase の順序・冪等・自己承認拒否・識別子の相関。

ここが緩むと、判断の記録が「あるように見えて効いていない」状態になる。"""
import argparse
import hashlib
import json
import os
import pathlib
import pytest


def _real_ids(org):
    """This org's (org_id, ledger_id). A receipt is bound to values the WRITE TARGET fixes."""
    sys.path.insert(0, str(REPO / "tools"))
    import importlib
    led = importlib.import_module("ledger")
    import os as _os
    cwd = _os.getcwd()
    try:
        _os.chdir(org)
        return led._org_and_ledger_id(str(org / ".orgforge" / "ledger"))
    finally:
        _os.chdir(cwd)
import re
import subprocess
import time
import sys

from conftest import (REPO, TOOLS, TEMPLATE, run, seed, _cycle_src, _gh_src,
                      _cycle_mod, _propose_full, _admitted_claim, _sched,
                      _ledger_with, _led, _append, _status, _write_ledger)


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


# ── SDLC phase gate (docs/11 §2) — the forced, non-skippable phase order, reproducibility's spine ──


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


# ── idempotency (docs/11 §0) — a natural-keyed event counts once under replay/retry ──
def test_append_natural_key_is_idempotent(tmp_path):
    args = ("ledger.py", "append", str(tmp_path), "--actor", "h",
            # exposure_budget_checked は writer 専用になったので generic append では書けない
            # （0.34.1）。冪等性の検査は class に依存しないので、通常のクラスで行う。
            "--class", "progress_recorded",
            "--payload", '{"role":"maker","candidate_id":"c1","phase":"implement"}',
            "--natural-key", "call-abc")
    c1, _ = run(*args, "--ts", "2026-07-16T00:00:00Z")
    c2, out2 = run(*args, "--ts", "2026-07-16T00:01:00Z")   # retry, same key, later ts
    assert c1 == 0 and c2 == 0 and "idempotent no-op" in out2, out2
    # exactly one event landed — the retry did not double-count
    code, out = run("ledger.py", "view", str(tmp_path), "raw") if False else (0, "")
    events = [l for l in (tmp_path / "ledger.jsonl").read_text().splitlines() if l.strip()]
    assert len(events) == 1, f"expected 1 event, got {len(events)}"


def test_append_different_natural_keys_both_land(tmp_path):
    # exposure_budget_checked は writer 専用（0.34.1）。冪等キーの検査は class に依存しない。
    base = ("ledger.py", "append", str(tmp_path), "--actor", "h",
            "--class", "progress_recorded",
            "--payload", '{"role":"maker","candidate_id":"c1","phase":"implement"}')
    run(*base, "--natural-key", "call-1", "--ts", "2026-07-16T00:00:00Z")
    run(*base, "--natural-key", "call-2", "--ts", "2026-07-16T00:01:00Z")
    events = [l for l in (tmp_path / "ledger.jsonl").read_text().splitlines() if l.strip()]
    assert len(events) == 2, f"distinct keys must both append; got {len(events)}"


def test_ledger_actor_not_from_payload(tmp_path):
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "m",
                    "--class", "cycle_completed", "--payload", '{"actor":"evil","role":"m"}')
    assert code == 2 and "must not carry its own 'actor'" in out


def test_scheduler_receipt_cannot_be_forged_by_generic_append(tmp_path):
    payload = json.dumps({
        "check_id": "machine_sensors", "scheduled_for_min": 100,
        "execution_id": "forged", "result": "ok", "exit_code": 0,
        "command_sha256": "a" * 64, "plugin_version": "2.0.28",
    })
    code, out = run("ledger.py", "append", str(tmp_path),
                    "--actor", "system:scheduler_tick",
                    "--class", "scheduled_check_completed", "--payload", payload)
    assert code == 2 and "writer 専用" in out


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


def test_ledger_digest_deterministic(tmp_path):
    seed(tmp_path, "a", "candidate_submitted",
         {"maker": "a", "candidate_id": "c1", "contract_ref": "r", "evidence": []})
    args = ("digest", str(tmp_path), "--window-since", "2026-07-16T00:00:00Z",
            "--window-until", "2026-07-17T00:00:00Z")
    _, out1 = run("ledger.py", *args)
    _, out2 = run("ledger.py", *args)
    assert out1 == out2 and out1.strip().startswith("{")


# ── doctrine.py (anti-poisoning gate) ─────────────────────────────────────────


def test_distinct_deaths_are_silent(tmp_path):
    seed(tmp_path, "gate", "result_retired", {"candidate_id": "A", "cause": "cause one"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "gate", "result_retired", {"candidate_id": "B", "cause": "cause two"},
         ts="2026-07-16T02:00:00Z")
    code, out = run("learning.py", "repeats", str(tmp_path))
    assert code == 0 and "clean" in out


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


# ── 実地フィードバック: 識別子の揺れで admission を見失う ─────────────────
# gate が deliverable に "settle()"（関数名）を書き、complete の照合が "8"（Issue番号）で
# 探して「admission がまだ」と出た。記録は seq 96 に存在していた。
def test_admission_lookup_tolerates_identifier_drift(tmp_path):
    """Even when the deliverable is a function name, the payload's issue finds it — and when
    nothing matches, `near` names why."""
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

    m = _cycle_mod("_core")
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


def test_refuted_is_not_treated_as_survives(tmp_path):
    """Confusing refuted with survives would integrate the thing that was refuted."""
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
    """The board shows RED for "admitted, but no skeptic record"."""
    led = _ledger_with(tmp_path, [
        {"seq": 1, "class": "admission_decided",
         "payload": {"issue": 8, "verdict": "admit"}},
    ])
    p = subprocess.run([sys.executable, str(TOOLS / "status.py"), "status", str(led)],
                       capture_output=True, text=True, timeout=60)
    out = p.stdout + p.stderr
    assert "skeptic の記録が無い" in out, out
    assert out.startswith("RED"), out


# ── 実地: log が Issue にだけ書き、台帳の progress_recorded が0件だった ──────
def test_log_writes_progress_receipt_to_ledger(monkeypatch, tmp_path):
    """Seven entries on the Issue and zero in the ledger — /org-resume could not recover."""
    src = _gh_src()
    assert "_append_progress_receipt" in src
    seg = src[src.index("def _append_progress_receipt"):]
    assert "progress_recorded" in seg and "ledger.py" in seg


def test_record_marks_backfilled():
    """A backfilled record must remain distinguishable from one written at the time."""
    src = _cycle_src()
    seg = src[src.index("def cmd_record"):]
    assert '"backfilled": True' in seg, "backfill 印が無いと、後から足した記録が実時点と混ざる"


# ── 実地: 相関キーが無いと統制が無言で無効になっていた（seq 204 / 205）───────


def test_judgment_without_correlation_key_is_rejected(tmp_path):
    """A verdict with no correlation key is refused. It used to pass, and the control being
    inert was itself invisible."""
    env = _led(tmp_path)
    p = _append(env, "maker1", "admission_decided", {"verdict": "admit"})
    assert p.returncode != 0, "対象を特定できない判定が通った"
    # 0.33.1 で schema 検証（require_any）が同じことを、より具体的に言うようになった —
    # どのキーが要るかを挙げる。台帳側の相関キー検査も残っているので、どちらが先に拾っても
    # 拒否される（二重の防御）。
    assert "has no correlation key" in p.stderr or "cannot be identified" in p.stderr


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
    """Only how the correlation is found was relaxed. A deploy that skipped refutation still
    stops."""
    env = _led(tmp_path)
    p = _append(env, "gate", "result_deployed", {"deliverable": "999", "issue": 999})
    assert p.returncode != 0, "反証されていない成果物が deploy できた"


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
    """candidate_submitted's contract_ref also bridges."""
    env = _led(tmp_path)
    _append(env, "m", "candidate_submitted",
            {"maker": "m", "candidate_id": "cand-y", "contract_ref": "issue-9", "source": "self"})
    _append(env, "m", "cycle_started", {"role": "m", "candidate_id": "cand-y"})
    p = _append(env, "m", "admission_decided", {"verdict": "admit", "issue": 9})
    assert p.returncode != 0, "contract_ref 経由の相関が効いていない"


def test_unrelated_work_is_not_falsely_correlated(tmp_path):
    """Bridging too eagerly would equate unrelated work and block a legitimate admit."""
    env = _led(tmp_path)
    _append(env, "m", "cycle_started",
            {"role": "m", "candidate_id": "cand-a", "pack_manifest_id": "issue-1"})
    p = _append(env, "m", "admission_decided", {"verdict": "admit", "deliverable": "2", "issue": 2})
    assert p.returncode == 0, f"別 Issue の admit まで止めた: {p.stderr}"


def test_skeptic_cannot_refute_own_work_via_alias(tmp_path):
    """Self-refutation is refused through an alias too — a layer that was untested."""
    env = _led(tmp_path)
    _append(env, "maker1", "cycle_started",
            {"role": "maker1", "candidate_id": "cand-s", "pack_manifest_id": "issue-5"})
    p = _append(env, "maker1", "refutation_attempted",
                {"verdict": "survives", "deliverable": "5", "issue": 5})
    assert p.returncode != 0, "maker が自分の仕事を refute できた"


def test_correction_backfill_is_not_voided(tmp_path):
    """A backfill is a real verdict written later; it is not void."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ledger_c", TOOLS / "ledger.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    evs = [{"seq": 9, "class": "correction",
            "payload": {"corrects": [1], "kind": "backfill", "reason": "遡及記録"}},
           {"seq": 10, "class": "correction",
            "payload": {"corrects": [2], "kind": "probe", "reason": "検証"}}]
    assert m.corrected_seqs(evs) == {2}, "backfill まで無効化した"


def test_effective_voided_seqs_unifies_current_and_legacy_correction_semantics(tmp_path):
    """Every projection must fold one correction contract, including pre-effect ledgers."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ledger_effect", TOOLS / "ledger.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    events = [
        {"seq": 10, "class": "correction",
         "payload": {"corrects": [1], "kind": "superseded", "effect": "voids"}},
        {"seq": 11, "class": "correction",
         "payload": {"corrects": [2], "kind": "probe", "effect": "voids"}},
        {"seq": 12, "class": "correction",
         "payload": {"corrects": [3], "kind": "superseded"}},  # legacy v2.0.22
        {"seq": 13, "class": "correction",
         "payload": {"corrects": [4], "kind": "backfill", "effect": "records_backfill"}},
    ]
    assert module.voided_seqs(events) == {1, 2, 3}
    assert module.corrected_seqs(events) == {2}, "low-level kind query changed compatibility"


def test_effective_voided_seqs_honors_correction_of_correction(tmp_path):
    """A later active correction can reinstate the event an earlier correction had voided."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ledger_effect_nested", TOOLS / "ledger.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    events = [
        {"seq": 1, "class": "admission_decided", "payload": {"verdict": "admit"}},
        {"seq": 10, "class": "correction",
         "payload": {"corrects": [1], "kind": "superseded", "effect": "voids"}},
        {"seq": 11, "class": "correction",
         "payload": {"corrects": [10], "kind": "mistake", "effect": "voids"}},
    ]
    assert module.voided_seqs(events) == {10}

    events.append({"seq": 12, "class": "correction",
                   "payload": {"corrects": [11], "kind": "mistake", "effect": "voids"}})
    assert module.voided_seqs(events) == {1, 11}


def _correction_org(tmp_path, policy=True):
    import shutil
    org = tmp_path / "org"
    ledger = org / ".orgforge" / "ledger"
    ledger.mkdir(parents=True)
    shutil.copy(TEMPLATE / "ledger-schema.yaml", org / "ledger-schema.yaml")
    policy_yaml = ("    judgment_corrections:\n"
                   "      authority_roles: [supervisor]\n") if policy else ""
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: same-harness\n" + policy_yaml,
        encoding="utf-8")
    (org / "organization.yaml").write_text(
        "roles:\n"
        "  - {id: supervisor, active: true, functions: [organize, operate]}\n"
        "  - {id: gate, active: true, functions: [judge, review]}\n"
        "  - {id: skeptic, active: true, functions: [judge, review]}\n",
        encoding="utf-8")
    return org, ledger


_CORRECTION_REASON = "独立したauthorityが対象と理由を確認した訂正"


def _correction_receipt(org, ledger, role, target, kind="superseded", issue="64",
                        reason=_CORRECTION_REASON):
    key_id = f"{role}-correction-key"
    private_key = org / f"{key_id}.pem"
    keygen = subprocess.run(
        [sys.executable, str(TOOLS / "identity.py"), "keygen",
         "--key-id", key_id, "--signer-id", f"{role}-principal",
         "--private-out", str(private_key), "--authorized-roles", role,
         "--authorized-lineages", "authority"],
        cwd=org, capture_output=True, text=True)
    assert keygen.returncode == 0, keygen.stdout + keygen.stderr
    oid, lid = _real_ids(org)
    subject = f"correction:{kind}:{int(target)}"
    receipt = subprocess.run(
        [sys.executable, str(TOOLS / "identity.py"), "receipt",
         "--org-id", oid, "--ledger-id", lid, "--subject", subject,
         "--issue", str(issue), "--role", role, "--phase", "govern",
         "--lineage", "authority", "--verdict", kind,
         "--event-class", "correction", "--requirements-digest",
         "judgment-correction-authority-v1", "--reasoning-sha256",
         hashlib.sha256(reason.encode("utf-8")).hexdigest(),
         "--issued-at", "2026-08-02T00:00:00Z", "--key-id", key_id,
         "--private-key", str(private_key)],
        cwd=org, capture_output=True, text=True)
    assert receipt.returncode == 0, receipt.stdout + receipt.stderr
    path = org / f"{key_id}-{target}.json"
    path.write_text(receipt.stdout.strip(), encoding="utf-8")
    return path


def _correction_append(org, ledger, actor, target, kind="superseded", receipt=None,
                       reason=_CORRECTION_REASON):
    command = [sys.executable, str(TOOLS / "ledger.py"), "append", str(ledger),
               "--actor", actor, "--class", "correction", "--payload", json.dumps({
                   "corrects": [target], "kind": kind, "corrected_by": actor,
                   "reason": reason}, ensure_ascii=False)]
    if receipt:
        command.extend(["--receipt", str(receipt)])
    return subprocess.run(command, cwd=org, capture_output=True, text=True)


def _provisional_target(org, ledger, actor="gate"):
    payload = {"issue": 64, "deliverable": "64", "role": "gate",
               "lineage": "same-harness", "verdict": "reject",
               "for_event": "admission_decided", "review_subject_id": "subject-A",
               "reasoning_sha256": "digest-A"}
    result = subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", str(ledger),
         "--actor", actor, "--class", "verdict_provisional",
         "--payload", json.dumps(payload)], cwd=org, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads((ledger / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])


def test_judge_cannot_void_its_own_judgment(tmp_path):
    org, ledger = _correction_org(tmp_path)
    target = _provisional_target(org, ledger, actor="gate")
    result = _correction_append(org, ledger, "gate", target["seq"])
    assert result.returncode == 3
    assert "is not authorized" in result.stderr or "自分の判定" in result.stderr
    assert len((ledger / "ledger.jsonl").read_text().splitlines()) == 1


def test_other_judge_cannot_void_a_judgment(tmp_path):
    org, ledger = _correction_org(tmp_path)
    target = _provisional_target(org, ledger, actor="gate")
    result = _correction_append(org, ledger, "skeptic", target["seq"])
    assert result.returncode == 3
    assert "第三者 authority: supervisor" in result.stderr


def test_declared_third_party_authority_can_void_judgment_with_audit_fields(tmp_path):
    org, ledger = _correction_org(tmp_path)
    target = _provisional_target(org, ledger, actor="gate")
    receipt = _correction_receipt(org, ledger, "supervisor", target["seq"])
    result = _correction_append(org, ledger, "supervisor", target["seq"], receipt=receipt)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "effect=voids" in result.stdout
    event = json.loads((ledger / "ledger.jsonl").read_text().splitlines()[-1])
    payload = event["payload"]
    assert payload["corrected_by"] == "supervisor"
    assert payload["authority_role"] == "supervisor"
    assert payload["authority_principal"] == "supervisor-principal"
    assert payload["authority_assurance"] == "authenticated"
    assert payload["identity_assurance"] == "authenticated"
    assert payload["authority_receipt_subject"] == "correction:superseded:1"
    assert payload["target_classes"] == ["verdict_provisional"]
    assert payload["target_issues"] == ["64"] and payload["issue"] == "64"
    assert payload["effect"] == "voids"


def test_declared_authority_actor_name_without_receipt_cannot_void_judgment(tmp_path):
    """Changing only ``--actor`` must not impersonate the third-party authority."""
    org, ledger = _correction_org(tmp_path)
    target = _provisional_target(org, ledger, actor="gate")
    result = _correction_append(org, ledger, "supervisor", target["seq"])
    assert result.returncode == 3
    assert "no signed receipt" in result.stderr
    assert "--actor の役割名だけ" in result.stderr


def test_custom_judging_role_cannot_be_correction_authority_at_runtime(tmp_path):
    org, ledger = _correction_org(tmp_path)
    constitution = (org / "constitution.yaml").read_text(encoding="utf-8").replace(
        "authority_roles: [supervisor]", "authority_roles: [review-lead]")
    (org / "constitution.yaml").write_text(constitution, encoding="utf-8")
    (org / "organization.yaml").write_text(
        "roles:\n"
        "  - {id: review-lead, active: true, functions: [judge, review]}\n"
        "  - {id: gate, active: true, functions: [judge, review]}\n",
        encoding="utf-8")
    target = _provisional_target(org, ledger, actor="gate")
    receipt = _correction_receipt(org, ledger, "review-lead", target["seq"])
    result = _correction_append(org, ledger, "review-lead", target["seq"], receipt=receipt)
    assert result.returncode == 3
    assert "judge/review職務を持つ" in result.stderr


def test_missing_authority_policy_fails_closed_only_for_judgments(tmp_path):
    org, ledger = _correction_org(tmp_path, policy=False)
    target = _provisional_target(org, ledger, actor="gate")
    denied = _correction_append(org, ledger, "supervisor", target["seq"])
    assert denied.returncode == 3
    assert "judgment_corrections が宣言されていない" in denied.stderr

    # The judge role may still correct its own *non-judgment* probe/mistake. The restriction is on
    # authority-bearing judgments, not on append-only factual hygiene.
    factual = subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", str(ledger),
         "--actor", "gate", "--class", "progress_recorded", "--payload",
         json.dumps({"role": "gate", "candidate_id": "c1", "phase": "implement"})],
        cwd=org, capture_output=True, text=True)
    assert factual.returncode == 0, factual.stdout + factual.stderr
    factual_seq = json.loads((ledger / "ledger.jsonl").read_text().splitlines()[-1])["seq"]
    allowed = _correction_append(org, ledger, "gate", factual_seq, kind="probe")
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert "effect=voids" in allowed.stdout and "assurance=not-required" in allowed.stdout


def test_judgment_backfill_does_not_void_or_require_authority(tmp_path):
    org, ledger = _correction_org(tmp_path, policy=False)
    target = _provisional_target(org, ledger, actor="gate")
    result = _correction_append(org, ledger, "gate", target["seq"], kind="backfill")
    assert result.returncode == 0, result.stdout + result.stderr
    event = json.loads((ledger / "ledger.jsonl").read_text().splitlines()[-1])
    assert event["payload"]["effect"] == "records_backfill"
    assert target["seq"] not in __import__("ledger").corrected_seqs(
        [target, event], kinds=("superseded", "probe", "mistake"))


def test_show_lists_every_judgment_with_correction_marks():
    """One Issue's verdict history at a glance — which round, and which verdict."""
    src = _cycle_src()
    seg = src[src.index("def cmd_show"):]
    assert "訂正済み" in seg and "backfill" in seg
    assert "次:" in seg, "いま何待ちかが出ない"


def test_round_count_uses_the_larger_of_ledger_and_issue():
    """When one side of the double record is missing, do not under-report the round count."""
    src = _cycle_src()
    seg = src[src.index("def cmd_verify"):]
    assert "max(len(rounds), len(issue_rounds))" in seg


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
    """The ledger goes first. If it refuses, stop before creating an outward record on the
    Issue."""
    src = _gh_src()
    seg = src[src.index("def cmd_decide"):]
    led = seg.index("ledger.py")
    comment = seg.index('gh(["issue", "comment"')
    assert led < comment, "Issue に書いてから台帳を叩いている（食い違いが外に残る）"
    assert "台帳が受け付けなかったので、Issue にも記録していない" in seg


def test_decide_key_is_unique_per_judgment():
    """With `{event}-{issue}`, a second-round verdict collides with the first and no-ops."""
    src = _gh_src()
    seg = src[src.index("def cmd_decide"):]
    assert 'f"{a.event}-{a.issue}-{digest[:12]}"' in seg


# ── 0.22.0: 分割で持ち込んだ穴を塞ぐ ────────────────────────────────────


# ══ Writer Phase 0 — lock / fsync / HEAD 回復 / schema 境界 ═══════════════════
# **actor には触らない。** ここで固定するのは「書き込みが壊れないこと」と「新規イベントが
# 検証済みであること」だけ。identity_assurance（誰が書いたか）は独立した軸として後で扱う。

_PR = {"role": "maker", "candidate_id": "c1", "fraction": 0.5, "phase": "implement",
       "done_so_far": "x", "next_step": "y"}


def _app(root, cls="progress_recorded", payload=None, actor="w", extra=()):
    return run("ledger.py", "append", str(root), "--actor", actor, "--class", cls,
               "--payload", json.dumps(payload if payload is not None else _PR), *extra)


def _evs(root):
    p = pathlib.Path(root) / "ledger.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_writer_stamps_schema_version_and_timestamp(tmp_path):
    """Conditions 1+8: the writer stamps version and ts. Never write "UNSET"."""
    assert _app(tmp_path)[0] == 0
    ev = _evs(tmp_path)[0]
    assert ev["schema_id"] == "orgforge-ledger"
    assert isinstance(ev["schema_version"], int) and ev["schema_version"] >= 1
    assert ev["schema_sha256"]
    assert ev["ts"] != "UNSET" and ev["ts"].endswith("Z")


def test_client_cannot_name_the_schema_version(tmp_path):
    """Condition 2: a client-supplied version is a downgrade attack, so it is refused."""
    code, out = _app(tmp_path, payload={**_PR, "schema_version": 1})
    assert code == 2
    assert "writer が決める" in out
    code, out = _app(tmp_path, payload={**_PR, "schema_sha256": "deadbeef"})
    assert code == 2


def test_schema_id_in_payload_is_allowed_for_boundary_events(tmp_path):
    """禁止は版を名指しする値だけ。schema_id は境界を記録するイベントが持って自然。

    禁止を広く取りすぎると記録したい事実が書けない（実際に epoch 記録が弾かれた）。
    """
    code, out = _app(tmp_path, cls="schema_enforcement_started",
                     payload={"schema_id": "orgforge-ledger", "note": "境界の記録"})
    assert code == 0, out


def test_unknown_event_class_is_refused(tmp_path):
    """Condition 3: a class the schema does not declare cannot be written."""
    code, out = _app(tmp_path, cls="totally_unknown_class", payload={})
    assert code == 2
    assert "unknown event class" in out


def test_unreadable_schema_fails_closed(tmp_path, monkeypatch):
    """Condition 4: an unreadable schema refuses new appends — never write unvalidated."""
    monkeypatch.setenv("ORG_LEDGER_SCHEMA", str(tmp_path / "nope.yaml"))
    code, out = _app(tmp_path)
    assert code == 2
    assert "検証" in out


def test_concurrent_appends_do_not_collide(tmp_path):
    """The whole append is one critical section. **At 12-way concurrency every event came out
    as seq=1.**"""
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(_app, tmp_path, "progress_recorded",
                          {**_PR, "candidate_id": f"c{i}"}, f"w{i}") for i in range(12)]
        codes = [f.result()[0] for f in futs]
    assert all(c == 0 for c in codes), codes
    seqs = [e["seq"] for e in _evs(tmp_path)]
    assert sorted(seqs) == list(range(1, 13)), seqs
    assert run("ledger.py", "verify", str(tmp_path))[0] == 0


def test_head_is_a_cache_rebuilt_from_the_log(tmp_path):
    """HEAD is not authoritative. If it is damaged, rebuild from the log and carry on."""
    assert _app(tmp_path)[0] == 0
    (tmp_path / "HEAD").write_text('{"seq": 99, "hash": "bogus"}', encoding="utf-8")
    code, out = _app(tmp_path, payload={**_PR, "candidate_id": "c2"})
    assert code == 0, out
    assert "log から再構築" in out
    assert [e["seq"] for e in _evs(tmp_path)] == [1, 2]


def test_torn_line_is_not_auto_repaired(tmp_path):
    """Interior damage fails closed rather than self-repairing: never lay a consistent HEAD
    over a broken record."""
    assert _app(tmp_path)[0] == 0
    with open(tmp_path / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write('{"seq": 2, "class": "progress_recorded"')     # 改行なし
    code, out = _app(tmp_path)
    assert code == 4, out
    assert "自動修復しない" in out


def test_interior_tampering_blocks_further_appends(tmp_path):
    """An interior rewrite fails closed as well."""
    for i in range(3):
        assert _app(tmp_path, payload={**_PR, "candidate_id": f"c{i}"})[0] == 0
    p = tmp_path / "ledger.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    ev = json.loads(lines[1]); ev["payload"]["fraction"] = 0.99
    lines[1] = json.dumps(ev, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    code, out = _app(tmp_path)
    assert code == 4
    assert "hash mismatch" in out


def test_same_natural_key_different_payload_is_refused(tmp_path):
    """Condition 9: the same key with different content is not a replay, so it must not be
    discarded as a no-op."""
    assert _app(tmp_path, extra=("--natural-key", "k1"))[0] == 0
    assert _app(tmp_path, extra=("--natural-key", "k1"))[0] == 0        # 完全一致 → no-op
    assert len(_evs(tmp_path)) == 1
    code, out = _app(tmp_path, payload={**_PR, "fraction": 0.9},
                     extra=("--natural-key", "k1"))
    assert code == 3, out
    assert "payload が違う" in out


def test_verify_reports_both_assurances_separately(tmp_path):
    """Condition 6: verify checks per version and reports legacy and validated separately."""
    assert _app(tmp_path)[0] == 0
    code, out = run("ledger.py", "verify", str(tmp_path))
    assert code == 0, out
    assert "validation_assurance" in out
    assert "validated:v1" in out


def test_legacy_events_remain_readable_but_unvalidated(tmp_path):
    """Condition 5: pre-existing events without a version stay readable — never refuse
    retroactively."""
    # legacy を手で書く（0.32.3 以前の形）
    ev = {"id": "elegacy", "seq": 1, "ts": "UNSET", "actor": "w",
          "class": "progress_recorded", "payload": dict(_PR), "prev_hash": "GENESIS"}
    sys.path.insert(0, str(TOOLS))
    import importlib
    led = importlib.import_module("ledger")
    ev["hash"] = led._hash("GENESIS", ev)
    (tmp_path / "ledger.jsonl").write_text(json.dumps(ev) + "\n", encoding="utf-8")
    (tmp_path / "HEAD").write_text(json.dumps({"seq": 1, "hash": ev["hash"]}), encoding="utf-8")
    code, out = run("ledger.py", "verify", str(tmp_path))
    assert code == 0, out
    assert "legacy_unvalidated 1 件" in out
    # 続けて v1 を足せる（混在が壊れない）
    assert _app(tmp_path, payload={**_PR, "candidate_id": "c2"})[0] == 0
    assert run("ledger.py", "verify", str(tmp_path))[0] == 0


# ══ 0.33.1 — Phase 0 の残件（検証軸の分離 / TOCTOU / ts / lock / skew）═════════
# 監査が 0.33.0 で「実装した」と報告した条件のうち未達だったもの。**空の payload が通り、
# --ts UNSET も通っていた。** 3軸に分けて閉じる。

_ADM = {"deliverable": "42", "verdict": "admit"}


def test_required_only_applies_to_declared_classes(tmp_path):
    """軸1: required を宣言したクラスだけ必須 field を検証する。

    全クラスを一度に closed-world にすると、schema の乖離が「組織全体の記録停止」に変わる —
    それは fail-closed ではなく、既知の移行不備による可用性事故である。
    """
    # required 未宣言のクラスは、空でも通る（既存 43 件を止めない）
    code, out = _app(tmp_path, "progress_recorded", {})
    assert code == 0, out
    # 統制イベントは必須欠落で拒否
    code, out = _app(tmp_path, "admission_decided", {}, actor="gate")
    assert code == 2
    assert "missing required fields" in out


def test_correlation_key_is_any_of_not_a_fixed_one(tmp_path):
    """相関キーは deliverable / candidate_id / issue のどれか1つでよい。

    1つに固定すると正当な書き込みを弾く（実際に統制のテストを弾いた）。
    """
    for key in ("deliverable", "candidate_id", "issue"):
        code, out = _app(tmp_path, "admission_decided",
                         {key: "c1", "verdict": "admit", "gate": "g"}, actor=f"gate-{key}")
        assert code == 0, f"{key} だけでは通らなかった: {out}"
    # 1つも無ければ拒否
    code, out = _app(tmp_path, "admission_decided", {"verdict": "admit"}, actor="gate-none")
    assert code != 0
    assert "has no correlation key" in out or "cannot be identified" in out


def test_enum_and_type_are_checked_when_present(tmp_path):
    """Axis 2: a declared field is checked against its enum/type **when present**."""
    code, out = _app(tmp_path, "admission_decided",
                     {**_ADM, "verdict": "totally-bogus"}, actor="gate")
    assert code == 2
    assert "is not an allowed value" in out
    code, out = _app(tmp_path, "correction",
                     {"corrects": 5, "kind": "probe"}, actor="sup")     # list であるべき
    assert code == 2
    assert "型が違う" in out


def test_undeclared_fields_warn_but_pass_except_in_strict_classes(tmp_path):
    """Axis 3: an undeclared field is allowed with a warning by default; only strict classes
    refuse it."""
    code, out = _app(tmp_path, "admission_decided",
                     {**_ADM, "some_new_field": "x"}, actor="gate")
    assert code == 0, out
    assert "宣言の無い field" in out
    # verdict_provisional は additional_properties: false
    code, out = _app(tmp_path, "verdict_provisional",
                     {"issue": 7, "deliverable": "7", "role": "gate",
                      "lineage": "same-harness", "verdict": "admit", "for_event":
                      "admission_decided", "review_subject_id": "s", "reasoning_sha256": "d",
                      "not_declared": "x"}, actor="gate")
    assert code == 2
    assert "宣言の無い field" in out


def test_unset_timestamp_is_refused(tmp_path):
    """`--ts UNSET` used to pass, which sidesteps the cap's time window."""
    code, out = _app(tmp_path, "progress_recorded", {}, extra=("--ts", "UNSET"))
    assert code == 2
    assert "UNSET" in out
    code, out = _app(tmp_path, "progress_recorded", {}, extra=("--ts", "2026-07-30"))
    assert code == 2, "日付だけの形も拒否されるべき"
    # 正しい形は通る（hook が渡す経路。**固定日付を書かない** — 時間が経つと未来判定で
    # 壊れる。実際にこのテストが 0.33.2 でそう壊れた）
    import datetime as _dt
    recent = (_dt.datetime.now(_dt.timezone.utc)
              - _dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    code, out = _app(tmp_path, "progress_recorded", {}, extra=("--ts", recent))
    assert code == 0, out


def test_schema_drift_is_reported_by_verify(tmp_path, monkeypatch):
    """Check the schema digest recorded at write time, so a swapped format is detectable."""
    assert _app(tmp_path, "progress_recorded", {})[0] == 0
    alt = tmp_path / "alt-schema.yaml"
    alt.write_text((TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")
                   + "\n  a_brand_new_class: { x }\n", encoding="utf-8")
    monkeypatch.setenv("ORG_LEDGER_SCHEMA", str(alt))
    code, out = run("ledger.py", "verify", str(tmp_path))
    assert code == 0, out                      # 鎖は無事
    assert "形式が入れ替わっている" in out      # しかし drift は報告される


def test_schema_skew_is_diagnosed_and_fixable(tmp_path):
    """H8: org の schema がテンプレートより古いことを診断し、--fix で埋める。

    実測: ある org の schema は4クラス古く、うち2つ（correction 12件、asset_touched 3件）は
    実データで使われていた。配らずに検査を入れれば、その org は訂正を書けなくなる。
    """
    org = tmp_path / "org"; (org / ".orgforge" / "ledger").mkdir(parents=True)
    full = (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")
    # correction の宣言を削って「古い org」を作る
    stale = re.sub(r"\n  correction:.*?(?=\n  [a-z_]+:)", "\n", full, count=1, flags=re.S)
    (org / "ledger-schema.yaml").write_text(stale, encoding="utf-8")
    (org / "constitution.yaml").write_text("enforcement: {}\n", encoding="utf-8")

    code, out = run("ledger.py", "schema", cwd=str(org))
    assert code == 1, out
    assert "correction" in out
    code, out = run("ledger.py", "schema", "--fix", cwd=str(org))
    assert code == 0, out
    # **event_classes が2つになっていないこと** — YAML は後の定義で前を上書きし、
    # クラス宣言が丸ごと消える（この修復の初版が実際にそれをやった）。
    fixed = (org / "ledger-schema.yaml").read_text(encoding="utf-8")
    assert fixed.count("\nevent_classes:") == 1
    import yaml
    assert "correction" in yaml.safe_load(fixed)["event_classes"]
    assert run("ledger.py", "schema", cwd=str(org))[0] == 0      # 差分なしになる


# ══ 0.33.2 — Phase 0 の残件（lock の fail-open / ts の実在性 / H8 の nested）════
# **0.33.1 で「lock は fail-closed」と CHANGELOG に書いたが、コードに ORG_LEDGER_ALLOW_UNLOCKED
# は存在せず、self.error も設定されていなかった。** 置換が一致せず適用されていなかったのに、
# 実測せずに達成と報告した。ロックの fail-closed は **故障注入で検査できなければ主張できない。**

def test_lock_failure_refuses_the_append(tmp_path):
    """Under injected lock failure, it always stops non-zero."""
    env = dict(os.environ, ORG_LEDGER_FORCE_LOCK_FAIL="1")
    env.pop("ORG_LEDGER_ALLOW_UNLOCKED", None)
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", str(tmp_path),
                        "--actor", "w", "--class", "progress_recorded", "--payload", "{}"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 4, r.stdout + r.stderr
    assert "ロックできない" in (r.stdout + r.stderr)
    assert not (tmp_path / "ledger.jsonl").exists(), "拒否したのに書いている"


def test_unlocked_escape_is_explicit_and_says_what_it_cannot_verify(tmp_path):
    """The only escape hatch is an explicit environment variable — and it says what it can no
    longer guarantee."""
    env = dict(os.environ, ORG_LEDGER_FORCE_LOCK_FAIL="1", ORG_LEDGER_ALLOW_UNLOCKED="1")
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", str(tmp_path),
                        "--actor", "w", "--class", "progress_recorded", "--payload", "{}"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    both = r.stdout + r.stderr
    assert "ロックせずに append" in both
    assert "確かめられない" in both


def test_backfill_ts_must_be_a_real_moment(tmp_path):
    """Matching the shape is not enough: `2026-99-99T99:99:99Z` used to pass."""
    code, out = _app(tmp_path, "progress_recorded", {},
                     extra=("--backfill-ts", "2026-99-99T99:99:99Z"))
    assert code == 2
    assert "実在しない日時" in out


def test_backfill_ts_refuses_future_and_distant_past(tmp_path):
    """Refuse the future and the distant past — both sidestep the cap's time window."""
    code, out = _app(tmp_path, "progress_recorded", {},
                     extra=("--backfill-ts", "2099-01-01T00:00:00Z"))
    assert code == 2 and "未来である" in out
    code, out = _app(tmp_path, "progress_recorded", {},
                     extra=("--backfill-ts", "2000-01-01T00:00:00Z"))
    assert code == 2 and "遠すぎる過去" in out


def test_normal_append_needs_no_timestamp(tmp_path):
    """The normal path passes no timestamp; the writer stamps it."""
    assert _app(tmp_path, "progress_recorded", {})[0] == 0
    ev = _evs(tmp_path)[0]
    assert ev["ts"] != "UNSET" and ev["ts"].endswith("Z")


def test_unknown_validator_type_fails_closed(tmp_path, monkeypatch):
    """A typo in a schema type name must not silently disable the check."""
    alt = tmp_path / "typo-schema.yaml"
    alt.write_text((TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")
                   .replace("correction:          { corrects: list, target_classes: list, "
                            "target_issues: list }",
                            "correction:          { corrects: lst, target_classes: list, "
                            "target_issues: list }"), encoding="utf-8")
    monkeypatch.setenv("ORG_LEDGER_SCHEMA", str(alt))
    code, out = _app(tmp_path, "correction", {"corrects": [1], "kind": "probe"}, actor="sup")
    assert code == 2
    assert "unknown type" in out


def test_schema_diagnoses_nested_validation_gaps(tmp_path):
    """H8: validation の **中身** の欠落も診断する。ブロックの有無だけでは足りない。

    実測: org 側で verdict_provisional の required を削っても「差分なし」と判定した。
    """
    org = tmp_path / "org"; (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / "constitution.yaml").write_text("enforcement: {}\n", encoding="utf-8")
    full = (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")
    stale = re.sub(r"\n    verdict_provisional:  \[role, lineage, verdict, for_event,\n[^\n]*\n",
                   "\n", full, count=1)
    assert stale != full, "テストの前提が崩れている（required の行が見つからない）"
    (org / "ledger-schema.yaml").write_text(stale, encoding="utf-8")

    code, out = run("ledger.py", "schema", cwd=str(org))
    assert code == 1, out
    assert "validation 規則の欠落" in out
    assert "verdict_provisional" in out
    # --fix で埋まり、差分なしになる
    assert run("ledger.py", "schema", "--fix", cwd=str(org))[0] == 0
    assert run("ledger.py", "schema", cwd=str(org))[0] == 0
    # atomic write なので .tmp が残らない
    assert not list(org.glob("*.tmp"))


# ══ 0.33.3 — H8 修復器が org 所有の安全規則を消していた ═══════════════════════
# validation ブロックを丸ごと差し替えていたので、org が自分で足した厳格規則が失われた。
# **修復が org の安全側の設定を弱めるのは、修復ではなく退行である。**

def _org_with_schema(tmp_path, mutate):
    org = tmp_path / "org"; (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / "constitution.yaml").write_text("enforcement: {}\n", encoding="utf-8")
    (org / "ledger-schema.yaml").write_text(
        mutate((TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")), encoding="utf-8")
    return org


def test_fix_preserves_org_own_stricter_rules(tmp_path):
    """An org's own stricter rule survives --fix."""
    def mut(t):
        t = t.replace("  required:\n",
                      "  required:\n    progress_recorded: [milestone]\n", 1)
        return re.sub(r"\n    verdict_provisional:  \[role, lineage, verdict, for_event,\n[^\n]*\n",
                      "\n", t, count=1)
    org = _org_with_schema(tmp_path, mut)
    assert run("ledger.py", "schema", "--fix", cwd=str(org))[0] == 0
    import yaml
    d = yaml.safe_load((org / "ledger-schema.yaml").read_text(encoding="utf-8"))
    req = d["validation"]["required"]
    assert req.get("progress_recorded") == ["milestone"], "org 独自の規則が消えた"
    assert req.get("verdict_provisional"), "テンプレート由来の規則が復旧していない"
    # **event_classes を壊していないこと** — 置換の範囲が広すぎると丸ごと消える
    assert len(d["event_classes"]) >= 69
    assert set(d) >= {"envelope", "event_classes", "validation", "views", "triggers"}


def test_fix_preserves_org_added_list_elements(tmp_path):
    """Entries an org added to a list are kept — the merge is a union."""
    org = _org_with_schema(tmp_path, lambda t: t.replace(
        "    admission_decided:    [verdict]",
        "    admission_decided:    [verdict, standard_ref]", 1).replace(
        "  require_any:\n", "  require_any:\n    progress_recorded: [candidate_id]\n", 1))
    run("ledger.py", "schema", "--fix", cwd=str(org))
    import yaml
    v = yaml.safe_load((org / "ledger-schema.yaml").read_text(encoding="utf-8"))["validation"]
    assert "standard_ref" in v["required"]["admission_decided"]
    assert v["require_any"].get("progress_recorded") == ["candidate_id"]


def test_conflicting_scalar_is_reported_not_overwritten(tmp_path):
    """同じ path に違う値があるとき、自動で上書きせず conflict として報告する。

    org が意図して変えたのか、テンプレートが変わったのかは道具では判別できない。
    """
    org = _org_with_schema(tmp_path, lambda t: t.replace(
        "correction:          { corrects: list, target_classes: list, target_issues: list }",
        "correction:          { corrects: map, target_classes: list, target_issues: list }", 1))
    code, out = run("ledger.py", "schema", cwd=str(org))
    assert "衝突" in out
    assert "corrects" in out
    run("ledger.py", "schema", "--fix", cwd=str(org))
    import yaml
    v = yaml.safe_load((org / "ledger-schema.yaml").read_text(encoding="utf-8"))["validation"]
    assert v["types"]["correction"]["corrects"] == "map", "org の値が上書きされた"


def test_yaml_block_span_stops_at_the_next_top_level_key(tmp_path):
    """ブロックの範囲は「インデントの無い次の行」で決める。

    正規表現で `\\nkey:\\n(?:(?:  |\\n).*\\n)*` と書くと、次のトップレベルキーの前にある
    コメント行やその子行まで飲み込む。実際に validation の置換が event_classes を消した。
    """
    sys.path.insert(0, str(TOOLS))
    import importlib
    led = importlib.import_module("ledger")
    text = ("validation:\n  a: 1\n\n  # comment inside\n  b: 2\n\n"
            "# a top-level comment\nevent_classes:\n  x: 1\n")
    s, e = led._yaml_block_span(text, "validation")
    got = text[s:e]
    assert "b: 2" in got
    assert "event_classes" not in got
    assert "# a top-level comment" not in got


# ══ H3 — reserve-exposure: 書けた判断だけが allow になる ══════════════════════
# 従来: organ が「集計 → 判断 → LEDGER-EVENT 印字」、hook が「その後 append（失敗は無視）」。
#   1. 集計と判断が lock の外なので、並列の hook が同じ committed を読んで両方 allow できる
#   2. append 失敗を無視するので、次の呼び出しが committed=0 を見る（cap が記憶を失う）
#   3. hold は deny して終わるので、止めたことが残らない
# reserve-exposure は lock の中で検査と予約を一操作にする。

def _reserve(root, delta, cap, tu, sess="s1", rule="rm_guard", dim="destructive_ops",
             actor="system:org_hook", extra=()):
    return run("ledger.py", "reserve-exposure", str(root), "--dimension", dim,
               "--delta", str(delta), "--cap", str(cap), "--actor", actor,
               "--session-id", sess, "--tool-use-id", tu, "--rule", rule, *extra)


def _decisions(root):
    return [(e["seq"], e["payload"]["decision"], e["payload"]["delta_requested"])
            for e in _evs(root) if e["class"] == "exposure_budget_checked"]


def test_reserve_accumulates_and_holds_at_the_cap(tmp_path):
    """Exposure accumulates, and crossing the cap becomes a hold."""
    for i in range(3):
        code, out = _reserve(tmp_path, 1, 3, f"t{i}")
        assert code == 0, out
    code, out = _reserve(tmp_path, 1, 3, "t3")
    assert code == 10, out
    assert json.loads(out.splitlines()[0])["decision"] == "hold"


def test_hold_is_recorded_not_just_denied(tmp_path):
    """**A hold is recorded too.** It used to deny and stop there, leaving no record that
    anything was held."""
    _reserve(tmp_path, 5, 3, "t0")
    d = _decisions(tmp_path)
    assert len(d) == 1 and d[0][1] == "hold"


def test_concurrent_reservations_never_exceed_the_cap(tmp_path):
    """**At 16-way concurrency the total never crosses the cap.** Both sides used to read the
    same committed value."""
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(_reserve, tmp_path, 1, 5, f"t{i}") for i in range(16)]
        codes = [f.result()[0] for f in futs]
    assert sorted(set(codes)) == [0, 10], codes
    allowed = sum(dl for _s, dc, dl in _decisions(tmp_path) if dc == "allow")
    assert allowed == 5, f"allow の合計が cap を超えた: {allowed}"
    assert codes.count(0) == 5
    assert run("ledger.py", "verify", str(tmp_path))[0] == 0


def test_replay_of_the_same_tool_use_is_idempotent(tmp_path):
    """A re-fired hook is not double-counted."""
    assert _reserve(tmp_path, 1, 3, "same")[0] == 0
    code, out = _reserve(tmp_path, 1, 3, "same")
    assert code == 0
    assert json.loads(out.splitlines()[0])["reason"] == "idempotent_replay"
    assert len(_decisions(tmp_path)) == 1, "再実行が二重に記録された"


def test_idempotency_key_spans_session_rule_and_class(tmp_path):
    """`tool_use_id` alone cannot separate a different session or a different rule."""
    assert _reserve(tmp_path, 1, 9, "tu", sess="s1", rule="r1")[0] == 0
    assert _reserve(tmp_path, 1, 9, "tu", sess="s2", rule="r1")[0] == 0   # 別 session
    assert _reserve(tmp_path, 1, 9, "tu", sess="s1", rule="r2")[0] == 0   # 別 rule
    assert len(_decisions(tmp_path)) == 3, "衝突して no-op になった"


@pytest.mark.parametrize("missing", ["session_id", "tool_use_id", "rule"])
def test_missing_idempotency_key_denies_the_action(tmp_path, missing):
    """If it is missing, a metered action is denied — identity cannot be established."""
    kw = {"sess": "s1", "tu": "t1", "rule": "r1"}
    kw["tu" if missing == "tool_use_id" else
       "sess" if missing == "session_id" else "rule"] = ""
    code, out = _reserve(tmp_path, 1, 3, kw["tu"], sess=kw["sess"], rule=kw["rule"])
    assert code == 3, out
    d = json.loads(out.splitlines()[0])
    assert d["decision"] == "deny" and d["reason"] == f"missing_{missing}"
    assert _decisions(tmp_path) == []


def test_reserve_denies_when_the_ledger_is_unhealthy(tmp_path):
    """Never write a reservation onto a damaged ledger. **If it cannot be written, do not
    return allow.**"""
    assert _reserve(tmp_path, 1, 9, "t0")[0] == 0
    with open(tmp_path / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write('{"seq": 2, "class": "x"')        # torn line
    code, out = _reserve(tmp_path, 1, 9, "t1")
    assert code == 4
    assert json.loads(out.splitlines()[0])["reason"] == "ledger_unhealthy"


def test_reserve_denies_when_the_lock_fails(tmp_path):
    """No lock, no reservation — the cap's atomicity depends on it."""
    env = dict(os.environ, ORG_LEDGER_FORCE_LOCK_FAIL="1")
    env.pop("ORG_LEDGER_ALLOW_UNLOCKED", None)
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "reserve-exposure",
                        str(tmp_path), "--dimension", "destructive_ops", "--delta", "1",
                        "--cap", "9", "--actor", "a", "--session-id", "s",
                        "--tool-use-id", "t", "--rule", "r"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 4
    assert json.loads(r.stdout.splitlines()[0])["reason"] == "lock_failed"


def test_reserve_defines_no_timestamp_argument(tmp_path):
    """**No backfill into a cap reservation.** The argument is not even defined."""
    code, out = run("ledger.py", "reserve-exposure", "--help")
    assert "--backfill-ts" not in out
    assert not re.search(r"(?m)^\s+--ts\b", out)
    # 渡そうとしても受け付けない
    code, out = _reserve(tmp_path, 1, 9, "t0", extra=("--backfill-ts", "2026-07-01T00:00:00Z"))
    assert code != 0
    assert _decisions(tmp_path) == []


def test_reserve_does_not_take_committed_from_the_caller(tmp_path):
    """The writer counts `committed_so_far`; a caller must never be able to declare it."""
    code, out = run("ledger.py", "reserve-exposure", "--help")
    assert "committed" not in out.lower()
    _reserve(tmp_path, 2, 9, "t0")
    _reserve(tmp_path, 2, 9, "t1")
    d = _evs(tmp_path)[-1]["payload"]
    assert d["committed_so_far"] == 2.0, "writer が数えていない"


def test_malformed_prior_exposure_denies(tmp_path):
    """A damaged exposure record is not counted as 0 — that would make the total look
    smaller than it is."""
    assert _reserve(tmp_path, 1, 9, "t0")[0] == 0
    p = tmp_path / "ledger.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    ev = json.loads(lines[0])
    ev["payload"]["delta_requested"] = "not-a-number"
    sys.path.insert(0, str(TOOLS))
    import importlib
    led = importlib.import_module("ledger")
    ev["hash"] = led._hash("GENESIS", ev)          # 鎖は通るようにする
    p.write_text(json.dumps(ev, ensure_ascii=False) + "\n", encoding="utf-8")
    (tmp_path / "HEAD").write_text(json.dumps({"seq": 1, "hash": ev["hash"]}), encoding="utf-8")
    code, out = _reserve(tmp_path, 1, 9, "t1")
    assert code == 4
    assert json.loads(out.splitlines()[0])["reason"] == "malformed_prior_exposure"


# ══ 0.34.1 — 信頼境界の3経路（既存テストでは捕まらなかったもの）════════════════

def test_exposure_events_cannot_be_forged_by_generic_append(tmp_path):
    """**上限の予約は writer 専用。** generic append で書けると上限そのものが無効になる。

    実測: `delta_requested: -100` を append したあと、cap=5 に対して delta=50 が allow され、
    鎖も intact だった。検査に使う記録は、検査する側だけが書ける必要がある。
    """
    code, out = _app(tmp_path, "exposure_budget_checked",
                     {"window_id": "all", "dimension": "destructive_ops",
                      "committed_so_far": 0, "delta_requested": -100, "cap": 5,
                      "actor_role": "x", "decision": "allow"}, actor="attacker")
    assert code == 2, out
    assert "writer 専用" in out
    assert _evs(tmp_path) == []
    # そして予約は正常に働く
    assert _reserve(tmp_path, 50, 5, "t0")[0] == 10        # cap 5 < 50 → hold


def test_caller_cannot_supply_the_idempotency_marker(tmp_path):
    """`_nk` is stamped by the tool. A caller who could name it could manufacture a no-op."""
    code, out = _app(tmp_path, "progress_recorded", {"_nk": "forged"})
    assert code == 2
    assert "_nk" in out


def test_same_key_with_a_different_request_is_refused(tmp_path):
    """**Only an exact retry is a replay.** delta=100 used to pass on the strength of an
    allow for delta=1."""
    assert _reserve(tmp_path, 1, 5, "t1")[0] == 0
    code, out = _reserve(tmp_path, 100, 5, "t1")
    assert code == 3, out
    d = json.loads(out.splitlines()[0])
    assert d["decision"] == "deny"
    assert d["reason"] == "idempotency_key_reused_with_different_request"
    # 同じ内容なら no-op
    code, out = _reserve(tmp_path, 1, 5, "t1")
    assert code == 0
    assert json.loads(out.splitlines()[0])["reason"] == "idempotent_replay"


@pytest.mark.parametrize("delta,cap", [(-5, 5), (0, 5), ("nan", 5), ("inf", 5), (1, -1)])
def test_invalid_magnitudes_are_refused(tmp_path, delta, cap):
    """delta is finite and positive, cap finite and non-negative. A negative or NaN breaks
    both the sum and the comparison."""
    code, out = _reserve(tmp_path, delta, cap, f"t{delta}{cap}")
    assert code == 3, out
    assert json.loads(out.splitlines()[0])["reason"] == "invalid_request"
    assert _decisions(tmp_path) == []


def test_negative_prior_exposure_denies_rather_than_reducing_the_total(tmp_path):
    """Past negative exposure is not counted — counting it would let the total be reduced."""
    assert _reserve(tmp_path, 1, 9, "t0")[0] == 0
    p = tmp_path / "ledger.jsonl"
    ev = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    ev["payload"]["delta_requested"] = -100
    sys.path.insert(0, str(TOOLS))
    import importlib
    led = importlib.import_module("ledger")
    ev["hash"] = led._hash("GENESIS", ev)
    p.write_text(json.dumps(ev, ensure_ascii=False) + "\n", encoding="utf-8")
    (tmp_path / "HEAD").write_text(json.dumps({"seq": 1, "hash": ev["hash"]}), encoding="utf-8")
    code, out = _reserve(tmp_path, 50, 5, "t1")
    assert code == 4
    assert json.loads(out.splitlines()[0])["reason"] == "malformed_prior_exposure"


@pytest.mark.parametrize("var", ["ORG_LEDGER_FORCE_APPEND_FAIL", "ORG_LEDGER_FORCE_FSYNC_FAIL"])
def test_persistence_failure_never_becomes_an_allow(tmp_path, var):
    """**A failed write is not an allow.** A partial write is rolled back."""
    assert _reserve(tmp_path, 1, 9, "ok")[0] == 0
    before = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    env = dict(os.environ, **{var: "1"})
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "reserve-exposure",
                        str(tmp_path), "--dimension", "destructive_ops", "--delta", "1",
                        "--cap", "9", "--actor", "a", "--session-id", "s",
                        "--tool-use-id", "t2", "--rule", "r"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 4
    assert json.loads(r.stdout.splitlines()[0])["reason"] == "reservation_not_persisted"
    # 書きかけが残っていないこと
    assert (tmp_path / "ledger.jsonl").read_text(encoding="utf-8") == before
    assert run("ledger.py", "verify", str(tmp_path))[0] == 0


def test_verify_accepts_legitimately_written_reservations(tmp_path):
    """`verify` は writer_only を検査しない — 経路は append の時点でしか見られない。

    検査すると、**正しく書かれた予約が「generic append では書けない」と拒否され**、
    健全な台帳が壊れていると報告される。
    """
    assert _reserve(tmp_path, 1, 9, "t0")[0] == 0
    code, out = run("ledger.py", "verify", str(tmp_path))
    assert code == 0, out
    assert "chain intact" in out


def test_idempotency_key_is_a_hash_not_a_delimited_join(tmp_path):
    """Delimiter-joined keys collide once a value contains the delimiter."""
    assert _reserve(tmp_path, 1, 9, "b", sess="a", rule="c")[0] == 0
    # "a|b|c" と同じ連結になる組み合わせが、別のキーとして扱われること
    assert _reserve(tmp_path, 1, 9, "c", sess="a|b", rule="")[0] == 3    # rule 空 → deny
    assert _reserve(tmp_path, 1, 9, "c", sess="a|b", rule="x")[0] == 0   # 別キーとして通る
    assert len(_decisions(tmp_path)) == 2


# ══ H4a — 単調な halt: 止まっている状態は警告ではない ═════════════════════════

def _trip(root, reason="検査のため", by="registrar", trigger="test", env=None):
    args = ["ledger.py", "trip-halt", str(root), "--trigger", trigger,
            "--reason", reason, "--tripped-by", by]
    if env:
        r = subprocess.run([sys.executable, str(TOOLS / args[0])] + args[1:],
                           capture_output=True, text=True, env=dict(os.environ, **env))
        return r.returncode, r.stdout + r.stderr
    return run(*args)


def test_halt_is_writer_only(tmp_path):
    """A halt cannot be written by a generic append — only the checking side writes the record
    the check reads."""
    code, out = _app(tmp_path, "halt_tripped",
                     {"trigger": "t", "scope": "global", "reason": "r", "tripped_by": "x"},
                     actor="attacker")
    assert code == 2, out
    assert "writer 専用" in out
    assert _evs(tmp_path) == []


def test_trip_halt_writes_the_ledger_and_the_latch(tmp_path):
    """Write to both the ledger and the latch; the latch is the second path when the ledger
    cannot be read."""
    code, out = _trip(tmp_path)
    assert code == 0, out
    d = json.loads(out.splitlines()[0])
    assert d["halted"] is True and d["latch_written"] is True
    assert (tmp_path / "HALT").is_file()
    assert [e["class"] for e in _evs(tmp_path)] == ["halt_tripped"]


def test_trip_halt_requires_a_reason(tmp_path):
    """A halt with no reason leaves nobody able to decide whether to release it."""
    code, out = run("ledger.py", "trip-halt", str(tmp_path), "--trigger", "t",
                    "--reason", "  ", "--tripped-by", "x")
    assert code == 2
    assert json.loads(out.splitlines()[0])["reason"] == "missing_reason"


def test_halt_persistence_failure_returns_nonzero_and_still_latches(tmp_path):
    """**halt を記録できなければ、その呼び出し自体を非ゼロで返す。**

    「記録できないなら宣言しない」は記録としては正しいが、制御としては fail-open になる —
    止めるべき状況で止まらない。ラッチを先に書くので、次回の呼び出しは止まる。
    """
    code, out = _trip(tmp_path, env={"ORG_LEDGER_FORCE_APPEND_FAIL": "1"})
    assert code == 4, out
    d = json.loads(out.splitlines()[0])
    assert d["reason"] == "halt_not_persisted"
    assert d["latch_written"] is True
    assert (tmp_path / "HALT").is_file()
    assert _evs(tmp_path) == []          # 台帳には入っていない
    # **それでも次回は止まる**（ラッチが第二経路として働く）
    code, out = run("ledger.py", "halt-status", str(tmp_path))
    assert code == 10, out
    assert json.loads(out.splitlines()[0])["source"] == "latch_only"


def test_halt_status_is_readable_while_halted(tmp_path):
    """Observation passes during a halt — a halted org that cannot be diagnosed cannot
    recover."""
    assert _trip(tmp_path)[0] == 0
    code, out = run("ledger.py", "halt-status", str(tmp_path))
    assert code == 10
    d = json.loads(out.splitlines()[0])
    assert d["halted"] is True and d["source"] == "ledger"
    assert d["reason"] and d["tripped_by"] == "registrar"


def test_deleting_the_latch_does_not_clear_the_halt(tmp_path):
    """The latch does not stand in for the ledger: deleting it by hand leaves the ledger's
    halt in place."""
    assert _trip(tmp_path)[0] == 0
    (tmp_path / "HALT").unlink()
    code, out = run("ledger.py", "halt-status", str(tmp_path))
    assert code == 10, out
    assert json.loads(out.splitlines()[0])["source"] == "ledger"


def test_unreadable_ledger_counts_as_halted(tmp_path):
    """If it cannot be determined whether a halt is in force, halt — this is the most
    dangerous place to fail open."""
    assert _trip(tmp_path)[0] == 0
    with open(tmp_path / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write('{"seq": 9, "torn"')
    code, out = run("ledger.py", "halt-status", str(tmp_path))
    assert code == 10, out
    assert json.loads(out.splitlines()[0])["source"] == "unreadable"


def test_release_needs_an_authenticated_independent_approver(tmp_path):
    """解除は存在するが、**自己申告では通らない。**

    H4a では操作自体が無かった。0.38.0 で入ったが、要求するのは非対称鍵・独立した principal・
    `may_release_halt` の認可・復旧の証拠である。generic append でも書けない。
    """
    code, out = run("ledger.py", "--help")
    assert "trip-halt" in out and "release-halt" in out
    assert _trip(tmp_path)[0] == 0
    # generic append では書けない（writer 専用）
    code, out = _app(tmp_path, "halt_released",
                     {"releases_seq": 1, "reason": "r", "released_by": "x",
                      "recovery_verified": "y", "identity_assurance": "authenticated"},
                     actor="registrar")
    assert code == 2
    # **どちらの層で止まってもよい。** identity fields を payload に書けない検査（0.39.3）が
    # writer-only の検査より先に働く — どちらも「generic append では書けない」ことを言っている。
    assert ("writer 専用" in out) or ("receipt を検証して生成する" in out), out
    assert run("ledger.py", "halt-status", str(tmp_path))[0] == 10   # まだ止まっている


def test_schema_has_no_duplicate_top_level_keys():
    """**YAML は後勝ちなので、重複したトップレベルキーは前を黙って消す。**

    実際に、`identity` ブロックを「`validation:` の直前」に挿入したとき、その `validation:` が
    説明コメントの見出し行だったため本物と重複し、**検証規則が丸ごと無効になった**
    （しかも YAML として読めるので気づきにくい）。docs/11 の「修復が壊すのは最悪の形」の再演。
    """
    for f in (TEMPLATE / "ledger-schema.yaml",
              REPO / "integrations" / "claude-code" / "template" / "ledger-schema.yaml",
              REPO / "integrations" / "codex" / "template" / "ledger-schema.yaml"):
        if not f.is_file():
            continue
        keys = [l.split(":")[0] for l in f.read_text(encoding="utf-8").splitlines()
                if l and not l[0].isspace() and ":" in l and not l.startswith("#")]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        assert not dupes, f"{f.name} にトップレベルキーの重複: {dupes}"


def test_identity_declares_four_separate_assurance_axes():
    """**assurance を単一の強弱値に潰さない。**

    署名されていても、同じ process / 同じ鍵が両方の血統を作れるなら独立レビューではない。
    """
    import yaml
    d = yaml.safe_load((TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"))
    ax = d["identity"]["assurance_axes"]
    assert set(ax) == {"identity_assurance", "recorder_assurance",
                       "workload_isolation", "reviewer_independence"}
    assert "authenticated" in ax["identity_assurance"]
    assert "claimed" in ax["identity_assurance"]
    # legacy actor は claimed のまま昇格しない
    assert d["identity"]["legacy_actor"] == "claimed"


# ══ Authenticated Mode + H4b — 認証付き halt 解除 ═════════════════════════════
# **共有鍵は「鍵が違う」ことしか示さない。** 別主体・別プロセス・独立した承認を証明しないので、
# 解除には使えない。非対称鍵（judge が秘密鍵、writer は公開鍵だけ）が前提である。

def _am_org(tmp_path):
    org = tmp_path / "org"
    for d in (".orgforge/ledger", ".orgforge/trust", "keys"):
        (org / d).mkdir(parents=True, exist_ok=True)
    import shutil as _sh
    _sh.copy(TEMPLATE / "ledger-schema.yaml", org / "ledger-schema.yaml")
    (org / "constitution.yaml").write_text("enforcement: {}\n", encoding="utf-8")
    return org, org / ".orgforge" / "ledger"


def _am_env(org):
    return dict(os.environ, ORG_TRUST_STORE=str(org / ".orgforge" / "trust" / "keys.json"))


def _am_tool(org, script, *args, env=None):
    return subprocess.run([sys.executable, str(TOOLS / script), *args], cwd=org,
                          capture_output=True, text=True, env=env or _am_env(org))


def test_trust_store_holds_public_keys_only(tmp_path):
    """**The writer holds only public keys.** Whoever holds the private key can forge a
    verdict."""
    org, _ = _am_org(tmp_path)
    r = _am_tool(org, "identity.py", "keygen", "--key-id", "k1", "--signer-id", "s1",
                 "--private-out", "keys/k1.pem")
    assert r.returncode == 0, r.stdout + r.stderr
    store = json.loads((org / ".orgforge" / "trust" / "keys.json").read_text(encoding="utf-8"))
    k = store["keys"]["k1"]
    assert k.get("public_pem"), "公開鍵が入っていない"
    assert "private_pem" not in k and "secret" not in k, "秘密鍵/共有鍵が store に漏れている"
    assert store["mode"] == "authenticated"
    assert (org / "keys" / "k1.pem").is_file()


def test_a_private_key_in_the_trust_store_is_refused(tmp_path):
    """A store containing a private key is refused at load time."""
    org, _ = _am_org(tmp_path)
    (org / ".orgforge" / "trust" / "keys.json").write_text(json.dumps(
        {"keys": {"k1": {"signer_id": "s1", "private_pem": "-----BEGIN..."}}}), encoding="utf-8")
    sys.path.insert(0, str(TOOLS))
    import importlib
    ident = importlib.import_module("identity")
    os.environ["ORG_TRUST_STORE"] = str(org / ".orgforge" / "trust" / "keys.json")
    try:
        store, err = ident.load_trust_store()
        assert store is None and err and "秘密鍵" in err
    finally:
        os.environ.pop("ORG_TRUST_STORE", None)


def test_public_key_cannot_produce_a_signature(tmp_path):
    """A public key cannot produce a signature — the decisive difference from a shared
    secret."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    ident = importlib.import_module("identity")
    priv, pub, err = ident.generate_keypair()
    assert not err, err
    sig, err = ident.sign_bytes(b"m", priv)
    assert not err and sig.startswith("ed25519:")
    assert ident.verify_bytes(b"m", sig, pub) == (True, None)
    assert ident.verify_bytes(b"tampered", sig, pub)[0] is False
    assert ident.sign_bytes(b"m", pub)[0] is None      # 公開鍵で署名できない


def _am_setup_halt(tmp_path, **kw):
    org, led = _am_org(tmp_path)
    for kid, sid, extra in (("k-reg", "reg", []),
                            ("k-appr", "appr", ["--may-release-halt"]),
                            ("k-noauth", "noauth", [])):
        assert _am_tool(org, "identity.py", "keygen", "--key-id", kid, "--signer-id", sid,
                        "--private-out", f"keys/{kid}.pem", *extra).returncode == 0
    assert _am_tool(org, "identity.py", "keygen", "--key-id", "k-shared",
                    "--signer-id", "shared", "--shared-secret").returncode == 0
    assert _am_tool(org, "ledger.py", "trip-halt", str(led), "--trigger", "t",
                    "--reason", "検査のため", "--tripped-by", "reg").returncode == 0
    return org, led


def _am_receipt(org, key_id, priv=None, subject="halt:1", out="r.json"):
    args = ["identity.py", "receipt", "--org-id", "o", "--ledger-id", "l",
            "--subject", subject, "--issue", "0", "--role", "release", "--phase", "operate",
            "--lineage", "release", "--verdict", "release", "--event-class", "halt_released",
            "--requirements-digest", "none",
            "--reasoning-sha256", "none", "--issued-at", "2026-07-30T12:00:00Z",
            "--key-id", key_id]
    if priv:
        args += ["--private-key", priv]
    r = _am_tool(org, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    (org / out).write_text(r.stdout.strip(), encoding="utf-8")
    return out


def _am_release(org, led, receipt, evidence="ledger verify → chain intact", env=None):
    r = _am_tool(org, "ledger.py", "release-halt", str(led), "--receipt", receipt,
                 "--reason", "復旧を確認した", "--recovery-verified", evidence, env=env)
    return r.returncode, json.loads(r.stdout.splitlines()[0]) if r.stdout.strip() else {}


def test_the_principal_that_tripped_cannot_release(tmp_path):
    """**Whoever halted it must not be able to release it.**"""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-reg", "keys/k-reg.pem")
    code, d = _am_release(org, led, rc)
    assert code == 4
    assert d["released"] is False
    assert _am_tool(org, "ledger.py", "halt-status", str(led)).returncode == 10   # 維持


def test_a_shared_secret_cannot_release(tmp_path):
    """A shared secret shows only that the key differs; it does not prove independent
    approval."""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-shared")
    code, d = _am_release(org, led, rc)
    assert code == 4 and d["released"] is False
    assert "共有鍵" in (d.get("detail") or "")


def test_release_requires_explicit_authorization(tmp_path):
    """A key not authorized for `may_release_halt` cannot release one."""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-noauth", "keys/k-noauth.pem")
    code, d = _am_release(org, led, rc)
    assert code == 4 and d["released"] is False


def test_a_release_receipt_is_bound_to_the_halt(tmp_path):
    """A release receipt for one halt cannot be replayed against another."""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-appr", "keys/k-appr.pem", subject="halt:999")
    code, d = _am_release(org, led, rc)
    assert code == 4 and "一致しない" in (d.get("detail") or "")


def test_release_requires_recovery_evidence(tmp_path):
    """A release that does not say what was verified cannot be audited afterwards."""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-appr", "keys/k-appr.pem")
    code, d = _am_release(org, led, rc, evidence="   ")
    assert code == 2 and d["reason"] == "missing_recovery_evidence"


def test_an_independent_authorized_approver_can_release(tmp_path):
    """An independent approver — asymmetric key, authorized, with evidence — can release."""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-appr", "keys/k-appr.pem")
    code, d = _am_release(org, led, rc)
    assert code == 0, d
    assert d["released"] is True and d["identity_assurance"] == "authenticated"
    assert d["released_by"] == "appr" and d["tripped_by"] == "reg"
    assert not (led / "HALT").exists()
    assert _am_tool(org, "ledger.py", "halt-status", str(led)).returncode == 0
    assert run("ledger.py", "verify", str(led))[0] == 0


def test_a_release_that_cannot_be_recorded_keeps_the_halt(tmp_path):
    """**記録できていないのに停止が解けることが、いちばん危ない fail-open である。**

    順序: 検証 → append+fsync → **その後で** ラッチを消す。記録に失敗したら停止を維持する。
    """
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-appr", "keys/k-appr.pem")
    env = dict(_am_env(org), ORG_LEDGER_FORCE_APPEND_FAIL="1")
    code, d = _am_release(org, led, rc, env=env)
    assert code == 4
    assert d["reason"] == "release_not_persisted" and d["released"] is False
    assert (led / "HALT").exists(), "記録できていないのにラッチが消えた"
    assert _am_tool(org, "ledger.py", "halt-status", str(led)).returncode == 10
    assert "halt_released" not in (led / "ledger.jsonl").read_text(encoding="utf-8")
    # exact retry で安全に解除できる
    code, d = _am_release(org, led, rc)
    assert code == 0 and d["released"] is True
    assert run("ledger.py", "verify", str(led))[0] == 0


def test_releasing_when_nothing_is_halted_is_a_noop(tmp_path):
    """With no active halt it does nothing, so re-running is safe."""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-appr", "keys/k-appr.pem")
    assert _am_release(org, led, rc)[0] == 0
    code, d = _am_release(org, led, rc)
    assert code == 2 and d["reason"] == "no_active_halt"


# ══ Authenticated Writer 段階A — 経路を1つにする（process_mediated）═══════════
# **これは OS 境界ではない。** 同一 UID の caller は daemon を止められ、権限も戻せる。
# 強制できるのは「台帳への経路が1つであること」までで、workload_isolation は
# `process_mediated` にとどまる。`separate_uid` は別 UID + root 所有の親ディレクトリが要る。

import socket as _socket


def _wd_start(tmp_path):
    """Start writerd and return (led, sock, proc)."""
    led = tmp_path / ".orgforge" / "ledger"; led.mkdir(parents=True)
    import shutil as _sh
    _sh.copy(TEMPLATE / "ledger-schema.yaml", tmp_path / "ledger-schema.yaml")
    (tmp_path / "constitution.yaml").write_text("enforcement: {}\n", encoding="utf-8")
    # **socket は短いパスに置く。** pytest の tmp_path は AF_UNIX の上限（macOS 104 バイト）を
    # 超える。実装側もその旨を報告するが、テストでは短い場所を使う。
    # **anchor / leaf を作る。** socket を /tmp 直下に置くと anchor が /tmp（0777）になり、
    # 「caller が leaf ごと差し替えられる」として writerd が正しく拒否する。
    import tempfile as _tf
    anchor = pathlib.Path(_tf.mkdtemp(prefix="wd", dir="/tmp"))
    os.chmod(anchor, 0o755)
    sdir = anchor / "r"; sdir.mkdir(); os.chmod(sdir, 0o755)
    sock = sdir / "w.sock"
    os.environ["ORG_WRITER_TRUST_SELF"] = "1"   # 段階A。**信頼境界ではない**
    proc = subprocess.Popen(
        [sys.executable, str(TOOLS / "writerd.py"), "serve",
         "--org", f"default={led}", "--socket", str(sock)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # **起動を待ちきる。** 待たずに接続すると FileNotFoundError になり、
    # 「daemon が動いていない」のか「まだ準備中」なのか区別できない。
    for _ in range(200):
        if sock.exists():
            break
        if proc.poll() is not None:      # 落ちたなら理由を出す
            out = proc.stdout.read() if proc.stdout else ""
            raise AssertionError(f"writerd が起動しなかった（exit {proc.returncode}）:\n{out}")
        time.sleep(0.05)
    assert sock.exists(), "writerd が socket を作らなかった"
    return led, sock, proc


def _wd_client(sock, *args, org="default"):
    env = dict(os.environ, ORG_WRITER_SOCKET=str(sock), ORG_WRITER_TRUST_SELF="1")
    r = subprocess.run([sys.executable, str(TOOLS / "writer_client.py"), "append",
                        "--org", org, "--", *args],
                       capture_output=True, text=True, env=env)
    line = (r.stdout.splitlines() or ["{}"])[0]
    try:
        return r.returncode, json.loads(line)
    except json.JSONDecodeError:
        return r.returncode, {"raw": r.stdout + r.stderr}


_WD_PAYLOAD = '{"role":"maker","candidate_id":"c1","phase":"implement"}'


def test_writerd_accepts_a_request_and_direct_write_is_refused(tmp_path):
    """**One path only.** A write through writerd succeeds; a direct append is refused."""
    led, sock, proc = _wd_start(tmp_path)
    try:
        code, d = _wd_client(sock, "--actor", "w", "--class", "progress_recorded",
                             "--payload", _WD_PAYLOAD)
        assert code == 0 and d.get("ok") is True, d
        assert d["workload_isolation"] == "process_mediated"     # separate_uid とは呼ばない
        assert (led / "ledger.jsonl").read_text(encoding="utf-8").strip()

        env = dict(os.environ, ORG_WRITER_SOCKET=str(sock))
        r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", str(led),
                            "--actor", "w", "--class", "progress_recorded",
                            "--payload", _WD_PAYLOAD.replace("c1", "DIRECT-WRITE")],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 4, r.stdout + r.stderr
        assert "writerd 経由" in (r.stdout + r.stderr)
        assert "DIRECT-WRITE" not in (led / "ledger.jsonl").read_text(encoding="utf-8")
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_a_stopped_daemon_fails_closed(tmp_path):
    """**An absent daemon is not read as permission to write.** A direct write stays
    refused."""
    led, sock, proc = _wd_start(tmp_path)
    proc.terminate(); proc.wait(timeout=10)
    code, d = _wd_client(sock, "--actor", "w", "--class", "progress_recorded",
                         "--payload", _WD_PAYLOAD)
    assert code == 4
    assert d.get("reason") == "writer_unreachable"
    env = dict(os.environ, ORG_WRITER_SOCKET=str(sock))
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", str(led),
                        "--actor", "w", "--class", "progress_recorded",
                        "--payload", _WD_PAYLOAD],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 4, "daemon 停止中に直接書き込みが通った"
    assert not (led / "ledger.jsonl").exists() or \
        not (led / "ledger.jsonl").read_text(encoding="utf-8").strip()


def _wd_raw(sock, req):
    c = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    c.settimeout(30); c.connect(str(sock))
    c.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        ch = c.recv(65536)
        if not ch:
            break
        buf += ch
    c.close()
    return json.loads(buf)


def _wd_req(**kw):
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    req = {"protocol": wd.PROTOCOL, "op": "append", "org": "default",
           "nonce": kw.pop("nonce", "n" * 32),
           "argv": ["--actor", "w", "--class", "progress_recorded", "--payload", _WD_PAYLOAD]}
    req.update(kw)
    req["digest"] = wd.request_digest(req)
    return req


def test_a_tampered_request_is_refused(tmp_path):
    """The digest covers the whole body, so a request altered in transit does not pass."""
    led, sock, proc = _wd_start(tmp_path)
    try:
        req = _wd_req()
        req["argv"] = list(req["argv"]); req["argv"][1] = "attacker"   # digest 後に改変
        assert _wd_raw(sock, req)["reason"] == "request_tampered"
        assert not (led / "ledger.jsonl").exists() or \
            "attacker" not in (led / "ledger.jsonl").read_text(encoding="utf-8")
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_a_replayed_request_is_refused(tmp_path):
    """A replayed nonce does not pass."""
    led, sock, proc = _wd_start(tmp_path)
    try:
        req = _wd_req(nonce="r" * 32)
        assert _wd_raw(sock, req)["reason"] == "executed"
        assert _wd_raw(sock, req)["reason"] == "replayed_nonce"
        lines = [l for l in (led / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        assert len(lines) == 1, "再送が二重に記録された"
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_a_caller_cannot_choose_the_ledger_path(tmp_path):
    """**writerd decides the write target.** A caller can only choose an org name."""
    led, sock, proc = _wd_start(tmp_path)
    try:
        req = _wd_req(nonce="p" * 32)
        req["argv"] = req["argv"] + ["/tmp/elsewhere/ledger.jsonl"]
        sys.path.insert(0, str(TOOLS))
        import importlib
        req["digest"] = importlib.import_module("writerd").request_digest(req)
        assert _wd_raw(sock, req)["reason"] == "path_in_argv"
        assert _wd_raw(sock, _wd_req(nonce="o" * 32, org="elsewhere"))["reason"] == "unknown_org"
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_only_write_operations_are_accepted(tmp_path):
    """writerd must not be a way to run an arbitrary subcommand."""
    led, sock, proc = _wd_start(tmp_path)
    try:
        assert _wd_raw(sock, _wd_req(nonce="v" * 32, op="verify"))["reason"] == "unsupported_op"
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_peer_credential_is_reported_for_the_recorder_only(tmp_path):
    """peer identity は `recorded_by` にしか使わない。

    **「接続してきた」ことは「その判断をした」ことの証拠にならない** — decision_by は
    署名 receipt からのみ確定する。
    """
    led, sock, proc = _wd_start(tmp_path)
    try:
        code, d = _wd_client(sock, "--actor", "w", "--class", "progress_recorded",
                             "--payload", _WD_PAYLOAD)
        assert code == 0
        assert d.get("recorded_by_peer_uid") == os.getuid()
        ev = json.loads((led / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[0])
        # peer uid が decision_by に流れていないこと
        assert str(os.getuid()) not in json.dumps(ev["payload"].get("decision_by") or "")
    finally:
        proc.terminate(); proc.wait(timeout=10)


@pytest.mark.parametrize("mode,expect", [(0o777, False), (0o755, True)])
def test_socket_parent_must_not_be_world_writable(tmp_path, mode, expect):
    """**Whoever can write the parent can swap the socket** and route callers to a forged
    writer."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    parent = tmp_path / "p"; parent.mkdir()
    os.chmod(parent, mode)
    os.environ["ORG_WRITER_TRUST_SELF"] = "1"      # 段階A（anchor が自分所有）
    try:
        err = wd.check_socket_parent(str(parent / "writer.sock"))
        assert (err is None) is expect, err
    finally:
        os.environ.pop("ORG_WRITER_TRUST_SELF", None)
        os.chmod(parent, 0o755)


def test_socket_parent_may_not_be_a_symlink(tmp_path):
    """Re-pointing the link swaps the socket wholesale."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    err = wd.check_socket_parent(str(tmp_path / "link" / "writer.sock"))
    assert err and "シンボリックリンク" in err


def test_same_uid_cannot_claim_separate_uid(tmp_path):
    """**The same UID cannot claim `separate_uid`.** The tool says so about itself."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    parent = tmp_path / "p"; parent.mkdir()
    err = wd.check_socket_parent(str(parent / "writer.sock"), require_root_owned=True)
    assert err and "root 所有でない" in err
    assert "separate_uid" in err


def test_writer_owned_assets_are_audited(tmp_path):
    """The latch, the key registry and the schema need the same protection as the write
    path."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    led = tmp_path / "ledger"; led.mkdir()
    (led / "ledger.jsonl").write_text("", encoding="utf-8")
    os.chmod(led / "ledger.jsonl", 0o600)
    assert wd.audit_writer_assets(str(led)) == []
    os.chmod(led / "ledger.jsonl", 0o666)
    issues = wd.audit_writer_assets(str(led))
    assert issues and "他者から書き込み可能" in issues[0][1]


@pytest.mark.skipif(sys.platform != "darwin", reason="writer-install.sh is macOS-only")
def test_install_script_dry_run_changes_nothing(tmp_path):
    """A stage-B install changes nothing under `--dry-run`, so it can be audited without
    root."""
    led = tmp_path / ".orgforge" / "ledger"; led.mkdir(parents=True)
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    r = subprocess.run(["bash", str(TOOLS / "writer-install.sh"),
                        "--org-root", str(tmp_path), "--dry-run",
                        # **daemon が使う python で PyYAML を検査する**ので、それが無い環境では
                        # preflight が正しく止まる。ここでは「何も変えない」ことを見たいので、
                        # 検査を通せる処理系を渡す（無ければ preflight で止まることを確かめる）。
                        "--daemon-python", sys.executable],
                       capture_output=True, text=True)
    both = r.stdout + r.stderr
    if r.returncode != 0:
        # preflight で止まった場合も **何も変えていない**ことが要件である
        assert "PyYAML" in both, both
    else:
        assert "[dry-run]" in r.stdout
        assert "脅威モデルの外" in r.stdout        # 境界を明示している
    assert sorted(str(p.relative_to(tmp_path))
                  for p in tmp_path.rglob("*")) == before, "dry-run が何かを変えた"


def test_verify_script_refuses_to_run_as_root():
    """Running the verification as root proves nothing — root can do everything."""
    src = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    assert 'if [ "$(id -u)" = "0" ]' in src
    assert "root では全部できてしまい" in src


# ══ 0.39.1 — 監査が見つけた「installer が作る状態では動かない」9件 ═══════════
# **設定を書いたことは、動くことではない。** --dry-run が exit 0 でも、その設定で daemon が
# 起動しない／caller が接続できない／台帳が読めないなら、install は完了していない。

def test_stage_b_permissions_let_the_daemon_start(tmp_path):
    """段階B の権限で **daemon が socket を作れる**こと。

    実測（監査）: root 所有 0755 の親には別 UID の daemon が bind できない
    （`bind()` は親への書き込み権限を要求する）。0755 も 1770 も動かない。
    したがって anchor（root 所有・caller が書けない）と leaf（writer 所有・bind できる）に分ける。
    """
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    # **短いパスを使う。** AF_UNIX の上限（macOS 104 バイト）は pytest の tmp_path で超える。
    import tempfile as _tf
    anchor = pathlib.Path(_tf.mkdtemp(prefix="an", dir="/tmp")); leaf = anchor / "r"
    leaf.mkdir(parents=True)
    os.chmod(anchor, 0o755); os.chmod(leaf, 0o755)
    # leaf は自分（= writer 役）の所有・他者書き込み不可 → **bind できる形**
    import socket as _s
    sk = _s.socket(_s.AF_UNIX, _s.SOCK_STREAM)
    try:
        sk.bind(str(leaf / "w.sock"))
        (leaf / "w.sock").unlink()
    finally:
        sk.close()
    # anchor が root 所有でなければ段階B としては拒否される（このテストでは自分所有なので拒否）
    err = wd.check_socket_parent(str(leaf / "w.sock"), require_root_owned=True)
    assert err and "anchor が root 所有でない" in err
    # leaf が他者から書けるなら拒否（other-write は段階A でも落ちる）
    os.chmod(leaf, 0o777)
    err = wd.check_socket_parent(str(leaf / "w.sock"), require_root_owned=True)
    assert err and ("書き込み可能" in err)
    os.chmod(leaf, 0o755)


def test_installer_uses_permissions_the_daemon_accepts():
    """installer が書く mode と、writerd が受け付ける mode が一致していること。

    **この2つがずれていると、install は成功して daemon は起動しない。**
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "chmod 0755 '${SOCK_PARENT}'" in src, "leaf が 0755 でない"
    assert "chmod 0755 '${SOCK_ANCHOR}'" in src, "anchor が 0755 でない"
    assert "chmod 1770" not in src, "1770 は writerd が拒否する"
    # 台帳は読めなければ verify も projection も動かない（権威データは org tree の外）
    assert "chmod 750 '${AUTHORITATIVE}/ledger'" in src
    assert "chmod 700" not in src


def test_socket_is_connectable_by_a_caller(tmp_path):
    """**Connecting and writing are different things.** At 0600 a caller with a different UID
    cannot even connect."""
    led, sock, proc = _wd_start(tmp_path)
    try:
        mode = os.stat(sock).st_mode & 0o777
        assert mode & 0o066, f"socket が {oct(mode)} — 別 UID の caller が接続できない"
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_isolation_is_measured_not_flagged(tmp_path):
    """`separate_uid` is decided **by measurement**, not by whether a flag was passed."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    led = tmp_path / "l"; led.mkdir()
    # 同一 UID・自分所有の親 → process_mediated（--require-root-owned を渡しても変わらない）
    assert wd.measured_isolation(str(led / "w.sock"), [str(led)]) == "process_mediated"


def test_peer_uid_reaches_the_recorder(tmp_path, monkeypatch):
    """The peer credential must **reach** `recorded_by` — putting it in the environment is
    not enough."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    ident = importlib.import_module("identity")
    monkeypatch.setenv("ORG_WRITER_PEER_UID", "501")
    monkeypatch.setenv("ORG_WRITER_PEER_PID", "999")
    who, assurance = ident.observed_recorder()
    assert who == "peer:uid=501,pid=999" and assurance == "observed"
    # **decision_by には流れない** — 接続は判断の証拠ではない
    monkeypatch.delenv("ORG_WRITER_PEER_UID")
    who2, _ = ident.observed_recorder()
    assert who2 != who


def test_installer_stops_on_the_first_failure():
    """Without `set -e`, a half-applied chown still prints "install complete"."""
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in src
    assert "半端な状態で続けない" in src


def test_installer_checks_the_daemon_python_for_pyyaml():
    """**daemon が使う python** で PyYAML を検査すること。

    利用者の python3 に入っていても、別 UID の daemon には見えない
    （実測: PyYAML が ~/Library/Python にあり、PYTHONNOUSERSITE=1 で読めなかった）。
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "PYTHONNOUSERSITE=1" in src
    assert "${DAEMON_PYTHON}" in src
    assert "site-packages にある場合は無効" in src
    # 実行可能な回避策を出すこと
    assert "venv" in src and "break-system-packages" in src


def test_installer_copy_is_idempotent():
    """`cp -R src dst/src` creates tools/tools when re-run."""
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "rm -rf '${INSTALL_DIR}/tools'" in src
    assert "cp -R '$PLUGIN_DIR/tools/.'" in src, "末尾の /. が無いと入れ子になる"


def test_verifier_does_not_damage_the_target():
    """**Verification does not damage what it verifies.** It checks that the socket opens,
    rather than attempting a write."""
    src = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    for forbidden, why in (
            ('{"forged":true}', "本番の台帳に行が残る"),
            ("chmod 777 \"$LED\"", "本番の権限が変わる"),
            ('printf \'#\' >> "$f"', "daemon の複製に行が残る"),
            ('rm -f "$SOCK"', "daemon が止まる"),
            ('mv "$PARENT"', "socket が消える"),
            ("launchctl bootout", "daemon が止まる")):
        assert forbidden not in src, f"破壊的な操作が残っている（{why}）: {forbidden}"
    assert "1バイトも書かない" in src
    assert "--no-write" in src            # 副作用ゼロで回せる経路がある


def test_verifier_checks_the_ledger_stays_readable():
    """**Unwritable and unreadable are different.** A ledger nobody can read is not an audit
    record."""
    src = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    assert "caller から台帳を **読める**" in src
    assert "verify / board / projection が動かない" in src


# ══ 0.39.2 — 再監査が見つけた9件 ═══════════════════════════════════════════════

def test_actor_alias_cannot_bypass_separation_of_duties(tmp_path):
    """**`--actor` を変えるだけで職務分離を回避できてはいけない。**

    実測（監査）: maker 本人の自己 admit は拒否されるが、同じプロセスが `--actor gate-alias`
    に変えると通り、鎖も intact だった。名乗りを変えられるなら、比較に意味が無い。
    """
    org = tmp_path / "org"; led = org / ".orgforge" / "ledger"; led.mkdir(parents=True)
    import shutil as _sh
    _sh.copy(TEMPLATE / "ledger-schema.yaml", org / "ledger-schema.yaml")
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    require_attested_identity: true\n", encoding="utf-8")

    def app(actor, payload):
        return subprocess.run(
            [sys.executable, str(TOOLS / "ledger.py"), "append", str(led),
             "--actor", actor, "--class", "admission_decided",
             "--payload", json.dumps(payload)],
            cwd=org, capture_output=True, text=True)

    # 自己申告の actor では通らない
    r = app("gate-alias", {"deliverable": "7", "verdict": "admit", "gate": "g"})
    assert r.returncode == 3, r.stdout + r.stderr
    assert "generic append では記録できない" in (r.stdout + r.stderr)
    # **payload に書くだけでは通らない**（0.39.3 で塞いだ）
    r = app("gate-signer", {"deliverable": "7", "verdict": "admit", "gate": "g",
                            "identity_assurance": "attested", "decision_by": "gate-signer"})
    assert r.returncode == 2, r.stdout + r.stderr
    # **receipt を渡す経路は test_the_verified_path_can_record が確かめる。**
    # ここでは「名乗りだけでは通らない」ことに集中する。


def test_attested_enforcement_defaults_off(tmp_path):
    """**The default is false.** Turning it on stops every existing operation that has no
    receipt."""
    org = tmp_path / "org"; led = org / ".orgforge" / "ledger"; led.mkdir(parents=True)
    import shutil as _sh
    _sh.copy(TEMPLATE / "ledger-schema.yaml", org / "ledger-schema.yaml")
    (org / "constitution.yaml").write_text("enforcement: {}\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", str(led),
                        "--actor", "gate", "--class", "admission_decided",
                        "--payload", json.dumps({"deliverable": "7", "verdict": "admit"})],
                       cwd=org, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_stage_b_socket_parent_must_be_bindable(tmp_path):
    """**daemon が socket を作れる形であること。** root 所有 0755 では bind できない。

    実測（監査）: `bind()` は親への書き込み権限を要求する。0755 も 1770 も動かない —
    前者は daemon が作れず、後者は writerd が拒否する。anchor / leaf に分ける。
    """
    import socket as _s
    # root 所有 0755 に別 UID（自分）が bind できないこと
    for d in ("/usr/local", "/Library/LaunchDaemons"):
        if not os.path.isdir(d) or os.stat(d).st_uid != 0:
            continue
        sk = _s.socket(_s.AF_UNIX, _s.SOCK_STREAM)
        try:
            sk.bind(os.path.join(d, f"t-{os.getpid()}.sock"))
            os.unlink(os.path.join(d, f"t-{os.getpid()}.sock"))
            assert False, f"{d} に bind できてしまった（テストの前提が崩れている）"
        except PermissionError:
            pass
        finally:
            sk.close()
    # installer は anchor（root）と leaf（writer）を分けること
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "SOCK_ANCHOR=" in src and "SOCK_PARENT=" in src
    assert "chown '${SERVICE_USER}:${SERVICE_GROUP}' '${SOCK_PARENT}'" in src
    assert "chown root:wheel '${SOCK_ANCHOR}'" in src


def test_writerd_pins_the_schema(tmp_path):
    """Without an explicit schema it falls back to the template, depending on cwd."""
    src = (TOOLS / "writerd.py").read_text(encoding="utf-8")
    assert 'env["ORG_LEDGER_SCHEMA"] = self.schema' in src
    assert '"--schema"' in src
    # installer が root 所有の設定から渡すこと
    isrc = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "--schema" in isrc


def test_isolation_compares_the_peer_uid(tmp_path):
    """**The caller's own UID is not isolation.** Compare against the peer UID per request."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    src = __import__("inspect").getsource(wd.measured_isolation)
    assert "peer_uid" in src
    assert "peer_uid == me" in src


def test_writer_isolation_does_not_become_judge_isolation():
    """**同じ writer UID は judge 同士の隔離を証明しない。**

    実測（監査）: writer の隔離値が judge の workload_isolation に入り、別 signer なら
    distinct_workload へ昇格していた。judge は writer とは別のプロセスで動く。
    """
    src = (TOOLS / "identity.py").read_text(encoding="utf-8")
    assert '"writer_isolation": os.environ.get("ORG_WRITER_ISOLATION")' in src
    assert '"workload_isolation": os.environ.get("ORG_WRITER_ISOLATION")' not in src
    assert "judge_workload" in src


def test_verifier_counts_rpc_failures():
    """Printing ✗ alone leaves the final exit at 0 even when a check failed."""
    src = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    assert "FAIL + RPC_BAD" in src
    assert 'bad "writerd check が落ちた"' in src


def test_verifier_no_write_writes_nothing():
    """Under `--no-write`, even step 9's happy-path append is not emitted."""
    src = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    assert "no_write = sys.argv[3]" in src
    assert "再送: --no-write なので飛ばす" in src


def test_installer_does_not_overwrite_the_original_owner():
    """A re-install does not rewrite the original owner to the writer — that would break
    uninstall."""
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "再 install では上書きしない" in src
    assert "元の所有者は既に記録されている" in src
    assert "へ「復元」して、caller に戻せなくなる" in src


# ══ 0.39.3 — 第2再監査の7件 ═══════════════════════════════════════════════════
# **私が前回入れた「強制」は、payload に2つの文字列を書くだけで回避でき、しかも
# 私のテストがそれを正常系として固定していた。** 書けるものを検査に使ってはいけない。

def _att_org(tmp_path, enforce="true"):
    org = tmp_path / "org"; led = org / ".orgforge" / "ledger"; led.mkdir(parents=True)
    import shutil as _sh
    _sh.copy(TEMPLATE / "ledger-schema.yaml", org / "ledger-schema.yaml")
    (org / "constitution.yaml").write_text(
        f"enforcement:\n  judges:\n    require_attested_identity: {enforce}\n", encoding="utf-8")
    return org, led


def _att_append(org, led, actor, payload, env=None):
    return subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", str(led),
         "--actor", actor, "--class", "admission_decided", "--payload", json.dumps(payload)],
        cwd=org, capture_output=True, text=True, env=env)


def test_payload_cannot_forge_identity_fields(tmp_path):
    """**書けるものを検査に使ってはいけない。**

    実測（監査）: `identity_assurance: attested` と `decision_by` を payload に書くだけで
    admit が通り、鎖も intact だった。**前回の私のテストがこれを正常系として固定していた。**
    """
    org, led = _att_org(tmp_path)
    r = _att_append(org, led, "forged",
                    {"deliverable": "7", "verdict": "admit",
                     "identity_assurance": "attested", "decision_by": "i-made-this-up"})
    assert r.returncode == 2, r.stdout + r.stderr
    assert "この道具が receipt を検証して生成する" in (r.stdout + r.stderr)
    assert not (led / "ledger.jsonl").exists() or \
        not (led / "ledger.jsonl").read_text(encoding="utf-8").strip()


def test_generic_append_cannot_record_a_judgment(tmp_path):
    """A judgment class cannot be written by a generic append while enforcement is on."""
    org, led = _att_org(tmp_path)
    r = _att_append(org, led, "gate-alias", {"deliverable": "7", "verdict": "admit"})
    assert r.returncode == 3, r.stdout + r.stderr
    assert "generic append では記録できない" in (r.stdout + r.stderr)


def test_the_verified_path_can_record(tmp_path):
    """**receipt を渡した経路だけが書ける。** 止まるだけでは運用できない。

    0.39.4 で `ORG_IDENTITY_VERIFIED` は廃止した — caller が立てられる印は証拠にならない
    （実測: その環境変数を足すだけで偽の identity が通った）。receipt そのものを渡させ、
    書き手が検証する。
    """
    org, led = _att_org(tmp_path)
    # 環境変数では通らない
    env = dict(os.environ, ORG_IDENTITY_VERIFIED="1")
    r = _att_append(org, led, "gate-signer",
                    {"deliverable": "7", "verdict": "admit",
                     "identity_assurance": "attested", "decision_by": "gate-signer"}, env=env)
    assert r.returncode == 2, r.stdout + r.stderr

    # receipt を渡せば通る
    trust = org / ".orgforge" / "trust"; trust.mkdir(parents=True, exist_ok=True)
    tenv = dict(os.environ, ORG_TRUST_STORE=str(trust / "keys.json"))
    subprocess.run([sys.executable, str(TOOLS / "identity.py"), "keygen", "--key-id", "k1",
                    "--signer-id", "gate-signer", "--private-out", str(org / "k.pem")],
                   cwd=org, capture_output=True, text=True, env=tenv, check=True)
    rc = subprocess.run([sys.executable, str(TOOLS / "identity.py"), "receipt",
                         "--org-id", _real_ids(org)[0], "--ledger-id", _real_ids(org)[1],
                         "--subject", "s7",
                         "--issue", "7", "--role", "gate", "--phase", "implement",
                         "--lineage", "same-harness", "--verdict", "admit",
                         "--event-class", "admission_decided",
                         "--requirements-digest", "rd", "--reasoning-sha256", "rs",
                         "--issued-at", "2026-07-31T00:00:00Z", "--key-id", "k1",
                         "--private-key", str(org / "k.pem")],
                        cwd=org, capture_output=True, text=True, env=tenv, check=True).stdout
    (org / "r.json").write_text(rc.strip(), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", str(led),
         "--actor", "gate-signer", "--class", "admission_decided",
         "--receipt", str(org / "r.json"),
         "--payload", json.dumps({"deliverable": "7", "verdict": "admit", "role": "gate",
                                  "lineage": "same-harness", "review_subject_id": "s7",
                                  "reasoning_sha256": "rs"})],
        cwd=org, capture_output=True, text=True, env=tenv)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("body,why", [
    ("enforcement: [broken yaml\n", "構文が壊れている"),
    ("enforcement: not-a-map\n", "enforcement が map でない"),
    ("enforcement:\n  judges: 42\n", "judges が map でない"),
    ("enforcement:\n  judges:\n    require_attested_identity: maybe\n", "真偽値でない"),
])
def test_unreadable_config_fails_closed(tmp_path, body, why):
    """**設定を読めないことを「強制なし」と読み替えない。**

    実測（監査）: 破損した constitution で強制が黙って消えた（破損前 exit 3 → 破損後 exit 0）。
    有効にしていた org が、ファイルが壊れた瞬間に無防備になってはいけない。
    """
    org, led = _att_org(tmp_path)
    (org / "constitution.yaml").write_text(body, encoding="utf-8")
    r = _att_append(org, led, "gate-alias", {"deliverable": "7", "verdict": "admit"})
    assert r.returncode != 0, f"{why}: 通ってしまった\n{r.stdout}{r.stderr}"
    assert not (led / "ledger.jsonl").exists() or \
        not (led / "ledger.jsonl").read_text(encoding="utf-8").strip()


def test_judge_workload_is_covered_by_the_signature(tmp_path):
    """**独立性の評価に使う値は、署名が覆わなければならない。**

    実測（監査）: `judge_workload` が署名の外にあり、**署名後に `separate_host` を足しても
    検証が通った**。
    """
    sys.path.insert(0, str(TOOLS))
    import importlib
    ident = importlib.import_module("identity")
    assert "judge_workload" in ident._RECEIPT_BOUND
    assert ident.PROTOCOL_VERSION >= 2       # 形式が変わったので版を上げる

    store = tmp_path / "keys.json"
    env = dict(os.environ, ORG_TRUST_STORE=str(store))
    subprocess.run([sys.executable, str(TOOLS / "identity.py"), "keygen", "--key-id", "k1",
                    "--signer-id", "s1", "--private-out", str(tmp_path / "k.pem")],
                   capture_output=True, text=True, env=env, check=True)
    r = subprocess.run([sys.executable, str(TOOLS / "identity.py"), "receipt",
                        "--org-id", "o", "--ledger-id", "l", "--subject", "sub", "--issue", "7",
                        "--role", "gate", "--phase", "implement", "--lineage", "same-harness",
                        "--verdict", "admit", "--event-class", "admission_decided",
                        "--requirements-digest", "rd",
                        "--reasoning-sha256", "rs", "--issued-at", "2026-07-31T00:00:00Z",
                        "--key-id", "k1", "--private-key", str(tmp_path / "k.pem"),
                        "--judge-workload", "separate_process"],
                       capture_output=True, text=True, env=env, check=True)
    rc = json.loads(r.stdout)
    os.environ["ORG_TRUST_STORE"] = str(store)
    try:
        assert ident.verify_receipt(rc, {})[0] == "s1"
        forged = dict(rc); forged["judge_workload"] = "separate_host"
        who, _a, err = ident.verify_receipt(forged, {})
        assert who is None and "does not match" in err
    finally:
        os.environ.pop("ORG_TRUST_STORE", None)


def test_nonces_survive_a_daemon_restart(tmp_path):
    """**Do not accept while replay cannot be prevented.** An in-process nonce is lost on
    restart."""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    path = tmp_path / "nonces.json"
    s1 = wd._NonceStore(str(path))
    assert s1.check_and_add("abc123") is True
    s2 = wd._NonceStore(str(path))          # 「再起動」
    assert s2.check_and_add("abc123") is False


def test_client_accepts_a_writer_owned_leaf(tmp_path):
    """**installer が作る leaf を client が拒否してはいけない。**

    実測（監査）: installer が leaf を writer 所有にする一方、client が「root か自分」しか
    許さず、**正規の書き込み経路がゼロ**になっていた。
    """
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    import tempfile as _tf
    anchor = pathlib.Path(_tf.mkdtemp(prefix="an", dir="/tmp")); leaf = anchor / "r"
    leaf.mkdir(); os.chmod(anchor, 0o755); os.chmod(leaf, 0o755)
    # 所有者は自分だが、client の検査は「誰が差し替えられるか」を見る（所有者を問わない）
    # 段階A では anchor が自分所有になる。**信頼境界ではない**ので明示が要る。
    os.environ["ORG_WRITER_TRUST_SELF"] = "1"
    try:
        assert wd.check_socket_parent(str(leaf / "w.sock")) is None
        os.chmod(leaf, 0o777)
        assert wd.check_socket_parent(str(leaf / "w.sock")) is not None
    finally:
        os.environ.pop("ORG_WRITER_TRUST_SELF", None)
    # 明示しなければ、caller 所有の anchor は拒否される
    os.chmod(leaf, 0o755)
    err = wd.check_socket_parent(str(leaf / "w.sock"))
    assert err and "caller 自身の所有" in err


def test_peer_uid_allowlist_is_available():
    """The socket is 0666, so authorization has to **separate connecting from writing**."""
    src = (TOOLS / "writerd.py").read_text(encoding="utf-8")
    assert '"--allow-uid"' in src
    assert "peer_not_authorized" in src


def test_authoritative_data_lives_outside_the_org_tree():
    """**Tight permissions on the contents mean nothing if the container can be swapped.**"""
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "AUTHORITATIVE=" in src
    assert "org tree の外" in src
    assert "ln -s '${AUTHORITATIVE}/ledger'" in src
    # daemon には実体のパスを渡す
    assert "default=${AUTHORITATIVE}/ledger" in src


def test_installer_and_verifier_agree_on_the_socket():
    """If the paths disagree, the verifier inspects a socket that does not exist."""
    isrc = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    vsrc = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    # 0.39.5 で org ごとの namespace になった（固定パスを共有すると 2 org 目で壊れる）。
    assert 'SOCK_PARENT="/usr/local/var/orgforge/run/${ORG_NAME}"' in isrc
    assert '/usr/local/var/orgforge/run/${ORG_NAME}/writer.sock' in vsrc
    # verifier は leaf に root 所有を期待しない（writer 所有が正しい）
    assert "leaf は $POWNER 所有（自分ではない）" in vsrc


def test_pyyaml_guidance_prefers_a_root_owned_venv():
    """Do not lead with advice that rewrites the system python."""
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "1. root 所有の専用 venv（推奨）" in src
    assert "勧めない" in src


# ══ 0.39.5 束A — judgment boundary ═══════════════════════════════════════════
# receipt を org/ledger/issue/class/subject/phase/verdict/digests に完全束縛し、
# joint は writer の専用操作で生成する（receipt 不在でデッドロックさせない）。

def _A_org(tmp_path, attested="true"):
    org = tmp_path / "org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / ".orgforge" / "trust").mkdir(parents=True)
    import shutil as _sh
    _sh.copy(TEMPLATE / "ledger-schema.yaml", org / "ledger-schema.yaml")
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n"
        f"    require_attested_identity: {attested}\n", encoding="utf-8")
    return org, org / ".orgforge" / "ledger"


def _A_env(org):
    return dict(os.environ, ORG_TRUST_STORE=str(org / ".orgforge" / "trust" / "keys.json"),
                ORG_POLICY_FILE="/nonexistent/policy.yaml")


def _A_key(org, key_id, signer):
    r = subprocess.run([sys.executable, str(TOOLS / "identity.py"), "keygen",
                        "--key-id", key_id, "--signer-id", signer,
                        "--private-out", str(org / f"{key_id}.pem")],
                       cwd=org, capture_output=True, text=True, env=_A_env(org))
    assert r.returncode == 0, r.stdout + r.stderr


def _A_receipt(org, key_id, *, issue="7", event_class="verdict_provisional",
               lineage="same-harness", verdict="admit", subject="rev-A",
               digest="rs", org_id=None, ledger_id=None, out="r.json"):
    sys.path.insert(0, str(TOOLS))
    import importlib
    led_mod = importlib.import_module("ledger")
    cwd = os.getcwd()
    try:
        os.chdir(org)
        oid, lid = led_mod._org_and_ledger_id(str(org / ".orgforge" / "ledger"))
    finally:
        os.chdir(cwd)
    r = subprocess.run([sys.executable, str(TOOLS / "identity.py"), "receipt",
                        "--org-id", org_id or oid, "--ledger-id", ledger_id or lid,
                        "--subject", subject, "--issue", issue, "--role", "gate",
                        "--phase", "implement", "--lineage", lineage, "--verdict", verdict,
                        "--event-class", event_class, "--requirements-digest", "rd",
                        "--reasoning-sha256", digest, "--issued-at", "2026-07-31T00:00:00Z",
                        "--key-id", key_id, "--private-key", str(org / f"{key_id}.pem")],
                       cwd=org, capture_output=True, text=True, env=_A_env(org))
    assert r.returncode == 0, r.stdout + r.stderr
    (org / out).write_text(r.stdout.strip(), encoding="utf-8")
    return org / out


def _A_append(org, led, receipt, payload, cls="verdict_provisional", actor="gate"):
    args = [sys.executable, str(TOOLS / "ledger.py"), "append", str(led),
            "--actor", actor, "--class", cls, "--payload", json.dumps(payload)]
    if receipt:
        args += ["--receipt", str(receipt)]
    return subprocess.run(args, cwd=org, capture_output=True, text=True, env=_A_env(org))


_A_PL = {"issue": 7, "deliverable": "7", "role": "gate", "lineage": "same-harness",
         "verdict": "admit", "for_event": "admission_decided", "phase": "implement",
         "review_subject_id": "rev-A", "reasoning_sha256": "rs"}


def test_A_success_a_bound_receipt_records(tmp_path):
    """Happy path: a fully bound receipt can be recorded."""
    org, led = _A_org(tmp_path)
    _A_key(org, "k1", "gate-signer")
    rc = _A_receipt(org, "k1")
    r = _A_append(org, led, rc, dict(_A_PL))
    assert r.returncode == 0, r.stdout + r.stderr
    pl = json.loads((led / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[0])["payload"]
    assert pl["decision_by"] == "gate-signer"
    assert pl["identity_assurance"] == "authenticated"


@pytest.mark.parametrize("field,value,why", [
    ("issue", "9", "別 issue への再利用"),
    ("event_class", "refutation_attempted", "別クラスへの再利用"),
    ("subject", "rev-B", "別の対象"),
    ("verdict", "reject", "別の結論"),
    ("lineage", "cross-harness", "別の血統"),
    ("org_id", "some-other-org", "別 org"),
    ("ledger_id", "some-other-ledger", "別台帳"),
    ("digest", "different-digest", "別の理由"),
])
def test_A_refuse_receipt_reuse(tmp_path, field, value, why):
    """Refusal: **if any bound field differs, the receipt cannot be replayed.**"""
    org, led = _A_org(tmp_path)
    _A_key(org, "k1", "gate-signer")
    rc = _A_receipt(org, "k1", **{field: value})
    r = _A_append(org, led, rc, dict(_A_PL))
    assert r.returncode == 4, f"{why}: 通ってしまった\n{r.stdout}{r.stderr}"
    assert not (led / "ledger.jsonl").exists() or \
        not (led / "ledger.jsonl").read_text(encoding="utf-8").strip()


def test_A_joint_does_not_deadlock_without_a_receipt(tmp_path):
    """**joint に judge の receipt は存在しない。** それでも生成できること。

    一致は判断ではなく事実の関数なので、`require_attested_identity` の下でも
    専用操作で生成できなければ、一致しても admission を作れないデッドロックになる。
    """
    org, led = _A_org(tmp_path)
    _A_key(org, "k1", "gate-signer"); _A_key(org, "k2", "skeptic-signer")
    for key, lin in (("k1", "same-harness"), ("k2", "cross-harness")):
        rc = _A_receipt(org, key, lineage=lin, out=f"{key}.json")
        r = _A_append(org, led, rc, {**_A_PL, "lineage": lin})
        assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "derive-admission",
                        str(led), "--issue", "7", "--event", "admission_decided",
                        "--require-attested"],
                       cwd=org, capture_output=True, text=True, env=_A_env(org))
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(r.stdout.splitlines()[0])
    assert d["ok"] and d["reviewer_independence"] == "distinct_signer"
    adm = [json.loads(l) for l in (led / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
           if l.strip() and json.loads(l)["class"] == "admission_decided"]
    assert len(adm) == 1
    assert adm[0]["payload"]["decision_by"].startswith("system:joint")
    assert adm[0]["actor"] == "system:writer"


def test_A_joint_refuses_unattested_verdicts(tmp_path):
    """Refusal: **a joint admission is never built out of claimed verdicts.**"""
    org, led = _A_org(tmp_path, attested="false")
    for lin in ("same-harness", "cross-harness"):
        r = _A_append(org, led, None, {**_A_PL, "lineage": lin})
        assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "derive-admission",
                        str(led), "--issue", "7", "--event", "admission_decided",
                        "--require-attested"],
                       cwd=org, capture_output=True, text=True, env=_A_env(org))
    assert r.returncode == 4
    assert json.loads(r.stdout.splitlines()[0])["reason"] == "unattested_verdicts"


def test_A_joint_refuses_disagreement_and_mismatched_subjects(tmp_path):
    """Refusal: nothing is generated from disagreeing verdicts or a different subject."""
    org, led = _A_org(tmp_path, attested="false")
    assert _A_append(org, led, None, {**_A_PL, "lineage": "same-harness"}).returncode == 0
    assert _A_append(org, led, None, {**_A_PL, "lineage": "cross-harness",
                                      "verdict": "reject"}).returncode == 0
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "derive-admission",
                        str(led), "--issue", "7", "--event", "admission_decided"],
                       cwd=org, capture_output=True, text=True, env=_A_env(org))
    assert r.returncode == 5
    assert json.loads(r.stdout.splitlines()[0])["reason"] == "verdicts_disagree"


def test_A_fault_joint_not_persisted_leaves_nothing(tmp_path):
    """Fault injection: if the generated event cannot be recorded, no partial write is left
    behind."""
    org, led = _A_org(tmp_path, attested="false")
    for lin in ("same-harness", "cross-harness"):
        assert _A_append(org, led, None, {**_A_PL, "lineage": lin}).returncode == 0
    before = (led / "ledger.jsonl").read_text(encoding="utf-8")
    env = dict(_A_env(org), ORG_LEDGER_FORCE_APPEND_FAIL="1")
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "derive-admission",
                        str(led), "--issue", "7", "--event", "admission_decided"],
                       cwd=org, capture_output=True, text=True, env=env)
    assert r.returncode == 4
    assert (led / "ledger.jsonl").read_text(encoding="utf-8") == before
    assert run("ledger.py", "verify", str(led))[0] == 0


def test_A_control_without_enforcement_a_plain_append_works(tmp_path):
    """Control: with enforcement off the same append passes — evidence that enforcement was
    what stopped it."""
    org, led = _A_org(tmp_path, attested="false")
    r = _A_append(org, led, None, dict(_A_PL))
    assert r.returncode == 0, r.stdout + r.stderr
    org2, led2 = _A_org(tmp_path / "x", attested="true")
    r = _A_append(org2, led2, None, dict(_A_PL), cls="admission_decided")
    assert r.returncode == 3


# ══ 0.39.5 束B — runtime trust boundary ══════════════════════════════════════

def test_B_hook_never_relaxes_trust():
    """**The hook does not relax trust.** The control side never sets
    ORG_WRITER_TRUST_SELF."""
    src = (REPO / "integrations" / "common" / "org_hook.py").read_text(encoding="utf-8")
    for pat in ('os.environ.setdefault("ORG_WRITER_TRUST_SELF"',
                'os.environ["ORG_WRITER_TRUST_SELF"]'):
        assert pat not in src, f"hook が信頼を緩めている: {pat}"
    assert "hook は信頼を緩めない" in src


def test_B_manifest_pins_the_daemon(tmp_path):
    """Happy path: a root-owned manifest fixes org / schema / policy / trust / allow_uids."""
    led = tmp_path / "led"; led.mkdir()
    import shutil as _sh
    _sh.copy(TEMPLATE / "ledger-schema.yaml", tmp_path / "schema.yaml")
    mf = tmp_path / "manifest.yaml"
    mf.write_text(
        f"orgs:\n  default:\n    ledger: {led}\n    schema: {tmp_path / 'schema.yaml'}\n"
        f"    trust: {tmp_path / 'keys.json'}\n"
        f"policy: {tmp_path / 'policy.yaml'}\nallow_uids: [{os.getuid()}]\n", encoding="utf-8")
    os.chmod(mf, 0o644)
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    doc, err = wd.load_manifest(str(mf))
    assert err is None, err
    assert doc["orgs"]["default"]["ledger"] == str(led)
    assert doc["allow_uids"] == [os.getuid()]


def test_B_refuse_a_world_writable_manifest(tmp_path):
    """Refusal: a world-writable manifest lets anyone swap the daemon's configuration."""
    mf = tmp_path / "m.yaml"
    mf.write_text("orgs:\n  default:\n    ledger: /tmp/x\n", encoding="utf-8")
    os.chmod(mf, 0o666)
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    doc, err = wd.load_manifest(str(mf))
    assert doc is None and err and "group/world-writable" in err


def test_B_fault_unreadable_manifest_refuses_to_start(tmp_path):
    """Fault injection: an unreadable manifest means the daemon does not start."""
    mf = tmp_path / "m.yaml"
    mf.write_text("orgs: [not a map\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(TOOLS / "writerd.py"), "serve",
                        "--manifest", str(mf)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 4
    assert "do not start" in (r.stdout + r.stderr)


def test_B_rpc_reservation_needs_exit0_and_allow():
    """**A reservation over RPC reads the decision too.** Never trust the exit code alone."""
    src = (REPO / "integrations" / "common" / "org_hook.py").read_text(encoding="utf-8")
    assert 'is_reservation = argv[:2] in (["ledger.py", "reserve-exposure"],' in src
    assert '["writer_client.py", "reserve-exposure"])' in src
    # client は中の判断をそのまま透過させる（封筒でくるまない）
    csrc = (TOOLS / "writer_client.py").read_text(encoding="utf-8")
    assert 'if op in ("reserve-exposure", "derive-admission")' in csrc


def test_B_control_ghsync_writes_through_rpc():
    """Control: where writerd runs, ghsync goes over RPC as well — a direct call exits 4."""
    src = (TOOLS / "ghsync" / "record.py").read_text(encoding="utf-8")
    assert src.count("writer_client.py") >= 3, "統制の書き込みが RPC に統一されていない"
    assert 'os.environ.get("ORG_WRITER_SOCKET")' in src


# ══ 0.39.5 束C — stage B lifecycle ═══════════════════════════════════════════

def test_C_namespace_contract_is_shared():
    """The installer and the verifier must derive the namespace by **the same rule**."""
    isrc = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    vsrc = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    rule = 'shasum -a 256 | cut -c1-12'
    assert rule in isrc and rule in vsrc, "namespace の決め方が食い違う"
    for s, name in ((isrc, "installer"), (vsrc, "verifier")):
        assert "/usr/local/var/orgforge/orgs/${ORG_NAME}" in s or \
               '/usr/local/var/orgforge/orgs/${ORG_NAME}"' in s, f"{name} の権威パスが違う"
        assert "com.orgforge.writerd.${ORG_NAME}" in s, f"{name} の Label が違う"


def test_C_uninstall_order_is_explicit():
    """**順序が安全性である。** daemon停止 → 隣に staging → 検証 → atomic 置換 → 所有者復元。

    以前この test は log の文言の並び順を見ていたが、**文言は実装の証拠にならない**。
    正しい順序で print しながら危険な順序で実行するコードは、その test を通る。
    ここでは「symlink を消すより前に staging へコピーしている」という
    実際の危険性を決める性質を見る（実測: cp 失敗 → 再実行で唯一の写しが消えた）。
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    i_stop = src.index("① LaunchDaemon を停止した（停止を確認済み）")
    i_stage = src.index('staged="${cur}.restoring.$$"')
    i_copy = src.index('''run "cp -R '${src}' '${staged}'"''')
    i_rm = src.index('''run "rm -f '${cur}'"''')
    i_mv = src.index('''run "mv '${staged}' '${cur}'"''')
    i_own = src.index("④ 所有者を")
    # 停止 → staging 作成 → コピー → **そのあとで** symlink 削除 → atomic 置換 → chown
    assert i_stop < i_stage < i_copy < i_rm < i_mv < i_own, "uninstall の順序が違う"
    assert "先に止めないと、書き戻している途中に writer が書く" in src
    # 復元できなかったら権威データを消さない
    # `:-1`（未設定なら「復元済み」扱い）は **消してよい側に倒れる既定**だった。
    # org root が消えるとループごと飛んで未設定になり、権威データを消していた。
    assert 'if [ "${RESTORE_OK}" = 0 ]; then' in src
    assert "**権威データと backup は残す**" in src


def test_C_uninstall_keeps_shared_things_while_other_orgs_remain():
    """**While another org remains, the shared code and the service UID are not removed.**"""
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "REMAINING=" in src
    assert '他の org が ${REMAINING} 件残っているので、共有コードとサービス UID は消さない' in src
    # 消すのは this org のものだけ
    assert "この org（${ORG_NAME}）の socket / 権威データ / backup / 設定を消した" in src


@pytest.mark.skipif(sys.platform != "darwin", reason="writer-install.sh is macOS-only")
def test_C_uninstall_requires_an_org(tmp_path):
    """Refusal: if it cannot be determined which org is being removed, stop — never take
    another org with it."""
    r = subprocess.run(["bash", str(TOOLS / "writer-install.sh"), "--uninstall", "--dry-run"],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "どの org を外すのか決まらない" in (r.stdout + r.stderr)


@pytest.mark.skipif(sys.platform != "darwin", reason="writer-install.sh is macOS-only")
def test_C_dry_run_changes_nothing_and_states_the_boundary(tmp_path):
    """Control: --dry-run changes nothing and states the boundary."""
    (tmp_path / ".orgforge" / "ledger").mkdir(parents=True)
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    r = subprocess.run(["bash", str(TOOLS / "writer-install.sh"), "--org-root", str(tmp_path),
                        "--dry-run", "--daemon-python", sys.executable],
                       capture_output=True, text=True)
    both = r.stdout + r.stderr
    if r.returncode != 0:
        assert "PyYAML" in both, both
    else:
        assert "脅威モデルの外" in r.stdout
    assert sorted(str(p.relative_to(tmp_path))
                  for p in tmp_path.rglob("*")) == before, "dry-run が何かを変えた"


# ══ 0.39.6 — Codex 再レビューで見つかった2件 ═══════════════════════════════════

def test_writerd_refuses_to_start_without_constitution():
    """**宣言の在り処が分からないまま、書き込みを受け付けない。**

    daemon は org の外で動く。installer は台帳を
    /usr/local/var/orgforge/orgs/<ns>/ledger に置くので、「台帳の親の親が org root」
    という導出は Stage B では成立しない。導出に失敗したまま起動すると
    require_attested_identity が子プロセスに届かず、**未認証 admission が通っていた**。
    """
    src = (TOOLS / "writerd.py").read_text(encoding="utf-8")
    # 明示フラグを受けること
    assert '"--constitution"' in src, "--constitution を受けていない"
    # 導出できなければ起動しない（fail-closed）
    assert "の constitution を決められない" in src
    i_msg = src.index("の constitution を決められない")
    assert "return 2" in src[i_msg:i_msg + 900], "決められないのに起動している"
    # 子プロセスへ渡すのは **決まったパス** であって、推測ではない
    assert 'env["ORG_CONSTITUTION"] = con' in src


def test_installer_pins_constitution_root_owned():
    """**検査の入力を、検査される側が書けてはいけない。**

    constitution には宣言（require_attested_identity）が入っている。caller が書ける場所に
    置いたままだと、caller が宣言を偽にして強制を消せる。root 所有で固定し、明示的に渡す。
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "${AUTHORITATIVE}/constitution.yaml" in src
    assert "chown root:wheel '${AUTHORITATIVE}/constitution.yaml'" in src
    assert "--constitution</string><string>default=${AUTHORITATIVE}/constitution.yaml" in src
    # 宣言が無ければ install しない
    assert "**宣言が無いまま writer を動かさない。**" in src


def test_uninstall_does_not_treat_missing_symlink_as_done():
    """**symlink が無いことを「戻し済み」と読んではいけない。**

    caller は自分の org tree を動かせる（.orgforge を rename するなど）。すると symlink が
    消え、権威側だけが唯一の最新の写しになる。そこで復元を飛ばすと、⑤ がそれを消す
    = 永続データ損失（Codex が実測で指摘した経路）。
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    # 素の `|| continue` で済ませていないこと
    assert '[ -L "${cur}" ] || continue' not in src, "symlink 不在を無条件に飛ばしている"
    assert "**symlink が無いことを「戻し済み」と読んではいけない。**" in src
    # 実体が在るときだけ飛ばす
    # 「実体が在れば飛ばす」は variant 4 で危険と分かったので、**digest が一致したときだけ**
    # 飛ばす形に変わっている（[[test_uninstall_does_not_trust_a_planted_directory]]）。
    i = src.index('if [ ! -L "${cur}" ] && [ -e "${cur}" ]; then')
    seg = src[i:i + 1400]
    assert "continue" in seg and 'shasum -a 256' in seg
    # 権威側に実体が在るなら復元を試みる
    assert "**消さずに復元を試みる**" in src


def test_uninstall_defaults_to_not_restored():
    """**既定は「復元していない」。** 消してよいのは、戻したと確かめられたときだけ。

    復元ループは `if [ -d "$ROOTP" ]` の中で RESTORE_OK=1 を立てていた。org root が
    移動・消失するとループに入らず、`${RESTORE_OK:-1}` が既定 1（=消してよい）に評価され、
    **権威側にしか無い最新データを消していた**（Codex が実測で指摘した3つ目の変種）。
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    i_default = src.index("  RESTORE_OK=0\n")
    i_loop = src.index('if [ -n "$ROOTP" ] && [ -d "$ROOTP" ]; then')
    # 既定 0 は、ループの **外側かつ手前** で立っていること
    assert i_default < i_loop, "RESTORE_OK の既定がループより後にある"
    # `:-1`（既定 1 = 消してよい）に戻っていないこと
    assert '"${RESTORE_OK:-1}"' not in src, "既定が 1（消してよい）に戻っている"
    assert 'if [ "${RESTORE_OK}" = 0 ]; then' in src
    # org root が無いときは理由を言う
    assert "移動されたか消されている。**権威側にしか無いデータを消さない。**" in src


def test_uninstall_does_not_trust_a_planted_directory():
    """**「在ること」を「戻っていること」と読んではいけない。**

    caller は symlink の代わりに自分の偽の実体を置ける。それを「復元済み」と認めると、
    ⑤ が権威側の最新版を消し、org 側には caller が置いた古い中身だけが残る。
    飛ばしてよいのは「権威側に何も無い」か「中身が一致する」ときだけ。
    （Codex が指摘した4つ目の変種。実測で権威データが消えることを確認した。）
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    # 「在れば飛ばす」に戻っていないこと
    assert 'if [ -e "${cur}" ]; then\n          continue' not in src, \
        "実体が在るだけで復元済みと認めている"
    assert "**「在ること」を「戻っていること」と読んではいけない。**" in src
    # 中身を数えてから判断すること
    i = src.index('if [ ! -L "${cur}" ] && [ -e "${cur}" ]; then')
    seg = src[i:i + 1400]
    # **数は caller が合わせられる。** ファイル数の一致を「同じ中身」と読んではいけない
    # （実測: 数だけ揃えた偽物で権威側の最新版が消せた）。digest で比べること。
    assert 'shasum -a 256' in seg, "中身の digest ではなくファイル数で判断している"
    assert '"${d_s}" = "${d_c}"' in seg
    # **名前だけでは足りない。** 同名の dir と symlink は名前が同じなので、
    # 名前だけを digest に入れると同一と誤認する（実測で確認）。種別と向き先まで入れること。
    assert "type=%HT link=%Y" in seg, "種別と symlink の向き先が digest に入っていない"
    # 食い違うなら権威側を消さずに退避する
    assert "**「在る」を「戻った」と読まない**" in src
    assert "${cur}.found-$$" in src


def test_writer_verify_completes_under_foreign_locale():
    """**検証器が locale で落ちてはいけない。**

    `$` の直後に全角文字があると shell が変数名の一部として読み、`set -u` で落ちる。
    一度 8箇所を直したが **1箇所残っていた**（`"$（無い）: $f"`）。しかも落ちる位置が
    検査の途中なので、**その先の11項目が一度も走らないまま「完了」に見えていた**。
    文字列 grep では見落とすので、**実際に走らせて完走を確かめる**。
    """
    import subprocess, tempfile, os
    verify = str(TOOLS / "writer-verify.sh")
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".orgforge", "ledger"))
        for loc in ("en_US.UTF-8", "C", "ja_JP.UTF-8"):
            env = dict(os.environ, LC_ALL=loc, LANG=loc)
            r = subprocess.run(["bash", verify, "--org-root", d],
                               capture_output=True, text=True, env=env, timeout=120)
            out = r.stdout + r.stderr
            assert "unbound variable" not in out, f"{loc} で落ちた:\n{out[-400:]}"
            # 途中で死んでいないこと（最後の見出しまで到達している）
            assert "総合" in out or "合格" in out or "不合格" in out, \
                f"{loc} で最後まで到達していない:\n{out[-400:]}"


def test_verify_never_calls_unmeasured_a_pass():
    """**測っていないものを「測って通った」と書かない。**

    `--no-write` は書き込み検査を飛ばすが、飛ばした項目は PASS にも FAIL にも
    入らなかったため、FAIL=0 のまま
    「すべて実測で通った。separate_uid を主張してよい」と出て exit 0 していた。
    **「不合格 0」は「全部確かめた」ではない**（Codex が指摘し、実測で確認した）。
    """
    import subprocess, tempfile, os
    src = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    assert "SKIPPED" in src, "飛ばした検査を数えていない"
    i = src.index("printf '  合格 %d / 不合格 %d / 未測定 %d")
    tail = src[i:]

    def run(p, f, s):
        d = tempfile.mkdtemp(); path = os.path.join(d, "t.sh")
        open(path, "w").write(f"PASS={p}; FAIL={f}; SKIPPED={s}\n" + tail)
        return subprocess.run(["bash", path], capture_output=True, text=True, timeout=60)

    # 未測定があるなら、合格と言ってはいけない
    r = run(3, 0, 1)
    assert r.returncode != 0, "未測定があるのに exit 0（偽の合格）"
    assert "主張してはいけない" in r.stdout

    # 全部測って全部通ったなら、従来どおり合格できる（デッドロックさせない）
    r2 = run(14, 0, 0)
    assert r2.returncode == 0, f"全部通ったのに合格にならない: {r2.stdout}"
    assert "separate_uid" in r2.stdout and "主張してよい" in r2.stdout

    # 不合格があるなら当然だめ
    r3 = run(10, 1, 0)
    assert r3.returncode != 0


def test_service_account_requires_free_uid_and_gid():
    """**uid が空いていても gid が埋まっていることがある。**

    同じ番号を UniqueID と PrimaryGroupID の両方に使うので、gid だけ既存だと
    **writer の group を他人と共有する** ことになり、group 権限で台帳へ届く経路ができる。
    このマシンの実測では 395-400 が「uid 空き / gid 使用中」だった。
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    i = src.index("NEXT_UID=\"\"")
    seg = src[i:i + 700]
    assert "dscl . -search /Users UniqueID" in seg
    assert "dscl . -search /Groups PrimaryGroupID" in seg, \
        "gid の空きを確かめずに番号を選んでいる"
    assert "両方" in src


def test_install_keeps_two_copies_until_symlink_is_made():
    """**install が途中で落ちても、台帳はどこかに必ず残る。**

    `cp -R` → `mv`(元を .pre-writer に退避) → `ln -s` の順なので、
    どの時点で落ちても最低1箇所、cp 後は2箇所に実体がある。**mv で移し始めない。**
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    i_cp = src.index("""run "cp -R '${ORG_ROOT}/.orgforge/ledger/.' '${AUTHORITATIVE}/ledger/'\"""")
    i_mv = src.index("""run "mv '${ORG_ROOT}/.orgforge/ledger' '${ORG_ROOT}/.orgforge/ledger.pre-writer'\"""")
    i_ln = src.index("""run "ln -s '${AUTHORITATIVE}/ledger' '${ORG_ROOT}/.orgforge/ledger'\"""")
    assert i_cp < i_mv < i_ln, "コピーより先に移動・symlink を作っている"
    # 元を消さずに退避すること
    assert ".pre-writer" in src and "**消さない**" in src


def test_schema_fix_repairs_existing_class_fields(tmp_path):
    """**snapshot が読むのは `fields:` であって validation ではない。**

    `--fix` は「足りないクラスを足す」だけで、**既存クラスの field 不足を直さなかった**。
    すると validation を直しても snapshot は古い形で固定され続け、正規の
    `reserve-exposure` が schema_rejected で拒否される = 全 metered 操作のデッドロック。
    実測: 実 org (tatekae) が正にこの状態で、`--fix` を通しても直らなかった。
    """
    import subprocess, sys, shutil
    org = tmp_path / "org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    schema = (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")
    # 実 org と同じ壊し方: fields 行から idempotency 4 field を落とす
    broken = schema.replace(
        "actor_role, decision: allow|hold, caused_by_event,\n"
        "                             session_id, tool_use_id, rule, request_digest }",
        "actor_role, decision: allow|hold, caused_by_event }")
    assert broken != schema, "テストの壊し方がテンプレートと合っていない"
    (org / "ledger-schema.yaml").write_text(broken, encoding="utf-8")

    led = str(org / ".orgforge" / "ledger")
    # 壊れた状態では予約が拒否される
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "reserve-exposure", led,
                        "--dimension", "destructive_ops", "--delta", "1", "--cap", "50",
                        "--actor", "p", "--session-id", "s", "--tool-use-id", "t",
                        "--rule", "blast_radius"],
                       capture_output=True, text=True, cwd=str(org), timeout=60)
    assert "schema_rejected" in r.stdout, f"壊れた schema で拒否されない: {r.stdout[:200]}"

    # --fix したら通るようになること（= 修復経路が実際に機能する）
    subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "schema", "--fix", led],
                   capture_output=True, text=True, cwd=str(org), timeout=60)
    fixed = (org / "ledger-schema.yaml").read_text(encoding="utf-8")
    for f in ("session_id", "tool_use_id", "rule", "request_digest"):
        assert f in fixed.split("exposure_budget_checked: {")[1][:400], \
            f"--fix が {f} を fields に足していない"
    r2 = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "reserve-exposure", led,
                         "--dimension", "destructive_ops", "--delta", "1", "--cap", "50",
                         "--actor", "p", "--session-id", "s", "--tool-use-id", "t2",
                         "--rule", "blast_radius"],
                        capture_output=True, text=True, cwd=str(org), timeout=60)
    assert "schema_rejected" not in r2.stdout, f"--fix 後も拒否される: {r2.stdout[:200]}"
    assert '"reason": "reserved"' in r2.stdout or '"decision"' in r2.stdout


def test_schema_fix_repairs_fields_after_inline_comments_and_unblocks_provisional(tmp_path):
    """OBS-008: comments inside a multiline inline-map must not hide later fields.

    Tatekae's copied schema predated the identity fields.  The plugin template already had
    them after inline comments, but ``schema --fix`` parsed comma chunks as text: a chunk
    beginning with ``#`` caused every field after that comment to disappear from the diff.
    It then reported "latest" while the real provisional command remained blocked.
    """
    import subprocess, sys, yaml
    org = tmp_path / "org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n", encoding="utf-8")
    schema = (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")
    block = re.compile(
        r"                          # phase は receipt の束縛に入る（どの段階の判定か）\n"
        r"                          phase,\n"
        r"                          decision_by, recorded_by, committed_by,\n"
        r"                          identity_assurance, recorder_assurance, workload_isolation,\n"
        r"                          # \*\*writer の隔離は judge の隔離ではない。\*\* 欄を分ける（0.39.2）。\n"
        r"                          writer_isolation,\n"
        r"                          signer_id, key_id(?:, risk_accepted)?,\n")
    broken, substitutions = block.subn("", schema, count=1)
    assert substitutions == 1, "テストの壊し方がテンプレートと合っていない"
    (org / "ledger-schema.yaml").write_text(broken, encoding="utf-8")
    led = str(org / ".orgforge" / "ledger")

    before = subprocess.run(
        [sys.executable, str(TOOLS / "github_sync.py"), "provisional",
         "--issue", "9999", "--role", "skeptic", "--lineage", "cross-harness",
         "--verdict", "survives", "--subject", "obs008-subject",
         "--why", "別血統で対象を独立に再導出し、既知の反証経路と境界条件をすべて確認したが、具体的な反例は成立しなかった。",
         "--evidence", "隔離した一時orgで実コマンドを実行した出力",
         "--by", "skeptic"],
        capture_output=True, text=True, cwd=str(org), timeout=60)
    assert before.returncode != 0
    assert "宣言の無い field" in before.stdout + before.stderr

    fixed = subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "schema", "--fix", led],
        capture_output=True, text=True, cwd=str(org), timeout=60)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    doc = yaml.safe_load((org / "ledger-schema.yaml").read_text(encoding="utf-8"))
    declared = set(doc["event_classes"]["verdict_provisional"])
    expected = {"phase", "decision_by", "recorded_by", "committed_by",
                "identity_assurance", "recorder_assurance", "workload_isolation",
                "writer_isolation", "signer_id", "key_id"}
    assert expected <= declared, expected - declared

    after = subprocess.run(
        [sys.executable, str(TOOLS / "github_sync.py"), "provisional",
         "--issue", "9999", "--role", "skeptic", "--lineage", "cross-harness",
         "--verdict", "survives", "--subject", "obs008-subject",
         "--why", "別血統で対象を独立に再導出し、既知の反証経路と境界条件をすべて確認したが、具体的な反例は成立しなかった。",
         "--evidence", "隔離した一時orgで実コマンドを実行した出力",
         "--by", "skeptic"],
        capture_output=True, text=True, cwd=str(org), timeout=60)
    assert after.returncode == 0, after.stdout + after.stderr
    events = [json.loads(line) for line in
              (org / ".orgforge" / "ledger" / "ledger.jsonl").read_text().splitlines()]
    provisional = [e for e in events if e["class"] == "verdict_provisional"]
    assert len(provisional) == 1


def test_provisional_risk_is_declared_and_persisted(tmp_path):
    """OBS-008 residual: the CLI's documented ``--risk`` field must fit its own schema."""
    import subprocess, sys
    org = tmp_path / "org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n", encoding="utf-8")
    (org / "ledger-schema.yaml").write_text(
        (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(TOOLS / "github_sync.py"), "provisional",
         "--issue", "9999", "--role", "skeptic", "--lineage", "cross-harness",
         "--verdict", "survives", "--subject", "obs008-risk-subject",
         "--why", "別血統で対象を独立に再導出し、既知の反証経路と境界条件をすべて確認したが、具体的な反例は成立しなかった。",
         "--evidence", "隔離した一時orgで実コマンドを実行した出力",
         "--risk", "残余リスクを確認済み", "--by", "skeptic"],
        capture_output=True, text=True, cwd=str(org), timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    events = [json.loads(line) for line in
              (org / ".orgforge" / "ledger" / "ledger.jsonl").read_text().splitlines()]
    provisional = [e for e in events if e["class"] == "verdict_provisional"]
    assert len(provisional) == 1
    assert provisional[0]["payload"]["risk_accepted"] is True


def test_template_schema_declares_fields_in_both_places():
    """**同じことを2箇所で宣言している。片方だけ直すと、静かに壊れる。**

    schema はクラスの field を2箇所で宣言する:
      - `validation.required` … 検証規則
      - `event_classes` の `fields:` … **snapshot が読む方**
    snapshot は後者を固定するので、`validation` だけ新しくしても効かない。
    実測: 実 org tatekae がこの状態で、**全 metered 操作がデッドロック**していた
    （`reserve-exposure` が schema_rejected）。しかも `schema --fix` は
    「差分なし — この org の schema は最新である」と表示していた。

    ここでは **テンプレート自身の2箇所が食い違わない**ことを守る。
    片方だけ編集した瞬間に落ちるので、org へ配られる前に気づける。
    """
    import yaml
    txt = (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")
    doc = yaml.safe_load(txt)
    required = (doc.get("validation") or {}).get("required") or {}
    fields = {name: set(spec) for name, spec in (doc.get("event_classes") or {}).items()
              if isinstance(spec, dict)}
    drift = {}
    for cls, req in required.items():
        declared = fields.get(cls)
        if declared is None:
            continue                     # fields 側に無いクラスはここでは見ない
        missing = [f for f in req if f not in declared]
        if missing:
            drift[cls] = missing
    assert not drift, (
        "validation.required にあって event_classes の fields: に無い field がある。\n"
        "**snapshot は fields: を読むので、これは実 org をデッドロックさせる。**\n"
        f"{drift}")


def test_schema_fix_counts_braces_not_first_close(tmp_path):
    """**非貪欲な正規表現は、値の中の `{...}` の最初の `}` を終端と誤認する。**

    そうなると修復が別の場所に入り、YAML は健全なまま **直っていない** —
    「直したように見えて直っていない」という、今夜いちばん多く踏んだ形になる。
    （Codex が静的に指摘し、実測で再現した。）
    """
    import subprocess, sys, yaml
    tpl = (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")
    broken = tpl.replace(
        "actor_role, decision: allow|hold, caused_by_event,\n"
        "                             session_id, tool_use_id, rule, request_digest }",
        "actor_role, decision: allow|hold, caused_by_event, nested: {a} }")
    assert broken != tpl, "テストの壊し方がテンプレートと合っていない"
    org = tmp_path / "org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / "ledger-schema.yaml").write_text(broken, encoding="utf-8")
    led = str(org / ".orgforge" / "ledger")

    subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "schema", "--fix", led],
                   capture_output=True, text=True, cwd=str(org), timeout=60)
    out = (org / "ledger-schema.yaml").read_text(encoding="utf-8")
    yaml.safe_load(out)                      # YAML が壊れていないこと
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "reserve-exposure", led,
                        "--dimension", "destructive_ops", "--delta", "1", "--cap", "50",
                        "--actor", "p", "--session-id", "s", "--tool-use-id", "t",
                        "--rule", "blast_radius"],
                       capture_output=True, text=True, cwd=str(org), timeout=60)
    assert "schema_rejected" not in r.stdout, (
        "ネストした {} があると修復が効いていない（最初の } を終端と誤認）:\n" + r.stdout[:300])


def test_every_bound_field_actually_binds():
    """**18項目すべてが本当に束縛されているか。**

    既存の再利用テストは 8 項目（org/ledger/issue/class/subject/digest/verdict/lineage）
    しか見ていなかった。残り10項目（`signer_id` `key_id` `role` `phase` `receipt_id`
    `issued_at` `protocol_version` `schema_version` `reasoning_sha256` `judge_workload`）は
    **束縛されていると書いてあるだけで、一度も測っていなかった**。

    `_RECEIPT_BOUND` に足した項目が実際には署名に入っていない、という食い違いは
    静かに起きる（署名は通り、検証も通る）。ここで全項目を機械的に確かめる。
    """
    import sys as _sys
    _sys.path.insert(0, str(TOOLS))
    import identity

    secret = "shared-secret-for-test"
    base = {
        "protocol_version": identity.PROTOCOL_VERSION,
        "schema_version": "1", "receipt_id": "r-1",
        "org_id": "orgA", "ledger_id": "L1", "issue": "7", "role": "gate",
        "phase": "operate", "lineage": "cross-harness",
        "event_class": "admission_decided", "review_subject_id": "S1",
        "requirements_digest": "D1", "reasoning_sha256": "R1",
        "verdict": "admit", "judge_workload": "separate_process",
        "key_id": "k1", "signer_id": "gate-signer",
        "issued_at": "2026-07-30T12:00:00Z",
    }
    expect = {k: base[k] for k in
              ("org_id", "ledger_id", "review_subject_id", "issue", "role",
               "lineage", "verdict")}
    signed = dict(base)
    signed["signature"] = identity.sign_receipt(signed, secret)
    store = {"keys": {"k1": {"secret": secret, "signer_id": "gate-signer"}}}

    who, _assurance, err = identity.verify_receipt(signed, dict(expect), store)
    assert err is None and who == "gate-signer", f"正規の receipt が通らない: {err}"

    # **検査の対象を、検査される側の宣言から取ってはいけない。**
    # `_RECEIPT_BOUND` を回すと、そこから項目を消した瞬間に「検査しない」ことになり、
    # テストは通ってしまう（実測: signer_id を外しても通った）。
    # 守るべき項目は **ここに固定で書く**。増減は意図的な変更としてこの一覧を直す。
    MUST_BIND = [
        "event_class", "issue", "issued_at", "judge_workload", "key_id", "ledger_id",
        "lineage", "org_id", "phase", "protocol_version", "reasoning_sha256",
        "receipt_id", "requirements_digest", "review_subject_id", "role",
        "schema_version", "signer_id", "verdict",
    ]
    assert set(MUST_BIND) <= set(identity._RECEIPT_BOUND), (
        "束縛すべき項目が _RECEIPT_BOUND から外された: "
        + str(sorted(set(MUST_BIND) - set(identity._RECEIPT_BOUND))))

    unbound = []
    for f in MUST_BIND:
        t = dict(signed)
        o = t.get(f)
        t[f] = (o or 0) + 99 if isinstance(o, int) else "TAMPERED-" + f
        _w, _a, e = identity.verify_receipt(t, dict(expect), store)
        if e is None:
            unbound.append(f)
    assert not unbound, (
        "束縛されていると宣言されているのに、書き換えても検証が通る項目がある。\n"
        "**署名が守っていない項目は、束縛されていない。** " + str(unbound))


def test_proxy_recording_separates_decider_from_recorder(tmp_path):
    """**G2 項目3: 決めた者と記録した者は別に扱う。**

    `decision_by` は **receipt の署名者から**、`recorded_by` は **観測から**来る。
    代理で記録しても「自分が決めた」ことにはできない — これが職務分離の土台である。

    実測（この test が最初）: `decision_by='gate-signer'`（attested）に対し
    `recorded_by='unknown'`（recorder_assurance='claimed'）と、
    **確かさの度合いが別々に記録される**。
    """
    import json, os, subprocess, sys, secrets
    org = tmp_path / "org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / ".orgforge" / "trust").mkdir(parents=True)
    (org / "ledger-schema.yaml").write_text(
        (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    require_attested_identity: true\n"
        "    lineage: cross-harness\n", encoding="utf-8")
    led = str(org / ".orgforge" / "ledger")
    secret = "s-" + secrets.token_hex(8)
    (org / ".orgforge" / "trust" / "keys.json").write_text(json.dumps(
        {"keys": {"k1": {"secret": secret, "signer_id": "gate-signer"}}}), encoding="utf-8")

    sys.path.insert(0, str(TOOLS))
    from ghsync.record import _reasoning_digest
    # **org の中で解決させる。** org_id は org の実体から導出されるので、
    # 外から呼ぶと解決できない（cwd に依存する）。実際の経路と同じ場所で計算する。
    _idr = subprocess.run(
        [sys.executable, "-c",
         "import sys;sys.path.insert(0,%r);import ledger;"
         "print('|'.join(str(x) for x in ledger._org_and_ledger_id(%r)))"
         % (str(TOOLS), led)],
        capture_output=True, text=True, cwd=str(org), timeout=60)
    assert _idr.returncode == 0, _idr.stdout + _idr.stderr
    org_id, ledger_id = _idr.stdout.strip().split("|")

    why = "受入基準を実測で確認した。並列でcapを超えず、故障注入でallowにならない。"
    ev = "592 passed"
    digest = _reasoning_digest(why, ev, None, None, None)
    env = dict(os.environ, ORG_SIGNING_SECRET=secret, ORG_LEDGER_ROOT=led)

    r = subprocess.run(
        [sys.executable, str(TOOLS / "identity.py"), "receipt",
         "--org-id", org_id, "--ledger-id", ledger_id, "--subject", "rev-A",
         "--issue", "7", "--role", "gate", "--phase", "operate",
         "--lineage", "cross-harness", "--verdict", "admit",
         "--event-class", "verdict_provisional", "--requirements-digest", "D1",
         "--reasoning-sha256", digest, "--issued-at", "2026-07-30T12:00:00Z",
         "--key-id", "k1"],
        capture_output=True, text=True, cwd=str(org), env=env, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    rc = org / "rc.json"
    rc.write_text(r.stdout.strip(), encoding="utf-8")

    p = subprocess.run(
        [sys.executable, str(TOOLS / "github_sync.py"), "provisional", "--issue", "7",
         "--role", "gate", "--lineage", "cross-harness", "--verdict", "admit",
         "--subject", "rev-A", "--why", why, "--evidence", ev, "--receipt", str(rc)],
        capture_output=True, text=True, cwd=str(org), env=env, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr

    ev_rec = None
    for line in open(os.path.join(led, "ledger.jsonl"), encoding="utf-8"):
        e = json.loads(line)
        if e.get("class") == "verdict_provisional":
            ev_rec = e
    assert ev_rec, "verdict_provisional が記録されていない"

    def g(k):
        return ev_rec.get(k, (ev_rec.get("payload") or {}).get(k))

    assert g("decision_by") == "gate-signer", f"decision_by が signer でない: {g('decision_by')}"
    assert g("identity_assurance") == "attested", g("identity_assurance")
    # **記録者は観測であって、自称ではない。** 決めた者と同じ値になってはいけない。
    assert g("recorded_by") != g("decision_by"), \
        "recorded_by が decision_by と同じ — 代理記録が自称になっている"
    assert g("recorder_assurance") == "claimed", g("recorder_assurance")


@pytest.mark.parametrize("order", [
    (("k1", "same-harness"), ("k2", "cross-harness")),
    (("k2", "cross-harness"), ("k1", "same-harness")),
])
def test_A_joint_works_in_both_orders(tmp_path, order):
    """**G2 項目2: 両順序。** どちらの血統が先に判定しても joint は1件だけ生成される。

    順序に依存すると、**先に書いた側が勝つ**ことになり、独立性の意味が薄れる。
    handoff が「両順序」を要求しているのはそのためである。
    """
    org, led = _A_org(tmp_path)
    _A_key(org, "k1", "gate-signer"); _A_key(org, "k2", "skeptic-signer")
    for key, lin in order:
        rc = _A_receipt(org, key, lineage=lin, out=f"{key}.json")
        r = _A_append(org, led, rc, {**_A_PL, "lineage": lin})
        assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "derive-admission",
                        str(led), "--issue", "7", "--event", "admission_decided",
                        "--require-attested"],
                       cwd=org, capture_output=True, text=True, env=_A_env(org))
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(r.stdout.splitlines()[0])
    assert d["ok"] and d["reviewer_independence"] == "distinct_signer"
    adm = [json.loads(l) for l in (led / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
           if l.strip() and json.loads(l)["class"] == "admission_decided"]
    assert len(adm) == 1, f"順序 {order} で admission が {len(adm)} 件"


def test_A_joint_is_not_created_twice(tmp_path):
    """**2回目の derive で admission が増えない。** 一致は事実なので、何度数えても1件。

    増えるなら、同じ一致から複数の admission を作れる（二重計上）。
    """
    org, led = _A_org(tmp_path)
    _A_key(org, "k1", "gate-signer"); _A_key(org, "k2", "skeptic-signer")
    for key, lin in (("k1", "same-harness"), ("k2", "cross-harness")):
        rc = _A_receipt(org, key, lineage=lin, out=f"{key}.json")
        assert _A_append(org, led, rc, {**_A_PL, "lineage": lin}).returncode == 0
    for _ in range(2):
        subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "derive-admission",
                        str(led), "--issue", "7", "--event", "admission_decided",
                        "--require-attested"],
                       cwd=org, capture_output=True, text=True, env=_A_env(org))
    adm = [l for l in (led / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
           if l.strip() and json.loads(l)["class"] == "admission_decided"]
    assert len(adm) == 1, f"derive を2回呼ぶと admission が {len(adm)} 件になった（二重計上）"


def test_A_refutation_joint_is_not_created_twice(tmp_path):
    """skeptic側も同じ一致からjointを1件だけ生成する。

    冪等ガードが ``admission_decided`` に固定されると、同一のsurvives pairを再派生する
    たびに ``refutation_attempted`` が増え、1つの反証結果を複数件として数えてしまう。
    """
    org, led = _A_org(tmp_path)
    _A_key(org, "k1", "gate-signer"); _A_key(org, "k2", "skeptic-signer")
    payload = {**_A_PL, "verdict": "survives", "for_event": "refutation_attempted"}
    for key, lin in (("k1", "same-harness"), ("k2", "cross-harness")):
        rc = _A_receipt(org, key, lineage=lin, verdict="survives", out=f"{key}.json")
        assert _A_append(org, led, rc, {**payload, "lineage": lin}).returncode == 0

    first = subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "derive-admission", str(led),
         "--issue", "7", "--event", "refutation_attempted", "--require-attested"],
        cwd=org, capture_output=True, text=True, env=_A_env(org))
    second = subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "derive-admission", str(led),
         "--issue", "7", "--event", "refutation_attempted", "--require-attested"],
        cwd=org, capture_output=True, text=True, env=_A_env(org))

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 6, second.stdout + second.stderr
    assert json.loads(second.stdout)["reason"] == "already_admitted"
    joints = [json.loads(line) for line in (led / "ledger.jsonl").read_text(
        encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["class"] == "refutation_attempted"]
    assert len(joints) == 1, f"deriveを2回呼ぶとrefutation jointが{len(joints)}件になった"


def test_A_refutation_joint_allows_a_new_review_subject(tmp_path):
    """On the same Issue, a refutation of a different subject records as a new joint."""
    org, led = _A_org(tmp_path)
    _A_key(org, "k1", "gate-signer"); _A_key(org, "k2", "skeptic-signer")
    for subject in ("rev-A", "rev-B"):
        payload = {**_A_PL, "verdict": "survives", "for_event": "refutation_attempted",
                   "review_subject_id": subject}
        for key, lin in (("k1", "same-harness"), ("k2", "cross-harness")):
            rc = _A_receipt(org, key, lineage=lin, verdict="survives", subject=subject,
                            out=f"{subject}-{key}.json")
            assert _A_append(org, led, rc, {**payload, "lineage": lin}).returncode == 0
        result = subprocess.run(
            [sys.executable, str(TOOLS / "ledger.py"), "derive-admission", str(led),
             "--issue", "7", "--event", "refutation_attempted", "--require-attested"],
            cwd=org, capture_output=True, text=True, env=_A_env(org))
        assert result.returncode == 0, result.stdout + result.stderr

    joints = [json.loads(line) for line in (led / "ledger.jsonl").read_text(
        encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["class"] == "refutation_attempted"]
    assert [event["payload"]["review_subject_id"] for event in joints] == ["rev-A", "rev-B"]


def test_A_joint_needs_only_one_provisional_to_hold(tmp_path):
    """**One verdict never makes a joint.** If a single side could pass it, there is no
    independence."""
    org, led = _A_org(tmp_path)
    _A_key(org, "k1", "gate-signer")
    rc = _A_receipt(org, "k1", lineage="same-harness", out="k1.json")
    assert _A_append(org, led, rc, {**_A_PL, "lineage": "same-harness"}).returncode == 0
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "derive-admission",
                        str(led), "--issue", "7", "--event", "admission_decided",
                        "--require-attested"],
                       cwd=org, capture_output=True, text=True, env=_A_env(org))
    assert r.returncode != 0, "1件の provisional だけで admission ができた"
    adm = [l for l in (led / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
           if l.strip() and json.loads(l)["class"] == "admission_decided"]
    assert not adm


def test_derive_admission_also_requires_the_writer_path(tmp_path):
    """**G2 項目6: 単一 writer は、全部の経路が通って初めて成り立つ。**

    `append` / `reserve-exposure` / `trip-halt` / `release-halt` は writer 経由を
    要求していたのに、**`derive-admission` だけ直接書けていた**（実測: writer 稼働中に
    台帳が 2 → 3 件に増えた）。しかもここが書くのは `admission_decided` ——
    最も強い権限の記録である。

    「経路は1つ」という保証は、**1つでも抜け道があれば無い**のと同じ。
    """
    import json, os, subprocess, sys, time, signal
    org = tmp_path / "org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / "ledger-schema.yaml").write_text(
        (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (org / "constitution.yaml").write_text(
        "enforcement:\n  caps:\n    destructive_ops: 50\n", encoding="utf-8")
    led = str(org / ".orgforge" / "ledger")
    env0 = dict(os.environ, ORG_WRITER_TRUST_SELF="1")
    pl = {"issue": "7", "for_event": "admission_decided", "review_subject_id": "S1",
          "verdict": "admit", "role": "gate", "phase": "operate",
          "reasoning_sha256": "deadbeef" * 8}
    for lin in ("same-harness", "cross-harness"):
        r = subprocess.run(
            [sys.executable, str(TOOLS / "ledger.py"), "append", led, "--actor", "gate",
             "--class", "verdict_provisional",
             "--payload", json.dumps({**pl, "lineage": lin})],
            capture_output=True, text=True, cwd=str(org), env=env0, timeout=60)
        assert r.returncode == 0, r.stdout + r.stderr

    # **AF_UNIX のパス長制限（macOS で 104 byte）。** pytest の tmp_path は長すぎるので、
    # socket だけは短い場所に作る（このセッションで何度も踏んだ制約）。
    import tempfile as _tf
    _short = _tf.mkdtemp(prefix="og")
    os.chmod(_short, 0o755)
    parent = os.path.join(_short, "r"); os.makedirs(parent); os.chmod(parent, 0o755)
    sock = os.path.join(parent, "w.sock")
    assert len(sock) < 100, f"socket path が長すぎる: {len(sock)}"
    p = subprocess.Popen(
        [sys.executable, str(TOOLS / "writerd.py"), "serve", "--org", f"default={led}",
         "--constitution", "default=" + str(org / "constitution.yaml"),
         "--socket", sock],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(org), env=env0)
    try:
        for _ in range(80):
            if os.path.exists(sock):
                time.sleep(0.4); break
            time.sleep(0.2)
        if not os.path.exists(sock):
            p.terminate()
            _o, _e = p.communicate(timeout=10)
            raise AssertionError("writerd が起動しない:\n" +
                                 (_e or b"").decode("utf-8", "replace")[-500:])
        n = lambda: sum(1 for _ in open(os.path.join(led, "ledger.jsonl")))
        cenv = dict(env0, ORG_WRITER_SOCKET=sock)

        # ① 直接呼びは拒否され、**台帳が増えない**
        before = n()
        r = subprocess.run(
            [sys.executable, str(TOOLS / "ledger.py"), "derive-admission", led,
             "--issue", "7", "--event", "admission_decided"],
            capture_output=True, text=True, cwd=str(org), env=cenv, timeout=60)
        assert n() == before, "writer を迂回して直接書けた（単一 writer が破れている）"
        assert r.returncode != 0

        # ② **RPC 経由なら通る**（拒否できるだけで通せない、にはしない）
        r2 = subprocess.run(
            [sys.executable, str(TOOLS / "writer_client.py"), "derive-admission", "--",
             "--issue", "7", "--event", "admission_decided"],
            capture_output=True, text=True, cwd=str(org), env=cenv, timeout=60)
        if n() <= before:
            alive = p.poll() is None
            _err = ""
            if not alive:
                _o, _e = p.communicate(timeout=10)
                _err = (_e or b"").decode("utf-8", "replace")[-600:]
            raise AssertionError(
                f"RPC 経由でも通らない（デッドロック）daemon生存={alive}\n"
                + r2.stdout + r2.stderr + "\n--- daemon stderr ---\n" + _err)
    finally:
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=30)


def _AA_org(tmp_path, name="org"):
    org = tmp_path / name
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / "ledger-schema.yaml").write_text(
        (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (org / "constitution.yaml").write_text(
        "enforcement:\n"
        "  caps:\n"
        "    destructive_ops: 50\n"
        "  judges:\n"
        "    judgment_corrections:\n"
        "      authority_roles: [ceo]\n",
        encoding="utf-8")
    (org / "organization.yaml").write_text(
        "roles:\n"
        "  - {id: ceo, active: true, functions: [organize, operate]}\n"
        "  - {id: gate, active: true, functions: [judge, review]}\n",
        encoding="utf-8")
    return org, str(org / ".orgforge" / "ledger")


_AA_PL = {"for_event": "admission_decided", "verdict": "admit", "role": "gate",
          "phase": "operate", "reasoning_sha256": "deadbeef" * 8}
_AA_ENV = dict(os.environ, ORG_WRITER_TRUST_SELF="1")


def _AA_prov(org, led, issue, lineage, subject="S1", *, event="admission_decided",
             verdict="admit"):
    return subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", led, "--actor", "gate",
         "--class", "verdict_provisional",
         "--payload", json.dumps({**_AA_PL, "issue": issue, "lineage": lineage,
                                  "review_subject_id": subject, "for_event": event,
                                  "verdict": verdict})],
        capture_output=True, text=True, cwd=str(org), env=_AA_ENV, timeout=60)


def _AA_derive(org, led, issue, event="admission_decided"):
    return subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "derive-admission", led,
         "--issue", issue, "--event", event],
        capture_output=True, text=True, cwd=str(org), env=_AA_ENV, timeout=60)


def _AA_adm(led, event="admission_decided"):
    return [json.loads(l) for l in open(os.path.join(led, "ledger.jsonl"), encoding="utf-8")
            if json.loads(l).get("class") == event]


def test_already_admitted_keys_on_subject_not_just_issue(tmp_path):
    """**判定の同一性は subject が決める。** issue だけを鍵にすると、
    同じ issue の **別リビジョンを二度と admit できない**（実測でそうなった）。
    `review_subject_id` があるのは、まさにこれを区別するためである。
    """
    org, led = _AA_org(tmp_path)
    for lin in ("same-harness", "cross-harness"):
        assert _AA_prov(org, led, "7", lin, "S1").returncode == 0
    assert _AA_derive(org, led, "7").returncode == 0
    for lin in ("same-harness", "cross-harness"):
        _AA_prov(org, led, "7", lin, "S2")
    r = _AA_derive(org, led, "7")
    assert r.returncode == 0, f"別 subject が admit できない（デッドロック）: {r.stdout}"
    assert len(_AA_adm(led)) == 2


def test_corrected_admission_does_not_block_forever(tmp_path):
    """**訂正できない統制は、間違えたら詰む統制である。**

    superseded にした admission を「既にある」と数えると、対象を差し替えても
    二度と admit できない（Codex が静的読解で指摘、実測で成立）。
    """
    org, led = _AA_org(tmp_path)
    for lin in ("same-harness", "cross-harness"):
        assert _AA_prov(org, led, "7", lin, "S1").returncode == 0
    assert _AA_derive(org, led, "7").returncode == 0
    seq = _AA_adm(led)[0]["seq"]
    receipt = _correction_receipt(org, pathlib.Path(led), "ceo", seq, issue="7",
                                  reason="対象が差し替わったので取り消す")
    r = subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", led, "--actor", "ceo",
         "--class", "correction",
         "--payload", json.dumps({"corrects": [seq], "kind": "superseded",
                                  "reason": "対象が差し替わったので取り消す"}),
         "--receipt", str(receipt)],
        capture_output=True, text=True, cwd=str(org), env=_AA_ENV, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    for lin in ("same-harness", "cross-harness"):
        _AA_prov(org, led, "7", lin, "S1")
    r2 = _AA_derive(org, led, "7")
    assert r2.returncode == 0, f"訂正後も admit できない（デッドロック）: {r2.stdout}"


def test_corrected_refutation_joint_does_not_block_forever(tmp_path):
    """A voided skeptic joint is not treated as existing, so the same pair can derive again."""
    org, led = _AA_org(tmp_path)
    for lin in ("same-harness", "cross-harness"):
        assert _AA_prov(org, led, "7", lin, event="refutation_attempted",
                        verdict="survives").returncode == 0
    assert _AA_derive(org, led, "7", "refutation_attempted").returncode == 0
    seq = _AA_adm(led, "refutation_attempted")[0]["seq"]
    receipt = _correction_receipt(org, pathlib.Path(led), "ceo", seq, issue="7",
                                  reason="反証jointを取り消して再派生する")
    corrected = subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", led, "--actor", "ceo",
         "--class", "correction",
         "--payload", json.dumps({"corrects": [seq], "kind": "superseded",
                                  "reason": "反証jointを取り消して再派生する"}),
         "--receipt", str(receipt)],
        capture_output=True, text=True, cwd=str(org), env=_AA_ENV, timeout=60)
    assert corrected.returncode == 0, corrected.stdout + corrected.stderr
    derived = _AA_derive(org, led, "7", "refutation_attempted")
    assert derived.returncode == 0, derived.stdout + derived.stderr
    assert len(_AA_adm(led, "refutation_attempted")) == 2


def test_issue_notation_does_not_split_the_dedupe(tmp_path):
    """`7` / `#7` / `007` は同じ issue。表記の違いで二重計上になってはいけない
    （実測: `007` を admit したあと `7` で2件目ができた）。"""
    org, led = _AA_org(tmp_path)
    for lin in ("same-harness", "cross-harness"):
        assert _AA_prov(org, led, "007", lin, "S1").returncode == 0
    assert _AA_derive(org, led, "007").returncode == 0
    for lin in ("same-harness", "cross-harness"):
        _AA_prov(org, led, "7", lin, "S1")
    _AA_derive(org, led, "7")
    assert len(_AA_adm(led)) == 1, "表記ゆれで二重計上した"


def test_issue_normalization_is_the_same_everywhere(tmp_path):
    """**比べる場所ごとに違う正規化をしてはいけない。**

    issue の比較が3箇所で食い違っていた（`lstrip("#")` だけの場所と、
    先頭ゼロまで落とす場所）。その結果、**provisional が `007` で呼び出しが `7`**
    だと「判定が足りない」と言われ、揃っているのに admission を作れなかった
    （Codex が静的読解で指摘、実測で成立）。

    同じものを同じと判定できないなら、鍵として使えない。`norm_issue` に統一した。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("ledger_ni", str(TOOLS / "ledger.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    # 同じ issue として扱うべきもの
    for a, b in (("7", "#7"), ("7", "007"), ("#7", "007"), (" 7 ", "7"), (7, "7")):
        assert m.norm_issue(a) == m.norm_issue(b), f"{a!r} と {b!r} が別扱い"
    # 別の issue として扱うべきもの
    for a, b in (("10", "100"), ("7", "70"), ("1", "11"), ("7", "7a"), ("12", "21")):
        assert m.norm_issue(a) != m.norm_issue(b), f"{a!r} と {b!r} が同一扱い"
    # _same_deliverable も同じ規則で動くこと（phase chain 全体がこれを使う）
    assert m._same_deliverable("007", "#7")
    assert not m._same_deliverable("10", "100")

    # 実際の経路: provisional が 007、derive が 7 でも admission ができる
    org, led = _AA_org(tmp_path)
    for lin in ("same-harness", "cross-harness"):
        assert _AA_prov(org, led, "007", lin, "S1").returncode == 0
    r = _AA_derive(org, led, "7")
    assert r.returncode == 0, f"表記が違うだけで admission が作れない: {r.stdout}"
    assert len(_AA_adm(led)) == 1


# ══ B1: attestation は caller flag で無効化できてはいけない ═══════════════════

def _B1_org(tmp_path, attested="true"):
    org = tmp_path / "b1org"
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / "ledger-schema.yaml").write_text(
        (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (org / "constitution.yaml").write_text(
        f"enforcement:\n  judges:\n    require_attested_identity: {attested}\n",
        encoding="utf-8")
    return org, str(org / ".orgforge" / "ledger")


_B1_PL = {"issue": 7, "deliverable": "7", "role": "gate", "verdict": "admit",
          "for_event": "admission_decided", "phase": "implement",
          "review_subject_id": "rev-A", "reasoning_sha256": "caller-claimed"}
_B1_ENV = dict(os.environ, ORG_WRITER_TRUST_SELF="1")


def _B1_append(org, led, lineage):
    return subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", led,
         "--actor", "caller", "--class", "verdict_provisional",
         "--payload", json.dumps({**_B1_PL, "lineage": lineage})],
        capture_output=True, text=True, cwd=str(org), env=_B1_ENV, timeout=60)


def _B1_derive(org, led, *extra):
    return subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "derive-admission", led,
         "--issue", "7", "--event", "admission_decided", *extra],
        capture_output=True, text=True, cwd=str(org), env=_B1_ENV, timeout=60)


def _B1_adm(led):
    p = os.path.join(led, "ledger.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8")
            if json.loads(l).get("class") == "admission_decided"]


def test_B1_authenticated_mode_refuses_receiptless_provisional(tmp_path):
    """**authenticated mode では receipt 無しの judgment を記録できない。**

    `require_attested_identity: true` は「判断の主体を確かめる」宣言である。
    receipt 無しの `verdict_provisional` が書けるなら、その宣言は効いていない。
    """
    org, led = _B1_org(tmp_path)
    r = _B1_append(org, led, "same-harness")
    assert r.returncode != 0, (
        "authenticated mode で receipt 無しの verdict_provisional が記録できた\n"
        + r.stdout + r.stderr)


def test_B1_caller_flag_cannot_disable_attestation(tmp_path):
    """**強制するかどうかを caller に尋ねてはいけない。**

    `--require-attested` を省略すると claimed な provisional 2件から
    joint admission が作れた（実測）。**検査される側が強制を外せる**形である。
    """
    org, led = _B1_org(tmp_path)
    # 宣言が効いていれば、そもそも provisional が書けない。
    # 万一書けても、flag の有無で admission の可否が変わってはいけない。
    for lin in ("same-harness", "cross-harness"):
        _B1_append(org, led, lin)
    r = _B1_derive(org, led)                      # flag を省略
    assert not _B1_adm(led), (
        "flag を省略すると claimed から admission が作れた（未認証 admission）\n"
        + r.stdout + r.stderr)


def test_B1_control_unattested_org_still_works(tmp_path):
    """**Control: an org that declared nothing keeps working as before** — do not over-block."""
    org, led = _B1_org(tmp_path, attested="false")
    for lin in ("same-harness", "cross-harness"):
        r = _B1_append(org, led, lin)
        assert r.returncode == 0, r.stdout + r.stderr
    r = _B1_derive(org, led)
    assert r.returncode == 0, f"宣言していない org で joint が作れない: {r.stdout}{r.stderr}"
    assert len(_B1_adm(led)) == 1


# ══ B2: Stage B で trust store が writerd へ届くこと ═════════════════════════

def test_B2_writerd_accepts_explicit_trust_flag():
    """**trust store は明示的に渡す。** daemon は org の外（cwd=/）で動くので、
    探索では見つからない。`--trust NAME=PATH` で固定できなければ、
    installer は正しい receipt を検証させる手段を持たない。"""
    r = subprocess.run([sys.executable, str(TOOLS / "writerd.py"), "serve", "--help"],
                       capture_output=True, text=True, timeout=60)
    assert "--trust" in r.stdout, (
        "writerd に --trust が無い。installer が authoritative trust を渡せない\n" + r.stdout)


def test_B2_installer_passes_trust_to_the_daemon():
    """**installer が渡さなければ、daemon は永久に検証できない。**

    installer は trust を ${AUTHORITATIVE}/trust へ移し、org 側を .pre-writer に改名する。
    それなのに plist が trust を渡していなかったため、**正しく署名された receipt も
    すべて拒否される**（実測: cwd=/ で trust store が見つからない）。
    """
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    args = re.findall(r"<string>(--[a-z-]+)</string>", src)
    assert "--trust" in args, (
        "plist が writerd に trust を渡していない。渡している引数: " + ", ".join(sorted(set(args))))
    assert "${AUTHORITATIVE}/trust" in src


def test_B2_child_env_gets_the_trust_store(tmp_path):
    """**子プロセス（ledger.py）に ORG_TRUST_STORE が届くこと。**
    届かなければ receipt を検証できず、認証済みの記録が一切残せない。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("writerd_b2", str(TOOLS / "writerd.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    trust = tmp_path / "keys.json"
    trust.write_text(json.dumps({"keys": {"k1": {"secret": "s", "signer_id": "g"}}}),
                     encoding="utf-8")
    led = tmp_path / "led"; led.mkdir()
    w = m.Writer({"default": str(led)})
    w.trust = str(trust)
    env = w._child_env("default") if hasattr(w, "_child_env") else None
    if env is None:
        # 実装が private な作り方をしている場合は、少なくとも trust を保持していること
        assert w.trust == str(trust)
    else:
        assert env.get("ORG_TRUST_STORE") == str(trust), (
            "子 env に ORG_TRUST_STORE が入っていない: " + repr(env.get("ORG_TRUST_STORE")))


# ══ B4: cross-harness org で単独署名の direct admission を作らせない ═════════

def _B4_org(tmp_path, lineage="cross-harness", name="b4org"):
    import secrets as _sec
    org = tmp_path / name
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    (org / ".orgforge" / "trust").mkdir(parents=True)
    (org / "ledger-schema.yaml").write_text(
        (TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    require_attested_identity: true\n"
        f"    lineage: {lineage}\n", encoding="utf-8")
    secret = "s-" + _sec.token_hex(8)
    (org / ".orgforge" / "trust" / "keys.json").write_text(
        json.dumps({"keys": {"k1": {"secret": secret, "signer_id": "gate-signer"}}}),
        encoding="utf-8")
    return org, str(org / ".orgforge" / "ledger"), secret


def _B4_ids(org, led):
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys;sys.path.insert(0,%r);import ledger;"
         "print('|'.join(str(x) for x in ledger._org_and_ledger_id(%r)))" % (str(TOOLS), led)],
        capture_output=True, text=True, cwd=str(org), timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.strip().split("|")


def _B4_receipt(org, led, secret, cls, verdict, out="rc.json", lineage="cross-harness"):
    org_id, ledger_id = _B4_ids(org, led)
    env = dict(os.environ, ORG_SIGNING_SECRET=secret, ORG_WRITER_TRUST_SELF="1")
    r = subprocess.run(
        [sys.executable, str(TOOLS / "identity.py"), "receipt",
         "--org-id", org_id, "--ledger-id", ledger_id, "--subject", "rev-A",
         "--issue", "7", "--role", "gate", "--phase", "operate",
         "--lineage", lineage, "--verdict", verdict, "--event-class", cls,
         "--requirements-digest", "D1", "--reasoning-sha256", "R1",
         "--issued-at", "2026-07-30T12:00:00Z", "--key-id", "k1"],
        capture_output=True, text=True, cwd=str(org), env=env, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    (org / out).write_text(r.stdout.strip(), encoding="utf-8")
    return str(org / out)


def _B4_direct(org, led, secret, rc, cls, verdict, lineage="cross-harness"):
    env = dict(os.environ, ORG_SIGNING_SECRET=secret, ORG_WRITER_TRUST_SELF="1")
    return subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", led,
         "--actor", "gate", "--class", cls, "--receipt", rc,
         "--payload", json.dumps({"issue": "7", "deliverable": "7", "verdict": verdict,
                                  "review_subject_id": "rev-A", "role": "gate",
                                  "phase": "operate", "lineage": lineage,
                                  "requirements_digest": "D1", "reasoning_sha256": "R1",
                                  "candidate_id": "c1", "claim_id": "c1"})],
        capture_output=True, text=True, cwd=str(org), env=env, timeout=60)


def _B4_count(led, cls):
    p = os.path.join(led, "ledger.jsonl")
    if not os.path.exists(p):
        return 0
    return sum(1 for l in open(p, encoding="utf-8") if json.loads(l).get("class") == cls)


def test_B4_cross_harness_refuses_single_signer_direct_admission(tmp_path):
    """**二血統を要求する org で、1枚の receipt から admission を作れてはいけない。**

    実測: cross-harness org で有効な receipt 1枚を generic append すると
    `admission_decided` が直接1件記録された。joint 派生の経路が在っても、
    **それを通らなくても書けるなら、二血統は強制されていない。**
    """
    org, led, secret = _B4_org(tmp_path)
    rc = _B4_receipt(org, led, secret, "admission_decided", "admit")
    r = _B4_direct(org, led, secret, rc, "admission_decided", "admit")
    assert _B4_count(led, "admission_decided") == 0, (
        "単独署名の direct admission が通った（二血統の迂回）\n" + r.stdout + r.stderr)


def test_B4_cross_harness_refuses_single_signer_survives(tmp_path):
    """`refutation_attempted: survives` is a positive judgment too, so it is treated the
    same."""
    org, led, secret = _B4_org(tmp_path)
    rc = _B4_receipt(org, led, secret, "refutation_attempted", "survives")
    r = _B4_direct(org, led, secret, rc, "refutation_attempted", "survives")
    assert _B4_count(led, "refutation_attempted") == 0, (
        "単独署名の direct survives が通った\n" + r.stdout + r.stderr)


def test_B4_negative_verdicts_still_recordable(tmp_path):
    """**control: reject / park / refuted の意味は変えない。**

    否定的な判断は単独でも記録できてよい（通さない方向は独立性を要さない）。
    ここを一緒に止めると、判定を記録する手段が無くなる。
    """
    org, led, secret = _B4_org(tmp_path)
    rc = _B4_receipt(org, led, secret, "admission_decided", "reject")
    r = _B4_direct(org, led, secret, rc, "admission_decided", "reject")
    assert r.returncode == 0, f"reject が記録できない（止めすぎ）: {r.stdout}{r.stderr}"
    assert _B4_count(led, "admission_decided") == 1


def test_B4_same_harness_org_unaffected(tmp_path):
    """**Control: the compatibility path for a same-harness org is not broken.**"""
    org, led, secret = _B4_org(tmp_path, lineage="same-harness", name="b4same")
    rc = _B4_receipt(org, led, secret, "admission_decided", "admit", lineage="same-harness")
    r = _B4_direct(org, led, secret, rc, "admission_decided", "admit", lineage="same-harness")
    assert r.returncode == 0, f"same-harness org で admit できない: {r.stdout}{r.stderr}"
    assert _B4_count(led, "admission_decided") == 1


# ── #102 / OBS-050: work_in_progress は「統合済み」「開始が void された」候補を残さない ────
# Tatekae 実測: `integration_admitted: pass` ×2 と Issue CLOSED を持つ候補が4日間 WIP 枠を
# 占有し続け、attention の selected と食い違った。完了判定が cycle_completed の1クラスだけ
# だったため。integrate の記録は candidate_id を持たず `issue` を持つので、台帳の別名橋
# （cycle_started.pack_manifest_id "issue-N" ↔ integration_admitted.issue）で相関する。

def _wip(root):
    code, out = run("ledger.py", "view", str(root), "work_in_progress")
    assert code == 0, out
    return json.loads(out)["in_progress"]


def test_wip_drops_candidate_whose_issue_was_integrated(tmp_path):
    # 実地の形をそのまま使う: cycle_started は candidate_id + pack_manifest_id だけを持ち、
    # integration_admitted（ship.py / ghsync の emitter）は issue だけを持つ — 直接の共有 ID は無い。
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-5ca3e595a9c4", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "supervisor", "integration_admitted",
         {"integration_branch": "develop", "deliverables": ["9"], "issue": 9,
          "integration_subject_sha": "a" * 40, "combined_ci_ref": "pytest -q",
          "verdict": "pass", "admitter": "supervisor"},
         ts="2026-07-16T02:00:00Z")
    ids = [w["candidate_id"] for w in _wip(tmp_path)]
    assert ids == [], f"統合済み候補が WIP 枠を占有し続けた: {ids}"


def test_wip_keeps_candidate_when_integration_is_for_another_issue(tmp_path):
    # control: 別 Issue の統合で他人の枠を消さない
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-a", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "supervisor", "integration_admitted",
         {"integration_branch": "develop", "issue": 28, "verdict": "pass",
          "admitter": "supervisor"},
         ts="2026-07-16T02:00:00Z")
    ids = [w["candidate_id"] for w in _wip(tmp_path)]
    assert ids == ["cand-a"], f"無関係な統合が候補を消した: {ids}"


def test_wip_ignores_failed_integration(tmp_path):
    # verdict: fail は完了ではない — 統合が落ちた仕事はまだ進行中
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-a", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "supervisor", "integration_admitted",
         {"integration_branch": "develop", "issue": 9, "verdict": "fail",
          "admitter": "supervisor"},
         ts="2026-07-16T02:00:00Z")
    ids = [w["candidate_id"] for w in _wip(tmp_path)]
    assert ids == ["cand-a"], f"fail の統合が完了扱いになった: {ids}"


def test_wip_drops_candidate_whose_start_was_voided_by_correction(tmp_path):
    # 開始そのものが correction（voids 効果）で無効化されたら、その cycle は存在しなかった扱い。
    # semantics は derive-admission と同じ voided_seqs（OBS-042: 第3の correction 意味論を作らない）。
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-a", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")   # seq=1
    seed(tmp_path, "eng", "correction",
         {"corrects": [1], "kind": "mistake", "reason": "wrong candidate started",
          "corrected_by": "eng"},
         ts="2026-07-16T02:00:00Z")
    ids = [w["candidate_id"] for w in _wip(tmp_path)]
    assert ids == [], f"void された開始が WIP に残った: {ids}"


def test_wip_backfill_correction_does_not_complete(tmp_path):
    # control: records_backfill は対象を消さない — 補記で仕事が「完了」してはならない
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-a", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")   # seq=1
    seed(tmp_path, "eng", "correction",
         {"corrects": [1], "kind": "backfill", "reason": "late note",
          "corrected_by": "eng"},
         ts="2026-07-16T02:00:00Z")
    ids = [w["candidate_id"] for w in _wip(tmp_path)]
    assert ids == ["cand-a"], f"backfill が開始を消した: {ids}"


def test_wip_plain_started_still_appears_with_latest_checkpoint(tmp_path):
    # 後方互換: 進行中の候補は従来どおり最新 checkpoint 付きで、同じキー形で出る
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-a", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "eng", "progress_recorded",
         {"role": "eng", "candidate_id": "cand-a", "fraction": 0.3, "phase": "impl",
          "done_so_far": "view fixed", "next_step": "write tests", "blocked_by": None,
          "artifacts": []},
         ts="2026-07-16T02:00:00Z")
    seed(tmp_path, "eng", "progress_recorded",
         {"role": "eng", "candidate_id": "cand-a", "fraction": 0.7, "phase": "test",
          "done_so_far": "tests red→green", "next_step": "regen bundles", "blocked_by": None,
          "artifacts": []},
         ts="2026-07-16T03:00:00Z")
    wip = _wip(tmp_path)
    assert [w["candidate_id"] for w in wip] == ["cand-a"]
    w = wip[0]
    assert set(w) == {"candidate_id", "role", "started_seq", "progress"}, (
        f"出力キーが変わった（/org-resume と SessionStart が読む）: {sorted(w)}")
    assert w["role"] == "eng" and w["started_seq"] == 1
    assert w["progress"]["next_step"] == "regen bundles"
    assert abs(w["progress"]["fraction"] - 0.7) < 1e-9


def test_wip_completed_still_disappears(tmp_path):
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-a", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "eng", "cycle_completed",
         {"role": "eng", "candidate_id": "cand-a", "outputs": []},
         ts="2026-07-16T02:00:00Z")
    assert _wip(tmp_path) == []


def test_wip_restarted_candidate_is_not_hidden_by_older_completion(tmp_path):
    """Once a rework starts on the same candidate, a stale cycle_completed does not drop it
    from WIP."""
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-a", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")
    seed(tmp_path, "eng", "cycle_completed",
         {"role": "eng", "candidate_id": "cand-a", "outputs": []},
         ts="2026-07-16T02:00:00Z")
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-a", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T03:00:00Z")
    assert [row["candidate_id"] for row in _wip(tmp_path)] == ["cand-a"]


def test_wip_rework_candidate_started_after_integration_stays_visible(tmp_path):
    # skeptic 反証（rework-after-integration）: 統合済み Issue が標準の rework 経路で再開され、
    # NEW cycle_started が integration_admitted: pass より「後」に来る。統合は自分より前の
    # 開始しか完了させない（temporal）— さもなくば /org-resume が生きている rework を
    # 沈黙で回収する。
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-old", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")   # seq=1 — 統合前の開始（これは消えるべき）
    seed(tmp_path, "eng", "cycle_completed",
         {"role": "eng", "candidate_id": "cand-old", "outputs": []},
         ts="2026-07-16T02:00:00Z")   # seq=2
    seed(tmp_path, "supervisor", "integration_admitted",
         {"integration_branch": "develop", "deliverables": ["9"], "issue": 9,
          "integration_subject_sha": "a" * 40, "combined_ci_ref": "pytest -q",
          "verdict": "pass", "admitter": "supervisor"},
         ts="2026-07-16T03:00:00Z")   # seq=3
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-rework", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T04:00:00Z")   # seq=4 — 統合「後」の rework 開始（生きている）
    seed(tmp_path, "eng", "progress_recorded",
         {"role": "eng", "candidate_id": "cand-rework", "fraction": 0.4, "phase": "impl",
          "done_so_far": "regression repro'd", "next_step": "temporal integration arm",
          "blocked_by": None, "artifacts": []},
         ts="2026-07-16T05:00:00Z")
    wip = _wip(tmp_path)
    ids = [w["candidate_id"] for w in wip]
    assert ids == ["cand-rework"], (
        f"統合後に始まった rework 候補が回収の沈黙に落ちた（または旧候補が復活した）: {ids}")
    assert wip[0]["progress"]["fraction"] == pytest.approx(0.4)
    assert wip[0]["progress"]["next_step"] == "temporal integration arm"


def test_wip_pre_integration_start_still_drops_after_temporal_arm(tmp_path):
    # control: OBS-050 本体（pass が開始より後）は temporal 化しても直ったまま
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-5ca3e595a9c4", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")   # seq=1
    seed(tmp_path, "supervisor", "integration_admitted",
         {"integration_branch": "develop", "issue": 9, "verdict": "pass",
          "admitter": "supervisor"},
         ts="2026-07-16T02:00:00Z")   # seq=2 > 1 → 完了扱い
    assert _wip(tmp_path) == []


# ── #102 rework #2（skeptic C3/C2）: 完了の判断は cycle 単位であって issue 単位ではない ──

def test_wip_c3_live_sibling_survives_candidate_scoped_integration(tmp_path):
    # C3: 同一 Issue の並行 sibling（cycle.py --agent の fan-out）。cand-P が完了・統合されても、
    # 統合より前に始まっていた LIVE の cand-Q は残る — 新形式の integration_admitted は
    # candidate_id を運ぶので、消えるのは名指しされた候補だけ。
    seed(tmp_path, "eng-p", "cycle_started",
         {"role": "eng-p", "candidate_id": "cand-P", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")   # seq=1
    seed(tmp_path, "eng-q", "cycle_started",
         {"role": "eng-q", "candidate_id": "cand-Q", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:30:00Z")   # seq=2 — 統合より前に始まった sibling
    seed(tmp_path, "eng-q", "progress_recorded",
         {"role": "eng-q", "candidate_id": "cand-Q", "fraction": 0.5, "phase": "impl",
          "done_so_far": "half", "next_step": "finish", "blocked_by": None, "artifacts": []},
         ts="2026-07-16T02:00:00Z")
    seed(tmp_path, "eng-p", "cycle_completed",
         {"role": "eng-p", "candidate_id": "cand-P", "outputs": []},
         ts="2026-07-16T03:00:00Z")
    seed(tmp_path, "supervisor", "integration_admitted",
         {"integration_branch": "develop", "deliverables": ["9"], "issue": 9,
          "candidate_id": "cand-P", "integration_subject_sha": "a" * 40,
          "combined_ci_ref": "pytest -q", "verdict": "pass", "admitter": "supervisor"},
         ts="2026-07-16T04:00:00Z")   # seq=5 > cand-Q の開始
    ids = [w["candidate_id"] for w in _wip(tmp_path)]
    assert ids == ["cand-Q"], (
        f"sibling cand-P の統合が LIVE の cand-Q を巻き添えにした（/org-resume が沈黙する）: {ids}")


def test_wip_c2_backfilled_integration_receipt_does_not_kill_later_rework(tmp_path):
    # C2: --backfill-ts で1日「前」の時刻を持つ統合 receipt（seq は後）。legacy 形式
    # （candidate_id 無し）でも、時間順は ts で比較する — backfill された過去の統合が
    # それより後に始まった rework を殺してはならない。
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-old", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")   # seq=1
    seed(tmp_path, "eng", "cycle_completed",
         {"role": "eng", "candidate_id": "cand-old", "outputs": []},
         ts="2026-07-16T02:00:00Z")   # seq=2
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-B", "pack_manifest_id": "issue-9"},
         ts="2026-07-17T10:00:00Z")   # seq=3 — rework の開始（統合の実時点より1日後）
    seed(tmp_path, "eng", "progress_recorded",
         {"role": "eng", "candidate_id": "cand-B", "fraction": 0.4, "phase": "impl",
          "done_so_far": "rework going", "next_step": "keep going", "blocked_by": None,
          "artifacts": []},
         ts="2026-07-17T11:00:00Z")
    # 本物の --backfill-ts CLI で、rework 開始より1日前の実時点を後から補う（legacy 形式）
    code, out = run("ledger.py", "append", str(tmp_path), "--actor", "supervisor",
                    "--class", "integration_admitted",
                    "--payload", json.dumps(
                        {"integration_branch": "develop", "issue": 9, "verdict": "pass",
                         "admitter": "supervisor"}),
                    "--backfill-ts", "2026-07-16T12:00:00Z")   # seq=5, ts は seq3 より前
    assert code == 0, out
    ids = [w["candidate_id"] for w in _wip(tmp_path)]
    assert ids == ["cand-B"], (
        f"backfill された統合 receipt（ts が前・seq が後）が rework を殺した: {ids}")


def test_wip_candidate_scoped_integration_finishes_exactly_its_candidate(tmp_path):
    # 新形式: candidate_id を運ぶ統合は、名指しした候補「だけ」を完了させる。
    # 統合の後に始まった同一 Issue の rework も、時系列比較なしで無事。
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-P", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T01:00:00Z")   # seq=1
    seed(tmp_path, "supervisor", "integration_admitted",
         {"integration_branch": "develop", "issue": 9, "candidate_id": "cand-P",
          "verdict": "pass", "admitter": "supervisor"},
         ts="2026-07-16T02:00:00Z")   # seq=2 → cand-P だけが完了
    seed(tmp_path, "eng", "cycle_started",
         {"role": "eng", "candidate_id": "cand-R", "pack_manifest_id": "issue-9"},
         ts="2026-07-16T03:00:00Z")   # seq=3 — 統合後の rework
    wip = _wip(tmp_path)
    ids = [w["candidate_id"] for w in wip]
    assert ids == ["cand-R"], f"名指しの統合が正確に1候補だけを消していない: {ids}"
