#!/usr/bin/env python3
"""sensors — evaluate the machine sensors of sensors.yaml against a real ledger.

sensors.yaml declares each crisis signal's formula, window, threshold, hysteresis, and who
evaluates it: `machine` (a pure formula over the ledger) or `llm` (a judgment the registrar
obtains and records). Before this existed, EVERY sensor formula was only linted for shape —
no code computed any of them (the audit's D1 gap), except doctrine_stale which doctrine.py
happens to compute. This tool computes the `machine` sensors as pure functions of the ledger,
so a `judge: machine` sensor actually measures instead of merely being declared.

It ships no scheduler (docs/08, R0): the registrar is the agent a host runs every 30 min
(sensors.yaml defaults.evaluation_cadence); this tool is the pure formula it calls and whose
result it ledgers as a sensor_reading BEFORE any move consumes it. `llm` sensors are NOT
evaluated here — they require a judgment; this tool reports them as `judge: llm (deferred to
the registrar)` so the boundary between measured and judged is explicit, never faked.

  eval <root> <sensors_yaml> [--now TS] [--only SENSOR]   evaluate all machine sensors; print
                                                          each reading (value, fired?) as it
                                                          would be ledgered as a sensor_reading

Formulas implemented (the machine sensors whose inputs are fully in the ledger):
  - red_tape_ratio          (gate+reporting)/task tokens from cycle_completed.tokens
  - doctrine_stale          any doctrine claim past review_by (also in doctrine.py; unified here)
  - context_utilization     avg over roles of referenced/granted views (needs grants → partial)
  - blocked_on_missing_context  count of ledgered pull-denials at one seam
Sensors needing an llm judgment (divergence, demand_signal) or inputs this tool can't derive
from the ledger alone are reported as deferred — honestly, not silently skipped.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import read_events   # noqa: E402

# minimal YAML reader for sensors.yaml's flat list-of-maps (avoids a pyyaml dependency for a
# tool that must run anywhere; sensors.yaml is intentionally simple). Falls back to pyyaml if
# present. We only need id/judge/window/threshold/source_views/formula per sensor.
def _load_sensors(path):
    try:
        import yaml  # noqa
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        return doc.get("sensors", [])
    except Exception:
        pass
    # tiny fallback parser: good enough for the shipped sensors.yaml shape
    sensors, cur = [], None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            s = line.strip()
            if s.startswith("- id:"):
                if cur:
                    sensors.append(cur)
                cur = {"id": s.split("id:", 1)[1].strip()}
            elif cur is not None and s and ":" in s and not s.startswith("#") \
                    and (len(line) - len(line.lstrip())) >= 4:
                k, v = s.split(":", 1)
                cur[k.strip()] = v.strip()
    if cur:
        sensors.append(cur)
    return sensors


# ── machine formulas: each returns (value, fired_bool, note) given the events + now ──
def f_red_tape_ratio(events, now):
    task = gate = rep = 0
    for e in events:
        if e["class"] == "cycle_completed":
            t = e["payload"].get("tokens", {})
            task += t.get("task", 0); gate += t.get("gate", 0); rep += t.get("reporting", 0)
        elif e["class"] == "admission_decided":
            gate += e["payload"].get("tokens", 0) if isinstance(e["payload"].get("tokens"), int) else 0
    if task == 0:
        return (None, False, "no task tokens in window — undefined, not fired")
    val = (gate + rep) / task
    return (round(val, 4), val > 0.35, f"(gate+reporting)/task = ({gate}+{rep})/{task}")


def f_doctrine_stale(events, now):
    stale = []
    for e in events:
        if e["class"] == "doctrine_diff_admitted":
            for c in e["payload"].get("claims", []):
                rb = c.get("review_by")
                if now and rb and rb != "UNSET" and rb < now:
                    stale.append((e["payload"].get("role"), rb, c.get("claim", "")[:40]))
    return (len(stale), len(stale) >= 1,
            f"{len(stale)} claim(s) past review_by as of {now}: " +
            "; ".join(f"{r}<{rb}" for r, rb, _ in stale[:4]))


def f_blocked_on_missing_context(events, now):
    # ledgered pull-denials: recorded as anomaly_detected with detector == pull_denied, or a
    # cycle_completed carrying a denial marker. We count anomaly_detected{detector:pull_denied}.
    denials = {}
    for e in events:
        if e["class"] == "anomaly_detected" and e["payload"].get("detector") == "pull_denied":
            seam = e["payload"].get("description", "?")
            denials[seam] = denials.get(seam, 0) + 1
    worst = max(denials.values()) if denials else 0
    return (worst, worst >= 3,
            f"max denials at one seam = {worst} " +
            (f"({max(denials, key=denials.get)})" if denials else "(no ledgered denials)"))


def f_context_utilization(events, now):
    # referenced views / (a role's granted views). Grants live in organization.yaml, not the
    # ledger, so from the ledger alone we can only measure DISTINCT referenced views per role.
    # Report that honestly as a partial input, not a fabricated ratio.
    refs = {}
    for e in events:
        if e["class"] == "cycle_completed":
            role = e["payload"].get("role", "?")
            refs.setdefault(role, set()).update(e["payload"].get("views_referenced", []))
    summary = {r: len(v) for r, v in refs.items()}
    return (summary, False,
            "distinct referenced views per role (grant denominator lives in organization.yaml "
            "— pass grants to compute the ratio; not fired from ledger alone): " + str(summary))


# NOTE: each formula above hardcodes its fire threshold (e.g. red_tape_ratio's > 0.35), which
# sensors.yaml ALSO declares. They agree today, but the yaml value is intent-only — editing it
# does NOT change behavior; the code threshold wins. Wiring s.get("threshold") would be a behavior
# change, deliberately not done here. Keep the two in sync by hand until a follow-up unifies them.
MACHINE = {
    "red_tape_ratio": f_red_tape_ratio,
    "doctrine_stale": f_doctrine_stale,
    "blocked_on_missing_context": f_blocked_on_missing_context,
    "context_utilization": f_context_utilization,
}


def cmd_eval(a):
    sensors = _load_sensors(a.sensors_yaml)
    events = read_events(a.root)
    if not sensors:
        print("eval: no sensors parsed from " + a.sensors_yaml, file=sys.stderr)
        return 2
    any_fired = False
    for s in sensors:
        sid = s.get("id")
        if a.only and sid != a.only:
            continue
        judge = s.get("judge", "")
        if judge != "machine":
            print(f"[{sid}] judge: {judge} → deferred to the registrar (needs a judgment; "
                  f"not computed here)")
            continue
        if sid not in MACHINE:
            print(f"[{sid}] machine sensor, but its inputs are not fully in the ledger — "
                  f"deferred (not silently skipped)")
            continue
        value, fired, note = MACHINE[sid](events, a.now)
        any_fired = any_fired or fired
        mark = "FIRED" if fired else "ok"
        # this dict is exactly the sensor_reading payload the registrar would ledger BEFORE
        # any move consumes it (sensors.yaml header; ledger-schema sensor_reading).
        reading = {"sensor": sid, "value": value, "window": s.get("window", "?"),
                   "fired": fired, "note": note}
        print(f"[{sid}] {mark}: {note}")
        print("   sensor_reading payload → " +
              json.dumps({k: reading[k] for k in ("sensor", "value", "window")},
                         ensure_ascii=False))
    print("\n(hysteresis: sensors.yaml requires two consecutive readings over threshold "
          "before a move fires — this tool computes one reading; the registrar keeps the run "
          "of readings and applies hysteresis before selecting a move.)")
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="sensors", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("eval"); q.set_defaults(fn=cmd_eval)
    q.add_argument("root", nargs="?", help="ledger root (omitted: auto-discovered from the cwd — .orgforge/ledger)"); q.add_argument("sensors_yaml")
    q.add_argument("--now"); q.add_argument("--only")
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
