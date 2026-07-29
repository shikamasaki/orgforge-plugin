"""org_cycle の共有部品 — 実行・台帳・GitHub・識別子の解決。

ここに置くのは「どのサブコマンドからも使う」ものだけ。特定のサブコマンド専用の
ヘルパは、そのサブコマンドのモジュールに置く（core が肥大すると分割の意味が消える）。"""

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
    """python3 <tool> ... を実行。(code, out) を返す。"""
    p = subprocess.run([sys.executable] + args, capture_output=capture, text=True, timeout=60)
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
        from ledger import corrected_seqs
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
    voided = corrected_seqs(evs)
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
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    # HERE は tools/ を指す（このファイルは tools/orgcycle/ に居る）。その親が
    # プラグインルート / repo ルート。**分割時に `__file__` の階層が1つ深くなったのに
    # ここを直さず、探索先が全部1階層ずれて憲章を見失った**（0.22.0 の実害）。
    # 基点は HERE に集約する — `__file__` を各所で解決し直すと、また同じ穴を掘る。
    bases = ([env] if env else []) + [os.path.dirname(HERE)]
    for base in bases:
        # プラグインとして入った形（agents/ は tools/ の兄弟）と、この repo を直接使う形の両方。
        # 片方しか見ないと、バンドル側で憲章を見失って verify が成り立たなくなる。
        for d in (os.path.join(base, "agents"),
                  os.path.join(base, "integrations", "claude-code", "agents")):
            if os.path.isdir(d):
                return d
    return None
