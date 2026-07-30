"""カバレッジ — coverage-manifest の must-have が Issue に降りているかの検査。"""

import hashlib
import json
import os
import re
import subprocess
import sys

from ._core import (
    gh,
)


def _manifest_rows(path):
    """Parse coverage-manifest.md (docs/11 §0a, the FIXED name) into rows.

    The manifest is a markdown table whose columns are {rfp_capability, owning_role, deliverable,
    acceptance} — the RFP→contract coverage map /org-found emits. We read the header to locate the
    columns by NAME (not position), so a manifest that adds a column still parses. Rows whose
    rfp_capability cell is empty or a separator are skipped.

    A non-table line ENDS the table. This matters: /org-found emits an explicit EXCLUDE list alongside
    the manifest, so a second table below it is expected. Without the reset, that table's rows would be
    read as must-haves — and since the decomposition agent is told to work until coverage-check is
    green, it would mint task Issues for exactly the scope the CEO cut. A table is a contiguous block of
    `|` lines; anything else closes it."""
    import io
    rows = []
    with io.open(path, encoding="utf-8") as fh:
        header, idx = None, {}
        for line in fh:
            if not line.lstrip().startswith("|"):
                header, idx = None, {}     # blank/prose line ends this table (see docstring)
                continue
            cells = [c.strip().strip("`*") for c in line.strip().strip("|").split("|")]
            if header is None:
                header = [c.lower().replace(" ", "_") for c in cells]
                idx = {name: i for i, name in enumerate(header)}
                if "rfp_capability" not in idx:      # not the manifest table — keep looking
                    header = None
                continue
            if all(set(c) <= set("-: ") for c in cells):
                continue                              # the |---|---| separator
            def get(name):
                i = idx.get(name)
                return cells[i] if i is not None and i < len(cells) else ""
            cap = get("rfp_capability")
            if not cap or cap.startswith("<"):
                continue
            rows.append({"rfp_capability": cap, "owning_role": get("owning_role"),
                         "deliverable": get("deliverable"), "acceptance": get("acceptance")})
    return rows


def cmd_coverage_check(a):
    """DECOMPOSITION COVERAGE gate (docs/11 §0a/§4b): every must-have row in coverage-manifest.md must
    have reached at least one open-or-closed task Issue, and every such Issue must trace back to a row.

    /org-found's O10 lint proves each must-have has ONE owning contract; that is coverage at the
    *design* layer. This is the same guarantee one layer down, at the *decomposition* layer: a
    must-have that never became a task Issue is silently unbuilt — the coverage gap reappears exactly
    where it is hardest to see. The trace key is the `coverage_row:` trailer /org-decompose writes into
    each task Issue body (the rfp_capability verbatim), so the check is mechanical, not fuzzy-matched.

    Exit 0 = every must-have covered · 10 = uncovered rows (or orphan Issues) · 2 = usage/gh error."""
    try:
        rows = _manifest_rows(a.manifest)
    except OSError as e:
        print(f"cannot read manifest {a.manifest}: {e}", file=sys.stderr)
        return 2
    if not rows:
        print(f"no manifest rows parsed from {a.manifest} — expected a markdown table with an "
              f"`rfp_capability` column (docs/11 §0a).", file=sys.stderr)
        return 2
    code, out = gh(["issue", "list", "--repo", a.repo, "--label", "orgforge:kind:task",
                    "--state", "all", "--limit", "500", "--json", "number,title,body,state,labels"])
    if code != 0:
        print(f"gh error listing task Issues: {out}", file=sys.stderr)
        return 2
    try:
        issues = json.loads(out)
    except Exception as e:
        print(f"parse: {e}", file=sys.stderr)
        return 2

    def covered_rows(body):
        """The coverage_row: trailers in an Issue body (one Issue may serve several rows).

        Strip the markdown decoration BEFORE splitting on the colon: an agent writing the Issue body in
        the org's output_language naturally bolds a label (`**coverage_row:** X`), and splitting the raw
        line would yield "** X" → " X" — a leading space that fails the exact match, reporting a GAP for
        a row that is in fact covered and sending the operator to mint a duplicate Issue."""
        found = []
        for line in (body or "").splitlines():
            clean = line.strip().lstrip("*-`> ")
            if clean.lower().startswith("coverage_row:"):
                val = clean.split(":", 1)[1].strip().strip("`* ")
                if val:
                    found.append(val)
        return found

    claimed = {}
    orphans = []           # any task Issue with no trailer (self-raised items legitimately have none)
    mandate_orphans = []   # RFP-derived (orgforge:mandate) with no trailer — that IS a defect
    for it in issues:
        cs = covered_rows(it.get("body"))
        if not cs:
            names = [l.get("name", "") for l in (it.get("labels") or [])]
            (mandate_orphans if "orgforge:mandate" in names else orphans).append(it["number"])
        for c in cs:
            claimed.setdefault(c, []).append(it["number"])

    uncovered = [r for r in rows if r["rfp_capability"] not in claimed]
    unknown = sorted(set(claimed) - {r["rfp_capability"] for r in rows})

    for r in rows:
        hits = claimed.get(r["rfp_capability"], [])
        mark = "ok " if hits else "GAP"
        where = ", ".join(f"#{n}" for n in hits) if hits else "— no task Issue"
        print(f"  [{mark}] {r['rfp_capability']}  ({r['owning_role'] or '?'})  → {where}")
    print(f"\n{len(rows) - len(uncovered)}/{len(rows)} must-have rows covered by task Issues.")
    rc = 0
    if uncovered:
        print(f"\nCOVERAGE GAP — {len(uncovered)} must-have(s) never became a task Issue:", file=sys.stderr)
        for r in uncovered:
            print(f"  · {r['rfp_capability']} (owner: {r['owning_role'] or '?'})", file=sys.stderr)
        print("Decompose these before starting work — an unowned must-have is silently unbuilt "
              "(docs/11 §0a).", file=sys.stderr)
        rc = 10
    if unknown:
        print(f"\nORPHAN trailers — coverage_row values matching no manifest row: {unknown}",
              file=sys.stderr)
        print("Either the manifest changed or a trailer is mistyped; the trailer must be the "
              "rfp_capability verbatim.", file=sys.stderr)
        rc = 10
    if mandate_orphans:
        # An RFP-derived task (source: mandate) with NO trailer at all is the likeliest decomposition
        # mistake, and the one the row-side check cannot see: if some OTHER Issue happens to cover the
        # same row, the manifest reads green while this task floats unattached to any requirement.
        # A mistyped trailer already fails as an orphan; a MISSING one must fail the same way.
        print(f"\nUNTRACED MANDATE TASKS — {len(mandate_orphans)} RFP-derived task Issue(s) carry no "
              f"`coverage_row:` trailer: {', '.join('#' + str(n) for n in mandate_orphans)}",
              file=sys.stderr)
        print("Every orgforge:mandate task must name the manifest row it serves (docs/11 §0a). Add the "
              "trailer, or relabel it orgforge:self if it is genuinely self-raised.", file=sys.stderr)
        rc = 10
    if orphans:
        print(f"\nNOTE: {len(orphans)} task Issue(s) carry no `coverage_row:` trailer "
              f"({', '.join('#' + str(n) for n in orphans[:10])}{' …' if len(orphans) > 10 else ''}) — "
              f"self-raised items from /org-discover are expected here; RFP-derived tasks are not.")
    return rc
