"""台帳と統制 — phase の順序・冪等・自己承認拒否・識別子の相関。

ここが緩むと、判断の記録が「あるように見えて効いていない」状態になる。"""
import argparse
import json
import os
import pathlib
import pytest
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


# ── 実地: log が Issue にだけ書き、台帳の progress_recorded が0件だった ──────
def test_log_writes_progress_receipt_to_ledger(monkeypatch, tmp_path):
    """Issue に7回書いたのに台帳は0件。/org-resume が復帰できない状態だった。"""
    src = _gh_src()
    assert "_append_progress_receipt" in src
    seg = src[src.index("def _append_progress_receipt"):]
    assert "progress_recorded" in seg and "ledger.py" in seg


def test_record_marks_backfilled():
    """遡って記録したものは、実時点の記録と区別できること。"""
    src = _cycle_src()
    seg = src[src.index("def cmd_record"):]
    assert '"backfilled": True' in seg, "backfill 印が無いと、後から足した記録が実時点と混ざる"


# ── 実地: 相関キーが無いと統制が無言で無効になっていた（seq 204 / 205）───────


def test_judgment_without_correlation_key_is_rejected(tmp_path):
    """相関キーの無い判定は拒否する。以前は素通りし、統制が効いていないことも見えなかった。"""
    env = _led(tmp_path)
    p = _append(env, "maker1", "admission_decided", {"verdict": "admit"})
    assert p.returncode != 0, "対象を特定できない判定が通った"
    # 0.33.1 で schema 検証（require_any）が同じことを、より具体的に言うようになった —
    # どのキーが要るかを挙げる。台帳側の相関キー検査も残っているので、どちらが先に拾っても
    # 拒否される（二重の防御）。
    assert "相関キーが無い" in p.stderr or "特定できない" in p.stderr


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
    src = _cycle_src()
    seg = src[src.index("def cmd_show"):]
    assert "訂正済み" in seg and "backfill" in seg
    assert "次:" in seg, "いま何待ちかが出ない"


def test_round_count_uses_the_larger_of_ledger_and_issue():
    """二重記録の片側が落ちていても回数を過少に言わない。"""
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
    """台帳を先に通す。拒否されるなら Issue に外向きの記録を作る前に止める。"""
    src = _gh_src()
    seg = src[src.index("def cmd_decide"):]
    led = seg.index("ledger.py")
    comment = seg.index('gh(["issue", "comment"')
    assert led < comment, "Issue に書いてから台帳を叩いている（食い違いが外に残る）"
    assert "台帳が受け付けなかったので、Issue にも記録していない" in seg


def test_decide_key_is_unique_per_judgment():
    """`{event}-{issue}` だと2周目の判定が1周目と衝突して no-op になる。"""
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
    """条件1+8: version と ts は writer が付ける。"UNSET" を書かない。"""
    assert _app(tmp_path)[0] == 0
    ev = _evs(tmp_path)[0]
    assert ev["schema_id"] == "orgforge-ledger"
    assert isinstance(ev["schema_version"], int) and ev["schema_version"] >= 1
    assert ev["schema_sha256"]
    assert ev["ts"] != "UNSET" and ev["ts"].endswith("Z")


def test_client_cannot_name_the_schema_version(tmp_path):
    """条件2: クライアント指定は downgrade 攻撃なので拒否する。"""
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
    """条件3: schema に宣言の無いクラスは書けない。"""
    code, out = _app(tmp_path, cls="totally_unknown_class", payload={})
    assert code == 2
    assert "未知のイベントクラス" in out


def test_unreadable_schema_fails_closed(tmp_path, monkeypatch):
    """条件4: schema を読めないなら新規 append を拒否する（検証せずに書かない）。"""
    monkeypatch.setenv("ORG_LEDGER_SCHEMA", str(tmp_path / "nope.yaml"))
    code, out = _app(tmp_path)
    assert code == 2
    assert "検証" in out


