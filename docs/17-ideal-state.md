# 17 — The ideal state: what orgforge is for, and the gap to it

The docs before this one each argue a part. This one steps back and asks the question a five-perspective
review (loop-reliability, factory-mechanics, multi-agent-safety, conceptual-genealogy, user-experience)
plus a practitioner's field report converged on: **given why the governing concepts were invented, what
is the one thing orgforge is for — and where does it fall short of being that?** It is the north star the
other docs' mechanisms serve, and the honest ledger of the distance still to travel.

## §1 The four concepts collapse into one act

orgforge lives at the convergence of four ideas, each invented against a specific pain:

- **Software Factory** (Greenfield & Short 2003; the 2025-26 AI revival) — against artisanal,
  non-repeatable, non-reused bespoke software. Load-bearing idea: *industrialize via reusable,
  model-driven assembly under guardrails, with human judgment moved upstream.* Its named failure mode is
  **comprehension debt** — run the factory for months with no human reading output and green tests hide
  eroding understanding (Osmani).
- **Harness engineering** (Anthropic, "Building Effective Agents") — against the belief that a raw model
  is an agent. Load-bearing idea: *the scaffold (loop, tools, memory, permissions, context) is the
  product; the model is a swappable part.* Corollary: don't rebuild the substrate — an existing coding
  agent already is one.
- **Loop engineering** (r_kaga, y-hirakaw; docs/sources.md §16) — against "an agent that runs once."
  Load-bearing idea: *the operation loop and its verification are the real product* — start conditions,
  verification gates, budget caps, no-progress detection, crash-safe continuity. The human's role shifts
  from giving task instructions to **designing and supervising the loop**.
- **SDD / Spec-Driven Development** (Spec Kit, Kiro; "the spec is the program") — against non-reproducible
  vibe-coding that loses intent. Load-bearing idea: *externalize intent as a durable, machine-actionable
  spec that is the source of truth; code is a projection of it, regenerated, never hand-forked.*

They are four vocabularies for one principle:

> **Externalize the tacit as machine-actionable source (SDD); make the verifying loop, not the one-shot
> agent, the product (loop engineering); build it on the substrate the industry already engineered rather
> than re-forging it (harness engineering); and industrialize the result as reusable, model-driven
> assembly under upstream human guardrails (factory).**

And all four independently arrive at one governing constraint: **autonomy is bounded by verifiability.**
SDD validates against the spec; loop engineering grants autonomy only up to cheap, un-gameable
verification ("back-pressure"); the factory moves judgment upstream or accrues comprehension debt; harness
engineering spends more on the check/tool design than on the prompt. This is orgforge's true center of
gravity (Organ 6's risk-calibrated maker/checker, Organ 2's verification-bandwidth bound, the lint), and
it is **already correct**.

## §2 The ideal, in one sentence

> **orgforge is a spec-driven factory for autonomous work: the spec is the organization, the product is a
> verifying loop that runs unattended, the substrate is borrowed, and the yield is a compounding
> context base — reusable parts, doctrine, and an inferable codebase — not a pile of outputs.**

The spec is the org; the loop is the product; the harness is borrowed; verification is the governor; the
compounding context base is the yield.

## §3 The amplifier constraint — the practitioner's correction, adopted as the top-level bound

A field report (docs/sources.md §16, the AI-DLC practitioner) supplies the constraint that ranks above the
mechanics: **AI is an amplifier (DORA 2025) — it amplifies good process and bad process equally.** Three
consequences bind orgforge's ideal:

1. **The bottleneck does not vanish; it moves** (Theory of Constraints). Making coding faster moved the
   bottleneck to review, test, and upstream design. An ideal orgforge optimizes the *whole* lifecycle's
   throughput, not the coding fraction (25-35% of it) — which is exactly why its human-judgment rung sits
   on requirements/architecture (upstream), and its verification ladder sits on review (the new
   bottleneck), not on generation.
