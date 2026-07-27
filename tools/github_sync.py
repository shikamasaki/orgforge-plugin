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
  create  --repo R --title T [--body B] [--objective O] [--source mandate|self] [--depends 3,7] [--priority N]
                                           mint a backlog Issue with the label set (priority/dep/objective)
  stage   --repo R --issue N --stage S     set the lifecycle label (ready|in-progress|blocked|needs-human|done)
  ready   --repo R                         list Issues that are ready to work (no open dependency, unclaimed)

Labels: orgforge:claimed:<agent> · orgforge:{ready,in-progress,blocked,needs-human,done} ·
        orgforge:objective:<id> · orgforge:{mandate,self} · orgforge:off-ranking

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


def cmd_create(a):
    labels = ["orgforge:ready"]
    ensure = [("orgforge:ready", "1d76db")]
    if a.objective:
        lbl = f"orgforge:objective:{a.objective}"
        labels.append(lbl); ensure.append((lbl, "5319e7"))
    if a.source:
        lbl = f"orgforge:{a.source}"
        labels.append(lbl); ensure.append((lbl, "fbca04"))
    _ensure_labels(a.repo, ensure)
    body = a.body or ""
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
    ready = []
    for it in issues:
        names = [l["name"] for l in it.get("labels", [])]
        if any(n.startswith(CLAIM_PREFIX) for n in names):
            continue   # already claimed
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
    q = sub.add_parser("stage")
    q.add_argument("--repo", required=True); q.add_argument("--issue", required=True, type=int)
    q.add_argument("--stage", required=True)
    q = sub.add_parser("ready"); q.add_argument("--repo", required=True)
    a = p.parse_args(argv[1:])
    return {"claim": cmd_claim, "release": cmd_release, "create": cmd_create,
            "stage": cmd_stage, "ready": cmd_ready}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
