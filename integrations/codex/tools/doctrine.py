#!/usr/bin/env python3
"""doctrine — the knowledge/guardrail store for orgforge-plugin (docs/06).

This is the running implementation of the doctrine organ: external information is
watched, admitted through the gate, distilled into per-role **doctrine** (each role's
current normative playbook — what it should currently believe about its domain and how it
should therefore work), version-and-TTL'd, and INJECTED into a role's working directory
before its harness launches. Doctrine is the guardrail: a role never acts on last
quarter's world, because its current doctrine is loaded every cycle.

It ships no runtime and no scheduler (docs/08): the curator/gate are agents a host harness
runs on a cadence; this tool is the file-backed store + the injection step + the admission
gate they call. Doctrine is a directory of per-role JSON files under a doctrine root:

    <root>/<role>.json  ->  { role, claims: [ {id, claim, provenance:{source,retrieved_at,
                              confidence,affected_roles}, review_by, admitted_at, version} ] }

Commands:
  propose  <root> <role> --claim TXT --source S --confidence C [--review-by DATE] [--affects R,R]
             curator step: file an intelligence item as a PENDING doctrine claim (not yet admitted)
  admit    <root> <role> <claim_id> --by gate                  gate step: admit a pending claim
  reject   <root> <role> <claim_id> --by gate --reason TXT     gate step: reject (provenance/standard fail)
  render   <root> <role> [--budget-tokens N] [--now DATE]      write the role's DOCTRINE.md for injection
  stale    <root> [--now DATE]                                 list claims past review_by (fires the curator)
  show     <root> <role>                                       print the role's doctrine (admitted + pending)

Guardrail invariants this tool enforces (docs/06 §3/§4):
  - Nothing external becomes loaded doctrine without passing `admit` (untrusted-until-admitted).
  - Every claim carries provenance {source, retrieved_at, confidence, affected_roles} — no
    anonymous doctrine (anti-poisoning).
  - Every claim carries a review_by TTL; `stale` surfaces expired claims so doctrine can't rot.
  - `render` only ever emits ADMITTED claims, within the context budget (over-budget = re-distill,
    never silent-truncate).
"""
import argparse
import hashlib
import json
import os
import sys


