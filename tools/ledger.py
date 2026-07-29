#!/usr/bin/env python3
"""ledger — the append-only, hash-chained record for orgforge-plugin (ledger-schema.yaml).

This is the running implementation of Organ 5's record and Organ 6's custody holder: the
append-only AUDIT + ENFORCEMENT record from which every derived view (and therefore every
context pack) is projected. It is NOT the SSoT — the SSoT is code + the domain model
(conventions + the org spec); this ledger is the process journal (audit, requires_prior
gating, crash-safe resume), a record of *what happened*, not of *what the system is*. A
settled decision co-commits to code or conventions; the ledger holds only the receipt that it
was made. Before this existed, ledger-schema.yaml specified an envelope and event classes
that no code ever wrote, chained, or verified — the audit's D3 gap. This tool closes it:
events are appended under a hash chain, the chain is independently replayable (the external
watchdog's primitive), views are projected DETERMINISTICALLY from events, and the census /
digest are exact projections (same window + same ledger ⇒ byte-identical), never curated.

It ships no runtime and no scheduler (docs/08, R0): the registrar/watchdog are agents a host
runs on a cadence; this tool is the file-backed store + the projection + the verify they call.
The ledger is one JSON-lines file (append-only) plus a companion HEAD file holding the last
hash, so a writer never has to load the whole log to append:

    <root>/ledger.jsonl   ->  one envelope per line (id, seq, ts, actor, class, payload,
                              prev_hash, hash) — ledger-schema.yaml §envelope
    <root>/HEAD           ->  {"seq": N, "hash": "..."}  (the chain tip)

Invariants this tool enforces (ledger-schema.yaml §envelope.write_control, §event_classes):
  - Append-only, gapless seq, single writer: `append` never rewrites a line; seq = prev+1.
  - Hash chain: hash = H(prev_hash || canonical_json(id,seq,ts,actor,class,payload)); any
    edit to any past line breaks `verify` (tamper evidence, not tamper proof).
  - actor comes from the --actor arg (runtime identity), NEVER from the payload — an agent
    cannot forge another actor by writing it into the event body.
  - requires_prior: a `result_deployed` for candidate C is REJECTED at append time unless a
    prior `refutation_attempted{claim_id==C, verdict==survives}` exists — the skeptic is
    load-bearing, enforced at write time, not merely charted (org_lint's O6 checks the shape;
    this checks the actual event history).
  - Deterministic projection: `view`, `census`, `digest` are pure functions of the events in
    the window; no clock, no ordering nondeterminism (events carry their own seq/ts).

Commands:
  append <root> --actor A --class C --payload JSON [--ts TS]   append one event (chained)
  verify <root>                                                replay the chain; report first break
  view   <root> <view_id> [--since TS] [--until TS]            project a derived view (ledger-schema §views)
  census <root> [--since TS] [--until TS]                      counts of every event class (view: ledger_census)
  digest <root> --window-since TS [--window-until TS]          the deterministic digest (ledger-schema §digest)
  cat    <root> [--class C] [--actor A]                        print raw events (debug)
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import read_events, LedgerCorruption, resolve_root   # noqa: E402

# ── the forced SDLC phase order (docs/11) — reproducibility's spine ──
# A deliverable travels these phases in this order; a phase may not START until the prior phase is
# ADMITTED (phase_admitted{verdict==pass}) for the same deliverable. This is the same requires_prior
# idiom as result_deployed, generalized from admission-gating to phase-gating so that the PROCESS is
# reproducible: same spec ⇒ the same phases run in the same order for every founder and every run.
PHASE_ORDER = ["requirements", "design", "implement", "test", "integrate", "deploy", "operate"]


def _same_deliverable(a, b):
    """Do two payloads name the same deliverable? Compared as NORMALIZED STRINGS, not by ==.

    The deliverable is a GitHub Issue number that agents write freely as `42`, `"42"`, or `"#42"` across
    the flow. Raw equality makes `42 != "42"`, so the phase chain intermittently rejects a `phase_started`
    whose predecessor is visibly present in the ledger — an unreproducible failure whose message says
    "design was never admitted" while the admission is right there. That is the worst possible signature
    for an unattended run, so the comparison normalizes instead of trusting the writer's JSON type."""
    if a is None or b is None:
        return False
    return str(a).strip().lstrip("#") == str(b).strip().lstrip("#")


