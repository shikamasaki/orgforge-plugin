# 13 — Is the org still solving the right problem? (the proxy-stack, mandate conflict, precedent)

A systematic scan of the major organizational-theory domains against this repo's articulation
found five more gaps of the same character as intra-unit attention allocation (docs/12) — and the
same blind-spot explains all of them. Every prior discovery lens looked at the org's *seams*
(inter-department, org-wide, founding shape). None looked **up the proxy stack**
(metric → goal → purpose → world), at an **open, still-running** course, at **co-equal mandates**,
or at **accumulating internal precedent**. This document articulates those, with running code.

The unifying pathology of the first three: **a local optimizer perfecting a lossy proxy while the
real thing drifts**, at three altitudes. Each guard is a pure projection over the ledger
([`tools/alignment.py`](../tools/alignment.py)), fail-quiet, and preserves the decision line (C3):
it **surfaces**; the human **decides** (revising a goal, a frame, or the purpose is human-only).

## §1 PREMISE / telos-validity — the highest gap (`alignment.py premise`)

**Failure prevented: "correct machine, wrong problem."** Every organ can be green — ledger
consistent, guardrails quiet, learning converging — while the org executes flawlessly against a
**dead telos**: the market vanished, the problem got solved elsewhere, the founding premise no
longer holds. This is the environment-side twin of STATE-RECONCILED (docs/11 §2.2): that reconciles
belief-about-*assets* vs. reality; this reconciles belief-about-*purpose-validity* vs. the world.

**Why nothing covered it:** doctrine (docs/07) is charter-forbidden from touching the telos.
STATE-RECONCILED watches assets, not premise. The design *assigns* the human "revise purpose when
the world changes" (docs/06 §2.5) — but gave the human **no sensor to know when**. The single most
essential decision was the one essential decision with no instrument to trigger it. This is that
instrument.

`alignment.py premise` diffs an asserted founding premise against an observed ground-truth snapshot
(the calling agent supplies the snapshot — the tool does no scanning; *enactment* is the agent's
job, Weick). Silent when the premise **holds**; escalates a **weakened** premise as a watch; on a
**broken** premise it is **charter-hold** — the org does *not* auto-pivot, it surfaces the
pivot/sunset decision (moves already in moves.yaml) to the human with the evidence. Verified: a
matching premise is silent; a broken one escalates as possibly-obsolete-purpose.
**Anchor:** Weick (enactment), Aguilar (environmental scanning) — see docs/sources.md.

## §2 SUNK-COURSE — escalation of commitment (`alignment.py sunk`)

**Failure prevented: bounded work silently becoming unbounded burn.** A running course of action
never gets killed — a department re-issues work against a failing approach, pours compute into a
branch whose outcomes are not converging. In a manned org a human notices the team is stuck; here
nobody is watching. This is peer to BLAST-RADIUS-CAP (docs/11 §2.1) — a spend-bounding guard — but
for a *single course outrunning its own progress*, which the aggregate cap cannot see.

**Why nothing covered it:** OUTCOME-DELTA fires on *closed* decisions and only on *recurrence*; it
is silent on a single *open* course still consuming. ALLOCATION-RECLAIM reclaims *idle* grants — it
can't see a *busy* course. DEPENDENCY-STALL catches a dept that *stopped*; this is the opposite — a
dept that *won't stop*.

`alignment.py sunk` joins an open course's accumulated attempts and cost against a commitment cap
and its outcome trend. Self-halt (`abandon`) is the **safe direction** — abandoning is reversible,
the ledger keeps the work — so it runs unattended; it escalates only if the course is
charter-scoped. Verified: a course past its attempt cap with flat outcomes returns `abandon`.
**Anchor:** Staw (1976), "Knee-deep in the Big Muddy."

## §3 FRAME-REVIEW — double-loop learning (`alignment.py frame`)

**Failure prevented: accurate predictions against a target that is itself wrong.** OUTCOME-DELTA
(docs/11 §3) is *single-loop* by construction — it joins predicted vs. realized *within a fixed
goal frame* and never questions the goal/threshold/assumption that generated the prediction. An org
whose predictions are individually accurate against a wrong target drives confidently off a cliff:
every delta is small, nothing recurs, no signal fires, because the error is in the *frame*, not the
execution.

