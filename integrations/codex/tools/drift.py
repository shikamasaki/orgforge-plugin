#!/usr/bin/env python3
"""drift — count the common factors across reasons for refusal. **It does not judge.**

## Why per-item checks are not enough on their own

Every check orgforge runs (gate / skeptic / repro_lint / intake) is a **per-item judgment**. Each
may be working correctly and still nobody is asking "there were 18 rejects tonight — what do their
reasons have in common?" **If 18 fell to the same factor, what needs fixing is not 18 deliverables
but whatever is producing that factor: the instructions, the spec, the conventions.**

In resilience-engineering terms, this digs out the gap between **work-as-imagined and
work-as-done** — not by tracing individual causation, but by decomposing everyday variation into
factors and looking at what they share. This command produces that material; **how to fix it is the
supervisor's decision.**

## The ledger alone cannot count it

The payload of `admission_decided` / `refutation_attempted` carries only `reasoning_sha256` — a
hash — and **the prose of the why exists solely in an Issue comment**. So the ledger settles which
Issue fell how many times, and the reason itself is read from the Issue. Looking only at the ledger
and claiming to have counted reasons is not possible — and not claiming to have counted what cannot
be counted is part of this tool's job.
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# The factors a refusal falls into. Cut by **the shape of the gap, not the defect in the
# deliverable**: not "there are no tests" but "it satisfied the MUST's wording while betraying its
# intent" — a grain at which the instructions or the spec can actually be changed. Anything coarser
# is not material to act on.
# The patterns themselves keep their Japanese alternatives: they match the prose a judge wrote, and
# this org's judges write Japanese. That is INPUT matching, not source language.
_FACTORS = (
    ("intent vs wording",
     r"文言(?:だけ|のみ)|意図を裏切|placebo|プラセボ|形だけ|体裁|見せかけ|"
     r"満たしているように見え|字面"),
    ("asserted without measuring",
     r"未測定|測っていな|計測していな|再導出できな|確認していな|検証していな|"
     r"実行していな|エビデンスが無|証跡が無"),
    ("missing foundation (nothing can be built on it)",
     r"依存(?:関係)?が無|インストールされていな|package\.json に無|"
     r"環境が無|設定が無|後続|土台|基盤が"),
    ("out of scope, or missed within it",
     r"範囲外|スコープ外|out_of_scope|MUST の一部|漏れ|抜け落ち|含まれていな"),
    ("not reproducible",
     r"再現できな|repro|手順が無|同じ結果にならな|環境依存"),
    ("broke something that worked",
     r"回帰|regression|既存の.*壊|落ちるようになった|失敗するようになった"),
    ("permission and authorisation",
     r"RLS|認可|権限|policy|ポリシー|漏洩|他人の|越境"),
    ("escaping the type or static check",
     r"ignoreBuildErrors|any 型|as any|@ts-|型を逃|typecheck を"),
)


def _sh(cmd):
    try:
        pr = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return pr.stdout if pr.returncode == 0 else ""
    except Exception:
        return ""


def _ledger_rejections(window_days):
    """Collect (issue, class, verdict, actor, ts) from the ledger. Corrected records are not
    counted."""
    from discover import ledger_root
    from ledger import voided_seqs
    root = ledger_root()
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        print("cannot find the ledger. Run this from the org root.", file=sys.stderr)
        return None
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = voided_seqs(evs)
    out = []
    for e in evs:
        if e.get("seq") in voided:
            continue
        if e.get("class") not in ("admission_decided", "refutation_attempted"):
            continue
        pl = e.get("payload") or {}
        if pl.get("verdict") not in ("reject", "refuted"):
            continue
        iss = pl.get("issue") or pl.get("deliverable")
        if iss is None:
            continue
        out.append({"issue": str(iss).lstrip("#"), "class": e["class"],
                    "verdict": pl["verdict"], "actor": e.get("actor"),
                    "ts": e.get("ts"), "seq": e.get("seq"),
                    "lineage": pl.get("lineage")})
    return out


def _issue_reasons(issue):
    """Extract **only the reason for the judgment** from an Issue's comments — the part the ledger
    does not hold.

    Never concatenate the comments and run the regex over the lot. It picks up the maker's report,
    the rework instruction and the supervisor's notes as well, and **four of the eight factors come
    out matching every Issue, so the distribution disappears** (measured — the first implementation
    did exactly that). A judgment comment has the structure

        ## ⛔ admission_decided — `reject`
        **Why (the reasoning):**   ← the reason is here
        **Evidence consulted:**    ← from here on it is a different matter

    so only the `Why` section is cut out. **Never match by full-text search something that has a
    structure.**
    """
    raw = _sh(["gh", "issue", "view", str(issue), "--json", "comments"])
    if not raw:
        return []
    try:
        cs = (json.loads(raw) or {}).get("comments") or []
    except Exception:
        return []
    hits = []
    for c in cs:
        b = c.get("body") or ""
        # only those carrying a judgment comment's heading
        if not re.search(r"^##\s*\S*\s*(?:admission_decided|refutation_attempted)\s*—\s*`?"
                         r"(?:reject|refuted)`?", b, re.I | re.M):
            continue
        m = re.search(r"\*\*Why[^*]*\*\*\s*\n(.*?)(?=\n\*\*[A-Z]|\n##\s|\Z)",
                      b, re.S)
        if m:
            hits.append(m.group(1).strip())
    return hits


def cmd_factors(a):
    rows = _ledger_rejections(a.window)
    if rows is None:
        return 3
    if not rows:
        print("the ledger holds no refusals or refutations. There is nothing to count.")
        return 0

    by_issue = {}
    for r in rows:
        by_issue.setdefault(r["issue"], []).append(r)

    print(f"— {len(rows)} refusal(s)/refutation(s) across {len(by_issue)} Issue(s)")
    print(f"  The ledger holds the fact of the judgment and reasoning_sha256, no further. "
          f"**The prose of the reason exists only in an Issue comment**, so it is read from "
          f"there.\n")

    factor_hits, unmatched, read = {}, [], 0
    for iss in sorted(by_issue, key=lambda x: -len(by_issue[x])):
        bodies = _issue_reasons(iss)
        if not bodies:
            unmatched.append((iss, len(by_issue[iss]), "the Issue comments could not be read"))
            continue
        read += 1
        text = "\n".join(bodies)
        matched = False
        for name, pat in _FACTORS:
            if re.search(pat, text, re.I):
                factor_hits.setdefault(name, []).append(iss)
                matched = True
        if not matched:
            unmatched.append((iss, len(by_issue[iss]), "matches no known factor"))

    print(f"===== common factors across the reasons (from the comments of {read} Issue(s)) =====")
    if not factor_hits:
        print("  nothing could be counted as a common factor.")
    for name, isses in sorted(factor_hits.items(), key=lambda kv: -len(kv[1])):
        bar = "█" * len(isses)
        print(f"  {len(isses):>3} Issue  {bar:<12} {name}")
        print(f"            #{'  #'.join(sorted(isses, key=lambda x: int(x) if x.isdigit() else 0))}")

    if unmatched:
        # **Never drop what could not be counted, silently.** Whatever is dropped distorts the
        # reading "these are the common factors" — the tool says what it has not looked at
        # (docs/11).
        print(f"\n===== {len(unmatched)} that could not be counted =====")
        for iss, n, why in unmatched:
            print(f"  #{iss} ({n} refusal(s)) — {why}")
        print("  These are not in the totals above. **Do not read them as \"these are the common "
              "factors\".**")

    top = max(factor_hits.items(), key=lambda kv: -(-len(kv[1]))) if factor_hits else None
    print(f"\n===== the material ends here. The judgment is the supervisor's =====")
    if top and len(top[1]) >= 2:
        print(f"  The largest is \"{top[0]}\", across {len(top[1])} Issue(s).\n"
              f"  Where several fell to the same factor, **what needs fixing may not be the "
              f"individual deliverables but whatever is producing that factor** — how the spec is "
              f"written, the standard handed to the gate,\n"
              f"  the conventions, or the grain of the decomposition. **Which of them it is, this "
              f"tool cannot tell.**")
    else:
        print("  No factor spans several Issues. Treating them as individual defects is the "
              "natural reading.")
    print("  To make this reading an asset of the org, write it into conventions (the next maker "
          "reads it):\n"
          f'    python3 "{os.path.join(HERE, "doctrine.py")}" --help')
    return 0


def main():
    p = argparse.ArgumentParser(
        prog="drift",
        description="count the common factors across reasons for refusal. It does not judge — it "
                    "only produces the material.")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("factors", help="decompose the reasons for refusal/refutation into factors "
                                       "and count them")
    f.add_argument("--window", type=int, default=0,
                   help="how many days back (0 = all time, the default — narrowing it while there "
                        "is little data yields nothing)")
    f.set_defaults(fn=cmd_factors)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
