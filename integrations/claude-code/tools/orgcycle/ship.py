"""成果物を外に出す — handback / integrate。

PR を作り、develop へ fan-in する。マージするかどうかは判定しない —
前提（gate の admit と skeptic の survives）が台帳に揃っているかを照合するだけ。"""

import json
import os
import re
import sys

from ._core import (
    _admission_for,
    _branch_for,
    _execute,
    _gh_sync,
    _issue_body,
    _ledger,
    _raw,
    _refutation_for,
    _repo,
)


def _resolve_integration_branch(issue, requested=None):
    """Resolve one durable local branch + commit for an Issue, or return an actionable error.

    The deterministic title slug is a creation convention, not durable identity: a branch can be
    renamed or recreated after the Issue title changes. Never turn a missing ref into a zero-change
    preview. Exact explicit ``--branch`` values are existence-checked; implicit resolution may use a
    sole ``feat/issue-N[-…]`` candidate, but ambiguity and local/tracking divergence always stop.
    A tracking-only ref is diagnostic, not a merge target: without a local branch we cannot know
    whether the last fetch is fresh, so the operator must fetch/checkout explicitly.
    """
    derived = requested or _branch_for(issue)
    prefix = f"feat/issue-{issue}"
    requested_logical = derived[len("origin/"):] if derived.startswith("origin/") else derived
    code, out = _raw([
        "git", "for-each-ref", "--format=%(refname:short)",
        "refs/heads", "refs/remotes/origin",
    ])
    if code != 0:
        return None, None, "git branch refs を列挙できないため、統合対象を確認できない。"

    entries = {}

    def add(logical, ref, available):
        is_issue_candidate = logical == prefix or logical.startswith(prefix + "-")
        if not is_issue_candidate and not (requested and logical == requested_logical):
            return
        entry = entries.setdefault(logical, {"local": None, "tracking": None})
        if available == "local":
            entry["local"] = ref
        elif available == "tracking":
            entry["tracking"] = ref

    for ref in (out or "").splitlines():
        ref = ref.strip()
        if not ref:
            continue
        if ref.startswith("origin/"):
            add(ref[len("origin/"):], ref, "tracking")
        else:
            add(ref, ref, "local")

    def resolve(logical):
        entry = entries.get(logical) or {}
        local, tracking = entry.get("local"), entry.get("tracking")

        def sha(ref):
            if not ref:
                return None
            rc, value = _raw(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"])
            return value.strip() if rc == 0 and value.strip() else None

        local_sha, tracking_sha = sha(local), sha(tracking)
        if local and not local_sha:
            return None, None, f"local ref {local} の commit を解決できない。"
        if tracking and not tracking_sha:
            return None, None, f"tracking ref {tracking} の commit を解決できない。"
        if local_sha and tracking_sha and local_sha != tracking_sha:
            return None, None, (f"{logical} の local/tracking が分岐している: "
                                f"local={local_sha[:12]}, tracking={tracking_sha[:12]}。"
                                "fetch/rebase/merge で一致させるか、確認済みcommit SHAを "
                                "--branch で明示してから統合すること。")
        if local_sha:
            return local, local_sha, None
        if tracking_sha:
            return None, None, (f"候補 {tracking} は tracking ref のみにある。"
                                "`git fetch --prune origin` と checkout を行い、"
                                "local branch として内容を確認してから統合すること。")
        return None, None, None

    exact_ref, exact_sha, exact_error = resolve(requested_logical)
    if exact_error:
        return None, None, exact_error
    if exact_ref:
        return exact_ref, exact_sha, None

    candidate_names = sorted(entries)
    candidate_text = ", ".join(candidate_names) if candidate_names else "なし"
    if requested:
        # An immutable commit SHA (or tag) is a valid explicit override even when it is not an Issue
        # branch. The merge below uses this resolved SHA, so a later ref move cannot change subject.
        rc, explicit_sha = _raw(["git", "rev-parse", "--verify", f"{derived}^{{commit}}"])
        if rc == 0 and explicit_sha.strip():
            return derived, explicit_sha.strip(), None
        return None, None, (f"--branch {derived} がlocal/tracking refsに存在しない。"
                            f" Issue候補: {candidate_text}。必要なら `git fetch --prune origin` 後に"
                            "再実行すること。")

    if len(candidate_names) == 1:
        only = candidate_names[0]
        ref, subject_sha, error = resolve(only)
        if error:
            return None, None, error
        if ref:
            return ref, subject_sha, None
    if not candidate_names:
        return None, None, (f"導出した branch {derived} が存在せず、local/tracking refsに "
                            f"{prefix}* の候補も無い。`git fetch --prune origin` 後に再実行するか、"
                            "先に begin/handback するか、--branch を渡すこと。")
    return None, None, (f"導出した branch {derived} が存在せず、候補が複数ある: "
                        f"{candidate_text}。統合対象を --branch で明示すること。")


def _integrate_preview(issue, branch, subject_sha, base, test):
    """統合前に「何を統合するか」を見せる。**衝突しそうな箇所の予告が主目的。**

    統合後に失敗が出ても、その多くが worktree 走査の偽陽性で、切り分けに時間がかかる。
    事前に分かれば早い。並行する他の worktree が同じファイルを触っていれば、それも出す —
    複数の Issue が並行して同じマニフェストを触っている状態では、「後で分かる」より
    「先に見える」ほうが安い。
    """
    code, base_sha = _raw(["git", "rev-parse", "--verify", f"{base}^{{commit}}"])
    if code != 0 or not base_sha.strip():
        return (f"{branch} → {base}\n  ✗ base ref {base} が存在しない。",
                {}, "base ref missing")
    code, verified_subject = _raw([
        "git", "rev-parse", "--verify", f"{subject_sha}^{{commit}}",
    ])
    if code != 0 or verified_subject.strip() != subject_sha:
        return (f"{branch} → {base}\n  ✗ 解決済み subject {subject_sha[:12]} が利用できない。",
                {}, "subject commit missing")

    L = [f"{branch} @ {subject_sha[:12]} → {base}"]
    code, files = _raw(["git", "diff", "--name-only", f"{base_sha.strip()}...{subject_sha}"])
    if code != 0:
        return ("\n".join(L + ["  ✗ refs は存在するが git diff に失敗した。"]),
                {}, "git diff failed")
    changed = [f for f in (files or "").split("\n") if f.strip()]
    L.append(f"  変更: {len(changed)} files")
    for f in changed[:12]:
        L.append(f"    {f}")
    if len(changed) > 12:
        L.append(f"    … 他 {len(changed) - 12} 件")

    code, ahead = _raw(["git", "log", "--oneline", f"{base_sha.strip()}..{subject_sha}"])
    if code != 0:
        return ("\n".join(L + ["  ✗ commit range を読めない。branch の実在を再確認すること。"]),
                {}, "git log failed")
    n = len([x for x in (ahead or "").split("\n") if x.strip()])
    L.append(f"  コミット: {n} 件")

    # 並行している他の worktree と同じファイルを触っていないか
    wt_base = os.path.join(os.getcwd(), ".orgforge", "wt")
    overlaps = {}
    if os.path.isdir(wt_base):
        for name in sorted(os.listdir(wt_base)):
            if not name.startswith("issue-") or name == f"issue-{issue}":
                continue
            other = name[len("issue-"):]
            ob = _branch_for(other)
            c2, of = _raw(["git", "diff", "--name-only", f"{base}...{ob}"])
            if c2 != 0:
                continue
            shared = sorted(set(changed) & {x for x in (of or "").split("\n") if x.strip()})
            if shared:
                overlaps[other] = shared
    for other, shared in overlaps.items():
        L.append(f"  ⚠ #{other} も同じファイルを変更しています: {', '.join(shared[:5])}")

    # CI のワークフローを触る統合は、**どの job にステップが入ったか**を見せる。
    # YAML として妥当でテストが緑でも、**条件付きでしか走らない job にステップが入ると
    # その検査は一度も走らない**。運用では union でのマージ結果が条件付き job の末尾に入り、
    # 依存する Issue が未統合の間、追加した検査が動いていなかった。
    # **YAML の意味は読まない** — job 名と `if:` の有無だけを出す。判定は人がする。
    for f in changed:
        if not re.search(r"\.github/workflows/.+\.ya?ml$", f):
            continue
        code, ci = _raw(["git", "show", f"{subject_sha}:{f}"])
        if code != 0:
            continue
        # **`jobs:` 配下だけを見る。** トップレベルには `on:` `permissions:` などがあり、
        # その子（`pull_request:` `push:`）を job と誤認する（最初の実装がそうなった）。
        jobs, cur, conditional = [], None, set()
        in_jobs = False
        for line in (ci or "").split("\n"):
            if re.match(r"^jobs:\s*$", line):
                in_jobs = True
                continue
            if in_jobs and re.match(r"^\S", line):
                in_jobs = False          # 次のトップレベルキーで抜ける
            if not in_jobs:
                continue
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if m:
                cur = m.group(1)
                jobs.append(cur)
                continue
            # job 自身の `if:` と、その job のどれかの step の `if:` の両方を数える —
            # どちらでも「条件を満たさない間その検査は走らない」ことになる
            # step の `if:` は `- if: …` の形でも書ける（リストの先頭要素）。ハイフンを
            # 見落とすと、**まさに捕まえたい形**（step 単位の条件付き実行）を落とす。
            if cur and re.match(r"^\s{4,}(?:-\s+)?if:\s*\S", line):
                conditional.add(cur)
        if jobs:
            L.append(f"  ⚠ CI を触っている: {f}")
            L.append(f"      job: {', '.join(j + '（if: 条件付き）' if j in conditional else j for j in jobs)}")
            if conditional:
                L.append(f"      **条件付きの job がある。** 追加したステップがそこに入っていると、"
                         f"条件を満たさない間その検査は一度も走らない — YAML が妥当でテストが"
                         f"緑でも、検査していないことに気づけない。入った先を確かめること。")

    # develop の現状（統合先が既に壊れていないか）
    L.append(f"  統合後に走るもの: {test}")
    return "\n".join(L), overlaps, None


def _plan_integrate(a, branch, subject_sha, base):
    body, overlaps, preview_error = _integrate_preview(
        a.issue, branch, subject_sha, base, a.test)
    print(body)
    if preview_error:
        return 3
    av, aseq, _ = _admission_for(a.issue)
    rv, rseq, _ = _refutation_for(a.issue)
    print(f"  gate: {av or '記録なし'}" + (f"（seq {aseq}）" if aseq else "")
          + f" · skeptic: {rv or '記録なし'}" + (f"（seq {rseq}）" if rseq else ""))
    if not (av == "admit" and rv == "survives"):
        print("  → 前提が揃っていないので、このまま integrate しても止まる。")
    elif overlaps:
        print("  → 統合できるが、上の重複は先に見ておくこと"
              "（衝突は統合後に分かるより前に分かるほうが安い）。")
    else:
        print("  → 統合できる。")
    return 0


def cmd_handback(a):
    """C: feature ブランチを push し、develop 宛の PR を作り、Issue に紐付ける。

    /org-work §4 は「各 child の feature ブランチ → PR → develop」と書いていたが、PR を作る
    ツールが無かった。結果として実地では PR がゼロ件になり、`git merge` で直接統合され、
    統合済みの Issue が OPEN のまま残った。**GitHub で運用する前提が成立していなかった。**

    body に `Closes #N` を入れるので、develop へのマージで Issue が自動 close される。
    マージするかどうかは判定しない — PR を作るところまでが配管。
    """
    branch, subject_sha, branch_error = _resolve_integration_branch(a.issue, a.branch)
    if branch_error:
        print(f"handback branch を解決できない（#{a.issue}）: {branch_error}", file=sys.stderr)
        return 3
    local_code, _ = _raw(["git", "show-ref", "--verify", f"refs/heads/{branch}"])
    if local_code != 0:
        print(f"handback は push できる local branch が必要だが、{branch} は local branch "
              "ではない。branch を checkout してから再実行すること。", file=sys.stderr)
        return 3
    base = a.base or "develop"

    # 前提: gate の admit（PR は「見せる」ためのものなので skeptic 前でも作れてよい）
    av, aseq, _ = _admission_for(a.issue)

    title, body = _issue_body(a.issue)
    if title is None:
        title = f"Issue #{a.issue}"

    # 既に PR があれば作り直さない（冪等）
    code, out = _raw(["gh", "pr", "list", "--head", branch, "--json", "number,url", "--limit", "1"]
                     + (["--repo", _repo()] if _repo() else []))
    existing = None
    if code == 0:
        try:
            arr = json.loads(out or "[]")
            existing = arr[0] if arr else None
        except Exception:
            pass

    pr_body = [
        f"Closes #{a.issue}",
        "",
        f"## 何を作ったか",
        a.summary or "(--summary で1行)",
        "",
        "## DoD の実出力",
        "```",
        (a.result or "(--result に実際の出力を貼ること)").strip(),
        "```",
        "",
        f"## 判定",
        (f"gate: `{av}`（ledger seq {aseq}）" if av else
         "gate の admission はまだ。`org_cycle.py verify --issue %d --role gate`" % a.issue),
        "",
        f"仕様は #{a.issue} の本文。判断の理由は同 Issue のコメントに記録されている"
        f"（人間の diff レビューは廃止 — docs/11 §4f）。",
    ]

    steps = [
        (f"{branch} を push",
         lambda: _raw(["git", "push", "-u", "origin", branch])),
    ]
    if existing:
        print(f"既に PR がある: {existing.get('url')} — 作り直さない（push だけ更新）")
    else:
        steps.append(
            (f"PR を作成（{branch} → {base}）",
             lambda: _raw(["gh", "pr", "create", "--base", base, "--head", branch,
                           "--title", f"{title} (#{a.issue})",
                           "--body", "\n".join(pr_body)]
                          + (["--repo", _repo()] if _repo() else []))))
    rc = _execute(steps, f"handback #{a.issue} → {base}")
    if rc != 0:
        return rc

    code, out = _raw(["gh", "pr", "list", "--head", branch, "--json", "url", "--limit", "1"]
                     + (["--repo", _repo()] if _repo() else []))
    url = ""
    try:
        arr = json.loads(out or "[]")
        url = arr[0]["url"] if arr else ""
    except Exception:
        pass

    # B: ツールが知っている事実は自動で入れる。人が書くのは summary だけ。
    return _execute([
        (f"log handback_opened → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "handback_opened",
                          "--event-id", f"handback-{a.issue}",
                          "--detail", f"{branch} → {base} の PR を作成: {url or '(URL 未取得)'}",
                          "--command", f"gh pr create --base {base} --head {branch}",
                          "--result", (a.result or out or "PR created").strip()[:4000],
                          "--files", a.files or branch,
                          "--next-step", f"skeptic → `org_cycle.py integrate --issue {a.issue}`")),
    ], f"record handback #{a.issue}")


