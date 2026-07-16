#!/usr/bin/env python3
"""org_hook — the ONE neutral PreToolUse adapter both Claude Code and Codex call.

This is the load-bearing bridge that makes the org's guardrails actually BLOCK inside a real
agent's tool loop, on either harness, without either harness knowing anything org-specific. It
is the projection layer of PROJECTION.md, made concrete: the neutral organ tools stay neutral
(they read the ledger and exit 0=allow / 10=escalate); THIS adapter maps an organ's verdict onto
the pre-tool-hook contract that Claude Code and Codex SHARE — read a hook-event JSON on stdin,
and either allow (exit 0) or BLOCK (exit 2 + reason on stderr, or a deny-JSON on stdout).

Both harnesses converge on the same PreToolUse contract (verified 2026-07 against code.claude.com
/docs/en/hooks and learn.chatgpt.com/docs/hooks):
  - stdin: JSON with at least {hook_event_name, tool_name, tool_input, cwd, session_id}
  - to BLOCK: exit 2 with the reason on stderr, OR print
      {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                              "permissionDecision": "deny", "permissionDecisionReason": "..."}}
    and exit 0.
  - to ALLOW: exit 0 with no decision.
So one script serves both. The only per-harness difference (Claude uses --allowedTools, Codex
uses sandbox+MCP) is about tool *availability*, not the *block* — and the block is what a
guardrail is. We standardize the guardrail on exit-2/deny-JSON (NOT the organ's exit-10, which
stays the neutral internal convention the tools use among themselves).

WHY a hook and not an allowlist (the OSS survey's lesson, e.g. rulebricks/claude-code-guardrails):
an allowlist gates tool *identity* ("may you run Bash?"); the org's guardrails gate tool *effect
in context* ("does THIS Bash command, given the ledger's committed exposure this window, cross the
blast-radius cap?"). Only a hook that reads the event AND the ledger can decide that. The hook is
the thin policy-decision-point client; the organ tool is the policy engine; the ledger is state.

Mapping (tool_name + tool_input) -> which organ guards it, declared in RULES below. Each rule
names an organ command and how to derive its args from the tool_input. A rule that ESCALATES
(the organ exits 10) becomes a BLOCK with the organ's stderr as the reason — "the org's decision
line reached into the harness and held this action for the human" (docs/11 §0). Fail-OPEN is never
the default: a rule whose organ errors blocks with a clear message (fail-safe, docs/06 §2.4),
unless ORG_HOOK_FAIL_OPEN=1 is set for a permissive dev mode.

Usage (wired identically in Claude settings.json and Codex hooks.json):
  {"matcher": "Bash|Write|Edit", "type": "command",
   "command": "python3 <repo>/integrations/common/org_hook.py"}
Environment:
  ORG_LEDGER_ROOT   directory holding ledger.jsonl (required; the org's state)
  ORG_TOOLS_DIR     directory holding the organ *.py (default: <this>/../../tools)
  ORG_HOOK_FAIL_OPEN=1  allow on organ error instead of blocking (dev only)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# resolve the organ tools. This file is the single source; it is COPIED into the plugin's
# scripts/ (build.sh), where a sibling tools/ exists. So: explicit override wins; else a sibling
# tools/ (bundled-in-plugin layout: scripts/ + tools/ share a parent); else the repo layout
# (integrations/common/ -> ../../tools).
_BUNDLED = os.path.join(HERE, "..", "tools")
_REPO = os.path.join(HERE, "..", "..", "tools")
TOOLS_DIR = os.environ.get("ORG_TOOLS_DIR",
                           _BUNDLED if os.path.isdir(_BUNDLED) else _REPO)
LEDGER_ROOT = os.environ.get("ORG_LEDGER_ROOT", "")
FAIL_OPEN = os.environ.get("ORG_HOOK_FAIL_OPEN") == "1"


def _deny(reason):
    """Emit the shared deny contract and exit 2 (blocks on BOTH harnesses)."""
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "deny",
                                  "permissionDecisionReason": reason}}
    print(json.dumps(out))
    print(reason, file=sys.stderr)
    sys.exit(2)


def _allow():
    sys.exit(0)


def _append_emitted(output):
    """Close the emit->append loop (external review BLOCKER, 2026-07). An organ COMPUTES an event
    and prints `LEDGER-EVENT {json}`; nothing appended it, so the aggregate cap never accumulated
    (committed_so_far was always 0 -> the blast-radius cap silently degraded to a memoryless
    per-action check). Here the host (this hook) appends the emitted event via `ledger.py append`,
    with a --ts so window filters work. This is the R0-correct split: the organ stays a pure
    function that emits; the host writes. Best-effort — a failed append must not crash the hook."""
    for line in output.splitlines():
        if not line.startswith("LEDGER-EVENT "):
            continue
        try:
            ev = json.loads(line[len("LEDGER-EVENT "):])
            cls, payload = ev["class"], ev["payload"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        ts = os.environ.get("ORG_NOW_TS", "1970-01-01T00:00:00Z")
        try:
            subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "ledger.py"), "append",
                            LEDGER_ROOT, "--actor", "system:org_hook", "--class", cls,
                            "--payload", json.dumps(payload, ensure_ascii=False), "--ts", ts],
                           capture_output=True, text=True, timeout=30)
        except Exception:
            pass   # a failed write-back must never turn an allow into a crash


def _run_organ(argv):
    """Run an organ command; return (exit_code, combined_output). Never raises."""
    try:
        p = subprocess.run([sys.executable, os.path.join(TOOLS_DIR, argv[0])] + argv[1:],
                           capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout + p.stderr)
    except Exception as e:  # organ missing / crashed / timed out
        return 99, f"organ {argv[0]} failed to run: {e}"


# ── RULES: (predicate on the tool call) -> organ command to consult ──────────────────────────
# Each rule: match(tool_name, tool_input) -> None (skip) or a list argv for an organ command.
# The organ is consulted with the CURRENT ledger; exit 10 (or its block message) => BLOCK.
# These are examples wired to the shipped organs; an adopter tunes the caps/dimensions to its org.

def _asset_dimension(tool_name, ti):
    """Classify a tool call into a real-asset exposure dimension. Returns None ONLY for calls that
    demonstrably touch no external asset (a bare read). This is the BLAST-RADIUS-CAP entry point.

    Fail-SAFE classification (external review, 2026-07): the earlier version returned None for any
    command outside a keyword list, so `find -delete` / `dd` / `>file` / `… | bash` slipped past
    the cap entirely. Now an UNRECOGNISED shell command falls into a catch-all `shell_effect`
    dimension — unknown effect is consulted against the cap, not waved through. An adopter narrows
    this to its real asset taxonomy; the default errs toward gating, not skipping."""
    # tool_input may be a dict OR a raw string (some harnesses pass the command as a string).
    if isinstance(ti, dict):
        cmd = ti.get("command") or ti.get("cmd") or ""
    elif isinstance(ti, str):
        cmd = ti
    else:
        cmd = ""
    if tool_name in ("Write", "Edit", "MultiEdit", "ApplyPatch"):
        return ("file_writes", 1)            # writing a file is an asset effect
    if tool_name not in ("Bash", "Shell", "Terminal"):
        return None                          # non-shell, non-write tools touch no asset here
    if not cmd.strip():
        return ("shell_effect", 1)           # an opaque shell call — gate it, don't guess it safe
    # named high-signal dimensions (kept so their caps can be tuned independently)
    if any(k in cmd for k in ("curl", "wget", "http")) and any(
            k in cmd for k in ("POST", "PUT", "DELETE", "-d ", "--data")):
        return ("external_writes", 1)
    if any(k in cmd for k in ("aws ", "gcloud ", "terraform apply", "kubectl apply")):
        return ("infra_changes", 1)
    if any(k in cmd for k in ("rm -rf", "rm -r", "git push", "-delete", "dd ", "truncate",
                              "DROP ", "DELETE ", "mkfs", " > /", "| bash", "|bash", "| sh")):
        return ("destructive_ops", 1)
    # a read-only shell command touches nothing — the only safe None. Everything else is gated.
    _READONLY = ("ls", "cat", "grep", "find", "echo", "pwd", "head", "tail", "wc", "git status",
                 "git log", "git diff", "git show", "which", "file", "stat", "sort", "uniq")
    first = cmd.strip().split()[0] if cmd.strip() else ""
    if first in _READONLY and not any(w in cmd for w in ("-delete", "-exec", ">", ">>", "|")):
        return None
    return ("shell_effect", 1)               # unknown effect -> consult the cap (fail-safe)


def rule_blast_radius(tool_name, ti):
    dim = _asset_dimension(tool_name, ti)
    if not dim:
        return None
    dimension, delta = dim
    cap = os.environ.get(f"ORG_CAP_{dimension.upper()}", "3")
    return ["guardrails.py", "cap", LEDGER_ROOT, "--dimension", dimension,
            "--delta", str(delta), "--cap", cap, "--actor", "harness-agent",
            "--window-since", os.environ.get("ORG_WINDOW_SINCE", "1970-01-01")]


# Only the blast-radius cap is wired into the tool loop today. reconcile.py `mandate` and the
# doctrine organ are real, tested code but are NOT PreToolUse rules — mandate fires on a contested
# decision (not every tool call) and doctrine loads via the SessionStart hook, not here. Wiring
# them as tool-loop rules is future work; the honest surface is one enforced rule + one injected
# organ (doctrine at session start), not three enforced here (external review, 2026-07).
RULES = [rule_blast_radius]


def main():
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        event = {}
    # only gate PreToolUse; anything else passes (the hook may be wired to several events)
    if event.get("hook_event_name") not in (None, "PreToolUse"):
        _allow()
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    if not LEDGER_ROOT:
        # no ledger configured => the org has no state to judge against. Fail-safe: allow, but
        # say so loudly on stderr so a misconfiguration is visible, not silent.
        print("org_hook: ORG_LEDGER_ROOT unset — no org state to gate against; allowing "
              "(set it to enable guardrails)", file=sys.stderr)
        _allow()

    for rule in RULES:
        argv = rule(tool_name, tool_input)
        if not argv:
            continue
        code, output = _run_organ(argv)
        if code == 10:
            _deny(f"org guardrail HELD this {tool_name} call: {output.strip()[:400]}")
        if code == 0:
            # allow — but record the allowed exposure so the NEXT call's aggregate check sees it
            # (closes the emit->append loop; without this the cap never accumulates). Only the
            # allow decision is written; a held call was already denied above and never happens.
            _append_emitted(output)
            continue        # keep checking other rules
        # ANY other code (2 = interpreter couldn't run the script, 99 = our sentinel, a crash,
        # a timeout) means the guardrail did NOT return a clean allow. Fail-SAFE: block, never
        # let an unevaluable guardrail become a silent allow (docs/06 §2.4). Dev may opt out.
        if FAIL_OPEN:
            print(f"org_hook: organ returned {code}: {output} (fail-open) — allowing",
                  file=sys.stderr)
            continue
        _deny(f"org guardrail could not be evaluated (exit {code}) — fail-safe block: "
              f"{output.strip()[:300]}")
    _allow()


if __name__ == "__main__":
    main()
