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
                                           append a WORK-LOG comment to a task Issue on a milestone
                                           event (cycle_started/progress_recorded/phase_admitted/
                                           cycle_completed …), so progress accrues on the Issue as it
                                           happens. Idempotent per --event-id (a replay logs once).
  ready   --repo R [--kind task|objective|any]
                                           list Issues ready to work (no open dependency, unclaimed);
                                           default lists TASKS only (objectives are parents, not work)
  branch  --repo R --issue N [--create] [--base B]
                                           print the DETERMINISTIC feature branch for a task Issue —
                                           `feat/issue-N-<slug>` off `develop` (docs/11 §4c). --create
                                           also `git checkout -b` it. Same Issue ⇒ same branch (repro).
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
    """Return an existing OPEN Issue number matching this backlog item's natural key (title, and the
    objective label if given), else None. The backlog projection must be idempotent (docs/11 §0): a
    replayed discovery/founding cycle, or a web + local session projecting the same ledger, must not
    mint duplicate Issues."""
    code, out = gh(["issue", "list", "--repo", repo, "--state", "open",
                    "--search", title, "--json", "number,title,labels"])
    if code != 0:
        return None   # can't check — fall through to create (best effort; a dup is recoverable)
    try:
        for it in json.loads(out):
            if it.get("title") != title:
                continue
            if objective:
                names = [l["name"] for l in it.get("labels", [])]
                if f"orgforge:objective:{objective}" not in names:
                    continue
            return it["number"]
    except Exception:
        return None
    return None


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
    existing = _find_open_issue(a.repo, a.title, a.objective)
    if existing is not None:
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


def cmd_log(a):
    """Append a WORK-LOG comment to a task Issue on a milestone event (cycle_started, progress_recorded,
    phase_admitted, cycle_completed, …). The ledger stays the SSoT — this comment is its projection onto
    the Issue so the human (on a phone) sees progress accrue without opening the ledger.

    IDEMPOTENT (docs/11 §0): each comment carries a hidden marker `<!-- orgforge:event:<id> -->`. If a
    comment with this event id already exists on the Issue, we no-op — a replayed/retried cycle logs the
    same milestone once, never twice. Pass --event-id (the ledger event's id) to key the dedup; without
    it we fall back to a hash of (event, detail)."""
    marker_key = a.event_id or ("h" + str(abs(hash((a.event, a.detail or "")))))
    marker = f"<!-- orgforge:event:{marker_key} -->"
    # dedup: has this milestone already been logged on the Issue?
    code, out = gh(["issue", "view", str(a.issue), "--repo", a.repo, "--json", "comments"])
    if code == 0:
        try:
            for c in json.loads(out).get("comments", []):
                if marker in (c.get("body") or ""):
                    print(f"log: event {marker_key} already on issue #{a.issue} — idempotent no-op "
                          f"(docs/11 §0).")
                    return 0
        except Exception:
            pass   # can't read comments — fall through and post (a rare dup is recoverable)
    # the visible line: a compact, human-readable milestone. detail is optional free text.
    line = f"**{a.event}**"
    if a.phase:
        line += f" · phase: `{a.phase}`"
    if a.detail:
        line += f" — {a.detail}"
    body = f"{line}\n\n{marker}"
    code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", body])
    if code != 0:
        print(f"gh error posting work-log comment: {out}", file=sys.stderr)
        return 2
    print(f"logged {a.event} to issue #{a.issue}.")
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
        print(f"gh error: {out}", file=sys.stderr)
        return 2
    try:
        title = json.loads(out).get("title", "")
    except Exception:
        title = ""
    name = f"feat/issue-{a.issue}-{_slug(title)}"
    print(name)
    if getattr(a, "create", False):
        base = getattr(a, "base", None) or "develop"
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
            for tok in line.split(":", 1)[-1].split(","):
                num = "".join(ch for ch in tok if ch.isdigit())
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
        q.add_argument("--repo", required=True); q.add_argument("--issue", required=True, type=int)
        q.add_argument("--agent", required=True)
    q = sub.add_parser("create")
    q.add_argument("--repo", required=True); q.add_argument("--title", required=True)
    q.add_argument("--body"); q.add_argument("--objective"); q.add_argument("--source")
    q.add_argument("--depends"); q.add_argument("--priority", type=int)
    q.add_argument("--kind", choices=("objective", "task"), default="task",
                   help="objective = the big-picture RFP/objective Issue (parent); "
                        "task = a department's unit of work (a sub-issue of its objective)")
    q.add_argument("--dept", help="the department this task belongs to (labels orgforge:dept:<name>)")
    q.add_argument("--parent", help="parent Issue number: link this task as a NATIVE GitHub sub-issue "
                                    "of that objective (GitHub shows the hierarchy + progress roll-up)")
    q = sub.add_parser("stage")
    q.add_argument("--repo", required=True); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--stage", required=True)
    q = sub.add_parser("ready"); q.add_argument("--repo", required=True)
    q.add_argument("--kind", choices=("task", "objective", "any"), default="task",
                   help="which kind of Issue to list as ready (default: task — objectives are "
                        "parent/roll-up Issues, not claimable units of work)")
    q = sub.add_parser("log")
    q.add_argument("--repo", required=True); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--event", required=True,
                   help="the milestone ledger event class (cycle_started, progress_recorded, "
                        "phase_admitted, cycle_completed, …)")
    q.add_argument("--detail", help="optional free-text detail for the log line")
    q.add_argument("--phase", help="the SDLC phase, if this milestone is a phase transition")
    q.add_argument("--event-id", dest="event_id",
                   help="the ledger event's id — keys the idempotent dedup so a replay logs once")
    q = sub.add_parser("branch")
    q.add_argument("--repo", required=True); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--create", action="store_true",
                   help="also `git checkout -b <name> <base>` in the current repo (idempotent)")
    q.add_argument("--base", help="the branch to fork from (default: develop, docs/11 §4c)")
    q = sub.add_parser("split-check")
    q.add_argument("--repo", required=True); q.add_argument("--issue", required=True, type=int)
    a = p.parse_args(argv[1:])
    return {"claim": cmd_claim, "release": cmd_release, "create": cmd_create,
            "stage": cmd_stage, "ready": cmd_ready, "log": cmd_log,
            "branch": cmd_branch, "split-check": cmd_split_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
