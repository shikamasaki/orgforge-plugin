"""Backlog operations — creation, claim, stage transitions, and the split check.

The side that keeps an Issue in a workable state. It holds no judgment."""

import hashlib
import json
import os
import re
import subprocess
import sys

from ._core import (
    GITHUB_LABEL_MAX,
    HERE,
    CLAIM_PREFIX,
    label_too_long,
    _ensure_labels,
    _find_open_issue,
    _issue_number,
    _link_sub_issue,
    gh,
    issue_labels,
)


STAGES = ("ready", "in-progress", "blocked", "needs-human", "done")

# PARKED is the machine-readable vocabulary for "the work exists, but do not start it now". On
# Tatekae the only means available was the title prose `[PARKED]`, and `ready` handed work that had
# been stopped to a maker (OBS-051 / Issue #103). park/unpark ensure the label (part of the
# label-ensure list).
PARKED_LABEL = "orgforge:parked"
PARKED_COLOR = "ededed"

# The "cannot be started" states, struck from the ready roster. Even where one sits alongside
# `orgforge:ready` (mid-rework, or a label sweep that was missed), an Issue carrying one of these is
# not startable.
_NON_STARTABLE_LABELS = (PARKED_LABEL, "orgforge:in-progress", "orgforge:blocked",
                         "orgforge:needs-human")
_PLACEHOLDER_BODIES = frozenset({"(no body)", "no body", "tbd", "todo", "placeholder",
                                 "n/a", "none", "x", ".", "..."})


def _normalized_body(body):
    return str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _body_problem(body):
    """Return why an Issue body cannot carry task context, without echoing its contents."""
    normalized = _normalized_body(body)
    if not normalized:
        return "empty"
    visible = re.sub(r"<!--.*?-->", "", normalized, flags=re.S).strip()
    token = re.sub(r"\s+", " ", visible).lower().strip("#*_`~- ")
    if not token or token in _PLACEHOLDER_BODIES:
        return "placeholder-only"
    return None


def _body_digest(body):
    return hashlib.sha256(_normalized_body(body).encode("utf-8")).hexdigest()


def _issue_body(repo, issue):
    code, out = gh(["issue", "view", str(issue), "--repo", repo, "--json", "body"])
    if code != 0:
        return None, out
    try:
        value = json.loads(out)
        return str(value.get("body") or ""), ""
    except Exception as exc:
        return None, f"could not parse Issue body: {exc}"


def _composed_body(a):
    body = _normalized_body(a.body)
    parent = getattr(a, "parent", None)
    if parent:
        body += f"\n\nParent: #{str(parent).lstrip('#')}"
    dep_refs = []
    depends = getattr(a, "depends", None)
    if depends:
        dep_refs += [d.strip().lstrip("#") for d in depends.split(",") if d.strip()]
    # The carve-out path: an Issue split off mid-rework for an out-of-scope finding depends on the
    # original without exception (the parts exist only in the original worktree). Left to prose,
    # ready cannot see it (Issue #103).
    carved = getattr(a, "carved_from", None)
    if carved:
        dep_refs.append(str(carved).strip().lstrip("#"))
    if dep_refs:
        deps = ", ".join(f"#{d}" for d in dict.fromkeys(dep_refs))
        body += f"\n\nDepends on: {deps}"
    priority = getattr(a, "priority", None)
    if priority is not None:
        body += f"\n\npriority: {priority} (computed by attention.py — a projection, do not hand-edit)"
    return body


# The heading of a `Depends on:` line. The orthography is `Depends on: #n, #m` (the form
# _composed_body writes), but humans write it with markdown decoration (**emphasis**, lists,
# quotes), as `Depends-on`/`depends_on`, and with a space before the colon — all of it observed in
# the field (#103 rework 2). Read generously, write in the orthography.
_DEP_HEADER = re.compile(r"^[>*_\s•-]*depends[\s_-]*on\s*:\s*(.*)$", re.I)


def _depends_refs(body):
    """Collect the machine-readable Issue references (`#N`, and bare number tokens) from every
    Depends-on line in the body.

    References are recovered with `#(\\d+)` — an annotated token (`#63 (main 未統合)`) or an
    and-joined pair is not silently discarded. **Discarding them was what reproduced OBS-051** (the
    skeptic's refutation, #103 rework 2): a human merely added an annotation to the hand-written
    line the docs prescribe, and ready treated it as having no dependencies.
    A line carrying no reference at all (`Depends on: none`) is an explicit declaration of "no
    dependencies" — let it through quietly."""
    refs = []
    for line in str(body or "").splitlines():
        m = _DEP_HEADER.match(line)
        if not m:
            continue
        rest = m.group(1)
        line_refs = re.findall(r"#(\d+)", rest)
        for tok in rest.split(","):
            tok = tok.strip().strip("*_` ")
            if re.fullmatch(r"\d+", tok):
                line_refs.append(tok)   # a bare number token (`Depends on: 63`) is accepted as
                                        # before
        refs += line_refs
    return list(dict.fromkeys(refs))


# A GitHub closing keyword (Fixes/Closes/Resolves #N) references what will be closed, not a
# dependency. Making it trigger the prose WARN trains the operator, through false positives, to skim
# past warnings.
_CLOSING_REF = re.compile(r"\b(?:clos(?:e[sd]?)|fix(?:e[sd])?|resolv(?:e[sd]?))\s*:?\s*#(\d+)", re.I)


def _prose_dependency_warning(a):
    """The warning for a body that references another Issue as `#N` while carrying no `Depends on:`
    line (None where there is none).

    Measured on Tatekae (OBS-051): all four carved-out Issues wrote their dependencies only in the
    body's prose, and since `ready` does not read prose, work that could not be started was handed to
    a maker. Prose is **not** automatically read as a dependency — a guess is worse than a warning
    (`replaces #63` is not a dependency). This only says it loudly, where a human can see it."""
    raw = _normalized_body(getattr(a, "body", None))
    closing = set(_CLOSING_REF.findall(raw))
    refs = [r for r in dict.fromkeys(re.findall(r"#(\d+)", raw)) if r not in closing]
    if not refs:
        return None
    # Stay quiet where there is a declaration — but a declaration means one that **carries a
    # reference**. `Depends on: none` is an explicit "no dependencies", so where the prose talks
    # about #63 it is that contradiction which should surface.
    declared = bool(getattr(a, "depends", None)) or bool(getattr(a, "carved_from", None)) or \
        bool(_depends_refs(raw))
    if declared:
        return None
    listed = ", ".join(f"#{r}" for r in refs)
    return (f"WARN: the body references {listed} but declares NO `Depends on:` line. `ready` reads "
            f"only `Depends on:` lines — a dependency written in prose is invisible, and a maker can "
            f"be handed unstartable work (Issue #103). If any of {listed} gates this task, re-run "
            f"with --depends or --carved-from; prose is NOT auto-parsed into dependencies "
            f"(guessing is worse than warning).")


