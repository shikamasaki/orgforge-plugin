#!/usr/bin/env python3
"""repro_lint — the Level-2 reproducibility gate (docs/11 §4a).

An IT business company's output is a REPOSITORY, and a repository is only reproducible if a stranger
who clones it gets the same system the maker did: same install, same tests, same build, on any machine,
any day. The generated CODE may vary (LLM non-determinism, accepted); the DEV EXPERIENCE must not.

This tool checks a candidate repository against the reproducibility admission standard the SDLC mold
forces at the implement → test → deploy gates. It is DETERMINISTIC (same repo ⇒ same verdict) and is
meant to be run BY THE GATE, not trusted from a maker's "I verified it" claim.

It checks presence/shape, not correctness — "is there a committed lockfile", not "does install work"
(the gate re-runs setup+test from a clean clone for that). Presence is the cheap, deterministic first
tooth; the clean-clone re-run is the expensive second one the deploy pipeline performs.

Usage:
  repro_lint check <repo_dir> [--phase implement|test|deploy] [--json]

Exit: 0 = all required artifacts for the phase present · 10 = one or more missing (gate should HOLD) ·
      2 = usage/error.

Each artifact is tagged with the earliest phase that requires it, so an implement-phase candidate is
held to a lighter bar than a deploy-phase one (docs/11 §4a table):
  implement→test : a lockfile + populated manifest, a pinned toolchain
  test→deploy    : a one-command setup + test documented in a README, idempotent migrations, .env.example
  deploy         : a committed CI workflow that runs setup+test from clean
"""
import argparse
import glob
import json
import os
import sys

PHASES = ["implement", "test", "deploy"]


def _exists(repo, *names):
    """True if any of the given repo-relative paths exists (glob-aware)."""
    for n in names:
        if glob.glob(os.path.join(repo, n)) or glob.glob(os.path.join(repo, "**", n), recursive=True):
            return True
    return False


def _read(repo, name):
    for p in glob.glob(os.path.join(repo, name)) + glob.glob(os.path.join(repo, "**", name), recursive=True):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except Exception:
            continue
    return ""


# ── the checks. each returns (ok: bool, detail: str). tagged with the phase that first requires it. ──
def check_lockfile(repo):
    # a committed lockfile so `clone → install` resolves one dependency tree on every machine/day
    locks = ["package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb",
             "poetry.lock", "Pipfile.lock", "requirements.txt", "Cargo.lock", "go.sum",
             "composer.lock", "Gemfile.lock"]
    if _exists(repo, *locks):
        return True, "a committed lockfile is present"
    return False, ("no committed lockfile (package-lock.json / pnpm-lock.yaml / poetry.lock / Cargo.lock "
                   "/ go.sum …). `clone → install` will resolve different versions over time.")


