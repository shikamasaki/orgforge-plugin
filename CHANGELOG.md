# Changelog

All notable changes to orgforge-plugin. This project follows a pragmatic semver:
minor = new mechanisms/features, patch = fixes, major = breaking articulation changes.

## 0.6.0

Loop reliability — the failure modes a practitioner hits building an autonomous loop, checked against
the code and closed where the code fell short.

### Added
- **docs/16 — Loop reliability.** Why an unattended loop survives: a loop pass is a series system, so
  `n` decisions at accuracy `p` succeed `p^n` (10×0.95 ≈ 60%) — cut the decision *count* before
  sharpening steps (Barlow & Proschan 1965). Load-bearing constraints belong in the **enforcement layer**
  (hooks/lint, deterministic), not the request layer (prompts, probabilistic); a **subagent doesn't
  inherit the parent's prompt**, so cross-fan-out control must be a hook (with the honest caveat that the
  child's call reaching the hook is a harness property). State is **explicit in the ledger**, not context;
  trust is **staged read-only-first**. Grounded in the loop-engineering literature (docs/sources.md §16,
  r_kaga and y-hirakaw).
- **Catastrophic denylist** (`org_hook.py`). A verification pass found that the blast-radius cap — a
  *daily budget* — could not stop a single unrecoverable command: at the default cap, `rm -rf /` passed
  (weight 3, ~16 before the budget tripped). The denylist now **hard-blocks** the catastrophic class
  (`rm -rf /`/`~`/root-glob, `mkfs`, `dd` to a raw block device, fork bombs) regardless of budget and
  even with no ledger configured. Deliberately narrow — ordinary `rm -rf ./build` / `node_modules` stay
  cap-metered, not blocked. Sandbox opt-out: `ORG_ALLOW_CATASTROPHIC=1`.

### Fixed
- **docs/16 subagent-gating claim made honest.** The doc had asserted the hook "gates every subagent at
  every depth" as a plugin property; whether a subagent's tool call reaches `PreToolUse` is a *harness*
  property. The doc now states the plugin is correct-by-construction (verdict from the raw call + ledger,
  no inherited context) and requires a harness that fires the event for subagents — the docs/09 host
  contract, not a reimplementation.

## 0.7.1

Simplify the drive: delegate it to Claude Code's `/loop`, keep only the monitoring.

### Changed
- **`/org-start` drives with `/loop`, not CronCreate.** The drive — firing each cycle on a cadence — is
  now delegated to Claude Code's built-in `/loop` (R0: borrow the harness's loop, don't build one).
  `/org-start` prints three invocations (`/loop 15m /org-tick`, `/loop 60m /org-work`, `/loop 6h
  /org-discover`) — no cron expressions, no CronList idempotency dance. The SessionStart nudge and
  QUICKSTART/SCHEDULER updated to match.
- **The monitoring stays with the org.** `/loop` fires a command but can't judge whether a *due org
  check* ran; `tick.py`'s missed-check detection (a due check with no `verify_event` = MISS) is the
  org-specific part `/loop` can't provide, so it stays — "the loop stopped" is still a detected fact,
  not silence (docs/16). Delegate the drive, keep the monitor.
- OS cron (`scheduler-install.sh`) demoted to the one case `/loop` can't cover: running 24/7 with no
  session open. For everyday attended/kept-open runs, the three `/loop`s are the whole drive.

## 0.7.0

The ideal-state build-out (docs/17): a six-opinion synthesis defined what orgforge is *for* — a
spec-driven factory whose product is a verifying unattended loop and whose yield is a compounding
context base. This release closes the enumerated gap in three layers.

### Layer 1 — the loop can't run away (all enforcement-layer)
- **Concurrent-write prevention.** The seam/independence spawn gate is now **default-on** (opt out with
  `ORG_REQUIRE_SEAM=0`), and a spawn declaring `owns:` territory that collides with a live sibling's
  claim is refused — turning reconcile's post-hoc scan into a spawn-time precondition (single-writer
  ownership, prevented not detected).
