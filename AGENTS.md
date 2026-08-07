# Working on the orgforge plugin itself

This file governs work **on this repository** — the plugin's own source. It is not the instruction
file an org receives; that one is generated per-org from `integrations/codex/AGENTS.md.tmpl`.

Read the file you are about to change before changing it. The comments in this codebase carry
measured findings ("measured: 1.90s → 0.24s", "12 rounds on issue #170"), and those are the reason
a given line exists. Preserve them; do not paraphrase a number away.

## Language: write source in English

**Comments, docstrings, and every message the tool prints go in English.**

This is not a style preference. A guardrail that blocks an action explains *why* in that message,
and a reader who cannot read the explanation cannot comply. The hook alone carried 437 lines of
Japanese, so an English-speaking operator hit a wall of text they could not act on. Translating
that back out is expensive; not adding more is free.

Do not confuse this with `constitution.yaml: output_language`. That setting governs what an **org**
writes *for its humans* — Issue bodies, work-log comments, status boards — and `ja` is a legitimate
value there. **The plugin's own source is a different surface with a different audience:** its
readers are contributors and operators of any locale.

| Surface | Language | Why |
|---|---|---|
| Source comments and docstrings | **English** | Contributors read them |
| `print()` / `stderr` / exception text | **English** | Operators of any locale read them |
| Test names and test docstrings | **English** | They are the executable spec |
| `template/*.md` section headings | **English** | The skeleton is shared |
| Filled-in Issue/SPEC prose an org writes | `output_language` | The CEO reads it |
| CHANGELOG, README, docs/ | **English** | Public surface |

Existing Japanese is being translated incrementally. When you touch a function whose comments are
still Japanese, translate that block as you go — but keep the *content*, especially the field
evidence. A comment that says "実測で12周した" becomes "measured: 12 rounds", not "this was slow".

A short Japanese phrase inside an otherwise-English sentence is acceptable where it names something
the org itself writes in Japanese (a label, an Issue heading). Do not use it for reasoning.

## Do not describe; state the invariant

Comments here explain **why a line must exist**, not what it does. The valuable ones name a failure
that actually happened. Prefer:

    # Retrying exit 2 spent 1.5s of sleep on every tool call: the organs return it for a
    # deliberate ValueError, which a re-run cannot change. Measured 1.90s → 0.24s.

over "retry only transient failures".

## Before you open a PR

```bash
integrations/claude-code/build.sh          # regenerate the bundles
integrations/codex/build.sh
integrations/claude-code/build.sh --check  # both must report in-sync
integrations/codex/build.sh --check
python3 tools/release_check.py             # publishable metadata
python3 -m pytest tests -q -n 8            # ~60s on 8 workers, not 638s serial
```

`build.sh` copies `tools/`, `integrations/common/`, and `template/` into each harness bundle. A new
module that is not synced dies with `ImportError` the moment the plugin is installed, so never skip
the `--check`.

Bump `integrations/claude-code/.claude-plugin/plugin.json` and give the Codex manifest the same base
version plus `+codex.<cachebuster>`. Merging publishable changes without a bump fails the release
job by design — the existing tag is immutable.

## Lines this repository does not cross

- **A tool never decides a verdict.** `verify` assembles material; `gate`/`skeptic` judge. Fixing
  the pass/fail rule mechanically measured 84.6s → 26.2s and **admitted a placebo implementation**.
  Speed there comes from removing judgment (docs/03 §6.5).
- **A check reports absence, not quality.** EARS, DoD command, domain sections, counterexamples —
  each reports what is missing. Whether the content is *good* stays with a human and the gate.
- **Guardrails fail closed.** An organ that errors blocks; it does not allow. `ORG_HOOK_FAIL_OPEN=1`
  is a development escape hatch, never a default.
- **Do not guess a project's layout.** Domain paths, integration refs, and judge harnesses are
  declared in `constitution.yaml`. Four different domain prefixes already coexist across live orgs;
  a guess misfires on all but one.
- **Ship what you measured.** `tools/orgcycle/lens.py` is present but unwired: hand-written review
  lenses measured -25%, the generated ones did not reproduce it, and the difference is unexplained.
  An unexplained speedup does not ship.
