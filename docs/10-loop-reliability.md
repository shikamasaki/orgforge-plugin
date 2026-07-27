# 10 — Loop reliability: fewer decisions, explicit state, staged trust

*Part III · Operate — see [the four-part map](README.md).*

docs/05 named what a running org checks and when. docs/09/15 said how a unit picks and splits work.
None of them addressed the property that decides whether an *unattended* loop survives contact with
reality: **a loop is a series system, and a series of probabilistic steps fails compoundingly.** This
document is the reliability discipline for the operating loop — why the goal is *fewer decision points*,
not *smarter ones*; why loop state must be **explicit**, not held in an agent's context; and why trust
is **staged**, read-only before destructive.

It is the org-level answer to the "loop engineering / software factory" problem the industry is now
naming (see docs/sources.md §16): the hard part of an autonomous loop is not the model's per-step
intelligence — it is the *architecture around the loop* that keeps a hundred consecutive steps from
compounding into failure.

## §1 The compound-failure law — a loop is a series system

A run of the loop succeeds only if **every** decision in it succeeds. That is a **series (non-redundant)
reliability system** (the classical result: the reliability of a series system is the *product* of its
parts' reliabilities — Barlow & Proschan, *Mathematical Theory of Reliability*, 1965). So per-step
accuracy `p` over `n` independent decision points gives whole-loop success `p^n`, which collapses fast:

| decisions in one loop pass (`n`) | whole-pass success at `p = 0.95` |
|---|---|
| 1 | 95% |
| 3 | 86% |
| 10 | **60%** |
| 20 | 36% |

The 10-decisions → ~60% figure is the load-bearing intuition (y-hirakaw, docs/sources.md §16): *even at
95% per step*, ten steps in a row is a coin-flip. The consequence inverts the naive instinct:

> **Reducing the number of decisions moves the number more than raising per-decision accuracy does.**
> Going from `n=10` to `n=5` at `p=0.95` lifts a pass from 60% to 77% — a bigger gain than lifting every
> step from 0.95 to 0.97 at `n=10` (60% → 74%). Cut decisions first; sharpen steps second.

**Design rules that follow:**
1. **Count the decisions in one loop pass, and drive the count down.** Every place the agent must *judge*
   (not execute a fixed step) is a factor in the product. Collapse judgments: pre-decide with a fixed
   rule where a rule suffices, batch several small judgments into one, remove steps that don't earn their
   risk.
2. **Prefer one bigger reliable step to three small flaky ones.** This is the reliability face of docs/03
   §2.4 (split only when the parallelism beats the coordination cost) and docs/09's "keep tightly-coupled
   work single-threaded": each extra sub-task is another factor in `p^n`, so fan out only when the pieces
   are genuinely independent — needless subdivision multiplies failure, not throughput.
3. **Put the load-bearing constraints in the enforcement layer, not the request layer** (§2) — a
   deterministic gate is `p = 1.0` and drops out of the product; a "please remember to…" is another `<1`
   factor.

## §2 Two layers: request (probabilistic) vs enforcement (deterministic)

Every control in the loop lives in one of two layers, and putting a control in the wrong one is the most
common way a loop silently degrades:

- **The request layer** — skills, doctrine, prompts, profile instructions. **Probabilistic**: read and
  usually followed, but each is a `<1` factor in the compound product, and *a subagent does not inherit
  the parent's skill/prompt context*, so a "the agent was told to…" control is weakest exactly where the
  loop fans out.
- **The enforcement layer** — the PreToolUse hook, the lint, permissions, wrapper scripts.
  **Deterministic**: it blocks at the tool boundary regardless of what any prompt said, and it applies to
  *every* agent including spawned children, because it gates the tool call, not the conversation.

**The rule: a constraint that must not be violated goes in the enforcement layer; a preference that should
usually be honored goes in the request layer.** This is exactly the division docs already draws —
guardrails/lint *block* (docs/05 §2, docs/08), doctrine/conventions *guide* (docs/06, docs/05) — stated
here as a reliability principle. It is also why the org's hard guarantees (blast-radius cap, no
doctrine-capture, seam-on-spawn) are hooks and lint teeth, **not** lines in a role's profile: a profile
line is a probabilistic factor, a hook is `p = 1.0`.

