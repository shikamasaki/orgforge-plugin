# 11 — Operating events: what a 24/7 unattended org needs beyond the founding shape

The seven organs (THEORY.md) articulate the org's *anatomy*. This document articulates its
**operating events** — the recurring things that must happen while it runs unattended, which
a human company handles with meetings, reviews, and standing rituals. The requirement that
started this: *"put in something like 1-on-1s, team meetings, an exec review."* The discipline
applied: **name each by its essence — the failure it prevents and the information it moves —
not by the human ritual it resembles.** A ritual borrowed by name imports the human latency
and synchrony that an async AI org exists to shed.

## §0 The governing decision: reconcile by exception, never stop to meet

A human meeting pays a real cost — it stops everyone's work to synchronize — because human
information is otherwise trapped in people's heads. **That premise does not hold for an AI
org.** Every role's work product is already in the ledger (Organ 5); peers can read it
asynchronously. So the part of a meeting that survives is only *reconciliation* — checking
outputs against each other — and the part that dies is *co-presence*.

The fixed rule for every operating event below:

> **Default silent (fail-quiet). Compute the check; if outputs are consistent, emit nothing
> that reaches a human. Escalate only the exception, and only as far up as needed — lateral
> self-heal first, the CEO (the main agent) last.**

This is the same decision line as Organ 6, applied to *running* instead of *founding*: the
human decides only the essential exception; everything consistent runs delegated and
unattended. An event that pages the human on the happy path has reintroduced the meeting.

## §1 The meetings dissolve — they were three directions of one primitive

Decomposed honestly, 1-on-1 / team-sync / exec-review are **not three events and not one new
organ.** Each is one *direction* of a single primitive — *detect divergence between what a
role is doing and a reference it must stay consistent with* — and each direction routes to an
organ the repo **already owns**:

| Ritual | Essence (direction) | Where it already lives | Net-new? |
|---|---|---|---|
| 1-on-1 | vertical: a subordinate's output vs the superior's intent | the **skeptic/gate** already check output-against-norm (Organ 6) | only the *timing* win — re-check the instant the reference moves — which is **STALE-REFERENCE** (§2.3) |
| exec-review | whole-org: local optima vs the global optimum | a **wide-scope sensor** → MOVE → approval-queue → digest (Organs 6/7), against a **priority ranking** reference | no new organ; the ranking is the one missing reference (§3) |
| team-sync | horizontal: peer vs peer, *in flight* | **nothing** — the gate sees finished outputs, doctrine is external, the digest reports upward | **yes** — this is the only genuinely new information flow (§2.4) |

So there is no "meeting organ" to build. Two of the three directions are existing organs; the
third — **lateral, in-flight reconciliation between peers** — is the real gap, and it is
*narrower* than "reconciliation": it is specifically the horizontal seam no other organ watches.

## §2 The load-bearing safety events (running code: `tools/guardrails.py`)

These are the events an org running all night, touching real assets, with the human asleep,
cannot be safe without — and which no existing organ covered. Each is a **pure function over
the ledger** ([`tools/guardrails.py`](../tools/guardrails.py)); it ships no scheduler (R0) —
a host-run agent calls it at the act or on a cadence and ledgers the verdict. Each returns
exit `0` on the silent path and `10` when the exception must surface, so a host script branches
on it. The three were the top of a broader discovery set (§4); they are the ones with running
code because they are the ones safety most depends on.

### §2.1 BLAST-RADIUS-CAP — the aggregate the approval queue can't see

**Failure prevented:** death by a thousand approved cuts. The approval queue (Organ 6) gates by
action *class* — is this kind of action allowed? — but nothing sums the cumulative *magnitude*
of many individually-fine actions in one unattended window. A hundred small, in-scope,
reversible real-asset writes can drain a budget or mutate a hundred records overnight while each
one passes.