def _issue_state(repo, issue):
    """A GitHub Issue's open/closed state.

    The stage label is a projection of the backlog, and GitHub's Issue state is part of that same
    projection. Moving only one produces two truths — CLOSED while `ready`, or OPEN while `done` —
    so both are read at the entrance to a stage transition.
    """
    code, out = gh(["issue", "view", str(issue), "--repo", repo, "--json", "state"])
    if code != 0:
        return None, out
    try:
        state = str(json.loads(out).get("state") or "").upper()
    except Exception as e:
        return None, f"parse: {e}"
    if state not in ("OPEN", "CLOSED"):
        return None, f"unexpected issue state: {state or '(empty)'}"
    return state, ""


def cmd_claim(a):
    labels, err = issue_labels(a.repo, a.issue)
    if labels is None:
        print(f"gh error: {err}", file=sys.stderr)
        return 2
    mine = CLAIM_PREFIX + a.agent
    others = [l for l in labels if l.startswith(CLAIM_PREFIX) and l != mine]
    if others:
        print(f"CONTENDED: issue #{a.issue} is already claimed by {others} — not touching it "
              f"(concurrent-write prevention; another session owns it). (integrations/web)",
              file=sys.stderr)
        return 10
    if mine in labels:
        print(f"already claimed by {a.agent}; idempotent no-op.")
        return 0
    # ensure the label exists, then add it (atomic on GitHub's side)
    gh(["label", "create", mine, "--repo", a.repo, "--color", "0e8a16", "--force"], check=False)
    code, out = gh(["issue", "edit", str(a.issue), "--repo", a.repo, "--add-label", mine])
    if code != 0:
        print(f"gh error adding claim: {out}", file=sys.stderr)
        return 2
    print(f"claimed issue #{a.issue} for {a.agent}.")
    return 0


def cmd_release(a):
    mine = CLAIM_PREFIX + a.agent
    code, out = gh(["issue", "edit", str(a.issue), "--repo", a.repo, "--remove-label", mine])
    if code != 0:
        print(f"gh error releasing: {out}", file=sys.stderr)
        return 2
    print(f"released issue #{a.issue} ({a.agent}).")
    return 0


def cmd_create(a):
    # KIND: objective (the big-picture RFP/objective Issue — the parent) vs task (a department's unit of
    # work — a sub-issue of its objective). The kind label makes the two legible at a glance; the native
    # sub-issue link (below) makes the hierarchy real in GitHub's UI. Both are ledger projections (SSoT
    # unchanged): an objective Issue projects an org objective; a task Issue projects a candidate.
    kind = getattr(a, "kind", None) or "task"
    problem = _body_problem(getattr(a, "body", None))
    if problem:
        print(f"create: refusing {problem} Issue body before GitHub write. A {kind} must carry "
              f"the context another session needs to act; pass a non-placeholder --body.",
              file=sys.stderr)
        return 2
    prose_warning = _prose_dependency_warning(a)
    if prose_warning:
        print(prose_warning, file=sys.stderr)
    body = _composed_body(a)
    # idempotency (docs/11 §0): if an open Issue with this title (+objective) already exists, this is a
    # replay only when the body is also the same. Title equality must not silently discard context.
    existing, state = _find_open_issue(a.repo, a.title, a.objective)
    if existing is not None:
        current_body, err = _issue_body(a.repo, existing)
        if current_body is None:
            print(f"create: issue #{existing} exists but its body could not be verified: {err}. "
                  f"Refusing both a duplicate and an unverified no-op.", file=sys.stderr)
            return 2
        current_digest, wanted_digest = _body_digest(current_body), _body_digest(body)
        if _normalized_body(current_body) != _normalized_body(body):
            quality = _body_problem(current_body)
            condition = f"existing body is {quality}" if quality else "existing body differs"
            print(f"create: issue #{existing} matches the title but {condition}; refusing an "
                  f"idempotent no-op that would discard context. old_sha256={current_digest} "
                  f"new_sha256={wanted_digest}. Repair explicitly with `github_sync.py repair-body "
                  f"--repo {a.repo} --issue {existing} --body <correct-body> --reason <why>`.",
                  file=sys.stderr)
            return 10
        if state == "CLOSED":
            # already DELIVERED — re-minting it would duplicate finished work and re-open settled scope
            print(f"issue #{existing} already exists for {a.title!r} and is CLOSED (delivered) — "
                  f"idempotent no-op; not re-minting completed work (docs/11 §0).")
            return 0
        print(f"issue #{existing} already open for {a.title!r} — idempotent no-op (docs/11 §0).")
        # still (re)assert the parent link so a replayed task lands under its objective
        parent = getattr(a, "parent", None)
        if parent:
            ok, detail = _link_sub_issue(a.repo, int(str(parent).lstrip("#")), existing)
            print(detail if ok else f"WARN: {detail}", file=sys.stderr if not ok else sys.stdout)
        return 0
    labels = ["orgforge:ready", f"orgforge:kind:{kind}"]
    ensure = [("orgforge:ready", "1d76db"),
              (f"orgforge:kind:{kind}", "0e8a16" if kind == "objective" else "bfd4f2")]
    if a.objective:
        lbl = f"orgforge:objective:{a.objective}"
        labels.append(lbl); ensure.append((lbl, "5319e7"))
    dept = getattr(a, "dept", None)
    if dept:
        lbl = f"orgforge:dept:{dept}"
        labels.append(lbl); ensure.append((lbl, "d4c5f9"))
    if a.source:
        lbl = f"orgforge:{a.source}"
        labels.append(lbl); ensure.append((lbl, "fbca04"))
    # **Stop here if a label could not be created.** Creating the Issue anyway fails one call
    # later with `could not add label`, which reads as "this repository is not set up for
    # OrgForge" and sends the reader looking for an initialisation command that does not exist.
    # The real cause is usually a label over GitHub's 50-character limit, and it is fixable in
    # one edit — but only if the message says so.
    label_failures = _ensure_labels(a.repo, ensure)
    if label_failures:
        print("github_sync create: these labels could not be created, so no Issue was created:",
              file=sys.stderr)
        for name, why in label_failures:
            print(f"  {name!r}\n      {why}", file=sys.stderr)
        if any(label_too_long(name) for name, _ in label_failures):
            print(f"\n  `--objective` and `--dept` become labels, so they must be SHORT, stable "
                  f"identifiers — not the objective's prose. The full sentence belongs in --title "
                  f"and --body.\n"
                  f"    --objective self-dogfood-poc      # an id: label-safe, stable, greppable\n"
                  f"    --objective \"do … with our own product material\"   # prose: exceeds "
                  f"{GITHUB_LABEL_MAX} characters and is refused\n"
                  f"  Nothing was created; re-run with a shorter identifier.", file=sys.stderr)
        return 2
    parent = getattr(a, "parent", None)
    args = ["issue", "create", "--repo", a.repo, "--title", a.title, "--body", body]
    for l in labels:
        args += ["--label", l]
    code, out = gh(args)
    if code != 0:
        print(f"gh error creating issue: {out}", file=sys.stderr)
        return 2
    print(out.strip())   # gh prints the new issue URL
    # attach as a native sub-issue of its parent objective, so GitHub shows the hierarchy + roll-up
    if parent:
        child_number = _issue_number(out)
        if child_number is None:
            print("WARN: created the Issue but could not parse its number to link it as a sub-issue.",
                  file=sys.stderr)
            return 0
        ok, detail = _link_sub_issue(a.repo, int(str(parent).lstrip("#")), child_number)
        print(detail if ok else f"WARN: {detail}", file=(sys.stdout if ok else sys.stderr))
    return 0


