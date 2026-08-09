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
          --body B [--source mandate|self] [--depends 3,7] [--carved-from N] [--priority N]
                                           mint a backlog Issue. --kind objective = the big-picture
                                           RFP/objective Issue (the parent); --kind task (default) = a
                                           department's unit of work, linked as a NATIVE GitHub
                                           sub-issue of --parent so the hierarchy + roll-up shows in
                                           the UI. --dept tags the owning department.
  repair-body --repo R --issue N --body B --reason WHY
                                           explicitly repair an Issue body and record old/new
                                           digests plus the authenticated GitHub actor in an audit
                                           comment. Audit failure rolls the body update back.
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
                                           list Issues ready to work: unclaimed, not parked /
                                           in-progress / blocked / needs-human, and EVERY
                                           `Depends on:` line's targets verifiably closed;
                                           default lists TASKS only (objectives are parents, not
                                           work). Output also carries `withheld_unverifiable`
                                           (issues withheld because a dependency's state could
                                           not be verified — gh degradation is visible, not a
                                           silent empty list) + a stderr WARN per such withhold
  park    --repo R --issue N [--why W]     mark an Issue PARKED (label orgforge:parked, machine-
                                           readable — not title prose): ready excludes it until
                                           unpark. --why is recorded as a comment (Issue #103)
  unpark  --repo R --issue N [--why W]     remove orgforge:parked; the Issue re-enters ready's view
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
        orgforge:{mandate,self} · orgforge:off-ranking · orgforge:parked

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

from ghsync.backlog import (STAGES, cmd_claim, cmd_release, cmd_create, cmd_repair_body, cmd_stage,
                            cmd_ready, cmd_needs_human, cmd_split_check, cmd_candidate_id,
                            cmd_park, cmd_unpark)
from ghsync._core import banner
from ghsync.record import (cmd_log, cmd_decide, cmd_provisional, cmd_review_findings,
                           cmd_review_response, DECISIONS)
from ghsync.branch import cmd_branch
from ghsync.coverage import cmd_coverage_check


def main(argv):
    p = argparse.ArgumentParser(prog="github_sync", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("claim", "release"):
        q = sub.add_parser(name)
        q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)"); q.add_argument("--issue", required=True, type=int)
        q.add_argument("--agent", required=True)
    q = sub.add_parser("create")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)"); q.add_argument("--title", required=True)
    q.add_argument("--body", required=True, help="complete non-placeholder Issue context")
    q.add_argument("--objective"); q.add_argument("--source")
    q.add_argument("--depends"); q.add_argument("--priority", type=int)
    q.add_argument("--kind", choices=("objective", "task"), default="task",
                   help="objective = the big-picture RFP/objective Issue (parent); "
                        "task = a department's unit of work (a sub-issue of its objective)")
    q.add_argument("--dept", help="the department this task belongs to (labels orgforge:dept:<name>)")
    q.add_argument("--parent", help="parent Issue number: link this task as a NATIVE GitHub sub-issue "
                                    "of that objective (GitHub shows the hierarchy + progress roll-up)")
    q.add_argument("--carved-from", dest="carved_from",
                   help="the number of the Issue a mid-rework carve-out came from. \"A carve-out "
                        "depends on its origin\" holds without exception, so `Depends on: #N` is "
                        "added automatically in machine-readable form (Issue #103). Writing the "
                        "dependency in prose is not read by ready — this option is the only path by "
                        "which it propagates")
    q = sub.add_parser("repair-body")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--body", required=True, help="complete replacement Issue body")
    q.add_argument("--reason", required=True, help="why this rewrite is necessary")
    q.add_argument("--confirm-drop-depends", action="store_true",
                   help="explicitly confirm removing existing Depends on references")
    q = sub.add_parser("stage")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--stage", required=True)
    for name in ("park", "unpark"):
        q = sub.add_parser(name)
        q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)")
        q.add_argument("--issue", required=True, type=int)
        q.add_argument("--why",
                       help="the reason for the park/unpark — left as a comment on the Issue "
                            "(replacing the prose title `[PARKED]`, Issue #103)")
    q = sub.add_parser("ready"); q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)")
    q.add_argument("--kind", choices=("task", "objective", "any"), default="task",
                   help="which kind of Issue to list as ready (default: task — objectives are "
                        "parent/roll-up Issues, not claimable units of work)")
    q = sub.add_parser("log")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)"); q.add_argument("--issue", required=True, type=int)
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
    # A finding and its response must be addressable across harnesses, and durable: that is what
    # lets the next reviewer say "this was answered, here is what changed" instead of raising it
    # fresh. Without it, agents/gate.md's "a finding may only block again if head/evidence/risk
    # changed" is a rule nobody can check (tatekae #170 ran 12 rounds partly on re-raised findings).
    q = sub.add_parser("review-findings",
                       help="report the findings raised on an Issue, and which are answered or "
                            "still open")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin if omitted)")
    q.add_argument("--issue", required=True, type=int)

    q = sub.add_parser("review-response",
                       help="append the response to a review finding to the Issue, in a form "
                            "another harness can re-confirm")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--review", required=True,
                   help="the original review's review_subject_id, or an Issue comment marker")
    q.add_argument("--finding", required=True,
                   help="the finding ID the original review assigned (e.g. GATE-001)")
    q.add_argument("--status", required=True, choices=("addressed", "not_reproducible", "deferred"))
    q.add_argument("--response", required=True,
                   help="what was done about it and how, or how it was refuted")
    q.add_argument("--evidence", required=True,
                   help="the command and real output backing the response")
    q.add_argument("--by", required=True, help="who responded (maker / reviewer / supervisor)")
    q.add_argument("--blocked-by", dest="blocked_by", help="what is blocking, if anything")
    # Record each lineage's judge's judgment as **provisional**. admission_decided /
    # refutation_attempted are generated only once the two lineages agree (acceptance criteria 1-4).
    pv = sub.add_parser("provisional",
                        help="record one lineage's judge's judgment provisionally, and generate "
                             "the admission once they agree")
    pv.add_argument("--issue", type=int, required=True)
    pv.add_argument("--role", required=True, choices=("gate", "skeptic"))
    pv.add_argument("--lineage", required=True, choices=("same-harness", "cross-harness"))
    pv.add_argument("--verdict", required=True,
                    help="gate: admit|reject|park / skeptic: survives|refuted")
    # **A value no judge produces.** What verify observed and printed is passed through as-is.
    # It is the key that stops two judgments of different subjects being declared as "having looked
    # at the same thing" and made to agree.
    pv.add_argument("--subject", required=True,
                    help="review_subject_id — the value verify printed. Not something a judge "
                         "produces")
    pv.add_argument("--repo",
                    help="owner/name (used to project onto the Issue; discovered when omitted)")
    pv.add_argument("--why", required=True,
                    help="what was read and where it was decided (a paraphrase is not accepted)")
    pv.add_argument("--evidence", default="",
                    help="required to pass it — what was referred to")
    pv.add_argument("--alternatives", default="")
    pv.add_argument("--standard", default="")
    pv.add_argument("--risk", default="")
    pv.add_argument("--phase", default=None)
    pv.add_argument("--by", default=None, help="the recorder (defaults to --role)")
    # **The judge's signed receipt.** decision_by is settled only where this is present (H1).
    # A file path or a JSON string. **No argument is provided** for declaring decision_by on the
    # CLI.
    pv.add_argument("--receipt", default=None,
                    help="the judgment's receipt (a file or JSON). decision_by becomes attested "
                         "only where it verifies. Without one it stays claimed — it cannot be used "
                         "to enforce independence")
    pv.set_defaults(fn=cmd_provisional)

    q = sub.add_parser("decide")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--event", required=True, help=f"the judgment class, one of {DECISIONS}")
    q.add_argument("--verdict", required=True, help="admit|reject|pass|rework|survives|refuted|park|…")
    q.add_argument("--why", required=True,
                   help="THE REASONING that produced the verdict — what was weighed and what evidence "
                        "decided it. With human review retired this is the only account of why the "
                        "change merged; a restatement of the verdict is rejected (docs/11 §4f)")
    # The lineage of the judge that judged. In an org with judges.lineage = cross-harness, recording
    # admit/survives needs **both lineages** (negative from either side is negative, so only an admit
    # demands agreement).
    q.add_argument("--lineage", choices=("same-harness", "cross-harness"),
                   help="the lineage of the judge that produced this judgment (required when "
                        "recording admit/survives in a cross-harness org)")
    q.add_argument("--by", help="the role that decided (gate, skeptic, registrar, …)")
    q.add_argument("--phase", help="the SDLC phase this judgment gates")
    q.add_argument("--evidence", help="what was consulted — test output, CI run, repro_lint verdict, files read")
    q.add_argument("--claimed",
                   help="what the maker / gate / skeptic **reported** (close to the original "
                        "wording). Carry the qualifiers (\u300c\u301c\u306b\u306f\u7121"
                        "\u3044\u300d, \u300c\u672a\u6e2c\u5b9a\u300d, and the like) through "
                        "rather than dropping them")
    q.add_argument("--verified",
                   help="what **the supervisor ran and confirmed themselves** (the command and its "
                        "output). Not a summary of the report — where it was not run, it belongs "
                        "under --claimed")
    q.add_argument("--alternatives", help="the options considered and why they were rejected")
    q.add_argument("--standard", help="the acceptance standard applied (the bar, not a vibe)")
    q.add_argument("--risk", help="a known risk knowingly accepted by this decision")
    q.add_argument("--root", help="the root-cause-of-death class (learning.py DEATH_ROOTS: "
                                  "placebo_test / "
                                  "declaration_drift / integration_base_moved / "
                                  "self_written_premise / other) — attaching it to a "
                                  "reject/refuted record lets recurrence detection count by root "
                                  "(Issue #104)")
    q.add_argument("--event-id", dest="event_id", help="the ledger event's id — keys the idempotent dedup")
    q = sub.add_parser("branch")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--no-worktree", dest="no_worktree", action="store_true",
                   help="switch the main repository's branch deliberately, even in an org that "
                        "uses worktrees")
    q.add_argument("--create", action="store_true",
                   help="also `git checkout -b <name> <base>` in the current repo (idempotent). "
                        "Use --worktree when running makers in parallel — a checkout switches the "
                        "tree, so in parallel the commits are certain to mix")
    q.add_argument("--worktree", action="store_true",
                   help="create a git worktree dedicated to the branch at "
                        "`.orgforge/wt/issue-<N>/`. The only safe shape for a parallel fan-out")
    q.add_argument("--base", help="the branch to fork from (default: develop, docs/11 §4c)")
    q = sub.add_parser("split-check")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)"); q.add_argument("--issue", required=True, type=int)
    q = sub.add_parser("needs-human")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)")
    q.add_argument("--title", required=True, help="the work a human does (one line)")
    q.add_argument("--body", help="the steps: what, where, and what to hand back")
    q.add_argument("--objective", help="the related objective id")
    q.add_argument("--parent",
                   help="the objective Issue number (linked as a native sub-issue)")
    q.add_argument("--blocks",
                   help="the Issue numbers that cannot start until this is done "
                        "(comma-separated)")
    q = sub.add_parser("candidate-id")
    q.add_argument("--role", required=True, help="the maker/department that owns the item")
    q.add_argument("--contract", required=True, help="contract_ref — the objective this item serves")
    q.add_argument("--gap", required=True, help="a SHORT one-line description of the gap/deliverable")
    q = sub.add_parser("coverage-check")
    q.add_argument("--repo", help="owner/name (discovered from the git remote origin when omitted)")
    q.add_argument("--manifest", default="coverage-manifest.md",
                   help="path to the founding coverage manifest (docs/11 §0a fixes the name)")
    a = p.parse_args(argv[1:])
    banner()
    # --repo is optional: when omitted it is discovered from the git remote origin (no .envrc
    # needed). Where the backlog Issues live is a fact readable from the checkout, not a setting an
    # operator transcribes — transcription is a step, steps get skipped, and it drifts on another
    # machine.
    # A provisional is written only to the ledger (the Issue comment waits until the admission is
    # generated). A ledger-only org with no GitHub remote should still be able to record both
    # lineages' judgments, so this returns before the repo is resolved.
    # For a provisional the ledger is primary and the projection onto the Issue is incidental (it
    # preserves what the reasoning is reconciled against).
    # **A ledger-only org must still be able to record both lineages' judgments** — dropping a
    # judgment because there is no GitHub leaves that org unable to use cross-harness. Where there is
    # no repo the projection is skipped, and cmd_provisional says that nothing holds what it
    # reconciles against.
    if a.cmd == "provisional" and getattr(a, "repo", None) is None:
        import os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        import discover as _d
        a.repo = _d.backlog_repo()          # where there is none, proceed with None
        return cmd_provisional(a)
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
            "repair-body": cmd_repair_body,
            "stage": cmd_stage, "ready": cmd_ready, "log": cmd_log,
            "park": cmd_park, "unpark": cmd_unpark,
            "branch": cmd_branch, "split-check": cmd_split_check,
            "coverage-check": cmd_coverage_check,
            "candidate-id": cmd_candidate_id, "decide": cmd_decide,
            "provisional": cmd_provisional,
            "review-findings": cmd_review_findings,
            "review-response": cmd_review_response,
            "needs-human": cmd_needs_human}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
