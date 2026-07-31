# SKEPTIC REFUTATION: slugify submission

**Verdict: REFUTED (one genuine spec violation found)**

> **Resolved in 1.0.0:** the implementation now applies `[^A-Za-z0-9]+` to
> the original code points before lowercasing. The Kelvin-sign attack is an
> ordinary passing regression test; no `xfail` remains. The analysis below is
> retained as the historical evidence that caused the correction.

Skeptic department (adversarial checker). I am a different agent from both the
maker and the gate. I read `slugify.py`, derived expected outputs strictly from
the 5 requirements, wrote my own adversarial suite
(`/tmp/founding-rehearsal/workdir-skeptic/attack_test.py`), and ran it against
the maker's implementation. 16 of 17 attacks were survived cleanly; one attack
exposes a real requirement-2 violation that the maker's test suite never probes.

---

## The genuine defect

**Requirement violated: (2)** — "runs of non-[a-z0-9] (unicode letters é/ñ count
as non-alphanumeric) → single hyphen."

| Field | Value |
|---|---|
| Reproducing input | `"a" + "K" + "b"` (U+212A KELVIN SIGN between two ASCII letters) |
| Character identity | `unicodedata.name` = `KELVIN SIGN`, `category` = `Lu` (Unicode uppercase **letter**) |
| Expected per spec | `"a-b"` — it is a unicode letter, not in ASCII `[a-z0-9]`, so req 2 makes it a hyphen separator |
| Original output | `"akb"` — the unicode letter leaked through as an alphanumeric |
| Original reproductions | `slugify("K")` → `"k"` (spec: `"n-a"`, no ASCII alnum); `slugify("temp K")` → `"temp-k"` (spec: `"temp"`) |

### Root cause

`slugify` lowercases **before** applying the `[^a-z0-9]+` regex:

```python
lowered = text.lower()                       # <-- U+212A .lower() == ASCII 'k'
hyphenated = _NON_ALNUM_RUN.sub("-", lowered)
```

The gate's admission explicitly rests on the claim: *"Lowercasing before the
regex correctly lets ASCII uppercase survive while unicode letters fall outside
[a-z0-9]."* That claim has exactly one counterexample. I exhaustively scanned
all code points U+0080–U+10FFFF for non-ASCII characters whose `.lower()` is
entirely ASCII-alphanumeric. **There is exactly one: U+212A KELVIN SIGN**, which
folds to ASCII `k`. (`str.lower()`, being locale-independent full case folding
for this codepoint, maps K → k.) For this single character the "unicode letters
fall outside [a-z0-9]" invariant is false: it is a unicode letter that lands
*inside* [a-z0-9] after lowering, so it is preserved instead of hyphenated.

### Why the gate missed it (coverage gap)

The maker's suite tests unicode letters é, ñ, ü, ß — all of which lowercase to
*non-ASCII* and therefore behave as separators. It never tests a unicode letter
that case-folds *into* ASCII. So the suite passes while req 2 is violated for
U+212A. The gate re-ran the suite and reasoned about é/ñ, but did not probe the
lower()-into-ASCII class, so the gap propagated into the ADMIT.

### Severity note (honest)

This is a real but narrow correctness bug. U+212A is rare in practice (the
ordinary letter "K" is U+004B and is handled correctly). A spec-faithful fix is
to normalize/restrict to ASCII before or independently of lowering — e.g.
`text.encode("ascii", "ignore")`-style filtering, or apply the non-alnum regex
against the original casing using an explicit `[^A-Za-z0-9]+` and lowercase
afterward. Under a literal reading of requirement 2, though, the current output
`"akb"`/`"k"`/`"temp-k"` was wrong, so the original admission was refuted.

---

## Attacks the implementation SURVIVED (reported honestly)

All of the following produced spec-correct output — no defect:

- Tabs / newlines / CR (`"a\tb"`, `"a\nb"`, `"a\r\nb"`) → `"a-b"`
- Already-hyphenated and mixed separator runs (`"--a--b--"` → `"a-b"`, `"a-_- b"` → `"a-b"`)
- Numeric-only (`"12345"`, `"1 2 3"` → `"1-2-3"`)
- Very long symbol run (500 symbols between two letters) → `"a-b"`
- Whitespace-only input → `"n-a"` (req 5)
- **`"n/a"` / `"N/A"` sentinel-collision probe → `"n-a"`** — collides with the
  empty sentinel, but per spec `"n-a"` IS the correct output here, so it is not
  a defect. (Strongest *non-breaking* edge case: the sentinel is ambiguous by
  design, but the spec does not forbid the collision.)
- Uppercase unicode (`"CAFÉ"` → `"caf"`, `"PIÑATA"` → `"pi-ata"`)
- German sharp-s (`"straße"` → `"stra-e"`)
- Turkish/plain `.lower()` (`"ISTANBUL"` → `"istanbul"`)
- Ligature not expanded (`"aﬀb"` → `"a-b"`; ﬀ stays a separator, not "ff")
- Non-ASCII digits treated as separators (`"a²b"`, `"a٣b"`, `"x½y"` → `"a-b"`/`"x-y"`)
- Fullwidth letters (`"Ａb"` → `"b"`; Ａ lowercases to non-ASCII ａ, a separator)
- Input already equal to `"n-a"` / `"n_a"` → `"n-a"`
- Emoji / astral (`"hi😀there"` → `"hi-there"`, `"😀😀😀"` → `"n-a"`)
- NBSP / zero-width space → `"a-b"`

Original suite result: `16 passed, 1 xfailed`. Current suite result: all 17
skeptic attacks pass, including the U+212A regression.

---

## Bottom line

**REFUTED.** The implementation is correct on every ordinary and near-ordinary
input, and the gate's ADMIT is defensible for the cases it examined. But there
exists a concrete input — `"aKb"` (Kelvin sign) — where the implementation
violates requirement 2, producing `"akb"` where the spec demands `"a-b"`. It is
the unique counterexample to the very "lowercase-first is safe" invariant the
gate relied on, and the maker's test suite has no coverage for the
lower()-into-ASCII class of unicode letters.

The correction reverses that order and adds the missing maker and skeptic
coverage. The historical gate verdict remains evidence of what the independent
skeptic caught; it is not the current implementation status.