**What it does:** projects committed exposure in the window for a dimension (spend / external
writes / records / api-cost) from prior `exposure_budget_checked` events, and **blocks** — not
merely annotates — when `committed + requested > cap`. This is the one guardrail that stops an
action rather than recording it; a held action enqueues to the approval queue.
`guardrails.py cap` verified: two acts under an aggregate cap of 1000 pass silently (300, then
+400 = 700); the third (+500 → 1200) is HELD (exit 10).

**Ledger event:** `exposure_budget_checked {window_id, dimension, committed_so_far,
delta_requested, cap, actor_role, decision(allow|hold), caused_by_event}`.
**Fire:** at every act touching a real asset (not a cadence). **Escalate:** only on `hold`.

### §2.2 STATE-RECONCILED — the ledger is belief, not ground truth

**Failure prevented:** every downstream decision resting on a silent lie. The ledger is the
org's *belief* about the world; real assets live in external systems. A half-applied write, an
unauthored external mutation, or a missed webhook makes the ledger's asserted state diverge from
reality — and the anomaly sensor watches event *streams*, not *asserted-state vs ground-truth*.

**What it does:** diffs an external ground-truth snapshot (passed in — the tool does **no
network**; taking the snapshot is the calling agent's job) against the ledger's asserted value.
Silent when they match; escalates on drift; **trips the halt path** (rather than waiting for the
CEO) when drift exceeds a magnitude threshold, because a large silent divergence means every
decision since the last clean reconciliation may be wrong. `guardrails.py reconcile` verified:
700==700 is a silent breadcrumb; 700 vs 650 escalates; 700 vs 100 (magnitude 600 > halt 200)
trips halt.

**Ledger event:** `state_reconciled {domain, expected_value, observed_value, drift, magnitude,
unaccounted_events[]}`.
**Fire:** cadence (e.g. hourly + pre-dawn) or after a large `exposure_budget_checked`.
**Escalate:** on drift; halt beyond the magnitude threshold.

### §2.3 STALE-REFERENCE — the inverse of fail-quiet

**Failure prevented:** the failure mode fail-quiet *creates*. In a silence-is-consent org, a
role that has gone quiet against a reference that has **moved** (a superseded mandate, a revoked
scope, freshly-admitted doctrine) is indistinguishable from a role that is silently fine.
Nothing else can tell dormant-*wrong* from dormant-*right*. This is the vertical 1-on-1's real
residue: not "have a check-in," but "the instant the reference moves, re-check who's bound to it."

**What it does:** given a reference-changing trigger event and the roles bound to that reference,
lists those bound roles that have **not** re-derived (produced a cycle) since the trigger. Silent
when all current; on the first finding it **nudges self-re-derivation** (no CEO traffic);
escalates only a role still stale past a cycle threshold — genuinely stuck, not merely quiet.
`guardrails.py staleref` verified: a bound role 1 cycle stale gets a silent nudge; still stale
after 5 cycles (> threshold 3) escalates as dormant-wrong.

**Ledger event:** `reference.staleness_checked {trigger_event, bound_roles, stale_roles,
silent_duration_per_role, result(all_current|stale_found)}`.
**Fire:** event-triggered by any reference change (doctrine admitted, charter edit, scope
change, dept activate/deactivate). **Escalate:** only a role stuck past threshold.

### §2.4 Lateral reconciliation — the only net-new *information flow* (running code: `tools/reconcile.py`)

The horizontal team-sync residue. It splits by timing into three siblings that share one shape,
one fire rule, and one escalation rule — a single **lateral seam family**, an extension of
Organ 5 (information flow):

- **COLLISION-SCAN** — two peers pick up overlapping work unaware of each other and produce
  duplicate or contradictory outputs that only collide at merge. Peers emit a lightweight
  `work.claimed {role, work_territory, intent_summary}` on pickup; a scan reconciles the open
  claim set. `duplicate` → peers self-resolve laterally, one yields, **zero CEO traffic**; only
  a `contradiction` where both mandates genuinely disagree escalates (it's a mandate-boundary
  dispute, not a work overlap).
- **DEPENDENCY-STALL** — the mirror: a blocked dept in a meeting-free org is *invisible* because
  it simply stops emitting, and silence-as-block looks identical to silence-as-consent. A
  freshness-window sensor on a `depends_on` edge converts the *absence* of output into an
  explicit `dependency.stall.raised`, routed to the lowest common owner of consumer+producer —
  who issues a scope/priority MOVE that clears it. Escalates only if the stall persists after a
  self-heal MOVE.
- **CONTRACT-CHANGE-INTENT** — a producer edits a depended-on seam; today the divergence sensor
  fires *after* every dependent is already broken. This moves reconciliation *before* the
  mutation: the gate refuses to admit a seam-shape change unless a matching
  `contract.change.proposed {seam_id, proposed_shape, is_breaking, dependents[],
  objection_deadline}` exists upstream. Silence = consent after the deadline; objections route
  **through the skeptic** (reuse, don't duplicate); escalates only an unresolved objection or a
  breaking change to a charter-scoped dependency.

**Shared shape:** `{observer_role, subjects[], reference, result(consistent|divergent),
divergence_kind(duplicate|contradiction|stall|breaking-change), evidence_event_ids[]}`.
**Shared fire:** event-triggered by a peer's claim / edit / freshness-cross (never a cadence —
lateral collisions are created at claim/edit time, not on a clock). **Shared escalate (one rule,
three tiers):** `consistent` → write-and-silence; `divergent` but resolvable within peers' own
scope → lateral self-heal, zero CEO traffic; `divergent` AND neither peer can yield without
violating its mandate → up, and only as an approval-queue entry surfaced by the existing digest.

[`tools/reconcile.py`](../tools/reconcile.py) implements all three over the ledger: `collision`
(open `work_claimed` set → overlap → duplicate self-heals laterally, contradiction escalates),
`stall` (a started-but-not-completed cycle past a freshness window → the silence-as-block made
explicit), `contract` (a breaking seam change → the gate must not admit it until objections
resolve). Verified: two peers on one territory surface as a lateral overlap (no CEO); a 3-cycle
stall escalates; a breaking contract change escalates.

## §2.5 Resource & learning events (running code: `tools/resource.py`, `tools/learning.py`)

The §3 set below, of which these three have running code because a 24/7 org strands resources
and repeats its own mistakes without them:

- **PRIORITY-RANKING** ([`resource.py rank`](../tools/resource.py)) — the reference every
  allocation reads. Emits `priority_ranking_set` **only when the order changed** (silent when a
  recompute matches the current order — no event, no digest). Verified: a reorder emits; the same
  order re-ranked is silent.
- **ALLOCATION-RECLAIM** ([`resource.py reclaim`](../tools/resource.py)) — grants exist but
  nothing takes them back; stranded resource is the dominant 24/7 waste. Reclaims from a low-yield
  or idle holder in the safe direction, unattended, no CEO traffic; escalates only if it would
  touch a CEO-protected dept. Verified: an idle holder is reclaimed silently.
- **AUTHORITY-EXPIRED** ([`resource.py authority`](../tools/resource.py)) — delegations never
  decay; privilege-creep is the deepest overnight-compromise surface. Auto-narrows stale grants
  past their TTL unattended (safe direction); escalates only to *widen/renew* past a cap.
- **OUTCOME-DELTA** ([`learning.py delta`](../tools/learning.py)) — doctrine is the outside world;
  this is the org's own track record. Joins closed decisions to realized outcomes; silent when
  predictions matched; escalates only when the **same delta class recurs** past a systemic
  threshold ("how we operate is wrong"). Verified: three same-direction misses escalate as
  systemic; a match is silent.

## §3 The rest of the discovery set — where each belongs

The full essence-first sweep (five lenses: sync-alignment, control-safety, resource-priority,
knowledge-learning, coordination-dependency) surfaced more events. Ranked, with honest routing:

| Event | Essence | Home | Status |
|---|---|---|---|
| **PRIORITY-RANKING** | every allocation MOVE is only correct relative to a current ranking; without one authoritative order, each dept funds yesterday's #1 | the reference the exec-review sensor reads; a `priority_ranking_set` event, re-emitted only when the order changes (Organ 7) | **code** (`resource.py rank`) |
| **ALLOCATION-RECLAIM** | grants (`context_budget`, `model_tier`, dept-slot) are given but no event *takes them back* — stranded resource is the dominant 24/7 waste | a sensor on ledger-derived yield → an existing narrow/deactivate MOVE; net-new is the reclaim *event*, not a new organ | **code** (`resource.py reclaim`) |
| **OUTCOME-DELTA** | doctrine imports *external* best-practice and is structurally blind to *this org's own* miscalibration; without a self-outcome event the org repeats its own mistakes | distinct from doctrine (which docs/07 fixes as outside-world only); a cadence reconciler joining closed decisions to realized outcomes, escalating only when the same delta recurs N times ("how we operate is wrong") | **code** (`learning.py delta`) |
| **AUTHORITY-EXPIRED** | delegations are granted but never *decay*; a standing over-broad grant no one revisits is the deepest overnight-compromise surface | a cadence + event-triggered scan; auto-revokes/narrows in the safe direction unattended, escalates only to *widen/renew* past a cap | **code** (`resource.py authority`) |
| **CONTEXT-TRANSFER** | on deactivation a dept's live state (open threads, why-we-chose-X) is in the ledger but not indexed for whoever inherits it | a deterministic reaction bound to any activate/deactivate MOVE (Organ 7); escalates only if it would orphan a live commitment | design — a projection bound to a move; event class declared |
| **RECOVERY-PROVEN** | "reversible" claims never tested are not reversibility; prove the undo works before you need it | ship only if the org relies on rollback for its reversible-action claims; a low-frequency dry-run, escalating + reducing autonomy on failure | design — **conditional** (only if the org relies on rollback) |

**Dropped as human-ritual-only** (their information-role is already carried by the ledger causal
chain, doctrine admission, the skeptic, or the digest): postmortem, risk-review, CAB,
budget-review, capacity-forecast, backlog-grooming, onboarding, SLA-negotiation. None move
information no organ already moves; adding them would only re-import human latency.

## §5 The self-driving schedule — and the guarantee that a check actually fires

An org that runs 24/7 must decide *when* each check above runs, and must keep running while the
human sleeps. The naive answer — ship a scheduler — violates R0 (docs/09 §4: "the system never
ships a scheduler"). A scheduler is a stateful long-lived process; putting one in the repo would
leak org state outside the ledger (breaking auditability), pin the repo to one host's timer, and
make this "just another agent framework." So the schedule is split the same way every organ is:

| | The repo ships (neutral, declarative, pure) | The host provides (drive, state, env-specific) |
|---|---|---|
| **the schedule's content** | [`template/schedule.yaml`](../template/schedule.yaml) — which check runs on which cadence/trigger, and whether it is night-safe | |
| **one tick's plan** | [`tools/tick.py`](../tools/tick.py) — a **pure planner**: given schedule + now + ledger, which checks are DUE, night rules applied, which were MISSED | |
| **the drive** | | a cron / CI / harness loop that invokes `tick.py plan` on the base interval, then runs the tools it names |

The registrar (an LLM agent, organization.yaml) **owns** `schedule.yaml`: it edits the cadences
to set the org's own schedule. The **lint is the guardrail on that ownership** — `org_lint.py`'s
`SCH` checks reject any edit that would be unsatisfiable (a cadence finer than the host's base
interval, which the cron could never fire), fail-open (a check missing its `night_safe` policy),
or unverifiable (a `verify_event` that names no real ledger class). So "the LLM sets its own
schedule" is real, and the guardrail keeps every such edit R0-safe and night-safe.

**Night is fail-safe, not fail-open.** `tick.py --night` suspends every check not marked
`night_safe`; for sensor→move checks the *tighter* of `schedule.night_safe` and the sensor's
`preregistered_for_night` (sensors.yaml) wins. An undeclared night policy is a lint error, not a
default-on — the constitution's `delegated.night` forbids fail-open.

### §5.1–5.2 "It was supposed to run" is a detected fact, never an excuse

The core guarantee. A schedule the host quietly stopped firing is **indistinguishable from an org
that had nothing to do** — and that ambiguity is the exact failure this layer exists to remove.
So each check declares a `verify_event`: the ledger event class whose presence *proves it ran* in
its window. `tick.py` computes, for every due check, whether that proof exists — a due check with
no matching event within the grace window is a **MISS**, and consecutive misses **escalate**
(`wake_up_push` — a missing schedule is a page). `tick.py`'s own run emits `tick_planned`, so a
gap in *that* stream proves the host cron itself died — the outermost dead-man's switch.

Verified: with `chain_verify` due every 30 min but zero `heartbeat` events in the ledger,
`tick.py plan` reports the miss and exits 10 (escalate). This is the direct answer to "don't say
it was supposed to fire — make it actually fire": the tools don't *assume* the host called them;
the planner *detects* when it didn't and pages. Fail-safe by construction.

## §6 What is code vs. design here (the honesty ledger)

To not repeat the "described as if built" gap this repo has been audited for:

- **Running code, verified:** all three safety guardrails
  ([`tools/guardrails.py`](../tools/guardrails.py) — BLAST-RADIUS-CAP, STATE-RECONCILED,
  STALE-REFERENCE), the lateral reconciliation family
  ([`tools/reconcile.py`](../tools/reconcile.py) — collision, stall, contract), the resource
  events ([`tools/resource.py`](../tools/resource.py) — rank, reclaim, authority), self-learning
  ([`tools/learning.py`](../tools/learning.py) — outcome delta), and the schedule planner with
  its missed-tick guard ([`tools/tick.py`](../tools/tick.py)). Each verified fail-quiet on the
  happy path and exit-10 on the exception. They sit on [`tools/ledger.py`](../tools/ledger.py)
  (append-only hash chain + deterministic views/digest) and
  [`tools/sensors.py`](../tools/sensors.py) (machine sensors over the ledger). The schedule
  itself is declarative data ([`template/schedule.yaml`](../template/schedule.yaml)),
  lint-guarded by `org_lint.py`'s `SCH` checks.
- **Still design (honestly conditional):** CONTEXT-TRANSFER (a projection bound to an
  activate/deactivate move) and RECOVERY-PROVEN (only meaningful if the org actually relies on
  rollback for its reversible-action claims) — event classes declared, tools deliberately not
  written until an adopter's system needs them. Flagged as design, not narrated as operational.
- **Delegated by R0:** the cron/CI/harness loop that *drives* `tick.py` and invokes the tools it
  names, and the external ground-truth snapshot STATE-RECONCILED diffs against, are the host's —
  this repo ships the pure planner and the pure checks, never the loop that fires them. The
  guarantee that a delegated tick actually fired is *not* left to trust: §5.2's missed-tick guard
  detects and pages when it doesn't.

*Status: §2.1–§2.5 and §5 are running, verified code; the two §3 conditionals are design with
declared event classes; the routing claims (which ritual dissolves into which organ) are this
repo's synthesis from the five-lens discovery sweep, to be verified against a running system. The
governing rule (§0, reconcile by exception, never stop to meet) is realized in every coded tool's
exit-code contract, and the self-driving guarantee (§5.2) is realized in tick.py's missed-tick
escalation — "it was supposed to run" is a detected fact, not an assumption.*
