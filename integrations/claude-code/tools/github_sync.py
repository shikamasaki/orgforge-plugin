#!/usr/bin/env python3
"""github_sync — project the org's backlog onto GitHub Issues and back (integrations/web).

R0: this organ BORROWS GitHub as the host (labels = the exclusion lock, Issues = the backlog window);
it builds no lock and no second SSoT. The ledger stays authoritative (SSoT). The sync is asymmetric:
  - ledger → Issue: stage, computed priority, dependency/blocked (regenerated projection, never hand-edited)
  - Issue → ledger: a human's label / a new Issue enters via triage as a candidate (gated intake)

The one thing this organ arbitrates directly is the WORK-LOCK, because that must be atomic and visible to
both a web session and a local session: an agent claims an Issue by ADDING `orgforge:claimed:<agent>`, but
ONLY if the Issue carries no other `claimed:*` label. GitHub's label add is the atomic primitive; we read
the current labels first and refuse to claim a contended Issue — the GitHub projection of the 0.7.2
concurrent-write prevention.

Commands (all shell out to `gh`, which the host authenticates — the organ does no network of its own):
  claim   --repo R --issue N --agent A     claim an Issue if unclaimed; exit 0 claimed / 10 contended
  release --repo R --issue N --agent A     drop this agent's claim
  create  --repo R --title T [--kind objective|task] [--parent N] [--dept D] [--objective O]
          [--body B] [--source mandate|self] [--depends 3,7] [--priority N]
                                           mint a backlog Issue. --kind objective = the big-picture
                                           RFP/objective Issue (the parent); --kind task (default) = a
                                           department's unit of work, linked as a NATIVE GitHub
                                           sub-issue of --parent so the hierarchy + roll-up shows in
                                           the UI. --dept tags the owning department.
  stage   --repo R --issue N --stage S     set the lifecycle label (ready|in-progress|blocked|needs-human|done)
  log     --repo R --issue N --event E [--detail T] [--phase P] [--event-id ID]
          [--command C] [--result R] [--files F] [--next-step S] [--blocked-by B]
                                           append a WORK-LOG comment to a task Issue on a milestone
                                           event (cycle_started/progress_recorded/phase_admitted/
                                           cycle_completed …), so progress accrues on the Issue as it
                                           happens. Idempotent per --event-id (a replay logs once).
                                           Pass the command run + what it returned: with human review
                                           retired the Issue is the audit record (docs/11 §4f).
  decide  --repo R --issue N --event E --verdict V --why TEXT [--by ROLE] [--phase P]
          [--evidence E] [--alternatives A] [--standard S] [--risk K] [--event-id ID]
                                           record a JUDGMENT with its REASONING on the Issue. Ledger
                                           keeps the receipt; the Issue keeps the account of why the
                                           change was allowed to merge unread. A --why that merely
                                           restates the verdict is REJECTED (docs/11 §4f).
  ready   --repo R [--kind task|objective|any]
                                           list Issues ready to work (no open dependency, unclaimed);
                                           default lists TASKS only (objectives are parents, not work)
  branch  --repo R --issue N [--create] [--base B]
                                           print the DETERMINISTIC feature branch for a task Issue —
                                           `feat/issue-N-<slug>` off `develop` (docs/11 §4c). --create
                                           also `git checkout -b` it. Same Issue ⇒ same branch (repro).
  candidate-id --role R --contract C --gap "one-line gap"
                                           print the DETERMINISTIC candidate_id for a backlog item —
                                           sha256 over (role, contract_ref, normalized gap) joined on
                                           \\x1f. Same item ⇒ same id (so a replay dedups); different
                                           items cannot collide (so neither is silently swallowed).
  coverage-check --repo R [--manifest coverage-manifest.md]
                                           DECOMPOSITION COVERAGE gate: every must-have row in the
                                           founding manifest must have reached >=1 task Issue (traced
                                           by the `coverage_row:` trailer /org-decompose writes).
                                           Exit 10 on a gap — a must-have that never became an Issue
                                           is silently unbuilt (docs/11 §0a).
  split-check --repo R --issue N           SHAPE check: warn (exit 10) if a task Issue is too coarse —
                                           `owns:` spans multiple territories, or a `depends_on:` is
                                           still open (docs/11 §4b). Shape only; sense is the skeptic's.

Two-level hierarchy (the org's structure projected onto GitHub):
  objective Issue  — orgforge:kind:objective — the RFP/objective (a projection of an org objective)
    └─ task Issue  — orgforge:kind:task + orgforge:dept:<name> — a department's work, a native
                     sub-issue of its objective (GitHub's own parent/child, borrowed under R0)

Labels: orgforge:claimed:<agent> · orgforge:{ready,in-progress,blocked,needs-human,done} ·
        orgforge:kind:{objective,task} · orgforge:dept:<name> · orgforge:objective:<id> ·
        orgforge:{mandate,self} · orgforge:off-ranking

Exit: 0 ok / 10 contended-or-blocked (escalate) / 2 usage or gh error.
"""
import argparse
import json
import os
import re
import subprocess
import sys


import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from ghsync.backlog import (STAGES, cmd_claim, cmd_release, cmd_create, cmd_stage,
                            cmd_ready, cmd_needs_human, cmd_split_check, cmd_candidate_id)
from ghsync.record import cmd_log, cmd_decide, DECISIONS
from ghsync.branch import cmd_branch
from ghsync.coverage import cmd_coverage_check


