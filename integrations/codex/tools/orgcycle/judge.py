"""Assemble the material for a judgment — verify / record.

**It holds no judging logic whatsoever.** The verdict, the why, the risk, and which mutations to
try are decided by the gate / skeptic. The moment a tool decides the verdict, the gate becomes a
formality."""

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import re
import sys

from organ_binding import BindingError

from ._core import (
    HERE,
    issue_worktree,
    issue_worktree_head,
    review_subject,
    worktree_rooted_at,
    _agents_dir,
    _events_for,
    _execute,
    _gh_sync,
    _issue_body,
    _ledger,
    _raw,
    _repo,
    _run,
    _sub,
)
from .preflight import PreflightConfigError, run_declared_preflights


def _role_charter(role):
    """The body of agents/<role>.md (with the front-matter stripped).

    **This is the heart of approach 2.** If a person writes out the verification steps each time,
    the gate's strictness changes with every writing — 18 Issues means 18 different standards.
    Inject the charter and the standard is fixed at one, and changing it takes effect from the
    single place in agents/<role>.md.
    """
    d = _agents_dir()
    path = os.path.join(d, f"{role}.md") if d else None
    if not path or not os.path.isfile(path):
        return None, path
    body = open(path, encoding="utf-8").read()
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            body = body[end + 4:]
    return body.strip(), path


# Seconds before a headless judge is treated as hung. Measured, not guessed: a realistic subject
# runs median ~46s / max ~87s, with a ~3x spread across identical prompts. This is deliberately
# well above that maximum — the value exists to catch a hang, and cutting a slow-but-working
# judgment costs a whole review round (#203).
JUDGE_TIMEOUT_DEFAULT = 300


def _verdict_schema(role):
    """Return the bundled structured-output schema for a judge role.

    ``HERE`` is the tools directory in both the neutral checkout and each self-contained
    harness bundle.  Keeping this resolution in one named helper makes the packaging contract
    executable: build scripts must place schemas under the adjacent ``template/schemas`` tree.
    """
    return os.path.normpath(
        os.path.join(HERE, "..", "template", "schemas", f"{role}-verdict.json"))


def _stable_organ_invocation():
    """Return the org-side launcher; installed bundles fail closed if SessionStart did not bind."""
    from discover import org_root
    from organ_binding import BindingError, installation_kind, invocation
    root = org_root()
    harness = installation_kind(HERE)
    stable = invocation(root, harness) if root else None
    if root and harness in ("claude-code", "codex") and not stable:
        raise BindingError(
            "running from an installed plugin, but the organization-side launcher is not "
            "registered. Enable the SessionStart hook and restart the host session")
    return stable


def _organ_command(stable, organ):
    """Render a stable public invocation, retaining a source-checkout fallback for development."""
    if stable:
        return f'"{stable}" {organ.replace("_", "-")}'
    filename = organ.replace("-", "_") + ".py"
    return f'python3 "{os.path.join(HERE, filename)}"'


def _seam(role, issue, title):
    """Build the seam contract by calling handoff.py internally, absorbing the six arguments that
    would otherwise be typed by hand."""
    slice_ = {
        "gate": f"admission of #{issue} \"{title}\" — re-derive each MUST one at a time",
        "skeptic": f"refutation of the admitted deliverable for #{issue} \"{title}\"",
    }.get(role, f"#{issue} 「{title}」")
    outputs = {
        "gate": "admission_decided (you decide the verdict yourself; an admit needs --evidence)",
        "skeptic": ("refutation_attempted (you decide the verdict yourself; a survives needs "
                    "--evidence)"),
    }.get(role, "a decision, and the grounds for it")
    code, out = _run([os.path.join(HERE, "handoff.py"), role,
               "--slice", slice_,
               "--inputs", f"the SPEC / MUSTs of task Issue #{issue}, and the maker's deliverable",
               "--outputs", outputs,
               "--owns", "the judgment itself (this plumbing does not decide the verdict)",
               "--forbid", ("admitting a deliverable you produced yourself / retracing the "
                            "maker's steps (re-derive the result instead)")])
    return out if code == 0 else None


def _prior_gate(issue, repo=None):
    """What the gate has already looked at, handed to the skeptic.

    Without it the skeptic repeats the gate's mutations and wastes the round (confirmed in
    practice). **This is plumbing, not judgment** — it carries what the gate wrote, verbatim, and
    decides neither whether that was right nor what should be tried next.
    """
    args = ["gh", "issue", "view", str(issue), "--json", "comments"]
    r = repo or _repo()
    if r:
        args += ["--repo", r]
    code, out = _raw(args)
    if code != 0:
        return None
    try:
        cs = json.loads(out).get("comments", [])
    except Exception:
        return None
    hits = [c.get("body", "") for c in cs if "admission_decided" in (c.get("body") or "")]
    return hits[-1] if hits else None


def _judgment_history(issue, cls=None):
    """Past judgments on this Issue (excluding corrected ones), oldest first.

    Without being handed these each time, the gate **treats it as a first judgment**. There is a
    field observation that quality rose once a third round was made to state "how what was missed
    last time was checked this time". A gate that does not know about a past reject either repeats
    the same finding or skips confirming that it was fixed.
    """
    evs, voided = _events_for(issue)
    out = []
    for e in evs:
        if e.get("seq") in voided:
            continue
        if e["class"] not in ("admission_decided", "refutation_attempted", "rework_requested"):
            continue
        if cls and e["class"] != cls:
            continue
        pl = e.get("payload", {}) or {}
        out.append({"seq": e.get("seq"), "class": e["class"], "actor": e.get("actor"),
                    "verdict": pl.get("verdict"),
                    "why": (pl.get("why") or pl.get("reason") or pl.get("note") or "")})
    return out


def _round_fingerprint(evidence, risk):
    """What a re-review is allowed to turn on, beyond the revision itself.

    `review_subject_id` digests the revision (tree, head, integration ref). It deliberately does
    NOT cover the evidence a maker cited or the residual risk a judge recorded — those are payload
    fields, not properties of the tree. So matching on the subject alone suppresses the legitimate
    case: the tree is unchanged because the fix was already committed, and what changed is that the
    claim is now evidenced by a DoD command that was actually run.

    Normalised to a digest so that whitespace and ordering do not manufacture a difference, and so
    a long evidence blob does not have to be held in memory to compare.
    """
    def _norm(value):
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return "\n".join(sorted(" ".join(str(v).split()) for v in value))
        return " ".join(str(value).split())
    return hashlib.sha256(
        (_norm(evidence) + "\x00" + _norm(risk)).encode("utf-8")).hexdigest()


def _prior_verdict_for_subject(issue, role, subject_id):
    """A recorded verdict for this exact review subject, or None.

    `review_subject_id` is a digest of (issue, role, phase, integration_ref, tree) — so an equal
    id means the judge would be looking at the same revision it already judged. Re-dispatching
    then spends a judge run (~100s) and, on the maker side, a CI run to reach a verdict that is
    already recorded. Issue #170 ran 12 CI rounds at a ~5.7 min median; not every round changed
    something a verdict could depend on.

    Only the ledger is consulted. A verdict that never landed there did not happen as far as the
    org is concerned, so it must not suppress a review.
    """
    event = {"gate": "admission_decided", "skeptic": "refutation_attempted"}.get(role)
    if not event or not subject_id:
        return None
    try:
        evs, voided = _events_for(issue)
    except Exception:
        return None                     # unreadable history must not suppress a review
    for e in reversed(evs):
        if e.get("seq") in voided or e.get("class") != event:
            continue
        pl = e.get("payload") or {}
        if pl.get("review_subject_id") != subject_id:
            continue
        return {"seq": e.get("seq"), "verdict": pl.get("verdict"), "actor": e.get("actor"),
                "why": pl.get("why") or "", "evidence": pl.get("evidence"),
                "risk": pl.get("risk") or "",
                "fingerprint": _round_fingerprint(pl.get("evidence"), pl.get("risk"))}
    return None


