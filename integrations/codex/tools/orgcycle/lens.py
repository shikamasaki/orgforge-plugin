"""Fix the **lens** of a judgment before the judgment (never have the judge derive it).

## Status: **not wired up** (2.3.0 does not call this from verify)

Three hand-written lens items produced -25%, but **the lens this module generates automatically did
not reproduce it** (the last two rows of the table below). Narrowing to three items does not help
either: 59.0s → 100.9s. Until the difference from the hand-written version can be explained,
something of unknown effect does not go into the delivery path.

It is kept because the measurements are worth having; wiring it up waits until the difference can be
explained. Add it on "it should be faster" and the next hunt for slowness has one more suspect.

## Why it is needed (measured)

The material handed to a judge holds the SPEC and the charter, but not **where specifically to look
for this Issue**. So the judge assembles the scope of its checks from nothing every time — and that
is most of the judging time.

Medians over three runs each, same material, same model (gpt-5.6-terra / medium):

| what was handed over | median |
| --- | --- |
| as it stands (charter + SPEC only) | 104.8 s |
| **a concrete lens** | **78.6 s (-25%)** |
| only the procedure, "derive the lens from the MUSTs" | 96.5 s (-8%) |
| all ten acceptance criteria, expanded | 116.0 s (**slower**) |

That last row decides how much of this is safe. **A lens works on the condition that it is
narrowed**; line up more of them and it adds work rather than removing it. So `max_items` defaults
to 3 — the same scale as the hand-written version that produced -25%. Raise it and the effect
inverts.

**Handing over the procedure does not work** (it merely makes the judge do the deriving). What works
is the lens itself. So the lens has to be settled beforehand — and since a person writing it each
time varies by Issue, it is **assembled mechanically** here.

## The line this does not cross (docs/03 §6.5)

**It never writes the pass condition.** Measured, tightening as far as "judge on the output of these
three commands alone, no other consideration is needed" fell to 26.2 s (-69%) — and **admitted a
placebo implementation** (one that satisfies the wording while betraying the intent, missed because
the rule commanded that no other consideration was needed). It was fast because it had stopped the
thinking, and that is the disappearance of the gate.

So what is written here is **only where to look, and in what order**. What counts as a pass is not
written. The judgment belongs to the judge.

## Three layers (increasingly specific)

1. **phase defaults** — what is worth confirming differs by phase (asking for CI green at
   requirements is meaningless; checking EARS syntax at deploy is late)
2. **the seams / contracts that changed** — the acceptance criterion of Issue #175. Re-reviewing
   untouched territory every time spins CI and the model on every round trip
3. **the SPEC's acceptance criteria** — one at a time, one minimal observation each
"""

from __future__ import annotations

import re


# ── 1. phase defaults ───────────────────────────────────────────────────────
# Only **what is worth confirming in that phase** goes here. The pass condition is never written.
# The phase names match the non-skippable phases of docs/11.
_PHASE_LENS = {
    "requirements": [
        "whether each acceptance criterion is written in one of the five EARS forms and is "
        "**testable** (prose such as \"authentication works\" is itself grounds for a send-back)",
        "whether the Intent connects to the org's telos (as a purpose, not a metric)",
    ],
    "design": [
        "whether the seam contract's `provides` is written in **a named form** (a signature, a "
        "schema, a table) so that downstream can wire up without guessing",
        "whether `boundary (NOT mine)` is stated, so parallel makers do not build the same "
        "thing",
    ],
    "implement": [
        "**actually running** the SPEC's DoD command (where there is one) and making its real "
        "output the evidence",
        "whether one observation exists for each acceptance criterion",
    ],
    "test": [
        "whether a test is shown **to actually go RED** (a test shown only to pass may be "
        "guarding nothing)",
        "whether the error paths and boundaries are covered within the scope of the acceptance "
        "criteria",
    ],
    "integrate": [
        "whether **the downstream consumers are unbroken** against the seam contracts that "
        "changed",
        "whether the diff against the integration ref stays within this Issue's scope",
    ],
    "deploy": [
        "whether the committed CI workflow is green from a clean clone (**in this phase, that "
        "carries the weight**)",
        "whether the mechanical bar for reproducibility (repro_lint) is holding",
    ],
    "operate": [
        "whether there is a way back on a regression (a rollback, a feature flag)",
        "whether it comes with a way to observe it (logs, metrics)",
    ],
}

# The five EARS forms. Used as **a lens on** whether an acceptance criterion is syntactically
# verifiable (it does not judge).
_EARS = re.compile(r"\b(?:WHEN|WHILE|IF|WHERE|THE\s+system\s+SHALL|SHALL)\b", re.I)


def _acceptance_lines(spec_text):
    """Collect the acceptance / MUST lines from a SPEC body.

    Real Issues vary in their headings — `## Acceptance`, `## MUST`, `## Required change`. Fix the
    heading words too tightly and this returns zero, leaving the lens empty, so headings that look
    like acceptance criteria are matched broadly and the bullets or numbered items beneath them are
    the target.
    """
    if not spec_text:
        return []
    heading = re.compile(
        r"^#{1,6}\s*.*(?:acceptance|MUST|受け入れ|required\s+outcome|required\s+change"
        r"|proposed\s+acceptance)", re.I)
    out, inside = [], False
    for line in spec_text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            inside = bool(heading.match(s))
            continue
        if not inside or not s:
            continue
        if re.match(r"^(?:[-*+]|\d+[.)])\s+", s):
            # Drop the checkbox and the bullet marker, leaving the text
            out.append(re.sub(r"^(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?", "", s))
    return out


def build_lens(phase, spec_text, changed_seams=None, max_items=3):
    """Assemble and return the "lens" section handed to the judge (None if there is none).

    The judge never derives it. **It does not judge either** — it only gives an order to look in.
    """
    phase_key = (phase or "implement").strip().lower()
    lines = []

    defaults = _PHASE_LENS.get(phase_key)
    if defaults:
        lines.append(f"### What to confirm in this phase ({phase_key})")
        lines.extend(f"- {d}" for d in defaults)

    seams = [s for s in (changed_seams or []) if s]
    if seams:
        lines.append("\n### The seams / contracts that changed (only a finding tied to these "
                     "blocks)")
        lines.extend(f"- `{s}`" for s in seams[:max_items])
        lines.append("- Territory the above does not touch is **not re-reviewed** this round. A "
                     "finding there is recorded separately as `out_of_scope`.")

    accepts = _acceptance_lines(spec_text)
    if accepts:
        shown = accepts[:max_items]
        lines.append(f"\n### Acceptance criteria to re-derive ({len(accepts)}, one at a time)")
        for i, a in enumerate(shown, 1):
            mark = "" if _EARS.search(a) else "  ← not EARS syntax (confirm it is testable)"
            lines.append(f"{i}. {a[:220]}{mark}")
        if len(accepts) > len(shown):
            lines.append(f"(for the remaining {len(accepts) - len(shown)}, see the SPEC body)")
        lines.append("- For each, choose **one minimal observation**, actually run it, and paste "
                     "the real output as evidence.")
        lines.append("- If an implementation that satisfies the wording while betraying the "
                     "intent (a placebo) would produce the same output, add one more observation. "
                     "**This is never skipped.**")

    if not lines:
        return None
    return ("\n## The lens (settled before the judgment — begin the search here)\n"
            + "\n".join(lines)
            + "\n\n> This is **where to look**, not **what counts as a pass**. You settle that "
              "against the charter and the SPEC above. Even in territory the lens does not name, "
              "anything that concretely demonstrates a safety, data-integrity or security problem, "
              "or that it cannot be released, may be made a blocker.\n")
