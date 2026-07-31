"""URL-safe slug generation.

Converts an arbitrary string into a URL-safe slug where the only
allowed characters are ASCII [a-z0-9] plus hyphen separators.
"""

import re

# Any run of one-or-more characters that are not ASCII letters or digits.
# Filtering before lowercasing matters: U+212A KELVIN SIGN lowercases to
# ASCII ``k`` and would otherwise cross the explicit ASCII boundary.
_NON_ALNUM_RUN = re.compile(r"[^A-Za-z0-9]+")


def slugify(text):
    """Convert an arbitrary string into a URL-safe slug.

    Rules:
      1. Lowercase the result.
      2. Replace any run of non-alphanumeric characters (ASCII [a-z0-9]
         only; unicode letters like é, ñ count as non-alphanumeric) with
         a single hyphen.
      3. Strip leading/trailing hyphens.
      4. Collapse consecutive hyphens into one (implied by rule 2, since
         runs are replaced by a single hyphen).
      5. Return "n-a" for input that is empty or contains no
         alphanumeric characters.
    """
    # Apply the ASCII boundary to the original code points. Lowercasing first
    # would turn U+212A KELVIN SIGN into ASCII ``k`` and incorrectly keep it.
    hyphenated = _NON_ALNUM_RUN.sub("-", text)

    # Lowercase the retained ASCII characters and strip separator edges.
    slug = hyphenated.lower().strip("-")

    # Empty (or no alphanumeric content) -> "n-a".
    if not slug:
        return "n-a"

    return slug
