# Genesis — founding rehearsal (S1 demonstration)

This is a real founding run of an org-first-agents organization, executed on a real
host harness (Claude Code + subagents as the departments). Purpose: demonstrate S1
(docs/01 §4) — an org from the template actually launching and doing useful work
end-to-end, with the maker/checker separation enforced structurally, and nothing
bespoke in the loop (the host harness supplies perception, tools, and the loop).

## The RFP (verbatim, as the client submitted it)

> Build a small Python utility `slugify(text)` that converts an arbitrary string into a
> URL-safe slug. Requirements:
>   1. Lowercase the result.
>   2. Replace any run of non-alphanumeric characters with a single hyphen.
>   3. Strip leading/trailing hyphens.
>   4. Collapse consecutive hyphens into one.
>   5. Return "n-a" for input that is empty or contains no alphanumeric characters.
> Acceptance: a pytest test file must pass, covering — normal text, unicode letters
> (é, ñ should be treated as non-alphanumeric per ASCII rule and dropped/hyphenated),
> leading/trailing punctuation, all-symbol input, and the empty string. The deliverable
> is admitted only if an INDEPENDENT reviewer confirms every acceptance case is covered
> AND the implementation actually passes the tests when run.

## FOUNDER step 1 — telos (Organ 1)

**Purpose:** Deliver a correct, tested, URL-safe `slugify` utility that meets every
stated requirement — a working asset, not code that merely looks right.

**Admission standard** (derived from the RFP acceptance criteria, gaming-defense-backed):
- The pytest suite must actually RUN and PASS (forward test — not "looks correct").
- Coverage must include every named case: normal text, unicode letters, leading/trailing
  punctuation, all-symbol input, empty string (completeness, both directions).
- Gaming defense: the checker RUNS the tests in a fresh context and independently judges
  coverage — it does not trust the maker's assertion that they pass.

**objective_metric:** admitted-and-passing deliverables. `reward_agents_on_this: false`.

## FOUNDER step 2 — architecture, then org (inverse Conway)

Target artifact: one module `slugify.py` + one test file `test_slugify.py`. Single
seam (implementation ↔ verification). Minimal org that still honors SoD:

- **miner** (organic maker): writes `slugify.py` + `test_slugify.py` toward the contract.
- **gate** (mechanistic checker/authorization): independently RUNS the tests and judges
  coverage against the admission standard; admits or rejects. Different profile lineage
  from miner (anti-puppet-checker).
- **skeptic** (mechanistic, adversarial): on an admitted positive, tries to REFUTE it —
  find an uncovered case or a way the tests pass while the requirement is unmet.
- **operator** (human — me relaying to the user): holds charter authority; this rehearsal
  is Tier-A (no assets touched), so no host sandbox is required.

## FOUNDER step 3 — output contracts

- **miner contract:** deliverable = `slugify.py` + `test_slugify.py` meeting all 5 rules;
  standard = tests present for all named cases, honestly labeled; checker = gate;
  depends_on = [].
- No department is the checker of its own contract. miner ≠ gate ≠ skeptic (lineage
  distinct). Matches the lint's O6/O6c/O7 requirements.

## FOUNDER step 4 — design fully, activate minimally

Active set for the first (only) milestone: miner, gate, skeptic. That is the full org for
this RFP. Within span (1 supervisor could watch 3; here the operator watches directly).

## Founding commit

Lint of the skeleton: the template already passes `org_lint.py`. This rehearsal instantiates
a 3-role subset whose SoD shape (maker routes to a distinct-lineage mechanistic checker;
no self-admission) is exactly what the lint enforces. Human charter approval: the operator
(relaying to the user) authorized this run. Founding is complete; departments launch below.
