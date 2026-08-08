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
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import read_events, LedgerCorruption, resolve_root   # noqa: E402

# ── the forced SDLC phase order (docs/11) — reproducibility's spine ──
# A deliverable travels these phases in this order; a phase may not START until the prior phase is
# ADMITTED (phase_admitted{verdict==pass}) for the same deliverable. This is the same requires_prior
# idiom as result_deployed, generalized from admission-gating to phase-gating so that the PROCESS is
# reproducible: same spec ⇒ the same phases run in the same order for every founder and every run.
PHASE_ORDER = ["requirements", "design", "implement", "test", "integrate", "deploy", "operate"]



# The identifiers naming the same piece of work had split into two families: the human side,
# `decide` and org_cycle matched on `deliverable` / `issue`, while the enforcement logic
# (requires_prior / DISTINCT_ACTOR) matched on `candidate_id` / `claim_id`. They named the same
# thing, but each side saw only one family — so **in operation both a self-admission and a deploy
# of a non-existent deliverable went straight through.**
# Bundle them, so the correlation holds whichever family it was written in.
_CORRELATION_KEYS = ("candidate_id", "claim_id", "deliverable", "issue")


def _correlation_ids(payload):
    """Every identifier this payload uses to name a piece of work (as a normalised set).

    A match on any one of them counts as the same work. Whether enforcement holds must not depend
    on which key the writer happened to use — if it does, control disappears silently the moment
    someone drops that key.
    """
    out = set()
    for k in _CORRELATION_KEYS:
        v = payload.get(k)
        if v is not None and str(v).strip() != "":
            out.add(str(v).strip().lstrip("#"))
    return out


# `pack_manifest_id: "issue-7"` / `contract_ref` are the only bridge between a candidate_id and
# an Issue number. Even with no directly shared ID, following this bridge shows it is the same work.
_ALIAS_KEYS = ("pack_manifest_id", "contract_ref", "spec_ref")


def _alias_ids(payload):
    """Extract the Issue number out of an alias such as `issue-7`."""
    out = set()
    for k in _ALIAS_KEYS:
        v = payload.get(k)
        if v is None or str(v).strip() == "":
            continue
        s = str(v).strip()
        out.add(s.lstrip("#"))
        m = re.match(r"^(?:issue|task)[-_#]?(\d+)$", s, re.I)
        if m:
            out.add(m.group(1))
    return out


def _work_aliases(hist):
    """Build the equivalence classes of "identifiers naming the same work" across the ledger.

    In practice cycle_started carried only a candidate_id while the judging side was written with
    deliverable, so a direct comparison never correlated them — which is how a maker came to admit
    its own work. The bridge is already in the ledger:
    `cycle_started{candidate_id, pack_manifest_id:"issue-7"}` and
    `candidate_submitted{candidate_id, contract_ref}` connect the two.
    **Rather than making people write the same key, follow the correspondence that already exists.**
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for e in hist:
        pl = e.get("payload", {}) or {}
        ids = _correlation_ids(pl) | _alias_ids(pl)
        ids = sorted(ids)
        for other in ids[1:]:
            union(ids[0], other)
    return find


def _same_work(pa, pb, hist=None):
    """Do these two payloads name the same work?

    True if they share even one identifier. If they share none, still True when the alias
    correspondence held in the ledger (candidate_id ↔ issue-N) leads to the same work.
    """
    a, b = _correlation_ids(pa), _correlation_ids(pb)
    if a & b:
        return True
    if not hist or not a or not b:
        return False
    find = _work_aliases(hist)
    return bool({find(x) for x in a} & {find(y) for y in b})



def corrected_seqs(events, kinds=("probe", "mistake")):
    """Return correction targets selected by an explicit legacy ``kind`` query.

    This compatibility helper answers a narrow historical question and intentionally keeps its
    probe/mistake default.  Consumers projecting current truth must use :func:`voided_seqs` instead;
    otherwise each organ invents a different list of correction kinds (OBS-042).
    """
    out = set()
    for e in events:
        if e.get("class") != "correction":
            continue
        pl = e.get("payload", {}) or {}
        if pl.get("kind") not in kinds:
            continue
        for s in (pl.get("corrects") or []):
            try:
                out.add(int(s))
            except (TypeError, ValueError):
                continue
    return out


def voided_seqs(events):
    """Return every sequence whose correction has the authoritative ``voids`` effect.

    Since v2.0.23 the writer derives ``effect`` from the correction kind and schema-validates it.
    Older ledgers have no effect field, so replay maps the historical voiding kinds to the same
    meaning.  An explicit effect wins over the legacy fallback; ``records_backfill`` never erases
    the target.  This is the single effective-event projection shared by status, admission,
    integration, drift, and budget accounting.
    """
    # Corrections are themselves correctable. Evaluate newest-to-oldest so a later active
    # correction can disable an earlier correction before that earlier event affects its target.
    # This also makes a correction-of-a-correction genuinely reversible instead of merely adding
    # another inert row to the append-only log.
    def event_sequence(event):
        try:
            return int(event.get("seq", 0))
        except (TypeError, ValueError):
            return 0

    out = set()
    for event in sorted(events, key=event_sequence, reverse=True):
        if event.get("class") != "correction":
            continue
        if event_sequence(event) in out:
            continue
        payload = event.get("payload", {}) or {}
        effect = payload.get("effect")
        is_voiding = effect == "voids" or (
            effect is None and payload.get("kind") in VOIDING_CORRECTION_KINDS)
        if not is_voiding:
            continue
        for target_sequence in payload.get("corrects") or []:
            try:
                out.add(int(target_sequence))
            except (TypeError, ValueError):
                continue
    return out


# A correction aimed at one of these events changes a governance decision, not merely a factual
# note.  Letting either judge void such an event gives that judge the power to manufacture the
# empty slot into which its preferred replacement verdict is written.  Keep the vocabulary here
# aligned with the judgment surface accepted by github_sync (plus the derived/provisional classes).
JUDGMENT_CLASSES = frozenset({
    "verdict_provisional", "admission_decided", "refutation_attempted",
    "phase_admitted", "conformance_reviewed", "integration_admitted", "deploy_decided",
    "rework_requested", "scope_decided", "design_decided", "tradeoff_decided",
    "adaptive_envelope_adopted", "acceptable_outcome_recorded", "microexperiment_concluded",
})
VOIDING_CORRECTION_KINDS = frozenset({"probe", "mistake", "superseded"})


def _correction_subject(payload):
    """Return the receipt subject that binds an authority decision to targets and effect.

    A receipt for merely ``event_class=correction`` is replayable onto any correction.  Sequence
    numbers are unique inside the receipt-bound ledger, so binding the normalized target set and
    kind closes that replay without pretending the explanatory prose is an authorization token.
    """
    targets = []
    for raw in payload.get("corrects") or []:
        try:
            targets.append(int(raw))
        except (TypeError, ValueError):
            continue
    return f"correction:{payload.get('kind')}:{','.join(str(seq) for seq in sorted(set(targets)))}"


def _judgment_correction_policy():
    """Return the constitution-declared correction authority, or an explicit policy error.

    The authority is deliberately not a hard-coded ``supervisor`` string.  Different orgs may
    assign append-only record custody to a registrar, supervisor, or another non-judge role.  A
    missing/unreadable declaration is not interpreted as permission: judgment correction is a
    fail-closed operation while ordinary factual corrections remain available.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from discover import constitution as _constitution, org_root as _org_root
        path = _constitution()
    except Exception as exc:
        return None, f"cannot resolve the constitution's location: {exc}"
    if not path or not os.path.isfile(path):
        return None, "constitution.yaml is missing"
    try:
        import yaml
        with open(path, encoding="utf-8") as handle:
            doc = yaml.safe_load(handle) or {}
    except Exception as exc:
        return None, f"cannot read constitution.yaml: {exc}"
    if not isinstance(doc, dict):
        return None, "constitution.yaml is not a map"
    enforcement = doc.get("enforcement") or {}
    judges = enforcement.get("judges") if isinstance(enforcement, dict) else None
    policy = judges.get("judgment_corrections") if isinstance(judges, dict) else None
    if not isinstance(policy, dict):
        return None, ("enforcement.judges.judgment_corrections is not declared")
    roles = policy.get("authority_roles")
    if (not isinstance(roles, list) or not roles
            or any(not isinstance(role, str) or not role.strip() for role in roles)):
        return None, "judgment_corrections.authority_roles is empty or malformed"
    roles = tuple(dict.fromkeys(role.strip() for role in roles))
    judges_forbidden = sorted(set(roles) & {"gate", "skeptic"})
    if judges_forbidden:
        return None, ("a judge cannot be the judgment correction authority: "
                      + ", ".join(judges_forbidden))
    root = _org_root()
    organization_path = os.path.join(root, "organization.yaml") if root else None
    if not organization_path or not os.path.isfile(organization_path):
        return None, "organization.yaml is missing, so the authority role's remit cannot be verified"
    try:
        with open(organization_path, encoding="utf-8") as handle:
            organization = yaml.safe_load(handle) or {}
    except Exception as exc:
        return None, f"cannot read organization.yaml: {exc}"
    if not isinstance(organization, dict) or not isinstance(organization.get("roles"), list):
        return None, "organization.yaml roles is not a list, so the authority role cannot be verified"
    declared = {role.get("id"): role for role in organization["roles"]
                if isinstance(role, dict) and role.get("id")}
    for role_id in roles:
        role = declared.get(role_id)
        if role is None:
            return None, f"judgment correction authority {role_id!r} is not in the organization"
        if role.get("active") is False:
            return None, f"judgment correction authority {role_id!r} is dormant"
        functions = set(role.get("functions") or [])
        if functions & {"judge", "review"}:
            return None, (f"judgment correction authority {role_id!r} holds a judge/review "
                          "function — that is not a third-party authority")
    return {"authority_roles": roles}, None


def _annotate_correction(payload, hist):
    """Resolve correction targets and add a reconstructable, writer-derived effect."""
    wanted = []
    for raw in payload.get("corrects") or []:
        try:
            wanted.append(int(raw))
        except (TypeError, ValueError):
            return None, "correction.corrects contains a non-integer seq"
    by_seq = {int(item.get("seq")): item for item in hist if item.get("seq") is not None}
    missing = sorted(set(wanted) - set(by_seq))
    if missing:
        return None, f"correction target seq is not in the ledger: {missing}"
    targets = [by_seq[seq] for seq in wanted]
    classes = sorted({str(target.get("class") or "") for target in targets})
    payload["target_classes"] = classes
    target_issues = sorted({norm_issue((target.get("payload") or {}).get("issue"))
                            for target in targets
                            if (target.get("payload") or {}).get("issue") is not None})
    payload["target_issues"] = target_issues
    if (len(target_issues) == 1 and payload.get("issue") is not None
            and norm_issue(payload.get("issue")) != target_issues[0]):
        return None, (f"correction.issue={payload.get('issue')!r} does not match the target "
                      f"event's Issue {target_issues[0]!r}")
    if len(target_issues) == 1:
        payload["issue"] = target_issues[0]
    kind = payload.get("kind")
    payload["effect"] = "voids" if kind in VOIDING_CORRECTION_KINDS else "records_backfill"
    judgments = [target for target in targets if target.get("class") in JUDGMENT_CLASSES]
    if judgments and kind in VOIDING_CORRECTION_KINDS:
        payload["authority_receipt_subject"] = _correction_subject(payload)
    return judgments, None


def _judgment_correction_violation(ev, judgments):
    """Authorize a voiding correction after its targets and receipt have been resolved.

    ``backfill`` never voids its target, so it does not exercise correction authority.  Probe,
    mistake, and superseded do remove a judgment from at least one derived decision path and must be
    performed by a constitution-declared third party with a verified receipt.  A configurable actor
    name alone is insufficient: the receipt is bound to org, ledger, targets, kind, role, and signer.
    """
    payload = ev.get("payload") or {}
    kind = payload.get("kind")
    if not judgments or kind not in VOIDING_CORRECTION_KINDS:
        return None

    policy, error = _judgment_correction_policy()
    if error:
        return (f"cannot determine the judgment correction authority — {error}.\n"
                "  Declare the following in constitution.yaml and pass org_lint:\n"
                "    enforcement.judges.judgment_corrections.authority_roles: [supervisor]\n"
                "  **If it cannot be determined, do not void the judgment.**")
    actor = str(ev.get("actor") or "")
    authority_role = str(payload.get("authority_role") or actor)
    if payload.get("authority_role") and authority_role != actor:
        return (f"authority_role={authority_role!r} does not match envelope actor={actor!r}. "
                "a proxy authority name must not be written into the payload")
    if authority_role not in policy["authority_roles"]:
        return (f"actor {actor!r} is not authorized to make a judgment {kind}.\n"
                f"  third-party authority declared by the constitution: "
                f"{', '.join(policy['authority_roles'])}\n"
                f"  targets seq={payload.get('corrects')} / class={payload.get('target_classes')}. "
                "Do not clear the way yourself as the judge — hand back to the authority.")

    assurance = payload.get("identity_assurance")
    authority_principal = payload.get("decision_by")
    if assurance not in {"attested", "authenticated"} or not authority_principal:
        return (f"no signed receipt for judgment correction authority {authority_role!r}.\n"
                f"  expected subject: {payload.get('authority_receipt_subject')}\n"
                "  A role name in --actor does not prove third-party status. Sign with the "
                "authority's key and pass --receipt.")

    def principal(target):
        target_payload = target.get("payload") or {}
        return str(target_payload.get("decision_by") or target.get("actor") or "")

    target_principals = sorted({principal(target) for target in judgments})
    if actor in target_principals or str(authority_principal) in target_principals:
        return (f"the judgment's decision principal {authority_principal!r} cannot itself "
                f"perform the {kind}.\n  targets seq={payload.get('corrects')}.\n"
                "  A different, already-declared authority must make the correction.")
    supplied = payload.get("corrected_by")
    if supplied is not None and str(supplied) != actor:
        return (f"corrected_by={supplied!r} does not match envelope actor={actor!r}. "
                "the writer determines who made the correction")
    payload["corrected_by"] = actor
    payload["authority_role"] = authority_role
    payload["authority_principal"] = authority_principal
    payload["authority_assurance"] = assurance
    return None


def norm_issue(x):
    """Normalise an issue number. **Do not normalise differently in each place you compare.**

    `7`, `#7`, `007` and `" 7 "` are the same issue. The implementation, however, compared them
    three separate ways (some places only `lstrip("#")`, others stripping leading zeros as well).
    Because of that mismatch, **a provisional written as `007` against a call using `7`** was
    reported as "not enough judgments" and no admission could be created (raised by Codex,
    reproduced by measurement).
    If it cannot judge the same thing to be the same, it cannot serve as a key.
    """
    s = str(x if x is not None else "").strip().lstrip("#").strip()
    return s.lstrip("0") or s or ""


def _same_deliverable(a, b):
    """Do two payloads name the same deliverable? Compared as NORMALIZED STRINGS, not by ==.

    The deliverable is a GitHub Issue number that agents write freely as `42`, `"42"`, or `"#42"` across
    the flow. Raw equality makes `42 != "42"`, so the phase chain intermittently rejects a `phase_started`
    whose predecessor is visibly present in the ledger — an unreproducible failure whose message says
    "design was never admitted" while the admission is right there. That is the worst possible signature
    for an unattended run, so the comparison normalizes instead of trusting the writer's JSON type."""
    if a is None or b is None:
        return False
    return norm_issue(a) == norm_issue(b)


def _prior_phase(phase):
    """The phase that must be admitted before `phase` may start; None for the first phase."""
    try:
        i = PHASE_ORDER.index(phase)
    except ValueError:
        return None  # unknown phase name — the schema enum will reject it upstream; don't gate here
    return PHASE_ORDER[i - 1] if i > 0 else None