def _prior_phase(phase):
    """The phase that must be admitted before `phase` may start; None for the first phase."""
    try:
        i = PHASE_ORDER.index(phase)
    except ValueError:
        return None  # unknown phase name — the schema enum will reject it upstream; don't gate here
    return PHASE_ORDER[i - 1] if i > 0 else None


def _phase_admitted_for(ev, hist, phase):
    """この deliverable（またはその親）に対して `phase` が admit 済みか。

    **なぜ親まで遡るのか。** founding は objective 単位で requirements/design を admit する
    （設計はそこで起きるので当然）。一方 /org-work は task Issue 番号を deliverable にして
    `phase_started{implement}` を打つ。両者は別の文字列なので、objective #1 で admit しても
    task #7 には効かず、指示どおり進めても task #1 が弾かれた（実地で判明）。

    task ごとに requirements/design を再度 admit させるのは、同じ設計を N 回 admit させる
    セレモニーにしかならない。**設計は objective の単位で起きた**のだから、その admit を
    子タスクが継承するのが正しい。継承は payload の `parent`（/org-decompose が書く）で辿る。

    親を持たない deliverable は従来どおり自分の admit だけを見る — 挙動は変わらない。"""
    target = ev["payload"].get("deliverable")
    parent = ev["payload"].get("parent")          # /org-decompose が task に書く objective Issue 番号
    for e in hist:
        if e["class"] != "phase_admitted":
            continue
        if e["payload"].get("phase") != phase or e["payload"].get("verdict") != "pass":
            continue
        d = e["payload"].get("deliverable")
        if _same_deliverable(d, target):
            return True
        if parent is not None and _same_deliverable(d, parent):
            return True                            # 親 objective の admit を継承する
    return False


# ── event classes with a required-prior constraint (ledger-schema §event_classes) ──
# result_deployed{candidate_id==C} is INVALID without a prior refutation_attempted with
# claim_id==C and verdict==survives. This is the one write-time invariant the schema states
# in prose ("requires_prior"); we execute it against the actual event history.
REQUIRES_PRIOR = {
    # SDLC phase gate (docs/11 §2): phase_started{deliverable==D, phase==P} is INVALID unless a
    # phase_admitted{deliverable==D, phase==prior(P), verdict==pass} exists. requirements (prior==None)
    # is always allowed to start. Same shape as result_deployed — one predicate, more events.
    "phase_started": lambda ev, hist: (
        _prior_phase(ev["payload"].get("phase")) is None
        or _phase_admitted_for(ev, hist, _prior_phase(ev["payload"].get("phase")))
    ),
    # A phase may not be ADMITTED unless it was STARTED (docs/11 §2). Without this the mold is
    # decorative: `phase_admitted{integrate}` on an empty ledger makes `phase_started{deploy}` legal,
    # so a deliverable reaches deploy with requirements/design/implement/test never having happened.
    # Worse, it is the move an operator naturally reaches for when phase_started is rejected — the gate
    # would otherwise teach its own bypass.
    "phase_admitted": lambda ev, hist: any(
        e["class"] == "phase_started"
        and _same_deliverable(e["payload"].get("deliverable"), ev["payload"].get("deliverable"))
        and e["payload"].get("phase") == ev["payload"].get("phase")
        for e in hist
    ),
    "result_deployed": lambda ev, hist: any(
        e["class"] == "refutation_attempted"
        and e["payload"].get("claim_id") == ev["payload"].get("candidate_id")
        and e["payload"].get("verdict") == "survives"
        for e in hist
    ),
    # A4 report-up is INVALID unless this supervisor has done at least one A3 conformance review
    # that CONFORMS — a manager may not report subordinate work up as its own without having
    # verified it against the intent it delegated (docs/09 §A3/§A4). Without this, the schema's
    # requires_prior promise (ledger-schema.yaml) is prose, not enforced.
    "report_up": lambda ev, hist: any(
        e["class"] == "conformance_reviewed"
        and e["payload"].get("supervisor") == ev["payload"].get("supervisor")
        and e["payload"].get("verdict") == "conforms"
        for e in hist
    ),
    # A3 conformance review is INVALID unless the intent it reviews against was actually delegated
    # as a spec first (spec-driven, docs/09): the delegated_intent_ref must resolve to a prior
    # spec_delegated for the same (supervisor, subordinate). Otherwise delegated_intent_ref dangles
    # — a manager cannot "verify against the intent it delegated" if it never delegated one.
    "conformance_reviewed": lambda ev, hist: any(
        e["class"] == "spec_delegated"
        and e["payload"].get("supervisor") == ev["payload"].get("supervisor")
        and e["payload"].get("subordinate") == ev["payload"].get("subordinate")
        for e in hist
    ),
    # SSoT底上げ enforcement (docs/11 §4d): a cycle_completed is INVALID unless it STATES what it did to
    # the domain model — either `updated` (it co-committed a convention / domain-model artifact) or
    # `none_asserted` (it explicitly claims this cycle established no new domain rule — a claim the
    # skeptic can refute). This is a payload-shape requirement, not a history lookup: it makes "forgot to
    # update the domain model" impossible to do SILENTLY, so SDD runs on a growing context base, not in a
    # vacuum. Same explicit-negative pattern as exceptions_none_asserted.
    "cycle_completed": lambda ev, hist: (
        isinstance(ev["payload"].get("domain_model"), dict)
        and ("updated" in ev["payload"]["domain_model"] or "none_asserted" in ev["payload"]["domain_model"])
    ),
}

