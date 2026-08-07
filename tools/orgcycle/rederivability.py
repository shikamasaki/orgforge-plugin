"""read-only judge が再導出できない MUST を、judge を起動する **前に** 検出する。

## なぜ要るか（実測）

`enforcement.judges.read_only: true` の judge は、書き込みも実行も出来ないサンドボックスで走る。
そのため「実際に走らせて緑を確かめる」類の MUST は **構造的に** 再導出できず、judge は park
（判定不能）を返すしかない。park 自体は正しい振る舞い（測れないのに admit しない）だが、
**それが分かるのが judge を起動して数分〜30分待った後**というのが問題だった。

judge.py はこれを人間向けの警告として「先に言う」だけで、時間の浪費は防いでいなかった:

    実測: #34 は「静的には妥当だが『100回連続 green』を read-only サンドボックスで再導出
    できない」として park を返した。

cross-harness の judge は `codex exec` / `claude -p` を別プロセスとして起動し、既定の
`ORG_JUDGE_TIMEOUT` は 1800 秒。gate → skeptic は直列なので、1 Issue の admission で
これを 2 回踏む。**空振りの park 1 回が数分〜30分**を捨てる。

ここは「その MUST は read-only では測れない」ことだけを **静的に** 指摘して、監督に実測を
促す。judge を起動する前に止めるので、捨てる時間が 0 になる。

## 越えない線（docs/03 §6.5）

**判定はしない。** admit / reject / park を決めるのは gate であって、この module ではない。
ここが返すのは「この MUST は read-only judge の *再導出能力の外* にある」という
**能力の話**だけで、その MUST を満たしているかどうかには一切触れない。
forced invariant は正しいが forced judgment は判定の消滅、という線をここでも守る。

だから既定は **助言（advice）** であって block ではない。`--strict-rederivability` を
明示したときだけ exit 13 で止める（監督が「空振りを絶対に踏みたくない」と宣言した場合）。
"""

from __future__ import annotations

import re


# read-only サンドボックスの *外* にある能力。「その MUST を確かめるには、書く / 動かす /
# 外へ出る」必要があるもの。表現は日英どちらの SPEC でも拾えるようにする（この repo の
# SPEC は実際に混在している）。
#
# 語をここに足すときの基準は「read-only で **原理的に** 測れないか」であって、
# 「難しそうか」ではない。静的に読めば分かるもの（型・命名・構造）は入れない。
_UNMEASURABLE = (
    # 実行して緑を確かめる系
    # 語順を固定しない。`consecutively 100 times` と `100 times consecutively` は同じことを
    # 言っているのに、数字が前に来る形だけを見ていて後者を取りこぼしていた（cross-harness の
    # judge が実地の判定でこの漏れを指摘した — 2周目 verdict=reject の根拠）。
    (r"\b\d+\s*回連続|\b\d+\s*回\s*(?:繰り返|連続)"
     r"|consecutive(?:ly)?\s+\d+\s*(?:times)?|\b\d+\s+times\s+consecutive(?:ly)?"
     r"|\b\d+\s+times\s+in\s+a\s+row|\b\d+\s+consecutive\s+\w+",
     "反復実行の実測（read-only では走らせられない）"),
    (r"\bRED\s*→\s*GREEN|\bred\s*to\s*green|going\s+RED\b",
     "テストを実際に RED→GREEN させる観測"),
    (r"\bCI\b.*\b(?:green|緑|pass)|\b(?:green|緑)\b.*\bCI\b|clean\s+clone.*\b(?:test|build)",
     "CI / クリーンクローンでの実行結果"),
    (r"\bbenchmark|\bp9[59]\b|\blatency\b|\bthroughput\b|スループット|レイテンシ",
     "性能の実測"),
    (r"\bmutation\s+test|ミューテーション",
     "ミューテーションを実際に効かせた観測"),
    # 外部到達系
    (r"\b(?:real|実)\s*(?:DB|database|データベース)|\bmigration\b.*\b(?:apply|適用)",
     "実データベースへの到達"),
    (r"\bdeploy(?:ed|ment)?\b.*\b(?:verif|confirm|確認)|本番.*(?:到達|確認)",
     "デプロイ先での確認"),
    (r"\bnetwork\b.*\b(?:call|request)|外部API.*(?:到達|呼び出)",
     "ネットワーク越しの到達"),
    # 書き込み系
    (r"\bwrites?\s+to\s+disk|ファイルに書き|\bidempotent\b.*\b(?:re-?run|再実行)",
     "書き込みを伴う観測"),
)

_COMPILED = tuple((re.compile(pat, re.I), why) for pat, why in _UNMEASURABLE)


def _must_lines(spec_text):
    """SPEC 本文から MUST の各行を拾う。

    SPEC.md の形（`## MUST — acceptance criteria in EARS`）に従い、MUST 見出しから
    次の見出しまでの箇条書きを対象にする。見出しが無い SPEC（自由記述）でも取りこぼさない
    ように、本文中の `MUST` を含む行も拾う。
    """
    if not spec_text:
        return []
    lines = spec_text.splitlines()
    out, in_must = [], False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            in_must = bool(re.search(r"\bMUST\b|受け入れ基準|acceptance", stripped, re.I))
            continue
        if not stripped:
            continue
        if in_must and re.match(r"^[-*+]\s+|^\d+[.)]\s+", stripped):
            out.append(stripped)
        elif not in_must and re.search(r"\bMUST\b", stripped):
            # 見出しの外に書かれた MUST（自由記述の SPEC）も対象にする。
            out.append(stripped)
    return out


def unmeasurable_musts(spec_text):
    """read-only judge が再導出できない MUST を [(該当行, 理由), ...] で返す。

    **満たしているかは見ない。** 「その MUST を確かめる手段が read-only の外にある」
    ことだけを返す。1行が複数の理由に当たる場合は最初の理由を採る（監督に伝えたいのは
    「実測が要る」という一点で、理由の網羅ではない）。
    """
    found = []
    for line in _must_lines(spec_text):
        for rx, why in _COMPILED:
            if rx.search(line):
                found.append((line, why))
                break
    return found


def advisory(findings, role):
    """監督に見せる助言文。judge を起動する前に出すので、待ち時間が発生しない。"""
    if not findings:
        return None
    head = (f"[rederivability] read-only の {role} judge では再導出できない MUST が "
            f"{len(findings)} 件ある。**このまま起動すると park が返る公算が高い**"
            f"（judge 1回は数分〜{'30分'}かかる — その時間は判定を生まない）。\n")
    body = "".join(f"  - {why}\n      {line[:160]}\n" for line, why in findings)
    tail = ("  対処: 監督が先に実測し、その **実出力** を evidence として渡してから judge を\n"
            "  起動すること（憲章どおり、evidence は実際に走らせたコマンドとその出力）。\n"
            "  この指摘は助言であって判定ではない。承知の上で起動するならそのまま進めてよい。\n"
            "  空振りを絶対に踏みたくないなら `--strict-rederivability` を付けると、ここで止まる。\n")
    return head + body + tail
