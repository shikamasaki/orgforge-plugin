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
from ghsync.record import (cmd_log, cmd_decide, cmd_provisional, cmd_review_response,
                           DECISIONS)
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
                   help="rework 中の carve-out 元 Issue 番号。「carve out 先は元に依存する」は例外なく"
                        "成り立つので、`Depends on: #N` を機械可読に自動付与する（Issue #103）。"
                        "散文で依存を書いても ready は読まない — この option が唯一の伝播経路")
    q = sub.add_parser("repair-body")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--body", required=True, help="complete replacement Issue body")
    q.add_argument("--reason", required=True, help="why this rewrite is necessary")
    q.add_argument("--confirm-drop-depends", action="store_true",
                   help="explicitly confirm removing existing Depends on references")
    q = sub.add_parser("stage")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--stage", required=True)
    for name in ("park", "unpark"):
        q = sub.add_parser(name)
        q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）")
        q.add_argument("--issue", required=True, type=int)
        q.add_argument("--why", help="park/unpark の理由 — Issue のコメントとして残す（散文タイトル "
                                     "`[PARKED]` の置き換え、Issue #103）")
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
    # A finding and its response must be addressable across harnesses, and durable: that is what
    # lets the next reviewer say "this was answered, here is what changed" instead of raising it
    # fresh. Without it, agents/gate.md's "a finding may only block again if head/evidence/risk
    # changed" is a rule nobody can check (tatekae #170 ran 12 rounds partly on re-raised findings).
    q = sub.add_parser("review-response",
                       help="review finding への対応を Issue に追記し、別harnessが再確認できる形にする")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--review", required=True,
                   help="元レビューの review_subject_id または Issue comment marker")
    q.add_argument("--finding", required=True, help="元レビューが付けた finding ID（例: GATE-001）")
    q.add_argument("--status", required=True, choices=("addressed", "not_reproducible", "deferred"))
    q.add_argument("--response", required=True, help="何をどう対応したか、または反証したか")
    q.add_argument("--evidence", required=True, help="対応を裏付けるコマンドと実出力")
    q.add_argument("--by", required=True, help="対応者（maker / reviewer / supervisor）")
    q.add_argument("--blocked-by", dest="blocked_by", help="what is blocking, if anything")
    # 各血統の judge の判定を **暫定** として記録する。2血統が一致したときにだけ
    # admission_decided / refutation_attempted が生成される（受け入れ条件1〜4）。
    pv = sub.add_parser("provisional",
                        help="ある血統の judge の判定を暫定記録し、一致したら admission を生成")
    pv.add_argument("--issue", type=int, required=True)
    pv.add_argument("--role", required=True, choices=("gate", "skeptic"))
    pv.add_argument("--lineage", required=True, choices=("same-harness", "cross-harness"))
    pv.add_argument("--verdict", required=True,
                    help="gate: admit|reject|park / skeptic: survives|refuted")
    # **judge に作らせない値。** verify が観測して出したものをそのまま渡す。
    # 別の対象を見た2判定を「同じものを見た」と申告して一致を作られないための鍵。
    pv.add_argument("--subject", required=True,
                    help="review_subject_id — verify が出した値。judge が作るものではない")
    pv.add_argument("--repo", help="owner/name（Issue への投影に使う。省略時は自動発見）")
    pv.add_argument("--why", required=True, help="何を見て、どこで決まったか（言い換えは不可）")
    pv.add_argument("--evidence", default="", help="通過させるなら必須 — 参照したもの")
    pv.add_argument("--alternatives", default="")
    pv.add_argument("--standard", default="")
    pv.add_argument("--risk", default="")
    pv.add_argument("--phase", default=None)
    pv.add_argument("--by", default=None, help="記録者（既定は --role）")
    # **judge の署名 receipt。** これがあるときだけ decision_by が確定する（H1）。
    # ファイルパスか JSON 文字列。CLI で decision_by を申告する引数は **用意しない**。
    pv.add_argument("--receipt", default=None,
                    help="判断の receipt（ファイルか JSON）。検証できたときだけ decision_by が "
                         "attested になる。無ければ claimed のまま — 独立性の強制には使えない")
    pv.set_defaults(fn=cmd_provisional)

    q = sub.add_parser("decide")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--event", required=True, help=f"the judgment class, one of {DECISIONS}")
    q.add_argument("--verdict", required=True, help="admit|reject|pass|rework|survives|refuted|park|…")
    q.add_argument("--why", required=True,
                   help="THE REASONING that produced the verdict — what was weighed and what evidence "
                        "decided it. With human review retired this is the only account of why the "
                        "change merged; a restatement of the verdict is rejected (docs/11 §4f)")
    # 判定した judge の血統。judges.lineage = cross-harness の org では、admit/survives の
    # 記録に **両方の血統** が要る（片方でも否なら否なので、admit だけが一致を要求する）。
    q.add_argument("--lineage", choices=("same-harness", "cross-harness"),
                   help="この判定を出した judge の血統（cross-harness の org で admit/survives "
                        "を記録するときは必須）")
    q.add_argument("--by", help="the role that decided (gate, skeptic, registrar, …)")
    q.add_argument("--phase", help="the SDLC phase this judgment gates")
    q.add_argument("--evidence", help="what was consulted — test output, CI run, repro_lint verdict, files read")
    q.add_argument("--claimed",
                   help="maker / gate / skeptic が**報告した**こと（原文に近い形で）。"
                        "条件節（「〜には無い」「未測定」など）は落とさず運ぶこと")
    q.add_argument("--verified",
                   help="**監督が自分で実行して確かめた**こと（コマンドと出力）。"
                        "報告の要約ではない — 走らせていないなら --claimed 側に書く")
    q.add_argument("--alternatives", help="the options considered and why they were rejected")
    q.add_argument("--standard", help="the acceptance standard applied (the bar, not a vibe)")
    q.add_argument("--risk", help="a known risk knowingly accepted by this decision")
    q.add_argument("--root", help="死因の根の分類（learning.py DEATH_ROOTS: placebo_test / "
                                  "declaration_drift / integration_base_moved / "
                                  "self_written_premise / other）— reject/refuted の記録に"
                                  "付けると再発検出が根で数えられる（Issue #104）")
    q.add_argument("--event-id", dest="event_id", help="the ledger event's id — keys the idempotent dedup")
    q = sub.add_parser("branch")
    q.add_argument("--repo", help="owner/name（省略時は git remote origin から自動発見）"); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--no-worktree", dest="no_worktree", action="store_true",
                   help="worktree 運用の org でも、あえてメインリポジトリのブランチを切り替える")
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
    banner()
    # --repo は省略可能: 省略時は git remote origin から発見する（.envrc 不要）。
    # バックログ Issue の所在はチェックアウトを見れば分かる事実であって、operator が
    # 書き写す設定ではない — 書き写しは手順であり、飛ばされ、別マシンでずれる。
    # provisional は台帳だけに書く（Issue へのコメントは admission が生成されてから）。
    # GitHub remote が無い ledger-only の org でも 2血統の判定は記録できるべきなので、
    # repo 解決より前に返す。
    # provisional は台帳が主で、Issue への投影は付随（reasoning の照合対象を残すため）。
    # **ledger-only の org でも2血統の判定は記録できなければならない** — GitHub が無いことを
    # 理由に判定を落とすと、その org は cross-harness を使えない。repo が無ければ投影を省き、
    # 「照合対象が残らない」ことを cmd_provisional が言う。
    if a.cmd == "provisional" and getattr(a, "repo", None) is None:
        import os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        import discover as _d
        a.repo = _d.backlog_repo()          # 無ければ None のまま進む
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
            "review-response": cmd_review_response,
            "needs-human": cmd_needs_human}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