# ── separation of duties, enforced at WRITE time (docs/03 §3.1, docs/11 §4f) ──────────────────────
# REQUIRES_PRIOR asks "did the right events happen in the right order?" — it never asks WHO wrote them.
# That gap was survivable while a human read the diff. With human review retired (docs/11 §4f) the gate
# and the skeptic are the only judges left, so an actor that can write its own admission IS the whole
# judgment layer, and the hash chain then LAUNDERS the forgery: a forged verdict is tamper-evidently
# recorded and verifies clean, which reads as stronger evidence than no record at all.
#
# So judgment classes carry a distinct-actor predicate: the actor recording a verdict must not be the
# actor whose work it judges. This is the runtime half of O6 (org_lint's O6 checks the CHART separates
# maker from checker; this checks the RUN did too — a static chart cannot see one process writing both
# sides). Keyed on candidate_id/claim_id, so it needs only that candidate's own history.
#
# (class, payload-key naming the judged candidate, [classes whose actor must differ], why)
DISTINCT_ACTOR = {
    "admission_decided": ("candidate_id", ("cycle_started", "cycle_completed", "candidate_submitted"),
                          "the gate may not admit work it produced itself — the maker/checker split is "
                          "the org's load-bearing control (docs/03 §3.1). With human review retired "
                          "(docs/11 §4f) a self-admission is unappealable and undetectable downstream."),
    "refutation_attempted": ("claim_id", ("cycle_started", "cycle_completed", "admission_decided"),
                             "the skeptic may not refute work it made or already admitted — adversarial "
                             "review decorrelates blind spots only if the reviewer is a different actor "
                             "(docs/03 §5, docs/11 §4f.3)."),
}


def _distinct_actor_violation(ev, hist):
    """Return a rejection reason if this event's actor already acted as maker/prior-judge for the same
    candidate, else None. Compares the ACTOR (envelope), never a payload field — a payload role name is
    agent-authored and therefore forgeable; the actor is the recorded writer."""
    rule = DISTINCT_ACTOR.get(ev["class"])
    if not rule:
        return None
    key_field, conflicting, why = rule
    key = ev["payload"].get(key_field)
    if key is None:
        return None            # nothing to correlate on; the payload-shape check is elsewhere
    actor = ev.get("actor")
    for e in hist:
        if e["class"] not in conflicting:
            continue
        # the judged candidate may be named by either key (cycle_* use candidate_id; admission uses it too)
        e_key = e["payload"].get(key_field) or e["payload"].get("candidate_id")
        if str(e_key) == str(key) and e.get("actor") == actor:
            return (f"{ev['class']} rejected — actor {actor!r} already acted as {e['class']} for "
                    f"{key_field}={key!r}: {why}")
    return None

