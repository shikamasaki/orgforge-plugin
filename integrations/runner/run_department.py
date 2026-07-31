#!/usr/bin/env python3
"""run_department — launch ONE department as a headless agent turn, on Claude Code or Codex.

The projection of a role from organization.yaml onto an actual unattended agent process (the
thing docs/08 delegates to the host). It reads the role's neutral settings and builds the
harness-specific headless invocation:

  Claude Code:  claude -p "<task>" --append-system-prompt "<profile>" --allowedTools "<tools>"
                --dangerously-skip-permissions --output-format json
  Codex:        codex exec --model <m> --dangerously-bypass-approvals-and-sandbox
                --dangerously-bypass-hook-trust --cd <workdir> --json "<task>"

Both run ONE turn unattended and return structured output. The org's guardrails still apply,
because the harness's PreToolUse hook (integrations/{claude-code,codex}) invokes the neutral
org_hook.py regardless of which runner launched the process — the runner starts the department;
the hook keeps it inside the decision line. This runner ships NO scheduler (R0): a cron/CI calls
it on the role's cadence, or the tick planner (tools/tick.py) says when.

  run_department.py --harness claude|codex --role R --task "..." [--ledger DIR] [--workdir DIR]
                    [--profile FILE] [--doctrine DIR] [--conventions DIR] [--dry-run]

The role's brain persists across turns as its doctrine: pass --doctrine DIR and the launched
department inherits ORG_DOCTRINE_ROOT, so its SessionStart hook (org_session_start.py) renders
<role>.DOCTRINE.md into context before it acts — the same role, next turn, starts already holding
what it learned. Without --doctrine the department simply starts with no doctrine (a clean no-op).

--dry-run prints the exact command it WOULD run (so you can inspect/verify the projection without
a harness installed — used by the tests). Without --dry-run it execs the harness and streams JSON.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

# neutral tool names -> Claude Code tool ids (the PROJECTION.md harness-map, minimal form).
CLAUDE_TOOLS = {"read": "Read", "write": "Write", "edit": "Edit", "run_tests": "Bash",
                "network": "WebFetch", "web_read": "WebFetch", "grep": "Grep"}


def build_claude(role, task, profile, tools, mode, workdir, plugin_dir):
    cmd = ["claude", "-p", task, "--output-format", "json"]
    if plugin_dir:
        # loads the org plugin so the launched turn fires the PreToolUse + SessionStart hooks —
        # without it, raw `claude -p` runs no hooks and doctrine is never injected.
        cmd += ["--plugin-dir", plugin_dir]
    if profile:
        cmd += ["--append-system-prompt", profile]
    if tools:
        mapped = sorted({CLAUDE_TOOLS.get(t, t) for t in tools})
        cmd += ["--allowedTools", ",".join(mapped)]
    if mode:
        cmd += ["--permission-mode", mode]
    else:
        cmd += ["--dangerously-skip-permissions"]
    return cmd


def build_codex(role, task, profile, model, workdir):
    cmd = [
        "codex",
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
    ]
    if model:
        cmd += ["--model", model]
    if workdir:
        cmd += ["--cd", workdir, "--skip-git-repo-check"]
    # Codex reads the profile from AGENTS.md in --cd; --append-system-prompt has no exec flag,
    # so the runner writes the profile into <workdir>/AGENTS.md before launch (done by caller).
    cmd += [task]
    return cmd


def main(argv):
    p = argparse.ArgumentParser(prog="run_department", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--harness", choices=["claude", "codex"], required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--ledger")
    p.add_argument("--doctrine")          # doctrine store dir -> ORG_DOCTRINE_ROOT (the role's brain)
    p.add_argument("--conventions")       # conventions store dir -> ORG_CONVENTIONS_ROOT
    p.add_argument("--workdir")
    p.add_argument("--profile")           # a file with the role's projected system prompt
    p.add_argument("--tools")             # comma-separated neutral tool names
    p.add_argument("--model")
    p.add_argument("--permission-mode", dest="mode")
    p.add_argument("--plugin-dir", dest="plugin_dir",
                   help="Claude Code plugin dir to load so the launched turn fires the org hooks "
                        "(PreToolUse guardrail + SessionStart doctrine injection). Defaults to the "
                        "bundled integrations/claude-code when that layout is present.")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv[1:])

    profile_text = ""
    if a.profile and os.path.exists(a.profile):
        with open(a.profile, encoding="utf-8") as f:
            profile_text = f.read()
    tools = [t.strip() for t in (a.tools or "").split(",") if t.strip()]

    if a.harness == "claude":
        # default to the bundled plugin dir if it exists next to this runner's repo
        plugin_dir = a.plugin_dir
        if plugin_dir is None:
            cand = os.path.join(REPO, "integrations", "claude-code")
            if os.path.isdir(os.path.join(cand, ".claude-plugin")):
                plugin_dir = cand
        cmd = build_claude(a.role, a.task, profile_text, tools, a.mode, a.workdir, plugin_dir)
    else:
        cmd = build_codex(a.role, a.task, profile_text, a.model, a.workdir)

    # the guardrail env every launched department inherits — the hook reads these
    env = dict(os.environ)
    if a.ledger:
        env["ORG_LEDGER_ROOT"] = a.ledger
    if a.doctrine:
        env["ORG_DOCTRINE_ROOT"] = a.doctrine
    if a.conventions:
        env["ORG_CONVENTIONS_ROOT"] = a.conventions
    env["ORG_ROLE"] = a.role

    if a.dry_run:
        print("# projected headless invocation for role=%s on harness=%s" % (a.role, a.harness))
        print(" ".join(shlex.quote(c) for c in cmd))
        print("# env: ORG_LEDGER_ROOT=%s ORG_DOCTRINE_ROOT=%s ORG_ROLE=%s"
              % (a.ledger or "(unset)", a.doctrine or "(unset)", a.role))
        return 0

    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode
    except FileNotFoundError:
        print(f"run_department: harness '{a.harness}' CLI not found on PATH — install it or use "
              f"--dry-run to inspect the projected command", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main(sys.argv))
