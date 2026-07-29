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


def _integrate_preview(issue, branch, base, test):
    """統合前に「何を統合するか」を見せる。**衝突しそうな箇所の予告が主目的。**

    実地では #7 の統合後に10件失敗し、切り分けに時間を使った（8件が worktree 走査の
    偽陽性）。事前に分かれば早い。並行する他の worktree が同じファイルを触っていれば、
    それも出す — #9/#10/#11 が並行し package.json を3つとも触っている状態では、
    「後で分かる」より「先に見える」ほうが安い。
    """
    L = []
    code, files = _raw(["git", "diff", "--name-only", f"{base}...{branch}"])
    changed = [f for f in (files or "").split("\n") if f.strip()]
    L.append(f"{branch} → {base}")
    L.append(f"  変更: {len(changed)} files")
    for f in changed[:12]:
        L.append(f"    {f}")
    if len(changed) > 12:
        L.append(f"    … 他 {len(changed) - 12} 件")

    code, ahead = _raw(["git", "log", "--oneline", f"{base}..{branch}"])
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

    # develop の現状（統合先が既に壊れていないか）
    L.append(f"  統合後に走るもの: {test}")
    return "\n".join(L), overlaps


def _plan_integrate(a, branch, base):
    body, overlaps = _integrate_preview(a.issue, branch, base, a.test)
    print(body)
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
    branch = a.branch or _branch_for(a.issue)
    base = a.base or "develop"

    # 前提: gate の admit（PR は「見せる」ためのものなので skeptic 前でも作れてよい）
    av, aseq, _ = _admission_for(a.issue)

    title, body = _issue_body(a.issue)
    if title is None:
        title = f"Issue #{a.issue}"

    code, out = _raw(["git", "rev-parse", "--verify", branch])
    if code != 0:
        print(f"ブランチ {branch} が無い。--branch で渡すか、先に begin すること。", file=sys.stderr)
        return 3

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
    #8 が「refutation が台帳に無いまま統合され、integration_admitted も記録されなかった」。
    最も抜けやすいのは統合の直前なので、そこを配管にする。
    """
    if getattr(a, "plan", False):
        return _plan_integrate(a, a.branch or _branch_for(a.issue), a.base or "develop")
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

    branch = a.branch or _branch_for(a.issue)
    base = a.base or "develop"
    steps = [
        (f"{base} に切り替え",
         lambda: _raw(["git", "checkout", base])),
        (f"{branch} を --no-ff でマージ",
         lambda: _raw(["git", "merge", "--no-ff", branch,
                       "-m", f"Merge {branch} into {base} (#{a.issue})"])),
        (f"統合後の全体テスト: {a.test}",
         lambda: _raw(a.test.split())),
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
                                                  "combined_ci_ref": a.test,
                                                  "verdict": "pass"}, ensure_ascii=False))),
        (f"log → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "integration_admitted",
                          "--event-id", f"integrate-{a.issue}",
                          "--detail", f"{branch} → {base} に統合、統合後 `{a.test}` green")),
    ]
    return _execute(rec, f"record integrate #{a.issue}")
