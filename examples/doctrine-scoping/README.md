# Doctrine scoping — per-role brains that narrow down the org and survive refounding

Each role in an orgforge-plugin organization carries its **own** doctrine (its accumulated,
gate-admitted brain). This example is the physical evidence, verified on the real Claude Code
CLI, that three properties hold:

1. **The brain is keyed by role, and roles are named by trade** — so scope narrows as you go
   down and splits sideways by specialty. Not one `worker` brain: `ui-worker`, `api-worker`,
   `db-worker` are separate brains.
2. **A spawned subordinate gets its own brain, not its parent's** — the manager renders the
   child's doctrine and hands it down; the parent's broader brain does not leak down.
3. **When roles are redefined (refound), the brains follow as assets** — renamed, split by
   scope, or merged, and never silently lost.

The brains themselves are in [`brains/`](brains/) — one `<role>.json` per role.

## 1. Scope narrows down and splits by trade

```
cto.json            broad, shallow:  "prefer boring tech", "one team owns a capability end-to-end"
  eng-manager.json  domain norms:    "independent modules parallel; coupled unit → one agent"
    ui-worker.json   craft:  "don't split a ~250-line coupled single-file UI"
    api-worker.json  craft:  "endpoints contract-first; idempotency keys on state-changing POST"
    db-worker.json   craft:  "avoid N+1; covering index on hot queries; reversible migrations"
```

Verified: rendering each role's doctrine (the exact step the SessionStart hook runs) returns
**only that role's claims** — the CTO never sees the keypad rule, the ui-worker never sees the
DB rule. Same store, same tool, keyed by `ORG_ROLE`. Widen the naming to a single `worker`
brain and the specialist thins into a generalist — the keying is what buys narrow-and-deep
(docs/07 §1.1).

## 2. Two load paths — and why a manager must hand down the brain

The SessionStart hook (`org_session_start.py`) auto-injects doctrine **only for a top-level
launch** (`claude -p` via the runner). A probe confirmed the gap: a subordinate spawned
in-process via the Agent tool started with `NO-DOCTRINE-IN-CONTEXT` — the hook does not reach
it, and it inherits the parent's `ORG_ROLE`, not its own.

The fix, verified in a second run: the **manager renders the child's brain before spawning**
(`doctrine.py render <root> eng-manager`) and prepends it to the child's prompt. The child
then started holding its own `eng-manager` doctrine (2 claims, verbatim in its transcript) and
**none** of the parent CTO's brain. That is the manager duty now written into
`template/PROJECTION.md` §1 and docs/06 §2.1.

## 3. Refound re-routes the brains (assets intact)

When the org is reshaped, `doctrine.py remap` performs what `refound`'s `doctrine_remap`
declares. Verified on these brains:

| Case | Map | Result |
|---|---|---|
| Rename / merge | `{"eng-manager": "platform-manager"}` | platform-manager inherits the eng brain (2 claims) |
| Split by scope | `{"ui-worker": ["frontend-worker", "mobile-worker"]}` | each claim routed by its `affected_roles`: frontend gets 2, mobile gets 1 |
| Orphan guard | `{"api-worker": ["x-worker", "y-worker"]}` | **blocked (exit 2)** — api claims map to neither target; refound refuses rather than lose a brain |

`--allow-orphans` instead surfaces orphans to `UNROUTED.json` for a human to place. No brain
is ever silently dropped — the admission principle (docs/06) run in reverse. Regression tests:
`tests/test_organs.py::test_doctrine_remap_*` (rename, split, orphan-block, allow-orphans).

## 4. Delegation fixes the seam, not the axis

A recursive org decomposes freely but must recombine cleanly. Three independent adversarial
critiques — organizational theory, software architecture, and multi-agent systems — all
rejected the tempting idea of fixing one **decomposition axis** (by-feature vs by-layer vs
by-phase) top-to-bottom: the right axis changes by level (a company splits by function; an
auth team inside it splits by layer), and a global axis is redundant with the scoped doctrine
and can contradict it. What actually makes sibling pieces compose is the **seam contract** at
each cut, owned by the parent.

So `tools/handoff.py` builds the packet a manager hands each child: **slice + seam contract
(inputs / outputs / owns / forbid / invariant) + brain scoped to the slice**. The axis is
demoted to local advice ("choose the cut that fits YOUR slice — do not inherit a global one").

Verified across two levels (see [`handoff-L1-api-worker.md`](handoff-L1-api-worker.md) →
[`handoff-L2-login-worker.md`](handoff-L2-login-worker.md)):

- The child's brain **narrows** each level: api-worker gets the API-general doctrine; the
  login-worker below it gets only login craft (rate-limit, constant-time compare) — the
  API-general `idempotency` claim does **not** leak down.
- The `{error,code}` seam invariant is **carried across the level** as a hard constraint, so
  the login handler integrates back into the exact interface its parent fixed.
- `handoff.py` **requires** inputs+outputs — a manager cannot delegate without fixing the
  boundary, so no child is ever spawned with an un-owned seam (the integration-drift guard).

Regression tests: `tests/test_organs.py::test_handoff_*` (seam required, brain scoped +
sibling brain does not leak, axis is local advice).

## Honest limits

- The nested hand-down was driven by a manager profile that I authored for the probe. It is
  now documented as a standing duty (PROJECTION.md §1), but a full multi-level org that
  hands brains down two or more levels *from the profile alone* — no per-run authoring — has
  not yet been run end-to-end here.
- `remap`'s split routes by `affected_roles`; a claim relevant to several new roles must tag
  them all. Authoring that tagging correctly at refound time is a human/curator judgment, not
  automated.
