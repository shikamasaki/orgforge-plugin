#!/usr/bin/env python3
"""org_hook — the ONE neutral PreToolUse adapter both Claude Code and Codex call.

This is the load-bearing bridge that makes the org's guardrails actually BLOCK inside a real
agent's tool loop, on either harness, without either harness knowing anything org-specific. It
is the projection layer of PROJECTION.md, made concrete: the neutral organ tools stay neutral
(they read the ledger and exit 0=allow / 10=escalate); THIS adapter maps an organ's verdict onto
the pre-tool-hook contract that Claude Code and Codex SHARE — read a hook-event JSON on stdin,
and either allow (exit 0) or BLOCK (exit 2 + reason on stderr, or a deny-JSON on stdout).

Both harnesses converge on the same PreToolUse contract (verified 2026-07 against code.claude.com
/docs/en/hooks and learn.chatgpt.com/docs/hooks):
  - stdin: JSON with at least {hook_event_name, tool_name, tool_input, cwd, session_id,
    tool_use_id}. `tool_use_id` is the per-call identity the cap reservation keys on; subagent
    invocations also carry {agent_id, agent_type}. Whether the same tool call can fire PreToolUse
    more than once is NOT documented — so the reservation is keyed idempotently rather than
    assuming it fires once.
  - to BLOCK: exit 2 with the reason on stderr, OR print
      {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                              "permissionDecision": "deny", "permissionDecisionReason": "..."}}
    and exit 0.
  - to ALLOW: exit 0 with no decision.
So one script serves both. The only per-harness difference (Claude uses --allowedTools, Codex
uses sandbox+MCP) is about tool *availability*, not the *block* — and the block is what a
guardrail is. We standardize the guardrail on exit-2/deny-JSON (NOT the organ's exit-10, which
stays the neutral internal convention the tools use among themselves).

WHY a hook and not an allowlist (the OSS survey's lesson, e.g. rulebricks/claude-code-guardrails):
an allowlist gates tool *identity* ("may you run Bash?"); the org's guardrails gate tool *effect
in context* ("does THIS Bash command, given the ledger's committed exposure this window, cross the
blast-radius cap?"). Only a hook that reads the event AND the ledger can decide that. The hook is
the thin policy-decision-point client; the organ tool is the policy engine; the ledger is state.

Mapping (tool_name + tool_input) -> which organ guards it, declared in RULES below. Each rule
names an organ command and how to derive its args from the tool_input. A rule that ESCALATES
(the organ exits 10) becomes a BLOCK with the organ's stderr as the reason — "the org's decision
line reached into the harness and held this action for the human" (docs/05 §5.0). Fail-OPEN is never
the default: a rule whose organ errors blocks with a clear message (fail-safe, docs/05 §2.4),
unless ORG_HOOK_FAIL_OPEN=1 is set for a permissive dev mode.

Usage (wired identically in Claude settings.json and Codex hooks.json):
  {"matcher": "Bash|Write|Edit", "type": "command",
   "command": "python3 <repo>/integrations/common/org_hook.py"}
Environment:
  ORG_LEDGER_ROOT   directory holding ledger.jsonl (required; the org's state)
  ORG_TOOLS_DIR     directory holding the organ *.py (default: <this>/../../tools)
  ORG_CONSTITUTION  path to constitution.yaml (default: <ORG_LEDGER_ROOT>/../constitution.yaml)
  ORG_HOOK_FAIL_OPEN=1  allow on organ error instead of blocking (dev only)

The GATE REGIME (caps, budget window, iteration limits, seam gate) is declared in
constitution.yaml's `enforcement:` block, so every install of the same org enforces the SAME gates
(docs/11 §0 reproducibility). The ORG_CAP_<DIM> / ORG_WINDOW / ORG_MAX_CYCLES / ORG_MAX_TOKENS /
ORG_REQUIRE_SEAM env vars remain as DEV OVERRIDES only (resolution order: env → constitution →
built-in default); the shipped org's behavior is what the spec declares, not what a host's
environment happens to set.
"""
import json
import os
import re
import tempfile
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# resolve the organ tools. This file is the single source; it is COPIED into the plugin's
# scripts/ (build.sh), where a sibling tools/ exists. So: explicit override wins; else a sibling
# tools/ (bundled-in-plugin layout: scripts/ + tools/ share a parent); else the repo layout
# (integrations/common/ -> ../../tools).
_BUNDLED = os.path.join(HERE, "..", "tools")
_REPO = os.path.join(HERE, "..", "..", "tools")
TOOLS_DIR = os.environ.get("ORG_TOOLS_DIR",
                           _BUNDLED if os.path.isdir(_BUNDLED) else _REPO)
def _discover_ledger():
    """The ledger root: env override, else DISCOVERED from the working directory.

    The guardrail is off when it cannot find a ledger, so requiring `.envrc` to be sourced meant a
    session that forgot it ran UNGATED — the failure mode is silent permissiveness, exactly what a
    guardrail must not have. An org is a place on disk (`.orgforge/` beside `organization.yaml`), so
    the hook finds it the same way it already finds its own tools/ dir. Env still wins, for a ledger
    deliberately kept outside the checkout or pinned in CI."""
    env = os.environ.get("ORG_LEDGER_ROOT", "")
    if env:
        return env
    try:
        sys.path.insert(0, TOOLS_DIR)
        import discover                                   # noqa: E402  (resolved at runtime)
        return discover.ledger_root() or ""
    except Exception:
        return ""                                          # discovery must never break the hook


LEDGER_ROOT = _discover_ledger()
FAIL_OPEN = os.environ.get("ORG_HOOK_FAIL_OPEN") == "1"


def _deny(reason):
    """Emit the shared deny contract and exit 2 (blocks on BOTH harnesses)."""
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "deny",
                                  "permissionDecisionReason": reason}}
    print(json.dumps(out))
    print(reason, file=sys.stderr)
    sys.exit(2)


SESSION_ID = ""      # from the PreToolUse stdin; part of the idempotency key
TOOL_USE_ID = ""     # likewise. **If it is missing, a metered action is denied**


def _allow():
    sys.exit(0)


def _append_emitted(output):
    """Close the emit->append loop (external review BLOCKER, 2026-07). An organ COMPUTES an event
    and prints `LEDGER-EVENT {json}`; nothing appended it, so the aggregate cap never accumulated
    (committed_so_far was always 0 -> the blast-radius cap silently degraded to a memoryless
    per-action check). Here the host (this hook) appends the emitted event via `ledger.py append`,
    with a --ts so window filters work. This is the R0-correct split: the organ stays a pure
    function that emits; the host writes. Best-effort — a failed append must not crash the hook."""
    for line in output.splitlines():
        if not line.startswith("LEDGER-EVENT "):
            continue
        try:
            ev = json.loads(line[len("LEDGER-EVENT "):])
            cls, payload = ev["class"], ev["payload"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        ts = _now_ts()
        try:
            subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "ledger.py"), "append",
                            LEDGER_ROOT, "--actor", "system:org_hook", "--class", cls,
                            "--payload", json.dumps(payload, ensure_ascii=False), "--ts", ts],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        except Exception:
            pass   # a failed write-back must never turn an allow into a crash



def _record_bypass(what, tool_input):
    """Record a declared bypass in the ledger. **If it cannot be recorded, deny.**

    This used to be `except: pass`, and the return value was not read either. **A bypass that
    failed to record goes through leaving no trace of the bypass** — which empties the escape
    hatch of its meaning (a declaration is permitted BECAUSE it is recorded, not because
    someone says they declared it).

    The writer stamps the time (do not pass `--ts`).

    Returns: None if it was recorded. A string giving the reason if it failed.
    """
    if not LEDGER_ROOT:
        return "cannot record the bypass: ORG_LEDGER_ROOT is unset"
    payload = {"what": what,
               "command": _command_text(tool_input)[:400],
               "declared_by": os.environ.get("ORG_ROLE") or "unknown"}
    try:
        r = subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "ledger.py"), "append",
                            LEDGER_ROOT, "--actor", "system:org_hook",
                            "--class", "bypass_declared",
                            "--payload", json.dumps(payload, ensure_ascii=False)],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    except Exception as e:
        return f"could not append to the ledger: {e}"
    if r.returncode != 0:
        return (f"the ledger refused bypass_declared (exit {r.returncode}): "
                f"{((r.stdout or '') + (r.stderr or '')).strip()[:300]}")
    return None


# Organ exit codes that are a VERDICT ON THE INPUT rather than a transient fault. The organs use
# exit 2 for a deliberate ValueError/OSError (usage error, unreadable/absent constitution, bad root);
# `argparse` also exits 2 on a malformed argv. None of those are re-runnable, so they must not sleep.
_DETERMINATE_ORGAN_CODES = frozenset({2})


def _run_organ(argv):
    """Run an organ command; return (exit_code, combined_output). Never raises.

    BOUNDED RETRY on a TRANSIENT failure (docs/12 §5): a timeout / crash (an exception, or a run that
    produced no clean verdict) is retried a bounded number of times with a short backoff, so a single
    flake in a long unattended run does not convert to a hard fail-safe block. A CLEAN verdict (exit 0
    allow, 10 escalate) never retries — only genuinely transient failures do. After the bounded retries
    the fail-safe block still applies (the caller blocks on the non-clean code). Retries: ORG_ORGAN_RETRIES
    (default 2); backoff: ORG_ORGAN_BACKOFF seconds (default 0.5), skipped entirely when ORG_NOW_TS is set
    (tests pin a clock and must not sleep).

    A DETERMINATE failure never retries either (perf fix, measured): the organs return exit 2 for a
    deliberate ValueError/OSError — bad usage, an unreadable constitution, a missing root. That verdict
    is a PROPERTY OF THE INPUT, so a second and third identical run cannot change it; retrying only
    bought 1.5s of pure `time.sleep` on EVERY PreToolUse. Measured on a benign Read with an org whose
    constitution.yaml was absent: 1.90s/call with the retry, 0.24s without (~8x). Retry is reserved for
    what is genuinely re-runnable — a crash/timeout (no exit code, code 99 here) or a signal death
    (negative returncode) — so a real flake still gets its bounded second chance.

    UTF-8 pin (cp932 fix): the child pipe is read as UTF-8 with errors=replace, so an organ status
    message containing a non-ASCII char (an em-dash) never crashes the guardrail on a non-UTF-8 console
    locale (e.g. Japanese cp932) — a UnicodeDecodeError here would fail-safe-block every tool call."""
    import time
    retries = int(os.environ.get("ORG_ORGAN_RETRIES", "2"))
    backoff = float(os.environ.get("ORG_ORGAN_BACKOFF", "0.5"))
    last = (99, f"organ {argv[0]} did not run")
    for attempt in range(retries + 1):
        try:
            p = subprocess.run([sys.executable, os.path.join(TOOLS_DIR, argv[0])] + argv[1:],
                               capture_output=True, encoding="utf-8", errors="replace", timeout=30)
            # a clean verdict (allow / escalate) is authoritative — return immediately, never retry it.
            if p.returncode in (0, 10):
                return p.returncode, (p.stdout + p.stderr)
            last = (p.returncode, (p.stdout + p.stderr))
            # a DETERMINATE failure is equally authoritative: the organ ran to completion and judged
            # the input unusable (exit 2 = its ValueError/OSError path). Re-running cannot change it.
            if p.returncode in _DETERMINATE_ORGAN_CODES:
                return last
        except Exception as e:  # organ missing / crashed / timed out — transient, retry
            last = (99, f"organ {argv[0]} failed to run (attempt {attempt + 1}): {e}")
        if attempt < retries and not os.environ.get("ORG_NOW_TS"):
            time.sleep(backoff * (2 ** attempt))   # exponential backoff
    return last


# ── RULES: (predicate on the tool call) -> organ command to consult ──────────────────────────
# Each rule: match(tool_name, tool_input) -> None (skip) or a list argv for an organ command.
# The organ is consulted with the CURRENT ledger; exit 10 (or its block message) => BLOCK.
# These are examples wired to the shipped organs; an adopter tunes the caps/dimensions to its org.


def _tokenize(cmd):
    """Split a shell command into tokens for WORD-BOUNDARY matching.

    The destructive classifier must not fire on substrings: a path like
    `/Volumes/.../fx-ml-platform/...` contains neither the token `rm` nor `-f`, yet the old
    `"rm " in cmd` / `"-f " in cmd` substring tests would misfire on commands that merely
    *contain* those bytes (e.g. `grep -f pattern`, a path with `form`, `--info` → `-f`). We tokenize
    once and test token membership instead. shlex is used for correctness; if the command is not
    valid shell (unbalanced quotes, etc.) we fall back to a whitespace split so we still gate it
    rather than silently passing an unparseable — and thus opaque — command."""
    # **shlex alone is the slow part.** Measured: 11s on a million characters, long enough
    # that the hook stops returning. Tokenising is only used to find word boundaries, so the
    # first N characters suffice — a dangerous word appears near the start of a line.
    # **Regex matching still runs over the whole string**: that costs ~10ms even at a
    # million characters, and truncating it would let anything hide in the middle.
    # **When it is too long, drop shlex and split on word boundaries with a regex.**
    # Truncating hides whatever sits past the cut: measured, the middle of
    # `echo <70k chars>; <destructive command>; echo <70k chars>` passed straight through.
    # A regex split is good enough for word boundaries and stays ~10ms at a million
    # characters.
    if len(cmd) > _MAX_TOKENIZE_CHARS:
        return re.findall(r"[^\s;&|()`'\"]+", cmd)
    try:
        return shlex.split(cmd, posix=True)
    except ValueError:
        return cmd.split()


def _has_token(tokens, *words):
    """True if any of `words` appears as a WHOLE token (not a substring of one)."""
    tset = set(tokens)
    return any(w in tset for w in words)


def _has_seq(tokens, *pairs):
    """True if any (a, b) pair appears as ADJACENT tokens, e.g. ('git','push') or ('reset','--hard').
    Catches multi-word operators that a single-token test would miss."""
    for a, b in pairs:
        for i in range(len(tokens) - 1):
            if tokens[i] == a and tokens[i + 1] == b:
                return True
    return False


_QUOTED_HEREDOC = re.compile(
    r"<<(?P<strip_tabs>-)?[ \t]*(?P<quote>['\"])(?P<delimiter>[^'\"\r\n]+)(?P=quote)")