def _phase_admitted_for(ev, hist, phase):
    """Has `phase` been admitted for this deliverable (or for its parent)?

    **Why walk up to the parent.** Founding admits requirements/design per objective — naturally,
    since that is where the design happens. /org-work, on the other hand, uses the task Issue
    number as the deliverable and emits `phase_started{implement}`. Those are different strings,
    so an admission on the objective did not apply to the task, and a task was rejected even when
    the instructions had been followed exactly (found in practice).

    Making every task admit requirements/design again would be pure ceremony: admitting the same
    design N times. **The design happened at the level of the objective**, so the correct thing is
    for the child tasks to inherit that admission. Inheritance follows `parent` in the payload
    (written by /org-decompose).

    A deliverable with no parent still looks only at its own admission, exactly as before — its
    behaviour does not change."""
    target = ev["payload"].get("deliverable")
    parent = ev["payload"].get("parent")          # the objective Issue /org-decompose writes onto the task番号
    for e in hist:
        if e["class"] != "phase_admitted":
            continue
        if e["payload"].get("phase") != phase or e["payload"].get("verdict") != "pass":
            continue
        d = e["payload"].get("deliverable")
        if _same_deliverable(d, target):
            return True
        if parent is not None and _same_deliverable(d, parent):
            return True                            # inherit the parent objective's admission
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
    # Look at the identifiers as a bundle (_same_work). Comparing only `claim_id == candidate_id`
    # failed to correlate two real refutations that had been written with deliverable/issue — and
    # worse, None == None compared equal, which **disabled the deploy gate entirely** (it passed).
    "result_deployed": lambda ev, hist: any(
        e["class"] == "refutation_attempted"
        and _same_work(e["payload"], ev["payload"], hist)
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


_GOAL_CLASSES = {
    "goal_started", "goal_progressed", "goal_paused", "goal_blocker_observed",
    "goal_blocked", "goal_resumed", "goal_completed", "goal_host_synced",
}


def goal_states_from_events(events):
    """Fold portable goal events into deterministic current states, oldest goal first."""
    states = {}
    for event in events:
        if event.get("class") not in _GOAL_CLASSES:
            continue
        payload = event.get("payload") or {}
        goal_id = str(payload.get("goal_id") or "")
        if not goal_id:
            continue
        if event["class"] == "goal_started":
            state = {
                "goal_id": goal_id,
                "objective": payload.get("objective"),
                "status": "active",
                "session_id": payload.get("session_id"),
                "harness": payload.get("harness"),
                "started_seq": event.get("seq"),
                "updated_seq": event.get("seq"),
                "progress": None,
                "blocker": None,
                "evidence": [],
                "host_sync": {},
            }
            states[goal_id] = state
            continue
        state = states.get(goal_id)
        if not state:
            continue
        state["updated_seq"] = event.get("seq")
        if event["class"] == "goal_progressed":
            state["status"] = "active"
            state["progress"] = {
                key: payload.get(key) for key in ("summary", "next_step", "evidence")
            }
            state["blocker"] = None
        elif event["class"] == "goal_paused":
            state["status"] = "paused"
            state["progress"] = {"summary": payload.get("reason"),
                                 "next_step": payload.get("next_step")}
        elif event["class"] == "goal_blocker_observed":
            prior = state.get("blocker") or {}
            occurrences = prior.get("occurrences", 0) + 1 \
                if prior.get("reason") == payload.get("blocker") else 1
            state["blocker"] = {"reason": payload.get("blocker"),
                                "occurrences": occurrences,
                                "evidence": payload.get("evidence") or []}
        elif event["class"] == "goal_blocked":
            state["status"] = "blocked"
            state["blocker"] = {"reason": payload.get("blocker"),
                                "occurrences": payload.get("occurrences"),
                                "evidence": payload.get("evidence") or []}
        elif event["class"] == "goal_resumed":
            state["status"] = "active"
            state["session_id"] = payload.get("session_id")
            state["harness"] = payload.get("harness")
            state["blocker"] = None
        elif event["class"] == "goal_completed":
            state["status"] = "complete"
            state["summary"] = payload.get("summary")
            state["evidence"] = payload.get("evidence") or []
        elif event["class"] == "goal_host_synced":
            state.setdefault("host_sync", {})[str(payload.get("harness") or "unknown")] = {
                "state": payload.get("native_state"),
                "native_ref": payload.get("native_ref"),
                "detail": payload.get("detail"),
                "assurance": payload.get("assurance"),
                "seq": event.get("seq"),
            }
    return sorted(states.values(), key=lambda state: state.get("started_seq") or 0)


def _goal_evidence_error(reference, ledger_root, history):
    """Resolve completion evidence without network access; return None only for a real object."""
    reference = str(reference or "")
    if reference.startswith("ledger:"):
        raw = reference[len("ledger:"):]
        if not raw.isdigit() or int(raw) <= 0:
            return f"invalid ledger evidence reference {reference!r}"
        if not any(event.get("seq") == int(raw) for event in history):
            return f"ledger evidence does not exist: {reference}"
        return None
    org_root = os.path.realpath(os.path.join(ledger_root, "..", ".."))
    if reference.startswith("file:"):
        raw = reference[len("file:"):]
        target = os.path.realpath(raw if os.path.isabs(raw) else os.path.join(org_root, raw))
        try:
            inside = os.path.commonpath([org_root, target]) == org_root
        except ValueError:
            inside = False
        if not inside:
            return f"file evidence escapes the organization root: {reference}"
        if not os.path.isfile(target):
            return f"file evidence does not exist: {reference}"
        return None
    if reference.startswith("git:"):
        revision = reference[len("git:"):]
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", revision):
            return f"invalid git evidence reference {reference!r}"
        try:
            run = subprocess.run(
                ["git", "-C", org_root, "cat-file", "-e", revision + "^{commit}"],
                capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"cannot inspect git evidence {reference}: {exc}"
        if run.returncode != 0:
            return f"git evidence does not resolve to a commit: {reference}"
        return None
    return (f"unsupported completion evidence {reference!r}; use file:<path>, git:<commit>, "
            "or ledger:<seq> so the writer can resolve it")


def _goal_lifecycle_violation(event, history, ledger_root):
    """Enforce one unfinished goal and session compare-and-swap inside the ledger lock."""
    cls = event.get("class")
    if cls not in _GOAL_CLASSES:
        return None
    payload = event.get("payload") or {}
    goal_id = str(payload.get("goal_id") or "").strip()
    session_id = str(payload.get("session_id") or "").strip()
    if not goal_id or not session_id:
        return f"{cls} rejected — goal_id and session_id must be non-empty"
    states = goal_states_from_events(history)
    unfinished = [state for state in states if state.get("status") != "complete"]
    if cls == "goal_started":
        if not str(payload.get("objective") or "").strip():
            return "goal_started rejected — objective must be concrete and non-empty"
        if not str(payload.get("harness") or "").strip():
            return "goal_started rejected — harness must be non-empty"
        if unfinished:
            current = unfinished[-1]
            return ("goal_started rejected — an unfinished goal already exists: "
                    f"{current['goal_id']} ({current['status']}); complete it before starting another")
        if any(state.get("goal_id") == goal_id for state in states):
            return f"goal_started rejected — goal_id {goal_id!r} was already used"
        return None
    current = next((state for state in reversed(states) if state.get("goal_id") == goal_id), None)
    if not current:
        return f"{cls} rejected — goal {goal_id!r} has not been started"
    if cls == "goal_host_synced":
        if session_id != current.get("session_id"):
            return (f"goal_host_synced rejected — session {session_id!r} does not own goal {goal_id}; "
                    "resume it first")
        if not str(payload.get("harness") or "").strip():
            return "goal_host_synced rejected — harness must be non-empty"
        return None
    if cls == "goal_resumed":
        expected = str(payload.get("from_session_id") or "")
        actual = str(current.get("session_id") or "")
        if current.get("status") == "complete":
            return f"goal_resumed rejected — goal {goal_id} is complete"
        if expected != actual:
            return (f"goal_resumed rejected — concurrent resume lost compare-and-swap: expected "
                    f"session {expected!r}, current owner is {actual!r}")
        if session_id == actual and current.get("status") == "active":
            return f"goal_resumed rejected — session {session_id!r} already owns goal {goal_id}"
        if not str(payload.get("reason") or "").strip():
            return "goal_resumed rejected — reason is required"
        if not str(payload.get("harness") or "").strip():
            return "goal_resumed rejected — harness must be non-empty"
        return None
    if current.get("status") == "complete":
        return f"{cls} rejected — goal {goal_id} is complete"
    if session_id != str(current.get("session_id") or ""):
        return (f"{cls} rejected — session {session_id!r} does not own goal {goal_id}; current owner "
                f"is {current.get('session_id')!r}. Run org-goal resume first")
    if cls in {"goal_progressed", "goal_paused", "goal_blocker_observed", "goal_completed"} \
            and current.get("status") != "active":
        return (f"{cls} rejected — goal {goal_id} is {current.get('status')}; resume it before "
                "recording more work")
    if cls == "goal_progressed" and (not str(payload.get("summary") or "").strip() or
                                      not str(payload.get("next_step") or "").strip()):
        return "goal_progressed rejected — summary and next_step must be non-empty"
    if cls == "goal_paused" and (not str(payload.get("reason") or "").strip() or
                                  not str(payload.get("next_step") or "").strip()):
        return "goal_paused rejected — reason and next_step must be non-empty"
    if cls == "goal_blocker_observed" and (
            not str(payload.get("blocker") or "").strip() or not (payload.get("evidence") or [])):
        return "goal_blocker_observed rejected — blocker and at least one evidence item are required"
    if cls == "goal_blocked":
        blocker = str(payload.get("blocker") or "")
        matching = 0
        for prior in reversed(history):
            prior_payload = prior.get("payload") or {}
            if str(prior_payload.get("goal_id") or "") != goal_id:
                continue
            if prior.get("class") == "goal_blocker_observed" and \
                    str(prior_payload.get("blocker") or "") == blocker:
                matching += 1
                continue
            if prior.get("class") == "goal_host_synced":
                continue
            break
        if current.get("status") != "active" or matching < 3 or payload.get("occurrences") != matching:
            return (f"goal_blocked rejected — the same blocker needs 3 consecutive observations; "
                    f"found {matching}")
    if cls == "goal_completed":
        if not str(payload.get("summary") or "").strip():
            return "goal_completed rejected — summary must be non-empty"
        evidence = payload.get("evidence") or []
        if not evidence:
            return "goal_completed rejected — at least one resolvable evidence reference is required"
        for reference in evidence:
            error = _goal_evidence_error(reference, ledger_root, history)
            if error:
                return f"goal_completed rejected — evidence audit failed: {error}"
    return None

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



def _enforce_attested():
    """Does a control event require a receipt-derived identity? **Treated as three-valued.**

    **Never rest on a setting the caller can erase.** Measured (audit):
      - merely adding `ORG_REQUIRE_ATTESTED_IDENTITY=0` made the enforcement vanish
      - merely **deleting** `constitution.yaml` made the enforcement vanish

    Therefore:
      1. **Read the policy from a root-owned location** (`ORG_POLICY_FILE`, default
         `/usr/local/etc/orgforge/policy.yaml`). A declaration there is **final** and cannot be
         overridden by env or by the org's constitution.
      2. In an org with no policy (stage A / not yet adopted), read the constitution. **Deletion is
         not "disabled", it is "undeclared"** — so that an org which had it enabled does not become
         defenceless merely by deleting the file, **any record of it once being enabled makes the
         disappearance a refusal** (the sticky check below).
      3. Unreadable, or the wrong type: stop (fail-closed).

    The env override is **for development, and only when there is no policy**; it additionally
    requires `ORG_ALLOW_POLICY_ENV=1` — no escape hatch that takes effect silently.
    """
    # (1) a root-owned policy is final
    pol = os.environ.get("ORG_POLICY_FILE") or "/usr/local/etc/orgforge/policy.yaml"
    if os.path.isfile(pol):
        try:
            st = os.stat(pol)
        except OSError as e:
            raise SystemExit(f"cannot stat the policy: {e}\n  file: {pol}")
        if st.st_uid != 0 and st.st_uid != os.getuid():
            raise SystemExit(f"the policy is owned by neither root nor you (uid={st.st_uid}): {pol}")
        if st.st_mode & 0o022:
            raise SystemExit(f"the policy is group/world-writable (mode "
                             f"{oct(st.st_mode & 0o777)}): {pol}\n"
                             f"  **whoever can write it can switch enforcement off.**")
        try:
            import yaml
            with open(pol, encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
        except Exception as e:
            raise SystemExit(f"the policy cannot be read, so enforcement cannot be determined: {e}\n"
                             f"  file: {pol}\n  **if it cannot be determined, stop.**")
        if not isinstance(doc, dict):
            raise SystemExit(f"the policy is not a map: {pol}")
        v = doc.get("require_attested_identity")
        if v is not None:
            if not isinstance(v, bool):
                raise SystemExit(f"the policy's require_attested_identity is not a boolean"
                                 f" ({v!r}): {pol}")
            return v            # **This is final.** Neither env nor the constitution overrides it

    # (2) env is for development when there is no policy. **It never takes effect silently.**
    env = os.environ.get("ORG_REQUIRE_ATTESTED_IDENTITY")
    if env is not None:
        if os.environ.get("ORG_ALLOW_POLICY_ENV") != "1":
            raise SystemExit(
                "ORG_REQUIRE_ATTESTED_IDENTITY is set, but switching enforcement through an "
                "environment variable is not permitted.\n"
                "  **enforcement must not rest on something the caller can unset** — measured: "
                "adding this variable alone made it disappear.\n"
                "  To use it in development, state ORG_ALLOW_POLICY_ENV=1 as well "
                "(production uses a root-owned policy).")
        if env not in ("0", "1"):
            raise SystemExit(f"ORG_REQUIRE_ATTESTED_IDENTITY is not 0/1 ({env!r}).")
        return env == "1"

    # (3) the org's constitution
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from discover import constitution, ledger_root
        path = constitution()
    except Exception as e:
        raise SystemExit(f"the constitution's location cannot be resolved, so enforcement cannot be determined: {e}")
    declared = None
    if path and os.path.isfile(path):
        try:
            import yaml
        except Exception:
            raise SystemExit("PyYAML is missing, so the constitution cannot be read and enforcement "
                         "cannot be determined.")
        try:
            with open(path, encoding="utf-8") as f:
                c = yaml.safe_load(f)
        except Exception as e:
            raise SystemExit(f"constitution.yaml cannot be parsed, so this cannot be determined: {e}\n"
                             f"  file: {path}\n  **Do not reinterpret corruption as "
                             f"'no enforcement'.**")
        if c is not None:
            if not isinstance(c, dict):
                raise SystemExit(f"constitution.yaml is not a map: {path}")
            enf = c.get("enforcement")
            if enf is not None and not isinstance(enf, dict):
                raise SystemExit(f"enforcement is not a map: {path}")
            j = ((enf or {}).get("judges") or {})
            if not isinstance(j, dict):
                raise SystemExit(f"enforcement.judges is not a map: {path}")
            v = j.get("require_attested_identity")
            if v is not None:
                if not isinstance(v, bool):
                    raise SystemExit(f"require_attested_identity is not a boolean ({v!r}): {path}")
                declared = v

    # (4) **sticky.** In an org where it was once enabled, stop if the declaration has vanished.
    #     Measured: merely deleting the constitution made the enforcement vanish. "Deleted" is not
    #     "disabled".
    try:
        root = ledger_root()
        marker = os.path.join(root, "attested-identity-enabled") if root else None
    except Exception:
        marker = None
    if declared is True and marker:
        try:
            if not os.path.exists(marker):
                with open(marker, "w", encoding="utf-8") as f:
                    f.write("require_attested_identity was enabled here\n")
        except OSError:
            pass
    if declared is None and marker and os.path.exists(marker):
        raise SystemExit(
            f"this org previously had require_attested_identity enabled, but the declaration is "
            f"now absent.\n"
            f"  trace: {marker}\n"
            f"  **Deleting a declaration is not disabling it.** Establish whether the constitution "
            f"was lost or removed deliberately.\n"
            f"  To genuinely disable it, state `require_attested_identity: false` in the "
            f"constitution and clear this trace.")
    return bool(declared)



# **A judgment at the core of control requires authentication at the door.**
# This check originally lived inside `_distinct_actor_violation()`, and that function returns
# immediately when the class is not in `DISTINCT_ACTOR` — so it **was never applied to
# `verdict_provisional` at all** (measured, B1: writing two provisionals with no receipt was enough
# to create a joint admission).
# SoD (is it the same actor?) and attestation (has the principal been verified?) are separate
# controls, so neither may ride on the other's applicability condition.
_ATTESTED_REQUIRED = ("admission_decided", "refutation_attempted", "verdict_provisional")


def _attestation_violation(ev):
    """In authenticated mode, return the reason for refusal when there is no identity derived
    from a verified receipt."""
    if ev.get("class") not in _ATTESTED_REQUIRED:
        return None
    if not _enforce_attested():
        return None
    if (ev.get("_verified_identity") or {}).get("decision_by"):
        return None
    return (f"{ev['class']} cannot be recorded through a generic append "
            f"(require_attested_identity is enabled).\n"
            f"  **Writing identity_assurance into the payload is not evidence** — never use "
            f"something the writer can set as the thing you check.\n"
            f"  A judgment can only be recorded through **a path that verified a receipt**:\n"
            f"    github_sync.py provisional --receipt <a receipt signed by the judge> …\n"
            f"  That path verifies the receipt and derives the identity fields itself.")



def _declared_lineage():
    """The lineage the org declared (`enforcement.judges.lineage`); None if undeclared.

    **Never rest on a setting the caller can erase** — as in `_enforce_attested()`, read it from
    the root-owned policy / the constitution. Unreadable or corrupt does not mean "no enforcement".
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from discover import constitution as _constitution
        path = os.environ.get("ORG_POLICY_FILE") or _constitution()
    except Exception:
        return None
    if not path or not os.path.exists(path):
        return None
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    j = (((doc.get("enforcement") or {}) if isinstance(doc.get("enforcement"), dict) else {})
         .get("judges") or {})
    v = j.get("lineage") if isinstance(j, dict) else None
    return v if isinstance(v, str) else None


# **Only an affirmative decision requires independence.**
# `admit` and `survives` are decisions that LET WORK THROUGH; if either can be written alone, the
# two-lineage rule is not being enforced.
# `reject` / `park` / `refuted` point the other way — they stop work — so they may be recorded
# alone (block them and there is no way left to record a judgment at all).
_POSITIVE_VERDICTS = {"admission_decided": {"admit"},
                      "refutation_attempted": {"survives"}}


def _dual_lineage_violation(ev):
    """In an org that declared cross-harness, return why an affirmative decision via generic
    append is refused.

    Measured (B4): a generic append of one valid receipt recorded a single `admission_decided`
    directly. A joint-derivation path may exist, but **if the record can be written without going
    through it, the two-lineage rule is not being enforced.**
    """
    cls = ev.get("class")
    positives = _POSITIVE_VERDICTS.get(cls)
    if not positives:
        return None
    if (ev.get("payload") or {}).get("verdict") not in positives:
        return None                      # a negative decision may be recorded alone
    if _declared_lineage() != "cross-harness":
        return None                      # leave the compatibility path for same-harness orgs
    if _inside_writer():
        return None                      # the writer's own derivation (derive-admission) passes
    return (f"an affirmative {cls} decision "
            f"({(ev.get('payload') or {}).get('verdict')}) cannot be recorded through a generic "
            f"append.\n"
            f"  This org declares **cross-harness** (two lineages). If one signer can let it "
            f"through, the two-lineage rule is not being enforced.\n"
            f"  Record a provisional from each lineage, then have the writer derive from them:\n"
            f"    github_sync.py provisional --receipt <the judge's receipt> …  (one per "
            f"lineage)\n"
            f"    ledger.py derive-admission --issue <n> --event {cls}\n"
            f"  A negative decision (reject / park / refuted) can be recorded alone.")


def _inside_writer():
    """**Are we being called from inside the writer?** Decided in a form the caller cannot simply
    assert.

    Measured (re-audit): merely adding `ORG_INSIDE_WRITER=1` to the environment let a single signer
    write a cross-harness admission directly, and walked straight through the single-writer gate.
    **The input to a check must not be writable by the thing being checked.**

    writerd mints an unguessable token per start-up and passes it only to its child processes.
    So the condition is not "the value is 1" but "**it is a token of unguessable length**".
    A guessable value such as `1` or `true` is no evidence of being inside the writer.

    **This is not a boundary.** A caller with the same UID can mint its own 64 hex digits and
    assert them — a child process cannot verify that the token came from writerd. What this raises
    is the bar from "passes by guesswork" to "requires deliberate forgery"; **the real boundary is
    the separate UID of Stage B** (where OS permissions forbid writing to the ledger).
    Do not call this `separate_uid` at stage A.
    """
    v = os.environ.get("ORG_INSIDE_WRITER") or ""
    if len(v) < 32:
        return False
    try:
        int(v, 16)
    except ValueError:
        return False
    return True


def _distinct_actor_violation(ev, hist):
    """Return a rejection reason if this event's actor already acted as maker/prior-judge for the same
    candidate, else None. Compares the ACTOR (envelope), never a payload field — a payload role name is
    agent-authored and therefore forgeable; the actor is the recorded writer."""
    rule = DISTINCT_ACTOR.get(ev["class"])
    if not rule:
        return None
    key_field, conflicting, why = rule
    ids = _correlation_ids(ev["payload"])
    if not ids:
        # **Refuse** a judgment that carries no correlation key at all. This used to be let
        # through ("the payload-shape check is elsewhere", said the comment — but that elsewhere
        # did not exist), and in practice a maker was able to admit its own deliverable. A judgment
        # that cannot be correlated is a judgment that cannot be verified — it is not "a judgment
        # that passed verification". Passing it silently is the worst outcome: nobody can see that
        # control is not in force, while the hash chain lends its endorsement to the forgery.
        return (f"{ev['class']} rejected — the judged subject cannot be identified: payload "
                f"none of {' / '.join(_CORRELATION_KEYS)} is present.\n"
                f"  Without a correlation key there is no way to check whether the maker and the "
                f"gate are the same actor, and this control silently stops working ({why})\n"
                f"  Put the target Issue number or the candidate_id into the payload and run "
                f"again.")
    # **Changing `--actor` must not be enough to evade separation of duties.**
    # Measured: a maker's own self-admission is refused, but the same process passing
    # `--actor gate-alias` got through — with the chain still intact. If the name can be changed at
    # will, comparing names means nothing.
    #
    # So **a judgment at the core of control requires a `decision_by` derived from a verified
    # receipt**. Without a receipt the judgment is no basis for enforcing independence — it can
    # still be recorded, but it is recorded as `identity_assurance: claimed` and cannot be used to
    # produce an admission.
    _ENFORCED = {"admission_decided", "refutation_attempted"}
    if ev["class"] in _ENFORCED and _enforce_attested():
        pl = ev.get("payload") or {}
        # **The writer derives the identity.** A value written into the payload is self-reported,
        # not evidence — measured (audit): simply writing `identity_assurance: attested` and a
        # `decision_by` was enough for the admit to pass, chain intact. And **our own test had
        # pinned that as the expected behaviour.** Never use something writable as the thing you
        # check.
        if not (ev.get("_verified_identity") or {}).get("decision_by"):
            return (f"{ev['class']} cannot be recorded through a generic append "
                    f"(require_attested_identity is enabled).\n"
                    f"  **Writing identity_assurance into the payload is not evidence** — never "
                    f"use something writable as the thing you check.\n"
                    f"  **Changing `--actor` alone would evade separation of duties** — measured, "
                    f"a maker's\n"
                    f"  own self-admission is refused, yet the same process passed by giving "
                    f"another name.\n"
                    f"  A judgment can only be recorded through **a path that verified a "
                    f"receipt**:\n"
                    f"    github_sync.py provisional --receipt <a receipt signed by the judge> …\n"
                    f"  That path verifies the receipt and derives the identity fields itself.\n"
                    f"  (This enforcement applies when the constitution's\n"
                    f"   enforcement.judges.require_attested_identity is true. It defaults to "
                    f"false, so orgs can migrate in stages.)")

    # **Separation of duties compares `decision_by` against `decision_by` (H1).** Never compare
    # `recorded_by` — under proxy recording that is always the same principal, so comparing it
    # would make every legitimate operation a violation.
    # For events with no `decision_by` (pre-0.36.x / no receipt), use the legacy `actor` **as a
    # claimed attribute**. It is never promoted — being comparable and being authenticated are
    # different things.
    def _who(e):
        return (e.get("payload") or {}).get("decision_by") or e.get("actor")

    actor = _who(ev)
    for e in hist:
        if e["class"] not in conflicting:
            continue
        # Match on the identifiers as a bundle — whether the writer used deliverable or
        # candidate_id, it correlates as the same work (look at only one and control disappears
        # the moment someone switches key).
        if _same_work(e["payload"], ev["payload"], hist) and _who(e) == actor:
            shared = sorted(_correlation_ids(e["payload"]) & ids)
            if shared:
                what = ", ".join(shared)
            else:
                # Matched via an alias. **Show how the connection was made** — a message that
                # leaves the person told "this is the same work" unable to either accept or dispute
                # it is not a reason for refusal at all.
                mine = ", ".join(sorted(ids))
                theirs = ", ".join(sorted(_correlation_ids(e["payload"])
                                          | _alias_ids(e["payload"])))
                what = (f"the same work (this judgment names {mine}, seq {e.get('seq')} names "
                        f"{theirs}; the ledger's alias correspondence resolved them as one)")
            return (f"{ev['class']} rejected — actor {actor!r} already acted as {e['class']} for "
                    f"{what}: {why}")
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

# ── views read `views:` in ledger-schema.yaml as the single source of truth ──────────────────
# This used to hardcode 13 views while the schema declared 26. What the drift actually cost:
#   - `/org-work` could not fetch parts_inventory, so the whole command failed to start
#   - **all three of the gate's context_pack views and both of the skeptic's were unimplemented.**
#     organization.yaml could declare "the gate admits by looking at these three" and at runtime
#     not one of them could be fetched. SoD (maker ≠ checker) is a central claim, yet the checker
#     could not obtain the material it was to judge by
#   - and `org_lint` passed anyway (the CP check only asked "is it defined in the schema?", never
#     "does the tool implement it?")
# Reading the schema means adding a view no longer requires touching Python, so the drift cannot
# structurally recur.
_VIEW_FROM_CACHE = None


def _schema_path():
    """Where ledger-schema.yaml lives: look at the org's copy first, then the plugin's template.

    `ORG_LEDGER_SCHEMA` wins (the same discipline as the discover family — env is the escape hatch
    for when an override is genuinely needed). **Being able to test the state where it points at a
    broken or missing schema is itself a requirement**: "do not write while unable to validate" is
    meaningless if it cannot actually be confirmed.
    """
    env = os.environ.get("ORG_LEDGER_SCHEMA")
    if env:
        return env if os.path.exists(env) else None
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
    """Read {view_id: [derived-from classes]} from the schema; an empty dict if it cannot be read."""
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


# The census views count every class, so treat them as "*" regardless of the schema's `from`
_ALL_CLASS_VIEWS = ("ledger_census", "recent_ledger_census")


# ══ Writer Phase 0 — schema boundary / lock / fsync / HEAD recovery ══════════
#
# **Do not touch actor here.** This phase covers only "the write does not get corrupted" and "a
# new event has been validated"; authenticating who wrote it (identity_assurance) is a separate
# axis handled later. Mixing them invites the misreading that validating the schema also makes the
# actor trustworthy.
#
#   validation_assurance:  legacy_unvalidated | validated:v1
#   identity_assurance:    claimed | observed | attested | authenticated   ← not started
#
# **The writer stamps schema_version.** If a client could specify it, it could name a laxer
# version and slip past validation (a downgrade). Specifying it is refused.

LEDGER_SCHEMA_VERSION = 1          # the ledger's format. Deliberately not tied to the plugin's
                                   # version — a code fix must not imply the format changed.


def _envelope_core_keys(ev):
    """The fields the hash covers. **Switched per version.**

    From v1 onward the hash includes `schema_version` — without it, a rewrite would go undetected
    and refusing downgrades would mean nothing. Legacy events (no version) are validated over the
    original six fields.
    This is the concrete form of the discipline that a validator adds versions rather than altering
    past ones.
    """
    if ev.get("schema_version"):
        return ("id", "seq", "ts", "actor", "class", "payload",
                "schema_id", "schema_version", "schema_sha256")
    return ("id", "seq", "ts", "actor", "class", "payload")


def schema_digest():
    """A digest of the ledger-schema.yaml in use, so a swapped format can be detected after the
    fact."""
    path = _schema_path()
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:32]


def load_schema_snapshot():
    """Read the schema **exactly once, and make the parse result and the digest one snapshot**.

    If validation and digest collection each read the schema separately, it can be swapped in
    between (TOCTOU).
    Build one snapshot inside the lock and use that same one for both validation and the digest.

    Returns: (snapshot, error). If there is an error, refuse the new append (fail-closed).
    """
    path = _schema_path()
    if not path or not os.path.isfile(path):
        return None, ("ledger-schema.yaml cannot be found. **Do not write while unable to "
                      "validate** — something unvalidated sitting in the ledger AS validated is "
                      "the worse outcome.")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as e:
        return None, f"cannot read ledger-schema.yaml: {e}"
    try:
        import yaml
        doc = yaml.safe_load(raw.decode("utf-8")) or {}
    except Exception as e:
        return None, f"cannot parse ledger-schema.yaml: {e}"
    ec = doc.get("event_classes")
    if not isinstance(ec, dict):
        return None, "ledger-schema.yaml has no event_classes (or it is not a map)."
    v = doc.get("validation") or {}
    return {
        "path": path,
        "digest": hashlib.sha256(raw).hexdigest()[:32],
        "classes": set(ec.keys()),
        "fields": {k: set(s.keys()) for k, s in ec.items() if isinstance(s, dict)},
        "required": v.get("required") or {},
        "require_any": v.get("require_any") or {},
        "closed": set(v.get("additional_properties_false") or []),
        "writer_only": set(v.get("writer_only") or []),
        "enums": v.get("enums") or {},
        "types": v.get("types") or {},
    }, None


def _check_type(name, val):
    if name == "list":
        return isinstance(val, list)
    if name == "int_or_str":
        return isinstance(val, (int, str)) and not isinstance(val, bool)
    if name == "int":
        return isinstance(val, int) and not isinstance(val, bool)
    if name == "str":
        return isinstance(val, str)
    if name == "map":
        return isinstance(val, dict)
    if name == "number":
        # bool is a subclass of int, so exclude it. NaN / inf are not treated as numbers — mixed
        # into a total they break comparison, and the cap decision stops meaning anything.
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            return False
        return val == val and val not in (float("inf"), float("-inf"))
    # **An unknown type name does not pass.** Returning True silently turns a typo in the schema
    # into a disabled check — write `lst` for `list` and that check vanishes, with no route by
    # which anyone would notice it had gone.
    return None                       # the caller refuses it as an error in the schema


def validate_event(cls, payload, snap, writer_op=None):
    """Validate a new append. **Three axes, kept separate.**

      1. only for classes that declare `required`, refuse a missing mandatory field
      2. for declared fields, validate enum / type **when the field is present**
      3. only for classes with additional_properties_false, refuse undeclared fields

    Making every class closed-world at once turns any schema drift into "the whole organisation
    stops recording". That is not fail-closed; it is an availability incident caused by a known
    migration gap.

    Returns: (error, warnings). An error refuses; warnings are recorded and let through.
    """
    if cls not in snap["classes"]:
        near = sorted(k for k in snap["classes"] if k[:4] == cls[:4])
        return (f"unknown event class {cls!r} (not in event_classes of ledger-schema.yaml). "
                + (f"\n  did you mean: {', '.join(near)}" if near else "")
                + "\n  To add a class, declare it in the schema before writing it — an "
                  "undeclared class appears in no projection and no sensor, so writing it means "
                  "nobody reads it."), []
    if not isinstance(payload, dict):
        return f"payload must be a map (got {type(payload).__name__}).", []

    # **A writer-only class can be written only by that writer operation.** If the records a
    # check relies on can be written by an ordinary append, the check itself is void (measured:
    # inserting a single negative exposure made the cap disappear).
    if cls in snap["writer_only"] and writer_op != cls:
        return (f"{cls} is a writer-only class and cannot be written by a generic append"
                f"（ledger-schema.yaml validation.writer_only）。\n"
                f"  The records a check relies on must be writable only by the side doing the "
                f"checking — if this record can be written freely, the check itself is void.\n"
                f"  For a cap reservation, use `ledger.py reserve-exposure`."), []

    given = {k for k in payload if k != "_nk"}

    # (1) required (only for classes that declare it)
    req = snap["required"].get(cls) or []
    missing = [k for k in req if k not in payload or payload[k] in (None, "")]
    if missing:
        return (f"{cls} is missing required fields: {', '.join(missing)}\n"
                f"  （ledger-schema.yaml validation.required.{cls}）\n"
                f"  A control event with no contents is of no use to a check — an empty record "
                f"creates only the APPEARANCE of having been recorded."), []

    # (1') correlation key — **any one of them suffices.** Which one is used differs by path
    #      (union-find bundles them). A judgment with none of them is a judgment whose subject is
    #      unknown, and so is of no use to a check.
    anyof = snap["require_any"].get(cls) or []
    if anyof and not any(payload.get(k) not in (None, "") for k in anyof):
        return (f"{cls} has no correlation key: exactly one of {' / '.join(anyof)} is "
                f"required.\n"
                f"  A record whose subject is unknown is of no use to a check or to a "
                f"projection."), []

    # (2) enum / type (validated **when the field is present**)
    for f, allowed in (snap["enums"].get(cls) or {}).items():
        if f in payload and payload[f] not in allowed:
            return (f"{cls}.{f} = {payload[f]!r} is not an allowed value: "
                    f"{'|'.join(map(str, allowed))}"), []
    for f, tname in (snap["types"].get(cls) or {}).items():
        if f not in payload:
            continue
        r = _check_type(tname, payload[f])
        if r is None:
            return (f"validation.types.{cls}.{f} in ledger-schema.yaml names an unknown type "
                    f"names {tname!r} (expected one of list | int | str | map | int_or_str).\n"
                    f"  **A typo in the schema does not pass silently** — let it through and that "
                    f"check stays gone, with no route by which anyone notices."), []
        if not r:
            return (f"{cls}.{f} has the wrong type (expected {tname}, got "
                    f"{type(payload[f]).__name__})"), []

    # (3) undeclared fields — allowed by default, and recorded as drift
    declared = snap["fields"].get(cls, set())
    unknown = sorted(given - declared)
    if unknown and cls in snap["closed"]:
        return (f"{cls} carries undeclared fields: {', '.join(unknown)}\n"
                f"  This class is additional_properties: false (it is core to control). "
                f"To add a field, declare it in the schema before writing it."), []
    warns = ([f"{cls} has undeclared fields: {', '.join(unknown)} — they can be written, but "
              f"they appear in no projection and no sensor. The schema and reality have "
              f"drifted apart"] if unknown else [])
    return None, warns



def _now_iso():
    """The writer's own clock. **Never write "UNSET".**

    Acceptance condition: the writer stamps the timestamp. If a client could decide it, it could
    fake the ordering and thereby evade the cap's time window. Real data still holds events with
    `ts: "UNSET"`, and any view or sensor that filters by window either drops them silently or
    places them outside the boundary.

    An event `id` is derived only from (seq, class, payload), so putting a clock here does not
    cost append its determinism — the same logical event still gets the same id.
    """
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _check_backfill_ts(ts):
    """Validate a backfill timestamp. **Matching the shape is not enough.**

    0.33.1 looked only at a regex, so `2026-99-99T99:99:99Z` passed (measured). Parse it as a real
    date-time and **refuse the future, and a past that is too distant** — being able to fake the
    ordering means being able to evade the cap's time window.

    Authority (who may backfill at all) belongs to identity_assurance and cannot be settled here.
    **Saying what it cannot settle** is also part of this function's job.
    """
    import datetime as _dt
    if not isinstance(ts, str) or not re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts):
        return (f"--backfill-ts {ts!r} is not ISO8601 UTC"
                f"（YYYY-MM-DDTHH:MM:SSZ）。")
    try:
        when = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc)
    except ValueError as e:
        return (f"--backfill-ts {ts!r} is not a date-time that exists ({e}).\n"
                f"  Matching the shape is not enough — values like 2026-99-99T99:99:99Z used to "
                f"pass.")
    now = _dt.datetime.now(_dt.timezone.utc)
    if when > now + _dt.timedelta(minutes=5):
        return (f"--backfill-ts {ts} is in the future (now "
                f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')}).\n"
                f"  backfill exists to **fill in a moment that already happened**, not to stamp a "
                f"date ahead of time. A future timestamp can evade a window-filtered cap.")
    if when < now - _dt.timedelta(days=int(os.environ.get("ORG_BACKFILL_MAX_DAYS", "90"))):
        return (f"--backfill-ts {ts} is too far in the past (earlier than "
                f"{os.environ.get('ORG_BACKFILL_MAX_DAYS', '90')} days).\n"
                f"  Writing at an old moment puts something that happened NOW into a past window, "
                f"where the cap no longer counts it.\n"
                f"  If there is a legitimate reason, widen it explicitly with "
                f"ORG_BACKFILL_MAX_DAYS.")
    return None


def _canonical(ev):
    """The bytes the hash covers: id,seq,ts,actor,class,payload in a fixed, sorted-key form.
    Canonical JSON (sorted keys, no incidental whitespace) so the hash is reproducible."""
    core = {k: ev[k] for k in _envelope_core_keys(ev) if k in ev}
    return json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(prev_hash, ev):
    return hashlib.sha256((prev_hash + _canonical(ev)).encode("utf-8")).hexdigest()



class _LedgerLock:
    """An exclusive lock making the whole append one critical section.

    **Without it, parallel appends all compute the same seq.** Measured (audit): with 12 in
    parallel, all 12 came out as seq=1 and validation failed on seq gap/disorder. The whole of
    `read the log → decide the seq → write → update HEAD` has to be a single operation.

    This org runs six worktrees in parallel, so the danger is not theoretical.
    """

    def __init__(self, root):
        self.path = os.path.join(root, "LOCK")
        self.fh = None
        self.locked = False
        self.error = None          # why the lock failed; the caller stops the append

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        try:
            self.fh = open(self.path, "a+")
        except Exception as e:
            self.error = f"cannot open the LOCK file ({e}): {self.path}"
            return self
        # **If it cannot be locked, do not write.** Warning and carrying on lets parallel appends
        # compute the same seq and break the chain (measured: 12 in parallel, all seq=1). The only
        # escape hatch is an explicit environment variable, and it says outright that **the
        # guarantee it asks for (serial execution) is not something the tool can confirm.**
        # ORG_LEDGER_FORCE_LOCK_FAIL=1 exists for fault injection — without being able to test the
        # lock's fail-closed behaviour, we cannot claim it IS fail-closed.
        try:
            if os.environ.get("ORG_LEDGER_FORCE_LOCK_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_LOCK_FAIL=1 (fault injection)")
            import fcntl
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
            self.locked = True
        except Exception as e:
            if os.environ.get("ORG_LEDGER_ALLOW_UNLOCKED") == "1":
                print(f"ledger: appending without a lock "
                      f"(ORG_LEDGER_ALLOW_UNLOCKED=1, reason: {e}).\n"
                      f"  **Do not run this in parallel.** The tool cannot confirm the guarantee "
                      f"of serial execution.",
                      file=sys.stderr)
            else:
                self.error = (
                    f"cannot lock the append ({e}).\n"
                    f"  Unlocked parallel appends compute the same seq and break the chain "
                    f"(measured: 12 in parallel, all seq=1).\n"
                    f"  It can be lifted with ORG_LEDGER_ALLOW_UNLOCKED=1 only where serial "
                    f"execution can be guaranteed — **and that guarantee is not something the "
                    f"tool can confirm.**")
        return self

    def __exit__(self, *exc):
        try:
            if self.locked:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            if self.fh:
                self.fh.close()
        except Exception:
            pass
        return False


def _fsync_dir(path):
    """fsync the directory. Without it, the durability of a rename is not guaranteed.

    **Do not stay silent about a failure.** Some filesystems cannot do it, so this does not stop
    the append itself — but it must not leave unsaid that the ledger's durability is best-effort.
    Otherwise a state where a power cut can lose the HEAD rename gets read as "persisted".
    """
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except Exception as e:
        print(f"ledger: note — could not fsync the directory ({e}). On this filesystem the "
              f"durability of the HEAD rename is best-effort (the log itself is fsynced, and HEAD "
              f"can be rebuilt from the log).", file=sys.stderr)
        return False


def _head_from_log(root):
    """**Rebuild** HEAD from the log. HEAD is a cache, not the authority.

    **Rebuild only when the whole log is sound.** Never auto-repair a corruption partway through
    (a torn line, a seq gap, a hash mismatch) — placing a consistent HEAD on top of a broken record
    makes the breakage impossible to see. Corruption is reported fail-closed.

    Returns: (head, error). If there is an error, do not append.
    """
    log, _ = _paths(root)
    if not os.path.isfile(log):
        return {"seq": 0, "hash": "GENESIS"}, None
    prev, expect, last = "GENESIS", 1, None
    with open(log, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            if not line.endswith("\n"):
                return None, (f"line {lineno} of the log does not end in a newline (a torn "
                              f"line — the trace of a write that died partway). **This is not "
                              f"auto-repaired.** Inspect the contents and deal with it.")
            try:
                ev = json.loads(line)
            except Exception as e:
                return None, f"line {lineno} of the log is not readable as JSON: {e}"
            if ev.get("seq") != expect:
                return None, (f"seq gap / out of order: expected {expect} at line {lineno}, "
                              f"got {ev.get('seq')}.")
            if ev.get("prev_hash") != prev:
                return None, f"prev_hash mismatch (seq={ev.get('seq')}) — the chain has been cut."
            if _hash(prev, ev) != ev.get("hash"):
                return None, f"hash mismatch (seq={ev.get('seq')}) — evidence of rewriting."
            prev, last, expect = ev["hash"], ev, expect + 1
    if last is None:
        return {"seq": 0, "hash": "GENESIS"}, None
    return {"seq": last["seq"], "hash": last["hash"]}, None


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



def require_writer_path(op):
    """In an org where `ORG_WRITER_SOCKET` is set, **refuse any write that does not go through
    writerd**.

    All stage A (process_mediated) can enforce is that there is exactly ONE path.
    **This is not an OS boundary** — a caller with the same UID can stop the daemon and can unset
    this environment variable. That is why `workload_isolation` is `process_mediated` and not
    `separate_uid`.

    Only once a separate UID and a root-owned parent directory for the socket are both in place
    does unsetting the variable stop working — writing to the ledger file then fails on OS
    permissions. That is the point at which it becomes a boundary.

    Returns: None to continue. A string giving the reason for refusal.
    """
    if _inside_writer():
        return None                     # writerd itself is the caller
    sock = os.environ.get("ORG_WRITER_SOCKET")
    if not sock:
        return None                     # an org that does not use writerd (unchanged behaviour)
    return (f"this org permits writes only through writerd"
            f"（ORG_WRITER_SOCKET={sock}）。\n"
            f"  Do not run `{op}` directly; send it to writerd:\n"
            f"    python3 tools/writer_client.py {op} -- <arguments…>\n"
            f"  **The point is to have exactly one path to the ledger.** With several paths, "
            f"\"the records a check relies on are writable only by the side doing the checking\" "
            f"cannot be enforced.\n"
            f"  Note: this is not an OS boundary (the same UID can stop the daemon). "
            f"workload_isolation is process_mediated.")




def _org_and_ledger_id(root):
    """(org_id, ledger_id). **Taken from the write destination** — a value in the payload is
    something the caller can write.

    org_id    … the org's identifier (`.orgforge/ORG_ID` if present, otherwise a hash of the org root)
    ledger_id … the ledger's identifier (`<root>/LEDGER_ID` if present, otherwise a hash of the root)

    In an org with neither, return None and skip the matching check for that item — so as not to
    stop existing orgs. **A newly created org does write them** (`org-init` places them).
    """
    def _read_or_hash(path, fallback):
        if path and os.path.isfile(path):
            try:
                v = open(path, encoding="utf-8").read().strip()
                if v:
                    return v
            except OSError:
                pass
        return hashlib.sha256(os.path.abspath(fallback).encode()).hexdigest()[:16] \
            if fallback else None

    led_id = _read_or_hash(os.path.join(root, "LEDGER_ID") if root else None, root)
    org_root = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from discover import org_root as _orgroot
        org_root = _orgroot()
    except Exception:
        pass
    org_id = _read_or_hash(
        os.path.join(org_root, ".orgforge", "ORG_ID") if org_root else None, org_root)
    return org_id, led_id


def _verify_receipt_for(a, payload, cls, receipt_expect=None):
    """Verify `--receipt` and derive the identity fields. (fields, error).

    **Never use an environment variable as a "verified" marker.** Anything the caller can set is
    not evidence — measured (audit): merely adding `ORG_IDENTITY_VERIFIED=1` let a forged identity
    through.

    What verifies here is this tool itself; the caller can only **hand over** a receipt.
    If the signature does not check out, nothing is derived.
    """
    rc_arg = getattr(a, "receipt", None)
    if not rc_arg:
        return {}, None
    try:
        rc = json.loads(open(rc_arg, encoding="utf-8").read()) \
            if os.path.isfile(rc_arg) else json.loads(rc_arg)
    except Exception as e:
        return None, f"cannot read --receipt: {e}"
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from identity import verify_receipt, observed_recorder
    except Exception as e:
        return None, f"cannot load the identity module: {e}"
    # **Check that the receipt matches the contents of the judgment.** Without that check, one
    # could bring the receipt of a DIFFERENT judgment and borrow only its identity.
    # **Bind the receipt completely to this judgment.** Check only part of it and a receipt that
    # differs in the unchecked items can be reused (across orgs, issues, or classes).
    expect = {"event_class": cls}
    for k, pk in (("verdict", "verdict"), ("role", "role"), ("lineage", "lineage"),
                  ("review_subject_id", "review_subject_id"),
                  ("reasoning_sha256", "reasoning_sha256"),
                  ("issue", "issue"), ("phase", "phase"),
                  ("envelope_id", "envelope_id"),
                  ("human_decision_ref", "human_decision_ref"),
                  ("microexperiment_ref", "microexperiment_ref"),
                  ("practice_change_ref", "practice_change_ref")):
        if payload.get(pk) is not None:
            expect[k] = payload[pk]
    if receipt_expect:
        expect.update(receipt_expect)
    # org / ledger belong to the ledger itself. **Take them from the write destination, not from
    # the payload** — a payload value is something the caller can write, so checking it against
    # itself proves nothing.
    _org_id, _led_id = _org_and_ledger_id(a.root)
    if _org_id:
        expect["org_id"] = _org_id
    if _led_id:
        expect["ledger_id"] = _led_id
    who, assurance, err = verify_receipt(rc, expect)
    if err:
        return None, err
    recorded_by, rec_assurance = observed_recorder()
    return {"decision_by": who, "recorded_by": recorded_by,
            "identity_assurance": assurance.get("identity_assurance"),
            "recorder_assurance": rec_assurance,
            "workload_isolation": assurance.get("workload_isolation"),
            "writer_isolation": assurance.get("writer_isolation") or "none",
            **({"signer_id": assurance["signer_id"], "key_id": assurance["key_id"]}
               if assurance.get("signer_id") else {})}, None


def cmd_append(a):
    """Append one event under the hash chain. actor is from --actor (runtime identity),
    never the payload. seq is gapless. requires_prior is enforced against real history."""
    _wp = require_writer_path(getattr(a, "writer_op", None) or "append")
    if _wp:
        print(json.dumps({"ok": False, "reason": "direct_write_refused", "detail": _wp},
                         ensure_ascii=False) if "append" != "append" else f"append: {_wp}",
              file=sys.stderr if "append" == "append" else sys.stdout)
        return 4

    try:
        payload = json.loads(a.payload)
    except json.JSONDecodeError as e:
        print(f"append: --payload is not valid JSON: {e}", file=sys.stderr)
        return 2
    if isinstance(payload, dict) and "actor" in payload:
        print("append: payload must not carry its own 'actor' — actor comes from --actor "
              "(runtime identity), never the event body (ledger-schema §envelope)", file=sys.stderr)
        return 2
    # **The writer stamps schema_version.** If a client could name it, it could specify a laxer
    # version and slip past validation (a downgrade). It is accepted neither via the payload nor
    # via the envelope.
    # What is forbidden is only **a value that names a version**. `schema_id` is a value an event
    # that records the schema boundary itself — such as `schema_enforcement_started` — naturally
    # carries in its payload, and it is not a downgrade target (it is not a version).
    # Draw the prohibition too widely and facts you want to record become unwritable (our own
    # epoch record was rejected that way).
    # **`_nk` must not be written into the payload.** The idempotency key is a mark the tool
    # applies, not something the caller names. If it could be named, one could claim the same key
    # as an existing record and manufacture a no-op (i.e. believe you wrote something when nothing
    # was written, or make someone else's record read as your own).
    # **The caller cannot write the identity fields.** The writer — the path that verified a
    # receipt — derives them.
    # **Never trust a marker the caller can set.** Measured (audit): merely adding
    # `ORG_IDENTITY_VERIFIED=1` to the environment let a forged identity through. An environment
    # variable is under the caller's control, so it is no evidence of verification.
    #
    # Instead, **make them hand over the receipt itself and verify it here.** Identity is derived
    # only when that verification succeeds (identity fields written by the caller are always
    # refused).
    _IDENT = ("identity_assurance", "decision_by", "recorder_assurance", "signer_id", "key_id",
              "workload_isolation", "writer_isolation", "authority_principal",
              "authority_role", "authority_assurance", "authority_receipt_subject")
    if isinstance(payload, dict):
        forged = [k for k in _IDENT if k in payload]
        if forged:
            print(f"append: the payload must not contain {', '.join(forged)} — "
                  f"**this tool derives identity by verifying a receipt**.\n"
                  f"  **Never use something writable as the thing you check.** Measured: writing "
                  f"these alone evaded separation of duties, and so did merely adding an "
                  f"environment variable.\n"
                  f"  To record a judgment, pass --receipt.", file=sys.stderr)
            return 2
    if isinstance(payload, dict) and "_nk" in payload:
        print("append: the payload must not contain '_nk' — the tool applies the idempotency "
              "key. If the caller could name it, they could claim the same key as an existing "
              "record and manufacture a no-op.",
              file=sys.stderr)
        return 2
    for k in ("schema_version", "schema_sha256"):
        if isinstance(payload, dict) and k in payload:
            print(f"append: the payload must not contain {k!r} — the writer decides the schema "
                  f"version. If a client could name it, it could specify a laxer version and "
                  f"bypass validation.",
                  file=sys.stderr)
            return 2
        if getattr(a, k, None):
            print(f"append: --{k.replace('_', '-')} is not accepted — the writer decides the "
                  f"schema version (to prevent a downgrade).", file=sys.stderr)
            return 2

    # ── idempotency (docs/11 §0 reproducibility): if a natural key is given, this event is a
    # RETRY of a logical event that must be counted once. A replayed/re-fired cycle (a hook that
    # re-fires PreToolUse, a resumed session, a crash-retry) must NOT double-append — else the
    # aggregate caps (exposure, cycles, WIP) drift with how many times the tool ran, not with the
    # spec+action. We no-op (exit 0) when (class, natural_key) already exists in history. The seq
    # counter is monotonic, so without this an identical logical event would land twice under two
    # ids — the non-idempotency the "idempotent under replay" note wrongly claimed we already had.
    #
    # **An idempotent no-op is limited to "the same logical event BY THE SAME ACTOR".** This used
    # to look only at (class, natural_key), so a matching key made it **a no-op even for a
    # different actor**, and the controls (DISTINCT_ACTOR / REQUIRES_PRIOR) were never even
    # evaluated. In practice, a maker using the same key as the gate's decision —
    # `admission_decided-11` — got its self-approval through as "already recorded", exit 0.
    # Idempotency exists to make a re-run safe; it is not a back door around control.
    # **ここから書き込みまでを1つの critical section にする。** log を読む → seq を決める →
    # 書く → HEAD を更新する、が分かれていると並列 append が同じ seq を計算する
    # （実測: 12並列で12件すべて seq=1）。
    os.makedirs(a.root, exist_ok=True)
    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(f"append: {lk.error}", file=sys.stderr)
            return 4
        # **schema は lock 内で1回だけ読む。** 検証と digest 取得が別々に読むと、その間に
        # 差し替えられる（TOCTOU）。解析結果と digest を1つの snapshot にして両方に使う。
        snap, serr = load_schema_snapshot()
        if serr:
            print(f"append: {serr}\n"
                  f"  schema の場所と PyYAML を確認すること。", file=sys.stderr)
            return 2
        # **receipt を検証して identity を生成する。** caller は receipt を渡せるだけで、
        # identity fields を書くことはできない（上で拒否済み）。
        _ident = {}
        if a.cls != "correction":
            _ident, _ierr = _verify_receipt_for(a, payload, a.cls)
            if _ierr:
                print(f"append: receipt を検証できない — {_ierr}\n"
                      f"  **検証できない receipt では identity を生成しない。**",
                      file=sys.stderr)
                return 4
        if _ident:
            payload.update(_ident)
        elif a.cls in ("verdict_provisional", "admission_decided", "refutation_attempted",
                       "judges_disagreed", "adaptive_envelope_adopted"):
            # **receipt が無いときも identity を記録する — ただし `claimed` として。**
            # 欄が無いと「確かめた結果 claimed だった」のか「そもそも見ていない」のかを
            # 区別できない。書き手が生成するので、caller は値を選べない。
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from identity import observed_recorder
            _rb, _ra = observed_recorder()
            payload.update({"decision_by": a.actor, "recorded_by": _rb,
                            "identity_assurance": "claimed", "recorder_assurance": _ra,
                            "workload_isolation": "none"})

        # 新規 append だけを検証する。既存イベントに遡って適用すると移行できない。
        bad, warns = validate_event(a.cls, payload, snap,
                                    writer_op=getattr(a, "writer_op", None))
        if bad:
            print(f"append: {bad}", file=sys.stderr)
            return 2
        # **健全性の検査を先に置く。** `_read_events` は破損で例外を投げるので、そこに入る前に
        # log を検査して、拒否理由を人が読める形で出す。トレースバックは「壊れている」ことを
        # 伝える手段としては弱く、呼び出し側（hook / organ）も扱えない。
        head, err = _head_from_log(a.root)
        if err:
            print(f"append: log が健全でないので追記しない — {err}\n"
                  f"  **壊れた記録の上に整合した HEAD を載せない。** 壊れていることが"
                  f"分からなくなる。", file=sys.stderr)
            return 4
        hist = _read_events(a.root)
        cached = _read_head(a.root)
        if cached != head and cached != {"seq": 0, "hash": "GENESIS"}:
            print(f"append: HEAD が log と食い違っていたので log から再構築した"
                  f"（HEAD={cached.get('seq')} / log={head['seq']}）— "
                  f"HEAD は cache なので log を正とする。", file=sys.stderr)

        if a.cls == "correction":
            judgments, correction_error = _annotate_correction(payload, hist)
            if correction_error:
                print(f"append: correction rejected — {correction_error}", file=sys.stderr)
                return 3
            voids_judgment = bool(judgments and payload.get("kind") in
                                  VOIDING_CORRECTION_KINDS)
            if voids_judgment and not str(payload.get("reason") or "").strip():
                print("append: correction rejected — judgmentを無効化するcorrectionには "
                      "reason が必要", file=sys.stderr)
                return 3
            if voids_judgment or getattr(a, "receipt", None):
                reason_digest = hashlib.sha256(
                    str(payload.get("reason") or "").encode("utf-8")).hexdigest()
                receipt_expect = {
                    "review_subject_id": (payload.get("authority_receipt_subject") or
                                          _correction_subject(payload)),
                    "issue": (payload.get("issue") or
                              ",".join(payload.get("target_issues") or []) or "ledger"),
                    "role": a.actor,
                    "phase": "govern",
                    "lineage": "authority",
                    "verdict": payload.get("kind"),
                    "reasoning_sha256": reason_digest,
                }
                _ident, _ierr = _verify_receipt_for(
                    a, payload, a.cls, receipt_expect=receipt_expect)
                if _ierr:
                    print(f"append: receipt を検証できない — {_ierr}\n"
                          "  **別の対象・kind・理由へreceiptを再利用しない。**",
                          file=sys.stderr)
                    return 4
                if _ident:
                    payload.update(_ident)
            correction_error = _judgment_correction_violation(
                {"actor": a.actor, "class": a.cls, "payload": payload}, judgments)
            if correction_error:
                print(f"append: correction rejected — {correction_error}", file=sys.stderr)
                return 3

            # Target/effect/authority fields are writer-derived after history resolution. Validate
            # the final payload too; otherwise generated audit fields could silently drift from the
            # schema even though the caller-provided prefix passed validation.
            bad, final_warns = validate_event(a.cls, payload, snap)
            if bad:
                print(f"append: {bad}", file=sys.stderr)
                return 2
            warns.extend(w for w in final_warns if w not in warns)
        for w in warns:
            print(f"append: 注意 — {w}", file=sys.stderr)

        nk = getattr(a, "natural_key", None)
        if nk:
            for e in hist:
                if e["class"] != a.cls or e.get("payload", {}).get("_nk") != nk:
                    continue
                if e.get("actor") != a.actor:
                    print(f"append: {a.cls} rejected — natural key {nk!r} は既に "
                          f"actor {e.get('actor')!r} が seq={e['seq']} で使っている。\n"
                          f"  別の actor が同じキーで書くのは再実行ではない。冪等 no-op で通すと、"
                          f"自己承認や順序違反が『既に記録済み』として統制を素通りする"
                          f"（実地で確認）。判定ごとに一意なキーを使うこと。", file=sys.stderr)
                    return 3
                # **同じキー・同じ actor でも payload が違えば再実行ではない。**
                prior_pl = {k: v for k, v in (e.get("payload") or {}).items() if k != "_nk"}
                now_pl = {k: v for k, v in payload.items() if k != "_nk"}
                if prior_pl != now_pl:
                    print(f"append: {a.cls} rejected — natural key {nk!r} は seq={e['seq']} に"
                          f"あるが、payload が違う。\n"
                          f"  同じキーで中身の違うものを書くのは再実行ではない。"
                          f"no-op で通すと、後から書いた内容が黙って捨てられる。\n"
                          f"  差し替えるなら correction を追記してからにすること。",
                          file=sys.stderr)
                    return 3
                print(f"append: idempotent no-op — {a.cls} with natural key {nk!r} "
                      f"already recorded at seq={e['seq']} id={e['id']} (docs/11 §0). "
                      f"Not re-appended.")
                return 0
            payload["_nk"] = nk
        seq = head["seq"] + 1
        eid = "e" + hashlib.sha256(
            f"{seq}:{a.cls}:{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
        ).hexdigest()[:12]
        # **ts は writer が付ける。** クライアントが決められるなら順序を偽れるので、cap の
        # 時間窓を迂回できる。`--ts` は過去の記録を補う backfill のためだけに残し、
        # **"UNSET" と不正な形は受け取らない** — 窓で絞る view や sensor が黙って落とす。
        # `--ts` は 0.33.2 で `--backfill-ts` に分離した。旧名は受け取るが、**意図を確かめる** —
        # 通常経路で時刻を指定できると、順序を偽って cap の時間窓を迂回できる。
        given = a.ts or getattr(a, "ts_legacy", None)
        ts = given or _now_iso()
        if given:
            err = _check_backfill_ts(given)
            if err:
                print(f"append: {err}", file=sys.stderr)
                return 2
        ev = {"id": eid, "seq": seq, "ts": ts, "actor": a.actor,
              "class": a.cls, "payload": payload,
              # 検証結果を統制の判定に渡す。**台帳には書かない**（hash の直前で外す）。
              "_verified_identity": _ident,
              "schema_id": "orgforge-ledger",
              "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"],
              "prev_hash": head["hash"]}
        goal_error = _goal_lifecycle_violation(ev, hist, a.root)
        if goal_error:
            print(f"append: {goal_error}", file=sys.stderr)
            return 3
        try:
            from adaptation import ledger_event_violation
            adaptation_error = ledger_event_violation(ev, hist, a.root)
        except Exception as exc:
            adaptation_error = (f"adaptive contract could not be evaluated: {exc}"
                                if a.cls.startswith("adaptive_") or
                                a.cls in {"acceptable_outcome_recorded", "microexperiment_concluded"}
                                else None)
        if adaptation_error:
            print(f"append: {a.cls} rejected — {adaptation_error}", file=sys.stderr)
            return 3
        try:
            from operational_state import ledger_event_violation as operational_violation
            operational_error = operational_violation(ev, hist, a.root)
        except Exception as exc:
            operational_error = (f"operational state contract could not be evaluated: {exc}"
                                 if a.cls in {"circuit_state_changed",
                                              "operational_state_transitioned",
                                              "operational_escalated", "artifact_tainted",
                                              "recovery_probe_recorded", "artifact_revalidated"}
                                 else None)
        if operational_error:
            print(f"append: {a.cls} rejected — {operational_error}", file=sys.stderr)
            return 3
        if a.cls in REQUIRES_PRIOR and not REQUIRES_PRIOR[a.cls](ev, hist):
            why = REQUIRES_PRIOR_WHY.get(a.cls, "a required prior event does not exist")
            print(f"append: {a.cls} rejected — requires a prior event that does not exist: {why} "
                  f"(ledger-schema §event_classes {a.cls}.requires_prior)", file=sys.stderr)
            return 3
        dl = _dual_lineage_violation(ev)
        if dl:
            print(f"append: {dl}", file=sys.stderr)
            return 3
        att = _attestation_violation(ev)
        if att:
            print(f"append: {att}", file=sys.stderr)
            return 3
        sod = _distinct_actor_violation(ev, hist)
        if sod:
            print(f"append: {sod}", file=sys.stderr)
            return 3
        ev.pop("_verified_identity", None)   # 内部の受け渡し用。記録には残さない
        ev["hash"] = _hash(head["hash"], ev)
        log, headp = _paths(a.root)
        # append → fsync(log) → HEAD を一時ファイルへ → atomic rename → fsync(dir)
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        tmp = headp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"seq": seq, "hash": ev["hash"]}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, headp)
        _fsync_dir(a.root)
    print(f"appended seq={seq} {a.cls} id={eid} hash={ev['hash'][:12]}…")
    if a.cls == "correction":
        print("correction-effect: "
              f"kind={payload.get('kind')} effect={payload.get('effect')} "
              f"targets={payload.get('corrects')} classes={payload.get('target_classes')} "
              f"authority={payload.get('authority_role') or a.actor} "
              f"assurance={payload.get('authority_assurance') or 'not-required'}")
    return 0


def cmd_record_scheduled_check(a):
    """Persist scheduler proof through a dedicated writer operation.

    A generic caller must not be able to forge the receipt that satisfies missed-tick accounting.
    This is still only the configured writer boundary (and therefore not stronger than its UID),
    but it prevents ordinary append from manufacturing a healthy unattended run.
    """
    payload = {
        "check_id": a.check_id,
        "scheduled_for_min": a.scheduled_for_min,
        "execution_id": a.execution_id,
        "result": a.result,
        "exit_code": a.exit_code,
        "command_sha256": a.command_sha256,
        "plugin_version": a.plugin_version,
    }
    forwarded = argparse.Namespace(
        root=a.root,
        actor="system:scheduler_tick",
        cls="scheduled_check_completed",
        payload=json.dumps(payload, ensure_ascii=False),
        natural_key=f"scheduler-check-{a.check_id}-{a.scheduled_for_min}",
        ts=None,
        ts_legacy=None,
        receipt=None,
        schema_version=None,
        schema_sha256=None,
        writer_op="scheduled_check_completed",
    )
    return cmd_append(forwarded)





def _class_field_span(text, cls):
    """`  <cls>: { ... }` の中身の span を返す。**波括弧の深さを数える** —
    非貪欲な正規表現だと、値の中の `{...}` の最初の `}` を終端と誤認し、
    修復が別の場所に入って **直ったように見えて直っていない**（Codex の指摘、実測で再現）。
    見つからなければ None。"""
    # field alignment uses a variable number of spaces before ``{``.  Requiring exactly one
    # meant repair worked for e.g. ``integration_admitted: {`` but silently skipped aligned
    # names such as ``verdict_provisional:  {`` and ``halt_tripped:         {``.
    m = re.search(rf"\n  {re.escape(cls)}:[ \t]*\{{", text)
    if not m:
        return None
    i = m.end() - 1                     # 開き `{` の位置
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (i + 1, j)       # 中身だけの span
    return None


def _yaml_block_span(text, key):
    """トップレベルの `key:` ブロックの (start, end) を行境界で返す。無ければ None。

    正規表現で `\nkey:\n(?:(?:  |\n).*\n)*` と書くと、**次のトップレベルキーの前にある
    コメント行や、そのブロックの子行まで飲み込む**。実際に validation の置換が
    `event_classes:` を丸ごと消した（YAML が読めるので気づきにくい）。

    ブロックの終わりは「インデントの無い次の行」で決める — それが YAML の構造である。
    """
    lines = text.split("\n")
    start = None
    for i, l in enumerate(lines):
        if l == f"{key}:" or l.startswith(f"{key}:"):
            if not l[0].isspace():
                start = i
                break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        l = lines[j]
        if l and not l[0].isspace():          # 次のトップレベル（コメントも含む）
            end = j
            break
    off = lambda n: sum(len(x) + 1 for x in lines[:n])
    return off(start), off(end)


def _deep_add(dst, src, path=""):
    """`src` にあって `dst` に無いものだけを足す。**dst 独自のものは必ず残す。**

    設定の修復は「追加」でなければならない。ブロックごと置き換えると、org が自分で足した
    厳格規則が消える — それは修復ではなく退行である（実測: org の
    `required.progress_recorded: [milestone]` が置換で失われた）。

    同じ path に違う **スカラー値** があるときは、自動で上書きしない。org が意図して変えたのか、
    テンプレートが変わったのかは道具では判別できないので、conflict として報告して人に決めさせる。

    返り値: (merged, conflicts)
    """
    conflicts = []
    if isinstance(dst, dict) and isinstance(src, dict):
        out = dict(dst)
        for k, sv in src.items():
            here = f"{path}.{k}" if path else str(k)
            if k not in out:
                out[k] = sv
                continue
            dv = out[k]
            if isinstance(dv, dict) and isinstance(sv, dict):
                out[k], c = _deep_add(dv, sv, here)
                conflicts += c
            elif isinstance(dv, list) and isinstance(sv, list):
                # list は集合として足す（org が足した要素を落とさない）。順序はテンプレート優先。
                out[k] = sv + [x for x in dv if x not in sv]
            elif dv != sv:
                conflicts.append(f"{here}: org={dv!r} / テンプレート={sv!r}")
        return out, conflicts
    if isinstance(dst, list) and isinstance(src, list):
        return src + [x for x in dst if x not in src], conflicts
    if dst != src:
        conflicts.append(f"{path}: org={dst!r} / テンプレート={src!r}")
    return dst, conflicts


def cmd_schema(a):
    """org の ledger-schema.yaml とプラグインのテンプレートの差分を診断し、必要なら埋める。

    ## なぜこれが要るか（H8: schema rollout skew）

    org は自分の `ledger-schema.yaml` を持つ（org が自分の形式を所有するため）。プラグインが
    新しいイベントクラスを増やしても、**org のコピーは古いまま**になる。そこに「宣言の無い
    クラスは書けない」検査を入れると、**更新直後に org の記録が止まる**。

    実測: ある org の schema はプラグインより4クラス古く、うち2つ（`correction` 12件、
    `asset_touched` 3件）は実データで使われていた。schema を配らずに検査を入れれば、
    その org は訂正を書けなくなる。

    **これは fail-closed ではなく、既知の移行不備による可用性事故である。** だから
    「検査を入れる前に診断できること」「明示的に移行できること」を道具として持つ。
    """
    here = os.path.dirname(os.path.abspath(__file__))    # ledger.py はローカルに here を作る流儀
    plug_p = os.path.join(here, "..", "template", "ledger-schema.yaml")
    if not os.path.isfile(plug_p):
        plug_p = os.path.join(here, "template", "ledger-schema.yaml")
    org_p = _schema_path()
    if not org_p or not os.path.isfile(org_p):
        print("org の ledger-schema.yaml が見つからない。", file=sys.stderr)
        return 2
    if os.path.abspath(org_p) == os.path.abspath(plug_p):
        print("この org はプラグインのテンプレートを直接使っている — skew は起こらない。")
        return 0
    try:
        import yaml
        plug = yaml.safe_load(open(plug_p, encoding="utf-8")) or {}
        org = yaml.safe_load(open(org_p, encoding="utf-8")) or {}
    except Exception as e:
        print(f"schema を解析できない: {e}", file=sys.stderr)
        return 2

    pc = set((plug.get("event_classes") or {}).keys())
    oc = set((org.get("event_classes") or {}).keys())
    missing = sorted(pc - oc)
    # **validation の中身も比べる。** 「ブロックの有無」だけを見ていたので、org 側で
    # `verdict_provisional` の required を削っても「差分なし」と判定した（監査が実証）。
    # 検証規則が欠けていることは、クラスが欠けていることと同じくらい静かに効く。
    pv, ov = plug.get("validation") or {}, org.get("validation") or {}
    # **欠落と衝突を1つの計算から出す。** 別々に判定すると、片方だけ検出して片方を見落とす
    # （実測: 欠落だけを見ていたので、org が型名を変えていた衝突が --fix に入らず報告もされなかった）。
    _merged, vconf = _deep_add(ov, pv, path="validation")
    vgaps = []
    for sect in ("required", "require_any", "enums", "types"):
        pd, od = pv.get(sect) or {}, ov.get(sect) or {}
        for cls_, spec in pd.items():
            if cls_ not in od:
                vgaps.append(f"validation.{sect}.{cls_} が無い")
            elif isinstance(spec, (list, dict)) and isinstance(od.get(cls_), (list, dict)):
                lost = sorted(set(spec) - set(od[cls_]))
                if lost:
                    vgaps.append(f"validation.{sect}.{cls_} に {', '.join(map(str, lost))} が無い")
    for cls_ in (pv.get("additional_properties_false") or []):
        if cls_ not in (ov.get("additional_properties_false") or []):
            vgaps.append(f"validation.additional_properties_false に {cls_} が無い")

    # **実データで使われているかを言う。** 使われているクラスが欠けているなら、検査を入れた
    # 瞬間にその記録が止まる — 緊急度が違う。
    used = set()
    try:
        for e in read_events(a.root):
            used.add(e.get("class"))
    except Exception:
        pass

    # **クラス数が同じでも、field が欠けていれば最新ではない。**
    # snapshot が読むのは `event_classes` の `fields:` 行なので、ここが古いと
    # validation を直しても snapshot は古い形で固定され、正規経路が拒否される
    # （実測: 実 org tatekae が「差分なし」と表示されたまま全 metered 操作がデッドロックしていた）。
    _src_txt = open(plug_p, encoding="utf-8").read()
    _dst_txt = open(org_p, encoding="utf-8").read()
    # **field は YAML の構造から読む。** inline-map の途中にコメントがあると、文字列を
    # comma split する実装では `# ...\n phase, decision_by, ...` が1 chunkになり、コメント
    # 以降の正当な field までまとめて捨てていた。その結果 ``schema --fix`` が「最新」と
    # 誤報したまま、writer が生成する identity field を closed-world schema が拒否した
    # （OBS-008）。safe_load 済みの map が、ここで比較すべき規範的な構造である。
    def _fields_from_doc(doc):
        return {name: list(spec.keys()) for name, spec in
                ((doc.get("event_classes") or {}).items()) if isinstance(spec, dict)}
    _sf, _df = _fields_from_doc(plug), _fields_from_doc(org)
    fgaps = []
    for _c, _want in _sf.items():
        _have = _df.get(_c)
        if _have is None:
            continue
        _miss = [f for f in _want if f and f not in _have]
        if _miss:
            fgaps.append(f"{_c}: {', '.join(_miss)}")

    print(f"org schema : {org_p}")
    print(f"テンプレート: {plug_p}")
    print(f"  org {len(oc)} クラス / テンプレート {len(pc)} クラス")
    if fgaps:
        print(f"\n**既存クラスに足りない field: {len(fgaps)}**"
              " — snapshot はここを読む。欠けていると正規経路が拒否される。")
        for _g in fgaps:
            print(f"    {_g}")
    if not missing and not vgaps and not vconf and not fgaps:
        print("  差分なし — この org の schema は最新である"
              "（クラス宣言と validation 規則の両方）。")
        return 0

    if missing:
        print(f"\n**org に無いクラス: {len(missing)}**")
        for c in missing:
            mark = "  ← 実データで使用中。**このクラスの記録が止まる**" if c in used else ""
            print(f"    {c}{mark}")
    if vconf:
        print(f"\n**validation 規則の衝突: {len(vconf)}** — 自動では直さない。")
        for c in vconf:
            print(f"    {c}")
        print("  同じ path に違う値がある。org が意図して変えたのか、テンプレートが変わったのかは"
              "道具では判別できない。**手で決めること。**")
    if vgaps:
        print(f"\n**validation 規則の欠落: {len(vgaps)}**")
        for g in vgaps[:20]:
            print(f"    {g}")
        if len(vgaps) > 20:
            print(f"    …他 {len(vgaps) - 20} 件")
        print("  検証規則が欠けていることは、クラスが欠けていることと同じくらい静かに効く — "
              "拒否されるべき記録が通る。")

    if not a.fix:
        print(f"\n埋めるには --fix を付けて実行すること:\n"
              f'    python3 "{os.path.join(here, "ledger.py")}" schema --fix\n'
              f"  **既存の宣言は書き換えない。** 足りないものを足すだけである — org が自分で"
              f"変えた宣言（実態に合わせた形）を上書きしてはいけない。")
        return 1

    # ── --fix: 足りないクラスと validation を **追加するだけ** ──────────────
    src = open(plug_p, encoding="utf-8").read()
    dst = open(org_p, encoding="utf-8").read()
    added = []
    for c in missing:
        m = re.search(rf"\n((?:  #[^\n]*\n)*  {re.escape(c)}:.*?)(?=\n  [a-z_]+:|\n  # ──|\n[a-z_]+:)",
                      src, re.S)
        if not m:
            print(f"  警告: {c} の宣言をテンプレートから取り出せなかった（手で足すこと）",
                  file=sys.stderr)
            continue
        # event_classes の末尾に足す（既存の宣言には触らない）
        anchor = "\ntriggers:"
        if anchor not in dst:
            print("  警告: 挿入位置（triggers:）が見つからない", file=sys.stderr)
            break
        dst = dst.replace(anchor, "\n" + m.group(1).rstrip() + "\n" + anchor, 1)
        added.append(c)
    # ── **既存クラスの field 不足も直す。** ────────────────────────────────
    # snapshot が読むのは `event_classes` の `fields:` 行であって validation ではない。
    # ここが古いままだと、validation を直しても **snapshot は古い形で固定され続け**、
    # 正規の `reserve-exposure` が schema_rejected で拒否される = 全 metered 操作の
    # デッドロック（実測: 実 org tatekae がこの状態だった）。
    # `--fix` は「クラスを足すだけ」だったので、この経路を直せていなかった。
    field_added = []
    for cls in sorted(set(_sf) & set(_df)):
        ss = _class_field_span(src, cls)
        ds = _class_field_span(dst, cls)
        if not ss or not ds:
            continue
        want, have = _sf[cls], _df[cls]
        missing_f = [f for f in want if f and f not in have]
        if not missing_f:
            continue
        # 既存の並びは壊さず、閉じ括弧の直前に足すだけ
        body = dst[ds[0]:ds[1]].rstrip()
        if "\n" in body:
            # 手書きschemaの揃え方を保持する。固定幅だと意味は同じでも、修復のたびに
            # org-owned specへ不要なindent差分を作る。
            last_line = body.rsplit("\n", 1)[-1]
            indent = re.match(r"[ \t]*", last_line).group(0)
            sep = ",\n" + indent
        else:
            sep = ", "
        dst = dst[:ds[0]] + body + sep + ", ".join(missing_f) + " " + dst[ds[1]:]
        field_added.append(f"{cls}: +{', '.join(missing_f)}")
    if field_added:
        print("  既存クラスに field を足した（snapshot が読む箇所）:", file=sys.stderr)
        for f in field_added:
            print(f"    {f}", file=sys.stderr)

    conflicts = vconf
    if vgaps or vconf:
        # **deep-add でマージする。** ブロックごと差し替えると、org 独自の厳格規則が消える
        # （実測: org が足した `required.progress_recorded: [milestone]` が --fix で失われた）。
        # org 所有の安全規則を弱めるのは、修復ではなく退行である。
        #
        #   欠けている key / list 要素だけを足す
        #   org 側の追加規則は必ず残す
        #   同じ path で値が違うなら **自動で上書きせず conflict として報告する**
        merged = _merged
        if conflicts:
            print(f"\n**衝突: {len(conflicts)}** — 自動では直さない。", file=sys.stderr)
            for c in conflicts:
                print(f"    {c}", file=sys.stderr)
            print("  同じ path に違う値がある。org が意図して変えたのか、テンプレートが"
                  "変わったのかは道具では判別できない。**手で決めること。**", file=sys.stderr)
        if merged != ov:
            # YAML として書き直すのは validation ブロックだけに限る。event_classes は
            # コメントが規律の説明そのものなので、再 serialize で失いたくない。
            try:
                import yaml as _y
                block = _y.dump({"validation": merged}, sort_keys=False,
                                allow_unicode=True, default_flow_style=False, width=100)
            except Exception as e:
                print(f"validation を書き出せない: {e}", file=sys.stderr)
                return 3
            span = _yaml_block_span(dst, "validation")
            if span is None:
                dst = dst.replace("\nevent_classes:", "\n" + block + "\nevent_classes:", 1)
            else:
                dst = dst[:span[0]] + block + dst[span[1]:]
            added.append(f"validation 規則（{len(vgaps)} 件を deep-add。org 独自の規則は保存）")

    # **atomic write。** 直接上書きすると、修復途中で止まったときに schema を壊す — org の
    # 形式定義が壊れれば、その org は何も書けなくなる。temp → fsync → rename → fsync(dir)。
    tmp_p = org_p + ".tmp"
    with open(tmp_p, "w", encoding="utf-8") as f:
        f.write(dst)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_p, org_p)
    _fsync_dir(os.path.dirname(os.path.abspath(org_p)))
    print(f"\n足した: {', '.join(added)}\n"
          f"  **--fix の exit 0 を preflight 成功と読まないこと。** 修復したあとに"
          f"通常の診断（--fix なし）が exit 0 を返すことを確かめる:\n"
          f'    python3 "{os.path.join(here, "ledger.py")}" schema\n'
          f"  衝突が残っていれば --fix は 0 を返しても差分は残っている。\n"
          f"  **クラス宣言は足すだけ**で、既存のものは書き換えていない — org が実態に合わせて"
          f"変えた宣言はそのままである。\n"
          + ("  **validation 規則は deep-add した** — org が自分で足した厳格規則は残っている。"
             "同じ path で値が違うものは上書きせず、衝突として報告した。\n"
             if any("validation" in x for x in added) else ""))
    return 0



def cmd_reserve_exposure(a):
    """**書けた判断だけが allow になる。** cap の検査と予約を1つの writer 操作にする。

    ## なぜ二段構成では足りないか

    0.33.x までは organ が「集計して判断して LEDGER-EVENT を印字」し、hook が「その後で
    append（失敗は無視）」していた。そこには3つの穴がある:

      1. 集計と判断が lock の外なので、**並列の hook が同じ committed を読んで両方 allow**
         してから順に append できる。合計が cap を超える。
      2. append の失敗を無視するので、allow したのに曝露が記録されない。**次の呼び出しは
         committed=0 を見る**ので、cap は記憶を失った per-action 検査に退化する。
      3. hold は deny して終わるので、**止めたことが記録に残らない**。

    ここでは lock の中で
    schema snapshot → 履歴検証 → 冪等性照合 → 現在の曝露を算出 → allow/hold 判断 →
    予約 event の append + fsync
    を一操作として行い、**予約が永続化された後にだけ allow を返す**。

    ## caller から受け取らないもの

    - `committed_so_far` — writer が数える。caller が渡せるなら、少なく申告して cap を通れる。
    - 時刻 — writer が付ける。`--backfill-ts` も隠し `--ts` も **この操作には定義しない**。
      通常台帳の backfill 権限は identity の側（H1）に残すが、cap 予約に持ち込んではいけない。

    ## 冪等キー

    `(session_id, tool_use_id, rule, event_class)`。`tool_use_id` 単独では、別 session・別 rule の
    衝突を防げない。**欠落していれば metered action を deny する** — 同一性を確かめられないなら、
    hook の再実行を二重計上しないという保証が成り立たない。
    """
    _wp = require_writer_path("reserve-exposure")
    if _wp:
        print(json.dumps({"ok": False, "reason": "direct_write_refused", "detail": _wp},
                         ensure_ascii=False) if "reserve-exposure" != "append" else f"reserve-exposure: {_wp}",
              file=sys.stderr if "reserve-exposure" == "append" else sys.stdout)
        return 4

    for k in ("session_id", "tool_use_id", "rule"):
        if not (getattr(a, k, None) or "").strip():
            print(json.dumps({"decision": "deny", "reason": f"missing_{k}",
                              "detail": f"--{k.replace('_', '-')} が無い。冪等キーは "
                                        f"(session_id, tool_use_id, rule, event_class) で、"
                                        f"欠けていると hook の再実行を二重計上しない保証が"
                                        f"成り立たない。metered action は通さない。"},
                             ensure_ascii=False))
            return 3

    # **入力の検証を先に。** 負・NaN・inf の delta は上限の判定を壊す（負なら合計を減らせる）。
    for name, val, ok in (
            ("--delta", a.delta, lambda v: v == v and v > 0 and v != float("inf")),
            ("--cap", a.cap, lambda v: v == v and v >= 0 and v != float("inf"))):
        try:
            if not ok(float(val)):
                raise ValueError
        except (TypeError, ValueError):
            print(json.dumps({"decision": "deny", "reason": "invalid_request",
                              "detail": f"{name}={val!r} は使えない。delta は有限かつ正、"
                                        f"cap は有限かつ非負でなければならない — 負や NaN を"
                                        f"通すと合計を減らして上限を迂回できる。"},
                             ensure_ascii=False))
            return 3

    # 冪等キーは **canonical tuple の hash**。区切り文字で連結すると、値に区切り文字が
    # 入ったときに別のキーと衝突する（"a|b" + "c" と "a" + "b|c" が同じになる）。
    nk = "reserve:" + hashlib.sha256(json.dumps(
        ["exposure_budget_checked", a.session_id, a.tool_use_id, a.rule],
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]
    # 要求内容の digest。**同じキーで内容が違う要求は再実行ではない。**
    req_digest = hashlib.sha256(json.dumps(
        {"dimension": a.dimension, "delta": float(a.delta), "cap": float(a.cap),
         "window_since": a.window_since or "", "actor": a.actor},
        sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]
    os.makedirs(a.root, exist_ok=True)
    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(json.dumps({"decision": "deny", "reason": "lock_failed",
                              "detail": lk.error}, ensure_ascii=False))
            return 4

        snap, serr = load_schema_snapshot()
        if serr:
            print(json.dumps({"decision": "deny", "reason": "schema_unreadable",
                              "detail": serr}, ensure_ascii=False))
            return 4

        head, herr = _head_from_log(a.root)
        if herr:
            print(json.dumps({"decision": "deny", "reason": "ledger_unhealthy",
                              "detail": herr}, ensure_ascii=False))
            return 4

        try:
            hist = _read_events(a.root)
        except Exception as e:
            print(json.dumps({"decision": "deny", "reason": "ledger_unreadable",
                              "detail": str(e)}, ensure_ascii=False))
            return 4

        # 冪等性 — 同じ (session, tool_use, rule) の予約が既にあるなら、その判断を返す。
        # hook が再実行されても二重計上しない。
        for e in hist:
            if e.get("class") != "exposure_budget_checked":
                continue
            if (e.get("payload") or {}).get("_nk") != nk:
                continue
            prior = e["payload"]
            # **exact retry だけが再実行である。** 同じキーで内容が違う要求を通すと、
            # delta=1 の allow を根拠に delta=100 が通る（実測でそうなった）。
            if prior.get("request_digest") != req_digest:
                print(json.dumps(
                    {"decision": "deny", "reason": "idempotency_key_reused_with_different_request",
                     "detail": f"同じ冪等キー（session/tool_use/rule）が seq={e.get('seq')} で"
                               f"別の要求に使われている。dimension / delta / cap / window / actor の"
                               f"どれかが違う要求は再実行ではない。",
                     "prior": {"dimension": prior.get("dimension"),
                               "delta_requested": prior.get("delta_requested"),
                               "cap": prior.get("cap")},
                     "now": {"dimension": a.dimension, "delta": a.delta, "cap": a.cap}},
                    ensure_ascii=False))
                return 3
            print(json.dumps({"decision": prior.get("decision"), "reason": "idempotent_replay",
                              "seq": e.get("seq"), "committed_so_far": prior.get("committed_so_far"),
                              "delta_requested": prior.get("delta_requested"),
                              "cap": prior.get("cap")}, ensure_ascii=False))
            return 0 if prior.get("decision") == "allow" else 10

        # **writer が数える。** caller の申告は受け取らない。
        voided = set()
        try:
            voided = set(voided_seqs(hist))
        except Exception:
            pass
        committed = 0.0
        for e in hist:
            if e.get("class") != "exposure_budget_checked" or e.get("seq") in voided:
                continue
            p = e.get("payload") or {}
            if p.get("dimension") != a.dimension or p.get("decision") != "allow":
                continue
            if a.window_since and str(e.get("ts", "")) < a.window_since:
                continue
            try:
                dv = float(p.get("delta_requested"))
                # **負・NaN・inf の過去の曝露を数えない。** 数えると合計を減らせる／比較が壊れる。
                if not (dv == dv) or dv < 0 or dv in (float("inf"), float("-inf")):
                    raise ValueError(f"delta_requested={dv!r}")
                committed += dv
            except (TypeError, ValueError):
                # 壊れた曝露記録は 0 として数えず、**deny する** — 合計が実際より小さく見える。
                print(json.dumps({"decision": "deny", "reason": "malformed_prior_exposure",
                                  "detail": f"seq={e.get('seq')} の delta_requested が数値でない"
                                            f"（{p.get('delta_requested')!r}）。合計が実際より"
                                            f"小さく見えるので通さない。"}, ensure_ascii=False))
                return 4

        would_be = committed + a.delta
        decision = "allow" if would_be <= a.cap else "hold"
        payload = {"window_id": a.window_since or "all", "dimension": a.dimension,
                   "committed_so_far": committed, "delta_requested": a.delta, "cap": a.cap,
                   "actor_role": a.actor, "decision": decision,
                   "caused_by_event": a.caused_by,
                   "session_id": a.session_id, "tool_use_id": a.tool_use_id, "rule": a.rule,
                   "request_digest": req_digest, "_nk": nk}

        bad, warns = validate_event("exposure_budget_checked", payload, snap,
                                    writer_op="exposure_budget_checked")
        if bad:
            print(json.dumps({"decision": "deny", "reason": "schema_rejected",
                              "detail": bad}, ensure_ascii=False))
            return 4
        for w in warns:
            print(f"reserve-exposure: 注意 — {w}", file=sys.stderr)

        ev = {"id": "e" + hashlib.sha256(
                  f"{head['seq'] + 1}:exposure_budget_checked:"
                  f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
              ).hexdigest()[:12],
              "seq": head["seq"] + 1, "ts": _now_iso(), "actor": a.actor,
              "class": "exposure_budget_checked", "payload": payload,
              "schema_id": "orgforge-ledger", "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"], "prev_hash": head["hash"]}
        ev["hash"] = _hash(head["hash"], ev)

        log, headp = _paths(a.root)
        # 途中で失敗したら、書いた分を切り戻す位置。**deny したのに曝露が残る**と、次の予約が
        # それを数える（過大計上）。それは安全側だが正確ではなく、上限が実際より早く尽きる。
        prior_size = os.path.getsize(log) if os.path.exists(log) else 0
        try:
            # 故障注入。**書けなかったら allow にならない**ことを検査できなければ、
            # 「書けた判断だけが allow になる」とは言えない（fail-closed は故障注入で示す）。
            if os.environ.get("ORG_LEDGER_FORCE_APPEND_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_APPEND_FAIL=1（故障注入）")
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                if os.environ.get("ORG_LEDGER_FORCE_FSYNC_FAIL") == "1":
                    raise OSError("ORG_LEDGER_FORCE_FSYNC_FAIL=1（故障注入）")
                os.fsync(f.fileno())
            tmp = headp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": ev["seq"], "hash": ev["hash"]}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, headp)
            _fsync_dir(a.root)
        except Exception as e:
            # 書きかけを切り戻す。lock の中なので、他の書き手は割り込んでいない。
            try:
                if os.path.exists(log) and os.path.getsize(log) > prior_size:
                    with open(log, "r+b") as f:
                        f.truncate(prior_size)
                        f.flush()
                        os.fsync(f.fileno())
            except Exception as te:
                print(f"reserve-exposure: 書きかけを切り戻せなかった（{te}）。"
                      f"台帳に未確定の行が残っている可能性がある — `ledger verify` で確認すること。",
                      file=sys.stderr)
            # **書けなかったら allow を返さない。** hold の記録に失敗した場合も deny である
            # （記録できない hold を allow に読み替えるのが、いちばん危ない誤りである）。
            print(json.dumps({"decision": "deny", "reason": "reservation_not_persisted",
                              "detail": f"予約を永続化できなかった（{e}）。"
                                        f"**書けた判断だけが allow になる。**"},
                             ensure_ascii=False))
            return 4

    out = {"decision": decision, "reason": "reserved", "seq": ev["seq"],
           "committed_so_far": committed, "delta_requested": a.delta, "cap": a.cap,
           "would_be": would_be}
    print(json.dumps(out, ensure_ascii=False))
    if decision == "hold":
        print(f"HOLD: {a.dimension} committed {committed} + requested {a.delta} = {would_be} "
              f"> cap {a.cap}。**hold は記録済み（seq={ev['seq']}）** — 止めたことが残る。",
              file=sys.stderr)
        return 10
    return 0



HALT_LATCH = "HALT"          # <ledger-root>/HALT — 台帳が読めなくても止まる第二経路


def active_halt(root):
    """いま halt しているか。(halt_event | None, error | None) を返す。

    **2つの経路を見る。**

      1. 台帳の `halt_tripped`（正）— 対応する `halt_released` が無いものが active
      2. `<root>/HALT` ラッチ（保険）— 台帳が読めないときにも止まるため

    台帳を読めないときは **halt とみなす**（error を返す）。読めないことを「halt していない」と
    読むのは、いちばん危ない fail-open である — 止まっているかどうか分からないなら、止める。

    ラッチは台帳の代わりではない。手でラッチを消しても台帳の halt は残るので、hook は止め続ける。
    逆に台帳が読めなくてもラッチがあれば止まる。**どちらかが止めていれば止まる。**
    """
    latch = os.path.join(root, HALT_LATCH) if root else None
    latched = bool(latch and os.path.exists(latch))
    try:
        evs = read_events(root)
    except Exception as e:
        # 読めないなら止める。ラッチの有無に関わらず。
        return ({"reason": f"台帳を読めないので halt とみなす: {e}", "source": "unreadable"},
                str(e))
    released = set()
    for e in evs:
        if e.get("class") == "halt_released":
            s = (e.get("payload") or {}).get("releases_seq")
            if isinstance(s, int):
                released.add(s)
    for e in reversed(evs):
        if e.get("class") == "halt_tripped" and e.get("seq") not in released:
            return {**(e.get("payload") or {}), "seq": e.get("seq"),
                    "actor": e.get("actor"), "source": "ledger"}, None
    if latched:
        # 台帳に active な halt が無いのにラッチがある。**ラッチを信じて止める** —
        # halt を書けなかった（fail-open になりかけた）痕跡である可能性がある。
        return ({"reason": "HALT ラッチが存在するが、台帳に対応する halt_tripped が無い。"
                          "halt の記録に失敗した痕跡かもしれない。手で確かめること。",
                 "source": "latch_only"}, None)
    return None, None


def cmd_trip_halt(a):
    """halt を発動する。**記録できなければ、その呼び出し自体を deny する。**

    「記録できないなら宣言しない」は記録としては正しいが、**制御としては fail-open** になる —
    止めるべき状況で止まらない。だから:

      1. 先に `<root>/HALT` ラッチを書く（台帳より先。台帳が壊れていても止まる）
      2. 台帳に `halt_tripped` を書く
      3. どちらかが失敗したら **非ゼロで返す** — 呼び出し側はその行為を通してはいけない

    ラッチが残って台帳が空になった場合、`active_halt` は `latch_only` として halt を報告する。
    **止まりすぎる方向の失敗**であり、それが正しい向きである。
    """
    _wp = require_writer_path("trip-halt")
    if _wp:
        print(json.dumps({"ok": False, "reason": "direct_write_refused", "detail": _wp},
                         ensure_ascii=False) if "trip-halt" != "append" else f"trip-halt: {_wp}",
              file=sys.stderr if "trip-halt" == "append" else sys.stdout)
        return 4

    if not (a.reason or "").strip():
        print(json.dumps({"halted": False, "reason": "missing_reason",
                          "detail": "--reason が必要。なぜ止めたのかが記録されない halt は、"
                                    "解除の判断ができない。"}, ensure_ascii=False))
        return 2
    os.makedirs(a.root, exist_ok=True)
    latch_path = os.path.join(a.root, HALT_LATCH)
    latch_ok = False
    try:
        # **ラッチを先に書く。** 台帳の追記に失敗しても、次の呼び出しは止まる。
        with open(latch_path, "w", encoding="utf-8") as f:
            json.dump({"trigger": a.trigger, "scope": a.scope, "reason": a.reason,
                       "tripped_by": a.tripped_by}, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        _fsync_dir(a.root)
        latch_ok = True
    except Exception as e:
        print(f"trip-halt: HALT ラッチを書けなかった（{e}）。", file=sys.stderr)

    payload = {"trigger": a.trigger, "scope": a.scope, "reason": a.reason,
               "tripped_by": a.tripped_by, "latch_written": latch_ok}
    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(json.dumps({"halted": latch_ok, "reason": "lock_failed",
                              "latch_written": latch_ok, "detail": lk.error},
                             ensure_ascii=False))
            return 4
        snap, serr = load_schema_snapshot()
        if serr:
            print(json.dumps({"halted": latch_ok, "reason": "schema_unreadable",
                              "latch_written": latch_ok, "detail": serr}, ensure_ascii=False))
            return 4
        bad, _w = validate_event("halt_tripped", payload, snap, writer_op="halt_tripped")
        if bad:
            print(json.dumps({"halted": latch_ok, "reason": "schema_rejected",
                              "latch_written": latch_ok, "detail": bad}, ensure_ascii=False))
            return 4
        head, herr = _head_from_log(a.root)
        if herr:
            # 台帳が壊れていても **ラッチは書けている** ので、次の呼び出しは止まる。
            print(json.dumps({"halted": latch_ok, "reason": "ledger_unhealthy",
                              "latch_written": latch_ok, "detail": herr},
                             ensure_ascii=False))
            return 4
        ev = {"id": "e" + hashlib.sha256(
                  f"{head['seq'] + 1}:halt_tripped:"
                  f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
              ).hexdigest()[:12],
              "seq": head["seq"] + 1, "ts": _now_iso(), "actor": a.tripped_by,
              "class": "halt_tripped", "payload": payload,
              "schema_id": "orgforge-ledger", "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"], "prev_hash": head["hash"]}
        ev["hash"] = _hash(head["hash"], ev)
        log, headp = _paths(a.root)
        try:
            # 故障注入。**halt が書けなかったときに何が起きるか**を検査できなければ、
            # 「記録できない halt は fail-open にならない」とは言えない。
            if os.environ.get("ORG_LEDGER_FORCE_APPEND_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_APPEND_FAIL=1（故障注入）")
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp = headp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": ev["seq"], "hash": ev["hash"]}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, headp)
            _fsync_dir(a.root)
        except Exception as e:
            print(json.dumps({"halted": latch_ok, "reason": "halt_not_persisted",
                              "latch_written": latch_ok,
                              "detail": f"台帳に halt を書けなかった（{e}）。"
                                        f"ラッチ={'あり' if latch_ok else 'なし'}。"},
                             ensure_ascii=False))
            return 4
    print(json.dumps({"halted": True, "reason": "tripped", "seq": ev["seq"],
                      "latch_written": latch_ok}, ensure_ascii=False))
    print(f"HALT tripped (seq={ev['seq']}): {a.reason}\n"
          f"  gated な行為はすべて止まる。観測・検証・安全な修復だけが通る。\n"
          f"  **解除は H4a では実装していない** — trip した主体と独立した承認が要り、それは"
          f"identity の認証（H1）に依存する。\n"
          f"  いま解除するには、台帳に halt_released を書ける仕組みが必要である"
          f"（writer 専用として宣言済み、操作は未実装）。", file=sys.stderr)
    return 0



def cmd_release_halt(a):
    """halt を解除する。**止めた主体とは独立した principal の署名が必要（H4b）。**

    ## 順序が重要である

      1. active halt を確認する（無ければ解除するものが無い）
      2. **独立した release principal** を receipt で検証する
         - 非対称鍵であること（共有鍵は「別主体」を証明しない）
         - `may_release_halt` を認可されていること
         - **halt を発動した主体と別であること**
      3. 復旧の証拠を検証する（`--recovery-verified` の中身が空なら拒否）
      4. `halt_released` を append + fsync
      5. **その後で初めて** HALT ラッチを消す
      6. ラッチの削除に失敗したら **停止を維持する**（消せないなら止まったままにする）

    逆順にすると、ラッチを消したあとに台帳への追記が失敗して **halt が消えたまま記録が無い**
    状態になる。それは「止まっていたのに、止まっていた証拠も止まっている状態も無い」である。
    """
    _wp = require_writer_path("release-halt")
    if _wp:
        print(json.dumps({"ok": False, "reason": "direct_write_refused", "detail": _wp},
                         ensure_ascii=False) if "release-halt" != "append" else f"release-halt: {_wp}",
              file=sys.stderr if "release-halt" == "append" else sys.stdout)
        return 4

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from identity import verify_receipt, observed_recorder

    halt, herr = active_halt(a.root)
    if not halt:
        print(json.dumps({"released": False, "reason": "no_active_halt"}, ensure_ascii=False))
        return 2
    if not (a.recovery_verified or "").strip():
        print(json.dumps({"released": False, "reason": "missing_recovery_evidence",
                          "detail": "--recovery-verified が必要。**何を確かめて復旧したのか**が"
                                    "記録されない解除は、解除の判断を後から検証できない。"},
                         ensure_ascii=False))
        return 2
    try:
        rc = json.loads(open(a.receipt, encoding="utf-8").read()) \
            if os.path.isfile(a.receipt) else json.loads(a.receipt)
    except Exception as e:
        print(json.dumps({"released": False, "reason": "receipt_unreadable",
                          "detail": str(e)}, ensure_ascii=False))
        return 2

    # **解除の receipt は halt の seq に束縛する。** 束縛しないと、別の halt の解除 receipt を
    # 持ち込んで使える（再利用）。
    expect = {"review_subject_id": f"halt:{halt.get('seq')}", "role": "release",
              "verdict": "release", "lineage": "release"}
    released_by, ident, rerr = verify_receipt(rc, expect, expect_release=True)
    if rerr:
        print(json.dumps({"released": False, "reason": "receipt_rejected", "detail": rerr},
                         ensure_ascii=False))
        return 4
    if ident.get("identity_assurance") != "authenticated":
        print(json.dumps({"released": False, "reason": "not_authenticated",
                          "detail": f"解除には authenticated な identity が必要"
                                    f"（いま {ident.get('identity_assurance')!r}）。\n"
                                    f"  共有鍵は「鍵が違う」ことしか示さず、"
                                    f"**別主体・独立した承認を証明しない。**"},
                         ensure_ascii=False))
        return 4
    # **止めた主体が自分で解除できてはいけない。**
    tripped_by = halt.get("tripped_by")
    if tripped_by and released_by == tripped_by:
        print(json.dumps({"released": False, "reason": "not_independent",
                          "detail": f"halt を発動した主体（{tripped_by}）が自分で解除しようと"
                                    f"している。**独立した承認が要る。**"}, ensure_ascii=False))
        return 4

    recorded_by, rec_assurance = observed_recorder()
    payload = {"releases_seq": halt.get("seq"), "reason": a.reason,
               "released_by": released_by, "recovery_verified": a.recovery_verified,
               "tripped_by": tripped_by,
               "identity_assurance": ident.get("identity_assurance"),
               "recorded_by": recorded_by, "recorder_assurance": rec_assurance,
               "signer_id": ident.get("signer_id"), "key_id": ident.get("key_id")}

    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(json.dumps({"released": False, "reason": "lock_failed",
                              "detail": lk.error}, ensure_ascii=False))
            return 4
        snap, serr = load_schema_snapshot()
        if serr:
            print(json.dumps({"released": False, "reason": "schema_unreadable",
                              "detail": serr}, ensure_ascii=False))
            return 4
        bad, _w = validate_event("halt_released", payload, snap, writer_op="halt_released")
        if bad:
            print(json.dumps({"released": False, "reason": "schema_rejected",
                              "detail": bad}, ensure_ascii=False))
            return 4
        head, hh = _head_from_log(a.root)
        if hh:
            print(json.dumps({"released": False, "reason": "ledger_unhealthy",
                              "detail": hh}, ensure_ascii=False))
            return 4
        ev = {"id": "e" + hashlib.sha256(
                  f"{head['seq'] + 1}:halt_released:"
                  f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
              ).hexdigest()[:12],
              "seq": head["seq"] + 1, "ts": _now_iso(), "actor": released_by,
              "class": "halt_released", "payload": payload,
              "schema_id": "orgforge-ledger", "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"], "prev_hash": head["hash"]}
        ev["hash"] = _hash(head["hash"], ev)
        log, headp = _paths(a.root)
        prior_size = os.path.getsize(log) if os.path.exists(log) else 0
        try:
            # 故障注入。**記録できていないのに停止が解けることが、いちばん危ない fail-open**
            # である。故障を再現できなければ「停止を維持する」とは言えない。
            if os.environ.get("ORG_LEDGER_FORCE_APPEND_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_APPEND_FAIL=1（故障注入）")
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp = headp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": ev["seq"], "hash": ev["hash"]}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, headp)
            _fsync_dir(a.root)
        except Exception as e:
            try:
                if os.path.exists(log) and os.path.getsize(log) > prior_size:
                    with open(log, "r+b") as f:
                        f.truncate(prior_size)
                        f.flush()
                        os.fsync(f.fileno())
            except Exception:
                pass
            print(json.dumps({"released": False, "reason": "release_not_persisted",
                              "detail": f"解除を記録できなかった（{e}）。**停止は維持される。**"},
                             ensure_ascii=False))
            return 4

        # **記録できてから、初めてラッチを消す。** 逆順にすると、ラッチを消したあとに追記が
        # 失敗して「止まっていた証拠も、止まっている状態も無い」状態になる。
        latch = os.path.join(a.root, HALT_LATCH)
        latch_cleared = True
        if os.path.exists(latch):
            try:
                os.unlink(latch)
                _fsync_dir(a.root)
            except Exception as e:
                latch_cleared = False
                print(f"release-halt: ラッチを消せなかった（{e}）。**停止は維持される** — "
                      f"台帳の解除は記録済みなので、同じ receipt で再実行すれば後片付けだけが"
                      f"行われる（exact retry は安全）。", file=sys.stderr)

    print(json.dumps({"released": latch_cleared, "reason": "released" if latch_cleared
                      else "recorded_but_latch_remains",
                      "seq": ev["seq"], "releases_seq": halt.get("seq"),
                      "released_by": released_by, "tripped_by": tripped_by,
                      "identity_assurance": ident.get("identity_assurance")},
                     ensure_ascii=False))
    return 0 if latch_cleared else 4


def cmd_halt_status(a):
    """halt しているかを報告する。**観測は halt 中でも通る。**"""
    h, err = active_halt(a.root)
    if h is None:
        print(json.dumps({"halted": False}, ensure_ascii=False))
        return 0
    print(json.dumps({"halted": True, "source": h.get("source"),
                      "seq": h.get("seq"), "reason": h.get("reason"),
                      "tripped_by": h.get("tripped_by"), "trigger": h.get("trigger"),
                      "scope": h.get("scope")}, ensure_ascii=False))
    return 10



def cmd_derive_admission(a):
    """**2件の認証済み provisional から admission を生成する。** writer の専用操作。

    ## なぜ専用操作にするのか

    joint admission は「2つの判定が一致した」という **事実の関数**であって、新しい判断ではない。
    したがって judge の receipt は存在しない — それを generic append で書こうとすると、
    `require_attested_identity` が「receipt が無い」として拒否し、**一致しても admission を
    作れないデッドロック**になる。

    ここでは台帳の中の2件を読んで検証する:
      - 同じ issue / event / subject であること
      - verdict が一致していること
      - **両方が認証済み**であること（claimed の判定からは joint を作らない）
      - 血統が異なること（same-harness と cross-harness）

    生成する identity は `system:joint(...)` であり、**judge の identity ではない** —
    誰かの判断として記録しない。
    """
    # **writer が居るなら、ここも RPC を通す。** 他の書き込み経路（append /
    # reserve-exposure / trip-halt / release-halt）は writer 経由を要求していたのに、
    # **この経路だけ直接書けていた**（実測: writer 稼働中に台帳が 2 → 3 件に増えた）。
    # しかもここが書くのは `admission_decided` — 最も強い権限の記録である。
    # 単一 writer の保証は、**全部の経路が通って初めて成り立つ**。
    _wp = require_writer_path("derive-admission")
    if _wp:
        print(json.dumps({"ok": False, "reason": "writer_required", "detail": _wp},
                         ensure_ascii=False))
        return 4
    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(json.dumps({"ok": False, "reason": "lock_failed", "detail": lk.error},
                             ensure_ascii=False))
            return 4
        snap, serr = load_schema_snapshot()
        if serr:
            print(json.dumps({"ok": False, "reason": "schema_unreadable", "detail": serr},
                             ensure_ascii=False))
            return 4
        head, herr = _head_from_log(a.root)
        if herr:
            print(json.dumps({"ok": False, "reason": "ledger_unhealthy", "detail": herr},
                             ensure_ascii=False))
            return 4
        try:
            evs = _read_events(a.root)
        except Exception as e:
            print(json.dumps({"ok": False, "reason": "ledger_unreadable", "detail": str(e)},
                             ensure_ascii=False))
            return 4
        voided = set(voided_seqs(evs))
        found = {}
        for e in evs:
            if e.get("class") != "verdict_provisional" or e.get("seq") in voided:
                continue
            pl = e.get("payload") or {}
            if norm_issue(pl.get("issue")) != norm_issue(a.issue):
                continue
            if pl.get("for_event") != a.event:
                continue
            found[pl.get("lineage")] = {**pl, "seq": e.get("seq")}
        # 今回の一致がどの対象についてのものかを先に決める（同一性の鍵）。
        _subject_now = None
        for e in evs:
            if e.get("class") != "verdict_provisional" or e.get("seq") in voided:
                continue
            _p = e.get("payload") or {}
            if (norm_issue(_p.get("issue")) == norm_issue(a.issue)
                    and _p.get("for_event") == a.event):
                _subject_now = _p.get("review_subject_id")
        # **同じ一致から2件目を作らない。** joint は「2つの判定が一致した」という
        # *事実の関数* であって、新しい判断ではない。事実は一度きりなので、
        # 同じ issue / event に joint が既に在るなら、もう作ってはいけない。
        # 作れてしまうと、1つの成果物が2回 admit されたように見える（二重計上）。
        # 実測: derive-admission を2回呼ぶと admission が2件になっていた。
        for e in evs:
            # Gate の joint だけに固定すると skeptic の `refutation_attempted` は毎回
            # 素通りし、同じ provisional pair から無限に複製できる。呼び出しが派生する
            # event class 自体を natural key の一部として照合する。
            if e.get("class") != a.event:
                continue
            # **訂正・取り消しされた admission は「既にある」に数えない。**
            # 数えると、対象を差し替えて訂正したあと **二度と admit できない**
            # （実測: superseded にしても already_admitted で拒否された）。
            # 訂正できない統制は、間違えたら詰む統制である。
            if e.get("seq") in voided:
                continue
            _pl = e.get("payload") or {}
            # **同じ「対象」に対する二重計上だけを止める。**
            # (issue, event) だけを鍵にすると、**同じ issue の別リビジョンを
            # 二度と admit できない**（実測: S1 を admit したあと S2 が
            # already_admitted で拒否された）。判定の同一性は
            # `review_subject_id` が決める — それが subject という概念の意味である。
            if (norm_issue(_pl.get("issue")) == norm_issue(a.issue)
                    and _pl.get("for_event", a.event) == a.event
                    and _pl.get("review_subject_id") == _subject_now):
                print(json.dumps(
                    {"ok": False, "reason": "already_admitted",
                     "seq": e.get("seq"),
                     "detail": f"#{a.issue} / {a.event} の joint は seq="
                               f"{e.get('seq')} に既にある。**一致は事実なので、"
                               f"同じ一致から2件目は作らない**（二重計上になる）。"},
                    ensure_ascii=False))
                return 6
        if len(found) < 2:
            print(json.dumps({"ok": False, "reason": "not_enough_verdicts",
                              "detail": f"#{a.issue} / {a.event} の provisional が "
                                        f"{len(found)} 件しかない（血統: {sorted(found)}）。"
                                        f"2血統が揃ってから生成すること。"}, ensure_ascii=False))
            return 3
        subs = {v.get("review_subject_id") for v in found.values()}
        if len(subs) != 1:
            print(json.dumps({"ok": False, "reason": "subject_mismatch",
                              "detail": f"2件が別の対象を見ている: {sorted(map(str, subs))}"},
                             ensure_ascii=False))
            return 3
        # Two independent positive judgments may still agree on the same obsolete premise.  Strict
        # orgs therefore re-resolve the integration ref after both votes exist and immediately
        # before the joint event is created.  This does not fetch or rebase; uncertainty stops here.
        try:
            from discover import constitution
            from review_freshness import descriptor_status, freshness_policy
            _constitution_path = constitution()
            _declared, _strict_freshness, _freshness_error = freshness_policy(_constitution_path)
        except Exception as exc:
            _strict_freshness, _freshness_error = False, str(exc)
        if _freshness_error:
            print(json.dumps({"ok": False, "reason": "freshness_policy_unreadable",
                              "detail": _freshness_error}, ensure_ascii=False))
            return 4
        if _strict_freshness:
            for lineage, provisional in sorted(found.items()):
                descriptor = provisional.get("review_subject")
                if not isinstance(descriptor, dict):
                    print(json.dumps({
                        "ok": False, "reason": "subject_descriptor_missing",
                        "detail": (f"{lineage} の provisional は integration ref/base の descriptor "
                                   "を持たない。旧判定は strict admission に再利用できない。"
                                   "verify と判定をやり直すこと。")}, ensure_ascii=False))
                    return 7
                if descriptor.get("review_subject_id") != provisional.get("review_subject_id"):
                    print(json.dumps({"ok": False, "reason": "subject_descriptor_mismatch",
                                      "detail": f"{lineage} の descriptor が subject と一致しない"},
                                     ensure_ascii=False))
                    return 7
                subject_cwd = descriptor.get("subject_root") or os.getcwd()
                freshness = descriptor_status(descriptor, subject_cwd)
                if not freshness["ok"]:
                    print(json.dumps({"ok": False, "reason": freshness["reason"],
                                      "detail": (f"{lineage}: {freshness['detail']}。"
                                                 "自動 rebase はせず、再検証を要求する。"),
                                      "review_subject_id": provisional.get("review_subject_id"),
                                      "integration_ref": descriptor.get("integration_ref"),
                                      "observed": freshness}, ensure_ascii=False))
                    return 7
        verdicts = {v.get("verdict") for v in found.values()}
        if len(verdicts) != 1:
            print(json.dumps({"ok": False, "reason": "verdicts_disagree",
                              "detail": f"一致していない: {sorted(map(str, verdicts))}。"
                                        f"**片方でも否なら否である。**"}, ensure_ascii=False))
            return 5
        # **両方が認証済みでなければ joint を作らない。** claimed の判定から作ると、
        # 「一致した」という事実に、確かめていない identity の重みが乗る。
        weak = {lin: v.get("identity_assurance") or "claimed" for lin, v in found.items()
                if (v.get("identity_assurance") or "claimed") == "claimed"}
        # **強制するかどうかを caller に尋ねない。**
        # 元は `a.require_attested`（caller が渡す flag）だけを見ていたので、
        # flag を省略するだけで claimed な判定から admission を作れた（実測: B1）。
        # 宣言（constitution / root-owned policy）が真なら、flag の有無に関わらず強制する。
        # flag は「宣言していない org でも厳しくしたい」ときの *上乗せ* としてのみ残す。
        _must_attest = bool(a.require_attested) or _enforce_attested()
        if weak and _must_attest:
            print(json.dumps({"ok": False, "reason": "unattested_verdicts",
                              "detail": f"identity が claimed の判定がある: {weak}。"
                                        f"**確かめていない identity から joint を作らない。**"},
                             ensure_ascii=False))
            return 4
        # **独立性も writer が判定する。** 2件の signer / key / workload は台帳にあるので、
        # 呼び出し側の申告を待つ必要が無い。
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from identity import reviewer_independence
            _a, _b = list(found.values())
            independence = reviewer_independence(
                _a.get("decision_by"),
                {"signer_id": _a.get("signer_id"), "key_id": _a.get("key_id"),
                 "workload_isolation": _a.get("workload_isolation") or "none"},
                {"signer_id": _b.get("signer_id"), "key_id": _b.get("key_id"),
                 "workload_isolation": _b.get("workload_isolation") or "none"})
        except Exception:
            independence = "same_signer"        # 判定できないなら最も弱い方に倒す
        lineages = sorted(found)
        pair = {lin: {"seq": v["seq"], "reasoning_sha256": v.get("reasoning_sha256"),
                      "reasoning_ref": v.get("reasoning_ref")} for lin, v in found.items()}
        joint_digest = hashlib.sha256(json.dumps(
            {k: v["reasoning_sha256"] for k, v in sorted(pair.items())},
            sort_keys=True).encode("utf-8")).hexdigest()
        order = ["claimed", "observed", "attested", "authenticated"]
        payload = {"issue": a.issue, "deliverable": str(a.issue),
                   "verdict": list(verdicts)[0], "lineage": "joint",
                   "agreed_by": lineages, "review_subject_id": list(subs)[0],
                   "reviewer_independence": independence,
                   "from_seqs": sorted(v["seq"] for v in found.values()),
                   "reasoning_by_lineage": pair, "reasoning_sha256": joint_digest,
                   "agreed_identity_assurance": min(
                       (v.get("identity_assurance") or "claimed" for v in found.values()),
                       key=order.index),
                   # **judge の identity ではない。** 誰かの判断として記録しない。
                   "decision_by": f"system:joint({','.join(lineages)})",
                   "recorded_by": "system:writer", "identity_assurance": "derived",
                   "recorder_assurance": "observed", "workload_isolation": "none"}
        if _strict_freshness:
            payload["review_subject"] = next(iter(found.values()))["review_subject"]
        bad, _w = validate_event(a.event, payload, snap, writer_op=a.event)
        if bad:
            print(json.dumps({"ok": False, "reason": "schema_rejected", "detail": bad},
                             ensure_ascii=False))
            return 4
        ev = {"id": "e" + hashlib.sha256(
                  f"{head['seq'] + 1}:{a.event}:"
                  f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
              ).hexdigest()[:12],
              "seq": head["seq"] + 1, "ts": _now_iso(), "actor": "system:writer",
              "class": a.event, "payload": payload,
              "schema_id": "orgforge-ledger", "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"], "prev_hash": head["hash"]}
        ev["hash"] = _hash(head["hash"], ev)
        log, headp = _paths(a.root)
        prior = os.path.getsize(log) if os.path.exists(log) else 0
        try:
            # 故障注入。**書けなかったら生成しない**ことを検査できなければ、そう言えない。
            if os.environ.get("ORG_LEDGER_FORCE_APPEND_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_APPEND_FAIL=1（故障注入）")
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp = headp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": ev["seq"], "hash": ev["hash"]}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, headp)
            _fsync_dir(a.root)
        except Exception as e:
            try:
                if os.path.exists(log) and os.path.getsize(log) > prior:
                    with open(log, "r+b") as f:
                        f.truncate(prior)
                        f.flush()
                        os.fsync(f.fileno())
            except Exception:
                pass
            print(json.dumps({"ok": False, "reason": "not_persisted", "detail": str(e)},
                             ensure_ascii=False))
            return 4
    print(json.dumps({"ok": True, "reason": "derived", "seq": ev["seq"],
                      "verdict": payload["verdict"], "from_seqs": payload["from_seqs"],
                      "reviewer_independence": independence,
                      "agreed_identity_assurance": payload["agreed_identity_assurance"]},
                     ensure_ascii=False))
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
    validated = legacy = 0
    vsnap, drift = None, set()
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
        # 条件6: **version 別の validator を再実行する。** 鎖が通っていることは「書き換えられて
        # いない」ことしか言わず、「schema に沿っている」ことは言わない。version を持つ
        # イベントだけを検証する — legacy に遡って適用すると移行できない。
        v = ev.get("schema_version")
        if v:
            if v > LEDGER_SCHEMA_VERSION:
                print(f"BROKEN: seq {ev['seq']} は未知の schema_version {v} "
                      f"（この writer は v{LEDGER_SCHEMA_VERSION} まで）。"
                      f"新しい版で書かれた台帳を古い道具で読んでいる。", file=sys.stderr)
                return 1
            if vsnap is None:
                vsnap, verr = load_schema_snapshot()
                if verr:
                    print(f"BROKEN: schema を読めないので v{v} の検証ができない — {verr}",
                          file=sys.stderr)
                    return 1
            # **記録時の digest を照合する。** 記録された schema_sha256 と、いま読んでいる
            # schema の digest が違うなら、形式が入れ替わっている。検証が「いまの schema に
            # 沿っているか」しか言えないなら、記録時に何で検証したのかは失われる。
            rec = ev.get("schema_sha256")
            if rec and rec != vsnap["digest"]:
                drift.add(rec)
            # **verify では writer_only を検査しない。** これは「誰が書いたか」の検査で、
            # append の時点でしか行えない（経路は記録に残らない）。既に書かれた予約を
            # 「generic append では書けない」と拒否すると、正しい台帳が壊れていると報告される。
            bad, _w = validate_event(ev.get("class"), ev.get("payload"), vsnap,
                                     writer_op=ev.get("class"))
            if bad:
                print(f"BROKEN: seq {ev['seq']} が v{v} の検証を通らない — {bad}",
                      file=sys.stderr)
                return 1
            validated += 1
        else:
            legacy += 1
        prev = ev["hash"]
        expect_seq += 1
    if validated or legacy:
        # **2つの保証を混ぜない。** schema 検証済みかと actor 認証済みかは独立した性質である。
        if drift:
            print(f"注意: {len(drift)} 種類の schema digest で記録されたイベントがある "
                  f"（いまの schema は {vsnap['digest'][:12]}…）。\n"
                  f"  形式が入れ替わっている — 再検証は **いまの schema** に対して行われた。"
                  f"記録時に何で検証したのかは、その版の schema が無ければ再現できない。",
                  file=sys.stderr)
        print(f"validation_assurance: validated:v{LEDGER_SCHEMA_VERSION} {validated} 件 / "
              f"legacy_unvalidated {legacy} 件"
              + ("\n  legacy は読めるが、schema 検証済みとしては扱わない"
                 "（遡って拒否すると移行できない）。" if legacy else ""))
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
        # RESOLVE (not raw rows): candidates started but not FINISHED, each with its LATEST progress
        # checkpoint. This is the recovery source after a context wipe — the SessionStart hook and
        # /org-resume read it to answer "what was this role mid-way through, and what's the next step?"
        # "Finished" is any of (#102 / OBS-050 — cycle_completed alone leaks WIP slots forever):
        #   - cycle_completed for the candidate;
        #   - integration_admitted{verdict: pass} that names THIS candidate_id — the integrate
        #     step (ship.py) records which candidate it merged, so exactly that slot frees and
        #     nothing else: a parallel sibling on the same issue and a later rework start both
        #     stay visible (skeptic C3/C2 — the finish decision is cycle-level, not issue-level);
        #   - LEGACY fallback for integrations WITHOUT candidate_id (all pre-#102 ledgers, incl.
        #     Tatekae/OBS-050): correlate candidate_id ↔ issue via the ledger's alias bridge, and
        #     only a TEMPORALLY LATER integration finishes the start — compared on ts when both
        #     events carry the writer-enforced UTC form (a backfilled receipt with an earlier ts
        #     must not kill a later rework start), on seq only when ts is unusable or tied.
        #     Documented limitation: this legacy path has no candidate information, so it cannot
        #     protect a live SIBLING started before the integration on the same issue; only the
        #     candidate_id-carrying form (new ledgers) gives full protection;
        #   - the cycle_started itself voided by a correction — voided_seqs, the single
        #     effective-event projection derive-admission uses (OBS-042: no third semantics).
        started, completed, latest = {}, {}, {}
        integrated_exact, integrated_legacy = set(), []
        for e in events:
            pl = e["payload"]
            if e["class"] == "integration_admitted":
                if str(pl.get("verdict", "")).strip().lower() in ("pass", "admit"):
                    icid = str(pl.get("candidate_id") or "").strip()
                    if icid:
                        integrated_exact.add(icid)
                    else:
                        integrated_legacy.append((e["seq"], str(e.get("ts") or ""), pl))
                continue
            cid = pl.get("candidate_id")
            if not cid:
                continue
            if e["class"] == "cycle_started":
                started[cid] = {"candidate_id": cid, "role": pl.get("role"),
                                "started_seq": e["seq"], "started_ts": str(e.get("ts") or ""),
                                "payload": pl}
            elif e["class"] == "cycle_completed":
                completed[cid] = (e["seq"], str(e.get("ts") or ""))
            elif e["class"] == "progress_recorded":
                latest[cid] = {k: pl.get(k) for k in
                               ("fraction", "phase", "done_so_far", "next_step", "blocked_by", "artifacts")}
        voided = voided_seqs(events)
        find = _work_aliases(events)
        legacy_roots = [(iseq, its, {find(x) for x in _correlation_ids(p)})
                        for iseq, its, p in integrated_legacy]
        _TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

        def _event_after(eseq, ets, sseq, sts):
            # Writer-enforced UTC form makes lexicographic ts comparison a real temporal order;
            # seq decides only when ts is unusable on either side, or exactly tied.
            if _TS.match(ets) and _TS.match(sts) and ets != sts:
                return ets > sts
            return eseq > sseq

        wip = []
        for cid, row in started.items():
            finished = completed.get(cid)
            if (finished and _event_after(*finished, row["started_seq"], row["started_ts"])) \
                    or row["started_seq"] in voided:
                continue
            if cid in integrated_exact:
                continue
            row_roots = {find(x) for x in
                         (_correlation_ids(row["payload"]) | _alias_ids(row["payload"]))}
            if any(_event_after(iseq, its, row["started_seq"], row["started_ts"])
                   and (roots & row_roots)
                   for iseq, its, roots in legacy_roots):
                continue
            wip.append({"candidate_id": cid, "role": row["role"],
                        "started_seq": row["started_seq"], "progress": latest.get(cid)})
        wip.sort(key=lambda w: w["started_seq"])
        print(json.dumps({"view": "work_in_progress", "in_progress": wip}, indent=2, ensure_ascii=False))
        return 0
    if a.view_id == "goal_state":
        goals = goal_states_from_events(events)
        print(json.dumps({"view": "goal_state", "goals": goals,
                          "current": goals[-1] if goals else None},
                         indent=2, ensure_ascii=False))
        return 0
    if a.view_id == "adaptive_envelope_status":
        from adaptation import fold, load_contract
        contract, _, _ = load_contract(a.root, required=False)
        print(json.dumps({"view": "adaptive_envelope_status", **fold(events, contract=contract)},
                         indent=2, ensure_ascii=False))
        return 0
    if a.view_id == "operational_state":
        from operational_state import fold
        from adaptation import load_contract
        contract, _, _ = load_contract(a.root, required=False)
        print(json.dumps({"view": "operational_state", **fold(events, contract=contract)},
                         indent=2, ensure_ascii=False))
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



def _banner():
    """実行しているバージョンと cwd を stderr に1行（docs/11 — 古いパスの流用に気づくため）。"""
    ver = "?"
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, "..", ".claude-plugin", "plugin.json"),
              os.path.join(here, "..", "integrations", "claude-code",
                           ".claude-plugin", "plugin.json")):
        try:
            with open(c, encoding="utf-8") as f:
                ver = json.load(f).get("version", "?")
            break
        except Exception:
            continue
    # **機械可読な出力を汚さない。** stderr に書いていても、消費側が 2>&1 で混ぜると JSON が
    # 壊れる（実地でテストが JSONDecodeError で落ちた）。view / census / digest は JSON を返す
    # サブコマンドなので、`--json` の有無に関わらず黙る。人間向けの補助のために、機械が読む
    # 出力を壊すのは筋が通らない。
    _MACHINE = ("view", "census", "digest", "cat")
    if (os.environ.get("ORG_QUIET") or "--json" in sys.argv
            or any(m in sys.argv[1:2] for m in _MACHINE)):
        return
    print(f"[orgforge {ver} @ {os.getcwd()}]", file=sys.stderr)


def main(argv):
    p = argparse.ArgumentParser(prog="ledger", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("append"); q.set_defaults(fn=cmd_append)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")
    q.add_argument("--actor", required=True)
    q.add_argument("--class", dest="cls", required=True)
    q.add_argument("--payload", required=True)
    # **通常の append で時刻を指定させない。** 時刻は writer が付ける（順序を偽れないように）。
    # 実時点を後から補う backfill だけが別経路で、**意図を名前に出す**。
    q.add_argument("--backfill-ts", dest="ts", default=None, metavar="TS",
                   help="実時点を後から補う場合の時刻（ISO8601 UTC）。通常は渡さない — "
                        "時刻は writer が付ける。未来や遠い過去は拒否される")
    q.add_argument("--ts", dest="ts_legacy", default=None, help=argparse.SUPPRESS)
    # **judgment を記録するなら receipt を渡す。** この道具が検証し、identity fields を生成する。
    # 環境変数の印は受け取らない — caller が立てられるものは証拠にならない。
    q.add_argument("--receipt", default=None,
                   help="judge が署名した receipt（ファイルか JSON）。検証できたときだけ "
                        "identity fields が生成される")
    # cap 予約は writer 側の専用操作。**時刻の引数を定義しない** — cap 予約に backfill を
    # 持ち込むと、窓の外に予約を置いて上限を迂回できる。
    rx = sub.add_parser("reserve-exposure",
                        help="cap を検査して予約を1操作で書く（書けた判断だけが allow）")
    rx.add_argument("root", nargs="?", default=None)
    rx.add_argument("--dimension", required=True)
    rx.add_argument("--delta", type=float, required=True)
    rx.add_argument("--cap", type=float, required=True)
    rx.add_argument("--actor", required=True)
    rx.add_argument("--window-since", dest="window_since")
    rx.add_argument("--caused-by", dest="caused_by")
    # 冪等キー。**欠けていれば metered action を deny する。**
    rx.add_argument("--session-id", dest="session_id", required=True)
    rx.add_argument("--tool-use-id", dest="tool_use_id", required=True)
    rx.add_argument("--rule", required=True)
    rx.set_defaults(fn=cmd_reserve_exposure)
    # **2件の認証済み provisional から admission を生成する。** judge の receipt は存在しない
    # （一致は判断ではなく事実の関数）ので、専用操作にする — generic append では
    # 「receipt が無い」として拒否され、一致してもデッドロックする。
    da = sub.add_parser("derive-admission",
                        help="2血統の一致から admission を生成する（writer 専用）")
    da.add_argument("root", nargs="?", default=None)
    da.add_argument("--issue", required=True)
    da.add_argument("--event", required=True,
                    choices=("admission_decided", "refutation_attempted"))
    da.add_argument("--require-attested", dest="require_attested", action="store_true",
                    help="claimed の判定からは生成しない")
    da.set_defaults(fn=cmd_derive_admission)
    # HALT。**writer 専用の操作。** 記録できなければ非ゼロで返す（呼び出し側は通さない）。
    th = sub.add_parser("trip-halt", help="halt を発動する（ラッチ→台帳の順に書く）")
    th.add_argument("root", nargs="?", default=None)
    th.add_argument("--trigger", required=True, help="何が halt を引き起こしたか")
    th.add_argument("--scope", default="global", choices=("global", "role"))
    th.add_argument("--reason", required=True, help="なぜ止めたのか（解除の判断に使う）")
    th.add_argument("--tripped-by", dest="tripped_by", required=True)
    th.set_defaults(fn=cmd_trip_halt)
    rh = sub.add_parser("release-halt",
                        help="halt を解除する（**独立した principal の非対称署名が必要**）")
    rh.add_argument("root", nargs="?", default=None)
    rh.add_argument("--receipt", required=True,
                    help="解除の receipt。may_release_halt を認可された **非対称** 鍵で署名し、"
                         "halt の seq に束縛されていること")
    rh.add_argument("--reason", required=True, help="なぜ解除してよいと判断したのか")
    rh.add_argument("--recovery-verified", dest="recovery_verified", required=True,
                    help="**何を確かめて復旧したのか**（実行したコマンドと出力）")
    rh.set_defaults(fn=cmd_release_halt)
    hs = sub.add_parser("halt-status", help="halt しているかを報告する（観測なので halt 中も通る）")
    hs.add_argument("root", nargs="?", default=None)
    hs.set_defaults(fn=cmd_halt_status)
    s = sub.add_parser("schema",
                       help="org の schema とテンプレートの差分を診断する（--fix で埋める）")
    s.add_argument("root", nargs="?", default=None)
    s.add_argument("--fix", action="store_true", help="足りないクラス／validation を追加する")
    s.set_defaults(fn=cmd_schema)
    q.add_argument("--natural-key", dest="natural_key",
                   help="idempotency key: if a prior event of this class carries the same key, "
                        "this append is a no-op (docs/11 §0 — replay/retry must count once)")

    sc = sub.add_parser("record-scheduled-check",
                        help="scheduler checkの実行receiptを書く（writer専用）")
    sc.add_argument("root", nargs="?", default=None)
    sc.add_argument("--check-id", required=True)
    sc.add_argument("--scheduled-for-min", type=int, required=True)
    sc.add_argument("--execution-id", required=True)
    sc.add_argument("--result", choices=("ok", "escalate"), required=True)
    sc.add_argument("--exit-code", type=int, choices=(0, 10), required=True)
    sc.add_argument("--command-sha256", required=True)
    sc.add_argument("--plugin-version", required=True)
    sc.set_defaults(fn=cmd_record_scheduled_check)

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
    _banner()
    # root は省略可能: 省略時はカレントから自動発見する（.envrc 不要 — tools/discover.py）
    if hasattr(a, "root"):
        a.root = resolve_root(a.root)
    # A long-running judge can forget the installed plugin path and find an unrelated development
    # checkout. Read-only inspection remains useful from anywhere, but every mutation must come
    # from the organ registered by SessionStart (or carry an explicit developer bypass).
    mutating = a.cmd in {"append", "record-scheduled-check", "reserve-exposure", "derive-admission",
                         "trip-halt", "release-halt"}
    mutating = mutating or (a.cmd == "schema" and getattr(a, "fix", False))
    if mutating:
        try:
            from organ_binding import BindingError, foreign_invocation_error
            mismatch = foreign_invocation_error(a.root, os.path.dirname(os.path.abspath(__file__)))
        except BindingError as exc:
            print(f"ledger: installed-organ binding を検証できない: {exc}", file=sys.stderr)
            return 12
        if mismatch:
            print(f"ledger: {mismatch}", file=sys.stderr)
            return 12
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
