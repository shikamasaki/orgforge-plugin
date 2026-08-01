#!/usr/bin/env python3
"""Portable, ledger-backed Goal lifecycle shared by Claude Code and Codex.

The ledger is normative.  A host-native Goal is a projection recorded with an explicit assurance;
this tool never claims that a closed host keeps executing.  SessionStart gives each host session a
compare-and-swap token, so a restarted session must resume before it can progress or finish a goal.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _organ import LedgerCorruption, read_events, resolve_root  # noqa: E402
from ledger import goal_states_from_events                    # noqa: E402


def _session(args):
    return str(args.session_id or os.environ.get("ORG_ORGAN_SESSION_ID") or
               os.environ.get("ORG_SESSION_ID") or "").strip()


def _harness(args):
    explicit = getattr(args, "harness", None)
    return str(explicit or os.environ.get("ORG_ORGAN_HARNESS") or "source").strip()


def _actor(args):
    return str(args.actor or os.environ.get("ORG_ROLE") or "system:org-goal").strip()


def _state(root, session_id=None):
    goals = goal_states_from_events(read_events(root))
    current = goals[-1] if goals else None
    if current:
        current = dict(current)
        current["resume_required"] = bool(
            current.get("status") != "complete" and session_id and
            current.get("session_id") != session_id)
    return current, goals


def _host_action(harness, action, goal):
    if harness != "codex" or not goal:
        return None
    if action in {"start", "resume"}:
        return {"action": "ensure_native_goal", "objective": goal.get("objective"),
                "after_success": "org-goal host-sync --state active --assurance observed"}
    if action == "complete":
        return {"action": "complete_native_goal",
                "after_success": "org-goal host-sync --state complete --assurance observed"}
    if action == "block":
        return {"action": "block_native_goal",
                "after_success": "org-goal host-sync --state blocked --assurance observed"}
    if action == "status":
        return {"action": "compare_native_goal"}
    return None


def _emit(args, payload, code=0):
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    elif code:
        print(payload.get("error") or payload, file=sys.stderr)
    else:
        goal = payload.get("goal")
        if not goal:
            print("NO GOAL")
        else:
            print(f"{goal['status'].upper()} {goal['goal_id']}: {goal['objective']}")
            if goal.get("resume_required"):
                print(f"RESUME REQUIRED: current session does not own this goal")
            progress = goal.get("progress") or {}
            if progress.get("next_step"):
                print(f"next: {progress['next_step']}")
            blocker = goal.get("blocker") or {}
            if blocker:
                print(f"blocker ({blocker.get('occurrences', 0)}/3): {blocker.get('reason')}")
        if payload.get("note"):
            print(payload["note"])
        if payload.get("host_action"):
            print("HOST ACTION " + json.dumps(payload["host_action"], ensure_ascii=False))
    return code


def _error(args, message, code=3):
    return _emit(args, {"ok": False, "error": message}, code)


def _append(args, cls, payload, natural_key=None):
    command = [sys.executable, str(HERE / "ledger.py"), "append", args.root,
               "--actor", _actor(args), "--class", cls,
               "--payload", json.dumps(payload, ensure_ascii=False)]
    if natural_key:
        command.extend(["--natural-key", natural_key])
    run = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if run.returncode:
        detail = (run.stderr or run.stdout or f"ledger append exited {run.returncode}").strip()
        if detail.startswith("append: "):
            detail = detail[len("append: "):]
        return run.returncode, detail
    return 0, (run.stdout or "").strip()


def _mutation_context(args):
    session_id = _session(args)
    if not session_id:
        return None, None, "no host session id; invoke through the SessionStart-bound stable launcher"
    try:
        current, goals = _state(args.root, session_id)
    except LedgerCorruption as exc:
        return None, None, f"ledger is corrupt: {exc}"
    return current, goals, None


def cmd_start(args):
    current, _, error = _mutation_context(args)
    if error:
        return _error(args, error, 12)
    if current and current.get("status") != "complete":
        return _error(args, f"unfinished goal {current['goal_id']} already exists ({current['status']})")
    objective = args.objective.strip()
    if not objective:
        return _error(args, "objective must be concrete and non-empty", 2)
    goal_id = args.goal_id or "goal-" + uuid.uuid4().hex[:12]
    payload = {"goal_id": goal_id, "objective": objective, "session_id": _session(args),
               "harness": _harness(args)}
    code, detail = _append(args, "goal_started", payload, natural_key=goal_id)
    if code:
        return _error(args, detail, code)
    goal, _ = _state(args.root, _session(args))
    return _emit(args, {"ok": True, "goal": goal,
                        "host_action": _host_action(_harness(args), "start", goal)})


def cmd_status(args):
    try:
        goal, goals = _state(args.root, _session(args))
    except LedgerCorruption as exc:
        return _error(args, f"ledger is corrupt: {exc}", 4)
    return _emit(args, {"ok": True, "goal": goal, "history_count": len(goals),
                        "host_action": _host_action(_harness(args), "status", goal),
                        "capability": {
                            "persistence": "ledger-backed",
                            "background_without_host": False,
                            "resume_trigger": "SessionStart",
                        }})


def _owned_active(args):
    goal, _, error = _mutation_context(args)
    if error:
        return None, error, 12
    if not goal:
        return None, "no goal has been started", 3
    if goal.get("status") == "complete":
        return None, f"goal {goal['goal_id']} is complete", 3
    if goal.get("session_id") != _session(args):
        return None, (f"session {_session(args)!r} does not own goal {goal['goal_id']}; "
                      "run org-goal resume first"), 3
    return goal, None, 0


def cmd_progress(args):
    goal, error, code = _owned_active(args)
    if error:
        return _error(args, error, code)
    payload = {"goal_id": goal["goal_id"], "session_id": _session(args),
               "summary": args.summary.strip(), "next_step": args.next_step.strip(),
               "evidence": args.evidence or []}
    code, detail = _append(args, "goal_progressed", payload)
    if code:
        return _error(args, detail, code)
    goal, _ = _state(args.root, _session(args))
    return _emit(args, {"ok": True, "goal": goal})


def cmd_pause(args):
    goal, error, code = _owned_active(args)
    if error:
        return _error(args, error, code)
    payload = {"goal_id": goal["goal_id"], "session_id": _session(args),
               "reason": args.reason.strip(), "next_step": args.next_step.strip()}
    code, detail = _append(args, "goal_paused", payload)
    if code:
        return _error(args, detail, code)
    goal, _ = _state(args.root, _session(args))
    return _emit(args, {"ok": True, "goal": goal})


def cmd_resume(args):
    goal, _, error = _mutation_context(args)
    if error:
        return _error(args, error, 12)
    if not goal:
        return _error(args, "no goal has been started")
    if goal.get("status") == "complete":
        return _error(args, f"goal {goal['goal_id']} is complete")
    payload = {"goal_id": goal["goal_id"], "from_session_id": goal.get("session_id"),
               "session_id": _session(args), "reason": args.reason.strip(),
               "harness": _harness(args)}
    code, detail = _append(args, "goal_resumed", payload,
                           natural_key=(f"{goal['goal_id']}:{goal.get('updated_seq')}:"
                                        f"{goal.get('session_id')}:{_session(args)}"))
    if code:
        return _error(args, detail, code)
    goal, _ = _state(args.root, _session(args))
    return _emit(args, {"ok": True, "goal": goal,
                        "host_action": _host_action(_harness(args), "resume", goal)})


def cmd_block(args):
    goal, error, code = _owned_active(args)
    if error:
        return _error(args, error, code)
    payload = {"goal_id": goal["goal_id"], "session_id": _session(args),
               "blocker": args.reason.strip(), "evidence": args.evidence}
    code, detail = _append(args, "goal_blocker_observed", payload)
    if code:
        return _error(args, detail, code)
    goal, _ = _state(args.root, _session(args))
    occurrences = (goal.get("blocker") or {}).get("occurrences", 0)
    host_action = None
    if occurrences >= 3:
        events = read_events(args.root)
        evidence = []
        for event in reversed(events):
            body = event.get("payload") or {}
            if event.get("class") == "goal_blocker_observed" and \
                    body.get("goal_id") == goal["goal_id"] and body.get("blocker") == args.reason:
                evidence.extend(body.get("evidence") or [])
            elif body.get("goal_id") == goal["goal_id"] and event.get("class") != "goal_host_synced":
                break
        blocked = {"goal_id": goal["goal_id"], "session_id": _session(args),
                   "blocker": args.reason.strip(), "occurrences": occurrences,
                   "evidence": list(reversed(evidence))}
        code, detail = _append(args, "goal_blocked", blocked,
                               natural_key=f"{goal['goal_id']}:{occurrences}:{args.reason}")
        if code:
            return _error(args, detail, code)
        goal, _ = _state(args.root, _session(args))
        host_action = _host_action(_harness(args), "block", goal)
    return _emit(args, {"ok": True, "goal": goal,
                        "blocker": {"reason": args.reason, "occurrences": occurrences},
                        "host_action": host_action})


def cmd_complete(args):
    goal, error, code = _owned_active(args)
    if error:
        return _error(args, error, code)
    payload = {"goal_id": goal["goal_id"], "session_id": _session(args),
               "summary": args.summary.strip(), "evidence": args.evidence}
    code, detail = _append(args, "goal_completed", payload, natural_key=goal["goal_id"])
    if code:
        return _error(args, detail, code)
    goal, _ = _state(args.root, _session(args))
    return _emit(args, {"ok": True, "goal": goal,
                        "host_action": _host_action(_harness(args), "complete", goal)})


def cmd_host_sync(args):
    goal, error, code = _owned_active(args)
    if error and args.state not in {"complete", "blocked"}:
        return _error(args, error, code)
    if not goal:
        goal, _ = _state(args.root, _session(args))
    if not goal:
        return _error(args, "no goal has been started")
    payload = {"goal_id": goal["goal_id"], "session_id": _session(args),
               "harness": _harness(args), "native_state": args.state,
               "assurance": args.assurance}
    if args.native_ref:
        payload["native_ref"] = args.native_ref
    if args.detail:
        payload["detail"] = args.detail
    code, detail = _append(args, "goal_host_synced", payload)
    if code:
        return _error(args, detail, code)
    goal, _ = _state(args.root, _session(args))
    return _emit(args, {"ok": True, "goal": goal})


def _schema_surface(path):
    try:
        import yaml
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return set(document.get("event_classes", {})), set(document.get("views", {})), None
    except Exception as exc:
        return set(), set(), str(exc)


def cmd_doctor(args):
    required = _GOAL_SCHEMA_CLASSES
    schema_path = os.environ.get("ORG_LEDGER_SCHEMA")
    if not schema_path:
        org_root = Path(args.root).resolve().parent.parent
        schema_path = str(org_root / "ledger-schema.yaml")
    classes, views, schema_error = _schema_surface(schema_path)
    source_root = HERE.parent
    is_source = (source_root / "integrations" / "claude-code").is_dir()
    if args.harness == "all":
        harnesses = ["claude-code", "codex"]
    elif args.harness == "auto":
        try:
            from organ_binding import installation_kind
            detected = os.environ.get("ORG_ORGAN_HARNESS") or installation_kind(str(HERE))
        except Exception:
            detected = os.environ.get("ORG_ORGAN_HARNESS") or "unknown"
        harnesses = ["claude-code", "codex"] if detected == "source" else [detected]
    else:
        harnesses = [args.harness]
    adapters = {
        "claude-code": {
            "native_goal": "unavailable (ledger is normative)",
            "resume_trigger": "SessionStart",
            "periodic_resume": "session-scoped /loop",
        },
        "codex": {
            "native_goal": "skill-mediated",
            "resume_trigger": "SessionStart + native Goal",
            "periodic_resume": "host Goal continuation",
        },
    }
    checks = {
        "schema": not schema_error and required <= classes and "goal_state" in views,
        "goal_tool": Path(__file__).is_file(),
        "session_start_resume": "_goal_resume_context" in (
            (source_root / "integrations" / "common" / "org_session_start.py").read_text(
                encoding="utf-8") if is_source else
            (source_root / "scripts" / "org_session_start.py").read_text(encoding="utf-8")),
    }
    for harness in harnesses:
        if harness == "claude-code":
            path = (source_root / "integrations" / "claude-code" / "commands" / "org-goal.md") \
                if is_source else source_root / "commands" / "org-goal.md"
            checks["claude_command"] = path.is_file()
        elif harness == "codex":
            path = (source_root / "integrations" / "codex" / "skills" / "org-goal" / "SKILL.md") \
                if is_source else source_root / "skills" / "org-goal" / "SKILL.md"
            checks["codex_skill"] = path.is_file()
        else:
            checks[f"known_harness:{harness}"] = False
    if not is_source:
        try:
            from organ_binding import load_binding
            binding = load_binding(ledger_root=args.root, harness=harnesses[0])
            checks["installed_binding"] = bool(
                binding and os.path.realpath(str(binding.get("tools_root") or "")) ==
                os.path.realpath(str(HERE)))
        except Exception:
            checks["installed_binding"] = False
    ready = all(checks.values())
    report = {
        "ok": ready, "ready": ready, "checks": checks,
        "schema_error": schema_error,
        "adapters": {name: adapters[name] for name in adapters},
        "guarantees": {
            "portable_ledger_state": True,
            "session_compare_and_swap": True,
            "background_without_host": False,
            "native_state_is_normative": False,
        },
    }
    return _emit(args, report, 0 if ready else 1)


_GOAL_SCHEMA_CLASSES = {
    "goal_started", "goal_progressed", "goal_paused", "goal_blocker_observed",
    "goal_blocked", "goal_resumed", "goal_completed", "goal_host_synced",
}


def _common(parser, *, mutating=True):
    parser.add_argument("--root")
    parser.add_argument("--actor")
    parser.add_argument("--session-id")
    parser.add_argument("--harness")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    parser = argparse.ArgumentParser(prog="org-goal")
    sub = parser.add_subparsers(dest="command", required=True)
    start = _common(sub.add_parser("start")); start.add_argument("objective")
    start.add_argument("--goal-id"); start.set_defaults(fn=cmd_start)
    status = _common(sub.add_parser("status"), mutating=False); status.set_defaults(fn=cmd_status)
    progress = _common(sub.add_parser("progress")); progress.add_argument("--summary", required=True)
    progress.add_argument("--next-step", required=True); progress.add_argument("--evidence", action="append")
    progress.set_defaults(fn=cmd_progress)
    pause = _common(sub.add_parser("pause")); pause.add_argument("--reason", required=True)
    pause.add_argument("--next-step", required=True); pause.set_defaults(fn=cmd_pause)
    resume = _common(sub.add_parser("resume")); resume.add_argument("--reason", required=True)
    resume.set_defaults(fn=cmd_resume)
    block = _common(sub.add_parser("block")); block.add_argument("--reason", required=True)
    block.add_argument("--evidence", action="append", required=True); block.set_defaults(fn=cmd_block)
    complete = _common(sub.add_parser("complete")); complete.add_argument("--summary", required=True)
    complete.add_argument("--evidence", action="append", required=True); complete.set_defaults(fn=cmd_complete)
    sync = _common(sub.add_parser("host-sync")); sync.add_argument(
        "--state", choices=("active", "complete", "blocked", "unavailable", "failed"), required=True)
    sync.add_argument("--native-ref"); sync.add_argument("--detail")
    sync.add_argument("--assurance", choices=("reported", "observed"), default="reported")
    sync.set_defaults(fn=cmd_host_sync)
    doctor = _common(sub.add_parser("doctor"), mutating=False)
    doctor.set_defaults(fn=cmd_doctor, harness="auto")
    args = parser.parse_args(argv)
    args.root = resolve_root(args.root)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
