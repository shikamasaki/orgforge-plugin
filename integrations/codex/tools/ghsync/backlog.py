"""バックログの操作 — 作成・claim・ステージ遷移・分割の検査。

Issue を「働ける状態」に保つ側。判断は含まない。"""

import hashlib
import json
import os
import re
import subprocess
import sys

from ._core import (
    CLAIM_PREFIX,
    _ensure_labels,
    _find_open_issue,
    _issue_number,
    _link_sub_issue,
    gh,
    issue_labels,
)


STAGES = ("ready", "in-progress", "blocked", "needs-human", "done")

# PARKED は「仕事として存在するが、いま着手させない」の機械可読な語彙。Tatekae で
# `[PARKED]` というタイトル散文しか手段が無く、`ready` が止めた仕事を maker に渡した
# （OBS-051 / Issue #103）。ラベルは park/unpark が ensure する（label-ensure list の一部）。
PARKED_LABEL = "orgforge:parked"
PARKED_COLOR = "ededed"

# ready 名簿から外す「着手不能」状態。`orgforge:ready` と同居していても（rework 中や
# ラベル片寄せ漏れ）、こちらが立っている Issue は startable ではない。
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
    # carve-out 経路: rework 中に範囲外発見を切り出した Issue は、例外なく元 Issue に依存する
    # （部品は元の worktree にしか無い）。散文に任せると ready が見えない（Issue #103）。
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


def _prose_dependency_warning(a):
    """Body が他 Issue を `#N` で参照しているのに `Depends on:` 行が無いときの警告文（無ければ None）。

    Tatekae の実測（OBS-051）: carve-out された4 Issue すべてが依存を本文の散文にしか書いておらず、
    `ready` は散文を読まないので着手不能な仕事が maker に渡った。散文を自動で依存に解釈は**しない**
    — 推測は警告より悪い（`#63 を置き換える` は依存ではない）。人間に見える形で大声で言うだけ。"""
    raw = _normalized_body(getattr(a, "body", None))
    refs = list(dict.fromkeys(re.findall(r"#(\d+)", raw)))
    if not refs:
        return None
    declared = bool(getattr(a, "depends", None)) or bool(getattr(a, "carved_from", None)) or \
        any(l.lower().lstrip().startswith("depends on:") for l in raw.splitlines())
    if declared:
        return None
    listed = ", ".join(f"#{r}" for r in refs)
    return (f"WARN: the body references {listed} but declares NO `Depends on:` line. `ready` reads "
            f"only `Depends on:` lines — a dependency written in prose is invisible, and a maker can "
            f"be handed unstartable work (Issue #103). If any of {listed} gates this task, re-run "
            f"with --depends or --carved-from; prose is NOT auto-parsed into dependencies "
            f"(guessing is worse than warning).")


