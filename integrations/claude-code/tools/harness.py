#!/usr/bin/env python3
"""Resolve the running host harness and the honest reviewer-diversity mode.

The active host is a runtime fact, not an organization.yaml preference.  Adaptive mode uses the
opposite product when it is locally available; otherwise it degrades explicitly to same-harness
role separation so a user with one subscription can still operate the organization.
"""
import os
import shutil
import subprocess
import sys


_HARNESS_NAMES = ("claude", "codex")


def active_harness(env=None):
    env = os.environ if env is None else env
    override = str(env.get("ORGFORGE_ACTIVE_HARNESS") or "").strip()
    if override:
        if override not in _HARNESS_NAMES:
            raise SystemExit("ORGFORGE_ACTIVE_HARNESS は claude | codex のどちらか。")
        return override

    signals = []
    if env.get("CLAUDECODE"):
        signals.append("claude")
    if env.get("CODEX_THREAD_ID") or env.get("CODEX_CI"):
        signals.append("codex")
    signals = sorted(set(signals))
    if len(signals) == 1:
        return signals[0]
    if not signals:
        raise SystemExit("実行中のハーネスを判定できない。Claude Code / Codex のセッション内で"
                         "実行するか、ORGFORGE_ACTIVE_HARNESS=claude|codex を指定すること。")
    raise SystemExit("Claude Code と Codex の識別信号が同時にあるため主系を判定できない。"
                     "ORGFORGE_ACTIVE_HARNESS=claude|codex を明示すること。")


def opposite_harness(active):
    if active == "claude":
        return "codex"
    if active == "codex":
        return "claude"
    raise SystemExit(f"未対応のハーネス: {active!r}（claude | codex）")


def _availability_override(name, env):
    key = f"ORGFORGE_{name.upper()}_AVAILABLE"
    raw = str(env.get(key) or "").strip().lower()
    if not raw:
        return None
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise SystemExit(f"{key} は true | false のどちらか。")


def harness_available(name, env=None):
    """Return whether the secondary CLI can be used without claiming more than we know.

    Codex exposes an offline login-status command, so use it. Claude Code 2.x exposes no equivalent
    CLI probe; on macOS its Keychain entry can be tested without reading the credential. Other
    platforms use executable presence and retain the explicit override as the honest escape hatch.
    """
    if name not in _HARNESS_NAMES:
        raise SystemExit(f"未対応のハーネス: {name!r}（claude | codex）")
    env = os.environ if env is None else env
    override = _availability_override(name, env)
    if override is not None:
        return override
    exe = shutil.which(name)
    if not exe:
        return False
    if name == "codex":
        try:
            result = subprocess.run([exe, "login", "status"], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=10, env=dict(env))
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0
    if sys.platform == "darwin":
        security = shutil.which("security")
        if security:
            try:
                result = subprocess.run(
                    [security, "find-generic-password", "-s", "Claude Code-credentials"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=10, env=dict(env))
            except (OSError, subprocess.TimeoutExpired):
                return False
            return result.returncode == 0
    return True


def effective_lineage(declared, env=None):
    """Resolve same/cross/adaptive without ever labelling a fallback as cross-harness."""
    declared = str(declared or "same-harness").strip()
    if declared in ("same-harness", "cross-harness"):
        return declared
    if declared != "adaptive":
        raise SystemExit(f"judges.lineage が不正: {declared!r}"
                         "（same-harness | cross-harness | adaptive）")
    active = active_harness(env)
    secondary = opposite_harness(active)
    if harness_available(secondary, env):
        return "cross-harness"
    print(f"[orgforge] {secondary} は利用可能と確認できないため、adaptive reviewer を "
          f"{active} 内の pseudo same-harness 分離で実行する。別ベンダー保証は無い。",
          file=sys.stderr)
    return "same-harness"
