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
    """Classify a tool call into a blast-radius exposure dimension, PRICED BY REVERSIBILITY.

    A blast-radius cap must bound *irreversible effect*, not *activity*. The earlier version
    charged every file write 1 against a single low cap, so a normal build (hundreds of
    reversible file creations) exhausted a budget meant for destruction — the guardrail stopped
    construction, not runaways. A three-perspective review (security / rate-limiting / control
    theory) converged on the fix: meter irreversibility, not tool-call count.

    Dimensions returned (each has its own cap; the dangerous ones are low, the safe ones high):
      - None            : reversible/benign — NOT blast radius, not metered (new-file create,
                          read-only shell). A 300-file build lives here and proceeds.
      - "file_mutations": overwriting an EXISTING file (reversible under VCS, but real) — high cap.
      - "external_writes"/"infra_changes"/"destructive_ops": irreversible / external side effects
                          — LOW cap. This is the actual blast radius.
      - "shell_effect"  : genuinely unclassifiable shell — fail-safe metered (unknown=dangerous).

    CREATE-vs-MUTATE is decided by a filesystem stat (does the path already exist?), exactly as
    the reviewers recommended — the single check that unblocks a legit build while keeping
    overwrite metered. Fail-safe: unknown shell is charged, ambiguous destroys are max-cost."""
    if isinstance(ti, dict):
        cmd = ti.get("command") or ti.get("cmd") or ""
        path = ti.get("file_path") or ti.get("path") or ""
    elif isinstance(ti, str):
        cmd, path = ti, ""
    else:
        cmd, path = "", ""

    # ── file-editing tools: CREATE (new path) is reversible & free; MUTATE (existing) is metered.
    if tool_name in ("Write", "Edit", "MultiEdit", "ApplyPatch"):
        # Edit/MultiEdit/ApplyPatch always target an existing file (a mutation). A Write to a
        # path that does not yet exist is a reversible creation — not blast radius.
        if tool_name == "Write" and path and not os.path.exists(path):
            return None                      # new file — reversible, cheap; do not meter
        if tool_name == "Write" and not path:
            return ("file_mutations", 1)     # can't tell → fail-safe meter
        return ("file_mutations", 1)         # overwrote/edited an existing file
    if tool_name not in ("Bash", "Shell", "Terminal"):
        return None                          # non-shell, non-write tools touch no asset here
    if not cmd.strip():
        return ("shell_effect", 1)           # an opaque shell call — gate it, don't guess it safe

    # ── irreversible / external side effects — the real blast radius (LOW cap) ────────────
    if any(k in cmd for k in ("curl", "wget", "http")) and any(
            k in cmd for k in ("POST", "PUT", "DELETE", "-d ", "--data")):
        return ("external_writes", 1)
    if any(k in cmd for k in ("aws ", "gcloud ", "terraform apply", "kubectl apply")):
        return ("infra_changes", 1)
    if any(k in cmd for k in ("rm -rf", "rm -r", "rm ", "git push", "-delete", "dd ", "truncate",
                              "DROP ", "DELETE ", "TRUNCATE", "mkfs", " > /", "| bash", "|bash",
                              "| sh", "shutil.rmtree", "git reset --hard", "--force", "-f ")):
        # scope-weight the catastrophic recursive/glob deletes so ONE can trip the cap alone
        heavy = any(k in cmd for k in ("rm -rf", "-delete", "DROP ", "TRUNCATE", "mkfs",
                                       "shutil.rmtree", "/*", "reset --hard"))
        return ("destructive_ops", 3 if heavy else 1)

    # ── reversible / benign shell — NOT blast radius, not metered ────────────────────────
    # build/test/package tooling and read-only inspection create or read within the workspace;
    # they are reversible and must not burn the destruction budget (reviewers: unknown≠dangerous,
    # but common-safe IS safe). Interpreters (bash -c/python -c/make) stay opaque -> metered below.
    _BENIGN = ("ls", "cat", "grep", "rg", "echo", "pwd", "head", "tail", "wc", "which", "file",
               "stat", "sort", "uniq", "mkdir", "touch", "cp", "node", "npm", "npx", "pnpm",
               "yarn", "pip", "python", "python3", "pytest", "go", "cargo", "tsc", "vite",
               "git status", "git log", "git diff", "git show", "git add", "git commit",
               "git branch", "git checkout", "git init")
    stripped = cmd.strip()
    first = stripped.split()[0] if stripped else ""
    starts_benign = first in _BENIGN or any(stripped.startswith(b + " ") for b in _BENIGN)
    # a benign head still gets metered if it hides a redirect-overwrite or a pipe-to-shell
    if starts_benign and not any(w in cmd for w in ("-delete", "-exec", " > /", ">>/", "| bash",
                                                    "|bash", "| sh", "-c ")):
        return None
    return ("shell_effect", 1)               # genuinely unknown effect -> fail-safe meter


