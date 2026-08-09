"""Helpers shared across the tests.

pytest loads this automatically, but anything other than a fixture needs an explicit import:
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


# ── organ binding: let the tests run from this checkout ─────────────────────
# The organ-binding guard refuses a write to the ledger by any organ other than the installed
# plugin SessionStart bound. That is correct behaviour, but running a development checkout's tests
# inside such a host session fails every test that writes to the ledger with exit 12 (measured: 184
# failed). CI is green because no binding exists there, not because the guard is broken.
#
# So it is stated here **for the whole process**: this test run is a deliberate development
# checkout. Placing it in os.environ means it applies equally to helpers that build an env with
# `dict(os.environ, ...)` and to `run()`, which inherits the env without being passed one.
#
# A test verifying the binding guard itself must override this default and construct the state
# where nothing is stated (build an env with ORG_ALLOW_FOREIGN_ORGAN removed and have it write to
# the organization).
os.environ.setdefault("ORG_ALLOW_FOREIGN_ORGAN", "1")


# ── org_cycle was split into tools/orgcycle/ (0.22.0) ───────────────────────
# A test that inspects source as text is fragile against a split. What we want to see is **what is
# written, not which module it lives in**, so the target is every module concatenated.
# Anything verifiable by behaviour is checked by behaviour (that is the main line).

TEMPLATE = REPO / "template"

# ── org_cycle was split into tools/orgcycle/ (0.22.0) ───────────────────────
# A test that inspects source as text is fragile against a split. What we want to see is **what is
# written, not which module it lives in**, so the target is every module concatenated.
# Anything verifiable by behaviour is checked by behaviour (that is the main line).
def _cycle_src(*mods):
    """Return the source of orgcycle's modules (the named ones, or all) concatenated."""
    base = TOOLS / "orgcycle"
    names = mods or ("_core", "cycle", "judge", "ship", "inspect")
    out = []
    for m in names:
        f = base / f"{m}.py"
        if f.is_file():
            out.append(f.read_text(encoding="utf-8"))
    return "\n".join(out)

def _gh_src(*mods):
    """Return the source of ghsync's modules (the named ones, or all) concatenated.

    github_sync was split into tools/ghsync/ as well (0.22.0). A test that searches source as text
    is fragile against a split, so this form does not depend on the module layout.
    """
    base = TOOLS / "ghsync"
    names = mods or ("_core", "backlog", "record", "branch", "coverage")
    return "\n".join((base / f"{m}.py").read_text(encoding="utf-8")
                      for m in names if (base / f"{m}.py").is_file())

def _cycle_mod(name):
    """Import and return one orgcycle module (for tests that call a function directly).

    It is imported as a package — read as a standalone file, the relative import in
    `from ._core import ...` cannot resolve.
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

# ── field report: the moment just before integration is the easiest to skip ──
def _ledger_with(tmp_path, rows):
    led = tmp_path / "ledger"; led.mkdir(exist_ok=True)
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return led

# ── field report: with no correlation key the control had silently stopped working
# ──               (seq 204 / 205) ───────────────────────────────────────────
def _led(tmp_path):
    d = tmp_path / "l"; d.mkdir(exist_ok=True)
    return dict(os.environ, ORG_LEDGER_ROOT=str(d))

def _append(env, actor, cls, payload):
    return subprocess.run(
        [sys.executable, str(TOOLS / "ledger.py"), "append", "--actor", actor,
         "--class", cls, "--payload", json.dumps(payload)],
        capture_output=True, text=True, env=env, timeout=60)

# ── 0.18.0: the latest judgment holds (in an append-only ledger a reject arrives later) ──
def _status(led):
    return subprocess.run([sys.executable, str(TOOLS / "status.py"), "status", str(led)],
                          capture_output=True, text=True, timeout=60)

def _write_ledger(tmp_path, name, rows):
    led = tmp_path / name; led.mkdir(parents=True, exist_ok=True)
    (led / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return led

