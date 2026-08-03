import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"


def _run(repo, tool, *args):
    return subprocess.run([sys.executable, str(TOOLS / tool), *args], cwd=repo,
                          capture_output=True, text=True)


def _git(repo, *args, env=None):
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                          check=True, env=env)
    return proc.stdout.strip()


def _org(tmp_path, *, feature_commit=False):
    org = tmp_path / "org"
    org.mkdir(parents=True)
    (org / ".orgforge" / "ledger").mkdir(parents=True)
    _git(org, "init", "-q")
    _git(org, "config", "user.email", "test@example.invalid")
    _git(org, "config", "user.name", "Test")
    (org / ".gitignore").write_text(".orgforge/\n", encoding="utf-8")
    (org / "constitution.yaml").write_text(
        "enforcement:\n  judges:\n    lineage: cross-harness\n"
        "    require_current_integration_head: true\n"
        "    integration_ref: main\n", encoding="utf-8")
    (org / "REQUIREMENTS.md").write_text("MUST keep the target current\n", encoding="utf-8")
    (org / "artifact.txt").write_text("baseline\n", encoding="utf-8")
    shutil.copy2(REPO / "template" / "ledger-schema.yaml", org / "ledger-schema.yaml")
    _git(org, "add", "-A")
    _git(org, "commit", "-qm", "baseline")
    _git(org, "branch", "-M", "main")
    _git(org, "checkout", "-qb", "feature")
    if feature_commit:
        (org / "artifact.txt").write_text("feature\n", encoding="utf-8")
        _git(org, "add", "artifact.txt")
        _git(org, "commit", "-qm", "feature")
    return org


def _subject(org, role="gate"):
    sys.path.insert(0, str(TOOLS))
    from orgcycle._core import review_subject
    from review_freshness import persist_descriptor
    sid, parts = review_subject(7, role, "implement", cwd=str(org), integration_ref="main")
    persist_descriptor(sid, parts, str(org))
    return sid, {**parts, "review_subject_id": sid}


def _advance_main(org):
    parent = _git(org, "rev-parse", "main")
    tree = _git(org, "rev-parse", "main^{tree}")
    env = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
               GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid")
    commit = _git(org, "commit-tree", tree, "-p", parent, "-m", "advance main", env=env)
    _git(org, "update-ref", "refs/heads/main", commit, parent)
    return commit


def test_persist_descriptor_keeps_subject_root_as_audit_sidecar(tmp_path):
    org = _org(tmp_path)
    sys.path.insert(0, str(TOOLS))
    from review_freshness import persist_descriptor
    parts = {"issue": "7", "role": "gate", "subject_root": str(org)}
    path = persist_descriptor("a" * 64, parts, str(org))
    recorded = json.loads(Path(path).read_text(encoding="utf-8"))
    assert recorded["subject_root"] == str(org)


def _append_provisional(org, lineage, descriptor):
    payload = {
        "issue": 7, "deliverable": "7", "role": "gate", "lineage": lineage,
        "verdict": "admit", "for_event": "admission_decided",
        "review_subject_id": descriptor["review_subject_id"],
        "review_subject": descriptor, "reasoning_sha256": f"reason-{lineage}",
    }
    return _run(org, "ledger.py", "append", str(org / ".orgforge" / "ledger"),
                "--actor", lineage, "--class", "verdict_provisional",
                "--natural-key", f"freshness-{lineage}",
                "--payload", json.dumps(payload))


