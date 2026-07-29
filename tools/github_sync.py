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

CLAIM_PREFIX = "orgforge:claimed:"
STAGES = ("ready", "in-progress", "blocked", "needs-human", "done")


def gh(args, check=True):
    """Run a gh command; return (code, stdout). gh handles auth; we never see the token."""
    try:
        p = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, "gh CLI not found — install it and `gh auth login`"
    except Exception as e:
        return 1, f"gh failed: {e}"


def issue_labels(repo, n):
    code, out = gh(["issue", "view", str(n), "--repo", repo, "--json", "labels"])
    if code != 0:
        return None, out
    try:
        return [l["name"] for l in json.loads(out).get("labels", [])], ""
    except Exception as e:
        return None, f"parse: {e}"


def cmd_claim(a):
    labels, err = issue_labels(a.repo, a.issue)
    if labels is None:
        print(f"gh error: {err}", file=sys.stderr)
        return 2
    mine = CLAIM_PREFIX + a.agent
    others = [l for l in labels if l.startswith(CLAIM_PREFIX) and l != mine]
    if others:
        print(f"CONTENDED: issue #{a.issue} is already claimed by {others} — not touching it "
              f"(concurrent-write prevention; another session owns it). (integrations/web)",
              file=sys.stderr)
        return 10
    if mine in labels:
        print(f"already claimed by {a.agent}; idempotent no-op.")
        return 0
    # ensure the label exists, then add it (atomic on GitHub's side)
    gh(["label", "create", mine, "--repo", a.repo, "--color", "0e8a16", "--force"], check=False)
    code, out = gh(["issue", "edit", str(a.issue), "--repo", a.repo, "--add-label", mine])
    if code != 0:
        print(f"gh error adding claim: {out}", file=sys.stderr)
        return 2
    print(f"claimed issue #{a.issue} for {a.agent}.")
    return 0


def cmd_release(a):
    mine = CLAIM_PREFIX + a.agent
    code, out = gh(["issue", "edit", str(a.issue), "--repo", a.repo, "--remove-label", mine])
    if code != 0:
        print(f"gh error releasing: {out}", file=sys.stderr)
        return 2
    print(f"released issue #{a.issue} ({a.agent}).")
    return 0


def _ensure_labels(repo, names):
    for name, color in names:
        gh(["label", "create", name, "--repo", repo, "--color", color, "--force"], check=False)


def _find_open_issue(repo, title, objective):
    """Return an existing Issue number matching this backlog item's natural key (title, and the
    objective label if given), else None — plus whether it is closed. The backlog projection must be
    idempotent (docs/11 §0): a replayed discovery/founding cycle, or a web + local session projecting
    the same ledger, must not mint duplicate Issues.

    Searches `--state all`, NOT just open. A COMPLETED task is CLOSED (`stage done` closes it), so an
    open-only search makes delivered work invisible: re-running decomposition after a manifest
    amendment — the documented repair path — would re-mint a fresh Issue for every task already
    shipped. Matching closed Issues too is what makes 'a second pass fills gaps rather than duplicating
    the backlog' true for an org that has completed anything.

    Returns (number, state) or (None, None)."""
    code, out = gh(["issue", "list", "--repo", repo, "--state", "all",
                    "--search", title, "--json", "number,title,labels,state"])
    if code != 0:
        return None, None   # can't check — fall through to create (best effort; a dup is recoverable)
    try:
        for it in json.loads(out):
            if it.get("title") != title:
                continue
            if objective:
                names = [l["name"] for l in it.get("labels", [])]
                if f"orgforge:objective:{objective}" not in names:
                    continue
            return it["number"], (it.get("state") or "OPEN").upper()
    except Exception:
        return None, None
    return None, None


def _issue_number(url_or_out):
    """Extract the trailing issue number from a `gh issue create` URL (…/issues/123)."""
    tok = url_or_out.strip().rstrip("/").rsplit("/", 1)[-1]
    return int(tok) if tok.isdigit() else None


def _issue_id(repo, number):
    """The GitHub REST database id of an issue (needed by the sub-issues API, which keys on id, not
    the human number). Returns None on failure."""
    owner_repo = repo.split("/")
    if len(owner_repo) != 2:
        return None
    code, out = gh(["api", f"repos/{repo}/issues/{number}", "--jq", ".id"])
    if code != 0:
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None


def _link_sub_issue(repo, parent_number, child_number):
    """Attach child as a NATIVE GitHub sub-issue of parent (GitHub's own hierarchy, so the parent shows
    a sub-issue list + progress roll-up in the UI). The sub-issues API keys on the child's database id.
    R0: we borrow GitHub's native parent/child primitive rather than inventing our own link. Returns
    (ok, detail)."""
    child_id = _issue_id(repo, child_number)
    if child_id is None:
        return False, f"could not resolve issue #{child_number} database id for the sub-issue link"
    # -F (not -f): the sub_issues API requires sub_issue_id as a JSON *integer*; -f sends a string,
    # which the API rejects ("not of type integer"). -F preserves the numeric type.
    code, out = gh(["api", "--method", "POST",
                    f"repos/{repo}/issues/{parent_number}/sub_issues",
                    "-F", f"sub_issue_id={child_id}"])
    if code != 0:
        # already-linked is not an error for us (idempotent). GitHub phrases this as "already"
        # or "duplicate sub-issues" / "may only have one parent" — all mean the link already exists.
        low = out.lower()
        if "already" in low or "duplicate sub-issue" in low or "one parent" in low:
            return True, f"#{child_number} already a sub-issue of #{parent_number} (idempotent)"
        return False, f"sub-issue link failed: {out.strip()[:160]}"
    return True, f"#{child_number} linked as a sub-issue of #{parent_number}"


