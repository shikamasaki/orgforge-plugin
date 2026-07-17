#!/usr/bin/env python3
"""org_session_start — inject a role's doctrine + conventions at session start (both harnesses).

The "load" step of the doctrine organ (docs/07 §load) and the conventions organ (docs/13 §5),
wired as a SessionStart hook so a department's current normative playbook and its org's settled
precedent are in context BEFORE it acts — every cycle, not last quarter's world. Neutral: both
Claude Code and Codex fire a SessionStart hook whose stdout `additionalContext` is prepended to
the model's context. This renders the role's DOCTRINE.md + CONVENTIONS.md (via the organ tools)
and returns them as that context.

Env: ORG_LEDGER_ROOT (state), ORG_DOCTRINE_ROOT (doctrine store dir), ORG_CONVENTIONS_ROOT
     (conventions store dir), ORG_ROLE (which department this session is). All optional; a
     missing store simply contributes nothing (no crash) — a role with no doctrine yet is fine.
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
    if not parts:
        sys.exit(0)   # nothing to inject; clean no-op
    context = ("\n\n---\n\n".join(parts) +
               "\n\n(The above is your current doctrine and your org's settled conventions, "
               "injected by orgforge-plugin. Act on the current world; follow settled "
               "precedent instead of re-deriving it.)")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": context}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
