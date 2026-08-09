#!/usr/bin/env python3
"""handoff — assemble the packet a manager hands a subordinate when it delegates a slice.

The delegation hand-off is where recursive decomposition either composes or drifts. Three
independent design critiques (org theory, software architecture, multi-agent systems) landed
on the same invariant: **do not fix a global decomposition axis; fix the SEAM CONTRACT at each
cut, and let each manager choose its own axis locally.** Decomposition is free; recombination
is bound (Thompson). The seam — not the taxonomy — is what makes siblings compose (Parnas /
Conway: the parent defines the interface, or the children drift on it).

So when a manager delegates a slice to a child, it emits ONE packet with three parts:

  1. THE SLICE          — what the child owns, in one line.
  2. THE SEAM CONTRACT  — the boundary the parent fixes and later integrates against:
                          inputs the child receives, outputs it MUST produce (exact interface),
                          files/modules it owns, files it must NOT touch. Inherited as a HARD
                          constraint the child may not renegotiate.
  3. THE CHILD'S BRAIN  — the parent's own doctrine, SCOPED DOWN to this slice (narrow-and-deep,
                          docs/06 §2.1): only the claims whose affected_roles include the child
                          role. The parent's broader brain does not leak down.

Plus a standing instruction: *if you split further, choose the axis that fits YOUR slice, and
emit a seam contract for each of your children the same way.* The axis is local advice; the
seam is the load-bearing, inherited constraint.

This tool ships no runtime (R0): a manager (an agent on a host harness) calls it to build the
child's prompt prefix, then spawns the child with it. It reuses doctrine.py's store as the
brain source.

Usage:
  handoff.py <doctrine_root> <child_role>
      --slice "what the child owns"
      --inputs "..."  --outputs "..."          (the seam contract)
      [--owns "fileA,fileB"] [--forbid "fileC,..."]
      [--axis "how THIS parent cut, one line + why"]     (optional, local advice only)
      [--invariant "a shared rule both sides honor"]      (repeatable)
      [--now DATE] [--out FILE]

Writes the hand-off packet (markdown) to --out (or stdout). The child's task prompt begins
with this text.
"""
import argparse
import json
import os
import sys


# The checking roles. They judge one candidate against one Issue's contract, so they are handed
# that contract and nothing else — see the brain/bar split below.
JUDGE_ROLES = frozenset({"gate", "skeptic"})


def _load(root, role):
    path = os.path.join(root, f"{role}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"role": role, "claims": []}


def _scoped_claims(root, child_role):
    """The child's brain = the admitted claims whose affected_roles name this child. This is
    the scope-down: a manager hands its subordinate only the slice-relevant doctrine, never
    its own broader picture (docs/07 §1.1 narrow-and-deep)."""
    out = []
    # a claim lands in the child's brain if the child role is in its affected_roles, wherever
    # the claim currently lives in the store (search every role file).
    # It does not fall over on a None/empty root — an org with no doctrine yet correctly has zero
    # claims, which is not a reason for seam-contract generation to fail.
    for fn in sorted(os.listdir(root)) if root and os.path.isdir(root) else []:
        if not fn.endswith(".json"):
            continue
        data = json.load(open(os.path.join(root, fn), encoding="utf-8"))
        for c in data.get("claims", []):
            if c.get("status") != "admitted":
                continue
            if child_role in c.get("provenance", {}).get("affected_roles", []):
                out.append(c)
    # dedup by id
    seen, uniq = set(), []
    for c in out:
        if c["id"] not in seen:
            seen.add(c["id"]); uniq.append(c)
    return uniq


def main(argv):
    p = argparse.ArgumentParser(prog="handoff", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)")
    p.add_argument("child_role")
    p.add_argument("--slice", required=True, dest="slice_")
    p.add_argument("--inputs", required=True)
    p.add_argument("--outputs", required=True)
    p.add_argument("--owns", default="")
    p.add_argument("--forbid", default="")
    p.add_argument("--axis", default="")
    p.add_argument("--invariant", action="append", default=[])
    p.add_argument("--now")
    p.add_argument("--out")
    a = p.parse_args(argv[1:])

    # With root omitted, discover it from the cwd (the help said so while it was unimplemented,
    # and it died with a TypeError). doctrine is a per-role claim store, so the doctrine root is
    # what is consulted.
    if not a.root:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from discover import _sub_root
            a.root = _sub_root("doctrine") or ""
        except Exception:
            a.root = ""

    claims = _scoped_claims(a.root, a.child_role)

    L = []
    L.append(f"# HAND-OFF — you are: {a.child_role}")
    L.append("")
    L.append("## Your slice")
    L.append(a.slice_)
    L.append("")
    L.append("## Boundary contract (FIXED by your manager — do not renegotiate)")
    L.append(f"- Inputs you receive: {a.inputs}")
    L.append(f"- Outputs you MUST produce (the exact interface others depend on): {a.outputs}")
    if a.owns:
        L.append(f"- You own: {a.owns}")
    if a.forbid:
        L.append(f"- You must NOT touch: {a.forbid}")
    for inv in a.invariant:
        L.append(f"- Shared invariant: {inv}")
    L.append("")
    # A JUDGE gets no brain. Doctrine is organization-wide standing knowledge; a judge's bar is
    # the Issue in front of it — its acceptance criteria, changed seam, declared DoD, submitted
    # evidence, recorded risk. Handing a judge the org's accumulated lessons turns a bounded
    # admission check into open-ended research: the bar moves between rounds, and findings
    # accumulate that no MUST in the Issue asked for.
    #
    # This is about the judge's INPUT, never its judgment (docs/03 §6.5). It still decides the
    # verdict; it just decides against the contract it was handed rather than against everything
    # the org has ever learned.
    #
    # Makers keep their brain: a maker BUILDS, and prior lessons are what stop it rebuilding a
    # known mistake. Only the checking roles are scoped down.
    if a.child_role in JUDGE_ROLES:
        L.append("## Your bar (this Issue only — you get no org-wide doctrine)")
        L.append("- Judge against the Issue's acceptance criteria, the changed seam contract, the "
                 "declared DoD, the submitted evidence, and the recorded residual risk.")
        L.append("- A finding outside that boundary is `out_of_scope` with a follow-up "
                 "recommendation — not a blocker — unless it concretely demonstrates an immediate "
                 "safety, data-integrity, security, or release-blocking failure.")
        L.append("")
    else:
        L.append("## Your brain (doctrine scoped to your slice)")
        if claims:
            for c in claims:
                exp = ""
                if a.now and c["review_by"] != "UNSET" and c["review_by"] < a.now:
                    exp = "  ⟨REVIEW OVERDUE⟩"
                prov = c["provenance"]
                L.append(f"- {c['claim']}{exp}")
                L.append(f"    (source: {prov['source']}; confidence: {prov['confidence']}; "
                         f"review by {c['review_by']})")
        else:
            L.append("- (no admitted doctrine scoped to this role yet)")
        L.append("")
    L.append("## If you split your slice further")
    if a.axis:
        L.append(f"- Suggested cut for THIS slice (local advice, your call): {a.axis}")
    L.append("- Choose the axis that fits YOUR slice — do not inherit a global one. For EACH "
             "child you spawn, emit a Boundary contract the same way (inputs / outputs / owns "
             "/ forbid), and hand down only the doctrine scoped to that child.")
    L.append("- Do NOT re-split across a boundary your manager fixed above; integrate to the "
             "outputs interface exactly.")
    body = "\n".join(L) + "\n"

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"hand-off packet -> {a.out} ({len(claims)} scoped claim(s), seam contract fixed)")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
