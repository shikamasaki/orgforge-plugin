#!/usr/bin/env python3
"""run_department — launch ONE department as a headless agent turn, on Claude Code or Codex.

The projection of a role from organization.yaml onto an actual unattended agent process (the
thing docs/09 delegates to the host). It reads the role's neutral settings and builds the
harness-specific headless invocation:

  Claude Code:  claude -p "<task>" --append-system-prompt "<profile>" --allowedTools "<tools>"
                --permission-mode <mode> --output-format json
  Codex:        codex exec --model <m> --sandbox <s> --cd <workdir> --json "<task>"

Both run ONE turn unattended and return structured output. The org's guardrails still apply,
because the harness's PreToolUse hook (integrations/{claude-code,codex}) invokes the neutral
org_hook.py regardless of which runner launched the process — the runner starts the department;
the hook keeps it inside the decision line. This runner ships NO scheduler (R0): a cron/CI calls
it on the role's cadence, or the tick planner (tools/tick.py) says when.

  run_department.py --harness claude|codex --role R --task "..." [--ledger DIR] [--workdir DIR]
                    [--profile FILE] [--dry-run]

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
                "network": "WebFetch", "grep": "Grep"}
# Codex has no allowlist flag; tool availability is sandbox + MCP. We map the org's tier to a
# sandbox mode instead (asset-touching Tier-B would need a host-provided custody sandbox).
CODEX_SANDBOX_BY_TIER = {"A": "workspace-write", "B": "danger-full-access"}


def build_claude(role, task, profile, tools, mode, workdir):
    cmd = ["claude", "-p", task, "--output-format", "json"]
    if profile:
        cmd += ["--append-system-prompt", profile]
    if tools:
        mapped = sorted({CLAUDE_TOOLS.get(t, t) for t in tools})
        cmd += ["--allowedTools", ",".join(mapped)]
    cmd += ["--permission-mode", mode or "acceptEdits"]
    return cmd


def build_codex(role, task, profile, tier, model, workdir):
    cmd = ["codex", "exec", "--json"]
    if model:
        cmd += ["--model", model]
    cmd += ["--sandbox", CODEX_SANDBOX_BY_TIER.get(tier or "A", "workspace-write")]
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
    p.add_argument("--workdir")
    p.add_argument("--profile")           # a file with the role's projected system prompt
    p.add_argument("--tools")             # comma-separated neutral tool names
    p.add_argument("--tier", default="A")
    p.add_argument("--model")
    p.add_argument("--permission-mode", dest="mode")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv[1:])

    profile_text = ""
    if a.profile and os.path.exists(a.profile):
        with open(a.profile, encoding="utf-8") as f:
            profile_text = f.read()
    tools = [t.strip() for t in (a.tools or "").split(",") if t.strip()]

    if a.harness == "claude":
        cmd = build_claude(a.role, a.task, profile_text, tools, a.mode, a.workdir)
    else:
        cmd = build_codex(a.role, a.task, profile_text, a.tier, a.model, a.workdir)

    # the guardrail env every launched department inherits — the hook reads these
    env = dict(os.environ)
    if a.ledger:
        env["ORG_LEDGER_ROOT"] = a.ledger
    env["ORG_ROLE"] = a.role

    if a.dry_run:
        print("# projected headless invocation for role=%s on harness=%s" % (a.role, a.harness))
        print(" ".join(shlex.quote(c) for c in cmd))
        print("# env: ORG_LEDGER_ROOT=%s ORG_ROLE=%s" % (a.ledger or "(unset)", a.role))
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
