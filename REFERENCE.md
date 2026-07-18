# Reference — configuration, commands, events, troubleshooting

The lookup companion to [QUICKSTART.md](QUICKSTART.md) (how to get started) and
[ARCHITECTURE.md](ARCHITECTURE.md) (how the system fits together). This is the flat reference: every
environment variable, every command, the blast-radius caps, the ledger event vocabulary, and the
fixes for the problems people actually hit.

---

## 1. Environment variables

Set these in your harness config (`.claude/settings.json` → `"env"`, or the shell before a headless
run). Only `ORG_LEDGER_ROOT` is required to turn the guardrails on; everything else has a safe default.

### Core

| Variable | What it does | Default |
|---|---|---|
| `ORG_LEDGER_ROOT` | Directory holding the org's ledger (`ledger.jsonl` + `HEAD`) — the shared record everything reads/writes. **Required** for the guardrails to gate; without it the hook allows everything and says so on stderr (visible, never silent). | *(unset → guardrails inert)* |
| `ORG_ROLE` | Which department/role this session is. Keys the doctrine injection, the work-in-progress resume, and the ledger events. | *(unset)* |
| `ORG_DOCTRINE_ROOT` | Directory of per-role `<role>.json` doctrine stores; the SessionStart hook injects this role's doctrine at launch. | *(unset → no doctrine injected)* |
| `ORG_CONVENTIONS_ROOT` | Directory of settled conventions, injected alongside doctrine. | *(unset)* |

### Blast-radius caps (per-day budgets)

The cap bounds **irreversible effect per day** (the window rolls daily — see §5). Override any
dimension with `ORG_CAP_<DIMENSION>`. Defaults are sized so a normal day of real work (including a
research/ML day that deletes and replaces artifacts many times) proceeds untouched, while a runaway
(hundreds of irreversible acts in a day) still trips.

| Variable | Dimension — what it meters | Default (per day) |
|---|---|---|
| `ORG_CAP_DESTRUCTIVE_OPS` | `rm`/`dd`/`DROP`/`--force`/`git push`/`reset --hard`/… — irreversible deletes & force-writes (scope-weighted: one `rm -rf`/`DROP` counts as 3) | `50` |
| `ORG_CAP_EXTERNAL_WRITES` | outbound `POST`/`PUT`/`DELETE` (curl/wget with a write verb) | `30` |
| `ORG_CAP_INFRA_CHANGES` | `terraform apply`/`kubectl apply`/`aws`/`gcloud` — changes to real infra | `20` |
| `ORG_CAP_FILE_MUTATIONS` | overwriting an **existing** file (reversible under VCS — high ceiling; new-file creates are never metered) | `500` |
| `ORG_CAP_SHELL_EFFECT` | **deprecated** — the classifier no longer meters "unknown" shell; kept only so an old override is not an error | *(unused)* |

**Not metered at all** (return no charge): reading (`ls`, `cat`, `grep`, `find`, `du`, `stat`, `head`),
build/test tooling (`npm`, `pytest`, `go`, `cargo`, `node`), new-file creation, and any command that
matches none of the destructive/external/infra patterns. "Unknown" is not "dangerous" — only explicit
irreversible patterns draw down a budget.

### Window & tuning

| Variable | What it does | Default |
|---|---|---|
| `ORG_WINDOW_SINCE` | Explicit ISO timestamp for the start of the cap window (overrides the rolling daily default). | *(rolling daily)* |
| `ORG_WINDOW` | Set to `all` to opt into a deliberate **all-time** cap (no reset). Use only if you truly want a lifetime budget — otherwise leave unset for the daily reset. | *(rolling daily)* |
| `ORG_REQUIRE_SEAM` | `1`/`true`/`yes` turns on the spawn gate: an `Agent`/`Task` spawn is blocked unless its prompt carries a seam contract or an `INDEPENDENT:` declaration. Off by default. | *(off)* |
| `ORG_HOOK_FAIL_OPEN` | `1` allows a tool call when the guardrail organ errors, instead of blocking. **Dev only** — the safe default is fail-closed. | *(off / fail-safe)* |
| `ORG_NOW_TS` | Pins the hook's "now" (append ts + window boundary). Mainly for tests; leave unset in production so the real clock is used. | *(real UTC now)* |
| `ORG_TOOLS_DIR` | Override the directory the hooks resolve the organ tools from. Set automatically by the plugin bundle; rarely touched by hand. | *(bundled/repo auto-resolve)* |

---

## 2. Commands (Claude Code slash-commands)

