#!/usr/bin/env python3
"""org_session_start — inject a role's doctrine + conventions at session start (both harnesses).

The "load" step of the doctrine organ (docs/07 §load) and the conventions organ (docs/13 §5),
wired as a SessionStart hook so a department's current normative playbook and its org's settled
precedent are in context BEFORE it acts — every cycle, not last quarter's world. Neutral: both
Claude Code and Codex fire a SessionStart hook whose stdout `additionalContext` is prepended to
the model's context. This renders the role's DOCTRINE.md + CONVENTIONS.md (via the organ tools)
and returns them as that context.

It ALSO injects the role's WORK IN PROGRESS — candidates it started but did not finish, each with
its latest progress checkpoint (how far / next step / blocker). This is what makes "just continue"
work after a context wipe (/clear) or a fresh session: the half-done work lives in the LEDGER, not in
the lost conversation, so the role resumes exactly where it stopped without the human re-explaining
(docs/01 R−1: the org acts only on what is written). The recovery is automatic — no /org-resume needed.

Env: ORG_LEDGER_ROOT (state — also the source of work-in-progress), ORG_DOCTRINE_ROOT (doctrine store
     dir), ORG_CONVENTIONS_ROOT (conventions store dir), ORG_ROLE (which department this session is).
     All optional; a missing store simply contributes nothing (no crash).
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# single source, copied into the plugin's scripts/ (build.sh); prefer a sibling tools/ when
# bundled, else the repo layout. See org_hook.py for the same resolution.
_BUNDLED = os.path.join(HERE, "..", "tools")
_REPO = os.path.join(HERE, "..", "..", "tools")
TOOLS = os.environ.get("ORG_TOOLS_DIR", _BUNDLED if os.path.isdir(_BUNDLED) else _REPO)
ROLE = os.environ.get("ORG_ROLE", "")
DOCTRINE_ROOT = os.environ.get("ORG_DOCTRINE_ROOT", "")
CONV_ROOT = os.environ.get("ORG_CONVENTIONS_ROOT", "")
LEDGER_ROOT = os.environ.get("ORG_LEDGER_ROOT", "")


def _work_in_progress():
    """Read the role's started-but-unfinished candidates + latest progress from the ledger. Returns a
    human-readable resume block, or "" if there is nothing in flight (a clean role = clean no-op)."""
    if not (LEDGER_ROOT and ROLE):
        return ""
    try:
        p = subprocess.run([sys.executable, os.path.join(TOOLS, "ledger.py"),
                            "view", LEDGER_ROOT, "work_in_progress"],
                           capture_output=True, text=True, timeout=20)
        data = json.loads(p.stdout or "{}")
    except Exception:
        return ""
    mine = [w for w in data.get("in_progress", []) if w.get("role") == ROLE]
    if not mine:
        return ""
    lines = ["## Work in progress (resume from here — recovered from the ledger, not the lost session)"]
    for w in mine:
        pr = w.get("progress") or {}
        frac = pr.get("fraction")
        head = f"- **{w['candidate_id']}**" + (f" — {round(float(frac) * 100)}%" if frac is not None else "")
        if pr.get("phase"):
            head += f" ({pr['phase']})"
        lines.append(head)
        if pr.get("done_so_far"):
            lines.append(f"    - done so far: {pr['done_so_far']}")
        if pr.get("next_step"):
            lines.append(f"    - **next step: {pr['next_step']}**")
        if pr.get("blocked_by"):
            lines.append(f"    - ⚠ blocked by: {pr['blocked_by']}")
        if not pr:
            lines.append("    - started, no progress checkpoint yet — verify state before continuing")
    return "\n".join(lines)


def _render(tool, root, subcmd_args, out_path):
    if not root:
        return ""
    try:
        subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + subcmd_args,
                       capture_output=True, text=True, timeout=20)
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return ""


def main():
    # read (and ignore) the event; SessionStart carries no decision we need
    try:
        sys.stdin.read()
    except Exception:
        pass
    parts = []
    if ROLE and DOCTRINE_ROOT:
        out = os.path.join(DOCTRINE_ROOT, f"{ROLE}.DOCTRINE.md")
        doc = _render("doctrine.py", DOCTRINE_ROOT,
                      ["render", DOCTRINE_ROOT, ROLE, "--out", out], out)
        if doc.strip():
            parts.append(doc)
    if ROLE and CONV_ROOT:
        out = os.path.join(CONV_ROOT, f"{ROLE}.CONVENTIONS.md")
        conv = _render("conventions.py", CONV_ROOT,
                       ["render", CONV_ROOT, "--role", ROLE, "--out", out], out)
        if conv.strip():
            parts.append(conv)
    # work in progress — so "just continue" lands on the freshest, most actionable block.
    wip = _work_in_progress()
    if wip.strip():
        parts.append(wip)
    # start-the-metabolism nudge — only when the org is configured (ledger + role). A hook CANNOT call
    # CronCreate itself (SessionStart hooks cannot invoke tools), so this is an INSTRUCTION the model
    # acts on: it asks you to run /org-start, which registers the cycles. Injected LAST so it is the most
    # salient line at session start. If the model does not act, the user runs /org-start manually — the
    # explicit, guaranteed path.
    if LEDGER_ROOT and ROLE:
        parts.append(
            "## Start the org (do this first)\n"
            f"This is an orgforge session (role: {ROLE}). To bring the org to its running state, "
            "**run the `/org-start` command now** — it registers this session's recurring cycles "
            "(`/org-tick`, `/org-work`, `/org-discover`) via CronCreate so the org drives itself while "
            "this session is open. `/org-start` is idempotent: if the cycles are already scheduled it "
            "does nothing, so it is safe to run. (A hook cannot register them for you; this is why the "
            "step is a command.)")
    if not parts:
        sys.exit(0)   # nothing to inject; clean no-op
    context = ("\n\n---\n\n".join(parts) +
               "\n\n(Injected by orgforge-plugin: your current doctrine, settled conventions, any work "
               "in progress, and — if this is an org session — the start step. Act on the current world; "
               "follow settled precedent; resume in-progress work from its next step; and if asked to "
               "start the org, run /org-start so the metabolism begins.)")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": context}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