def main(argv):
    p = argparse.ArgumentParser(prog="github_sync", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("claim", "release"):
        q = sub.add_parser(name)
        q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--issue", required=True, type=int)
        q.add_argument("--agent", required=True)
    q = sub.add_parser("create")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--title", required=True)
    q.add_argument("--body"); q.add_argument("--objective"); q.add_argument("--source")
    q.add_argument("--depends"); q.add_argument("--priority", type=int)
    q.add_argument("--kind", choices=("objective", "task"), default="task",
                   help="objective = the big-picture RFP/objective Issue (parent); "
                        "task = a department's unit of work (a sub-issue of its objective)")
    q.add_argument("--dept", help="the department this task belongs to (labels orgforge:dept:<name>)")
    q.add_argument("--parent", help="parent Issue number: link this task as a NATIVE GitHub sub-issue "
                                    "of that objective (GitHub shows the hierarchy + progress roll-up)")
    q = sub.add_parser("stage")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--stage", required=True)
    q = sub.add_parser("ready"); q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）")
    q.add_argument("--kind", choices=("task", "objective", "any"), default="task",
                   help="which kind of Issue to list as ready (default: task — objectives are "
                        "parent/roll-up Issues, not claimable units of work)")
    q = sub.add_parser("log")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--event", required=True,
                   help="the milestone ledger event class (cycle_started, progress_recorded, "
                        "phase_admitted, cycle_completed, …)")
    q.add_argument("--detail", help="optional free-text detail for the log line")
    q.add_argument("--phase", help="the SDLC phase, if this milestone is a phase transition")
    q.add_argument("--event-id", dest="event_id",
                   help="the ledger event's id — keys the idempotent dedup so a replay logs once")
    q.add_argument("--command", help="the exact command run at this step (verbatim, so it is re-runnable)")
    q.add_argument("--result", help="what that command returned — the real output, not 'it worked'")
    q.add_argument("--files", help="the files created/changed at this step")
    q.add_argument("--next-step", dest="next_step", help="what happens next (what a fresh session resumes from)")
    q.add_argument("--blocked-by", dest="blocked_by", help="what is blocking, if anything")
    q = sub.add_parser("decide")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--event", required=True, help=f"the judgment class, one of {DECISIONS}")
    q.add_argument("--verdict", required=True, help="admit|reject|pass|rework|survives|refuted|park|…")
    q.add_argument("--why", required=True,
                   help="THE REASONING that produced the verdict — what was weighed and what evidence "
                        "decided it. With human review retired this is the only account of why the "
                        "change merged; a restatement of the verdict is rejected (docs/11 §4f)")
    q.add_argument("--by", help="the role that decided (gate, skeptic, registrar, …)")
    q.add_argument("--phase", help="the SDLC phase this judgment gates")
    q.add_argument("--evidence", help="what was consulted — test output, CI run, repro_lint verdict, files read")
    q.add_argument("--alternatives", help="the options considered and why they were rejected")
    q.add_argument("--standard", help="the acceptance standard applied (the bar, not a vibe)")
    q.add_argument("--risk", help="a known risk knowingly accepted by this decision")
    q.add_argument("--event-id", dest="event_id", help="the ledger event's id — keys the idempotent dedup")
    q = sub.add_parser("branch")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--create", action="store_true",
                   help="also `git checkout -b <name> <base>` in the current repo (idempotent). "
                        "並列で maker を走らせるなら --worktree を使うこと — checkout は"
                        "ツリーを切り替えるので、並列だと必ずコミットが混ざる")
    q.add_argument("--worktree", action="store_true",
                   help="ブランチ専用の git worktree を `.orgforge/wt/issue-<N>/` に作る。"
                        "並列 fan-out の唯一の安全な形")
    q.add_argument("--base", help="the branch to fork from (default: develop, docs/11 §4c)")
    q = sub.add_parser("split-check")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--issue", required=True, type=int)
    q = sub.add_parser("needs-human")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）")
    q.add_argument("--title", required=True, help="人間がやる作業（一行）")
    q.add_argument("--body", help="何を・どこで・何を返せばよいかの手順")
    q.add_argument("--objective", help="関連する objective id")
    q.add_argument("--parent", help="objective Issue 番号（native sub-issue として繋ぐ）")
    q.add_argument("--blocks", help="この作業が終わるまで着手できない Issue 番号（カンマ区切り）")
    q = sub.add_parser("candidate-id")
    q.add_argument("--role", required=True, help="the maker/department that owns the item")
    q.add_argument("--contract", required=True, help="contract_ref — the objective this item serves")
    q.add_argument("--gap", required=True, help="a SHORT one-line description of the gap/deliverable")
    q = sub.add_parser("coverage-check")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）")
    q.add_argument("--manifest", default="coverage-manifest.md",
                   help="path to the founding coverage manifest (docs/11 §0a fixes the name)")
    a = p.parse_args(argv[1:])
    # --repo は省略可能: 省略時は git remote origin から発見する（.envrc 不要）。
    # バックログ Issue の所在はチェックアウトを見れば分かる事実であって、operator が
    # 書き写す設定ではない — 書き写しは手順であり、飛ばされ、別マシンでずれる。
    if getattr(a, "repo", None) is None:
        import os as _os
        _here = _os.path.dirname(_os.path.abspath(__file__))
        sys.path.insert(0, _here)
        import discover as _d
        a.repo = _d.backlog_repo()
        if not a.repo:
            print("no --repo given and no GitHub remote found — pass --repo owner/name, or "
                  "run inside a checkout whose origin is a GitHub repo.", file=sys.stderr)
            return 2
    return {"claim": cmd_claim, "release": cmd_release, "create": cmd_create,
            "stage": cmd_stage, "ready": cmd_ready, "log": cmd_log,
            "branch": cmd_branch, "split-check": cmd_split_check,
            "coverage-check": cmd_coverage_check,
            "candidate-id": cmd_candidate_id, "decide": cmd_decide,
            "needs-human": cmd_needs_human}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
