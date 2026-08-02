#!/usr/bin/env python3
"""learning — the org learning from its OWN outcomes (docs/05 §5.4, OUTCOME-DELTA).

The doctrine organ (docs/06) imports EXTERNAL best-practice and is, by explicit design,
structurally blind to THIS org's own miscalibration. Without a self-outcome event the org
repeats its own mistakes forever — nothing converts "our prediction was wrong" into a durable,
injectable fact. This tool joins closed decisions to their realized outcomes and emits an
outcome_delta ONLY when the miss is large or recurrent; it escalates to the CEO only when the
SAME delta class recurs past a systemic threshold ("how we operate is wrong"), never on a
single miss. It is distinct from doctrine: doctrine is the outside world, this is the org's
own track record. Pure projection over tools/ledger.py; ships no scheduler (R0).

  delta <root> [--threshold F] [--recurrence N]   join decisions to outcomes; emit deltas past
      threshold; escalate only a delta CLASS that recurs >= N times (systemic).

  repeats <root> [--recurrence N]   REPEATED-DEATH detector: escalate a death cause that reappears
      on a later candidate (>= N times) — the org re-made a mistake it had already recorded, i.e.
      accumulated learning was NOT fed forward. The direct measure of "learning lifts quality."

A "decision" is an admission_decided (verdict admit) carrying a predicted_outcome in its
payload; its "realized outcome" is a later result_deployed / result_retired for the same
candidate_id carrying an observed_outcome. The delta is |predicted - observed|. Silent when
predictions matched (the default — no event at all).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import ESCALATE, OK, read_events, emit_event   # noqa: E402

# ── 死因の「根」の分類語彙（closed vocabulary、Issue #104 / OBS-052）────────────────
# 実地（Tatekae）では、同じ根の失敗が別の言葉で記録され、文字列完全一致の検出器が
# 3回連続で clean を出した。**自由文の意味一致を機械に推測させない** — 記録する側が
# 記録時に分類する。語彙は ledger-schema.yaml validation.enums の `root` と同一で
# なければならない（tests/test_learning.py が突き合わせる）。
DEATH_ROOTS = {
    "placebo_test":          "検査が本番経路を測っていない（テスト硬化・placebo テスト）",
    "declaration_drift":     "宣言と実装が乖離した",
    "integration_base_moved": "統合先が動いて前提が崩れた",
    "self_written_premise":  "検査される当事者が検査の前提を書ける",
    "other":                 "上記のどれでもない（自由文 cause で根を補足すること。判別する根では"
                             "ないので再発は文字列一致でしか見えない — root グループを形成しない）",
}


def cmd_delta(a):
    events = read_events(a.root)
    # index predictions by candidate_id, from admission_decided(admit) with a predicted_outcome
    predicted = {}
    for e in events:
        if e["class"] == "admission_decided" and e["payload"].get("verdict") == "admit":
            cid = e["payload"].get("candidate_id")
            po = e["payload"].get("predicted_outcome")
            if cid is not None and po is not None:
                predicted[cid] = {"value": po, "seq": e["seq"],
                                  "dept": e["payload"].get("gate")}
    # realized outcomes from result_deployed / result_retired carrying observed_outcome
    deltas = []
    for e in events:
        if e["class"] in ("result_deployed", "result_retired"):
            cid = e["payload"].get("candidate_id")
            oo = e["payload"].get("observed_outcome")
            if cid in predicted and oo is not None:
                pred = predicted[cid]["value"]
                try:
                    mag = abs(float(oo) - float(pred))
                    sign = 1 if float(oo) > float(pred) else -1 if float(oo) < float(pred) else 0
                except (TypeError, ValueError):
                    mag = 0 if oo == pred else 1
                    sign = 0
                if mag > a.threshold:
                    deltas.append({"decision_event_id": predicted[cid]["seq"],
                                   "candidate_id": cid,
                                   "predicted_outcome": pred, "observed_outcome": oo,
                                   "delta_magnitude": mag, "delta_sign": sign,
                                   "department": predicted[cid]["dept"],
                                   "hypothesized_cause": e["payload"].get("cause")})
    if not deltas:
        print("matched: every closed decision's outcome matched its prediction within "
              f"threshold {a.threshold} — silent, no event.")
        return OK
    # recurrence: same department + same sign is a "delta class"; count occurrences
    klass = {}
    for d in deltas:
        k = (d["department"], d["delta_sign"])
        klass.setdefault(k, []).append(d)
    escalate = False
    for d in deltas:
        rc = len(klass[(d["department"], d["delta_sign"])])
        d["recurrence_count"] = rc
        emit_event("outcome_delta", d)
        if rc >= a.recurrence:
            escalate = True
    if escalate:
        systemic = [k for k, v in klass.items() if len(v) >= a.recurrence]
        print(f"SYSTEMIC: {len(deltas)} outcome delta(s); classes {systemic} recurred >= "
              f"{a.recurrence} times — 'how we operate is wrong', escalate to the CEO. This is "
              f"the org learning from ITS OWN track record, not the outside world (that's "
              f"doctrine).", file=sys.stderr)
        return ESCALATE
    print(f"noted: {len(deltas)} outcome delta(s) past threshold, none recurring >= "
          f"{a.recurrence} — recorded as injectable facts, no CEO traffic yet.")
    return OK


def cmd_repeats(a):
    """REPEATED-DEATH detector — the direct measure of whether accumulated learning is actually USED.
    A death (a result_retired / a refutation that failed) carries a `cause`. If the SAME cause reappears
    on a LATER candidate, the org failed to feed its own lesson forward — it re-made a mistake it had
    already recorded (the org's core purpose, missed). This escalates a cause that recurs >= --recurrence
    times, naming the deaths, so "learning lifts quality" is a checked fact, not a hope. Silent when every
    death cause is distinct (no lesson was ignored).

    再発は記録時の根分類 `root`（DEATH_ROOTS）で数え、root の無いレガシー記録だけ文字列完全一致に
    フォールバックする（Issue #104: 完全一致は同根の言い換えを素通りした）。"""
    events = read_events(a.root)
    by_key = {}
    # 「死因」を運ぶフィールドは書き手によって揺れる。以前は `cause` しか読まず、
    # rework_requested は対象ですらなかったため、**同じ失敗を3回した org に対して
    # 「学習が使われている」と報告した**。検出器が読むキーは、実際に書かれるキーに合わせる。
    _CAUSE_KEYS = ("cause", "hypothesized_cause", "reason", "why", "checklist_ref")
    _DEATH_CLASSES = ("result_retired", "rework_requested", "refutation_attempted")

    def _cause_text_of(p):
        for k in _CAUSE_KEYS:
            v = p.get(k)
            if v and str(v).strip():
                return v
        return None

    # 再発は **記録時の根分類（`root`、DEATH_ROOTS）** で数える。文字列一致は、root の無い
    # レガシー記録への後方互換フォールバック（Issue #104: 完全一致は同根の言い換えを素通りした）。
    classified = 0        # root が付いた死
    unclassified = 0      # 自由文しか無い死（文字列完全一致でしか見えない）
    for e in events:
        p = e.get("payload", {})
        if e["class"] not in _DEATH_CLASSES:
            continue
        if e["class"] == "refutation_attempted" and p.get("verdict") != "refuted":
            continue      # survives は死ではない
        root = str(p.get("root") or "").strip()
        cause = _cause_text_of(p)
        # `other` は判別する根ではない — 「上記のどれでもない」が2件あっても、根が同じ
        # ことは何も記録されていない。root グループにすると、無関係な死2件を「文言は
        # 違っても根は同じ」と escalate する（意味一致の捏造。gate が実測で検出）。
        # `other` は **マーカー付きの未分類** として文字列一致にフォールバックする。
        # 同じ理由で **語彙（DEATH_ROOTS）の外の文字列も root グループにしない** —
        # enum の無い旧 schema 経由でしか書けない値で、共有していても根の同一性は
        # 何も記録されていない（skeptic が実測で検出）。文字列一致に落とす。
        if root and root != "other" and root in DEATH_ROOTS:
            classified += 1
            key = ("root", root)
        elif cause:
            unclassified += 1
            key = ("cause", str(cause).strip().lower())
        else:
            continue      # 死因を読み取れない（下の unknown 分岐で数える）
        by_key.setdefault(key, []).append({"seq": e["seq"], "cause": cause, "root": root or None,
                                           "candidate_id": p.get("candidate_id")})
    readable = classified + unclassified
    repeated = {k: hits for k, hits in by_key.items() if len(hits) >= a.recurrence}
    deaths = sum(1 for e in events if e["class"] in _DEATH_CLASSES
                 and not (e["class"] == "refutation_attempted"
                          and e.get("payload", {}).get("verdict") != "refuted"))
    if not repeated:
        if deaths and not readable:
            # **読めるものが1件も無いのに clean と言わない。** 「繰り返していない」と
            # 「見えていない」は別で、混同すると誤った安心になる — 検出器が嘘をつくのは、
            # 検出器が無いより悪い（実地でまさにこれが起きた）。
            print(f"unknown: {deaths} 件の差し戻し/反証があるが、死因を読み取れたものが0件。"
                  f"繰り返しの有無は判定できていない。\n"
                  f"  payload に {' / '.join(_CAUSE_KEYS)} のいずれかで死因を書き、あわせて "
                  f"`root`（{'/'.join(DEATH_ROOTS)}）で根を分類すること。"
                  f"書かれていない限り、同じ失敗を何度繰り返してもこの検出器は気づけない。")
            return OK
        print(f"clean: no death cause recurred >= {a.recurrence} times — accumulated learning is being "
              f"used, no known mistake re-made. Silent."
              + (f" ({readable} 件の死因を読んだ)" if readable else ""))
        if readable:
            # clean の判定基準を明示する — root 分類で見た件数と、文字列一致でしか
            # 見えていない未分類の件数を分けて言う（両者の保証は同じではない）。
            print(f"  判定基準: 根分類（root）{classified} 件 / 文字列完全一致（root 未分類）"
                  f"{unclassified} 件。")
        if unclassified >= 1:
            # **移行期でも警告は消えない**（unclassified が1件でも出す）。分類済みが増えて
            # 未分類が recurrence 未満に減った途端に警告が消えると、残った未分類の1件が
            # 同根の再発でも黙って clean に見える（skeptic が実測で検出）。
            # root の無い記録は完全一致でしか繰り返しを見ない。実地では「端数の偏り」と
            # 「テスト硬化」という別々の文言で記録された2件が、根は同じ（性質が壊れる場所を
            # 検証していない）だった。clean を「同じ失敗をしていない」証明として読ませない
            # ために、限界を明示する。
            print(f"  注意: root 未分類の {unclassified} 件は死因の**文字列**でしか見ていない。"
                  f"同じ根の失敗が別の言葉で書かれていれば、この検出器は素通りする。"
                  f"並べて読み直し、`root`（{'/'.join(DEATH_ROOTS)}）を付けて記録し直す価値が"
                  f"ある（`ledger.py view` / Issue のコメント）。")
        return OK
    for key, hits in sorted(repeated.items(), key=lambda kv: -len(kv[1])):
        emit_event("repeated_death_detected", {
            "cause": hits[0]["cause"] or hits[0]["root"], "occurrences": len(hits),
            "root": hits[0]["root"], "basis": key[0],
            "candidate_ids": [h["candidate_id"] for h in hits]})
    worst = max(repeated.items(), key=lambda kv: len(kv[1]))
    wkey, whits = worst
    if wkey[0] == "root":
        root = wkey[1]
        cause = whits[0]["cause"] or DEATH_ROOTS.get(root, root)
        wordings = sorted({str(h["cause"]) for h in whits if h["cause"]})
        print(f"REPEATED DEATH: root {root!r}（{DEATH_ROOTS.get(root, '未知の分類')}）recurred "
              f"{len(whits)} times (candidates {[h['candidate_id'] for h in whits]}) — 文言は"
              f"違っても根は同じ: {wordings}. The org re-made a mistake it had already recorded. "
              f"Accumulated learning was NOT fed forward; strengthen the death into doctrine and "
              f"inject it before the next attempt (docs/06). This is the org's core purpose "
              f"failing — escalate.", file=sys.stderr)
    else:
        cause = whits[0]["cause"]
        print(f"REPEATED DEATH: cause {cause!r} recurred {len(whits)} times "
              f"(candidates {[h['candidate_id'] for h in whits]}) — the org re-made a mistake it had "
              f"already recorded. Accumulated learning was NOT fed forward; strengthen the death into "
              f"doctrine and inject it before the next attempt (docs/06). This is the org's core purpose "
              f"failing — escalate.", file=sys.stderr)
    # 「doctrine に強化せよ」と散文で言うだけでは強化されない。実地では検出も蓄積も配布も
    # 動かないまま同じ失敗を3回繰り返した。**打つべきコマンドを出す** — 経路が無い指示は、
    # 指示ではなく願望になる。何を doctrine にするか（文言・対象役割）は人が決める。
    here = os.path.dirname(os.path.abspath(__file__))
    droot = os.path.join(os.path.dirname(a.root.rstrip("/")), "doctrine")
    print(f"\nNEXT: この死因を doctrine に上げること（配布は handoff.py が役割ごとに行う）:\n"
          f'  python3 "{os.path.join(here, "doctrine.py")}" propose "{droot}" <role> \\\n'
          f'      --claim "{str(cause)[:80]}" --source "repeated-death" --confidence 0.9 \\\n'
          f'      --retrieved-at $(date -u +%Y-%m-%d) --review-by $(date -u -v+180d +%Y-%m-%d) \\\n'
          f'      --affects <この失敗が効く役割をカンマ区切りで>\n'
          f'  そのうえで gate が admit する: doctrine.py admit "{droot}" <role> <claim-id> --by gate\n'
          f"  admit されるまで次のサイクルには渡らない。", file=sys.stderr)
    return ESCALATE


def main(argv):
    p = argparse.ArgumentParser(prog="learning", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("delta"); q.set_defaults(fn=cmd_delta)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")
    q.add_argument("--threshold", type=float, default=0.2)
    q.add_argument("--recurrence", type=int, default=3)
    q = sub.add_parser("repeats"); q.set_defaults(fn=cmd_repeats)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")
    q.add_argument("--recurrence", type=int, default=2)
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