- **Iteration/token/spend cap in the hook** (`guardrails.py cycles`, `ORG_MAX_CYCLES`/`ORG_MAX_TOKENS`)
  — the runaway kill ("$3-5, not $180") the blast-radius cap couldn't make.
- **Circuit breaker on non-progress** (`guardrails.py stall`) — trips a wedged cycle (identical output
  twice, or flat fraction) and frees its slot, over the `progress_recorded` stream it already writes.
- **O9 no-domain-deliverable lint tooth** — a mechanistic/control role may hold no contract.deliverable
  (the docs/15 §5 tooth, now implemented; catches the implement-without-judge case O8 misses).
- **Harness-capability probe** (`tools/harness_probe.py`, `/org-verify-guards`) — certify PreToolUse
  fires for a spawned subagent before trusting the org to fan out.

### The heart — learning accumulates and is used; the domain model grows
- **Learning feeds forward and is measured.** `/org-work` checks each item against `nearby_deaths` /
  `death_causes` before delegating; `learning.py repeats` escalates a death cause that reappears (the
  org re-made a recorded mistake) so "learning lifts quality" is a checked fact.
- **Reuse fires.** `/org-work` consults `reusable_modules` / `parts_inventory` before authoring, and
  `cycle_completed.reused` records what was pulled — reuse is now visible, not a library nobody imports.
- **The SSoT / domain model grows during operation.** `/org-work` settles domain rules IN the work
  cycle (co-commit, not a deferred task); `conventions.py growth` reports the domain model's size so
  rising inferability is a checked fact.

### Layer 2 — a factory, not a workshop
- **External-signal front door** (`/org-triage`) — a bug/issue/feedback becomes a triaged backlog item;
  the host feeds it from an issue tracker (SCHEDULER.md), compressing the human's input to one label.

### Layer 3 — anyone can use it
- **One status board** (`/org`, `tools/status.py`) — "how's my org?" in one glanceable GREEN/AMBER/RED
  answer, in the user's language, without reading the ledger. Command surface reframed: the few you use
  (`/org-found`, `/org-start`, `/org`, `/org-triage`) vs the internal metabolism (`/org-work` etc.) that
  runs on cadence.
- **Version drift fixed** (plugin.json / README now agree).

### Lower-priority reliability
- **Bounded retry/backoff** on a transient organ failure (`_run_organ`) so one flake doesn't hard-block
  an overnight run; a clean verdict is never retried.
- **Proven-rollback** (`guardrails.py rollback`) — a reversible action with no declared undo escalates,
  so silence-consent never trusts an untested reversibility claim.

## 0.5.1

Follow the quickstart, get a running org — the metabolism starts in-session without hunting for how.

### Added
- **`/org-start`** — one idempotent command brings the org to its running state in the current session:
  it registers the recurring cycles (`/org-tick`, `/org-work`, `/org-discover`) via Claude Code's
  `CronCreate`, checking `CronList` first so it never double-registers. Session-scoped (stops when the
  session closes; OS cron via `scheduler-install.sh` is the 24/7 path).
- **SessionStart nudge to start the org.** On an org session (ledger + role set), the SessionStart hook
  now injects a prompt asking the model to run `/org-start` — so the org starts on its own at the top of
  the session. A hook cannot call `CronCreate` itself (SessionStart hooks cannot invoke tools), so this
  is an instruction the model acts on, with `/org-start` as the guaranteed manual fallback. Non-org
  sessions get no nudge.

### Changed
- **QUICKSTART §6 rewritten** around `/org-start` as the start step, and corrected the "unattended 24/7"
  claim: in-session scheduling is session-only; the OS cron is the genuinely-unattended path.

## 0.5.0

The scheduler is real now, not just documented. Previously SCHEDULER.md described how one *could*
wire the cadence but nothing actually registered it — so nothing ran unattended.