| Command | What it does |
|---|---|
| `/org-found <RFP or brief>` | Draft an org from a brief: a feature inventory, an architecture with seam contracts, a linted `organization.yaml` — then stop and report up for scope approval. Design only; the build is a separate call. |
| `/org-work <role> [wip] [floor]` | The **PM loop**: select from the role's backlog by situated attention, delegate the selected items to subordinates in parallel (one `Task` each, where the split is genuine), record progress and completion. Acts. |
| `/org-discover <role> [aspiration]` | **Problemistic search**: surface the role's aspiration gaps and raise them as `source: self` backlog items. Adds to the backlog; never executes; fail-quiet when there is no gap. |
| `/org-resume [role]` | Show a role's **work in progress** — candidates started but not finished, each with its latest checkpoint (how far / next step / blocker). The manual counterpart to the automatic resume injection. |
| `/org-tick` | Read-only **health tick**: which checks are due / MISSED, machine sensors, ledger-chain integrity. Surfaces, never acts. Fail-quiet is the normal state. |
| `/org-mandate <subjectA,subjectB> <decision>` | Adjudicate a genuine **mandate conflict** against the constitution's human-authored precedence: precedence applies, both integrate, or escalate. |

Scheduling these on a cadence: see [integrations/claude-code/SCHEDULER.md](integrations/claude-code/SCHEDULER.md)
(`/schedule` cron routines for unattended runs, `/loop` for attended ones).

---

## 3. The org's files

An org is these source files (templates in `template/`), validated by `tools/org_lint.py`:

| File | What it declares |
|---|---|
| `organization.yaml` | the chart: purpose, latent layers, roles + contracts, separation-of-duties, info-flow scopes |
| `constitution.yaml` | the charter: decision line, invariants, change tiers, mandate precedence — **no agent edits it** |
| `moves.yaml` | the catalog of legal structural changes, each tiered (delegated / charter / irreversible) |
| `ledger-schema.yaml` | the ledger's event vocabulary + derived views (incl. the backlog and work-in-progress views) |
| `sensors.yaml` | the sensors that trigger reorg moves |
| `role-settings.yaml` | neutral per-role runtime knobs (model tier, tools, budget, stop) — the projection input |
| `ROLE.md` / `SUPERVISOR.md` / `FOUNDER.md` / `PROJECTION.md` | neutral role/supervisor/founder profiles + the projection contract |

Validate: `python3 tools/org_lint.py organization.yaml constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml [role-settings.yaml]` (exit 0 = pass, 1 = violations).

---

## 4. Ledger events you'll touch most

The backlog and progress live in the ledger. The events that drive the metabolism:

| Event | Payload (key fields) | Meaning |
|---|---|---|
| `candidate_submitted` | `maker, candidate_id, contract_ref, source: mandate\|self` | a backlog item enters (top-down mandate or self-raised) |
| `cycle_started` | `role, candidate_id, pack_manifest_id` | a role began working a specific backlog item |
| `progress_recorded` | `role, candidate_id, fraction, phase, done_so_far, next_step, blocked_by, artifacts` | a **checkpoint** — the memory of "how far", so a context wipe doesn't lose it |
| `cycle_completed` | `role, candidate_id, outputs, …` | the item is done and drains from the backlog |
| `exposure_budget_checked` | `dimension, committed_so_far, delta_requested, cap, decision` | one blast-radius cap decision (allow / hold) |

Views (read with `python3 tools/ledger.py view <root> <view>`):
- `open_experiments` — the backlog (submitted, not yet completed).
- `work_in_progress` — started-but-not-completed candidates with their latest checkpoint (the resume source).

---

## 5. Troubleshooting

**"org guardrail HELD this … `committed_so_far … > cap`" — everything is blocked.**
The daily budget for a dimension is spent. First check it is not a stale window: the cap resets daily
by default, so a restart usually clears yesterday's exhaustion. If real work legitimately exceeds the
default in one day, raise that dimension's cap — e.g. `ORG_CAP_DESTRUCTIVE_OPS=100`. Do **not** set
`ORG_WINDOW=all` to escape a block (that removes the daily reset and re-creates the deadlock).

**A benign command (`ls`, `git status`, `find`, an unfamiliar CLI) seems to draw down the budget.**
It shouldn't anymore — only explicit destructive/external/infra patterns are metered; unknown and
read-only shell are not. If you see this, you are on an old plugin version — update it (§ below) and
restart.

**A path like `.../fx-ml-platform/...` was flagged as a destructive `rm`.**
Fixed by word-boundary matching — update the plugin and restart. The classifier tokenizes now, so a
path containing `rm`/`form`/`-f` bytes is not mistaken for the `rm` command.

**Doctrine / work-in-progress isn't injected at session start.**
The SessionStart injection needs `ORG_ROLE` and `ORG_LEDGER_ROOT` (and `ORG_DOCTRINE_ROOT` for
doctrine). Confirm all three are set in your settings.

**Updating the plugin after a fix.**
```
claude plugin update orgforge-plugin@orgforge-plugin --scope <project|user>
```
Then **restart Claude Code** — "Restart to apply changes" means the new hook code is not live until you do.

**A due check reports MISS.**
`tick.py` found no proof-of-run for a check that was due — the scheduler may be down. It is a paged
fact by design (silence must not read as success), not a bug in the org.
