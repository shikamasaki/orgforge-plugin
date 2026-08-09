#!/usr/bin/env python3
"""req_lint — check that REQUIREMENTS.md conforms to the standard for writing requirements
(docs/11 §0b).

**Why this is needed.** docs/11 §0a fixed the *file names* of the founding artifacts but prescribed
nothing about *the format of their content*. As a result an agent invented the structure afresh at
every founding, and the same requirements produced documents of different structure — the plugin's
central claim (same spec ⇒ same process, same contract) was broken from the start at the layer where
requirements are written. Checking the format mechanically closes that hole.

**Level of conformance: tailored conformance to ISO/IEC/IEEE 29148:2018** (the form of conformance
that standard's §4.5.2 formally recognises). Not all twenty SRS clauses (§9.6) are adopted —
`Memory constraints` and the like are for embedded and defence work, and in a small product they
would only line up empty fields, and a document with empty sections stops being read and stops being
updated. Four clauses are adopted:

  §5.2.4  syntactic rules   — subject + shall. must is not used (it is mistaken for a requirement)
  §5.2.5  each requirement  — Verifiable / Singular / Unambiguous … (nine characteristics)
  §5.2.6  set properties    — no TBD/TBS/TBR left, no contradiction or duplication (five)
  §5.2.7  words to avoid    — subjective, superlative, loophole, and universal words (this tool's
                              core)

To that it adds the six patterns of EARS (Alistair Mavin / Rolls-Royce; adopted by Airbus, NASA,
Bosch, Intel, and Siemens) and the `[NEEDS CLARIFICATION]` marker from GitHub Spec Kit. The last
matters most — **an agent implementing on a guess while things stay ambiguous is the largest failure
mode**, and this mechanically stops the implementation phase from starting with an unresolved marker
still in place.

  req_lint.py check <path/to/REQUIREMENTS.md> [--json] [--warn-only]

Exit: 0 conforms / 10 violations found (the gate should HOLD) / 2 usage or read error
"""
import argparse
import json
import os
import re
import sys

# ── required sections (the skeleton of template/REQUIREMENTS.md) ─────────────
# To absorb variation in how a heading is written, each section is decided by "a heading containing
# any of these words". A strict string match fails on a mix of Japanese and English or on different
# numbering, and would not survive use.
REQUIRED_SECTIONS = [
    ("why",        ["why", "なぜ", "目的", "purpose"]),
    ("goals",      ["goal", "ゴール", "目標"]),
    ("non-goals",  ["non-goal", "non goal", "やらない", "非目標"]),
    ("requirements", ["requirement", "要求", "機能要件"]),
    ("acceptance", ["acceptance", "受入", "受け入れ"]),
    ("success",    ["success criteria", "成功基準", "成功指標"]),
    ("constraints", ["constraint", "制約", "non-functional", "非機能"]),
    ("out-of-scope", ["out of scope", "スコープ外", "除外", "exclude"]),
]

# ── §5.2.7 words to avoid ───────────────────────────────────────────────────
# The words the standard says "shall be avoided". Appearing inside a requirement statement fails it.
# (regex, kind, explanation) — Japanese has no word boundary, so \b is not used for it.
BANNED = [
    (r"\b(best|most|optimal|maximum possible)\b", "superlative",
     "what it is superlative to cannot be verified"),
    (r"(最高の|最適な|最善の|可能な限り)", "superlative",
     "what it is superlative to cannot be verified"),
    (r"\b(user[- ]friendly|easy to use|cost[- ]effective|intuitive|seamless)\b", "subjective",
     "the judgment changes from person to person. Rewrite it as an observable condition"),
    (r"(使いやすい|分かりやすい|わかりやすい|直感的|快適に|スムーズに)", "subjective",
     "the judgment changes from person to person. Rewrite it as an observable condition"),
    (r"\b(almost always|significant|minimal|sufficient|adequate|reasonable)\b", "vague degree",
     "the degree is unsettled. Make it a number or an observable condition"),
    (r"(ほぼ|十分に|適切に|なるべく|できるだけ|柔軟に)", "vague degree",
     "the degree is unsettled. Make it a number or an observable condition"),
    (r"\b(and\s*/\s*or)\b", "vague conjunction", "settle on either and or or"),
    (r"(および/または|かつ/または)", "vague conjunction", "settle on either and or or"),
    (r"\b(etc\.|and so on|but not limited to|as a minimum|provide support for)\b",
     "unverifiable", "the range does not close. Enumerate it fully, or write the boundary"),
    (r"(など|等をサポート|その他)", "unverifiable",
     "the range does not close. Enumerate it fully, or write the boundary"),
    (r"\b(better than|faster than|improved)\b", "comparative",
     "no reference is given. Write what it is compared against, and by how much"),
    (r"(より良い|より速い|改善された)", "comparative", "no reference is given"),
    (r"\b(if possible|as appropriate|if needed|where necessary)\b", "loophole",
     "it becomes an excuse not to implement. Settle the condition"),
    (r"(可能であれば|必要に応じて|状況に応じて)", "loophole",
     "it becomes an excuse not to implement"),
    (r"\b(all|always|never|every|none)\b", "universal",
     "whether exceptions exist has not been verified. Confirm there are none, and write them where "
     "there are"),
    (r"(すべての場合|常に|決して|一切)", "universal",
     "whether exceptions exist has not been verified"),
]