def _issue_decision_comments(issue, event):
    """The reason for a judgment as written on the Issue (the ledger holds only a digest, so the
    text lives here)."""
    args = ["gh", "issue", "view", str(issue), "--json", "comments"]
    r = _repo()
    if r:
        args += ["--repo", r]
    code, out = _raw(args)
    if code != 0:
        return []
    try:
        cs = json.loads(out).get("comments", [])
    except Exception:
        return []
    return [c.get("body", "") for c in cs if event in (c.get("body") or "")]


def _focused_review_contract(role):
    """The non-negotiable, bounded contract for an Issue-scoped review.

    The Issue already supplies the acceptance criteria, seam, and executable DoD.  Copying the
    complete role charter and generic mutation playbook into every dispatch turns a focused
    review into an unbounded research prompt, and made the configured fast judge time out before
    it could return a verdict.  Keep the invariant here, while leaving the concrete bar in the
    Issue that owns it.
    """
    verdict = "admit/reject/park" if role == "gate" else "survives/refuted"
    return (
        "## Fixed review contract\n"
        "Review only this Issue's acceptance criteria, changed seam contract, and declared DoD. "
        "Do not add unrelated review criteria or redesign the verification method. "
        "A finding outside that boundary is `out_of_scope`, unless it concretely proves an "
        "immediate safety, integrity, security, or release-blocking failure.\n\n"
        f"Return exactly one verdict: `{verdict}`. Cite the concrete command output or file "
        "evidence that decided it; if required evidence is unavailable, return `park` rather "
        "than infer success."
    )