def _issue_state(repo, issue):
    """GitHub Issue の open/closed 状態。

    stage label は backlog の投影だが、GitHub の Issue state も同じ投影の一部である。
    片方だけ動かすと `ready` なのに CLOSED、または `done` なのに OPEN という二つの真実が
    生まれるので、stage 遷移の入口で両方を見る。
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
    _ensure_labels(a.repo, ensure)
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

    # ready/in-progress/blocked/needs-human はすべて「まだ仕事として存在する」状態。
    # CLOSED のまま label だけ戻すと `ready --state open` から永久に見えない。rework の
    # 正式経路も stage ready を通るので、ここで state と label を同じ投影として揃える。
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
        # dependency: parse EVERY "Depends on: #n, #m" line (a body can carry several — carve-out
        # plus needs-human each append one; the old parser kept only the LAST line, so an open
        # dependency on an earlier line was silently dropped, Issue #103). Ready only if all
        # referenced issues are verifiably CLOSED — an unverifiable dependency withholds too:
        # "state unknown" is not proof of startability.
        body = it.get("body") or ""
        deps = []
        for line in body.splitlines():
            if line.lower().lstrip().startswith("depends on:"):
                deps += [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
        blocked = False
        for d in dict.fromkeys(deps):
            if not re.fullmatch(r"#?\d+", d):
                continue   # prose token — not a machine-readable ref; warned at create, never guessed here
            c, o = gh(["issue", "view", d.lstrip("#"), "--repo", a.repo, "--json", "state"])
            state = None
            if c == 0:
                try:
                    state = str(json.loads(o).get("state") or "").upper()
                except Exception:
                    state = None
            if state != "CLOSED":
                blocked = True   # OPEN, or could not be verified
                break
        if not blocked:
            ready.append(it["number"])
    print(json.dumps({"ready": ready}))
    return 0


def cmd_park(a):
    """Issue を PARKED にする — 機械可読なラベルで（タイトル散文 `[PARKED]` の置き換え、Issue #103）。

    parked は「仕事として存在するが、いま着手させない」。`ready` はこのラベルを見て除外する。
    --why は Issue にコメントとして残す — 止めた理由が散文のまま消えると、誰も解除できなくなる。"""
    labels, err = issue_labels(a.repo, a.issue)
    if labels is None:
        print(f"gh error: {err}", file=sys.stderr)
        return 2
    if PARKED_LABEL in labels:
        print(f"issue #{a.issue} is already parked; idempotent no-op.")
        return 0
    _ensure_labels(a.repo, [(PARKED_LABEL, PARKED_COLOR)])
    code, out = gh(["issue", "edit", str(a.issue), "--repo", a.repo, "--add-label", PARKED_LABEL])
    if code != 0:
        print(f"gh error parking: {out}", file=sys.stderr)
        return 2
    why = _normalized_body(getattr(a, "why", None))
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
    """PARKED を解除して Issue を通常の backlog 判定に戻す（`ready` から再び見える）。"""
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
    """CEO（人間）にしか実行できない前提条件を Issue として立てる（docs/11 §0c）。

    **なぜ専用のコマンドが要るのか。** org は自分が作れる作業だけを Issue にし、人間に頼むものは
    コマンドの散文に落としていた。実地の founding で3件（Supabase プロジェクト作成 / Google OAuth
    クライアント登録 / GitHub のブランチ保護設定）がセッションの文章の中にしか存在せず、Issue にも
    台帳にも残らなかった。結果:

      - セッションが切れたら消える（/org-resume でも復元されない）
      - `/org` が GREEN と出すのに、実際は人間待ちで着手できない Issue がある
      - `ready` がブロック済みのタスクを maker に渡す（人間待ちを表現する手段がなかった）
      - coverage-check は「Issue になったか」しか見ないので 66/66 と表示される

    **人間への依頼こそ、忘れられると最も長く止まる。** `orgforge:needs-human` ラベルは
    `/org-init` が作っていたのに、それを立てる手順がどのコマンドにも無く、使用実績は 0 件だった。
    このコマンドがその穴を埋める。

    立てた Issue は通常の task と同じ形なので、下流タスクの `--depends` で縛れる — 人間の作業が
    終わって close されるまで、それに依存する task は `ready` に出てこない。"""
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
    body += ("\n\n---\n**これは CEO（人間）にしか実行できない作業です。** org は着手できません。\n"
             "完了したらこの Issue を close してください — 下流のタスクが自動的に ready になります。")
    if a.blocks:
        blocked = ", ".join(f"#{b.strip().lstrip('#')}" for b in a.blocks.split(",") if b.strip())
        body += f"\n\n**この作業が終わるまで着手できないもの:** {blocked}"
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
        print(f"\nNEXT: これに依存する task の body に `Depends on: #{n}` を書くこと。"
              f"そうすれば人間の作業が終わるまで `ready` に出てこない。")
    return 0


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
            # `#N` の形だけを依存とみなす。数字を全部拾うと散文が誤検出される —
            # 「実装コードは1行も入らない」の「1」が として解釈された（実地で判明）。
            # 同じ依存が本文の複数行に出ると同じ警告が並ぶ（実地で3行出た）。
            # 一度言えば足りる — 同じことを繰り返す警告は、読み飛ばされる側に回る。
            for num in dict.fromkeys(re.findall(r"#(\d+)", line.split(":", 1)[-1])):
                if num and not any(f"depends_on #{num} " in w for w in warnings):
                    c, o = gh(["issue", "view", num, "--repo", a.repo, "--json", "state"])
                    if c == 0 and json.loads(o).get("state") == "OPEN":
                        warnings.append(f"depends_on #{num} is still OPEN — a fresh maker can't take this "
                                        f"green until it lands (single-unit assertion fails, docs/11 §4b).")
    # (c) MUST written in EARS? A body with a MUST/acceptance section but no EARS keyword is prose
    # ("auth works") the gate can't test (docs/11 §4b). Shape check: does an acceptance line use one
    # of WHEN/WHILE/IF/WHERE/SHALL? Only checked if the Issue actually has a MUST/acceptance section.
    low_body = body.lower()
    if ("must" in low_body or "acceptance" in low_body) and "shall" not in low_body \
            and not any(kw in body for kw in ("WHEN ", "WHILE ", "IF ", "WHERE ")):
        warnings.append("the MUST/acceptance criteria are not in EARS (no WHEN/WHILE/IF/WHERE/SHALL) — "
                        "prose like \"auth works\" isn't testable; rewrite each as an EARS pattern "
                        "(docs/11 §4b), so the gate has a checkable bar.")
    # (d) 守る対象の偏り — 認可を扱う deliverable なのに、**何が守られているか**が偏っていないか。
    #
    # 運用で見つかった形: 12件の MUST のうち認可を定めているのは2件だけで、その1件は「あだ名」
    # （装飾的なテキスト列）だった。金額・支払者・債務の向き・グループ所有権については
    # 一行も無い。skeptic の言葉では「装飾的なテキスト列を守り、金額・支払者・債務の向き・
    # グループ所有権を無防備にしていた」。結果、後半6周の rework は Issue のどの MUST にも
    # 対応しない作業になった。
    #
    # **起票時に気づける材料**を出す（判定はしない — 何を守るべきかは人が決める）。
    must_lines = [l for l in body.splitlines()
                  if re.search(r"\bSHALL\b|しなければならない|するものとする", l)]
    AUTHZ_DOMAIN = ("RLS", "ROW LEVEL SECURITY", "権限", "認可", "policy", "grant",
                    "SECURITY DEFINER", "拒否", "許可")
    if len(must_lines) >= 6 and sum(1 for w in AUTHZ_DOMAIN if w in body) >= 2:
        authz_musts = [l for l in must_lines if any(k in l for k in AUTHZ_DOMAIN)]
        # 「入った後に何ができるか」を定めた MUST があるか。**内側の主体**が出てくるかで見る。
        # 資産名（金額・支払）で判定すると `SUM(shares.amount) = expenses.amount` のような
        # 整合性制約を「金額を守っている」と誤読する — あれは認可ではない。
        INSIDE = ("メンバーが", "メンバー同士", "他のメンバー", "他人の", "作成者", "所有者",
                  "自分以外", "owner", "creator", "member who", "書き換え")
        # 「非メンバーが」は境界の話。部分一致で内側に数えると、境界しか定めていない Issue が
        # 「内側も定めている」ことになり、この検査が丸ごと無効になる（運用の例では がそうだった）。
        OUTSIDE = ("非メンバー", "non-member", "未認証", "unauthenticated", "anonymous")
        guarded = [l for l in authz_musts
                   if any(k in l for k in INSIDE) and not any(o in l for o in OUTSIDE)]
        # あだ名・表示名だけを守っているなら、それは「守っている」に数えない（運用で観測）
        DECORATIVE = ("あだ名", "表示名", "nickname", "display_name", "アイコン", "avatar")
        substantive = [l for l in guarded if not any(d in l for d in DECORATIVE)]
        if authz_musts and not substantive:
            warnings.append(
                f"MUST {len(must_lines)} 件中、認可を定めているのは {len(authz_musts)} 件だが、"
                f"**「入った後に何ができるか」を定めたものが無い**"
                + (f"（内側に触れているのは装飾的な列だけ: "
                   f"{', '.join(l.strip()[:28] for l in guarded[:2])}…）" if guarded else "") + "。"
                f"実地では、この形の Issue が「装飾的なテキスト列を守り、金額・支払者・債務の向き・"
                f"所有権を無防備にする」状態を生み、12周の rework になった。"
                f"認可は「誰が入れるか」と「入った後に何ができるか」の両方で成立する — "
                f"**内側の規則**が要求として書かれているか確認すること。")

    # (e) 壊れ方が何種類あるか — `owns` が同じでも、**壊れ方と検証手段が違えば別 Issue**。
    # 運用では「スキーマの形（型・制約）」と「認可（攻撃シナリオ）」を1つに束ねており、
    # gate が毎回両方を見ることになり、一方の修正が他方を壊し続けた（migration 5本が相互干渉）。
    FAILURE_MODES = {
        "スキーマ/型の誤り": ("型", "制約", "schema", "column", "not null", "型検査", "migration"),
        "認可の穴": ("RLS", "権限", "認可", "policy", "grant", "SECURITY DEFINER", "非メンバー"),
        "計算の誤り": ("端数", "合計", "配分", "計算", "金額が一致", "SUM"),
        "配信/実行環境": ("Service Worker", "PWA", "CI", "ビルド", "デプロイ", "キャッシュ"),
    }
    hit = [k for k, kws in FAILURE_MODES.items() if sum(1 for w in kws if w in body) >= 2]
    if len(hit) > 1:
        warnings.append(
            f"壊れ方が {len(hit)} 種類ある: {' / '.join(hit)}。"
            f"**`owns` が同じでも、壊れ方と検証手段が違えば別 Issue** — 束ねると gate が毎回"
            f"「どこを見るか」から始めることになり、一方の修正が他方を壊す"
            f"（相互に干渉するマイグレーションを生む）。"
            f"「この deliverable が壊れたとき、壊れ方は1種類か」を問うこと。")

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
