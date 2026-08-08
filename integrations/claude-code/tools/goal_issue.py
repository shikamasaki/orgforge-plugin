"""Project a persistent Goal onto a GitHub Issue, so the work is visible where the org looks.

## Why this exists

`org_goal` recorded `goal_started` / `goal_completed` in the ledger and nowhere else. Nothing
appeared on GitHub. An agent could start a goal, implement, commit, push, open a PR, and complete
the goal — with **no Issue at any point** — and truthfully report "recorded in OrgForge", because
it was: in a local ledger only the host that wrote it can read.

That contradicts how this org is meant to run. The Issue is the surface a human, a second agent, or
a different harness can all see; the ledger is the audit record behind it (`SPEC.md`: the ledger is
the audit record, not the SSoT). A goal that exists only in the ledger is invisible to everyone who
did not run the command.

It also routed around every check added for the Issue path. `split-check` and `ready` are what
require EARS acceptance, a DoD command, counterexamples and the domain sections — and they only
run on Issues. A goal that never becomes an Issue is never asked for any of them, which is exactly
how a proof-of-concept got built and "completed" with no spec at all.

## What this does NOT do

It does not turn `org-goal` into `org-cycle`. A goal stays a bookmark across sessions and
harnesses; the *work* still belongs in task Issues under the objective, driven by
`org_cycle begin/complete`. This makes the bookmark visible, not authoritative.

## When GitHub is unavailable

Say so and continue. A goal is for surviving a lost session, so refusing to record one because
`gh` is not configured would remove the mechanism exactly when it is needed. But **never silently**
degrade to a ledger-only record — that silence is the defect being fixed here.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

# GitHub refuses a label over 50 characters, and `--objective` becomes one. A goal's objective is
# prose, so it is hashed into a short stable id rather than truncated: truncation collides on two
# goals sharing a prefix, and this id is what links every Issue of the same goal.
OBJECTIVE_ID_PREFIX = "goal-"


def objective_label_id(goal_id):
    """The label-safe objective id for a goal. Stable for the life of the goal."""
    return f"{OBJECTIVE_ID_PREFIX}{str(goal_id).replace('goal-', '')[:12]}"


def _gh(args, timeout=30):
    try:
        p = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, "gh CLI not found"
    except Exception as exc:                                   # pragma: no cover - env dependent
        return 1, f"gh failed: {exc}"


def repo_slug(explicit=None):
    """owner/name for the current checkout, or None when it cannot be determined."""
    if explicit:
        return explicit
    for env in ("ORG_GITHUB_REPO", "GH_REPO"):
        if os.environ.get(env):
            return os.environ[env]
    code, out = _gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
    return out.strip() if code == 0 and out.strip() else None


def find_goal_issue(repo, goal_id):
    """The Issue already projecting this goal, or None. Keyed on the goal id in the body."""
    marker = _marker(goal_id)
    code, out = _gh(["issue", "list", "--repo", repo, "--state", "all", "--limit", "50",
                     "--search", goal_id, "--json", "number,body"])
    if code != 0:
        return None
    try:
        for row in json.loads(out):
            if marker in (row.get("body") or ""):
                return row["number"]
    except Exception:
        return None
    return None


def _marker(goal_id):
    return f"<!-- orgforge:goal:{goal_id} -->"


def open_goal_issue(repo, goal_id, objective, harness):
    """Create the objective Issue for a goal. Returns (number, detail) with number None on failure.

    Idempotent: a goal already projected returns its existing Issue rather than minting a second.
    """
    existing = find_goal_issue(repo, goal_id)
    if existing:
        return existing, f"goal {goal_id} already projected to issue #{existing}"

    body = "\n".join([
        f"## Objective\n\n{objective}\n",
        "## How this goal is worked\n",
        "This Issue is the **objective**. The work happens in task sub-issues:",
        "",
        "```",
        f'github-sync create --kind task --objective {objective_label_id(goal_id)} \\',
        "    --parent <this issue> --dept <role> --title … --body <the SPEC>",
        "org-cycle begin --role <role> --issue <task>",
        "```",
        "",
        "A task's body carries its SPEC — EARS acceptance, a runnable DoD command, and the",
        "counterexamples. `split-check` refuses a task without them, and `ready` will not hand it",
        "to a maker. That check only runs on Issues, which is why the work belongs here rather",
        "than in a goal record alone.",
        "",
        f"Harness: `{harness}` · goal id: `{goal_id}`",
        "",
        _marker(goal_id),
    ])

    label = f"orgforge:objective:{objective_label_id(goal_id)}"
    for name, color in ((label, "5319e7"), ("orgforge:kind:objective", "0e8a16")):
        _gh(["label", "create", name, "--repo", repo, "--color", color, "--force"])

    code, out = _gh(["issue", "create", "--repo", repo,
                     "--title", f"Objective: {_one_line(objective)}",
                     "--body", body,
                     "--label", label, "--label", "orgforge:kind:objective"])
    if code != 0:
        return None, out.strip()[:300]
    number = _trailing_number(out)
    return number, (f"projected goal {goal_id} to issue #{number}" if number
                    else f"issue created but its number could not be read: {out.strip()[:120]}")


def comment_on_goal_issue(repo, goal_id, heading, body, event_id=None):
    """Append a goal event to its Issue. Returns (ok, detail); a no-op when already present."""
    number = find_goal_issue(repo, goal_id)
    if not number:
        return False, f"no Issue projects goal {goal_id}"
    marker = f"<!-- orgforge:goal-event:{event_id or heading} -->"
    code, out = _gh(["issue", "view", str(number), "--repo", repo, "--json", "comments"])
    if code == 0 and marker in out:
        return True, f"already on issue #{number} (idempotent)"
    code, out = _gh(["issue", "comment", str(number), "--repo", repo,
                     "--body", f"### {heading}\n\n{body}\n\n{marker}"])
    if code != 0:
        return False, out.strip()[:200]
    return True, f"recorded on issue #{number}"


def close_goal_issue(repo, goal_id, summary):
    number = find_goal_issue(repo, goal_id)
    if not number:
        return False, f"no Issue projects goal {goal_id}"
    code, out = _gh(["issue", "close", str(number), "--repo", repo, "--comment", summary])
    if code != 0:
        return False, out.strip()[:200]
    return True, f"closed issue #{number}"


def _one_line(text, limit=120):
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _trailing_number(url_or_out):
    match = re.search(r"/issues/(\d+)", url_or_out)
    return int(match.group(1)) if match else None
