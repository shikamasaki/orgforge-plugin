#!/usr/bin/env python3
"""Bind an organization to the installed OrgForge organ that started its host session.

This is an operational provenance check, not a hostile-user security boundary.  Its purpose is to
make a stale cache path or an unrelated development checkout loud before it writes the ledger.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid


SCHEMA = "orgforge-installed-organ/v1"


class BindingError(RuntimeError):
    pass


_LAUNCHER = r'''#!/usr/bin/env python3
"""Stable OrgForge organ launcher. Generated from the installed-organ binding contract."""
import json
import os
import re
import sys

binding_path = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "installed-organ.json"))
try:
    with open(binding_path, encoding="utf-8") as handle:
        binding = json.load(handle)
except Exception as exc:
    print(f"orgforge: installed-organ binding is unavailable: {exc}\n"
          "  restart the Claude Code/Codex session so SessionStart can rebind it", file=sys.stderr)
    raise SystemExit(12)
if binding.get("schema") != "orgforge-installed-organ/v1":
    print(f"orgforge: unsupported installed-organ binding schema: {binding.get('schema')!r}",
          file=sys.stderr)
    raise SystemExit(12)
if len(sys.argv) < 2 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", sys.argv[1]):
    print("usage: orgforge <organ> [args...]\n"
          "  examples: orgforge ledger verify | orgforge org-cycle verify ...", file=sys.stderr)
    raise SystemExit(2)
organ = sys.argv[1].replace("-", "_")
tools_root = os.path.realpath(str(binding.get("tools_root") or ""))
target = os.path.realpath(os.path.join(tools_root, organ + ".py"))
if not tools_root or os.path.dirname(target) != tools_root or not os.path.isfile(target):
    print(f"orgforge: bound organ {organ!r} is unavailable under {tools_root!r}\n"
          "  the plugin may have been updated; restart the host session to refresh the binding",
          file=sys.stderr)
    raise SystemExit(12)
os.environ["ORG_INSTALLED_ORGAN_BINDING"] = binding_path
os.environ["ORG_ORGAN_SESSION_ID"] = str(binding.get("session_id") or "")
os.environ["ORG_ORGAN_HARNESS"] = str(binding.get("harness") or "unknown")
os.execv(sys.executable, [sys.executable, target, *sys.argv[2:]])
'''


def _atomic_write(path, content, mode=0o600):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".organ-binding-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _manifest(tools_root):
    plugin_root = os.path.dirname(os.path.realpath(tools_root))
    candidates = (
        ("claude-code", os.path.join(plugin_root, ".claude-plugin", "plugin.json")),
        ("codex", os.path.join(plugin_root, ".codex-plugin", "plugin.json")),
        ("source", os.path.join(plugin_root, "integrations", "claude-code",
                                ".claude-plugin", "plugin.json")),
    )
    for harness, path in candidates:
        try:
            with open(path, encoding="utf-8") as handle:
                version = str((json.load(handle) or {}).get("version") or "unknown")
            return harness, version, plugin_root
        except Exception:
            continue
    return "unknown", "unknown", plugin_root


def installation_kind(tools_root):
    """Return installed harness name, or ``source``/``unknown`` for a development tree."""
    return _manifest(tools_root)[0]


def _fingerprint(tools_root):
    digest = hashlib.sha256()
    for name in ("organ_binding.py", "ledger.py", "org_goal.py", "org_cycle.py", "github_sync.py"):
        path = os.path.join(tools_root, name)
        digest.update(name.encode("utf-8"))
        try:
            with open(path, "rb") as handle:
                digest.update(handle.read())
        except OSError:
            digest.update(b"<missing>")
    return digest.hexdigest()


def _harness_name(value):
    value = str(value or "unknown")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise BindingError(f"invalid harness name: {value!r}")
    return value


def binding_path(org_root, harness):
    return os.path.join(runtime_root(org_root), _harness_name(harness), "installed-organ.json")


def launcher_path(org_root, harness):
    return os.path.join(runtime_root(org_root), _harness_name(harness), "bin", "orgforge")


def runtime_root(org_root):
    """Use Git's untracked common dir when possible; fall back for ledger-only organizations."""
    org_root = os.path.realpath(org_root)
    try:
        completed = subprocess.run(
            ["git", "-C", org_root, "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=10)
        if completed.returncode == 0 and (completed.stdout or "").strip():
            common = completed.stdout.strip()
            if not os.path.isabs(common):
                common = os.path.join(org_root, common)
            return os.path.join(os.path.realpath(common), "orgforge", "runtime")
    except Exception:
        pass
    return os.path.join(org_root, ".orgforge", "runtime")


def bind(org_root, tools_root, session_id=None):
    """Atomically register this installed organ and ensure the path-stable launcher exists."""
    org_root = os.path.realpath(org_root)
    tools_root = os.path.realpath(tools_root)
    if not os.path.isfile(os.path.join(tools_root, "ledger.py")):
        raise BindingError(f"tools root に ledger.py が無い: {tools_root}")
    harness, version, plugin_root = _manifest(tools_root)
    session_id = str(session_id or os.environ.get("ORG_ORGAN_SESSION_ID") or uuid.uuid4().hex)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", session_id):
        raise BindingError(f"invalid host session id: {session_id!r}")
    record = {
        "schema": SCHEMA,
        "org_root": org_root,
        "plugin_root": plugin_root,
        "tools_root": tools_root,
        "harness": harness,
        "version": version,
        "session_id": session_id,
        "tools_fingerprint": _fingerprint(tools_root),
        "bound_at_unix": time.time(),
        "launcher": launcher_path(org_root, harness),
    }
    _atomic_write(launcher_path(org_root, harness), _LAUNCHER, mode=0o700)
    _atomic_write(binding_path(org_root, harness),
                  json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return record


def _read_binding(path):
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except FileNotFoundError:
        return None
    except Exception as exc:
        raise BindingError(f"installed-organ binding を読めない: {path}: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise BindingError(f"installed-organ binding の schema が不正: {path}")
    return record


def _org_from_ledger(ledger_root):
    if ledger_root:
        ledger_root = os.path.realpath(ledger_root)
        parent = os.path.dirname(ledger_root)
        if os.path.basename(ledger_root) == "ledger" and os.path.basename(parent) == ".orgforge":
            return os.path.dirname(parent)
    return None


def load_binding(org_root=None, ledger_root=None, harness=None):
    explicit = os.environ.get("ORG_INSTALLED_ORGAN_BINDING")
    if explicit:
        path = os.path.realpath(explicit)
        return _read_binding(path)
    if org_root is None and ledger_root:
        org_root = _org_from_ledger(ledger_root)
    if not org_root:
        return None
    if harness:
        return _read_binding(binding_path(org_root, harness))
    records = load_bindings(org_root=org_root)
    if not records:
        return None
    return max(records, key=lambda item: float(item.get("bound_at_unix") or 0))


def load_bindings(org_root=None, ledger_root=None):
    if org_root is None:
        org_root = _org_from_ledger(ledger_root)
    if not org_root:
        return []
    records = []
    pattern = os.path.join(runtime_root(org_root), "*", "installed-organ.json")
    for path in sorted(glob.glob(pattern)):
        record = _read_binding(path)
        if record:
            records.append(record)
    return records


def invocation(org_root, harness):
    """Return the stable launcher only when a complete, live binding exists."""
    record = load_binding(org_root=org_root, harness=harness)
    if not record:
        return None
    launcher = os.path.realpath(str(record.get("launcher") or ""))
    if launcher != os.path.realpath(launcher_path(org_root, harness)) or not os.path.isfile(launcher):
        raise BindingError("installed-organ launcher が binding と一致しない。session を再起動すること")
    return launcher


def foreign_invocation_error(ledger_root, current_tools):
    """Return a diagnosis when a mutating tool is not the organ bound by SessionStart."""
    explicit = os.environ.get("ORG_INSTALLED_ORGAN_BINDING")
    records = [load_binding(ledger_root=ledger_root)] if explicit else load_bindings(
        ledger_root=ledger_root)
    records = [record for record in records if record]
    if not records:
        try:
            from discover import org_root
            root = org_root()
            records = load_bindings(org_root=root) if root else []
        except Exception:
            records = []
    if not records:
        return None
    observed = os.path.realpath(current_tools)
    for record in records:
        if os.path.realpath(str(record.get("tools_root") or "")) == observed:
            return None
    if os.environ.get("ORG_ALLOW_FOREIGN_ORGAN") == "1":
        print("WARNING: ORG_ALLOW_FOREIGN_ORGAN=1 — installed-organ binding mismatch を明示的に"
              " bypass した", file=sys.stderr)
        return None
    expected = ", ".join(sorted(
        f"{record.get('harness')}={os.path.realpath(str(record.get('tools_root') or ''))}"
        for record in records))
    launchers = ", ".join(sorted(str(record.get("launcher") or "") for record in records))
    return ("この組織へ書き込もうとした organ は SessionStart が束縛した installed organ と"
            "一致しない。\n"
            f"  expected tools_root: {expected}\n"
            f"  observed tools_root: {observed}\n"
            f"  stable invocation: {launchers} <organ> ...\n"
            "  plugin更新後ならホストsessionを再起動してbindingを更新すること。"
            "意図的な開発checkoutなら ORG_ALLOW_FOREIGN_ORGAN=1 を同じコマンドに明示する。")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="organ-binding")
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("bind")
    make.add_argument("--org-root", required=True)
    make.add_argument("--tools-root", required=True)
    show = sub.add_parser("status")
    show.add_argument("--org-root", required=True)
    show.add_argument("--harness")
    args = parser.parse_args(argv)
    try:
        if args.command == "bind":
            print(json.dumps(bind(args.org_root, args.tools_root), ensure_ascii=False, sort_keys=True))
        else:
            record = load_binding(org_root=args.org_root, harness=args.harness)
            if not record:
                print("UNBOUND")
                return 3
            print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return 0
    except BindingError as exc:
        print(f"organ-binding: {exc}", file=sys.stderr)
        return 12


if __name__ == "__main__":
    raise SystemExit(main())
