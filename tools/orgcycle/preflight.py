"""Organization-declared, bounded environment probes for judge dispatch.

The probes report what their command measured.  They deliberately do not infer a runtime
implementation (for example, a process named ``docker``) from that result.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
import re
import subprocess
import sys
import time


MAX_TIMEOUT_SECONDS = 3600.0
MAX_CAPTURE_CHARS = 8000


class PreflightConfigError(ValueError):
    """The organization declared an ambiguous or unbounded probe."""


@dataclass(frozen=True)
class Probe:
    probe_id: str
    command: tuple[str, ...]
    timeout_seconds: float


@dataclass(frozen=True)
class ProbeResult:
    probe: Probe
    ok: bool
    elapsed_ms: int
    returncode: int | None
    timed_out: bool
    stdout: str
    stderr: str


def _constitution_path():
    try:
        from discover import constitution
        return constitution()
    except Exception as exc:
        raise PreflightConfigError(f"constitution の場所を解決できない: {exc}") from exc


def _as_selector(value, field, probe_id):
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise PreflightConfigError(
            f"preflight {probe_id!r} の applies_to.{field} は空でない list が必要")
    return {str(item) for item in value}


def _matches_scope(raw, issue, role, phase, probe_id):
    scope = raw.get("applies_to") or {}
    if not isinstance(scope, dict):
        raise PreflightConfigError(
            f"preflight {probe_id!r} の applies_to は map が必要")
    unknown = sorted(set(scope) - {"issues", "roles", "phases"})
    if unknown:
        raise PreflightConfigError(
            f"preflight {probe_id!r} の applies_to に未知の selector: {', '.join(unknown)}")
    selectors = {
        "issues": _as_selector(scope.get("issues"), "issues", probe_id),
        "roles": _as_selector(scope.get("roles"), "roles", probe_id),
        "phases": _as_selector(scope.get("phases"), "phases", probe_id),
    }
    actual = {"issues": str(issue), "roles": role, "phases": phase}
    return all(wanted is None or actual[name] in wanted or "*" in wanted
               for name, wanted in selectors.items())


def parse_probes(declared, issue, role, phase):
    """Validate every declaration and return only the probes matching this scope."""
    if not isinstance(declared, list):
        raise PreflightConfigError("enforcement.judges.preflights は list が必要")

    probes = []
    seen = set()
    for index, raw in enumerate(declared, 1):
        if not isinstance(raw, dict):
            raise PreflightConfigError(f"preflight #{index} は map が必要")
        unknown = sorted(set(raw) - {
            "id", "description", "enabled", "command", "timeout_seconds", "applies_to"})
        if unknown:
            raise PreflightConfigError(
                f"preflight #{index} に未知の field: {', '.join(unknown)}")
        probe_id = str(raw.get("id") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", probe_id):
            raise PreflightConfigError(
                f"preflight #{index} の id は英数字で始まる80文字以内の識別子が必要")
        if probe_id in seen:
            raise PreflightConfigError(f"preflight id {probe_id!r} が重複している")
        seen.add(probe_id)
        if "enabled" in raw and not isinstance(raw["enabled"], bool):
            raise PreflightConfigError(f"preflight {probe_id!r} の enabled は boolean が必要")
        if raw.get("enabled", True) is False:
            continue
        command = raw.get("command")
        if (not isinstance(command, list) or not command
                or any(not isinstance(arg, str) or not arg for arg in command)):
            raise PreflightConfigError(
                f"preflight {probe_id!r} の command は空でない argv list が必要（shell文字列は不可）")
        timeout = raw.get("timeout_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise PreflightConfigError(
                f"preflight {probe_id!r} に数値 timeout_seconds の明示が必要")
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
            raise PreflightConfigError(
                f"preflight {probe_id!r} の timeout_seconds は 0 より大きく "
                f"{int(MAX_TIMEOUT_SECONDS)} 以下が必要（実値: {timeout:g}）")
        if not _matches_scope(raw, issue, role, phase, probe_id):
            continue
        probes.append(Probe(probe_id, tuple(command), timeout))
    return probes


def declared_preflights(document):
    """Read the declaration while rejecting malformed parent containers."""
    enforcement = document.get("enforcement") or {}
    if not isinstance(enforcement, dict):
        raise PreflightConfigError("enforcement は map が必要")
    judges = enforcement.get("judges") or {}
    if not isinstance(judges, dict):
        raise PreflightConfigError("enforcement.judges は map が必要")
    return judges.get("preflights") or []


def load_probes(issue, role, phase):
    """Load only probes whose explicit scope matches this verification."""
    path = _constitution_path()
    if not path or not os.path.isfile(path):
        return []
    try:
        import yaml
    except Exception as exc:
        raise PreflightConfigError(
            "PyYAML が無いので constitution の preflight 宣言を読めない") from exc
    try:
        with open(path, encoding="utf-8") as handle:
            document = yaml.safe_load(handle) or {}
    except Exception as exc:
        raise PreflightConfigError(
            f"constitution.yaml を解析できない: {exc}（{path}）") from exc
    if not isinstance(document, dict):
        raise PreflightConfigError(f"constitution.yaml が map ではない: {path}")
    return parse_probes(declared_preflights(document), issue, role, phase)


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_probe(probe, *, issue, role, phase, cwd=None):
    env = dict(os.environ)
    env.update({
        "ORG_PREFLIGHT_ISSUE": str(issue),
        "ORG_PREFLIGHT_ROLE": role,
        "ORG_PREFLIGHT_PHASE": phase,
        "ORG_PREFLIGHT_ROOT": os.path.abspath(cwd or os.getcwd()),
    })
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(probe.command), cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=probe.timeout_seconds)
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return ProbeResult(probe, completed.returncode == 0, elapsed_ms,
                           completed.returncode, False,
                           completed.stdout or "", completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return ProbeResult(probe, False, elapsed_ms, None, True,
                           _text(exc.stdout), _text(exc.stderr))
    except OSError as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return ProbeResult(probe, False, elapsed_ms, None, False, "", str(exc))


def _capture(value):
    if len(value) <= MAX_CAPTURE_CHARS:
        return value
    omitted = len(value) - MAX_CAPTURE_CHARS
    return value[:MAX_CAPTURE_CHARS] + f"\n...[{omitted} chars truncated]"


def result_evidence(result):
    """Stable, machine-readable evidence suitable for stderr and a judge prompt."""
    status = "timeout" if result.timed_out else ("pass" if result.ok else "fail")
    payload = {
        "id": result.probe.probe_id,
        "status": status,
        "command": list(result.probe.command),
        "timeout_seconds": result.probe.timeout_seconds,
        "elapsed_ms": result.elapsed_ms,
        "exit_code": result.returncode,
        "stdout": _capture(result.stdout),
        "stderr": _capture(result.stderr),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def run_declared_preflights(issue, role, phase, cwd=None):
    """Run matching probes sequentially and stop at the first non-pass."""
    probes = load_probes(issue, role, phase)
    evidence = []
    for probe in probes:
        result = run_probe(probe, issue=issue, role=role, phase=phase, cwd=cwd)
        rendered = result_evidence(result)
        evidence.append(rendered)
        print(f"[preflight] {rendered}", file=sys.stderr)
        if not result.ok:
            return False, evidence
    return True, evidence