# an honest per-class reason for a requires_prior rejection (the reject message uses this instead
# of a single hardcoded 'skeptic is load-bearing' line that only fit result_deployed).
REQUIRES_PRIOR_WHY = {
    "phase_started": "a phase_admitted{deliverable, phase==prior(phase), verdict==pass} — the SDLC "
                     "phase order is non-skippable (requirements→design→implement→test→deploy→operate); "
                     "a phase cannot start before its predecessor is admitted (docs/11 §2). This is what "
                     "makes the process reproducible across founders and runs.",
    "phase_admitted": "a phase_started{deliverable, phase} for the SAME deliverable and phase — a phase "
                      "cannot be admitted without having been entered (docs/11 §2). Without this the "
                      "mold is decorative: admitting a late phase out of nowhere makes every earlier one "
                      "skippable.",
    "result_deployed": "a refutation_attempted{claim_id==candidate_id, verdict==survives} — the "
                       "skeptic is load-bearing; a result cannot deploy without surviving adversarial review",
    "report_up": "a conformance_reviewed{verdict==conforms} by this supervisor — a manager cannot "
                 "report subordinate work up as its own without verifying it against the intent it "
                 "delegated (docs/09 §A3/§A4)",
    "conformance_reviewed": "a spec_delegated for this (supervisor, subordinate) — a manager cannot "
                            "verify against 'the intent it delegated' if it never delegated a spec "
                            "(docs/09 §spec-driven)",
    "cycle_completed": "a `domain_model` field — {updated: [ref]} if this cycle co-committed a "
                       "convention/domain-model artifact, or {none_asserted: <reason>} if it "
                       "established no new domain rule. A cycle cannot silently skip updating the "
                       "domain model (SSoT底上げ, docs/11 §4d) — state it or the append is rejected.",
}

# ── views は ledger-schema.yaml の `views:` を単一の情報源として読む ────────────────────────
# 以前はここに13件をハードコードしていたが、スキーマは26件を宣言していた。乖離の実害:
#   - `/org-work` が parts_inventory を引けず、コマンド全体が起動しなかった
#   - **gate の context_pack 3件と skeptic の 2件がすべて未実装**だった。organization.yaml が
#     「gate はこの3つを見て admit する」と宣言していても、実行時に1つも引けない。
#     SoD（maker≠checker）は中核主張なのに、checker が判断材料を取得できなかった
#   - それでも `org_lint` は pass した（CP 検査は「スキーマに定義があるか」しか見ず、
#     「ツールが実装しているか」を見ていなかった）
# スキーマを読めば、view を足すのに Python を触る必要がなくなり、乖離が構造的に起きない。
_VIEW_FROM_CACHE = None


def _schema_path():
    """ledger-schema.yaml の場所。org のもの → プラグインのテンプレート、の順に探す。"""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    try:
        sys.path.insert(0, here)
        import discover
        root = discover.org_root()
        if root:
            cands.append(os.path.join(root, "ledger-schema.yaml"))
    except Exception:
        pass
    cands.append(os.path.join(here, "..", "template", "ledger-schema.yaml"))
    cands.append(os.path.join(here, "template", "ledger-schema.yaml"))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def _view_from():
    """{view_id: [derived-from classes]} をスキーマから読む。読めなければ空 dict。"""
    global _VIEW_FROM_CACHE
    if _VIEW_FROM_CACHE is not None:
        return _VIEW_FROM_CACHE
    out = {}
    path = _schema_path()
    if path:
        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            for vid, spec in (doc.get("views") or {}).items():
                frm = (spec or {}).get("from") if isinstance(spec, dict) else None
                out[vid] = list(frm) if frm else ["*"]
        except Exception:
            pass
    _VIEW_FROM_CACHE = out
    return out


# census 系は全クラスを数えるので、スキーマの `from` に関わらず "*" 扱いにする
_ALL_CLASS_VIEWS = ("ledger_census", "recent_ledger_census")


