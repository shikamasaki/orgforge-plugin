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

It also enforces the UNREAD-SAFE bar (docs/11 §4e): at parallel-agent throughput nobody reads every
diff, so the defect classes only a careful reader catches must be made unmergeable instead. Those
checks assert the repo has a mechanical rejection layer *configured* — a bounded function
size/complexity, closed type escape hatches, tests, and duplication/dead-code scanning — not that it
currently passes (CI runs it; this is the presence tooth).

Each artifact is tagged with the earliest phase that requires it, so an implement-phase candidate is
held to a lighter bar than a deploy-phase one (docs/11 §4a/§4e table):
  implement→test : a lockfile + populated manifest, a pinned toolchain,
                   a complexity/size ceiling, closed type escapes (§4e)
  test→deploy    : a one-command setup + test documented in a README, idempotent migrations,
                   .env.example, executable tests (§4e)
  deploy         : a committed CI workflow that runs setup+test from clean,
                   duplication/dead-code scanning (§4e)
"""
import argparse
import glob
import json
import os
import re
import sys

PHASES = ["implement", "test", "deploy"]


# Directories whose contents are NOT the repo's own work. Without this exclusion every check reads
# vendored trees, so a dependency's config satisfies the gate on BORROWED evidence: a repo that has
# merely run `npm install` passes lockfile, complexity, type-escapes and tests-present while having
# configured none of them itself. That is the default state of a JS working tree, so it is the
# highest-blast-radius false pass this tool can have.
VENDOR_DIRS = {"node_modules", "vendor", "third_party", "bower_components", ".venv", "venv",
               "site-packages", ".git", "dist", "build", ".next", "target", ".tox", ".mypy_cache",
               "__pycache__", ".pytest_cache", "coverage", ".yarn"}


def _own_file(repo, path):
    """True if `path` is the repo's OWN file — not inside a vendored/generated directory."""
    try:
        rel = os.path.relpath(path, repo)
    except ValueError:
        return False
    return not any(part in VENDOR_DIRS for part in rel.split(os.sep))


def _iter_matches(repo, name):
    """Repo-owned paths matching `name`, at the root or nested, in a STABLE order.

    Sorted because `_read` returns the first match: with two `tsconfig.json`s (a strict one and a lax
    one) glob order would otherwise decide the verdict, contradicting this tool's determinism contract
    (same repo ⇒ same verdict). Shallower paths sort first, so the root config wins over a nested one."""
    seen = []
    for p in glob.glob(os.path.join(repo, name)) + glob.glob(os.path.join(repo, "**", name),
                                                             recursive=True):
        if _own_file(repo, p) and p not in seen:
            seen.append(p)
    return sorted(seen, key=lambda p: (len(os.path.relpath(p, repo).split(os.sep)), p))


def _exists(repo, *names):
    """True if any of the given repo-relative paths exists (glob-aware, vendored dirs excluded)."""
    return any(_iter_matches(repo, n) for n in names)


def _read(repo, name):
    for p in _iter_matches(repo, name):
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


# ── the unread-safe bar (docs/11 §4e) ────────────────────────────────────────────────────────────
# An org that fans out parallel makers produces more diff than any human — or any reviewing agent —
# reads end to end. The answer is not to read faster; it is to make the classes of defect that ONLY a
# careful reader catches impossible to merge. These checks ask whether the repo has a MECHANICAL
# rejection layer configured at all: bounded function size/complexity, a closed type-escape hatch, and
# duplication/dead-code reporting. They check for the layer's PRESENCE and that its bars are actually
# set — running it is CI's job, not this tool's (same presence-not-correctness discipline as above).

