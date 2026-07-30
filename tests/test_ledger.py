"""台帳と統制 — phase の順序・冪等・自己承認拒否・識別子の相関。

ここが緩むと、判断の記録が「あるように見えて効いていない」状態になる。"""
import argparse
import json
import os
import pathlib
import re
import subprocess
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