# Per-dimension default caps, priced by reversibility (a three-perspective review's conclusion:
# meter irreversibility, not activity). The irreversible/external dimensions are LOW — that is
# the real blast radius. Reversible-but-real mutations get a HIGH cap so a normal build proceeds.
# Reversible creations and reads return None from the classifier and are never metered at all.
# Every value is overridable per-adopter via ORG_CAP_<DIMENSION>.
_DEFAULT_CAPS = {
    "destructive_ops": "3",    # rm/DROP/force — irreversible; low, scope-weighted
    "external_writes": "3",    # outbound POST/PUT/DELETE — irreversible side effect
    "infra_changes":   "3",    # apply to real infra — irreversible
    "shell_effect":    "8",    # unclassifiable shell — metered fail-safe, but not build-killing
    "file_mutations":  "200",  # overwriting existing files — reversible under VCS; high ceiling
}

def rule_blast_radius(tool_name, ti):
    dim = _asset_dimension(tool_name, ti)
    if not dim:
        return None
    dimension, delta = dim
    cap = os.environ.get(f"ORG_CAP_{dimension.upper()}", _DEFAULT_CAPS.get(dimension, "3"))
    return ["guardrails.py", "cap", LEDGER_ROOT, "--dimension", dimension,
            "--delta", str(delta), "--cap", cap, "--actor", "harness-agent",
            "--window-since", os.environ.get("ORG_WINDOW_SINCE", "1970-01-01")]


# ── Agent spawn discipline (docs/07 §2.1.1) ──────────────────────────────────
# A manager that spawns a subordinate must either hand it a SEAM CONTRACT (so integrating
# siblings don't drift) or declare the child INDEPENDENT (a non-integrating fan-out — e.g. a
# parallel enumeration whose outputs are never merged). This turns the profile's "please use
# handoff.py" from advice into structure: without one of the two, the spawn is blocked. Not an
# organ/ledger rule — it's a pure shape check on the spawn prompt, so it returns a verdict
# directly (see main()'s SPAWN_GATE branch) rather than an organ argv.
_SEAM_MARKERS = ("outputs you must produce", "boundary contract", "inputs you receive",
                 "seam contract", "## your slice")
_INDEP_MARKERS = ("independent:", "non-integrating", "no seam", "outputs are not merged",
                  "independent fan-out")

def spawn_needs_seam_or_independence(tool_name, ti):
    """Return None to allow, or a deny-reason string to block. Gate the Agent/Task spawn tool."""
    if tool_name not in ("Agent", "Task"):
        return None
    if os.environ.get("ORG_REQUIRE_SEAM", "") not in ("1", "true", "yes"):
        return None                      # opt-in: only enforced when the org turns it on
    prompt = (ti.get("prompt") or "").lower()
    if any(m in prompt for m in _SEAM_MARKERS):
        return None                      # carries a seam contract — integrating child, fine
    if any(m in prompt for m in _INDEP_MARKERS):
        return None                      # explicitly an independent, non-integrating child
    return ("this Agent spawn carries neither a seam contract (build it with tools/handoff.py: "
            "slice + inputs/outputs the child integrates to) nor an explicit independence "
            "declaration (start the child prompt with 'INDEPENDENT: ...' if its output is never "
            "merged with a sibling's). Recursive splits drift without an owned seam — docs/07 §2.1.1.")


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

    # Agent-spawn discipline is a pure shape check on the spawn prompt — it needs no ledger, so
    # it runs before the ledger gate. Blocks a manager that spawns a child with neither a seam
    # contract nor an independence declaration (docs/07 §2.1.1); opt-in via ORG_REQUIRE_SEAM.
    seam_reason = spawn_needs_seam_or_independence(tool_name, tool_input)
    if seam_reason:
        _deny(f"org guardrail HELD this {tool_name} spawn: {seam_reason}")

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