2. **The root cause of bad output is context absence, not prompt quality.** What is missing is structured,
   team-specific context (design policy, domain rules, consistency) the agent can always reference. "Bad
   design gets mass-produced 10×." An ideal orgforge therefore treats **building and compounding the
   context base as its primary work**, not a side effect — because precise autonomy over an absent
   context base only amplifies ambiguity.
3. **Context must accumulate as a by-product of normal work, enforced by mechanism, not by a separate
   task** (else it is deferred and rots). The rule-consistency check belongs in the loop's own gate (the
   PreToolUse hook / lint), not in human attention. And the durable source of truth is the **inferable
   artifact** (for the practitioner, code; for orgforge, the org spec + the ledger), *not* a pile of
   task-scoped Specs — a hundred fragment-Specs never become a system-wide coherent context, and their
   maintenance cost is unsustainable. orgforge already sits on the right side of this: its SDD spec is the
   *producer* (the organization), a small coherent set of files, not per-task Specs — so it escapes the
   fragment trap by construction. The open question §5 raises is whether its doctrine/ledger context
   actually accumulates *as a by-product of work*, or as a separate act that gets deferred.

## §4 Where orgforge already is the ideal (and is ahead of the field)

Stated plainly so the gap in §5 is not mistaken for a weak foundation:

