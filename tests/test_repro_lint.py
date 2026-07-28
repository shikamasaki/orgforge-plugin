"""Level-2 reproducibility gate (docs/11 §4a) — repro_lint checks a generated repo is clone-and-run
reproducible: lockfile, pinned toolchain, one-command setup+test, idempotent migrations, .env.example,
CI-from-clean. Presence checks, deterministic (same repo ⇒ same verdict)."""
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "repro_lint.py"
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("repro_lint", TOOL)
RL = _ilu.module_from_spec(_spec); _spec.loader.exec_module(RL)


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
    # the unread-safe bar (docs/11 §4e): a repo with no complexity ceiling, no tests, and no
    # duplication scan is not "clean" at fan-out scale — it is merely installable.
    (root / "eslint.config.js").write_text(
        'export default [{ rules: { "max-lines-per-function": ["error", 60],'
        ' "complexity": ["error", 20], "@typescript-eslint/no-explicit-any": "error" } }]')
    (root / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}}')
    (root / "app.test.ts").write_text("test('x', () => {})")
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("name: ci\non: [push]\njobs:\n  q:\n    runs-on: ubuntu-latest\n"
                               "    steps:\n      - run: npx jscpd src\n      - run: npx knip\n"
                               "  win:\n    runs-on: windows-latest\n    steps:\n      - run: npm test\n")


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
    # the root workflow is also where a monorepo's cross-cutting scans live (docs/11 §4e)
    (wf / "ci.yml").write_text("name: ci\non: [push]\njobs:\n  q:\n    runs-on: ubuntu-latest\n"
                               "    steps:\n      - run: npx jscpd .\n      - run: npx knip\n"
                               "  win:\n    runs-on: windows-latest\n    steps:\n      - run: npm test\n")
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


# ── the unread-safe bar (docs/11 §4e) ────────────────────────────────────────
# At fan-out scale nobody reads every diff. These checks assert the repo has a MECHANICAL rejection
# layer for the defects that only a careful reader would otherwise catch.
STRICT_ESLINT = ('export default [{ rules: {'
                 '"max-lines-per-function": ["error", 60], "complexity": ["error", 20],'
                 '"max-depth": ["error", 4], "sonarjs/cognitive-complexity": ["error", 15],'
                 '"@typescript-eslint/no-explicit-any": "error",'
                 '"@typescript-eslint/ban-ts-comment": "error" } }]')
LOOSE_ESLINT = 'export default [{ rules: { "no-console": "warn" } }]'


def _ts_repo(root, eslint, tsconfig='{"compilerOptions":{"strict": true}}', ci=None):
    (root / "eslint.config.js").write_text(eslint, encoding="utf-8")
    (root / "tsconfig.json").write_text(tsconfig, encoding="utf-8")
    (root / "package.json").write_text('{"dependencies":{"react":"18"},'
                                       '"scripts":{"setup":"npm ci","test":"vitest"}}',
                                       encoding="utf-8")
    (root / "package-lock.json").write_text("{}", encoding="utf-8")
    (root / ".nvmrc").write_text("20\n", encoding="utf-8")
    (root / "app.test.ts").write_text("test('x', () => {})", encoding="utf-8")
    (root / "README.md").write_text("# App\n## Setup\nnpm install\n## Test\nnpm test\n",
                                    encoding="utf-8")
    if ci:
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / "ci.yml").write_text(ci, encoding="utf-8")
    return root


CI_WITH_SCANS = ("jobs:\n  q:\n    runs-on: ubuntu-latest\n    steps:\n"
                 "      - run: npx jscpd src\n      - run: npx knip\n"
                 "  win:\n    runs-on: windows-latest\n    steps:\n      - run: npm test\n")


def test_article_style_repo_passes_the_full_deploy_bar(tmp_path):
    """End-to-end: a repo configured the way the fan-out thesis requires clears the deploy gate."""
    code, out = run(_ts_repo(tmp_path, STRICT_ESLINT, ci=CI_WITH_SCANS), "--phase", "deploy")
    assert code == 0, out
    assert "complexity/size bars configured" in out
    assert "jscpd" in out