# TBD/TBS/TBR — explicitly forbidden by §5.2.6 Complete
TBX = re.compile(r"\b(TBD|TBS|TBR)\b")

# §5.2.4 — `must` is not used, because it is mistaken for a requirement
MUST_KEYWORD = re.compile(r"\bmust\b", re.I)

# The six EARS patterns (both English and Japanese are accepted).
# The Japanese equivalent of shall. 「〜すること」 alone is not enough — a real requirement statement
# ends with an attributive verb plus 「こと」, as in 「記録に残すこと」, 「対象に含めないこと」, or
# 「リマインダーを送ること」.
# Limiting it to 「すること」 rejects most correctly-written requirements as violations (found in the
# field).
EARS_PATTERNS = [
    (r"\bshall\b", "shall"),
    (r"こと(\s*\||\s*$|。)", "shall(ja: 〜こと)"),
    (r"(しなければならない|するものとする|してはならない)", "shall(ja)"),
]
EARS_TRIGGERS = [r"\bwhile\b", r"\bwhen\b", r"\bwhere\b", r"\bif\b",
                 r"(のとき|の場合|している間|ならば)"]

CLARIFY = re.compile(r"\[NEEDS[ _]CLARIFICATION[^\]]*\]", re.I)
# Requirement IDs in the FR-001 form. Allowed at the start of a line or inside a table cell
REQ_ID = re.compile(r"\bFR-\d{3,}\b")
SC_ID = re.compile(r"\bSC-\d{3,}\b")


# Nothing from the appendix (the review checklist) onward is checked. The banned words themselves
# line up there as "examples", so checking it always fails — this avoids the absurdity of a document
# that states the rules violating them.
APPENDIX = re.compile(r"^#{1,6}\s*(付録|appendix|レビューチェックリスト)", re.M | re.I)


def _strip_noise(text):
    """Return only the body to be checked. Three things are removed:

    1. **quotes (`> ...`)** — the template's commentary, which contains explanations of EARS and of
       the banned words
    2. **code blocks** — illustrations of notation
    3. **everything from the appendix onward** — the banned-word list itself lines up there

    Checking these means the better a document explains the rules, the more violations it has. What
    should be checked is *the requirement statements the author wrote*, and nothing else."""
    m = APPENDIX.search(text)
    if m:
        text = text[:m.start()]
    out, in_code = [], False
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or s.startswith(">"):
            continue
        out.append(line)
    return "\n".join(out)


def _sections(text):
    """Return the headings (# through ######) in lower case."""
    return [m.group(1).strip().lower()
            for m in re.finditer(r"^#{1,6}\s+(.+)$", text, flags=re.M)]


# The acceptance-criteria section is written in Given-When-Then (not EARS). It references FR-xxx and
# so gets mistaken for a requirement statement, but the different notation is correct — requirements
# in EARS, the scenarios that verify them in GWT.
GWT = re.compile(r"\b(given|when|then)\b", re.I)
ACCEPTANCE_HEAD = re.compile(r"^#{1,6}.*(acceptance|受入|受け入れ)", re.M | re.I)
NEXT_HEAD = re.compile(r"^#{1,6}\s", re.M)