### Added
- **`scheduler-install.sh` / `scheduler-uninstall.sh`** — one command installs the org's metabolism
  on the **OS cron**, so it runs 24/7 with no Claude Code session open. It writes crontab entries that
  invoke `claude -p "/org-tick" | "/org-work <role>" | "/org-discover <role>"` headless, with the
  plugin attached (hooks + doctrine injection fire) and ORG_* env inlined; output streams to
  `$ORG_LEDGER_ROOT/cron.log`; each entry is tagged `# orgforge:<role>` for clean removal. `--dry-run`
  previews the lines; intervals of 60+ minutes become valid hourly cron expressions (no invalid `*/60`).

### Changed
- **SCHEDULER.md corrected.** The in-session schedulers (`/schedule`, `/loop`) are **session-only** —
  they stop when Claude Code exits and are not "unattended." The doc now states this plainly and points
  to the OS-cron install for a genuinely 24/7 org (docs/09 §4 names "a cron" first for this reason).

## 0.4.3

### Fixed
- **`2>/dev/null` and `> /dev/null` are no longer charged as destructive.** The redirect-to-absolute-path
  check (`(\||>>?)\s*/`) fired on stderr suppression and `/dev/null` sinks, so a read-only search like
  `grep -r foo . 2>/dev/null` was metered as a destructive op and drained the daily budget — the reason
  the cap had to be raised repeatedly. The check now excludes `/dev/*` sinks and stderr redirects and
  matches only a genuine overwrite of a system path (`> /etc/…`, `>> /usr/…`). Real system-path
  overwrites and pipe-to-shell stay destructive; `2>/dev/null`, `> /dev/null 2>&1`, and relative-path
  redirects (`> out.log`, `>> ./local.txt`) draw down nothing.

## 0.4.2

Stop the guardrail from taxing benign work, right-size the caps for real days, and ship a proper
reference so operators aren't reading source to configure the thing.

### Fixed
- **Unknown/read-only shell is no longer metered.** The classifier used to charge a `shell_effect`
  budget for any command it couldn't classify — so benign work (`git status`, `find`, `du`, an
  unfamiliar CLI) quietly drained the daily budget until the cap blocked everything, a false-positive
  deadlock. Now "unknown" is not "dangerous": only explicit destructive / external / infra patterns
  draw down a budget; reads, build tooling, and unclassified shell draw down nothing. (Also fixes a
  2-word benign-match bug where `git status` exactly could slip the allowlist.)

### Changed
- **Right-sized per-day caps.** With the daily rolling window (0.4.0), the caps are per-day budgets;
  the old floor of 3 was a hand-count that a research/ML day blew through immediately. New defaults:
  `destructive_ops` 3→**50**, `external_writes` 3→**30**, `infra_changes` 3→**20**, `file_mutations`
  200→**500**. Still trips a genuine runaway (hundreds of irreversible acts/day); no longer blocks a
  normal day. `ORG_CAP_SHELL_EFFECT` is deprecated (unused; kept so an old override is not an error).

### Added
- **`REFERENCE.md`** — the flat lookup operators were missing: every environment variable (with
  defaults), every command, the org's files, the ledger events you touch most, and a troubleshooting
  section for the problems people actually hit (cap deadlock, benign-flagged commands, missing
  injection, updating the plugin). Linked from README and QUICKSTART; QUICKSTART's env table updated
  to the new defaults.

## 0.4.1

Work-in-progress survives a context wipe. Half-done work now lives in the ledger, not in the
conversation, so `/clear` or a fresh session no longer loses "how far did we get."

### Added
- **Progress checkpoints** (`ledger-schema.yaml`). `cycle_started`/`cycle_completed` gain a
  `candidate_id` (in-flight is now per-item, not just a per-role count), and a new
  `progress_recorded {role, candidate_id, fraction, phase, done_so_far, next_step, blocked_by,
  artifacts}` event records "how far / what's done / the next step / any blocker" at each milestone.
- **`work_in_progress` view** (`ledger.py`). Resolves the candidates started-but-not-completed, each
  with its latest checkpoint — the recovery source after a context wipe.