- **Deeply SDD-native.** The YAML files are the canonical spec; `org_lint.py` is a *compiler* that
  rejects an internally-contradictory org (a checker sharing lineage with its maker, a pack smuggling an
  ungranted view, a skeptic sharing the gate's model family). A spec you can lint for contradiction is
  more rigorously spec-driven than Spec Kit's Markdown.
- **Correct harness engineering.** R0 (run on an existing harness; ship no runtime) is the anti-MetaGPT
  bet: one neutral PreToolUse hook blocks the same dangerous call on Claude Code and Codex.
- **Verification structure ahead of the research.** Independent, deploy-path-mandatory adversarial review
  (the ledger makes `result_deployed` require a prior `survives`), on a **decorrelated model family**
  (the anti-monoculture lint) — the research's "adversarial verifier caught 96.4% of injected errors" and
  "same model for plan+verify is a monoculture," both already enforced.
- **Single-agent by default; the compound-failure law stated.** docs/14/15/16 keep coupled work
  single-threaded and treat `p^n` as the reason to cut decision count — resisting the multi-agent hype the
  research shows is often *worse* (17× error amplification for independent agents).
- **Explicit resumable state, blast-radius cap, catastrophic denylist, missed-tick dead-man's switch** —
  all real and verified.

## §5 The gap — three layers, ordered

The distance to the ideal is concrete and enumerable. It is not a foundation problem; it is that
orgforge's strongest guarantees are *enforced* while its drift/runaway/context-compounding guarantees
still live in docs, opt-in flags, and un-run demonstrations.

### Layer 1 — Close the self-contradictions (orgforge violating its own docs/16 rule)

The docs/16 rule is: *must-not-violate constraints live in the enforcement layer (deterministic, p=1.0),
not the request layer (probabilistic).* These five are where orgforge breaks its own rule:

1. **Prevent concurrent-write drift, don't detect it post-hoc.** The seam/independence spawn gate is
   opt-in (`ORG_REQUIRE_SEAM` off by default); collisions are found by a scan (`reconcile.py collision`)
   that fires only when called. Make the gate default-on when the org fans out, and have it reject a spawn
   whose declared `owns` set intersects a live sibling claim — a p=1.0 precondition, not a scan. *(The
   research's load-bearing "single-writer ownership"; the multi-agent lens's #1 gap.)*
2. **Enforce iteration/token/spend caps in the hook.** `max_iterations` and `context_budget_tokens` are
   request-layer data in `role-settings.yaml`; nothing caps loop cycles or spend at the tool boundary. A
   reversible read-think-edit loop is charged nothing and never trips ("endless file-reading loop," 17%
   of long-horizon failures). Kill at "$3-5, not $180."
3. **Circuit-breaker on non-progress.** `progress_recorded {fraction, next_step}` is written but never
   read to detect a stalled fraction or an identical output twice (AgentMesh's break-on-identical-output).
   Add a breaker over the stream the ledger already has.
4. **Implement the docs/15 §5 tooth.** The doc specifies "a mechanistic coordinator produces no domain
   deliverable" and admits it is *not yet implemented*. O8 catches implement+judge; it does not catch a
   coordinator that merely implements a domain deliverable. Ship the tooth.
5. **Harness-capability probe.** The whole tool-layer guarantee silently degrades if the harness does not
   fire PreToolUse for subagents. Ship a founding-time probe that spawns a trivial subagent, has it attempt
   a gated call, and refuses to certify "fan-out safe" if the hook didn't fire.

### Layer 2 — Become a factory, not a workshop (the amplifier + factory gaps)

6. **An external-signal front door.** The factory activates by a human running a command; there is no
   ingestion of an issue tracker / bug report / webhook that mints a labeled backlog item without a
   prompt. Add a triage stage: external signal → `candidate_submitted`, the human's input compressed to
   one label (the articles' whole premise, acknowledged in docs but unbuilt).
7. **Make reuse fire.** `reusable_modules` / `parts_inventory` are passive views; nothing makes a worker
   consult the inventory and reuse a part before authoring from scratch. Add a reuse-first discipline to
   the worker contracts — "check the inventory; don't rebuild what exists." (SPLE's proactive planned
   reuse; the factory lens's "library built, nobody imports it.")
8. **Accumulate context as a by-product, by mechanism.** Adopt the practitioner's principle: rule/doctrine
   updates ride the same unit of work as the change that motivated them (the co-commit discipline), and
   the loop's own gate checks rule-consistency — so the context base grows without a separate,
   deferrable task. Verify orgforge's doctrine/ledger accretion actually works this way; where it is a
   separate act, fold it into the work cycle.

### Layer 3 — Contract the user surface (unattended must not mean unobservable)

9. **Collapse the surface to the user's outcomes.** Seven commands mixing user-verbs and internal organs,
   ~15 `ORG_*` env vars, a hand-run guardrail proof, three "front doors" with drifting version strings.
   The ideal user surface: **one intent verb (`found`), one steering signal (feed the backlog / a
   label), one run toggle, one status view (green/amber/red), and one escalation channel that actually
   reaches the user.** Demote the metabolism (`work`/`discover`/`tick`/`resume`) and every tuning arg to
   internal, drill-into-on-curiosity detail. Move caps/cadences into the reviewable founding page as org
   policy in plain language, not env exports. And **unattended requires a push/inbox** — a detected stall
   that lands only in `cron.log` is an exception queue that never rings.

## §5.5 The heart, and what "most important" means

The layers of §5 are ordered by dependency (a runaway loop must be bounded before anything is loaded onto
it). But the **purpose** they serve — the one thing orgforge exists to do — is narrower and must not be
lost in the gap list:

> **Split work, run it independently and unattended, accumulate the learning from failures and
> exploration, and use that accumulated learning to raise the team's output quality over time.**

Three things are therefore *most important*, and they are co-equal:

1. **Loop engineering works** — the self-running loop does not drift or run away (all of Layer 1). This is
   the floor: without it, the other two load failure onto an unstable base.
2. **Failure and exploration learning is actually used** — not merely recorded. A death (a rejected
   candidate, a failed experiment) must feed forward so the *next* cycle or worker does not repeat it, and
   an exploration win must enter the reusable base so it is not re-derived. Recording without feed-forward
   is the "library built, nobody imports it" failure (Layer 2, items 7-8) applied to *lessons*, and it is
   the exact mechanism by which "team output quality rises over time" — or fails to.
3. **Anyone can use it** — the README and the surface are coherent enough that a new user gets a running,
   observable org without becoming a systems operator (Layer 3).

And one property spans all three because orgforge is *operated continuously, not founded once*:

**The SSoT and the domain model must GROW during operation.** The org spec (the SSoT) and its domain model
— ubiquitous language, responsibility boundaries — are not static founding artifacts. As the org runs,
they must be *refined as a by-product of the work* (the co-commit discipline of §3.3), so the codebase's
and the org's **inferability rises over time**. This is the amplifier constraint (§3) made dynamic: an org
that runs for months without its context base growing amplifies a *fixed* ambiguity forever; an org whose
domain model sharpens each cycle amplifies an *improving* clarity. A living SSoT is the difference between
a factory that compounds and one that merely repeats.

## §6 What NOT to build (every lens agreed)

- **Do not default to parallel multi-agent code-writing.** 17× error amplification independent vs 4.4×
  centralized; single-agent often wins; Cognition recommends single-threaded for production. Fan out only
  for genuinely-independent, pooled work; the burden of proof is on the split. Do not let "prefer
  fine-grained decomposition" drift into default fan-out.
- **Do not ship a scheduler / long-lived runtime.** R0 is correct. Breakers, leases, caps must be *pure
  functions over the ledger* invoked by the host — never a stateful supervisor daemon that leaks org
  state outside the ledger.
- **Do not force decomposition quality through a hook.** A hook checks *shape* (a seam contract is
  present); *sense* (is the split good) stays with the skeptic. Blurring this makes a false p=1.0.
- **Do not fix drift by handing children the full parent transcript.** Fat context dilutes instruction
  density (the Goldilocks dilemma) exactly where the child is thin. The seam contract, not the transcript,
  is the handoff.
- **Do not add correlated verifiers.** Five reviewers on one base model is one verifier with extra cost.
  Decorrelation, not count, buys the catch rate.
- **Do not measure the factory by items-drained-from-backlog.** That is the comprehension-debt trap
  (green tests pass, understanding erodes). Measure verified, comprehended, value-bearing outcomes —
  keep human judgment upstream (telos, admission standard), not bolted on at the end.
- **Do not make the SDD Spec the SSoT.** Per-task Specs are fragments; they never form a system-wide
  coherent context and their maintenance cost is unsustainable. The durable source is the *inferable*
  artifact — the org spec + the ledger — with task-Specs used as disposable prompts.

## §7 The honest status

orgforge is **genuinely the SDD + harness convergence** — the lint and the shared hook contract are too
load-bearing for "organization theory wearing the others loosely" to stick. It is **still-becoming the
loop + factory convergence**: loop-engineered by declaration but demonstrated only at n=1 (docs/10; S2-S6
— scale, on-time delivery, unit economics, unattended 24-hour operation — remain to be shown), and
factory-shaped but not yet operated long enough to have met the comprehension-debt failure the factory
concept exists to warn against. The theory has, honestly, outrun the operation. The danger to guard
against is the one Organ 1 already names and the factory lineage confirms: **mistaking the elegance of the
chart for the value of the product.** Every organ and lint tooth is currently richer than the single
demonstrated run. Closing Layer 1 (stop violating its own enforcement rule), then Layer 2 (become a
context-compounding factory, per the amplifier constraint), then Layer 3 (contract the surface so a human
can actually run and observe it), is the path from *specified-and-linted* to *lived*.

*Status: this is a design north-star synthesizing a five-perspective internal review with an external
practitioner field report (docs/sources.md §16). It states the ideal and the enumerated gap; the Layer-1
items are implementable as pure functions over the existing ledger wired into `org_hook.py`/`org_lint.py`
without violating R0. Layers 2-3 are larger and partly reframe the product (factory intake, reuse-first,
surface contraction). Nothing here is yet built beyond what §4 credits as already present; this doc is the
target the subsequent work is measured against, and the amplifier constraint (§3) is its top-level bound.*