def _load(root, role):
    path = os.path.join(root, f"{role}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"role": role, "claims": []}


def _save(root, role, data):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, f"{role}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _claim_id(role, claim):
    return "c" + hashlib.sha256(f"{role}:{claim}".encode()).hexdigest()[:10]


def _find(data, cid):
    for c in data["claims"]:
        if c["id"] == cid:
            return c
    return None


def cmd_propose(a):
    """curator: file an intelligence item as a PENDING claim. Never admitted here —
    the curator proposes; only the gate admits (docs/06 §1)."""
    if not (a.source and a.confidence is not None):
        print("propose: --source and --confidence are required — no anonymous doctrine "
              "(provenance is the anti-poisoning guard, docs/06 §3)", file=sys.stderr)
        return 2
    data = _load(a.root, a.role)
    cid = _claim_id(a.role, a.claim)
    if _find(data, cid):
        print(f"claim {cid} already exists for {a.role}")
        return 0
    data["claims"].append({
        "id": cid,
        "claim": a.claim,
        "status": "pending",              # pending -> admitted | rejected (gate decides)
        "provenance": {
            "source": a.source,
            "retrieved_at": a.retrieved_at or "UNSET",
            "confidence": a.confidence,
            "affected_roles": [r.strip() for r in (a.affects or a.role).split(",")],
        },
        "review_by": a.review_by or "UNSET",   # TTL — stale doctrine must be re-checked
        "version": 1,
    })
    _save(a.root, a.role, data)
    print(f"proposed pending claim {cid} for {a.role} (awaits gate admission)")
    # propose は retrieved_at / review_by を省略できるのに admit はそれを必須にするので、
    # 素直に使うと **admit の段階で必ず詰まる**。実地で doctrine が空のままだった一因なので、
    # 詰まる前に、この場で言う（admit まで黙っていると、学びを差し出した側は理由を知れない）。
    if not a.retrieved_at or not a.review_by:
        missing = " と ".join(x for x, v in
                              (("--retrieved-at", a.retrieved_at), ("--review-by", a.review_by))
                              if not v)
        print(f"注意: {missing} が無い。このままでは gate が admit できない"
              f"（provenance が不完全な doctrine は正典にしない — docs/06 §3）。\n"
              f"  再 propose するか、admit の前に埋めること。TTL の無い doctrine は"
              f"「いつまで信じてよいか」を誰も知らないまま残り続ける。", file=sys.stderr)
    return 0


def cmd_admit(a):
    """gate: admit a pending claim. External content is untrusted until this step."""
    data = _load(a.root, a.role)
    c = _find(data, a.claim_id)
    if c is None:
        print(f"admit: no claim {a.claim_id} for {a.role}", file=sys.stderr)
        return 2
    if a.by != "gate":
        print("admit: --by must be 'gate' — only the authorization holder admits doctrine "
              "(a maker may not admit its own doctrine, docs/06 §4)", file=sys.stderr)
        return 2
    if c["provenance"]["retrieved_at"] == "UNSET" or c["review_by"] == "UNSET":
        print(f"admit: claim {a.claim_id} lacks retrieved_at or review_by — incomplete "
              f"provenance cannot be admitted (docs/06 §3)", file=sys.stderr)
        return 2
    c["status"] = "admitted"
    c["admitted_at"] = a.at or "UNSET"
    _save(a.root, a.role, data)
    print(f"admitted {a.claim_id} for {a.role} — now guardrail doctrine, loaded next cycle")
    return 0


def cmd_reject(a):
    data = _load(a.root, a.role)
    c = _find(data, a.claim_id)
    if c is None:
        print(f"reject: no claim {a.claim_id} for {a.role}", file=sys.stderr)
        return 2
    c["status"] = "rejected"
    c["reject_reason"] = a.reason
    _save(a.root, a.role, data)
    print(f"rejected {a.claim_id} for {a.role}: {a.reason}")
    return 0


def cmd_render(a):
    """Write the role's DOCTRINE.md — the guardrail loaded into its working dir before
    launch. Only ADMITTED claims; over budget => re-distill, never silent-truncate."""
    data = _load(a.root, a.role)
    admitted = [c for c in data["claims"] if c.get("status") == "admitted"]
    lines = [f"# DOCTRINE — {a.role}", "",
             "Your current normative playbook — what to believe about your domain now, and how",
             "to work given it. Admitted from watched external sources; each claim carries its",
             "provenance and a review-by date. This is a guardrail: act on the current world.",
             ""]
    stale_now = a.now
    for c in admitted:
        exp = ""
        if stale_now and c["review_by"] != "UNSET" and c["review_by"] < stale_now:
            exp = "  ⟨REVIEW OVERDUE⟩"
        prov = c["provenance"]
        lines.append(f"- {c['claim']}{exp}")
        lines.append(f"    (source: {prov['source']}; confidence: {prov['confidence']}; "
                     f"review by {c['review_by']})")
    body = "\n".join(lines) + "\n"
    # budget: doctrine that outgrows the pack budget must be re-distilled, not truncated
    approx_tokens = len(body) // 4
    if a.budget_tokens and approx_tokens > a.budget_tokens:
        print(f"render: doctrine for {a.role} is ~{approx_tokens} tokens > budget "
              f"{a.budget_tokens} — re-distill (fewer, sharper claims); not truncating "
              f"silently (docs/06 §3)", file=sys.stderr)
        return 1
    out = a.out or os.path.join(a.root, f"{a.role}.DOCTRINE.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"rendered {len(admitted)} admitted claim(s) -> {out}")
    return 0


def cmd_stale(a):
    """List admitted claims past their review_by — the doctrine_stale signal that fires
    the curator to re-check the world (docs/06 §3, sensors.yaml)."""
    if not a.now:
        print("stale: --now DATE required to compare against review_by", file=sys.stderr)
        return 2
    found = 0
    for fn in sorted(os.listdir(a.root)) if os.path.isdir(a.root) else []:
        if not fn.endswith(".json"):
            continue
        role = fn[:-5]
        data = _load(a.root, role)
        for c in data["claims"]:
            if c.get("status") == "admitted" and c["review_by"] != "UNSET" \
                    and c["review_by"] < a.now:
                print(f"STALE {role} {c['id']}: review_by {c['review_by']} < {a.now} — "
                      f"{c['claim'][:70]}")
                found += 1
    if not found:
        print("no stale doctrine")
    return 0


def cmd_show(a):
    data = _load(a.root, a.role)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def _live(c):
    """A claim whose brain-value must survive a refound: admitted, or still pending
    (rejected claims are settled history and are not re-routed)."""
    return c.get("status") in ("admitted", "pending")


def cmd_remap(a):
    """refound executor: re-route each role's LIVE doctrine onto the new role structure,
    ASSETS INTACT (docs/05 §4.4). This is what performs `doctrine_remapped`; org_lint's
    `doctrine_remap_covers_every_live_claim` checks the plan, this applies it.

    The map is a JSON object {old_role: new_role | [new_role, ...]}:
      - old -> new        : rename / merge (many olds may point at one new; claims union).
      - old -> [n1, n2]   : SPLIT — each live claim goes to the new role(s) named in its
                            provenance.affected_roles ∩ {n1,n2}; a claim naming none of the
                            targets is an ORPHAN (surfaced, never silently dropped).
    Refuses to run (exit 2) if any live claim would be orphaned, unless --allow-orphans,
    which instead writes them to <new_root>/UNROUTED.<old>.json for a human to place —
    so the refound is atomic-or-surfaced, never a silent brain loss.
    """
    try:
        mapping = json.loads(a.map)
    except Exception as e:
        print(f"remap: --map must be JSON {{old_role: new_role|[roles]}} — {e}", file=sys.stderr)
        return 2
    src_root, dst_root = a.root, (a.into or a.root)
    routed, orphans = {}, []          # new_role -> [claims];  orphans -> [(old, claim)]
    for old, target in mapping.items():
        data = _load(src_root, old)
        targets = [target] if isinstance(target, str) else list(target)
        for c in data["claims"]:
            if not _live(c):
                continue
            if len(targets) == 1:
                dests = targets                      # rename/merge: everything moves
            else:
                aff = set(c.get("provenance", {}).get("affected_roles", []))
                dests = [t for t in targets if t in aff]   # split by affected_roles
            if not dests:
                orphans.append((old, c))
                continue
            for d in dests:
                routed.setdefault(d, []).append(c)

    if orphans and not a.allow_orphans:
        print(f"remap: {len(orphans)} live claim(s) would be orphaned (no target role) — "
              f"refound BLOCKED so no brain is silently lost (docs/05 §4.4). Fix the map or "
              f"pass --allow-orphans to surface them to UNROUTED.* for a human:", file=sys.stderr)
        for old, c in orphans:
            print(f"    [{old}] {c['claim'][:80]}", file=sys.stderr)
        return 2

    # apply: union claims into each new role's file (dedup by id, keep existing)
    for new_role, claims in routed.items():
        dst = _load(dst_root, new_role)
        have = {c["id"] for c in dst["claims"]}
        for c in claims:
            if c["id"] not in have:
                dst["claims"].append(c)
                have.add(c["id"])
        _save(dst_root, new_role, dst)
        print(f"remapped -> {new_role}: {len(claims)} claim(s) routed in")

    if orphans:   # --allow-orphans path: surface, do not drop
        orphan_doc = {"role": "UNROUTED", "claims": [c for _, c in orphans]}
        _save(dst_root, "UNROUTED", orphan_doc)
        print(f"surfaced {len(orphans)} orphan claim(s) -> {dst_root}/UNROUTED.json "
              f"(a human must re-place these; NOT lost)")
    print("doctrine remap complete — assets preserved, roles re-routed")
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="doctrine", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("propose"); q.set_defaults(fn=cmd_propose)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)"); q.add_argument("role")
    q.add_argument("--claim", required=True)
    q.add_argument("--source"); q.add_argument("--confidence", type=float)
    q.add_argument("--retrieved-at", dest="retrieved_at")
    q.add_argument("--review-by", dest="review_by")
    q.add_argument("--affects")

    q = sub.add_parser("admit"); q.set_defaults(fn=cmd_admit)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)"); q.add_argument("role"); q.add_argument("claim_id")
    q.add_argument("--by", required=True); q.add_argument("--at")

    q = sub.add_parser("reject"); q.set_defaults(fn=cmd_reject)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)"); q.add_argument("role"); q.add_argument("claim_id")
    q.add_argument("--by", required=True); q.add_argument("--reason", required=True)

    q = sub.add_parser("render"); q.set_defaults(fn=cmd_render)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)"); q.add_argument("role")
    q.add_argument("--budget-tokens", dest="budget_tokens", type=int)
    q.add_argument("--now"); q.add_argument("--out")

    q = sub.add_parser("stale"); q.set_defaults(fn=cmd_stale)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)"); q.add_argument("--now")

    q = sub.add_parser("show"); q.set_defaults(fn=cmd_show)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)"); q.add_argument("role")

    q = sub.add_parser("remap"); q.set_defaults(fn=cmd_remap)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)")                                  # source doctrine store (old roles)
    q.add_argument("--map", required=True)                  # JSON {old_role: new_role|[roles]}
    q.add_argument("--into")                                # dest store (default: same as root)
    q.add_argument("--allow-orphans", dest="allow_orphans", action="store_true")

    a = p.parse_args(argv[1:])
    # root は省略可能: 省略時は `.orgforge/doctrine` を発見する（tools/discover.py）。
    # ここは ledger とは別のストアで、以前は `${ORG_CONVENTIONS_ROOT:-$ORG_LEDGER_ROOT}` の
    # ようなフォールバックで ledger に混入していた — 監査記録に別種のデータが混ざるので誤り。
    if getattr(a, "root", None) is None:
        import os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        import discover as _d
        a.root = _d._sub_root("doctrine")
        if not a.root:
            print("doctrine の置き場が見つからない。org の中（.orgforge/ のあるディレクトリ）で "
                  "実行するか、root を明示すること。", file=sys.stderr)
            return 2
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
