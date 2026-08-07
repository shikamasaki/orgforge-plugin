"""別ハーネスの judge を **MCP 経由** で起動する（stdio / JSON-RPC 2.0）。

## なぜ MCP を選べるようにするか

判定の中身は一切変えない。**呼び出しの経路だけ**を各製品の公式インターフェースに寄せる。
憲章（agents/<role>.md）も SPEC も review_subject_id も、`verify` が組み立てたものを
そのまま渡すので、判定基準は `same-harness` / `codex exec` の場合と同一である。

公式に存在するもの（実測 2026-08 / codex 0.147.0）:
  - `codex mcp-server`  … Codex を MCP サーバとして起動（stdio）
  - `claude mcp serve`  … Claude Code を MCP サーバとして起動（stdio）

`codex mcp-server` の `codex` ツールは judge に必要なものを揃えている:
  prompt / model / sandbox(read-only) / base-instructions / cwd、返りは {threadId, content}。

## exec 直接起動に対する利点（速度ではない）

**速度は改善しない。** 実測: 単純応答 codex exec 4.7s / MCP 4.1s、実 Gate 材料は 102s。
遅さの実体は LLM の推論時間であって、プロセス起動ではなかった。MCP を採る理由は:

  1. **argv 誤認が構造的に起きない。** exec は material を *位置引数* で渡すので、材料が
     `-` で始まると CLI がフラグと誤認して即死する（実測: 憲章を直接渡すと exit 2 で
     `unexpected argument '---\\nname: gate'`）。MCP は JSON の値として渡すので原理的に無い。
  2. **threadId が返る。** どの判定セッションだったかを記録に残せる。
  3. 引数の組み立てが CLI のフラグ体系に依存しない。

## ここは **1判定 = 1セッション** にする（意図的に継続しない）

`codex-reply` に threadId を渡せば会話は続き、2周目は差分だけで済む（実測 72s→19s）。
それでもここでは継続しない。**gate と skeptic を1セッションで繋ぐと、skeptic が gate の
思考過程を読んだ状態で反証を始める** — それは「別の目で見る」ではなく「gate の続きを
考える」であって、docs/03 §3 が要求する血統の非相関化が構造的に壊れる。
`review_subject_id` を2件突き合わせる検査も、同一プロセス・同一文脈なら一致して当然になり
形骸化する。**速度のために保証を売らない。**

なおセッションはサーバプロセスのメモリ内にあり、別プロセスから threadId で再開すると
`Session not found` になる（実測）。継続を選ぶならサーバ常駐が前提になる、という意味でも
単発のほうが運用の負債が無い。

## 構造化 verdict の扱い（弱くなる点を明示する）

`codex exec` は `--output-schema` でスキーマ準拠を **CLI 側が強制** する。MCP の `codex`
ツールにはその引数が無いので、ここではスキーマを本文で要求し、**返ってきた JSON を
こちら側で検査する**。`claude -p` 経路と同じ強度であり、exec より一段弱い。
だから既定は変えない — MCP は `judges.harness.<h>.<role>.transport: mcp` を明示した
ときだけ使う。弱くなる側へ黙って倒れないようにする。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


# MCP サーバとして起動する公式コマンド。ここに無い CLI は MCP 経路を持たない。
_SERVER_ARGV = {
    "codex": ("mcp-server",),
    "claude": ("mcp", "serve"),
}

# サーバが公開するツール名と、判定本文を載せる引数名。
_TOOL = {
    "codex": ("codex", "prompt"),
    "claude": ("claude", "prompt"),
}


class McpJudgeError(RuntimeError):
    """MCP 経路そのものが成立しなかった（判定が得られなかった）。"""


def _rpc(stream_lines, want_id):
    """stdout の JSON-RPC 行から目的の id の応答を拾う。通知や log 行は読み飛ばす。"""
    for line in stream_lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue                      # サーバの人間向けログ行
        if msg.get("id") == want_id:
            return msg
    return None


def run_mcp_judge(cli, material, schema_text, model=None, effort=None,
                  cwd=None, timeout=1800, base_instructions=None):
    """MCP 経由で judge を1回走らせ、返ってきた本文（str）を返す。

    判定はしない。**運ぶだけ。** verdict の中身も、それが妥当かも、ここでは一切見ない。
    """
    server = _SERVER_ARGV.get(cli)
    tool = _TOOL.get(cli)
    if not server or not tool:
        raise McpJudgeError(f"{cli!r} に MCP 経路は定義されていない（codex | claude）")
    exe = shutil.which(cli)
    if not exe:
        raise McpJudgeError(f"{cli!r} が PATH に無い")
    tool_name, prompt_key = tool

    prompt = material
    if schema_text:
        # MCP の codex ツールは --output-schema を持たない。スキーマは本文で要求し、
        # 返りは呼び出し側が検査する（exec より一段弱いことは docstring に明示済み）。
        prompt = (material + "\n\n## 返す形\n"
                  "次のスキーマに厳密に一致する JSON **のみ** を返すこと"
                  "（前後に散文を付けない）:\n" + schema_text)

    args = {prompt_key: prompt}
    if cli == "codex":
        # judge は read-only。別ハーネスのガードレールは未検証なので安全側に倒す。
        args["sandbox"] = "read-only"
        args["approval-policy"] = "never"      # 対話プロンプトで固まらせない
        if model:
            args["model"] = str(model)
        if effort:
            args["config"] = {"model_reasoning_effort": str(effort)}
        if base_instructions:
            args["base-instructions"] = base_instructions
        if cwd:
            args["cwd"] = str(cwd)

    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "orgforge-judge", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": tool_name, "arguments": args}},
    ]
    payload = "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs) + "\n"

    try:
        proc = subprocess.run([exe, *server], input=payload, capture_output=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              cwd=cwd or None)
    except subprocess.TimeoutExpired as exc:
        raise McpJudgeError(f"{cli} mcp が {timeout}s でタイムアウトした") from exc

    reply = _rpc((proc.stdout or "").splitlines(), 2)
    if reply is None:
        raise McpJudgeError(
            f"{cli} mcp から判定応答が返らなかった (exit={proc.returncode})\n"
            + ((proc.stderr or "")[-800:]))
    if "error" in reply:
        raise McpJudgeError(f"{cli} mcp がエラーを返した: "
                            + json.dumps(reply['error'], ensure_ascii=False)[:600])

    result = reply.get("result") or {}
    structured = result.get("structuredContent") or {}
    text = structured.get("content")
    if not text:
        # structuredContent が無いサーバのための素直な fallback。
        blocks = [b.get("text") for b in (result.get("content") or [])
                  if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(b for b in blocks if b)
    if not text or not text.strip():
        raise McpJudgeError(f"{cli} mcp が空を返した。判定は得られていない。")
    return text, structured.get("threadId")
