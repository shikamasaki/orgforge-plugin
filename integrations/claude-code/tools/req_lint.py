#!/usr/bin/env python3
"""req_lint — REQUIREMENTS.md が要求記述の標準に適合しているか検査する（docs/11 §0b）。

**なぜこれが要るのか。** docs/11 §0a は founding 成果物の *ファイル名* を固定したが、*中身の書式*
は規定していなかった。その結果、founding のたびにエージェントが構成をその場で発明し、同じ要求から
別の構造の文書が出る — プラグインの中核主張（同じ spec ⇒ 同じプロセス・同じ契約）が、要求記述の
層で最初から破れていた。書式を機械検査することでその穴を塞ぐ。

**準拠のレベル: ISO/IEC/IEEE 29148:2018 の tailored conformance**（同規格 §4.5.2 が正式に認める
適合形態）。SRS の全20条項（§9.6）は採らない — `Memory constraints` 等は組込み・防衛向けで、
小規模プロダクトでは空欄が並ぶだけになり、空欄の節がある文書は読まれなくなり更新もされなくなる。
採るのは4条項:

  §5.2.4  構文規約      — 主語＋shall。must は使わない（要求と誤解される）
  §5.2.5  個々の要求    — Verifiable / Singular / Unambiguous …（9特性）
  §5.2.6  集合の特性    — TBD/TBS/TBR を残さない、矛盾・重複がない（5特性）
  §5.2.7  避けるべき語  — 主観語・最上級・抜け穴・全称語（本ツールの中核）

加えて EARS（Alistair Mavin / Rolls-Royce。Airbus・NASA・Bosch・Intel・Siemens 採用）の6パターンと、
GitHub Spec Kit 由来の `[NEEDS CLARIFICATION]` マーカーを検査する。後者が最重要 — **エージェントが
曖昧なまま推測で実装するのが最大の失敗モード**であり、未解決のマーカーが残ったまま実装フェーズに
入るのを機械的に止める。

  req_lint.py check <path/to/REQUIREMENTS.md> [--json] [--warn-only]

Exit: 0 適合 / 10 違反あり（gate は HOLD すべき）/ 2 usage・読み取りエラー
"""
import argparse
import json
import os
import re
import sys

# ── 必須セクション（template/REQUIREMENTS.md の骨格）──────────────────────────
# 見出しの表記ゆれを吸収するため、各セクションは「これらの語のいずれかを含む見出し」で判定する。
# 厳密な文字列一致にすると、日本語/英語の混在や番号付けの違いで落ちて実用に耐えない。
REQUIRED_SECTIONS = [
    ("why",        ["why", "なぜ", "目的", "purpose"]),
    ("goals",      ["goal", "ゴール", "目標"]),
    ("non-goals",  ["non-goal", "non goal", "やらない", "非目標"]),
    ("requirements", ["requirement", "要求", "機能要件"]),
    ("acceptance", ["acceptance", "受入", "受け入れ"]),
    ("success",    ["success criteria", "成功基準", "成功指標"]),
    ("constraints", ["constraint", "制約", "non-functional", "非機能"]),
    ("out-of-scope", ["out of scope", "スコープ外", "除外", "exclude"]),
]

