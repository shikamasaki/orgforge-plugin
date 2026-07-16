# 10 — The Founding Rehearsal: S1, Demonstrated

> docs/01 names **S1** — "the system runs, unmodified, on at least one existing host
> harness, with no custom runtime" — as *the* open item, the one that turns every other
> claim from a design into a fact. This document records the first end-to-end run that
> closes it. It is not a hypothetical; it happened, on a real host harness (Claude Code +
> subagents as the departments), and the full artifacts are reproduced below. The result
> was better than "it ran": the control system caught a real bug the maker and the gate
> both missed — which is the entire reason the control system exists.

---

## What was run

A real RFP — build a tested `slugify(text)` utility — was taken through the FOUNDER
process (docs/06 §1) and instantiated as a minimal three-department organization, each
department a **separate agent on the host harness** with its own working directory:

- **miner** (organic maker) — wrote `slugify.py` + `test_slugify.py` toward its contract.
- **gate** (mechanistic checker / authorization) — a *different* agent; independently
  re-ran the tests and judged coverage against the admission standard.
- **skeptic** (mechanistic adversarial checker) — a *third* agent; tried to refute the
  admitted result.

No bespoke runtime was involved. Each department was launched on the host harness, read
its contract and discipline from its working directory (the projection), did a cycle of
real work with the harness's own tools and loop, and wrote its output as files. That is
exactly the delegation model of docs/09 — the host supplied perception, tools, and the
loop; the repository supplied only the skeleton (who owes what, who checks whom) and the
separation.

## What happened, step by step (the audit trail)

1. **Founding.** The RFP was distilled to a telos and a gaming-defense-backed admission
   standard ("the tests must actually RUN and PASS when an *independent* party runs
   them"), decomposed into one maker contract with a named, distinct checker. (Genesis in
   the ledger; docs/06 §1.)

2. **maker cycle.** The miner produced `slugify.py` + `test_slugify.py`, ran pytest
   itself (7 passed), and — critically — **flagged a genuine spec ambiguity in its
   submission instead of guessing silently**: whether a unicode letter like `ñ` acts as a
   separator (`piñata` → `pi-ata`) or is deleted (`piata`). This is the ROLE.md discipline
   *"honesty over optimism"* working on a live harness: the maker surfaced its own
   uncertainty rather than papering over it.

3. **gate cycle (independent verification).** A *different* agent copied the files into
   its own working directory, re-ran pytest from scratch (7 passed — it did **not** trust
   the maker's claim), checked each of the five named acceptance cases against a real test
   (not just the count), and **ruled on the maker's flagged ambiguity from the RFP
   wording** — upholding the separator interpretation as the more literal reading of rule
   2. Verdict: **ADMIT.** This is separation of duties realized structurally: the maker
   could not admit its own work; an independent agent did, and re-derived the result
   rather than rubber-stamping it.

4. **skeptic cycle (adversarial refutation).** A *third* agent attacked the admitted
   result with 17 adversarial tests. Sixteen survived. One **refuted** it: input `"aKb"`
   where `K` is U+212A (KELVIN SIGN, a Unicode uppercase letter). The implementation
   lowercases *before* the regex; U+212A is the **unique** non-ASCII code point whose
   `.lower()` is a pure-ASCII alphanumeric (`k`), so it leaks through as a letter instead
   of becoming a hyphen — violating requirement 2. Spec-correct output `"a-b"`; actual
   `"akb"`. Verdict: **REFUTED.**

   The skeptic also noted the bug is narrow and its refutation honest (it did not
   manufacture a false positive — 16 of 17 attacks it reported as survived).

## Why this is the result that mattered

The rehearsal's purpose was never "ship a slug function." It was to test whether the
organization's **control skeleton actually functions on a real harness**. It did — and it
did the one thing the whole two-layer law (docs/03) exists to buy:

- **The maker could not have caught this** — its own mental model (lowercase-then-regex)
  *was* the bug; its tests encoded that model, so they passed.
- **The gate did not catch it** — its ADMIT explicitly rested on the invariant
  "lowercasing lets ASCII uppercase survive while unicode letters fall outside `[a-z0-9]`."
  U+212A is the sole counterexample to that invariant, and the maker's suite never probed
  a unicode letter that case-folds *into* ASCII.
- **Only the independent adversarial skeptic caught it**, because refutation is a
  different job from verification: the gate asks "do the stated cases pass?"; the skeptic
  asks "what case breaks the requirement while the tests still pass?"

This is Organ 6 (docs/03 §3, docs/04 §5) demonstrated, not asserted: **an agent that
checks its own work — or a checker that rubber-stamps — ships this bug. The maker/checker
line, and the adversarial layer beyond it, are what caught it.** If this org had collapsed
maker and gate into one agent (self-admission), or stopped at the gate (no adversarial
review), the defect reaches production. It didn't, because the structure forbade it.

## What this closes, and what it does not

**Closes:** S1's core claim (docs/01 §4). An organization from this template launched on
an existing harness, its departments ran as separate agents with no bespoke runtime, the
maker/checker separation held structurally, and the control system did real work —
catching a defect the producing agent could not have caught. Delegation (docs/09) is not
just specified; it ran.

**Does not close:** this was a **Tier-A** rehearsal (docs/01 §5) — no assets, no
production, no external boundary — so it exercised structural separation and the loop
delegation, not the Tier-B host-environment controls (sandboxing, tamper-evident storage,
credential custody). It used the harness's own scheduler implicitly (sequential launches),
not a declared cadence over many cycles. And it was one small RFP, not the elastic
multi-department lifecycle of docs/05–06. The projection was done by hand (files written
into working directories), not by an automated projection tool — which remains the open
build item (docs/01 §7 #1). So: the load-bearing claim is now demonstrated; the fuller
autonomy story (24h operation, elasticity, Tier-B, automated projection) is still ahead.

## Reproducing it

The complete artifacts from the run — the genesis entry, the maker's submission, the
gate's verdict, and the skeptic's refutation with its reproducing test — are preserved
under `examples/founding-rehearsal/` in this repository. The bug is real and reproducible:
`slugify("aKb")` returns `"akb"` where the spec requires `"a-b"` (with `K` = U+212A).

*Status: this is a record of one real run, not a claim that the whole system is proven. It
demonstrates the load-bearing requirement (S1) and the load-bearing control property
(independent verification catches what the maker cannot). Everything docs/01 §4 lists
beyond S1 remains to be shown.*