Corollary (the subagent trap): because a child agent does not inherit the parent's prompt context, any
control you need to hold across a fan-out **must** be in the enforcement layer. A parent that "tells" its
children a rule has not enforced it; only a hook that fires on the child's *own* tool call enforces it.
The org's `org_hook.py` is written to make this possible: its verdict is derived purely from the raw tool
call plus the ledger — it inspects no nesting depth and no inherited context, so it returns the same
verdict for a spawned child's call as for a top-level one. **The caveat is honest:** whether the child's
tool call actually reaches the hook is a property of the *harness* (does Claude Code fire `PreToolUse`
for a subagent's calls?), not of this plugin. The plugin is correct-by-construction if the harness fires
the event for every agent; on a harness that does not, the guarantee degrades to the top level. Choose a
harness that gates subagent tool calls when the org fans out — this is the same host-selection contract
as docs/08 (the plugin requires the right host; it does not reimplement the host).

## §3 State is explicit, not held in context

An unattended loop cannot keep its state in an agent's working memory — a context wipe, a fresh session,
or a scheduled wake starts blank. So **the loop's state lives in the ledger, as named, inspectable
facts**, and the human's steering is compressed to setting one of those facts:

- Each backlog item carries an explicit **stage** and a **checkpoint** (docs/09: `candidate_submitted` →
  `cycle_started` → `progress_recorded {fraction, next_step, blocked_by}` → `cycle_completed`), so at any
  moment "what stage is this in, and what's the next step" is a lookup, not a memory
  (`ledger.py view work_in_progress`), and a resumed session continues from `next_step` rather than
  restarting. This is the industry's "state is labels; the start switch is a label" (y-hirakaw,
  §sources) rendered on the ledger: the org's equivalent of a `ready` / `needs-human` / `blocked` label
  is an explicit ledger stage, and "the human's instruction compressed to one label" is the human setting
  a `source: mandate` item or a stage.
- Because each stage is explicit and independent, the loop's phases can run on **independent cadences**
  and still compose — the health tick, the PM cycle, and discovery each fire on their own schedule and
  coordinate only through the shared, stage-tagged backlog (docs/05 §5.0's reconcile-by-exception), never
  by holding shared state in a live context. Explicit state is what lets the phases decouple without
  drifting.

## §4 Stage the trust: read-only before destructive; and a hard floor under the budget

A loop earns the right to touch assets. Stand up the **read-only, reporting** shape first — a cadence
that ticks, reads the ledger, computes checks, and surfaces/notifies, touching nothing irreversible — and
only once its start/stop/failure-handling is proven, extend it to asset-touching cycles. The org ships
this staging: `/org-tick` is the read-only health cycle (surfaces due/missed checks; acts on nothing),
and it is the safe first cadence to schedule; `/org-work` (which delegates and mutates) is the later,
asset-touching stage, bounded by the blast-radius cap. Bring a new org up read-only-first: schedule the
tick, watch it run clean, then turn on the acting cycles.

**Two kinds of destructive limit, because they fail differently.** The blast-radius cap is a *budget* —
it bounds the SUM of irreversible acts over a window ("death by a thousand cuts"), and its default is
sized for a real day's work, so a single ordinary destructive op passes. But some commands are
unrecoverable in ONE execution (`rm -rf /`, `mkfs`, `dd` to a raw disk, a fork bomb) — a budget cannot
stop those, because the first one already lost. So the enforcement layer has a **catastrophic denylist**
(`org_hook.py`, `_catastrophic_reason`) that hard-blocks that narrow class **regardless of budget and
even with no ledger configured** — a fresh org is never one command from catastrophe. This is the
deterministic per-command block the practitioner wanted (docs/sources.md §16); the cap handles the
ordinary irreversible ops as a rate limit, the denylist handles the one-shot catastrophes as an absolute
floor. The denylist is deliberately narrow (root/home/whole-disk forms only) so it never fights the
common `rm -rf ./build` / `rm -rf node_modules` of daily work.

## §5 The verification ladder (why §1's product doesn't just decay to zero)

Compound failure would be fatal if nothing caught the failures — but the loop is not open-loop. Each pass
is checked by a ladder of increasing cost and independence, so a bad step is caught and retried rather
than shipped, which is what makes a long loop survivable despite `p^n`:

1. **Mechanical gates** — tests, lint, type-checks, `org_lint.py` (deterministic, `p≈1`, cheap).
2. **Agent self-check** — the maker runs/verifies its own output before handing off (docs/06 §2.1.1).
3. **Independent verification** — a *separate* context reviews: the gate/skeptic (docs/03 §3, docs/05),
   never the maker signing off its own positive.
4. **Human judgment** — requirements, UX, high-risk/irreversible calls, release (constitution's
   charter/irreversible tiers).

Put each check at the lowest rung that can decide it (a mechanical gate over an agent opinion, an agent
opinion over a human page), so the human sees only the essential exception (docs/05 §5.0). The ladder is
why "fewer decisions" (§1) and "not zero verification" coexist: cut the decision *count*, but keep every
surviving decision *checked* — cheaply and independently.

*Status: this document is a design discipline synthesizing a classical reliability result (series-system
reliability, Barlow & Proschan 1965) with the current loop-engineering / software-factory practice
(docs/sources.md §16, r_kaga and y-hirakaw). The compound-failure law and the request-vs-enforcement
split are already realized in this repo (the hook/lint enforcement layer, the explicit ledger stages of
docs/09, the read-only `/org-tick` vs acting `/org-work` staging); this doc states the principle the
existing mechanisms follow, and the "count and cut the decisions per pass" rule is guidance for authoring
loops, to be verified against a running system.*
