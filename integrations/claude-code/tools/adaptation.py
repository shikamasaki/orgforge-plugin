#!/usr/bin/env python3
"""Bounded adaptation against the organization-owned resilience contract.

This is not a policy bypass.  It activates an expiring declared envelope, answers whether one
concrete action is inside it, records WAI/action/result/missingness, and derives taint/revalidation.
Safe stop and observation remain available when an envelope is absent or expired.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import read_events, resolve_root  # noqa: E402


EVENTS = {
    "adaptive_envelope_activated", "adaptive_deviation_recorded", "adaptive_envelope_expired",
    "adaptive_envelope_reverted", "adaptive_envelope_adopted", "acceptable_outcome_recorded",
    "microexperiment_concluded",
}


def _iso(value=None):
    if value:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def _fmt(value):
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _org_root(ledger_root):
    return os.path.realpath(os.path.join(resolve_root(ledger_root), "..", ".."))


def load_contract(ledger_root, constitution=None, required=True):
    path = Path(constitution or os.environ.get("ORG_CONSTITUTION") or
                os.path.join(_org_root(ledger_root), "constitution.yaml"))
    if not path.is_file() and not required:
        return None, None, path
    try:
        import yaml
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ValueError(f"cannot read resilience contract from {path}: {exc}") from exc
    contract = document.get("resilience")
    if not isinstance(contract, dict):
        raise ValueError(f"constitution has no resilience contract: {path}")
    return contract, document, path


def _by_id(rows):
    return {str(row.get("id")): row for row in (rows or []) if isinstance(row, dict) and row.get("id")}


def fold(events, now=None, contract=None):
    now = _iso(now)
    activations = {}
    outcomes = []
    experiments = []
    for event in events:
        cls = event.get("class")
        payload = event.get("payload") or {}
        if cls == "adaptive_envelope_activated":
            aid = str(payload.get("activation_id") or "")
            activations[aid] = {
                "activation_id": aid, "envelope_id": payload.get("envelope_id"),
                "version": payload.get("envelope_version"), "status": "active",
                "activation_seq": event.get("seq"), "expires_at": payload.get("expires_at"),
                "affected_critical_functions": payload.get("affected_critical_functions") or [],
                "deviations": [], "tainted_artifacts": [], "missing_evidence": [],
            }
        elif cls == "adaptive_deviation_recorded":
            state = activations.get(str(payload.get("activation_id") or ""))
            if state:
                state["deviations"].append({"seq": event.get("seq"), **payload})
                state["tainted_artifacts"] = sorted(set(state["tainted_artifacts"]) |
                                                       set(payload.get("tainted_artifacts") or []))
                state["missing_evidence"] = sorted(set(state["missing_evidence"]) |
                                                     set(payload.get("missing_evidence") or []))
        elif cls in {"adaptive_envelope_expired", "adaptive_envelope_reverted",
                     "adaptive_envelope_adopted"}:
            state = activations.get(str(payload.get("activation_id") or ""))
            if state:
                state["status"] = cls.rsplit("_", 1)[-1]
                state["terminal_seq"] = event.get("seq")
        elif cls == "acceptable_outcome_recorded":
            outcomes.append({"seq": event.get("seq"), **payload})
        elif cls == "microexperiment_concluded":
            experiments.append({"seq": event.get("seq"), **payload})
    for state in activations.values():
        try:
            if state["status"] == "active" and _iso(state["expires_at"]) <= now:
                state["status"] = "expired"
                state["expiry_derived"] = True
        except Exception:
            state["status"] = "expired"
            state["expiry_derived"] = True
    ordered = sorted(activations.values(), key=lambda row: row.get("activation_seq") or 0)
    if contract:
        activated_ids = {row["envelope_id"] for row in ordered}
        for envelope_id, envelope in _by_id(contract.get("adaptive_envelopes")).items():
            if envelope_id not in activated_ids:
                ordered.append({
                    "activation_id": None, "envelope_id": envelope_id,
                    "version": envelope.get("version"), "status": "proposed",
                    "affected_critical_functions": envelope.get("affected_critical_functions") or [],
                    "deviations": [], "tainted_artifacts": [], "missing_evidence": [],
                })
    return {"activations": ordered, "outcomes": outcomes, "microexperiments": experiments}


def _current(state, envelope_id):
    matches = [row for row in state["activations"] if row["envelope_id"] == envelope_id]
    return matches[-1] if matches else None


_POTENTIAL_EVIDENCE_CLASSES = {
    "Respond": ("adaptive_envelope_activated", "adaptive_deviation_recorded",
                "adaptive_envelope_reverted", "adaptive_envelope_expired",
                "halt_tripped", "halt_released"),
    "Monitor": ("scheduled_check_completed", "sensor_reading", "heartbeat",
                 "tick_planned", "dependency_stall_raised"),
    "Learn": ("outcome_delta", "repeated_death_detected", "microexperiment_concluded",
              "acceptable_outcome_recorded", "practice_change_proposed"),
    "Anticipate": ("preflight_completed", "dependency_declared", "risk_accepted",
                   "adaptive_envelope_activated", "exercise_completed"),
}


def evidence_profile(events):
    """Project observed event presence and missingness; never score resilience or claims."""
    counts = {}
    for event in events:
        cls = event.get("class")
        counts[cls] = counts.get(cls, 0) + 1
    profile = {}
    for potential, classes in _POTENTIAL_EVIDENCE_CLASSES.items():
        observed = [{"event_class": cls, "count": counts[cls]}
                    for cls in classes if counts.get(cls)]
        missing = [cls for cls in classes if not counts.get(cls)]
        profile[potential] = {
            "observed": observed,
            "missingness": missing,
            "confidence": "unknown",
            "interpretation": "observation-only; no capability or support verdict",
        }
    return profile


def outcome_indicators(events):
    """Return a non-scoring indicator surface with explicit not-observed values."""
    classes = {event.get("class") for event in events}
    return {
        name: {"value": None, "status": "observed" if source in classes else "not_observed",
               "confidence": "unknown"}
        for name, source in {
            "time_to_detect": "fault_observed",
            "time_to_contain": "adaptive_envelope_activated",
            "time_to_recover": "adaptive_envelope_reverted",
            "repeated_failure_rate": "repeated_death_detected",
            "evidence_reconstruction": "acceptable_outcome_recorded",
        }.items()
    }


def authorize(contract, events, envelope_id, action, phase=None, artifacts=None,
              missing_evidence=None, tainted_artifacts=None, now=None):
    action = str(action or "")
    safe = set(contract.get("safe_diagnostic_actions") or [])
    globally_forbidden = set(contract.get("globally_forbidden_actions") or [])
    if action in globally_forbidden:
        return {"allowed": False, "reason": "constitutional/global forbidden action"}
    if action in safe:
        return {"allowed": True, "mode": "safe-diagnostic", "reason": "diagnosis/stop path remains open",
                "envelope_id": envelope_id, "revalidation_scope": [],
                "affected_critical_functions": []}
    envelopes = _by_id(contract.get("adaptive_envelopes"))
    envelope = envelopes.get(str(envelope_id or ""))
    if not envelope:
        return {"allowed": False, "reason": "undeclared adaptive envelope"}
    current = _current(fold(events, now), envelope_id)
    if not current or current.get("status") != "active":
        return {"allowed": False, "reason": f"envelope is {current.get('status') if current else 'inactive'}"}
    allowed = set(envelope.get("allowed_actions") or [])
    forbidden = set(envelope.get("forbidden_actions") or [])
    if action not in allowed or action in forbidden:
        return {"allowed": False, "reason": "action is outside the declared envelope"}
    if missing_evidence and envelope.get("missing_evidence_policy") == "safe_only" and action not in safe:
        return {"allowed": False, "reason": "required evidence is missing; only safe diagnosis/stop remains"}
    scope = envelope.get("scope") or {}
    if phase not in set(scope.get("phases") or []):
        return {"allowed": False, "reason": f"phase {phase!r} is outside envelope scope"}
    patterns = scope.get("artifact_patterns") or []
    for artifact in list(artifacts or []) + list(tainted_artifacts or []):
        if not any(fnmatch.fnmatch(str(artifact), pattern) for pattern in patterns):
            return {"allowed": False, "reason": f"artifact {artifact!r} is outside envelope scope"}
    deviations = current.get("deviations") or []
    maximum = (envelope.get("blast_radius") or {}).get("max_deviations", 0)
    if len(deviations) >= maximum:
        return {"allowed": False, "reason": "blast-radius deviation budget exhausted"}
    taint = set(current.get("tainted_artifacts") or []) | set(tainted_artifacts or [])
    max_taint = (envelope.get("blast_radius") or {}).get("max_tainted_artifacts", 0)
    if len(taint) > max_taint:
        return {"allowed": False, "reason": "tainted-artifact blast radius exceeded"}
    retry_actions = {"cross_harness_failover", "retry"}
    retries = sum(1 for row in deviations if row.get("action") in retry_actions)
    if action in retry_actions and retries >= envelope.get("retry_budget", 0):
        return {"allowed": False, "reason": "retry/failover budget exhausted"}
    return {
        "allowed": True, "mode": "adaptive-envelope", "activation_id": current["activation_id"],
        "reason": "inside declared envelope", "revalidation_scope": envelope["revalidation_scope"],
        "affected_critical_functions": envelope["affected_critical_functions"],
        "preserves_invariants": envelope["preserves_invariants"],
    }


def ledger_event_violation(event, history, ledger_root):
    """Writer-side enforcement so generic append cannot bypass the adaptation tool."""
    cls = event.get("class")
    if cls not in EVENTS:
        return None
    payload = event.get("payload") or {}
    try:
        contract, _, _ = load_contract(ledger_root)
    except ValueError as exc:
        return str(exc)
    envelopes = _by_id(contract.get("adaptive_envelopes"))
    if cls == "adaptive_envelope_activated":
        envelope = envelopes.get(str(payload.get("envelope_id") or ""))
        if not envelope:
            return "adaptive envelope is undeclared"
        if payload.get("envelope_version") != envelope.get("version") or \
                payload.get("trigger") != (envelope.get("trigger") or {}).get("kind"):
            return "activation version/trigger does not match the constitution"
        if payload.get("source") not in set((envelope.get("trigger") or {}).get("evidence_sources") or []):
            return "activation observation source is not declared for this envelope"
        if payload.get("affected_critical_functions") != envelope.get("affected_critical_functions"):
            return "activation critical functions do not match the constitution"
        if not str(payload.get("baseline_ref") or "").strip():
            return "activation requires a non-empty WAI baseline reference"
        if not all(str(ref or "").strip() for ref in (payload.get("evidence") or {}).values()):
            return "activation evidence references must be non-empty"
        required = set(envelope.get("required_evidence") or [])
        if not required <= set((payload.get("evidence") or {}).keys()):
            return f"activation evidence missing: {sorted(required - set((payload.get('evidence') or {}).keys()))}"
        confidence = payload.get("confidence", -1)
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1 or \
                confidence < (envelope.get("trigger") or {}).get("minimum_confidence", 1):
            return "activation observation confidence is below the declared minimum"
        try:
            event_time = _iso(event.get("ts"))
            expiry = _iso(payload.get("expires_at"))
            lifetime = (expiry - event_time).total_seconds()
            declared = envelope.get("expires_after_minutes", 0) * 60
            if lifetime <= 0 or lifetime > declared + 5:
                return "activation expiry exceeds the declared envelope lifetime"
        except Exception:
            return "activation expiry is invalid"
        current = _current(fold(history, event.get("ts")), payload.get("envelope_id"))
        if current and current.get("status") == "active":
            return "an activation for this envelope is already active"
        return None
    if cls == "adaptive_deviation_recorded":
        decision = authorize(contract, history, payload.get("envelope_id"), payload.get("action"),
                             payload.get("phase"), payload.get("artifacts"),
                             payload.get("missing_evidence"), payload.get("tainted_artifacts"),
                             event.get("ts"))
        if not decision["allowed"]:
            return decision["reason"]
        if decision.get("activation_id") != payload.get("activation_id"):
            return "deviation activation_id is stale or foreign"
        if payload.get("revalidation_scope") != decision.get("revalidation_scope"):
            return "deviation revalidation_scope does not match the constitution"
        for field in ("wai_baseline", "reason", "result"):
            if not str(payload.get(field) or "").strip():
                return f"deviation {field} must be non-empty"
        return None
    if cls in {"adaptive_envelope_expired", "adaptive_envelope_reverted",
               "adaptive_envelope_adopted"}:
        current = _current(fold(history, event.get("ts")), payload.get("envelope_id"))
        if not current or current.get("activation_id") != payload.get("activation_id"):
            return "terminal envelope event does not identify the current activation"
        if cls == "adaptive_envelope_reverted" and current.get("status") not in {"active", "expired"}:
            return f"cannot revert envelope in state {current.get('status')}"
        if cls == "adaptive_envelope_reverted" and (not str(payload.get("reason") or "").strip() or
                                                     not all(str(ref or "").strip()
                                                             for ref in payload.get("evidence") or [])):
            return "revert requires a reason and non-empty evidence references"
        if cls == "adaptive_envelope_expired" and current.get("status") != "expired":
            return "cannot record expiry before the declared expiry time"
        if cls == "adaptive_envelope_expired" and not str(payload.get("reason") or "").strip():
            return "expiry requires a reason"
        if cls == "adaptive_envelope_adopted":
            if current.get("status") not in {"reverted", "expired"}:
                return "temporary adaptation must be reverted or expired before permanent adoption"
            envelope = envelopes.get(str(payload.get("envelope_id") or "")) or {}
            if payload.get("human_decision_ref") != (envelope.get("adoption") or {}).get("human_decision"):
                return "human decision reference does not match the constitution"
            if not str(payload.get("practice_change_ref") or "").strip():
                return "permanent adoption requires the exact proposed practice change reference"
            experiment = str(payload.get("microexperiment_ref") or "")
            if not any(str(row.get("seq")) == experiment.removeprefix("ledger:") and
                       row.get("envelope_id") == payload.get("envelope_id")
                       for row in fold(history)["microexperiments"]):
                return "permanent adoption requires a concluded microexperiment ledger reference"
            if payload.get("identity_assurance") not in {"attested", "authenticated"} or \
                    not str(payload.get("decision_by") or "").startswith("human:"):
                return "permanent adoption requires an attested human-held decision"
        return None
    if cls == "acceptable_outcome_recorded":
        critical = _by_id(contract.get("critical_functions")).get(str(payload.get("critical_function") or ""))
        if not critical or payload.get("outcome") not in set(critical.get("acceptable_outcomes") or []):
            return "outcome is not acceptable for the declared critical function"
        if not str(payload.get("judged_by") or "").strip():
            return "acceptable outcome requires an explicit judgment subject"
        if payload.get("envelope_id"):
            current = _current(fold(history, event.get("ts")), payload.get("envelope_id"))
            if not current or current.get("activation_id") != payload.get("activation_id"):
                return "acceptable outcome references no current envelope activation"
        if not payload.get("evidence") or not all(str(ref or "").strip()
                                                  for ref in payload.get("evidence") or []):
            return "acceptable outcome requires evidence"
    if cls == "microexperiment_concluded":
        if str(payload.get("envelope_id") or "") not in envelopes:
            return "microexperiment references an undeclared envelope"
        if not payload.get("evidence") or not all(str(ref or "").strip()
                                                  for ref in payload.get("evidence") or []) or \
                not str(payload.get("hypothesis") or "").strip() or \
                not str(payload.get("result") or "").strip() or \
                not str(payload.get("judged_by") or "").strip():
            return "microexperiment requires a hypothesis, result, and evidence"
    return None


def _append(args, cls, payload, natural_key=None, receipt=None):
    command = [sys.executable, os.path.join(os.path.dirname(__file__), "ledger.py"), "append",
               args.root, "--actor", args.actor, "--class", cls,
               "--payload", json.dumps(payload, ensure_ascii=False)]
    if natural_key:
        command.extend(["--natural-key", natural_key])
    if receipt:
        command.extend(["--receipt", receipt])
    run = subprocess.run(command, capture_output=True, text=True, timeout=30)
    return run.returncode, (run.stderr or run.stdout).strip()


def _emit(args, body, code=0):
    if args.json:
        print(json.dumps(body, ensure_ascii=False, sort_keys=True))
    elif code:
        print(body.get("error", body), file=sys.stderr)
    else:
        print(json.dumps(body, ensure_ascii=False, indent=2))
    return code


def _evidence(values):
    out = {}
    for item in values or []:
        if "=" not in item:
            raise ValueError(f"evidence must be kind=ref: {item!r}")
        kind, ref = item.split("=", 1)
        if not kind or not ref or kind in out:
            raise ValueError(f"evidence must have a unique non-empty kind and ref: {item!r}")
        out[kind] = ref
    return out


def cmd_doctor(args):
    events = []
    try:
        events = read_events(args.root)
        contract, document, path = load_contract(args.root, args.constitution)
        from org_lint import Lint, lint_resilience
        lint = Lint()
        inv = document.get("invariants") or []
        present = {}
        for item in inv if isinstance(inv, list) else [inv]:
            if isinstance(item, dict):
                present.update(item)
        charter = (document.get("charter") or {}).get("items") or []
        held = (document.get("irreversible") or {}).get("held_actions") or []
        lint_resilience(document, present, charter, held, lint)
        errors = lint.errs
    except Exception as exc:
        contract, path, errors = {}, args.constitution or "(discovered)", [str(exc)]
    report = {"ready": not errors, "contract": str(path), "schema_version": contract.get("schema_version"),
              "critical_functions": sorted(_by_id(contract.get("critical_functions"))),
              "adaptive_envelopes": sorted(_by_id(contract.get("adaptive_envelopes"))),
              "errors": errors, "resilience_score": None,
              "evidence_profile": evidence_profile(events),
              "outcome_indicators": outcome_indicators(events),
              "work_observation_model": {
                  "work_as_imagined": ["constitution", "workflow", "doctrine"],
                  "work_as_recorded": ["ledger", "git", "ci", "trace"],
                  "work_as_reported": ["agent report", "human report"],
                  "inferred_work_as_done": "triangulation with explicit missingness/confidence",
              },
              "human_judgment_remains": ["acceptable outcome", "inferred work-as-done",
                                           "permanent practice adoption"]}
    return _emit(args, report, 0 if not errors else 1)


def cmd_status(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    state = fold(read_events(args.root), args.now, contract)
    declared = _by_id(contract.get("adaptive_envelopes"))
    for row in state["activations"]:
        envelope = declared.get(row["envelope_id"], {})
        row["forbidden_actions"] = envelope.get("forbidden_actions") or []
        row["revalidation_scope"] = envelope.get("revalidation_scope") or []
    return _emit(args, {"state": state, "resilience_score": None,
                        "safe_diagnostic_actions": contract.get("safe_diagnostic_actions")})


def cmd_activate(args):
    try:
        contract, _, _ = load_contract(args.root, args.constitution)
        envelope = _by_id(contract.get("adaptive_envelopes")).get(args.envelope)
        evidence = _evidence(args.evidence)
    except ValueError as exc:
        return _emit(args, {"error": str(exc)}, 2)
    if not envelope:
        return _emit(args, {"error": "undeclared adaptive envelope"}, 3)
    trigger = envelope.get("trigger") or {}
    if args.trigger != trigger.get("kind") or args.source not in set(trigger.get("evidence_sources") or []):
        return _emit(args, {"error": "trigger/source is not declared for this envelope"}, 3)
    required = set(envelope.get("required_evidence") or [])
    if not required <= set(evidence) or not 0 <= args.confidence <= 1 or \
            args.confidence < trigger.get("minimum_confidence", 1):
        return _emit(args, {"error": "required evidence or observation confidence is insufficient"}, 3)
    now = _iso(args.now)
    activation_id = "adapt-" + uuid.uuid4().hex[:12]
    payload = {"envelope_id": args.envelope, "envelope_version": envelope["version"],
               "trigger": args.trigger, "source": args.source, "activation_id": activation_id,
               "baseline_ref": args.baseline_ref, "evidence": evidence,
               "confidence": args.confidence,
               "expires_at": _fmt(now + dt.timedelta(minutes=envelope["expires_after_minutes"])),
               "affected_critical_functions": envelope["affected_critical_functions"]}
    code, detail = _append(args, "adaptive_envelope_activated", payload,
                           natural_key=activation_id)
    return _emit(args, {"ok": code == 0, "activation": payload,
                        **({"error": detail} if code else {})}, code)


def cmd_authorize(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    decision = authorize(contract, read_events(args.root), args.envelope, args.action, args.phase,
                         args.artifact, args.missing_evidence, args.tainted_artifact, args.now)
    return _emit(args, decision, 0 if decision["allowed"] else 3)


def cmd_deviate(args):
    contract, _, _ = load_contract(args.root, args.constitution)
    events = read_events(args.root)
    decision = authorize(contract, events, args.envelope, args.action, args.phase, args.artifact,
                         args.missing_evidence, args.tainted_artifact, args.now)
    if not decision["allowed"] or decision.get("mode") != "adaptive-envelope":
        return _emit(args, {"error": decision["reason"], "authorization": decision}, 3)
    payload = {"envelope_id": args.envelope, "activation_id": decision["activation_id"],
               "action": args.action, "phase": args.phase, "artifacts": args.artifact or [],
               "wai_baseline": args.wai_baseline, "reason": args.reason, "result": args.result,
               "missing_evidence": args.missing_evidence or [],
               "tainted_artifacts": args.tainted_artifact or [],
               "revalidation_scope": decision["revalidation_scope"]}
    code, detail = _append(args, "adaptive_deviation_recorded", payload)
    return _emit(args, {"ok": code == 0, "deviation": payload,
                        **({"error": detail} if code else {})}, code)


def cmd_revert(args):
    state = fold(read_events(args.root), args.now)
    current = _current(state, args.envelope)
    if not current:
        return _emit(args, {"error": "no activation to revert"}, 3)
    payload = {"envelope_id": args.envelope, "activation_id": current["activation_id"],
               "reason": args.reason, "evidence": args.evidence}
    code, detail = _append(args, "adaptive_envelope_reverted", payload)
    return _emit(args, {"ok": code == 0, "revert": payload,
                        **({"error": detail} if code else {})}, code)


def cmd_expire(args):
    state = fold(read_events(args.root), args.now)
    current = _current(state, args.envelope)
    if not current:
        return _emit(args, {"error": "no activation to expire"}, 3)
    payload = {"envelope_id": args.envelope, "activation_id": current["activation_id"],
               "reason": args.reason}
    code, detail = _append(args, "adaptive_envelope_expired", payload)
    return _emit(args, {"ok": code == 0, "expiry": payload,
                        **({"error": detail} if code else {})}, code)


def cmd_outcome(args):
    payload = {"critical_function": args.critical_function, "outcome": args.outcome,
               "evidence": args.evidence, "judged_by": args.judged_by,
               "judgment_required": args.judgment_required}
    if args.envelope:
        state = _current(fold(read_events(args.root), args.now), args.envelope)
        payload.update({"envelope_id": args.envelope,
                        "activation_id": state.get("activation_id") if state else None})
    code, detail = _append(args, "acceptable_outcome_recorded", payload)
    return _emit(args, {"ok": code == 0, "outcome": payload,
                        **({"error": detail} if code else {})}, code)


def cmd_experiment(args):
    payload = {"experiment_id": args.experiment_id or "experiment-" + uuid.uuid4().hex[:12],
               "envelope_id": args.envelope, "hypothesis": args.hypothesis,
               "result": args.result, "evidence": args.evidence,
               "judged_by": args.judged_by}
    code, detail = _append(args, "microexperiment_concluded", payload,
                           natural_key=payload["experiment_id"])
    return _emit(args, {"ok": code == 0, "microexperiment": payload,
                        **({"error": detail} if code else {})}, code)


def cmd_adopt(args):
    current = _current(fold(read_events(args.root), args.now), args.envelope)
    if not current:
        return _emit(args, {"error": "no activation to adopt"}, 3)
    payload = {"envelope_id": args.envelope, "activation_id": current["activation_id"],
               "human_decision_ref": args.human_decision_ref,
               "microexperiment_ref": args.microexperiment_ref,
               "practice_change_ref": args.practice_change_ref}
    code, detail = _append(args, "adaptive_envelope_adopted", payload,
                           natural_key=f"{current['activation_id']}:adopt", receipt=args.receipt)
    return _emit(args, {"ok": code == 0, "adoption": payload,
                        **({"error": detail} if code else {})}, code)


def _common(parser):
    parser.add_argument("--root")
    parser.add_argument("--constitution")
    parser.add_argument("--actor", default=os.environ.get("ORG_ROLE", "supervisor"))
    parser.add_argument("--now")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    parser = argparse.ArgumentParser(prog="adaptation")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = _common(sub.add_parser("doctor")); doctor.set_defaults(fn=cmd_doctor)
    status = _common(sub.add_parser("status")); status.set_defaults(fn=cmd_status)
    activate = _common(sub.add_parser("activate")); activate.add_argument("--envelope", required=True)
    activate.add_argument("--trigger", required=True); activate.add_argument("--source", required=True)
    activate.add_argument("--baseline-ref", required=True); activate.add_argument("--evidence", action="append", required=True)
    activate.add_argument("--confidence", type=float, required=True); activate.set_defaults(fn=cmd_activate)
    authorize_p = _common(sub.add_parser("authorize")); authorize_p.add_argument("--envelope")
    authorize_p.add_argument("--action", required=True); authorize_p.add_argument("--phase")
    authorize_p.add_argument("--artifact", action="append"); authorize_p.add_argument("--missing-evidence", action="append")
    authorize_p.add_argument("--tainted-artifact", action="append"); authorize_p.set_defaults(fn=cmd_authorize)
    deviate = _common(sub.add_parser("deviate")); deviate.add_argument("--envelope", required=True)
    deviate.add_argument("--action", required=True); deviate.add_argument("--phase", required=True)
    deviate.add_argument("--artifact", action="append"); deviate.add_argument("--wai-baseline", required=True)
    deviate.add_argument("--reason", required=True); deviate.add_argument("--result", required=True)
    deviate.add_argument("--missing-evidence", action="append"); deviate.add_argument("--tainted-artifact", action="append")
    deviate.set_defaults(fn=cmd_deviate)
    revert = _common(sub.add_parser("revert")); revert.add_argument("--envelope", required=True)
    revert.add_argument("--reason", required=True); revert.add_argument("--evidence", action="append", required=True)
    revert.set_defaults(fn=cmd_revert)
    expire = _common(sub.add_parser("expire")); expire.add_argument("--envelope", required=True)
    expire.add_argument("--reason", required=True); expire.set_defaults(fn=cmd_expire)
    outcome = _common(sub.add_parser("outcome")); outcome.add_argument("--critical-function", required=True)
    outcome.add_argument("--outcome", required=True); outcome.add_argument("--evidence", action="append", required=True)
    outcome.add_argument("--judged-by", required=True); outcome.add_argument("--judgment-required", action="store_true")
    outcome.add_argument("--envelope"); outcome.set_defaults(fn=cmd_outcome)
    experiment = _common(sub.add_parser("experiment")); experiment.add_argument("--envelope", required=True)
    experiment.add_argument("--experiment-id"); experiment.add_argument("--hypothesis", required=True)
    experiment.add_argument("--result", required=True); experiment.add_argument("--evidence", action="append", required=True)
    experiment.add_argument("--judged-by", required=True); experiment.set_defaults(fn=cmd_experiment)
    adopt = _common(sub.add_parser("adopt")); adopt.add_argument("--envelope", required=True)
    adopt.add_argument("--human-decision-ref", required=True); adopt.add_argument("--microexperiment-ref", required=True)
    adopt.add_argument("--practice-change-ref", required=True)
    adopt.add_argument("--receipt", required=True); adopt.set_defaults(fn=cmd_adopt)
    args = parser.parse_args(argv)
    args.root = resolve_root(args.root)
    try:
        return args.fn(args)
    except (ValueError, OSError) as exc:
        return _emit(args, {"error": str(exc)}, 2)


if __name__ == "__main__":
    raise SystemExit(main())