- **Automatic resume injection** (`org_session_start.py`). The SessionStart hook now injects the role's
  work in progress alongside its doctrine — so a fresh session (after `/clear`, a crash, or a scheduled
  wake) picks up from `next_step` automatically, with no `/org-resume` needed. "Just continue" works.
- **`/org-resume`** — the manual counterpart: show a role's in-progress board and pick up an item.

### Changed
- **`/org-work` records as it goes.** The PM loop now checkpoints keyed by `candidate_id`
  (started → progress at each milestone → completed), and states the discipline explicitly: work only
  items that are on the backlog; submit first if it isn't, so nothing is invisible/unrecoverable.

## 0.4.0

The running metabolism: a department now has a driven backlog, a PM loop that delegates in
parallel, a self-improvement loop, and a scheduler wired to the harness's own loop — plus the
knowledge-aggregation guarantee made load-bearing, and two guardrail deadlocks fixed. Aligns the
plugin version with the autonomous-founding narrative the docs already describe (v0.3/v0.4).

### Added
- **Driven backlog with two intake paths** (`ledger-schema.yaml`, `attention.py`). `candidate_submitted`
  gains `source: mandate|self`; top-down instructions and self-raised tasks share one backlog
  (`open_experiments`) and are prioritized on one footing. An in-ranking **mandate rides a floor**
  (zone of acceptance, Simon 1947) so a live instruction is never starved by low-priority self work;
  an off-ranking mandate gets no floor (a visible drift signal). (docs/12)
- **The PM loop** (`/org-work <role>`). Select from the backlog by situated attention, delegate the
  selected items to subordinates **in parallel** (one `Task` each, where the split is genuine), record
  `cycle_completed`. Parallelism is a judgment, not a mandate.
- **The discovery loop** (`/org-discover <role>`). Problemistic search raises `source: self` backlog
  items from aspiration gaps, scoped to the role's own domain; append-only, fail-quiet when there is
  no gap. (docs/12)
- **Decomposition doctrine** (`docs/15`, projected into `ROLE.md`). How a manager splits an assignment,
  grounded in Parnas (information hiding), Simon (near-decomposability), Thompson (interdependence),
  Becker & Murphy (coordination cost), Conway. Never split reciprocal work; cut at the design secret;
  each child carries a seam contract; route another role's domain to that role.
- **Scheduler wiring** (`integrations/claude-code/SCHEDULER.md`). Realize `schedule.yaml`'s cadences on
  Claude Code's own scheduler (`/schedule`, `/loop`) — R0-conformant ("the harness's own loop"), no R0
  change, wiring confined to the integration layer.
- **`ARCHITECTURE.md`** — the whole-system map: ecosystem (neutral core → projection → harness, organs,
  enforcement vs advisory) and lifecycle (founding → projection → operation → guardrails → evolution).

### Changed
- **O8 no-doctrine-capture lint tooth** (`org_lint.py`). No control role may carry `implement` together
  with `judge`/`review` — a coordinator that produces a domain deliverable collapses maker and checker
  and pools domain knowledge in the boss instead of the field role that owns it (docs/08 §1.1, docs/15
  §3). Generalizes O6's "authorization holder must not implement" to every adjudicating seat.

### Fixed
- **Word-boundary destructive classification** (`org_hook.py`). The blast-radius classifier tested
  destructive tokens as substrings (`"rm " in cmd`, `"-f " in cmd`), so a path like `.../fx-ml-platform/…`
  or a flag like `grep -f` was miscounted as destructive and eventually blocked every command. Now
  tokenizes and matches on word boundaries; operators/dotted calls stay on tight-anchored regex.
- **Rolling-window deadlock** (`org_hook.py`). The blast-radius window was hardcoded to `1970-01-01`
  (all-time) while appended events were stamped `1970` too — read-window and write-ts diverged, so
  committed exposure accumulated forever and the cap eventually **blocked every edit**. Now a rolling
  **daily** window (both the append ts and the read window share one `_now_ts` clock); the budget
  resets each day with no operator action. `ORG_WINDOW=all` opts back into an all-time cap deliberately.

