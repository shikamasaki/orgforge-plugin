"""org_cycle の共有部品 — 実行・台帳・GitHub・識別子の解決。

ここに置くのは「どのサブコマンドからも使う」ものだけ。特定のサブコマンド専用の
ヘルパは、そのサブコマンドのモジュールに置く（core が肥大すると分割の意味が消える）。"""

import hashlib
import json
import os
import re
import subprocess
import sys


# tools/ を指す。**このファイルは tools/orgcycle/ に居るので、親を1つ上る。**
# 分割時にここを直し忘れ、_gh_sync が github_sync.py を見失って `_branch_for` が
# slug 無しのブランチ名を返した（実地で show の実装行と integrate --plan の変更一覧が
# 黙って空になった）。組み立て系のツールは「見つからない」を静かに素通りするので、
# パスの基点は分割で最初に壊れる場所になる。
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def _run(args, capture=True):
    """python3 <tool> ... を実行。(code, out) を返す。

    戻り値は stdout+stderr を混ぜたものなので、**呼ばれた側の banner が混ざる**。
    `_branch_for` は先頭行を取るので今は無事だが、混ざりうる構造そのものを消す
    （0.22.1 で「静かに壊れる」経路を1つ踏んだばかりである）。
    """
    env = dict(os.environ, ORG_QUIET="1")
    p = subprocess.run([sys.executable] + args, capture_output=capture, text=True,
                       timeout=60, env=env)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")) if capture else ""


def _raw(args):
    """外部コマンドをそのまま実行。(code, out) — _run は python3 を前置するので gh には使えない。"""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout or "")
    except Exception as e:
        return 1, str(e)


def _ledger(*args):
    return _run([os.path.join(HERE, "ledger.py")] + list(args))


def _gh_sync(*args):
    return _run([os.path.join(HERE, "github_sync.py")] + list(args))


def _repo():
    import discover
    return discover.backlog_repo()


def resolve_integration_base(explicit=None, start=None):
    """統合先 ref を決める。明示 --base > constitution の enforcement.judges.integration_ref。

    どちらも無ければ ``(None, 理由)`` を返す — **develop を推測しない**（#106）。
    Tatekae 実測では constitution が `integration_ref: origin/main` を宣言しているのに
    begin/show/gc/integrate が develop を hard-code し、「統合先はどこか」への答えが
    1製品内に複数あった（OBS-048/053/054/057）。verify が使う解決
    （review_freshness.integration_ref_policy — #81）をそのまま共有し、第二のパーサは書かない。
    """
    if explicit:
        return str(explicit), None
    try:
        from discover import constitution
        path = constitution(start)
    except Exception:
        path = None
    from review_freshness import integration_ref_policy
    declared, ref, err = integration_ref_policy(path)
    if err:
        return None, f"integration ref policy が不正: {err}"
    if declared and ref:
        return ref, None
    return None, ("統合先が決まらない。develop があるというだけで推測はしない（#106）。\n"
                  "  constitution.yaml に `enforcement.judges.integration_ref: origin/main` "
                  "のように宣言するか、\n"
                  "  今回だけ `--base <ref>` を明示すること。")


def local_branch_for(ref, cwd=None):
    """checkout / PR base に使える branch 名。remote-tracking ref（origin/X）は X に写す。

    integration_ref は「どこへ統合するか」の宣言なので origin/main のような remote-tracking
    形で書かれる。`git checkout origin/main` は detached HEAD、`gh pr create --base origin/main`
    はエラーになるので、実際に checkout / PR する文脈だけ branch 名に写す（判定・diff は
    ref のまま使う）。"""
    code, _ = _raw(["git"] + (["-C", cwd] if cwd else [])
                   + ["rev-parse", "--verify", "--quiet", f"refs/remotes/{ref}"])
    if code == 0 and "/" in ref:
        return ref.split("/", 1)[1]
    return ref


