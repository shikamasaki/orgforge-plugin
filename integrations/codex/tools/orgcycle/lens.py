"""判定の**観点**を、判定の前に確定させる（judge に導出させない）。

## 状態: **未接続**（2.3.0 では verify から呼んでいない）

手書きの観点3項目では -25% が出たが、**この module が自動生成した観点では再現しなかった**
（下の表の最後の2行）。項目数を3件に絞っても 59.0s → 100.9s と改善しない。手書きとの差が
どこにあるのかを説明できていない以上、効果不明のものを配信経路に入れない。

残しているのは実測記録に価値があるからで、接続するのは差が説明できてからにする。
「速くなるはず」で入れると、後から遅さの原因を探すときに疑う対象が増える。

## なぜ要るか（実測）

judge に渡す材料には SPEC も憲章も入っているが、「**この Issue で具体的にどこを見るか**」
だけが無い。だから judge は毎回ゼロから確認範囲を組み立てる — それが判定時間の大半を占める。

同一材料・同一モデル（gpt-5.6-terra / medium）で3回ずつ計測した中央値:

| 渡したもの | 中央値 |
|---|---|
| 現状（憲章＋SPEC のみ） | 104.8 s |
| **具体的な観点を渡す** | **78.6 s（-25%）** |
| 「MUST から観点を導け」と手順だけ渡す | 96.5 s（-8%） |
| acceptance を10件すべて展開して渡す | 116.0 s（**遅化**） |

最後の行が効く量を決めている。**観点は「絞られている」ことが条件**であり、数を並べると
削減どころか仕事を増やす。だから `max_items` の既定は 3 — 手書きで -25% を出したのと
同じ規模に合わせている。ここを増やすと効果が反転する。

**手順を渡しても効かない**（導出作業を judge にやらせるだけ）。効くのは観点そのもの。
だから観点は「先に確定している」必要があり、それを人が毎回書くと Issue ごとにブレるので、
ここで **機械的に組み立てる**。

## 越えない線（docs/03 §6.5）

**合否条件は書かない。** 実測では「この3コマンドの出力だけで判定せよ、他の考慮は不要」まで
厳格化すると 26.2 s（-69%）まで落ちたが、**placebo 実装を admit した**（文言は満たすが意図を
裏切る実装を、規則が「他の考慮は不要」と命じたために見逃した）。速いのは考えることを
やめさせたからで、それは gate の消滅である。

だからここが書くのは **「どこを・どの順で見るか」だけ**。「何をもって pass とするか」は
書かない。判定は judge のもの。

## 3層（この順に具体的になる）

1. **phase 既定** — フェーズによって確かめるものは変わる（requirements で CI green を
   求めても意味が無く、deploy で EARS 構文を見ても遅い）
2. **変更された seam / contract** — Issue #175 の受け入れ基準。触れていない領域を
   毎回 re-review すると、往復のたびに CI が回り LLM も回る
3. **SPEC の Acceptance** — 1件ずつ、最小の観測を1つ
"""

from __future__ import annotations

import re


# ── 1. phase 既定 ────────────────────────────────────────────────────────────
# 「そのフェーズで**確かめる価値があるもの**」だけを置く。合否は書かない。
# docs/11 の非スキップ相のフェーズ名に合わせる。
_PHASE_LENS = {
    "requirements": [
        "各 acceptance criterion が EARS の5型のいずれかで書かれ、**テスト可能**か"
        "（「認証が動く」のような散文は、それ自体が差し戻しの理由）",
        "Intent が org の telos に接続しているか（指標ではなく目的として）",
    ],
    "design": [
        "seam contract の `provides` が**名前の付いた形**（signature / schema / table）で"
        "書かれ、下流が推測せず結線できるか",
        "`boundary (NOT mine)` が明示され、並行 maker が同じものを作らないか",
    ],
    "implement": [
        "SPEC の DoD command（あれば）を**実際に走らせ**、その実出力を evidence にする",
        "各 acceptance criterion に対応する観測が1つずつ存在するか",
    ],
    "test": [
        "テストが**実際に RED になることが示されているか**（通ることしか示していない"
        "テストは、何も守っていない可能性がある）",
        "異常系・境界が acceptance の範囲で覆われているか",
    ],
    "integrate": [
        "変更された seam contract に対し、**下流の消費側が壊れていないか**",
        "統合先 ref に対する差分が、この Issue の範囲に収まっているか",
    ],
    "deploy": [
        "committed CI workflow が clean clone から green か（**この相ではこれが荷重**）",
        "reproducibility の機械バー（repro_lint）が HOLD していないか",
    ],
    "operate": [
        "退行時に戻せる形（rollback / feature flag）があるか",
        "観測できる形（ログ・メトリクス）が伴っているか",
    ],
}

