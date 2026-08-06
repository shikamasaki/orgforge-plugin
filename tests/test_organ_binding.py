import importlib.util
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest


REPO = pathlib.Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"
SOURCE = TOOLS / "organ_binding.py"


def _module():
    spec = importlib.util.spec_from_file_location("organ_binding_under_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BINDING = _module()


def _fake_tools(root, answer):
    root.mkdir()
    for name in ("ledger.py", "org_cycle.py", "github_sync.py", "organ_binding.py"):
        (root / name).write_text(
            "import sys\nprint(" + repr(answer + ":" + name) + ")\n", encoding="utf-8")
    return root


def _fake_bundle(base, answer):
    """A plugin-bundle layout: <base>/tools plus its sibling <base>/scripts (issue #108)."""
    base.mkdir()
    tools = _fake_tools(base / "tools", answer)
    scripts = base / "scripts"
    scripts.mkdir()
    (scripts / "redline_monitor.py").write_text(
        "print(" + repr(answer + ":redline_monitor.py") + ")\n", encoding="utf-8")
    return tools, scripts


def _org(tmp_path):
    root = tmp_path / "org"
    root.mkdir()
    (root / "organization.yaml").write_text("purpose: test\n", encoding="utf-8")
    return root


def test_stable_launcher_follows_rebinding_after_update(tmp_path):
    org = _org(tmp_path)
    first = _fake_tools(tmp_path / "tools-v1", "v1")
    second = _fake_tools(tmp_path / "tools-v2", "v2")
    one = BINDING.bind(org, first)
    launcher = pathlib.Path(one["launcher"])
    assert launcher.is_file()
    assert launcher.stat().st_mode & 0o111
    run = subprocess.run([str(launcher), "org-cycle"], capture_output=True, text=True)
    assert run.returncode == 0 and run.stdout.strip() == "v1:org_cycle.py"

    two = BINDING.bind(org, second)
    assert two["launcher"] == str(launcher), "public invocation changed across update"
    run = subprocess.run([str(launcher), "org-cycle"], capture_output=True, text=True)
    assert run.returncode == 0 and run.stdout.strip() == "v2:org_cycle.py"
    assert json.loads(pathlib.Path(BINDING.binding_path(org, two["harness"])).read_text())[
        "tools_root"] == str(second)


def test_launcher_diagnoses_a_removed_plugin_cache(tmp_path):
    org = _org(tmp_path)
    tools = _fake_tools(tmp_path / "cache-v1", "v1")
    record = BINDING.bind(org, tools)
    shutil.rmtree(tools)
    run = subprocess.run([record["launcher"], "ledger", "verify"],
                         capture_output=True, text=True)
    assert run.returncode == 12
    assert "restart" in run.stderr and "unavailable" in run.stderr


def test_launcher_resolves_an_organ_under_scripts_root(tmp_path):
    org = _org(tmp_path)
    tools, scripts = _fake_bundle(tmp_path / "bundle", "v1")
    record = BINDING.bind(org, tools)
    assert record["scripts_root"] == os.path.realpath(str(scripts))
    run = subprocess.run([record["launcher"], "redline-monitor"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "v1:redline_monitor.py"


def test_traversal_is_refused_for_both_roots(tmp_path):
    org = _org(tmp_path)
    tools, scripts = _fake_bundle(tmp_path / "bundle", "v1")
    secret = tmp_path / "secret.py"
    secret.write_text("print('escaped')\n", encoding="utf-8")
    record = BINDING.bind(org, tools)
    run = subprocess.run([record["launcher"], "../secret"], capture_output=True, text=True)
    assert run.returncode != 0 and "escaped" not in run.stdout
    # a symlink inside either root must not resolve to a file outside that root
    (tools / "sneaky_t.py").symlink_to(secret)
    (scripts / "sneaky_s.py").symlink_to(secret)
    for organ in ("sneaky-t", "sneaky-s"):
        run = subprocess.run([record["launcher"], organ], capture_output=True, text=True)
        assert run.returncode == 12, organ
        assert "escaped" not in run.stdout


def test_binding_without_scripts_root_resolves_tools_organs_as_before(tmp_path):
    org = _org(tmp_path)
    tools = _fake_tools(tmp_path / "tools-old", "v1")
    record = BINDING.bind(org, tools)
    path = pathlib.Path(BINDING.binding_path(org, record["harness"]))
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("scripts_root", None)  # simulate a binding written before issue #108
    path.write_text(json.dumps(data), encoding="utf-8")
    run = subprocess.run([record["launcher"], "org-cycle"], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "v1:org_cycle.py"


def test_old_binding_requesting_scripts_organ_advises_restart_to_rebind(tmp_path):
    """The upgrade gap: a pre-#108 binding (no scripts_root) on a bundle that DOES ship scripts/.

    Restart genuinely fixes this state (SessionStart rebinds and records scripts_root), so the
    launcher must say so — and must NOT claim restarting won't help.
    """
    org = _org(tmp_path)
    tools, scripts = _fake_bundle(tmp_path / "bundle", "v1")
    record = BINDING.bind(org, tools)
    path = pathlib.Path(BINDING.binding_path(org, record["harness"]))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["plugin_root"] == os.path.realpath(str(tmp_path / "bundle"))
    data.pop("scripts_root")  # simulate a binding written before issue #108
    path.write_text(json.dumps(data), encoding="utf-8")
    run = subprocess.run([record["launcher"], "redline-monitor"], capture_output=True, text=True)
    assert run.returncode == 12
    assert "restart the host session" in run.stderr
    assert "will not add it" not in run.stderr


def test_tools_root_wins_over_scripts_root_on_name_collision(tmp_path):
    org = _org(tmp_path)
    tools, scripts = _fake_bundle(tmp_path / "bundle", "v1")
    (scripts / "org_cycle.py").write_text("print('shadowed')\n", encoding="utf-8")
    record = BINDING.bind(org, tools)
    run = subprocess.run([record["launcher"], "org-cycle"], capture_output=True, text=True)
    assert run.returncode == 0 and run.stdout.strip() == "v1:org_cycle.py"


def test_unavailable_organ_names_searched_roots_and_does_not_advise_restart(tmp_path):
    org = _org(tmp_path)
    tools, scripts = _fake_bundle(tmp_path / "bundle", "v1")
    record = BINDING.bind(org, tools)
    run = subprocess.run([record["launcher"], "never-bundled"], capture_output=True, text=True)
    assert run.returncode == 12
    assert os.path.realpath(str(tools)) in run.stderr
    assert os.path.realpath(str(scripts)) in run.stderr
    assert "restart the host session" not in run.stderr


def test_foreign_checkout_is_rejected_before_ledger_write(tmp_path):
    org = _org(tmp_path)
    foreign = _fake_tools(tmp_path / "bound-installed-tools", "installed")
    BINDING.bind(org, foreign)
    ledger = org / ".orgforge" / "ledger"
    payload = json.dumps({"maker": "miner", "candidate_id": "c1",
                          "contract_ref": "goal", "source": "self", "evidence": ["x"]})
    run = subprocess.run([
        sys.executable, str(TOOLS / "ledger.py"), "append", str(ledger),
        "--actor", "miner", "--class", "candidate_submitted", "--payload", payload,
    ], capture_output=True, text=True, cwd=org)
    assert run.returncode == 12
    assert "expected tools_root" in run.stderr
    assert "observed tools_root" in run.stderr
    assert "stable invocation" in run.stderr
    assert not (ledger / "ledger.jsonl").exists()


def test_bound_stable_launcher_can_write_the_real_ledger(tmp_path):
    org = _org(tmp_path)
    record = BINDING.bind(org, TOOLS)
    ledger = org / ".orgforge" / "ledger"
    payload = json.dumps({"maker": "miner", "candidate_id": "c1",
                          "contract_ref": "goal", "source": "self", "evidence": ["x"]})
    run = subprocess.run([
        record["launcher"], "ledger", "append", str(ledger),
        "--actor", "miner", "--class", "candidate_submitted", "--payload", payload,
    ], capture_output=True, text=True, cwd=org)
    assert run.returncode == 0, run.stdout + run.stderr
    event = json.loads((ledger / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert event["class"] == "candidate_submitted"


@pytest.mark.parametrize("harness", ["claude-code", "codex"])
def test_session_start_binds_each_installed_harness_and_injects_contract(tmp_path, harness):
    org = _org(tmp_path)
    ledger = org / ".orgforge" / "ledger"
    bundle = REPO / "integrations" / harness
    env = dict(os.environ, ORG_LEDGER_ROOT=str(ledger), ORG_ROLE="supervisor",
               ORG_TOOLS_DIR=str(bundle / "tools"))
    run = subprocess.run(
        [sys.executable, str(bundle / "scripts" / "org_session_start.py")],
        input=json.dumps({"session_id": f"{harness}-session"}),
        capture_output=True, text=True, cwd=org, env=env)
    assert run.returncode == 0, run.stderr
    context = json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"]
    record = json.loads(pathlib.Path(BINDING.binding_path(org, harness)).read_text(encoding="utf-8"))
    assert record["harness"] == harness
    assert record["session_id"] == f"{harness}-session"
    assert record["launcher"] in context
    assert "do not search for another OrgForge checkout" in context
    assert ".claude/plugins/cache" not in context


def test_binding_contract_is_identical_in_both_bundles():
    source = SOURCE.read_bytes()
    for harness in ("claude-code", "codex"):
        assert (REPO / "integrations" / harness / "tools" / "organ_binding.py").read_bytes() == source


def test_git_org_binding_lives_outside_the_reviewed_tree(tmp_path):
    org = _org(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=org, check=True)
    subprocess.run(["git", "add", "organization.yaml"], cwd=org, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "init"], cwd=org, check=True)
    BINDING.bind(org, TOOLS)
    assert pathlib.Path(BINDING.binding_path(org, "source")).is_relative_to(org / ".git")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=org,
                            capture_output=True, text=True, check=True)
    assert status.stdout == "", "SessionStart binding changed the review subject"


def test_claude_and_codex_bindings_do_not_overwrite_each_other(tmp_path):
    org = _org(tmp_path)
    claude = BINDING.bind(org, REPO / "integrations" / "claude-code" / "tools")
    codex = BINDING.bind(org, REPO / "integrations" / "codex" / "tools")
    assert claude["harness"] == "claude-code"
    assert codex["harness"] == "codex"
    assert claude["launcher"] != codex["launcher"]
    assert BINDING.invocation(org, "claude-code") == claude["launcher"]
    assert BINDING.invocation(org, "codex") == codex["launcher"]
    assert len(BINDING.load_bindings(org_root=org)) == 2


def test_judge_prompt_uses_stable_launcher_not_a_tools_checkout(
        tmp_path, monkeypatch, capsys):
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import orgcycle.judge as judge
    org = _org(tmp_path)
    record = BINDING.bind(org, TOOLS)
    monkeypatch.chdir(org)
    monkeypatch.setattr(judge, "_role_charter", lambda role: ("charter", "gate.md"))
    monkeypatch.setattr(judge, "_issue_body", lambda issue: ("stable organ", "MUST work"))
    monkeypatch.setattr(judge, "_seam", lambda *args: "seam")
    monkeypatch.setattr(judge, "_prior_gate", lambda *args: None)
    monkeypatch.setattr(judge, "_judgment_history", lambda *args: [])
    monkeypatch.setattr(judge, "_issue_decision_comments", lambda *args: [])
    monkeypatch.setattr(judge, "_judge_lineage", lambda *args: ("same-harness", None))
    monkeypatch.setattr(judge, "review_subject",
                        lambda *args, **kwargs: ("a" * 64, {"issue": "37"}))
    monkeypatch.setattr(judge, "_run", lambda *args, **kwargs: (1, ""))
    # #101: subject は Issue の worktree（か明示の --subject-root）から。この org に
    # issue-37 の worktree は無いので明示する — このテストの主題は launcher の注入。
    args = argparse.Namespace(issue=37, role="gate", phase="implement", print_subject=False,
                              subject_root=str(org))
    assert judge.cmd_verify(args) == 0
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert f'"{record["launcher"]}" github-sync decide' in output
    assert f'"{record["launcher"]}" org-cycle rework' in output
    assert "mechanical_bar: declared_only" in output
    assert f'"{record["launcher"]}" repro-lint check' not in output
    assert str(TOOLS / "github_sync.py") not in output
    assert ".claude/plugins/cache" not in output
