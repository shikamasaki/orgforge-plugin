# Changelog

All notable changes to orgforge-plugin. This project follows a pragmatic semver:
minor = new mechanisms/features, patch = fixes, major = breaking articulation changes.

Entries from 0.12.0 on are in English and follow Keep a Changelog headings; earlier entries
predate that convention and are left as written. Design rationale lives in `docs/`, not here.

## 2.8.1 — re-review when the evidence changed, as the message already promised

2.7.0's refusal told the caller that changing the reviewed head, the cited evidence, or the stated
residual risk would earn another review. Only the first was true: `review_subject_id` digests the
revision (tree, head, integration ref) and carries neither evidence nor risk, so re-submitting with
real DoD output against an unchanged tree was silently skipped.

That is worse than a missing feature — the tool gave instructions that did not work, the same shape
as #186. The case it blocked is ordinary: the fix was already committed, so the tree is unchanged,
and what changed is that the claim is now evidenced by a command that was actually run. The earlier
verdict was reached without that evidence and must not stand in for a review of it.

### Fixed

- **The skip now compares a round fingerprint** — a digest of the cited evidence and the stated
  residual risk — alongside `review_subject_id`. A difference in either dispatches; all three
  identical still skips, which is the case 2.7.0 was built for.
- Normalised for whitespace and ordering, so a reformatted paste does not masquerade as new
  evidence and cost a judge run.
- `verify` accepts `--evidence` and `--risk` to carry this round's values.

An absent fingerprint on either side dispatches: an unknown is never a skip.

Closes #193.

## 2.8.0 — print the way out, not just the rule

A rebase moves `review_subject_id`, so `github_sync provisional` correctly refuses to let the same
lineage restack its verdict — a judge may not void its own. The refusal named that requirement and
stopped there. Everything needed to comply already existed (`identity keygen`, `identity receipt
--event-class correction`, `ledger append --class correction --receipt`), and a test has been
exercising that exact path since before this release. Reaching it from the message did not work:
the field report concluded the correction command was missing, and rediscovering it took five
failed attempts over argument shapes, the trust-store path, and the constitution key.

### Changed

- **The refusal now prints the recovery as three runnable commands** — register the authority's
  key, sign a receipt bound to `correction:superseded:<seq>`, append the correction — plus the
  `enforcement.judges.judgment_corrections.authority_roles` key the ledger requires. The authority
  role is read from the constitution rather than hardcoded, and the message states that the old
  verdict is preserved rather than erased.

The control is unchanged: a judge still cannot void its own verdict, the authority must still be a
declared third party, and the receipt must still bind to the target. What cannot be skipped is now
reachable.

Closes #186.

## 2.7.0 — do not judge the same revision twice

`review_subject_id` is a digest of (issue, role, phase, integration_ref, tree), so an equal id
means a judge would be looking at the revision it already judged. Re-dispatching then spends a
judge run — measured at ~100s on real material — plus, on the maker's side, a CI round, to
re-derive a verdict the ledger already holds. Issue #170 ran 12 CI rounds at a ~5.7 min median,
roughly 68 minutes on a single Issue.

### Changed

- **`org_cycle verify` reports the recorded verdict instead of dispatching**, when the ledger
  already holds one for this exact subject and role. It names what would have to change to
  warrant another review: the reviewed head, the cited evidence, or the stated residual risk.
- **`--force` dispatches anyway**, for a deliberate re-review.

### What is deliberately *not* suppressed

A different revision, the other role, a first-ever review, a voided (corrected) judgment, and an
unreadable ledger all still dispatch. This suppresses **repetition**, never the independent
cross-harness review itself — and an unknown is never treated as a skip.

Closes #182.

## 2.6.0 — a judge is handed the Issue's contract, not the org's memory

A gate review kept expanding past the Issue it was judging: organization-wide doctrine reached the
dispatch and became review criteria, so the bar moved between rounds and findings accumulated that
no MUST in the Issue had asked for. 2.3.1 removed the role charter from the prompt, but doctrine
was still arriving by another route — `handoff.py` builds the seam contract every dispatch carries,
and it attached the role's scoped doctrine unconditionally.

### Changed

- **`handoff.py` gives `gate` and `skeptic` a bar instead of a brain.** Their section now states
  the boundary — acceptance criteria, changed seam, declared DoD, submitted evidence, recorded
  residual risk — and that anything outside it is `out_of_scope` rather than a blocker, unless it
  concretely demonstrates an immediate safety, data-integrity, security, or release-blocking
  failure.
- **Every other role keeps its doctrine.** A maker builds, and prior lessons are what stop it
  rebuilding a known mistake. Only the checking roles are scoped down.

This bounds a judge's **input**, never its judgment (docs/03 §6.5). It still decides the verdict; it
decides against the contract it was handed rather than against everything the org has ever learned.

Closes #181.

## 2.5.1 — collect the judge's verdict from where it actually is

### Fixed

- **A Claude headless judge's verdict was produced and then dropped.**
  `claude -p --output-format json --json-schema ...` returns the answer twice in one envelope:
  `structured_output` (the schema-validated object the flag produced) and `result` (the same
  content rendered for display). The collector read `result` and re-parsed it — throwing away a
  validated object to recover it from a string. That holds only while the model emits bare JSON;
  the moment it wraps the JSON in prose the parse fails, and a review that genuinely ran looks
  like it returned nothing. Observed in the field as the gate "not responding" across two runs
  while the CLI itself answered normally (~6s plain, ~13.5s with a schema).
- **An empty `result` was reported as success.** `env.get("result") or pr.stdout` fell back to the
  whole envelope, so `{"result": ""}` was handed on as if the envelope were the verdict. Found by
  the test written for the fix above; no verdict now fails closed, as it always should have.
- An envelope carrying `is_error` / `api_error_status` is now announced on stderr instead of
  passing a degraded answer off as a clean verdict.

## 2.5.0 — write down what "wrong" looks like, since intent cannot be written down whole

The hardest failure is the one where every MUST is satisfied and the result is still not what was
wanted. No amount of model capability closes it: intent that never reached the specification cannot
be recovered from it, and a more capable model fills the gap more plausibly, not more correctly.

Intent cannot be stated exhaustively — but a **counterexample** can. "Returning an empty array
always" is easy to write down even when the full purpose is not, and unlike the purpose it is
something the gate can *run*.

### Added

- **`SPEC.md` asks for a placebo and a null** — an implementation that satisfies the wording while
  betraying the intent, and an output a real user would reject. `split-check` reports either one
  missing on work that touches the declared domain surface.
- With them recorded, the gate has an executable question — *does this placebo turn the tests red?*
  — instead of inventing a new one each round, which is what made the bar drift between rounds.

### Why this became load-bearing in 2.3.1

2.3.1 replaced the full role charter with a compact review contract. The charter carried the
placebo/null instruction; the compact contract does not, so **no dispatched judge currently receives
it** (`_focused_review_contract` contains neither word). The defense now has to live in the Issue,
where it is a recorded fact rather than something the judge is trusted to remember.

Explanatory prose in a blockquote — including this template's own — is not counted as an instance,
and neither is an unfilled `<placeholder>`.

## 2.4.0 — put the human/AI agreement where a mismatch is visible

Reviewing a diff means hunting for mistakes: a miss passes silently, and the cost grows with the
volume of generated code — exactly the wrong shape when an agent writes ten times more of it.
Reviewing a domain model, a use-case scenario, or an authorization rule is a different act: two
parties describe the same thing, and a mismatch is *visible*. The reading cost tracks the domain,
not the output. This release makes that surface a precondition for the work rather than a habit.

It also fixes an ordering problem. `cycle_completed` asks for a domain model *after* the work, so
the implementation decides the model. Requiring it at decomposition puts the model first, which is
what "SSoT is the code and the domain model" already implied.

### Added

- **`SPEC.md` gains three sections** — domain model (vocabulary and invariants), use-case scenarios
  (who does what, what results), and authorization (who is protected from whom). Authorization sits
  here because it is *domain*, not library-level security: "who may see whose expense" is not
  decidable by a dependency. In the field, 12 MUSTs contained 2 authorization rules and one of those
  covered a nickname — amount, payer, direction of debt, and group ownership were left unguarded.
- **`split-check` reports those sections missing, and `ready` withholds the Issue** — but only for
  work touching the domain surface the org itself declares in `constitution.yaml`
  (`enforcement.domain_surface.paths`). A CI fix is not asked for a domain model.
  `ORG_READY_SKIP_DOMAIN=1` stands the withholding down during migration.
- **A heading with nothing under it, or an unfilled `<placeholder>`, counts as missing.** Pasting
  the template is the dangerous failure: it looks like agreement was reached and records none.

### Notes

The plugin does not guess where your domain lives. Whether it is `src/domain/`, `app/models/`, or
`supabase/migrations/` is a project's choice — one live org already mixed four such prefixes — so
the check runs against declared paths only, and does nothing until an org declares them. Content is
never judged here: whether the model is *right* stays with the human and the gate (docs/03 §6.5).

## 2.3.0 — give the gate a target so review rallies converge

