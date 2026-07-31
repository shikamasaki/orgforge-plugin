# Submission: slugify (miner department)

Status: SUBMITTED (not admitted). Independent gate must re-run.

## What I built

- `slugify.py` — `slugify(text)` producing a URL-safe slug. Implementation:
  replace every run outside ASCII `[A-Za-z0-9]` with one hyphen, lowercase
  the retained ASCII characters, strip leading/trailing hyphens, and return
  `"n-a"` when nothing alphanumeric remains. Filtering before lowercasing
  prevents Unicode characters such as U+212A from folding into the allowed
  ASCII set.
- `test_slugify.py` — pytest suite (7 tests).

## Acceptance case -> test mapping

| Named acceptance case | Test function |
|---|---|
| normal text | `test_normal_text` |
| unicode letters (é/ñ dropped per ASCII rule) | `test_unicode_letters_dropped` |
| leading/trailing punctuation | `test_leading_trailing_punctuation` |
| all-symbol input (no alphanumerics) -> "n-a" | `test_all_symbol_input` |
| empty string -> "n-a" | `test_empty_string` |
| (rule 4) collapse consecutive hyphens | `test_collapse_consecutive_hyphens` |
| (supporting) ASCII digits preserved | `test_digits_preserved` |

All five named cases are covered; the last two are supporting tests for
rules 4 (collapse) and digit handling.

## My pytest result

`python3 -m pytest -v` → 7 passed in 0.04s (pytest 8.4.2, Python 3.9.6).

## Honest note

The contract says é/ñ are "dropped," which the tests interpret as: the
unicode letter becomes a separator, so it contributes a hyphen that then
collapses/strips (e.g. `café` -> `caf`, `piñata` -> `pi-ata`). If the gate
intends "dropped" to mean deleted with adjacent segments joined
(`piñata` -> `piata`), that is a spec-interpretation difference, not a bug
in the collapse/strip logic — I read "replace any run of non-alphanumeric
with a single hyphen" (rule 2) as governing, and unicode letters are
explicitly non-alphanumeric under the ASCII rule.