def _execute(steps, label):
    """順に実行し、最初の失敗で止める。**部分適用のまま黙って進まない**こと —
    台帳の整合が崩れた状態を「成功」と報告するのが最悪なので、どこで止まったかを言う。"""
    print(f"— {label} —")
    for i, (desc, fn) in enumerate(steps, 1):
        code, out = fn()
        tail = (out or "").strip().split("\n")[-1][:110]
        if code == 0:
            print(f"  {i}. ✓ {desc}")
        elif code == 10:
            print(f"  {i}. ⚠ {desc} — contended: {tail}", file=sys.stderr)
            print(f"\n止めた（{i}/{len(steps)} まで実行）。別のセッションが持っている。",
                  file=sys.stderr)
            return 10
        else:
            print(f"  {i}. ✗ {desc}\n      {tail}", file=sys.stderr)
            print(f"\n止めた（{i-1}/{len(steps)} まで実行済み）。ここから先は打っていない。\n"
                  f"台帳が拒否したなら順序違反（docs/11 §2）— 前提を満たしてから再実行すること。\n"
                  f"再実行は安全: 各イベントは natural-key で冪等なので、済んだ分は no-op になる。",
                  file=sys.stderr)
            return 3
    print(f"  完了（{len(steps)} 件）")
    return 0



# ── verify（案2）: 配管だけを引き受ける ──────────────────────────────────────
# ここが持ってよいのは「gate/skeptic を正しい材料つきで起動する」ことだけ。
# verdict / why / risk / どのミューテーションを試すか は一切決めない。
# ツールが判定した瞬間に gate は形骸化するので、その線は越えない。


def _today():
    code, out = _raw(["date", "-u", "+%Y-%m-%d"])
    return (out or "").strip() or "UNSET"


def _plus_days(n):
    """doctrine の TTL。既定は 180 日 — 「いつまで信じてよいか」の無い doctrine は、
    古い前提のまま残って害になる（docs/06 §3）。"""
    for fmt in (["date", "-u", "-v", f"+{n}d", "+%Y-%m-%d"],
                ["date", "-u", "-d", f"+{n} days", "+%Y-%m-%d"]):
        code, out = _raw(fmt)
        if code == 0 and (out or "").strip():
            return out.strip()
    return "UNSET"


def _sub(kind):
    """doctrine / conventions のルート。discovery に任せる（環境変数の設定を要求しない）。"""
    try:
        sys.path.insert(0, HERE)
        from discover import _sub_root
        return _sub_root(kind) or os.path.join(os.getcwd(), ".orgforge", kind)
    except Exception:
        return os.path.join(os.getcwd(), ".orgforge", kind)


def _issue_body(issue, repo=None):
    """task Issue の title/body（= SPEC / MUST）。ここが検証対象の仕様そのもの。"""
    args = ["gh", "issue", "view", str(issue), "--json", "title,body"]
    r = repo or _repo()
    if r:
        args += ["--repo", r]
    code, out = _raw(args)
    if code != 0:
        return None, None
    try:
        d = json.loads(out)
        return d.get("title", ""), d.get("body", "")
    except Exception:
        return None, None


def _branch_for(issue):
    """その Issue のブランチ名。github_sync が決定的に導出するので、それを借りる。"""
    code, out = _gh_sync("branch", "--issue", str(issue))
    if code == 0 and out.strip():
        return out.strip().split("\n")[0]
    return f"feat/issue-{issue}"


def _events_for(issue):
    """#issue に関係する台帳イベントを時系列で返す（訂正で無効化されたものは除く）。"""
    root = None
    try:
        sys.path.insert(0, HERE)
        from discover import ledger_root
        from ledger import voided_seqs
        root = ledger_root()
    except Exception:
        return [], set()
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return [], set()
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = voided_seqs(evs)
    want = str(issue).lstrip("#")
    mine = []
    for e in evs:
        pl = e.get("payload", {}) or {}
        ids = {str(pl.get(k, "")).lstrip("#") for k in
               ("deliverable", "issue", "claim_id", "candidate_id", "spec_ref") if pl.get(k)}
        alias = str(pl.get("pack_manifest_id") or pl.get("contract_ref") or "")
        if want in ids or alias in (f"issue-{want}", want):
            mine.append(e)
    return mine, voided


