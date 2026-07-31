"""Adversarial test suite attacking maker's slugify.py.

Each test derives the EXPECTED output strictly from the 5 requirements:
  (1) lowercase
  (2) runs of non-[a-z0-9] (unicode letters count as non-alnum) -> single hyphen
  (3) strip leading/trailing hyphens
  (4) collapse consecutive hyphens
  (5) "n-a" for empty or no-alphanumeric input

Where a case exposes a possible spec violation, it is marked ATTACK.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "miner"))

from slugify import slugify


# ---- whitespace variants (tabs, newlines, CR) ----
def test_tabs_newlines():
    assert slugify("a\tb") == "a-b"
    assert slugify("a\nb") == "a-b"
    assert slugify("a\r\nb") == "a-b"
    assert slugify("\t\n hello \n\t") == "hello"


# ---- already-hyphenated / mixed separator runs ----
def test_already_hyphenated():
    assert slugify("a-b-c") == "a-b-c"
    assert slugify("a - b") == "a-b"
    assert slugify("--a--b--") == "a-b"
    assert slugify("a-_- b") == "a-b"  # mixed unicode+punct-ish run


# ---- numeric-only ----
def test_numeric_only():
    assert slugify("12345") == "12345"
    assert slugify("1 2 3") == "1-2-3"


# ---- very long run of symbols between two letters ----
def test_long_symbol_run():
    assert slugify("a" + "!@#$%^&*()" * 50 + "b") == "a-b"


# ---- whitespace-only input -> req 5 ----
def test_whitespace_only():
    assert slugify("   ") == "n-a"
    assert slugify("\t\n\r ") == "n-a"


# ---- ATTACK: "n/a" sentinel collision ----
# "n/a": 'n' alnum, '/' non-alnum -> hyphen, 'a' alnum. Per spec -> "n-a".
# This legitimately collides with the empty-input sentinel, but per spec
# "n-a" IS the correct output here, so it should pass.
def test_na_slash_collision():
    assert slugify("n/a") == "n-a"
    assert slugify("N/A") == "n-a"


# ---- ATTACK: uppercase unicode case-folding to ASCII? ----
# 'É'.lower() == 'é' (still non-ASCII) -> separator. Fine.
def test_uppercase_unicode():
    assert slugify("CAFÉ") == "caf"
    assert slugify("PIÑATA") == "pi-ata"


# ---- ATTACK: German sharp S. 'ß'.lower() == 'ß' (non-ASCII) -> separator.
def test_sharp_s():
    # "straße" -> "stra" + sep(ß) + "e" -> "stra-e"
    assert slugify("straße") == "stra-e"


# ---- ATTACK: Turkish dotless / dotted I via .lower() ----
# Python str.lower() is locale-independent: 'I'.lower() == 'i' (ASCII). Fine.
def test_turkish_i_plain_lower():
    assert slugify("ISTANBUL") == "istanbul"


# ---- ATTACK: ligature that lowercases to multiple ASCII letters? ----
# 'ﬀ' (U+FB00) is already lowercase; .lower() leaves it unchanged (non-ASCII)
# -> it is a separator, NOT expanded to "ff".
def test_ligature_not_expanded():
    # "aﬀb" -> "a" + sep + "b" -> "a-b"
    assert slugify("aﬀb") == "a-b"


# ---- ATTACK: Unicode digits (non-ASCII) must be treated as non-alnum ----
# '²' superscript two, '٣' arabic-indic three, '½' fraction: none in [0-9].
def test_unicode_digits_are_separators():
    assert slugify("a²b") == "a-b"
    assert slugify("a٣b") == "a-b"      # arabic-indic digit
    assert slugify("x½y") == "x-y"


# ---- ATTACK: fullwidth ASCII letters (U+FF21 etc.) ----
# 'Ａ' fullwidth A -> .lower() -> 'ａ' (U+FF41), NOT ASCII 'a' -> separator.
def test_fullwidth_letters():
    # "Ａb" -> sep(Ａ) + "b" -> stripped -> "b"
    assert slugify("Ａb") == "b"


# ---- ATTACK: input that is ALREADY "n-a" ----
def test_already_na():
    assert slugify("n-a") == "n-a"
    assert slugify("n_a") == "n-a"


# ---- ATTACK: emoji / astral plane ----
def test_emoji():
    assert slugify("hi😀there") == "hi-there"
    assert slugify("😀😀😀") == "n-a"


# ---- ATTACK: single alnum char surrounded by junk ----
def test_single_char():
    assert slugify("---a---") == "a"
    assert slugify("...5...") == "5"


# ---- REFUTATION: Unicode letter that case-folds INTO ASCII [a-z0-9] ----
# U+212A KELVIN SIGN is a Unicode uppercase LETTER (category Lu). Per req 2,
# unicode letters count as non-alphanumeric and must become a hyphen. The
# original implementation lowercased first and leaked U+212A as ASCII ``k``.
# This regression stays in the ordinary passing suite after the correction.
def test_kelvin_sign_is_a_separator():
    assert slugify("aKb") == "a-b"
    assert slugify("K") == "n-a"
    assert slugify("temp K") == "temp"


# ---- ATTACK: non-breaking space / zero-width chars ----
def test_special_spaces():
    assert slugify("a b") == "a-b"   # nbsp
    assert slugify("a​b") == "a-b"   # zero-width space (non-alnum)