def cmd_create(a):
    # KIND: objective (the big-picture RFP/objective Issue — the parent) vs task (a department's unit of
    # work — a sub-issue of its objective). The kind label makes the two legible at a glance; the native
    # sub-issue link (below) makes the hierarchy real in GitHub's UI. Both are ledger projections (SSoT
    # unchanged): an objective Issue projects an org objective; a task Issue projects a candidate.
    kind = getattr(a, "kind", None) or "task"
    # idempotency (docs/11 §0): if an open Issue with this title (+objective) already exists, this is a
    # replay — return it instead of minting a duplicate.
    existing, state = _find_open_issue(a.repo, a.title, a.objective)
    if existing is not None:
        if state == "CLOSED":
            # already DELIVERED — re-minting it would duplicate finished work and re-open settled scope
            print(f"issue #{existing} already exists for {a.title!r} and is CLOSED (delivered) — "
                  f"idempotent no-op; not re-minting completed work (docs/11 §0).")
            return 0
        print(f"issue #{existing} already open for {a.title!r} — idempotent no-op (docs/11 §0).")
        # still (re)assert the parent link so a replayed task lands under its objective
        parent = getattr(a, "parent", None)
        if parent:
            ok, detail = _link_sub_issue(a.repo, int(str(parent).lstrip("#")), existing)
            print(detail if ok else f"WARN: {detail}", file=sys.stderr if not ok else sys.stdout)
        return 0
    labels = ["orgforge:ready", f"orgforge:kind:{kind}"]
    ensure = [("orgforge:ready", "1d76db"),
              (f"orgforge:kind:{kind}", "0e8a16" if kind == "objective" else "bfd4f2")]
    if a.objective:
        lbl = f"orgforge:objective:{a.objective}"
        labels.append(lbl); ensure.append((lbl, "5319e7"))
    dept = getattr(a, "dept", None)
    if dept:
        lbl = f"orgforge:dept:{dept}"
        labels.append(lbl); ensure.append((lbl, "d4c5f9"))
    if a.source:
        lbl = f"orgforge:{a.source}"
        labels.append(lbl); ensure.append((lbl, "fbca04"))
    _ensure_labels(a.repo, ensure)
    body = a.body or ""
    parent = getattr(a, "parent", None)
    if parent:
        body += f"\n\nParent: #{str(parent).lstrip('#')}"   # human-readable; the native link is added below
    if a.depends:
        deps = ", ".join(f"#{d.strip().lstrip('#')}" for d in a.depends.split(",") if d.strip())
        body += f"\n\nDepends on: {deps}"
    if a.priority is not None:
        body += f"\n\npriority: {a.priority} (computed by attention.py — a projection, do not hand-edit)"
    args = ["issue", "create", "--repo", a.repo, "--title", a.title, "--body", body or "(no body)"]
    for l in labels:
        args += ["--label", l]
    code, out = gh(args)
    if code != 0:
        print(f"gh error creating issue: {out}", file=sys.stderr)
        return 2
    print(out.strip())   # gh prints the new issue URL
    # attach as a native sub-issue of its parent objective, so GitHub shows the hierarchy + roll-up
    if parent:
        child_number = _issue_number(out)
        if child_number is None:
            print("WARN: created the Issue but could not parse its number to link it as a sub-issue.",
                  file=sys.stderr)
            return 0
        ok, detail = _link_sub_issue(a.repo, int(str(parent).lstrip("#")), child_number)
        print(detail if ok else f"WARN: {detail}", file=(sys.stdout if ok else sys.stderr))
    return 0


def cmd_stage(a):
    if a.stage not in STAGES:
        print(f"stage must be one of {STAGES}", file=sys.stderr)
        return 2
    labels, err = issue_labels(a.repo, a.issue)
    if labels is None:
        print(f"gh error: {err}", file=sys.stderr)
        return 2
    _ensure_labels(a.repo, [(f"orgforge:{s}", "c2e0c6") for s in STAGES])
    remove = [l for l in labels if l.startswith("orgforge:") and l[len("orgforge:"):] in STAGES]
    args = ["issue", "edit", str(a.issue), "--repo", a.repo, "--add-label", f"orgforge:{a.stage}"]
    for r in remove:
        if r != f"orgforge:{a.stage}":
            args += ["--remove-label", r]
    code, out = gh(args)
    if code != 0:
        print(f"gh error: {out}", file=sys.stderr)
        return 2
    if a.stage == "done":
        cc, co = gh(["issue", "close", str(a.issue), "--repo", a.repo])
        if cc != 0:
            print(f"WARN: labeled done but close failed ({co.strip()[:120]}); a dependent Issue "
                  f"stays blocked until this closes — retry the close.", file=sys.stderr)
            return 10
    print(f"issue #{a.issue} → orgforge:{a.stage}")
    return 0


def _stable_key(*parts):
    """A process-stable idempotency marker from the given parts.

    Must NOT use hash(): Python salts str/tuple hashing per interpreter process, so each CLI run would
    mint a different marker for identical input and the "log this milestone once" guarantee would hold
    only within a single process — silently false for the replay case it exists to cover."""
    import hashlib
    joined = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _already_logged(repo, issue, marker):
    """True if a comment carrying this hidden marker is already on the Issue (idempotency, docs/11 §0)."""
    code, out = gh(["issue", "view", str(issue), "--repo", repo, "--json", "comments"])
    if code != 0:
        return False   # can't read — fall through and post (a rare dup is recoverable)
    try:
        return any(marker in (c.get("body") or "") for c in json.loads(out).get("comments", []))
    except Exception:
        return False


# マイルストーン: ここで「何をしたか」が残らないと、後から再構成する手段が無くなる。
# 途中経過（progress_recorded）は軽く刻めてよいが、サイクルの節目は監査点なので実出力を要求する。
_LOG_MILESTONES = ("cycle_started", "cycle_completed", "phase_admitted", "integration_admitted",
                   "result_deployed", "handback_opened")


def _log_defect(a):
    """作業ログが再構成可能かを検査する。None なら合格。

    `decide` は --why の空・言い換え・水増しを拒否するのに、`log` は --detail を一切検査して
    いなかった。結果は実測に出ていて、同じ Issue の中で判定は3,506〜5,894字、作業ログは
    276〜473字。**検査のある側だけが厚くなった。** 散文の指示を守るのは人だが、必須引数を
    守るのはツールなので、同じ強制を掛ける。
    """
    if a.event not in _LOG_MILESTONES:
        return None
    if not getattr(a, "command", None):
        return ("--command が要る（マイルストーンの log）。実際に走らせたコマンドを verbatim で。\n"
                "  「テストを流した」ではなく `npm test` のように、他人が再実行できる形で書くこと。")
    if not getattr(a, "result", None):
        return ("--result が要る（マイルストーンの log）。そのコマンドが返した**実出力**を、\n"
                "  失敗も含めて。成功だけの記録は作り話であり、失敗した試行こそ最も情報量が高い。")
    res = str(a.result)
    if len(res.encode("utf-8")) < 24:
        return ("--result が短すぎて実出力とは言えない。"
                "「通った」ではなく、返ってきたものを貼ること。")
    words = re.findall(r"[^\W\d_]+", res.lower(), flags=re.UNICODE)
    filler = {"ok", "okay", "done", "fine", "good", "green", "pass", "passed", "passes",
              "success", "succeeded", "yes", "worked", "works", "完了", "成功"}
    if words and not [w for w in words if w not in filler]:
        return ("--result が「通った」の言い換えでしかない。実出力（テスト件数、エラー、"
                "差分など）を貼ること。")
    return None