def _without_inert_heredoc_data(cmd):
    """Remove data from one provably inert, quoted ``cat`` heredoc before policy inspection.

    PreToolUse receives Bash source as one string. Treating every byte as executable makes an
    observation such as ``cat >> notes <<'EOF'`` look like it executes the commands quoted in its
    body. We remove the body only for a deliberately narrow shape:

    * exactly one quoted heredoc (quoted delimiters disable shell expansion),
    * a standalone ``cat`` command with no pipeline/separator/substitution, and
    * no command after the terminating delimiter.

    Interpreter consumers, pipelines to a shell, unquoted/expanding heredocs, multiple heredocs,
    and ambiguous syntax are returned unchanged so every guardrail continues to fail closed.
    """
    if not isinstance(cmd, str) or "<<" not in cmd:
        return cmd
    lines = cmd.splitlines(keepends=True)
    starts = []
    for index, line in enumerate(lines):
        for match in _QUOTED_HEREDOC.finditer(line):
            starts.append((index, match))
    if len(starts) != 1:
        return cmd
    start, match = starts[0]
    if any(line.strip() for line in lines[:start]):
        return cmd
    header = lines[start].rstrip("\r\n")
    # A shell operator can send the data to an interpreter or attach a later command. Quoted
    # filenames containing these bytes are conservatively left unsanitized as well.
    if any(operator in header for operator in ("|", ";", "&", "`", "$(", "<(", ">(")):
        return cmd
    try:
        header_tokens = shlex.split(header, posix=True)
    except ValueError:
        return cmd
    if not header_tokens or os.path.basename(header_tokens[0]) != "cat":
        return cmd

    delimiter = match.group("delimiter")
    strip_tabs = bool(match.group("strip_tabs"))
    end = None
    for index in range(start + 1, len(lines)):
        candidate = lines[index].rstrip("\r\n")
        if strip_tabs:
            candidate = candidate.lstrip("\t")
        if candidate == delimiter:
            end = index
            break
    if end is None or any(line.strip() for line in lines[end + 1:]):
        return cmd
    # Inspection does not execute this returned text; retaining the header preserves redirects and
    # asset classification while removing only the bytes the shell supplies to cat as stdin.
    return "".join(lines[:start]) + header


# stdout/stderr redirect onto an ABSOLUTE path — but NOT the harmless cases that dominate real work.
# The earlier check `(\||>>?)\s*/` fired on `2>/dev/null`, `> /dev/null 2>&1`, and any pipe-to-absolute,
# so read-only searches with stderr suppressed were mis-charged as destructive and drained the budget.
# We match only a REAL overwrite of a system path: an optional fd, `>`/`>>`, then an absolute path that
# is NOT a /dev/* sink (writing to /dev/null|stdout|stderr|tty is a no-op sink, not blast radius).
_REDIR_TO_ABS = re.compile(r"(?:^|\s)\d?>>?\s*(/[^\s|&;>]*)")


def _redirects_to_system_path(cmd):
    for m in _REDIR_TO_ABS.finditer(cmd):
        target = m.group(1)
        if target.startswith("/dev/"):
            continue                          # /dev/null, /dev/stdout, … — a sink, not a write
        return True                           # a genuine `> /etc/…` / `>> /usr/…` overwrite
    return False


# Regenerable build output — deleting it loses no information, it can be rebuilt.
_REGENERABLE = (
    ".orgforge/wt/",          # per-Issue worktree (begin can recreate it)
    "node_modules",           # dependencies (install brings them back)
    "/scratchpad/", ".pytest_cache", "__pycache__",
    "dist/", "build/", ".next/", "coverage/", ".turbo/",
)


def _is_regenerable_target(cmd):
    """Check whether every deletion target is regenerable.

    False as soon as ONE "gone for good" item is mixed in — relaxing is only safe when all of
    the targets can be rebuilt. Soften that judgement and the cap stops meaning anything.
    """
    if not any(m in cmd for m in _REGENERABLE):
        return False
    # Do not relax when the path sits directly under root or home, or climbs to a parent.
    if re.search(r"(^|\s)(/|~|\$HOME)(\s|$)", cmd) or "/.." in cmd or " .. " in cmd:
        return False
    return True


def _asset_dimension(tool_name, ti):
    """Classify a tool call into a blast-radius exposure dimension, PRICED BY REVERSIBILITY.

    A blast-radius cap must bound *irreversible effect*, not *activity*. The earlier version
    charged every file write 1 against a single low cap, so a normal build (hundreds of
    reversible file creations) exhausted a budget meant for destruction — the guardrail stopped
    construction, not runaways. A three-perspective review (security / rate-limiting / control
    theory) converged on the fix: meter irreversibility, not tool-call count.

    Dimensions returned (each has its own cap; the dangerous ones are low, the safe ones high):
      - None            : reversible/benign — NOT blast radius, not metered (new-file create,
                          read-only shell). A 300-file build lives here and proceeds.
      - "file_mutations": overwriting an EXISTING file (reversible under VCS, but real) — high cap.
      - "external_writes"/"infra_changes"/"destructive_ops": irreversible / external side effects
                          — LOW cap. This is the actual blast radius.
      - "shell_effect"  : genuinely unclassifiable shell — fail-safe metered (unknown=dangerous).

    CREATE-vs-MUTATE is decided by a filesystem stat (does the path already exist?), exactly as
    the reviewers recommended — the single check that unblocks a legit build while keeping
    overwrite metered. Fail-safe: unknown shell is charged, ambiguous destroys are max-cost."""
    if isinstance(ti, dict):
        cmd = _without_inert_heredoc_data(_command_text(ti))
        path = ti.get("file_path") or ti.get("path") or ""
    elif isinstance(ti, str):
        cmd, path = ti, ""
    else:
        cmd, path = "", ""

    # ── file-editing tools: CREATE (new path) is reversible & free; MUTATE (existing) is metered.
    if tool_name in ("Write", "Edit", "MultiEdit", "ApplyPatch"):
        # Edit/MultiEdit/ApplyPatch always target an existing file (a mutation). A Write to a
        # path that does not yet exist is a reversible creation — not blast radius.
        if tool_name == "Write" and path and not os.path.exists(path):
            return None                      # new file — reversible, cheap; do not meter
        if tool_name == "Write" and not path:
            return ("file_mutations", 1)     # can't tell → fail-safe meter
        return ("file_mutations", 1)         # overwrote/edited an existing file
    if not _is_shell_tool(tool_name):
        return None                          # non-shell, non-write tools touch no asset here
    if not cmd.strip():
        return None                          # an empty command touches no asset — not blast radius

    # ── irreversible / external side effects — the real blast radius (LOW cap) ────────────
    if any(k in cmd for k in ("curl", "wget", "http")) and any(
            k in cmd for k in ("POST", "PUT", "DELETE", "-d ", "--data")):
        return ("external_writes", 1)
    if any(k in cmd for k in ("aws ", "gcloud ", "terraform apply", "kubectl apply")):
        return ("infra_changes", 1)
    # WORD-BOUNDARY matching (not substring): tokenize first so a path like `.../fx-ml-platform/...`
    # or a flag like `grep -f` never masquerades as `rm`/`-f`. Operators (`|`, `>`) and dotted calls
    # (`shutil.rmtree`) don't tokenize as clean words, so those few are matched on the raw string
    # with tight anchors. See _tokenize/_has_token/_has_seq above and the tests that pin this.
    # **Look inside the container too.** shlex turns `psql -c 'DROP TABLE users'` into a
    # single quoted token, so it never matches as `DROP`. In other words, **a destructive SQL
    # operation in the form people actually write it — quoted after -c / -e — was never counted
    # toward the cap** (measured: a bare `DROP TABLE users` counted, `psql -c '…'` passed).
    # What cannot be counted cannot be capped.
    toks = _tokenize(cmd)
    for _inner in re.findall(r"\$\(([^)]*)\)|`([^`]*)`", cmd):
        toks += " ".join(x for x in _inner if x).split()
    _dec = _decode_escapes(cmd)
    if _dec != cmd:
        toks += re.sub(r"[$'\"]", " ", _dec).split()
    if _EXECUTES_STRING.search(cmd) or _SQL_CLIENT.search(cmd):
        # In `psql -c 'DROP …'` the **quoted text is what gets executed**. Open only the
        # strings that are executed — `grep 'DROP …'` is not one of them.
        toks += re.sub(r"['\"]", " ", cmd).split()
    destructive = (
        _has_token(toks, "rm", "dd", "truncate", "mkfs", "shred")                 # dangerous binaries
        or _has_token(toks, "DROP", "DELETE", "TRUNCATE")                         # SQL (as whole tokens)
        or _has_token(toks, "--force", "--delete", "-delete")                     # force / find -delete
        # Only the **force variants** of `git push` are destructive. A normal push appends and
        # is undoable — by a revert, or a further commit. Counting them all filled the cap
        # during ordinary development: a maker finished its work and then could not push it.
        # The cap measures IRREVERSIBILITY, not activity; stopping development itself is a
        # misuse of it. force-with-lease stays on the heavy side — it can still erase someone
        # else's history.
        or (_has_seq(toks, ("git", "push"))
            and _has_token(toks, "--force", "-f", "--force-with-lease", "--delete", "--mirror"))
        or _has_seq(toks, ("git", "reset"), ("reset", "--hard"),
                    ("terraform", "destroy"), ("kubectl", "delete"))
        or "shutil.rmtree" in cmd                                                 # python dotted call
        or _redirects_to_system_path(cmd)                                        # `> /etc/…` overwrite of a system path
        or bool(re.search(r"\|\s*(bash|sh)\b", cmd))                              # pipe-to-shell
    )
    if destructive:
        # A regenerable target is not an irreversible effect. Because the cap measures
        # irreversibility rather than activity, weighting something a rebuild restores stops
        # only routine cleanup. Measured: five holds in one day, all five with zero real impact
        # (removing a worktree, a node_modules symlink, a scratchpad) — and five worktrees
        # piled up as a result. Relaxing this lets nothing catastrophic through: `rm -rf /`
        # and its class are hard-blocked by the catastrophic denylist regardless.
        if _is_regenerable_target(cmd):
            return ("destructive_ops", 0)
        # scope-weight the catastrophic recursive/glob deletes so ONE can trip the cap alone
        rm_recursive = _has_token(toks, "rm") and _has_token(toks, "-r", "-rf", "-fr", "-R")
        heavy = (rm_recursive
                 or _has_token(toks, "-delete", "--delete", "DROP", "TRUNCATE", "mkfs", "shred")
                 or _has_seq(toks, ("reset", "--hard"))
                 or "shutil.rmtree" in cmd
                 or "/*" in cmd)
        return ("destructive_ops", 3 if heavy else 1)

    # ── everything else — NOT blast radius, not metered ──────────────────────────────────
    # The cap bounds IRREVERSIBLE EFFECT, not activity. A command that matched none of the explicit
    # destructive / external-write / infra patterns above is not charged — including read-only
    # inspection (ls, cat, grep, find, du, stat), build/test tooling (npm, pytest, go, cargo), and
    # any unclassified shell. Earlier this returned a metered `shell_effect` for "unknown" commands,
    # which quietly drained the daily budget on benign work (git status, find, an unfamiliar CLI) until
    # the cap blocked everything — a false-positive deadlock. "Unknown" is not "dangerous": the danger
    # is caught by the explicit patterns above (kept broad and word-boundary-accurate), and the danger
    # that slips those is caught by the SEPARATE guards (a Write/Edit to an existing file is metered as
    # file_mutations; a genuinely novel destructive verb is a coverage gap to add to the patterns, not
    # a reason to tax every command). So: no match ⇒ not blast radius ⇒ not metered.
    return None


# Per-dimension default caps, priced by reversibility (a three-perspective review's conclusion:
# meter irreversibility, not activity). The irreversible/external dimensions are LOW — that is
# the real blast radius. Reversible-but-real mutations get a HIGH cap so a normal build proceeds.
# Reversible creations and reads return None from the classifier and are never metered at all.
# Every value is overridable per-adopter via ORG_CAP_<DIMENSION>.
# Per-dimension default caps — a PER-DAY budget (the window rolls daily, see _window_since). Sized so
# a normal day of real work proceeds untouched while a runaway (hundreds of irreversible acts in a day)
# still trips. The irreversible dimensions are the real blast radius, but "irreversible" is not "rare":
# a research/ML day legitimately deletes and replaces artifacts, models, and caches many times, so the
# floor must clear that, not a hand-count of 3. Tune per adopter via ORG_CAP_<DIMENSION>; a tighter
# threat tier (asset-touching prod) sets these lower, a sandboxed dev tier may raise them further.
_DEFAULT_CAPS = {
    # rm/DROP/force per day — irreversible but routine in real work; scope-weighted.
    # 50 was not enough in practice: a day running 18 Issues in parallel filled it, leaving a
    # maker unable to push work it had finished. The cap exists to stop a runaway of irreversible
    # operations, not to govern the pace of development. With ordinary `git push` taken out
    # of scope (0.23.0), 150 leaves realistic headroom while still biting: **a weight-3
    # operation (recursive delete / DROP / reset --hard) reaches it in 50 uses.**
    "destructive_ops": "150",
    "external_writes": "30",   # outbound POST/PUT/DELETE per day — irreversible side effect
    "infra_changes":   "20",   # apply to real infra per day — irreversible, rarer than local deletes
    "shell_effect":    "100",  # DEPRECATED: the classifier no longer emits shell_effect (unknown≠metered);
                               #   kept only so an existing ORG_CAP_SHELL_EFFECT override is not an error.
    "file_mutations":  "500",  # overwriting existing files per day — reversible under VCS; high ceiling
}

# ── the spec-declared enforcement policy (docs/11 §0 reproducibility) ─────────
# The gate regime (caps, window, iteration limits, seam gate) is declared in constitution.yaml so
# that EVERY install of the same org enforces the SAME gates — not in per-host env vars, which made
# two adopters diverge. We read it once (cached). Resolution order for any value: env var (a DEV
# OVERRIDE, kept for a developer loosening a cap locally) → constitution.enforcement → built-in
# default. So the shipped org's behavior is the spec's; env is only a local escape hatch.
_ENFORCEMENT_CACHE = None