def test_loose_repo_is_held_at_the_implement_gate(tmp_path):
    """A lint config alone is not the bar: style-only rules bound nothing, and strict:false plus an
    unbanned `any` leaves the escape hatch an agent reaches for to turn a build green."""
    code, out = run(_ts_repo(tmp_path, LOOSE_ESLINT,
                             tsconfig='{"compilerOptions":{"strict": false}}'), "--phase", "implement")
    assert code == 10, out
    assert "complexity-bounded" in out and "type-escapes-closed" in out


def test_no_lint_config_at_all_is_held(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies":{"a":"1"}}', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".nvmrc").write_text("20\n", encoding="utf-8")
    code, out = run(tmp_path, "--phase", "implement")
    assert code == 10
    assert "no lint config" in out


def test_strict_typing_without_banning_any_is_held(tmp_path):
    """strict:true still leaves `any` / @ts-ignore available — the hole is invisible in an unread diff."""
    code, out = run(_ts_repo(tmp_path, 'export default [{ rules: { "complexity": ["error", 20] } }]'),
                    "--phase", "implement")
    assert code == 10, out
    assert "type-escapes-closed" in out


def test_dup_and_dead_code_scan_is_required_only_at_deploy(tmp_path):
    """Report-only tooling, required late: it catches cross-cutting waste no single diff shows."""
    repo = _ts_repo(tmp_path, STRICT_ESLINT, ci="jobs:\n  q:\n    runs-on: ubuntu-latest\n    steps:\n      - run: npm test\n"
                        "  w:\n    runs-on: windows-latest\n    steps:\n      - run: npm test\n")
    assert run(repo, "--phase", "implement")[0] == 0          # not required yet
    code, out = run(repo, "--phase", "deploy")
    assert code == 10 and "dup-dead-code" in out


def test_a_repo_with_no_tests_is_held_at_the_test_gate(tmp_path):
    repo = _ts_repo(tmp_path, STRICT_ESLINT)
    (repo / "app.test.ts").unlink()
    code, out = run(repo, "--phase", "test")
    assert code == 10 and "tests-present" in out


def test_non_typescript_repo_is_not_penalised_for_tsconfig(tmp_path):
    """The type check is n/a for a language with no static type layer — not a silent failure."""
    (tmp_path / "main.rb").write_text("puts 1", encoding="utf-8")
    (tmp_path / "Gemfile.lock").write_text("GEM\n", encoding="utf-8")
    (tmp_path / ".rubocop.yml").write_text("Metrics/MethodLength:\n  Max: 30\n", encoding="utf-8")
    (tmp_path / ".tool-versions").write_text("ruby 3.3.0\n", encoding="utf-8")
    (tmp_path / "Gemfile").write_text("gem 'rails'\n", encoding="utf-8")
    code, out = run(tmp_path, "--phase", "implement")
    assert code == 0, out
    assert "type-escapes-closed: no static type layer detected (n/a)" in out, out
    assert "MethodLength" in out, "rubocop's size bar should satisfy the complexity check"


def test_inline_suppression_is_held(tmp_path):
    """A config exception carries a reason and can expire; an inline one is invisible and immortal —
    and with nobody reading the diff it is the cheapest way to make a bar stop applying."""
    repo = _ts_repo(tmp_path, STRICT_ESLINT, ci=CI_WITH_SCANS)
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "a.ts").write_text("// @ts-ignore\nconst x: any = 1\n", encoding="utf-8")
    code, out = run(repo, "--phase", "test")
    assert code == 10 and "no-inline-suppress" in out, out


def test_targeted_coded_ignore_is_allowed(tmp_path):
    """`# type: ignore[arg-type]` names what it suppresses — that is a scoped exception, not a blanket."""
    repo = _ts_repo(tmp_path, STRICT_ESLINT, ci=CI_WITH_SCANS)
    (repo / "helper.py").write_text("x = 1  # type: ignore[arg-type]\n", encoding="utf-8")
    ok, _ = RL.check_no_inline_suppressions(str(repo))
    assert ok