# ── §5.2.7 避けるべき語 ──────────────────────────────────────────────────────
# 規格が "shall be avoided" とする語。要求文の中に現れたら落とす。
# (正規表現, 種類, 説明) — 日本語は語境界が無いので \b を使わない。
BANNED = [
    (r"\b(best|most|optimal|maximum possible)\b", "最上級",
     "何と比べて最上かが検証できない"),
    (r"(最高の|最適な|最善の|可能な限り)", "最上級", "何と比べて最上かが検証できない"),
    (r"\b(user[- ]friendly|easy to use|cost[- ]effective|intuitive|seamless)\b", "主観語",
     "人によって判定が変わる。観測可能な条件に書き換える"),
    (r"(使いやすい|分かりやすい|わかりやすい|直感的|快適に|スムーズに)", "主観語",
     "人によって判定が変わる。観測可能な条件に書き換える"),
    (r"\b(almost always|significant|minimal|sufficient|adequate|reasonable)\b", "曖昧な形容",
     "程度が定まらない。数値か観測条件にする"),
    (r"(ほぼ|十分に|適切に|なるべく|できるだけ|柔軟に)", "曖昧な形容",
     "程度が定まらない。数値か観測条件にする"),
    (r"\b(and\s*/\s*or)\b", "曖昧な接続", "and と or のどちらかに決める"),
    (r"(および/または|かつ/または)", "曖昧な接続", "and と or のどちらかに決める"),
    (r"\b(etc\.|and so on|but not limited to|as a minimum|provide support for)\b", "非検証語",
     "範囲が閉じない。列挙し切るか、境界を書く"),
    (r"(など|等をサポート|その他)", "非検証語", "範囲が閉じない。列挙し切るか、境界を書く"),
    (r"\b(better than|faster than|improved)\b", "比較句",
     "基準が示されていない。何と比べてどれだけかを書く"),
    (r"(より良い|より速い|改善された)", "比較句", "基準が示されていない"),
    (r"\b(if possible|as appropriate|if needed|where necessary)\b", "抜け穴",
     "実装しない口実になる。条件を確定させる"),
    (r"(可能であれば|必要に応じて|状況に応じて)", "抜け穴", "実装しない口実になる"),
    (r"\b(all|always|never|every|none)\b", "全称語",
     "例外の有無が検証されていない。本当に例外がないか確認し、あるなら書く"),
    (r"(すべての場合|常に|決して|一切)", "全称語", "例外の有無が検証されていない"),
]

# TBD/TBS/TBR — §5.2.6 Complete が明示的に禁じる
TBX = re.compile(r"\b(TBD|TBS|TBR)\b")

# §5.2.4 — `must` は要求と誤解されるので使わない
MUST_KEYWORD = re.compile(r"\bmust\b", re.I)

# EARS の6パターン（英語・日本語の両方を認める）
# 日本語の shall 相当。「〜すること」だけでは足りない — 実際の要求文は「記録に残すこと」
# 「対象に含めないこと」「リマインダーを送ること」のように、動詞の連体形＋「こと」で終わる。
# 「すること」限定にすると、正しく書かれた要求の大半を違反として弾く（実地で判明）。
EARS_PATTERNS = [
    (r"\bshall\b", "shall"),
    (r"こと(\s*\||\s*$|。)", "shall(ja: 〜こと)"),
    (r"(しなければならない|するものとする|してはならない)", "shall(ja)"),
]
EARS_TRIGGERS = [r"\bwhile\b", r"\bwhen\b", r"\bwhere\b", r"\bif\b",
                 r"(のとき|の場合|している間|ならば)"]

CLARIFY = re.compile(r"\[NEEDS[ _]CLARIFICATION[^\]]*\]", re.I)
# 要求 ID: FR-001 形式。行頭やテーブルセル内を許す
REQ_ID = re.compile(r"\bFR-\d{3,}\b")
SC_ID = re.compile(r"\bSC-\d{3,}\b")


# 付録（レビューチェックリスト）以降は検査しない。そこには禁止語そのものが「例」として並ぶので、
# 検査すると必ず落ちる — 規約を書いた文書が規約違反になるという不合理を避ける。
APPENDIX = re.compile(r"^#{1,6}\s*(付録|appendix|レビューチェックリスト)", re.M | re.I)


def _strip_noise(text):
    """検査対象の本文だけを返す。除くのは3つ:

    1. **引用（`> ...`）** — テンプレの解説。EARS の説明や禁止語の解説が含まれる
    2. **コードブロック** — 記法の例示
    3. **付録以降** — 禁止語リストそのものが並ぶ

    これらを検査すると、規約を正しく説明している文書ほど違反数が多くなる。検査すべきは
    *著者が書いた要求文* だけ。"""
    m = APPENDIX.search(text)
    if m:
        text = text[:m.start()]
    out, in_code = [], False
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or s.startswith(">"):
            continue
        out.append(line)
    return "\n".join(out)


