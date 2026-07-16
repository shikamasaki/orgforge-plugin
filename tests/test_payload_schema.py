"""Regression guard: every payload an organ tool EMITS must use only fields the ledger schema
declares for that event class. This is the machine-check for the schema's own promise — "if it
isn't an event class, it didn't happen" — extended to the field level, so a tool can't quietly
emit an off-schema key (the reference_staleness_checked / breadcrumb-drift class of bug). It runs
the tools and diffs their real LEDGER-EVENT output against the schema; a mismatch fails the build.
"""
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
SCHEMA = REPO / "template" / "ledger-schema.yaml"


def _schema_fields():
    """Parse ledger-schema.yaml event_classes into {class: {top-level field names}} by
    brace-matching each block (payloads span multiple lines with nested {..}/[..])."""
    s = SCHEMA.read_text()
    ec = s[s.find("event_classes:"):s.find("# ── Cadence triggers")]
    out = {}
    for m in re.finditer(r"^  ([a-z_]+):\s*\{", ec, re.M):
        cls, start, depth, j = m.group(1), m.end() - 1, 0, m.end() - 1
        while j < len(ec):
            if ec[j] == "{":
                depth += 1
            elif ec[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = ec[start + 1:j]
        flat = re.sub(r"\{[^{}]*\}", "", body)      # strip one level of nesting
        flat = re.sub(r"\[[^\]]*\]", "", flat)
        fields = {tok.split(":")[0].strip() for tok in flat.split(",")}
        out[cls] = {f for f in fields if re.match(r"^[a-z_]+$", f)}
    return out


def _run(*args, cwd):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=cwd)


def _seed(root, cls, payload, ts="2026-07-16T00:00:00Z"):
    _run(str(TOOLS / "ledger.py"), "append", str(root), "--actor", "a", "--class", cls,
         "--payload", json.dumps(payload), "--ts", ts, cwd=REPO)


def _emitted(root, *args):
    out = _run(*[str(TOOLS / args[0]), *args[1:]], cwd=REPO).stdout
    evs = []
    for line in out.splitlines():
        if line.startswith("LEDGER-EVENT "):
            evs.append(json.loads(line[len("LEDGER-EVENT "):]))
    return evs


def test_all_emitted_payloads_are_in_schema(tmp_path):
    schema = _schema_fields()
    root = str(tmp_path)
    # seed enough state to make the stall/attention/learning paths fire
    _seed(root, "cycle_started", {"role": "m", "pack_manifest_id": "x"})
    for k in range(3):
        _seed(root, "cycle_started", {"role": "n", "pack_manifest_id": f"a{k}"},
              ts=f"2026-07-16T0{k+1}:00:00Z")

    cases = [
        ("guardrails.py", "cap", root, "--dimension", "spend", "--delta", "1", "--cap", "5",
         "--actor", "x"),
        ("guardrails.py", "reconcile", root, "--domain", "d", "--observed", "1", "--expected", "1"),
        ("reconcile.py", "stall", root, "--freshness-cycles", "1"),
        ("reconcile.py", "collision", root),
        ("reconcile.py", "contract", root, "--seam", "s", "--producer", "p", "--breaking",
         "false", "--dependents", "a"),
        ("reconcile.py", "mandate", root, "--subjects", "a,b", "--decision", "d",
         "--precedence", "a>b"),
        ("attention.py", "select", root, "--role", "miner"),
        ("resource.py", "rank", root, "--objectives", "a:1,b:2"),
        ("resource.py", "reclaim", root, "--holder", "h", "--resource", "context",
         "--yield-threshold", "0.5", "--idle-cycles", "1"),
        ("resource.py", "authority", root),
        ("alignment.py", "premise", root, "--premise-id", "p", "--asserted", "1", "--observed", "1"),
        ("alignment.py", "sunk", root, "--course-id", "c", "--attempt-cap", "4"),
        ("alignment.py", "frame", root),
        ("learning.py", "delta", root),
    ]
    problems = []
    for c in cases:
        for ev in _emitted(root, *c):
            cls = ev["class"]
            assert cls in schema, f"{c[0]} emits undeclared event class '{cls}'"
            extra = set(ev["payload"]) - schema[cls]
            if extra:
                problems.append(f"{c[0]} emits '{cls}' with off-schema keys {sorted(extra)}")
    assert not problems, "payload/schema drift:\n" + "\n".join(problems)
