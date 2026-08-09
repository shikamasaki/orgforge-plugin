"""Recording — work logs and the record of a judgment.

**Both the Issue and the ledger are written by one command.** A structure where a person types
twice produces one side going missing (three times in the field). The ledger goes first — if
control refuses, stop before creating a record visible from outside. An empty, restated or padded
`--why` is refused."""

import hashlib
import json
import os
import re
import subprocess
import sys

from ._core import (
    HERE,
    _already_logged,
    _stable_key,
    gh,
)


# Milestones: without "what was done" recorded here, there is no way to reconstruct it later.
# Interim progress (progress_recorded) may be logged lightly, but a cycle's milestone is an audit
# point, so real output is required.
_LOG_MILESTONES = ("cycle_started", "cycle_completed", "phase_admitted", "integration_admitted",
                   "result_deployed", "handback_opened")


def _log_defect(a):
    """Check whether a work log can be reconstructed from. None means it passes.

    `decide` refuses an empty, restated or padded --why, while `log` checked --detail not at all.
    The result showed up in measurement: within one Issue, judgments ran 3,506–5,894 characters and
    work logs 276–473. **Only the side with a check got thicker.** Following a prose instruction is
    a person's job; enforcing a required argument is a tool's — so the same enforcement applies
    here.
    """
    if a.event not in _LOG_MILESTONES:
        return None
    if not getattr(a, "command", None):
        return ("--command is required for a milestone log. Give the command you actually ran, "
                "verbatim.\n"
                "  Not \"ran the tests\" but `npm test` — a form a stranger can re-run.")
    if not getattr(a, "result", None):
        return ("--result is required for a milestone log. Paste what that command actually "
                "returned,\n"
                "  failures included. A record of successes only is fiction, and the failed "
                "attempt carries the most information.")
    res = str(a.result)
    if len(res.encode("utf-8")) < 24:
        return ("--result is too short to be real output. Paste what came back, "
                "not \"it passed\".")
    words = re.findall(r"[^\W\d_]+", res.lower(), flags=re.UNICODE)
    filler = {"ok", "okay", "done", "fine", "good", "green", "pass", "passed", "passes",
              "success", "succeeded", "yes", "worked", "works", "完了", "成功"}   # noqa: RUF001
                                                                # (the last two match what a
                                                                # Japanese-writing agent types)
    if words and not [w for w in words if w not in filler]:
        return ("--result is only a paraphrase of \"it passed\". Paste the real output — test "
                "counts, errors, the diff.")
    return None