def _canonical(ev):
    """The bytes the hash covers: id,seq,ts,actor,class,payload in a fixed, sorted-key form.
    Canonical JSON (sorted keys, no incidental whitespace) so the hash is reproducible."""
    core = {k: ev[k] for k in ("id", "seq", "ts", "actor", "class", "payload")}
    return json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(prev_hash, ev):
    return hashlib.sha256((prev_hash + _canonical(ev)).encode("utf-8")).hexdigest()


def _paths(root):
    return os.path.join(root, "ledger.jsonl"), os.path.join(root, "HEAD")


def _read_events(root):
    # the log path _paths(root)[0] == ledger_path(root); delegate to the shared reader.
    return read_events(root)


def _read_head(root):
    _, head = _paths(root)
    if os.path.exists(head):
        with open(head, encoding="utf-8") as f:
            return json.load(f)
    return {"seq": 0, "hash": "GENESIS"}


def _in_window(ev, since, until):
    ts = ev.get("ts", "")
    if since and ts < since:
        return False
    if until and ts > until:
        return False
    return True


def cmd_append(a):
    """Append one event under the hash chain. actor is from --actor (runtime identity),
    never the payload. seq is gapless. requires_prior is enforced against real history."""
    try:
        payload = json.loads(a.payload)
    except json.JSONDecodeError as e:
        print(f"append: --payload is not valid JSON: {e}", file=sys.stderr)
        return 2
    if isinstance(payload, dict) and "actor" in payload:
        print("append: payload must not carry its own 'actor' — actor comes from --actor "
              "(runtime identity), never the event body (ledger-schema §envelope)", file=sys.stderr)
        return 2
    hist = _read_events(a.root)
    head = _read_head(a.root)
    # ── idempotency (docs/11 §0 reproducibility): if a natural key is given, this event is a
    # RETRY of a logical event that must be counted once. A replayed/re-fired cycle (a hook that
    # re-fires PreToolUse, a resumed session, a crash-retry) must NOT double-append — else the
    # aggregate caps (exposure, cycles, WIP) drift with how many times the tool ran, not with the
    # spec+action. We no-op (exit 0) when (class, natural_key) already exists in history. The seq
    # counter is monotonic, so without this an identical logical event would land twice under two
    # ids — the non-idempotency the "idempotent under replay" note wrongly claimed we already had.
    nk = getattr(a, "natural_key", None)
    if nk:
        for e in hist:
            if e["class"] == a.cls and e.get("payload", {}).get("_nk") == nk:
                print(f"append: idempotent no-op — {a.cls} with natural key {a.natural_key!r} "
                      f"already recorded at seq={e['seq']} id={e['id']} (docs/11 §0). Not re-appended.")
                return 0
        payload["_nk"] = a.natural_key   # stamp the key so a future retry can find this event
    seq = head["seq"] + 1
    # id is derived from (seq, class, canonical payload) so append is deterministic and
    # idempotent under replay — no wall-clock/random id (docs/08: tools stay deterministic).
    eid = "e" + hashlib.sha256(
        f"{seq}:{a.cls}:{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
    ).hexdigest()[:12]
    ev = {"id": eid, "seq": seq, "ts": a.ts or "UNSET", "actor": a.actor,
          "class": a.cls, "payload": payload, "prev_hash": head["hash"]}
    if a.cls in REQUIRES_PRIOR and not REQUIRES_PRIOR[a.cls](ev, hist):
        why = REQUIRES_PRIOR_WHY.get(a.cls, "a required prior event does not exist")
        print(f"append: {a.cls} rejected — requires a prior event that does not exist: {why} "
              f"(ledger-schema §event_classes {a.cls}.requires_prior)", file=sys.stderr)
        return 3
    sod = _distinct_actor_violation(ev, hist)
    if sod:
        print(f"append: {sod}", file=sys.stderr)
        return 3
    ev["hash"] = _hash(head["hash"], ev)
    os.makedirs(a.root, exist_ok=True)
    log, headp = _paths(a.root)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    with open(headp, "w", encoding="utf-8") as f:
        json.dump({"seq": seq, "hash": ev["hash"]}, f)
    print(f"appended seq={seq} {a.cls} id={eid} hash={ev['hash'][:12]}…")
    return 0


