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
  - stdin: JSON with at least {hook_event_name, tool_name, tool_input, cwd, session_id}
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
line reached into the harness and held this action for the human" (docs/11 §0). Fail-OPEN is never
the default: a rule whose organ errors blocks with a clear message (fail-safe, docs/06 §2.4),
unless ORG_HOOK_FAIL_OPEN=1 is set for a permissive dev mode.

Usage (wired identically in Claude settings.json and Codex hooks.json):
  {"matcher": "Bash|Write|Edit", "type": "command",
   "command": "python3 <repo>/integrations/common/org_hook.py"}
Environment:
  ORG_LEDGER_ROOT   directory holding ledger.jsonl (required; the org's state)
  ORG_TOOLS_DIR     directory holding the organ *.py (default: <this>/../../tools)
  ORG_HOOK_FAIL_OPEN=1  allow on organ error instead of blocking (dev only)
"""
import json
import os
import re
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
LEDGER_ROOT = os.environ.get("ORG_LEDGER_ROOT", "")
FAIL_OPEN = os.environ.get("ORG_HOOK_FAIL_OPEN") == "1"


def _deny(reason):
    """Emit the shared deny contract and exit 2 (blocks on BOTH harnesses)."""
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "deny",
                                  "permissionDecisionReason": reason}}
    print(json.dumps(out))
    print(reason, file=sys.stderr)
    sys.exit(2)


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
                           capture_output=True, text=True, timeout=30)
        except Exception:
            pass   # a failed write-back must never turn an allow into a crash


def _run_organ(argv):
    """Run an organ command; return (exit_code, combined_output). Never raises."""
    try:
        p = subprocess.run([sys.executable, os.path.join(TOOLS_DIR, argv[0])] + argv[1:],
                           capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout + p.stderr)
    except Exception as e:  # organ missing / crashed / timed out
        return 99, f"organ {argv[0]} failed to run: {e}"


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
        cmd = ti.get("command") or ti.get("cmd") or ""
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
    if tool_name not in ("Bash", "Shell", "Terminal"):
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
    toks = _tokenize(cmd)
    destructive = (
        _has_token(toks, "rm", "dd", "truncate", "mkfs", "shred")                 # dangerous binaries
        or _has_token(toks, "DROP", "DELETE", "TRUNCATE")                         # SQL (as whole tokens)
        or _has_token(toks, "--force", "--delete", "-delete")                     # force / find -delete
        or _has_seq(toks, ("git", "push"), ("git", "reset"), ("reset", "--hard"),
                    ("terraform", "destroy"), ("kubectl", "delete"))
        or "shutil.rmtree" in cmd                                                 # python dotted call
        or _redirects_to_system_path(cmd)                                        # `> /etc/…` overwrite of a system path
        or bool(re.search(r"\|\s*(bash|sh)\b", cmd))                              # pipe-to-shell
    )
    if destructive:
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
    "destructive_ops": "50",   # rm/DROP/force per day — irreversible but routine in real work; scope-weighted
    "external_writes": "30",   # outbound POST/PUT/DELETE per day — irreversible side effect
    "infra_changes":   "20",   # apply to real infra per day — irreversible, rarer than local deletes
    "shell_effect":    "100",  # DEPRECATED: the classifier no longer emits shell_effect (unknown≠metered);
                               #   kept only so an existing ORG_CAP_SHELL_EFFECT override is not an error.
    "file_mutations":  "500",  # overwriting existing files per day — reversible under VCS; high ceiling
}

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
    budget that resets — the "death by a thousand cuts" guard of docs/11 §2.1), so the window must
    ROLL FORWARD, or committed exposure accumulates for all time and the cap eventually blocks every
    action (the frozen-epoch deadlock). Default: a rolling DAILY window (the day of _now_ts, at
    00:00), so the budget resets each day with no operator action. Override with ORG_WINDOW_SINCE for
    a custom boundary, or ORG_WINDOW=all to opt into an all-time cap deliberately."""
    override = os.environ.get("ORG_WINDOW_SINCE")
    if override:
        return override
    if os.environ.get("ORG_WINDOW") == "all":
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
def _catastrophic_reason(tool_name, ti):
    if tool_name not in ("Bash", "Shell", "Terminal"):
        return None
    cmd = ti.get("command") or ti.get("cmd") or "" if isinstance(ti, dict) else (ti if isinstance(ti, str) else "")
    if not cmd.strip():
        return None
    toks = _tokenize(cmd)
    recursive_rm = _has_token(toks, "rm") and _has_token(toks, "-rf", "-fr", "-r", "-R", "--recursive")
    # rm -rf targeting root, home, or a root glob — the unambiguously catastrophic forms
    if recursive_rm and re.search(r"(?:^|\s)(/\s|/\*|/$|~/?\s|~/?$|\$HOME)", cmd + " "):
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
    cap = os.environ.get(f"ORG_CAP_{dimension.upper()}", _DEFAULT_CAPS.get(dimension, "3"))
    return ["guardrails.py", "cap", LEDGER_ROOT, "--dimension", dimension,
            "--delta", str(delta), "--cap", cap, "--actor", "harness-agent",
            "--window-since", _window_since()]


# ── Agent spawn discipline (docs/07 §2.1.1) ──────────────────────────────────
# A manager that spawns a subordinate must either hand it a SEAM CONTRACT (so integrating
# siblings don't drift) or declare the child INDEPENDENT (a non-integrating fan-out — e.g. a
# parallel enumeration whose outputs are never merged). This turns the profile's "please use
# handoff.py" from advice into structure: without one of the two, the spawn is blocked. Not an
# organ/ledger rule — it's a pure shape check on the spawn prompt, so it returns a verdict
# directly (see main()'s SPAWN_GATE branch) rather than an organ argv.
_SEAM_MARKERS = ("outputs you must produce", "boundary contract", "inputs you receive",
                 "seam contract", "## your slice")
_INDEP_MARKERS = ("independent:", "non-integrating", "no seam", "outputs are not merged",
                  "independent fan-out")

def _declared_owns(prompt):
    """Parse the `owns:` / `owns —` territory list a seam contract declares in a spawn prompt.
    handoff.py writes an `Owns:` line (docs/07 §2.1.1); we read the paths/globs after it so the gate
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

    DEFAULT-ON (docs/17 §5 Layer-1 #1): a must-not-violate control across a fan-out belongs in the
    enforcement layer, not a prompt (docs/16 §2). Opt OUT with ORG_REQUIRE_SEAM=0 for a deliberately
    ungated dev run. Two gates: (a) SHAPE — the child must carry a seam contract or an independence
    declaration; (b) NON-COLLISION — if it declares `owns:` territory, that territory must not intersect
    a sibling's live claim in the ledger, turning reconcile.py's post-hoc collision SCAN into a
    spawn-time PRECONDITION (the research's single-writer-ownership, prevented not detected)."""
    if tool_name not in ("Agent", "Task"):
        return None
    if os.environ.get("ORG_REQUIRE_SEAM", "1") in ("0", "false", "no", "off"):
        return None                      # explicit opt-out for an ungated dev run
    prompt_raw = ti.get("prompt") or ""
    prompt = prompt_raw.lower()
    has_seam = any(m in prompt for m in _SEAM_MARKERS)
    has_indep = any(m in prompt for m in _INDEP_MARKERS)
    if not (has_seam or has_indep):
        return ("this Agent spawn carries neither a seam contract (build it with tools/handoff.py: "
                "slice + inputs/outputs the child integrates to) nor an explicit independence "
                "declaration (start the child prompt with 'INDEPENDENT: ...' if its output is never "
                "merged with a sibling's). Recursive splits drift without an owned seam — docs/07 §2.1.1.")
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
                        f"disjoint `owns:` set, or wait for the holder to release (docs/17 §5).")
    return None


