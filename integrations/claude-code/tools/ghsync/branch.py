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
    `git checkout -b <name> develop` in the current repo (R0: borrow git; we build no ref store)."""
    labels, err = issue_labels(a.repo, a.issue)  # also validates the Issue exists
    code, out = gh(["issue", "view", str(a.issue), "--repo", a.repo, "--json", "title"])
    if code != 0:
        # slug は名前を読みやすくするだけで、識別子は Issue 番号。GitHub に届かない
        # （オフライン / 認証切れ / repo 未作成）ことを、作業場を用意できない理由にはしない —
        # ここで止めると並列 maker が分離ツリーを持てず、同一ツリーに落ちて混線する。
        if not (getattr(a, "worktree", False) or getattr(a, "create", False)):
            print(f"gh error: {out}", file=sys.stderr)
            return 2
        print(f"警告: Issue のタイトルを取れなかったので slug を省く（{out.strip()[:80]}）",
              file=sys.stderr)
        title = ""
    else:
        try:
            title = json.loads(out).get("title", "")
        except Exception:
            title = ""
    slug = _slug(title)
    name = f"feat/issue-{a.issue}-{slug}" if slug else f"feat/issue-{a.issue}"
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