def cmd_verify(a):
    """Replay the whole chain from GENESIS — the external watchdog's core primitive. Reports
    the FIRST break (edited line, reordered seq, or forged hash). Exit 1 if the chain is broken."""
    try:
        events = _read_events(a.root)
    except LedgerCorruption as c:
        # a non-JSON line IS tamper evidence — report BROKEN, do not crash with a traceback
        print(f"BROKEN: malformed (non-JSON) content at ledger line {c.lineno} — the append-only "
              f"log was edited to something that isn't a valid event (tamper evidence)",
              file=sys.stderr)
        return 1
    prev = "GENESIS"
    expect_seq = 1
    for ev in events:
        if ev["seq"] != expect_seq:
            print(f"BROKEN: seq gap/disorder at line — expected seq {expect_seq}, got {ev['seq']}",
                  file=sys.stderr)
            return 1
        if ev["prev_hash"] != prev:
            print(f"BROKEN: prev_hash mismatch at seq {ev['seq']} — chain was cut/reordered",
                  file=sys.stderr)
            return 1
        if _hash(prev, ev) != ev["hash"]:
            print(f"BROKEN: hash mismatch at seq {ev['seq']} — event {ev['id']} was edited "
                  f"after it was written (tamper evidence)", file=sys.stderr)
            return 1
        prev = ev["hash"]
        expect_seq += 1
    head = _read_head(a.root)
    if head["hash"] != prev:
        print(f"BROKEN: HEAD hash {head['hash'][:12]}… does not match chain tip {prev[:12]}…",
              file=sys.stderr)
        return 1
    print(f"chain intact: {len(events)} event(s), tip {prev[:12]}… — hash chain replays clean")
    return 0


def cmd_view(a):
    """Project a derived view — a DETERMINISTIC function of the events it derives from
    (ledger-schema §views). Context packs may contain only views; this is how they're built."""
    views = _view_from()
    if a.view_id not in views:
        known = ", ".join(sorted(views)) or "(ledger-schema.yaml が読めない)"
        print(f"view: unknown view '{a.view_id}'. known: {known}", file=sys.stderr)
        return 2
    classes = ["*"] if a.view_id in _ALL_CLASS_VIEWS else views[a.view_id]
    events = [e for e in _read_events(a.root)
              if _in_window(e, a.since, a.until)
              and (classes == ["*"] or e["class"] in classes)]
    if a.view_id in ("ledger_census", "recent_ledger_census"):
        counts = {}
        for e in events:
            counts[e["class"]] = counts.get(e["class"], 0) + 1
        print(json.dumps({"view": a.view_id, "counts": dict(sorted(counts.items()))},
                         indent=2, ensure_ascii=False))
        return 0
    if a.view_id == "work_in_progress":
        # RESOLVE (not raw rows): candidates started but not completed, each with its LATEST progress
        # checkpoint. This is the recovery source after a context wipe — the SessionStart hook and
        # /org-resume read it to answer "what was this role mid-way through, and what's the next step?"
        started, completed, latest = {}, set(), {}
        for e in events:
            cid = e["payload"].get("candidate_id")
            if not cid:
                continue
            if e["class"] == "cycle_started":
                started[cid] = {"candidate_id": cid, "role": e["payload"].get("role"),
                                "started_seq": e["seq"]}
            elif e["class"] == "cycle_completed":
                completed.add(cid)
            elif e["class"] == "progress_recorded":
                latest[cid] = {k: e["payload"].get(k) for k in
                               ("fraction", "phase", "done_so_far", "next_step", "blocked_by", "artifacts")}
        wip = [{**started[cid], "progress": latest.get(cid)}
               for cid in started if cid not in completed]
        wip.sort(key=lambda w: w["started_seq"])
        print(json.dumps({"view": "work_in_progress", "in_progress": wip}, indent=2, ensure_ascii=False))
        return 0
    # generic projection: the events feeding the view, newest last, payloads intact.
    rows = [{"seq": e["seq"], "ts": e.get("ts", ""), "class": e["class"], "payload": e["payload"]}
            for e in events]
    print(json.dumps({"view": a.view_id, "from": classes, "rows": rows},
                     indent=2, ensure_ascii=False))
    return 0


