"""Detect the MUSTs a read-only judge cannot re-derive, **before** the judge is launched.

## Why it is needed (measured)

A judge under `enforcement.judges.read_only: true` runs in a sandbox that can neither write nor
execute. So a MUST of the "actually run it and see it go green" kind **structurally** cannot be
re-derived, and the judge can only return park (undecidable). The park itself is correct behaviour
— do not admit what you cannot measure — but **learning that only after launching the judge and
waiting minutes to half an hour** was the problem.

judge.py said this up front as advice for a human, which did not stop the waste:

    Measured: #34 returned park, on the grounds that it was statically sound but that "100
    consecutive greens" could not be re-derived inside a read-only sandbox.

A cross-harness judge launches `codex exec` / `claude -p` as a separate process, and the default
`ORG_JUDGE_TIMEOUT` is 1800 seconds. gate → skeptic run in series, so one Issue's admission hits
this twice. **One wasted park throws away minutes to half an hour.**

This points out **statically** only that a MUST cannot be measured read-only, and prompts the
supervisor to measure it. Stopping before the judge is launched makes the wasted time zero.

## The line this does not cross (docs/03 §6.5)

**It does not judge.** admit / reject / park is the gate's decision, not this module's. What is
returned here is purely **a statement about capability** — that this MUST lies *outside a read-only
judge's power to re-derive* — and says nothing whatever about whether the MUST is met.
A forced invariant is fine; a forced judgment is the disappearance of judgment. That line holds
here too.

So the default is **advice**, not a block. Only with an explicit `--strict-rederivability` does it
stop with exit 13 (for a supervisor who has declared they will not tolerate a wasted round).
"""

from __future__ import annotations

import re


# Capabilities that lie *outside* a read-only sandbox: MUSTs that can only be confirmed by
# writing, running, or reaching outside. The patterns match both Japanese and English SPECs
# deliberately — this repo's SPECs genuinely are mixed, so these alternatives are INPUT matching,
# not source language.
#
# The bar for adding a word here is "can this be measured read-only **in principle**", not "does
# it look hard". Anything a static read settles (types, naming, structure) does not belong.
_UNMEASURABLE = (
    # the "run it and see it go green" family
    # Do not fix the word order. `consecutively 100 times` and `100 times consecutively` say the
    # same thing, but only the number-first form was matched and the other was missed (a
    # cross-harness judge raised this gap in a live judgment — the grounds for verdict=reject on
    # the second round).
    (r"\b\d+\s*回連続|\b\d+\s*回\s*(?:繰り返|連続)"
     r"|consecutive(?:ly)?\s+\d+\s*(?:times)?|\b\d+\s+times\s+consecutive(?:ly)?"
     r"|\b\d+\s+times\s+in\s+a\s+row|\b\d+\s+consecutive\s+\w+",
     "measuring repeated execution (a read-only judge cannot run it)"),
    (r"\bRED\s*→\s*GREEN|\bred\s*to\s*green|going\s+RED\b",
     "observing a test actually go RED→GREEN"),
    (r"\bCI\b.*\b(?:green|緑|pass)|\b(?:green|緑)\b.*\bCI\b|clean\s+clone.*\b(?:test|build)",
     "the result of running in CI or from a clean clone"),
    (r"\bbenchmark|\bp9[59]\b|\blatency\b|\bthroughput\b|スループット|レイテンシ",
     "measuring performance"),
    (r"\bmutation\s+test|ミューテーション",
     "observing a mutation actually take effect"),
    # the "reach outside" family
    (r"\b(?:real|実)\s*(?:DB|database|データベース)|\bmigration\b.*\b(?:apply|適用)",
     "reaching a real database"),
    (r"\bdeploy(?:ed|ment)?\b.*\b(?:verif|confirm|確認)|本番.*(?:到達|確認)",
     "confirming it at the deploy target"),
    (r"\bnetwork\b.*\b(?:call|request)|外部API.*(?:到達|呼び出)",
     "reaching across the network"),
    # the "writes" family
    (r"\bwrites?\s+to\s+disk|ファイルに書き|\bidempotent\b.*\b(?:re-?run|再実行)",
     "an observation that entails writing"),
)

_COMPILED = tuple((re.compile(pat, re.I), why) for pat, why in _UNMEASURABLE)


def _must_lines(spec_text):
    """Collect the MUST lines from a SPEC body.

    Following SPEC.md's shape (`## MUST — acceptance criteria in EARS`), the bullets from the MUST
    heading to the next heading are the target. So that a SPEC without headings (free prose) is not
    missed, lines containing `MUST` anywhere in the body are collected too.
    """
    if not spec_text:
        return []
    lines = spec_text.splitlines()
    out, in_must = [], False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            in_must = bool(re.search(r"\bMUST\b|受け入れ基準|acceptance", stripped, re.I))
            continue
        if not stripped:
            continue
        if in_must and re.match(r"^[-*+]\s+|^\d+[.)]\s+", stripped):
            out.append(stripped)
        elif not in_must and re.search(r"\bMUST\b", stripped):
            # A MUST written outside any heading (a free-prose SPEC) counts too.
            out.append(stripped)
    return out


def unmeasurable_musts(spec_text):
    """Return the MUSTs a read-only judge cannot re-derive, as [(line, reason), ...].

    **It does not look at whether they are met.** All it returns is that the means of confirming
    that MUST lies outside read-only. Where a line matches several reasons, the first is taken —
    what the supervisor needs to hear is the single point "this needs measuring", not an exhaustive
    list of reasons.
    """
    found = []
    for line in _must_lines(spec_text):
        for rx, why in _COMPILED:
            if rx.search(line):
                found.append((line, why))
                break
    return found


def advisory(findings, role):
    """The advice shown to the supervisor. Emitted before the judge is launched, so no waiting is
    incurred."""
    if not findings:
        return None
    head = (f"[rederivability] {len(findings)} MUST(s) cannot be re-derived by a read-only "
            f"{role} judge. **Launch as things stand and park is the likely result** (one judge "
            f"run takes minutes to half an hour — time that produces no judgment).\n")
    body = "".join(f"  - {why}\n      {line[:160]}\n" for line, why in findings)
    tail = ("  What to do: measure it yourself first and hand the **actual output** over as\n"
            "  evidence, then launch the judge (as the charter says, evidence is the command you\n"
            "  actually ran and its output).\n"
            "  This is advice, not a judgment. Knowing it, you may launch anyway.\n"
            "  To rule out a wasted round entirely, add `--strict-rederivability` and it stops "
            "here.\n")
    return head + body + tail
