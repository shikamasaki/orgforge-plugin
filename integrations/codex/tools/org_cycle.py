#!/usr/bin/env python3
"""org_cycle — run one cycle's plumbing with one command (docs/11 §0d).

**Why this is needed.** `/org-work` was a prose instruction to "type these events", and an agent was
what executed it. In the field **eleven commands** were typed by hand per cycle (two Issues), which
comes to around ninety for eighteen Issues. One mistake among them breaks the ledger's consistency.

Worse was how `parent` was handled. A phase chain inherits the parent objective's admit
(docs/11 §2), yet **a human picked that `parent` value out of the Issue by eye and typed it in**.
Implementing the inheritance changes nothing while the value is typed by hand — mistaking one for
another still happens. **Not picking up what can be picked up is negligence in the design.**

This tool takes on only "plumbing whose order and actor are already settled". **It takes on no
judgment** — what to choose, whom to delegate to, and whether to admit are the roles' work, and are
not automated here (it follows exactly the line docs/03 §6.5 draws: forced delegation is a design
error, a forced invariant is right).

  org_cycle.py begin    --role R --issue N [--phase implement] [--agent A]
      claim → spec_delegated → phase_started (parent resolved automatically) → cycle_started →
      log to the Issue
  org_cycle.py complete --role R --issue N --outputs TEXT
                        (--domain-model-updated REF | --domain-model-none WHY)
      cycle_completed (domain_model required) → log to the Issue → stage done
  org_cycle.py plan     --role R --issue N [...]
      **Runs nothing**; prints the sequence of events that would be typed (the --dry-run
      equivalent)

Exit: 0 ok / 3 the ledger refused it (an order violation and the like) / 8 judge preflight failed /
      9 the installed-organ binding is deficient / 10 contended / 2 usage or configuration error
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

from orgcycle._core import banner
from orgcycle.cycle import cmd_begin, cmd_complete, cmd_plan
from orgcycle.judge import cmd_verify, cmd_record, cmd_rework, cmd_intake
from orgcycle.ship import cmd_handback, cmd_integrate
from orgcycle.inspect import cmd_show, cmd_gc, cmd_touched


def main(argv):
    p = argparse.ArgumentParser(prog="org_cycle", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("begin", "plan"):
        q = sub.add_parser(name)
        q.add_argument("--role", required=True,
                       help="the delegating side (a supervisor / department head)")
        q.add_argument("--issue", required=True, type=int, help="the task Issue number")
        q.add_argument("--agent", help="the side that actually builds (defaults to --role)")
        q.add_argument("--phase", default="implement",
                       help="the phase to start (default: implement)")
        q.add_argument("--parent",
                       help="the parent objective number (resolved from the Issue when omitted)")
        q.add_argument("--candidate-id", dest="candidate_id",
                       help="read from the Issue's candidate_id trailer when omitted")
        q.add_argument("--base",
                       help="what the worktree branches from (the constitution's "
                            "enforcement.judges.integration_ref when omitted; with neither it "
                            "fails — develop is not guessed, #106)")
        q.add_argument("--why",
                       help="why this was chosen now (attention_allocated's reason)")
        q.add_argument("--no-check", dest="no_check", action="store_true",
                       help="do not print the pre-start checks (dependency states, work waiting on "
                            "a human)")
        q.add_argument("--no-worktree", dest="no_worktree", action="store_true",
                       help="do not create a worktree. **Do not use this when running in "
                            "parallel** — running parallel makers over one tree causes the accident "
                            "where one Issue's commits land on another Issue's branch (it actually "
                            "happened). Only for single, sequential work.")
    q = sub.add_parser("verify",
                       help="assemble the material that starts gate/skeptic (it does not judge)")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--role", required=True, choices=("gate", "skeptic"))
    # phase is part of review_subject (which phase the judgment belongs to).
    q.add_argument("--phase", default=None,
                   help="the phase being judged (it enters review_subject_id)")
    q.add_argument("--base", dest="base", default=None,
                   help="the integration ref (resolved in the order origin/develop, develop, "
                        "origin/main, main when omitted)")
    q.add_argument("--subject-root", dest="subject_root", default=None,
                   help="state the checkout being judged explicitly (the Issue's worktree "
                        ".orgforge/wt/issue-<N> by default). Only for deliberately judging a layout "
                        "that does not use worktrees — there is no implicit fallback to the cwd "
                        "(#101)")
    # Do not start a judge merely to record something. In a cross-harness org verify actually runs a
    # headless judge, so waiting minutes just to learn the subject makes no sense (measured).
    q.add_argument("--print-subject", action="store_true",
                   help="print review_subject_id and stop (no judge is started)")
    # What a re-review may turn on besides the revision (#193). The subject id digests the tree,
    # not the evidence a maker cited or the risk a judge recorded, so those are passed here and
    # compared against the recorded round.
    q.add_argument("--evidence", default=None,
                   help="the evidence being submitted this round (compared with the recorded "
                        "round; a difference earns a fresh review)")
    q.add_argument("--risk", default=None,
                   help="the residual risk stated this round (same comparison as --evidence)")
    # Dispatch a judge for a subject that already has a recorded verdict. Suppressed by default:
    # the subject id encodes the revision, so re-deriving an unchanged one cannot change the
    # verdict — it only spends a judge run and a CI round (#182).
    q.add_argument("--force", action="store_true",
                   help="dispatch even when this review subject already has a recorded verdict")
    # A MUST a read-only judge cannot re-derive can only become a park. By default it advises and
    # does not obstruct the start (the judgment is the gate's), but where paying minutes to half an
    # hour for a miss is unwanted, it can stop.
    q.add_argument("--strict-rederivability", dest="strict_rederivability",
                   action="store_true",
                   help="stop without starting the judge where a MUST cannot be re-derived by a "
                        "read-only judge (advice only by default). For when paying time for a park "
                        "that goes nowhere is unwanted")

    q = sub.add_parser("touched",
                       help="leave a change to a production asset in the ledger (DDL, privileges, "
                            "infrastructure)")
    q.add_argument("--target", required=True,
                   help='against what (e.g. supabase:<project>)')
    q.add_argument("--op", required=True, help="apply_migration / revoke / grant / deploy …")
    q.add_argument("--name", help="the subject's name (a migration name, a function name, …)")
    q.add_argument("--by", required=True, help="who put it in")
    q.add_argument("--authority", required=True,
                   help="under whose authority (part of issue-N / an explicit CEO instruction / "
                        "its own judgment)")
    q.add_argument("--issue", type=int, help="the related Issue")
    q.add_argument("--reversible", action="store_true", help="pass this where it can be undone")
    q.add_argument("--rollback", help="how to undo it (write this where reversible)")

    q = sub.add_parser("show",
                       help="the whole picture of one Issue (its judgment history, what it waits "
                            "on)")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--base", default=None,
                   help="the reference for attributing irreversible changes (the constitution's "
                        "integration_ref when omitted)")

    q = sub.add_parser("gc",
                       help="sweep up accumulated worktrees (leaving any with uncommitted changes)")
    q.add_argument("--base", default=None,
                   help="the reference for deciding integration (the constitution's "
                        "integration_ref when omitted)")
    q.add_argument("--all", action="store_true", help="include the unintegrated ones too")

    q = sub.add_parser("intake",
                       help="check whether a subagent's report has the shape of a deliverable")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--role", required=True, help="gate / skeptic / maker")
    q.add_argument("--report", required=True,
                   help="the report the subagent returned (`-` reads standard input)")

    q = sub.add_parser("rework",
                       help="record that rework was commissioned in answer to a reject/refuted")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--after", required=True, choices=("reject", "refuted"),
                   help="which judgment the rework answers")
    q.add_argument("--by", required=True, help="the role that commissioned it (the supervisor)")
    q.add_argument("--reason", required=True,
                   help="what the maker is to fix, in one line")
    q.add_argument("--round", default="1", help="which round (it enters the idempotency key)")
    q.add_argument("--to", help="whom it was commissioned to")
    q.add_argument("--root", help="the root-cause-of-death class (learning.py DEATH_ROOTS: "
                                  "placebo_test / "
                                  "declaration_drift / integration_base_moved / "
                                  "self_written_premise / other) — recurrence detection counts by "
                                  "matching roots (Issue #104)")

    q = sub.add_parser("record",
                       help="record a judgment already made, retroactively (it carries a backfill "
                            "mark)")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--event", required=True,
                   help="integration_admitted / refutation_attempted / …")
    q.add_argument("--verdict", required=True)
    q.add_argument("--by", required=True, help="whose judgment it is")
    q.add_argument("--why", required=True, help="what was read, and what decided it")
    q.add_argument("--command", help="the command run at the time")
    q.add_argument("--result", help="its real output")
    q.add_argument("--base", default=None,
                   help="integration_admitted's integration target (the constitution's "
                        "integration_ref when omitted)")

    q = sub.add_parser("handback",
                       help="push the feature branch → open a PR against the integration target → "
                            "link it to the Issue")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--branch", help="derived deterministically from the Issue when omitted")
    q.add_argument("--base", default=None,
                   help="the PR's integration target (the constitution's integration_ref when "
                        "omitted)")
    q.add_argument("--summary", help="what was built (one line)")
    q.add_argument("--result",
                   help="the DoD command's real output (it enters the PR body and the log)")
    q.add_argument("--files", help="the changed files")

    q = sub.add_parser("integrate",
                       help="fan-in to the integration target (reconcile the preconditions → merge "
                            "→ test after integration → record)")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--role", default="integrator",
                   help="the role running the integration (the record's actor)")
    q.add_argument("--branch", help="derived deterministically from the Issue when omitted")
    q.add_argument("--base", default=None,
                   help="the integration target (the constitution's integration_ref when omitted; "
                        "with neither it fails — #106)")
    q.add_argument("--test", default="npm test",
                   help="the whole-suite test to run after integration")
    q.add_argument("--force", action="store_true",
                   help="proceed without the gate/skeptic preconditions. **Record the reason**")
    q.add_argument("--plan", action="store_true",
                   help="run nothing; show what would be integrated and where it may conflict")

    q = sub.add_parser("complete")
    q.add_argument("--role", required=True)
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--agent")
    q.add_argument("--outputs", required=True, help="what was built (one line)")
    q.add_argument("--command", required=True,
                   help="the DoD command (verbatim, in a form someone else can re-run)")
    q.add_argument("--result", required=True,
                   help="that command's **real output** (failures included; \"it passed\" is not "
                        "accepted — the log refuses it)")
    q.add_argument("--files", help="the files changed")
    q.add_argument("--new-surface", dest="new_surface", action="append",
                   help="the surface this cycle exposed outward (who can call it / what it can "
                        "do). Repeatable")
    q.add_argument("--new-surface-none", dest="new_surface_none",
                   help="the reason no public surface was added (an explicit negation)")
    q.add_argument("--learned",
                   help="a learning that holds for the next cycle too (proposed to doctrine; the "
                        "admit is the gate's)")
    q.add_argument("--affects", help="the roles that learning holds for (comma-separated)")
    q.add_argument("--confidence", type=float, default=0.7,
                   help="confidence in that learning, 0..1 (default 0.7)")
    q.add_argument("--review-days", dest="review_days", type=int, default=180,
                   help="days until that learning is re-confirmed (default 180)")
    q.add_argument("--domain-model-updated", dest="domain_model_updated",
                   help="a reference to the domain rule this cycle established")
    q.add_argument("--domain-model-none", dest="domain_model_none",
                   help="the reason nothing was established (an explicit negation; docs/11 §4d)")
    q.add_argument("--candidate-id", dest="candidate_id")
    a = p.parse_args(argv[1:])
    banner()
    return {"begin": cmd_begin, "complete": cmd_complete, "plan": cmd_plan,
            "verify": cmd_verify, "integrate": cmd_integrate, "handback": cmd_handback, "gc": cmd_gc, "record": cmd_record, "rework": cmd_rework, "intake": cmd_intake, "show": cmd_show, "touched": cmd_touched}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