def _enforcement():
    """Load constitution.yaml's `enforcement:` block (cached). constitution.yaml lives at the org
    root — ORG_CONSTITUTION if set, else next to the ledger (LEDGER_ROOT/../constitution.yaml). If
    yaml is unavailable or the file is absent, return {} (the built-in defaults apply — the org still
    runs, just on defaults rather than spec-declared values)."""
    global _ENFORCEMENT_CACHE
    if _ENFORCEMENT_CACHE is not None:
        return _ENFORCEMENT_CACHE
    _ENFORCEMENT_CACHE = {}
    path = os.environ.get("ORG_CONSTITUTION")
    if not path:
        # **Find the org root.** constitution.yaml lives at the org root — the PARENT of
        # `.orgforge/`, which is where /org-init writes it. The ledger root's parent IS
        # `.orgforge/`, so looking there can never find it. On a miss this returned {} and
        # every declared cap and window silently fell back to a built-in default, while the
        # hook still looked healthy. Measured: `_enforcement()` came back empty on a live org.
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), "tools"))
            import discover                               # noqa: E402
            cand = discover.constitution()
            if cand and os.path.exists(cand):
                path = cand
        except Exception:
            pass
    if not path and LEDGER_ROOT:
        # Fallback for when discover is unavailable: look at the **org root** — the parent of the
    # parent of `.orgforge`.
        for cand in (
            os.path.join(os.path.dirname(os.path.dirname(
                LEDGER_ROOT.rstrip("/"))), "constitution.yaml"),
            os.path.join(os.path.dirname(LEDGER_ROOT.rstrip("/")), "constitution.yaml"),
        ):
            if os.path.exists(cand):
                path = cand
                break
    if path and os.path.exists(path):
        try:
            import yaml  # yaml may be absent in a minimal interpreter; degrade to defaults
            with open(path, encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            _ENFORCEMENT_CACHE = doc.get("enforcement", {}) or {}
        except Exception:
            _ENFORCEMENT_CACHE = {}
    return _ENFORCEMENT_CACHE


def _cap_for(dimension):
    """The per-day cap for a dimension. env ORG_CAP_<DIM> (dev override) → constitution.enforcement.caps
    → built-in default. Returns a string (the guardrails.py --cap arg is a string)."""
    env = os.environ.get(f"ORG_CAP_{dimension.upper()}")
    if env is not None:
        return env
    caps = _enforcement().get("caps") or {}
    if dimension in caps:
        return str(caps[dimension])
    return _DEFAULT_CAPS.get(dimension, "3")


def _now_ts():
    """The host's 'now', as an ISO ts. Used BOTH for the ts stamped on appended events and for the
    rolling window boundary — they MUST share one clock, or events are written under one epoch and
    read under another (the deadlock's root cause: events stamped 1970 while the window rolled to
    today, so nothing ever fell inside the window and committed exposure was mis-summed). Override
    with ORG_NOW_TS (tests pin a fixed clock); else the real UTC now."""
    override = os.environ.get("ORG_NOW_TS")
    if override:
        return override
    try:
        import datetime
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return "1970-01-01T00:00:00Z"


def _window_since():
    """The start of the CURRENT blast-radius window. The cap bounds exposure PER WINDOW (a rolling
    budget that resets — the "death by a thousand cuts" guard of docs/05 §2.1), so the window must
    ROLL FORWARD, or committed exposure accumulates for all time and the cap eventually blocks every
    action (the frozen-epoch deadlock). Default: a rolling DAILY window (the day of _now_ts, at
    00:00), so the budget resets each day with no operator action. Override with ORG_WINDOW_SINCE for
    a custom boundary, or ORG_WINDOW=all to opt into an all-time cap deliberately."""
    override = os.environ.get("ORG_WINDOW_SINCE")
    if override:
        return override
    # env ORG_WINDOW (dev override) → constitution.enforcement.window → daily default (docs/11 §0)
    window = os.environ.get("ORG_WINDOW") or str(_enforcement().get("window", "daily"))
    if window == "all":
        return "1970-01-01"                       # explicit, deliberate all-time budget
    # the day-boundary of the same clock the appends use — keep read-window and write-ts consistent
    return _now_ts()[:10] + "T00:00:00Z"


# CATASTROPHIC denylist — commands whose ONE execution is unrecoverable at a scope no daily budget
# should ever permit. The blast-radius cap bounds "death by a thousand cuts" (many small irreversible
# acts summed over a window); it CANNOT bound "death by one cut" — a single `rm -rf /` is weight 3 and
# passes under any non-zero cap. This layer hard-blocks those regardless of budget, so a fresh org with
# the default cap is not one command away from catastrophe. It is deliberately narrow (only the
# unambiguously catastrophic, root-scoped / whole-disk forms) to avoid false positives; the cap handles
# the ordinary irreversible ops. Override for a sandbox with ORG_ALLOW_CATASTROPHIC=1 (never in prod).

# Integrating outside the organ. **Only the hook can notice a check that was never called** —
# `integrate` verifies the gate's admit and the skeptic's survives, but verifies nothing if
# nobody runs it. In the field a supervisor, convinced by a strong maker report, merged into
# develop with `git merge`: two changes landed with neither gate nor skeptic. The ledger
# refused them afterwards — correctly, and after the code was already in.
# **Whether a check runs must not be the decision of the thing being checked.**
_PROTECTED_BRANCHES = ("develop", "main", "master")
_MERGE_VERBS = (("git", "merge"), ("git", "rebase"), ("git", "cherry-pick"))
_MERGE_COMMANDS = {verb for _, verb in _MERGE_VERBS}
_REBASE_RECOVERY_ACTIONS = {"--abort", "--continue", "--skip"}
_GIT_GLOBAL_FLAGS = {"--paginate", "-P", "--no-pager", "--no-replace-objects",
                     "--bare", "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs",
                     "--icase-pathspecs", "--no-optional-locks", "--no-advice"}
_GIT_GLOBAL_WITH_VALUE = {"-c", "--config-env"}


def _git_command_at(tokens, index, target):
    """Parse Git global options and return ``(verb, verb_index, target)``.

    Only options that leave checkout identity unchanged are accepted. ``-C`` updates the static
    target; ``--git-dir``/``--work-tree`` and unknown global options are intentionally unresolved
    so the integration guard fails closed instead of inspecting a different repository from Git.
    """
    pos = index + 1
    while pos < len(tokens):
        token = tokens[pos]
        if token == "-C":
            if pos + 1 >= len(tokens):
                return None, None, None
            raw = tokens[pos + 1]
            if (not raw or raw.startswith("-")
                    or any(mark in raw for mark in ("$", "`", "~"))):
                return None, None, None
            target = raw if os.path.isabs(raw) else os.path.join(target, raw)
            pos += 2
            continue
        if token in _GIT_GLOBAL_WITH_VALUE:
            if pos + 1 >= len(tokens):
                return None, None, None
            pos += 2
            continue
        if token in _GIT_GLOBAL_FLAGS or token.startswith("--config-env="):
            pos += 1
            continue
        if token.startswith("-"):
            return None, None, None
        return token, pos, os.path.realpath(target)
    return None, None, None


def _rebase_recovery_target(cmd):
    """Return ``(is_recovery, cwd)`` for one statically targeted rebase recovery command.

    ``rebase --abort/--continue/--skip`` does not choose a branch to integrate. Git applies it to
    rebase state already stored in one checkout. Allow that recovery on a protected branch, but
    only when the command contains exactly one Git invocation and its checkout can be resolved
    before Bash runs. A compound or dynamic command remains held.
    """
    if not isinstance(cmd, str):
        return False, None
    plain = _tokenize(cmd)
    if (not _has_token(plain, "git") or not _has_token(plain, "rebase")
            or not _REBASE_RECOVERY_ACTIONS.intersection(plain)):
        return False, None
    if len(cmd) > _MAX_TOKENIZE_CHARS or re.search(r"`|\$\(|(?:^|\s)[<>]\(", cmd):
        return True, None
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = "#"
        tokens = list(lexer)
    except (TypeError, ValueError):
        return True, None

    git_positions = [i for i, token in enumerate(tokens) if token == "git"]
    if len(git_positions) != 1:
        return True, None
    index = git_positions[0]
    direct_cd = (index == 3 and tokens[0] == "cd" and tokens[2] == "&&")
    if index != 0 and not direct_cd:
        return True, None
    if any(token in {";", "&&", "||", "|", "|&", "&", "\n"}
           for token in tokens[index + 1:]):
        return True, None

    target = os.getcwd()
    if direct_cd:
        raw_cd = tokens[1]
        if (not raw_cd or raw_cd.startswith("-")
                or any(mark in raw_cd for mark in ("$", "`", "~"))):
            return True, None
        target = raw_cd if os.path.isabs(raw_cd) else os.path.join(os.getcwd(), raw_cd)
    verb, verb_index, target = _git_command_at(tokens, index, target)
    if verb != "rebase" or verb_index is None:
        return False, None
    args = tokens[verb_index + 1:]
    actions = [arg for arg in args if arg in _REBASE_RECOVERY_ACTIONS]
    if len(actions) != 1 or len(args) != 1:
        return True, None
    if not target or not os.path.isdir(target):
        return True, None
    return True, target


def _integration_target_cwd(cmd):
    """Return ``(has_integration, cwd)`` for a statically resolvable git integration.

    PreToolUse runs before Bash, so its process cwd does not reflect a leading ``cd`` and ordinary
    token matching does not understand ``git -C``. Resolve only the two narrow, deterministic forms
    used for worktrees. If a target path is dynamic, missing, or there is more than one integration,
    return ``(True, None)`` so the caller fails closed instead of inspecting the wrong checkout.
    """
    if not isinstance(cmd, str):
        return False, None
    plain = _tokenize(cmd)
    might_integrate = (_has_token(plain, "git")
                       and bool(_MERGE_COMMANDS.intersection(plain)))
    if not might_integrate:
        return False, None
    if len(cmd) > _MAX_TOKENIZE_CHARS or re.search(r"`|\$\(|(?:^|\s)[<>]\(", cmd):
        return True, None
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = "#"
        tokens = list(lexer)
    except (TypeError, ValueError):
        return True, None

    targets = []
    for index, token in enumerate(tokens):
        if token != "git":
            continue
        preceding_cds = [pos for pos, word in enumerate(tokens[:index]) if word == "cd"]
        direct_cd = (index >= 3 and tokens[index - 1] == "&&" and tokens[index - 3] == "cd")
        # Resolving a shell state machine here would recreate a shell incompletely. Support exactly
        # one direct ``cd PATH && git``; chained, separated, or otherwise earlier cd commands are
        # ambiguous and must not make us inspect a checkout different from the one Bash will use.
        if preceding_cds and not (len(preceding_cds) == 1 and direct_cd
                                  and preceding_cds[0] == index - 3):
            return True, None
        target = os.getcwd()
        if direct_cd:
            raw_cd = tokens[index - 2]
            if (not raw_cd or raw_cd.startswith("-")
                    or any(mark in raw_cd for mark in ("$", "`", "~"))):
                return True, None
            target = raw_cd if os.path.isabs(raw_cd) else os.path.join(os.getcwd(), raw_cd)
        verb, _verb_index, target = _git_command_at(tokens, index, target)
        if verb in _MERGE_COMMANDS:
            if target is None:
                return True, None
            targets.append(target)
        elif verb is None:
            # A Git global option we do not model may redirect the repository (for example
            # --git-dir/--work-tree). If this shell segment still names an integration verb, the
            # target is ambiguous — never turn parser incompleteness into an authorization bypass.
            segment = []
            for word in tokens[index + 1:]:
                if word in {";", "&&", "||", "|", "|&", "&", "\n"}:
                    break
                segment.append(word)
            if _MERGE_COMMANDS.intersection(segment):
                return True, None

    if not targets:
        return False, None
    if len(targets) != 1 or not os.path.isdir(targets[0]):
        return True, None
    return True, targets[0]


def _git_integration_context(cwd):
    """Return ``(branch, repo_root)`` for the checkout an integration would mutate."""
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"], capture_output=True, text=True,
            timeout=10).stdout.strip()
        root_result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
            timeout=10)
        root = root_result.stdout.strip() if root_result.returncode == 0 else ""
        return branch, root
    except Exception:
        return "", ""


def _integration_bypass(tool_name, ti):
    """Is this a direct integration into a protected branch? Return the reason to hold (and the
    command to run instead).

    **Putting the command to run into the hold message is the decisive part.** People bypass not
    for speed but because they did not want to pay the cost of remembering the tool's name. With
    the command right in front of them, the reason to bypass disappears. Hold without offering
    the command and they instead memorise the declaration (`ORG_ALLOW_MANUAL_MERGE`) and reach
    for it habitually — **bypassing gets faster AND stops leaving a record**, which is worse
    than where we are now.
    """
    if tool_name != "Bash":
        return None
    cmd = _without_inert_heredoc_data(_command_text(ti))
    is_recovery, recovery_cwd = _rebase_recovery_target(cmd)
    if is_recovery:
        if recovery_cwd is None:
            _current_branch, current_root = _git_integration_context(os.getcwd())
            if current_root and os.path.isdir(os.path.join(current_root, ".orgforge")):
                return ("cannot statically resolve which worktree this rebase-recovery command "
                        "targets. Make the target worktree the cwd and run "
                        "`git rebase --abort|--continue|--skip` on its own.")
            return None
        _branch, recovery_root = _git_integration_context(recovery_cwd)
        if recovery_root and os.path.isdir(os.path.join(recovery_root, ".orgforge")):
            return None
    has_integration, target_cwd = _integration_target_cwd(cmd)
    if not has_integration:
        return None
    _current_branch, current_root = _git_integration_context(os.getcwd())
    if target_cwd is None:
        if current_root and os.path.isdir(os.path.join(current_root, ".orgforge")):
            return ("cannot statically resolve which worktree this integration command targets. "
                    "Do not bundle a dynamic `cd` / `git -C` or several integrations into one "
                    "call — make the target worktree the cwd and run them one at a time.")
        return None
    cur, repo_root = _git_integration_context(target_cwd)
    if cur not in _PROTECTED_BRANCHES:
        return None
    # Stay silent in a repository with no org — this discipline applies only to an orgforge org.
    if not repo_root or not os.path.isdir(os.path.join(repo_root, ".orgforge")):
        return None

    tools_dir = os.environ.get("ORG_TOOLS_DIR") or ""
    oc = os.path.join(tools_dir, "org_cycle.py") if tools_dir else "org_cycle.py"
    return (f"a direct integration into {cur}. **Integrate through `org_cycle integrate`** — it "
            f"checks the ledger for the gate\'s admit and the skeptic\'s survives:\n"
            f"    python3 \"{oc}\" integrate --issue <N> --plan   # see what would be integrated\n"
            f"    python3 \"{oc}\" integrate --issue <N>          # check the preconditions, then integrate\n"
            f"  Without those preconditions `integrate` stops at exit 4 and never reaches the "
            f"merge. It also runs the post-integration tests, records `integration_admitted`, and "
            f"logs to the Issue in one go.\n"
            f"  Split preparation, integration and verification into separate Bash/exec calls "
            f"(e.g. prepare only -> `org_cycle integrate` only -> `git status`/CI check only).\n"
            f"  **To integrate by hand deliberately**, pass `ORG_ALLOW_MANUAL_MERGE=1`. That "
            f"declaration is recorded in the ledger as `bypass_declared` — what cannot be blocked "
            f"is at least written down.")



