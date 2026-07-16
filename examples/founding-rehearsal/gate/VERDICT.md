# GATE VERDICT: slugify submission

**Verdict: ADMIT**

Checker: gate department (independent authorization/checker role). I did not
author this work; I judged it independently and re-ran everything in a fresh
context under `/tmp/founding-rehearsal/workdir-gate/`.

---

## 1. Independent pytest result (forward test)

I copied `slugify.py` and `test_slugify.py` into my own working directory and
ran pytest myself. I did NOT rely on the maker's claim.

Command:

```
cd /tmp/founding-rehearsal/workdir-gate && python3 -m pytest -v
```

Output:

```
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: /private/tmp/founding-rehearsal/workdir-gate
collecting ... collected 7 items

test_slugify.py::test_normal_text PASSED                                 [ 14%]
test_slugify.py::test_unicode_letters_dropped PASSED                     [ 28%]
test_slugify.py::test_leading_trailing_punctuation PASSED                [ 42%]
test_slugify.py::test_all_symbol_input PASSED                            [ 57%]
test_slugify.py::test_empty_string PASSED                                [ 71%]
test_slugify.py::test_collapse_consecutive_hyphens PASSED                [ 85%]
test_slugify.py::test_digits_preserved PASSED                            [100%]

============================== 7 passed in 0.03s ===============================
```

**Result: 7 passed, 0 failed.** The suite actually runs and passes.

---

## 2. Case-by-case coverage check (each named acceptance case)

I read the test file line-by-line; I did not merely trust the test count. Each
named case has a real assertion with a meaningful, non-trivial expected value.

| # | Named acceptance case | Covered? | Which test | Real assertion(s) |
|---|---|---|---|---|
| 1 | normal text | YES | `test_normal_text` | `"Hello World"` → `"hello-world"`; `"The Quick Brown Fox"` → `"the-quick-brown-fox"` |
| 2 | unicode letters (é/ñ non-alphanumeric per ASCII rule) | YES | `test_unicode_letters_dropped` | `"café"` → `"caf"`; `"piñata"` → `"pi-ata"`; `"Niño"` → `"ni-o"` |
| 3 | leading/trailing punctuation | YES | `test_leading_trailing_punctuation` | `"...Hello..."` → `"hello"`; `"!!!Wow!!!"` → `"wow"`; `"  spaced out  "` → `"spaced-out"` |
| 4 | all-symbol input (no alphanumerics) | YES | `test_all_symbol_input` | `"!!!"`, `"@#$%^&*()"`, `"---"`, `"éñü"` → all `"n-a"` |
| 5 | empty string | YES | `test_empty_string` | `""` → `"n-a"` |

Supporting tests (`test_collapse_consecutive_hyphens`, `test_digits_preserved`)
exercise rule 4 collapse and digit preservation; both are genuine, not padding.

**No named case is missing. No test is fake or trivial.** Each expected value is
the true output the spec demands, not a tautology.

---

## 3. Requirements satisfaction (verified by direct execution, not via tests)

I imported `slugify` and exercised it directly to confirm the implementation
itself (not just the maker's tests) satisfies all 5 requirements:

| Req | Requirement | Probe | Result | OK |
|---|---|---|---|---|
| 1 | lowercase | `"HELLO"` | `"hello"` | YES |
| 2 | runs of non-[a-z0-9] → single hyphen (unicode letters count as non-alnum) | `"piñata"` | `"pi-ata"` | YES |
| 3 | strip leading/trailing hyphens | `"...Hello..."` | `"hello"` | YES |
| 4 | collapse consecutive hyphens | `"a---b"`, `"a_+_b"` | `"a-b"` | YES |
| 5 | "n-a" for empty / no-alphanumeric | `""`, `"@#$%^&*()"`, `"éñü"` | `"n-a"` | YES |

Implementation is a clean, correct realization: lowercase → `re.sub(r"[^a-z0-9]+", "-", ...)`
→ `strip("-")` → `"n-a"` fallback. Lowercasing before the regex correctly lets
ASCII uppercase survive while unicode letters fall outside `[a-z0-9]`. Rule 2's
`+` quantifier inherently collapses consecutive separators, so rule 4 is
satisfied by construction. No bugs found.

---

## 4. Ruling on the unicode-interpretation ambiguity

**The maker flagged (SUBMISSION.md "Honest note"):** whether a unicode letter
(é/ñ) acts as a *separator* that produces a hyphen (their reading:
`piñata` → `pi-ata`), versus being *deleted* with adjacent segments joined
(alternative: `piñata` → `piata`).

**RFP rule 2 wording:** "replace any run of non-alphanumeric characters with a
single hyphen."

**RULING: The maker's interpretation is CORRECT and is the more literal reading
of the RFP. Upheld.**

Justification, grounded in the RFP text:

- Rule 2 defines the mechanism as *replace with a hyphen*, not *delete*. There
  is no rule anywhere in the spec that authorizes deleting a character and
  joining the neighbors; the only transformation offered for non-alphanumeric
  content is hyphen-replacement.
- The RFP explicitly establishes (acceptance criterion 3, restating rule 2) that
  é and ñ are to be "treated as non-alphanumeric per ASCII rule." A character
  that is non-alphanumeric is, by rule 2's own words, part of "a run of
  non-alphanumeric characters" and must therefore be "replaced with a single
  hyphen."
- Therefore an *internal* unicode letter sits between two alphanumeric segments
  and becomes a single hyphen: `piñata` → `pi-ata`. A *trailing/leading* one
  becomes a hyphen that rule 3 then strips: `café` → `caf`. Both outputs follow
  directly from applying rules 2 and 3 in sequence.
- The "delete-and-join" alternative (`piata`) would require a deletion rule the
  RFP does not contain. It is the less defensible reading.

The word "dropped" in the informal case list is loose shorthand; where it
conflicts with the operative rule-2 mechanism, **rule 2 governs.** The maker
correctly identified rule 2 as controlling and applied it faithfully.

This is precisely the interpretive judgment the gate exists to make, and it
resolves in the maker's favor.

---

## 5. Conditions / notes

- No conditions. Admitted as-is.
- Minor terminology note (non-blocking): the test name
  `test_unicode_letters_dropped` and SUBMISSION's use of "dropped" are slightly
  misleading — internal unicode letters are not dropped, they become a hyphen
  (`pi-ata`), which is correct behavior. The wording could be tightened to
  "unicode letters treated as separators," but the behavior and assertions are
  right, so this does not affect admission.
- Environment: Python 3.9.6, pytest 8.4.2 (matches maker's reported environment;
  reproduced independently).

**FINAL: ADMIT.**