A review rally that ran 12 rounds on a single issue (tatekae #170) was traced to its cause: the
acceptance criteria were prose, so the gate designed its own verification on every round and the
bar moved each time. Nothing converges against a moving bar. This release closes the hole where
the shape check could be skipped, and cuts the wasted judge time that made each round expensive.

### Fixed

- **An empty headless judge response is now diagnosable** (issue #166). `claude -p` was observed
  exiting 0 with no stdout and no stderr, leaving no way to tell a crashed CLI from expired auth
  from a silently terminated tool-use turn. The empty result is still fail-closed — no verdict, no
  admission — but it now reports exit status, stream sizes, the flags used, and the one-line probe
  to run next. Flags only: rendering the argv by position leaked the material itself on the
  `claude -p <material>` route, which is why the test asserts the material never appears.
- **The test suite runs on 8 workers instead of serially** — 638 s → 61 s for the same 1079 tests.
  It is bound by process startup (every organ is a real subprocess), not CPU, so `-n auto` in CI is
  nearly free. Tests must stay independent for this to hold; one that leans on another's leftover
  state now fails instead of passing by accident.
- **`split-check` no longer passes prose acceptance.** The EARS check tested the *whole issue body*
  for `WHEN `/`WHILE `/`IF `/`WHERE `, so acceptance written entirely as prose slipped through on an
  unrelated "IF ANY" or a SQL `WHERE` in a fenced block (reproduced). It now checks the acceptance
  bullets themselves, reusing `req_lint`'s EARS patterns so the definition lives in one place, and
  reports which lines failed. Seam-contract metadata (`owns:`, `depends_on:`, …) is no longer
  miscounted as a requirement.
- **The PreToolUse hook no longer sleeps on a permanent failure.** `_run_organ` retried any exit
  code outside `{0, 10}` with exponential backoff, including exit 2 — the organs' deliberate
  "bad input" verdict (unreadable constitution, missing root). Re-running cannot change that, so
  every tool call paid 1.5 s of `time.sleep`. Measured on a benign `Read` against an org with no
  `constitution.yaml`: **1.90 s → 0.24 s per call**. Genuine crashes and timeouts still retry.

### Added

- **`ready` withholds issues whose acceptance is not in EARS.** `split-check` ran only when a human
  chose to run it; an issue that skipped it reached a maker with no checkable bar. The backlog now
  declines to hand those out, listing them under `withheld_non_ears`. Set `ORG_READY_SKIP_EARS=1`
  while migrating an existing backlog.
- **`split-check` requires a runnable DoD command (on by default).** Without a command the gate is
  told to re-derive but given nothing to run, so it designs the check itself — the main cost in a
  ~100 s judgment and the reason the bar drifts between rounds. `ORG_REQUIRE_DOD=0` stands it down.
- **`org_cycle verify` warns before dispatching a judge that can only park.** A read-only judge
  cannot re-derive a MUST that requires execution (repeated runs, a real database, latency), so it
  returns `park` after minutes of work. `tools/orgcycle/rederivability.py` detects those statically
  and says so before the judge starts; `--strict-rederivability` stops instead of warning. Advisory
  by design — it reports what is measurable, never a verdict.
- **`github_sync review-response`** records a maker's answer to a specific review finding on the
  Issue, keyed by finding id. `agents/gate.md` already forbids re-blocking on a finding unless the
  head, evidence, or risk changed — but that is unenforceable when nobody can address the previous
  finding by name. Written to the Issue rather than a local status file, so the *other* lineage's
  judge can read it (carried over from PR #165, which is otherwise superseded by #167).
- **MCP transport for cross-harness judges** (`tools/orgcycle/mcp_judge.py`). `codex mcp-server` and
  `claude mcp serve` are the official interfaces; passing the material as a JSON value removes the
  argv-misparse failure where material beginning with `-` killed `codex exec` outright. One
  judgment per session, deliberately: continuing a session would let the skeptic read the gate's
  reasoning, and that lineage decorrelation is the point (docs/03 §3). Not faster — measured 4.1 s
  vs 4.7 s — so it is opt-in via `judges.harness.<h>.<role>.transport: mcp`.

## 2.1.1 — restore the reviewed Graph adapter

### Fixed

- 2.1.0 shipped the pre-review in-place graph adapter: the old `assurance-graph-v0alpha1`
  tag pin, an `assuranceGraph` block folded into `v0alpha2.lock.json`, and no
  `--no-replace-objects` hardening. This release restores the independently reviewed
  separate adapter (`tools/assurance_graph_export.py`) pinned to `assurance-graph-v0alpha1.1`
  with its own lock file, the git-replace (`--no-replace-objects`) hardening on both the
  graph and delegation-resilience adapters, and the bound `verifierManifestPath`.

## 2.0.32 — atomic hold guidance

### Fixed

- State explicitly that a Bash/exec call held by PreToolUse never started: its preparation,
  mutation, and verification segments are all unexecuted, not partially successful.
- Give the governed GitHub and integration routes a three-call preparation → mutation → verification
  example, while retaining fail-closed handling for compound mutations.
- Keep non-shell tool messages atomic to their own tool call, rather than implying shell-segment
  semantics for Write/Edit-style inputs.

## 2.0.31 — governed Issue-body repair

### Fixed

- Reject empty and placeholder-only task or objective bodies before any GitHub write, and verify an
  existing matching Issue's body before treating `create` as an idempotent replay.
- Refuse to silently discard a different non-empty body: report only old/new SHA-256 digests and
  direct the operator to an explicit `repair-body` command.
- Add a governed body-repair path that records the Issue, authenticated actor, reason, and old/new
  body digests in an audit comment, rolling the edit back if that evidence cannot be written.

## 2.0.30 — idempotent skeptic joints

### Fixed

- Apply joint-admission idempotency to the event being derived instead of hard-coding only
  `admission_decided`, preventing repeated `refutation_attempted` derivations from duplicating the
  same two-lineage skeptic decision.
- Preserve new joints for a different review subject and permit re-derivation after the prior joint
  has been explicitly voided.

## 2.0.29 — evidence-based env examples

### Fixed

- Make the reproducibility gate read env-example contents and require at least one dotenv-style
  `KEY=` declaration instead of accepting an empty, comment-only, or arbitrary one-byte file.
- Limit the successful claim to the declaration count actually observed; do not imply that all
  semantically required configuration was inferred, and never report variable values.

## 2.0.28 — explicit integration target

### Fixed

- Stop guessing a strict review's integration target from whichever conventional branch name is
  present; repositories that retain both `develop` and `main` can otherwise validate the obsolete
  branch as current.
- Require strict organizations to declare `enforcement.judges.integration_ref`, while preserving an
  explicit per-review `verify --base` override and binding the selected ref into the subject.
- Make doctor reject missing, malformed, or locally unresolvable strict integration refs in Git
  repositories so the ambiguity is detected before a judgment is dispatched.

## 2.0.27 — integration-base freshness

### Fixed

- Bind each review subject to an explicit integration ref, its observed head, merge-base relation,
  reviewed tree, and requirements digest rather than treating agreement on an old base as current.
- Re-resolve that target both when a provisional judgment is recorded and immediately before a
  joint admission is derived; moved, stale, diverged, deleted, and unresolvable targets fail closed
  without fetching or rebasing as a side effect.
- Preserve the observable subject descriptor in the ledger so a stale/tainted decision can be
  reconstructed, and require re-review after a rebase produces a new subject.
- Add an explicit `require_current_integration_head` migration choice to doctor; new organizations
  select strict current-head matching while existing organizations must choose strict or documented
  compatibility mode instead of silently inheriting behavior.

## 2.0.26 — effective correction projection

### Fixed

- Project current ledger truth through one shared `voided_seqs` resolver, using the writer-derived
  correction effect for current events and preserving legacy kind semantics for older ledgers.
- Apply that resolver consistently to status, joint-admission derivation, integration, GitHub
  synchronization, drift, and exposure accounting without treating backfills as voids.
- Honor corrections of corrections, so voiding an earlier correction restores its target instead
  of leaving an irreversible phantom decision.
- Distinguish a provisional cross-harness skeptic refutation from a missing skeptic record and
  surface the pending joint/rework materialization as AMBER rather than a false RED.

## 2.0.25 — scheduler check receipts

### Fixed

- Record a strict, idempotent `scheduled_check_completed` receipt after each unattended machine
  check instead of treating absent domain events as proof that the check never ran.
- Run covered checks before missed-tick planning, require exact receipt readback, and count unique
  cadence windows so retries cannot hide a skipped execution.
- Align cadence windows with the scheduler's first observed tick rather than Unix wall-clock
  boundaries, matching relative cron/launchd execution.
- Report unattended versus attended-only schedule coverage and keep unsupported, context-dependent
  checks outside the headless scheduler's claims instead of silently pretending to execute them.

## 2.0.24 — installed exercise session binding

### Fixed

- Make the deterministic reviewer-outage exercise inherit the current installed-organ session,
  so the documented pre-scheduler readiness check can complete without weakening stale-session
  rejection; standalone and CI runs retain their deterministic fixture identity.

## 2.0.23 — receipt-bound judgment correction authority

### Fixed

- Prevent a gate or skeptic from voiding its own or another judge's verdict to manufacture room for
  a replacement admission; provisional conflicts now hand the decision back to a declared
  third-party correction authority.
- Require a verified authority receipt bound to the org, ledger, target sequence numbers, correction
  kind, role, and reason digest, so changing only `--actor` cannot impersonate the authority.
- Preserve append-only factual corrections and judgment backfills while recording the correction's
  effect, target classes and Issues, authority principal, and assurance in the ledger and cycle view.
- Lint and enforce that correction authorities are declared, active, and outside judging/review
  duties, with synchronized Claude Code, Codex, and neutral projections.

## 2.0.22 — receipt-backed native host scheduling

### Fixed

- Replace unattended `claude -p '/org-tick'` with a deterministic, zero-LLM machine-tick entrypoint
  that requires a matching `tick_planned` receipt and records atomic run state.
- Select native per-user launchd on macOS and cron elsewhere, with bounded subprocesses, exact
  definition readback, a real smoke tick, safe replacement/removal, and status freshness checks.
- Fail closed for persistent `work` and `discover` while Claude Code can return exit 0 without
  expanding their slash commands; attended `/loop` remains their supported driver.
- Preflight the Python/PyYAML interpreter so dependency drift cannot masquerade as ledger corruption.

## 2.0.21 — staged persistent scheduling

### Fixed

- Let the Claude Code cron installer select `tick`, `work`, and `discover` independently with
  `--cycles`, so the documented read-only-first rollout works for unattended organizations instead
  of silently enabling the acting PM loop.
- Make reinstallation remove cycles that are no longer selected, preserve unrelated crontab entries,
  validate exactly representable wall-clock intervals, and quote cron command inputs safely.
- Document the `tick,discover` staging command and keep the three-cycle default backward compatible.

## 2.0.20 — ledger-backed graceful degradation and recovery

### Added

- Add one operational state machine for `NORMAL | DEGRADED | HALTED | RECOVERING`, with
  dependency circuits, retry budgets, cooldown/half-open probes, explicit actor/reason/evidence/
  confidence, repeated-failure escalation, and compatibility with the existing HALT latch.
- Enforce adaptive-envelope actions and a no-ship rule at the PreToolUse boundary while degraded;
  recovering and derived HALT permit observation and the ledger-validated recovery path only.
- Propagate taint from the initial outage and every artifact generated or referenced by a degraded
  deviation, then require the declared revalidation scope before closing the circuit and returning
  to NORMAL. Stale sessions and unauthorized recovery actors fail closed.
- Project identical state semantics through doctor, the status board, the ledger view, OpenTelemetry
  attributes, and a GitHub Checks payload without producing a synthetic resilience score.
- Turn the deterministic reviewer-outage exercise GREEN through the production sequence
  `NORMAL → DEGRADED → RECOVERING → NORMAL`, including independent recovery preflight, failover,
  taint revalidation, envelope reversion, and circuit closure.

## 2.0.19 — deterministic resilience exercise

### Added

- Add a sub-three-minute reviewer-outage fixture using a temporary workspace, injected dependency,
  local tracker artifact, and the production judge-preflight, adaptive-envelope, and ledger paths.
- Require a fault receipt proving the injected marker reached the decision boundary, reject no-op
  faults, and assert allowed/forbidden actions, critical functions, missing evidence, taint, and the
  declared acceptable outcome without using a resilience score.
- Preserve the missing `DEGRADED` operational-state transition as one intentional Phase-A RED gap
  that Issue #45 must turn GREEN through the same fixture.

## 2.0.18 — bounded adaptation contract

### Added

- Define versioned critical functions, acceptable outcomes, constitutional invariants, adaptive
  practices, and expiring adaptive envelopes without treating the four resilience potentials as
  separate product modules or reducing resilience to a score.
- Add ledger-enforced activation, authorization, deviation, expiry, revert, outcome,
  microexperiment, and human-attested permanent-adoption flows with declared observation sources,
  confidence, scope, blast radius, retries, taint, and recovery revalidation.
- Ship deterministic reviewer/provider outage and safe-stop contracts in both harnesses, expose
  proposed/active/expired/reverted/adopted state in doctor/status, and distinguish Work-as-Imagined,
  Work-as-Recorded, Work-as-Reported, and inferred Work-as-Done.

## 2.0.17 — portable persistent goals

### Added

- Add a ledger-backed `org-goal` lifecycle shared by Claude Code and Codex: start, status,
  progress, pause, compare-and-swap resume, repeated-blocker escalation, and evidence-audited
  completion survive process and host restarts.
- Bind the host session identifier at SessionStart, reject concurrent takeover and unfinished-goal
  overwrite inside the ledger lock, and re-inject the objective and next action on restart.
- Project the same state through a Claude Code command and a Codex skill that explicitly reconciles
  native Goal state without treating it as the portable source of truth or claiming execution while
  the host is closed.
- Add `org-goal doctor` capability reporting for both adapters, including the real SessionStart,
  session-scoped loop, native-skill, installed-binding, and no-background-execution boundaries.

## 2.0.16 — stable installed-organ binding

### Added

- Bind each organization at SessionStart to the Claude Code or Codex organ that is actually
  installed, and expose a version-stable organization-side launcher in session and judge context.
- Rebind that launcher atomically after a plugin update/restart without embedding cache paths in
  judge instructions.
- Refuse ledger mutations from an unrelated development checkout with the expected/observed tools
  roots and the exact stable invocation needed to recover.

## 2.0.15 — bounded judge environment preflights

### Added

- Let an organization declare argv-based environment probes with explicit timeouts and
  issue/phase/role selectors under `enforcement.judges.preflights`.
- Stop verification before judge dispatch on a failed or timed-out matching probe, and preserve
  the measured command, exit code, elapsed time, stdout, and stderr as review evidence.
- Validate the preflight contract during organization linting and bundle the identical runner and
  constitution contract in Claude Code and Codex.

## 2.0.14 — host-independent monitor liveness

### Added

- Record an atomic heartbeat after every redline probe with PID, plugin version, role, logical
  instance, cadence, poll count, and last signal state.
- Add `status`, `rearm-check`, and token-bound cooperative `stop` commands that distinguish live,
  stale, dead, duplicate, orphaned, and old-version monitor processes without host task metadata.
- Bundle the same monitor contract in Claude Code and Codex, and require a successful rearm check
  before the Claude Monitor guidance creates a replacement.

## 2.0.13 — recover interrupted rebases safely

### Fixed

- Allow `git rebase --abort`, `--continue`, and `--skip` to recover an interrupted checkout
  without misclassifying the recovery as a new protected-branch integration.
- Bind recovery to one statically resolved checkout across direct cwd, `cd PATH && git`, `git -C`,
  linked worktrees, and safe Git global options.
- Keep ordinary rebases guarded and fail closed for dynamic, compound, or repository-redirecting
  commands whose target cannot be resolved before execution.

## 2.0.12 — authoritative worktree governance

### Fixed

- Resolve organization governance from Git's primary worktree even when Claude Code or Codex
  creates a linked worktree outside the repository directory.
- Keep the reviewed commit and file tree pinned to the caller's actual worktree while surfacing
  stale embedded governance files as an AMBER status condition.
- Emit the schema-declared `blocked_by` field in `progress_recorded` receipts and keep the neutral,
  Claude Code, and Codex projections byte-identical.

## 2.0.11 — coherent rework transitions

### Fixed

- Reopen a closed GitHub Issue when a governed lifecycle stage moves it back to ready,
  in-progress, blocked, or needs-human, while leaving already-open transitions idempotent.
- Make `org_cycle rework` restore the Issue to OPEN / ready before recording
  `rework_requested`, so a failed GitHub transition cannot advance the ledger alone.
- Keep `done` close idempotent and cover open, closed, replay, and reopen-failure paths in both
  harness projections.

## 2.0.10 — measured mutation evidence

### Fixed

- Require mutation-based judge evidence to prove the mutation's applied postcondition, preserve the
  real command/output, and restore the original state before interpreting a test result.
- Reject structured skeptic reports that claim unapplied or unmeasured mutations while preserving
  valid static reviews with an empty mutation list.
- Bundle the gate and skeptic structured-output schemas in both Claude Code and Codex projections,
  and verify byte parity plus runtime path resolution in CI.

## 2.0.9 — reliable org schema migration

### Fixed

- Compare existing event-class fields from parsed YAML rather than comma-splitting inline maps, so
  comments cannot hide every field that follows them from `ledger schema --fix`.
- Resolve aligned inline-map declarations regardless of spacing and add every missing field without
  replacing organization-owned schema rules.
- Declare the `risk_accepted` field emitted by provisional cross-harness verdicts and verify that an
  old Tatekae schema can be additively migrated until the real `survives` command succeeds.

## 2.0.8 — worktree-aware integration guard

### Fixed

- Resolve a statically declared leading `cd <worktree> && git …` or `git -C <worktree> …` before
  deciding which checked-out branch an integration command would mutate.
- Allow feature-worktree updates such as `git rebase main` while continuing to hold commands that
  target a protected checkout; ambiguous, dynamic, missing, and multiple targets fail closed.

## 2.0.7 — usable one-shot integration bypass

### Fixed

- Honor `ORG_ALLOW_MANUAL_MERGE=1` when it is scoped to the sole direct
  `git merge`/`rebase`/`cherry-pick` command in the same Bash call, where PreToolUse can verify and
  record the declaration before Bash starts.
- Keep compound commands, pipelines, substitutions, multiple integrations, declarations attached
  to another command, and unrecordable bypasses fail-closed.

## 2.0.6 — real integration branch resolution

### Fixed

- Resolve `integrate` targets against real local and origin-tracking refs rather than treating the
  current Issue-title slug as durable branch identity.
- Use a sole matching Issue branch when the derived name changed, and stop with actionable missing
  or ambiguity diagnostics instead of reporting a nonexistent ref as zero files and commits.
- Existence-check explicit `--branch` overrides and fail if a ref disappears between resolution and
  preview.
- Stop on local/tracking divergence, merge the immutable resolved commit rather than a movable ref,
  and record that subject SHA in integration evidence.

## 2.0.5 — executable shell data boundaries

### Fixed

- Stop hook policies from treating the body of a standalone, quoted `cat` heredoc as executable
  shell source, so observation files can quote held GitHub, integration, and destructive commands.
- Keep interpreter input, shell pipelines/process substitutions, unquoted expanding heredocs, and
  ambiguous multi-command forms fail-closed.

## 2.0.4 — quiet RED monitoring

### Fixed

- Add a state-aware Claude Code Monitor adapter that emits the first or changed RED signal, suppresses
  identical polls, and resets after GREEN so a later recurrence still notifies.
- Keep `status.py redline` as a stateless probe and surface probe failures as deduplicated RED alerts.
  This adapter is Claude Code-specific; Codex has no corresponding Monitor recipe or runtime.

## 2.0.3 — usable one-shot GitHub bypass

### Fixed

- Honor `ORG_ALLOW_MANUAL_GH=1` when it is scoped to the actual `gh issue` command in the same
  Claude Code Bash call, where PreToolUse can verify and record it before Bash starts.
- Preserve the guardrail for mentions, assignments to other commands, pipeline-local exports,
  explicit unsets, and command-local overrides that disable the bypass.

## 2.0.2 — reliable missed-tick monitoring

### Fixed

- Anchor scheduled-check accounting to the first persisted `tick_planned` receipt instead of Unix
  epoch zero, eliminating decades of false missed-check alerts in newly monitored organizations.
- Persist planner receipts through a host adapter on every Claude Code tick path, including writerd
  deployments, while keeping retries idempotent and append failures visible.
- Preserve real missed-check accounting across malformed receipts, fail visibly on incompatible
  clock domains, and recover after the host records a valid receipt in the active clock domain.

## 2.0.0 — adaptive reviewer routing

### Breaking changes

- `judges.harness` now declares both `claude` and `codex` secondary configurations. The previous
  role-only shape is removed.

### Added

- `judges.lineage: adaptive` detects whether the running agent is Claude Code or Codex and selects
  the opposite product as the secondary reviewer.
- Users with one subscription retain the maker/gate/skeptic workflow through an explicitly
  lower-assurance pseudo `same-harness` fallback. The fallback is never recorded as cross-harness.
- The admission-recording path uses the same adaptive resolution as judge launch, preventing a
  fallback review from being upgraded to a cross-harness claim later in the workflow.

## 1.0.0 — governance for existing coding-agent teams

### Breaking changes

- **orgforge is now explicitly a governance layer, not a replacement agent runtime or an autonomous
  company prerequisite.** Existing Claude Code and Codex workflows remain the execution surface;
  orgforge contributes ownership, workflow gates, independent checks, evidence, and bounded
  organization evolution.
- **The org-wide Runtime Tier A/B mode is removed.** `run_department.py --tier ...` is rejected and
  existing `defaults.tier: A|B` declarations must be migrated to explicit role capabilities.
- **Trusted developer mode is the shipped default.** Claude Code bypasses permission prompts and
  Codex runs without approval prompts or sandboxing. Use it only in a trusted development checkout
  without production credentials.
- **Asset protection belongs to the host platform.** Deployments, funds, publication, production
  credentials, and regulated assets require host-side custody and approval; role policy and local
  hooks are not a hostile-process containment boundary.

### Added

- One-command adoption for existing repositories in Claude Code and Codex, without prior founding,
  sudo, daemons, branches, Issues, keys, or network access.
- Additive migration for already-operated orgforge repositories. Existing ledgers are preserved;
  schema skew and obsolete runtime modes prevent `doctor` from reporting false readiness.
- Standalone English and Japanese product, architecture, assurance, operations, and adoption guides.
- Repository-local trusted developer defaults and regression tests for both harness projections.

### Fixed

- Resolved the founding-rehearsal Kelvin-sign defect instead of carrying it as a permanent expected
  failure. The adversarial suite now imports the repository artifact rather than an absolute `/tmp`
  copy, and the complete test suite has no `xfail` allowance.

### Assurance terminology

- **The supported assurance model is explicit.** It addresses drift, hallucination, sycophancy,
  skipped verification, and honest operational error on an existing host harness.
- **Local signed receipts are `attested`, not `authenticated`.** An asymmetric signature binds an
  account to a registered key, but a key readable by the same local UID is not an adversarial
  identity boundary.
- **`cross-harness` means decorrelated review.** It buys a second model lineage with different blind
  spots, not a cryptographically independent principal.
- **Separate-UID writer isolation is not adopted as supported core.** Experimental code may document
  failure modes, but it is not a release prerequisite and does not establish judge-key custody.
- Historical entries below retain the terminology used by those releases. The current definitions
  in the language-specific documentation govern new claims.

## 0.39.5 — three bundles, no new features

Scoped to the three bundles the audit asked for. No new capability was added.

### A. Judgment boundary
- **A receipt is now bound to the whole judgment**: org, ledger, issue, `event_class`, subject,
  phase, verdict and both digests (`protocol_version` 3). `org_id`/`ledger_id` are taken **from the
  write target**, not from the payload — a value the caller writes cannot be checked against itself.
  Eight reuse attempts are refused: other issue, other class, other subject, other verdict, other
  lineage, other org, other ledger, other reasoning.
- **`ledger.py derive-admission`** builds the joint admission from two recorded provisional verdicts.
  A joint has no judge receipt — agreement is a function of fact, not a judgment — so writing it
  through generic append hit "no receipt" and **deadlocked: two lineages could agree and no admission
  could be recorded**. The derived event is `system:writer` / `system:joint(...)`, never anyone's
  judgment, and `reviewer_independence` is computed by the writer from what is in the ledger.
  It refuses disagreement, mismatched subjects, and (with `--require-attested`) `claimed` verdicts.

### B. Runtime trust boundary
- **`ORG_WRITER_TRUST_SELF` is gone from the hook.** The guardrail was relaxing its own trust so it
  could connect to a caller-owned anchor. Relaxing is now the operator's explicit choice. Measured: a
  world-writable socket parent makes the hook deny.
- **`writerd --manifest`** pins orgs, schema, policy, trust store and allowed UIDs from a root-owned
  file; when present it overrides `--org`/`--schema`, and the daemon refuses to start if it cannot be
  read or is world-writable.
- **All control writes go through RPC.** `ghsync`'s remaining direct `ledger.py append` calls would
  have returned exit 4 under `ORG_WRITER_SOCKET`.
- **RPC reservations are checked the same way as direct ones** — `exit 0` *and* `decision == allow`.
  The hook was only pattern-matching the direct form, so the RPC path was judged on its exit code
  alone.

### C. Stage B lifecycle
- One namespace rule shared by installer and verifier (`sha256(org root)[:12]`), covering the
  authoritative path, socket, launchd label, config and backup.
- **`--uninstall` runs in order**: stop the daemon → copy authoritative contents back → replace
  symlinks with real directories → restore ownership. Stopping first matters (otherwise the writer
  writes while you copy); restoring ownership last matters (otherwise the writer cannot write).
- **Shared code and the service UID survive while another org remains.** Uninstall requires an org
  and refuses without one. Measured: two orgs get distinct namespaces, and uninstalling one only
  touches its own paths.

### Status
`sudo` and live-org application remain NO-GO pending re-audit. `workload_isolation` is
`process_mediated`; H1's `separate_uid` is unresolved.

## 0.39.4 — an environment variable reopened everything the previous release closed

Fourth audit, NO-GO on all four lenses again. 0.39.3 refused forged identity in the payload — and
then accepted it if the caller also set `ORG_IDENTITY_VERIFIED=1`. **The check I added was gated on a
flag the caller controls**, and the test I wrote set that flag without any receipt.

### Fixed — P0
- **`ORG_IDENTITY_VERIFIED` is gone.** `ledger.py append` now takes `--receipt` and **verifies it
  itself**, generating the identity fields. The caller can hand over a receipt; it cannot assert that
  one was checked. Without a receipt, the fields are still written — as `claimed` — so "checked and
  found self-declared" stays distinguishable from "never looked".
- **Policy can no longer be switched off by the caller.** Measured: `ORG_REQUIRE_ATTESTED_IDENTITY=0`
  turned enforcement off, and so did **deleting `constitution.yaml`**. Now a root-owned
  `/usr/local/etc/orgforge/policy.yaml` is final when present; the environment variable additionally
  requires `ORG_ALLOW_POLICY_ENV=1` so it can never take effect quietly; and a **sticky marker** means
  an org that once enabled enforcement refuses to run if the declaration later disappears —
  **removing a declaration is not disabling it**.
- **The hook and `ghsync` now speak to the daemon.** They called `ledger.py` directly, so under
  `ORG_WRITER_SOCKET` every cap reservation and every judgment returned exit 4 — the guardrail would
  have stopped ordinary operation entirely. Measured after the fix: the hook runs and the reservation
  lands.
- **The hook reads halt state through the writer.** Measured: re-pointing the org's ledger symlink at
  an empty directory took `halt-status` from exit 10 to exit 0 while the authoritative ledger was
  still halted — the hook lost the stop. The daemon reads the **real path** fixed at startup;
  re-pointing the symlink no longer hides anything.

### Fixed — the rest
- `--allow-uid` is wired into the plist (it existed but was never passed, so it did nothing in a real
  deployment). The caller UID defaults to `SUDO_UID`, not root.
- A corrupt nonce file no longer restarts as empty — it refuses. Being unable to detect a replay is
  the same as having no nonce.
- The client refuses a caller-owned anchor unless `ORG_WRITER_TRUST_SELF=1` is explicit, since anyone
  who can write the anchor can substitute the socket. Stage A sets it deliberately, and says it is
  not a boundary.
- `--dry-run` no longer executes backticks inside an unquoted heredoc.
- **Per-org namespacing**: authoritative path, socket, launchd label, config and backup are all keyed
  by the org. `--uninstall` now needs to know which org, restores the symlinks to real directories,
  and copies the authoritative contents back.

### Status
`sudo` and live-org application remain NO-GO. `workload_isolation` is `process_mediated`; H1's
`separate_uid` is unresolved.

## 0.39.3 — the enforcement I added could be bypassed by writing two strings

Third audit, again NO-GO on all four lenses. The worst finding is about my own work: **the control
added in 0.39.2 was defeated by putting `identity_assurance: attested` and `decision_by` in the
payload — and the test I wrote fixed that forgery in place as the happy path.** A check whose input
the caller can write is not a check.

### Fixed
- **Identity fields cannot come from the payload.** `identity_assurance`, `decision_by`,
  `recorder_assurance`, `signer_id` and `key_id` are refused in any caller-supplied payload; only the
  path that verified a receipt may write them. Judgment classes are refused from generic append
  entirely when enforcement is on.
- **Unreadable configuration no longer silences enforcement.** Measured: a corrupted
  `constitution.yaml` took the check from exit 3 to exit 0. Reading it is now three-valued —
  true, false, or **cannot tell** — and "cannot tell" fails closed. Broken YAML, a non-map
  `enforcement`, a non-map `judges` and a non-boolean flag are each refused.
- **`judge_workload` is now signed** (`protocol_version` 2). It was outside the signature while being
  used to assess independence, so adding `separate_host` after signing still verified.
- **Authoritative data moved out of the org tree.** `.orgforge` and the org root are caller-owned, so
  a writer-owned ledger or a root-owned schema could be replaced *by path*. They now live under a
  root-owned directory with symlinks from the org, and the daemon is given the **real paths**, so
  re-pointing a symlink does not move where writes land.
- **The installer's leaf and the client's expectation now agree.** The installer made the leaf
  writer-owned while the client accepted only "root or self" — leaving **zero legitimate write
  paths** even with the daemon up. The client now checks *who could substitute the socket* rather
  than who owns it.
- **The verifier used a different socket path** than the installer, and expected the leaf to be
  root-owned (it must be writer-owned, or the daemon cannot bind). Both now match, and it also checks
  that the org's entries are symlinks into the authoritative tree.
- **Peer UID authorization** (`--allow-uid`): the socket is `0666`, so connecting is open to all —
  connecting and being allowed to write are different things.
- **Nonces persist across a restart.** Measured: they lived in process memory, so stopping and
  starting the daemon let the same request through. If the nonce cannot be persisted, the request is
  refused — being unable to detect a replay is the same as having no nonce.

### PyYAML guidance
A root-owned dedicated venv is now the first option; `--break-system-packages` was dropped entirely.

### Status
`sudo` and live-org application remain NO-GO pending re-audit. `workload_isolation` is
`process_mediated`; H1's `separate_uid` is unresolved.

## 0.39.2 — the second audit: the installer still could not run, and actor spoofing was open

Re-audit (four `claude -p` lenses, all NO-GO again) found nine more. Nothing was run against the live
org and no `sudo` was executed.

### Fixed — the P0 that undermined H1
**`--actor` alone bypassed separation of duties.** Measured: the maker's own self-admission is
refused, but the *same process* re-running with `--actor gate-alias` succeeded and the chain verified
clean. If the name can be changed at will, comparing names proves nothing.

Control events (`admission_decided`, `refutation_attempted`) can now require a receipt-derived
identity — `enforcement.judges.require_attested_identity`. **It defaults to false**, because turning
it on stops every org that has not yet distributed keys; that is a migration decision, not a safe
default. With it on, a self-declared actor is refused and a receipt-derived one passes.

### Fixed — the installer produced a state that still could not run
- **A root-owned `0755` parent cannot be bound by a different-UID daemon.** `bind()` needs write
  permission on the parent, so `0755` fails to start and `1770` is refused by `writerd` — neither
  works. Split into **anchor** (root-owned `0755`, so a caller cannot swap the leaf) and **leaf**
  (writer-owned `0755`, so the daemon can create its socket). `writerd` now checks both.
  launchd socket activation would be stronger still; anchor/leaf is chosen for portability.
- **The daemon's schema was not pinned**, so `ledger.py` fell back to the plugin template depending
  on cwd — validating against the template's rules rather than the org's. The plist now passes
  `--schema` from the root-owned config.

### Fixed — two labels that were still not measured
- **`measured_isolation()` never compared the caller's UID.** Measured: writer UID = caller UID = 502
  still reported `separate_uid`. It is now evaluated **per request** against the peer UID — at startup
  there is no caller to compare against.
- **The writer's isolation was being written into the judge's `workload_isolation`**, so two distinct
  signers were promoted to `distinct_workload`. **A shared writer UID says nothing about whether two
  judges are isolated from each other.** They are now separate fields: `writer_isolation` for the
  writer, and `workload_isolation` only from what the judge itself attests.

### Fixed — the verifier
`--no-write` still produced one real append (the replay check needs a successful first call — that
check is now skipped instead). RPC and `writerd check` failures printed `✗` without incrementing
`FAIL`, so a run could report failures and still exit 0.

### Fixed — the installer's rollback
Re-running overwrote `original-owner` with the *writer* (since ownership had already changed), so
`--uninstall` would have "restored" the ledger to the service account. It is now written once, and
re-running with no record while ownership is already the service user is a hard stop with the manual
fix printed.

### Status
`sudo` remains NO-GO pending re-audit. `workload_isolation` stays `process_mediated`; H1's
`separate_uid` is unresolved. PyYAML should go into a root-owned venv rather than the system Python.

## 0.39.1 — the stage-B installer produced a state that could not run

An independent audit (four `claude -p` lenses, all NO-GO) reviewed the stage-B scripts before any
`sudo` was run. **The installer's own output would have prevented the daemon from starting**, and the
verifier would have damaged a live org. Nothing was executed against the real org.

### Fixed — the installer built a broken state
- **`1770` on the socket parent is exactly what `writerd` refuses.** Group-write means anyone in that
  group can substitute the socket, so the daemon would have exited before binding. It is now `0755`:
  callers need **traverse (x)**, not write. The daemon's check now distinguishes other-write (always
  refused) from group-write (refused only under `--require-root-owned`), so stage A still works.
- **A `0600` socket owned by the writer is unreachable from a caller.** Connecting and writing are
  different things — the socket is now `0666`, and what protects the ledger is that only the writer
  process writes it, plus the RPC checks.
- **`700` on the ledger breaks the caller's `verify`, board and projections.** The control is "cannot
  write", not "cannot see" — a ledger nobody can audit is not an audit ledger. Now `750` with
  group-read and `640` files.
- **PyYAML was checked with the operator's `python3`, not the daemon's.** Measured on this machine:
  PyYAML lives in `~/Library/Python/3.9`, invisible to a daemon running as another UID, and
  `PYTHONNOUSERSITE=1 /usr/bin/python3 -c 'import yaml'` fails. Without it `ledger.py` refuses every
  append (fail-closed by design), so the daemon would run and write nothing. Preflight now tests
  `--daemon-python` and offers three working remedies.
- **No `set -e`.** A failed `chown` continued to "install complete", leaving a half-owned tree and a
  daemon that would not start. Now `set -euo pipefail`, and `run()` aborts with the rollback command.
- **`cp -R src dst/src` creates `tools/tools` on re-run** — the idempotence claim was false. Now
  removes and copies with a trailing `/.`.

### Fixed — the verifier damaged what it was verifying
It appended a forged line to the ledger, truncated HEAD, overwrote the schema and key registry,
deleted the socket, moved the socket's parent and stopped the daemon. Every check now **opens for
write without writing a byte**, or inspects ownership instead of attempting `chmod`. The daemon is
never stopped. `--no-write` removes even the single `progress_recorded` the success path adds.
It also now checks that the ledger **stays readable** — the previous version could have passed while
leaving the org unable to audit itself.

### Fixed — two claims that were not measured
- **`separate_uid` came from the flag, not the state.** `measured_isolation()` now derives it from the
  socket parent's ownership and mode, the ledger's owner, and the writer's own UID. Passing
  `--require-root-owned` no longer makes the label appear.
- **The peer UID was placed in the environment and never read.** `observed_recorder()` now consumes
  it, so `recorded_by` carries `peer:uid=…` — while `decision_by` still comes only from a signed
  receipt.

### Status
`sudo tools/writer-install.sh` and `tools/writer-verify.sh` were **not** run against a live org, and
the audit's NO-GO stands until it re-reviews these fixes. `workload_isolation` remains
`process_mediated`; H1's `separate_uid` is still unresolved.

## 0.39.0 — Authenticated Writer, stage A: one path to the ledger

`decision_by` was verified from a receipt, but **the write path itself was open to anyone** — and so
were the halt latch, the key registry and the schema. "A record used by a check is writable only by
the checker" was declared, with nothing forcing the path to be singular.

### Added
- **`tools/writerd.py`** — a Unix-socket daemon that is the only writer. Under
  `ORG_WRITER_SOCKET`, `ledger.py`'s four write operations (`append`, `reserve-exposure`,
  `trip-halt`, `release-halt`) **refuse to run directly**.
- **Requests carry a nonce and a digest over the whole body.** A tampered request is refused
  (`request_tampered`); a replayed nonce is refused (`replayed_nonce`).
- **The caller cannot choose the ledger path.** Write targets come from `--org NAME=ROOT` at startup;
  a path in `argv` is refused (`path_in_argv`) and an unknown org is refused (`unknown_org`). Only
  the four write ops are accepted (`unsupported_op`).
- **The socket's parent directory is validated before connecting** — not a symlink, not
  world-writable, owned by you or root. Whoever can write the parent can substitute the socket and
  answer as a fake writer.
- **Peer credentials (`LOCAL_PEERCRED` / `SO_PEERCRED`) feed `recorded_by` only.** Having connected is
  not evidence of having judged; `decision_by` still comes from a signed receipt.
- **`audit_writer_assets`** checks the latch, key registry, schema, ledger and HEAD. Making the ledger
  path singular means nothing if the latch can be deleted, the registry swapped, or the rules relaxed.
- **`tools/writer-install.sh`** (stage B, macOS) — idempotent, `--dry-run`, `--uninstall`. Creates a
  dedicated role UID, makes the ledger writer-owned, the socket parent root-owned `1770`, and the
  daemon/plist/config root-owned. Records the original owner and backs up the keys for rollback.
- **`tools/writer-verify.sh`** — measures the boundary instead of trusting the installer: appending to
  the ledger must fail, `chmod` must fail, moving the socket parent must fail, stopping the daemon must
  fail, and RPC tampering/replay must be refused. **It refuses to run as root**, since root can do all
  of it and would prove nothing.

### What stage A does NOT give you
**This is not an OS boundary.** At the same UID the caller can stop the daemon, restore file
permissions, or replace `writerd.py` itself. So `workload_isolation` is recorded as
**`process_mediated`**, and **H1's `separate_uid` remains unresolved**. Stage B needs a `sudo` step
this session could not perform, so it ships as a script plus a verifier rather than as a claim.

Even with stage B, **the host administrator is outside the threat model** — they can stop the daemon
and take ownership back. The guarantee is: *a normal agent/caller UID cannot alter the writer's
assets.* That is the definition of the boundary, not a shortfall.

### Measured
Writing through the daemon works and a direct append is refused (nothing lands). With the daemon
stopped, both paths fail closed and the ledger stays empty. Tampering, replay, path injection, an
unknown org and a non-write op are each refused. A world-writable or symlinked socket parent is
refused, and asking for `--require-root-owned` at the same UID is refused **with the tool saying why
`separate_uid` cannot be claimed**. An `AF_UNIX` path over the OS limit now reports that, instead of
failing to bind for no visible reason.

## 0.38.0 — Authenticated Mode, and H4b: releasing a halt

A different HMAC key proves only that *a key differs*. It does not prove a distinct principal, a
distinct process, or an independent approval — so building halt-release on top of it would have put
the name and the guarantee back out of step.

### Added — Authenticated Mode
- **Asymmetric signatures (Ed25519).** The judge holds the private key; **the writer holds only the
  public key** and can therefore verify but not produce a judgment. That is the property a shared
  secret cannot give. Backed by `cryptography` when present, `openssl` otherwise; if neither exists
  the mode refuses to run rather than falling back to a shared secret.
- **The trust store refuses to load if it contains a private key** — a writer holding one can forge
  the judgments it is meant to check.
- **Per-signer authorization**: `authorized_roles`, `authorized_lineages`, `may_release_halt`. A valid
  signature and *permission to issue that verdict* are different things; an unlisted capability is
  treated as denied.
- `identity_assurance` reaches `authenticated` only with an asymmetric key in an authenticated-mode
  store. `workload_isolation` stays a **separate axis** — a non-shared key says nothing about whether
  the writer runs under a different UID.

### Added — H4b: `ledger.py release-halt`
Releasing requires **all** of: an asymmetric receipt, a principal **other than** whoever tripped it,
`may_release_halt` authorization, a receipt bound to that specific halt's seq, and recorded recovery
evidence. Order is: verify → append + fsync → **then** clear the latch.

**If the release cannot be recorded, the halt stays.** Fault-injected: the release returns 4,
`halt_released` is absent, the latch remains, `halt-status` still reports halted — and the same
receipt replayed afterwards completes the release cleanly. Clearing the latch before recording would
produce the worst state available: stopped, then un-stopped, with no record that either happened.

### Acceptance tests (each run against a live org first, then fixed as tests)
The tripping principal cannot release; a shared secret cannot release; an unauthorized key cannot
release; a receipt bound to another halt is refused; missing recovery evidence is refused; an
independent authorized approver succeeds and the gated action passes afterwards; a release that
cannot be persisted keeps the halt; releasing with nothing halted is a no-op.

### Explicitly outside the threat model
**The host administrator.** They can disable the daemon or the hook, so no arrangement here
constrains them. Stated rather than implied.

### Still Compatibility Mode, and labelled as such
`workload_isolation` is `none` until the writer runs as a separate UID or service with ledger writes
restricted to it. Asymmetric keys close the "the verifier can also sign" hole; they do not by
themselves isolate the workload.

## 0.37.0 — H1: three principals, four assurance axes (Compatibility Mode)

`actor` conflated three things: who formed the judgment, who transcribed it, and who committed it.
In the real operating pattern the supervisor records a judge's verdict, so the observed actor is
always the supervisor — and separation of duties comparing `actor` to `actor` could only ever say
"the supervisor did not approve the supervisor".

### Added
- **Three principals, recorded separately.**
  `decision_by` is set **only from a verified receipt** — there is no CLI flag for it, because a flag
  means claiming to be anyone. `recorded_by` is *observed* from the session (proxy recording is
  fine — a judge need not append its own verdict). `committed_by` is the writer's own principal.
- **Separation of duties now compares `decision_by`**, never `recorded_by`. Comparing the recorder
  would make every legitimate proxy recording a violation.
- **`tools/identity.py`** — `keygen` / `revoke` / `receipt`. A judge signs its own judgment; the
  supervisor merely carries it. The receipt binds org, ledger, review subject, issue, role, phase,
  lineage, verdict, requirements digest, reasoning digest, signer, key, issue time and both versions.
  A receipt bound to a different org / subject / lineage / issue **cannot be replayed**.
- **Four assurance axes, deliberately not collapsed** into one strong/weak value:
  `identity_assurance`, `recorder_assurance`, `workload_isolation`, `reviewer_independence`.
  Collapsing them invites reading "it's signed" as "it's independent".
- **Agreement across lineages now records `reviewer_independence`.** When the same signer signed both
  lineages the joint admission is still generated, but it is marked `same_signer` and warns:
  **a signature does not make two lineages independent if one key can produce both.**

### What this is NOT
This is **Compatibility Mode**. The trust store holds shared HMAC secrets, so whoever can verify can
also sign, and the same user can replace the writer or the keys. Therefore `identity_assurance`
reaches `attested` and **never `authenticated`**, and legacy `actor` values stay `claimed` — they are
not promoted. Asking a separate process (0.36.0) prevents a `SystemExit` from propagating; **it is not
a trust boundary.** `authenticated` is earned only with an isolated writer, a restricted channel,
protected keys and per-principal authorization.

**Compatibility Mode results are evidence that an independent review happened. They must not be used
to enforce independence.**

### Acceptance tests
Same signer on both lineages, receipt replay, subject tampering, a revoked key, proxy recording, and
an unreadable trust store — each is a test, and each was run against a live org first.

### Fixed
- Inserting the `identity` block before `validation:` landed it before a **comment heading** that read
  `validation:`, producing two top-level `validation` keys — and YAML's later-wins rule silently
  dropped every validation rule while still parsing. The same failure mode docs/11 already records
  ("a repair that breaks things is the worst shape"), repeated. A test now fails on any duplicate
  top-level key in the schema.

### Next
H4b: authenticated release of a halt — an approver independent of whoever tripped it, which needs
identity to be authenticated rather than attested.

## 0.36.0 — H4a: a halt that actually stops things

`halt_tripped` existed in the schema and was displayed on the board. **Nothing enforced it** — the
hook never read it, so a tripped halt was a warning, not a state.

### Added
- **`ledger.py trip-halt`** — a writer-only operation. It writes the `<ledger-root>/HALT` latch
  **first**, then the ledger event, and returns non-zero if either fails.
- **The hook checks for an active halt on every gated call** and denies. It reads the *record*, not a
  declaration: a declaration can be removed, a hash-chained record cannot.
- **A recovery allowlist**, deliberately narrow: observation (`git status`, `cat`, `ls`), verification
  (`ledger verify`, `halt-status`, `repro_lint check`) and safe repair (`schema --fix`, appending a
  `correction`). **Ordinary work stops** — `npm test`, `git commit`, `git push`, any Write or Edit. A
  halt whose allowlist covers normal work is not a halt.
- `ledger.py halt-status` — readable while halted, since a halted org that cannot be diagnosed cannot
  be recovered.

### The fail-open this closes
"Don't declare a halt you couldn't record" is right as bookkeeping and **wrong as control** — it
leaves the situation unstopped. So:

- A failed halt write **returns non-zero**, so the caller must not let that action through.
- The latch is written before the ledger, so **the next call still stops** even when the ledger append
  fails. Fault-injected (`ORG_LEDGER_FORCE_APPEND_FAIL=1`): the trip returns 4, the ledger holds no
  `halt_tripped`, and the following call is denied via `source: latch_only` — which also flags that a
  halt may have failed to record.
- Deleting the latch by hand does **not** clear a halt that is in the ledger.
- **An unreadable ledger counts as halted.** Not knowing whether you are stopped is the worst
  fail-open available.

### Fixed — found while building this
**The halt check must not import the ledger into the hook process.** `from ledger import active_halt`
runs that module's top level inside the hook, so a replaced or broken `ledger.py` containing
`sys.exit(0)` made the hook **exit 0 and allow, printing nothing at all**. Measured. The check now
asks a separate process. A control decision must not execute inside the thing it is deciding about.

### Not implemented: release
`halt_released` is declared and writer-only, but **no operation writes it**. Releasing requires an
approver independent of whoever tripped it, and that depends on authenticated identity (H1). Deciding
"who may release" from a self-declared actor would let whoever stopped the org quietly restart it.
Sequence: H4a (this) → H1 (identity/receipts) → H4b (authenticated release).

## 0.35.0 — Codex plugin packaging, and what a Codex install actually guarantees

orgforge was not a Codex plugin: it was a `hooks.json` you copied into `.codex/`, pointing at
`${CODEX_PROJECT_ROOT}/integrations/common/org_hook.py` — so enforcement depended on a checkout the
plugin did not own, and vanished if that checkout moved.

### Added
- **A real Codex plugin** — `.codex-plugin/plugin.json`, `hooks/hooks.json`, and a `build.sh` that
  bundles the neutral core (`scripts/`, `tools/`, `template/`) so **every path is under
  `$PLUGIN_ROOT`**. Verified by deleting the source checkout mid-test: the hook still fired and still
  recorded its reservation.
- `.agents/plugins/marketplace.json`, so the repo can be added as a local marketplace
  (`codex plugin marketplace add .`).
- Tests that fail if the Codex bundle drifts, if a hook command references the checkout, if
  `hooks.json` carries a `//` key, or if the two projections' versions diverge.

### Learned by measurement (codex-cli 0.146.0; the public plugin docs URL is dead)
- `$PLUGIN_ROOT` is the injected variable. **`CODEX_PLUGIN_ROOT` does not exist** —
  `CLAUDE_PLUGIN_ROOT` is kept as an alias for Claude Code compatibility.
- The marketplace manifest must be at `.agents/plugins/marketplace.json`; a root `marketplace.json`
  is not read.
- **Codex's hooks parser accepts only `description` and `hooks`.** A `//` comment key — which Claude
  Code accepts, and which this repo's file had — makes it warn and **skip the whole file**, so the
  guardrail is silently absent. That is exactly how the first install looked like it worked while
  nothing was gated.
- **Installing and enabling a plugin does not enable enforcement.** An untrusted hook is silently
  skipped: no prompt, no warning in `codex exec`, no ledger entry. Trust is granted in the
  interactive TUI and stored as a content-bound sha256, so it cannot be seeded headlessly, and
  **editing a hook can require re-trusting**.
- `--dangerously-bypass-hook-trust` is a CI smoke-test tool. It proves the hook body works; it does
  **not** show that a normally-installed Codex is guarded, and it is not counted as a guarantee.

### Verified under bypass, in a disposable org against a sentinel
PreToolUse fires for `Bash` with `session_id` and `tool_use_id` both populated (so the reservation's
idempotency key is real); an operation inside the cap runs and leaves an `allow`; an operation over
the cap is denied with the **sentinel unchanged** and the `hold` recorded; a torn ledger denies; a
replayed `tool_use_id` does not double-count. Codex was told to try once and stop on refusal — a
correctly-denied call followed by a workaround would read as the hook never firing.

### Verified on the normal path — trusted, no bypass

The hooks were trusted once in the interactive TUI against v0.35.0's exact content, and the suite
re-run with no bypass flag: inside the cap the operation ran and left an `allow`; over the cap it was
denied with the **sentinel unchanged** and the `hold` recorded; a torn ledger denied; a replayed
`tool_use_id` did not double-count. All reservations are `validated:v1` and the chain replays clean.

**Control:** with the plugin removed, the same over-cap operation **succeeded** and the ledger did not
grow — so the stops above were this plugin's hook and not something else in the environment.
Re-installing the identical content kept the trust and enforcement returned.

So a normally-installed, normally-trusted Codex **is** gated. Note that trust is content-bound:
shipping a change to `hooks/hooks.json` can leave enforcement off until it is trusted again.

## 0.34.1 — three trust-boundary paths the atomic lock did not cover

0.34.0 made the reservation atomic, and the existing tests passed. Three ways around it remained,
none of which those tests could see, because they all sit on the boundary rather than inside it.

### Fixed
- **A reservation could be forged by a generic append.** Appending `exposure_budget_checked` with
  `delta_requested: -100` and then reserving `delta = 50` against `cap = 5` produced an allow with
  `committed = -99`, and the chain verified clean. `exposure_budget_checked` is now declared
  `writer_only`: only `reserve-exposure` can write it. **A record used by a check must be writable
  only by the checker** — otherwise the check is decorative. (`verify` deliberately does *not* apply
  this rule, since which path wrote an event is not recorded and can only be checked at append time.)
- **An idempotent replay was not required to be the same request.** Reserving `delta = 1` and then
  `delta = 100` under the same key returned the first allow. Reservations now carry a
  `request_digest` over (dimension, delta, cap, window, actor); a differing request under the same
  key is refused as a conflict. The key itself is the hash of a canonical tuple rather than a
  delimiter-joined string, which collides when a value contains the delimiter.
- **The hook trusted the exit code and ignored the structured result.** A writer printing
  `{"decision":"deny"}` and exiting 0 was allowed through. Only `exit 0` **and**
  `decision == "allow"` now passes; missing JSON, unparseable JSON, any other decision, or a decision
  that contradicts the exit code all deny. `ORG_HOOK_FAIL_OPEN` still applies when the result is
  *unreadable* (an environment problem) but not when a readable result says hold or deny.
- `_nk` is refused in any caller-supplied payload — the idempotency marker is the tool's, and a
  caller able to name it can claim an existing record's key and manufacture a no-op.
- `delta` must be finite and positive, `cap` finite and non-negative. Prior exposure that is
  negative, NaN or infinite denies rather than being counted, since counting it makes the running
  total smaller than it is.
- The reservation's own fields (`session_id`, `tool_use_id`, `rule`, `request_digest`) are declared in
  the schema, with `required`, types and `additional_properties: false`. They were being written
  while warning that they were undeclared.
- Append and fsync failures are fault-injectable (`ORG_LEDGER_FORCE_APPEND_FAIL` /
  `ORG_LEDGER_FORCE_FSYNC_FAIL`) and never become an allow. A partial write is truncated back, so a
  denied reservation does not leave exposure behind for the next call to count.

### Fixed — found while doing the above
- **Weight-0 operations were being denied.** Deleting a regenerable target (`node_modules`, build
  output) is priced at 0 deliberately, and a reservation requires `delta > 0`, so the guard turned
  "this is free" into "this is blocked". Unmetered operations now skip the reservation entirely.
- The deny message lost the word `HELD` when the decision moved from the organ to the writer.
  Whoever reads the log — supervisor or test — looks for that word; the name of "it was stopped"
  should not change because its source did.

### Migration
An org's existing `exposure_budget_checked` events predate the version stamp and are `legacy`, so the
new stricter rules do not apply retroactively — this repo's live org has 1071 of them and still
verifies clean. New reservations are validated.

## 0.34.0 — H3: only a decision that was written becomes an allow

The blast-radius cap used to work in two stages: an organ summed committed exposure, decided, and
printed `LEDGER-EVENT`; the hook then appended it and ignored any failure. Three holes followed from
that split. Parallel hooks could read the same `committed_so_far` and **both allow**, then append in
turn — so the total exceeded the cap. An ignored append meant the next call saw `committed = 0`, which
degrades an aggregate cap into a memoryless per-action check. And a hold was denied and returned, so
**stopping something left no record**.

### Added
- **`ledger.py reserve-exposure`** — one writer operation holding, inside the lock: schema snapshot,
  ledger-health check, idempotency lookup, exposure calculation, allow/hold decision, event append,
  fsync. It returns a structured JSON result and **only returns allow once the reservation is
  durable**. Measured: 16 concurrent reservations against `cap = 5` produced exactly 5 allows
  totalling 5.0, no duplicate seq, chain intact.
- **Holds are recorded.** The hook still blocks the call, but the decision is now in the ledger, so a
  cap that fires leaves evidence instead of silence.
- `committed_so_far` is computed by the writer and is **not an argument** — a caller able to declare
  it could under-report its way past the cap. Malformed prior exposure denies rather than counting
  as zero, since counting it as zero makes the running total look smaller than it is.
- The idempotency key is `(session_id, tool_use_id, rule, event_class)`; `tool_use_id` alone collides
  across sessions and rules. When invoked inside a subagent, `agent_id` is folded into the session
  part — whether one tool call can fire PreToolUse twice is not documented, so the reservation is
  keyed rather than assumed to fire once. **A missing key denies the metered action**: without
  identity there is no guarantee against double-counting a re-fired hook.
- The reservation defines **no timestamp argument at all** — not `--ts`, not `--backfill-ts`. Backfill
  authority stays on the ordinary ledger path (an H1 question); letting it near a cap reservation
  would allow placing a reservation outside the window it is summed over.

### Fixed
- **A bypass declaration that cannot be recorded now denies the call.** `ORG_ALLOW_MANUAL_MERGE` /
  `ORG_ALLOW_MANUAL_GH` were `except: pass` with the exit code unchecked, so a failed write let the
  bypass through with no trace. The escape hatch is granted in exchange for the declaration being
  recorded; if it isn't recorded, the exchange did not happen.
- Two hook tests seeded the ledger with hand-written events (`seq` starting at 0, no hashes). The
  health check is right to refuse appending onto a chain that was never a chain; they now seed
  through the real append path with a relative timestamp.

### Rollout
`ledger.py schema --fix` first, then confirm plain `ledger.py schema` exits 0 — **`--fix` returning 0
is not preflight success**, since a conflict it declined to overwrite still leaves a difference. Only
then is the reservation path meaningful. This repo's live org passed all three steps.

## 0.33.3 — the schema repairer weakened org-owned rules

`schema --fix` replaced the whole `validation` block when it found any gap, so a stricter rule an org
had added for itself (`required.progress_recorded: [milestone]`) was deleted while the template's
rules were restored. **A repair that weakens the org's own safety settings is a regression, not a
repair.**

### Fixed
- **`--fix` now deep-adds.** Only missing dict keys and list elements are added; anything the org
  added itself is kept. Lists merge as sets, so an org-added element survives.
- **A differing scalar at the same path is a conflict, not an overwrite.** Whether the org changed it
  deliberately or the template moved is not something the tool can tell, so it reports and leaves the
  org's value in place. Diagnosis and repair now derive gaps and conflicts from one computation —
  computing them separately is how the conflict case ended up neither reported nor repaired.
- **Block boundaries are found by indentation, not by regex.** `\nkey:\n(?:(?:  |\n).*\n)*`
  swallowed the comment lines and children that follow the next top-level key: replacing
  `validation` deleted `event_classes` outright, and the result still parsed as YAML.
- `used` (which classes are in live use) was dropped while rewriting the diagnosis and raised
  `NameError` on any org with a skew — caught by the 0.33.1 test.

### Note
Class declarations are still added as text, never rewritten: their comments carry the reasoning and a
YAML round-trip would discard it. Only the `validation` block is re-serialised.

## 0.33.2 — the lock was still fail-open

0.33.1's changelog described a fail-closed lock and an `ORG_LEDGER_ALLOW_UNLOCKED` escape hatch.
**Neither existed in the code.** The edit that was supposed to add them did not match its target and
was silently skipped, `self.error` was initialised but never set, and the escape variable appeared
nowhere outside the changelog — so an append continued after failing to lock. H3's atomicity was
about to be built on top of that.

### Fixed
- **A failed lock now refuses the append (exit 4)** and writes nothing. `ORG_LEDGER_ALLOW_UNLOCKED=1`
  is the only escape, and it states plainly that the serial-execution guarantee it depends on cannot
  be verified by the tool. `ORG_LEDGER_FORCE_LOCK_FAIL=1` injects the failure, because **fail-closed
  behaviour that cannot be fault-injected cannot be claimed** — that is what went wrong here.
- **`--ts` is gone from the normal append path.** Backfilling a real past moment is now
  `--backfill-ts`, so the intent is in the name. `--ts` is still accepted (hidden) because the
  PreToolUse hook passes it and must keep recording.
- **Timestamps are parsed as real moments**, not regex-matched. `2026-99-99T99:99:99Z` passed before.
  Future timestamps and anything older than 90 days (`ORG_BACKFILL_MAX_DAYS`) are refused — both
  move an event outside the rolling window a cap is summed over.
- **H8 compares the contents of `validation`, not just its presence.** Deleting
  `required.verdict_provisional` from an org's schema was reported as "no difference". Missing rules
  are as quiet as missing classes: records that should be refused get through. `--fix` replaces the
  whole `validation` block and says so — unlike class declarations, which are only added.
- **`schema --fix` writes atomically** (temp → fsync → rename → fsync(dir)). A direct overwrite
  interrupted halfway leaves the org unable to write anything at all.
- **An unknown validator type name fails closed.** `{ corrects: lst }` silently disabled that check;
  a schema typo must not be a way to switch validation off.
- A test from 0.33.1 pinned a literal timestamp (`2026-07-30T12:00:00Z`) and started failing as soon
  as that moment became the future. Tests that assert on time must compute it relative to now.

## 0.33.1 — Phase 0, the parts 0.33.0 claimed but did not do

The audit re-ran 0.33.0 and found six items I had reported as done that were not. An empty
`progress_recorded {}` passed both append and verify, and `--ts UNSET` was still accepted.

### Fixed
- **Field validation was only "is it a known class" and "is the payload a map".** Now three
  separate axes, deliberately not one switch:
  - `validation.required` — checked **only for classes that declare it**. Control events
    (`admission_decided`, `verdict_provisional`, `phase_admitted`, `correction`, …) declare it;
    `progress_recorded` does not, because its real payload has drifted from its declaration
    (43 events, none carrying the declared `fraction`, 38 carrying an undeclared `milestone`).
    Making every class closed-world at once would turn schema drift into **an org-wide recording
    outage** — that is not fail-closed, it is a known-migration availability incident.
  - `validation.require_any` — the correlation key may be any of `deliverable` / `candidate_id` /
    `claim_id` / `issue`; which one is used depends on the path. Pinning it to one rejected
    legitimate writes (it broke the separation-of-duties tests). A judgment with **none** of them
    is still refused.
  - Declared fields are enum/type-checked **when present**; undeclared fields warn and pass, except
    in the classes listed under `additional_properties_false`.
- **`--ts UNSET` and malformed timestamps are refused.** The writer stamps the time; `--ts` remains
  only for backfilling a real past moment, and must be `YYYY-MM-DDTHH:MM:SSZ`. A window-filtered
  view silently drops `UNSET`, which is how a cap's time window gets bypassed.
- **TOCTOU between validation and the recorded digest.** Validation ran before the lock while the
  digest was read inside it, so a different schema could be used for each. Both now come from one
  snapshot taken inside the lock.
- **`verify` now compares each event's recorded `schema_sha256`** against the schema being read and
  reports drift. Re-validation can only speak for the *current* schema; without this, what an event
  was validated against at write time was simply lost.
- **A platform without `fcntl` no longer writes.** It warned and continued, which is how 12 parallel
  appends all computed `seq=1`. `ORG_LEDGER_ALLOW_UNLOCKED=1` is the explicit escape, and it says
  plainly that the tool cannot verify the serial-execution guarantee it depends on.
- `_fsync_dir` failure is reported instead of swallowed — durability on such a filesystem is
  best-effort, and calling it "persisted" would be wrong.

### Added — H8 schema rollout skew
`ledger.py schema` diagnoses an org's `ledger-schema.yaml` against the plugin template, names which
missing classes are **in live use**, and `--fix` adds what is missing without rewriting existing
declarations. Needed because orgs own their copy: this repo's live org was four classes behind, two
of them in use (`correction` ×12, `asset_touched` ×3), so introducing "undeclared classes cannot be
written" would have stopped it from recording corrections. `--fix` refuses to write if the result
would contain two `event_classes` blocks — the first version of this repair did exactly that, and
YAML's later-wins rule silently dropped 65 class declarations.

### Note on the live org
After the skew fix, validation refuses exactly two of 1364 real events, and both are known defects it
should refuse: a `correction` written earlier this session with the wrong payload shape (already
superseded), and the pre-0.32.3 provisional verdict with no `review_subject_id`. No sound record is
blocked. Existing events are never retroactively validated.

## 0.33.0 — Ledger writer, Phase 0

Makes the ledger's write path survive concurrency and crashes, and validates new events against the
schema. **It does not touch `actor`.** Identity remains self-declared; `validation_assurance` and
`identity_assurance` are deliberately separate axes, and only the first one moves here.

### Added
- **Every append is one critical section** (`flock` on `<root>/LOCK`), covering read → seq → write →
  HEAD. Measured before: 12 concurrent appends all computed `seq=1` and verification failed on
  seq disorder. Measured after: seq 1–12, no duplicates, chain intact. Platforms without `fcntl`
  are told they cannot lock rather than silently racing.
- **Durable write order**: append → `fsync(log)` → HEAD to a temp file → `fsync` → atomic rename →
  `fsync(dir)`. **HEAD is now a cache, not the authority** — it is rebuilt from the log, and a HEAD
  that disagrees is reported and replaced.
- **Interior damage fails closed.** A torn (unterminated) line, a seq gap, a `prev_hash` break or a
  hash mismatch refuses the append with exit 4 instead of writing a consistent HEAD on top of a
  broken log. Previously a malformed line surfaced as a Python traceback.
- **Schema validation on new appends only.** The writer stamps `schema_id`, `schema_version` and
  `schema_sha256` into the envelope, and these are covered by the hash for v1+ events (a version
  outside the hash could be rewritten, which would make refusing a downgrade meaningless). Events
  without a version stay readable as `legacy_unvalidated` — validating retroactively would make
  migration impossible. `verify` re-runs the per-version validator and reports both counts.
- **The client cannot name the schema version.** `schema_version` / `schema_sha256` in the payload or
  on the command line are refused as downgrade attempts. `schema_id` is allowed, since a
  boundary-recording event holds it naturally (refusing it broke this release's own epoch record).
- **Unknown event classes are refused**, and an unreadable schema refuses the append rather than
  writing something unvalidated.
- `ts` is stamped by the writer. `UNSET` timestamps exist in real ledgers and any window-filtered
  view silently drops them.
- `schema_enforcement_started` — an **optional** audit record of where enforcement began. The
  normative record of which validator applies is each event's own envelope; this event may be absent.
- Same natural key with a **different payload** is now refused. Previously it was a no-op, which
  silently discarded the second write.

### Fixed — surfaced by the validation itself
- **Five event classes the tools write were never declared in `ledger-schema.yaml`**:
  `design_decided`, `rework_requested`, `scope_decided`, `tradeoff_decided`, `deploy_decided`.
  A live ledger holds 5 and 23 of the first two. Undeclared classes ride in no projection and no
  sensor — they are written and never read, which is part of why the rework warning stayed quiet.
  All five are now declared, shaped to match the real payloads.
- Two tests seeded a ledger by hand-writing events with no `hash`/`prev_hash`. The health check
  correctly refuses to append onto a chain that was never a chain; the tests now seed through the
  real append.

### Migration
Orgs keep their own copy of `ledger-schema.yaml`, so **an existing org must take the new class
declarations or its appends will be refused as unknown classes** — this repo's live org needed
exactly that. Existing events are untouched and stay `legacy_unvalidated`.

### Still not fixed
Actor spoofing (Phase 2), unpersisted organ emits with the cap fail-open they imply, and the absent
halt state machine. `lineage` and separation of duties remain evidence, not authenticated boundaries.

## 0.32.3

Closes the last gap the audit left open in `review_subject_id`, before the ledger-writer work starts.

### Fixed
- **`review_subject_id` recorded untracked filenames but not their contents.** The dirty digest was
  built from `git status --porcelain` plus `git diff HEAD`, and `git diff HEAD` does not include
  untracked content — so replacing an untracked file's contents entirely left the subject identical
  (demonstrated by the audit). A judge reading untracked files could have two verdicts about
  different artefacts count as agreement.
  The reviewed tree is now a real tree SHA: `read-tree HEAD` + `add -A` + `write-tree` against a
  **temporary index** (`GIT_INDEX_FILE`), binding tracked, staged, unstaged and untracked state into
  one identity without touching the supervisor's real index. `.gitignore`d build output stays
  excluded, so the same review is still reproducible. `dirty` and `head_tree_sha` are recorded
  separately so a dirty review can be recognised as such afterwards.

### Migration
Subjects computed by 0.32.2 differ from 0.32.3 for the same tree, so a provisional verdict recorded
under the old scheme cannot pair with a new one. Re-run both lineages on the same tree.

## 0.32.2

The same independent audit re-ran against 0.32.1: conditions 1, 2, 3, 5, 6 and 7 held, but
**condition 4 (stale/corrected verdicts) did not**. Four defects, all in the "the check refuses
correctly but there is no way out" family this project has now hit three times.

### Fixed
- **The `correction` command printed on rejection did not work.** It named `corrects_seq` / `reason`;
  the ledger requires `corrects: [seq]` / `kind`. The append succeeded, nothing was invalidated, and
  the next verdict was still refused — so a rejected lineage could never be replaced. Compounding it,
  `corrected_seqs` deliberately excludes only `probe`/`mistake`, leaving `superseded` for time-order
  resolution to handle; `_provisional_for` did not resolve it. Both are fixed, and the test now
  **executes the printed command and asserts the escape works end to end** (reject → correction →
  new verdict → joint) rather than asserting the word "correction" appears.
  The same wrong payload shape was used on this repo's own ledger earlier in the session; that entry
  has been superseded with a correctly-shaped one.
- **Verdicts about different artefacts counted as agreement.** Identity was
  `(issue, role, lineage, verdict)` only, so admitting revision A in one lineage and revision B in
  the other produced a joint admission. `verify` now generates a `review_subject_id` —
  a digest of issue, role, phase, base sha, reviewed tree sha, dirty-worktree state and the
  requirements digest — once, and the judge carries it rather than making it. Two verdicts with
  different subjects do not agree (exit 6), and pre-0.32.2 verdicts carry no subject, so they
  cannot participate.
- **The joint record carried only the second judge's reasoning.** It now holds
  `reasoning_by_lineage` (seq + digest + a `reasoning_ref` per lineage) and its own digest is derived
  from both, so neither account can go missing. `provisional` also projects the reasoning onto the
  Issue, so the digest has something to be checked against; ledger-only orgs are told that it does not.
- **A lineage could stack another verdict of the same value with different reasoning.** Only an exact
  retry (same subject, same verdict, same digest) is now a no-op; any other re-judgement is refused
  and must go through `correction`.
- `park` / `reject` no longer enter agreement handling at all — a non-pass verdict stands on its own,
  so it no longer draws an irrelevant "different subject" warning.
- `verify --print-subject` returns the subject without launching a judge. Obtaining it previously
  meant running the headless judge (measured: a 2-minute timeout) — a recording step must not require
  executing a judgement.

### Still not fixed (unchanged from 0.32.1)
Ledger actor spoofing, unlocked concurrent append, unpersisted organ emits, and the absent halt state
machine. `lineage` remains evidence that an independent review happened, not an authenticated
boundary. The authenticated single-writer design is the next change, staged separately.

## 0.32.1

An independent 4-lens audit (resilience engineering / STPA / adversarial code review / SRE) of
0.32.0 found that the agreement check shipped **deadlocked**. This release is the stop-the-bleeding
fix for that plus the fail-open it came with. Deeper findings from the same audit (ledger actor
spoofing, unlocked concurrent append, unpersisted emits, no effective halt state) are **not**
addressed here.

### Fixed
- **`cross-harness` orgs could not record an admit at all.** 0.32.0 required the other lineage's
  verdict to already be in the ledger, so from an empty ledger both orders were rejected
  (measured: exit 4 either way, nothing recorded). Admission is now produced in two stages:
  each lineage records a `verdict_provisional` in any order, and the tool generates
  `admission_decided{lineage: joint}` only when two lineages agree. Building that verdict is
  plumbing, not judgment — it is a function of the fact that they agreed; verdict/why/evidence
  are carried through from the judges verbatim.
  0.32.0 verified only that one side was refused, never that the pair could pass — the tests
  covered the predicate, not the CLI. `provisional` now has an end-to-end suite that starts from
  an empty ledger.
- **Unreadable safety config silently downgraded to `same-harness`.** A broken `constitution.yaml`
  or a missing PyYAML made a `cross-harness` org judge with one lineage and no way to notice.
  Reading the lineage now fails closed (non-zero exit, explicit message) in both `judge.py` and
  `ghsync/record.py`. There is no path that falls back to the weaker mode.
- A lineage can no longer rewrite its own verdict to manufacture agreement; correcting one
  requires a `correction` event. Cross-issue and cross-role verdicts do not satisfy agreement.
- Headless judge output no longer lands on a fixed `/tmp/orgforge-{role}-{issue}.json`, where
  concurrent runs collided and a failed run's stale file could be read as this run's verdict.
- `lineage`, `verdict_provisional` and `judges_disagreed` are now declared in `ledger-schema.yaml`.
- README stated v0.28.

### Known limitations recorded, not fixed
- `ledger.py append --actor` takes the actor from its argument, so one process can sign as both
  maker and gate and pass `DISTINCT_ACTOR` with an intact hash chain. **Until that is fixed,
  `lineage` is evidence that an independent review happened — not an authenticated boundary**,
  and 0.32's agreement requirement rests on the same assumption.
- Judgments recorded before 0.32 carry no `lineage`, so they cannot participate in agreement.
  Only new judgments flow through the two-stage path.
- Concurrent `append` has no lock: parallel writers can all compute the same `seq`.
- `LEDGER-EVENT` emits from organs are printed, not durably appended; a failed append does not
  fail the hook, so blast-radius caps degrade toward fail-open when recording breaks.
- `halt_tripped` exists in the schema but nothing enforces a halted state.
- README/docs describe enforcement as inescapable without stating the TCB and threat model.
  orgforge can constrain agents running under an enabled hook; it cannot constrain the host owner
  who can disable the hook.

## 0.32.0

### Added
- **Judge lineage is now a declared, enforced choice** — `constitution.yaml`
  `enforcement.judges.lineage` selects `same-harness` (default; nothing changes for an org that
  has not contracted a second harness) or `cross-harness`. Under `cross-harness`, `verify`
  **launches the second-lineage judge itself** (`codex exec` / `claude -p`, read-only,
  `--output-schema`) and returns its verdict on stdout, rather than printing a command the
  supervisor may or may not run. Both judges run: the in-harness subagent and the headless one.
- **`decide` requires both lineages to agree before recording an admit** — under
  `cross-harness`, `admission_decided = admit` / `refutation_attempted = survives` needs
  `--lineage` and a matching pass from the other lineage already in the ledger. Either side's
  reject/refuted stands alone. Without this, `verify` would print two verdicts and the
  supervisor could pick the convenient one — more checks, less strictness.
- **`drift factors`** — reads the reject/refuted reasons across Issues and counts common
  factors, so a defect recurring in five deliverables can be traced to what produced it
  (spec wording, the standard handed to the gate, conventions, task granularity) instead of
  being fixed five times. It reports what it could not count, and decides nothing.
- `verify` warns up front that a read-only judge structurally cannot admit a MUST that
  requires execution (a test loop, a live DB, a build) — measured: it returns `park`.

### Fixed
- `drift` read whole Issue comments, matching maker reports and rework instructions, so four
  of eight factors hit every Issue and the distribution vanished. It now parses only the
  judgment comment's `Why` section.

### Notes
- Two live findings from a second lineage, both after the in-harness judge had passed the work:
  a `left_at`-blind membership check granting SELECT authority across groups, and a
  "screen tests are writable" MUST met in wording with no DOM test environment installed.
- `role-settings.yaml`'s `model_family: family-B` still has no effect on an in-harness
  subagent; `judges.lineage: cross-harness` is what makes the separation real.

## 0.31.0

`role-settings.yaml` has declared `skeptic: model_family: family-B` — a different family from the
gate and maker — since the settings layer existed. Inside one harness a subagent inherits the
parent's model, so the declaration had no effect: the adversarial checker shared the maker's blind
spots (docs/03 §3). Running a judge on **another harness** is what makes that lineage real.

### Added
- `template/schemas/{gate,skeptic}-verdict.json` — the `output.json_schema` from
  `role-settings.yaml`, in a form `codex exec --output-schema` accepts. A verdict cannot come back
  missing `verdict`, `evidence` or (for the skeptic) the mutations it tried.
- `verify` prints the headless route on stderr: build the prompt, run it on the other harness with
  the schema, then pass the result through `intake` before reading it as a judgment.

### Changed
- `intake` reads a structured verdict **as structure** rather than by regex. A schema can require a
  field and still receive an empty string; shape and content are now two separate layers.
- `integrations/codex/config.toml` sets `model_reasoning_effort = "high"` for the judge tier and
  notes that a model name must be confirmed against the account before being written down.

### Notes
Verified against Codex CLI 0.146.0 with a ChatGPT account. Three things bit, all recorded in
`integrations/README.md`: `gpt-5-codex` is rejected for ChatGPT accounts; Structured Outputs
requires every property in `required` when `additionalProperties: false` (an optional field is
`"type": ["string", "null"]`); and `codex exec` reads stdin, so a non-interactive call needs
`</dev/null`.

A judge runs `--sandbox read-only`, so it cannot write regardless of whether the Codex hook is
wired — the guardrail projection for Codex remains unexercised.

## 0.30.0

Controls existed for the deliverable, the judgment, the report and the declaration. Nothing
covered **the supervisor doing the same state change by hand** — `git merge` instead of
`integrate`, `gh issue create` instead of `github_sync create`. In one session that put two
deliverables into `develop` with no gate and no skeptic; the ledger refused correctly, but only
once `complete` was run hours later.

### Added
- `PreToolUse` holds `git merge` / `rebase` / `cherry-pick` when the checkout is on `develop`,
  `main` or `master` inside an org. Feature-branch merges and read-only commands
  (`git merge-base`) are untouched. `ORG_ALLOW_MANUAL_MERGE=1` proceeds and records
  `bypass_declared` in the ledger.
- `PreToolUse` holds `gh issue create|close|edit|reopen` inside an org. `gh issue view|list` and
  `gh pr *` are untouched. `ORG_ALLOW_MANUAL_GH=1` behaves the same way.
- `bypass_declared` ledger class — a declared bypass is allowed but never unrecorded.

### Changed
- `github_sync decide --event integration_admitted` requires a `gate` admit for that Issue in the
  ledger and exits 4 without one, writing nothing to the Issue. The ledger already enforces the
  same shape on `phase_started`; this puts it on the integration side. A maker's report, however
  well evidenced, is not an admission.

Every hold prints the command to run instead. A hold that only refuses teaches its own bypass:
the bypass flag gets memorised and used routinely, and then the detour stops being recorded.

## 0.29.0

### Added
- `integrate --plan` lists the jobs of any `.github/workflows/*.yml` the merge touches and marks
  those carrying an `if:` condition — on the job or on any of its steps. A merge that unions a CI
  file can land steps in a job that only runs conditionally, so the check never executes while the
  YAML is valid and the suite is green. It reports the structure; reading it is the operator's job.

## 0.28.2

### Documentation
- This file rewritten for 0.12.0 onward: English, Keep a Changelog headings, one entry per
  version at 5–20 lines. It had grown to 50–70 lines per version and read as a work journal —
  retracted assessments, session narrative, an essay-length preamble about the 0.12–0.22 period.
  A changelog states what changed; rationale belongs in `docs/`. 1768 → ~1070 lines, with the
  0.11.0-and-earlier entries left as they were written.
- `docs/11-sdlc-mold.md` and the tool comments keep the design reasons but drop the incident
  detail — Issue numbers, round counts, ledger sequence numbers. A comment explaining why a check
  exists is useful to whoever maintains it; which Issue first tripped it is not.

## 0.28.1

### Fixed
- Independence and seam-contract declarations are matched **at the start of a line** only. A
  negation ("no `INDEPENDENT:` and no contract here") was matching as a declaration, and an
  independence declaration exempts the `owns` check — so the exemption could be taken by accident.
- Dropped the bare `"seam contract"` string from the seam markers; the gate now looks for the
  **structure** `handoff.py` emits (`## Your slice`, `Inputs you receive:`, `Outputs you MUST
  produce:`), which does not appear inside a negation.
- `intake` prints a machine-readable `[intake] INCOMPLETE issue=N role=R missing=…` line. Its
  exit code was already 10, but a shell pipeline (`| tail`) reports the last command's status.

## 0.28.0

### Added
- `org_cycle intake --issue N --role gate|skeptic|maker --report TXT` — checks that a subagent's
  report has the shape its role owes (verdict + evidence for gate/skeptic; a commit hash + DoD
  output for maker). Exit 10 when incomplete. It does not judge the verdict, only its presence.
  `--report -` reads stdin.

### Changed
- `github_sync branch --create` creates a **worktree** when `.orgforge/wt/issue-*` exists instead
  of switching the main checkout's branch. `--no-worktree` restores the old behaviour; switching
  the main branch now warns.
- The seam-gate rejection message leads with the shorter path (`INDEPENDENT:` on the first line)
  and states that it exempts the `owns` collision check.

## 0.27.1

### Changed
- `verify` no longer repeats the prior judgment twice (it appeared in both the judgment history
  and the "what the gate already saw" section). Skeptic prompts drop ~58 lines.

### Notes
- Considered per-role model/effort tiers and did not adopt them. Measured over 52 runs: one wait
  is ~21% of total time and rework rounds are ~79%, so lowering a tier cannot move the total, and
  lowering the gate or skeptic would add rounds.

## 0.27.0

### Added
- `org_cycle rework --issue N --after reject|refuted --by WHO --reason TXT` records that a rework
  was ordered. `verify` prints this command next to the `decide` command on a reject, so the
  ordering and the recording happen together.
- `github_sync decide --claimed / --verified` separate what was reported from what the supervisor
  ran themselves. Warns when `--verified` carries no trace of a command, and when a hedge in
  `--claimed` ("not present", "not measured", …) is not addressed in `--verified`. Existing calls
  without these flags are unaffected.
- `org_cycle` / `github_sync` / `ledger` print `[orgforge <version> @ <cwd>]` to stderr.
  Suppressed for `view` / `census` / `digest`, for internal calls, and by `ORG_QUIET=1`.

## 0.26.0

### Changed
- `agents/skeptic.md` splits findings in two: a refutation of the Issue's MUSTs is grounds for
  `refuted`; a real defect outside those MUSTs is returned as "recommend filing an Issue" and is
  not. Ambiguous cases go to the supervisor rather than being decided by the skeptic.
  `agents/gate.md` states the same line for `reject`.
- `verify` asks the skeptic for an `out_of_scope` field.
- `template/SPEC.md` and `/org-decompose` require a **definition of done**: the MUSTs going
  RED→GREEN completes the Issue; defects found afterwards outside that scope become new Issues.
- `org_cycle show` warns when a deliverable has been reworked more than three times. Counts
  reworks, not judgments — an Issue can take many rounds and still converge.

### Documentation
- README rewritten: English throughout, 331 → 215 lines, scoped to an entry point (what it is,
  why the decomposition, what ships, where to read, honest status). Command-level detail moved to
  `REFERENCE.md`; the per-cycle walkthrough to `QUICKSTART.md` §8.

## 0.25.3

### Documentation
- `QUICKSTART.md` §8 gains the actual command sequence for one Issue
  (`begin → complete → handback → verify → integrate`), which existed nowhere in prose.
- `REFERENCE.md`, `ARCHITECTURE.md` and the marketplace description catch up with 0.12–0.25.2.

## 0.25.2

### Fixed
- `repro_lint check` states that it has **not** judged whether a failure is new when no baseline
  exists. It had been asserting "not in the baseline, so newly regressed" without reading one,
  which stopped a gate from judging work whose whole purpose was to fix those items.
- `/org-init` takes a `repro_lint baseline` once, as `/org-adopt` already did.

### Changed
- `agents/gate.md` and `agents/skeptic.md` end at returning the judgment (verdict, why, evidence,
  standard, risk); recording is the supervisor's. Subagents have neither `ORG_GITHUB_REPO` nor the
  ledger path, so the previous instruction to record could not be followed.
- `verify` splits its output: stdout is what the subagent receives (what to return), stderr is the
  command the supervisor runs.

## 0.25.1

### Removed
- `req_lint` VOIDDEP (added in 0.25.0). It keyed on backtick identifiers, and real requirement
  documents in Japanese carry none, so it never fired. A version keying on particles produced
  false positives on every line. The formalisation is sound; extracting the object from Japanese
  prose is not tractable here.

## 0.25.0

### Added
- `req_lint` VOIDDEP — flags an update/delete requirement whose object is never created (the QUS
  `Complete` predicate). *Removed in 0.25.1.*

### Changed
- `/org-decompose` doctrine: do not split by layer or by file. A unit is a valuable change in
  behaviour that will likely touch several layers; `owns` avoids collisions but is not the split
  criterion. INVEST's *Small* is cited for its actual reason — above that size the scope of the
  story stops being knowable.

### Documentation
- `docs/sources.md` records the split criteria of Spec Kit, Kiro, INVEST, SPIDR, QUS, PBR, BMAD,
  Devin and Tessl with primary quotes. None of them detects an oversized task.

## 0.24.0

### Added
- `github_sync split-check` gains two checks: (d) authorisation MUSTs that only define who may
  enter and never what a member may do; (e) more than one failure mode in one Issue (same `owns`,
  different verification means).

### Changed
- `/org-decompose` asks whether the deliverable has one failure mode and one verification means,
  in addition to disjoint `owns`.

## 0.23.0

### Fixed
- `discover.py` walks past a worktree created by `begin`. Tracked files under `.orgforge/`
  restored an `.orgforge/` inside each worktree, which stopped the search and produced a stray
  ledger there — judgments written from a worktree never reached the org's ledger.
- `integrate` passes its own test output to the Issue log; it was failing its own log check.
- Ordinary `git push` is no longer metered against `destructive_ops` (only `--force`,
  `--force-with-lease`, `--delete`, `--mirror` are). Default cap raised 50 → 150.

### Added
- `org_cycle show` reports what the recent rounds were about (implementation vs test defects).
- `verify --role skeptic` forwards the areas the gate said it did not probe.

## 0.22.1

### Fixed
- `verify` could not find `agents/*.md` or `handoff.py` after the 0.22.0 split — two of the four
  `__file__`-relative lookups were not updated. Path resolution is now in one place per package
  (`HERE`), enforced by a test.

## 0.22.0

### Changed
- `org_cycle.py` (1440 lines) → a 149-line dispatcher plus `tools/orgcycle/`
  (`_core`, `cycle`, `judge`, `ship`, `inspect`).
- `github_sync.py` (1176 lines) → a 197-line dispatcher plus `tools/ghsync/`
  (`_core`, `backlog`, `record`, `branch`, `coverage`).
- `tests/` split into `conftest.py` + `test_ledger` / `test_orgcycle` / `test_status` /
  `test_organs`.
- CLI invocation is unchanged (`python3 tools/org_cycle.py begin …`).
- `build.sh` syncs `tools/` subpackages into the plugin bundle.

## 0.21.0

### Changed
- `github_sync decide` writes **both** the Issue comment and the ledger receipt in one command,
  ledger first — if a control rejects the judgment, nothing is written to the Issue. Previously
  the receipt was a second command the operator had to run.
- Idempotent no-op requires the **same actor**. `(class, natural_key)` alone meant a different
  actor reusing a key was treated as a replay, so `DISTINCT_ACTOR` and `REQUIRES_PRIOR` were
  never evaluated. `decide` keys on `{event}-{issue}-{digest}` so a second round does not collide
  with the first.

## 0.20.0

### Added
- `verify` embeds the judgment history (which round this is, prior reasons in full). Round count
  takes the larger of ledger and Issue, since one side of the double record can be missing.
- `integrate --plan` shows what would be merged and which parallel worktrees touch the same files.
- `asset_touched` ledger class + `org_cycle touched` — records production-asset changes (DDL,
  privilege grants) with `authority` and `reversible`.
- `public_surface_declared` ledger class — `complete` lists newly exported symbols, DB functions,
  grants, RLS policies and endpoints and requires a declaration (`--new-surface` /
  `--new-surface-none`). Ranks `SECURITY DEFINER` and granted functions first; excludes tests.

## 0.19.0

### Added
- `org_cycle show --issue N` — one view of an Issue: commits, worktree, judgment history (with
  correction and backfill marks), what it is waiting on, next command.
- `correction` ledger class — `kind: probe|mistake` is excluded from counts; `backfill` and
  `superseded` are not.
- `begin` / `plan` list unready dependencies and open human tasks before starting. Advisory.

### Changed
- The status board shows the reason a deliverable was rejected, read from the Issue.
- The seam gate reads a seam contract from a file the prompt references (org root and temp
  directories, 512 KB limit), so a long contract need not be pasted inline.

## 0.18.0

### Fixed
- The status board takes the **latest** `admission_decided` per deliverable. Held as a set, an
  earlier `admit` survived a later `reject`.
- Rejected deliverables awaiting rework appear on the board (AMBER).
- `verify` templates use absolute paths instead of an undefined `$P`.

## 0.17.0

### Fixed
- Correlation resolves identifiers transitively through the ledger. `cycle_started` carries
  `candidate_id` and `pack_manifest_id: "issue-N"` while judgments carry `deliverable`/`issue`,
  so direct comparison never matched and a maker could admit its own work. Rejection messages
  show how the identifiers were linked.

### Notes
- Verified the previously untested controls: skeptic self-refutation, `report_up` /
  `conformance_reviewed` ordering, and every `alignment` / `resource` / `reconcile` subcommand.

## 0.16.0

### Fixed
- A judgment carrying no correlation key is **rejected** rather than silently accepted. The
  `DISTINCT_ACTOR` check returned early when the key was absent.
- `result_deployed` correlates a `refutation_attempted` by any shared identifier. Comparing
  `claim_id == candidate_id` matched `null == null`, which disabled the deploy gate.
- `learning.py repeats` reads `cause`, `hypothesized_cause`, `reason`, `why` and
  `checklist_ref`, and covers `rework_requested`. Reports `unknown` rather than `clean` when no
  cause is readable, and states that matching is by string.

### Documentation
- `REFERENCE.md` lists `handoff`, `doctrine`, `learning`, `alignment`, `resource`, `reconcile`,
  `harness_probe`, `status`, `attention` and `conventions`, which were absent.

## 0.15.0

### Added
- `github_sync log` writes a `progress_recorded` receipt to the ledger. Without it the
  `work_in_progress` view stayed empty and `/org-resume` could not recover.
- `complete --learned` proposes a claim to doctrine with provenance filled in (`propose` allowed
  omitting `retrieved_at` / `review_by` that `admit` requires, so it always stalled).
- `org_cycle gc` removes merged worktrees, keeping unmerged or dirty ones; `org_cycle record`
  backfills a past judgment with a `backfilled` marker; `begin` records `attention_allocated`.

### Changed
- `destructive_ops` weights 0 for regenerable targets (`.orgforge/wt/`, `node_modules`, build
  output). Recursive deletes of source, `/`, `~` or parent traversal are unchanged.

## 0.14.0

### Added
- `org_cycle handback --issue N` — pushes the feature branch, opens a PR against `develop` with
  `Closes #N`, and logs it. There was no command to open a PR.

### Changed
- `github_sync log` requires `--command` and `--result` on milestone events and rejects a result
  that only restates success. `progress_recorded` is exempt.
- `begin` fills the log with facts the tool already knows (branch, worktree, parent,
  `candidate_id`); `complete` requires `--command` / `--result`.

## 0.13.0

### Added
- `org_cycle integrate --issue N` — verifies the gate's `admit` and the skeptic's `survives` are
  in the **ledger**, then merges, runs the combined suite, records `integration_admitted` and
  logs it. Exit 4 when the prerequisites are missing.
- The status board reports deliverables admitted with no refutation record (RED).
- `verify` embeds an absolute path for `repro_lint`; the gate had been reporting it as unrunnable.
- `risk_accepted` in the ledger payload, surfaced on the board; the skeptic receives the gate's
  known risks.

### Changed
- `complete --domain-model-none` lists newly exported symbols and asks whether they are domain
  vocabulary. Advisory.
- `complete` removes the worktree `begin` created, keeping it if there are uncommitted changes.

## 0.12.1

### Fixed
- `complete` checks the ledger before reporting that a gate admission is missing; it printed the
  same line unconditionally. Matches on `deliverable` and `payload.issue`, and names a near-miss
  record when nothing matches.
- `verify` states that its output may be pasted inline (the seam gate reads the prompt body).
  *Superseded in 0.19.0, which lets the gate read a referenced file.*

## 0.12.0

### Added
- `begin` creates a per-Issue git worktree at `.orgforge/wt/issue-<N>/`. Running parallel makers
  in one checkout put one Issue's commits on another's branch. `--no-worktree` opts out.
- `org_cycle verify --issue N --role gate|skeptic` assembles the material for a judgment: the
  seam contract (via `handoff.py`), the charter from `agents/<role>.md`, the Issue's SPEC/MUSTs,
  and a `decide` skeleton. The skeptic also receives what the gate already examined. Verdict,
  reasoning and risk are left empty.

### Fixed
- `handoff.py` resolved its root by discovery only in its help text; the code raised `TypeError`.
- `_agents_dir` missed the bundled layout where `agents/` is a sibling of `tools/`.

## 0.11.0

**配管を自動化する（docs/11 §0d）。** 実地の指摘: 「なんか手で作業しているように見える」。
そのとおりだった — `/org-work` は「こういうイベントを打て」という散文の指示で、実行するのは
エージェントだった。**Issue 2件あたり11コマンド**、18 Issue なら約90回の手打ちで、1回の
取り違えで台帳の整合が崩れる。

とりわけ `parent` が問題だった。0.10.1 でフェーズ連鎖の親継承を実装したのに、**その値を人が
Issue から目で拾って手打ち**していた。値が手打ちである限り取り違えが起き、継承の実装が活きない。

### `tools/org_cycle.py`（新規）

```
org_cycle.py begin    --role R --issue N [--agent A]
  → claim / spec_delegated / phase_started / cycle_started / Issue へ log / stage を
    正しい順序と actor で一括実行。parent と candidate_id は Issue から自動解決
org_cycle.py complete --role R --issue N --outputs T (--domain-model-updated|--domain-model-none)
org_cycle.py plan     --role R --issue N     # 何も実行せずイベント列を印字
```

三つの性質:

1. **自動解決** — `parent` は Issue の `Parent: #N`（`create` が書く）と sub-issue API から。
   `candidate_id` は Issue のトレーラから。**人が値を運ばない**
2. **止まったら止まったまま** — 途中失敗ならそこから先は打たない。部分適用を「成功」と
   報告するのが最悪（台帳が壊れた状態を正常に見せる）
3. **再実行が安全** — 各イベントは natural-key で冪等。「止まったら直して再実行」が成立する

### 線引き: 配管は自動化する、判断は自動化しない

自動化したのは**順序と actor が決まっている配管**だけ。**何を選ぶか・誰に委ねるか・分割するか・
admit するかは自動化していない** — docs/03 §6.5 の「forced delegation は設計エラー、
forced invariant は正しい」をそのまま踏襲する。

### ドキュメント

ARCHITECTURE のツール表が14件のままで、実際の20件と乖離していた（`github_sync` `status`
`discover` `req_lint` `org_cycle` が未掲載）。README/REFERENCE にも `org_cycle` と
`needs-human` を追加。

テスト 218 → 221件。
## 0.10.1

**タテカエ org の申し送り（改訂版）に全件対応。** A-1 は `/org-work` が起動せず、しかも
**lint が GREEN を出す**という組み合わせで、報告のとおり最も重い。

### A-1【重大】views の実装がスキーマの半分しかなかった

`ledger.py` が13件をハードコードしていた一方、`ledger-schema.yaml` は26件を宣言していた。実害:

- `/org-work` が `parts_inventory` を引けず、**コマンド全体が起動しなかった**
- **gate の context_pack 3件と skeptic の 2件がすべて未実装**だった。`organization.yaml` が
  「gate はこの3つを見て admit する」と宣言していても実行時に1つも引けない。SoD（maker≠checker）は
  中核主張なのに、**checker が判断材料を取得できなかった**
- それでも `org_lint` は pass した。CP 検査は「スキーマに定義があるか」しか見ず、
  **「ツールが実装しているか」を見ていなかった**

対処は報告の提案1のとおり: **`VIEW_FROM` を廃し、`ledger-schema.yaml` の `views:` を読む。**
view を足すのに Python を触る必要がなくなり、**乖離が構造的に起きなくなった**。あわせて
`org_lint` に **VW 検査**（スキーマの全ビューをツールが引けるか）を足した — 提案2の
「lint が実装との乖離を検出できないのが本質的な穴」への対処で、安全網として残す。

### B-2 フェーズ連鎖が objective と task で分断されていた

founding は objective 単位で requirements/design を admit するが、`/org-work` は task Issue 番号を
`deliverable` にする。別の文字列なので連鎖せず、指示どおり進めても task が弾かれた。

task ごとに再 admit させるのは同じ設計を N 回 admit するセレモニーにしかならない。**設計は
objective の単位で起きた**のだから、`phase_started` の payload に `parent` を書けば
**親の admit を継承する**ようにした。親を持たない deliverable は従来どおり自分の admit だけを見る。

### B-4 CEO 承認を台帳に記録する手順を追加

「承認後に objective Issue を作れ」と指示しながら、承認そのものを記録する手段がなかった。
founding は charter-tier（docs/05 §1）なのに、承認された事実がどこにも残らない。
`proposal_adjudicated{proposal_id: founding, decision: approve, human}` を打つ手順を
`/org-found` に追加した（既存スキーマのまま）。

### あわせて: コマンドの env 依存を全廃

`${ORG_LEDGER_ROOT}` を渡していた箇所（10コマンド・24箇所）を discovery に置き換えた。0.9.0 で
ツール側は対応済みだったが、コマンド側が env を渡し続けていたので、設定が無い環境で壊れていた。

そのうち2箇所は **`${ORG_CONVENTIONS_ROOT:-$ORG_LEDGER_ROOT}` というフォールバック**で、
conventions を ledger ディレクトリに書き込む混入バグでもあった（監査記録に別種のデータが混ざる）。
`conventions.py` / `doctrine.py` を discovery 対応にして、フォールバック自体を消した。

### A-2 / A-3 / A-4 / B-1 / B-3

0.10.0 で対応済み（`split-check` の `#N` 限定、SKELETON の必須キー追加、`on_candidate_arrival` の
実例、`needs-human`、O2 メッセージ）。A-4 の cadence 表記は SKELETON のコメントで示している。

テスト 213 → 218件。
## 0.10.0

**人間にしか実行できない作業を Issue にする（docs/11 §0c）。** タテカエ org の founding〜decompose
を通しで走らせたセッションからの申し送りに基づく。

### 問題: org は自分が作れるものだけを Issue にしていた

実地の founding で3件が**セッションの散文にしか存在しなかった** — Supabase プロジェクト作成、
Google OAuth クライアント登録、GitHub のブランチ保護設定。いずれも org のツールでは完結しない
作業で、Issue にも台帳にも残らなかった。結果:

- セッションが切れれば消える（`/org-resume` は ledger を読むので復元されない）
- `/org` が「66/66 被覆・GREEN」と出すのに、実際は人間待ちで着手できない
- `ready` が人間待ちを依存として表現できず、ブロック済みの task を maker に渡す
- `coverage-check` は「Issue になったか」しか見ないので前提が欠けても通る

`orgforge:needs-human` ラベルは `/org-init` が作っていたのに、**それを立てる手順がどのコマンドにも
無く、使用実績は 0 件**だった。仕組みだけあって使う道がなかった。

とりわけブランチ保護は **§4e の機械的拒否層の一部**でありながら GitHub の管理設定なので
コードでは実現できない。散文に消えると「機械が守るはず」の層に穴が開いたまま誰も気づかない。

### 対処

- **`github_sync needs-human`**（新規）— 人間タスクを Issue にする専用の口。`--blocks` で
  下流を縛れ、`Depends on: #N` を書けば `ready` がブロック済み task を返さなくなる
- **`/org-found` と `/org-decompose` に抽出手順を追加** — 抽出源は既存の
  `REQUIREMENTS.md` の Open Questions / Assumptions（29148 の標準節。§0b でこれを必須にしたのは
  ここに効かせるためでもある）。判定は「org のツールで完結するか」
- **`/org` の board が needs-human を RED として最上位に出す** — 「あなたを待っている」ものこそ
  board の意味であり、それが見えないなら board は嘘をついている。GitHub が見られない環境では
  黙って飛ばす（board 自体は落とさない）

### 同じ申し送りにあった細かい修正

- **`split-check` が散文中の数字を依存と誤検出していた** — 「実装コードは1行も入らない」の「1」が
  `#1` として解釈された。`#N` の形だけを依存とみなすよう修正
- **`organization.SKELETON.yaml` が lint 必須項目を含んでいなかった** — そのまま埋めると初回
  lint で 31 violations が出た。`gaming_defenses` / SoD の `authorization`・`recording` /
  `structure.span` / layer の `departments:` キー / gate・skeptic の `loop` を、コメント付きの
  空欄として追加。特に `departments:`（`roles:` ではない）は例が無いと必ず間違える
- **`org_lint` O2 のメッセージが中間管理職の追加を勧めていた** — span 超過時の選択肢に
  「span を宣言し直す」を先に並べた。契約を持たない coordinator を足すのは docs/03 §6.5 と緊張する

## 0.9.4

**`!` ブロックは「エージェントが作業する前」に一斉展開される — 書いた後に走る検査を `!` に
置いてはならない。** 設計上の欠陥で、3コマンドが該当した。

`/org-found REQUIREMENTS.md` が次で落ちた:

```
req_lint: REQUIREMENTS.md がない。/org-found が REQUIREMENTS.md を書いたか確認すること
```

ファイルは実在していた。`!` ブロックはコマンドが**展開される時点**で実行されるので、
「REQUIREMENTS.md を書く → 検査する」という順序が原理的に成立しない。検査は必ず
「まだ書かれていないファイル」に対して走る。

該当箇所（すべて「書いた後に走るべき検査」）:

- `/org-found` の `req_lint`（REQUIREMENTS.md を書いた後）
- `/org-found` の `org_lint`（organization.yaml を書いた後）
- `/org-adopt` の `org_lint`（同上）
- `/org-decompose` の `coverage-check`（task Issue を作った後 — `!` だと Issue 0件の
  時点で走り、必ず全件 GAP になる）

いずれも `!` を外し、**エージェント自身が Bash で実行する**手順に変えた（コードブロックで
提示し、なぜ `!` にできないかも書き添えた）。

あわせて `/org-decompose` の `nearby_deaths` が `${ORG_LEDGER_ROOT}` に依存していたのを
discovery に変更（0.9.0 でツール側は対応済みだったが、コマンド側が env を渡していた）。

**判定基準:** `!` に置いてよいのは**前提の確認**（場所・発見結果・既存ファイルの状態）だけ。
そのコマンドの作業結果に依存する検査は、エージェントが順に実行する。

## 0.9.3

**zsh が変数を単語分割しないため、0.9.2 の修正が別の形で壊れていた。**

0.9.2 でシェル関数を消した際、引数を文字列に組み立てて渡す形にした:

```sh
A=organization.yaml; for f in …; do A="$A $f"; done
python3 org_lint.py $A          # ← zsh では引数1個として渡る
```

`sh`/`bash` は `$A` を空白で分割するが、**zsh は分割しない**（SH_WORD_SPLIT が既定 off）。
Claude Code のシェルは zsh なので、5ファイル分の文字列が**1引数**として渡り、
`org_lint` が「引数が足りない」と判断して usage を出して exit 2 になった。

位置パラメータ（`set -- "$@" "$f"`）に置き換えた。これは sh/bash/zsh のいずれでも
正しく複数引数として渡る。

**`!` ブロックのシェルは zsh である。** 変数に組み立てた引数リストを裸で渡してはならない。

## 0.9.2

**`/org-found` が引数を2つ以上受け取ると lint が壊れるバグを修正。**

`!` ブロック内でシェル関数を定義し、その中で `$1` を使っていた:

```
pick() { [ -f "$1" ] && echo "$1" || echo "${CLAUDE_PLUGIN_ROOT}/template/$1"; }
```

**関数内の `$1` は、関数の引数ではなくコマンドの第1引数に先に展開される。**
`/org-found REQUIREMENTS.md DECISIONS.md` と呼ぶと `pick constitution.yaml` が
`DECISIONS.md` を返し、4ファイルすべてが同じ誤ったパスを指した:

```
[SC] constitution.yaml file not found: .../template/DECISIONS.md
[SC] moves.yaml file not found:        .../template/DECISIONS.md
[SC] ledger-schema.yaml file not found: .../template/DECISIONS.md
[SC] sensors.yaml file not found:      .../template/DECISIONS.md
```

シェル関数を使わない形（`for` ループで組み立てる）に置き換えた。他のコマンドに同じ
パターンが無いことも確認済み。**`!` ブロックの中でシェル関数を定義しないこと** —
コマンド引数と衝突する。

## 0.9.1

**ドキュメントを 0.9.0 の実態に合わせ、`/org-init` の誤爆を機械的に止める。** 機能追加はない
patch リリースだが、**バージョンを上げないと `/plugin update` がキャッシュを更新しない** —
同じ version 番号のままドキュメントやコマンドを直しても、利用者には届かない（実地で判明）。

### 直したドキュメントの齟齬（実地で判明した4点）

- **コマンド名が未修飾だった** — 正しくは `/orgforge-plugin:org-init`。README / QUICKSTART /
  REFERENCE / ARCHITECTURE の24箇所を修正。他のプラグインと名前が衝突しないための正式な形
- **インストール手順が directory 参照のままだった** — ローカルディレクトリ参照はそのマシンで
  しか動かず、**未コミットの変更がそのまま動く**（検証していないコードで org を動かすことになる）。
  GitHub 参照に書き換え、push が必須になる開発フローも明記
- **「`ORG_LEDGER_ROOT` は必須」が 0.9.0 で嘘になっていた** — 発見が既定なので通常は不要。
  REFERENCE の env var 節を「すべて上書き」に書き直し、優先順位（明示的な引数 > 環境変数 >
  発見）と、なぜ発見が既定かを明記。QUICKSTART §2 も「セットアップは不要」に全面改稿
- README に `org-adopt` が無かった

### `/org-init` の誤爆ガードを機械判定に

ステップ0が「場所を表示する」だけで判断を人任せにしていたため、**プラグイン自身の開発ツリーを
org 化する事故を2回起こした**（`.orgforge/` + テンプレ7点 + `develop` ブランチ + GitHub ラベル
9件。いずれも復旧済み）。`.claude-plugin/marketplace.json` か `integrations/claude-code/commands`
の存在で機械的に判定し、**⛔ STOP を出して以降のステップを止める**ようにした。
「これは表示ではなく指示である」ことも明記 — 表示は読み飛ばされる。

## 0.9.0

**An org is a place on disk, not a shell environment — and the founding→backlog path is now a complete,
gated chain.** Two themes: the flow from an RFP to workable Issues got its missing steps and its
coverage gate, and human diff review was retired in exchange for a mandatory, tamper-evident record.
Alongside them, the setup that used to be a page of `export`s is gone entirely.

### Zero-setup discovery — `.envrc` is no longer part of the flow
`ORG_LEDGER_ROOT` / `ORG_GITHUB_REPO` used to be the only way the organs and the guardrail hook knew
where the org was. That had three costs, and the third is the serious one:

- **Not portable.** A state root written as `/Users/someone/proj/.orgforge/ledger` is wrong on the next
  machine — while the whole point of putting the full spec in the Issue is that *any* environment can
  pick up the work.
- **One org per shell.** A single exported variable cannot serve two checkouts, so running orgforge in
  several repositories from one environment either cross-contaminated the audit record and the
  blast-radius budget, or required direnv.
- **Silent permissiveness.** A session that had not sourced `.envrc` found no ledger — and the
  guardrail with no ledger **allows everything**. The failure mode of a forgotten setup step was an
  ungated session, which is the one failure mode a guardrail must not have.

New `tools/discover.py` resolves the org from the working directory: `.orgforge/` beside
`organization.yaml` (walking up, so subdirectories work), and the backlog repo parsed from
`git remote origin` (locally — no `gh`, no network). Precedence is **explicit argument > environment
variable > discovery**, so every existing override still wins. `_organ.resolve_root()` funnels it
through the one read path all organs share; `root` became optional on 43 tool commands and `--repo`
on 9; both hooks discover instead of requiring env. `/org-init` no longer writes `.envrc` — it
*verifies discovery works* instead. Multi-repo operation from one shell is now the default rather
than a configuration.

### Everything below shipped in this release


**The founding→backlog path is now a complete, gated chain.** Previously `/org-found` designed the
org and stopped, and the only way to get task Issues was `/org-discover`, whose input is a role's
*aspiration gaps* — so nothing turned the RFP's must-haves into workable units, and setting up a new
org was a page of manual `export`s. Two new commands close both ends, and a new gate proves the middle.

### New: `/org-init` — the setup step
Creates the ledger/doctrine/conventions roots, installs the org spec files, writes `.envrc` (including
a detected `ORG_GITHUB_REPO`), ensures the backlog label vocabulary and the `develop` branch, then
lints the spec and runs the harness probe so a session can't believe it is guarded when it isn't.
Idempotent — safe to re-run to repair a half-set-up org. Designs nothing.

### New: `/org-decompose` — RFP/全体設計書 → atomic SPEC task Issues
The missing bridge between design and execution. Reads the approved `coverage-manifest.md` +
`ARCHITECTURE.md`, carves each must-have into *independently-completable* units (split where sibling
`owns` sets are disjoint; keep reciprocally-coupled work together), fills the full `template/SPEC.md`
structure into each Issue body, and hangs each under its objective as a native GitHub sub-issue.
Because the whole spec lives in the Issue — clone URL, literal setup/test commands, entry files, MUSTs
in EARS, seam contract, DoD command — a task can be claimed and started from **any** environment.
Uses the same deterministic `candidate_id` derivation as `/org-discover`, so re-running fills gaps
rather than duplicating the backlog. RFP-derived tasks are `source: mandate`; self-raised ones stay
with `/org-discover`.

### New tooth: `github_sync coverage-check` — the decomposition coverage gate
`/org-found`'s O10 lint proves each must-have has exactly one owning *contract* (design layer). This
proves each one reached at least one *task Issue* (backlog layer), matching the manifest's
`rfp_capability` against a `coverage_row:` trailer in each Issue body. A must-have that was designed
but never decomposed is silently unbuilt — the hardest gap to see — so it now exits 10 instead of
passing unnoticed. A paraphrased trailer is reported as an orphan (it would otherwise mask a real
gap); Issues with no trailer are a note, not a failure, since `/org-discover` items legitimately have
none. Eight tests cover the gate, including the closed-Issue and unparsable-manifest cases.

### Rule: the founding artifacts have FIXED filenames (docs/11 §0a)
`/org-found` now writes exactly `RFP.md`, `FEATURE-INVENTORY.md`, **`ARCHITECTURE.md` (the 全体設計書)**,
`coverage-manifest.md`, and `organization.yaml` — under those exact names, as a rule rather than a
convention. Downstream commands address them **by name**; a renamed artifact is an unfindable one, and
variant names break Level-1 reproducibility at its root. `ARCHITECTURE.md` is explicitly **not** an SDD
artifact: SDD's spec/plan/tasks live in the Issue hierarchy (§4b) and are per-objective/per-task, while
the 全体設計書 sits above them as the standing whole-system design — which is why it is a file while task
specs are not (a single whole-system design doesn't fragment; per-task spec files rot, docs/12 §6).

### New bar: unread-safe (docs/11 §4e) — the diff nobody reads must still be safe to merge
§4a asks *"can a stranger run this?"*; §4e asks *"is this safe to merge without anyone reading it?"* At
parallel-agent throughput no one reads every diff — not the CEO, not a reviewing agent, not the maker —
and a reviewer who cannot keep up does not announce it, they skim. So the defect classes only a careful
reader catches are made **unmergeable by machine** instead. `repro_lint` gained four teeth, checking
that the rejection layer is *configured* (running it is CI's job):

- **complexity-bounded** (implement) — a ceiling on function size / cyclomatic / cognitive complexity /
  nesting. The highest-value tooth: over-long nested functions are where unread defects hide, and
  appending to a working function is what an agent does when the alternative is decomposing.
- **type-escapes-closed** (implement) — strict typing on, `any` / `@ts-ignore` / non-null assertions
  banned. Open escape hatches make a type checker advisory; an agent pushed to turn a build green
  reaches for them, and the hole is invisible in an unread diff.
- **tests-present** (test) — tests are what *substitutes* for a reader; a green CI with no tests proves
  only that the code compiles.
- **dup-dead-code** (deploy) — jscpd/knip/ts-prune/vulture. Parallel makers re-solve each other's
  problems and orphan superseded code; neither shows up in any single diff. Report-only by default.

Language-appropriate (rubocop's `Metrics/MethodLength` satisfies the complexity bar; a repo with no
static type layer marks the type check `n/a`). The doctrine records the two operating rules the bar
depends on — **drain then ratchet** (a rule that is on and violated everywhere enforces nothing) and
**exceptions in the config with a reason**, never inline `eslint-disable` — and states plainly that this
does *not* replace the gate/skeptic: the mechanical layer clears everything a machine can decide so the
scarce different-lineage judgment is spent where it is irreplaceable.

### Human diff review is RETIRED — the Issue becomes the audit record (docs/11 §4f)
§4e removed the human from *reading* the diff; §4f takes the consequence to its end: **there is no human
review step.** No person reads the change before it merges. The mechanical bar, the gate, and the
skeptic are the entire judgment layer. That is defensible at fan-out scale — a reviewer who cannot keep
up does not announce it, they skim, and a skimmed review launders unread code as reviewed — but it
removes the **account** of why a change was allowed. So the trade is explicit: **review is retired;
recording is not optional.**

- **`github_sync decide`** (new) — records a judgment **with its reasoning** on the task Issue.
  Judgments now double-write, the way settled conventions already do: the ledger takes the
  tamper-evident receipt, the Issue takes the account — `--why` (what was weighed), `--evidence`
  (commands run and their real output, CI runs, `repro_lint` verdicts), `--alternatives` rejected,
  `--standard` applied, and `--risk` knowingly accepted. It **refuses a `--why` that merely restates
  the verdict** and refuses non-judgment event classes, so the slide back into a rubber stamp is closed
  at the tool. Every posted decision carries an explicit "no human reviewed this change" notice.
- **`github_sync log` enriched** — `--command` (verbatim, re-runnable), `--result` (**the real output,
  failures included**), `--files`, `--next-step`, `--blocked-by`. A log of only successes is a fiction,
  and the failed attempt is usually the most informative entry on the Issue. Backwards compatible: all
  new fields are optional.
- **The gate and skeptic now post their reasoning**, not just ledger verdicts. The skeptic must write
  *who this fails for and under what conditions* **even when the work survives** — a bare `survives` is
  worthless to whoever audits the merge later. The gate must record `--risk` honestly: admitting despite
  a known hole is a legitimate decision only if it is written down.
- **The logging bar in `/org-work` and `template/SPEC.md`**: log at every step that changed the world or
  changed the plan, including course changes with their cause (feeding `nearby_deaths`). The stated bar
  — *a stranger reading only the Issue can reconstruct what was built, what was tried and abandoned,
  what was run, what came back, and why it merged, without the ledger or the transcript.*
- **What this does not license** (stated in §4f so it cannot drift): the *judgment* layer stays — O6c's
  distinct-lineage rule matters **more** without a human backstop, since a puppet checker is now the
  only checker. Phases are still non-skippable. And the CEO's charter-tier decisions (founding,
  irreversible moves, scope) remain human — what is retired is diff review, not governance.

### Other
- `role-settings.yaml` is now bundled into the plugin template dir (`/org-init` scaffolds it).
- `template/SPEC.md` documents the `candidate_id:` / `coverage_row:` trailers, and now carries the §4e
  bar in its Verification section so makers configure it rather than discovering it at the gate.
- **`github_sync candidate-id`** — the deterministic id derivation moved out of each command's prose
  into the organ. The echoed one-liner it replaces lost its `\x1f` field separator to shell escaping,
  so different items collided onto one id and the second one's ledger append was silently swallowed as
  a "replay" — it never entered the backlog. Both `/org-decompose` and `/org-discover` now call the tool.
- `create`'s idempotency search now covers **closed** Issues: a delivered task is closed, so an
  open-only search re-minted every completed task on the documented re-run/repair path.
- `/org-init` no longer truncates `.envrc` (a repair run was wiping `ORG_GITHUB_REPO`, silently
  demoting a GitHub-backed org to ledger-only) and no longer reports "installed" for files it kept.
- `/org-found`'s lint now reads the **org's own** spec files, falling back to plugin templates only for
  what the org hasn't installed — it was validating pristine templates while the org ran on edited
  copies, so a `SET_ME` left in the real `constitution.yaml` could never be caught.
- `coverage-check` hardening: a table *following* the manifest no longer inherits its header (an
  EXCLUDE list was being read as must-haves, which would have made the org build the scope the CEO
  cut); bold/backticked trailers now match; and an `orgforge:mandate` task with no trailer now fails
  instead of passing as a note.

## 0.8.0

**orgforge is a plugin for standing up and running an AI-native IT business company** — not merely
"an organization." The company decides what to build as a business, builds through a forced
non-skippable SDLC, ships via CI/CD, operates under a reliability budget, navigates by DORA to the
moving bottleneck, and grows the system and the org together. This release re-scopes the whole
project to that definition, restructures the docs, and — most importantly — makes the process
**reproducible**: same org spec + RFP ⇒ same process, gates, contracts, and verification, and the
repositories the company builds clone-and-run the same for anyone.

### Docs — restructured into 4 Parts × 12 chapters (was 18 flat files)
- Consolidated the docs from 18 → 12 chapters, grouped into four Parts (Foundations / Design /
  Operate / North star) with a new `docs/README.md` map. The chapter skeleton is now stable: new
  material is added as a section inside a chapter, not as a new file. Merges: former operating-events
  + proxy-stack folded into **05 Operating a Running Company**; decomposition folded into **03**;
  manager-accountability folded into **09**; elastic-org folded into **02**. The S1 founding rehearsal
  moved to `demos/`.
- **THEORY §1b** — a new layer over the neutral organization definition: the org this template stands
  up is an IT business company, filling Organ 1 with a business telos and specializing Organs 2/4/6/7
  with the SDLC, CI/CD, reliability budget, and DORA. The AI-as-amplifier thesis is stated here.
- **docs/11 — The forced SDLC mold** (new chapter): the non-skippable phase chain
  (requirements→design→implement→test→integrate→deploy→operate), enforced by generalizing the `requires_prior`
  predicate from admission-gating to phase-gating. §0 states reproducibility as the deep purpose;
  §4a is the Level-2 reproducibility admission standard for the repos the org builds.

### Reproducibility & idempotency (the release's core)
- **SDLC phase gate (F1).** New ledger events `phase_started` / `phase_admitted`; `ledger.py`
  `REQUIRES_PRIOR` now enforces the phase order (a phase cannot start until its predecessor is
  admitted), so the same spec runs the same phases in the same order for every founder and run.
- **Idempotent ledger append (F3).** `ledger.py append --natural-key` no-ops a replay/retry of the
  same logical event, so exposure/cycle/WIP counts no longer drift with how many times a hook fired.
- **Spec-declared enforcement (F5).** Caps, budget window, iteration limits, and the seam gate now
  live in `constitution.yaml`'s `enforcement:` block (hash-chained, agent-unwritable), so every
  install of the same org enforces the SAME gates. `ORG_CAP_*` / `ORG_WINDOW` / `ORG_MAX_*` /
  `ORG_REQUIRE_SEAM` are demoted to DEV OVERRIDES. The iteration cap is now default-on.
- **Deterministic backlog (F4).** `candidate_id` is now a hash of (role, contract_ref, normalized
  gap), so the same RFP yields the same backlog; attention tie-breaks on it, not append order.
- **Idempotent projections (F2, F9).** `github_sync create` no-ops when an open Issue already matches;
  `conventions adopt` no-ops on an identical (scope, choice).
- **Real clock in the tick (F6).** `/org-tick` now uses the host UTC clock, not a frozen literal date
  and a zero counter, so missed-check detection depends on ledger state, not operator-passed args.
- **Founding coverage gate (F8).** New lint tooth **O10**: every declared deliverable must carry a
  non-empty acceptance standard, be owned by exactly one role, and have a checker distinct from its
  maker — so two foundings from the same RFP converge on the same contracts. `/org-found` now emits a
  coverage manifest.
- **Level-2 repo reproducibility (`tools/repro_lint.py`).** A deterministic gate checking a generated
  repo is clone-and-run reproducible: committed lockfile, pinned toolchain, one-command setup+test in
  a README, idempotent migrations, `.env.example`, and a CI workflow green from a clean clone. The
  **gate** and **maker** agent doctrines now require it.
- **DORA + reliability budget.** New ledger events `reliability_budget_checked` / `dora_snapshot`
  fold into docs/05 as operating instruments (error budget bounds deploy velocity; DORA four keys
  navigate to the moving bottleneck).

### SDD canonical form + branch model + integration phase (post-0.8.0 fold)
Deep-dived Spec-Driven Development (GitHub Spec Kit / AWS Kiro) and folded the canonical form in,
mapped onto the Issue hierarchy (no fragment `spec/plan/tasks` files — SSoT stays code + domain model):
- **SDD 3 layers → Issue hierarchy** (docs/11 §4b): objective Issue = **spec** (WHAT) + **plan** (HOW);
  task sub-issue = one **atomic task** (dep order, disjoint `owns` = the `[P]` parallel marker, entry
  files). Acceptance criteria now in **EARS** (WHEN/WHILE/IF/WHERE…SHALL).
- **Branch model + integration phase** (docs/11 §4c): feature branch per task (`feat/issue-N-slug` off
  `develop`) → merge to **`develop`** → a new **`integrate` phase** (the 7th) where the fanned-out
  siblings build+test **together** (green CI on `develop` = `integration_admitted`) → deploy is
  `develop`→`main`. The ledger now enforces `deploy` requires `integrate` (fan-out must fan back in).
  Owned by the supervising manager's A3, extended to cross-deliverable.
- **New github_sync commands:** `branch` (deterministic feature-branch name, Japanese-title safe) and
  `split-check` (shape warning if a task's `owns` spans territories or a dep is still open).
- **SPEC strengthened** for the third-party/no-context maker: Working context (repo/branch/setup-run/
  entry files), a runnable DoD command, a worked input→output example, actionable `depends_on`, a
  single-unit assertion, prior-deaths, and a Hand-back that targets `develop`.

### SSoT corrected — code + domain model, not the ledger
The ledger was wrongly called the SSoT. Corrected repo-wide: **SSoT = code + the domain model**
(conventions + org spec); the ledger is the **audit / requires_prior-enforcement / crash-safe-resume
record** (it holds the *receipt* of a decision, not the decision — which co-commits to code/conventions).
The GitHub Issue is the **main, terminal-independent work surface** (spec + work-log); a local ledger
is terminal-bound. `conventions` elevated to "the domain model". SPEC is the Issue structure, never a
`docs/spec/*.md` file (the fragment-Spec trap).

### Tests
- 144 passing (was 114): phase-gate (incl. integrate), ledger idempotency, spec-declared caps,
  `repro_lint` (incl. monorepo-CI), the O10 founding-coverage tooth, `github_sync` two-level Issues,
  work-log idempotency, deterministic branch naming, and `split-check` all have regression coverage.

## 0.6.0

Loop reliability — the failure modes a practitioner hits building an autonomous loop, checked against
the code and closed where the code fell short.

### Added
- **docs/10 — Loop reliability.** Why an unattended loop survives: a loop pass is a series system, so
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
- **docs/10 subagent-gating claim made honest.** The doc had asserted the hook "gates every subagent at
  every depth" as a plugin property; whether a subagent's tool call reaches `PreToolUse` is a *harness*
  property. The doc now states the plugin is correct-by-construction (verdict from the raw call + ledger,
  no inherited context) and requires a harness that fires the event for subagents — the docs/08 host
  contract, not a reimplementation.

## 0.7.2

Close "unattended ≠ unobservable" by delegating the escalation transport to the harness — the last
R0 replacement the audit found (loop→/loop and this notification transport were the two big ones).

### Added
- **Escalation reaches the user.** orgforge detects escalations but shipped no notify transport (R0 —
  the host delivers them); Claude Code *is* the host, so it now uses:
  - `/org-tick` sends a **PushNotification** on a genuine escalation only (a MISS, a tripped stall, a
    repeated death, an unproven rollback, a broken chain) — never on a healthy tick (fail-quiet).
  - `status.py redline` prints one line ONLY when the org is RED (silent when healthy), purpose-built
    for a persistent **Monitor** to push the moment a RED appears — so a RED never waits for the next
    tick. `/org-start` and SCHEDULER.md document arming it.

An R0 audit confirmed the rest is already delegated or correctly self-built: the drive is `/loop`; the
ledger (hash-chained audit spine), the doctrine/conventions admit-gate, the single-writer backlog, and
the judgment organs stay self-built — `memory`/`TaskList` lack the audit/gate/provenance those need.

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
  not silence (docs/10). Delegate the drive, keep the monitor.
- OS cron (`scheduler-install.sh`) demoted to the one case `/loop` can't cover: running 24/7 with no
  session open. For everyday attended/kept-open runs, the three `/loop`s are the whole drive.

## 0.7.0

The ideal-state build-out (docs/12): a six-opinion synthesis defined what orgforge is *for* — a
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
  (the docs/03 §6.5 tooth, now implemented; catches the implement-without-judge case O8 misses).
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
  to the OS-cron install for a genuinely 24/7 org (docs/08 §4 names "a cron" first for this reason).

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
  an off-ranking mandate gets no floor (a visible drift signal). (docs/09)
- **The PM loop** (`/org-work <role>`). Select from the backlog by situated attention, delegate the
  selected items to subordinates **in parallel** (one `Task` each, where the split is genuine), record
  `cycle_completed`. Parallelism is a judgment, not a mandate.
- **The discovery loop** (`/org-discover <role>`). Problemistic search raises `source: self` backlog
  items from aspiration gaps, scoped to the role's own domain; append-only, fail-quiet when there is
  no gap. (docs/09)
- **Decomposition doctrine** (`docs/03`, projected into `ROLE.md`). How a manager splits an assignment,
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
  and pools domain knowledge in the boss instead of the field role that owns it (docs/07 §1.1, docs/03
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
  fires the doctrine-injection hook automatically. (docs/06 §2.1)
- **Doctrine remap for refounding** (`doctrine.py remap`). When roles are renamed / split /
  merged, every live claim follows as an asset; a claim that maps to nothing **blocks** the
  refound rather than being silently lost. (docs/05 §4.4, docs/06 §2.2)
- **Spawn seam-contract gate** (`ORG_REQUIRE_SEAM=1`). An `Agent`/`Task` spawn is blocked unless
  its prompt carries a seam contract or an explicit `INDEPENDENT:` declaration — recursive splits
  can't drift on an un-owned interface. (docs/06 §2.1.1)
- **Silence-consent gate** (`guardrails.py consent`). A reversible backlog action rides the
  delegated tier (silence = consent, proceeds); an irreversible one (deploy/spend/destroy/…) holds
  for an explicit human ack. (docs/05 §2.1)
- **STALE-REFERENCE auto-trigger** (`guardrails.py staleref --auto`). Derives the trigger event +
  bound roles from the ledger's latest reference change, so a central re-prioritization propagates
  to departments without hand-fed arguments. (docs/05 §5.1.3, docs/09 §3.1)
- **DEPENDENCY-STALL dependency edges** (`reconcile.py stall`). Reads `work_claimed.depends_on`
  edges to report who a blocked role awaits, which downstream roles are impacted, and the
  lowest-common-owner to route to — instead of cycle timing alone. (docs/05 §5.2)
- **QUICKSTART.md** — install, the one required setting, guardrail tuning, and a verified
  "prove it blocks" snippet.

### Changed
- **Blast-radius cap now meters irreversibility, not activity.** The old flat "every file write
  costs 1 against a cap of 3" blocked a normal build at its 4th file. Now: creating a new file
  (decided by a filesystem stat), reads, and build tooling (`npm`, `pytest`, `git commit`) are
  **not metered**; the scarce low caps are reserved for `destructive_ops` (scope-weighted —
  `rm -rf` = 3), `external_writes`, `infra_changes`; overwriting an existing file is
  `file_mutations` (high cap 200). A 300-file build proceeds; `rm -rf` still hard-stops. New caps
  are tunable via `ORG_CAP_*`. (docs/05 §2.1)

### Docs
- Operating-phase flow integrated into existing homes (no new file): the two-level backlog
  (org-wide ranking + per-dept next-task) in docs/09 §3.1; the registrar as org-wide priority
  owner in docs/05 §2.6; reversible-vs-irreversible consent in docs/05 §2.1.
- New `examples/`: `doctrine-scoping` (per-role brains that narrow + refound remap), and
  `seam-descent-run` (an org self-driving scoped hand-offs end to end).

Every change ships with regression tests (76 green) and passes the payload-schema drift guard.

## 0.1.0

Initial template: the articulated organization as installable Claude Code features — PreToolUse
guardrails that block, SessionStart doctrine injection, per-department subagents, organ tools
(ledger, guardrails, doctrine, reconcile, resource, attention, learning), and organ slash-commands.
Verified on the real CLI (v2.1.211).
