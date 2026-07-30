#!/usr/bin/env python3
"""drift — 却下事由を横断して、共通因子を数える。**判定はしない。**

## なぜ「1件ごとの検査」だけでは足りないか

orgforge の検査（gate / skeptic / repro_lint / intake）はすべて **1件ごとの判定** である。
1件ずつは正しく効いていても、「今夜 reject が18回出た、その事由の共通因子は何か」を見る組織が
無い。**同じ因子で18回落ちているなら、直すべきは18件の成果物ではなく、その因子を生んでいる
指示・spec・慣習の側である。**

レジリエンスエンジニアリングの言い方では、**意図された仕事（WAI）と実際に行われた仕事（WAD）の
乖離**を、個々の因果ではなく「日常の変動をファクターへ解体し、共通点を見る」ことで掘り出す。
このコマンドはその材料を出す係で、**どう直すかは監督が決める**。

## 台帳だけでは数えられない

`admission_decided` / `refutation_attempted` の payload は `reasoning_sha256`（ハッシュ）しか
持たず、**散文の why は Issue コメントにしか存在しない**。したがって台帳で「どの Issue が何回
落ちたか」を確定させ、事由の本文は Issue から読む。台帳だけを見て「事由を数えた」と言うことは
できない — 数えられないものを数えたと言わないのが、この道具の役目でもある。
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 却下事由のファクター。**成果物の欠陥ではなく、乖離の型**で切る。
# 「テストが無い」ではなく「MUST の文言は満たしたが意図を満たしていない」のような、
# 指示や spec の側に手を入れられる粒度にする — でなければ材料にならない。
_FACTORS = (
    ("意図と文言の乖離",
     r"文言(?:だけ|のみ)|意図を裏切|placebo|プラセボ|形だけ|体裁|見せかけ|"
     r"満たしているように見え|字面"),
    ("未測定のまま断定",
     r"未測定|測っていな|計測していな|再導出できな|確認していな|検証していな|"
     r"実行していな|エビデンスが無|証跡が無"),
    ("土台の欠落（後続が乗れない）",
     r"依存(?:関係)?が無|インストールされていな|package\.json に無|"
     r"環境が無|設定が無|後続|土台|基盤が"),
    ("範囲の逸脱・取りこぼし",
     r"範囲外|スコープ外|out_of_scope|MUST の一部|漏れ|抜け落ち|含まれていな"),
    ("再現性の欠落",
     r"再現できな|repro|手順が無|同じ結果にならな|環境依存"),
    ("既存の壊し",
     r"回帰|regression|既存の.*壊|落ちるようになった|失敗するようになった"),
    ("権限・認可",
     r"RLS|認可|権限|policy|ポリシー|漏洩|他人の|越境"),
    ("型・静的検査の逃げ",
     r"ignoreBuildErrors|any 型|as any|@ts-|型を逃|typecheck を"),
)


def _sh(cmd):
    try:
        pr = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return pr.stdout if pr.returncode == 0 else ""
    except Exception:
        return ""


def _ledger_rejections(window_days):
    """台帳から (issue, class, verdict, actor, ts) を集める。訂正済みは数えない。"""
    from discover import ledger_root
    from ledger import corrected_seqs
    root = ledger_root()
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        print("台帳が見つからない。org のルートで実行すること。", file=sys.stderr)
        return None
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = corrected_seqs(evs)
    out = []
    for e in evs:
        if e.get("seq") in voided:
            continue
        if e.get("class") not in ("admission_decided", "refutation_attempted"):
            continue
        pl = e.get("payload") or {}
        if pl.get("verdict") not in ("reject", "refuted"):
            continue
        iss = pl.get("issue") or pl.get("deliverable")
        if iss is None:
            continue
        out.append({"issue": str(iss).lstrip("#"), "class": e["class"],
                    "verdict": pl["verdict"], "actor": e.get("actor"),
                    "ts": e.get("ts"), "seq": e.get("seq"),
                    "lineage": pl.get("lineage")})
    return out


def _issue_reasons(issue):
    """その Issue のコメントから **判定の事由だけ** を取り出す。台帳には無い部分である。

    コメントを丸ごと連結して正規表現を当ててはいけない。maker の報告・rework の指示・監督の
    メモまで拾い、**8因子のうち4つが「全 Issue に該当」になって分布が消える**（実測。最初の
    実装がそうなった）。判定コメントは

        ## ⛔ admission_decided — `reject`
        **Why (the reasoning):**   ← ここが事由
        **Evidence consulted:**    ← ここから先は別の話

    という構造を持っているので、`Why` 節だけを切り出す。**構造があるものを本文検索で当てない。**
    """
    raw = _sh(["gh", "issue", "view", str(issue), "--json", "comments"])
    if not raw:
        return []
    try:
        cs = (json.loads(raw) or {}).get("comments") or []
    except Exception:
        return []
    hits = []
    for c in cs:
        b = c.get("body") or ""
        # 判定コメントの見出しを持つものだけ
        if not re.search(r"^##\s*\S*\s*(?:admission_decided|refutation_attempted)\s*—\s*`?"
                         r"(?:reject|refuted)`?", b, re.I | re.M):
            continue
        m = re.search(r"\*\*Why[^*]*\*\*\s*\n(.*?)(?=\n\*\*[A-Z]|\n##\s|\Z)",
                      b, re.S)
        if m:
            hits.append(m.group(1).strip())
    return hits


def cmd_factors(a):
    rows = _ledger_rejections(a.window)
    if rows is None:
        return 3
    if not rows:
        print("却下・反証の記録が台帳に無い。数える材料が無い。")
        return 0

    by_issue = {}
    for r in rows:
        by_issue.setdefault(r["issue"], []).append(r)

    print(f"— 却下・反証 {len(rows)} 件 / Issue {len(by_issue)} 件")
    print(f"  台帳が持つのは判定の事実と reasoning_sha256 まで。"
          f"**事由の散文は Issue コメントにしか無い**ので、そちらから読む。\n")

    factor_hits, unmatched, read = {}, [], 0
    for iss in sorted(by_issue, key=lambda x: -len(by_issue[x])):
        bodies = _issue_reasons(iss)
        if not bodies:
            unmatched.append((iss, len(by_issue[iss]), "Issue コメントを読めなかった"))
            continue
        read += 1
        text = "\n".join(bodies)
        matched = False
        for name, pat in _FACTORS:
            if re.search(pat, text, re.I):
                factor_hits.setdefault(name, []).append(iss)
                matched = True
        if not matched:
            unmatched.append((iss, len(by_issue[iss]), "既知のファクターに当たらない"))

    print(f"===== 却下事由の共通因子（Issue {read} 件のコメントから）=====")
    if not factor_hits:
        print("  共通因子として数えられたものが無い。")
    for name, isses in sorted(factor_hits.items(), key=lambda kv: -len(kv[1])):
        bar = "█" * len(isses)
        print(f"  {len(isses):>3} Issue  {bar:<12} {name}")
        print(f"            #{'  #'.join(sorted(isses, key=lambda x: int(x) if x.isdigit() else 0))}")

    if unmatched:
        # **数えられなかったものを黙って落とさない。** 落としたぶんは「共通因子はこれだけ」の
        # 読みを狂わせる — 道具は「見ていない」ことを言う（docs/11）。
        print(f"\n===== 数えられなかった {len(unmatched)} 件 =====")
        for iss, n, why in unmatched:
            print(f"  #{iss}（却下 {n} 回）— {why}")
        print("  この分は上の集計に入っていない。**「共通因子はこれだけ」と読まないこと。**")

    top = max(factor_hits.items(), key=lambda kv: -(-len(kv[1]))) if factor_hits else None
    print(f"\n===== 材料はここまで。判断は監督のもの =====")
    if top and len(top[1]) >= 2:
        print(f"  最も多いのは「{top[0]}」が {len(top[1])} Issue。\n"
              f"  同じ因子で複数落ちているなら、**直すべきは個々の成果物ではなく、その因子を"
              f"生んでいる側**かもしれない — spec の書き方、gate に渡している基準、\n"
              f"  conventions、あるいは分割の粒度。**どれなのかはこの道具には分からない。**")
    else:
        print("  複数の Issue に跨る因子は出ていない。個別の欠陥として扱うのが自然。")
    print("  この読みを org の資産にするなら conventions に書くこと（次の maker が読む）:\n"
          f'    python3 "{os.path.join(HERE, "doctrine.py")}" --help')
    return 0


def main():
    p = argparse.ArgumentParser(
        prog="drift",
        description="却下事由を横断して共通因子を数える。判定はしない — 材料を出すだけ。")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("factors", help="却下・反証の事由をファクターに解体して数える")
    f.add_argument("--window", type=int, default=0,
                   help="遡る日数（0 = 全期間。既定は全期間 — 少ないうちは絞ると何も出ない）")
    f.set_defaults(fn=cmd_factors)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