def cmd_repair_body(a):
    """Replace an Issue body through an explicit, digest-recorded, rollback-on-audit-failure path."""
    problem = _body_problem(a.body)
    if problem:
        print(f"repair-body: refusing {problem} replacement body before GitHub write.", file=sys.stderr)
        return 2
    reason = _normalized_body(a.reason)
    if not reason:
        print("repair-body: --reason is required; a body rewrite without rationale is not auditable.",
              file=sys.stderr)
        return 2
    old_body, err = _issue_body(a.repo, a.issue)
    if old_body is None:
        print(f"repair-body: could not read issue #{a.issue}: {err}", file=sys.stderr)
        return 2
    new_body = _normalized_body(a.body)
    probe = type("BodyProbe", (), {"body": new_body, "depends": None, "carved_from": None})()
    prose_warning = _prose_dependency_warning(probe)
    if prose_warning:
        print(prose_warning, file=sys.stderr)
    old_refs, new_refs = _depends_refs(old_body), _depends_refs(new_body)
    if old_refs and not new_refs and not getattr(a, "confirm_drop_depends", False):
        print("repair-body: replacement removes existing Depends on references "
              f"({', '.join('#' + ref for ref in old_refs)}). "
              "Pass --confirm-drop-depends to make that audited choice explicitly.",
              file=sys.stderr)
        return 2
    old_digest, new_digest = _body_digest(old_body), _body_digest(new_body)
    if _normalized_body(old_body) == new_body:
        print(f"repair-body: issue #{a.issue} already has sha256={new_digest}; idempotent no-op.")
        return 0
    code, actor = gh(["api", "user", "--jq", ".login"])
    actor = actor.strip() if code == 0 else ""
    if not actor:
        print("repair-body: authenticated GitHub actor could not be observed; refusing an "
              "unattributed rewrite.", file=sys.stderr)
        return 2
    code, out = gh(["issue", "edit", str(a.issue), "--repo", a.repo, "--body", new_body])
    if code != 0:
        print(f"repair-body: GitHub body update failed; no audit success was recorded: {out}",
              file=sys.stderr)
        return 2
    marker = f"<!-- orgforge:issue-body-repair:{new_digest} -->"
    audit = (f"## Issue body repaired\n\n"
             f"- issue: `#{a.issue}`\n"
             f"- actor: `{actor}`\n"
             f"- old_sha256: `{old_digest}`\n"
             f"- new_sha256: `{new_digest}`\n"
             f"- reason: {reason}\n\n{marker}")
    code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", audit])
    if code != 0:
        rollback_code, rollback_out = gh(
            ["issue", "edit", str(a.issue), "--repo", a.repo, "--body", old_body])
        if rollback_code == 0:
            print("repair-body: audit comment failed, so the body update was rolled back; no "
                  f"unaudited repair remains: {out}", file=sys.stderr)
        else:
            print("repair-body: audit comment failed AND rollback failed. The body may be changed "
                  f"without completion evidence; inspect issue #{a.issue} immediately. "
                  f"audit_error={out} rollback_error={rollback_out}", file=sys.stderr)
        return 2
    print(f"repair-body: issue #{a.issue} updated by {actor}; old_sha256={old_digest} "
          f"new_sha256={new_digest}; audit comment recorded.")
    return 0


def cmd_stage(a):
    if a.stage not in STAGES:
        print(f"stage must be one of {STAGES}", file=sys.stderr)
        return 2
    labels, err = issue_labels(a.repo, a.issue)
    if labels is None:
        print(f"gh error: {err}", file=sys.stderr)
        return 2
    state, err = _issue_state(a.repo, a.issue)
    if state is None:
        print(f"gh error reading issue state: {err}", file=sys.stderr)
        return 2

    # ready / in-progress / blocked / needs-human are all states where the work still exists.
    # Returning only the label while it stays CLOSED makes it permanently invisible to
    # `ready --state open`. The formal rework path also goes through stage ready, so state and label
    # are brought into line here as one projection.
    reopened = False
    if a.stage != "done" and state == "CLOSED":
        rc, ro = gh(["issue", "reopen", str(a.issue), "--repo", a.repo])
        if rc != 0:
            print(f"gh error reopening issue: {ro}", file=sys.stderr)
            return 2
        state = "OPEN"
        reopened = True
    _ensure_labels(a.repo, [(f"orgforge:{s}", "c2e0c6") for s in STAGES])
    remove = [l for l in labels if l.startswith("orgforge:") and l[len("orgforge:"):] in STAGES]
    args = ["issue", "edit", str(a.issue), "--repo", a.repo, "--add-label", f"orgforge:{a.stage}"]
    for r in remove:
        if r != f"orgforge:{a.stage}":
            args += ["--remove-label", r]
    code, out = gh(args)
    if code != 0:
        # Reopen + relabel is not atomic in GitHub. Restore the original CLOSED projection when the
        # second half fails so an open Issue cannot remain hidden behind its previous `done` label.
        # A later retry is safe whether this compensation succeeds or not.
        if reopened:
            cc, co = gh(["issue", "close", str(a.issue), "--repo", a.repo])
            if cc != 0:
                print(f"WARN: reopened issue but relabel and compensating close both failed "
                      f"({out.strip()[:80]}; {co.strip()[:80]}) — retry stage to reconcile it.",
                      file=sys.stderr)
                return 10
        print(f"gh error: {out}", file=sys.stderr)
        return 2
    if a.stage == "done" and state != "CLOSED":
        cc, co = gh(["issue", "close", str(a.issue), "--repo", a.repo])
        if cc != 0:
            print(f"WARN: labeled done but close failed ({co.strip()[:120]}); a dependent Issue "
                  f"stays blocked until this closes — retry the close.", file=sys.stderr)
            return 10
    print(f"issue #{a.issue} → orgforge:{a.stage}")
    return 0