def _acceptance_span(text):
    """Return the line-number range (start, end) of the acceptance-criteria section, or (0, 0)."""
    m = ACCEPTANCE_HEAD.search(text)
    if not m:
        return (0, 0)
    start = text[:m.start()].count("\n") + 1
    nxt = NEXT_HEAD.search(text, m.end())
    end = (text[:nxt.start()].count("\n") + 1) if nxt else text.count("\n") + 2
    return (start, end)


def _requirement_lines(text):
    """The lines taken to be requirement statements: a line containing FR-xxx, or a table row
    containing shall (or its Japanese equivalent).

    Excluded: headings (a section title can carry FR-001), anything inside the acceptance-criteria
    section (GWT is the correct notation there, and having no shall is not a violation), and lines
    containing a GWT keyword."""
    a_start, a_end = _acceptance_span(text)
    lines = []
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if a_start <= i < a_end:          # inside the acceptance section: out of scope
            continue
        if GWT.search(line) and not re.search(r"\bshall\b", line, re.I):
            continue                       # a GWT scenario line
        # Distinguish a line that "defines" a requirement ID from one that merely "references" it.
        # A constraints table or an EXCLUDE table references (FR-021) as grounds, but is not itself a
        # requirement statement. A defining line always carries the ID in its first cell
        # (`| FR-001 | …`), so that is what decides it.
        cells = [c.strip() for c in s.strip("|").split("|")] if s.startswith("|") else []
        defines = bool(cells) and bool(REQ_ID.match(cells[0].replace("**", "")))
        if defines or (s.startswith("|") and not cells[0:1]
                       and any(re.search(p, line, re.I) for p, _ in EARS_PATTERNS)):
            lines.append((i, line))
    return lines


