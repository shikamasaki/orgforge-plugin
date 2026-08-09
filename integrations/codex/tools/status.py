#!/usr/bin/env python3
"""status — one glanceable health board for the org (docs/12 §5 Layer-3).

The user should be able to ask "how's my org?" and get one answer — green / amber / red — without
reading the ledger or knowing the words "tick", "sensor", or "chain". This reads the ledger and rolls
its state up into: what's done, what's in progress (with next steps), what needs the human, and an
overall light. It is READ-ONLY (like /org-tick) and speaks the user's language, not the organs'.

  status <root> [--role R]   print the health board (GREEN/AMBER/RED + the rollup)

Light:
  RED    — needs the human now: a broken ledger chain, a tripped halt, an unproven-rollback or a
           repeated death (the org re-made a known mistake), or a stalled cycle holding a slot.
  AMBER  — running but something to watch: work in progress past a while, a mandate awaiting, an
           empty domain model over many cycles.
  GREEN  — healthy: work draining, nothing escalating (fail-quiet is normal).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import OK, read_events   # noqa: E402



def _reject_reason(issue):
    """その Issue の最新 reject の理由を1行で。

    理由は decide が Issue コメントに厚く書く（台帳が持つのは digest だけ — 設計どおり）。
    board からそれが読めないと、CEO が見る唯一の画面に「何が問題か」が一行も出ない。
    GitHub が見られなければ黙って None を返す（board は落とさない）。
    """
    import subprocess
    try:
        p = subprocess.run(["gh", "issue", "view", str(issue), "--json", "comments"],
                           capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            return None
        cs = json.loads(p.stdout).get("comments", [])
    except Exception:
        return None
    for c in reversed(cs):
        b = c.get("body") or ""
        if "admission_decided" not in b or "`reject`" not in b:
            continue
        m = re.search(r"\*\*Why \(the reasoning\):\*\*\s*\n(.+)", b)
        if m:
            s = " ".join(m.group(1).split())
            # board は一望する画面なので、1件が数行を占めると一望でなくなる。
            # 全文は Issue と `org_cycle show --issue N` にある。
            return s[:70] + ("…" if len(s) > 70 else "")
    return None


def _needs_human_issues():
    """orgforge:needs-human ラベルの open Issue を「あなた待ち」として返す。

    これが無いと board が嘘をつく: org が作れる作業だけを数えて GREEN と出すのに、実際は
    人間の前提条件（アカウント作成・鍵の発行・ストア審査・ブランチ保護など）が未了で
    着手できない、という状態が見えなかった。人間への依頼こそ忘れられると最も長く止まるので、
    board の最上位に出す。

    GitHub が見られない環境（ledger-only の org、gh 未認証、オフライン）では黙って空を返す —
    board 自体は落とさない。"""
    import subprocess
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        import discover
        repo = discover.backlog_repo()
        if not repo:
            return []
        p = subprocess.run(["gh", "issue", "list", "--repo", repo, "--state", "open",
                            "--label", "orgforge:needs-human", "--json", "number,title"],
                           capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            return []
        items = json.loads(p.stdout or "[]")
    except Exception:
        return []
    out = []
    for it in items[:5]:
        out.append(f"あなたの作業待ち: #{it['number']} {it['title']}")
    if len(items) > 5:
        out.append(f"あなたの作業待ち: 他 {len(items) - 5} 件")
    return out


def _governance_divergence_notice():
    """Return an AMBER notice when this linked worktree embeds stale governance."""
    try:
        import discover
        rows = discover.governance_divergences()
    except Exception:
        return None
    if not rows:
        return None
    names = ", ".join(r["path"] for r in rows[:5])
    if len(rows) > 5:
        names += f", +{len(rows) - 5} more"
    return (f"governance divergence: {len(rows)} file(s) differ in the subject worktree "
            f"({names}); enforcement uses the authoritative primary checkout")


def cmd_status(a):
    try:
        events = read_events(a.root)
    except Exception as e:
        print(f"RED — the ledger could not be read ({e}). The org's state is unknown; a human must look.")
        return OK
    governance_notice = _governance_divergence_notice()
    if not events and governance_notice:
        print("AMBER — running")
        print(f"  watch: {governance_notice}")
        return OK
    if not events:
        print("GREEN — no activity yet. The org is founded but has done nothing; drop work on the "
              "backlog (or wire an intake) and start it.")
        return OK

    counts = {}
    for e in events:
        counts[e["class"]] = counts.get(e["class"], 0) + 1

    # in-progress: started but not completed candidates
    started, completed, latest = {}, set(), {}
    for e in events:
        p = e.get("payload", {})
        cid = p.get("candidate_id")
        if not cid:
            continue
        if e["class"] == "cycle_started":
            started[cid] = p.get("role")
        elif e["class"] == "cycle_completed":
            completed.add(cid)
        elif e["class"] == "progress_recorded":
            latest[cid] = p.get("next_step")
    in_progress = {cid: r for cid, r in started.items() if cid not in completed}

    # red signals
    red = []
    operational = None
    try:
        from operational_state import fold as fold_operational
        operational = fold_operational(events)
        if operational["effective_state"] == "HALTED":
            detail = operational.get("derived_reason") or "an operational HALT is active"
            red.append(f"operational state HALTED — {detail}")
    except Exception:
        # Older bundles without the operational projection retain the original conservative signal.
        if counts.get("halt_tripped"):
            red.append("a HALT has tripped — the org stopped itself")
    if counts.get("repeated_death_detected"):
        red.append("a known mistake was re-made (repeated death) — accumulated learning isn't landing")
    if counts.get("rollback_unproven"):
        red.append("an action claimed reversible has no proven undo")
    if counts.get("stall_breaker_checked"):
        trips = sum(1 for e in events if e["class"] == "stall_breaker_checked"
                    and e.get("payload", {}).get("decision") == "trip")
        if trips:
            red.append(f"{trips} cycle(s) wedged (stall breaker tripped) — holding a slot")

    # amber signals
    amber = []
    adaptive_rows = []
    try:
        from adaptation import fold as fold_adaptation, load_contract
        contract, _, _ = load_contract(a.root)
        adaptive = fold_adaptation(events, contract=contract)
        if operational is not None:
            operational = fold_operational(events, contract=contract)
            if operational["effective_state"] == "DEGRADED":
                amber.append("operational state DEGRADED — only the active adaptive envelope is allowed")
            elif operational["effective_state"] == "RECOVERING":
                amber.append("operational state RECOVERING — ship remains blocked until revalidation completes")
        envelope_specs = {row.get("id"): row for row in contract.get("adaptive_envelopes", [])}
        for row in adaptive["activations"]:
            spec = envelope_specs.get(row.get("envelope_id"), {})
            row = {**row, "forbidden_actions": spec.get("forbidden_actions") or [],
                   "revalidation_scope": spec.get("revalidation_scope") or []}
            adaptive_rows.append(row)
            if row.get("status") == "expired":
                red.append(f"adaptive envelope {row['envelope_id']} expired — only safe diagnosis/stop remains")
            elif row.get("status") == "active":
                amber.append(f"adaptive envelope active: {row['envelope_id']} until {row.get('expires_at')}")
            elif row.get("status") == "reverted" and row.get("tainted_artifacts"):
                amber.append(f"adaptive envelope reverted with {len(row['tainted_artifacts'])} tainted "
                             "artifact(s) awaiting declared revalidation")
    except Exception:
        adaptive_rows = []
    if governance_notice:
        amber.append(governance_notice)
    open_backlog = counts.get("candidate_submitted", 0) - counts.get("cycle_completed", 0)
    if in_progress:
        amber.append(f"{len(in_progress)} item(s) in progress")
    mandates = sum(1 for e in events if e["class"] == "candidate_submitted"
                   and e.get("payload", {}).get("source") == "mandate")
    open_mandates = mandates  # approximate; a completed one still counts here, kept simple
    if open_mandates and open_backlog > 0:
        amber.append(f"{open_mandates} mandate(s) submitted")

    done = counts.get("cycle_completed", 0)

    # リスク付き admit を board に出す。gate は --risk を書けば admit できるので、正直に書くほど
    # 通りやすいという構造になっている。**それ自体は正しい運用**（書かれない穴より遥かによい）
    # だが、書き得にしないために「何件溜まっているか」は見えている必要がある。
    # **同一 deliverable は最新の判定が有効。** 集合で持つと reject が後から来ても admit が
    # 残り続け、rework 中の成果物を「admit 済み」と数える。運用では admit → reject の順で
    # 記録されたのに board が RED を出し続けた。台帳は追記型なので、
    # 「一度でも admit があった」と「いま admit されている」は別物。
    # correction{effect:voids} で無効化された記録は数えない。kind を organ ごとに解釈すると
    # status と derive-admission が同じ台帳から違う現在値を作る（OBS-042）。
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from ledger import voided_seqs
        voided = voided_seqs(events)
    except Exception:
        voided = set()

    latest_admission = {}
    for e in events:
        if e["class"] != "admission_decided" or e.get("seq") in voided:
            continue
        pl = e.get("payload", {}) or {}
        key = str(pl.get("issue") or pl.get("deliverable") or "")
        if not key:
            continue
        prev = latest_admission.get(key)
        if prev is None or (e.get("seq") or 0) >= prev[0]:
            latest_admission[key] = ((e.get("seq") or 0), pl.get("verdict"))
    admits = {k for k, (_, v) in latest_admission.items() if v == "admit"}

    # risk 付き admit も、後で reject された分は数えない（同上）
    risky = []
    for e in events:
        if e["class"] != "admission_decided" or e.get("seq") in voided:
            continue
        pl = e.get("payload", {}) or {}
        if pl.get("verdict") != "admit" or pl.get("risk_accepted") is not True:
            continue
        key = str(pl.get("issue") or pl.get("deliverable") or "")
        cur = latest_admission.get(key)
        if cur and cur[0] == (e.get("seq") or 0):
            risky.append(e)
    if risky:
        amber.append(f"リスク付き admit: {len(risky)} 件（承知の上で残した穴）")

    # 二重記録の乖離を検出する。判断は「台帳の受領証」と「Issue の理由」の両方に書く決まりだが、
    # 実地では skeptic が Issue にだけ書き、台帳に1件も無いまま統合されかけた。片側だけが
    # 落ちるのが実際の失敗形なので、落ちた側を数える。
    refutes = {str((e.get("payload", {}) or {}).get("issue") or
                   (e.get("payload", {}) or {}).get("claim_id") or
                   (e.get("payload", {}) or {}).get("deliverable") or "")
               for e in events if e["class"] == "refutation_attempted"
               and e.get("seq") not in voided}
    # In a strict cross-harness org, a negative verdict is recorded provisionally before any joint
    # event exists.  Calling that "no skeptic record" is observably false.  It is not a positive
    # joint decision either, so surface the pending rework/materialization as AMBER.
    provisional_refutes = {
        str((e.get("payload", {}) or {}).get("issue") or
            (e.get("payload", {}) or {}).get("claim_id") or
            (e.get("payload", {}) or {}).get("deliverable") or "")
        for e in events
        if e["class"] == "verdict_provisional" and e.get("seq") not in voided
        and (e.get("payload", {}) or {}).get("role") == "skeptic"
        and (e.get("payload", {}) or {}).get("for_event") == "refutation_attempted"
        and (e.get("payload", {}) or {}).get("verdict") == "refuted"
    }
    provisional_refutes.discard("")
    pending_refuted = sorted(admits & provisional_refutes - refutes)
    for issue in pending_refuted[:5]:
        amber.append(f"#{issue} skeptic が refuted — joint記録またはrework反映待ち")
    # reject されたまま放置されているものは board に出す。RED（あなたを待っている）ではなく
    # AMBER（回っているが見ておくこと）— 差し戻しは正常な過程であって障害ではない。
    # ただし黙って消えると、rework が止まっていることに誰も気づかない。
    rejected = sorted(k for k, (_, v) in latest_admission.items() if v == "reject")
    if rejected:
        # **何が問題だったかを一行出す。** 件数だけでは CEO に何も伝わらない。
        # 判定理由は decide で厚く書かれているのに board から読めないのは、
        # 唯一の画面が要約を持たないということ。
        why_of = {}
        for e in events:
            if e["class"] != "admission_decided" or e.get("seq") in voided:
                continue
            pl = e.get("payload", {}) or {}
            if pl.get("verdict") != "reject":
                continue
            k = str(pl.get("issue") or pl.get("deliverable") or "")
            cur = latest_admission.get(k)
            if cur and cur[0] == (e.get("seq") or 0):
                w = (pl.get("why") or pl.get("reason") or "").strip().replace("\n", " ")
                if w:
                    why_of[k] = w[:80] + ("…" if len(w) > 80 else "")
        for k in rejected[:5]:
            reason = why_of.get(k) or _reject_reason(k)
            amber.append(f"#{k} rework 待ち" + (f" — {reason}" if reason else ""))
        amber.append("詳細は `org_cycle.py show --issue N`")

    unrefuted = {a for a in admits if a and a not in refutes and a not in provisional_refutes}
    if unrefuted:
        red.append(f"admitted but no skeptic record: {len(unrefuted)} "
                   f"({', '.join('#' + x for x in sorted(unrefuted)[:5])}) — "
                   f"one step away from being integrated without facing refutation")

    # 人間待ちの Issue は定義上 RED — 「あなたを待っている」ものが board の意味そのもの。
    # ledger には現れないので GitHub を見る（見られなければ黙って飛ばす。board は落とさない）。
    for line in _needs_human_issues():
        red.append(line)

    if red:
        light = "RED"
    elif amber:
        light = "AMBER"
    else:
        light = "GREEN"

    print(f"{light} — {'needs you' if light == 'RED' else 'running' if light == 'AMBER' else 'healthy'}")
    print(f"  done: {done} cycle(s) completed | backlog open: {max(0, open_backlog)} | "
          f"in progress: {len(in_progress)}")
    if red:
        print("  NEEDS YOU:")
        for r in red:
            print(f"    - {r}")
    if in_progress:
        print("  in progress:")
        for cid, role in list(in_progress.items())[:8]:
            ns = latest.get(cid)
            print(f"    - {cid} ({role})" + (f" — next: {ns}" if ns else ""))
    if adaptive_rows:
        print("  adaptive envelopes:")
        for row in adaptive_rows[-5:]:
            print(f"    - {row['envelope_id']}: {row['status']} | critical: "
                  f"{','.join(row.get('affected_critical_functions') or [])} | taint: "
                  f"{len(row.get('tainted_artifacts') or [])} | revalidate: "
                  f"{','.join(row.get('revalidation_scope') or [])}")
            if row.get("forbidden_actions"):
                print(f"      forbidden: {','.join(row['forbidden_actions'])}")
    if operational and (operational["effective_state"] != "NORMAL" or
                        operational.get("circuits") or operational.get("taints")):
        print("  operational state:")
        print(f"    - effective: {operational['effective_state']} | recorded: "
              f"{operational['recorded_state']} | owner-session: "
              f"{operational.get('owner_session_id') or '-'}")
        for circuit_id, circuit in sorted(operational.get("circuits", {}).items()):
            print(f"    - circuit {circuit_id}: {circuit.get('to_state')} | dependency: "
                  f"{circuit.get('dependency')} | retries: {circuit.get('retry_count')}/"
                  f"{circuit.get('retry_budget')}")
        if operational.get("unresolved_taints"):
            print("    - unresolved taint: " + ", ".join(operational["unresolved_taints"]))
    if amber and not red:
        print("  watch: " + "; ".join(amber))
    if light == "GREEN":
        print("  nothing escalating — fail-quiet is the normal state.")
    return OK


def cmd_redline(a):
    """One-line RED signal for a Monitor to consume (docs/12 §5 Layer-3, escalation transport). Prints a
    single line ONLY when the org is RED (needs the human) — nothing when GREEN/AMBER. A `Monitor` polling
    this turns each RED into a push the moment it appears, so "unattended" is not "unobservable": the
    exception reaches the user without them opening /org. Silent (no output) when healthy — fail-quiet."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_status(a)
    out = buf.getvalue()
    if out.startswith("RED"):
        first = out.splitlines()[0]
        needs = [ln.strip("- ").strip() for ln in out.splitlines() if ln.strip().startswith("-")]
        print(f"RED — org needs you: {'; '.join(needs) if needs else first}", flush=True)
    return OK


def main(argv):
    p = argparse.ArgumentParser(prog="status", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("status"); q.set_defaults(fn=cmd_status)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)")
    q.add_argument("--role", default="")
    q = sub.add_parser("redline"); q.set_defaults(fn=cmd_redline)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)")
    q.add_argument("--role", default="")
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