def cmd_ready(a):
    # list open Issues labeled orgforge:ready, unclaimed, not parked/in-progress, no open dependency
    code, out = gh(["issue", "list", "--repo", a.repo, "--label", "orgforge:ready",
                    "--state", "open", "--json", "number,title,labels,body"])
    if code != 0:
        print(f"gh error: {out}", file=sys.stderr)
        return 2
    try:
        issues = json.loads(out)
    except Exception as e:
        print(f"parse: {e}", file=sys.stderr)
        return 2
    kind = getattr(a, "kind", None) or "task"   # default: only TASKS are workable ready items
    ready = []
    # Issues withheld because the state of a dependency **could not be confirmed**. Rendering an
    # empty ready and "gh is half dead and cannot be checked" as the same {"ready": []} stops the org
    # silently, with no means of observing the cause — the same class of machine-invisible-state this
    # Issue set out to kill (#103 rework).
    withheld_unverifiable = []
    withheld_prose = []
    withheld_domain = []
    # An escape hatch is left, but **the default is closed**. An existing org holds a stock of prose
    # SPECs, and having them all vanish from ready at once stops the work. This keeps it openable
    # during the migration.
    _READY_SKIP_EARS = os.environ.get("ORG_READY_SKIP_EARS") == "1"
    for it in issues:
        names = [l["name"] for l in it.get("labels", [])]
        if any(n.startswith(CLAIM_PREFIX) for n in names):
            continue   # already claimed
        # parked / in-progress / blocked / needs-human are all NOT startable, even when the Issue
        # still carries a stale orgforge:ready (rework that never went through `stage`). Tatekae:
        # a 7-round-reworked, integration-waiting Issue was listed as untouched (Issue #103).
        if any(n in _NON_STARTABLE_LABELS for n in names):
            continue
        # kind filter: an objective Issue is a parent/roll-up, not a claimable unit of work. Default to
        # tasks; pass --kind objective to list objectives, or --kind any for both.
        if kind != "any":
            it_kind = next((n[len("orgforge:kind:"):] for n in names
                            if n.startswith("orgforge:kind:")), "task")
            if it_kind != kind:
                continue
        # dependency: parse EVERY Depends-on line (a body can carry several — carve-out plus
        # needs-human each append one; the old parser kept only the LAST line, Issue #103) and
        # EVERY ref on each line — an annotated token (`#63 (main 未統合)`) or an and-joined pair
        # must not be silently dropped (skeptic refutation, #103 rework 2). Ready only if all
        # referenced issues are verifiably CLOSED — an unverifiable dependency withholds too:
        # "state unknown" is not proof of startability. A line with zero refs (`Depends on: none`)
        # is an explicit no-dep declaration: silent, no queries.
        blocked = False
        for num in _depends_refs(it.get("body") or ""):
            c, o = gh(["issue", "view", num, "--repo", a.repo, "--json", "state"])
            state = None
            if c == 0:
                try:
                    state = str(json.loads(o).get("state") or "").upper()
                except Exception:
                    state = None
            if state == "CLOSED":
                continue
            blocked = True
            if state == "OPEN":
                # A healthy withhold — not an alarm, but left **in an observable form**. Where an
                # empty ready cannot be told from "empty because it waits on a dependency" on
                # stderr, the org stops with no means of observing the cause.
                print(f"withheld: issue #{it['number']} waits on open dependency #{num}",
                      file=sys.stderr)
            else:
                # Neither OPEN nor CLOSED = "could not be confirmed". There is no proof it is
                # startable, so it is not handed over, but it goes out as an alarm so gh degrading
                # can be told from "there is no work".
                withheld_unverifiable.append(it["number"])
                print(f"WARN: issue #{it['number']} withheld from ready — dependency #{num} could "
                      f"not be verified ({o.strip()[:80] or 'unparseable state'}). Unknown is not "
                      f"proof of startability; if gh is degraded, ready is UNDERREPORTING, not "
                      f"empty (Issue #103).", file=sys.stderr)
            break
        if blocked:
            continue
        # **Do not hand an Issue with prose acceptance to a maker.**
        #
        # split-check runs the same check at filing time, but `/org-decompose`'s guidance is "type
        # this command" rather than compulsion, and not typing it let the Issue through. In the field
        # #170 reached a maker with nine of its ten acceptance items still prose; the gate began each
        # round by designing how to confirm them, the standard wobbled from round to round, and it
        # took **twelve rounds** (twelve CI runs, twelve judgments).
        #
        # The structure where "whoever is checked decides whether the check runs" is closed here. A
        # SPEC with no target does not make it onto ready — convergence comes from **giving the gate
        # a target**, not from making the gate faster.
        # The fix is to rewrite the SPEC in EARS. It is not to loosen this.
        if not _READY_SKIP_EARS:
            prose = _non_ears_acceptance(it.get("body") or "")
            if prose:
                withheld_prose.append(it["number"])
                print(f"withheld: issue #{it['number']} — {len(prose)} acceptance item(s) are not "
                      f"EARS (e.g. \u201c{prose[0][:60]}\u201d). Hand a SPEC with no target to a "
                      f"maker and the gate rebuilds the standard every round, so the rounds never "
                      f"converge. Rewrite them in EARS before making it ready (in an emergency, "
                      f"ORG_READY_SKIP_EARS=1 disables this temporarily).",
                      file=sys.stderr)
                continue
            # Work that touches the domain is handed over only once it carries the surface a human
            # and the AI agree on (domain model / use case / authorization rules). In an org with no
            # declaration, paths is empty and nothing happens.
            _p, _r = ([], []) if os.environ.get("ORG_READY_SKIP_DOMAIN") == "1" \
                else _domain_surface()
            if _touches_domain_surface(it.get("body") or "", _p):
                _miss = _missing_domain_sections(it.get("body") or "", _r)
                if _miss:
                    withheld_domain.append(it["number"])
                    print(f"withheld: issue #{it['number']} — it touches the domain surface but "
                          f"has no {'/'.join(_miss)}. Write the surface a human reads first "
                          f"(ORG_READY_SKIP_DOMAIN=1 disables this temporarily).",
                          file=sys.stderr)
                    continue
        ready.append(it["number"])
    out_obj = {"ready": ready, "withheld_unverifiable": withheld_unverifiable}
    if withheld_prose:
        out_obj["withheld_non_ears"] = withheld_prose
    if withheld_domain:
        out_obj["withheld_no_domain_surface"] = withheld_domain
    print(json.dumps(out_obj))
    return 0