`alignment.py frame` surfaces the double-loop question — "these N predictions were *accurate*, yet
the result they proxy is *drifting*" — and escalates it charter-tier. It **never revises the frame**
(that is the human's, C3); it makes the invisible visible. Verified: three accurate predictions
whose realized results trend down raise a frame-review. **Anchor:** Argyris & Schön (1978),
*Organizational Learning* — a canonical framework this repo had not cited anywhere.

## §4 MANDATE-CONFLICT — the collision class the repo's own code dead-ended on (`reconcile.py mandate`)

**Failure prevented: differentiated mandates paging the human nightly, or resolving by
merge-order accident.** Two departments each act *inside* their granted authority yet reach
decisions that cannot both stand (growth says "ship," safety says "hold") — not a resource grab
(ALLOCATION-RECLAIM), not a file collision (`reconcile.py collision`, which resolves by "one
yields" — legitimate only for a *duplicate* and which correctly *refuses* to auto-resolve a genuine
*contradiction*, dead-ending at "escalate to CEO").

**Why nothing covered it — and the artifact it forced:** `resource.py rank` ranks *objectives by
weight* ("what to fund first"); it does **not** resolve *which mandate governs this contested
action*. That is a different reference, and it is a **human decision**: the constitution now
declares a **`mandate_precedence`** ordering (human-authored, agent-unwritable, lint-guarded — the
`CH` check fails closed if it is missing). `reconcile.py mandate` reads it and adjudicates
deterministically: **precedence applies** (silent — the higher mandate governs) / **co-equal but
both satisfiable** → integrate laterally (Follett's integration, no CEO) / **co-equal and mutually
exclusive, or a party absent from the declared order** → escalate (the true exception — the org
never declared who governs, and only the human may). Verified all three paths. Belongs to Organ 6.
**Anchor:** Follett (constructive conflict), Lawrence & Lorsch.

## §5 CONVENTIONS — internal precedent, the third knowledge box (`tools/conventions.py`)

**Failure prevented: peers re-deriving "how we do X here" and diverging.** Human orgs coordinate
massively through routines and precedent — settled once, silently reused. An AI org cold-starting
each cycle has no shared memory of its *own* established conventions, so peer departments
independently re-derive a recurring cross-cutting choice (a naming scheme, an interface shape, an
escalation format) and drift — the tacit-not-articulated failure this whole repo exists to prevent,
reappearing one level down.

This is a **third box**, distinct from the others: not *doctrine* (external world-knowledge vs.
internal precedent), not the *constitution* (who decides vs. the content of a settled non-charter
choice), not *reconcile* (a live collision vs. the upstream shared prior so the collision never
forms). `conventions.py` reuses the doctrine machinery almost verbatim — adopt through a checker
(not the proposing dept), a conflict guard (a contradicting choice on the same scope escalates
before precedent forks), render into a role's workspace, and a review-by TTL (`stale` — routines
rot too). Verified: checker-only adoption, conflict detection, render, TTL.

**Honest framing:** because it reuses doctrine's shape so completely, whether this is a *new organ*
or a *second mode of the knowledge organ* (Organ 7) is a genuine design call. The concept —
internally-originated reusable articulated precedent — is what was missing, wherever it is housed.
**Anchor:** Nelson & Winter (1982), routines as organizational memory.

## §6 What was scanned and deliberately DROPPED (no AI analog)

The scan was ruthless about not inflating the list. Dropped, with reason: **motivation as such**
(expectancy/self-determination/goal-difficulty — an AI has no effort-cost, valence, or quit option;
only the per-unit *objective function* has an analog, already `contract`/`resource.rank`);
**culture-as-whole, org identity, institutional isomorphism** (culture *is* the articulation thesis,
split across telos + doctrine + constitution; identity decomposes into telos + discipline preamble +
conventions; isomorphism needs a peer field a solo org lacks); **groupthink / devil's advocacy** (the
structural cure — independent dissent on a different model family — is already the skeptic); **the
politics half of power** (empire-building, careerism, coalitions — parasitic on individual survival or
on information asymmetry the append-only ledger forbids; the residues are covered by resource.py +
reconcile.py); **embodied capability, tacit-knowledge storage, population ecology, TCE hold-up** (an
AI dept re-instantiates each cycle with no persistent skill substrate; capability improvement *is*
better ROLE.md + doctrine + OUTCOME-DELTA). **One watch-item on a fuse:** a transactive-memory index
("which live dept knows X") is premature now but graduates to a real gap **when elastic/RFP founding
lands** and dept membership becomes dynamic — build it *with* that, not ahead of it.

## §7 The honesty ledger

- **Running code, verified:** PREMISE, SUNK-COURSE, FRAME-REVIEW
  ([`tools/alignment.py`](../tools/alignment.py)); MANDATE-CONFLICT
  ([`tools/reconcile.py`](../tools/reconcile.py) `mandate`, reading the constitution's
  human-authored `mandate_precedence`); CONVENTIONS ([`tools/conventions.py`](../tools/conventions.py)).
  New ledger event classes for each; schedule.yaml checks; `org_lint.py` `CH` guards
  `mandate_precedence`.
- **The theory anchors** (Weick, Aguilar, Staw, Argyris & Schön, Follett, Lawrence & Lorsch, Nelson
  & Winter) are consensus ideas applied at this repo's granularity as explicit synthesis — flagged,
  not claimed verbatim (docs/sources.md discipline).
- **Preserved decision line (C3):** none of these organs decides — premise/frame surface to the
  human, sunk-course self-halts only in the reversible direction, mandate-conflict escalates the
  un-precedenced case. The human still makes the essential calls; these give the human the *sensors*
  to know when a call is needed — which several of them previously lacked entirely.

*Status: §1–§5 are running, verified code. The blind-spot analysis (why these were missed — the
lenses looked at seams, never up the proxy stack / at open courses / at co-equal mandates / at
accumulating precedent) is this repo's own synthesis, offered as the reason to keep auditing at new
granularities, not as a completeness proof. The audit's own verdict: this is not proof the
articulation is now complete — it is the set of gaps one systematic theory-sweep found.*
