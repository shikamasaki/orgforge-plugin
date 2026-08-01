#!/usr/bin/env python3
"""discover — find the org's state from the working directory, with no environment setup.

An org is a *place on disk*, not a set of shell variables. `.orgforge/ledger/` sits next to
`organization.yaml`, and the backlog repo is whatever `git remote origin` points at — both are
discoverable facts about the checkout. Requiring an operator to restate them in `.envrc` adds a
step that can be skipped, forgotten, or (worse) written with absolute paths that are wrong on the
next machine. That last failure is the one that matters here: the whole point of putting the spec in
the Issue is that ANY environment can pick up the work, and an org whose state is addressed by
`/Users/someone/proj/.orgforge/ledger` is not portable no matter how good the Issue is.

So: **discover first, environment only as an override.** The precedence is

    explicit argument  >  environment variable  >  discovery from the filesystem/git

which keeps every existing override working (CI pins, a ledger deliberately kept outside the repo,
a test fixture) while making the zero-setup path the default. Discovery walks up from the starting
directory to the VCS root, so it works from any subdirectory of the checkout — the same reasoning
`repro_lint._vcs_root` already uses for a monorepo's CI.

Nothing here writes; discovery is a pure read of what is already true.

  discover.py ledger [--start DIR]   print the ledger root      (exit 3 if none found)
  discover.py repo   [--start DIR]   print owner/name for the backlog repo
  discover.py root   [--start DIR]   print the org root (the dir holding organization.yaml)
  discover.py env    [--start DIR]   print all of them as shell exports (for a human who wants them)
"""
import argparse
import hashlib
import os
import subprocess
import sys

# the marker that says "an org lives here" — the chart is the one file founding always writes
ORG_MARKERS = ("organization.yaml", ".orgforge")
GOVERNANCE_FILES = ("organization.yaml", "constitution.yaml", "ledger-schema.yaml",
                    "moves.yaml", "role-settings.yaml", "schedule.yaml", "sensors.yaml")


def org_root(start=None):
    """The directory holding the org's spec/state, found by walking up from `start`.

    Accepts either marker: `organization.yaml` (post-founding) or an `.orgforge/` directory
    (post-init, pre-founding) — so discovery works between /org-init and /org-found too."""
    d = os.path.abspath(start or os.getcwd())
    while True:
        if any(os.path.exists(os.path.join(d, m)) for m in ORG_MARKERS):
            if not _is_worktree(d):
                return d
            primary = _primary_worktree(d)
            if primary and any(os.path.exists(os.path.join(primary, m)) for m in ORG_MARKERS):
                return primary
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _is_worktree(d):
    """`begin` が作った Issue ごとの作業ツリーか（`.orgforge/wt/issue-N/`）。

    **worktree を org root と誤認すると、迷子の台帳ができる。** doctrine と evidence を
    git 追跡下に置いた結果、worktree にも `.orgforge/` が復元され、それが ORG_MARKERS に
    当たって親の探索が止まる。そこで subagent が `ledger append` を打つと worktree 側の
    空の台帳に書かれ、`appended seq=1` が返る — 実判定が本体の台帳から消える。
    実地で1日に3回起き、実判定4件が迷子になった。

    警告で防ぐ設計は破れる（gate が一度踏んだ）ので、構造で防ぐ: worktree の中からは
    必ず親を辿る。判定は `git worktree` の実体（`.git` が**ファイル**でその中身が
    `gitdir:` を指す）で行う — パス名ではなくツリーの性質で見る。
    """
    dotgit = os.path.join(d, ".git")
    if not os.path.isfile(dotgit):
        return False
    try:
        with open(dotgit, encoding="utf-8") as f:
            head = f.read(256)
    except OSError:
        return False
    return head.startswith("gitdir:") and "/worktrees/" in head