def _decision_for(issue, cls):
    """#issue に対する `cls` の判定を台帳から探す。

    identity は Issue 番号だが、実地では deliverable に "settle()"（関数名）が入った記録が
    生まれた。**Issue 番号は payload の `issue` にも入っている**ので、片方だけ見て「無い」と
    言うのは、揃っている情報を取りこぼしているだけ。両方見る。

    返り値: (verdict, seq, near) — near は「番号は合わないが近い記録」（原因の特定用）。
    """
    root = None
    try:
        sys.path.insert(0, HERE)
        from discover import ledger_root
        root = ledger_root()
    except Exception:
        pass
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return None, None, []
    want = str(issue).lstrip("#")
    hit, near = None, []
    for line in open(path, encoding="utf-8"):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("class") != cls:
            continue
        pl = e.get("payload", {}) or {}
        # claim_id は refutation_attempted の識別子（candidate_id を指す）
        ids = [str(pl.get(k, "")).lstrip("#")
               for k in ("deliverable", "issue", "claim_id") if pl.get(k) is not None]
        if want in ids:
            hit = (pl.get("verdict"), e.get("seq"))
        elif any(ids):
            near.append((e.get("seq"), ids[0], pl.get("verdict")))
    return (hit[0], hit[1], near) if hit else (None, None, near)


def _admission_for(issue):
    """gate の admission。詳細は _decision_for を見ること。"""
    return _decision_for(issue, "admission_decided")


def _refutation_for(issue):
    """skeptic の反証試行。**admission と同じ強度で照合する** —

    docs/11 / agents/gate.md は「skeptic の反証を生き延びたものだけが deploy 可」と定めており、
    台帳の requires_prior は `result_deployed` にそれを課している。しかし統合はその手前にあり、
    実地では refutation_attempted が台帳に1件も無いまま develop へ統合されかけた
    （Issue にはコメントがあったので、二重記録の片側だけが落ちていた）。
    最も抜けやすいのは統合の直前なので、そこで照合する。
    """
    return _decision_for(issue, "refutation_attempted")


def resolve_parent(issue, repo=None):
    """task Issue の親 objective 番号を **自動で** 解決する。

    人が目で拾って手打ちしていたのがここ。`github_sync create --parent` は body に `Parent: #N` を
    書くので、そこから読める。GitHub のネイティブ sub-issue API も併用する（どちらか取れればよい）。
    取れなければ None — 親を持たない deliverable は従来どおり自分の admit だけを見る。"""
    repo = repo or _repo()
    if not repo:
        return None
    # 1) ネイティブの親子関係（あれば最も確か）
    code, out = _run(["-c", "import subprocess,sys,json;"
                      "p=subprocess.run(['gh','api',f'repos/{sys.argv[1]}/issues/{sys.argv[2]}',"
                      "'--jq','.sub_issue_of.number // empty'],capture_output=True,text=True);"
                      "print(p.stdout.strip())", repo, str(issue)])
    if code == 0 and out.strip().isdigit():
        return out.strip()
    # 2) body の `Parent: #N`（github_sync create が書く）
    p = subprocess.run(["gh", "issue", "view", str(issue), "--repo", repo, "--json", "body",
                        "-q", ".body"], capture_output=True, text=True, timeout=30)
    if p.returncode == 0:
        m = re.search(r"^\s*Parent:\s*#?(\d+)", p.stdout or "", flags=re.M | re.I)
        if m:
            return m.group(1)
    return None


def _candidate_id(issue, repo=None):
    """Issue body の `candidate_id:` トレーラを読む。無ければ Issue 番号を使う。"""
    repo = repo or _repo()
    if repo:
        p = subprocess.run(["gh", "issue", "view", str(issue), "--repo", repo, "--json", "body",
                            "-q", ".body"], capture_output=True, text=True, timeout=30)
        if p.returncode == 0:
            m = re.search(r"^\s*[*`\-\s]*candidate_id:\s*([^\s*`]+)", p.stdout or "",
                          flags=re.M | re.I)
            if m:
                return m.group(1)
    return f"issue-{issue}"


# ── verify（案2）: 配管だけを引き受ける ──────────────────────────────────────
# ここが持ってよいのは「gate/skeptic を正しい材料つきで起動する」ことだけ。
# verdict / why / risk / どのミューテーションを試すか は一切決めない。
# ツールが判定した瞬間に gate は形骸化するので、その線は越えない。

