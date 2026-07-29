"""テスト全体で共有するヘルパ。

pytest が自動で読み込むが、フィクスチャ以外は明示 import が要る:
    from conftest import run, seed, TOOLS
"""
import importlib
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

TOOLS = REPO / "tools"


# ── org_cycle は tools/orgcycle/ に分割された（0.22.0）─────────────────────
# ソースを文字列で検査するテストは分割に弱い。**どのモジュールに居るかではなく、
# 何が書かれているか**を見たいので、全モジュールを連結したものを対象にする。
# 「振る舞いで検証できるもの」は振る舞いで見る（そちらが本筋）。

TEMPLATE = REPO / "template"

# ── org_cycle は tools/orgcycle/ に分割された（0.22.0）─────────────────────
# ソースを文字列で検査するテストは分割に弱い。**どのモジュールに居るかではなく、
# 何が書かれているか**を見たいので、全モジュールを連結したものを対象にする。
# 「振る舞いで検証できるもの」は振る舞いで見る（そちらが本筋）。
def _cycle_src(*mods):
    """orgcycle の（指定した / 全）モジュールのソースを連結して返す。"""
    base = TOOLS / "orgcycle"
    names = mods or ("_core", "cycle", "judge", "ship", "inspect")
    out = []
    for m in names:
        f = base / f"{m}.py"
        if f.is_file():
            out.append(f.read_text(encoding="utf-8"))
    return "\n".join(out)

def _gh_src(*mods):
    """ghsync の（指定した / 全）モジュールのソースを連結して返す。

    github_sync も tools/ghsync/ に分割された（0.22.0）。ソースを文字列で探すテストは
    分割に弱いので、モジュール構成に依存しない形にする。
    """
    base = TOOLS / "ghsync"
    names = mods or ("_core", "backlog", "record", "branch", "coverage")
    return "\n".join((base / f"{m}.py").read_text(encoding="utf-8")
                      for m in names if (base / f"{m}.py").is_file())

def _cycle_mod(name):
    """orgcycle の1モジュールを import して返す（関数を直接呼ぶテスト用）。

    パッケージとして import する — 単体ファイルとして読むと `from ._core import ...` の
    相対 import が解決できない。
    """
    import importlib, sys as _s
    if str(TOOLS) not in _s.path:
        _s.path.insert(0, str(TOOLS))
    return importlib.import_module(f"orgcycle.{name}")

def run(tool, *args, cwd=None):
    r = subprocess.run([sys.executable, str(TOOLS / tool), *args],
                       capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout + r.stderr

def seed(root, actor, cls, payload, ts="2026-07-16T00:00:00Z"):
    # cycle_completed requires a domain_model field (docs/11 §4d); default to none_asserted for tests
    # that don't care about the domain-model gate, so they don't all have to spell it out.
    if cls == "cycle_completed" and "domain_model" not in payload:
        payload = {**payload, "domain_model": {"none_asserted": "test seed"}}
    # phase_admitted now requires its own phase_started (docs/11 §2 — a phase cannot be admitted
    # without having been entered). Seeding an admission therefore implies seeding its start, so a
    # fixture that only cares about the *admitted* state doesn't have to spell both out.
    if cls == "phase_admitted":
        run("ledger.py", "append", str(root), "--actor", actor, "--class", "phase_started",
            "--payload", json.dumps({"deliverable": payload.get("deliverable"),
                                     "phase": payload.get("phase"), "role": actor}), "--ts", ts)
    code, out = run("ledger.py", "append", str(root), "--actor", actor,
                    "--class", cls, "--payload", json.dumps(payload), "--ts", ts)
    assert code == 0, f"seed failed: {out}"


# ── ledger.py ────────────────────────────────────────────────────────────────

def _propose_full(tmp_path, role="role"):
    code, out = run("doctrine.py", "propose", str(tmp_path), role, "--claim", "c",
                    "--source", "s", "--confidence", "0.9",
                    "--retrieved-at", "2026-07-16", "--review-by", "2027-01-16")
    assert code == 0, out
    code, show = run("doctrine.py", "show", str(tmp_path), role)
    return json.loads(show)["claims"][0]["id"]

def _admitted_claim(tmp_path, role, claim, affects):
    """propose+admit one claim tagged for `affects`, return its id."""
    run("doctrine.py", "propose", str(tmp_path), role, "--claim", claim,
        "--source", "s", "--confidence", "0.9", "--retrieved-at", "2026-07-16",
        "--review-by", "2027-01-16", "--affects", affects)
    _, show = run("doctrine.py", "show", str(tmp_path), role)
    cid = [c for c in json.loads(show)["claims"] if c["claim"] == claim][0]["id"]
    run("doctrine.py", "admit", str(tmp_path), role, cid, "--by", "gate", "--at", "2026-07-16")
    return cid

# ── tick.py (missed-detection boundary) ───────────────────────────────────────
def _sched():
    return str(TEMPLATE / "schedule.yaml")

# ── 実地フィードバック: 統合直前が最も抜けやすい ─────────────────────────
def _ledger_with(tmp_path, rows):
    led = tmp_path / "ledger"; led.mkdir(exist_ok=True)
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return led

# ── 実地: 相関キーが無いと統制が無言で無効になっていた（seq 204 / 205）───────
def _led(tmp_path):
    d = tmp_path / "l"; d.mkdir(exist_ok=True)
    return dict(os.environ, ORG_LEDGER_ROOT=str(d))

def _append(env, actor, cls, payload):
    return subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", "--actor", actor,
         "--class", cls, "--payload", json.dumps(payload)],
        capture_output=True, text=True, env=env, timeout=60)

# ── 0.18.0: 判定は最新が有効（追記型の台帳で reject が後から来る）─────────
def _status(led):
    return subprocess.run([sys.executable, str(TOOLS / "status.py"), "status", str(led)],
                          capture_output=True, text=True, timeout=60)

def _write_ledger(tmp_path, name, rows):
    led = tmp_path / name; led.mkdir(parents=True, exist_ok=True)
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return led