def _primary_worktree(d):
    """Return the main worktree sharing ``d``'s git common directory.

    A linked worktree can live anywhere on disk, so parent walking is insufficient. Git's
    porcelain worktree list is the authority and its first entry is the primary worktree. Keep
    failure quiet: callers can still continue the ordinary parent walk for non-git directories.
    """
    try:
        p = subprocess.run(["git", "-C", d, "worktree", "list", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        if p.returncode != 0:
            return None
        for line in (p.stdout or "").splitlines():
            if line.startswith("worktree "):
                return os.path.abspath(line[len("worktree "):])
    except Exception:
        pass
    return None


def subject_root(start=None):
    """The checkout whose commit/files a command is measuring.

    This deliberately differs from :func:`org_root` inside a linked worktree: governance comes
    from the primary worktree, while review/integration evidence must describe the caller's real
    checkout rather than silently switching the subject under review.
    """
    d = os.path.abspath(start or os.getcwd())
    try:
        p = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10)
        if p.returncode == 0 and (p.stdout or "").strip():
            return os.path.abspath(p.stdout.strip())
    except Exception:
        pass
    return None


def _file_digest(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return None
    except OSError:
        return "unreadable"


def governance_divergences(start=None):
    """Describe governance files that differ in the caller's linked worktree.

    Resolution always uses the authoritative primary checkout, but divergence is not hidden: the
    stale checkout remains useful subject evidence and operators need to know its embedded rules
    no longer match the rules actually enforcing the organization.
    """
    authority = org_root(start)
    subject = subject_root(start)
    if not authority or not subject or os.path.realpath(authority) == os.path.realpath(subject):
        return []
    out = []
    for rel in GOVERNANCE_FILES:
        authoritative = _file_digest(os.path.join(authority, rel))
        observed = _file_digest(os.path.join(subject, rel))
        if authoritative != observed:
            out.append({"path": rel, "authoritative": authoritative, "subject": observed,
                        "authority_root": authority, "subject_root": subject})
    return out


def ledger_root(start=None):
    """The ledger root: explicit env wins, else `<org root>/.orgforge/ledger`.

    Returns the path even if it does not exist yet — ledger.py creates it on first append, and a
    caller that needs existence can test for it. Returning None only means "no org here at all"."""
    env = os.environ.get("ORG_LEDGER_ROOT")
    if env:
        return env
    root = org_root(start)
    return os.path.join(root, ".orgforge", "ledger") if root else None


def backlog_repo(start=None):
    """The GitHub `owner/name` for the backlog: env wins, else parsed from `git remote origin`.

    Parses the remote locally rather than calling `gh` — discovery must not need the network or an
    authenticated CLI just to answer "which repo is this". Returns None when there is no GitHub
    remote (a legitimately ledger-only org)."""
    env = os.environ.get("ORG_GITHUB_REPO")
    if env:
        return env
    cwd = org_root(start) or start or os.getcwd()
    try:
        p = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=10)
        if p.returncode != 0:
            return None
        url = (p.stdout or "").strip()
    except Exception:
        return None
    if not url:
        return None
    # git@github.com:owner/name.git  |  https://github.com/owner/name(.git)
    for sep in ("github.com:", "github.com/"):
        if sep in url:
            tail = url.split(sep, 1)[1]
            tail = tail[:-4] if tail.endswith(".git") else tail
            parts = [x for x in tail.strip("/").split("/") if x]
            return "/".join(parts[:2]) if len(parts) >= 2 else None
    return None


def constitution(start=None):
    env = os.environ.get("ORG_CONSTITUTION")
    if env:
        return env
    root = org_root(start)
    if not root:
        return None
    p = os.path.join(root, "constitution.yaml")
    return p if os.path.exists(p) else None


def _sub_root(name, start=None, env_key=None):
    env = os.environ.get(env_key) if env_key else None
    if env:
        return env
    root = org_root(start)
    return os.path.join(root, ".orgforge", name) if root else None


def main(argv):
    p = argparse.ArgumentParser(prog="discover", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("what", choices=("ledger", "repo", "root", "constitution",
                                    "doctrine", "conventions", "env"))
    p.add_argument("--start", help="directory to search from (default: cwd)")
    a = p.parse_args(argv[1:])
    fn = {
        "root": org_root,
        "ledger": ledger_root,
        "repo": backlog_repo,
        "constitution": constitution,
        "doctrine": lambda s: _sub_root("doctrine", s, "ORG_DOCTRINE_ROOT"),
        "conventions": lambda s: _sub_root("conventions", s, "ORG_CONVENTIONS_ROOT"),
    }
    if a.what == "env":
        root = org_root(a.start)
        if not root:
            print("discover: no org found (no organization.yaml or .orgforge/ walking up from "
                  f"{os.path.abspath(a.start or os.getcwd())})", file=sys.stderr)
            return 3
        for key, val in (("ORG_LEDGER_ROOT", ledger_root(a.start)),
                         ("ORG_DOCTRINE_ROOT", _sub_root("doctrine", a.start, "ORG_DOCTRINE_ROOT")),
                         ("ORG_CONVENTIONS_ROOT", _sub_root("conventions", a.start,
                                                            "ORG_CONVENTIONS_ROOT")),
                         ("ORG_CONSTITUTION", constitution(a.start)),
                         ("ORG_GITHUB_REPO", backlog_repo(a.start))):
            if val:
                print(f'export {key}="{val}"')
        return 0
    val = fn[a.what](a.start)
    if not val:
        print(f"discover: could not determine {a.what} from "
              f"{os.path.abspath(a.start or os.getcwd())}", file=sys.stderr)
        return 3
    print(val)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