def _sections(text):
    """見出し（# 〜 ######）の一覧を小文字で返す。"""
    return [m.group(1).strip().lower()
            for m in re.finditer(r"^#{1,6}\s+(.+)$", text, flags=re.M)]


# 受入基準セクションは Given-When-Then で書く（EARS ではない）。FR-xxx を参照するので要求文と
# 誤認されるが、記法が違うのは正しい — 要求は EARS、その検証シナリオは GWT という役割分担。
GWT = re.compile(r"\b(given|when|then)\b", re.I)
ACCEPTANCE_HEAD = re.compile(r"^#{1,6}.*(acceptance|受入|受け入れ)", re.M | re.I)
NEXT_HEAD = re.compile(r"^#{1,6}\s", re.M)


def _acceptance_span(text):
    """受入基準セクションの行番号の範囲 (start, end) を返す。無ければ (0, 0)。"""
    m = ACCEPTANCE_HEAD.search(text)
    if not m:
        return (0, 0)
    start = text[:m.start()].count("\n") + 1
    nxt = NEXT_HEAD.search(text, m.end())
    end = (text[:nxt.start()].count("\n") + 1) if nxt else text.count("\n") + 2
    return (start, end)


def _requirement_lines(text):
    """要求文とみなす行。FR-xxx を含む行、または表の行で shall/すること を含むもの。

    除外するもの: 見出し（節タイトルに FR-001 と書かれることがある）、受入基準セクション内
    （GWT で書くのが正しく、shall が無いのは違反ではない）、GWT キーワードを含む行。"""
    a_start, a_end = _acceptance_span(text)
    lines = []
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if a_start <= i < a_end:          # 受入基準セクション内は対象外
            continue
        if GWT.search(line) and not re.search(r"\bshall\b", line, re.I):
            continue                       # GWT シナリオ行
        # 要求 ID を「定義している」行か、「参照している」だけの行かを区別する。
        # 制約表や EXCLUDE 表は根拠として (FR-021) のように参照するが、それ自体は要求文ではない。
        # 定義行は必ず先頭セルが ID（`| FR-001 | …`）なので、そこで判定する。
        cells = [c.strip() for c in s.strip("|").split("|")] if s.startswith("|") else []
        defines = bool(cells) and bool(REQ_ID.match(cells[0].replace("**", "")))
        if defines or (s.startswith("|") and not cells[0:1]
                       and any(re.search(p, line, re.I) for p, _ in EARS_PATTERNS)):
            lines.append((i, line))
    return lines


