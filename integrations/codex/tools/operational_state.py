#!/usr/bin/env python3
"""Ledger-backed operational state, circuits, taint, and recovery.

The state machine does not optimize availability. It preserves declared critical functions and
human control while dependencies vary: NORMAL -> DEGRADED -> RECOVERING -> NORMAL, with HALTED
provided by the existing writer-owned halt latch. Recovery requires a successful probe, the owning
session, declared authority, and complete revalidation of every tainted artifact.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import read_events, resolve_root  # noqa: E402
from adaptation import _by_id, _current as current_envelope, authorize as authorize_adaptation
from adaptation import fold as fold_adaptation, load_contract  # noqa: E402


EVENTS = {
    "circuit_state_changed", "operational_state_transitioned", "operational_escalated",
    "artifact_tainted", "recovery_probe_recorded", "artifact_revalidated",
}
SHIP_ACTIONS = {"merge", "ship", "deploy", "publish", "merge_without_required_review"}


def _iso(value=None):
    if value:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def _fmt(value):
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _evidence(values):
    rows = list(values or [])
    if not rows or any(not str(value or "").strip() for value in rows):
        raise ValueError("at least one non-empty evidence reference is required")
    return rows


def fold(events, now=None, contract=None):
    recorded = "NORMAL"
    owner_session = None
    envelope_id = None
    activation_id = None
    circuit_id = None
    circuits = {}
    taints = {}
    probes = []
    escalations = []
    transitions = [{"seq": 0, "from_state": None, "to_state": "NORMAL", "source": "initial"}]
    active_halts = {}
    for event in events:
        cls = event.get("class")
        payload = event.get("payload") or {}
        if cls == "halt_tripped":
            active_halts[event.get("seq")] = payload
            transitions.append({"seq": event.get("seq"), "from_state": recorded,
                                "to_state": "HALTED", "source": "halt_tripped"})
        elif cls == "halt_released":
            active_halts.pop(payload.get("releases_seq"), None)
            if not active_halts:
                transitions.append({"seq": event.get("seq"), "from_state": "HALTED",
                                    "to_state": recorded, "source": "halt_released"})
        elif cls == "circuit_state_changed":
            circuits[payload.get("circuit_id")] = {"seq": event.get("seq"), **payload}
        elif cls == "operational_state_transitioned":
            recorded = payload.get("to_state")
            owner_session = payload.get("session_id") if recorded != "NORMAL" else None
            envelope_id = payload.get("envelope_id") if recorded != "NORMAL" else None
            activation_id = payload.get("activation_id") if recorded != "NORMAL" else None
            circuit_id = payload.get("circuit_id") if recorded != "NORMAL" else None
            transitions.append({"seq": event.get("seq"), "source": cls, **payload})
        elif cls == "artifact_tainted":
            taints[payload.get("artifact")] = {
                "taint_seq": event.get("seq"), "cleared": False, **payload}
        elif cls == "adaptive_deviation_recorded" and recorded in {"DEGRADED", "RECOVERING"}:
            # A deviation is the production record of work performed inside an envelope. Every
            # artifact it generated, referenced, or explicitly marked tainted inherits the cause
            # and declared revalidation scope; otherwise post-degradation work could escape the
            # recovery checklist merely because it did not exist at the initial outage.
            if payload.get("activation_id") == activation_id:
                affected = set(payload.get("artifacts") or []) | set(
                    payload.get("tainted_artifacts") or [])
                for artifact in affected:
                    taints[artifact] = {
                        "artifact": artifact, "taint_seq": event.get("seq"),
                        "cause_seq": event.get("seq"), "circuit_id": circuit_id,
                        "envelope_id": envelope_id, "activation_id": activation_id,
                        "reason": payload.get("reason") or "adaptive deviation",
                        "revalidation_scope": payload.get("revalidation_scope") or [],
                        "source": "adaptive_deviation_recorded", "cleared": False,
                    }
        elif cls == "artifact_revalidated":
            row = taints.get(payload.get("artifact"))
            if row and row.get("activation_id") == payload.get("activation_id"):
                required = set(row.get("revalidation_scope") or [])
                supplied = set(payload.get("checks") or [])
                row["last_revalidation_seq"] = event.get("seq")
                row["last_revalidation_result"] = payload.get("result")
                row["cleared"] = payload.get("result") == "pass" and required <= supplied
        elif cls == "recovery_probe_recorded":
            probes.append({"seq": event.get("seq"), **payload})
        elif cls == "operational_escalated":
            escalations.append({"seq": event.get("seq"), **payload})
    effective = recorded
    derived_reason = None
    if active_halts:
        effective = "HALTED"
        derived_reason = "active halt latch/event"
    elif recorded in {"DEGRADED", "RECOVERING"} and activation_id:
        adaptive = current_envelope(fold_adaptation(events, now), envelope_id)
        if not adaptive or adaptive.get("activation_id") != activation_id or \
                adaptive.get("status") == "expired":
            effective = "HALTED"
            derived_reason = "adaptive envelope expired or disappeared"
    return {
        "recorded_state": recorded, "effective_state": effective,
        "derived_reason": derived_reason, "owner_session_id": owner_session,
        "halt_latch_active": bool(active_halts),
        "envelope_id": envelope_id, "activation_id": activation_id, "circuit_id": circuit_id,
        "circuits": circuits, "taints": taints, "recovery_probes": probes,
        "escalations": escalations, "transitions": transitions,
        "unresolved_taints": sorted(path for path, row in taints.items() if not row.get("cleared")),
    }


def _envelope(contract, envelope_id):
    return _by_id(contract.get("adaptive_envelopes")).get(str(envelope_id or ""))


def authorize(contract, events, action, envelope_id=None, phase=None, artifacts=None, now=None):
    state = fold(events, now, contract)
    operational = contract.get("operational_state") or {}
    safe = set(operational.get("safe_actions") or [])
    if action in set(contract.get("globally_forbidden_actions") or []):
        return {"allowed": False, "reason": "constitutional/global forbidden action",
                "operational_state": state["effective_state"]}
    if action in SHIP_ACTIONS and state["effective_state"] in set(
            operational.get("ship_forbidden_states") or []):
        return {"allowed": False, "reason": f"ship is forbidden while {state['effective_state']}",
                "operational_state": state["effective_state"]}
    if state["effective_state"] == "NORMAL":
        return {"allowed": True, "reason": "operational state is NORMAL",
                "operational_state": "NORMAL"}
    if action in safe:
        return {"allowed": True, "reason": "safe response remains available",
                "operational_state": state["effective_state"]}
    if state["effective_state"] == "HALTED":
        return {"allowed": False, "reason": "HALTED permits only safe diagnosis or recovery",
                "operational_state": "HALTED"}
    bound_envelope = envelope_id or state.get("envelope_id")
    if bound_envelope != state.get("envelope_id"):
        return {"allowed": False, "reason": "action references a foreign adaptive envelope",
                "operational_state": state["effective_state"]}
    decision = authorize_adaptation(contract, events, bound_envelope, action, phase,
                                    artifacts or [], now=now)
    return {**decision, "operational_state": state["effective_state"]}


def _latest_probe(state, circuit_id, activation_id):
    rows = [row for row in state["recovery_probes"]
            if row.get("circuit_id") == circuit_id and row.get("activation_id") == activation_id]
    return rows[-1] if rows else None


def _bound_session_violation(session_id):
    bound = str(os.environ.get("ORG_ORGAN_SESSION_ID") or "")
    if bound and session_id != bound:
        return f"session {session_id!r} is not the installed-organ session {bound!r}"
    return None


def ledger_event_violation(event, history, ledger_root):
    cls = event.get("class")
    if cls not in EVENTS:
        return None
    payload = event.get("payload") or {}
    try:
        contract, _, _ = load_contract(ledger_root)
    except ValueError as exc:
        return str(exc)
    state = fold(history, event.get("ts"), contract)
    envelope = _envelope(contract, payload.get("envelope_id"))
    adaptive = current_envelope(fold_adaptation(history, event.get("ts")),
                                payload.get("envelope_id"))
    for field in ("reason",):
        if cls in {"circuit_state_changed", "operational_state_transitioned",
                   "operational_escalated", "artifact_tainted"} and \
                not str(payload.get(field) or "").strip():
            return f"{cls} requires a non-empty {field}"
    if cls == "circuit_state_changed":
        circuit = state["circuits"].get(payload.get("circuit_id"))
        prior = circuit.get("to_state") if circuit else "CLOSED"
        legal = {"CLOSED": {"OPEN"}, "OPEN": {"OPEN", "HALF_OPEN"},
                 "HALF_OPEN": {"OPEN", "CLOSED"}}
        if payload.get("from_state") != prior or payload.get("to_state") not in legal.get(prior, set()):
            return f"illegal circuit transition {payload.get('from_state')} -> {payload.get('to_state')}"
        if not envelope or not adaptive or adaptive.get("activation_id") != payload.get("activation_id") or \
                adaptive.get("status") not in {"active", "reverted"}:
            return "circuit transition requires the current declared envelope activation"
        if payload.get("retry_budget") != envelope.get("retry_budget"):
            return "circuit retry budget does not match the envelope"
        previous_count = circuit.get("retry_count", 0) if circuit else 0
        expected_count = previous_count + 1 if payload.get("to_state") == "OPEN" else previous_count
        if payload.get("retry_count") != expected_count:
            return "circuit retry count is not monotonic"
        if not 0 <= payload.get("confidence", -1) <= 1 or not payload.get("evidence"):
            return "circuit transition requires evidence and bounded confidence"
        if not str(payload.get("session_id") or "").strip():
            return "circuit transition requires a session owner"
        recovery = (envelope or {}).get("recovery") or {}
        if (payload.get("to_state") in {"HALF_OPEN", "CLOSED"} or prior == "HALF_OPEN") and \
                event.get("actor") != recovery.get("authority_role"):
            return "circuit recovery actor is not the declared recovery authority"
        return None
    if cls == "operational_state_transitioned":
        if state.get("halt_latch_active"):
            return "operational transition is blocked by the writer-owned HALT latch"
        operational = contract.get("operational_state") or {}
        source = state["recorded_state"]
        target = payload.get("to_state")
        if payload.get("from_state") != source or target not in set(
                (operational.get("transitions") or {}).get(source) or []):
            return f"illegal operational transition {payload.get('from_state')} -> {target}"
        if target == "HALTED":
            return "use the writer-owned trip-halt path for HALTED"
        if event.get("actor") != payload.get("transitioned_by"):
            return "operational transition actor does not match transitioned_by"
        circuit = state["circuits"].get(payload.get("circuit_id"))
        if not circuit:
            return "operational transition has no observed circuit"
        if source == "NORMAL" and target == "DEGRADED":
            if circuit.get("to_state") != "OPEN" or not adaptive or \
                    adaptive.get("status") != "active":
                return "DEGRADED requires an OPEN circuit and active adaptive envelope"
        else:
            if payload.get("session_id") != state.get("owner_session_id"):
                return "stale session cannot change operational recovery state"
            recovery = (envelope or {}).get("recovery") or {}
            if payload.get("transitioned_by") != recovery.get("authority_role"):
                return "transition actor is not the declared recovery authority"
        if source == "DEGRADED" and target == "RECOVERING":
            probe = _latest_probe(state, payload.get("circuit_id"), payload.get("activation_id"))
            if circuit.get("to_state") != "HALF_OPEN" or not probe or probe.get("result") != "pass" or \
                    probe.get("session_id") != payload.get("session_id"):
                return "RECOVERING requires a successful same-session half-open probe"
        if source == "RECOVERING" and target == "NORMAL":
            if circuit.get("to_state") != "CLOSED":
                return "NORMAL recovery requires a CLOSED circuit"
            if state["unresolved_taints"]:
                return f"NORMAL recovery blocked by unresolved taint: {state['unresolved_taints']}"
        if not 0 <= payload.get("confidence", -1) <= 1 or not payload.get("evidence"):
            return "operational transition requires evidence and bounded confidence"
        return None
    if cls == "artifact_tainted":
        if not envelope or not adaptive or adaptive.get("activation_id") != payload.get("activation_id"):
            return "taint requires the current adaptive envelope activation"
        if payload.get("revalidation_scope") != envelope.get("revalidation_scope"):
            return "taint revalidation scope does not match the envelope"
        if not str(payload.get("artifact") or "").strip() or \
                not isinstance(payload.get("cause_seq"), int):
            return "taint requires an artifact and causal ledger seq"
        return None
    if cls == "recovery_probe_recorded":
        circuit = state["circuits"].get(payload.get("circuit_id"))
        if state["recorded_state"] != "DEGRADED" or not circuit or \
                circuit.get("to_state") != "HALF_OPEN":
            return "recovery probe requires DEGRADED with a HALF_OPEN circuit"
        if payload.get("session_id") != state.get("owner_session_id"):
            return "stale session cannot record a recovery probe"
        recovery = (_envelope(contract, state.get("envelope_id")) or {}).get("recovery") or {}
        if event.get("actor") != recovery.get("authority_role"):
            return "recovery probe actor is not the declared recovery authority"
        if not 0 <= payload.get("confidence", -1) <= 1 or not payload.get("evidence"):
            return "recovery probe requires evidence and bounded confidence"
        if payload.get("result") not in {"pass", "fail"}:
            return "recovery probe result must be pass or fail"
        return None
    if cls == "artifact_revalidated":
        taint = state["taints"].get(payload.get("artifact"))
        if state["recorded_state"] != "RECOVERING" or not taint or taint.get("cleared"):
            return "revalidation requires an unresolved artifact taint in RECOVERING"
        if payload.get("session_id") != state.get("owner_session_id"):
            return "stale session cannot revalidate recovery artifacts"
        if event.get("actor") != payload.get("verified_by"):
            return "revalidation actor does not match verified_by"
        recovery = (_envelope(contract, state.get("envelope_id")) or {}).get("recovery") or {}
        if event.get("actor") != recovery.get("authority_role"):
            return "revalidation actor is not the declared recovery authority"
        required = set(taint.get("revalidation_scope") or [])
        if payload.get("result") == "pass" and not required <= set(payload.get("checks") or []):
            return f"passing revalidation omits required checks: {sorted(required - set(payload.get('checks') or []))}"
        if not payload.get("evidence") or not str(payload.get("verified_by") or "").strip():
            return "revalidation requires evidence and a verifier"
        if payload.get("result") not in {"pass", "fail"}:
            return "revalidation result must be pass or fail"
        return None
    if cls == "operational_escalated":
        circuit = state["circuits"].get(payload.get("circuit_id"))
        if not circuit or payload.get("failures") != circuit.get("retry_count") or \
                payload.get("retry_budget") != circuit.get("retry_budget") or \
                payload.get("failures") < payload.get("retry_budget"):
            return "escalation does not match an exhausted circuit budget"
        if payload.get("route_to") != (contract.get("operational_state") or {}).get(
                "repeated_failure_route") or not payload.get("evidence"):
            return "exhausted circuit must escalate with evidence to the declared route"
        return None
    return None


def _append(args, cls, payload, natural_key=None):
    command = [sys.executable, os.path.join(os.path.dirname(__file__), "ledger.py"), "append",
               args.root, "--actor", args.actor, "--class", cls,
               "--payload", json.dumps(payload, ensure_ascii=False)]
    if natural_key:
        command.extend(["--natural-key", natural_key])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    return completed.returncode, (completed.stderr or completed.stdout).strip()


def _emit(args, body, code=0):
    print(json.dumps(body, ensure_ascii=False, sort_keys=True,
                     indent=None if args.json else 2))
    return code


def _state(args, contract=None):
    contract = contract or load_contract(args.root, args.constitution)[0]
    return fold(read_events(args.root), args.now, contract)


def _current_activation(args, contract, events):
    adaptive = current_envelope(fold_adaptation(events, args.now), args.envelope)
    envelope = _envelope(contract, args.envelope)
    if not adaptive or adaptive.get("status") != "active" or not envelope:
        raise ValueError("operation requires the current active declared envelope")
    return envelope, adaptive


def _append_escalation_if_exhausted(args, circuit_payload):
    if circuit_payload["retry_count"] < circuit_payload["retry_budget"]:
        return None
    payload = {"circuit_id": circuit_payload["circuit_id"],
               "failures": circuit_payload["retry_count"],
               "retry_budget": circuit_payload["retry_budget"],
               "reason": "circuit retry budget exhausted",
               "evidence": circuit_payload["evidence"], "route_to": "human"}
    code, detail = _append(args, "operational_escalated", payload,
                           f"{payload['circuit_id']}:escalate:{payload['failures']}")
    if code:
        raise ValueError(f"could not record operational escalation: {detail}")
    return payload


def cmd_degrade(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    if args.by != args.actor:
        return _emit(args, {"error": "transitioned_by must match the ledger actor"}, 3)
    if violation := _bound_session_violation(args.session_id):
        return _emit(args, {"error": violation}, 3)
    events = read_events(args.root)
    envelope, activation = _current_activation(args, contract, events)
    state = fold(events, args.now, contract)
    existing = state["circuits"].get(args.circuit)
    if state["recorded_state"] == "DEGRADED" and \
            state.get("activation_id") == activation["activation_id"] and \
            state.get("circuit_id") == args.circuit:
        try:
            escalation = _append_escalation_if_exhausted(args, existing) if existing else None
        except ValueError as exc:
            return _emit(args, {"error": str(exc)}, 3)
        return _emit(args, {"ok": True, "idempotent": True, "escalation": escalation,
                            "state": state})
    if state["effective_state"] != "NORMAL":
        return _emit(args, {"error": f"cannot enter DEGRADED from {state['effective_state']}"}, 3)
    evidence = _evidence(args.evidence)
    now = _iso(args.now)
    recovery = envelope.get("recovery") or {}
    circuit_payload = existing or {
        "circuit_id": args.circuit, "dependency": args.dependency,
        "from_state": "CLOSED", "to_state": "OPEN", "reason": args.reason,
        "evidence": evidence, "confidence": args.confidence, "retry_count": 1,
        "retry_budget": envelope.get("retry_budget", 0),
        "cooldown_until": _fmt(now + dt.timedelta(seconds=recovery.get("cooldown_seconds", 0))),
        "session_id": args.session_id, "envelope_id": args.envelope,
        "activation_id": activation["activation_id"],
    }
    if existing:
        if existing.get("to_state") != "OPEN" or \
                existing.get("activation_id") != activation["activation_id"] or \
                existing.get("session_id") != args.session_id:
            return _emit(args, {"error": "existing circuit belongs to a foreign degradation"}, 3)
    else:
        code, detail = _append(args, "circuit_state_changed", circuit_payload,
                               f"{activation['activation_id']}:{args.circuit}:open:1")
        if code:
            return _emit(args, {"error": detail}, code)
    events = read_events(args.root)
    cause_seq = next(
        event["seq"] for event in reversed(events)
        if event.get("class") == "circuit_state_changed" and
        (event.get("payload") or {}).get("circuit_id") == args.circuit and
        (event.get("payload") or {}).get("activation_id") == activation["activation_id"])
    for artifact in args.artifact or []:
        taint = {"artifact": artifact, "cause_seq": cause_seq, "circuit_id": args.circuit,
                 "envelope_id": args.envelope, "activation_id": activation["activation_id"],
                 "reason": args.reason, "revalidation_scope": envelope["revalidation_scope"]}
        code, detail = _append(args, "artifact_tainted", taint,
                               f"{activation['activation_id']}:taint:{artifact}")
        if code:
            return _emit(args, {"error": detail}, code)
    transition = {
        "transition_id": "state-" + uuid.uuid4().hex[:12], "from_state": "NORMAL",
        "to_state": "DEGRADED", "circuit_id": args.circuit, "reason": args.reason,
        "evidence": evidence, "confidence": args.confidence, "session_id": args.session_id,
        "transitioned_by": args.by, "envelope_id": args.envelope,
        "activation_id": activation["activation_id"],
    }
    code, detail = _append(args, "operational_state_transitioned", transition,
                           transition["transition_id"])
    if code:
        return _emit(args, {"error": detail}, code)
    try:
        escalation = _append_escalation_if_exhausted(args, circuit_payload)
    except ValueError as exc:
        return _emit(args, {"error": str(exc)}, 3)
    return _emit(args, {"ok": True, "transition": transition, "circuit": circuit_payload,
                        "escalation": escalation, "state": _state(args, contract)})


def cmd_failure(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    if args.by != args.actor:
        return _emit(args, {"error": "failure observer must match the ledger actor"}, 3)
    if violation := _bound_session_violation(args.session_id):
        return _emit(args, {"error": violation}, 3)
    state = _state(args, contract)
    circuit = state["circuits"].get(args.circuit)
    envelope = _envelope(contract, state.get("envelope_id")) or {}
    if state["recorded_state"] != "DEGRADED" or not circuit or circuit.get("to_state") != "OPEN":
        return _emit(args, {"error": "repeated failure requires DEGRADED with an OPEN circuit"}, 3)
    if args.session_id != state.get("owner_session_id"):
        return _emit(args, {"error": "stale session cannot record repeated failure"}, 3)
    payload = {**{key: circuit.get(key) for key in (
                    "circuit_id", "dependency", "retry_budget",
                    "session_id", "envelope_id", "activation_id")},
               "from_state": "OPEN", "to_state": "OPEN", "reason": args.reason,
               "evidence": _evidence(args.evidence), "confidence": args.confidence,
               "retry_count": circuit.get("retry_count", 0) + 1,
               "cooldown_until": _fmt(_iso() + dt.timedelta(
                   seconds=(envelope.get("recovery") or {}).get("cooldown_seconds", 0)))}
    code, detail = _append(args, "circuit_state_changed", payload,
                           f"{payload['activation_id']}:{args.circuit}:open:{payload['retry_count']}")
    if code:
        return _emit(args, {"error": detail}, code)
    try:
        escalation = _append_escalation_if_exhausted(args, payload)
    except ValueError as exc:
        return _emit(args, {"error": str(exc)}, 3)
    return _emit(args, {"ok": True, "circuit": payload, "escalation": escalation,
                        "state": _state(args, contract)})


def cmd_begin_recovery(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    if args.by != args.actor:
        return _emit(args, {"error": "recovery authority must match the ledger actor"}, 3)
    if violation := _bound_session_violation(args.session_id):
        return _emit(args, {"error": violation}, 3)
    state = _state(args, contract)
    circuit = state["circuits"].get(args.circuit)
    envelope = _envelope(contract, state.get("envelope_id")) or {}
    if state["recorded_state"] != "DEGRADED" or not circuit or \
            circuit.get("to_state") not in {"OPEN", "HALF_OPEN"}:
        return _emit(args, {"error": "recovery requires DEGRADED with an OPEN/HALF_OPEN circuit"}, 3)
    if args.session_id != state.get("owner_session_id"):
        return _emit(args, {"error": "stale session cannot begin recovery"}, 3)
    if args.by != (envelope.get("recovery") or {}).get("authority_role"):
        return _emit(args, {"error": "actor is not the declared recovery authority"}, 3)
    if circuit.get("retry_count", 0) >= circuit.get("retry_budget", 0):
        return _emit(args, {"error": "circuit retry budget is exhausted; human handback is required"}, 3)
    if _iso(args.now) < _iso(circuit.get("cooldown_until")):
        return _emit(args, {"error": "circuit cooldown has not elapsed"}, 3)
    evidence = _evidence(args.evidence)
    half_open = {**{key: circuit.get(key) for key in (
                        "circuit_id", "dependency", "retry_count", "retry_budget",
                        "cooldown_until", "session_id", "envelope_id", "activation_id")},
                 "from_state": "OPEN", "to_state": "HALF_OPEN",
                 "reason": args.reason, "evidence": evidence, "confidence": args.confidence}
    if circuit.get("to_state") == "OPEN":
        code, detail = _append(args, "circuit_state_changed", half_open,
                               f"{state['activation_id']}:{args.circuit}:half-open:{circuit.get('retry_count', 0)}")
        if code:
            return _emit(args, {"error": detail}, code)
    probe = {"circuit_id": args.circuit, "activation_id": state["activation_id"],
             "result": args.result, "evidence": evidence, "confidence": args.confidence,
             "session_id": args.session_id}
    code, detail = _append(args, "recovery_probe_recorded", probe,
                           f"{state['activation_id']}:{args.circuit}:probe:"
                           f"{circuit.get('retry_count', 0)}:{args.result}")
    if code:
        return _emit(args, {"error": detail}, code)
    if args.result != "pass":
        reopened = {**half_open, "from_state": "HALF_OPEN", "to_state": "OPEN",
                    "retry_count": circuit.get("retry_count", 0) + 1,
                    "cooldown_until": _fmt(_iso() + dt.timedelta(
                        seconds=(envelope.get("recovery") or {}).get("cooldown_seconds", 0)))}
        code, detail = _append(args, "circuit_state_changed", reopened,
                               f"{state['activation_id']}:{args.circuit}:open:{reopened['retry_count']}")
        if code:
            return _emit(args, {"error": detail}, code)
        try:
            escalation = _append_escalation_if_exhausted(args, reopened)
        except ValueError as exc:
            return _emit(args, {"error": str(exc)}, 3)
        return _emit(args, {"ok": False, "probe": probe, "circuit": reopened,
                            "escalation": escalation, "state": _state(args, contract)}, 3)
    transition = {"transition_id": "state-" + uuid.uuid4().hex[:12],
                  "from_state": "DEGRADED", "to_state": "RECOVERING",
                  "circuit_id": args.circuit, "reason": args.reason, "evidence": evidence,
                  "confidence": args.confidence, "session_id": args.session_id,
                  "transitioned_by": args.by, "envelope_id": state["envelope_id"],
                  "activation_id": state["activation_id"]}
    code, detail = _append(args, "operational_state_transitioned", transition,
                           transition["transition_id"])
    return _emit(args, {"ok": code == 0, "transition": transition,
                        **({"error": detail} if code else {}),
                        "state": _state(args, contract)}, code)


def cmd_revalidate(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    if args.by != args.actor:
        return _emit(args, {"error": "verified_by must match the ledger actor"}, 3)
    if violation := _bound_session_violation(args.session_id):
        return _emit(args, {"error": violation}, 3)
    state = _state(args, contract)
    envelope = _envelope(contract, state.get("envelope_id")) or {}
    if args.by != (envelope.get("recovery") or {}).get("authority_role"):
        return _emit(args, {"error": "actor is not the declared recovery authority"}, 3)
    payload = {"artifact": args.artifact, "activation_id": state.get("activation_id"),
               "checks": args.check or [], "result": args.result,
               "evidence": _evidence(args.evidence), "verified_by": args.by,
               "session_id": args.session_id}
    code, detail = _append(args, "artifact_revalidated", payload,
                           f"{state.get('activation_id')}:revalidate:{args.artifact}:{args.result}")
    return _emit(args, {"ok": code == 0, "revalidation": payload,
                        **({"error": detail} if code else {}),
                        "state": _state(args, contract)}, code)


def cmd_recover(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    if args.by != args.actor:
        return _emit(args, {"error": "recovery authority must match the ledger actor"}, 3)
    if violation := _bound_session_violation(args.session_id):
        return _emit(args, {"error": violation}, 3)
    state = _state(args, contract)
    circuit = state["circuits"].get(args.circuit)
    envelope = _envelope(contract, state.get("envelope_id")) or {}
    if state["recorded_state"] != "RECOVERING" or not circuit or \
            circuit.get("to_state") not in {"HALF_OPEN", "CLOSED"}:
        return _emit(args, {"error": "completion requires RECOVERING with a HALF_OPEN/CLOSED circuit"}, 3)
    if args.session_id != state.get("owner_session_id"):
        return _emit(args, {"error": "stale session cannot complete recovery"}, 3)
    if args.by != (envelope.get("recovery") or {}).get("authority_role"):
        return _emit(args, {"error": "actor is not the declared recovery authority"}, 3)
    if state["unresolved_taints"]:
        return _emit(args, {"error": "recovery has unresolved taint",
                            "unresolved_taints": state["unresolved_taints"]}, 3)
    evidence = _evidence(args.evidence)
    revert = {"envelope_id": state["envelope_id"], "activation_id": state["activation_id"],
              "reason": args.reason, "evidence": evidence}
    adaptive = current_envelope(fold_adaptation(read_events(args.root), args.now),
                                state["envelope_id"])
    if adaptive and adaptive.get("status") in {"active", "expired"}:
        code, detail = _append(args, "adaptive_envelope_reverted", revert,
                               f"{state['activation_id']}:recovery-revert")
        if code:
            return _emit(args, {"error": detail}, code)
    closed = {**{key: circuit.get(key) for key in (
                    "circuit_id", "dependency", "retry_count", "retry_budget", "cooldown_until",
                    "session_id", "envelope_id", "activation_id")},
              "from_state": "HALF_OPEN", "to_state": "CLOSED", "reason": args.reason,
              "evidence": evidence, "confidence": args.confidence}
    if circuit.get("to_state") == "HALF_OPEN":
        code, detail = _append(args, "circuit_state_changed", closed,
                               f"{state['activation_id']}:{args.circuit}:closed")
        if code:
            return _emit(args, {"error": detail}, code)
    transition = {"transition_id": "state-" + uuid.uuid4().hex[:12],
                  "from_state": "RECOVERING", "to_state": "NORMAL",
                  "circuit_id": args.circuit, "reason": args.reason, "evidence": evidence,
                  "confidence": args.confidence, "session_id": args.session_id,
                  "transitioned_by": args.by, "envelope_id": state["envelope_id"],
                  "activation_id": state["activation_id"]}
    code, detail = _append(args, "operational_state_transitioned", transition,
                           transition["transition_id"])
    return _emit(args, {"ok": code == 0, "transition": transition,
                        **({"error": detail} if code else {}),
                        "state": _state(args, contract)}, code)


def cmd_status(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    return _emit(args, {"state": _state(args, contract), "resilience_score": None,
                        "human_judgment": ["acceptable outcome", "human-held HALT release",
                                           "permanent practice adoption"]})


def _projection(state, target):
    effective = state["effective_state"]
    canonical = {
        "schema": "orgforge.operational-state/v1",
        "recorded_state": state["recorded_state"],
        "effective_state": effective,
        "derived_reason": state.get("derived_reason"),
        "open_circuits": sorted(
            circuit_id for circuit_id, row in state["circuits"].items()
            if row.get("to_state") != "CLOSED"),
        "unresolved_taints": state["unresolved_taints"],
        "owner_session_id": state.get("owner_session_id"),
    }
    if target == "canonical":
        return canonical
    if target == "otel":
        return {
            "name": "orgforge.operational_state",
            "attributes": {
                "orgforge.operational_state.recorded": canonical["recorded_state"],
                "orgforge.operational_state.effective": effective,
                "orgforge.operational_state.open_circuit_count": len(canonical["open_circuits"]),
                "orgforge.operational_state.unresolved_taint_count": len(canonical["unresolved_taints"]),
                "orgforge.operational_state.requires_human": effective == "HALTED",
            },
            "body": canonical,
        }
    conclusion = {"NORMAL": "success", "DEGRADED": "neutral",
                  "RECOVERING": "neutral", "HALTED": "action_required"}[effective]
    return {
        "name": "OrgForge operational state",
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": f"OrgForge is {effective}",
            "summary": (f"recorded={canonical['recorded_state']}; "
                        f"open_circuits={len(canonical['open_circuits'])}; "
                        f"unresolved_taints={len(canonical['unresolved_taints'])}"),
        },
        "orgforge": canonical,
    }


def cmd_project(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    state = _state(args, contract)
    return _emit(args, _projection(state, args.target))


def cmd_authorize(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    decision = authorize(contract, read_events(args.root), args.action, args.envelope,
                         args.phase, args.artifact, args.now)
    return _emit(args, decision, 0 if decision["allowed"] else 3)


def cmd_doctor(args):
    try:
        contract, _, path = load_contract(args.root, args.constitution)
        operational = contract.get("operational_state") or {}
        ready = operational.get("initial") == "NORMAL" and set(operational.get("states") or []) == {
            "NORMAL", "DEGRADED", "HALTED", "RECOVERING"}
        errors = [] if ready else ["operational state contract is incomplete"]
    except Exception as exc:
        path, ready, errors = args.constitution or "(discovered)", False, [str(exc)]
    return _emit(args, {"ready": ready, "contract": str(path), "errors": errors,
                        "states": ["NORMAL", "DEGRADED", "HALTED", "RECOVERING"],
                        "existing_halt_compatible": True,
                        "projection_targets": ["canonical", "otel", "github-checks"],
                        "resilience_score": None},
                 0 if ready else 1)


def _common(parser):
    parser.add_argument("--root")
    parser.add_argument("--constitution")
    parser.add_argument("--actor", default=os.environ.get("ORG_ROLE", "supervisor"))
    parser.add_argument("--now")
    parser.add_argument("--json", action="store_true")
    return parser


def _evidenced(parser):
    parser.add_argument("--reason", required=True)
    parser.add_argument("--evidence", action="append", required=True)
    parser.add_argument("--confidence", type=float, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--by", required=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="operational-state")
    sub = parser.add_subparsers(dest="command", required=True)
    status = _common(sub.add_parser("status")); status.set_defaults(fn=cmd_status)
    doctor = _common(sub.add_parser("doctor")); doctor.set_defaults(fn=cmd_doctor)
    project = _common(sub.add_parser("project")); project.add_argument(
        "--target", choices=("canonical", "otel", "github-checks"), required=True)
    project.set_defaults(fn=cmd_project)
    auth = _common(sub.add_parser("authorize")); auth.add_argument("--action", required=True)
    auth.add_argument("--envelope"); auth.add_argument("--phase")
    auth.add_argument("--artifact", action="append"); auth.set_defaults(fn=cmd_authorize)
    degrade = _common(sub.add_parser("degrade")); _evidenced(degrade)
    degrade.add_argument("--envelope", required=True); degrade.add_argument("--circuit", required=True)
    degrade.add_argument("--dependency", required=True); degrade.add_argument("--artifact", action="append")
    degrade.set_defaults(fn=cmd_degrade)
    failure = _common(sub.add_parser("failure")); _evidenced(failure)
    failure.add_argument("--circuit", required=True); failure.set_defaults(fn=cmd_failure)
    begin = _common(sub.add_parser("begin-recovery")); _evidenced(begin)
    begin.add_argument("--circuit", required=True); begin.add_argument("--result", choices=("pass", "fail"), required=True)
    begin.set_defaults(fn=cmd_begin_recovery)
    revalidate = _common(sub.add_parser("revalidate")); revalidate.add_argument("--artifact", required=True)
    revalidate.add_argument("--check", action="append", required=True)
    revalidate.add_argument("--result", choices=("pass", "fail"), required=True)
    revalidate.add_argument("--evidence", action="append", required=True)
    revalidate.add_argument("--session-id", required=True); revalidate.add_argument("--by", required=True)
    revalidate.set_defaults(fn=cmd_revalidate)
    recover = _common(sub.add_parser("recover")); _evidenced(recover)
    recover.add_argument("--circuit", required=True); recover.set_defaults(fn=cmd_recover)
    args = parser.parse_args(argv)
    args.root = resolve_root(args.root)
    try:
        if args.command in {"degrade", "failure", "begin-recovery", "revalidate", "recover"} and \
                args.now is not None:
            raise ValueError("--now is read-only; mutation and cooldown use the writer clock")
        if hasattr(args, "confidence") and not 0 <= args.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return args.fn(args)
    except (ValueError, OSError) as exc:
        return _emit(args, {"error": str(exc)}, 2)


if __name__ == "__main__":
    raise SystemExit(main())