# Creating or closing an Issue outside the organ. In the field six were created with
# `gh issue create` — dropping `dept`, `objective`, `parent` and the idempotency key
# entirely — and five closed with `gh issue close`, leaving not one `cycle_completed`
# behind (the required `domain_model` went with them).
# **Reads are never blocked** — `view` and `list` stay open.
_GH_WRITE = {
    ("issue", "create"): ("Creating an Issue", "create --kind task --dept <role> --objective <id> "
                                               "--parent <objective#> --title … --body …"),
    ("issue", "close"): ("Closing an Issue", None),
    ("issue", "edit"): ("Changing an Issue's labels or body", None),
    ("issue", "reopen"): ("Reopening an Issue", None),
}


_SHELL_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)


def _command_scoped_declaration(cmd, variable, is_action):
    """Whether this Bash call gives its sole guarded action a one-shot bypass.

    PreToolUse runs before Bash, so an assignment inside the command cannot affect the hook
    process's ``os.environ``. Read the declaration from the command while preserving shell scope:
    a prefix assignment applies to that simple command, and ``export`` persists across later
    ``;``/``&&``/newline segments but not out of a pipeline. Merely echoing the declaration,
    assigning it to another command, or unsetting it before the guarded action must not unlock it.
    Exactly one guarded action is allowed per Bash call so one audit row always represents one
    mutation; a declared action cannot piggyback an undeclared (or second declared) action.
    """
    if not isinstance(cmd, str) or len(cmd) > 64 * 1024:
        return False
    # Do not attempt to prove scope through command/process substitution. A direct mutation plus
    # ``$(...)`` or backticks can execute another hidden mutation inside the same shell segment.
    if re.search(r"`|\$\(|(?:^|\s)[<>]\(", cmd):
        return False
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = "#"  # shell comments are not executable segments
        tokens = list(lexer)
    except (TypeError, ValueError):
        return False

    exported = False
    segment = []

    def evaluate(parts, separator):
        nonlocal exported
        if not parts:
            return "empty", None

        if parts[0] == "export":
            declared = None
            for token in parts[1:]:
                match = _SHELL_ASSIGNMENT.match(token)
                if match and match.group(1) == variable:
                    declared = match.group(2) == "1"
            # Each side of a pipeline runs in its own environment; an export there does not
            # establish the variable for a later command in the parent shell.
            if declared is not None and separator != "|":
                exported = declared
            return "state", None

        if parts[0] == "unset" and variable in parts[1:]:
            if separator != "|":
                exported = False
            return "state", None

        index = 0
        shell_local = None
        while index < len(parts):
            match = _SHELL_ASSIGNMENT.match(parts[index])
            if not match:
                break
            if match.group(1) == variable:
                shell_local = match.group(2) == "1"
            index += 1

        env_clears = False
        env_unsets = False
        if index < len(parts) and parts[index] == "env":
            index += 1
            while index < len(parts):
                token = parts[index]
                if token == "--":
                    index += 1
                    break
                if token in {"-i", "--ignore-environment"}:
                    env_clears = True
                    index += 1
                    continue
                if token in {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}:
                    if index + 1 >= len(parts):
                        return "other", None
                    if token in {"-u", "--unset"} and parts[index + 1] == variable:
                        env_unsets = True
                    index += 2
                    continue
                if token.startswith("--unset="):
                    env_unsets = token.split("=", 1)[1] == variable
                    index += 1
                    continue
                if token.startswith("--chdir=") or token.startswith("--split-string="):
                    index += 1
                    continue
                if token.startswith("-"):
                    # Unknown/combined env flags cannot establish the declaration themselves.
                    index += 1
                    continue
                break

        env_local = None
        while index < len(parts):
            match = _SHELL_ASSIGNMENT.match(parts[index])
            if not match:
                break
            if match.group(1) == variable:
                env_local = match.group(2) == "1"
            index += 1
        if not is_action(parts[index:]):
            return "other", None
        if env_local is not None:
            return "write", env_local
        if env_clears or env_unsets:
            return "write", False
        if shell_local is not None:
            return "write", shell_local
        return "write", exported

    writes = []
    has_other_command = False
    for token in tokens + [";"]:
        if token in {";", "&&", "||", "|", "|&", "&", "\n"}:
            kind, decision = evaluate(segment, token)
            if kind == "write":
                writes.append(decision)
            elif kind == "other":
                has_other_command = True
            segment = []
        else:
            segment.append(token)
    return not has_other_command and writes == [True]


def _command_scoped_manual_gh(cmd):
    """Whether the sole command is a declared ``gh issue`` mutation."""
    def is_issue_write(parts):
        return (len(parts) >= 3 and parts[:2] == ["gh", "issue"]
                and parts[2] in {action for _, action in _GH_WRITE})

    return _command_scoped_declaration(cmd, "ORG_ALLOW_MANUAL_GH", is_issue_write)


def _command_scoped_manual_merge(cmd):
    """Whether the sole command is a declared direct git integration.

    The hook process cannot see ``ORG_ALLOW_MANUAL_MERGE=1 git merge ...`` in ``os.environ``
    because PreToolUse runs before Bash. Keep the advertised one-shot escape genuinely one-shot:
    only a direct git merge/rebase/cherry-pick simple command is accepted here. Pipelines, command
    substitutions, a second command, or a declaration scoped to a different command fail closed.
    """
    def is_git_integration(parts):
        return (len(parts) >= 2 and parts[0] == "git"
                and parts[1] in {verb[1] for verb in _MERGE_VERBS})

    return _command_scoped_declaration(
        cmd, "ORG_ALLOW_MANUAL_MERGE", is_git_integration)


def _gh_bypass(tool_name, ti):
    """Is this an Issue mutation that bypasses the organ? Return the reason (and the command
    to run instead).
    """
    if tool_name != "Bash":
        return None
    cmd = _without_inert_heredoc_data(_command_text(ti))
    toks = _tokenize(cmd)
    # Command substitution executes even when the surrounding command only writes/prints data.
    # shlex keeps ``$(gh`` as one token, so expose the inner words explicitly. Single-quoted
    # occurrences can be conservatively held; the safe observation form is the quoted heredoc above.
    for inner in re.findall(r"\$\(([^)]*)\)|`([^`]*)`", cmd):
        toks += _tokenize(" ".join(part for part in inner if part))
    if not _has_token(toks, "gh"):
        return None
    if not os.path.isdir(os.path.join(os.getcwd(), ".orgforge")):
        return None
    for (a, b), (what, gs_args) in _GH_WRITE.items():
        if not _has_seq(toks, ("gh", a)) or not _has_token(toks, b):
            continue
        tools_dir = os.environ.get("ORG_TOOLS_DIR") or ""
        gs = os.path.join(tools_dir, "github_sync.py") if tools_dir else "github_sync.py"
        oc = os.path.join(tools_dir, "org_cycle.py") if tools_dir else "org_cycle.py"
        if gs_args:
            how = f'    python3 "{gs}" {gs_args}'
        else:
            how = (f'    python3 "{oc}" complete --role <role> --issue <N> --outputs … '
                   f"--command … --result … \\\n"
                   f"        (--domain-model-updated … | --domain-model-none …)\n"
                   f"  To change only the label or the stage:\n"
                   f'    python3 "{gs}" stage --issue <N> --stage ready|in-progress|blocked|done')
        return (f"{what} outside the organ. **Go through the organ** — it attaches "
                f"`dept` / `objective` / `parent` and the idempotency key, and leaves a record "
                f"in the ledger:\n"
                f"{how}\n"
                f"  Without the organ, `ready` keeps handing back Issues that are already "
                f"finished, new Issues are not tied to an objective, and the `domain_model` on "
                f"`cycle_completed` goes missing (all three happened in operation).\n"
                f"  Reads are not blocked (`gh issue view` / `gh issue list`). Split preparation, "
                f"mutation, and confirmation into separate Bash/exec calls (e.g. prepare the body "
                f"and check it → the organ command above on its own → `gh issue view <N>` on its "
                f"own). To rewrite by hand, declare it in the same Bash call: "
                f"`ORG_ALLOW_MANUAL_GH=1 gh issue …`. One mutation per call, and run several "
                f"Issues separately (so the ledger keeps a one-to-one record).")
    return None


# **Is the quoted text something that gets EXECUTED?** `sh -c '…'`, `eval "…"`, `xargs`
# and a pipe into a shell run their contents as commands; `grep '…'` and `echo "…"` do not.
# Without that distinction it becomes impossible to even **search for or document** a
# dangerous word — measured, three false positives.
# **A spelling must not be hideable behind an escape.** The shell expands `$'\x72\x6d'`
# to `rm`, and a different spelling misses a token match — so decode BEFORE deciding
# (raised by Codex; measured passing through).
def _decode_escapes(cmd):
    def _hex(m):
        try:
            return bytes.fromhex(m.group(1)).decode("utf-8", "replace")
        except Exception:
            return m.group(0)
    out = re.sub(r"(?:\\x([0-9a-fA-F]{2}))+",
                 lambda m: re.sub(r"\\x([0-9a-fA-F]{2})", _hex, m.group(0)), cmd)
    out = re.sub(r"\\0([0-7]{2,3})", lambda m: chr(int(m.group(1), 8)), out)
    return out


# **A difference in spelling or type must not switch enforcement off.**
# Measured: a lowercase `"bash"` in `tool_name` slipped past all three checks, and a
# `command` given as an array crashed the hook with AttributeError — and a hook that
# crashes returns no decision, which can fail open.
# Upper bound on the hook event used for a decision; beyond it the regexes effectively
# stall (measured).
_MAX_TOKENIZE_CHARS = 64 * 1024   # cap on what is handed to shlex (only shlex is slow)

_SHELL_TOOLS = ("bash", "shell", "terminal", "sh", "zsh")


def _is_shell_tool(tool_name):
    return str(tool_name or "").strip().lower() in _SHELL_TOOLS


def _held_call_atomicity(tool_name):
    """State precisely what a PreToolUse hold did (and did not) execute.

    A Bash/exec hook runs before the shell starts.  Saying only that its final mutation was held
    led operators to assume an earlier temporary-file or preparation command had succeeded, then
    to feed nonexistent/empty data to the next call.  Non-shell tools are atomic at this boundary,
    so do not incorrectly describe their input as a shell command sequence.
    """
    if _is_shell_tool(tool_name):
        return ("\n\n  **PreToolUse held this Bash/exec call before it ran, so every command in "
                "it — before and after — was not executed.** Split preparation, mutation, and "
                "confirmation into separate tool calls.")
    return (f"\n\n  **This {tool_name or 'tool'} call was held before it ran, so the tool call "
            "itself was not executed.** Do not read this as a partially executed sequence of "
            "commands the way a Bash call would be.")


def _command_text(ti):
    """Pull the command string out of tool_input. **Absorb the variation in type here.**
    It must not fall over whether it arrives as dict / str / list, under `command` or `cmd`."""
    if isinstance(ti, str):
        return ti
    if isinstance(ti, (list, tuple)):
        return " ".join(str(x) for x in ti)
    if not isinstance(ti, dict):
        return ""
    v = ti.get("command")
    if v is None:
        v = ti.get("cmd")
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v)
    if isinstance(v, dict):
        # **Look inside nested values too.** A payload shaped like
        # `{"command": {"c": "…"}}` hides the danger where no check ever sees it.
        return " ".join(_command_text(x) if isinstance(x, (dict, list, tuple)) else str(x)
                        for x in v.values())
    # **Do not truncate.** An implementation that read only the head and tail let anything
    # **hide in the middle** — measured, `echo <70k chars>; <destructive command>;
    # echo <70k chars>` passed straight through. And the slow part was never the regex:
    # at a million characters the regex costs ~10ms while `shlex.split` costs 11 seconds.
    # **Cut the slow one; keep matching over the whole string.**
    return v if isinstance(v, str) else ("" if v is None else str(v))


# **Execution whose contents cannot be read statically** — decoded or downloaded output
# piped straight into a shell.
_OPAQUE_EXEC = re.compile(
    # (0) **The shape itself: a string fed into a shell.** Whatever `echo '…' | sh` carries,
    #     it is the shape "assemble another command and run it". Nothing static can follow
    #     the positions inside it (measured: `echo '<destructive command>' | sh` slipped past
    #     the positional check). **If the contents cannot be verified, do not allow it** —
    #     writing them to a file first is enough.
    r"\b(?:echo|printf|cat)\b[^|]*\|\s*(?:ba|z|k|da)?sh\b"
    # (1) piping the result of a decode or a fetch straight into a shell
    r"|\b(?:base64|openssl\s+enc|xxd|uudecode|curl|wget)\b[^|]*\|\s*(?:ba|z|k|da)?sh\b"
    # (2) `sh -c "$( … decode … )"` — **decoding inside the substitution, then executing**
    #     (Codex's example: the pipe is inside the substitution, so (1) does not catch it)
    r"|\b(?:ba|z|k|da)?sh\b\s+-c[^\n]*\$\([^)]*"
    r"(?:base64|openssl\s+enc|xxd|uudecode|curl|wget)"
    r"|\beval\b[^\n]*\$\([^)]*(?:base64|openssl\s+enc|xxd|uudecode|curl|wget)", re.I)


# A SQL client **executes** the string handed to `-c` / `-e`.
_SQL_CLIENT = re.compile(r"\b(?:psql|mysql|mariadb|sqlite3|mongo|redis-cli)\b", re.I)
_EXECUTES_STRING = re.compile(
    r"(?:\b(?:ba|z|k|da)?sh\b\s+-c|\beval\b|\bxargs\b|\bsource\b|"
    r"\|\s*(?:ba|z|k|da)?sh\b|\|\s*python3?\b)", re.I)