def cmd_park(a):
    """Park an Issue — with a machine-readable label (replacing the title prose `[PARKED]`, Issue
    #103).

    parked means "the work exists, but do not start it now". `ready` reads this label and excludes
    it. --why is left on the Issue as a comment — where the reason for stopping vanishes as prose,
    nobody can lift it again."""
    labels, err = issue_labels(a.repo, a.issue)
    if labels is None:
        print(f"gh error: {err}", file=sys.stderr)
        return 2
    why = _normalized_body(getattr(a, "why", None))
    if PARKED_LABEL in labels:
        # The label may be an idempotent no-op, but --why must not be silently discarded — the
        # reason is exactly what whoever unparks it later needs (the gate residual of #103 rework).
        if why:
            code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo,
                            "--body", f"⏸️ **Still parked** — reason updated.\n\nwhy: {why}"])
            if code != 0:
                print(f"WARN: issue #{a.issue} is already parked, and the new --why could not be "
                      f"recorded: {out.strip()[:120]}", file=sys.stderr)
                return 10
            print(f"issue #{a.issue} is already parked; new why recorded as a comment.")
            return 0
        print(f"issue #{a.issue} is already parked; idempotent no-op.")
        return 0
    _ensure_labels(a.repo, [(PARKED_LABEL, PARKED_COLOR)])
    code, out = gh(["issue", "edit", str(a.issue), "--repo", a.repo, "--add-label", PARKED_LABEL])
    if code != 0:
        print(f"gh error parking: {out}", file=sys.stderr)
        return 2
    if why:
        comment = (f"⏸️ **Parked** — excluded from `ready` until `github_sync park`'s counterpart "
                   f"`unpark` removes `{PARKED_LABEL}`.\n\nwhy: {why}")
        code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", comment])
        if code != 0:
            print(f"WARN: issue #{a.issue} IS parked (label applied) but the why-comment failed: "
                  f"{out.strip()[:120]} — re-run with --why to record it.", file=sys.stderr)
            return 10
        print(f"issue #{a.issue} parked; why recorded as a comment.")
    else:
        print(f"issue #{a.issue} parked (no --why given — a reason makes unparking decidable later).")
    return 0


def cmd_unpark(a):
    """Lift PARKED and return the Issue to the ordinary backlog judgment (visible to `ready`
    again)."""
    labels, err = issue_labels(a.repo, a.issue)
    if labels is None:
        print(f"gh error: {err}", file=sys.stderr)
        return 2
    if PARKED_LABEL not in labels:
        print(f"issue #{a.issue} is not parked; idempotent no-op.")
        return 0
    code, out = gh(["issue", "edit", str(a.issue), "--repo", a.repo, "--remove-label", PARKED_LABEL])
    if code != 0:
        print(f"gh error unparking: {out}", file=sys.stderr)
        return 2
    why = _normalized_body(getattr(a, "why", None))
    if why:
        code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo,
                        "--body", f"▶️ **Unparked** — back in `ready`'s view.\n\nwhy: {why}"])
        if code != 0:
            print(f"WARN: issue #{a.issue} IS unparked but the why-comment failed: "
                  f"{out.strip()[:120]}", file=sys.stderr)
            return 10
    print(f"issue #{a.issue} unparked.")
    return 0


def cmd_needs_human(a):
    """File a precondition only the CEO (a human) can carry out as an Issue (docs/11 §0c).

    **Why a dedicated command is needed.** The org filed only the work it could do itself as Issues
    and let what it needed from a human fall into a command's prose. In a founding in the field,
    three of them (creating the Supabase project, registering the Google OAuth client, setting
    GitHub's branch protection) existed only in the session's text and were left neither on an Issue
    nor in the ledger. The result:

      - they vanish when the session ends (/org-resume does not restore them either)
      - `/org` reports GREEN while Issues that cannot be started sit waiting on a human
      - `ready` hands a blocked task to a maker (there was no means of expressing "waiting on a
        human")
      - coverage-check only asks "did it become an Issue", so it displays 66/66

    **A request to a human is exactly what stops things longest when it is forgotten.**
    `/org-init` created the `orgforge:needs-human` label, yet no command carried a step that raised
    it, and it had never once been used. This command fills that hole.

    The Issue it files has the same shape as an ordinary task, so a downstream task can bind to it
    with `--depends` — until the human's work is done and it is closed, whatever depends on it does
    not appear in `ready`."""
    labels = ["orgforge:needs-human", "orgforge:kind:task"]
    ensure = [("orgforge:needs-human", "d93f0b"), ("orgforge:kind:task", "bfd4f2")]
    if a.objective:
        lbl = f"orgforge:objective:{a.objective}"
        labels.append(lbl); ensure.append((lbl, "5319e7"))
    existing, state = _find_open_issue(a.repo, a.title, a.objective)
    if existing is not None:
        print(f"issue #{existing} already exists for {a.title!r} ({state}) — idempotent no-op.")
        return 0
    _ensure_labels(a.repo, ensure)
    body = a.body or ""
    body += ("\n\n---\n**This is work only the CEO (a human) can carry out.** The org cannot start "
             "it.\nClose this Issue once it is done — the downstream tasks then become ready "
             "automatically.")
    if a.blocks:
        blocked = ", ".join(f"#{b.strip().lstrip('#')}" for b in a.blocks.split(",") if b.strip())
        body += f"\n\n**What cannot be started until this is done:** {blocked}"
    args = ["issue", "create", "--repo", a.repo, "--title", a.title, "--body", body]
    for l in labels:
        args += ["--label", l]
    code, out = gh(args)
    if code != 0:
        print(f"gh error creating needs-human issue: {out}", file=sys.stderr)
        return 2
    print(out.strip())
    n = _issue_number(out)
    if n and a.parent:
        ok, detail = _link_sub_issue(a.repo, int(str(a.parent).lstrip("#")), n)
        print(detail if ok else f"WARN: {detail}", file=(sys.stdout if ok else sys.stderr))
    if n:
        print(f"\nNEXT: write `Depends on: #{n}` into the body of every task that depends on this. "
              f"It then stays out of `ready` until the human's work is done.")
    return 0


def _non_ears_acceptance(body):
    """Return the acceptance / MUST lines that are not written in EARS.

    **The standard lives in req_lint alone.** Holding the definition of EARS in two places is certain
    to drift and produces mismatches like "it passed at filing time but the gate read it as prose".
    Where req_lint cannot be imported (running an organ standalone, say) the check is **skipped** —
    staying quiet is safer than wrongly calling everything a violation.

    Only the bullets in the acceptance section are read. Reading the whole body makes it walk past on
    an "IF ANY" in another section, an `if` in a code block, or a SQL `WHERE` (the real harm the old
    implementation did).
    """
    if not body:
        return []
    try:
        # The base point is kept in _core.HERE alone (it points at tools/). Re-resolving `__file__`
        # here gets missed when the package hierarchy changes — which is what happened in the 0.22.0
        # split.
        sys.path.insert(0, HERE)
        from req_lint import EARS_PATTERNS, _strip_noise
    except Exception:
        return []                       # where the standard cannot be read, do not check (stay
                                        # quiet)

    text = _strip_noise(body)           # drop quotes, code blocks, and appendices
    heading = re.compile(
        r"^#{1,6}\s*.*(?:acceptance|MUST|受け入れ|required\s+outcome|required\s+change"
        r"|proposed\s+acceptance)", re.I)
    bad, inside = [], False
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("#"):
            inside = bool(heading.match(s))
            continue
        if not inside or not s:
            continue
        if not re.match(r"^(?:[-*+]|\d+[.)])\s+", s):
            continue
        item = re.sub(r"^(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?", "", s)
        if not item:
            continue
        # A seam contract's meta line is not acceptance. In SPEC.md, `provides` / `owns` /
        # `depends_on` / `boundary` / `tools` / `example` / `DoD` sit in the same bullet list as the
        # MUST section, so counting them as requirement statements means **the better a SPEC is
        # written, the more violations it has** (three existing tests actually failed that way).
        # Label lines are excluded from the check.
        if re.match(r"^\*{0,2}(?:provides|owns|depends_on|boundary|tools?/?sources?|example|"
                    r"DoD[^:]*|完了の判定|検証|verification)\b\*{0,2}\s*[:：(]", item, re.I):
            continue
        if not any(re.search(p, item, re.I) for p, _ in EARS_PATTERNS):
            bad.append(item)
    return bad