def test_current_integration_head_allows_joint_admission(tmp_path):
    org = _org(tmp_path)
    sid, descriptor = _subject(org)
    for lineage in ("same-harness", "cross-harness"):
        result = _run(org, "github_sync.py", "provisional", "--issue", "7",
                      "--role", "gate", "--lineage", lineage, "--verdict", "admit",
                      "--subject", sid,
                      "--why", f"{lineage} independently checked the current integration base and evidence.",
                      "--evidence", "pytest output and current git relationship")
        assert result.returncode == 0, result.stdout + result.stderr
    events = [json.loads(line) for line in
              (org / ".orgforge/ledger/ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    admissions = [event for event in events if event["class"] == "admission_decided"]
    assert len(admissions) == 1
    assert admissions[0]["payload"]["review_subject"]["integration_ref"] == "main"


def test_verify_reports_stale_diverged_and_unresolvable_targets(tmp_path):
    stale = _org(tmp_path / "stale")
    _advance_main(stale)
    result = _run(stale, "org_cycle.py", "verify", "--issue", "7", "--role", "gate",
                  "--phase", "implement", "--base", "main", "--print-subject",
                  "--subject-root", ".")
    assert result.returncode == 11
    assert "stale" in result.stderr and "1 commit" in result.stderr

    diverged = _org(tmp_path / "diverged", feature_commit=True)
    _advance_main(diverged)
    result = _run(diverged, "org_cycle.py", "verify", "--issue", "7", "--role", "gate",
                  "--phase", "implement", "--base", "main", "--print-subject",
                  "--subject-root", ".")
    assert result.returncode == 11
    assert "diverged" in result.stderr or "分岐" in result.stderr

    missing = _org(tmp_path / "missing")
    _git(missing, "branch", "-D", "main")
    result = _run(missing, "org_cycle.py", "verify", "--issue", "7", "--role", "gate",
                  "--phase", "implement", "--base", "main", "--print-subject",
                  "--subject-root", ".")
    assert result.returncode == 11
    assert "unresolvable" in result.stderr or "解決できない" in result.stderr


def test_strict_verify_uses_declared_ref_when_main_and_develop_both_exist(tmp_path):
    org = _org(tmp_path)
    _git(org, "branch", "develop", "main")
    result = _run(org, "org_cycle.py", "verify", "--issue", "7", "--role", "gate",
                  "--phase", "implement", "--print-subject",
                  "--subject-root", ".")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "integration_ref" in result.stderr and "= main" in result.stderr


def test_strict_verify_requires_declared_ref_but_cli_can_override(tmp_path):
    org = _org(tmp_path)
    constitution = org / "constitution.yaml"
    constitution.write_text(
        constitution.read_text(encoding="utf-8").replace("    integration_ref: main\n", ""),
        encoding="utf-8")
    missing = _run(org, "org_cycle.py", "verify", "--issue", "7", "--role", "gate",
                   "--phase", "implement", "--print-subject",
                  "--subject-root", ".")
    assert missing.returncode == 11
    assert "統合先を推測しない" in missing.stderr

    explicit = _run(org, "org_cycle.py", "verify", "--issue", "7", "--role", "gate",
                    "--phase", "implement", "--base", "main", "--print-subject",
                  "--subject-root", ".")
    assert explicit.returncode == 0, explicit.stdout + explicit.stderr
    assert "integration_ref" in explicit.stderr and "= main" in explicit.stderr


def test_target_movement_after_both_votes_blocks_derive(tmp_path):
    org = _org(tmp_path)
    _, descriptor = _subject(org)
    for lineage in ("same-harness", "cross-harness"):
        result = _append_provisional(org, lineage, descriptor)
        assert result.returncode == 0, result.stdout + result.stderr
    _advance_main(org)
    result = _run(org, "ledger.py", "derive-admission", str(org / ".orgforge/ledger"),
                  "--issue", "7", "--event", "admission_decided")
    assert result.returncode == 7
    answer = json.loads(result.stdout.splitlines()[0])
    assert answer["reason"] in {"integration_head_moved", "integration_base_stale"}


def test_reviewed_tree_change_after_votes_blocks_derive(tmp_path):
    org = _org(tmp_path)
    _, descriptor = _subject(org)
    for lineage in ("same-harness", "cross-harness"):
        result = _append_provisional(org, lineage, descriptor)
        assert result.returncode == 0, result.stdout + result.stderr
    (org / "artifact.txt").write_text("changed after review\n", encoding="utf-8")
    result = _run(org, "ledger.py", "derive-admission", str(org / ".orgforge/ledger"),
                  "--issue", "7", "--event", "admission_decided")
    assert result.returncode == 7
    assert json.loads(result.stdout.splitlines()[0])["reason"] == "reviewed_tree_changed"


def test_rebase_creates_a_new_current_subject(tmp_path):
    org = _org(tmp_path)
    old_id, _ = _subject(org)
    _advance_main(org)
    _git(org, "rebase", "main")
    new_id, descriptor = _subject(org)
    assert new_id != old_id
    assert descriptor["base_sha"] == descriptor["integration_head_sha"]
    assert descriptor["integration_relation"] == "current"