def check(path):
    """Check, and return the list of violations. Each is {code, severity, line, message}."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    body = _strip_noise(raw)
    v = []

    # SEC — the required sections (a tailoring of the equivalent of §9)
    heads = " || ".join(_sections(raw))
    for key, aliases in REQUIRED_SECTIONS:
        if not any(a in heads for a in aliases):
            v.append({"code": "SEC", "severity": "error", "line": 0,
                      "message": f"the required section '{key}' is missing (a heading such as "
                                 f"{'/'.join(aliases[:2])})"})

    reqs = _requirement_lines(body)

    # REQ — a document with no requirements at all is not a statement of requirements
    if not reqs:
        v.append({"code": "REQ", "severity": "error", "line": 0,
                  "message": "there is not one requirement statement. Number them in the FR-001 "
                             "form and write them in EARS"})

    # EARS — does each requirement statement carry shall (or its Japanese equivalent)?
    for ln, line in reqs:
        if not any(re.search(p, line, re.I) for p, _ in EARS_PATTERNS):
            v.append({"code": "EARS", "severity": "error", "line": ln,
                      "message": f"the requirement statement has no shall (in Japanese, "
                                 f"\u300c\u301c\u3059\u308b\u3053\u3068\u300d): "
                                 f"{line.strip()[:70]}"})
        # Two or more triggers = an EARS ruleset violation (at most one trigger). A sign the
        # granularity is coarse
        hits = sum(1 for p in EARS_TRIGGERS if re.search(p, line, re.I))
        if hits >= 3:
            v.append({"code": "EARS-1T", "severity": "warn", "line": ln,
                      "message": f"too many triggers/conditions (the EARS ruleset allows at most "
                                 f"one trigger). Split the requirement: {line.strip()[:60]}"})

    # MUST — §5.2.4, "must is avoided because it is mistaken for a requirement"
    for i, line in enumerate(body.split("\n"), 1):
        if MUST_KEYWORD.search(line) and not line.strip().startswith("#"):
            v.append({"code": "MUST", "severity": "warn", "line": i,
                      "message": "`must` is not used (29148 §5.2.4). A requirement is `shall`, a "
                                 "preference `should`, a permission `may`"})
            break   # reporting one is enough (reporting every line becomes noise)

    # BAN — §5.2.7, the words to avoid
    for i, line in enumerate(body.split("\n"), 1):
        if line.strip().startswith("#") or not line.strip():
            continue
        for rx, kind, why in BANNED:
            m = re.search(rx, line, re.I)
            if m:
                v.append({"code": "BAN", "severity": "error", "line": i,
                          "message": f"{kind} '{m.group(0)}' — {why} (29148 §5.2.7)"})
                break   # one per line (several findings on one line are noise)

    # TBX — §5.2.6 Complete explicitly forbids TBD/TBS/TBR
    for i, line in enumerate(body.split("\n"), 1):
        if TBX.search(line):
            v.append({"code": "TBX", "severity": "error", "line": i,
                      "message": "a TBD/TBS/TBR is still here (29148 §5.2.6 Complete). Settle it, "
                                 "or move it to Open Questions"})

    # CLARIFY — an unresolved [NEEDS CLARIFICATION] (from Spec Kit; the most important)
    for i, line in enumerate(body.split("\n"), 1):
        if CLARIFY.search(line):
            v.append({"code": "CLARIFY", "severity": "error", "line": i,
                      "message": "an unresolved [NEEDS CLARIFICATION] is still here. Resolve it "
                                 "before implementation, so nothing gets implemented on a guess"})

    # VOIDDEP (QUS's Complete) **went in at 0.25.0 and was withdrawn at 0.25.1.**
    #
    # The formalisation itself is right — "to read, update or delete an item one first needs to
    # create it". The problem was that **the object cannot be extracted mechanically** from
    # requirements written in Japanese. The implementation read backtick identifiers, and a
    # REQUIREMENTS.md in the field held **zero** of them. Writing with ordinary nouns, as in
    # 「利用者が表示名を変更したとき」, is natural Japanese, and the template has it written that way
    # too. An implementation splitting on particles to pick up 「〜を<verb>」 was tried as well, and
    # `利用者が支出` and `メンバーが支出` came out as different things, making **every finding a
    # false positive**.
    # Morphological analysis would reach it, but adopting that is a decision that changes req_lint's
    # weight by a whole step.
    #
    # A check that only produces false positives is worse than none (a false warning voids the
    # correct warnings too).
    # The aim (catching a missing requirement) is served by `github_sync split-check`'s "does the
    # authorization set only the boundary", which works on real data, so it leans on that instead.
    # Attempting it again presupposes **requirements in English, or a notation that mandates
    # identifiers**.

    # SC — are the success criteria numbered?
    if not SC_ID.search(body):
        v.append({"code": "SC", "severity": "warn", "line": 0,
                  "message": "the success criteria are not numbered in the SC-001 form "
                             "(technology-independent and quantitative)"})

    return v


def cmd_check(a):
    if not os.path.isfile(a.path):
        print(f"req_lint: there is no {a.path}. Check whether /org-found wrote REQUIREMENTS.md",
              file=sys.stderr)
        return 2
    try:
        v = check(a.path)
    except OSError as e:
        print(f"req_lint: cannot read it: {e}", file=sys.stderr)
        return 2
    errors = [x for x in v if x["severity"] == "error"]
    warns = [x for x in v if x["severity"] == "warn"]
    if a.json:
        print(json.dumps({"path": a.path, "passed": not errors,
                          "errors": len(errors), "warnings": len(warns),
                          "violations": v}, ensure_ascii=False, indent=2))
    else:
        print(f"checking how the requirements are written — {a.path}")
        print("  (ISO/IEC/IEEE 29148:2018 tailored conformance + EARS, docs/11 §0b)")
        if not v:
            print("\nconforms. The required sections, EARS, and the banned words are all clean.")
        for x in v:
            mark = "✗" if x["severity"] == "error" else "▲"
            loc = f"L{x['line']}" if x["line"] else "—"
            print(f"  {mark} [{x['code']}] {loc}: {x['message']}")
        if errors:
            print(f"\nHELD: {len(errors)} violation(s). Enter implementation with the requirements "
                  f"still ambiguous and the agent fills the gaps by guessing — that is the largest "
                  f"failure mode.")
        elif warns:
            print(f"\nOK ({len(warns)} warning(s)).")
    if a.warn_only:
        return 0
    return 10 if errors else 0


def main(argv):
    p = argparse.ArgumentParser(prog="req_lint", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("check")
    q.add_argument("path", nargs="?", default="REQUIREMENTS.md",
                   help="path to the requirements document (default: REQUIREMENTS.md)")
    q.add_argument("--json", action="store_true")
    q.add_argument("--warn-only", action="store_true",
                   help="exit 0 even with violations (for the drain early after adoption; "
                        "docs/11 §4e)")
    a = p.parse_args(argv[1:])
    return {"check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