def cmd_census(a):
    events = [e for e in _read_events(a.root) if _in_window(e, a.since, a.until)]
    counts = {}
    for e in events:
        counts[e["class"]] = counts.get(e["class"], 0) + 1
    print(json.dumps({"window": {"since": a.since, "until": a.until},
                      "total": len(events), "census": dict(sorted(counts.items()))},
                     indent=2, ensure_ascii=False))
    return 0


def cmd_digest(a):
    """The deterministic digest (ledger-schema §digest): same window + same ledger ⇒
    byte-identical output. Census is mandatory and UNCURATED; sections are exact projections."""
    since, until = a.window_since, a.window_until
    events = [e for e in _read_events(a.root) if _in_window(e, since, until)]
    census = {}
    for e in events:
        census[e["class"]] = census.get(e["class"], 0) + 1
    reorg = [e["payload"] for e in events if e["class"] == "move_executed"]
    filed = {e["payload"].get("dedup_key") or e["seq"]: e["payload"]
             for e in events if e["class"] == "proposal_filed"}
    decided = {e["payload"].get("proposal_id") for e in events
               if e["class"] == "proposal_adjudicated"}
    open_props = [p for k, p in filed.items() if k not in decided]
    staged = {e["payload"].get("staged_id") or e["seq"]: e["payload"]
              for e in events if e["class"] == "irreversible_staged"}
    executed = {e["payload"].get("staged_id") for e in events
                if e["class"] == "irreversible_executed"}
    held = [p for k, p in staged.items() if k not in executed]
    anomalies = [e["payload"] for e in events if e["class"] == "anomaly_detected"]
    budget = {}
    for e in events:
        if e["class"] == "cycle_completed":
            role = e["payload"].get("role", "?")
            toks = e["payload"].get("tokens", {})
            b = budget.setdefault(role, {"task": 0, "gate": 0, "reporting": 0})
            for k in ("task", "gate", "reporting"):
                b[k] += toks.get(k, 0)
    digest = {
        "window": {"since": since, "until": until},
        "census": dict(sorted(census.items())),          # mandatory, uncurated
        "reorg_commits": reorg,
        "open_proposals": open_props,
        "held_irreversibles": held,
        "anomalies": anomalies,
        "budget_report": dict(sorted(budget.items())),
    }
    # deterministic: sorted keys, fixed separators — re-runnable to a byte-identical result.
    print(json.dumps(digest, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


def cmd_cat(a):
    for e in _read_events(a.root):
        if a.cls and e["class"] != a.cls:
            continue
        if a.actor and e["actor"] != a.actor:
            continue
        print(json.dumps(e, ensure_ascii=False))
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="ledger", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("append"); q.set_defaults(fn=cmd_append)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")
    q.add_argument("--actor", required=True)
    q.add_argument("--class", dest="cls", required=True)
    q.add_argument("--payload", required=True)
    q.add_argument("--ts")
    q.add_argument("--natural-key", dest="natural_key",
                   help="idempotency key: if a prior event of this class carries the same key, "
                        "this append is a no-op (docs/11 §0 — replay/retry must count once)")

    q = sub.add_parser("verify"); q.set_defaults(fn=cmd_verify)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")

    q = sub.add_parser("view"); q.set_defaults(fn=cmd_view)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)"); q.add_argument("view_id")
    q.add_argument("--since"); q.add_argument("--until")

    q = sub.add_parser("census"); q.set_defaults(fn=cmd_census)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)"); q.add_argument("--since"); q.add_argument("--until")

    q = sub.add_parser("digest"); q.set_defaults(fn=cmd_digest)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")
    q.add_argument("--window-since", dest="window_since")
    q.add_argument("--window-until", dest="window_until")

    q = sub.add_parser("cat"); q.set_defaults(fn=cmd_cat)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")
    q.add_argument("--class", dest="cls"); q.add_argument("--actor")

    a = p.parse_args(argv[1:])
    # root は省略可能: 省略時はカレントから自動発見する（.envrc 不要 — tools/discover.py）
    if hasattr(a, "root"):
        a.root = resolve_root(a.root)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