def check_manifest_populated(repo):
    # a manifest that actually declares its dependencies (not an empty package.json)
    pj = _read(repo, "package.json")
    if pj:
        try:
            d = json.loads(pj)
            if d.get("dependencies") or d.get("devDependencies"):
                return True, "package.json declares dependencies"
            return False, "package.json is present but declares NO dependencies (the stack is unpinned)"
        except Exception:
            return False, "package.json is present but is not valid JSON"
    if _exists(repo, "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "Gemfile", "composer.json"):
        return True, "a language manifest is present"
    return False, "no dependency manifest found (package.json / pyproject.toml / Cargo.toml / go.mod …)"


def check_toolchain_pinned(repo):
    # a pinned runtime so the same source builds/tests identically
    if _exists(repo, ".nvmrc", ".tool-versions", ".python-version", "rust-toolchain.toml",
               "rust-toolchain", ".ruby-version", ".go-version"):
        return True, "a toolchain pin file is present"
    pj = _read(repo, "package.json")
    if pj:
        try:
            if json.loads(pj).get("engines"):
                return True, "package.json `engines` pins the runtime"
        except Exception:
            pass
    return False, ("no pinned toolchain (.nvmrc / .tool-versions / engines / rust-toolchain …). "
                   "The runtime that builds/tests the code floats across machines.")


def check_readme_setup(repo):
    # a README with a one-command setup + test path a stranger can follow
    rd = _read(repo, "README.md") or _read(repo, "README") or _read(repo, "readme.md")
    if not rd:
        return False, "no README — a stranger has no documented setup/test path"
    low = rd.lower()
    has_setup = any(k in low for k in ("install", "setup", "getting started", "make setup", "npm install",
                                       "pnpm install", "poetry install", "cargo build", "go build"))
    has_test = any(k in low for k in ("test", "npm test", "make test", "pytest", "cargo test", "go test"))
    if has_setup and has_test:
        return True, "README documents setup and test"
    missing = ", ".join(m for m, ok in (("setup", has_setup), ("test", has_test)) if not ok)
    return False, f"README present but does not document: {missing}"


def check_one_command(repo):
    # a one-command entry point (Makefile target, package.json scripts, taskfile, justfile)
    pj = _read(repo, "package.json")
    if pj:
        try:
            sc = json.loads(pj).get("scripts") or {}
            if sc.get("test") and (sc.get("setup") or sc.get("build") or sc.get("dev") or sc.get("start")):
                return True, "package.json scripts give one-command setup+test"
        except Exception:
            pass
    if _exists(repo, "Makefile", "makefile", "Taskfile.yml", "justfile", "Justfile"):
        return True, "a Makefile/Taskfile/justfile gives one-command entry points"
    return False, ("no one-command setup+test (package.json scripts / Makefile / Taskfile / justfile). "
                   "'verified end-to-end' can't be re-run by a stranger.")


def check_migrations_idempotent(repo):
    # migrations must be re-runnable; bare `create table` (no guard) is not. only checked if migrations exist.
    migs = (glob.glob(os.path.join(repo, "**", "migrations", "*.sql"), recursive=True)
            + glob.glob(os.path.join(repo, "**", "migrate", "*.sql"), recursive=True))
    if not migs:
        return True, "no SQL migrations to check (n/a)"
    unguarded = []
    for m in migs:
        try:
            txt = open(m, encoding="utf-8").read().lower()
        except Exception:
            continue
        # a create without an "if not exists" guard (and no explicit up/down framework marker) is a risk
        if "create table" in txt and "if not exists" not in txt and "-- migrate:" not in txt:
            unguarded.append(os.path.relpath(m, repo))
    if unguarded:
        return False, ("migrations are not re-runnable (bare `create table`, no `if not exists` / no "
                       f"migration-framework guard): {', '.join(unguarded[:3])}")
    return True, "migrations are guarded / re-runnable"


def check_env_example(repo):
    # the SET of required secrets must be discoverable (names only); only required if secrets are used
    if _exists(repo, ".env.example", ".env.sample", ".env.template", "env.example"):
        return True, ".env.example enumerates required config"
    # if there's no sign the app needs env config, this is n/a; heuristic: a .env in .gitignore implies use
    gi = _read(repo, ".gitignore")
    if ".env" in gi:
        return False, (".gitignore ignores .env (so secrets ARE used) but there is no .env.example "
                       "enumerating the required variable names — a stranger's setup fails silently.")
    return True, "no env config surface detected (n/a)"


def _vcs_root(start):
    """Walk up from `start` to the repository root (the dir containing .git), or return `start` if
    none is found. CI config lives at the VCS root by convention, even when the checked app is a
    sub-package (a monorepo's app/ dir) — so a root-only CI must still count for a sub-package check."""
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(start)   # no .git found — fall back to the checked dir
        d = parent


def check_ci(repo):
    # a committed CI workflow that (by convention) runs setup+test from clean — the machine deploy gate.
    # Look BOTH in the checked dir and at the VCS root (CI usually lives at the repo root even when the
    # app is a sub-package), so a monorepo layout (app/ under a root-level .github/) isn't a false HOLD.
    for base in (repo, _vcs_root(repo)):
        if _exists(base, ".github/workflows/*.yml", ".github/workflows/*.yaml",
                   ".gitlab-ci.yml", ".circleci/config.yml", "azure-pipelines.yml"):
            return True, "a committed CI workflow is present"
    return False, ("no committed CI workflow (.github/workflows/…). The deploy gate has no machine form: "
                   "reproducibility is not proven continuously from a clean clone.")


# artifact -> (checker, earliest phase that requires it)
CHECKS = [
    ("lockfile",            check_lockfile,            "implement"),
    ("manifest",            check_manifest_populated,  "implement"),
    ("toolchain-pin",       check_toolchain_pinned,    "implement"),
    ("readme-setup",        check_readme_setup,        "test"),
    ("one-command",         check_one_command,         "test"),
    ("idempotent-migrations", check_migrations_idempotent, "test"),
    ("env-example",         check_env_example,         "test"),
    ("ci-from-clean",       check_ci,                  "deploy"),
]


def cmd_check(a):
    if not os.path.isdir(a.repo):
        print(f"repro_lint: {a.repo} is not a directory", file=sys.stderr)
        return 2
    phase = a.phase or "deploy"   # default: hold to the full bar
    if phase not in PHASES:
        print(f"repro_lint: --phase must be one of {PHASES}", file=sys.stderr)
        return 2
    required_through = PHASES.index(phase)
    results = []
    failed = []
    for name, fn, req_phase in CHECKS:
        required = PHASES.index(req_phase) <= required_through
        ok, detail = fn(a.repo)
        results.append({"artifact": name, "required": required, "ok": ok, "detail": detail})
        if required and not ok:
            failed.append(name)
    if a.json:
        print(json.dumps({"repo": a.repo, "phase": phase, "passed": not failed,
                          "failed": failed, "checks": results}, ensure_ascii=False, indent=2))
    else:
        print(f"reproducibility check — {a.repo} (phase: {phase}, docs/11 §4a)")
        for r in results:
            mark = "✓" if r["ok"] else ("✗" if r["required"] else "–")
            tag = "" if r["required"] else "  (not required at this phase)"
            print(f"  {mark} {r['artifact']}: {r['detail']}{tag}")
        if failed:
            print(f"\nHELD: {len(failed)} required reproducibility artifact(s) missing "
                  f"for the {phase} gate: {', '.join(failed)}. The repo a stranger clones would not "
                  f"come up the same. (docs/11 §4a)")
        else:
            print(f"\nOK: reproducibility artifacts for the {phase} gate are present.")
    return 10 if failed else 0


def main(argv):
    p = argparse.ArgumentParser(prog="repro_lint", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("check")
    q.add_argument("repo")
    q.add_argument("--phase", choices=PHASES, help="hold the repo to this phase's bar (default: deploy)")
    q.add_argument("--json", action="store_true")
    a = p.parse_args(argv[1:])
    return {"check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
