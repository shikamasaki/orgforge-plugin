"""見る・片付ける・残す — show / gc / touched。

1つの Issue の全体像、溜まった worktree の掃除、本番資産への変更の記録。"""

import json
import os
import re
import sys

from ._core import (
    _admission_for,
    _branch_for,
    _events_for,
    _execute,
    _gh_sync,
    _issue_body,
    _ledger,
    _raw,
    _refutation_for,
    _repo,
)



def _issue_reasons(issue):
    """Issue に載っている admission_decided の理由を**古い順**に全部返す。

    台帳は digest しか持たない（設計どおり）ので、理由は Issue にある。1件だけ引くと
    どの周回も同じ最新コメントを見てしまい、周回の性質が全部同じに見える（最初の実装が
    そうなった）。周回ごとに違うものを見たいので、並びで取る。
    """
    args = ["gh", "issue", "view", str(issue), "--json", "comments"]
    r = _repo()
    if r:
        args += ["--repo", r]
    code, out = _raw(args)
    if code != 0:
        return []
    try:
        cs = json.loads(out).get("comments", [])
    except Exception:
        return []
    out_r = []
    for c in cs:
        b = c.get("body") or ""
        if "admission_decided" not in b:
            continue
        m = re.search(r"\*\*Why \(the reasoning\):\*\*\s*\n(.+)", b)
        out_r.append(" ".join(m.group(1).split())[:600] if m else "")
    return out_r


def cmd_show(a):
    """1つの Issue について「誰が何を判定し、いま何待ちか」を一望する。

    実地では gh issue view と台帳の grep と status.py を別々に叩く必要があり、#7 が3周した
    ときにどの周のどの判定を見ているのか分からなくなった。#8 の refutation 欠落も #11 の
    reject 欠落も、この視点があれば即座に見つかっていた。
    """
    title, _ = _issue_body(a.issue)
    av, aseq, _ = _admission_for(a.issue)
    rv, rseq, _ = _refutation_for(a.issue)
    evs, voided = _events_for(a.issue)

    state = ("rework 待ち" if av == "reject" else
             "統合できる" if av == "admit" and rv == "survives" else
             "反証で差し戻し" if rv == "refuted" else
             "skeptic 待ち" if av == "admit" else
             "gate 待ち" if any(e["class"] == "cycle_completed" for e in evs) else
             "実装中" if any(e["class"] == "cycle_started" for e in evs) else "未着手")

    print(f"#{a.issue} {title or ''} — {state}")

    br = _branch_for(a.issue)
    code, log = _raw(["git", "log", "--oneline", "-3", br])
    if code == 0 and log.strip():
        print(f"  実装:     {' / '.join(l.split(' ',1)[0] for l in log.strip().splitlines())}"
              f"  ({br})")
    wt = os.path.join(os.getcwd(), ".orgforge", "wt", f"issue-{a.issue}")
    print(f"  worktree: {'.orgforge/wt/issue-%d/' % a.issue if os.path.isdir(wt) else '(なし)'}")

    # 判定の履歴 — 何周目のどの判定かが分かるように全部出す
    judged = [e for e in evs if e["class"] in
              ("admission_decided", "refutation_attempted", "rework_requested",
               "integration_admitted", "result_deployed")]
    if judged:
        print("  判定:")
        for e in judged:
            pl = e.get("payload", {}) or {}
            mark = "✗" if e.get("seq") in voided else " "
            why = (pl.get("why") or pl.get("reason") or "")[:70]
            note = " ⟨訂正済み⟩" if e.get("seq") in voided else ""
            bf = " ⟨backfill⟩" if pl.get("backfilled") else ""
            print(f"   {mark} seq {e.get('seq')}: {e['class']} = {pl.get('verdict', '-')}"
                  f" by {e.get('actor')}{note}{bf}"
                  + (f"\n        {why}" if why else ""))
    else:
        print("  判定:     まだ無い")

    # 4: 周回が何を意味しているか。#9 が9周、#11 が10周した。統制は毎回実害のある欠陥を
    # 見つけており機能しているが、**いつ収束するかの見通しが立たない**。回数だけでなく
    # 「直近の判定が何を問題にしているか」が見えると、切るかどうかの判断材料になる。
    # **判定はしない** — 「もう切れ」とは言わない。性質の変化を並べるだけ。
    rounds = [e for e in judged if e["class"] == "admission_decided"]
    if len(rounds) >= 3:
        reasons = _issue_reasons(a.issue)
        kinds = []
        for idx, e in enumerate(rounds[-3:]):
            pl = e.get("payload", {}) or {}
            txt = " ".join(str(pl.get(k, "")) for k in ("why", "reason", "note"))
            if not txt.strip():
                # 台帳の並びと Issue の並びを末尾から対応させる（どちらも時系列）
                j = len(reasons) - 3 + idx
                txt = reasons[j] if 0 <= j < len(reasons) else ""
            # 分類はキーワードによる粗い当て推量である。**判断材料であって判断ではない** —
            # 「テストの欠陥が3周続いている」は切る理由になり得るが、切るかどうかは CEO が決める。
            # 誤分類しうるので、原文は Issue と `judged` の一覧で読めるようにしてある。
            k = ("テストの欠陥" if re.search(r"テスト|警報|検出できな|placebo|ミューテーション", txt)
                 else "実装の欠陥" if txt else "不明")
            kinds.append(k)
        print(f"  周回:     {len(rounds)} 周 — 直近3回: {' / '.join(kinds)}")
        if kinds.count("テストの欠陥") == 3:
            print(f"            直近3周とも「MUST は満たすが検査が足りない」型。"
                  f"実装ではなく検査の欠陥が続いている")

    nxt = ("gate 再判定 → skeptic → integrate" if av == "reject" else
           f"integrate --issue {a.issue}" if av == "admit" and rv == "survives" else
           f"verify --issue {a.issue} --role skeptic" if av == "admit" else
           f"verify --issue {a.issue} --role gate")
    print(f"  次:       {nxt}")
    return 0