def _domain_surface():
    """Read `enforcement.domain_surface` → (paths, require). ([], []) where there is no declaration.

    **The plugin does not guess paths.** Whether the domain layer sits in `src/domain/` or
    `app/models/` is the project's choice, and guessing produces false positives in an org with a
    different layout (among running orgs alone, src/domain/, src/usecase/, src/db/, and
    supabase/migrations/ coexisted). In an org with no declaration the check does not run — safer
    than silently stopping every Issue.
    """
    try:
        sys.path.insert(0, HERE)
        from discover import constitution
        path = constitution()
        if not path or not os.path.isfile(path):
            return [], []
        import yaml
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        ds = ((doc.get("enforcement") or {}).get("domain_surface") or {})
        paths = [str(p) for p in (ds.get("paths") or []) if str(p).strip()]
        require = [str(r) for r in (ds.get("require") or []) if str(r).strip()]
        return paths, (require or ["domain_model", "use_case", "authorization"])
    except Exception:
        return [], []


# How a section heading is recognised. Both the Japanese and English wordings are picked up
# (SPEC.md carries both).
_SECTION_PATTERNS = {
    "domain_model": r"ドメインモデル|domain\s*model|entities?\s*/\s*data-model",
    "use_case": r"ユースケース|use[-\s]*case",
    "authorization": r"認可|authoriz(?:ation|ed)|access\s*control",
}

# A counterexample (placebo / null) is written as **a label line inside the Verification section**,
# not as a heading. That is why a label is looked for rather than a section.
_COUNTEREXAMPLE_LABELS = {
    "placebo": r"\*{0,2}placebo\*{0,2}\s*[（(:：]",
    "null": r"\*{0,2}null\*{0,2}\s*[（(:：]",
}


def _missing_counterexamples(body):
    """Return the placebo / null counterexamples for which **nothing with substance exists**.

    Intent itself cannot be written whole, but an example of "this is not it" can be. Given a
    counterexample the gate can actually try "does the test go red if I put that placebo in" — it
    checks against a fact written on the Issue rather than against a judge's imagination.

    Without one the gate invents the placebo itself every round and the strictness shifts from round
    to round. And since 2.3.1 stopped injecting the role charter in full, **nothing** in what reaches
    a judge mentions placebo/null (`_focused_review_contract` does not carry the word). What can no
    longer rest on the judge's memory has to sit in the specification instead.

    **Whether the content is right is not read** — whether a counterexample is a good one is the work
    of a human and the gate.
    """
    if not body:
        return list(_COUNTEREXAMPLE_LABELS)
    missing = []
    for key, pat in _COUNTEREXAMPLE_LABELS.items():
        found = False
        for line in body.split("\n"):
            s = line.strip()
            if s.startswith(">") or not re.match(r"^(?:[-*+]|\d+[.)])\s+", s):
                continue
            if not re.search(pat, s, re.I):
                continue
            vals = re.findall(r"`([^`]*)`", s)
            # Left as the template (`<...>`) does not count as substance.
            if vals and all(v.strip().startswith("<") for v in vals):
                continue
            # Is there substance after the label (prose without backticks is allowed too)
            rest = re.split(pat, s, maxsplit=1, flags=re.I)[-1].strip(" ：:）)")
            if rest:
                found = True
                break
        if not found:
            missing.append(key)
    return missing


def _touches_domain_surface(body, paths):
    """Does a declared domain-surface prefix appear in the SPEC's owns / seam?"""
    if not body or not paths:
        return False
    quoted = re.findall(r"`([^`]+)`", body)
    return any(q.strip().startswith(p) or p.startswith(q.strip())
               for q in quoted for p in paths if q.strip())


def _missing_domain_sections(body, require):
    """Return the required sections for which **nothing with substance exists**.

    A heading alone does not pass — a SPEC that merely pastes the template is the most dangerous kind
    (it feels written, while nothing a human and the AI agreed on is there). It checks that at least
    one bullet exists and that it is not a placeholder (`<...>`). **Whether the content is right is
    not read** — that is the work of a human and a judge.
    """
    if not body:
        return list(require)
    lines = body.split("\n")
    missing = []
    for key in require:
        pat = _SECTION_PATTERNS.get(key)
        if not pat:
            continue
        filled, inside = False, False
        for line in lines:
            s = line.strip()
            if s.startswith("#"):
                inside = bool(re.search(pat, s, re.I))
                continue
            if not inside or not s or s.startswith(">"):
                continue
            if re.match(r"^(?:[-*+]|\d+[.)])\s+", s):
                item = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", s)
                # ``**label:** `<...>``` is still the template. It does not count as substance.
                vals = re.findall(r"`([^`]*)`", item)
                if vals and all(v.strip().startswith("<") for v in vals):
                    continue
                if item.strip():
                    filled = True
                    break
        if not filled:
            missing.append(key)
    return missing


def _has_dod_command(body):
    """Does the SPEC carry a DoD command that can be run?

    What is read is *whether it looks like a command*, not whether it is correct (the gate that runs
    it is what knows that). The one thing to be careful of is not counting the template's placeholder
    (`<the exact command …>`) as the real thing.
    """
    if not body:
        return False
    for line in body.split("\n"):
        if not re.search(r"DoD|完了の判定|Definition of Done", line, re.I):
            continue
        for code in re.findall(r"`([^`]+)`", line):
            code = code.strip()
            if code.startswith("<") or not code:
                continue            # the template's blank is unfilled
            if re.search(r"\b(npm|pnpm|yarn|make|pytest|python3?|go|cargo|bash|sh|npx|"
                         r"docker|supabase|deno|bun)\b", code):
                return True
    return False