# EARS の5型。acceptance が構文として検証可能かを **見る観点** として使う（判定はしない）。
_EARS = re.compile(r"\b(?:WHEN|WHILE|IF|WHERE|THE\s+system\s+SHALL|SHALL)\b", re.I)


def _acceptance_lines(spec_text):
    """SPEC 本文から acceptance / MUST の各行を拾う。

    実運用の Issue は `## Acceptance` / `## MUST` / `## Required change` など見出しが揺れる。
    見出し語を固定しすぎると 0 件になり観点が空になるので、受け入れ基準らしい見出しを
    広めに拾い、その下の箇条書き・番号付きを対象にする。
    """
    if not spec_text:
        return []
    heading = re.compile(
        r"^#{1,6}\s*.*(?:acceptance|MUST|受け入れ|required\s+outcome|required\s+change"
        r"|proposed\s+acceptance)", re.I)
    out, inside = [], False
    for line in spec_text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            inside = bool(heading.match(s))
            continue
        if not inside or not s:
            continue
        if re.match(r"^(?:[-*+]|\d+[.)])\s+", s):
            # チェックボックスと箇条書き記号を落として本文だけにする
            out.append(re.sub(r"^(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?", "", s))
    return out


def build_lens(phase, spec_text, changed_seams=None, max_items=3):
    """judge へ渡す「確認の観点」節を組み立てて返す（無ければ None）。

    judge に導出させない。**判定もしない** — 見る順序を与えるだけ。
    """
    phase_key = (phase or "implement").strip().lower()
    lines = []

    defaults = _PHASE_LENS.get(phase_key)
    if defaults:
        lines.append(f"### この相（{phase_key}）で確かめるもの")
        lines.extend(f"- {d}" for d in defaults)

    seams = [s for s in (changed_seams or []) if s]
    if seams:
        lines.append("\n### 変更された seam / contract（ここに結び付く所見だけが blocker）")
        lines.extend(f"- `{s}`" for s in seams[:max_items])
        lines.append("- 上記に触れていない領域は、今回 **re-review しない**。"
                     "所見があれば `out_of_scope` として別記する。")

    accepts = _acceptance_lines(spec_text)
    if accepts:
        shown = accepts[:max_items]
        lines.append(f"\n### 再導出する acceptance（{len(accepts)} 件。1件ずつ順に）")
        for i, a in enumerate(shown, 1):
            mark = "" if _EARS.search(a) else "  ※ EARS 構文でない（テスト可能性を確認せよ）"
            lines.append(f"{i}. {a[:220]}{mark}")
        if len(accepts) > len(shown):
            lines.append(f"（残り {len(accepts) - len(shown)} 件は SPEC 本文を参照）")
        lines.append("- 各件につき **最小の観測を1つ**選び、実際に走らせ、実出力を evidence に貼る。")
        lines.append("- 文言は満たすが意図を裏切る実装（placebo）でも同じ出力になるなら、"
                     "観測を1つ足す。**ここは省略しない。**")

    if not lines:
        return None
    return ("\n## 確認の観点（判定の前に確定済み。探索はここから始めよ）\n"
            + "\n".join(lines)
            + "\n\n> これは**どこを見るか**であって、**何をもって pass とするか**ではない。"
              "合否は上の憲章と SPEC に照らしてあなたが決める。"
              "観点に無い領域でも、安全性・データ完全性・セキュリティ・リリース不能を"
              "具体的に示すものは blocker にしてよい。\n")