def cmd_verify(a):
    """Assemble and print the material for launching the gate / skeptic. It does not judge."""
    role = a.role
    from review_freshness import (descriptor_status, freshness_policy, integration_ref_policy,
                                  persist_descriptor)
    try:
        from discover import constitution
        _constitution_path = constitution()
    except Exception:
        _constitution_path = None
    _declared, _strict_freshness, _policy_error = freshness_policy(_constitution_path)
    if _policy_error:
        print(f"the review freshness policy is malformed: {_policy_error}", file=sys.stderr)
        return 2
    _ref_declared, _configured_ref, _ref_error = integration_ref_policy(_constitution_path)
    if _ref_error and not getattr(a, "base", None):
        print(f"the integration ref policy is malformed: {_ref_error}", file=sys.stderr)
        return 2
    if _strict_freshness and not getattr(a, "base", None) and not _configured_ref:
        print("strict review freshness does not guess the integration target.\n"
              "  Declare it in constitution.yaml as "
              "`enforcement.judges.integration_ref: origin/main`, or state "
              "`verify --base <ref>` for this run only.", file=sys.stderr)
        return 11
    _integration_ref = getattr(a, "base", None) or _configured_ref
    # What is judged is the tree of **the Issue's worktree** (#101). Silently describing the cwd's
    # tree instead means a verify run from the main checkout mints the same subject (main at
    # ahead=0) for every Issue, which destroys the evidence a joint admission relies on — that both
    # lineages looked at the same thing. Measured: OBS-031/055/071.
    _subject_override = getattr(a, "subject_root", None)
    if _subject_override:
        _subject_cwd = os.path.abspath(_subject_override)
        if not os.path.isdir(_subject_cwd):
            print(f"--subject-root does not exist: {_subject_cwd}", file=sys.stderr)
            return 2
    else:
        _subject_cwd = issue_worktree(a.issue)
        # isdir is not enough: an empty leftover directory, or a symlink to the repo root, sits
        # inside the primary checkout, so git resolves it to the primary and the OBS-071 forgery
        # goes straight through.
        # Confirm it is a real worktree whose toplevel is exactly there (worktree_rooted_at).
        if not _subject_cwd or not worktree_rooted_at(_subject_cwd):
            _expected = _subject_cwd or os.path.join(
                ".orgforge", "wt", f"issue-{a.issue}")
            _hint = ("(the path exists but is not a real worktree — if it is leftover debris, "
                     "clear it with `git worktree prune` and begin again)\n"
                     if _subject_cwd and os.path.lexists(_subject_cwd) else "")
            print(f"there is no worktree for Issue #{a.issue}: {_expected}\n{_hint}"
                  "  The cwd's tree is not used as a substitute — run from the main checkout and "
                  "every Issue mints the same subject, destroying the identity of the judgment "
                  "(#101).\n"
                  "  Create the worktree with `org_cycle begin --issue N`, or, if you mean to "
                  "judge a checkout that is not a worktree, state it with `--subject-root <path>`.",
                  file=sys.stderr)
            return 12
        _actual_branch = issue_worktree_head(a.issue, cwd=_subject_cwd)
        if not _actual_branch or not re.fullmatch(
                rf"feat/issue-{int(a.issue)}(?:-[A-Za-z0-9][A-Za-z0-9._-]*)?",
                _actual_branch):
            print(f"the worktree branch for Issue #{a.issue} does not match the binding "
                  f"convention: "
                  f"{_actual_branch or '(detached)'}.\n"
                  f"  Create a `feat/issue-{int(a.issue)}[-<slug>]` worktree, or state the "
                  "checkout you intend with `--subject-root`.",
                  file=sys.stderr)
            return 12
    _sid, _sparts = review_subject(
        a.issue, role, getattr(a, "phase", None), cwd=_subject_cwd,
        integration_ref=_integration_ref)
    if _subject_override:
        # It does not enter the digest (it is outside SUBJECT_FIELDS), but which checkout was
        # deliberately judged is still printed — an escape hatch is never used silently.
        _sparts = {**_sparts, "subject_root": _subject_cwd}
    _subject_path = persist_descriptor(_sid, _sparts, cwd=_subject_cwd)
    _freshness = descriptor_status({**_sparts, "review_subject_id": _sid}, _subject_cwd)
    if _strict_freshness and not _freshness["ok"]:
        print(f"the review subject is not valid against the current integration target: "
              f"{_freshness['reason']} — {_freshness['detail']}\n"
              f"  subject: {_sid}\n  evidence: {_subject_path}\n"
              "  It does not rebase automatically. Take in the integration target and judge "
              "again through the same verify.",
              file=sys.stderr)
        return 11
    # **Do not run a judge merely to record something.** The subject is determined by git and the
    # acceptance criteria, so it can be answered before the material is assembled.
    if getattr(a, "print_subject", False):
        print(_sid)
        for k, v in _sparts.items():
            print(f"  {k:20}= {v or '(none)'}", file=sys.stderr)
        print(f"  {'descriptor':20}= {_subject_path}", file=sys.stderr)
        return 0
    # **Do not re-judge an unchanged subject.** The subject id already encodes the revision under
    # review, so an existing verdict for the same id means nothing a verdict depends on has moved.
    # Report the recorded one and say what would have to change; do not spend a judge run and a CI
    # round to re-derive it (Issue #182).
    #
    # This suppresses REPETITION, never the independent review itself: a different revision, a
    # different role, or a first-ever review all still dispatch. `--force` overrides deliberately.
    if not getattr(a, "force", False):
        _prior = _prior_verdict_for_subject(a.issue, role, _sid)
        # The message has always promised that new evidence or a changed residual risk earns
        # another review. Until #193 only the revision was actually compared, so re-submitting
        # with real DoD output against an unchanged tree was silently skipped — the tool gave
        # instructions that did not work, which is worse than not offering them.
        #
        # A missing fingerprint on either side dispatches: an unknown is never a skip.
        _now_fp = _round_fingerprint(getattr(a, "evidence", None), getattr(a, "risk", None))
        if _prior and _prior.get("fingerprint") == _now_fp:
            print(f"[{role}] already judged this exact subject — not dispatching again.\n"
                  f"  subject : {_sid}\n"
                  f"  verdict : {_prior['verdict']} (ledger seq {_prior['seq']}, "
                  f"by {_prior['actor']})\n"
                  f"  why     : {' '.join(str(_prior['why']).split())[:300]}\n"
                  f"  To warrant another review, one of these must change: the reviewed head "
                  f"(commit something), the cited evidence, or the stated residual risk. "
                  f"Pass --force to dispatch anyway.", file=sys.stderr)
            print(json.dumps({"skipped": "unchanged_subject", "review_subject_id": _sid,
                              "prior_verdict": _prior["verdict"], "prior_seq": _prior["seq"]},
                             ensure_ascii=False))
            return 0

    charter, cpath = _role_charter(role)
    if charter is None:
        print(f"agents/{role}.md not found (searched: {cpath}).\n"
              f"verify cannot stand without injecting the charter — the bar would depend on "
              f"how each person happens to write it. Check the plugin installation.", file=sys.stderr)
        return 2
    title, body = _issue_body(a.issue)
    if title is None:
        print(f"could not read Issue #{a.issue} (check gh auth and repo resolution).", file=sys.stderr)
        return 3
    # Before launching the judge, run the environment probes that apply **only to this Issue /
    # phase / role**. Nothing is inferred about Docker and the like from process names; the only
    # evidence is the measured result of the argv the org declared.
    phase = getattr(a, "phase", None) or "implement"
    try:
        preflight_ok, preflight_evidence = run_declared_preflights(
            a.issue, role, phase, cwd=os.getcwd())
    except PreflightConfigError as exc:
        print(f"the judge preflight declaration is malformed: {exc}\n"
              "  **if the config cannot be read, or is unbounded, the judge is not started.**", file=sys.stderr)
        return 2
    if not preflight_ok:
        print("the judge was not started: its preflight failed.\n"
              "  Fix the measured result above and re-run the same verify.", file=sys.stderr)
        return 8
    try:
        stable_organ = _stable_organ_invocation()
    except BindingError as exc:
        print(f"the installed-organ binding is not READY: {exc}\n"
              "  Do not substitute another checkout — restart the host session, then verify again.",
              file=sys.stderr)
        return 9
    # **Before launching the judge**, point out statically the MUSTs a read-only judge cannot
    # re-derive. A read_only judge structurally cannot re-derive the kind of MUST that means
    # "actually run it and see it go green", and can only return park — but that only became
    # apparent after launching and waiting minutes to half an hour (measured, #34).
    # A wasted park produces no judgment at all, so say it before the wait. **It does not judge** —
    # it says nothing about whether the MUST is met, only that it lies outside what read-only can
    # do (docs/03 §6.5).
    if _judges_read_only():
        from .rederivability import advisory, unmeasurable_musts
        _unmeasurable = unmeasurable_musts(body)
        _advice = advisory(_unmeasurable, role)
        if _advice:
            print(_advice, file=sys.stderr)
            if getattr(a, "strict_rederivability", False):
                print("  --strict-rederivability was given, so the judge was not started.",
                      file=sys.stderr)
                return 13
    seam = _seam(role, a.issue, title)
    prior = _prior_gate(a.issue) if role == "skeptic" else None
    history = _judgment_history(a.issue)

    ev = {"gate": "admission_decided", "skeptic": "refutation_attempted"}.get(role, "decided")
    verdicts = {"gate": "admit|reject|park", "skeptic": "survives|refuted"}[role]

    out = []
    out.append(f"===== prompt to feed the {role} subagent (#{a.issue}: {title}) =====\n")
    out.append(seam or "(failed to generate the seam contract — check handoff.py)")
    if stable_organ:
        out.append("\n## How to invoke an OrgForge organ (**use only this fixed launcher**)\n")
        out.append(f"`{stable_organ} <organ> [args...]`\n\n"
                   "Do not go looking for a versioned cache path or another development "
                   "checkout. After a plugin update, SessionStart re-binds this launcher to the "
                   "new implementation.")
    if preflight_evidence:
        out.append("\n## Environment preflight before dispatching the judge (measured by the "
                   "supervisor)\n")
        out.extend(preflight_evidence)
        out.append("\n> This is the measured result of a declared command, not something "
                   "inferred from a daemon name or an implementation.")
    # The complete role charter is an organization-wide doctrine, not the per-Issue standard.
    # The latter is fixed in the Issue body below; dispatch only the compact contract by default.
    # ORG_JUDGE_FULL_CHARTER remains an explicit diagnostic escape hatch, never the default.
    out.append("\n" + _focused_review_contract(role))
    if os.environ.get("ORG_JUDGE_FULL_CHARTER") == "1":
        out.append("\n\n## Full role charter (diagnostic override)\n")
        out.append(charter)
    rounds = [h for h in history if h["class"] == "admission_decided"]
    # Take **the larger** of the ledger's count and the Issue's. The failure seen in practice is
    # one side of a double record going missing, so counting the ledger alone would say "the second
    # time" when it is the third. Under-report the count and the gate treats it as near-enough a
    # first judgment, which empties this section of its purpose.
    issue_rounds = _issue_decision_comments(a.issue, "admission_decided")
    if history or issue_rounds:
        n = max(len(rounds), len(issue_rounds)) + 1
        out.append(f"\n## Judgment history for this Issue — **this is judgment number {n}**\n")
        for h in history:
            line = (f"- seq {h['seq']}: {h['class']} = `{h['verdict']}` by {h['actor']}")
            out.append(line + (f"\n    {' '.join(str(h['why']).split())[:300]}" if h["why"] else ""))
        # The ledger holds only a digest, so the text of the reason is pulled from the Issue
        bodies = issue_rounds
        if bodies:
            if len(bodies) > len(rounds):
                out.append(f"\n(the ledger holds only {len(rounds)}, while the Issue has "
                           f"{len(bodies)} — one side of the double record has gone missing)")
            out.append("\n<details><summary>Full text of the previous judgments (Issue "
                       "comments)</summary>\n")
            for b in bodies[-2:]:
                out.append(b[:5000] + "\n\n---\n")
            out.append("</details>")
        out.append("\n> **Checking only whether the previous findings were fixed is not enough.** "
                   "As well as confirming they are fixed, **re-derive** each MUST one at a time — "
                   "whatever the last rework newly broke does not appear on the previous list of "
                   "findings. In practice, fixing a finding has itself opened another hole "
                   "(silencing an alarm, adding a new public surface).\n"
                   "> When you judge, write into --why how you checked this time for what was "
                   "missed last time.")

    out.append(f"\n## The SPEC / MUSTs under verification (body of Issue #{a.issue})\n")
    out.append(body or "(the body is empty — an Issue with no SPEC is itself grounds for reject)")
    out.append("\n## The scope of judgment, and the discipline of a review rally\n")
    out.append(
        "Only a finding tied by concrete evidence to this Issue's SPEC / MUSTs and to the "
        "handoff seam contract may ground a `reject` / `refuted`. Unless it concretely "
        "demonstrates a safety, data-integrity or security problem, or that the work cannot be "
        "released, a finding outside the scope of the change must not stop the judgment — mark it "
        "`out_of_scope` and recommend a follow-up Issue.\n\n"
        "To make the same finding a blocker again, state which of the reviewed head, the "
        "evidence, or the residual risk has changed — at least one must have. Re-raising it with "
        "nothing changed does not demand a new review round. This is not a rule for ignoring "
        "something that was missed; it is a rule against rallying forever on the same evidence.")
    # `prior` (the full text of the gate's latest judgment) is already emitted by the judgment
    # history above. **Emit both and the same text appears twice** — measured, of the skeptic's
    # 457-line prompt, 26 lines of "one move away from 0013" and over 20 lines of "the maker's own
    # report" were duplicated. Prompt length translates directly into reading time (in a field
    # measurement, 21% of the total was a single wait, and part of that was this).
    # So emit prior only when the history was not emitted.
    if prior and not (history or issue_rounds):
        out.append("\n## What the gate has already looked at (to avoid duplication; you are "
                   "under no obligation to endorse it)\n")
        out.append(prior)
    elif role == "skeptic" and not prior:
        out.append("\n## What the gate has already looked at\n(there is no admission_decided "
                   "record for #%d. Check whether you are trying to run the skeptic before the "
                   "gate has admitted)" % a.issue)

    if role == "gate":
        # 6: the tool path could not be resolved and repro_lint had never run once. org_cycle
        # knows where it is, so it fills in the absolute path. For a mechanical refusal layer,
        # "it never ran" is the most dangerous failure of all, since nobody reads the diff.
        out.append("\n## The mechanical bar (**run these commands exactly as given. Not running "
                   "them is grounds for reject**)\n")
        out.append("```")
        out.append(f'{_organ_command(stable_organ, "repro-lint")} check . --phase implement')
        out.append("```")
        out.append("A HOLD (exit 10) means reject. If a path does not resolve, report that — "
                   "\"the tool was missing so it did not run\" is the gravest finding of all: "
                   "the mechanical bar is not in force.")
    if role == "skeptic" and prior:
        # 5: the gate writes into --risk, every time, the areas it did NOT probe this round. In
        # the field, a real bug came out of an area the gate had described as "not hit once". A
        # person was copying this across by hand, so the plumbing carries it instead.
        # **Pass the whole Known-risk section the gate wrote, rather than cutting fragments out
        # with a regex** — the gate has already structured it, and chopping it up produces a run of
        # duplicated fragments nobody can read (which is what the first implementation did).
        # **What to probe is the skeptic's decision.**
        m = re.search(r"\*\*Known risk accepted:\*\*\s*(.+?)(?:\n\n|\Z)", prior, re.S)
        if m:
            body = m.group(1).strip()
            if re.search(r"撃って|当てて|試して|検証して|not exercised|no (?:test|probe|mutation)",
                         body):
                out.append("\n## Areas the gate described as \"not probed this round\" "
                           "(**candidate targets**)\n")
                out.append(body[:3000])
                out.append("\n> Since the gate states outright that it did not probe here, "
                           "**no check has passed over this area even once**. In the field, a real "
                           "bug came out of an area the gate had described as \"not hit once\". "
                           "Whether to probe it is the skeptic's decision — but if you do not, "
                           "write the reason into --risk.")

        # 5: the structure allows an admit as long as --risk is written, so writing one must not
        # be a free pass. A risk the gate wrote itself is surfaced as the first target the skeptic
        # should go after (plumbing: it is only extracted and carried).
        risks = re.findall(r"\*\*Known risk accepted:\*\*\s*(.+?)(?:\n\n|\Z)", prior, re.S)
        if risks:
            out.append("\n## Residual risks the gate wrote itself (**go after these first**)\n")
            out.append(risks[-1].strip())
            out.append("\n> The gate can admit as long as it writes a risk. So that this is not "
                       "a free pass, it is the skeptic's job to establish whether the statement is "
                       "\"a decision taken knowingly\" or \"actually a trap\". If you can break "
                       "it, refuted; if you cannot and confirm it is within what was knowingly "
                       "accepted, say so in --risk and survives.")

    if role == "skeptic":
        out.append("\n## Mutation evidence rule\n")
        out.append("If you mutate, prove baseline → mutate → postcondition → test → restore → "
                   "restore postcondition. A GREEN from a mutation that never landed is not "
                   "evidence. Measure the post-apply state and the post-restore state, and never "
                   "count an unmeasured mutation as evidence.")

    # What the subagent is given is a specification of WHAT TO RETURN. **The recording commands
    # are not included** — the subagent has neither ORG_GITHUB_REPO nor the ledger path, so
    # including them would put the instructions at odds with its permissions. Seven times in the
    # field it produced a judgment and then stopped with "I leave the recording to the supervisor",
    # and once the judgment itself came close to being lost. Recording is the supervisor's job; the
    # subagent concentrates on judging.
    fields = [("verdict", f"exactly one of `{verdicts}`"),
              ("why", "what was weighed against what, and what decided it. Restating the verdict "
                      "does not count"),
              ("evidence", "the commands actually run, and their **actual output** (failures "
                           "included)")]
    if role == "gate":
        fields += [("standard", "the standard applied (the SPEC's MUSTs / the seam contract / "
                                "the mechanical bar)"),
                   ("alternatives", "the options not taken, and why")]
    else:
        fields += [("mutations", "the mutations **whose post-apply state you were able to "
                                 "measure**. Each entry includes `applied: true` and the actual "
                                 "command/output of the postcondition. The reading taken after "
                                 "restoring goes in `restore_postcondition`. A mutation that "
                                 "failed to apply does not belong here — leave it in evidence / "
                                 "risk as unmeasured; that is what stops the next round "
                                 "re-probing the same place"),
                   ("out_of_scope", "defects found **outside the MUSTs** (real, but not something "
                                    "this Issue said it would uphold). They do not count towards "
                                    "`verdict`; return them as \"recommend raising an Issue\" — a "
                                    "real defect is still the next Issue's work. If there are "
                                    "none, say so explicitly.\n"
                                    "    For anything genuinely hard to place, **do not decide it "
                                    "yourself**: write out both readings and return them to the "
                                    "supervisor (carving up scope is the supervisor's call)")]
    fields += [("risk", "holes knowingly left open / failure modes you could not rule out. If "
                        "there are none, say so explicitly")]

    if role == "skeptic":
        out.append("\n**The skeptic's return value is always structured JSON.** Include "
                   "`\"mutations\": []` even when a static judgment used no mutations. A report "
                   "in prose alone is not accepted as a deliverable, because the applying and "
                   "restoring of mutations cannot then be checked mechanically.")

    out.append("\n## What to return (**you decide the judgment; the supervisor records it**)\n")
    for k, desc in fields:
        out.append(f"- **{k}** — {desc}")
    out.append("\n> **You do not need to run any recording command.** You have neither "
               "`ORG_GITHUB_REPO` nor the ledger path. Return the fields above complete, and the "
               "supervisor records them to both the Issue and the ledger in one command.\n"
               "> **Never return them incomplete** — the supervisor then cannot record, and the "
               "judgment is lost (in the field, one judgment came close to being lost without "
               "ever reaching the ledger).\n"
               f"> Note that the ledger **refuses** both a maker admitting its own deliverable and "
               f"a refutation by the maker or by the gate that admitted it — your independence is "
               f"checked mechanically at the moment of recording.")

    # **Fix the identity of what is judged BEFORE the judgment.** If a judge could write the
    # subject, two judgments that looked at different deliverables could declare they looked at the
    # same one and manufacture an agreement (demonstrated by audit: a joint was generated from
    # admits of revision A and revision B). verify observes it; the judge only carries it.
    out.append(f"\n## What is being judged (review_subject_id — **do not change it**)\n\n"
               f"    {_sid}\n\n"
               + "\n".join(f"    {k:20}= {v or '(none)'}" for k, v in _sparts.items())
               + f"\n    {'descriptor':20}= {_subject_path}"
               + "\n\nThe supervisor puts this id into the record. **It is not a value you "
                 "produce.** The judge of the other lineage has been given the same id, and "
                 "**no admission is generated unless the two ids match** — two passes that looked "
                 "at different revisions are not an agreement.")

    _lineage, _hcfg = _judge_lineage(role)
    # Under cross-harness, stdout is where the **judgment** goes (in a form that can be handed
    # straight to intake). The material is diverted to stderr — still readable by the supervisor.
    print("\n".join(out), file=sys.stderr if _lineage == "cross-harness" else sys.stdout)
    # For the supervisor (stderr) — the command that pours in what the subagent returned.
    # **It never fills in the judgment.**
    print(f"\n[review_subject_id] {_sid}\n"
          f"  Pass this value to --subject when recording. **Never have the judge produce it.**",
          file=sys.stderr)
    print(f"\n===== The command you (the supervisor) run — fill in what {role} returned =====\n"
          f'{_organ_command(stable_organ, "github-sync")} decide --issue {a.issue} '
          f"--event {ev} \\\n"
          f"  --verdict <the verdict {role} returned> --by {role} \\\n"
          f"  --why \"<{role}'s why, verbatim>\" \\\n"
          f"  --evidence \"<{role}'s evidence, verbatim>\" \\\n"
          f"  --claimed \"<what {role} reported. Keep the qualifiers — 'not present in …', "
          f"'unmeasured' — do not drop them>\" \\\n"
          f"  --verified \"<what **you ran yourself** and confirmed. The command and its "
          f"output>\" \\\n"
          + (f"  --standard \"<...>\" --alternatives \"<...>\" \\\n" if role == "gate" else "")
          + f"  --risk \"<...>\"\n"
          f"(since 0.21.0, `decide` writes to **both** the Issue and the ledger in one command. "
          f"It goes through the ledger first, so if control refuses, nothing is recorded on the "
          f"Issue either)\n", file=sys.stderr)
    # (1) On a reject/refuted, also record that rework was commissioned. **Put it in the same
    # place as the record of the judgment** — the sequence is "receive the judgment → verify →
    # decide → commission → record", and once the commissioned subagent's notification arrives the
    # recording gets washed away. Commission it with the recording command already in front of you
    # and the order reverses.
    # In operation, many rejects/refuteds had no rework_requested in the ledger at all, and show's
    # warning fell silent.
    bad = "reject" if role == "gate" else "refuted"
    print(f"===== If it was {bad} — also record the commissioning of rework =====\n"
          f'{_organ_command(stable_organ, "org-cycle")} rework --issue {a.issue} '
          f"--after {bad} --by <your role> \\\n"
          f'  --reason "<in one line, which of {role}\'s findings the maker is to fix>" '
          f"--round {len(rounds) + 1 if 'rounds' in dir() else '<which round this is>'}\n"
          f"(without this, `show`'s rework warning falls silent — the material never enters the "
          f"ledger, so the threshold is never reached. **A tool does not count what it cannot "
          f"count**)\n", file=sys.stderr)
    # The headless form (Codex / claude -p). **If the lineages are to differ, run it on a different
    # harness** — role-settings.yaml declares family-B for the skeptic (a different line from the
    # gate), but as a subagent on the same harness that becomes inherit, and it shares the blind
    # spots of the same base model (docs/03 §3).
    # Read `enforcement.judges.lineage` from the constitution. **The default is same-harness** —
    # presuppose another harness's contract, CLI and authentication and the org stops working in
    # any environment that does not have them. Adding a layer is a choice, not a premise.
    _schema = _verdict_schema(role)
    _headless_rc = 0          # same-harness has no child to fail
    if _lineage == "cross-harness":
        if not os.path.isfile(_schema):
            print(f"judges.lineage = cross-harness, but there is no output schema for {role} "
                  f"(looked in: {_schema}). Dispatch to another harness without a schema and "
                  f"prose that came back missing its verdict cannot be caught structurally. "
                  f"**Put the schemas in place before separating the lineages.**",
                  file=sys.stderr)
            return 2
        # **Two judges run.** The subagent on this harness (its material is on stderr above) and
        # the headless one on another harness (launched below). If either says reject/refuted, the
        # result is reject — fall to the stricter side, not to an AND. Measured (the authorisation
        # hole in #11, the missing Testing Library in #42):
        # **in both cases the stricter side was the right one**. Make it a majority vote and a 1:1
        # cannot be settled, which hands the decision back to the supervisor's discretion.
        rc = _run_headless(role, a.issue, "\n".join(out), _hcfg, _schema, stable_organ)
        _headless_rc = rc
        print(f"\n===== There are two judges (judges.lineage = cross-harness) =====\n"
              f"  1. the {role} subagent on this harness — hand it the material above, verbatim\n"
              f"  2. the {role} on another harness — " +
              ("the JSON above (stdout) is its judgment" if rc == 0
               else "**it could not be launched. No judgment was obtained**") + "\n"
              f"  **If either one says {bad}, treat it as {bad}.** The shape requires agreement, "
              f"so recording an admit takes an admit from both (decide checks this).\n"
              f"  If the judgments disagree, record the disagreement itself —\n"
              f'    {_organ_command(stable_organ, "ledger")} append '
              f"--class judges_disagreed --actor <your role> \\\n"
              f"      --payload '{{\"issue\": {a.issue}, \"role\": \"{role}\", "
              f"\"same_harness\": \"<verdict>\", \"cross_harness\": \"<verdict>\"}}'\n"
              f"  (a disagreement is not a malfunction — it is **the point of separating the "
              f"lineages**. Do not erase it; count it)",
              file=sys.stderr)

    print(f"— Hand this output to the {role} subagent. Paste it into the body, or write it to a "
          f"file and reference that\n"
          f"  (with no contract in the body, the seam guard reads the file the prompt points at "
          f"and verifies it itself).\n"
          f"The plumbing ends here. The verdict / why / risk are decided by {role}.",
          file=sys.stderr)
    # **A cross-harness dispatch that failed must not exit 0.** `_run_headless` already diagnoses an
    # empty or malformed child result on stderr, but that diagnosis was discarded here: verify
    # returned 0 regardless, so a supervisor reading the exit code saw success, printed the handoff,
    # and moved on with no verdict recorded. In the field this read as "the child completed and the
    # verdict vanished" (#201) — the verdict never existed, and the only signal that said so was
    # thrown away one frame above the caller.
    #
    # Same-harness runs keep returning 0: there is no child to fail, and the subagent material on
    # stderr IS the deliverable.
    return _headless_rc