def cmd_split_check(a):
    """SHAPE check on a task Issue's granularity (docs/11 §4b): warn (do not block) if the Issue looks
    too COARSE for a no-context maker — its `owns:` spans multiple disjoint territories (should be one
    atomic unit), or a `depends_on:` names an Issue that is still OPEN (the single-unit assertion fails:
    a fresh maker can't take it green until that sibling lands). This checks SHAPE, never SENSE — is the
    split *good* stays with the skeptic (docs/12 §6). Exit 0 clean · 10 = re-split candidate · 2 error."""
    code, out = gh(["issue", "view", str(a.issue), "--repo", a.repo, "--json", "body,title"])
    if code != 0:
        print(f"gh error: {out}", file=sys.stderr)
        return 2
    try:
        body = json.loads(out).get("body") or ""
    except Exception as e:
        print(f"parse: {e}", file=sys.stderr)
        return 2
    warnings = []
    # (a) owns spanning multiple territories — pull the `owns:` line and count distinct top-level paths
    for line in body.splitlines():
        low = line.lower()
        if "owns" in low and (":" in line):
            territory = line.split(":", 1)[1]
            # split on commas / 'and' / semicolons; count distinct top-level dirs (before the first '/')
            parts = [p.strip() for p in re.split(r"[,;、]| and ", territory) if p.strip()
                     and not p.strip().startswith("<")]   # ignore the unfilled placeholder
            tops = {p.split("/")[0].strip("` ") for p in parts}
            if len(tops) > 1:
                warnings.append(f"`owns:` spans {len(tops)} distinct territories {sorted(tops)} — a task "
                                f"should own ONE atomic unit; consider splitting one Issue per territory.")
            break
    # (b) depends_on referencing an OPEN Issue — the single-unit assertion (docs/11 §4b) fails
    for line in body.splitlines():
        if line.lower().lstrip().startswith(("depends_on", "depends on", "- **depends_on")):
            # Only the `#N` shape counts as a dependency. Picking up every number produces false
            # positives on prose — the "1" of "not one line of implementation code goes in" was read
            # as a reference (found in the field).
            # Where the same dependency appears on several lines of the body, the same warning lines
            # up repeatedly (three lines of it in the field). Saying it once is enough — a warning
            # that repeats itself joins the ones that get skimmed past.
            for num in dict.fromkeys(re.findall(r"#(\d+)", line.split(":", 1)[-1])):
                if num and not any(f"depends_on #{num} " in w for w in warnings):
                    c, o = gh(["issue", "view", num, "--repo", a.repo, "--json", "state"])
                    if c == 0 and json.loads(o).get("state") == "OPEN":
                        warnings.append(f"depends_on #{num} is still OPEN — a fresh maker can't take this "
                                        f"green until it lands (single-unit assertion fails, docs/11 §4b).")
    # (c) MUST written in EARS? A body with a MUST/acceptance section but no EARS keyword is prose
    # ("auth works") the gate can't test (docs/11 §4b).
    #
    # **Never read this as "pass it if a keyword appears anywhere in the body".** The old
    # implementation read the whole body with
    # `any(kw in body for kw in ("WHEN ","WHILE ","IF ","WHERE "))`, so with every acceptance item in
    # prose it still **walked past** on an "IF ANY" in another section, an `if x:` in a code block,
    # or a SQL `WHERE id = 1` (reproduced by measurement). In the field #170 was filed with nine of
    # its ten acceptance items in prose, the gate was left beginning each round by designing how to
    # confirm them, and it took twelve rounds. **Letting the check be walked past was the entrance to
    # the loop that would not converge.**
    #
    # Correctly, **only each acceptance line** goes through the same EARS check as req_lint. The
    # standard sits in one place (req_lint.EARS_PATTERNS) — two separate definitions of EARS are
    # certain to drift.
    bad_lines = _non_ears_acceptance(body)
    if bad_lines:
        shown = "; ".join(f"“{l[:60]}”" for l in bad_lines[:3])
        more = f" (and {len(bad_lines) - 3} more)" if len(bad_lines) > 3 else ""
        warnings.append(
            f"{len(bad_lines)} acceptance item(s) are not EARS: {shown}{more} — "
            "the gate cannot test prose (\u201cauth works\u201d). Rewrite them as "
            "WHEN/WHILE/IF/WHERE…SHALL (docs/11 §4b). "
            "**Loosen this and the gate has no target: the standard wobbles from round to round and "
            "the rounds stop converging.**")
    # (c2) DoD command — a SPEC with no "run this, and green means done" has given the gate no
    # target. gate.md orders it to re-derive rather than believe the maker's "verified it", so with
    # no command to run in the SPEC the gate starts **by designing how to confirm it**. That is the
    # main reason a single judgment takes around a hundred seconds (measured), and since the design
    # differs every round the standard wobbles.
    # This stays a warn (it does not stop ready) — an exploratory Issue genuinely may not be able to
    # settle its DoD first, and this is not mechanically black the way an EARS violation is.
    # The default is **on**. The stock of existing Issues all warning at once is accepted, and having
    # them rewritten is chosen instead — a SPEC with no DoD command has given the gate no target, and
    # that was the cause of the rounds (#170 took twelve). Crying wolf is "when warnings get thrown
    # away unread", not "when it says fix what should be fixed". An org that wants it off sets
    # ORG_REQUIRE_DOD=0.
    # (c3) Work that touches the domain must carry **the surface a human and the AI agree on**.
    # A diff review lets an oversight through silently, whereas reconciling the domain model, the use
    # cases, and the authorization rules asks "do the two state the same thing", so a mismatch is
    # visible. This applies only to Issues touching the declared domain surface (the plugin does not
    # guess paths).
    _ds_paths, _ds_require = _domain_surface()
    if _touches_domain_surface(body, _ds_paths):
        _missing = _missing_domain_sections(body, _ds_require)
        if _missing:
            _label = {"domain_model": "a domain model", "use_case": "use-case scenarios",
                      "authorization": "authorization rules"}
            warnings.append(
                "it touches the domain surface but has no "
                + " / ".join(_label.get(m, m) for m in _missing)
                + " (a heading alone, or the template left as-is, also counts as none). "
                "**This is what a human reads** — put it in the order of remembering what was to be "
                "built only after implementing it, and a deliverable that satisfies every MUST while "
                "differing from what was wanted passes. "
                "Write authorization as part of the domain rather than as technical security (the "
                "assets protected, the rules, and what is not protected).")
        # The counterexamples (placebo / null). The only material that catches "satisfies the MUSTs
        # while differing from what was wanted".
        # Since 2.3.1 stopped injecting the role charter in full, no placebo/null instruction reaches
        # a judge, so it has to sit as **a fact written on the Issue** rather than in a judge's
        # memory.
        _ce = _missing_counterexamples(body)
        if _ce:
            warnings.append(
                "there is no counterexample (" + " / ".join(_ce) + "). "
                "**Intent cannot be written whole, but an example of \u201cthis is not it\u201d "
                "can be.** Write one placebo (an implementation that satisfies the MUSTs' wording "
                "while betraying their intent) and one null (an output a real user would reject). "
                "Given those, the gate can actually try \u201cdoes the test go red if I put that "
                "placebo in\u201d — without them it reinvents the placebo every round, so the "
                "strictness shifts from round to round.")
    if os.environ.get("ORG_REQUIRE_DOD") != "0" and not _has_dod_command(body):
        warnings.append(
            "the SPEC carries no DoD command (a concrete command of which it can be said: run this, "
            "and green means done). "
            "The gate re-derives by running that same command, so without one it **starts by "
            "designing how to confirm it** — which not only makes the judgment slow but changes the "
            "standard from round to round until the rounds stop converging. "
            "Write it in a form that can actually be typed, like `cd app && npm test -- expense`.")
    # (d) A lopsided set of protected things — in a deliverable that handles authorization, is
    # **what is protected** lopsided?
    #
    # The shape found in operation: of twelve MUSTs only two set authorization, and one of those two
    # was about the nickname (a decorative text column). Not one line covered the amount, the payer,
    # the direction of the debt, or group ownership. In the skeptic's words, it "protected a
    # decorative text column while leaving the amount, the payer, the direction of the debt, and
    # group ownership undefended". As a result the last six rounds of rework were work that answered
    # no MUST on the Issue at all.
    #
    # Put out **material that can be noticed at filing time** (it does not judge — what should be
    # protected is a human's call).
    must_lines = [l for l in body.splitlines()
                  if re.search(r"\bSHALL\b|しなければならない|するものとする", l)]
    AUTHZ_DOMAIN = ("RLS", "ROW LEVEL SECURITY", "権限", "認可", "policy", "grant",
                    "SECURITY DEFINER", "拒否", "許可")
    if len(must_lines) >= 6 and sum(1 for w in AUTHZ_DOMAIN if w in body) >= 2:
        authz_musts = [l for l in must_lines if any(k in l for k in AUTHZ_DOMAIN)]
        # Is there a MUST setting what can be done once inside? This is read by whether **an
        # inside subject** appears. Deciding by asset name (amount, payment) misreads a consistency
        # constraint like `SUM(shares.amount) = expenses.amount` as "it protects the amount" — that
        # is not authorization.
        INSIDE = ("メンバーが", "メンバー同士", "他のメンバー", "他人の", "作成者", "所有者",
                  "自分以外", "owner", "creator", "member who", "書き換え")
        # "a non-member" is about the boundary. Counting it as inside by substring makes an Issue
        # that sets only the boundary count as "it sets the inside too", which voids this check
        # entirely (that is what happened in the operational example).
        OUTSIDE = ("非メンバー", "non-member", "未認証", "unauthenticated", "anonymous")
        guarded = [l for l in authz_musts
                   if any(k in l for k in INSIDE) and not any(o in l for o in OUTSIDE)]
        # Protecting only the nickname or display name does not count as protecting (observed in
        # operation)
        DECORATIVE = ("あだ名", "表示名", "nickname", "display_name", "アイコン", "avatar")
        substantive = [l for l in guarded if not any(d in l for d in DECORATIVE)]
        if authz_musts and not substantive:
            warnings.append(
                f"of {len(must_lines)} MUST(s), {len(authz_musts)} set authorization, but "
                f"**none of them sets what can be done once inside**"
                + (f" (the only inside thing touched is a decorative column: "
                   f"{', '.join(l.strip()[:28] for l in guarded[:2])}…)" if guarded else "") + ". "
                f"In the field an Issue of this shape produced a state that \u201cprotected a "
                f"decorative text column while leaving the amount, the payer, the direction of the "
                f"debt, and ownership undefended\u201d, and became twelve rounds of rework. "
                f"Authorization holds only through both \u201cwho may enter\u201d and \u201cwhat "
                f"can be done once inside\u201d — check that **the inside rules** are written as "
                f"requirements.")

    # (e) How many ways it can break — even with the same `owns`, **a different way of breaking and
    # a different means of verification make it a different Issue**.
    # In operation "the shape of the schema (types, constraints)" and "authorization (attack
    # scenarios)" were bundled into one, which left the gate reading both every round while a fix to
    # one kept breaking the other (five migrations interfering with each other).
    FAILURE_MODES = {
        "schema/type errors": ("型", "制約", "schema", "column", "not null", "型検査", "migration"),
        "authorization holes": ("RLS", "権限", "認可", "policy", "grant", "SECURITY DEFINER",
                                "非メンバー"),
        "calculation errors": ("端数", "合計", "配分", "計算", "金額が一致", "SUM"),
        "delivery/runtime": ("Service Worker", "PWA", "CI", "ビルド", "デプロイ", "キャッシュ"),
    }
    hit = [k for k, kws in FAILURE_MODES.items() if sum(1 for w in kws if w in body) >= 2]
    if len(hit) > 1:
        warnings.append(
            f"it can break in {len(hit)} distinct ways: {' / '.join(hit)}. "
            f"**Even with the same `owns`, a different way of breaking and a different means of "
            f"verification make it a different Issue** — bundled together, the gate begins every "
            f"round with \u201cwhere do I look\u201d and a fix to one breaks the other (it "
            f"produces migrations that interfere with each other). "
            f"Ask: when this deliverable breaks, is there only one way it breaks?")

    if warnings:
        print(f"RE-SPLIT / RESHAPE CANDIDATE — issue #{a.issue} may not be ready for a no-context maker:")
        for w in warnings:
            print(f"  · {w}")
        print("(shape warning only — whether the split/spec is GOOD stays with the skeptic, docs/12 §6.)")
        return 10
    print(f"issue #{a.issue}: shape OK (one territory, deps landed, acceptance in EARS).")
    return 0


def cmd_candidate_id(a):
    """Derive a backlog candidate's id DETERMINISTICALLY from what it IS (docs/11 §0, reproducibility F4).

    `candidate_id` is the backlog/dedup/WIP key and the ledger's `--natural-key`. If it were authored
    freely, running discovery/decomposition twice on the same gap would mint two ids — the same spec +
    ledger would yield a different backlog, and a replay would duplicate rather than no-op. So the id is
    a pure function of (role, contract_ref, gap), normalized (lowercased, whitespace-collapsed) so that
    casing/spacing differences do not change it — only a genuinely different gap does.

    This lives in a tool rather than in each command's prose because the fields are joined on a UNIT
    SEPARATOR (\\x1f): an unambiguous delimiter that cannot appear in a title, so ("auth","obj1") and
    ("aut","hobj1") cannot collide into one id. A shell-echoed one-liner loses that byte (echo eats the
    escape) and silently degrades to bare concatenation — which collides, and a collision means the
    second task's ledger append is swallowed as an idempotent replay and it never enters the backlog."""
    import hashlib
    import re
    norm = re.sub(r"\s+", " ", a.gap.strip().lower())
    key = "\x1f".join([a.role, a.contract, norm])
    print("cand-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12])
    return 0
