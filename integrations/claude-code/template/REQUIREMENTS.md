# REQUIREMENTS — the template for writing requirements (`/org-found` writes it as `REQUIREMENTS.md`)

> **This is a template — the skeleton of the sections — and is not itself a set of requirements.**
> `/org-found` shapes the brief it received onto this structure and writes it to `REQUIREMENTS.md` at
> the org root. `org_lint` mechanically checks for missing required sections and for how the
> statements are written (docs/11 §0a / §0b).
>
> **Why this is not an "RFP":** an RFP (Request for Proposal) is a **procurement document**, meant to
> solicit proposals from competing external vendors, evaluate them comparatively, and select a party
> to contract with. Its core is the evaluation criteria, the scoring, the required proposal format,
> and the contract terms — none of which function for in-house development. What is written here
> corresponds to ISO/IEC/IEEE 29148:2018's **StRS (Stakeholder Requirements Specification)** — a
> document describing needs from the commissioning side, before stepping into a solution. The one
> thing worth borrowing from an RFP is the discipline of documenting the evaluation criteria in
> advance, and in this template that is carried by the acceptance criteria (§4) and the success
> criteria (§5).
>
> **Declared conformance:** **tailored conformance** to ISO/IEC/IEEE 29148:2018 (the form of
> conformance that standard's §4.5.2 formally recognises). Not all twenty SRS clauses (§9.6) are
> adopted — `Memory constraints` and `Site adaptation requirements` are clauses for embedded and
> defence work, and in a small product they would only line up empty fields, and **a document with
> empty sections stops being read and eventually stops being updated**. The four adopted are §5.2.4
> (syntactic rules), §5.2.5 (the characteristics of each requirement), §5.2.6 (the characteristics of
> the set), and §5.2.7 (the words to avoid).

---

## 1. Why — why is this being built

`<one paragraph from the customer's point of view. "For whom, in what situation, what changes."
Write the outcome, not the technology.>`

> After Amazon's PR-FAQ, **write it as though it were already out in the world**. If this does not
> fit in one paragraph, that is a sign the customer value is not settled, so go back before writing
> any requirements.

**Purpose (one sentence):** `<why this org exists. An outcome, not a metric.>`

## 2. Goals / Non-Goals

**Goals:**
- `<what is to be achieved>`

**Non-Goals (stated explicitly as not being done):**
- `<what will not be done. Write why, too>`

> From Google's Design Doc. **Non-Goals are the cheapest device there is for stopping scope creep**:
> making it "it is written down that we decided not to" rather than "it is not written, so we are not
> doing it" keeps "surely we need this too" from reigniting later. The difference from EXCLUDE (§7):
> a Non-Goal is something this product does not hold as a direction, while an EXCLUDE is something
> left out of this release.

## 3. Requirements — in EARS notation, numbered FR-001

> **Write each in one of the six EARS patterns** (Alistair Mavin, Rolls-Royce; adopted by Airbus,
> NASA, Bosch, Intel, and Siemens). The ruleset is "zero or more preconditions, **at most one
> trigger**, one system name, one or more responses". The constraint of at most one trigger is what
> **enforces the granularity of a requirement at the syntactic level**.
>
> | pattern | template |
> |---|---|
> | Ubiquitous | `The <system> shall <response>` |
> | State Driven | `While <precondition>, the <system> shall <response>` |
> | Event Driven | `When <trigger>, the <system> shall <response>` |
> | Optional Feature | `Where <the feature is included>, the <system> shall <response>` |
> | Unwanted Behaviour | `If <trigger>, then the <system> shall <response>` |
> | Complex | `While <precondition>, When <trigger>, the <system> shall <response>` |
>
> **Written in Japanese** the syntax still holds: 「〜のとき、システムは〜すること」. 29148 §5.2.4
> NOTE 2 also permits the user-story form, but **in a context where an AI agent implements it, use
> EARS** — vague words are excluded at the syntactic level and misinterpretation drops sharply.
>
> **The keyword convention (29148 §5.2.4):** `shall` = a requirement (mandatory) / `will` = a fact or
> a declaration about the future (not binding) / `should` = a preference (not a requirement) /
> `may` = permission. **Do not use `must`** (it is mistaken for a requirement).

| ID | requirement (EARS) | rationale |
|---|---|---|
| FR-001 | `<When ... the system shall ...>` | `<why it is needed>` |

> **Do not fill an ambiguity with a guess — state it as `[NEEDS CLARIFICATION: what is unclear]`**
> (from GitHub Spec Kit). An agent implementing on a guess is the largest failure mode, and the lint
> fails on any left unresolved.

## 4. Acceptance — acceptance criteria (Given-When-Then)

> For each requirement, write the verification scenario **before implementing**. The notation is
> borrowed from Gherkin (Cucumber's official specification), though adopting its toolchain is
> optional. This is the one essential thing worth borrowing from an RFP — the in-house translation of
> "document the evaluation criteria in advance".

```
FR-001:
  Given <the precondition>
  When  <the action>
  Then  <the observable result>
```

## 5. Success Criteria — numbered SC-001

> They must be **technology-independent and quantitative** (from Spec Kit). Not "fast" but "within
> 200ms at the 95th percentile". Do not mention the implementation.

| ID | success criterion |
|---|---|
| SC-001 | `<quantitative, technology-independent>` |

## 6. Constraints / Non-Functional

> **Go once through** ISO/IEC 25010:2023's nine characteristics (Functional suitability / Performance
> efficiency / Compatibility / **Interaction capability** (formerly Usability) / Reliability /
> Security / Maintainability / **Flexibility** (formerly Portability) / **Safety** (new in 2023))
> **and write only those that apply**. Filling in every characteristic is excessive. Where payments
> or personal data are handled, always look at Safety and Security.

- `<constraint>`

## 7. Out of Scope / Assumptions / Open Questions

**Out of Scope (not this time):**

| what is excluded | why |
|---|---|
| `<X>` | `<why it is left out. Where it is a known failure, say so: "a known death. Do not investigate again">` |

> **Writing down a known death is the most valuable thing here.** Without "it was investigated and
> found structurally impossible" on record, another agent re-runs the same investigation, reaches the
> same conclusion, and dissolves the time.

**Assumptions (premises; if one breaks, the requirements change):**
- `<premise>`

**Open Questions (undecided; must be settled before implementing):**
- `<question>`

---

## Appendix: the review checklist (29148 §5.2.5 / §5.2.6 / §5.2.7)

This contains both what `org_lint` checks mechanically and what a human reads.

**Each requirement (§5.2.5 — nine characteristics):**
Necessary / Appropriate (the level of abstraction fits; it does not needlessly constrain the design)
/ Unambiguous (interpretable in exactly one way) / Complete (understandable without reading
elsewhere) / **Singular (one capability only)** / Feasible / **Verifiable** / Correct (an accurate
expression of the original need) / Conforming (follows the template)

**The set of requirements (§5.2.6 — five characteristics):**
Complete (contains no TBD/TBS/TBR) / Consistent (no contradiction or duplication; units and terms
unified) / Feasible (including "affordable") / Comprehensible / Able to be validated

**The words to avoid (§5.2.7 — the lint fails on these):**

| kind | examples |
|---|---|
| superlative | best, most, 最高の, 最適な |
| subjective | user friendly, easy to use, cost effective, 使いやすい, 分かりやすい |
| vague pronoun | it, this, that (where what it refers to is unclear) |
| vague adverb or adjective | almost always, significant, minimal, ほぼ, 十分に, 適切に |
| vague conjunction | `and/or`, および/または |
| unverifiable | provide support, but not limited to, as a minimum, 等をサポートする |
| comparative | better than, より良い |
| loophole | if possible, as appropriate, 可能であれば, 必要に応じて |
| universal | all, always, never, every, すべて, 常に, 決して |
| incomplete reference | a reference to an external document with no version or date |