# The elements a report must carry, per role, to count as a deliverable at all.
# **A subagent's turn sometimes ends partway through the work** (several times in a short period, in
# operation). The status comes back completed and the result is a single declarative sentence such
# as "Now the key attack:". Resuming it with SendMessage carried on and ran to completion, so the
# agent had not died — the turn ended before the report took the shape of a deliverable.
#
# **The dangerous shape is the one nobody notices.** Cut off at "MUST 2 was defended", it could be
# read as a verdict and admitted — the thing this org keeps catching, "stating something unverified
# as though it had been verified", arriving this time by way of **a truncated report**.
_INTAKE = {
    "skeptic": [
        ("verdict", r"\b(survives|refuted)\b", "the verdict is neither survives nor refuted"),
        ("evidence", r"(npm |npx |git |psql|python3|node |pytest|exit=|passed|failed)",
         "there is no trace of anything actually being run (a command, its output)"),
    ],
    "gate": [
        ("verdict", r"\b(admit|reject|park)\b", "the verdict is none of admit, reject or park"),
        ("evidence", r"(npm |npx |git |psql|python3|node |pytest|exit=|passed|failed)",
         "there is no trace of anything actually being run (a command, its output)"),
    ],
    "maker": [
        ("commit", r"\b[0-9a-f]{7,40}\b", "there is no commit hash"),
        ("dod", r"(npm |npx |pytest|passed|failed|Tests?\s)",
         "there is no measured output from the DoD command"),
    ],
}
# Wording that tends to appear in a report cut off partway. **Never grounds on its own** — if the
# required elements are all present, a "Now …" in the middle still means it ran to completion. It
# only raises confidence when it coincides with something missing.
_TRUNCATED = (r"^\s*(now|next|then)\b", r"(しましょう|します)。?\s*$",
              r"(let me|i'll|i will)\b.*:$", r":\s*$")



