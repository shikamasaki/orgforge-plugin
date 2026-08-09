"""Shared parts of github_sync — invoking gh, resolving Issue labels/numbers, idempotency
markers.

Only what every subcommand uses belongs here."""

import hashlib
import json
import os
import re
import subprocess
import sys


CLAIM_PREFIX = "orgforge:claimed:"


# Points at tools/. **This file lives in tools/ghsync/, so go up one parent.**
# The path origin is kept in one place — resolve `__file__` separately in each spot and a change of
# hierarchy leaves some of them unfixed (which is what happened to _agents_dir and _seam in
# 0.22.0).
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


# GitHub refuses a label longer than this. Measured against the API, not inferred:
#   HTTP 422: Validation Failed — name is too long (maximum is 50 characters)
GITHUB_LABEL_MAX = 50


def label_too_long(name):
    """The label GitHub will refuse, or None. Length is counted the way GitHub counts it."""
    return len(name) > GITHUB_LABEL_MAX


def _ensure_labels(repo, names):
    """Create every label, and REPORT the ones GitHub refuses.

    `check=False` used to swallow the failure, and the very next call created an Issue *with* that
    label — so the operation died at `gh error creating issue: could not add label` with no hint
    that a label creation had already failed and why. In the field an agent read that as "the
    repository is not initialised for OrgForge" and went looking for a setup command that does not
    exist, when the real cause was a 53-character label: GitHub's limit is 50.

    A silent failure that surfaces one call later as a different error is worse than the error
    itself, because it sends the reader to the wrong place.
    """
    failed = []
    for name, color in names:
        if label_too_long(name):
            failed.append((name, f"{len(name)} characters — GitHub allows {GITHUB_LABEL_MAX}"))
            continue
        code, out = gh(["label", "create", name, "--repo", repo,
                        "--color", color, "--force"], check=False)
        if code != 0:
            failed.append((name, (out or "").strip().splitlines()[-1] if out else "unknown error"))
    return failed


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


# Milestones: without "what was done" recorded here, there is no way to reconstruct it later.
# Interim progress (progress_recorded) may be logged lightly, but a cycle's milestone is an audit
# point, so real output is required.


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


def banner():
    """One line on stderr giving the running version and cwd (same reason as org_cycle —
    docs/11)."""
    ver = "?"
    for c in (os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json"),
              os.path.join(HERE, "..", "integrations", "claude-code",
                           ".claude-plugin", "plugin.json")):
        try:
            with open(c, encoding="utf-8") as f:
                ver = json.load(f).get("version", "?")
            break
        except Exception:
            continue
    # **Do not pollute machine-readable output.** Even written to stderr, a consumer merging with
    # 2>&1 ends up with broken JSON (a test failed with JSONDecodeError in practice). It is a
    # convenience for humans, so it stays silent under --json or ORG_QUIET — breaking something for
    # the sake of convenience does not add up.
    if "--json" in sys.argv or os.environ.get("ORG_QUIET"):
        return
    print(f"[orgforge {ver} @ {os.getcwd()}]", file=sys.stderr)
