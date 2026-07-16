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
TOOLS_DIR = os.environ.get("ORG_TOOLS_DIR", os.path.join(HERE, "..", "..", "tools"))
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
    """Classify a tool call into a real-asset exposure dimension, or None if it touches no asset.
    This is the BLAST-RADIUS-CAP entry point — the aggregate the approval queue can't see."""
    cmd = (ti.get("command") or "") if isinstance(ti, dict) else ""
    # crude, tunable heuristics — an adopter replaces these with its real asset taxonomy
    if tool_name == "Bash":
        if any(k in cmd for k in ("curl", "wget", "http")) and any(
                k in cmd for k in ("POST", "PUT", "DELETE", "-d ", "--data")):
            return ("external_writes", 1)
        if any(k in cmd for k in ("aws ", "gcloud ", "terraform apply", "kubectl apply")):
            return ("infra_changes", 1)
        if "rm -rf" in cmd or "git push" in cmd:
            return ("destructive_ops", 1)
    return None


def rule_blast_radius(tool_name, ti):
    dim = _asset_dimension(tool_name, ti)
    if not dim:
        return None
    dimension, delta = dim
    cap = os.environ.get(f"ORG_CAP_{dimension.upper()}", "3")
    return ["guardrails.py", "cap", LEDGER_ROOT, "--dimension", dimension,
            "--delta", str(delta), "--cap", cap, "--actor", "harness-agent",
            "--window-since", os.environ.get("ORG_WINDOW_SINCE", "1970-01-01")]


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
            continue        # this organ allows; keep checking other rules
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