def _run_headless(role, issue, material, cfg, schema, stable_organ=None):
    """Actually launch the judge on another harness and bring back a structured verdict.

    **Do not merely print guidance.** If the supervisor gets to choose whether to run it, we are
    back to the shape where **the thing being checked decides whether the check is called**
    (docs/11). In an org that declared cross-harness, the plumbing extends to verify launching it
    itself and producing the result.

    The judge runs read-only. **The other harness's guardrails are unverified**, so if it cannot
    write, it falls to the safe side whatever that harness happens to permit.
    """
    cfg = cfg or {}
    cli = str(cfg.get("cli") or "codex")
    model, effort = cfg.get("model"), cfg.get("effort")
    exe = shutil.which(cli)
    if not exe:
        print(f"judges.harness.{role}.cli = {cli!r} is not on PATH.\n"
              f"  Install and authenticate it, or set judges.lineage back to "
              f"same-harness in the constitution.", file=sys.stderr)
        return 4

    # **Never use a fixed path.** With /tmp/orgforge-{role}-{issue}.json, concurrent runs tread on
    # the same file and the next run reads stale output from a failed one (raised in audit). Put a
    # digest of the material into the name, so that only a re-run on the same material lands on the
    # same file.
    _mat = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    _dir = os.path.join(tempfile.gettempdir(), "orgforge-judge")
    os.makedirs(_dir, exist_ok=True)
    out_json = os.path.join(_dir, f"{role}-{issue}-{_mat}.json")
    if os.path.exists(out_json):
        os.remove(out_json)          # never read last time's debris as a judgment
    if cli == "codex":
        cmd = [exe, "exec", "--sandbox", "read-only"]
        if model:
            cmd += ["-m", str(model)]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        cmd += ["--output-schema", schema, "-o", out_json, material]
    elif cli == "claude":
        # Claude Code provides --json-schema. Asking for JSON in the prompt body alone gets prose
        # back and makes intake impossible, so the structure is enforced at the CLI, as with Codex.
        # Claude Code's validator does not resolve the Draft 2020-12 meta-schema URI, so what is
        # passed to the CLI is the same object schema with only that declaration removed.
        _claude_schema = json.dumps({k: v for k, v in json.load(open(schema, encoding="utf-8")).items()
                                     if k != "$schema"}, ensure_ascii=False)
        cmd = [exe, "-p", material + "\n\n## The shape to return\n"
               "Return **only** JSON matching this schema exactly (no prose before or after):\n"
               + _claude_schema,
               "--output-format", "json", "--json-schema", _claude_schema]
        if model:
            cmd += ["--model", str(model)]
        if effort:
            cmd += ["--effort", str(effort)]
    else:
        print(f"judges.harness.{role}.cli = {cli!r} is unsupported (codex | claude).", file=sys.stderr)
        return 2

    # **A read-only judge structurally cannot admit a MUST that means "run it and see it go
    # green".** Measured: #34 returned park, on the grounds that it was statically sound but that
    # "100 consecutive greens" could not be re-derived inside a read-only sandbox. The park itself
    # is correct behaviour (do not admit what you cannot measure), but discovering it only after
    # running the judgment is waste — so **say it up front**.
    print(f"[{role}] the judge runs read-only (judges.read_only). The other harness's guardrails "
          f"are unverified, so if it cannot write, it falls to the safe side.\n"
          f"  Note that **a MUST of the \"run it and see it go green\" kind cannot be re-derived, "
          f"and becomes a park** (running tests repeatedly, reaching a real DB, building).\n"
          f"  If such a MUST carries the weight of the admission, the supervisor should measure it "
          f"before the judgment and hand it over as evidence.", file=sys.stderr)
    print(f"[{role}] launching {cli} read-only"
          + (f"（model={model}" + (f", effort={effort}" if effort else "") + "）" if model else "")
          + " — a response can take several minutes …", file=sys.stderr)
    try:
        # Close stdin. codex exec tries to read from it and hangs when there is no terminal
        # (measured).
        # A timeout catches a HUNG child; it is not a budget for normal work. Measured on a
        # realistic subject (compact contract + ~6k of target code, gpt-5.6-terra/medium):
        #
        #     median 46.4s, max 86.9s, spread 32–87s across four runs of the SAME prompt
        #
        # 120s was 1.4x that maximum — thin, because the run-to-run spread is nearly 3x on its own,
        # so a larger subject or a slower moment lands on the cutoff. Since 2.9.1 a timed-out
        # dispatch exits non-zero, so a cutoff is visible rather than silently passing as success;
        # but a killed judgment still costs the round, the tokens, and reads to the caller exactly
        # like a judge that produced nothing (#201, #203).
        #
        # Trimming the material does NOT buy headroom here: cutting it 68% (2.6.0) changed the
        # median by nothing measurable. Runtime is dominated by reading the subject and deciding.
        timeout = int(cfg.get("timeout_seconds") or os.environ.get("ORG_JUDGE_TIMEOUT",
                                                                   str(JUDGE_TIMEOUT_DEFAULT)))
        pr = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[{role}] {cli} timed out after {timeout}s. Measured normal range on a realistic "
              f"subject: median ~46s, max ~87s — so this is either a genuinely hung child or a "
              f"subject larger than what was measured. Raise it with ORG_JUDGE_TIMEOUT before "
              f"concluding the judge is broken.",
              file=sys.stderr)
        return 5
    if pr.returncode != 0:
        print(f"[{role}] {cli} exited with {pr.returncode}:\n"
              f"{(pr.stderr or pr.stdout or '')[-1200:]}", file=sys.stderr)
        return 6

    raw = None
    if os.path.isfile(out_json):
        raw = open(out_json, encoding="utf-8").read()
    elif cli == "claude":
        # Open the `claude -p --output-format json` envelope. It carries the answer twice:
        #
        #   structured_output : dict — the schema-validated object that --json-schema produced
        #   result            : str  — the same content, rendered for display
        #
        # Take structured_output. Reading `result` and re-parsing it threw away a validated
        # object in order to recover it from a string, which fails the moment the model wraps
        # the JSON in any prose: the verdict was produced but never collected, so a review that
        # really ran looked like it returned nothing. Measured on the installed CLI —
        # structured_output is a dict, result is its stringification.
        try:
            env = json.loads(pr.stdout) or {}
        except Exception:
            env = None
        if isinstance(env, dict):
            structured = env.get("structured_output")
            if isinstance(structured, (dict, list)):
                raw = json.dumps(structured, ensure_ascii=False)
            else:
                # An older CLI has no structured_output. Fall back to `result`, but do NOT fall
                # back to the raw envelope: `{"result": ""}` would otherwise be handed on as if
                # the envelope itself were the verdict, and an empty answer would read as success.
                raw = env.get("result") or ""
            # An envelope can report an error while still carrying text. Say so rather than
            # letting a degraded answer look like a clean verdict.
            if env.get("is_error") or env.get("api_error_status"):
                print(f"[{role}] the {cli} envelope reports an error "
                      f"(is_error={env.get('is_error')!r}, "
                      f"api_error_status={env.get('api_error_status')!r}, "
                      f"stop_reason={env.get('stop_reason')!r}). Treat any verdict below as "
                      f"unreliable.", file=sys.stderr)
        else:
            raw = pr.stdout
    if not raw or not raw.strip():
        # **fail-closed does not change** — with no judgment obtained, no admission is generated.
        # What changes is ending up none the wiser (Issue #166). In the field, `claude -p` returned
        # exit 0 with both stdout and stderr empty, leaving nothing to distinguish the CLI having
        # crashed, authentication having expired, or it having quietly ended midway through
        # tool-use.
        #
        # Emit the material only. **It does not judge** — whether to park or retry is the
        # supervisor's decision.
        # The material itself is not printed (that would leak the very thing under judgment); only
        # its length and where the output should have gone.
        _diag = [f"[{role}] {cli} returned nothing. No judgment was obtained (so no admission is "
                 f"generated).",
                 f"  exit={pr.returncode}  stdout={len(pr.stdout or '')}B  "
                 f"stderr={len(pr.stderr or '')}B  material={len(material)}B",
                 # Print **the flags only**. Slicing by position, as in `cmd[:3]`, leaks the very
                 # thing under judgment into the diagnostic on the claude path (`-p <material>`) —
                 # a test caught exactly that. For a long value, neither its name nor its contents
                 # is printed.
                 f"  invocation: {shlex.quote(os.path.basename(cmd[0]))} "
                 + " ".join(shlex.quote(c) for c in cmd[1:]
                            if c.startswith("-") and len(c) < 40)
                 + f" …({len(cmd)} arguments; the body and any long values are withheld)"]
        if cli == "codex" and not os.path.isfile(out_json):
            _diag.append(f"  the --output-schema destination was never created: {out_json}")
        _err = (pr.stderr or "").strip()
        if _err:
            _diag.append("  the tail of stderr:\n    " + "\n    ".join(_err.splitlines()[-5:]))
        else:
            _diag.append("  stderr is empty too. Check the CLI's authentication, model name and "
                         "sandbox settings:")
            _diag.append(f"    {cli} " + ("exec --sandbox read-only " if cli == "codex" else "-p ")
                         + "'Reply with exactly: OK' </dev/null")
        _diag.append("  Before retrying on the same material, confirm the subject with "
                     "`--print-subject` (a judgment that looked at a different revision does not "
                     "count as agreement).")
        print("\n".join(_diag), file=sys.stderr)
        return 7

    print(raw)                                  # to stdout, for the supervisor to read and for
                                                # intake to consume as-is
    print(f"\n[{role}] brought back the judgment from the other harness ({cli}"
          + (f" / {model}" if model else "") + f"). **It has not been recorded yet.**\n"
          f"  Check it on its contents:\n"
          f'    {_organ_command(stable_organ, "org-cycle")} intake --issue {issue} '
          f"--role {role} --report {out_json if os.path.isfile(out_json) else '-'}\n"
          f"  Record it once it passes (the verdict / why belong to whoever judged; the "
          f"supervisor does not rewrite them).",
          file=sys.stderr)
    return 0