def _append_progress_receipt(a):
    """Issue に書いた作業ログの受領証を台帳にも残す。

    `log` は Issue にコメントするだけで台帳に何も書いていなかった。結果、実地では Issue に
    7回の作業記録があるのに `progress_recorded` は **0件**。これは #8 の refutation で
    塞いだのと同型（二重記録の片側が落ちる）で、しかも影響が具体的:

      · work_in_progress ビューは progress_recorded を読むので `/org-resume` が復帰できない
      · board も進捗を見られない
      · 台帳だけ見ると「作業記録を一度も残していない」ことになる

    台帳が SSoT ではない（SSoT は code + ドメインモデル）が、**中断からの復帰と監査は台帳が
    担う**ので、ここが空だと復帰機構が丸ごと動かない。

    失敗しても log 自体は成功させる — コメントは既に投稿済みで、受領証が付かないことを理由に
    「ログに失敗した」と報告すると、実際には残っている記録を人が二重投稿しにいく。
    """
    payload = {"role": getattr(a, "by", None) or "org", "candidate_id": a.event_id or "",
               "phase": a.phase or "", "milestone": a.event,
               "done_so_far": (a.detail or "")[:2000],
               "next_step": getattr(a, "next_step", None) or "",
               "blocker": getattr(a, "blocked_by", None) or "",
               "issue": a.issue}
    if getattr(a, "command", None):
        payload["command"] = a.command
    if getattr(a, "result", None):
        payload["result"] = str(a.result)[:4000]
    if getattr(a, "files", None):
        payload["files"] = a.files
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        p = subprocess.run([sys.executable, os.path.join(here, "ledger.py"), "append",
                            "--actor", payload["role"], "--class", "progress_recorded",
                            "--natural-key", f"progress-{a.issue}-{a.event_id or a.event}",
                            "--payload", json.dumps(payload, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=30)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return False, str(e)



def cmd_log(a):
    """Append a WORK-LOG comment to a task Issue on a milestone event (cycle_started, progress_recorded,
    phase_admitted, cycle_completed, …). The ledger stays the SSoT — this comment is its projection onto
    the Issue so the CEO sees progress accrue without opening the ledger.

    With human diff review retired (docs/11 §4f), the Issue is the org's PRIMARY audit surface: what was
    tried, what was run, what came back, what changed course and why. So this command takes the detail
    fields that make a log entry reconstructable by someone who was never in the session — the command
    that was run and its result, the files touched, the next step. Terse logs ("progress recorded") are
    the failure mode; they satisfy the letter of logging while recording nothing recoverable.

    IDEMPOTENT (docs/11 §0): each comment carries a hidden marker `<!-- orgforge:event:<id> -->`. If a
    comment with this event id already exists on the Issue, we no-op — a replayed/retried cycle logs the
    same milestone once, never twice. Pass --event-id (the ledger event's id) to key the dedup; without
    it we fall back to a hash of (event, detail)."""
    # sha256, NOT hash(): Python salts hash() per process (PYTHONHASHSEED), so a CLI marker built from
    # hash() differs on every invocation and the dedup NEVER fires across runs — a retried cycle
    # double-posts while the docstring promises "logs once, never twice".
    defect = _log_defect(a)
    if defect:
        print(f"作業ログが薄い: {defect}\n\n"
              f"docs/11 §3b のバー: **Issue だけを読んだ他人が、何が作られ・何が試され・"
              f"何が捨てられ・何を実行して何が返り・なぜマージされたかを再構成できること**。\n"
              f"`decide` が --why を検査するのと同じ理由でここも検査する — 人間の diff レビューは"
              f"廃止されており、この Issue が唯一の監査面だから。\n"
              f"途中の軽い刻みなら --event progress_recorded を使うこと（検査は掛からない）。",
              file=sys.stderr)
        return 2
    marker_key = a.event_id or _stable_key(a.event, a.detail or "", a.phase or "")
    marker = f"<!-- orgforge:event:{marker_key} -->"
    if _already_logged(a.repo, a.issue, marker):
        print(f"log: event {marker_key} already on issue #{a.issue} — idempotent no-op (docs/11 §0).")
        return 0
    # the visible line: a compact, human-readable milestone. detail is optional free text.
    line = f"**{a.event}**"
    if a.phase:
        line += f" · phase: `{a.phase}`"
    if a.detail:
        line += f" — {a.detail}"
    parts = [line]
    # the reconstructable detail: what was actually run, what came back, what moved.
    if getattr(a, "command", None):
        result = getattr(a, "result", None)
        parts.append(f"\n**Ran:**\n```\n{a.command}\n```")
        if result:
            parts.append(f"**Result:**\n```\n{result}\n```")
    for label, val in (("Files", getattr(a, "files", None)),
                       ("Next step", getattr(a, "next_step", None)),
                       ("Blocked by", getattr(a, "blocked_by", None))):
        if val:
            parts.append(f"**{label}:** {val}")
    body = "\n".join(parts) + f"\n\n{marker}"
    code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", body])
    if code != 0:
        print(f"gh error posting work-log comment: {out}", file=sys.stderr)
        return 2
    ok, msg = _append_progress_receipt(a)
    if ok:
        print(f"logged {a.event} to issue #{a.issue}（台帳にも progress_recorded を記録）。")
    else:
        print(f"logged {a.event} to issue #{a.issue}.")
        print(f"注意: 台帳の受領証を書けなかった（{msg.strip()[:120]}）。"
              f"Issue には残っているが、`/org-resume` はこの進捗を見られない。", file=sys.stderr)
    return 0


# the judgment classes that must land on the Issue with their reasoning (docs/11 §4f)
DECISIONS = ("admission_decided", "refutation_attempted", "phase_admitted", "conformance_reviewed",
             "integration_admitted", "deploy_decided", "rework_requested", "scope_decided",
             "design_decided", "tradeoff_decided")


def _reasoning_digest(*fields):
    """A stable digest over a judgment's reasoning fields — the tamper-evidence anchor (docs/11 §4f.1).

    Normalizes whitespace so a cosmetic reflow does not read as tampering, while any change to the
    substance (a dropped `--risk`, a rewritten `--why`) changes the digest."""
    import hashlib
    norm = "\x1f".join(re.sub(r"\s+", " ", (f or "").strip()) for f in fields)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


def _reasoning_defect(why, verdict, event):
    """Return a defect phrase if `why` is not actual reasoning, else None.

    A pure length bound fails in both directions and must not be used alone:
      · it PASSES `"admit admit admit admit admit"` — the literal restatement it exists to reject;
      · it REJECTS `「全テスト通過を確認。cap近傍の並行joinは未検証」` — substantive reasoning that is
        short in codepoints because Japanese carries ~2-3x the information per character, and the org's
        default output_language is ja. Measuring bytes rather than codepoints fixes the CJK half.
    So: require some substance by BYTE length, then reject text that is only verdict/filler tokens."""
    if not why:
        return "is required — a verdict with no reasoning is a stamp."
    if len(why.encode("utf-8")) < 24:
        return "is too short to be an account of the decision."
    # strip punctuation, then see whether anything remains beyond verdict words and filler
    words = re.findall(r"[^\W\d_]+", why.lower(), flags=re.UNICODE)
    if not words:
        return "contains no words — punctuation or padding is not reasoning."
    filler = {verdict.lower(), event.lower(), "the", "is", "it", "this", "was", "a", "an", "and",
              "ok", "okay", "fine", "good", "looks", "lgtm", "pass", "passed", "passes", "green",
              "admit", "admitted", "approve", "approved", "yes", "no", "all", "to", "me", "verdict"}
    substantive = [w for w in words if w not in filler]
    if not substantive:
        return ("only restates the verdict — that is exactly the rubber stamp this check exists to "
                "reject.")
    if len(set(words)) <= 2 and len(words) >= 4:
        return "is one phrase repeated to clear a length bar, not reasoning."
    # keyboard-mash padding: almost no distinct characters across the whole text
    if len(set(why.replace(" ", ""))) <= 3:
        return "is padding, not an account of the decision."
    return None


def cmd_decide(a):
    """Record a JUDGMENT on the task Issue — the verdict AND the reasoning that produced it.

    Human diff review is retired (docs/11 §4f): no person reads the change before it merges. That makes
    the machine's own judgments the only judgments, and an unrecorded judgment is then indistinguishable
    from no judgment at all. A ledger `admission_decided{verdict: admit}` proves a decision HAPPENED and
    is tamper-evident; it does not say what was weighed, what the alternative was, or what evidence was
    consulted — and that is exactly what someone auditing the merge six weeks later needs.

    So every judgment double-writes, the same way a settled convention does (conventions.py): the ledger
    gets the RECEIPT (tamper-evident, machine-queryable), the Issue gets the REASONING (readable, in
    context, next to the work it judged). The Issue is where a decision can actually be inferred later.

    A verdict with an empty or contentless --why is rejected — a bare "admit" is the failure mode this
    command exists to prevent, and accepting it would let the audit trail degrade back into a stamp.
    Admitting also requires --evidence: an admission with nothing consulted IS the stamp."""
    if a.event not in DECISIONS:
        print(f"decide: --event must be a judgment class {DECISIONS}; got {a.event!r}. "
              f"For a progress milestone use `log`.", file=sys.stderr)
        return 2
    why = (a.why or "").strip()
    bad = _reasoning_defect(why, a.verdict, a.event)
    if bad:
        print(f"decide: --why {bad} With human review retired, this text is the only account of why "
              f"the change was allowed to merge (docs/11 §4f). Say what was weighed and what evidence "
              f"decided it.", file=sys.stderr)
        return 2
    # An admission with no evidence consulted is a stamp regardless of how well the prose reads.
    if a.verdict in ("admit", "pass", "survives", "conforms") and not (a.evidence or "").strip():
        print(f"decide: --evidence is required for verdict {a.verdict!r}. Naming what you actually "
              f"consulted (the command you ran and its real output, the CI run, the repro_lint verdict) "
              f"is what separates a judgment from a stamp — and nobody read the diff (docs/11 §4f).",
              file=sys.stderr)
        return 2
    marker_key = a.event_id or _stable_key(a.event, a.verdict, why)   # sha256; see cmd_log
    marker = f"<!-- orgforge:decision:{marker_key} -->"
    if _already_logged(a.repo, a.issue, marker):
        print(f"decide: decision {marker_key} already on issue #{a.issue} — idempotent no-op.")
        return 0
    icon = {"admit": "✅", "pass": "✅", "survives": "✅", "conforms": "✅",
            "reject": "⛔", "refuted": "⛔", "fail": "⛔",
            "rework": "🔁", "park": "⏸️", "freeze": "🧊"}.get(a.verdict, "•")
    parts = [f"## {icon} {a.event} — `{a.verdict}`"]
    if a.by:
        parts.append(f"**Decided by:** `{a.by}`" + (f" · **phase:** `{a.phase}`" if a.phase else ""))
    elif a.phase:
        parts.append(f"**Phase:** `{a.phase}`")
    parts.append(f"\n**Why (the reasoning):**\n{why}")
    if getattr(a, "evidence", None):
        parts.append(f"\n**Evidence consulted:**\n{a.evidence}")
    if getattr(a, "alternatives", None):
        parts.append(f"\n**Alternatives considered and rejected:**\n{a.alternatives}")
    if getattr(a, "standard", None):
        parts.append(f"\n**Standard applied:** {a.standard}")
    if getattr(a, "risk", None):
        parts.append(f"\n**Known risk accepted:** {a.risk}")
    # TAMPER EVIDENCE (docs/11 §4f.1). A GitHub comment is editable and deletable by anyone with write
    # access — including the agents this record judges — while the ledger is hash-chained. Without a
    # digest an agent could silently rewrite its own account (dropping the --risk it admitted, say) and
    # `ledger verify` would still report the chain intact. So the reasoning is hashed here and the digest
    # is printed for the caller to carry into the ledger receipt as `reasoning_sha256`: re-hashing the
    # comment later either matches, or the account was altered. It does not PREVENT the edit; it makes
    # the edit detectable, which is what "tamper-evident" means.
    digest = _reasoning_digest(why, a.evidence, a.alternatives, a.standard, a.risk)
    parts.append(f"\n`reasoning_sha256: {digest}` — re-hash this record's fields to detect an edit; "
                 f"the ledger receipt carries the same digest.")
    parts.append("\n_No human reviewed this change before merge (docs/11 §4f). This record is the "
                 "account of why it was allowed to._")
    body = "\n".join(parts) + f"\n\n{marker}"

    # **台帳を先に通す。** 統制（自己承認拒否・順序違反）は台帳が持っているので、
    # Issue に書いてから台帳が拒否すると「Issue には admit と書いてあるが台帳には無い」
    # という最悪の食い違いが残る。拒否されるなら、外に見える記録を作る前に止める。
    here = os.path.dirname(os.path.abspath(__file__))
    payload = {"verdict": a.verdict, "deliverable": str(a.issue), "issue": a.issue,
               "reasoning_sha256": digest}
    if getattr(a, "phase", None):
        payload["phase"] = a.phase
    if getattr(a, "risk", None):
        payload["risk_accepted"] = True
    try:
        r = subprocess.run([sys.executable, os.path.join(here, "ledger.py"), "append",
                            "--actor", a.by, "--class", a.event,
                            # 冪等キーは **判定の内容ごと**に一意。`{event}-{issue}` だと2周目の
                            # 判定が1周目と衝突して no-op になり、しかも冪等チェックは統制より
                            # 先に評価されるので、自己承認・順序違反が「既に記録済み」として
                            # 素通りする（実地で確認）。digest は verdict/why/evidence から
                            # 作られるので、同じ判定の再実行だけが正しく no-op になる。
                            "--natural-key", f"{a.event}-{a.issue}-{digest[:12]}",
                            "--payload", json.dumps(payload, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=30)
        led_out = ((r.stdout or "") + (r.stderr or "")).strip()
        led_ok = r.returncode == 0
    except Exception as e:
        led_out, led_ok = str(e), False

    if not led_ok:
        print(f"台帳が受け付けなかったので、Issue にも記録していない:\n  {led_out[:500]}",
              file=sys.stderr)
        if "rejected" in led_out:
            print("\n  これは統制が働いた結果である（自己承認・順序違反など）。"
                  "判定そのものを見直すこと。", file=sys.stderr)
        return 4

    code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", body])
    if code != 0:
        print(f"gh error posting decision comment: {out}", file=sys.stderr)
        print(f"  注意: 台帳には既に記録済み（{a.event} #{a.issue}）。Issue 側だけが欠けている。\n"
              f"  同じ引数で再実行すれば、台帳は冪等 no-op になり Issue だけが埋まる。",
              file=sys.stderr)
        return 2
    print(f"recorded decision {a.event}={a.verdict} on issue #{a.issue}.")
    print(f"reasoning_sha256={digest}")
    # 説明ではなく、そのまま打てる形を出す。実地では受領証が書かれず（refutation は台帳0件）、
    # 相関キーの無い判定が素通りしていた。`issue` は相関キーでもあるので、これが欠けると
    # DISTINCT_ACTOR / requires_prior が対象を特定できず、統制そのものが効かない。
    print(f"台帳にも受領証を記録した（{a.event} #{a.issue}, digest {digest[:12]}…）。")
    return 0


def _slug(text, maxlen=32):
    """A deterministic, git-ref-safe slug from an Issue title. Same title ⇒ same slug (reproducible
    branch names, docs/11 §0). Keeps ASCII words; if the title is mostly non-ASCII (e.g. a Japanese
    task title, output_language: ja), the ASCII part may be empty — then fall back to a short hash of
    the full title, so the branch is still unique and stable (feat/issue-N-<hash>) rather than collapsing
    to nothing. git refs allow non-ASCII, but a stable ASCII/hash slug is safer across tools."""
    import re
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    s = s[:maxlen].strip("-")
    if len(s) >= 3:
        return s
    # too little ASCII to be meaningful (non-Latin title) — deterministic short hash of the full title
    import hashlib
    return "t" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def cmd_branch(a):
    """Print (and optionally create) the DETERMINISTIC feature branch for a task Issue:
    `feat/issue-<N>-<slug-of-title>` off `develop` (the org's branch policy, docs/11 §4c). The name is
    a pure function of (issue number, title), so two makers / a replay derive the SAME branch — the
    reproducibility rule that governs Issue creation, applied to branches. With --create it also runs
    `git checkout -b <name> develop` in the current repo (R0: borrow git; we build no ref store)."""
    labels, err = issue_labels(a.repo, a.issue)  # also validates the Issue exists
    code, out = gh(["issue", "view", str(a.issue), "--repo", a.repo, "--json", "title"])
    if code != 0:
        # slug は名前を読みやすくするだけで、識別子は Issue 番号。GitHub に届かない
        # （オフライン / 認証切れ / repo 未作成）ことを、作業場を用意できない理由にはしない —
        # ここで止めると並列 maker が分離ツリーを持てず、同一ツリーに落ちて混線する。
        if not (getattr(a, "worktree", False) or getattr(a, "create", False)):
            print(f"gh error: {out}", file=sys.stderr)
            return 2
        print(f"警告: Issue のタイトルを取れなかったので slug を省く（{out.strip()[:80]}）",
              file=sys.stderr)
        title = ""
    else:
        try:
            title = json.loads(out).get("title", "")
        except Exception:
            title = ""
    slug = _slug(title)
    name = f"feat/issue-{a.issue}-{slug}" if slug else f"feat/issue-{a.issue}"
    print(name)
    base = getattr(a, "base", None) or "develop"
    # --worktree は --create を含意する（worktree を作れば分離した作業場ができる）。
    # 並列 fan-out ではこちらが正解 — checkout はツリーを切り替えるので必ず混ざる。
    if getattr(a, "worktree", False):
        return _make_worktree(name, base, a.issue)
    if getattr(a, "create", False):
        import subprocess
        try:
            p = subprocess.run(["git", "checkout", "-b", name, base],
                               capture_output=True, text=True, timeout=30)
            if p.returncode != 0:
                # branch may already exist (idempotent) — try to switch to it
                p2 = subprocess.run(["git", "checkout", name], capture_output=True, text=True, timeout=30)
                if p2.returncode != 0:
                    print(f"git error creating/switching branch: {(p.stderr or '')+(p2.stderr or '')}",
                          file=sys.stderr)
                    return 2
                print(f"branch {name} already existed — switched to it (idempotent).", file=sys.stderr)
            else:
                print(f"created and switched to {name} off {base}.", file=sys.stderr)
        except Exception as e:
            print(f"git not available: {e}", file=sys.stderr)
            return 2
    return 0


def _make_worktree(name, base, issue):
    """ブランチ専用の git worktree を作る — 並列 fan-out の唯一の安全な形。

    **なぜ checkout では駄目なのか。** `git checkout` は*ツリーを切り替える*ので、同一ディレクトリで
    2体の maker を並列に走らせると、片方のコミットがもう片方のブランチに載る。実地でそれが起きた
    （#7 のコミットが `feat/issue-8-settle` に載った）。内容が分離されていたので復旧できたが、
    **同一ツリーで並列に走らせる限り再発する**。

    「毎回正しいブランチにいることを確認する」という運用でこれを防ぐのは、判断に依存する設計であり、
    18 Issue を並列で回せば必ず破れる。worktree なら**物理的に別ディレクトリ**なので、混ざりようがない。

    R0: git の worktree をそのまま借りる。ref ストアも並行制御も作らない。"""
    import os
    import subprocess
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, timeout=30)
    if root.returncode != 0:
        print("git リポジトリの外にいる。", file=sys.stderr)
        return 2
    wt = os.path.join(root.stdout.strip(), ".orgforge", "wt", f"issue-{issue}")
    if os.path.isdir(wt):
        print(f"worktree は既にある（冪等）: {wt}")
        print(f"\ncd {wt}    # ここで作業すること。元のツリーには触らない")
        return 0
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    # ブランチが既にあれば繋ぐ、無ければ base から作る
    p = subprocess.run(["git", "worktree", "add", "-b", name, wt, base],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        p = subprocess.run(["git", "worktree", "add", wt, name],
                           capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(f"worktree を作れない: {(p.stderr or '').strip()[:200]}", file=sys.stderr)
        return 2
    print(f"worktree: {wt}  (branch {name} off {base})")
    print(f"\ncd {wt}    # ここで作業すること。元のツリーには触らない")
    print("完了したら PR を出し、`git worktree remove` で片付ける。")
    return 0


def cmd_split_check(a):
    """SHAPE check on a task Issue's granularity (docs/11 §4b): warn (do not block) if the Issue looks
    too COARSE for a no-context maker — its `owns:` spans multiple disjoint territories (should be one
    atomic unit), or a `depends_on:` names an Issue that is still OPEN (the single-unit assertion fails:
    a fresh maker can't take it green until that sibling lands). This checks SHAPE, never SENSE — is the
    split *good* stays with the skeptic (docs/12 §6). Exit 0 clean · 10 = re-split candidate · 2 error."""
    code, out = gh(["issue", "view", str(a.issue), "--repo", a.repo, "--json", "body,title"])
    if code != 0:
        print(f"gh error: {out}", file=sys.stderr)
        return 2
    try:
        body = json.loads(out).get("body") or ""
    except Exception as e:
        print(f"parse: {e}", file=sys.stderr)
        return 2
    warnings = []
    # (a) owns spanning multiple territories — pull the `owns:` line and count distinct top-level paths
    for line in body.splitlines():
        low = line.lower()
        if "owns" in low and (":" in line):
            territory = line.split(":", 1)[1]
            # split on commas / 'and' / semicolons; count distinct top-level dirs (before the first '/')
            import re
            parts = [p.strip() for p in re.split(r"[,;、]| and ", territory) if p.strip()
                     and not p.strip().startswith("<")]   # ignore the unfilled placeholder
            tops = {p.split("/")[0].strip("` ") for p in parts}
            if len(tops) > 1:
                warnings.append(f"`owns:` spans {len(tops)} distinct territories {sorted(tops)} — a task "
                                f"should own ONE atomic unit; consider splitting one Issue per territory.")
            break
    # (b) depends_on referencing an OPEN Issue — the single-unit assertion (docs/11 §4b) fails
    for line in body.splitlines():
        if line.lower().lstrip().startswith(("depends_on", "depends on", "- **depends_on")):
            # `#N` の形だけを依存とみなす。数字を全部拾うと散文が誤検出される —
            # 「実装コードは1行も入らない」の「1」が #1 として解釈された（実地で判明）。
            for num in re.findall(r"#(\d+)", line.split(":", 1)[-1]):
                if num:
                    c, o = gh(["issue", "view", num, "--repo", a.repo, "--json", "state"])
                    if c == 0 and json.loads(o).get("state") == "OPEN":
                        warnings.append(f"depends_on #{num} is still OPEN — a fresh maker can't take this "
                                        f"green until it lands (single-unit assertion fails, docs/11 §4b).")
    # (c) MUST written in EARS? A body with a MUST/acceptance section but no EARS keyword is prose
    # ("auth works") the gate can't test (docs/11 §4b). Shape check: does an acceptance line use one
    # of WHEN/WHILE/IF/WHERE/SHALL? Only checked if the Issue actually has a MUST/acceptance section.
    low_body = body.lower()
    if ("must" in low_body or "acceptance" in low_body) and "shall" not in low_body \
            and not any(kw in body for kw in ("WHEN ", "WHILE ", "IF ", "WHERE ")):
        warnings.append("the MUST/acceptance criteria are not in EARS (no WHEN/WHILE/IF/WHERE/SHALL) — "
                        "prose like \"auth works\" isn't testable; rewrite each as an EARS pattern "
                        "(docs/11 §4b), so the gate has a checkable bar.")
    if warnings:
        print(f"RE-SPLIT / RESHAPE CANDIDATE — issue #{a.issue} may not be ready for a no-context maker:")
        for w in warnings:
            print(f"  · {w}")
        print("(shape warning only — whether the split/spec is GOOD stays with the skeptic, docs/12 §6.)")
        return 10
    print(f"issue #{a.issue}: shape OK (one territory, deps landed, acceptance in EARS).")
    return 0


def cmd_candidate_id(a):
    """Derive a backlog candidate's id DETERMINISTICALLY from what it IS (docs/11 §0, reproducibility F4).

    `candidate_id` is the backlog/dedup/WIP key and the ledger's `--natural-key`. If it were authored
    freely, running discovery/decomposition twice on the same gap would mint two ids — the same spec +
    ledger would yield a different backlog, and a replay would duplicate rather than no-op. So the id is
    a pure function of (role, contract_ref, gap), normalized (lowercased, whitespace-collapsed) so that
    casing/spacing differences do not change it — only a genuinely different gap does.

    This lives in a tool rather than in each command's prose because the fields are joined on a UNIT
    SEPARATOR (\\x1f): an unambiguous delimiter that cannot appear in a title, so ("auth","obj1") and
    ("aut","hobj1") cannot collide into one id. A shell-echoed one-liner loses that byte (echo eats the
    escape) and silently degrades to bare concatenation — which collides, and a collision means the
    second task's ledger append is swallowed as an idempotent replay and it never enters the backlog."""
    import hashlib
    import re
    norm = re.sub(r"\s+", " ", a.gap.strip().lower())
    key = "\x1f".join([a.role, a.contract, norm])
    print("cand-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12])
    return 0


def _manifest_rows(path):
    """Parse coverage-manifest.md (docs/11 §0a, the FIXED name) into rows.

    The manifest is a markdown table whose columns are {rfp_capability, owning_role, deliverable,
    acceptance} — the RFP→contract coverage map /org-found emits. We read the header to locate the
    columns by NAME (not position), so a manifest that adds a column still parses. Rows whose
    rfp_capability cell is empty or a separator are skipped.

    A non-table line ENDS the table. This matters: /org-found emits an explicit EXCLUDE list alongside
    the manifest, so a second table below it is expected. Without the reset, that table's rows would be
    read as must-haves — and since the decomposition agent is told to work until coverage-check is
    green, it would mint task Issues for exactly the scope the CEO cut. A table is a contiguous block of
    `|` lines; anything else closes it."""
    import io
    rows = []
    with io.open(path, encoding="utf-8") as fh:
        header, idx = None, {}
        for line in fh:
            if not line.lstrip().startswith("|"):
                header, idx = None, {}     # blank/prose line ends this table (see docstring)
                continue
            cells = [c.strip().strip("`*") for c in line.strip().strip("|").split("|")]
            if header is None:
                header = [c.lower().replace(" ", "_") for c in cells]
                idx = {name: i for i, name in enumerate(header)}
                if "rfp_capability" not in idx:      # not the manifest table — keep looking
                    header = None
                continue
            if all(set(c) <= set("-: ") for c in cells):
                continue                              # the |---|---| separator
            def get(name):
                i = idx.get(name)
                return cells[i] if i is not None and i < len(cells) else ""
            cap = get("rfp_capability")
            if not cap or cap.startswith("<"):
                continue
            rows.append({"rfp_capability": cap, "owning_role": get("owning_role"),
                         "deliverable": get("deliverable"), "acceptance": get("acceptance")})
    return rows


def cmd_coverage_check(a):
    """DECOMPOSITION COVERAGE gate (docs/11 §0a/§4b): every must-have row in coverage-manifest.md must
    have reached at least one open-or-closed task Issue, and every such Issue must trace back to a row.

    /org-found's O10 lint proves each must-have has ONE owning contract; that is coverage at the
    *design* layer. This is the same guarantee one layer down, at the *decomposition* layer: a
    must-have that never became a task Issue is silently unbuilt — the coverage gap reappears exactly
    where it is hardest to see. The trace key is the `coverage_row:` trailer /org-decompose writes into
    each task Issue body (the rfp_capability verbatim), so the check is mechanical, not fuzzy-matched.

    Exit 0 = every must-have covered · 10 = uncovered rows (or orphan Issues) · 2 = usage/gh error."""
    try:
        rows = _manifest_rows(a.manifest)
    except OSError as e:
        print(f"cannot read manifest {a.manifest}: {e}", file=sys.stderr)
        return 2
    if not rows:
        print(f"no manifest rows parsed from {a.manifest} — expected a markdown table with an "
              f"`rfp_capability` column (docs/11 §0a).", file=sys.stderr)
        return 2
    code, out = gh(["issue", "list", "--repo", a.repo, "--label", "orgforge:kind:task",
                    "--state", "all", "--limit", "500", "--json", "number,title,body,state,labels"])
    if code != 0:
        print(f"gh error listing task Issues: {out}", file=sys.stderr)
        return 2
    try:
        issues = json.loads(out)
    except Exception as e:
        print(f"parse: {e}", file=sys.stderr)
        return 2

    def covered_rows(body):
        """The coverage_row: trailers in an Issue body (one Issue may serve several rows).

        Strip the markdown decoration BEFORE splitting on the colon: an agent writing the Issue body in
        the org's output_language naturally bolds a label (`**coverage_row:** X`), and splitting the raw
        line would yield "** X" → " X" — a leading space that fails the exact match, reporting a GAP for
        a row that is in fact covered and sending the operator to mint a duplicate Issue."""
        found = []
        for line in (body or "").splitlines():
            clean = line.strip().lstrip("*-`> ")
            if clean.lower().startswith("coverage_row:"):
                val = clean.split(":", 1)[1].strip().strip("`* ")
                if val:
                    found.append(val)
        return found

    claimed = {}
    orphans = []           # any task Issue with no trailer (self-raised items legitimately have none)
    mandate_orphans = []   # RFP-derived (orgforge:mandate) with no trailer — that IS a defect
    for it in issues:
        cs = covered_rows(it.get("body"))
        if not cs:
            names = [l.get("name", "") for l in (it.get("labels") or [])]
            (mandate_orphans if "orgforge:mandate" in names else orphans).append(it["number"])
        for c in cs:
            claimed.setdefault(c, []).append(it["number"])

    uncovered = [r for r in rows if r["rfp_capability"] not in claimed]
    unknown = sorted(set(claimed) - {r["rfp_capability"] for r in rows})

    for r in rows:
        hits = claimed.get(r["rfp_capability"], [])
        mark = "ok " if hits else "GAP"
        where = ", ".join(f"#{n}" for n in hits) if hits else "— no task Issue"
        print(f"  [{mark}] {r['rfp_capability']}  ({r['owning_role'] or '?'})  → {where}")
    print(f"\n{len(rows) - len(uncovered)}/{len(rows)} must-have rows covered by task Issues.")
    rc = 0
    if uncovered:
        print(f"\nCOVERAGE GAP — {len(uncovered)} must-have(s) never became a task Issue:", file=sys.stderr)
        for r in uncovered:
            print(f"  · {r['rfp_capability']} (owner: {r['owning_role'] or '?'})", file=sys.stderr)
        print("Decompose these before starting work — an unowned must-have is silently unbuilt "
              "(docs/11 §0a).", file=sys.stderr)
        rc = 10
    if unknown:
        print(f"\nORPHAN trailers — coverage_row values matching no manifest row: {unknown}",
              file=sys.stderr)
        print("Either the manifest changed or a trailer is mistyped; the trailer must be the "
              "rfp_capability verbatim.", file=sys.stderr)
        rc = 10
    if mandate_orphans:
        # An RFP-derived task (source: mandate) with NO trailer at all is the likeliest decomposition
        # mistake, and the one the row-side check cannot see: if some OTHER Issue happens to cover the
        # same row, the manifest reads green while this task floats unattached to any requirement.
        # A mistyped trailer already fails as an orphan; a MISSING one must fail the same way.
        print(f"\nUNTRACED MANDATE TASKS — {len(mandate_orphans)} RFP-derived task Issue(s) carry no "
              f"`coverage_row:` trailer: {', '.join('#' + str(n) for n in mandate_orphans)}",
              file=sys.stderr)
        print("Every orgforge:mandate task must name the manifest row it serves (docs/11 §0a). Add the "
              "trailer, or relabel it orgforge:self if it is genuinely self-raised.", file=sys.stderr)
        rc = 10
    if orphans:
        print(f"\nNOTE: {len(orphans)} task Issue(s) carry no `coverage_row:` trailer "
              f"({', '.join('#' + str(n) for n in orphans[:10])}{' …' if len(orphans) > 10 else ''}) — "
              f"self-raised items from /org-discover are expected here; RFP-derived tasks are not.")
    return rc


def cmd_needs_human(a):
    """CEO（人間）にしか実行できない前提条件を Issue として立てる（docs/11 §0c）。

    **なぜ専用のコマンドが要るのか。** org は自分が作れる作業だけを Issue にし、人間に頼むものは
    コマンドの散文に落としていた。実地の founding で3件（Supabase プロジェクト作成 / Google OAuth
    クライアント登録 / GitHub のブランチ保護設定）がセッションの文章の中にしか存在せず、Issue にも
    台帳にも残らなかった。結果:

      - セッションが切れたら消える（/org-resume でも復元されない）
      - `/org` が GREEN と出すのに、実際は人間待ちで着手できない Issue がある
      - `ready` がブロック済みのタスクを maker に渡す（人間待ちを表現する手段がなかった）
      - coverage-check は「Issue になったか」しか見ないので 66/66 と表示される

    **人間への依頼こそ、忘れられると最も長く止まる。** `orgforge:needs-human` ラベルは
    `/org-init` が作っていたのに、それを立てる手順がどのコマンドにも無く、使用実績は 0 件だった。
    このコマンドがその穴を埋める。

    立てた Issue は通常の task と同じ形なので、下流タスクの `--depends` で縛れる — 人間の作業が
    終わって close されるまで、それに依存する task は `ready` に出てこない。"""
    labels = ["orgforge:needs-human", "orgforge:kind:task"]
    ensure = [("orgforge:needs-human", "d93f0b"), ("orgforge:kind:task", "bfd4f2")]
    if a.objective:
        lbl = f"orgforge:objective:{a.objective}"
        labels.append(lbl); ensure.append((lbl, "5319e7"))
    existing, state = _find_open_issue(a.repo, a.title, a.objective)
    if existing is not None:
        print(f"issue #{existing} already exists for {a.title!r} ({state}) — idempotent no-op.")
        return 0
    _ensure_labels(a.repo, ensure)
    body = a.body or ""
    body += ("\n\n---\n**これは CEO（人間）にしか実行できない作業です。** org は着手できません。\n"
             "完了したらこの Issue を close してください — 下流のタスクが自動的に ready になります。")
    if a.blocks:
        blocked = ", ".join(f"#{b.strip().lstrip('#')}" for b in a.blocks.split(",") if b.strip())
        body += f"\n\n**この作業が終わるまで着手できないもの:** {blocked}"
    args = ["issue", "create", "--repo", a.repo, "--title", a.title, "--body", body]
    for l in labels:
        args += ["--label", l]
    code, out = gh(args)
    if code != 0:
        print(f"gh error creating needs-human issue: {out}", file=sys.stderr)
        return 2
    print(out.strip())
    n = _issue_number(out)
    if n and a.parent:
        ok, detail = _link_sub_issue(a.repo, int(str(a.parent).lstrip("#")), n)
        print(detail if ok else f"WARN: {detail}", file=(sys.stdout if ok else sys.stderr))
    if n:
        print(f"\nNEXT: これに依存する task の body に `Depends on: #{n}` を書くこと。"
              f"そうすれば人間の作業が終わるまで `ready` に出てこない。")
    return 0


def cmd_ready(a):
    # list open Issues labeled orgforge:ready, unclaimed, with no open dependency
    code, out = gh(["issue", "list", "--repo", a.repo, "--label", "orgforge:ready",
                    "--state", "open", "--json", "number,title,labels,body"])
    if code != 0:
        print(f"gh error: {out}", file=sys.stderr)
        return 2
    try:
        issues = json.loads(out)
    except Exception as e:
        print(f"parse: {e}", file=sys.stderr)
        return 2
    kind = getattr(a, "kind", None) or "task"   # default: only TASKS are workable ready items
    ready = []
    for it in issues:
        names = [l["name"] for l in it.get("labels", [])]
        if any(n.startswith(CLAIM_PREFIX) for n in names):
            continue   # already claimed
        # kind filter: an objective Issue is a parent/roll-up, not a claimable unit of work. Default to
        # tasks; pass --kind objective to list objectives, or --kind any for both.
        if kind != "any":
            it_kind = next((n[len("orgforge:kind:"):] for n in names
                            if n.startswith("orgforge:kind:")), "task")
            if it_kind != kind:
                continue
        # dependency: parse "Depends on: #n, #m"; ready only if all referenced issues are closed
        body = it.get("body") or ""
        deps = []
        for line in body.splitlines():
            if line.lower().startswith("depends on:"):
                deps = [t.strip().lstrip("#") for t in line.split(":", 1)[1].split(",") if t.strip()]
        blocked = False
        for d in deps:
            c, o = gh(["issue", "view", d, "--repo", a.repo, "--json", "state"])
            if c == 0 and json.loads(o).get("state") == "OPEN":
                blocked = True
                break
        if not blocked:
            ready.append(it["number"])
    print(json.dumps({"ready": ready}))
    return 0


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