def check(path):
    """検査して violations のリストを返す。各要素 {code, severity, line, message}"""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    body = _strip_noise(raw)
    v = []

    # SEC — 必須セクション（§9 相当を tailoring したもの）
    heads = " || ".join(_sections(raw))
    for key, aliases in REQUIRED_SECTIONS:
        if not any(a in heads for a in aliases):
            v.append({"code": "SEC", "severity": "error", "line": 0,
                      "message": f"必須セクション '{key}' がない（{'/'.join(aliases[:2])} 等の見出し）"})

    reqs = _requirement_lines(body)

    # REQ — 要求が1件もない文書は要求記述ではない
    if not reqs:
        v.append({"code": "REQ", "severity": "error", "line": 0,
                  "message": "要求文が1件もない。FR-001 形式で採番し、EARS で書くこと"})

    # EARS — 各要求文が shall（またはその日本語相当）を持つか
    for ln, line in reqs:
        if not any(re.search(p, line, re.I) for p, _ in EARS_PATTERNS):
            v.append({"code": "EARS", "severity": "error", "line": ln,
                      "message": f"要求文に shall（日本語なら「〜すること」）がない: {line.strip()[:70]}"})
        # trigger が2つ以上 = EARS ruleset 違反（trigger は最大1つ）。粒度が粗いサイン
        hits = sum(1 for p in EARS_TRIGGERS if re.search(p, line, re.I))
        if hits >= 3:
            v.append({"code": "EARS-1T", "severity": "warn", "line": ln,
                      "message": f"トリガー/条件が多すぎる（EARS の ruleset はトリガー最大1つ）。"
                                 f"要求を分割すること: {line.strip()[:60]}"})

    # MUST — §5.2.4「must は要求と誤解されるので避ける」
    for i, line in enumerate(body.split("\n"), 1):
        if MUST_KEYWORD.search(line) and not line.strip().startswith("#"):
            v.append({"code": "MUST", "severity": "warn", "line": i,
                      "message": "`must` は使わない（29148 §5.2.4）。要求は `shall`、"
                                 "選好は `should`、許容は `may`"})
            break   # 1件報告すれば足りる（全行報告するとノイズになる）

    # BAN — §5.2.7 避けるべき語
    for i, line in enumerate(body.split("\n"), 1):
        if line.strip().startswith("#") or not line.strip():
            continue
        for rx, kind, why in BANNED:
            m = re.search(rx, line, re.I)
            if m:
                v.append({"code": "BAN", "severity": "error", "line": i,
                          "message": f"{kind} '{m.group(0)}' — {why}（29148 §5.2.7）"})
                break   # 1行1件（同じ行の複数指摘はノイズ）

    # TBX — §5.2.6 Complete は TBD/TBS/TBR を明示的に禁じる
    for i, line in enumerate(body.split("\n"), 1):
        if TBX.search(line):
            v.append({"code": "TBX", "severity": "error", "line": i,
                      "message": "TBD/TBS/TBR が残っている（29148 §5.2.6 Complete）。"
                                 "決めるか、Open Questions に移すこと"})

    # CLARIFY — 未解決の [NEEDS CLARIFICATION]（Spec Kit 由来。最も重要）
    for i, line in enumerate(body.split("\n"), 1):
        if CLARIFY.search(line):
            v.append({"code": "CLARIFY", "severity": "error", "line": i,
                      "message": "未解決の [NEEDS CLARIFICATION] が残っている。"
                                 "推測で実装させないため、実装前に必ず解消すること"})

    # SC — 成功基準が採番されているか
    if not SC_ID.search(body):
        v.append({"code": "SC", "severity": "warn", "line": 0,
                  "message": "成功基準が SC-001 形式で採番されていない（技術非依存・定量的に）"})

    return v


def cmd_check(a):
    if not os.path.isfile(a.path):
        print(f"req_lint: {a.path} がない。/org-found が REQUIREMENTS.md を書いたか確認すること",
              file=sys.stderr)
        return 2
    try:
        v = check(a.path)
    except OSError as e:
        print(f"req_lint: 読み取れない: {e}", file=sys.stderr)
        return 2
    errors = [x for x in v if x["severity"] == "error"]
    warns = [x for x in v if x["severity"] == "warn"]
    if a.json:
        print(json.dumps({"path": a.path, "passed": not errors,
                          "errors": len(errors), "warnings": len(warns),
                          "violations": v}, ensure_ascii=False, indent=2))
    else:
        print(f"要求記述の検査 — {a.path}")
        print("  （ISO/IEC/IEEE 29148:2018 tailored conformance + EARS、docs/11 §0b）")
        if not v:
            print("\n適合。必須セクション・EARS・禁止語すべて問題なし。")
        for x in v:
            mark = "✗" if x["severity"] == "error" else "▲"
            loc = f"L{x['line']}" if x["line"] else "—"
            print(f"  {mark} [{x['code']}] {loc}: {x['message']}")
        if errors:
            print(f"\nHELD: {len(errors)} 件の違反。要求が曖昧なまま実装に入ると、"
                  f"エージェントは推測で埋める — それが最大の失敗モード。")
        elif warns:
            print(f"\nOK（警告 {len(warns)} 件）。")
    if a.warn_only:
        return 0
    return 10 if errors else 0


def main(argv):
    p = argparse.ArgumentParser(prog="req_lint", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("check")
    q.add_argument("path", nargs="?", default="REQUIREMENTS.md",
                   help="要求文書のパス（既定: REQUIREMENTS.md）")
    q.add_argument("--json", action="store_true")
    q.add_argument("--warn-only", action="store_true",
                   help="違反があっても exit 0（導入初期の drain 用。docs/11 §4e）")
    a = p.parse_args(argv[1:])
    return {"check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
