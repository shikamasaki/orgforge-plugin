"""Review-subject freshness shared by verify, judgment recording, and admission derivation.

The review subject already binds the reviewed tree.  Freshness is a different invariant: the
integration target may move after both reviewers inspected the same tree.  This module keeps the
observable descriptor next to the org state and re-resolves the target at every authority-bearing
transition.  No network fetch and no automatic rebase are performed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


SUBJECT_FIELDS = (
    "issue", "role", "phase", "integration_ref", "integration_head_sha",
    "base_sha", "integration_relation", "behind", "ahead", "reviewed_tree_sha",
    "dirty", "head_tree_sha", "requirements_digest",
)


def subject_digest(parts):
    canonical = {key: parts.get(key, "") for key in SUBJECT_FIELDS}
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _git(cwd, *args):
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return proc.returncode, proc.stdout.strip()


def select_integration_ref(cwd, requested=None):
    """Return the explicit target, or the first locally resolvable conventional target."""
    if requested:
        return str(requested)
    for ref in ("origin/develop", "develop", "origin/main", "main"):
        code, _ = _git(cwd, "rev-parse", "--verify", f"{ref}^{{commit}}")
        if code == 0:
            return ref
    # Keep the unresolved intent visible instead of replacing it with HEAD.
    return "origin/main"


def integration_observation(cwd, integration_ref=None):
    """Measure the relationship between HEAD and the integration target without changing either."""
    ref = select_integration_ref(cwd, integration_ref)
    code, target = _git(cwd, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if code != 0 or not target:
        return {
            "integration_ref": ref,
            "integration_head_sha": "",
            "base_sha": "",
            "integration_relation": "unresolvable",
            "behind": "",
            "ahead": "",
        }

    code, base = _git(cwd, "merge-base", "HEAD", target)
    if code != 0 or not base:
        return {
            "integration_ref": ref,
            "integration_head_sha": target,
            "base_sha": "",
            "integration_relation": "diverged",
            "behind": "",
            "ahead": "",
        }

    _, behind = _git(cwd, "rev-list", "--count", f"{base}..{target}")
    _, ahead = _git(cwd, "rev-list", "--count", f"{base}..HEAD")
    if base == target:
        relation = "current"
    else:
        code, _ = _git(cwd, "merge-base", "--is-ancestor", "HEAD", target)
        relation = "stale" if code == 0 else "diverged"
    return {
        "integration_ref": ref,
        "integration_head_sha": target,
        "base_sha": base,
        "integration_relation": relation,
        "behind": behind,
        "ahead": ahead,
    }


def freshness_policy(constitution_path):
    """Return ``(declared, value, error)`` for the strict-current-head declaration."""
    if not constitution_path or not os.path.isfile(constitution_path):
        return False, False, None
    try:
        import yaml
        with open(constitution_path, encoding="utf-8") as handle:
            doc = yaml.safe_load(handle) or {}
    except Exception as exc:
        return False, False, f"constitution を読めない: {exc}"
    try:
        judges = ((doc.get("enforcement") or {}).get("judges") or {})
    except AttributeError:
        return False, False, "enforcement.judges が map でない"
    if not isinstance(judges, dict):
        return False, False, "enforcement.judges が map でない"
    if "require_current_integration_head" not in judges:
        return False, False, None
    value = judges["require_current_integration_head"]
    if not isinstance(value, bool):
        return True, False, "require_current_integration_head が真偽値でない"
    return True, value, None


def integration_ref_policy(constitution_path):
    """Return ``(declared, ref, error)`` for the integration target declaration."""
    if not constitution_path or not os.path.isfile(constitution_path):
        return False, None, None
    try:
        import yaml
        with open(constitution_path, encoding="utf-8") as handle:
            doc = yaml.safe_load(handle) or {}
        judges = ((doc.get("enforcement") or {}).get("judges") or {})
    except Exception as exc:
        return False, None, f"constitution を読めない: {exc}"
    if not isinstance(judges, dict):
        return False, None, "enforcement.judges が map でない"
    if "integration_ref" not in judges:
        return False, None, None
    value = judges["integration_ref"]
    if not isinstance(value, str) or not value.strip():
        return True, None, "integration_ref が空でない文字列でない"
    return True, value.strip(), None


def descriptor_status(parts, cwd):
    """Re-resolve a descriptor and return a structured, fail-closed freshness result."""
    if not isinstance(parts, dict):
        return {"ok": False, "reason": "subject_descriptor_missing",
                "detail": "review subject descriptor が無い"}
    expected = subject_digest(parts)
    supplied = str(parts.get("review_subject_id") or expected)
    if supplied != expected:
        return {"ok": False, "reason": "subject_descriptor_mismatch",
                "detail": "descriptor の digest が review_subject_id と一致しない"}
    observed = integration_observation(cwd, parts.get("integration_ref"))
    relation = observed["integration_relation"]
    if relation == "unresolvable":
        return {"ok": False, "reason": "integration_ref_unresolvable",
                "detail": f"統合先 {observed['integration_ref']} を解決できない", **observed}
    if relation == "diverged":
        return {"ok": False, "reason": "integration_ref_diverged",
                "detail": f"HEAD と統合先 {observed['integration_ref']} が分岐している", **observed}
    if observed["integration_head_sha"] != parts.get("integration_head_sha"):
        return {"ok": False, "reason": "integration_head_moved",
                "detail": (f"統合先 {observed['integration_ref']} が判定後に移動した: "
                           f"{str(parts.get('integration_head_sha') or '')[:12]} → "
                           f"{observed['integration_head_sha'][:12]}"), **observed}
    if observed["base_sha"] != observed["integration_head_sha"]:
        return {"ok": False, "reason": "integration_base_stale",
                "detail": (f"base は統合先より {observed.get('behind') or '?'} commit 遅れている "
                           f"({observed['base_sha'][:12]} != "
                           f"{observed['integration_head_sha'][:12]})"), **observed}
    if parts.get("base_sha") != observed["base_sha"]:
        return {"ok": False, "reason": "integration_base_changed",
                "detail": "判定対象に束縛した base と現在の merge-base が一致しない", **observed}
    try:
        # Lazy import avoids a module cycle while `review_subject` itself is being assembled.
        from orgcycle._core import _worktree_tree_sha
        current_tree = _worktree_tree_sha(cwd)
    except Exception:
        current_tree = ""
    if not current_tree:
        return {"ok": False, "reason": "reviewed_tree_unresolvable",
                "detail": "現在の reviewed tree を再構成できない", **observed}
    if current_tree != parts.get("reviewed_tree_sha"):
        return {"ok": False, "reason": "reviewed_tree_changed",
                "detail": ("判定後に reviewed tree が変わった: "
                           f"{str(parts.get('reviewed_tree_sha') or '')[:12]} → "
                           f"{current_tree[:12]}。新しい subject で再検証が必要"), **observed}
    return {"ok": True, "reason": "current", "detail": "integration head と一致", **observed}


def _state_root(cwd):
    # Generated descriptors must not change the tree they describe.  Keep them under the shared Git
    # administration directory, which is also visible from every worktree.  Falling back to org state
    # supports ledger-only repositories, where there is no Git tree to perturb.
    code, git_dir = _git(cwd or os.getcwd(), "rev-parse", "--path-format=absolute", "--git-common-dir")
    if code == 0 and git_dir:
        return Path(git_dir).resolve() / "orgforge"
    override = os.environ.get("ORG_LEDGER_ROOT")
    if override:
        ledger = Path(override).resolve()
        return ledger.parent if ledger.name == "ledger" else ledger
    return Path(cwd or os.getcwd()).resolve() / ".orgforge"


def persist_descriptor(subject_id, parts, cwd=None):
    root = _state_root(cwd)
    target = root / "review-subjects" / f"{subject_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {**{key: parts.get(key, "") for key in SUBJECT_FIELDS},
               "review_subject_id": subject_id}
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")
    os.replace(temp, target)
    return str(target)


def load_descriptor(subject_id, cwd=None):
    path = _state_root(cwd) / "review-subjects" / f"{subject_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, str(path)
    if not isinstance(payload, dict) or subject_digest(payload) != subject_id:
        return None, str(path)
    return payload, str(path)
