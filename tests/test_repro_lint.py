"""Level-2 reproducibility gate (docs/11 §4a) — repro_lint checks a generated repo is clone-and-run
reproducible: lockfile, pinned toolchain, one-command setup+test, idempotent migrations, .env.example,
CI-from-clean. Presence checks, deterministic (same repo ⇒ same verdict)."""
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "repro_lint.py"


def run(repo, *args):
    r = subprocess.run([sys.executable, str(TOOL), "check", str(repo), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def _clean_repo(root):
    (root / "package.json").write_text(json.dumps({
        "name": "x", "engines": {"node": ">=20"},
        "dependencies": {"react": "18.0.0"},
        "scripts": {"setup": "npm ci", "test": "vitest"}}))
    (root / "package-lock.json").write_text("{}")
    (root / "README.md").write_text("# X\n\n## Setup\n`make setup`\n\n## Test\n`make test`\n")
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("name: ci\non: [push]\n")


def test_clean_repo_passes_deploy_bar(tmp_path):
    _clean_repo(tmp_path)
    code, out = run(tmp_path, "--phase", "deploy")
    assert code == 0, out


def test_missing_lockfile_holds(tmp_path):
    _clean_repo(tmp_path)
    (tmp_path / "package-lock.json").unlink()
    code, out = run(tmp_path, "--phase", "implement")
    assert code == 10 and "lockfile" in out, out


def test_empty_manifest_holds(tmp_path):
    _clean_repo(tmp_path)
    (tmp_path / "package.json").write_text('{"name":"x"}')   # no deps
    code, out = run(tmp_path, "--phase", "implement")
    assert code == 10 and "manifest" in out, out


def test_no_readme_holds_at_test_bar_but_not_implement(tmp_path):
    _clean_repo(tmp_path)
    (tmp_path / "README.md").unlink()
    # README is a test-phase requirement, so implement passes, test holds
    c_impl, _ = run(tmp_path, "--phase", "implement")
    c_test, out = run(tmp_path, "--phase", "test")
    assert c_impl == 0, "README not required at implement"
    assert c_test == 10 and "readme-setup" in out, out


def test_unguarded_migration_holds(tmp_path):
    _clean_repo(tmp_path)
    m = tmp_path / "supabase" / "migrations"
    m.mkdir(parents=True)
    (m / "0001.sql").write_text("create table users (id int);")   # no `if not exists`
    code, out = run(tmp_path, "--phase", "test")
    assert code == 10 and "idempotent-migrations" in out, out


def test_guarded_migration_passes(tmp_path):
    _clean_repo(tmp_path)
    m = tmp_path / "supabase" / "migrations"
    m.mkdir(parents=True)
    (m / "0001.sql").write_text("create table if not exists users (id int);")
    code, out = run(tmp_path, "--phase", "test")
    assert code == 0, out


def test_env_ignored_but_no_example_holds(tmp_path):
    _clean_repo(tmp_path)
    (tmp_path / ".gitignore").write_text(".env\n.env.local\n")   # secrets used…
    code, out = run(tmp_path, "--phase", "test")                 # …but no .env.example
    assert code == 10 and "env-example" in out, out


def test_ci_at_repo_root_counts_for_a_subpackage(tmp_path):
    # REGRESSION (found live on tatekae): CI lives at the VCS root (.github/), but the checked app is a
    # sub-package (monorepo app/). The CI check must walk up to the .git root, or it false-HOLDs a repo
    # that actually has CI.
    (tmp_path / ".git").mkdir()                       # mark the VCS root
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("name: ci\non: [push]\n")
    app = tmp_path / "app"
    app.mkdir()
    _clean_repo(app)
    (app / ".github").exists() and None               # app has NO ci of its own
    import shutil
    shutil.rmtree(app / ".github")                     # ensure the only CI is at the root
    code, out = run(app, "--phase", "deploy")
    assert code == 0, f"root-level CI must satisfy a sub-package's deploy bar: {out}"


def test_deterministic_same_verdict_twice(tmp_path):
    _clean_repo(tmp_path)
    (tmp_path / "package-lock.json").unlink()
    a = run(tmp_path, "--phase", "deploy")
    b = run(tmp_path, "--phase", "deploy")
    assert a == b, "same repo must yield the same verdict (reproducible check)"