def _judges_read_only():
    """Read `enforcement.judges.read_only` (default True — matching the template's declaration).

    This only ever branches **whether the advice is printed**. It affects neither the judgment nor
    whether anything launches, so when it cannot be read we treat it as read-only, i.e. fall to the
    side that prints the advice. Advice does not obstruct a launch, so nothing is lost by falling
    that way (fail-closed is needed on the `_judge_lineage` side).
    """
    env = os.environ.get("ORG_JUDGE_READ_ONLY")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no")
    try:
        sys.path.insert(0, HERE)
        from discover import constitution
        path = constitution()
        if not path or not os.path.isfile(path):
            return True
        import yaml
        with open(path, encoding="utf-8") as f:
            c = yaml.safe_load(f) or {}
        j = ((c.get("enforcement") or {}).get("judges") or {})
        return bool(j.get("read_only", True))
    except Exception:
        return True


def _judge_lineage(role):
    """Read `enforcement.judges` from the constitution. Returns (lineage, harness-cfg).

    **The default is `same-harness`.** Presuppose another harness and the org stops working in any
    environment that lacks its contract, CLI or authentication. Lining up several lineages is a
    choice to add another slice of the Swiss cheese — not a premise for the org to exist at all.

    **ただし読めないときは止める（fail-closed）。** 0.32.0 は例外を握りつぶして
    `same-harness` を返していた — cross-harness を宣言した org で YAML が壊れていると、
    **強い安全モードが黙って通常モードに落ちる**。判定の血統が分かれていないことに
    気づく経路が無くなるので、これは沈黙してはいけない側の失敗である。
    """
    env = os.environ.get("ORG_JUDGE_LINEAGE")
    if env:
        return env.strip(), None
    try:
        sys.path.insert(0, HERE)
        from discover import constitution
        path = constitution()
    except Exception as e:
        raise SystemExit(f"constitution の場所を解決できない: {e}\n"
                         "  judges.lineage を読めないまま judge を起動すると、cross-harness を"
                         "宣言した org が黙って同一血統で判定する。")
    if not path or not os.path.isfile(path):
        return "same-harness", None        # constitution が無い = 宣言が無い
    try:
        import yaml
    except Exception:
        raise SystemExit("PyYAML が無いので constitution を読めない。\n"
                         "  cross-harness の宣言が黙って消えることは許さない:\n"
                         "    python3 -m pip install pyyaml")
    try:
        with open(path, encoding="utf-8") as f:
            c = yaml.safe_load(f) or {}
    except Exception as e:
        raise SystemExit(f"constitution.yaml を解析できない: {e}\n  ファイル: {path}\n"
                         "  **設定を読めないなら止める。**")
    if not isinstance(c, dict):
        raise SystemExit(f"constitution.yaml が map ではない（{type(c).__name__}）: {path}")
    j = ((c.get("enforcement") or {}).get("judges") or {})
    declared = str(j.get("lineage") or "same-harness").strip()
    sys.path.insert(0, HERE)
    from harness import active_harness, effective_lineage, opposite_harness
    lineage = effective_lineage(declared)
    if lineage == "same-harness":
        return lineage, None

    harness = j.get("harness") or {}
    if not isinstance(harness, dict):
        raise SystemExit("judges.harness が map でない。cross-harness の経路を選べない。")
    missing = [name for name in ("claude", "codex")
               if not isinstance(harness.get(name), dict)]
    if missing:
        raise SystemExit("judges.harness に claude / codex 両方の map が必要（不足: "
                         + ", ".join(missing) + "）。")

    primary = active_harness()
    secondary = opposite_harness(primary)
    cfg = harness[secondary].get(role)
    if not isinstance(cfg, dict):
        raise SystemExit(f"judges.harness.{secondary}.{role} が必要。\n"
                         "  cross-harness の役割を暗黙の CLI に委ねない。")
    cli = str(cfg.get("cli") or "").strip()
    if cli != secondary:
        raise SystemExit(f"主系 {primary!r} の別血統 CLI は {secondary!r} でなければならないが、"
                         f"{cli!r} が指定されている。\n"
                         "  同じハーネスを2回走らせても cross-harness にはならない。")
    return lineage, cfg