def cmd_gc(a):
    """5: 溜まった worktree を片付ける。**未コミットの変更があるものは残す。**

    complete/integrate が片付けるようになったが、既に溜まったものと、予算 cap で消せず
    残ったものは誰の仕事でもなかった。統合済みなのに残っていると、次に同じ Issue を
    触ったとき古いツリーを掴む。
    """
    base = os.path.join(os.getcwd(), ".orgforge", "wt")
    if not os.path.isdir(base):
        print("worktree はありません。")
        return 0
    kept, removed = [], []
    for name in sorted(os.listdir(base)):
        if not name.startswith("issue-"):
            continue
        issue = name[len("issue-"):]
        wt = os.path.join(base, name)
        code, out = _raw(["git", "-C", wt, "status", "--porcelain"])
        if code == 0 and out.strip():
            kept.append((name, f"未コミットの変更 {len(out.strip().splitlines())} 件"))
            continue
        if not a.all:
            # 既定は「統合済みだけ」を消す。まだ取り込まれていない仕事は消さない。
            br = _branch_for(issue)
            code, merged = _raw(["git", "branch", "--merged", a.base, "--list", br])
            if code != 0 or not (merged or "").strip():
                kept.append((name, f"{a.base} に未統合"))
                continue
        code, out = _raw(["git", "worktree", "remove", wt])
        (removed if code == 0 else kept).append(
            (name, "片付けた" if code == 0 else out.strip()[:60]))
    # .orgforge/wt/ の外に作られた検証用 worktree（scratchpad 等）も git は把握している。
    # 実地では skeptic が scratchpad に作った sk7 が、予算 cap で消せず残っていた。
    # 「配管が作った場所」しか見ないと、こういう孤児が永久に残る。
    code, out = _raw(["git", "worktree", "list", "--porcelain"])
    if code == 0:
        for block in (out or "").split("\n\n"):
            m = re.search(r"^worktree (.+)$", block, re.M)
            if not m:
                continue
            wt = m.group(1)
            if wt == os.getcwd() or base in wt:
                continue
            if not any(k in wt for k in ("/scratchpad/", "/tmp/")):
                continue      # 素性の分からない場所は触らない
            name = os.path.basename(wt)
            code2, st = _raw(["git", "-C", wt, "status", "--porcelain"])
            if code2 == 0 and st.strip():
                kept.append((name, f"未コミットの変更 {len(st.strip().splitlines())} 件（{wt}）"))
                continue
            if not os.path.isdir(wt):
                code3, o3 = _raw(["git", "worktree", "prune"])
                removed.append((name, "消えていたので prune"))
                continue
            code3, o3 = _raw(["git", "worktree", "remove", wt])
            (removed if code3 == 0 else kept).append(
                (name, f"片付けた（{wt}）" if code3 == 0 else o3.strip()[:60]))

    for n, why in removed:
        print(f"  ✓ {n} — {why}")
    for n, why in kept:
        print(f"  · {n} — 残した（{why}）")
    print(f"\n{len(removed)} 個を片付け、{len(kept)} 個を残した。")
    if kept:
        print("残したものは中身を確認すること — 消えて困るかは、こちらが決めてよいことではない。")
    return 0


def cmd_touched(a):
    """本番資産への変更を台帳に残す。

    exposure_budget_checked はローカルのファイル操作を数えるが、リモート DB への DDL や
    本番の権限変更は数えていない。実際には後者のほうが危険で、しかも取り消しにコストが
    かかる。実地では本番 DB にマイグレーション2本と権限の revoke が入ったのに台帳には
    何も残らず、「あの revoke は誰の権限で入ったのか」が辿れない状態になった。
    """
    payload = {"target": a.target, "op": a.op, "name": a.name or "",
               "reversible": bool(a.reversible), "authority": a.authority,
               "issue": a.issue, "rollback": a.rollback or ""}
    rc = _execute([
        (f"asset_touched: {a.op} on {a.target}",
         lambda: _ledger("append", "--actor", a.by, "--class", "asset_touched",
                         "--natural-key", f"asset-{a.target}-{a.op}-{a.name or a.issue}",
                         "--payload", json.dumps(payload, ensure_ascii=False))),
    ], f"record asset_touched ({a.target})")
    if rc == 0 and a.issue:
        _gh_sync("log", "--issue", str(a.issue), "--event", "progress_recorded",
                 "--detail", f"本番資産に変更: {a.op} {a.name or ''} on {a.target}"
                             f"（{'戻せる' if a.reversible else '**戻せない**'} / 権限: {a.authority}）",
                 "--command", f"{a.op} {a.name or ''}".strip(),
                 "--result", a.rollback or "（rollback 手順は未記録）")
    if not a.reversible:
        print("  ⚠ reversible=false — 戻せないことを承知で入れた、という記録になった。", file=sys.stderr)
    return rc


# 外に晒される面のパターン。SQL / TS / Python の代表的な公開の形だけを見る。
# 完全な検出は目的ではない — **見落としを人に問い返す**のが目的なので、拾いすぎるより
# 「これは公開面ではないか」と聞ける程度で足りる。