def _agents_dir():
    """agents/*.md の場所。プラグインとして入っている場合と、この repo を直接使う場合の両方。"""
    # Codex injects PLUGIN_ROOT; Claude Code injects CLAUDE_PLUGIN_ROOT.  The
    # launcher can also invoke a bundled tool without either host variable, so
    # retain the tool-relative root as a final fallback.
    plugin_roots = [os.environ[name] for name in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")
                    if os.environ.get(name)]
    # HERE は tools/ を指す（このファイルは tools/orgcycle/ に居る）。その親が
    # プラグインルート / repo ルート。**分割時に `__file__` の階層が1つ深くなったのに
    # ここを直さず、探索先が全部1階層ずれて憲章を見失った**（0.22.0 の実害）。
    # 基点は HERE に集約する — `__file__` を各所で解決し直すと、また同じ穴を掘る。
    bases = plugin_roots + [os.path.dirname(HERE)]
    for base in bases:
        # プラグインとして入った形（agents/ は tools/ の兄弟）と、この repo を直接使う形の両方。
        # 片方しか見ないと、バンドル側で憲章を見失って verify が成り立たなくなる。
        for d in (os.path.join(base, "agents"),
                  os.path.join(base, "integrations", "claude-code", "agents")):
            if os.path.isdir(d):
                return d
    return None


def banner():
    """実行しているバージョンと cwd を stderr に1行出す。

    **どのコピーを動かしているかが見えないと、古いパスを流用しても気づけない。**
    実地で 0.26.0 のリリース後も 0.25.2 のパスを打っており（直前に使ったものを流用した）、
    さらに `cd` が持続しない前提のコマンドの exit=1 を「塞がった証拠」と読みかけた。
    可変値を流用したときに、次の行で気づける材料を置く。
    """
    ver = "?"
    for c in (os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json"),
              os.path.join(HERE, "..", ".claude-plugin", "plugin.json"),
              os.path.join(HERE, "..", "integrations", "claude-code",
                           ".claude-plugin", "plugin.json")):
        try:
            with open(c, encoding="utf-8") as f:
                ver = json.load(f).get("version", "?")
            break
        except Exception:
            continue
    # **機械可読な出力を汚さない。** stderr に書いていても、消費側が 2>&1 で混ぜると
    # JSON が壊れる（実地でテストが JSONDecodeError で落ちた）。人間向けの補助なので、
    # --json や ORG_QUIET のときは黙る — 「便利のために壊す」のは筋が通らない。
    if "--json" in sys.argv or os.environ.get("ORG_QUIET"):
        return
    print(f"[orgforge {ver} @ {os.getcwd()}]", file=sys.stderr)


def _worktree_tree_sha(cwd=None):
    """作業ツリー全体（tracked / staged / unstaged / **untracked**）を1つの tree SHA に束ねる。

    `git diff HEAD` は未追跡ファイルの内容を含まない。名前だけ拾って中身を見ないと、
    **未追跡ファイルの内容を丸ごと差し替えても同じ id になる**（監査が実証）。judge が
    未追跡ファイルを読んで判定していれば、別の成果物を「同じもの」として一致させられる。

    そこで **一時 index** に作業ツリーを読み込んで `git write-tree` する。`GIT_INDEX_FILE` で
    別ファイルを指すので、**実 index は変更しない** — 監督の staging 状態を壊さない。

    .gitignore された生成物は含めない（`--exclude-standard`）。ビルド出力やのモジュール群で
    id が毎回変わるなら、同じレビューを2度行えなくなる。
    """
    import tempfile as _tf
    def _git(*args, env=None):
        try:
            e = dict(os.environ)
            if env:
                e.update(env)
            r = subprocess.run(["git", *args], capture_output=True, text=True,
                               timeout=60, cwd=cwd, env=e)
            return r.returncode, r.stdout.strip()
        except Exception:
            return 1, ""

    fd, idx = _tf.mkstemp(prefix="orgforge-index-")
    os.close(fd)
    os.unlink(idx)                       # git は存在しないパスに新規 index を作る
    env = {"GIT_INDEX_FILE": idx}
    try:
        # HEAD の内容を土台にし、作業ツリーの実状態を重ねる
        _git("read-tree", "HEAD", env=env)
        _git("add", "-A", "--", ".", env=env)
        code, tree = _git("write-tree", env=env)
        return tree if code == 0 else ""
    finally:
        for p_ in (idx, idx + ".lock"):
            try:
                os.unlink(p_)
            except OSError:
                pass