def cmd_intake(a):
    """subagent が返した報告が成果物の形になっているかを検査する。

    **判定はしない。** verdict の中身も、その妥当性も見ない — 見るのは「役割として要求される
    欄が埋まっているか」だけである。埋まっていなければ「報告が不完全。再開させること」と言う。
    いまは監督が目で気づくかどうかに賭かっている。
    """
    text = a.report
    if a.report == "-":
        text = sys.stdin.read()
    role = a.role
    checks = _INTAKE.get(role)
    if not checks:
        print(f"役割 {role!r} の受け入れ検査は定義されていない"
              f"（定義済み: {', '.join(sorted(_INTAKE))}）。", file=sys.stderr)
        return 2

    # 構造化された返り値（Codex の --output-schema など）なら、**正規表現ではなく構造で見る**。
    # スキーマが形を保証していても、`out_of_scope` に「無し」と書くべき欄が空文字だったり、
    # verdict が enum 外の値だったりはしうる。JSON なら確実に読めるので、そちらを優先する。
    as_json = None
    try:
        cand = json.loads(text)
        if isinstance(cand, dict):
            as_json = cand
    except Exception:
        pass

    if as_json is not None:
        missing = []
        for k, pat, why in checks:
            v = as_json.get(k)
            if k == "verdict":
                ok = isinstance(v, str) and re.fullmatch(pat.replace(r"\b", ""), v.strip(), re.I)
            else:
                ok = bool(str(v).strip()) if not isinstance(v, (list, dict)) else bool(v) or v == []
            if not ok:
                missing.append((k, why + "（構造化された返り値の該当欄が空 / 値が不正）"))
        # スキーマが required にしていても、値が空文字なら埋まっていない
        for k in ("why", "evidence"):
            v = str(as_json.get(k) or "").strip()
            if k in dict((c[0], 1) for c in checks) and len(v) < 20 and (k, ) not in [(m[0],) for m in missing]:
                missing.append((k, "構造化された返り値の該当欄が短すぎる（20文字未満）"))
        if role == "skeptic":
            mutations = as_json.get("mutations")
            if not isinstance(mutations, list):
                missing.append(("mutations", "mutations が array ではない / 欠落している"))
                mutations = []
            for index, mutation in enumerate(mutations):
                if not isinstance(mutation, dict):
                    missing.append(("mutations", f"mutation[{index}] が object ではない"))
                    continue
                if mutation.get("applied") is not True:
                    missing.append(("mutations", f"mutation[{index}] の適用成立が確認されていない"))
                post = mutation.get("postcondition")
                if not isinstance(post, str) or len(post.strip()) < 10:
                    missing.append(("mutations", f"mutation[{index}] に適用後状態の実測が無い"))
                restored = mutation.get("restore_postcondition")
                if not isinstance(restored, str) or len(restored.strip()) < 10:
                    missing.append(("mutations", f"mutation[{index}] に復元後状態の実測が無い"))
    else:
        missing = [(k, why) for k, pat, why in checks
                   if not re.search(pat, text, re.I | re.M)]
        if role == "skeptic":
            # Claude's print mode cannot enforce --output-schema.  Free prose cannot prove an
            # empty list: a decoy `mutations: []` line may coexist with mutation claims elsewhere.
            # Require the structured contract for every skeptic report.  Static proofs represent
            # the empty list in JSON, which keeps both harness paths on the same intake boundary.
            missing.append(("mutations", "skeptic 報告は常に構造化 JSON が必要。"
                            "静的判定も `\"mutations\": []` を含む JSON で返す"))
    truncated = [p for p in _TRUNCATED if re.search(p, text.strip(), re.I | re.M)]

    print(f"— intake #{a.issue} ({role}) — {len(text)} 文字")
    if not missing:
        print(f"  ✓ 必須要素は揃っている（{', '.join(k for k, _, _ in checks)}）")
        if truncated:
            print(f"  · 途中で切れたように読める語があるが、必須要素は揃っているので"
                  f"完走とみなす（{truncated[0]}）")
        return 0

    print(f"  ✗ **報告が不完全 — 再開させること。**", file=sys.stderr)
    for k, why in missing:
        print(f"      {k}: {why}", file=sys.stderr)
    if truncated:
        print(f"    作業の途中で turn が終わった可能性が高い"
              f"（「{text.strip()[-60:]}」で終わっている）。", file=sys.stderr)
    print(f"    SendMessage で続きを促すこと。**この報告を判定として読まないこと** — "
          f"実地では「Now the key attack:」の1文だけが返り、status は completed だった。\n"
          f"    途中の1文を verdict として読めば、確かめていないものを admit する。\n"
          f"    [intake] INCOMPLETE issue={a.issue} role={role} "
          f"missing={','.join(k for k, _ in missing)} exit=10",
          file=sys.stderr)
    # 最後の1行は**機械が拾える形**にしてある。`| tail` や `| grep` を通すとシェルの終了コードは
    # 最後のコマンドのものになり、この 10 は消える（実地でそう観測された — 実装は 10 を返して
    # いたが、観測経路が 0 を見せた）。パイプで読む経路でも判定できるように、
    # `INCOMPLETE` を出力に置く。
    return 10