def cmd_integrate(a):
    """develop への fan-in を回す。**マージするかどうかは判定しない** — 前提が揃っているかを
    照合し、揃っていれば機械的な手順（マージ → 統合後テスト → 記録）を実行する。

    fan-out が半分なら fan-in は残り半分で、そこが散文の手順書のままだと抜ける。実地では
    が「refutation が台帳に無いまま統合され、integration_admitted も記録されなかった」。
    最も抜けやすいのは統合の直前なので、そこを配管にする。
    """
    if getattr(a, "plan", False):
        branch, subject_sha, branch_error = _resolve_integration_branch(a.issue, a.branch)
        if branch_error:
            print(f"統合対象 branch を解決できない（#{a.issue}）: {branch_error}", file=sys.stderr)
            return 3
        return _plan_integrate(a, branch, subject_sha, a.base or "develop")
    av, aseq, _ = _admission_for(a.issue)
    rv, rseq, _ = _refutation_for(a.issue)
    problems = []
    if av != "admit":
        problems.append(f"gate の admit が無い（verdict={av or '記録なし'}）— "
                        f"`org_cycle.py verify --issue {a.issue} --role gate`")
    if rv != "survives":
        problems.append(f"skeptic の survives が無い（verdict={rv or '記録なし'}）— "
                        f"`org_cycle.py verify --issue {a.issue} --role skeptic`")
    if problems and not a.force:
        print(f"統合の前提が揃っていない（#{a.issue}）:", file=sys.stderr)
        for x in problems:
            print(f"  ✗ {x}", file=sys.stderr)
        print("\ndocs/11 / agents/gate.md: skeptic の反証を生き延びたものだけが先に進める。\n"
              "Issue にコメントがあっても台帳に無ければ「記録されていない」— 二重記録の"
              "片側だけが落ちるのが実地の失敗形なので、ここは台帳を見る。\n"
              "前提を承知で進めるなら --force（理由は --why に書くこと）。", file=sys.stderr)
        return 4

    branch, subject_sha, branch_error = _resolve_integration_branch(a.issue, a.branch)
    if branch_error:
        print(f"統合対象 branch を解決できない（#{a.issue}）: {branch_error}", file=sys.stderr)
        return 3
    base = a.base or "develop"
    # 統合テストの実出力を保持する。**integrate 自身が log の必須検査に引っかかっていた** —
    # マイルストーンの log は --command/--result を要求するのに、integrate はそれを渡さず、
    # 統合は完了するのに Issue へのログだけ落ちていた（実地で人が手で補った）。
    # 自分で走らせた結果を持っているのだから、人に書かせる理由が無い。
    test_out = {"text": ""}

    def _run_test():
        code, out = _raw(a.test.split())
        test_out["text"] = (out or "").strip()
        return code, out

    steps = [
        (f"{base} に切り替え",
         lambda: _raw(["git", "checkout", base])),
        (f"{branch} @ {subject_sha[:12]} を --no-ff でマージ",
         lambda: _raw(["git", "merge", "--no-ff", subject_sha,
                       "-m", f"Merge {branch} into {base} (#{a.issue})"])),
        (f"統合後の全体テスト: {a.test}", _run_test),
    ]
    rc = _execute(steps, f"integrate #{a.issue} → {base}")
    if rc != 0:
        print(f"\n統合を止めた。{base} の状態を確認すること"
              f"（マージ済みでテストが落ちたなら、戻すか直すかは判断）。", file=sys.stderr)
        return rc

    # ここまで来たら「combined suite が green」— それが integrate gate の機械的な形（docs/11 §4c）
    rec = [
        (f"integration_admitted を記録",
         lambda: _ledger("append", "--actor", a.role, "--class", "integration_admitted",
                         "--natural-key", f"integrate-{a.issue}",
                         "--payload", json.dumps({"integration_branch": base,
                                                  "deliverables": [str(a.issue)],
                                                  "issue": a.issue,
                                                  "integration_subject_sha": subject_sha,
                                                  "combined_ci_ref": a.test,
                                                  "verdict": "pass"}, ensure_ascii=False))),
        (f"log → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "integration_admitted",
                          "--event-id", f"integrate-{a.issue}",
                          "--detail", (f"{branch} @ {subject_sha[:12]} → {base} に統合、"
                                       f"統合後 `{a.test}` green"),
                          "--command", a.test,
                          "--result", (test_out["text"] or "(統合テストの出力が空)")[-4000:],
                          "--files", f"{branch}@{subject_sha}")),
    ]
    return _execute(rec, f"record integrate #{a.issue}")