def test_concurrent_appends_do_not_collide(tmp_path):
    """条件: append 全体が critical section。**12並列で全件 seq=1 になっていた。**"""
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
    """条件: HEAD は権威ではない。壊れていても log から再構築して続ける。"""
    assert _app(tmp_path)[0] == 0
    (tmp_path / "HEAD").write_text('{"seq": 99, "hash": "bogus"}', encoding="utf-8")
    code, out = _app(tmp_path, payload={**_PR, "candidate_id": "c2"})
    assert code == 0, out
    assert "log から再構築" in out
    assert [e["seq"] for e in _evs(tmp_path)] == [1, 2]


def test_torn_line_is_not_auto_repaired(tmp_path):
    """条件: 途中の破損は自動修復せず fail-closed。上に整合した HEAD を載せない。"""
    assert _app(tmp_path)[0] == 0
    with open(tmp_path / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write('{"seq": 2, "class": "progress_recorded"')     # 改行なし
    code, out = _app(tmp_path)
    assert code == 4, out
    assert "自動修復しない" in out


def test_interior_tampering_blocks_further_appends(tmp_path):
    """条件: 中間の書き換えも fail-closed。"""
    for i in range(3):
        assert _app(tmp_path, payload={**_PR, "candidate_id": f"c{i}"})[0] == 0
    p = tmp_path / "ledger.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    ev = json.loads(lines[1]); ev["payload"]["fraction"] = 0.99
    lines[1] = json.dumps(ev, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    code, out = _app(tmp_path)
    assert code == 4
    assert "hash 不一致" in out


def test_same_natural_key_different_payload_is_refused(tmp_path):
    """条件9: 同じキーで中身が違うのは再実行ではない。no-op で捨ててはいけない。"""
    assert _app(tmp_path, extra=("--natural-key", "k1"))[0] == 0
    assert _app(tmp_path, extra=("--natural-key", "k1"))[0] == 0        # 完全一致 → no-op
    assert len(_evs(tmp_path)) == 1
    code, out = _app(tmp_path, payload={**_PR, "fraction": 0.9},
                     extra=("--natural-key", "k1"))
    assert code == 3, out
    assert "payload が違う" in out


def test_verify_reports_both_assurances_separately(tmp_path):
    """条件6: verify が version 別に検証し、legacy と validated を分けて報告する。"""
    assert _app(tmp_path)[0] == 0
    code, out = run("ledger.py", "verify", str(tmp_path))
    assert code == 0, out
    assert "validation_assurance" in out
    assert "validated:v1" in out


def test_legacy_events_remain_readable_but_unvalidated(tmp_path):
    """条件5: version を持たない既存イベントは読める。遡って拒否しない。"""
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
    assert "必須 field が無い" in out


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
    assert "相関キーが無い" in out or "特定できない" in out


def test_enum_and_type_are_checked_when_present(tmp_path):
    """軸2: 宣言済み field は **存在する場合に** enum / 型を検証する。"""
    code, out = _app(tmp_path, "admission_decided",
                     {**_ADM, "verdict": "totally-bogus"}, actor="gate")
    assert code == 2
    assert "許された値ではない" in out
    code, out = _app(tmp_path, "correction",
                     {"corrects": 5, "kind": "probe"}, actor="sup")     # list であるべき
    assert code == 2
    assert "型が違う" in out


def test_undeclared_fields_warn_but_pass_except_in_strict_classes(tmp_path):
    """軸3: 未宣言 field は既定で許可し、警告する。厳格クラスだけ拒否。"""
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
    """`--ts UNSET` が通っていた。cap の時間窓を迂回できる。"""
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
    """記録時の schema digest を照合する。形式が入れ替わったことを検出できる。"""
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
    """故障注入でロックできないとき、必ず非ゼロで止まる。"""
    env = dict(os.environ, ORG_LEDGER_FORCE_LOCK_FAIL="1")
    env.pop("ORG_LEDGER_ALLOW_UNLOCKED", None)
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", str(tmp_path),
                        "--actor", "w", "--class", "progress_recorded", "--payload", "{}"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 4, r.stdout + r.stderr
    assert "ロックできない" in (r.stdout + r.stderr)
    assert not (tmp_path / "ledger.jsonl").exists(), "拒否したのに書いている"


def test_unlocked_escape_is_explicit_and_says_what_it_cannot_verify(tmp_path):
    """逃げ道は明示の環境変数だけ。そして保証できないことを言う。"""
    env = dict(os.environ, ORG_LEDGER_FORCE_LOCK_FAIL="1", ORG_LEDGER_ALLOW_UNLOCKED="1")
    r = subprocess.run([sys.executable, str(TOOLS / "ledger.py"), "append", str(tmp_path),
                        "--actor", "w", "--class", "progress_recorded", "--payload", "{}"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    both = r.stdout + r.stderr
    assert "ロックせずに append" in both
    assert "確かめられない" in both


def test_backfill_ts_must_be_a_real_moment(tmp_path):
    """形が合っているだけでは足りない。`2026-99-99T99:99:99Z` が通っていた。"""
    code, out = _app(tmp_path, "progress_recorded", {},
                     extra=("--backfill-ts", "2026-99-99T99:99:99Z"))
    assert code == 2
    assert "実在しない日時" in out


def test_backfill_ts_refuses_future_and_distant_past(tmp_path):
    """未来と遠すぎる過去を拒否する — どちらも cap の時間窓を迂回できる。"""
    code, out = _app(tmp_path, "progress_recorded", {},
                     extra=("--backfill-ts", "2099-01-01T00:00:00Z"))
    assert code == 2 and "未来である" in out
    code, out = _app(tmp_path, "progress_recorded", {},
                     extra=("--backfill-ts", "2000-01-01T00:00:00Z"))
    assert code == 2 and "遠すぎる過去" in out


def test_normal_append_needs_no_timestamp(tmp_path):
    """通常経路は時刻を渡さない（writer が付ける）。"""
    assert _app(tmp_path, "progress_recorded", {})[0] == 0
    ev = _evs(tmp_path)[0]
    assert ev["ts"] != "UNSET" and ev["ts"].endswith("Z")


def test_unknown_validator_type_fails_closed(tmp_path, monkeypatch):
    """schema の型名の typo が「検査の無効化」になってはいけない。"""
    alt = tmp_path / "typo-schema.yaml"
    alt.write_text((TEMPLATE / "ledger-schema.yaml").read_text(encoding="utf-8")
                   .replace("correction:          { corrects: list }",
                            "correction:          { corrects: lst }"), encoding="utf-8")
    monkeypatch.setenv("ORG_LEDGER_SCHEMA", str(alt))
    code, out = _app(tmp_path, "correction", {"corrects": [1], "kind": "probe"}, actor="sup")
    assert code == 2
    assert "未知の型名" in out


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
    """org 独自の厳格規則は --fix で消えない。"""
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
    """org が list に足した要素も残す（集合として足す）。"""
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
        "correction:          { corrects: list }", "correction:          { corrects: map }", 1))
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
    """曝露は積み上がり、cap を超えると hold になる。"""
    for i in range(3):
        code, out = _reserve(tmp_path, 1, 3, f"t{i}")
        assert code == 0, out
    code, out = _reserve(tmp_path, 1, 3, "t3")
    assert code == 10, out
    assert json.loads(out.splitlines()[0])["decision"] == "hold"


def test_hold_is_recorded_not_just_denied(tmp_path):
    """**hold も台帳に残る。** 従来は deny して終わり、止めたことが記録されなかった。"""
    _reserve(tmp_path, 5, 3, "t0")
    d = _decisions(tmp_path)
    assert len(d) == 1 and d[0][1] == "hold"


def test_concurrent_reservations_never_exceed_the_cap(tmp_path):
    """**16並列で合計が cap を超えない。** 従来は両方が同じ committed を読めた。"""
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
    """hook の再実行を二重計上しない。"""
    assert _reserve(tmp_path, 1, 3, "same")[0] == 0
    code, out = _reserve(tmp_path, 1, 3, "same")
    assert code == 0
    assert json.loads(out.splitlines()[0])["reason"] == "idempotent_replay"
    assert len(_decisions(tmp_path)) == 1, "再実行が二重に記録された"


def test_idempotency_key_spans_session_rule_and_class(tmp_path):
    """`tool_use_id` 単独では別 session・別 rule の衝突を防げない。"""
    assert _reserve(tmp_path, 1, 9, "tu", sess="s1", rule="r1")[0] == 0
    assert _reserve(tmp_path, 1, 9, "tu", sess="s2", rule="r1")[0] == 0   # 別 session
    assert _reserve(tmp_path, 1, 9, "tu", sess="s1", rule="r2")[0] == 0   # 別 rule
    assert len(_decisions(tmp_path)) == 3, "衝突して no-op になった"


@pytest.mark.parametrize("missing", ["session_id", "tool_use_id", "rule"])
def test_missing_idempotency_key_denies_the_action(tmp_path, missing):
    """欠落していれば metered action を deny する（同一性を確かめられない）。"""
    kw = {"sess": "s1", "tu": "t1", "rule": "r1"}
    kw["tu" if missing == "tool_use_id" else
       "sess" if missing == "session_id" else "rule"] = ""
    code, out = _reserve(tmp_path, 1, 3, kw["tu"], sess=kw["sess"], rule=kw["rule"])
    assert code == 3, out
    d = json.loads(out.splitlines()[0])
    assert d["decision"] == "deny" and d["reason"] == f"missing_{missing}"
    assert _decisions(tmp_path) == []


def test_reserve_denies_when_the_ledger_is_unhealthy(tmp_path):
    """壊れた台帳の上に予約を書かない。**書けないなら allow を返さない。**"""
    assert _reserve(tmp_path, 1, 9, "t0")[0] == 0
    with open(tmp_path / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write('{"seq": 2, "class": "x"')        # torn line
    code, out = _reserve(tmp_path, 1, 9, "t1")
    assert code == 4
    assert json.loads(out.splitlines()[0])["reason"] == "ledger_unhealthy"


def test_reserve_denies_when_the_lock_fails(tmp_path):
    """ロックできないなら予約しない — cap の原子性はロックに依存している。"""
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
    """**cap 予約に backfill を持ち込まない。** 引数自体を定義しない。"""
    code, out = run("ledger.py", "reserve-exposure", "--help")
    assert "--backfill-ts" not in out
    assert not re.search(r"(?m)^\s+--ts\b", out)
    # 渡そうとしても受け付けない
    code, out = _reserve(tmp_path, 1, 9, "t0", extra=("--backfill-ts", "2026-07-01T00:00:00Z"))
    assert code != 0
    assert _decisions(tmp_path) == []


def test_reserve_does_not_take_committed_from_the_caller(tmp_path):
    """`committed_so_far` は writer が数える。caller が申告できてはいけない。"""
    code, out = run("ledger.py", "reserve-exposure", "--help")
    assert "committed" not in out.lower()
    _reserve(tmp_path, 2, 9, "t0")
    _reserve(tmp_path, 2, 9, "t1")
    d = _evs(tmp_path)[-1]["payload"]
    assert d["committed_so_far"] == 2.0, "writer が数えていない"


def test_malformed_prior_exposure_denies(tmp_path):
    """壊れた曝露記録を 0 として数えない — 合計が実際より小さく見える。"""
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
    """`_nk` は道具が付ける印。caller が名指しできると no-op を作れる。"""
    code, out = _app(tmp_path, "progress_recorded", {"_nk": "forged"})
    assert code == 2
    assert "_nk" in out


def test_same_key_with_a_different_request_is_refused(tmp_path):
    """**exact retry だけが再実行。** delta=1 の allow を根拠に delta=100 が通っていた。"""
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
    """delta は有限かつ正、cap は有限かつ非負。負や NaN は合計と比較を壊す。"""
    code, out = _reserve(tmp_path, delta, cap, f"t{delta}{cap}")
    assert code == 3, out
    assert json.loads(out.splitlines()[0])["reason"] == "invalid_request"
    assert _decisions(tmp_path) == []


def test_negative_prior_exposure_denies_rather_than_reducing_the_total(tmp_path):
    """過去の負の曝露を数えない（数えると合計を減らせる）。"""
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
    """**書けなかったら allow にならない。** 書きかけは切り戻す。"""
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
    """区切り連結だと、値に区切り文字が入ったときに別のキーと衝突する。"""
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
    """halt は generic append では書けない — 検査に使う記録は検査する側だけが書ける。"""
    code, out = _app(tmp_path, "halt_tripped",
                     {"trigger": "t", "scope": "global", "reason": "r", "tripped_by": "x"},
                     actor="attacker")
    assert code == 2, out
    assert "writer 専用" in out
    assert _evs(tmp_path) == []


def test_trip_halt_writes_the_ledger_and_the_latch(tmp_path):
    """台帳とラッチの両方に書く（ラッチは台帳が読めないときの第二経路）。"""
    code, out = _trip(tmp_path)
    assert code == 0, out
    d = json.loads(out.splitlines()[0])
    assert d["halted"] is True and d["latch_written"] is True
    assert (tmp_path / "HALT").is_file()
    assert [e["class"] for e in _evs(tmp_path)] == ["halt_tripped"]


def test_trip_halt_requires_a_reason(tmp_path):
    """なぜ止めたのかが無い halt は、解除の判断ができない。"""
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
    """観測は halt 中でも通る（止まった org を診断できないと復旧できない）。"""
    assert _trip(tmp_path)[0] == 0
    code, out = run("ledger.py", "halt-status", str(tmp_path))
    assert code == 10
    d = json.loads(out.splitlines()[0])
    assert d["halted"] is True and d["source"] == "ledger"
    assert d["reason"] and d["tripped_by"] == "registrar"


def test_deleting_the_latch_does_not_clear_the_halt(tmp_path):
    """ラッチは台帳の代わりではない — 手で消しても台帳の halt が残る。"""
    assert _trip(tmp_path)[0] == 0
    (tmp_path / "HALT").unlink()
    code, out = run("ledger.py", "halt-status", str(tmp_path))
    assert code == 10, out
    assert json.loads(out.splitlines()[0])["source"] == "ledger"


def test_unreadable_ledger_counts_as_halted(tmp_path):
    """止まっているか分からないなら止める（いちばん危ない fail-open を避ける）。"""
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
    assert ("writer 専用" in out) or ("identity は receipt を検証した経路が生成する" in out), out
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
    """**writer は公開鍵だけを持つ。** 秘密鍵を持つ側は判定を偽造できる。"""
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
    """store に秘密鍵が入っていたら読み込み自体を拒否する。"""
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
    """公開鍵では署名を作れない — これが共有鍵との決定的な差である。"""
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
            "--lineage", "release", "--verdict", "release", "--requirements-digest", "none",
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
    """**止めた主体が自分で解除できてはいけない。**"""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-reg", "keys/k-reg.pem")
    code, d = _am_release(org, led, rc)
    assert code == 4
    assert d["released"] is False
    assert _am_tool(org, "ledger.py", "halt-status", str(led)).returncode == 10   # 維持


def test_a_shared_secret_cannot_release(tmp_path):
    """共有鍵は「鍵が違う」ことしか示さない — 独立した承認を証明しない。"""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-shared")
    code, d = _am_release(org, led, rc)
    assert code == 4 and d["released"] is False
    assert "共有鍵" in (d.get("detail") or "")


def test_release_requires_explicit_authorization(tmp_path):
    """`may_release_halt` を認可されていない鍵では解除できない。"""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-noauth", "keys/k-noauth.pem")
    code, d = _am_release(org, led, rc)
    assert code == 4 and d["released"] is False


def test_a_release_receipt_is_bound_to_the_halt(tmp_path):
    """別の halt の解除 receipt を再利用できない。"""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-appr", "keys/k-appr.pem", subject="halt:999")
    code, d = _am_release(org, led, rc)
    assert code == 4 and "一致しない" in (d.get("detail") or "")


def test_release_requires_recovery_evidence(tmp_path):
    """何を確かめて復旧したのかが無い解除は、後から検証できない。"""
    org, led = _am_setup_halt(tmp_path)
    rc = _am_receipt(org, "k-appr", "keys/k-appr.pem")
    code, d = _am_release(org, led, rc, evidence="   ")
    assert code == 2 and d["reason"] == "missing_recovery_evidence"


def test_an_independent_authorized_approver_can_release(tmp_path):
    """独立した approver（非対称・認可あり・証拠あり）なら解除できる。"""
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
    """active halt が無ければ何もしない（再実行が安全）。"""
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
    """writerd を起動して (led, sock, proc) を返す。"""
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
    env = dict(os.environ, ORG_WRITER_SOCKET=str(sock))
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
    """**経路を1つにする。** writerd 経由なら書け、直接の append は拒否される。"""
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
    """**daemon が居ないことを「書けた」と読み替えない。** 直接書き込みも拒否のまま。"""
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
    """digest は本文全体を覆う — 途中で書き換えた要求は通らない。"""
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
    """同じ nonce の再送は通さない。"""
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
    """**書き込み先は writerd が決める。** caller は org 名でしか選べない。"""
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
    """writerd 経由で任意のサブコマンドを実行できてはいけない。"""
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
    """**親を書ける主体は socket を差し替えられる** — 偽 writer に繋がされる。"""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    parent = tmp_path / "p"; parent.mkdir()
    os.chmod(parent, mode)
    err = wd.check_socket_parent(str(parent / "writer.sock"))
    assert (err is None) is expect, err
    os.chmod(parent, 0o755)


def test_socket_parent_may_not_be_a_symlink(tmp_path):
    """リンクを張り替えれば socket ごと差し替えられる。"""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    err = wd.check_socket_parent(str(tmp_path / "link" / "writer.sock"))
    assert err and "シンボリックリンク" in err


def test_same_uid_cannot_claim_separate_uid(tmp_path):
    """**同一 UID では `separate_uid` を主張できない。** 道具が自分でそう言う。"""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    parent = tmp_path / "p"; parent.mkdir()
    err = wd.check_socket_parent(str(parent / "writer.sock"), require_root_owned=True)
    assert err and "root 所有でない" in err
    assert "separate_uid" in err


def test_writer_owned_assets_are_audited(tmp_path):
    """ラッチ・鍵 registry・schema も書き込み経路と同じ強さで守る必要がある。"""
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


def test_install_script_dry_run_changes_nothing(tmp_path):
    """段階B の install は `--dry-run` で何も変えない（root 不要で監査できる）。"""
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
    """検証を root で走らせたら意味が無い（全部できてしまう）。"""
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
    """**接続できることと、書けることは別。** 0600 だと別 UID の caller は接続すらできない。"""
    led, sock, proc = _wd_start(tmp_path)
    try:
        mode = os.stat(sock).st_mode & 0o777
        assert mode & 0o066, f"socket が {oct(mode)} — 別 UID の caller が接続できない"
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_isolation_is_measured_not_flagged(tmp_path):
    """`separate_uid` は **実測で** 決める。フラグを渡したかどうかで決めない。"""
    sys.path.insert(0, str(TOOLS))
    import importlib
    wd = importlib.import_module("writerd")
    led = tmp_path / "l"; led.mkdir()
    # 同一 UID・自分所有の親 → process_mediated（--require-root-owned を渡しても変わらない）
    assert wd.measured_isolation(str(led / "w.sock"), [str(led)]) == "process_mediated"


def test_peer_uid_reaches_the_recorder(tmp_path, monkeypatch):
    """peer credential が `recorded_by` に **届く**こと（環境に置くだけでは足りない）。"""
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
    """`set -e` が無いと、chown が半端な状態で「install 完了」と表示される。"""
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
    """`cp -R src dst/src` は再実行で tools/tools を作る。"""
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "rm -rf '${INSTALL_DIR}/tools'" in src
    assert "cp -R '$PLUGIN_DIR/tools/.'" in src, "末尾の /. が無いと入れ子になる"


def test_verifier_does_not_damage_the_target():
    """**検証が検証対象を壊さない。** 書き込みを試すのではなく、開けるかだけを見る。"""
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
    """**書けないことと、見えないことは別。** 読めない台帳は監査のための台帳ではない。"""
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
    # receipt を検証した経路（writer）からなら通る
    env = dict(os.environ, ORG_IDENTITY_VERIFIED="1")
    r = subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", str(led),
         "--actor", "gate-signer", "--class", "admission_decided",
         "--payload", json.dumps({"deliverable": "7", "verdict": "admit", "gate": "g",
                                  "identity_assurance": "attested",
                                  "decision_by": "gate-signer"})],
        cwd=org, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr


def test_attested_enforcement_defaults_off(tmp_path):
    """**既定は偽。** 真にすると receipt を持たない既存の運用が全部止まる。"""
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
    """schema を明示しないと cwd 依存でテンプレートに fallback する。"""
    src = (TOOLS / "writerd.py").read_text(encoding="utf-8")
    assert 'env["ORG_LEDGER_SCHEMA"] = self.schema' in src
    assert '"--schema"' in src
    # installer が root 所有の設定から渡すこと
    isrc = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "--schema" in isrc


def test_isolation_compares_the_peer_uid(tmp_path):
    """**caller と同じ UID なら隔離ではない。** 要求ごとに peer UID と比べる。"""
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
    """✗ を印字するだけでは、検査が落ちても最終 exit が 0 になる。"""
    src = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    assert "FAIL + RPC_BAD" in src
    assert 'bad "writerd check が落ちた"' in src


def test_verifier_no_write_writes_nothing():
    """`--no-write` では ⑨ の正常系 append も出さない。"""
    src = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    assert "no_write = sys.argv[3]" in src
    assert "再送: --no-write なので飛ばす" in src


def test_installer_does_not_overwrite_the_original_owner():
    """再 install で「元の所有者」を writer に書き換えない（uninstall が壊れる）。"""
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
    assert "identity は receipt を検証した経路が生成する" in (r.stdout + r.stderr)
    assert not (led / "ledger.jsonl").exists() or \
        not (led / "ledger.jsonl").read_text(encoding="utf-8").strip()


def test_generic_append_cannot_record_a_judgment(tmp_path):
    """judgment class は generic append では書けない（強制が有効なとき）。"""
    org, led = _att_org(tmp_path)
    r = _att_append(org, led, "gate-alias", {"deliverable": "7", "verdict": "admit"})
    assert r.returncode == 3, r.stdout + r.stderr
    assert "generic append では記録できない" in (r.stdout + r.stderr)


def test_the_verified_path_can_record(tmp_path):
    """**receipt を検証した経路だけが書ける。** 止まるだけでは運用できない。"""
    org, led = _att_org(tmp_path)
    env = dict(os.environ, ORG_IDENTITY_VERIFIED="1")
    r = _att_append(org, led, "gate-signer",
                    {"deliverable": "7", "verdict": "admit",
                     "identity_assurance": "authenticated", "decision_by": "gate-signer"},
                    env=env)
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
                        "--verdict", "admit", "--requirements-digest", "rd",
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
        assert who is None and "署名が一致しない" in err
    finally:
        os.environ.pop("ORG_TRUST_STORE", None)


def test_nonces_survive_a_daemon_restart(tmp_path):
    """**再送を防げない状態で通さない。** プロセス内だけの nonce は再起動で消える。"""
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
    assert wd.check_socket_parent(str(leaf / "w.sock")) is None
    os.chmod(leaf, 0o777)
    assert wd.check_socket_parent(str(leaf / "w.sock")) is not None


def test_peer_uid_allowlist_is_available():
    """socket が 0666 なので、**繋げることと書けることを分ける**認可が要る。"""
    src = (TOOLS / "writerd.py").read_text(encoding="utf-8")
    assert '"--allow-uid"' in src
    assert "peer_not_authorized" in src


def test_authoritative_data_lives_outside_the_org_tree():
    """**中身の権限を絞っても、入れ物を差し替えられるなら意味が無い。**"""
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "AUTHORITATIVE=" in src
    assert "org tree の外" in src
    assert "ln -s '${AUTHORITATIVE}/ledger'" in src
    # daemon には実体のパスを渡す
    assert "default=${AUTHORITATIVE}/ledger" in src


def test_installer_and_verifier_agree_on_the_socket():
    """パスが食い違えば、verifier は存在しない socket を検査する。"""
    isrc = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    vsrc = (TOOLS / "writer-verify.sh").read_text(encoding="utf-8")
    assert 'SOCK_PARENT="/usr/local/var/orgforge/run"' in isrc
    assert 'SOCK="/usr/local/var/orgforge/run/writer.sock"' in vsrc
    # verifier は leaf に root 所有を期待しない（writer 所有が正しい）
    assert "leaf は $POWNER 所有（自分ではない）" in vsrc


def test_pyyaml_guidance_prefers_a_root_owned_venv():
    """システム python を書き換える案内を第一候補にしない。"""
    src = (TOOLS / "writer-install.sh").read_text(encoding="utf-8")
    assert "1. root 所有の専用 venv（推奨）" in src
    assert "勧めない" in src
