"""Launch another harness's judge **over MCP** (stdio / JSON-RPC 2.0).

## Why MCP is offered as a choice

Nothing about the judgment changes. **Only the route of the call** moves onto each product's
official interface. The charter (agents/<role>.md), the SPEC and the review_subject_id are all
passed exactly as `verify` assembled them, so the standard applied is identical to the
`same-harness` / `codex exec` case.

What officially exists (measured 2026-08, codex 0.147.0):
  - `codex mcp-server`  … run Codex as an MCP server (stdio)
  - `claude mcp serve`  … run Claude Code as an MCP server (stdio)

The `codex` tool of `codex mcp-server` carries what a judge needs:
  prompt / model / sandbox(read-only) / base-instructions / cwd, returning {threadId, content}.

## What it buys over launching exec directly (it is not speed)

**It does not improve speed.** Measured: a simple response takes 4.7s under codex exec and 4.1s
under MCP, while real gate material takes 102s. The slowness is the model's inference time, not
process start-up. The reasons for MCP are:

  1. **A mistaken argv cannot structurally occur.** exec passes the material as a *positional
     argument*, so material beginning with `-` is mistaken for a flag and the CLI dies instantly
     (measured: passing the charter directly gave exit 2 with
     `unexpected argument '---\\nname: gate'`). MCP passes it as a JSON value, so it cannot
     happen in principle.
  2. **A threadId comes back.** Which judging session it was can be kept in the record.
  3. Assembling the arguments does not depend on a CLI's flag conventions.

## One judgment = one session (deliberately not continued)

Hand a threadId to `codex-reply` and the conversation continues, so a second round needs only the
delta (measured: 72s → 19s). It is still not continued here. **Join the gate and the skeptic in one
session and the skeptic begins its refutation having read the gate's reasoning** — that is not
"looking with different eyes" but "carrying on the gate's train of thought", and it structurally
destroys the decorrelation of lineages docs/03 §3 requires.
The check that reconciles two `review_subject_id`s would also become a formality: within one
process and one context they agree as a matter of course. **A guarantee is never sold for speed.**

Note also that a session lives in the server process's memory, and resuming by threadId from
another process gives `Session not found` (measured). Choosing continuation would presuppose a
resident server — another sense in which one-shot carries no operational debt.

## Structured verdicts — where this is weaker, stated outright

`codex exec` has **the CLI enforce** schema conformance through `--output-schema`. The MCP `codex`
tool has no such argument, so here the schema is requested in the prompt body and **the returned
JSON is checked on this side**. That is the same strength as the `claude -p` path, and one step
weaker than exec.
So the default does not change — MCP is used only where
`judges.harness.<h>.<role>.transport: mcp` is stated explicitly. It never falls silently toward the
weaker side.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


# The official command for running each as an MCP server. A CLI absent here has no MCP route.
_SERVER_ARGV = {
    "codex": ("mcp-server",),
    "claude": ("mcp", "serve"),
}

# The tool name each server exposes, and the argument that carries the judging material.
_TOOL = {
    "codex": ("codex", "prompt"),
    "claude": ("claude", "prompt"),
}


class McpJudgeError(RuntimeError):
    """The MCP route itself did not hold — no judgment was obtained."""


def _rpc(stream_lines, want_id):
    """Pick the response with the wanted id out of the JSON-RPC lines on stdout, skipping
    notifications and log lines."""
    for line in stream_lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue                      # a human-facing log line from the server
        if msg.get("id") == want_id:
            return msg
    return None


def run_mcp_judge(cli, material, schema_text, model=None, effort=None,
                  cwd=None, timeout=1800, base_instructions=None):
    """Run the judge once over MCP and return the body that came back (str).

    It does not judge. **It only carries.** Neither the contents of the verdict nor whether it is
    sound is looked at here at all.
    """
    server = _SERVER_ARGV.get(cli)
    tool = _TOOL.get(cli)
    if not server or not tool:
        raise McpJudgeError(f"no MCP route is defined for {cli!r} (codex | claude)")
    exe = shutil.which(cli)
    if not exe:
        raise McpJudgeError(f"{cli!r} is not on PATH")
    tool_name, prompt_key = tool

    prompt = material
    if schema_text:
        # The MCP codex tool has no --output-schema. The schema is requested in the body and the
        # caller checks what comes back (the docstring already states this is a step weaker than
        # exec).
        prompt = (material + "\n\n## The shape to return\n"
                  "Return **only** JSON matching this schema exactly (no prose before or "
                  "after):\n" + schema_text)

    args = {prompt_key: prompt}
    if cli == "codex":
        # The judge is read-only. The other harness's guardrails are unverified, so fall to the
        # safe side.
        args["sandbox"] = "read-only"
        args["approval-policy"] = "never"      # never let an interactive prompt freeze it
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
        raise McpJudgeError(f"{cli} mcp timed out after {timeout}s") from exc

    reply = _rpc((proc.stdout or "").splitlines(), 2)
    if reply is None:
        raise McpJudgeError(
            f"no judging response came back from {cli} mcp (exit={proc.returncode})\n"
            + ((proc.stderr or "")[-800:]))
    if "error" in reply:
        raise McpJudgeError(f"{cli} mcp returned an error: "
                            + json.dumps(reply['error'], ensure_ascii=False)[:600])

    result = reply.get("result") or {}
    structured = result.get("structuredContent") or {}
    text = structured.get("content")
    if not text:
        # A straightforward fallback for a server without structuredContent.
        blocks = [b.get("text") for b in (result.get("content") or [])
                  if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(b for b in blocks if b)
    if not text or not text.strip():
        raise McpJudgeError(f"{cli} mcp returned nothing. No judgment was obtained.")
    return text, structured.get("threadId")