def cmd_rework(a):
    """reject / refuted を受けて rework を発注したことを記録する。

    **専用コマンドが無かったことが記録漏れの一因である。** 運用で reject/refuted の多くに対し
    `rework_requested` が記録されていなかった（4回 reject されて記録0件の Issue もあった）。監督は
    `ledger.py append --class rework_requested --payload '{...}'` を手で組む必要があり、
    しかも発注は「判定を受け取る → 検証 → decide → **発注** → 記録」の順で、発注した subagent の
    通知が来ると記録が流れる。

    副作用として `show` の rework 警告（0.26.0）が沈黙していた — 台帳に材料が無いので閾値に
    届かない。**道具の誤検出ではなく、監督が材料を入れていなかった。**
    """
    payload = {"deliverable": str(a.issue), "issue": a.issue,
               "verdict": "rework", "reason": a.reason,
               "from_verdict": a.after, "to_role": a.to or "",
               "round": str(a.round)}
    # 死因の根の分類（Issue #104）。再発検出（learning.py repeats）は root の一致で数える —
    # 記録時に分類されなければ、この rework が同根の再発でも検出器は文字列一致でしか見えない。
    # 語彙は learning.DEATH_ROOTS が単一の情報源（schema の enum とはテストが突き合わせる）。
    root = (getattr(a, "root", None) or "").strip()
    if root:
        sys.path.insert(0, HERE)
        from learning import DEATH_ROOTS
        if root not in DEATH_ROOTS:
            print(f"rework: --root {root!r} は死因の根の語彙に無い。許される値:\n"
                  + "\n".join(f"  {k:<24}{v}" for k, v in DEATH_ROOTS.items()),
                  file=sys.stderr)
            return 2
        payload["root"] = root
    rc = _execute([
        # GitHub を先に作業可能な状態へ戻す。ここが失敗したら台帳へ rework を記録しない —
        # CLOSED/COMPLETED のまま ledger だけ次周へ進む分岐が実地で起きた。
        (f"stage ready / reopen → #{a.issue}",
         lambda: _gh_sync("stage", "--issue", str(a.issue), "--stage", "ready")),
        (f"rework_requested #{a.issue}（{a.after} を受けて）",
         lambda: _ledger("append", "--actor", a.by, "--class", "rework_requested",
                         "--natural-key", f"rework-{a.issue}-{a.round}",
                         "--payload", json.dumps(payload, ensure_ascii=False))),
        (f"log → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "progress_recorded",
                          "--detail", f"rework を発注（{a.after} を受けて）: {a.reason}",
                          "--command", f"org_cycle.py rework --issue {a.issue} "
                                       f"--after {a.after} --round {a.round}",
                          "--result", a.reason[:2000])),
    ], f"record rework #{a.issue}")
    if rc == 0:
        print(f"\n  Issue は OPEN / ready に戻り、`show --issue {a.issue}` の rework 警告も"
              f"正しく数えられる（台帳に材料が入っていないと、閾値に届かず沈黙する）。")
    return rc


def cmd_record(a):
    """2: 済んだ判定を遡って台帳に記録する。

    統合の判定がどこにも残らないことがある（`integration_admitted` が0件）。しかも「マージ後の
    10件失敗のうち8件は worktree 走査の偽陽性で、の欠陥はゼロ」という切り分けの判断が
    記録から消えていた。**その切り分けこそ後から最も知りたい情報**なので、遡って残せる口を開ける。

    追記型なので過去は書き換わらない — `backfilled: true` を付けて、後から足した記録だと
    分かるようにする（実時点の記録と混ぜない）。
    """
    payload = {"verdict": a.verdict, "issue": a.issue, "deliverable": str(a.issue),
               "backfilled": True, "why": a.why}
    if a.event == "integration_admitted":
        # base を消費するのはこのイベントだけなので、必要になった時だけ解決する（#106）。
        from ._core import resolve_integration_base
        base, base_err = resolve_integration_base(getattr(a, "base", None))
        if base_err:
            print(f"integration_admitted の統合先が決まらない（#{a.issue}）:\n{base_err}",
                  file=sys.stderr)
            return 2
        payload.update({"integration_branch": base, "deliverables": [str(a.issue)],
                        "combined_ci_ref": a.command or "(記録なし)"})
    if a.result:
        payload["result"] = a.result[:4000]
    steps = [
        (f"{a.event}（backfill）を記録",
         lambda: _ledger("append", "--actor", a.by, "--class", a.event,
                         "--natural-key", f"backfill-{a.event}-{a.issue}",
                         "--payload", json.dumps(payload, ensure_ascii=False))),
        (f"log → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", a.event,
                          "--event-id", f"backfill-{a.event}-{a.issue}",
                          "--detail", f"[遡って記録] {a.why}",
                          "--command", a.command or "(当時のコマンドは記録に残っていない)",
                          "--result", a.result or a.why)),
    ]
    return _execute(steps, f"backfill {a.event} #{a.issue}")
