"""ブランチと worktree — feature ブランチの決定的な導出と、Issue ごとの作業ツリー。

同一ツリーで並列 maker を走らせると、あるIssueのコミットが別Issueのブランチに載る。"""

import hashlib
import json
import os
import re
import subprocess
import sys

from ._core import (
    _slug,
    gh,
    issue_labels,
)


def derived_branch_name(issue, title):
    """(issue, title) の純関数としての導出名 — 作成時の規約。恒久 identity ではない（#107）:
    タイトルが後から変われば実在の branch とずれるので、**実在の branch を答える文脈**では
    そのまま使わず resolve_issue_branch で突合すること。"""
    if not title:
        # タイトル不明（gh に届かない等）の導出は**本当に** slug 無し。空文字にも _slug は
        # hash（te3b0c442…）を返すので、ここで落とさないと「slug を省く」と告知しながら
        # 幻の hash 付き名を導出する — 告知と実際の名前が食い違う（#107 rework）。
        return f"feat/issue-{issue}"
    slug = _slug(title)
    return f"feat/issue-{issue}-{slug}" if slug else f"feat/issue-{issue}"


def _make_worktree(name, base, issue):
    """ブランチ専用の git worktree を作る — 並列 fan-out の唯一の安全な形。

    **なぜ checkout では駄目なのか。** `git checkout` は*ツリーを切り替える*ので、同一ディレクトリで
    2体の maker を並列に走らせると、片方のコミットがもう片方のブランチに載る。実地でそれが起きた
    （のコミットが `feat/issue-8-settle` に載った）。内容が分離されていたので復旧できたが、
    **同一ツリーで並列に走らせる限り再発する**。

    「毎回正しいブランチにいることを確認する」という運用でこれを防ぐのは、判断に依存する設計であり、
    18 Issue を並列で回せば必ず破れる。worktree なら**物理的に別ディレクトリ**なので、混ざりようがない。

    R0: git の worktree をそのまま借りる。ref ストアも並行制御も作らない。"""
    import os
    import subprocess
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, timeout=30)
    if root.returncode != 0:
        print("git リポジトリの外にいる。", file=sys.stderr)
        return 2
    wt = os.path.join(root.stdout.strip(), ".orgforge", "wt", f"issue-{issue}")
    if os.path.isdir(wt):
        print(f"worktree は既にある（冪等）: {wt}")
        print(f"\ncd {wt}    # ここで作業すること。元のツリーには触らない")
        return 0
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    # ブランチが既にあれば繋ぐ、無ければ base から作る
    p = subprocess.run(["git", "worktree", "add", "-b", name, wt, base],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        p = subprocess.run(["git", "worktree", "add", wt, name],
                           capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(f"worktree を作れない: {(p.stderr or '').strip()[:200]}", file=sys.stderr)
        return 2
    print(f"worktree: {wt}  (branch {name} off {base})")
    print(f"\ncd {wt}    # ここで作業すること。元のツリーには触らない")
    print("完了したら PR を出し、`git worktree remove` で片付ける。")
    return 0


def cmd_branch(a):
    """Print (and optionally create) the DETERMINISTIC feature branch for a task Issue:
    `feat/issue-<N>-<slug-of-title>` off `develop` (the org's branch policy, docs/11 §4c). The name is
    a pure function of (issue number, title), so two makers / a replay derive the SAME branch — the
    reproducibility rule that governs Issue creation, applied to branches. With --create it also runs
    `git checkout -b <name> develop` in the current repo (R0: borrow git; we build no ref store).

    Query mode (no --create/--worktree) answers "which branch IS this Issue's branch" and therefore
    reports only a branch that EXISTS: the Issue worktree's HEAD is authoritative, else the derived
    name if it is a real branch, else fail-closed (#107 — a derived name is a creation convention,
    not durable identity; the title can change after the branch was cut)."""
    labels, err = issue_labels(a.repo, a.issue)  # also validates the Issue exists
    code, out = gh(["issue", "view", str(a.issue), "--repo", a.repo, "--json", "title"])
    if code != 0:
        # slug は名前を読みやすくするだけで、識別子は Issue 番号。GitHub に届かない
        # （オフライン / 認証切れ / repo 未作成）ことを、作業場を用意できない理由にはしない —
        # ここで止めると並列 maker が分離ツリーを持てず、同一ツリーに落ちて混線する。
        # query mode も止めない（#107）: 答えは git（worktree の HEAD / 実在 branch）に
        # あるので、slug 無しで導出して下の実在解決に委ねる。
        print(f"警告: Issue のタイトルを取れなかったので slug を省く（{out.strip()[:80]}）",
              file=sys.stderr)
        title = ""
    else:
        try:
            title = json.loads(out).get("title", "")
        except Exception:
            title = ""
    name = derived_branch_name(a.issue, title)
    if not (getattr(a, "worktree", False) or getattr(a, "create", False)):
        # query mode（#107）: 「この Issue の branch はどれか」への答えは**実在する branch**で
        # なければならない。導出名は作成規約であって恒久 identity ではない — タイトル変更や
        # 手動命名で実在名とずれる（Tatekae OBS-012: 導出 `feat/issue-15-google`、実在
        # `feat/issue-15-login-redirect` → gc が統合済み worktree を「未統合」と誤読）。
        # worktree の HEAD > 実在する導出名 > fail-closed。実在しない名前は黙って印字しない。
        from orgcycle._core import resolve_issue_branch
        resolved, warn, err = resolve_issue_branch(a.issue, derived=name)
        if err:
            print(err, file=sys.stderr)
            return 2
        if warn:
            print(f"警告: {warn}", file=sys.stderr)
        print(resolved)
        return 0
    print(name)
    base = getattr(a, "base", None) or "develop"
    # --worktree は --create を含意する（worktree を作れば分離した作業場ができる）。
    # 並列 fan-out ではこちらが正解 — checkout はツリーを切り替えるので必ず混ざる。
    if getattr(a, "worktree", False):
        return _make_worktree(name, base, a.issue)
    if getattr(a, "create", False):
        import subprocess
        # **worktree で並列運用している org では、メインリポジトリのブランチを切り替えない。**
        # 実地で `--create` がメインを develop から離し、気づかなければ develop での統合テストが
        # 別 Issue のブランチ上で走っていた。`.orgforge/wt/` が既にあるなら worktree 運用と
        # みなし、worktree を作る（`--worktree` と同じ経路）。
        wt_dir = os.path.join(os.getcwd(), ".orgforge", "wt")
        if (not getattr(a, "no_worktree", False)) and os.path.isdir(wt_dir) and any(
                n.startswith("issue-") for n in os.listdir(wt_dir)):
            print(f"注意: この org は worktree で並列運用している（{wt_dir} に "
                  f"{len([n for n in os.listdir(wt_dir) if n.startswith('issue-')])} 個）。\n"
                  f"  メインリポジトリのブランチは切り替えず、worktree を作る — メインが "
                  f"develop から離れると、develop での統合テストが別 Issue のブランチ上で走る。\n"
                  f"  メインで切り替えたいなら --no-worktree を付けること。", file=sys.stderr)
            return _make_worktree(name, base, a.issue)
        try:
            p = subprocess.run(["git", "checkout", "-b", name, base],
                               capture_output=True, text=True, timeout=30)
            if p.returncode != 0:
                # branch may already exist (idempotent) — try to switch to it
                p2 = subprocess.run(["git", "checkout", name], capture_output=True, text=True, timeout=30)
                if p2.returncode != 0:
                    print(f"git error creating/switching branch: {(p.stderr or '')+(p2.stderr or '')}",
                          file=sys.stderr)
                    return 2
                print(f"branch {name} already existed — switched to it (idempotent).", file=sys.stderr)
            else:
                print(f"created and switched to {name} off {base}.\n"
                      f"  ⚠ **メインリポジトリのブランチを切り替えた。** develop での統合テストを"
                      f"走らせる前に `git checkout {base}` で戻すこと"
                      f"（並列運用するなら --worktree を使う）。", file=sys.stderr)
        except Exception as e:
            print(f"git not available: {e}", file=sys.stderr)
            return 2
    return 0