## 0.2.0

Hierarchical doctrine, refounding, delegation seams, and an operating-phase spine —
plus a redesigned blast-radius cap that no longer blocks normal work.

### Added
- **Hierarchical per-role doctrine hand-off** (`tools/handoff.py`). A manager hands each
  subordinate a packet: the child's slice, a **seam contract** (inputs/outputs/owns/forbid), and
  **doctrine scoped to that slice** — so knowledge narrows going down and splits by trade
  (`ui-worker` ≠ `api-worker` ≠ `db-worker`), and a parent's broader brain never leaks down. The
  runner (`run_department.py`) wires `ORG_DOCTRINE_ROOT` + `--plugin-dir` so a top-level launch
  fires the doctrine-injection hook automatically. (docs/07 §2.1)
- **Doctrine remap for refounding** (`doctrine.py remap`). When roles are renamed / split /
  merged, every live claim follows as an asset; a claim that maps to nothing **blocks** the
  refound rather than being silently lost. (docs/06 §4.4, docs/07 §2.2)
- **Spawn seam-contract gate** (`ORG_REQUIRE_SEAM=1`). An `Agent`/`Task` spawn is blocked unless
  its prompt carries a seam contract or an explicit `INDEPENDENT:` declaration — recursive splits
  can't drift on an un-owned interface. (docs/07 §2.1.1)
- **Silence-consent gate** (`guardrails.py consent`). A reversible backlog action rides the
  delegated tier (silence = consent, proceeds); an irreversible one (deploy/spend/destroy/…) holds
  for an explicit human ack. (docs/06 §2.1)
- **STALE-REFERENCE auto-trigger** (`guardrails.py staleref --auto`). Derives the trigger event +
  bound roles from the ledger's latest reference change, so a central re-prioritization propagates
  to departments without hand-fed arguments. (docs/11 §2.3, docs/12 §3.1)
- **DEPENDENCY-STALL dependency edges** (`reconcile.py stall`). Reads `work_claimed.depends_on`
  edges to report who a blocked role awaits, which downstream roles are impacted, and the
  lowest-common-owner to route to — instead of cycle timing alone. (docs/11 §2.4)
- **QUICKSTART.md** — install, the one required setting, guardrail tuning, and a verified
  "prove it blocks" snippet.

### Changed
- **Blast-radius cap now meters irreversibility, not activity.** The old flat "every file write
  costs 1 against a cap of 3" blocked a normal build at its 4th file. Now: creating a new file
  (decided by a filesystem stat), reads, and build tooling (`npm`, `pytest`, `git commit`) are
  **not metered**; the scarce low caps are reserved for `destructive_ops` (scope-weighted —
  `rm -rf` = 3), `external_writes`, `infra_changes`; overwriting an existing file is
  `file_mutations` (high cap 200). A 300-file build proceeds; `rm -rf` still hard-stops. New caps
  are tunable via `ORG_CAP_*`. (docs/11 §2.1)

### Docs
- Operating-phase flow integrated into existing homes (no new file): the two-level backlog
  (org-wide ranking + per-dept next-task) in docs/12 §3.1; the registrar as org-wide priority
  owner in docs/06 §2.6; reversible-vs-irreversible consent in docs/06 §2.1.
- New `examples/`: `doctrine-scoping` (per-role brains that narrow + refound remap), and
  `seam-descent-run` (an org self-driving scoped hand-offs end to end).

Every change ships with regression tests (76 green) and passes the payload-schema drift guard.

## 0.1.0

Initial template: the articulated organization as installable Claude Code features — PreToolUse
guardrails that block, SessionStart doctrine injection, per-department subagents, organ tools
(ledger, guardrails, doctrine, reconcile, resource, attention, learning), and organ slash-commands.
Verified on the real CLI (v2.1.211).