def test_single_os_ci_is_held_at_deploy(tmp_path):
    """One platform means no other real machine; platform breakage reaches users first."""
    repo = _ts_repo(tmp_path, STRICT_ESLINT,
                    ci="jobs:\n  q:\n    runs-on: ubuntu-latest\n    steps:\n"
                       "      - run: npx jscpd src\n      - run: npx knip\n")
    code, out = run(repo, "--phase", "deploy")
    assert code == 10 and "multi-os-ci" in out, out
    # not required earlier — it is a deploy-phase bar
    assert run(repo, "--phase", "test")[0] == 0


# ── baseline / drain-then-ratchet（既存リポジトリの途中導入, docs/11 §4e） ──
# 既存コードは §4e のバーを構造上ほぼ満たさない（バーが存在する前に書かれたため）。初日から全部
# error にすると赤の壁ができ、予測どおり「抑制コメントで黙らせる」文化が育つ = バーを無効化する形で
# バーを満たす。baseline は採用時点の失敗を既知の負債として記録し、以後は「新たな失敗」だけを止める。
def _legacy_repo(root):
    """機械バーを一切持たない、途中まで作られた既存リポジトリ。"""
    (root / "package.json").write_text('{"dependencies":{"react":"18.0.0"}}', encoding="utf-8")
    (root / "package-lock.json").write_text("{}", encoding="utf-8")
    (root / "README.md").write_text("# L\n## Setup\nnpm install\n## Test\nnpm test\n", encoding="utf-8")
    (root / "app.test.ts").write_text("test('x',()=>{})", encoding="utf-8")
    return root


def _baseline(repo):
    r = subprocess.run([sys.executable, str(TOOL), "baseline", str(repo)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_legacy_repo_is_held_before_adoption(tmp_path):
    code, out = run(_legacy_repo(tmp_path), "--phase", "implement")
    assert code == 10 and "toolchain-pin" in out


def test_baseline_makes_existing_failures_non_blocking(tmp_path):
    """採用直後に作業を止めないこと。既知の負債は報告されるがブロックしない。"""
    _legacy_repo(tmp_path)
    bc, bout = _baseline(tmp_path)
    assert bc == 0 and "toolchain-pin" in bout
    code, out = run(tmp_path, "--phase", "implement")
    assert code == 0, out
    assert "既知の負債" in out


def test_a_new_failure_is_still_blocked_after_baseline(tmp_path):
    """baseline は免罪符ではない — baseline に無い失敗（=この変更で壊した）は止める。"""
    _legacy_repo(tmp_path)
    _baseline(tmp_path)
    (tmp_path / "app.test.ts").unlink()          # 採用時は green だった項目を壊す
    code, out = run(tmp_path, "--phase", "test")
    assert code == 10 and "tests-present" in out


def test_repaid_debt_is_reported_so_the_ratchet_can_tighten(tmp_path):
    _legacy_repo(tmp_path)
    _baseline(tmp_path)
    (tmp_path / ".nvmrc").write_text("20\n", encoding="utf-8")   # 負債を1つ返済
    code, out = run(tmp_path, "--phase", "implement")
    assert code == 0
    assert "返済済み" in out and "toolchain-pin" in out


def test_retightened_baseline_blocks_a_regression_of_repaid_debt(tmp_path):
    """返済 → 締め直し → 再び壊す = ブロック。これがラチェットの本体。"""
    _legacy_repo(tmp_path)
    _baseline(tmp_path)
    (tmp_path / ".nvmrc").write_text("20\n", encoding="utf-8")
    _baseline(tmp_path)                                          # 締め直す
    (tmp_path / ".nvmrc").unlink()                               # 再び壊す
    code, out = run(tmp_path, "--phase", "implement")
    assert code == 10 and "toolchain-pin" in out


def test_baseline_warns_when_it_would_absorb_a_new_failure(tmp_path):
    """「壊した」を「許容する」に書き換える操作は、黙って通してはならない。"""
    _legacy_repo(tmp_path)
    _baseline(tmp_path)
    (tmp_path / "app.test.ts").unlink()
    code, out = _baseline(tmp_path)
    assert code == 0
    assert "新たに負債として追加" in out and "tests-present" in out
