"""Pytest suite for slugify.slugify.

Each test maps to a named acceptance case from the contract.
"""

from slugify import slugify


def test_normal_text():
    """Named case: normal text.

    Plain words separated by spaces become lowercase, hyphen-joined.
    """
    assert slugify("Hello World") == "hello-world"
    assert slugify("The Quick Brown Fox") == "the-quick-brown-fox"


def test_unicode_letters_dropped():
    """Named case: unicode letters (e/n dropped per ASCII rule).

    é and ñ are not in ASCII [a-z0-9], so they are treated as
    non-alphanumeric separators and dropped (become hyphens, then
    collapse/strip).
    """
    # "café" -> "caf" + separator(é) at end -> stripped -> "caf"
    assert slugify("café") == "caf"
    # "piñata" -> "pi" + sep(ñ) + "ata" -> "pi-ata"
    assert slugify("piñata") == "pi-ata"
    # "Niño" -> "ni" + sep(ñ) + "o" -> "ni-o"
    assert slugify("Niño") == "ni-o"


def test_leading_trailing_punctuation():
    """Named case: leading/trailing punctuation.

    Punctuation at the ends becomes hyphens then is stripped.
    """
    assert slugify("...Hello...") == "hello"
    assert slugify("!!!Wow!!!") == "wow"
    assert slugify("  spaced out  ") == "spaced-out"


def test_all_symbol_input():
    """Named case: all-symbol input (no alphanumerics) -> 'n-a'."""
    assert slugify("!!!") == "n-a"
    assert slugify("@#$%^&*()") == "n-a"
    assert slugify("---") == "n-a"
    # All-unicode-letters also yields no ASCII alphanumerics -> "n-a".
    assert slugify("éñü") == "n-a"


def test_empty_string():
    """Named case: empty string -> 'n-a'."""
    assert slugify("") == "n-a"


def test_collapse_consecutive_hyphens():
    """Supporting case: runs of separators collapse to a single hyphen."""
    assert slugify("a---b") == "a-b"
    assert slugify("a   b") == "a-b"
    assert slugify("a_+_b") == "a-b"


def test_digits_preserved():
    """Supporting case: ASCII digits are alphanumeric and preserved."""
    assert slugify("Version 2.0") == "version-2-0"
    assert slugify("abc123") == "abc123"