def _strip_comments(text):
    """Drop // and /* */ and # comments, so a rule NAMED in a comment is not read as a rule that is SET.

    Without this, `{ /* "strict" would be nice */ }` and `# think about complexity someday` both satisfy
    their gate — the check would be scanning prose about a rule instead of the rule."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", " ", text)
    text = re.sub(r"(?m)(?<![:\w])#(?!\{).*$", " ", text)   # # comments; not a URL fragment / interpolation
    return text


def _linter_configs(repo):
    """Every lint/type config in the repo, as one comment-stripped blob (with the filenames found)."""
    names = ["eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
             ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
             "biome.json", "biome.jsonc", "ruff.toml", ".ruff.toml", "pyproject.toml",
             "setup.cfg", ".flake8", ".golangci.yml", ".golangci.yaml", "clippy.toml",
             ".rubocop.yml", "phpstan.neon", "detekt.yml"]
    blob, found = "", []
    for n in names:
        text = _read(repo, n)
        if text:
            blob += "\n" + _strip_comments(text)
            found.append(n)
    return blob, found


# a rule name followed by a DISABLING value — "off", 0, false, or eslint severity 0.
_DISABLED = r"""["']?\s*[:=]\s*\[?\s*["']?(off|0|false|none|never|disable)\b"""


def _rule_enabled(blob, key):
    """True if `key` appears in `blob` as a rule that is actually ON.

    A bare substring scan is not enough: `"complexity": "off"` contains the token `complexity`, and the
    literal way an agent turns a bar off is therefore the way that satisfies the check. So a hit only
    counts when (a) the token appears as a whole rule name — not as a fragment of an unrelated rule like
    `no-complexity-whatsoever` — and (b) it is not immediately assigned a disabling value."""
    for m in re.finditer(r"(?<![\w-])" + re.escape(key) + r"(?![\w-])", blob):
        tail = blob[m.end():m.end() + 40]
        if re.match(_DISABLED, tail):
            continue          # explicitly turned off — not a bar
        if not re.match(r"""["']?\s*[:=]""", tail):
            continue          # not an assignment (prose, an import, a mention) — not a bar
        return True
    return False


def _config_scope(repo):
    """Lint configs visible to this package: its own, plus the VCS root's (monorepo shared config).

    `check_ci` already walks to the VCS root because CI lives there in a monorepo; lint/tsconfig are
    shared exactly the same way. Without this a correctly-configured monorepo sub-package (`apps/web`
    under a root `eslint.config.js`) is HELD at the implement gate — a false failure blocking the
    standard layout for the kind of app this org builds."""
    blob, found = _linter_configs(repo)
    root = _vcs_root(repo)
    if os.path.abspath(root) != os.path.abspath(repo):
        rblob, rfound = _linter_configs(root)
        blob += "\n" + rblob
        found += [f"{f} (repo root)" for f in rfound]
    return blob, found


def _read_scoped(repo, name):
    """Read `name` from this package, falling back to the VCS root (same monorepo reasoning as above)."""
    text = _read(repo, name)
    if text:
        return text
    root = _vcs_root(repo)
    return _read(root, name) if os.path.abspath(root) != os.path.abspath(repo) else ""


def check_complexity_bounded(repo):
    """A configured ceiling on function size / cyclomatic / cognitive complexity.

    This is the single highest-value unread-safe rule: an over-long, deeply-nested function is where
    the defects a reader would have caught actually hide, and it is the shape an agent produces most
    readily when it keeps appending to a working function instead of decomposing."""
    blob, found = _config_scope(repo)
    if not blob:
        return False, ("no lint config found (eslint/biome/ruff/golangci/rubocop…). Nothing bounds "
                       "function size or complexity, so unbounded functions merge unread.")
    keys = ["max-lines-per-function", "max-lines", "complexity", "cognitive-complexity",
            "max-depth", "max-nested-callbacks", "max-statements", "C901", "mccabe",
            "gocyclo", "cyclop", "funlen", "MethodLength", "AbcSize", "LongMethod"]
    hits = [k for k in keys if _rule_enabled(blob, k)]
    if hits:
        return True, f"complexity/size bars configured ({', '.join(sorted(set(hits))[:4])}) in {found[0]}"
    disabled = [k for k in keys if k in blob]
    if disabled:
        return False, (f"lint config present ({found[0]}) but the size/complexity rules it names "
                       f"({', '.join(sorted(set(disabled))[:4])}) are DISABLED or unset. A bar turned "
                       f"off is not a bar — that is the exact move an agent makes to go green.")
    return False, (f"lint config present ({found[0]}) but NO size/complexity bar "
                   f"(max-lines-per-function / complexity / cognitive-complexity / max-depth). "
                   f"Unbounded functions are where unread defects hide.")


def check_type_escapes_closed(repo):
    """The type system's escape hatches are shut: strict mode on, and `any`/ignore-comments rejected.

    A type checker with `any` and `@ts-ignore` available is advisory — an agent under pressure to make
    the build green will reach for them, and the resulting hole is invisible in a diff nobody reads."""
    ts = _strip_comments(_read_scoped(repo, "tsconfig.json"))
    blob, found = _config_scope(repo)
    # "Is this a TypeScript repo?" must not be answered by a single stray .ts (a docs theme, a config
    # script): that would put a strict-mypy Python repo on the TS path and fail it for lacking a
    # tsconfig it has no reason to have. Require a tsconfig, a declared dependency, or several .ts files.
    ts_sources = [p for p in _iter_matches(repo, "*.ts") + _iter_matches(repo, "*.tsx")
                  if not p.endswith(".d.ts")]
    is_ts = bool(ts) or "typescript" in blob.lower() or len(ts_sources) >= 3
    if not is_ts:
        py = _strip_comments(_read_scoped(repo, "pyproject.toml") + _read_scoped(repo, "mypy.ini")
                             + _read_scoped(repo, "setup.cfg"))
        if "mypy" in py or "pyright" in py or "basedpyright" in py:
            # value-aware: `strict = false` / `ignore_errors = true` is NOT strict mode
            if _rule_enabled(py, "strict") or _rule_enabled(py, "disallow_untyped_defs"):
                if _rule_enabled(py, "ignore_errors"):
                    return False, ("mypy/pyright sets `ignore_errors` — type checking is disabled "
                                   "regardless of the strict flag.")
                return True, "python type checking configured in strict mode"
            return False, ("mypy/pyright configured but not strict (no enabled `strict` / "
                           "`disallow_untyped_defs`) — untyped code passes silently.")
        return True, "no static type layer detected (n/a)"
    problems = []
    if not re.search(r"""["']strict["']\s*:""", ts):
        problems.append("tsconfig has no `strict`")
    elif not _rule_enabled(ts, '"strict"') and not _rule_enabled(ts, "'strict'"):
        # present but assigned a disabling value — including across a newline, which a formatter emits
        problems.append("tsconfig `strict` is false")
    banned = ["no-explicit-any", "no-unsafe-argument", "no-unsafe-assignment", "ban-ts-comment",
              "no-non-null-assertion", "strict-type-checked", "strictTypeChecked"]
    if not any(_rule_enabled(blob, b) for b in banned):
        named = [b for b in banned if b in blob]
        if named:
            problems.append(f"the `any`/@ts-ignore bans it names ({', '.join(named[:3])}) are DISABLED "
                            f"— turning the escape hatch back on is not closing it")
        else:
            problems.append("no rule bans `any` / `@ts-ignore` / non-null assertions "
                            "(@typescript-eslint/no-explicit-any, ban-ts-comment)")
    if problems:
        return False, ("type escape hatches are open: " + "; ".join(problems) +
                       ". An agent will use them to turn a build green, unreviewed.")
    return True, "strict typing on and the escape hatches (any/@ts-ignore) are rejected"


def check_duplication_and_dead_code(repo):
    """Duplication + dead-code scanning is wired (report-only is fine, and is the recommended default).

    Parallel makers re-solve each other's problems: the same helper appears three times, and the
    superseded one is never deleted. Neither shows up as a failure in any single diff — only a
    cross-cutting scan sees them, which is exactly what a reader-less pipeline needs."""
    root = _vcs_root(repo)
    blob = ""
    for base in {repo, root}:
        for n in (".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml",
                  "package.json", "Makefile", "justfile", "Taskfile.yml"):
            for p in glob.glob(os.path.join(base, n)):
                try:
                    with open(p, encoding="utf-8") as f:
                        blob += "\n" + f.read()
                except Exception:
                    continue
    blob = _strip_comments(blob)
    # Match each tool as an INVOKED command, not a bare substring: "unused" appears inside
    # `eslint-plugin-unused-imports` and inside the words of a Makefile comment, and either would
    # otherwise satisfy the deploy gate without any scan being wired at all.
    tools = []
    for t in ("jscpd", "knip", "ts-prune", "depcheck", "vulture", "deadcode", "dupl",
              "unimported", "similarity-ts", "pmd cpd"):
        # as a command word: start of a line/script, or after npx/pnpm/yarn/run/&&/|/;
        if re.search(r"(?:^|[\s\"'`|;&]|npx\s+|pnpm\s+|yarn\s+)" + re.escape(t) + r"(?![\w-])",
                     blob, flags=re.M):
            tools.append(t)
    if tools:
        return True, f"duplication/dead-code scanning wired ({', '.join(sorted(set(tools)))})"
    return False, ("no duplication or dead-code scan (jscpd / knip / ts-prune / vulture …) in CI or "
                   "scripts. Parallel makers duplicate work and orphan superseded code; no single "
                   "diff shows it. Report-only (continue-on-error) is enough — it need not block.")


def check_no_inline_suppressions(repo):
    """No blanket inline suppressions of the unread-safe rules (docs/11 §4e).

    A config-level exception carries the file it covers and WHY, and can be audited and removed when
    the reason expires. An inline `eslint-disable` / `# type: ignore` / `@ts-ignore` is invisible at
    review time and immortal — nobody ever deletes one — and with no human reading the diff it is the
    cheapest way for an agent to make a bar stop applying. Bounded scan: repo-owned source only."""
    patterns = [
        (r"eslint-disable(?!-next-line\s+\S)", "eslint-disable (file-wide)"),
        (r"@ts-ignore", "@ts-ignore"),
        (r"@ts-nocheck", "@ts-nocheck"),
        (r"#\s*type:\s*ignore(?!\[)", "bare `# type: ignore`"),
        (r"#\s*noqa(?!:)", "bare `# noqa`"),
        (r"//\s*nolint(?!:)", "bare `//nolint`"),
        (r"rubocop:disable\s+all", "rubocop:disable all"),
    ]
    exts = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.py", "*.go", "*.rb", "*.rs")
    hits = []
    for ext in exts:
        for p in _iter_matches(repo, ext)[:400]:      # bounded: presence check, not an audit
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            for rx, label in patterns:
                if re.search(rx, text):
                    hits.append(f"{os.path.relpath(p, repo)}: {label}")
                    break
        if len(hits) > 6:
            break
    if hits:
        return False, ("inline rule suppressions found — move them to the lint config WITH A REASON, "
                       "where they can be audited and expired: " + "; ".join(hits[:6]) +
                       (f" (+{len(hits) - 6} more)" if len(hits) > 6 else ""))
    return True, "no blanket inline rule suppressions"


def check_multi_os_ci(repo):
    """CI runs on more than one OS (docs/11 §4e).

    A team on one platform has no other real machine, so platform-specific breakage (path case,
    reserved device names, line endings, fs watch behaviour) reaches users first. Nobody reads the
    diff, so the second OS is the only thing that catches it. A daily/scheduled second-OS job counts —
    it need not gate every PR."""
    root = _vcs_root(repo)
    blob = ""
    for base in {repo, root}:
        for n in (".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml",
                  ".circleci/config.yml", "azure-pipelines.yml"):
            for p in glob.glob(os.path.join(base, n)):
                try:
                    with open(p, encoding="utf-8") as f:
                        blob += "\n" + f.read()
                except OSError:
                    continue
    if not blob:
        return False, "no CI config to check for multi-OS coverage"
    families = set()
    for fam, keys in (("linux", ("ubuntu", "linux")), ("macos", ("macos", "darwin")),
                      ("windows", ("windows",))):
        if any(k in blob.lower() for k in keys):
            families.add(fam)
    if len(families) >= 2:
        return True, f"CI runs on {len(families)} OS families ({', '.join(sorted(families))})"
    return False, (f"CI runs on one OS only ({', '.join(families) or 'unknown'}). Platform-specific "
                   f"breakage (path case, reserved names, line endings) then reaches users first — and "
                   f"nobody reads the diff. A scheduled daily job on a second OS is enough.")


def check_tests_present(repo):
    """Executable tests exist at all — the one artifact that substitutes for a human reading the code.

    The whole unread-safe premise is that the machine, not a reader, catches regressions. A repo with
    a green CI and no tests is a pipeline that proves only that the code compiles."""
    # Match test FILES by name, never a bare `tests/` directory: `docs/test/notes.md` would otherwise
    # clear the test-phase bar, and a directory named tests proves nothing runs.
    patterns = ["*_test.go", "*_test.py", "test_*.py", "*.test.ts", "*.test.tsx", "*.test.js",
                "*.test.jsx", "*.test.mjs", "*.spec.ts", "*.spec.tsx", "*.spec.js", "*_spec.rb",
                "*_test.rb", "*_test.exs", "*Test.java", "*Tests.cs", "*_test.rs"]
    if _exists(repo, *patterns):
        return True, "executable tests are present"
    # a tests/ dir counts only if it actually holds source files (any language)
    for d in ("tests", "test", "__tests__", "spec"):
        for src in ("*.py", "*.ts", "*.js", "*.tsx", "*.go", "*.rb", "*.rs", "*.java", "*.exs"):
            if _exists(repo, f"{d}/{src}", f"{d}/**/{src}"):
                return True, f"executable tests are present ({d}/)"
    return False, ("no test files found (*.test.ts / *_test.py / a tests/ dir holding source files). "
                   "With no tests, nothing catches a regression except a human reading the diff — the "
                   "assumption this bar exists to remove.")


# artifact -> (checker, earliest phase that requires it)
CHECKS = [
    ("lockfile",            check_lockfile,            "implement"),
    ("manifest",            check_manifest_populated,  "implement"),
    ("toolchain-pin",       check_toolchain_pinned,    "implement"),
    ("complexity-bounded",  check_complexity_bounded,  "implement"),
    ("type-escapes-closed", check_type_escapes_closed, "implement"),
    ("readme-setup",        check_readme_setup,        "test"),
    ("one-command",         check_one_command,         "test"),
    ("tests-present",       check_tests_present,       "test"),
    ("idempotent-migrations", check_migrations_idempotent, "test"),
    ("env-example",         check_env_example,         "test"),
    ("no-inline-suppress",  check_no_inline_suppressions, "test"),
    ("dup-dead-code",       check_duplication_and_dead_code, "deploy"),
    ("multi-os-ci",         check_multi_os_ci,         "deploy"),
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