def issue_worktree(issue, cwd=None):
    """`begin` が作る Issue worktree の正準パス `.orgforge/wt/issue-<N>` を解決する。

    レイアウトの出所は `ghsync.branch._make_worktree`（primary checkout の toplevel 直下）。
    第2のレイアウトを発明しない — ここは**解決だけ**を再現する。linked worktree の中から
    呼ばれても primary に解決する（`git worktree list --porcelain` の先頭は常に primary）。
    解決できなければ None（呼び手が fail-closed にする — cwd で代用しない）。
    """
    d = os.path.abspath(cwd or os.getcwd())
    try:
        r = subprocess.run(["git", "-C", d, "worktree", "list", "--porcelain"],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    for line in (r.stdout or "").splitlines():
        if line.startswith("worktree "):
            primary = os.path.abspath(line[len("worktree "):])
            return os.path.join(primary, ".orgforge", "wt", f"issue-{int(issue)}")
    return None


def resolve_issue_branch(issue, derived=None, cwd=None):
    """Issue の**実在する** branch を2段で解決する（#107）。``(branch, warn, err)`` を返す。

    タイトル slug から導出した名前は**作成時の規約**であって恒久 identity ではない —
    タイトル変更や手動命名で実在名とずれる。Tatekae 実測（OBS-012 / OBS-048欠陥6 /
    OBS-057原因2）では導出名 `feat/issue-15-google` が実在せず（実在は
    `feat/issue-15-login-redirect`）、`git branch --merged --list <導出名>` が常に空になり、
    gc が統合済み worktree を「未統合」として永久に残した。

    (a) Issue worktree（`.orgforge/wt/issue-N`、issue_worktree が解決）が実在するなら、
        その HEAD branch が**常に真** — 実際に作業されたのはそこである。
        導出名とずれていれば warn で言う（黙ってどちらかを選ばない）。
    (b) 無ければ、導出名が**実在する場合に限り**使う（`git rev-parse --verify`）。
    (c) どちらも無ければ err — **実在しない導出名を黙って信じない**（fail-closed）。
    """
    try:
        wt = issue_worktree(issue, cwd)
    except Exception:
        wt = None
    wt_exists = bool(wt and worktree_rooted_at(wt))
    head = issue_worktree_head(issue, cwd) if wt_exists else None
    if head:
        warn = None
        if derived and derived != head:
            warn = (f"導出名 `{derived}` と worktree の実 branch `{head}` が一致しない"
                    f"（タイトル変更か手動命名）。worktree "
                    f".orgforge/wt/issue-{issue} の HEAD を採用する（#107）。")
        return head, warn, None
    if derived:
        code, _out = _raw(["git"] + (["-C", cwd] if cwd else [])
                          + ["rev-parse", "--verify", "--quiet", f"refs/heads/{derived}"])
        if code == 0:
            return derived, None, None
    # 事実だけを言う: worktree が「無い」のか「在るが branch を指していない（detached HEAD）」
    # のかは別の状態で、直し方も違う。嘘の診断は直し方まで誤らせる。
    wt_state = (f"worktree .orgforge/wt/issue-{issue} は在るが detached HEAD で"
                f"（branch を指していない）" if wt_exists
                else f"worktree .orgforge/wt/issue-{issue} も無い")
    return None, None, (
        f"Issue #{issue} の branch を解決できない: 導出名 `{derived or '(導出できず)'}` は"
        f"実在の branch ではなく、{wt_state}。\n"
        f"  実在の候補は `git branch --list 'feat/issue-{issue}*'` で探せる。\n"
        f"  これから作るなら `github_sync branch --issue {issue} --worktree` で"
        f"branch ごと worktree を作ること。")


def issue_worktree_head(issue, cwd=None):
    """Issue worktree（.orgforge/wt/issue-N）が実在するなら、その HEAD branch 名。

    無い / 偽 worktree / detached HEAD なら None。実在する Issue worktree の HEAD が
    その Issue の branch の**真値**である（#107）— 実際に作業されたのはそこだから。"""
    try:
        wt = issue_worktree(issue, cwd)
    except Exception:
        return None
    if not (wt and worktree_rooted_at(wt)):
        return None
    code, head = _raw(["git", "-C", wt, "symbolic-ref", "--short", "-q", "HEAD"])
    head = (head or "").strip()
    return head if code == 0 and head else None


def worktree_rooted_at(path):
    """`path` が「**まさにそこを toplevel とする**実 worktree」かを実体で確かめる。

    `os.path.isdir` だけでは偽 worktree が通る（skeptic が実証）: 失敗した
    `git worktree add` が残す空ディレクトリ・prune せず再作成されたディレクトリ・
    repo root への symlink は、どれも primary repo の**内側**に居るので `git -C` が
    primary に解決し、subject が primary の tree（ahead=0・relation=current）として
    警告なしに mint される — OBS-071 の偽造がそのまま再現する。

    判定は2段: (1) canonical path 自体が symlink なら偽（実体が別の場所にある worktree
    は worktree ではない）。(2) `git rev-parse --show-toplevel` の実体が path の実体と
    一致して初めて「そこに worktree がある」— 空ディレクトリや残骸は toplevel が
    primary root に解決するので、ここで落ちる。祖先の symlink（/var → /private/var 等）
    は両辺 realpath なので誤検出しない。
    """
    if not path or os.path.islink(path) or not os.path.isdir(path):
        return False
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return False
    top = (r.stdout or "").strip()
    if r.returncode != 0 or not top:
        return False
    return os.path.realpath(top) == os.path.realpath(path)


def review_subject(issue, role, phase=None, cwd=None, integration_ref=None):
    """**判定対象の同一性**を1つの digest に束ねる。`verify` が一度だけ生成する。

    0.32.1 の一致要求は (issue, role, lineage, verdict) だけで一致を判定していた。そのため
    **同一ハーネスが revision A を admit し、別ハーネスが revision B を admit しても joint が
    生成された**（監査が実証）。judge が別の成果物を見ていたなら、それは一致ではない。

    束ねるもの:

        issue                その Issue
        role                 gate か skeptic か（判定の種類）
        phase                どのフェーズの判定か
        integration_ref     統合先 ref
        integration_head_sha 判定時点の統合先 head
        base_sha             分岐元（何からの差分を見ているのか）
        reviewed_tree_sha    **実際にレビューされた木**。commit ではなく tree にする —
                             同じ内容の commit を作り直しても対象は変わらない
        requirements_digest  受け入れ基準の内容。**基準が変われば別の判定である**

    `dirty` は隠さない。作業ツリーに未コミットの変更があるなら、reviewed_tree_sha は
    **その時点の index/worktree** を指すべきで、「clean だったふり」をしてはいけない。

    judge にこの値を作らせない。judge が subject を書けるなら、別の成果物を見た2件を
    「同じものを見た」と申告して一致を作れる。**verify が観測し、judge は運ぶだけ。**
    """
    def _git(*args):
        try:
            r = subprocess.run(["git", *args], capture_output=True, text=True,
                               timeout=30, cwd=cwd)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    head_tree = _git("rev-parse", "HEAD^{tree}")
    # **実際にレビューされた木**。commit ではなく tree にするのは、同じ内容の commit を
    # 作り直しても対象は変わらないからである。未コミット・未追跡も含めて1つの id に束ねる
    # （`git diff HEAD` は未追跡の内容を含まないので、それでは足りない）。
    tree = _worktree_tree_sha(cwd) or head_tree
    dirty = "1" if tree != head_tree else ""
    from review_freshness import integration_observation, subject_digest
    integration = integration_observation(cwd or os.getcwd(), integration_ref)

    req_digest = ""
    for name in ("REQUIREMENTS.md",):
        p = os.path.join(cwd or ".", name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                req_digest = hashlib.sha256(f.read()).hexdigest()[:16]
            break

    parts = {"issue": str(issue), "role": role, "phase": phase or "",
             **integration, "reviewed_tree_sha": tree,
             "dirty": dirty, "head_tree_sha": head_tree,
             "requirements_digest": req_digest}
    sid = subject_digest(parts)
    return sid, parts
