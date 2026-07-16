"""URL-safe slug generation.

Converts an arbitrary string into a URL-safe slug where the only
allowed characters are ASCII [a-z0-9] plus hyphen separators.
"""

import re

# Any run of one-or-more characters that are NOT ASCII lowercase
# letters or digits. Because we lowercase first, uppercase ASCII
# letters become lowercase and pass through; unicode letters (é, ñ,
# etc.) are NOT in [a-z0-9] and are therefore treated as separators.
_NON_ALNUM_RUN = re.compile(r"[^a-z0-9]+")


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
    # Lowercase first so ASCII uppercase letters survive while unicode
    # letters remain outside the [a-z0-9] set.
    lowered = text.lower()

    # Replace every run of non-[a-z0-9] characters with a single hyphen.
    # This simultaneously collapses consecutive separators.
    hyphenated = _NON_ALNUM_RUN.sub("-", lowered)

    # Strip leading/trailing hyphens.
    slug = hyphenated.strip("-")

    # Empty (or no alphanumeric content) -> "n-a".
    if not slug:
        return "n-a"

    return slug