def _append_progress_receipt(a):
    """Leave a receipt in the ledger for the work log written on the Issue.

    `log` only commented on the Issue and wrote nothing to the ledger. In the field that produced
    seven work records on an Issue against **zero** `progress_recorded`. It is the same shape as the
    refutation record closed on another Issue — one side of a double record going missing — and its
    consequences are concrete:

      · the work_in_progress view reads progress_recorded, so `/org-resume` cannot resume
      · the board cannot see progress either
      · from the ledger alone, no work was ever recorded

    The ledger is not the SSoT (that is the code plus the domain model), but **resuming from an
    interruption and auditing are the ledger's job**, so an empty one takes the whole resume
    mechanism down.

    A failure here still lets log itself succeed — the comment is already posted, and reporting
    "the log failed" because a receipt did not attach sends a person to double-post a record that
    is in fact already there.
    """
    payload = {"role": getattr(a, "by", None) or "org", "candidate_id": a.event_id or "",
               "phase": a.phase or "", "milestone": a.event,
               "done_so_far": (a.detail or "")[:2000],
               "next_step": getattr(a, "next_step", None) or "",
               "blocked_by": getattr(a, "blocked_by", None) or "",
               "issue": a.issue}
    if getattr(a, "command", None):
        payload["command"] = a.command
    if getattr(a, "result", None):
        payload["result"] = str(a.result)[:4000]
    if getattr(a, "files", None):
        payload["files"] = a.files
    here = HERE
    try:
        # **Control writes all go through writerd.** Called directly under ORG_WRITER_SOCKET it
        # exits 4, and legitimate operation stops.
        _base = ([sys.executable, os.path.join(here, "writer_client.py"), "append", "--"]
                 if os.environ.get("ORG_WRITER_SOCKET")
                 else [sys.executable, os.path.join(here, "ledger.py"), "append"])
        p = subprocess.run(_base + [
                            "--actor", payload["role"], "--class", "progress_recorded",
                            "--natural-key", f"progress-{a.issue}-{a.event_id or a.event}",
                            "--payload", json.dumps(payload, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=30)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return False, str(e)


def cmd_log(a):
    """Append a WORK-LOG comment to a task Issue on a milestone event (cycle_started, progress_recorded,
    phase_admitted, cycle_completed, …). The ledger stays the SSoT — this comment is its projection onto
    the Issue so the CEO sees progress accrue without opening the ledger.

    With human diff review retired (docs/11 §4f), the Issue is the org's PRIMARY audit surface: what was
    tried, what was run, what came back, what changed course and why. So this command takes the detail
    fields that make a log entry reconstructable by someone who was never in the session — the command
    that was run and its result, the files touched, the next step. Terse logs ("progress recorded") are
    the failure mode; they satisfy the letter of logging while recording nothing recoverable.

    IDEMPOTENT (docs/11 §0): each comment carries a hidden marker `<!-- orgforge:event:<id> -->`. If a
    comment with this event id already exists on the Issue, we no-op — a replayed/retried cycle logs the
    same milestone once, never twice. Pass --event-id (the ledger event's id) to key the dedup; without
    it we fall back to a hash of (event, detail)."""
    # sha256, NOT hash(): Python salts hash() per process (PYTHONHASHSEED), so a CLI marker built from
    # hash() differs on every invocation and the dedup NEVER fires across runs — a retried cycle
    # double-posts while the docstring promises "logs once, never twice".
    defect = _log_defect(a)
    if defect:
        print(f"the work log is thin: {defect}\n\n"
              f"The bar in docs/11 §3b: **someone reading only the Issue can reconstruct what "
              f"was built, what was tried, what was discarded, what was run and what came back, "
              f"and why it was merged**.\n"
              f"This is checked for the same reason `decide` checks --why — human diff review is "
              f"retired, and this Issue is the only audit surface there is.\n"
              f"For a light interim note use --event progress_recorded (no check applies).",
              file=sys.stderr)
        return 2
    marker_key = a.event_id or _stable_key(a.event, a.detail or "", a.phase or "")
    marker = f"<!-- orgforge:event:{marker_key} -->"
    if _already_logged(a.repo, a.issue, marker):
        print(f"log: event {marker_key} already on issue #{a.issue} — idempotent no-op (docs/11 §0).")
        return 0
    # the visible line: a compact, human-readable milestone. detail is optional free text.
    line = f"**{a.event}**"
    if a.phase:
        line += f" · phase: `{a.phase}`"
    if a.detail:
        line += f" — {a.detail}"
    parts = [line]
    # the reconstructable detail: what was actually run, what came back, what moved.
    if getattr(a, "command", None):
        result = getattr(a, "result", None)
        parts.append(f"\n**Ran:**\n```\n{a.command}\n```")
        if result:
            parts.append(f"**Result:**\n```\n{result}\n```")
    for label, val in (("Files", getattr(a, "files", None)),
                       ("Next step", getattr(a, "next_step", None)),
                       ("Blocked by", getattr(a, "blocked_by", None))):
        if val:
            parts.append(f"**{label}:** {val}")
    body = "\n".join(parts) + f"\n\n{marker}"
    code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", body])
    if code != 0:
        print(f"gh error posting work-log comment: {out}", file=sys.stderr)
        return 2
    ok, msg = _append_progress_receipt(a)
    if ok:
        print(f"logged {a.event} to issue #{a.issue} (progress_recorded also written to the ledger).")
    else:
        print(f"logged {a.event} to issue #{a.issue}.")
        print(f"note: could not write the ledger receipt ({msg.strip()[:120]}). "
              f"The Issue keeps the entry, but `/org-resume` cannot see this progress.",
              file=sys.stderr)
    return 0


def cmd_review_response(a):
    """Project one concrete response to a review finding onto its GitHub Issue.

    Findings and their responses must be addressable ACROSS harnesses: a finding raised by the
    Claude-lineage judge has to be checkable — and acceptable — by the Codex-lineage one without
    either relying on a chat transcript that no longer exists. The Issue is the durable, shared
    surface both can read, so the response goes there rather than into a local status file that
    only one session can see.

    This is also what makes a review rally terminate. `agents/gate.md` already says a finding may
    only become a blocker again if the reviewed head, the cited evidence, or the stated risk
    changed — but that rule is unenforceable when nobody can point at the previous finding by id.
    An addressable id plus a recorded response is the material that lets the next reviewer say
    "this was answered, and here is what changed" instead of raising it fresh (tatekae #170 ran
    12 rounds partly on re-raised findings).

    Plumbing only: it records that a response was given, never whether the response is adequate.
    That judgment stays with the next independent reviewer (docs/03 §6.5).
    """
    return _review_response(a, gh)


# How much of the review to carry into the response. Enough that the finding can be read without
# leaving the comment; short enough that the response is still about the response.
_QUOTE_CHARS = 1200


def _review_quote(issue_json, review, finding):
    """Find the review being answered among the Issue's comments. Returns (quote, url).

    (None, None) when nothing matches — the caller refuses, because a response to a review that was
    never written is not traceable to anything.

    Matching is on the review id, then on the finding id, because a review comment carries its
    `review_subject_id` while the finding id may only appear in the reasoning text. Either is a
    real anchor; neither is inferred from the response itself.
    """
    try:
        comments = (json.loads(issue_json) or {}).get("comments") or []
    except Exception:
        return None, None
    for needle in (str(review or "").strip(), str(finding or "").strip()):
        if not needle:
            continue
        for c in comments:
            body = str(c.get("body") or "")
            if needle not in body:
                continue
            # Do not quote a response as though it were the review it answers.
            if "orgforge:review-response:" in body:
                continue
            text = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()
            if len(text) > _QUOTE_CHARS:
                text = text[:_QUOTE_CHARS].rstrip() + "\n…(truncated — see the linked comment)"
            quote = "\n".join("> " + line for line in text.splitlines())
            return quote, c.get("url")
    return None, None


def cmd_review_findings(a, gh=None):
    """List the findings raised on an Issue and which of them have been answered.

    **A rally you cannot count is a rally you cannot end.** Findings were only ever ids inside a
    judge's prose, so nobody could say how many were open, which were answered, or which were the
    same finding raised again — every round read as whack-a-mole because the tools could only see
    one response at a time. With `findings` first-class in the verdict schema, the open set is a
    fact rather than an impression.

    Reports, does not judge: it never decides whether a response was adequate, only whether one was
    recorded for each finding (docs/03 §6.5).
    """
    _gh = gh or globals()["gh"]
    code, existing = _gh(["issue", "view", str(a.issue), "--repo", a.repo, "--json", "comments"])
    if code != 0:
        print(existing, file=sys.stderr)
        return 3
    try:
        comments = (json.loads(existing) or {}).get("comments") or []
    except Exception as exc:
        print(f"review-findings: cannot read the comments on #{a.issue}: {exc}", file=sys.stderr)
        return 3

    raised, answered = {}, {}
    for c in comments:
        body = str(c.get("body") or "")
        if "orgforge:review-response:" in body:
            for fid in re.findall(r"orgforge:review-response:[^:]*:([A-Z]+-[0-9]{3}):(\w+)", body):
                answered[fid[0]] = fid[1]
            continue
        for block in re.findall(r'"id"\s*:\s*"([A-Z]+-[0-9]{3})"[^}]*?"claim"\s*:\s*"(.*?)"',
                                body, re.S):
            raised.setdefault(block[0], block[1][:160])
        # A judge that wrote its findings as prose still names them; count those too, so the
        # report does not silently under-report on Issues that predate the structured schema.
        for fid in re.findall(r"\b([A-Z]+-[0-9]{3})\b", body):
            raised.setdefault(fid, "")

    # An id answered but never raised means the finding lived only in a judge's prose, in a shape
    # this cannot read — which is the very gap `findings` closes. Say so rather than reporting a
    # tidy zero: "raised: 0, answered: 7" is not a clean sheet, it is a blind spot.
    unraised = sorted(f for f in answered if f not in raised)
    open_ids = sorted(f for f in raised if f not in answered)
    print(json.dumps({"issue": a.issue,
                      "raised": len(raised), "answered": len(answered), "open": len(open_ids),
                      "answered_but_never_raised": unraised,
                      "open_findings": [{"id": f, "claim": raised[f]} for f in open_ids],
                      "answered_findings": [{"id": f, "status": s}
                                            for f, s in sorted(answered.items())]},
                     ensure_ascii=False, indent=2))
    if unraised:
        print(f"\n{len(unraised)} finding(s) have a response but no finding recorded on the Issue: "
              f"{', '.join(unraised)}\n"
              f"  These were raised as prose inside a verdict, so nothing can check what was "
              f"answered. Judges emitting the structured `findings` array fixes this going "
              f"forward.", file=sys.stderr)
    if open_ids:
        print(f"\n{len(open_ids)} finding(s) have no recorded response: {', '.join(open_ids)}\n"
              f"  Answer each with `github_sync.py review-response --finding <id>`. An unanswered "
              f"finding is what the next round re-raises.", file=sys.stderr)
    return 0


def _review_response(a, gh):
    finding = (a.finding or "").strip()
    response = (a.response or "").strip()
    evidence = (a.evidence or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{0,63}", finding):
        print("review-response: --finding needs a traceable id (e.g. GATE-001).", file=sys.stderr)
        return 2
    if len(response) < 20 or len(evidence) < 20:
        print("review-response: --response and --evidence must record concretely what was done "
              "and what was measured.", file=sys.stderr)
        return 2
    marker = f"<!-- orgforge:review-response:{a.review}:{finding}:{a.status} -->"
    code, existing = gh(["issue", "view", str(a.issue), "--repo", a.repo,
                         "--json", "comments"])
    if code != 0:
        print(existing, file=sys.stderr)
        return 3
    if marker in existing:
        print(f"review-response: {finding} is already recorded on Issue #{a.issue} with the same "
              f"content (no-op).")
        return 0
    # **The review being answered has to exist.** `--review` used to be accepted on its shape alone,
    # so a response could name a review that was never written and still read as an answer to one.
    # On a real Issue (#67 of domain-spec-notes) the responses cited SKEPTIC-001/002 while nothing
    # on the Issue defined those ids: from the outside, "addressed" was unfalsifiable.
    # The judgment stays with the next reviewer; what is enforced here is only that there is
    # something to point AT.
    quoted, review_url = _review_quote(existing, a.review, finding)
    if quoted is None:
        print(f"review-response: no review matching {a.review!r} is recorded on Issue #{a.issue}.\n"
              f"  A response cannot answer a finding that was never written down. Record the "
              f"review first (provisional / decide), then respond to it by its "
              f"review_subject_id.", file=sys.stderr)
        return 2
    body = "\n".join([
        f"### ↪ Review response — `{finding}` ({a.status})",
        f"**Review:** `{a.review}`" + (f" — [the finding being answered]({review_url})"
                                       if review_url else ""),
        f"**Responded by:** `{a.by}`",
        # **Carry the finding, not just its id.** A reader of this comment alone could otherwise
        # see only "SKEPTIC-001 (addressed)" and have no way to tell what was addressed.
        "\n**The finding being answered:**\n" + quoted,
        "\n**Response:**\n" + response,
        "\n**Evidence:**\n" + evidence,
        "\nThe next independent reviewer confirms this response and its evidence, and states the "
        "conclusion in their own verdict.",
        marker,
    ])
    code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", body])
    if code != 0:
        print(out, file=sys.stderr)
        return 3
    print(f"recorded review response for {finding} on #{a.issue}")
    return 0


# the judgment classes that must land on the Issue with their reasoning (docs/11 §4f)
DECISIONS = ("admission_decided", "refutation_attempted", "phase_admitted", "conformance_reviewed",
             "integration_admitted", "deploy_decided", "rework_requested", "scope_decided",
             "design_decided", "tradeoff_decided")


def _reasoning_digest(*fields):
    """A stable digest over a judgment's reasoning fields — the tamper-evidence anchor (docs/11 §4f.1).

    Normalizes whitespace so a cosmetic reflow does not read as tampering, while any change to the
    substance (a dropped `--risk`, a rewritten `--why`) changes the digest."""
    import hashlib
    norm = "\x1f".join(re.sub(r"\s+", " ", (f or "").strip()) for f in fields)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]



# "Stating something unverified as though it had been verified" — the failure mode this org has
# caught eight times in the field appeared **on the detecting side: the supervisor**. As observed
# in operation:
#   the maker's report : "src/db/client.ts **does not exist on this branch yet**; it is on
#                        feat/issue-11"
#   the supervisor's summary : "the maker did not guess — it read loadEnv() in src/db/client.ts and
#                              settled the variables"
#   the qualifier dropped : "**not on this branch**"
# The maker had written the qualifier honestly. **The supervisor dropped it in the summary.** That
# summary flowed into the instruction to the gate, and the gate made "that file does not exist" its
# grounds for reject.
#
# The ledger holds only a hash of the reason, so the distinction cannot be checked there. The
# check sits **at decide's door** — seen before it lands in an Issue comment.
# Synonyms are grouped by the **kind** of qualifier. Treat expressions differing only in inflection
# ("存在せず" and "存在しない") as distinct and a warning fires while the qualifier is being carried
# correctly — which is what the first implementation did.
# The VALUES below match the prose an agent actually writes, so they stay in Japanese: they are
# input matching, not source language.
_HEDGE_GROUPS = {
    "absence": ("には無い", "にはない", "存在せず", "存在しない", "存在しま", "無かった", "なかった",
             "not present", "does not exist", "missing"),
    "unmeasured": ("未測定", "測っていない", "測定していない", "not measured", "unmeasured"),
    "unverified": ("確認していない", "確かめていない", "未検証", "未実行", "検証していない",
               "unverified", "not verified", "not run"),
    "conjecture": ("のはず", "だと思われ", "推測", "かもしれ", "可能性がある", "assumed", "presumably",
             "probably", "likely"),
    "conditional": ("の場合は", "であれば", "のときは", "if ", "when "),
    "incomplete": ("予定", "できていない", "していません", "まだ", "todo", "pending"),
}
# Traces of "it was actually run". Knowingly, this invites the formalism of **writing a command
# name to get through** — and it is still far better than nothing (in the field, when a thin
# --result on a cycle_completed was refused, the supervisor went and measured again: a case of a
# refusal changing behaviour rather than being a formal wall).
# It cannot be closed completely, and that is recorded as this check's limit (docs/11).
_RAN = ("npm ", "npx ", "git ", "psql", "python3", "node ", "pytest", "cargo ", "go test",
        "supabase", "curl ", "exit=", "exit code", "passed", "failed", "$ ", "→", "->")



def _prior_admission(issue):
    """Is there an `admit` from the gate on this Issue? Returns (verdict, actor), or (None, None).

    The ledger already applies the same check to `phase_started` (refusing implement where design
    has not been admitted). **The same shape goes on the integration side** — an
    `integration_admitted = pass` that
    Let it through without the gate's admit and the quality of the maker's report gets used in
    place of an admit. In operation, a high-quality report led to a `git merge`, with
    `integration_admitted` recorded afterwards, and it passed.
    """
    try:
        sys.path.insert(0, HERE)          # HERE = tools/ (kept in _core — the lesson of 0.22.1)
        from discover import ledger_root
        from ledger import voided_seqs
        root = ledger_root()
    except Exception:
        return None, None
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return None, None
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = voided_seqs(evs)
    want = str(issue).lstrip("#")
    hit = (None, None)
    for e in evs:
        if e.get("class") != "admission_decided" or e.get("seq") in voided:
            continue
        pl = e.get("payload", {}) or {}
        ids = {str(pl.get(k, "")).lstrip("#") for k in ("issue", "deliverable") if pl.get(k)}
        if want in ids:
            hit = (pl.get("verdict"), e.get("actor"))
    return hit


def _claim_verify_defect(a):
    """Check whether the supervisor's record distinguishes who verified what.

    Returns: a list of warnings (**it does not refuse** — with one exception). The judgment is the
    supervisor's job, but there has to be **something by which a dropped qualifier can be
    noticed**.
    """
    warns = []
    claimed = (getattr(a, "claimed", None) or "").strip()
    verified = (getattr(a, "verified", None) or "").strip()
    if not claimed and not verified:
        return warns          # a legacy call with only --why / --evidence passes (compatibility)

    # (a) no trace of execution in --verified = merely writing "verified"
    if verified and not any(k in verified for k in _RAN):
        warns.append(
            "--verified carries no **trace of anything actually run** (a command, output, an "
            "exit code). Writing \"confirmed\" is not confirming — it is precisely the failure "
            "mode this org has caught eight times. If you did not run it, write it on the "
            "--claimed side.")

    # (b) --claimed carries a qualifier that --verified does not touch = the summary dropped it
    # Compared by kind: where claimed carries an "absence" qualifier, verified touching "absence"
    # is enough
    untouched = []
    for kind, words in _HEDGE_GROUPS.items():
        if any(w in claimed for w in words) and not any(w in verified for w in words):
            untouched.append(kind)
    if untouched:
        warns.append(
            f"--claimed carries a qualifier ({', '.join(untouched[:3])}) that --verified does not "
            f"touch. **A qualifier dropped in the summary flows into the downstream judgment** — "
            f"in the field, \"not on this branch\" disappeared and became the gate's grounds for "
            f"reject. Carry the qualifier through as it stands, or verify it yourself and write "
            f"the result.")
    return warns


def _reasoning_defect(why, verdict, event):
    """Return a defect phrase if `why` is not actual reasoning, else None.

    A pure length bound fails in both directions and must not be used alone:
      · it PASSES `"admit admit admit admit admit"` — the literal restatement it exists to reject;
      · it REJECTS `「全テスト通過を確認。cap近傍の並行joinは未検証」` — substantive reasoning that is
        short in codepoints because Japanese carries ~2-3x the information per character, and the org's
        default output_language is ja. Measuring bytes rather than codepoints fixes the CJK half.
    So: require some substance by BYTE length, then reject text that is only verdict/filler tokens."""
    if not why:
        return "is required — a verdict with no reasoning is a stamp."
    if len(why.encode("utf-8")) < 24:
        return "is too short to be an account of the decision."
    # strip punctuation, then see whether anything remains beyond verdict words and filler
    words = re.findall(r"[^\W\d_]+", why.lower(), flags=re.UNICODE)
    if not words:
        return "contains no words — punctuation or padding is not reasoning."
    filler = {verdict.lower(), event.lower(), "the", "is", "it", "this", "was", "a", "an", "and",
              "ok", "okay", "fine", "good", "looks", "lgtm", "pass", "passed", "passes", "green",
              "admit", "admitted", "approve", "approved", "yes", "no", "all", "to", "me", "verdict"}
    substantive = [w for w in words if w not in filler]
    if not substantive:
        return ("only restates the verdict — that is exactly the rubber stamp this check exists to "
                "reject.")
    if len(set(words)) <= 2 and len(words) >= 4:
        return "is one phrase repeated to clear a length bar, not reasoning."
    # keyboard-mash padding: almost no distinct characters across the whole text
    if len(set(why.replace(" ", ""))) <= 3:
        return "is padding, not an account of the decision."
    return None


def _org_lineage():
    """Read `enforcement.judges.lineage` from the constitution. The default is `same-harness`.

    **When the configuration cannot be read, stop (fail-closed).** 0.32.0 swallowed the exception
    and returned `same-harness` — so in an org that declared cross-harness, a broken YAML or a
    missing PyYAML meant **a strong safety mode quietly dropping to the ordinary one**. That is
    exactly the shape of "the signal is broken, so its being broken is invisible".

    An org that declares nothing (no judges in the constitution) runs on the default. To tell
    "could not be read" from "not declared", **the file's existence and the parse's success are
    handled separately**.
    """
    env = os.environ.get("ORG_JUDGE_LINEAGE")
    if env:
        return env.strip()
    try:
        sys.path.insert(0, HERE)
        from discover import constitution
        path = constitution()
    except Exception as e:
        raise SystemExit(f"cannot resolve the constitution's location: {e}\n"
                         "  Record a judgment while judges.lineage cannot be read and an org that "
                         "declared cross-harness passes quietly on a single lineage.\n"
                         "  Check that you are running from the org root.")
    if not path or not os.path.isfile(path):
        return "same-harness"          # the org has no constitution = nothing is declared
    try:
        import yaml
    except Exception:
        raise SystemExit("PyYAML is missing, so the constitution cannot be read.\n"
                         "  Recording a judgment while judges.lineage cannot be read is not "
                         "allowed — a cross-harness declaration would vanish silently.\n"
                         "    python3 -m pip install pyyaml")
    try:
        with open(path, encoding="utf-8") as f:
            c = yaml.safe_load(f) or {}
    except Exception as e:
        raise SystemExit(f"cannot parse constitution.yaml: {e}\n"
                         f"  file: {path}\n"
                         "  **If the configuration cannot be read, stop.** Whether the reason it "
                         "cannot be read lies on the judges.lineage line is unknowable while it "
                         "cannot be read.")
    if not isinstance(c, dict):
        raise SystemExit(f"constitution.yaml is not a map ({type(c).__name__}): {path}")
    j = ((c.get("enforcement") or {}).get("judges") or {})
    declared = str(j.get("lineage") or "same-harness").strip()
    sys.path.insert(0, HERE)
    from harness import effective_lineage
    return effective_lineage(declared)


def _judgment_correction_authorities():
    """Return the declared third-party roles to which a re-judgment must be handed back."""
    try:
        sys.path.insert(0, HERE)
        from discover import constitution
        path = constitution()
        import yaml
        with open(path, encoding="utf-8") as handle:
            doc = yaml.safe_load(handle) or {}
        judges = ((doc.get("enforcement") or {}).get("judges") or {})
        policy = judges.get("judgment_corrections") or {}
        roles = policy.get("authority_roles") or []
        if isinstance(roles, list) and roles and all(isinstance(role, str) for role in roles):
            return [role.strip() for role in roles if role.strip()]
    except Exception:
        pass
    return []


def _has_lineage_verdict(issue, event, lineage):
    """Is there a **passing** judgment from the named lineage in the ledger, for the same event on
    this Issue?

    A negative (reject/refuted) is not counted — what is being sought is agreement, and with either
    side negative this is no place to record an admit at all. Corrected records
    (`corrected_seqs`) are not counted.
    """
    ok = {"admission_decided": ("admit",), "refutation_attempted": ("survives",)}.get(event, ())
    try:
        sys.path.insert(0, HERE)
        from discover import ledger_root
        from ledger import voided_seqs
        root = ledger_root()
    except Exception:
        return False
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return False
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = voided_seqs(evs)
    want = str(issue).lstrip("#")
    for e in evs:
        if e.get("class") != event or e.get("seq") in voided:
            continue
        pl = e.get("payload", {}) or {}
        ids = {str(pl.get(k, "")).lstrip("#") for k in ("issue", "deliverable") if pl.get(k)}
        if want in ids and pl.get("lineage") == lineage and pl.get("verdict") in ok:
            return True
    return False


def cmd_provisional(a):
    """Record a lineage's judge as **provisional**, and derive an admission once two lineages agree.

    ## Why it is two-stage

    0.32.0 had `admission_decided = admit` recorded directly, refusing it "unless the other
    lineage's judgment is already in the ledger". From an empty ledger that meant **neither order
    could be recorded and an admit could never be created** (measured: exit=4 in both directions,
    the ledger still empty). Only the refusal of one side had been checked; that it could be passed
    had not.

    The correct shape puts **a judgment that carries no authority on its own** first:

      1. `verdict_provisional`  each lineage's judge. The order does not matter
      2. `admission_decided`    **assembled by the tool** once the two agree

    Producing the verdict at stage 2 is plumbing, not judgment — it is a function of the fact that
    they agreed. Where they disagree the tool cannot produce an admit, which also removes any room
    for a supervisor to take whichever suits.

    ## On this tool "producing" an admit

    That does not contradict `verify` producing no judgment. All that is settled here is *whether
    they agree*; the verdict, the why and the evidence are all carried over exactly as the judge
    wrote them. **There is no point at which the tool adds a judgment of its own.**
    """
    # **If the configuration cannot be read, stop.** provisional is a command premised on
    # cross-harness, so stacking judgments while the lineage setting is unreadable lets whatever
    # counts the agreement later run on a different premise.
    # `_org_lineage()` raises SystemExit when it cannot read (fail-closed).
    lineage_mode = _org_lineage()
    if lineage_mode != "cross-harness":
        print(f"provisional is for an org with judges.lineage = cross-harness, but this org is "
              f"{lineage_mode!r}.\n"
              f"  Running on a single lineage, record the judgment through decide directly "
              f"(there is nobody to agree with).\n"
              f"  Running on two, set the constitution's enforcement.judges.lineage to "
              f"cross-harness.", file=sys.stderr)
        return 2
    # Subject equality alone cannot detect that both judges reviewed the same *old* base.  `verify`
    # persists the observable descriptor; embed it in the append-only event and re-resolve the ref
    # before accepting a positive vote.
    from review_freshness import descriptor_status, freshness_policy, load_descriptor
    try:
        from discover import constitution
        constitution_path = constitution()
    except Exception:
        constitution_path = None
    _declared, strict_freshness, policy_error = freshness_policy(constitution_path)
    if policy_error:
        print(f"provisional: the review freshness policy is invalid — {policy_error}",
              file=sys.stderr)
        return 2
    subject_descriptor, descriptor_path = load_descriptor(a.subject, os.getcwd())
    if strict_freshness and subject_descriptor is None:
        print("provisional: the subject descriptor that strict review freshness needs is "
              "absent.\n"
              f"  expected: {descriptor_path}\n"
              f"  org_cycle.py verify --issue {a.issue} --role {a.role} --print-subject\n"
              "  An old review_subject_id alone cannot check whether the integration target "
              "moved, so the judgment is not recorded.",
              file=sys.stderr)
        return 7
    if subject_descriptor is not None:
        # The descriptor was minted against the subject worktree.  Rechecking from the
        # supervisor's primary checkout compares an unrelated HEAD and falsely rejects a
        # current review whenever the primary branch is intentionally divergent.
        subject_cwd = subject_descriptor.get("subject_root") or os.getcwd()
        freshness = descriptor_status(subject_descriptor, subject_cwd)
        if strict_freshness and not freshness["ok"]:
            print(f"provisional: a stale review subject is not recorded — "
                  f"{freshness['reason']}: {freshness['detail']}\n"
                  "  Take in the integration target, and run verify and the judgment again.",
                  file=sys.stderr)
            return 7
    ok = {"gate": ("admit", "reject", "park"), "skeptic": ("survives", "refuted")}
    if a.role not in ok:
        print(f"provisional: --role is gate | skeptic (got {a.role!r})", file=sys.stderr)
        return 2
    if a.verdict not in ok[a.role]:
        print(f"provisional: a {a.role} verdict is {ok[a.role]} (got {a.verdict!r})",
              file=sys.stderr)
        return 2
    why = (a.why or "").strip()
    if len(why) < 40:
        print(f"provisional: --why is thin ({len(why)} characters). Not a restatement of the "
              f"verdict — write what you looked at and where it was decided.", file=sys.stderr)
        return 2
    pass_v = {"gate": "admit", "skeptic": "survives"}[a.role]
    if a.verdict == pass_v and not (a.evidence or "").strip():
        print(f"provisional: a {pass_v} requires --evidence. A pass that consulted nothing is a "
              f"rubber stamp, not a judgment.", file=sys.stderr)
        return 2

    event = {"gate": "admission_decided", "skeptic": "refutation_attempted"}[a.role]
    digest = _reasoning_digest(why, a.evidence, a.alternatives, a.standard, a.risk)

    # ── identity（H1）─────────────────────────────────────────────────────
    # **`decision_by` is set only from a verified receipt.** If it could be asserted on the CLI, it
    # could be claimed as anyone's judgment. With no receipt it stays `claimed` and **is not used to
    # enforce independence**. `recorded_by` is observed (proxy recording is allowed — the judge need
    # not write it itself).
    sys.path.insert(0, HERE)
    from identity import (verify_receipt, observed_recorder, PROTOCOL_VERSION)
    decision_by, ident = None, {"identity_assurance": "claimed"}
    if getattr(a, "receipt", None):
        try:
            rc = json.loads(open(a.receipt, encoding="utf-8").read()) \
                if os.path.isfile(a.receipt) else json.loads(a.receipt)
        except Exception as e:
            print(f"provisional: cannot read --receipt ({e}).", file=sys.stderr)
            return 2
        expect = {"review_subject_id": a.subject, "issue": a.issue, "role": a.role,
                  "lineage": a.lineage, "verdict": a.verdict,
                  "reasoning_sha256": digest}
        decision_by, ident, rerr = verify_receipt(rc, expect)
        if rerr:
            print(f"provisional: the receipt cannot be verified, so the judgment is not recorded "
                  f"— {rerr}\n"
                  f"  **If the deciding principal cannot be confirmed, it is not recorded as that "
                  f"principal's judgment.**\n"
                  f"  To record without a receipt, drop --receipt (decision_by is then `claimed` "
                  f"and cannot be used to enforce independence).", file=sys.stderr)
            return 4
    recorded_by, rec_assurance = observed_recorder()
    payload = {"issue": a.issue, "deliverable": str(a.issue), "role": a.role,
               "lineage": a.lineage, "verdict": a.verdict, "for_event": event,
               "review_subject_id": a.subject, "reasoning_sha256": digest,
               # **Three principals, kept apart (H1).** decision_by comes only from a receipt;
               # recorded_by is observed (proxy recording is allowed); committed_by is stamped by
               # the writer.
               #
               # Falling back to the RECORDER here made a supervisor who proxy-recorded an
               # unavailable judge's result the decision principal of that verdict. The ledger then
               # refused that same supervisor's correction of it as self-correction, and in a
               # single-authority org there was nobody else to ask — the recovery path documented
               # in #186 existed and could not complete. Measured on tatekae seq 3706.
               #
               # The judging ROLE is the right fallback: `gate` judged it, the supervisor only
               # wrote it down. That keeps the separation the self-correction check depends on,
               # and `recorded_by` still carries who actually typed the command. An unreceipted
               # verdict stays `identity_assurance: claimed`, so nothing is being upgraded here.
               "decision_by": decision_by or a.role,
               "recorded_by": recorded_by,
               "identity_assurance": ident.get("identity_assurance", "claimed"),
               "recorder_assurance": rec_assurance,
               "workload_isolation": ident.get("workload_isolation", "none"),
               **({"signer_id": ident["signer_id"], "key_id": ident["key_id"]}
                  if ident.get("signer_id") else {}),
               # Conditions 7+8: persist what the digest is reconciled against. No prose goes
               # into the ledger, but **where to look for the original** does (the marker in the
               # Issue comment).
               "reasoning_ref": f"issue:{a.issue}#provisional-{a.lineage}-{digest[:12]}"}
    if subject_descriptor is not None:
        payload["review_subject"] = subject_descriptor
    if getattr(a, "phase", None):
        payload["phase"] = a.phase
    if getattr(a, "risk", None):
        payload["risk_accepted"] = True

    # **How a second judgment from the same lineage is handled.** 0.32.1 refused only where the
    # verdict differed, so another provisional with the same verdict and a different reason could be
    # stacked (raised in audit) — leaving which one it agreed with a matter of operating practice.
    #   - an exactly identical re-run (same subject, same verdict, same digest) → no-op
    #   - any other re-judgment → refused. A correction goes through correction
    prior = _provisional_for(a.issue, event, a.lineage)
    if prior:
        same = (prior["verdict"] == a.verdict and prior.get("subject") == a.subject
                and prior.get("digest") == digest)
        if same:
            print(f"provisional: the {a.lineage} judgment for #{a.issue} is already present with "
                  f"identical content at seq={prior['seq']} (idempotent no-op).")
            return 0
        what = []
        if prior["verdict"] != a.verdict:
            what.append(f"verdict {prior['verdict']!r} → {a.verdict!r}")
        if prior.get("subject") != a.subject:
            what.append(f"subject {str(prior.get('subject'))[:12]}… → {a.subject[:12]}…")
        if prior.get("digest") != digest:
            what.append("the why/evidence differs")
        authorities = _judgment_correction_authorities()
        handback = (", ".join(authorities) if authorities
                    else "(undeclared — repair the constitution)")
        # **State the recovery as commands, not as a requirement.** The rule this enforces is
        # right — a lineage must not restack verdicts until they agree — but a refusal that only
        # names the rule leaves the caller stuck: the authority, the receipt and the correction
        # all exist, yet reaching them took five failed attempts to rediscover (issue #186, hit
        # in the field when a rebase moved review_subject_id). What cannot be skipped must still
        # be reachable.
        _sig = ("correction:superseded:%s" % prior["seq"])
        _auth = authorities[0] if authorities else "<authority-role>"
        print(f"provisional: #{a.issue} already has a {a.lineage} verdict "
              f"(seq={prior['seq']}). What differs: {', '.join(what)}\n"
              f"  **A lineage must not restack its verdicts until they agree.** A judge cannot "
              f"void its own prior verdict; a declared third-party authority must supersede it.\n"
              f"\n"
              f"  Authority roles declared by the constitution: {handback}\n"
              f"\n"
              f"  To supersede seq={prior['seq']}, the authority runs (not the judge):\n"
              f"\n"
              f"    # 1. once per authority — register a signing key, keep the private key off the writer\n"
              f"    python3 tools/identity.py keygen --key-id <key> --signer-id {_auth} \\\n"
              f"        --authorized-roles {_auth} --store <ledger>/../trust/keys.json \\\n"
              f"        --private-out <key>.pem\n"
              f"\n"
              f"    # 2. sign the correction — the subject binds it to this exact target\n"
              f"    python3 tools/identity.py receipt --org-id <org> --ledger-id <ledger-id> \\\n"
              f"        --subject {_sig} --role {_auth} \\\n"
              f"        --lineage {a.lineage} --verdict superseded \\\n"
              f"        --reasoning-sha256 <sha256 of the reason> --issued-at <ts> \\\n"
              f"        --key-id <key> --issue {a.issue} --event-class correction \\\n"
              f"        --private-key <key>.pem > correction-receipt.json\n"
              f"\n"
              f"    # 3. append it — the ledger verifies the receipt before recording\n"
              f"    python3 tools/ledger.py append <ledger> --actor {_auth} --class correction \\\n"
              f"        --payload '{{\"corrects\":[{prior['seq']}],\"kind\":\"superseded\",\"reason\":\"<why>\"}}' \\\n"
              f"        --receipt correction-receipt.json\n"
              f"\n"
              f"  Requires in constitution.yaml:\n"
              f"    enforcement.judges.judgment_corrections.authority_roles: [{_auth}]\n"
              f"\n"
              f"  The old verdict is not erased — the ledger is append-only, and the correction is "
              f"recorded beside it with its reason. `probe` and `mistake` void a judgment the same "
              f"way and demand the same authority and receipt.",
              file=sys.stderr)
        return 4

    # The idempotency key is built from **the identity of the judgment**. `_reasoning_digest`
    # bundles only the prose (correct, since prose is what tamper evidence covers), so a judgment
    # that kept the reason and changed the verdict would land on the same key. verdict and subject
    # are included, so a substitution cannot fall through as a no-op.
    # **Hand over the receipt itself.** No "verified" marker in an environment variable — anything
    # the caller can set is not evidence (measured: merely adding ORG_IDENTITY_VERIFIED=1 let a
    # forgery through). The writer (ledger.py / writerd) verifies it and derives the identity
    # fields itself.
    for k in ("decision_by", "recorded_by", "identity_assurance", "recorder_assurance",
              "workload_isolation", "signer_id", "key_id"):
        payload.pop(k, None)
    rc = _ledger_append(a.by or a.role, "verdict_provisional", payload,
                        f"verdict_provisional-{a.issue}-{a.lineage}-{a.verdict}"
                        f"-{a.subject[:8]}-{digest[:12]}",
                        receipt=getattr(a, "receipt", None))
    if rc != 0:
        return 4
    print(f"recorded provisional {a.role}={a.verdict} ({a.lineage}) on #{a.issue}.")
    # **Condition 8: persist what the digest is reconciled against.** The ledger holds only
    # reasoning_sha256, so without the prose on the Issue there is nothing to reconcile against
    # later. It goes through the ledger first and is then projected (if it is refused, no record
    # visible from outside is created — the same order as decide).
    if not getattr(a, "repo", None):
        print(f"  note: there is no GitHub repo, so nothing was projected onto an Issue.\n"
              f"  **Nothing anywhere holds what reasoning_sha256 ={digest[:12]}… reconciles "
              f"against** — the ledger keeps only the digest, so it cannot be matched to the prose "
              f"later.",
              file=sys.stderr)
    else:
        marker = f"<!-- orgforge:provisional:{a.lineage}:{digest[:12]} -->"
        parts = [
            f"### 🧪 verdict_provisional — `{a.verdict}` ({a.lineage})",
            f"**Judged by:** `{a.role}` / lineage `{a.lineage}`",
            f"**It carries no authority on its own.** {event} is generated only once two lineages "
            f"agree on the same subject.",
            f"\n**review_subject_id:** `{a.subject}`",
            f"\n**Why (the reasoning):**\n{why}",
        ]
        if subject_descriptor:
            parts.insert(4, "**Integration target:** "
                         f"`{subject_descriptor.get('integration_ref')}` @ "
                         f"`{str(subject_descriptor.get('integration_head_sha') or '')[:12]}`; "
                         f"base `{str(subject_descriptor.get('base_sha') or '')[:12]}` "
                         f"({subject_descriptor.get('integration_relation')})")
        if (a.evidence or "").strip():
            parts.append(f"\n**Evidence consulted:**\n{a.evidence}")
        if (a.alternatives or "").strip():
            parts.append(f"\n**Alternatives considered:**\n{a.alternatives}")
        if (a.standard or "").strip():
            parts.append(f"\n**Standard applied:** {a.standard}")
        if (a.risk or "").strip():
            parts.append(f"\n**Known risk accepted:** {a.risk}")
        parts.append(f"\n`reasoning_sha256: {digest}` — the receipt in the ledger carries the same "
                     f"digest. If a re-hash does not match, this record has been altered.")
        parts.append(f"\n{marker}")
        code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo,
                        "--body", "\n".join(parts)])
        if code != 0:
            print(f"  note: it entered the ledger but could not be projected onto the Issue: "
                  f"{out[:300]}\n"
                  f"  **Nothing holds what reasoning_sha256 reconciles against.** Re-running with "
                  f"the same arguments makes the ledger an idempotent no-op and fills in the Issue "
                  f"alone.", file=sys.stderr)

    # **A judgment that is not a pass is not about producing agreement at all.** park / reject /
    # refuted count as negative from either side alone (fall to the stricter reading), so there is
    # nothing to wait for and no subject to compare. Without separating this, a park draws the
    # irrelevant warning "they are looking at different subjects" (measured).
    other = "cross-harness" if a.lineage == "same-harness" else "same-harness"
    peer = _provisional_for(a.issue, event, other)

    # A negative (park / reject / refuted) stands alone — it waits for nobody and compares no
    # subject.
    # **But where the peer passed, that is a disagreement.** Returning early and skipping the
    # record leaves no judges_disagreed on the "a reject arrived after the admit" path (caught by
    # measurement).
    if a.verdict != pass_v:
        if peer and peer["verdict"] == pass_v:
            print(f"\n  ★ the two lineages disagree — {a.lineage}={a.verdict} against "
                  f"{other}={peer['verdict']} (seq={peer['seq']}).\n"
                  f"  **Fall to the stricter reading.** No admission is generated (one already "
                  f"there needs correcting).", file=sys.stderr)
            _ledger_append(a.by or a.role, "judges_disagreed",
                           {"issue": a.issue, "role": a.role, "for_event": event,
                            a.lineage.replace("-", "_"): a.verdict,
                            other.replace("-", "_"): peer["verdict"]},
                           f"judges_disagreed-{a.issue}-{event}-{digest[:12]}")
            ret = 5
        else:
            print(f"\n  {a.verdict} is not a pass, so no admission is generated (negative from "
                  f"either side is negative).")
            ret = 0
        print(f"  To settle it as a negative, record it with decide:\n"
              f'    python3 "{os.path.join(HERE, "github_sync.py")}" decide --issue {a.issue} '
              f"--event {event} --verdict {a.verdict} --by {a.role} --why \"…\"",
              file=sys.stderr if ret else sys.stdout)
        return ret
    if not peer:
        print(f"\n  The other lineage ({other}) has not judged yet. **No admission is generated "
              f"yet.**\n"
              f"  Order does not matter — this one may go first.\n"
              f'    python3 "{os.path.join(HERE, "org_cycle.py")}" verify '
              f"--issue {a.issue} --role {a.role}")
        return 0

    # Both are in. **Only agreement generates an admission.**
    # **Two judgments with different subjects are not made to agree.** Two passes that looked at
    # different revisions are not agreement (demonstrated in an audit: a joint was generated from an
    # admit of revision A and an admit of revision B).
    if peer.get("subject") != a.subject:
        print(f"\n  ★ the two lineages are looking at **different subjects** — no admission is "
              f"generated.\n"
              f"    {a.lineage:14} subject = {a.subject}\n"
              f"    {other:14} subject = {peer.get('subject') or '(none)'}\n"
              f"  base_sha, reviewed_tree_sha, or the acceptance criteria differ. "
              f"**Two passes that did not look at the same thing are not agreement.**\n"
              f"  Run both again over the same tree:\n"
              f'    python3 "{os.path.join(HERE, "org_cycle.py")}" verify '
              f"--issue {a.issue} --role {a.role}"
              + (f" --phase {a.phase}" if getattr(a, "phase", None) else "")
              + (f"\n  (a provisional from before 0.32.1 carries no subject. That judgment cannot "
                 f"take part in an agreement, so run it again)"
                 if not peer.get("subject") else ""),
              file=sys.stderr)
        return 6

    if peer["verdict"] != a.verdict:
        print(f"\n  ★ the two lineages disagree — {a.lineage}={a.verdict} / "
              f"{other}={peer['verdict']} (seq={peer['seq']}).\n"
              f"  **No admission is generated.** Negative from either side is negative.\n"
              f"  Record the disagreement itself — it is not an anomaly, it is the point of "
              f"separating the lineages:", file=sys.stderr)
        _ledger_append(a.by or a.role, "judges_disagreed",
                       {"issue": a.issue, "role": a.role, "for_event": event,
                        a.lineage.replace("-", "_"): a.verdict,
                        other.replace("-", "_"): peer["verdict"]},
                       f"judges_disagreed-{a.issue}-{event}-{digest[:12]}")
        bad = "reject" if a.role == "gate" else "refuted"
        print(f"  To treat it as a negative, record it as it stands (a negative demands no "
              f"agreement):\n"
              f'    python3 "{os.path.join(HERE, "github_sync.py")}" decide --issue {a.issue} '
              f"--event {event} --verdict {bad} --by {a.role} --why \"…\"", file=sys.stderr)
        return 5

    # **Carry both reasonings over.** 0.32.1 put only the second digest on the record, leaving the
    # first one's why/evidence unreachable from the joint (raised in an audit). The joint's
    # reasoning_sha256 is **derived deterministically from the two digests** — not from either one.
    mine = _provisional_for(a.issue, event, a.lineage)
    pair = {a.lineage: {"seq": mine["seq"], "reasoning_sha256": digest,
                        "reasoning_ref": payload["reasoning_ref"]},
            other: {"seq": peer["seq"], "reasoning_sha256": peer.get("digest"),
                    "reasoning_ref": peer.get("ref")}}
    joint_digest = hashlib.sha256(
        json.dumps({k: v["reasoning_sha256"] for k, v in sorted(pair.items())},
                   sort_keys=True).encode("utf-8")).hexdigest()
    # **A dedicated writer operation generates the joint.** Assembling the payload here and handing
    # it to the generic append makes `require_attested_identity` refuse it for "no receipt", which is
    # a **deadlock where agreement still cannot produce an admission** (no judge receipt exists for a
    # joint — agreement is a function of fact, not a judgment).
    from identity import reviewer_independence
    mine_assurance = {"signer_id": ident.get("signer_id"), "key_id": ident.get("key_id"),
                      "workload_isolation": ident.get("workload_isolation") or "none",
                      "identity_assurance": ident.get("identity_assurance") or "claimed"}
    independence = reviewer_independence(decision_by, mine_assurance, peer.get("assurance"))
    if independence == "same_signer" and mine_assurance.get("signer_id"):
        print(f"\n  ★ the two lineages agree, but **the same signer signed both** "
              f"({mine_assurance['signer_id']}).\n"
              f"  Signed or not, if one key can produce both lineages this is **not independent "
              f"review**.\n"
              f"  **Do not count it as evidence of independence.**", file=sys.stderr)

    args = ["--issue", str(a.issue), "--event", event]
    if os.environ.get("ORG_WRITER_SOCKET"):
        cmd = [sys.executable, os.path.join(HERE, "writer_client.py"),
               "derive-admission", "--", *args]
    else:
        cmd = [sys.executable, os.path.join(HERE, "ledger.py"), "derive-admission", *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        print(f"could not generate the admission: {e}", file=sys.stderr)
        return 4
    if r.returncode != 0:
        print(f"could not generate the admission:\n"
              f"  {((r.stdout or '') + (r.stderr or '')).strip()[:500]}", file=sys.stderr)
        return 4
    print(f"\n  ✓ the two lineages agree on {a.verdict} — generated {event} "
          f"(reviewer_independence={independence}).\n"
          f"  This admission is **a record of agreement, not a judgment**. verdict and why are "
          f"carried over exactly as the judge wrote them.")
    return 0


def _provisional_for(issue, event, lineage):
    """Return the **live** provisional judgment for that Issue, that event, that lineage.

    Voiding follows the shared `voided_seqs` projection. From v2.0.23 the writer-applied
    `effect: voids|records_backfill` is authoritative; only an older ledger derives it from kind for
    compatibility. Special-casing superseded in this function alone makes status and
    derive-admission diverge from the current value (OBS-042).
    """
    try:
        sys.path.insert(0, HERE)
        from discover import ledger_root
        from ledger import voided_seqs
        root = ledger_root()
    except Exception:
        return None
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return None
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = set(voided_seqs(evs))
    want, hit = str(issue).lstrip("#"), None
    for e in evs:
        if e.get("class") != "verdict_provisional" or e.get("seq") in voided:
            continue
        pl = e.get("payload") or {}
        if (str(pl.get("issue", "")).lstrip("#") == want
                and pl.get("for_event") == event and pl.get("lineage") == lineage):
            hit = {"verdict": pl.get("verdict"), "seq": e.get("seq"), "actor": e.get("actor"),
                   "subject": pl.get("review_subject_id"),
                   "digest": pl.get("reasoning_sha256"), "ref": pl.get("reasoning_ref"),
                   # identity (H1) — used to judge independence
                   "decision_by": pl.get("decision_by"),
                   "assurance": {"signer_id": pl.get("signer_id"), "key_id": pl.get("key_id"),
                                 "workload_isolation": pl.get("workload_isolation") or "none",
                                 "identity_assurance": pl.get("identity_assurance") or "claimed"}}
    return hit


def _ledger_append(actor, cls, payload, natural_key, receipt=None):
    """Append one row to the ledger. **Never swallow a failure silently.**

    **Where an org runs writerd, go through the RPC.** Calling ledger.py directly hits "only writerd
    may write", exits 4, and stops the judgment from being recorded (raised by measurement).
    """
    args = ["--actor", actor, "--class", cls, "--natural-key", natural_key,
            "--payload", json.dumps(payload, ensure_ascii=False)]
    if receipt:
        args += ["--receipt", receipt]
    if os.environ.get("ORG_WRITER_SOCKET"):
        cmd = [sys.executable, os.path.join(HERE, "writer_client.py"), "append", "--", *args]
    else:
        cmd = [sys.executable, os.path.join(HERE, "ledger.py"), "append", *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        print(f"could not append to the ledger: {e}", file=sys.stderr)
        return 4
    if r.returncode != 0:
        print(f"the ledger did not accept {cls}:\n"
              f"  {((r.stdout or '') + (r.stderr or '')).strip()[:600]}", file=sys.stderr)
        return 4
    return 0


def cmd_decide(a):
    """Record a JUDGMENT on the task Issue — the verdict AND the reasoning that produced it.

    Human diff review is retired (docs/11 §4f): no person reads the change before it merges. That makes
    the machine's own judgments the only judgments, and an unrecorded judgment is then indistinguishable
    from no judgment at all. A ledger `admission_decided{verdict: admit}` proves a decision HAPPENED and
    is tamper-evident; it does not say what was weighed, what the alternative was, or what evidence was
    consulted — and that is exactly what someone auditing the merge six weeks later needs.

    So every judgment double-writes, the same way a settled convention does (conventions.py): the ledger
    gets the RECEIPT (tamper-evident, machine-queryable), the Issue gets the REASONING (readable, in
    context, next to the work it judged). The Issue is where a decision can actually be inferred later.

    A verdict with an empty or contentless --why is rejected — a bare "admit" is the failure mode this
    command exists to prevent, and accepting it would let the audit trail degrade back into a stamp.
    Admitting also requires --evidence: an admission with nothing consulted IS the stamp."""
    if a.event not in DECISIONS:
        print(f"decide: --event must be a judgment class {DECISIONS}; got {a.event!r}. "
              f"For a progress milestone use `log`.", file=sys.stderr)
        return 2
    why = (a.why or "").strip()
    # integration_admitted presupposes an admit from the gate. **This is refused** — an integration
    # record left without an admit reads later as "it passed".
    if a.event == "integration_admitted" and a.verdict in ("pass", "admit"):
        verdict, actor = _prior_admission(a.issue)
        if verdict != "admit":
            print(f"cannot record integration_admitted: #{a.issue} has no admit from the gate "
                  f"(the ledger's latest is {verdict or 'nothing recorded'}).\n"
                  f"  Take it through the gate first:\n"
                  f'    python3 "{os.path.join(HERE, "org_cycle.py")}" verify '
                  f"--issue {a.issue} --role gate\n"
                  f"  **The quality of the maker's report is no substitute for an admit.** The\n"
                  f"  ledger already runs this same check against phase_started (implement is\n"
                  f"  refused unless design was admitted). An integration record left without an\n"
                  f"  admit reads later as \"it passed\".",
                  file=sys.stderr)
            return 4

    # In an org that declared cross-harness, admit/survives are **generated from the agreement of
    # two lineages** — they cannot be recorded directly. 0.32.0 refused "unless the other is in the
    # ledger", which made either order unrecordable from an empty ledger and left admit forever
    # unreachable (measured: exit=4 in both directions).
    #
    # The correct shape has two stages:
    #   1. `verdict_provisional` — one lineage's judge's judgment. **It carries no authority alone**
    #   2. `admission_decided`   — **assembled by the tool** once the two lineages agree
    #
    # Producing the verdict at stage 2 is plumbing, not judgment (a function of the fact of
    # agreement). Where they disagree the tool cannot produce an admit, so there is no room left for
    # a supervisor to take whichever side suits.
    if a.event in ("admission_decided", "refutation_attempted") \
            and a.verdict in ("admit", "survives") and _org_lineage() == "cross-harness":
        _who = "gate" if a.event == "admission_decided" else "skeptic"
        print(f"{a.event} = {a.verdict} cannot be recorded directly (judges.lineage = "
              f"cross-harness).\n"
              f"  In this org an admit is **generated from the agreement of two lineages**; it is "
              f"not something one judge can place alone.\n"
              f"  Record each lineage's judgment as provisional:\n"
              f'    python3 "{os.path.join(HERE, "github_sync.py")}" provisional '
              f"--issue {a.issue} --role {_who} \\\n"
              f"      --lineage same-harness|cross-harness --verdict {a.verdict} "
              f'--why "…" --evidence "…"\n'
              f"  The moment the second one lands, {a.event} is generated automatically if they "
              f"agree.\n"
              f"  **A negative ({'reject' if _who == 'gate' else 'refuted'}) demands no agreement** "
              f"— negative from either side is negative, so record it with decide as it stands.",
              file=sys.stderr)
        return 4

    # Look at how the supervisor separated the two (a warning, not a refusal — the judgment is the
    # supervisor's job)
    for w in _claim_verify_defect(a):
        print(f"note: {w}", file=sys.stderr)
    bad = _reasoning_defect(why, a.verdict, a.event)
    if bad:
        print(f"decide: --why {bad} With human review retired, this text is the only account of why "
              f"the change was allowed to merge (docs/11 §4f). Say what was weighed and what evidence "
              f"decided it.", file=sys.stderr)
        return 2
    # An admission with no evidence consulted is a stamp regardless of how well the prose reads.
    if a.verdict in ("admit", "pass", "survives", "conforms") and not (a.evidence or "").strip():
        print(f"decide: --evidence is required for verdict {a.verdict!r}. Naming what you actually "
              f"consulted (the command you ran and its real output, the CI run, the repro_lint verdict) "
              f"is what separates a judgment from a stamp — and nobody read the diff (docs/11 §4f).",
              file=sys.stderr)
        return 2
    marker_key = a.event_id or _stable_key(a.event, a.verdict, why)   # sha256; see cmd_log
    marker = f"<!-- orgforge:decision:{marker_key} -->"
    if _already_logged(a.repo, a.issue, marker):
        print(f"decide: decision {marker_key} already on issue #{a.issue} — idempotent no-op.")
        return 0
    icon = {"admit": "✅", "pass": "✅", "survives": "✅", "conforms": "✅",
            "reject": "⛔", "refuted": "⛔", "fail": "⛔",
            "rework": "🔁", "park": "⏸️", "freeze": "🧊"}.get(a.verdict, "•")
    parts = [f"## {icon} {a.event} — `{a.verdict}`"]
    if a.by:
        parts.append(f"**Decided by:** `{a.by}`" + (f" · **phase:** `{a.phase}`" if a.phase else ""))
    elif a.phase:
        parts.append(f"**Phase:** `{a.phase}`")
    parts.append(f"\n**Why (the reasoning):**\n{why}")
    if getattr(a, "claimed", None):
        parts.append(f"\n**Claimed (what was reported — close to the original wording):**\n"
                     f"{a.claimed}")
    if getattr(a, "verified", None):
        parts.append(f"\n**Verified (what the supervisor confirmed themselves — the command and "
                     f"its output):**\n{a.verified}")
    if getattr(a, "evidence", None):
        parts.append(f"\n**Evidence consulted:**\n{a.evidence}")
    if getattr(a, "alternatives", None):
        parts.append(f"\n**Alternatives considered and rejected:**\n{a.alternatives}")
    if getattr(a, "standard", None):
        parts.append(f"\n**Standard applied:** {a.standard}")
    if getattr(a, "risk", None):
        parts.append(f"\n**Known risk accepted:** {a.risk}")
    # TAMPER EVIDENCE (docs/11 §4f.1). A GitHub comment is editable and deletable by anyone with write
    # access — including the agents this record judges — while the ledger is hash-chained. Without a
    # digest an agent could silently rewrite its own account (dropping the --risk it admitted, say) and
    # `ledger verify` would still report the chain intact. So the reasoning is hashed here and the digest
    # is printed for the caller to carry into the ledger receipt as `reasoning_sha256`: re-hashing the
    # comment later either matches, or the account was altered. It does not PREVENT the edit; it makes
    # the edit detectable, which is what "tamper-evident" means.
    digest = _reasoning_digest(why, a.evidence, a.alternatives, a.standard, a.risk)
    parts.append(f"\n`reasoning_sha256: {digest}` — re-hash this record's fields to detect an edit; "
                 f"the ledger receipt carries the same digest.")
    parts.append("\n_No human reviewed this change before merge (docs/11 §4f). This record is the "
                 "account of why it was allowed to._")
    body = "\n".join(parts) + f"\n\n{marker}"

    # **Go through the ledger first.** The controls (refusing self-approval, order violations) live
    # in the ledger, so writing to the Issue first and then being refused leaves the worst kind of
    # mismatch: "the Issue says admit but the ledger has nothing". If it is refused, stop before any
    # record visible from outside exists.
    here = HERE
    payload = {"verdict": a.verdict, "deliverable": str(a.issue), "issue": a.issue,
               "reasoning_sha256": digest,
        **({"lineage": a.lineage} if getattr(a, "lineage", None) else {})}
    # Classifying the root cause of death (Issue #104). Recurrence detection (learning.py repeats)
    # counts by matching roots — unclassified at recording time, a failure with the same root walks
    # past the detector simply by being worded differently.
    # learning.DEATH_ROOTS is the single source for the vocabulary (a test reconciles it against the
    # schema's enum).
    root = (getattr(a, "root", None) or "").strip()
    if root:
        sys.path.insert(0, HERE)
        from learning import DEATH_ROOTS
        if root not in DEATH_ROOTS:
            print(f"decide: --root {root!r} is not in the root-cause-of-death vocabulary. "
                  f"Permitted values:\n"
                  + "\n".join(f"  {k:<24}{v}" for k, v in DEATH_ROOTS.items()),
                  file=sys.stderr)
            return 2
        payload["root"] = root
    if getattr(a, "phase", None):
        payload["phase"] = a.phase
    if getattr(a, "risk", None):
        payload["risk_accepted"] = True
    try:
        _base = ([sys.executable, os.path.join(here, "writer_client.py"), "append", "--"]
                 if os.environ.get("ORG_WRITER_SOCKET")
                 else [sys.executable, os.path.join(here, "ledger.py"), "append"])
        r = subprocess.run(_base + [
                            "--actor", a.by, "--class", a.event,
                            # The idempotency key is unique **per judgment content**. With
                            # `{event}-{issue}`, a second round's judgment collides with the first
                            # and becomes a no-op — and since the idempotency check is evaluated
                            # ahead of the controls, self-approval and order violations walk past
                            # as "already recorded" (confirmed in the field). The digest is built
                            # from verdict/why/evidence, so only a re-run of the same judgment is
                            # correctly a no-op.
                            "--natural-key", f"{a.event}-{a.issue}-{digest[:12]}",
                            "--payload", json.dumps(payload, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=30)
        led_out = ((r.stdout or "") + (r.stderr or "")).strip()
        led_ok = r.returncode == 0
    except Exception as e:
        led_out, led_ok = str(e), False

    if not led_ok:
        print(f"the ledger did not accept it, so nothing was recorded on the Issue "
              f"either:\n  {led_out[:500]}",
              file=sys.stderr)
        if "rejected" in led_out:
            print("\n  This is a control doing its work (self-approval, an order violation, and "
                  "the like). Revisit the judgment itself.", file=sys.stderr)
        return 4

    code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", body])
    if code != 0:
        print(f"gh error posting decision comment: {out}", file=sys.stderr)
        print(f"  note: the ledger already has it ({a.event} #{a.issue}). Only the Issue side is "
              f"missing.\n"
              f"  Re-running with the same arguments makes the ledger an idempotent no-op and fills "
              f"in the Issue alone.",
              file=sys.stderr)
        return 2
    print(f"recorded decision {a.event}={a.verdict} on issue #{a.issue}.")
    print(f"reasoning_sha256={digest}")
    # Print something that can be typed as-is rather than an explanation. In the field the receipt
    # went unwritten (refutation had zero ledger rows) and judgments with no correlation key walked
    # through. `issue` is also the correlation key, so without it DISTINCT_ACTOR / requires_prior
    # cannot identify their subject and the controls themselves stop working.
    print(f"the receipt is recorded in the ledger too ({a.event} #{a.issue}, digest "
          f"{digest[:12]}…).")
    return 0