# Only the blast-radius cap is wired into the tool loop today. reconcile.py `mandate` and the
# doctrine organ are real, tested code but are NOT PreToolUse rules — mandate fires on a contested
# decision (not every tool call) and doctrine loads via the SessionStart hook, not here. Wiring
# them as tool-loop rules is future work; the honest surface is one enforced rule + one injected
# organ (doctrine at session start), not three enforced here (external review, 2026-07).
RULES = [rule_blast_radius]


def main():
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        event = {}
    # only gate PreToolUse; anything else passes (the hook may be wired to several events)
    if event.get("hook_event_name") not in (None, "PreToolUse"):
        _allow()
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

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
    # contract nor an independence declaration (docs/07 §2.1.1); opt-in via ORG_REQUIRE_SEAM.
    seam_reason = spawn_needs_seam_or_independence(tool_name, tool_input)
    if seam_reason:
        _deny(f"org guardrail HELD this {tool_name} spawn: {seam_reason}")

    if not LEDGER_ROOT:
        # no ledger configured => the org has no state to judge against. Fail-safe: allow, but
        # say so loudly on stderr so a misconfiguration is visible, not silent.
        print("org_hook: ORG_LEDGER_ROOT unset — no org state to gate against; allowing "
              "(set it to enable guardrails)", file=sys.stderr)
        _allow()

    for rule in RULES:
        argv = rule(tool_name, tool_input)
        if not argv:
            continue
        code, output = _run_organ(argv)
        if code == 10:
            _deny(f"org guardrail HELD this {tool_name} call: {output.strip()[:400]}")
        if code == 0:
            # allow — but record the allowed exposure so the NEXT call's aggregate check sees it
            # (closes the emit->append loop; without this the cap never accumulates). Only the
            # allow decision is written; a held call was already denied above and never happens.
            _append_emitted(output)
            continue        # keep checking other rules
        # ANY other code (2 = interpreter couldn't run the script, 99 = our sentinel, a crash,
        # a timeout) means the guardrail did NOT return a clean allow. Fail-SAFE: block, never
        # let an unevaluable guardrail become a silent allow (docs/06 §2.4). Dev may opt out.
        if FAIL_OPEN:
            print(f"org_hook: organ returned {code}: {output} (fail-open) — allowing",
                  file=sys.stderr)
            continue
        _deny(f"org guardrail could not be evaluated (exit {code}) — fail-safe block: "
              f"{output.strip()[:300]}")
    _allow()


if __name__ == "__main__":
    main()