def _catastrophic_reason(tool_name, ti):
    if not _is_shell_tool(tool_name):
        return None
    cmd = _without_inert_heredoc_data(_command_text(ti))
    if not cmd.strip():
        return None
    # **Look inside nested values too — but only at what actually gets executed.**
    # shlex keeps `$(rm` and `` `rm `` as single tokens, so matching on tokens alone lets
    # substitutions and backticks straight through (measured). Opening every quote instead
    # hard-blocks `grep -n "…" notes.txt` and `echo "… is dangerous"`, which makes it
    # **impossible to search for or to document a dangerous word** (also measured — that is
    # obstruction, not control).
    # The distinction is whether the string gets executed:
    #   - `$( )` / backtick … always executed → always open it
    #   - a quote            … executed only when it reaches `sh -c`, `eval`, `xargs`,
    #                          or a pipe into a shell
    # So take **only the contents** of `$( )` / backtick, and leave quotes closed. Naively
    # replacing the punctuation with spaces splits quoted text into words as well, and
    # hard-blocks commands that merely WRITE — `echo "… is dangerous" >> README.md`.
    toks = _tokenize(cmd)
    for _inner in re.findall(r"\$\(([^)]*)\)|`([^`]*)`", cmd):
        toks += " ".join(x for x in _inner if x).split()
    _dec = _decode_escapes(cmd)
    if _dec != cmd:
        toks += re.sub(r"[$'\"]", " ", _dec).split()
    if _EXECUTES_STRING.search(cmd):
        toks += re.sub(r"['\"]", " ", cmd).split()
    # **Execution whose contents cannot be read** would pass without anyone verifying them.
    # For `base64 -d | sh` or `curl … | sh`, what will run is not statically decidable
    # (raised by Codex; measured slipping past the hard-block). **If it cannot be read,
    # it does not pass.**
    if _OPAQUE_EXEC.search(cmd):
        return ("execution whose contents cannot be verified statically (a decode or a download "
                "piped straight into a shell) — what cannot be read does not pass. Write it to a "
                "file first and verify the contents")
    # **`rm` given by absolute path is still `rm`.** `/bin/rm` does not match `rm` as a token,
    # so looking only at a bare `rm` let it through (measured). Treat any word ending in `/rm`
    # the same way.
    # **A word with punctuation glued to it is still `rm`.** shlex keeps `<(rm`, `/bin/rm` and
    # `(rm` as single words, so comparing against a bare `rm` lets them through (measured:
    # `cat <(rm -rf /)` — the contents of a process substitution **are executed**).
    # Strip the leading punctuation before comparing.
    _is_rm = _has_token(toks, "rm") or any(
        isinstance(x, str) and re.sub(r"^[^\w/]+", "", x).lstrip("/").split("/")[-1] == "rm"
        for x in toks)
    recursive_rm = _is_rm and _has_token(toks, "-rf", "-fr", "-r", "-R", "--recursive")
    # rm -rf targeting root, home, or a root glob — the unambiguously catastrophic forms
    # **Treat separators as boundaries too.** Inside `$( )` or a backtick, what follows `/` is
    # `)` or `` ` ``, so matching only whitespace and end-of-line never fires. Measured: the bare
    # form was denied while command substitution, backticks and `| sh` **went straight through**.
    # **Treat invisible and invalid characters as boundaries too.** Appending U+FFFD (the
    # replacement character for invalid UTF-8) or a zero-width space was enough to break the
    # boundary match and **let it through** (measured). Neither stops execution — the shell still
    # runs `rm -rf /`. Control must not come off over a difference nobody can see.
    _BND = r"[\s;&|()`'\"�​-‍⁠﻿ ]"
    # **Also require that `rm` and the root target are CONNECTED.**
    # Hard-blocking merely because `rm`, `-rf` and `/` appear somewhere on the same line stops
    # lines that **destroy nothing when executed**, such as `echo rm -rf foo / bar` (measured).
    # A hard-block is the strongest refusal there is, so drawing it widely halts ordinary work.
    # The condition is that **no other command separator** sits between `rm` and the root target.
    # And require that `rm` stands **in command position**. Only the start of a line, just after a
    # separator, or just after a substitution is an execution position; the `rm` in
    # `echo rm -rf foo / bar` is an argument to echo and never runs.
    #
    # **Enumerating the shapes of an execution position does not work.**
    # An implementation that allowed only line-start, separator, `sudo` and `env` let
    # **15 of 18 forms through** (measured) — `{ … }`, `( … )`, `if…then`, loops, `time`,
    # `timeout`, `xargs`, `/bin/rm`, `\rm` and more. Prefixes can be invented without limit, so
    # enumeration can never catch up.
    #
    # So invert it: **exclude only the few shapes where `rm` is CONSUMED AS AN ARGUMENT, and
    # treat everything else as execution.** `echo` / `printf` / `grep` and their kin do not
    # execute their arguments. An `rm` appearing anywhere else is treated as something that could
    # run. **Fall to the dangerous side.**
    # From `#` to end of line is a comment, and **the shell executes nothing there**.
    # We were hard-blocking notes that said "this is dangerous, never do it" (measured). It cannot
    # be used to hide danger — the moment it is a comment, it does not execute.
    _ARG_CONSUMERS = r"(?:echo|printf|cat|grep|rg|egrep|fgrep|sed|awk|comm|diff|test|\[)"
    _RM_AT_CMD = (
        rf"(?<!\w)(?:{_ARG_CONSUMERS}\b(?:(?![;&|`\n]).)*?)?"        # a word that eats arguments (if any)
        rf"(?<!\w)rm\b(?:(?![;&|`\n]).)*?"
        rf"(?:^|{_BND})(/{_BND}|/\*|/$|~/?{_BND}|~/?$|\$HOME)")
    # **Open the hidden forms first, then look at position.** In `'rm -rf /' | sh` or
    # `$'\x72\x6d'` the `rm` never lands in command position in the raw string, yet **the shell
    # executes it**. Run the same "is this an execution position?" test against the unquoted form
    # and the escape-decoded form as well.
    _variants = [cmd]
    if _EXECUTES_STRING.search(cmd) or _OPAQUE_EXEC.search(cmd):
        _variants.append(re.sub(r"['\"|]", " ", cmd))
    if _dec != cmd:
        _variants.append(re.sub(r"['\"$]", " ", _dec))
    # **An `rm` consumed as an argument does not execute.** The rm in `echo rm -rf foo / bar` is
    # an argument to echo; the shell never launches rm. That is the only thing excluded here.
    _ARG_ONLY = re.compile(
        rf"(?:^|[;&|`\n]|\$\(|<\()\s*(?:\w+=\S+\s+)*{_ARG_CONSUMERS}\b"
        rf"(?:(?![;&|`\n]).)*$", re.S)
    # **xargs receives its deletion targets from the left.** Split the two sides apart and the
    # rm side carries no root target, so it is missed (measured). Treat "the left side produces
    # the root and xargs launches rm" as a single dangerous shape.
    if re.search(rf"(?:^|{_BND})(/{_BND}|/\*|~/?{_BND})(?:(?!\|).)*\|\s*xargs\b"
                 rf"(?:(?![;&|`\n]).)*?(?<![\w-])(?:/\S*/)?rm\b", cmd + " ", re.S):
        return ("recursive delete of a root/home/glob path "
                "(`rm -rf /` class) — unrecoverable")
    # **A shape that executes later is still execution.**
    #   `bash <<< '…'`   … reads from stdin and executes it
    #   `trap '…' EXIT`  … executed on exit
    #   `alias x='…'`    … executed the moment it is called
    # In each of these the danger sits inside quotes, so the plain position test cannot see it
    # (measured going straight through).
    if re.search(rf"(?:<<<|\btrap\b|\balias\b)(?:(?![;&|`\n]).)*?"
                 rf"(?<![\w-])(?:/\S*/)?rm\b(?:(?![;`\n]).)*?"
                 rf"(?:^|{_BND})(/{_BND}|/\*|/$|~/?{_BND}|~/?$|\$HOME)",
                 cmd + " ", re.S):
        return ("recursive delete of a root/home/glob path "
                "(`rm -rf /` class) — unrecoverable")
    _rm_to_root = None
    for _v in _variants:
        # **Nothing inside single quotes is expanded.** Splitting segments at the `$(` of
        # `echo '$(…)'` makes an unexpanded string look like an execution position (measured as a
        # false positive). Keep the inside of a quote as one word: do not split it in the raw cmd.
        # **An escaped quote does not open a quote.** In `echo \\'$(…)\\'` the `$(…)` **is**
        # expanded, so only genuine (unescaped) single quotes count.
        _sq = re.sub(r"(?<!\\)'[^']*(?<!\\)'",
                     lambda m: m.group(0).replace("$(", "\x00("), _v)
        for _seg in re.split(r"[;&|`\n]|\$\(|<\(", _sq):
            _seg = _seg.replace("\x00(", "$(")
            # **A comment does not execute.** Drop everything from `#` before judging.
            _seg = re.sub(r"(?:^|\s)#.*$", " ", _seg, flags=re.S)
            if not re.search(r"(?<![\w-])(?:/\S*/)?rm\b", _seg):
                continue
            # If **a word that eats arguments appears before rm** in this segment, the rm does
            # not execute. Looking only at the start of the segment missed the shapes where
            # **echo arrives partway through** — `find … -exec echo rm -rf / …` and
            # `xargs echo rm -rf /` — and hard-blocked lines that execute nothing (raised by
            # Codex, confirmed by measurement). What gets launched is echo, not rm.
            _rm_at = re.search(r"(?<![\w-])(?:/\S*/)?rm\b", _seg)
            # **The consuming word only counts when IT is in command position too.**
            # In `X=echo rm -rf /` (an assigned value), `>echo rm -rf /` (a redirect target) and
            # `case echo in echo) rm -rf /;;` (a compared word), echo is not the command and
            # **the rm does execute**. Excluding on "there is an echo before it" alone let these
            # through (raised by Codex; four of them measured succeeding).
            _before = _seg[:_rm_at.start()] if _rm_at else ""
            _consumer_is_cmd = re.search(
                rf"(?:^|\s)(?:\w+=\S+\s+)*{_ARG_CONSUMERS}(?:\s|$)", _before) and not (
                re.search(rf"=\s*{_ARG_CONSUMERS}\b", _before)          # X=echo
                or re.search(rf"[<>]\s*{_ARG_CONSUMERS}\b", _before)    # >echo
                or re.search(rf"\bcase\b", _before)                     # case … in
            )
            if _rm_at and _consumer_is_cmd:
                continue
            if re.search(rf"(?<![\w-])(?:/\S*/)?rm\b(?:(?![;&|`\n]).)*?"
                         rf"(?:^|{_BND})(/{_BND}|/\*|/$|~/?{_BND}|~/?$|\$HOME)",
                         _seg + " ", re.S):
                _rm_to_root = True
                break
        if _rm_to_root:
            break
    if recursive_rm and _rm_to_root:
        return "recursive delete of a root/home/glob path (`rm -rf /` class) — unrecoverable"
    # whole-disk / filesystem destroyers
    if _has_token(toks, "mkfs") or re.search(r"\bmkfs\.\w+", cmd):
        return "filesystem format (`mkfs`) — destroys a whole device"
    if _has_token(toks, "dd") and re.search(r"of=\s*/dev/(sd|nvme|disk|hd|mmcblk|vd)", cmd):
        return "`dd` writing to a raw block device — destroys a disk"
    if re.search(r"of=\s*/dev/(sd|nvme|disk|hd|mmcblk|vd)", cmd):
        return "raw write to a block device — destroys a disk"
    if re.search(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", cmd):
        return "fork bomb"
    return None


def rule_blast_radius(tool_name, ti):
    dim = _asset_dimension(tool_name, ti)
    if not dim:
        return None
    dimension, delta = dim
    # **A weight of 0 is the judgement "this is not metered".** `_is_regenerable_target` has
    # decided that deleting a regenerable target (node_modules / build output / .orgforge/wt/)
    # is no exposure at all. A reservation requires delta > 0 (letting a negative or a zero
    # through would leave the total unmovable, or reducible), so **what is not metered must not
    # be reserved in the first place** — being denied while trying to reserve 0 produces the
    # exact opposite of the intent: **stopping an operation that is free** (measured happening).
    if not delta or float(delta) <= 0:
        return None
    cap = _cap_for(dimension)   # env override → constitution.enforcement.caps → default (docs/11 §0)
    # **Delegate to a single operation on the writer side.** The organ used to "total up → judge
    # → print LEDGER-EVENT" and the hook would "append afterwards (ignoring failure)". That left
    # three holes:
    #   two parallel hooks could read the same committed value and both allow (the total exceeds
    #   the cap) / ignoring an append failure meant the next call saw committed=0 (the cap loses
    #   its memory) / a hold ended in a deny, so nothing recorded that anything was stopped.
    # reserve-exposure makes the check and the reservation one operation inside the lock, so
    # **only a judgement that was successfully written becomes an allow.**
    # **In an org running writerd, reserve through the RPC.** Calling ledger.py directly hits
    # "writes must go through writerd" and exits 4, which halts legitimate operation (raised
    # from a measurement).
    if os.environ.get("ORG_WRITER_SOCKET"):
        # **The hook does not relax trust.** This used to set ORG_WRITER_TRUST_SELF, but that
        # is the control plane **deciding on its own** to connect even to a caller-owned anchor,
        # which leaves room for it to be pointed at a forged socket. If it is to be relaxed,
        # **the user states so explicitly.**
        return ["writer_client.py", "reserve-exposure", "--",
                "--dimension", dimension, "--delta", str(delta), "--cap", cap,
                "--actor", "harness-agent", "--window-since", _window_since(),
                "--session-id", SESSION_ID, "--tool-use-id", TOOL_USE_ID,
                "--rule", "blast_radius"]
    return ["ledger.py", "reserve-exposure", LEDGER_ROOT, "--dimension", dimension,
            "--delta", str(delta), "--cap", cap, "--actor", "harness-agent",
            "--window-since", _window_since(),
            "--session-id", SESSION_ID, "--tool-use-id", TOOL_USE_ID,
            "--rule", "blast_radius"]


# ── Agent spawn discipline (docs/06 §2.1.1) ──────────────────────────────────
# A manager that spawns a subordinate must either hand it a SEAM CONTRACT (so integrating
# siblings don't drift) or declare the child INDEPENDENT (a non-integrating fan-out — e.g. a
# parallel enumeration whose outputs are never merged). This turns the profile's "please use
# handoff.py" from advice into structure: without one of the two, the spawn is blocked. Not an
# organ/ledger rule — it's a pure shape check on the spawn prompt, so it returns a verdict
# directly (see main()'s SPAWN_GATE branch) rather than an organ argv.
# Look for the **structure** handoff.py emits. A bare phrase ("seam contract") was dropped
# because it occurs in prose — "no seam contract is attached" was passing AS a seam declaration
# (the same hole as the INDEPENDENT substring match, on this side too). Structure does not appear
# inside a negation: someone may write "there is no `Inputs you receive:`", but they will
# essentially never place a colon-terminated heading inside a negative sentence.
_SEAM_MARKERS = ("outputs you must produce", "boundary contract", "inputs you receive",
                 "## your slice")
# **The declaration must be at the start of a line.** Matching anywhere in the text lets **a
# negation pass as a declaration** — "I have attached neither a contract nor INDEPENDENT:" matched
# as (A) verbatim (found by a live probe). The harmful shape is a (B) spawn that says "this work
# is not independent, so a contract is attached" being misread as (A): since **(A) waives the
# `owns` declaration**, an accidental match wins the waiver. The guard's own message says to write
# one line at the top of the child prompt, so the check is aligned with what the message asks for.
_INDEP_RE = re.compile(
    r"^\s*(?:INDEPENDENT\s*:|独立\s*:"
    r"|(?:this (?:spawn|child|task) is )?non-integrating\b"
    r"|outputs are not merged\b"
    r"|independent fan-?out\b)",
    re.I | re.M)

def _seam_from_referenced_file(prompt_raw):
    """Look for a seam contract by having **the guard itself read** the file the prompt points at.

    This used to consider only the prompt body, on the grounds that "the contents of a reference
    cannot be guaranteed at spawn time". But that is only true *if the guard does not read it* —
    read it and it can be guaranteed. Restricting to the body meant pasting a 150-line seam
    contract every time, which crowds the maker's context.

    Only **an absolute path, or a relative path under the org root**, is read. A path is a string
    written in the prompt and therefore untrusted, so nothing outside the org and nothing huge
    is opened.
    """
    hits = re.findall(r"(?:^|[\s\"'`(=])((?:/|\./|\.orgforge/|[\w.-]+/)[\w./-]+\.(?:md|txt))",
                      prompt_raw)
    root = os.getcwd()
    for rel in hits[:8]:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        try:
            path = os.path.realpath(path)
            # Under the org root or a temp directory only. Never read an arbitrary file.
            if not (path.startswith(os.path.realpath(root))
                    or path.startswith("/tmp") or path.startswith("/private/tmp")
                    or path.startswith(os.path.realpath(tempfile.gettempdir()))):
                continue
            if not os.path.isfile(path) or os.path.getsize(path) > 512 * 1024:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                body = f.read(512 * 1024).lower()
        except Exception:
            continue
        if any(m in body for m in _SEAM_MARKERS):
            return path
    return None


def _declared_owns(prompt):
    """Parse the `owns:` / `owns —` territory list a seam contract declares in a spawn prompt.
    handoff.py writes an `Owns:` line (docs/06 §2.1.1); we read the paths/globs after it so the gate
    can check them against live sibling claims. Best-effort line/inline parse; returns a set of tokens."""
    owns = set()
    for m in re.finditer(r"(?im)^\s*owns\s*[:\-—]\s*(.+)$", prompt):
        for tok in re.split(r"[,\s]+", m.group(1).strip()):
            tok = tok.strip("`'\"").rstrip(".;")
            if tok:
                owns.add(tok)
    return owns


def _live_claimed_territories(ledger_root):
    """The set of work_territory strings currently claimed and not yet released, from the ledger.
    A `work_claimed` opens a claim; a `cycle_completed`/`result_deployed`/`result_retired` on the same
    territory (or an explicit release) closes it. Pure read; empty on any error (fail toward allow for
    the collision check specifically — the seam-contract requirement below still holds)."""
    try:
        import json as _json
        path = os.path.join(ledger_root, "ledger.jsonl")
        if not os.path.exists(path):
            return {}
        open_terr = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    e = _json.loads(line)
                except ValueError:
                    continue
                p = e.get("payload", {})
                if e.get("class") == "work_claimed" and p.get("work_territory"):
                    open_terr[p["work_territory"]] = p.get("role")
                elif e.get("class") in ("cycle_completed", "result_deployed", "result_retired",
                                        "claim_released") and p.get("work_territory"):
                    open_terr.pop(p["work_territory"], None)
        return open_terr
    except Exception:
        return {}


def spawn_needs_seam_or_independence(tool_name, ti):
    """Return None to allow, or a deny-reason string to block. Gate the Agent/Task spawn tool.

    DEFAULT-ON (docs/12 §5 Layer-1 #1): a must-not-violate control across a fan-out belongs in the
    enforcement layer, not a prompt (docs/10 §2). Opt OUT with ORG_REQUIRE_SEAM=0 for a deliberately
    ungated dev run. Two gates: (a) SHAPE — the child must carry a seam contract or an independence
    declaration; (b) NON-COLLISION — if it declares `owns:` territory, that territory must not intersect
    a sibling's live claim in the ledger, turning reconcile.py's post-hoc collision SCAN into a
    spawn-time PRECONDITION (the research's single-writer-ownership, prevented not detected)."""
    if tool_name not in ("Agent", "Task"):
        return None
    # spec-first (docs/11 §0): env ORG_REQUIRE_SEAM (dev override) → constitution.enforcement.seam_gate
    # → default ON. An org ships the gate ON in its spec; a dev may loosen it locally, but two installs
    # of the same org fan out the same way.
    seam_env = os.environ.get("ORG_REQUIRE_SEAM")
    if seam_env is not None:
        if seam_env in ("0", "false", "no", "off"):
            return None                  # explicit dev opt-out
    elif str(_enforcement().get("seam_gate", "on")).lower() in ("0", "false", "no", "off"):
        return None                      # the spec declared the gate off
    prompt_raw = ti.get("prompt") or ""
    prompt = prompt_raw.lower()
    has_seam = any(m in prompt for m in _SEAM_MARKERS)
    # Line starts only (use prompt_raw — prompt is lowercased but the positions are the same;
    # re.M looks at the head of every line)
    has_indep = bool(_INDEP_RE.search(prompt_raw))
    seam_file = None
    if not (has_seam or has_indep):
        # Not in the body: read the file the prompt points at and look there (pass by reference)
        seam_file = _seam_from_referenced_file(prompt_raw)
        has_seam = seam_file is not None
    if not (has_seam or has_indep):
        # **List the ways through in order of how short they actually are.** The wording used to
        # read as though handoff.py were the main route and INDEPENDENT: an afterthought, but in
        # practice the latter alone was what got people through — and it was the correct route.
        # Making a supervisor in a hurry read the name of a tool they will not use is waste.
        return ("this Agent spawn carries no seam contract and no independence declaration. "
                "Two ways through:\n"
                "  (A) If the output will not be merged with a sibling's — write one line at the "
                "top of the child prompt: `INDEPENDENT: <why it is independent>`. That is enough.\n"
                "  (B) If it will be integrated with a sibling's — put a seam contract in the body "
                "(`## Your slice` / `Inputs you receive:` / `Outputs you MUST produce:`). "
                "`tools/handoff.py <role> --slice … --inputs … --outputs … --owns …` assembles one. "
                "You may write it to a file and reference that instead (the guard reads it).\n"
                "  **(A) waives the `owns` declaration.** So if you are spawning several children "
                "in parallel, checking that they are not aimed at the same worktree or the same "
                "file is **yours to do** — under (A) the guard cannot check for a collision "
                "(there is no declaration to compare). docs/06 §2.1.1.")
    # NON-COLLISION: a declared owns territory must not overlap a live sibling claim (concurrent-write
    # drift is PREVENTED here, not detected later by reconcile.py collision).
    if LEDGER_ROOT:
        declared = _declared_owns(prompt_raw)
        if declared:
            live = _live_claimed_territories(LEDGER_ROOT)
            clash = sorted(t for t in declared if t in live)
            if clash:
                holders = ", ".join(f"{t} (held by {live[t]})" for t in clash)
                return (f"this spawn's declared owns-territory collides with a live sibling claim: "
                        f"{holders}. Two agents writing the same territory concurrently is the "
                        f"concurrent-write drift the org prevents at spawn time — give the child a "
                        f"disjoint `owns:` set, or wait for the holder to release (docs/12 §5).")
    return None


# Only the blast-radius cap is wired into the tool loop today. reconcile.py `mandate` and the
# doctrine organ are real, tested code but are NOT PreToolUse rules — mandate fires on a contested
# decision (not every tool call) and doctrine loads via the SessionStart hook, not here. Wiring
# them as tool-loop rules is future work; the honest surface is one enforced rule + one injected
# organ (doctrine at session start), not three enforced here (external review, 2026-07).
def rule_iteration_cap(tool_name, ti):
    """ITERATION/SPEND-CAP (docs/12 §5 #2): on a spawn (each Agent/Task = a delegated cycle), hold the
    role if its cycle count or token spend in the window would exceed a cap. Enforcement-layer home for
    the runaway kill — active only when a cap env is set, so an org that hasn't opted into a budget is
    unaffected. Role from ORG_ROLE; caps from ORG_MAX_CYCLES / ORG_MAX_TOKENS."""
    if tool_name not in ("Agent", "Task"):
        return None
    role = os.environ.get("ORG_ROLE", "")
    # spec-first (docs/11 §0): env ORG_MAX_* (dev override) → constitution.enforcement.iteration →
    # built-in default. DEFAULT-ON: an org ships iteration limits in its spec, so a runaway loop is
    # killed on every install, not only where three env vars happened to be set. null in the spec = no
    # cap for that dimension. Role is still the runtime identity (ORG_ROLE); without a role we can't
    # attribute cycles, so the cap can't apply.
    itr = _enforcement().get("iteration") or {}
    max_cycles = os.environ.get("ORG_MAX_CYCLES")
    if max_cycles is None and itr.get("max_cycles") is not None:
        max_cycles = str(itr["max_cycles"])
    max_tokens = os.environ.get("ORG_MAX_TOKENS")
    if max_tokens is None and itr.get("max_tokens") is not None:
        max_tokens = str(itr["max_tokens"])
    if not role or (not max_cycles and not max_tokens):
        return None
    argv = ["guardrails.py", "cycles", LEDGER_ROOT, "--role", role,
            "--window-since", _window_since()]
    if max_cycles:
        argv += ["--max-cycles", max_cycles]
    if max_tokens:
        argv += ["--max-tokens", max_tokens]
    return argv


RULES = [rule_blast_radius, rule_iteration_cap]



# ── HALT: being stopped is not a warning (H4a) ───────────────────────────────
# **What is allowed through, for recovery.** Deny everything and a halted org can neither be
# diagnosed nor repaired. Observation (reads), verification and safe repair only — **ordinary
# work stays stopped**.
_RECOVERY_READONLY = re.compile(
    r"^\s*(?:"
    r"git\s+(?:status|log|diff|show|branch\s*$|rev-parse|remote\s+-v|fsck)\b"
    r"|(?:cat|head|tail|less|wc|grep|rg|ls|stat|file|du|df)\b"
    # **`find` is not a read-only command.** It carries `-exec` / `-execdir` / `-delete` / `-ok`,
    # which makes it **an entry point for any command** — and it can delete (measured: during a
    # HALT, `find . -maxdepth 0 -exec python3 -c '...' {} +` was allowed and its contents ran).
    # Same reason `env` was removed. For reading alone, `ls` and `grep` suffice.
    # Do not judge by the shape of the arguments — **stamping out dangerous spellings one at a
    # time failed three times during this audit.**
    r"|find\s+(?![^|;&\n]*-(?:exec|execdir|delete|ok|fprint|fls))[^|;&\n]*$"
    r"|python3?\s+\S*(?:ledger|status|guardrails|org_lint|repro_lint)\.py\s+"
    r"(?:verify|halt-status|schema|census|digest|view|status|check|cat)\b"
    r"|gh\s+(?:issue|pr)\s+(?:view|list)\b"
    # **`env` was removed.** In the form `env FOO=1 <destructive command>` it becomes **an entry
    # point for any command** (raised by Codex; measured getting through during a HALT).
    # To simply look at the environment, use `printenv`.
    r"|echo\b|pwd\b|printenv\b|which\b"
    r")", re.I)
# Safe repair — only operations that restore the ledger's health. **Releasing the halt does not
# belong here** (H4b / H1 depend on it). Treat `python3` / `/usr/bin/python3` / `python`, with
# flags such as `-B` or `-u` attached, as one single prefix. **Do not restrict recovery to a
# single spelling.**
_PY = r"^\s*(?:\S*/)?python[0-9.]*(?:\s+-[A-Za-z]+)*"

_RECOVERY_REPAIR = re.compile(
    # **Allow the release command itself.** Stop `release-halt` too during a HALT and an org that
    # has halted once can never move again (measured: it was absent from the allowlist and denied).
    # The release is protected by a receipt signature, so allowing it here does not loosen control
    # — control only exists when **being stoppable and being restorable** hold together.
    # **How the interpreter is written must never be what makes recovery impossible.** Measured
    # (on re-audit): `/usr/bin/python3`, `python3 -B`, and a quoted script path were all falsely
    # rejected. A recovery path that works under exactly one spelling is a deadlock in practice.
    # Absorb the interpreter path, flags like `-B`, and quoting, here in this one place.
    _PY + r"\s+['\"]?\S*ledger\.py['\"]?\s+"
    r"(?:schema\s+--fix|append\s+.*--class\s+correction|release-halt)\b"
    # **Under Stage B the release goes through the writer too.** A direct `ledger.py release-halt`
    # is refused by the single-writer gate (measured exit=4), so without allowing
    # `writer_client.py release-halt` there is **no way to release at all**, and an org stopped
    # once can never move again. The release itself is protected by a receipt signature, so
    # allowing it here does not loosen control.
    # **The stopping side (trip-halt) is not recovery, so it is not allowed.**
    r"|" + _PY + r"\s+['\"]?\S*writer_client\.py['\"]?\s+release-halt\b"
    # The operational state machine owns its recovery transition. These commands remain ledger-
    # validated and session/authority checked; blocking the only recovery path would deadlock it.
    r"|" + _PY + r"\s+['\"]?\S*operational_state\.py['\"]?\s+"
    r"(?:status|doctor|authorize|project|begin-recovery|revalidate|recover)\b",
    re.I)


def _halt_recovery_allowed(tool_name, tool_input):
    """Is this an action to allow even during a halt? **Observation, verification and safe repair
    only.**

    Ordinary work stays stopped — being halted means work does not proceed. Draw this widely and
    we are back to "the org halted but execution carried on".
    """
    if not _is_shell_tool(tool_name):
        return False           # Write / Edit / ApplyPatch are not allowed during a halt
    cmd = _command_text(tool_input).strip()
    if not cmd:
        return False
    # **Match against the form the shell will execute.** Measured (fifth re-audit): `-e""xec`
    # becomes `-exec` once quotes are removed, so `find . -maxdepth 0 -e""xec echo Q {} +` passed
    # the allowlist and **actually ran** (confirmed by `QUOTED_EFFECT .`). As long as the allowlist
    # reads "the string as written" while the shell executes "the string with quotes removed",
    # that gap will be exploited — the same shape of bypass occurred four times in this audit.
    # So **fold quotes away before matching**. Fixing it here means not only find but every rule
    # added to the allowlist in future gets the same protection.
    # **Do not hand-roll the quote folding.** An implementation that folded only empty quotes
    # closed `-e""xec` but left `-ex"ec"` (measured). Split into tokens with the same lexer the
    # shell uses (shlex) and match on **the arguments the shell actually passes**. A spelling that
    # cannot be interpreted is not allowed through.
    # **Judge the metacharacters on the raw string first.** shlex folds a newline into whitespace,
    # so looking after tokenisation misses the newline-joined `git status\ngit push --force`
    # (measured as a regression). "Not allowed if it contains chaining, substitution or
    # redirection" is decided on **the form before the shell reads it**.
    if re.search(r"[;&|`\n><]|\$\(", cmd):
        return False
    try:
        _toks = shlex.split(cmd)
    except ValueError:
        return False           # quote が閉じていない等 — 解釈できないなら通さない
    if not _toks:
        return False
    cmd = " ".join(_toks)
    # **allowlist は先頭一致である。** つまり `git status; <破壊的コマンド>` のように
    # 連結すれば、先頭だけ安全に見せて後ろで何でも実行できる。実測で7通りの回避が通った
    # （`;` `&&` `||` 改行 パイプ `$( )` バッククォート）。
    # **HALT 中は「1つの安全なコマンド」だけを通す。** 連結・置換を含むなら、
    # 中身が何であれ通さない。復旧は1コマンドずつ行えばよい。
    # `>` `>>` も足す。**読み取りコマンドでもリダイレクトすればファイルを壊せる**
    # （実測: HALT 中に `git status > important` が通った）。
    # `<` も同じ理由で足す。**process substitution `<(cmd)` は任意コマンドを実行できる**
    # （実測: HALT 中に `--receipt <(python3 -c ...)` が通り、中の python3 が走った）。
    # `<` 単体のリダイレクトも、通す理由が無い。**同じ穴が3回開いたので、
    # 個別の記法を1つずつ塞ぐのをやめ、ここを「メタ文字があれば通さない」境界にした。**
    if re.search(r"[;&|`\n><]|\$\(", cmd):
        return False
    return bool(_RECOVERY_READONLY.match(cmd) or _RECOVERY_REPAIR.match(cmd))


def _check_halt(tool_name, tool_input):
    """active な halt があれば deny する。**毎回台帳を読む。**

    宣言（環境変数や設定）ではなく **記録** で止める。宣言を読むだけなら、宣言を消せば動く。
    台帳が読めないときは halt とみなす — 止まっているか分からないなら止める。
    """
    if not LEDGER_ROOT:
        return
    # **import せずに、別プロセスで聞く。** `ledger.py` を import すると、そのモジュールの
    # トップレベルが hook プロセスの中で走る — 壊れた（あるいは差し替えられた）ledger.py が
    # `sys.exit(0)` を持っていれば、**hook がそこで allow として終了する**（実測でそうなった）。
    # 統制の判定を、判定対象と同じプロセスで動かしてはいけない。
    # **停止の判定も writer に聞く。** org 側の symlink を張り替えて空の台帳を見せられると、
    # hook は停止を見失う（実測: HALT 中でも exit 10 → 0 になった）。writer は起動時に固定した
    # 実体のパスを見る。
    _cmd = ([sys.executable, os.path.join(TOOLS_DIR, "writer_client.py"), "halt-status"]
            if os.environ.get("ORG_WRITER_SOCKET")
            else [sys.executable, os.path.join(TOOLS_DIR, "ledger.py"),
                  "halt-status", LEDGER_ROOT])
    try:
        r = subprocess.run(_cmd, capture_output=True, encoding="utf-8",
                           errors="replace", timeout=30)
    except Exception as e:
        # 「確かめられない」は評価できなかった case — 開発用の逃げ道（ORG_HOOK_FAIL_OPEN）が
        # 効く側である。**読めた結果が halt なら効かせない**（下で _deny する）。
        if FAIL_OPEN:
            print(f"org_hook: halt の状態を確かめられない（{e}）(fail-open) — allowing",
                  file=sys.stderr)
            return
        _deny(f"org guardrail: halt の状態を確かめられない（{e}）。\n"
              f"  **止まっているか分からないなら止める。** ledger.py を実行できることを"
              f"確認すること。")
        return
    if r.returncode not in (0, 10):
        if FAIL_OPEN:
            print(f"org_hook: halt-status が exit {r.returncode} (fail-open) — allowing",
                  file=sys.stderr)
            return
        _deny(f"org guardrail: halt の状態を確かめられない（halt-status が exit "
              f"{r.returncode}）。**止まっているか分からないなら止める。**\n"
              f"  {((r.stdout or '') + (r.stderr or '')).strip()[:300]}")
        return
    halt = None
    if r.returncode == 10:
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    cand = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(cand, dict) and cand.get("halted"):
                    halt = cand
                    break
        if halt is None:
            _deny(f"org guardrail: halt-status が halt を報告したが（exit 10）、"
                  f"内容を読めなかった。**判断が読めないなら止める。**\n"
                  f"  {(r.stdout or '').strip()[:300]}")
            return
    if not halt:
        return
    if _halt_recovery_allowed(tool_name, tool_input):
        print(f"org_hook: HALT 中だが、観測・検証・安全な修復として通す: "
              f"{((tool_input or {}).get('command') or '')[:80]}", file=sys.stderr)
        return
    _deny(f"org guardrail HALTED: この org は停止している。**gated な行為は通らない。**\n"
          f"  理由: {halt.get('reason')}\n"
          f"  発動: {halt.get('tripped_by') or '?'} / trigger={halt.get('trigger') or '?'} "
          f"/ 出所={halt.get('source')}"
          + (f" / seq={halt['seq']}" if halt.get("seq") else "") + "\n"
          f"  通るのは観測・検証・安全な修復だけである（git status / ledger verify / "
          f"ledger halt-status / schema --fix など）。\n"
          f"  **解除は自動では行われない。** 何が起きたかを確かめ、復旧を検証してから解除する。")


_OPERATIONAL_READ_TOOLS = {"Read", "Grep", "Glob", "WebFetch", "WebSearch"}
_OPERATIONAL_RECOVERY = re.compile(
    _PY + r"\s+['\"]?\S*operational_state\.py['\"]?\s+"
    r"(?:status|doctor|authorize|project|begin-recovery|revalidate|recover)\b", re.I)


def _command_scoped_adaptation(cmd):
    """Read a one-command adaptive declaration before Bash executes it.

    The hook cannot see prefix assignments through ``os.environ``. Keep this deliberately smaller
    than a shell: one simple command, no chaining/substitution/redirection, and four explicit values.
    The declaration can authorize one bounded act; it cannot smuggle a second command beside it.
    """
    if not isinstance(cmd, str) or len(cmd) > 64 * 1024 or \
            re.search(r"[;&|`\n<>]|\$\(", cmd):
        return None
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None
    if not parts:
        return None
    index = 0
    if parts[0] == "env":
        index = 1
        if index < len(parts) and parts[index] == "--":
            index += 1
    values = {}
    while index < len(parts):
        match = _SHELL_ASSIGNMENT.match(parts[index])
        if not match:
            break
        if match.group(1) in {"ORG_ADAPTIVE_ACTION", "ORG_ADAPTIVE_ENVELOPE",
                             "ORG_ADAPTIVE_PHASE", "ORG_ADAPTIVE_ARTIFACT"}:
            values[match.group(1)] = match.group(2)
        index += 1
    required = {"ORG_ADAPTIVE_ACTION", "ORG_ADAPTIVE_ENVELOPE", "ORG_ADAPTIVE_PHASE",
                "ORG_ADAPTIVE_ARTIFACT"}
    if index >= len(parts) or not required <= set(values):
        return None
    if any(not str(values[key]).strip() for key in required):
        return None
    values["_command_argv"] = parts[index:]
    return values


def _adaptive_action_matches_command(declaration):
    """Keep a declared action tied to an observable command shape, not a self-applied label."""
    action = declaration.get("ORG_ADAPTIVE_ACTION")
    argv = declaration.get("_command_argv") or []
    if not argv:
        return False
    executable = os.path.basename(argv[0]).lower()
    if action == "cross_harness_failover":
        if executable in {"claude", "codex", "gemini", "opencode", "forge", "gt"}:
            return True
        return executable.startswith("python") and any(
            os.path.basename(token) == "run_department.py" for token in argv[1:3])
    if action in {"safe_stop", "observe_only", "scope_reduction", "human_handback",
                  "goal_abandonment"}:
        joined = " ".join(argv)
        return bool(re.search(
            r"(?:^|\s)(?:\S*/)?adaptation\.py\s+outcome\b|"
            r"(?:^|\s)(?:\S*/)?org_goal\.py\s+(?:pause|block|complete)\b|"
            r"^orgforge\s+(?:adaptation\s+outcome|org-goal\s+(?:pause|block|complete))\b",
            joined))
    return False


def _operational_ship_action(tool_name, tool_input):
    if not _is_shell_tool(tool_name):
        return None
    command = _without_inert_heredoc_data(_command_text(tool_input))
    patterns = (
        (r"(?:^|[;&|\n]\s*)git\s+(?:[^;&|\n]+\s+)?merge\b", "merge"),
        (r"(?:^|[;&|\n]\s*)git\s+(?:[^;&|\n]+\s+)?push\b", "ship"),
        (r"\bgh\s+pr\s+merge\b", "merge"),
        (r"\b(?:npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b|\bgh\s+release\s+create\b", "publish"),
        (r"\bdocker\s+push\b|\bkubectl\s+(?:apply|rollout)\b|\bterraform\s+apply\b|\bvercel\s+deploy\b", "deploy"),
    )
    for pattern, action in patterns:
        if re.search(pattern, command, re.I):
            return action
    return None


def _operational_recovery_allowed(tool_name, tool_input):
    if tool_name in _OPERATIONAL_READ_TOOLS:
        return True
    if not _is_shell_tool(tool_name):
        return False
    command = _command_text(tool_input).strip()
    if _halt_recovery_allowed(tool_name, tool_input):
        return True
    return bool(_OPERATIONAL_RECOVERY.match(command))


def _operational_status():
    code, output = _run_organ(["operational_state.py", "status", "--root", LEDGER_ROOT, "--json"])
    if code:
        return None, f"operational-state status failed (exit {code}): {output.strip()[:300]}"
    try:
        body = json.loads(output)
        state = body.get("state") if isinstance(body, dict) else None
    except json.JSONDecodeError:
        state = None
    if not isinstance(state, dict) or state.get("effective_state") not in {
            "NORMAL", "DEGRADED", "HALTED", "RECOVERING"}:
        return None, "operational-state status returned no recognized state"
    return state, None


def _ledger_mentions_operational_state():
    try:
        with open(os.path.join(LEDGER_ROOT, "ledger.jsonl"), encoding="utf-8") as stream:
            for line in stream:
                if any(name in line for name in (
                        '"operational_state_transitioned"', '"circuit_state_changed"',
                        '"artifact_tainted"', '"recovery_probe_recorded"')):
                    return True
    except OSError:
        return False
    return False


def _check_operational_state(tool_name, tool_input):
    """Enforce the effective state at the same PreToolUse boundary as HALT and blast radius."""
    if not LEDGER_ROOT:
        return
    state, error = _operational_status()
    if error:
        # Old organizations have no operational-state contract or events. Preserve compatibility,
        # but once the ledger contains this protocol, inability to evaluate it is fail-closed.
        if _ledger_mentions_operational_state():
            _deny("org guardrail: operational state cannot be evaluated. "
                  "The ledger contains operational events, so unknown state is not NORMAL.\n  " + error)
        return
    effective = state["effective_state"]
    if effective == "NORMAL":
        return
    ship_action = _operational_ship_action(tool_name, tool_input)
    if ship_action:
        _deny(f"org guardrail {effective}: {ship_action} is forbidden until the org returns to NORMAL. "
              "Complete the declared recovery probe and every taint revalidation first.")
    if _operational_recovery_allowed(tool_name, tool_input):
        return
    if effective in {"HALTED", "RECOVERING"}:
        _deny(f"org guardrail {effective}: only observation and the ledger-validated recovery path "
              "are allowed; ordinary mutation and delegation remain stopped.")
    declaration = _command_scoped_adaptation(_command_text(tool_input)) \
        if _is_shell_tool(tool_name) else None
    if not declaration:
        _deny("org guardrail DEGRADED: this action has no one-shot adaptive declaration. "
              "Use one simple Bash command prefixed with ORG_ADAPTIVE_ACTION, "
              "ORG_ADAPTIVE_ENVELOPE, ORG_ADAPTIVE_PHASE, and ORG_ADAPTIVE_ARTIFACT; "
              "ship actions remain forbidden.")
    if not _adaptive_action_matches_command(declaration):
        _deny("org guardrail DEGRADED: the declared adaptive action does not match the command "
              "shape. A label cannot authorize an unrelated shell mutation.")
    command = [sys.executable, os.path.join(TOOLS_DIR, "operational_state.py"), "authorize",
               "--root", LEDGER_ROOT, "--action", declaration["ORG_ADAPTIVE_ACTION"],
               "--envelope", declaration["ORG_ADAPTIVE_ENVELOPE"],
               "--phase", declaration["ORG_ADAPTIVE_PHASE"],
               "--artifact", declaration["ORG_ADAPTIVE_ARTIFACT"], "--json"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except Exception as exc:
        _deny(f"org guardrail DEGRADED: adaptive authorization could not run ({exc}).")
        return
    if result.returncode:
        detail = (result.stdout or result.stderr).strip()[:500]
        _deny(f"org guardrail DEGRADED: action is outside the active adaptive envelope.\n  {detail}")



def _org_root_of_targets(tool_input):
    """コマンド/引数に現れる **絶対パス** をたどり、gated org（`.orgforge/ledger` を持つ祖先）
    を返す。**cwd に org が無くても、操作先が org なら統制を効かせる**ため。
    見つからなければ None。判定に使うだけで、ここでは何も実行しない。"""
    import re as _re_mod
    blob = " ".join(str(v) for v in tool_input.values() if isinstance(v, (str, int, float)))
    # **相対パスも解決する。** 絶対パスだけを見ていたので、`cd ./halted && npm run build` が
    # 通っていた（実測: 再監査で HALT 中の org に対して exit=0、しかも理由は
    # 「org state が無いので allow」——**見つからなければ全部通す**という最悪の形）。
    # `cd ../halted` も同じ。cwd から解決すれば同じ org に着く以上、区別する理由がない。
    _abs = _re_mod.findall(r"(?:^|[\s'\"=])(/[^\s'\";|&)]+)", blob)
    _rel = _re_mod.findall(r"(?:^|[\s'\"=])(\.{1,2}/[^\s'\";|&)]*)", blob)
    # **`cd halted` のように `./` すら付かない形も解決する。** 実測（再監査4回目）:
    # `./halted` と `../halted` だけを足したので `cd halted && npm run build` が素通りし、
    # しかも理由は「org state 無し→allow」だった。**綴りを1つずつ足すのは3回失敗している。**
    # cwd 直下に実在するディレクトリを指す語は、すべて候補として解決する。
    _bare = []
    for _w in _re_mod.findall(r"(?:^|[\s'\"=])([A-Za-z0-9._-]+(?:/[^\s'\";|&)]*)?)", blob):
        try:
            if os.path.isdir(os.path.join(os.getcwd(), _w.rstrip("/"))):
                _bare.append(_w)
        except Exception:
            pass
    for raw in _abs + _rel + _bare:
        cand = os.path.abspath(raw.rstrip("/"))
        # そのパス自身と祖先をたどる（存在しなくてよい — 消す先が対象だから）
        for _ in range(40):
            if os.path.isdir(os.path.join(cand, ".orgforge", "ledger")):
                return cand
            nxt = os.path.dirname(cand)
            if nxt == cand:
                break
            cand = nxt
    return None

def main():
    # **不正な UTF-8 でも落ちない。** sys.stdin.read() は decode 失敗で
    # UnicodeDecodeError を投げ、hook がそこで落ちていた（実測 exit=1）。
    # バイト列で読んで、置換しながら decode する。
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    except Exception:
        raw = ""
    # **長い event を「大きいから」という理由で拒否しない。**
    # 最初の実装は 64KB を超えた event を deny していたが、それは
    # `echo <70,000文字>` のような **正当な長いコマンドを止める**（Codex が実測で指摘）。
    # 長いファイル一覧、base64 の埋め込み、SQL スクリプトは現実に存在する。
    # 止めたいのは「正規表現が事実上停止すること」であって、長さそのものではない。
    # よって **event はそのまま解析し、危険語の照合だけを先頭 N 文字に限る**
    # （危険なコマンドは先頭に現れる — 後ろに何万文字あっても実行されるのは同じ1行）。
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        event = {}
    # **object でない JSON でも落ちない。** `[1,2,3]` や `null` は json.loads を通るので
    # 上の except では拾えず、直後の `.get()` が AttributeError になって **hook が落ちた**
    # （実測 exit=1）。落ちた hook は判定を返さない = fail-open になりうる。
    if not isinstance(event, dict):
        event = {}
    # only gate PreToolUse; anything else passes (the hook may be wired to several events)
    if event.get("hook_event_name") not in (None, "PreToolUse"):
        _allow()
    # **event の cwd を使って org を決め直す。**
    # LEDGER_ROOT は import 時にプロセスの cwd から解決される。だが harness は hook を
    # org の外から起動しうるので（だからこそ event に `cwd` が入っている）、そのままだと
    # **org が見つからず、宣言した cap も判定も built-in default に落ちる** — hook は
    # 動いているように見えるのに、その org の統制で判定していない（実測: プラグイン dir から
    # 起動すると宣言 6 に対して cap=150 が使われた）。env の明示指定があればそれを優先する。
    _ev_cwd = event.get("cwd") or ""
    if _ev_cwd and not os.environ.get("ORG_LEDGER_ROOT") and os.path.isdir(_ev_cwd):
        try:
            os.chdir(_ev_cwd)                              # 以降の discover はこの org を見る
        except OSError:
            pass
        global LEDGER_ROOT, _ENFORCEMENT_CACHE
        _rediscovered = _discover_ledger()
        if _rediscovered and _rediscovered != LEDGER_ROOT:
            LEDGER_ROOT = _rediscovered
            _ENFORCEMENT_CACHE = None                      # 別 org の宣言を読み直す
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    # 冪等キーの材料。**(session_id, tool_use_id, rule, event_class) で一意にする** —
    # tool_use_id 単独では別 session・別 rule の衝突を防げない。
    # 欠けていれば metered action は writer 側で deny される（同一性を確かめられないなら、
    # hook の再実行を二重計上しない保証が成り立たない）。
    global SESSION_ID, TOOL_USE_ID
    # 2026-07 に code.claude.com/docs/en/hooks で確認: PreToolUse の stdin は
    # `tool_use_id`（"Unique identifier for this tool call"）と `session_id` を snake_case で
    # 持つ。subagent 実行時は `agent_id` / `agent_type` も入る。
    SESSION_ID = str(event.get("session_id") or "")
    TOOL_USE_ID = str(event.get("tool_use_id") or "")
    # **subagent の識別を session に含める。** 親と子が同じ session_id を共有するなら、
    # 別の agent が同じ tool_use_id を持ちうるかはドキュメントに書かれていない（不明）。
    # 書かれていないことを「衝突しない」と読まない — 識別子に足しておけば、衝突しても
    # 別の予約として数えられる（過大計上より、二重計上の見落としのほうが危ない）。
    _agent = str(event.get("agent_id") or "")
    if _agent:
        SESSION_ID = f"{SESSION_ID}/{_agent}"

    # CATASTROPHIC denylist — a hard block that does NOT depend on the ledger or the cap. The cap is a
    # daily budget (bounds many cuts); it cannot stop ONE unrecoverable cut (`rm -rf /`, `mkfs`, `dd`
    # to a raw disk, a fork bomb), which is weight-3 and passes under any non-zero cap. This fires
    # first, before any budget logic, and even when no org/ledger is configured — a catastrophic
    # command is never a budget question. Sandbox opt-out: ORG_ALLOW_CATASTROPHIC=1.
    if os.environ.get("ORG_ALLOW_CATASTROPHIC") != "1":
        cat = _catastrophic_reason(tool_name, tool_input)
        if cat:
            _deny(f"org guardrail HARD-BLOCKED this {tool_name}: {cat}. This is blocked regardless of "
                  f"budget — a single such command is unrecoverable. Set ORG_ALLOW_CATASTROPHIC=1 only "
                  f"in a disposable sandbox.")

    # Agent-spawn discipline is a pure shape check on the spawn prompt — it needs no ledger, so
    # it runs before the ledger gate. Blocks a manager that spawns a child with neither a seam
    # contract nor an independence declaration (docs/06 §2.1.1); opt-in via ORG_REQUIRE_SEAM.
    seam_reason = spawn_needs_seam_or_independence(tool_name, tool_input)
    if seam_reason:
        _deny(f"org guardrail HELD this {tool_name} spawn: {seam_reason}")

    # 保護ブランチへの直接統合を hold（台帳の有無に依存しない形状検査）。宣言があれば通すが、
    # **通したことを台帳に残す** — 迂回が記録に残らないまま常用されるのを防ぐ。
    if (os.environ.get("ORG_ALLOW_MANUAL_MERGE") == "1"
            or _command_scoped_manual_merge(_command_text(tool_input))):
        byp = _integration_bypass(tool_name, tool_input)
        if byp and LEDGER_ROOT:
            # **迂回そのものを記録する。** 宣言を許すが、記録に残らない迂回は許さない —
            # そうしないと宣言が常用され、迂回が見えないまま高速化する。
            # **記録できなければ通さない。** 宣言は記録されるから許されるのであって、
            # 宣言したと言えば許されるのではない。
            err = _record_bypass("manual merge into a protected branch", tool_input)
            if err:
                _deny(f"org guardrail: 迂回の宣言を記録できなかったので通さない — {err}\n"
                      f"  ORG_ALLOW_MANUAL_* は「宣言が台帳に残る」ことと引き換えの逃げ道で"
                      f"ある。残らないなら、逃げ道は成立しない。")
    else:
        byp = _integration_bypass(tool_name, tool_input)
        if byp:
            _deny(f"org guardrail HELD this {tool_name}: {byp}"
                  f"{_held_call_atomicity(tool_name)}")

    # 同じ形で、organ を通さない Issue の書き換えも hold する
    if (os.environ.get("ORG_ALLOW_MANUAL_GH") == "1"
            or _command_scoped_manual_gh(_command_text(tool_input))):
        ghb = _gh_bypass(tool_name, tool_input)
        if ghb and LEDGER_ROOT:
            # **記録できなければ通さない。** 宣言は記録されるから許されるのであって、
            # 宣言したと言えば許されるのではない。
            err = _record_bypass("manual gh issue write", tool_input)
            if err:
                _deny(f"org guardrail: 迂回の宣言を記録できなかったので通さない — {err}\n"
                      f"  ORG_ALLOW_MANUAL_* は「宣言が台帳に残る」ことと引き換えの逃げ道で"
                      f"ある。残らないなら、逃げ道は成立しない。")
    else:
        ghb = _gh_bypass(tool_name, tool_input)
        if ghb:
            _deny(f"org guardrail HELD this {tool_name}: {ghb}"
                  f"{_held_call_atomicity(tool_name)}")

    # **HALT の検査。** 台帳を要する他の検査より前に置く — 止まっている org では、
    # cap の予約を試すことにも意味が無い（そして予約は台帳に書く＝止まっているのに書く）。
    _check_halt(tool_name, tool_input)

    if not LEDGER_ROOT:
        # **cwd に org が無いことは「統制の対象が無い」ことではない。**
        # 空のディレクトリから harness を起動し、**管理下の org を絶対パスで操作する**と、
        # 台帳が見つからず fail-open で素通しになっていた（実測: 空 cwd から
        # `rm -rf <実 org>/.orgforge/ledger` が exit 0 で通った）。`rm -rf /` は止まるのに
        # 実 org は消せる、という穴である。
        # そこで **コマンドが触るパスの側から org を探す**。触る先が gated org なら、
        # その org の統制で判定する。
        _target_root = _org_root_of_targets(tool_input)
        if _target_root:
            try:
                os.chdir(_target_root)
            except OSError:
                pass
            _re = _discover_ledger()
            if _re:
                LEDGER_ROOT = _re
                _ENFORCEMENT_CACHE = None
                print(f"org_hook: cwd に org は無いが、操作先 {_target_root} の統制で判定する",
                      file=sys.stderr)
                # **org を解決したら、その台帳に対して HALT を確かめ直す。**
                # `_check_halt()` は org が判明する *前* に一度走っている。cwd が org の外だと
                # そのとき見る台帳が無く、**HALT 中の org へ絶対パスで書き込めた**
                # （実測 B3: Bash / Write / Edit の4経路すべてが素通しした）。
                # 止まっている org は、どこから呼ばれても止まっていなければならない。
                _check_halt(tool_name, tool_input)
    if not LEDGER_ROOT:
        # no ledger configured => the org has no state to judge against. Fail-safe: allow, but
        # say so loudly on stderr so a misconfiguration is visible, not silent.
        print("org_hook: ORG_LEDGER_ROOT unset — no org state to gate against; allowing "
              "(set it to enable guardrails)", file=sys.stderr)
        _allow()

    # Operational mode is a ledger-backed authorization boundary. HALT above remains the
    # writer-owned latch; this adds derived HALT (for example an expired envelope), DEGRADED
    # one-shot authorization, RECOVERING isolation, and the unconditional no-ship rule.
    _check_operational_state(tool_name, tool_input)

    for rule in RULES:
        argv = rule(tool_name, tool_input)
        if not argv:
            continue
        code, output = _run_organ(argv)
        # **RPC 経由も同じ検査にかける。** 以前は直接呼びの形だけを見ており、
        # writer_client 経由の予約は終了コードだけで判断されていた。
        is_reservation = argv[:2] in (["ledger.py", "reserve-exposure"],
                                      ["writer_client.py", "reserve-exposure"])
        if is_reservation:
            # **終了コードだけを信じない。** 予約は structured result を返すので、
            # `exit 0 かつ decision == "allow"` の組でしか通さない。
            # 実測: deny を印字して exit 0 する writer に対して、hook は allow していた。
            # JSON が無い・読めない・decision が allow 以外・code と矛盾 — すべて deny。
            verdict = None
            for line in output.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    cand = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(cand, dict) and "decision" in cand:
                    verdict = cand
                    break
            if verdict is None:
                # **判断が読めないのは「評価できなかった」case である。** ここは
                # ORG_HOOK_FAIL_OPEN（開発用の逃げ道）が効く側 — writer を起動できない、
                # 出力が壊れている、といった環境の問題である。
                # 一方、**読めた結果が hold / deny なら、それは評価できている**ので
                # FAIL_OPEN では通さない（下の分岐）。
                if FAIL_OPEN:
                    print(f"org_hook: 上限の予約が structured result を返さなかった"
                          f"（exit {code}）: {output.strip()[:200]} (fail-open) — allowing",
                          file=sys.stderr)
                    continue
                _deny(f"org guardrail HELD this {tool_name} call: "
                      f"上限の予約が structured result を返さなかった"
                      f"（exit {code}）。**判断が読めないなら通さない。**\n"
                      f"  {output.strip()[:300]}")
            decision = verdict.get("decision")
            if code == 0 and decision == "allow":
                continue        # 予約は writer が既に永続化している
            # 語彙を揃える。監督（と検査）が探すのは "HELD" である — 判断の出所が
            # organ から writer に移っても、止まったことの呼び名は変えない。
            _deny(f"org guardrail HELD this {tool_name} call: 上限の予約が allow を"
                  f"返さなかった (exit {code}, decision={decision!r}, "
                  f"reason={verdict.get('reason')!r})。\n"
                  f"  {verdict.get('detail') or ''}"[:600])
        if code == 10:
            _deny(f"org guardrail HELD this {tool_name} call: {output.strip()[:400]}")
        if code == 0:
            # 従来の organ（LEDGER-EVENT を印字するだけのもの）は、ここで host が書く。
            _append_emitted(output)
            continue        # keep checking other rules
        # ANY other code (2 = interpreter couldn't run the script, 99 = our sentinel, a crash,
        # a timeout) means the guardrail did NOT return a clean allow. Fail-SAFE: block, never
        # let an unevaluable guardrail become a silent allow (docs/05 §2.4). Dev may opt out.
        if FAIL_OPEN:
            print(f"org_hook: organ returned {code}: {output} (fail-open) — allowing",
                  file=sys.stderr)
            continue
        _deny(f"org guardrail could not be evaluated (exit {code}) — fail-safe block: "
              f"{output.strip()[:300]}")
    _allow()


if __name__ == "__main__":
    main()
