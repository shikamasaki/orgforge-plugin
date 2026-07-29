#!/usr/bin/env python3
"""org_cycle — 1サイクル分の配管を1コマンドで回す（docs/11 §0d）。

**なぜこれが要るのか。** `/org-work` は「こういうイベントを打て」という散文の指示で、実行するのは
エージェントだった。実地で1サイクル（Issue 2件）あたり **11コマンド**を手で叩いており、18 Issue
なら約90回になる。そのうち1回でも間違えれば台帳の整合が崩れる。

さらに悪いのは `parent` の扱いだった。フェーズ連鎖は親 objective の admit を継承する（docs/11 §2）
のに、その `parent` の値を**人が Issue から目で拾って手打ち**していた。継承の実装を入れても、
値が手打ちである限り取り違えが起きる — **拾えるものを拾わせないのは設計の怠慢**である。

このツールは「順序と actor が決まっている配管」だけを引き受ける。**判断は引き受けない** —
何を選ぶか、誰に委ねるか、admit するかは役割の仕事であり、ここでは自動化しない（docs/03 §6.5 の
「forced delegation は設計エラー、forced invariant は正しい」の線引きをそのまま踏襲する）。

  org_cycle.py begin    --role R --issue N [--phase implement] [--agent A]
      claim → spec_delegated → phase_started（parent 自動解決）→ cycle_started → Issue へ log
  org_cycle.py complete --role R --issue N --outputs TEXT
                        (--domain-model-updated REF | --domain-model-none WHY)
      cycle_completed（domain_model 必須）→ Issue へ log → stage done
  org_cycle.py plan     --role R --issue N [...]
      **何も実行せず**、打つイベント列を印字する（--dry-run 相当）

Exit: 0 ok / 3 台帳が拒否（順序違反など）/ 10 contended / 2 usage・gh エラー
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
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


def _steps_begin(a, parent, cid):
    """begin が打つイベント列。(ラベル, 実行関数) の並び — plan はこれを印字するだけ。"""
    phase = a.phase or "implement"
    agent = a.agent or a.role
    repo_args = []          # --repo は github_sync が discovery するので渡さない
    return [
        # 6: 何を選んだかの記録は配管（選ぶこと自体は判断だが、選んだ結果を残すのは機械の仕事）。
        # 実地では6件着手して attention_allocated が1件しか無く、選択の履歴が追えなかった。
        (f"attention_allocated（#{a.issue} を選択）",
         lambda: _ledger("append", "--actor", a.role, "--class", "attention_allocated",
                         "--natural-key", f"attn-{a.issue}-{cid}",
                         "--payload", json.dumps(
                             {"role": a.role, "ranking_id": f"issue-{a.issue}",
                              "selected": [{"candidate_id": cid, "objective": parent or "",
                                            "source": "mandate"}],
                              "deferred": [],
                              "reason": a.why or f"#{a.issue} に着手（begin）"},
                             ensure_ascii=False))),
        (f"claim #{a.issue} as {agent}",
         lambda: _gh_sync("claim", "--issue", str(a.issue), "--agent", agent, *repo_args)),
        *([(f"worktree .orgforge/wt/issue-{a.issue} を用意（並列 maker の物理分離）",
            lambda: _gh_sync("branch", "--issue", str(a.issue), "--worktree",
                             *(["--base", a.base] if getattr(a, "base", None) else [])))]
          if not getattr(a, "no_worktree", False) else []),
        (f"spec_delegated (spec_ref=#{a.issue})",
         lambda: _ledger("append", "--actor", a.role, "--class", "spec_delegated",
                         "--natural-key", f"spec-{a.issue}",
                         "--payload", json.dumps({"supervisor": a.role, "subordinate": agent,
                                                  "spec_ref": str(a.issue),
                                                  "contract_ref": parent or str(a.issue),
                                                  "intent_basis_ref": "REQUIREMENTS.md"},
                                                 ensure_ascii=False))),
        (f"phase_started{{{phase}}} deliverable=#{a.issue} parent=#{parent or '-'}",
         lambda: _ledger("append", "--actor", a.role, "--class", "phase_started",
                         "--natural-key", f"phase-{phase}-{a.issue}",
                         "--payload", json.dumps({"deliverable": str(a.issue),
                                                  **({"parent": parent} if parent else {}),
                                                  "phase": phase, "role": agent},
                                                 ensure_ascii=False))),
        (f"cycle_started candidate_id={cid}",
         lambda: _ledger("append", "--actor", agent, "--class", "cycle_started",
                         "--natural-key", f"start-{cid}",
                         "--payload", json.dumps({"role": agent, "candidate_id": cid,
                                                  "pack_manifest_id": f"issue-{a.issue}"},
                                                 ensure_ascii=False))),
        # ツールが知っている事実は人に書かせない（B）。実地で私が書いた 276 字には、
        # ブランチ名も worktree のパスも入っていなかったが、org_cycle は両方知っていた。
        (f"log cycle_started → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "cycle_started",
                          "--phase", phase, "--event-id", f"start-{cid}",
                          "--detail",
                          f"{agent} が着手（parent #{parent or '-'} を継承 / "
                          f"candidate_id `{cid}` / phase `{phase}`）",
                          "--command",
                          f"python3 org_cycle.py begin --role {a.role} --issue {a.issue} "
                          f"--agent {agent}",
                          "--result",
                          f"claim: {agent}\n"
                          f"branch: {_branch_for(a.issue)}\n"
                          f"worktree: "
                          + ("(なし — --no-worktree)" if getattr(a, "no_worktree", False)
                             else f".orgforge/wt/issue-{a.issue}/")
                          + f"\nparent: #{parent or '-'}\ncandidate_id: {cid}",
                          "--files", f".orgforge/wt/issue-{a.issue}/",
                          "--next-step",
                          f"仕様は #{a.issue} 本文。完了したら "
                          f"`org_cycle.py complete --issue {a.issue} ...` → handback → verify")),
        (f"stage #{a.issue} → in-progress",
         lambda: _gh_sync("stage", "--issue", str(a.issue), "--stage", "in-progress")),
    ]


def _steps_complete(a, cid):
    dm = ({"updated": [a.domain_model_updated]} if a.domain_model_updated
          else {"none_asserted": a.domain_model_none})
    agent = a.agent or a.role
    return [
        (f"cycle_completed candidate_id={cid}",
         lambda: _ledger("append", "--actor", agent, "--class", "cycle_completed",
                         "--natural-key", f"done-{cid}",
                         "--payload", json.dumps({"role": agent, "candidate_id": cid,
                                                  "outputs": [a.outputs], "reused": [],
                                                  "domain_model": dm}, ensure_ascii=False))),
        (f"log cycle_completed → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "cycle_completed",
                          "--event-id", f"done-{cid}", "--detail", a.outputs,
                          "--command", a.command or "(--command で DoD コマンドを渡すこと)",
                          "--result", a.result or "(--result に実出力を貼ること)",
                          *(["--files", a.files] if getattr(a, "files", None) else []),
                          "--next-step",
                          f"`org_cycle.py handback --issue {a.issue}` で PR → "
                          f"verify（gate → skeptic）→ integrate")),
        (f"release claim on #{a.issue}",
         lambda: _gh_sync("release", "--issue", str(a.issue), "--agent", agent)),
    ]


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

def _agents_dir():
    """agents/*.md の場所。プラグインとして入っている場合と、この repo を直接使う場合の両方。"""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    here = os.path.dirname(os.path.abspath(__file__))     # .../tools
    bases = ([env] if env else []) + [os.path.dirname(here)]
    for base in bases:
        # プラグインとして入った形（agents/ は tools/ の兄弟）と、この repo を直接使う形の両方。
        # 片方しか見ないと、バンドル側で憲章を見失って verify が成り立たなくなる。
        for d in (os.path.join(base, "agents"),
                  os.path.join(base, "integrations", "claude-code", "agents")):
            if os.path.isdir(d):
                return d
    return None


def _role_charter(role):
    """agents/<role>.md の本文（front-matter を落とす）。

    **これが案2の肝。** 検証手順を毎回人が書き下ろすと、書くたびに gate の厳しさが変わる。
    18 Issue なら18通りの基準になる。charter を注入すれば基準は1つに固定され、
    しかも基準の変更は agents/<role>.md の1箇所で効く。
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


def _seam(role, issue, title):
    """handoff.py を内部で呼んで seam contract を作る。引数6個の手打ちをここで吸収する。"""
    here = os.path.dirname(os.path.abspath(__file__))
    slice_ = {
        "gate": f"#{issue} 「{title}」の admission — MUST を1つずつ再導出する",
        "skeptic": f"#{issue} 「{title}」の admit 済み成果物への反証",
    }.get(role, f"#{issue} 「{title}」")
    outputs = {
        "gate": "admission_decided（verdict は自分で決める。admit には --evidence が要る）",
        "skeptic": "refutation_attempted（verdict は自分で決める。survives には --evidence が要る）",
    }.get(role, "決定と、その根拠")
    code, out = _run([os.path.join(here, "handoff.py"), role,
               "--slice", slice_,
               "--inputs", f"task Issue #{issue} の SPEC / MUST と、maker の成果物",
               "--outputs", outputs,
               "--owns", "判定そのもの（この配管は verdict を決めない）",
               "--forbid", "自分が作った成果物の admit／maker の手順の再追跡（結果を再導出すること）"])
    return out if code == 0 else None


def _prior_gate(issue, repo=None):
    """skeptic に渡す「gate が既に見たこと」。

    渡さないと skeptic は gate と同じミューテーションを繰り返して無駄になる（実地で確認済み）。
    **これは配管であって判断ではない** — gate が何を書いたかをそのまま運ぶだけで、
    その内容の当否も、次に何を試すべきかも、こちらは決めない。
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


def cmd_verify(a):
    """gate / skeptic を起動するための材料を組み立てて印字する。判定はしない。"""
    role = a.role
    charter, cpath = _role_charter(role)
    if charter is None:
        print(f"agents/{role}.md が見つからない（探した先: {cpath}）。\n"
              f"charter を注入できないなら verify は成り立たない — 検証基準が毎回人の書き方に"
              f"依存してしまう。プラグインの導入状態を確認すること。", file=sys.stderr)
        return 2
    title, body = _issue_body(a.issue)
    if title is None:
        print(f"Issue #{a.issue} を読めなかった（gh の認証 / repo 解決を確認）。", file=sys.stderr)
        return 3
    seam = _seam(role, a.issue, title)
    prior = _prior_gate(a.issue) if role == "skeptic" else None

    ev = {"gate": "admission_decided", "skeptic": "refutation_attempted"}.get(role, "decided")
    verdicts = {"gate": "admit|reject|park", "skeptic": "survives|refuted"}[role]

    out = []
    out.append(f"===== {role} subagent への投入プロンプト（#{a.issue}: {title}）=====\n")
    out.append(seam or "(seam contract の生成に失敗 — handoff.py を確認)")
    out.append("\n## あなたの憲章（agents/%s.md — 検証基準はここが唯一の出所）\n" % role)
    out.append(charter)
    out.append(f"\n## 検証対象の SPEC / MUST（Issue #{a.issue} 本文）\n")
    out.append(body or "(本文が空 — SPEC の無い Issue は、それ自体が reject 事由)")
    if prior:
        out.append("\n## gate が既に見たこと（重複を避けるため。追認する義務はない）\n")
        out.append(prior)
    elif role == "skeptic":
        out.append("\n## gate が既に見たこと\n(#%d に admission_decided の記録が無い。"
                   "gate の admit 前に skeptic を回そうとしていないか確認すること)" % a.issue)

    if role == "gate":
        # 6: ツールのパスが解決できず repro_lint が一度も走っていなかった。org_cycle は自分の
        # 位置を知っているので絶対パスを埋める。機械的拒否層は、誰も diff を読まない以上
        # 「走らなかった」が最も危ない失敗形。
        out.append("\n## 機械バー（**このコマンドをそのまま実行すること。未実行は reject 事由**）\n")
        out.append("```")
        out.append(f'python3 "{os.path.join(HERE, "repro_lint.py")}" check . --phase implement')
        out.append("```")
        out.append("HOLD（exit 10）なら reject。パスが通らない場合はそう報告すること — "
                   "「ツールが無いので未実行」は、機械バーが効いていないという最も重い所見。")
    if role == "skeptic" and prior:
        # 5: --risk を書けば admit できる構造なので、書き得にしない。gate が自分で書いた
        # リスクは、skeptic が最初に潰しに行くべき的として明示する（配管: 抜き出して渡すだけ）。
        risks = re.findall(r"\*\*Known risk accepted:\*\*\s*(.+?)(?:\n\n|\Z)", prior, re.S)
        if risks:
            out.append("\n## gate が自分で書いた残存リスク（**まずここを潰しに行くこと**）\n")
            out.append(risks[-1].strip())
            out.append("\n> gate はリスクを書けば admit できる。書き得にしないために、"
                       "この記述が「承知の上の判断」なのか「実は落とし穴」なのかを確かめるのは "
                       "skeptic の仕事。潰せたなら refuted、潰せず承知の範囲だと確認できたなら "
                       "その旨を --risk に書いて survives。")

    if role == "gate":
        code, pend = _run([os.path.join(HERE, "doctrine.py"), "show", _sub("doctrine")])
        if code == 0 and "pending" in (pend or "").lower():
            out.append("\n## 未 admit の doctrine（maker が差し出した学び）\n")
            out.append(pend.strip()[:2000])
            out.append("\n> 次のサイクルに渡す価値があるものだけ admit すること:\n"
                       f"> `python3 {os.path.join(HERE, 'doctrine.py')} admit "
                       f"{_sub('doctrine')} <role> <claim-id> --by gate`\n"
                       "> admit しなければ、この学びは次の Issue に渡らない。"
                       "実地では同じ失敗を3回繰り返した。")

    out.append(f"\n## 記録（**判定はあなたが決める。この雛形は値を埋めていない**）\n")
    out.append("```")
    out.append(f'python3 "{os.path.join(HERE, "github_sync.py")}" '
               f'decide --issue {a.issue} --event {ev} \\')
    out.append(f'  --verdict <{verdicts}> --by {role} \\')
    out.append('  --why "<何を天秤にかけ、何が決め手になったか>" \\')
    out.append('  --evidence "<実際に走らせたコマンドと、その実出力>" \\')
    if role == "gate":
        out.append('  --alternatives "<採らなかった選択肢と、その理由>" \\')
        out.append('  --standard "<適用した基準>" \\')
    out.append('  --risk "<承知の上で残す穴 / 排除しきれなかった失敗モード>"')
    out.append("# 出力される reasoning_sha256= を、次の ledger 受領証の payload に入れること")
    out.append(f"# deliverable は **Issue 番号 {a.issue}** のまま。関数名や機能名に書き換えないこと —")
    out.append("# 後続の照合が識別子の揺れで記録を見失う（実地で起きた）。呼び名は --why に書く。")
    out.append(f'python3 "{os.path.join(HERE, "ledger.py")}" '
               f'append --actor {role} --class {ev} \\')
    out.append(f'  --payload \'{{"verdict":"<...>","deliverable":"{a.issue}",'
               f'"reasoning_sha256":"<...>","issue":{a.issue},'
               f'"risk_accepted":<true|false>}}\'')
    out.append('# risk_accepted: --risk に穴を書いたうえで通すなら true。')
    out.append('# リスクを書けば通せる構造なので、書き得にしないために台帳側で数えられる形にする')
    out.append('# （Issue コメントだけだと集計できない）。'
               + ('skeptic はその穴を潰しに行くこと。' if role == 'gate' else ''))
    out.append("```")
    print("\n".join(out))
    print(f"\n— この出力を {role} subagent の**プロンプト本文にそのまま貼る**こと"
          f"（ファイルに落として「これを読め」と渡さない）。\n"
          f"  seam ガードは spawn 時のプロンプト本文を検査するので、seam contract が"
          f"ファイルの中にあると検出できず、spawn が HELD される。\n"
          f"  ガードが本文を見るのは正しい — 参照先の中身は spawn 時点で保証できないため。\n"
          f"配管はここまで。verdict / why / risk は {role} が決める。", file=sys.stderr)
    return 0



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


def _new_exports(issue, base="develop"):
    """このサイクルで新規に生えた公開型 / エクスポートを列挙する。

    3: domain_model は必須だが `--domain-model-none "理由"` で常に通るので、書く側が none を
    選べば形骸化する。実地では「純粋関数の追加のみ」と書かれたサイクルが Balance / Transfer /
    SettleResult という型＝ユビキタス言語を実際に作っていた。**判定はしない** — 素通りを
    させないために、反証材料を目の前に置くだけ。潰すか説明するかは役割が決める。
    """
    br = _branch_for(issue)
    code, out = _raw(["git", "diff", f"{base}...{br}", "--unified=0"])
    if code != 0:
        code, out = _raw(["git", "diff", base, "--unified=0"])
        if code != 0:
            return []
    pat = re.compile(
        r"^\+.*?\bexport\s+(?:default\s+)?"
        r"(type|interface|enum|class|const|function)\s+([A-Za-z_][A-Za-z0-9_]*)")
    seen, hits = set(), []
    for line in out.split("\n"):
        m = pat.match(line)
        if m and m.group(2) not in seen:
            seen.add(m.group(2))
            hits.append((m.group(1), m.group(2)))
    return hits


def _cleanup_worktree(issue):
    """4: begin が作った worktree を片付ける。18 Issue 回せば18個残り、次に同じ Issue を
    触ったとき古いツリーを掴む。**未コミットの変更があれば消さない** — 消えて困るものが
    あるかは、こちらが判断してよいことではない。"""
    root = os.getcwd()
    wt = os.path.join(root, ".orgforge", "wt", f"issue-{issue}")
    if not os.path.isdir(wt):
        return None
    code, out = _raw(["git", "-C", wt, "status", "--porcelain"])
    if code == 0 and out.strip():
        return (f"worktree を残した: {wt}\n"
                f"  未コミットの変更がある（{len(out.strip().split(chr(10)))} 件）。"
                f"確認してから `git worktree remove` すること。")
    code, out = _raw(["git", "worktree", "remove", wt])
    if code != 0:
        return f"worktree を消せなかった: {wt}（{out.strip()[:80]}）"
    return f"worktree を片付けた: .orgforge/wt/issue-{issue}"



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


def cmd_begin(a):
    parent = a.parent or resolve_parent(a.issue)
    cid = a.candidate_id or _candidate_id(a.issue)
    if parent is None:
        print(f"注意: #{a.issue} の親 objective が解決できなかった。phase 連鎖は自分の admit だけを "
              f"見る（親から継承しない）。意図した親があるなら --parent で渡すこと。", file=sys.stderr)
    return _execute(_steps_begin(a, parent, cid), f"begin #{a.issue} ({a.role})")


def cmd_complete(a):
    if not (a.domain_model_updated or a.domain_model_none):
        print("--domain-model-updated か --domain-model-none のどちらかが必要。\n"
              "docs/11 §4d: cycle_completed は「このサイクルがドメインモデルに何をしたか」を"
              "述べない限り台帳が拒否する。何も確立しなかったなら、その理由を書くこと"
              "（skeptic が反証できる主張になる）。", file=sys.stderr)
        return 2
    if a.domain_model_none:
        # 素通りをさせない: 「規則を定めていない」と書いたサイクルが、実は語彙を作っていないか。
        ex = _new_exports(a.issue)
        if ex:
            print(f"確認: none_asserted だが、このサイクルで {len(ex)} 個の公開シンボルが増えている:",
                  file=sys.stderr)
            for kind, name in ex[:12]:
                print(f"    {kind} {name}", file=sys.stderr)
            print("これらは領域の語彙（ユビキタス言語）ではないか。語彙なら "
                  "--domain-model-updated で記録すること。\n"
                  "語彙ではないと判断するなら、そのまま進めてよい — **判定はあなたの仕事**で、"
                  "ここは素通りを防ぐための問い返しにすぎない。\n", file=sys.stderr)

    cid = a.candidate_id or _candidate_id(a.issue)
    rc = _execute(_steps_complete(a, cid), f"complete #{a.issue} ({a.role})")
    if rc == 0 and a.learned:
        # 3: doctrine の蓄積経路がサイクルに繋がっておらず、doctrine/ も conventions/ も空だった。
        # 実地では同じ失敗を3回繰り返した知見（「性質のテストは壊れる場所で検証しないと無意味」）が
        # あり、doctrine に入っていれば止まったはず。docs/06 は「蓄積した失敗こそ最も価値ある
        # context」と書いているのに、蓄積の口がどこにも開いていなかった。
        # **propose まで。admit は gate の仕事**（自分の学びを自分で正典にできない）。
        code, out = _run([os.path.join(HERE, "doctrine.py"), "propose",
                          _sub("doctrine"), a.agent or a.role,
                          "--claim", a.learned,
                          "--source", f"issue-{a.issue}",
                          "--confidence", str(a.confidence),
                          # provenance を埋めないと gate が admit できず、学びは pending の
                          # まま死ぬ。日付は配管が知っているので人に打たせない。
                          "--retrieved-at", _today(),
                          "--review-by", _plus_days(a.review_days),
                          *(["--affects", a.affects] if a.affects else [])])
        if code == 0:
            print(f"  doctrine に propose した（admit は gate）: {out.strip()[:100]}")
        else:
            print(f"  doctrine への propose に失敗: {out.strip()[:120]}", file=sys.stderr)
    elif rc == 0:
        print(f"\n  ヒント: このサイクルで「次も効く学び」があれば --learned で残すこと。"
              f"doctrine に入らない学びは次の Issue に渡らない（実地で同じ失敗を3回繰り返した）。")
    if rc == 0:
        msg = _cleanup_worktree(a.issue)
        if msg:
            print(f"  {msg}")
        verdict, seq, near = _admission_for(a.issue)
        rv, rseq, _ = _refutation_for(a.issue)
        if verdict == "admit" and rv == "survives":
            print(f"\nNEXT: gate admit（seq {seq}）· skeptic survives（seq {rseq}）。統合できる:\n"
                  f"  python3 org_cycle.py integrate --issue {a.issue}")
        elif verdict == "admit" and rv == "refuted":
            print(f"\nNEXT: skeptic が refuted（seq {rseq}）。統合してはいけない —"
                  f" 反証に対処してから再度 verify にかけること。")
        elif verdict == "admit":
            print(f"\nNEXT: #{a.issue} は gate が admit 済み（seq {seq}）。次は skeptic:\n"
                  f"  python3 org_cycle.py verify --issue {a.issue} --role skeptic")
        elif verdict:
            print(f"\nNEXT: gate の判定は `{verdict}`（seq {seq}）。admit ではないので、"
                  f"指摘に対処してから再度 verify にかけること。")
        else:
            print(f"\nNEXT: gate の admission がまだ:\n"
                  f"  python3 org_cycle.py verify --issue {a.issue} --role gate\n"
                  f"maker は自分の仕事を admit できない（台帳が拒否する）。")
            # 「無い」と言い切る前に、取り違えの可能性を示す。実地で deliverable に関数名が
            # 入っていて、記録はあるのに「まだ」と出た。原因が即分かる形で出す。
            if near:
                s, d, i = near[-1]
                print(f"（近い記録: seq {s} に admission_decided があるが "
                      f"deliverable={d!r} / issue={i!r} で #{a.issue} と一致しない。"
                      f"gate が Issue 番号以外の識別子で記録した可能性がある）", file=sys.stderr)
    return rc



def cmd_integrate(a):
    """develop への fan-in を回す。**マージするかどうかは判定しない** — 前提が揃っているかを
    照合し、揃っていれば機械的な手順（マージ → 統合後テスト → 記録）を実行する。

    fan-out が半分なら fan-in は残り半分で、そこが散文の手順書のままだと抜ける。実地では
    #8 が「refutation が台帳に無いまま統合され、integration_admitted も記録されなかった」。
    最も抜けやすいのは統合の直前なので、そこを配管にする。
    """
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


def _branch_for(issue):
    """その Issue のブランチ名。github_sync が決定的に導出するので、それを借りる。"""
    code, out = _gh_sync("branch", "--issue", str(issue))
    if code == 0 and out.strip():
        return out.strip().split("\n")[0]
    return f"feat/issue-{issue}"



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



def cmd_gc(a):
    """5: 溜まった worktree を片付ける。**未コミットの変更があるものは残す。**

    complete/integrate が片付けるようになったが、既に溜まったものと、予算 cap で消せず
    残ったものは誰の仕事でもなかった。統合済みなのに残っていると、次に同じ Issue を
    触ったとき古いツリーを掴む。
    """
    base = os.path.join(os.getcwd(), ".orgforge", "wt")
    if not os.path.isdir(base):
        print("worktree はありません。")
        return 0
    kept, removed = [], []
    for name in sorted(os.listdir(base)):
        if not name.startswith("issue-"):
            continue
        issue = name[len("issue-"):]
        wt = os.path.join(base, name)
        code, out = _raw(["git", "-C", wt, "status", "--porcelain"])
        if code == 0 and out.strip():
            kept.append((name, f"未コミットの変更 {len(out.strip().splitlines())} 件"))
            continue
        if not a.all:
            # 既定は「統合済みだけ」を消す。まだ取り込まれていない仕事は消さない。
            br = _branch_for(issue)
            code, merged = _raw(["git", "branch", "--merged", a.base, "--list", br])
            if code != 0 or not (merged or "").strip():
                kept.append((name, f"{a.base} に未統合"))
                continue
        code, out = _raw(["git", "worktree", "remove", wt])
        (removed if code == 0 else kept).append(
            (name, "片付けた" if code == 0 else out.strip()[:60]))
    # .orgforge/wt/ の外に作られた検証用 worktree（scratchpad 等）も git は把握している。
    # 実地では skeptic が scratchpad に作った sk7 が、予算 cap で消せず残っていた。
    # 「配管が作った場所」しか見ないと、こういう孤児が永久に残る。
    code, out = _raw(["git", "worktree", "list", "--porcelain"])
    if code == 0:
        for block in (out or "").split("\n\n"):
            m = re.search(r"^worktree (.+)$", block, re.M)
            if not m:
                continue
            wt = m.group(1)
            if wt == os.getcwd() or base in wt:
                continue
            if not any(k in wt for k in ("/scratchpad/", "/tmp/")):
                continue      # 素性の分からない場所は触らない
            name = os.path.basename(wt)
            code2, st = _raw(["git", "-C", wt, "status", "--porcelain"])
            if code2 == 0 and st.strip():
                kept.append((name, f"未コミットの変更 {len(st.strip().splitlines())} 件（{wt}）"))
                continue
            if not os.path.isdir(wt):
                code3, o3 = _raw(["git", "worktree", "prune"])
                removed.append((name, "消えていたので prune"))
                continue
            code3, o3 = _raw(["git", "worktree", "remove", wt])
            (removed if code3 == 0 else kept).append(
                (name, f"片付けた（{wt}）" if code3 == 0 else o3.strip()[:60]))

    for n, why in removed:
        print(f"  ✓ {n} — {why}")
    for n, why in kept:
        print(f"  · {n} — 残した（{why}）")
    print(f"\n{len(removed)} 個を片付け、{len(kept)} 個を残した。")
    if kept:
        print("残したものは中身を確認すること — 消えて困るかは、こちらが決めてよいことではない。")
    return 0


def cmd_record(a):
    """2: 済んだ判定を遡って台帳に記録する。

    #7/#8 の統合には判定がどこにも無く（integration_admitted が0件）、しかも「マージ後の
    10件失敗のうち8件は worktree 走査の偽陽性で、#7 の欠陥はゼロ」という切り分けの判断が
    記録から消えていた。**その切り分けこそ後から最も知りたい情報**なので、遡って残せる口を開ける。

    追記型なので過去は書き換わらない — `backfilled: true` を付けて、後から足した記録だと
    分かるようにする（実時点の記録と混ぜない）。
    """
    payload = {"verdict": a.verdict, "issue": a.issue, "deliverable": str(a.issue),
               "backfilled": True, "why": a.why}
    if a.event == "integration_admitted":
        payload.update({"integration_branch": a.base, "deliverables": [str(a.issue)],
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


def cmd_plan(a):
    """何も実行せず、打つイベント列だけを印字する。"""
    parent = a.parent or resolve_parent(a.issue)
    cid = a.candidate_id or _candidate_id(a.issue)
    print(f"# begin #{a.issue} ({a.role}) — parent=#{parent or '(解決できず)'} candidate_id={cid}")
    for i, (desc, _) in enumerate(_steps_begin(a, parent, cid), 1):
        print(f"  {i}. {desc}")
    print(f"\n# complete #{a.issue} — 実行時に --outputs と domain_model が要る")
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="org_cycle", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("begin", "plan"):
        q = sub.add_parser(name)
        q.add_argument("--role", required=True, help="委譲する側（supervisor / 部門長）")
        q.add_argument("--issue", required=True, type=int, help="task Issue 番号")
        q.add_argument("--agent", help="実際に作る側（省略時は --role と同じ）")
        q.add_argument("--phase", default="implement", help="開始するフェーズ（既定 implement）")
        q.add_argument("--parent", help="親 objective 番号（省略時は Issue から自動解決）")
        q.add_argument("--candidate-id", dest="candidate_id",
                       help="省略時は Issue の candidate_id トレーラから読む")
        q.add_argument("--base", help="worktree を切る元（既定 develop）")
        q.add_argument("--why", help="なぜ今これを選んだか（attention_allocated の reason）")
        q.add_argument("--no-worktree", dest="no_worktree", action="store_true",
                       help="worktree を作らない。**並列で回すなら使わないこと** — 同一ツリーで"
                            "並列 maker を走らせると、あるIssueのコミットが別Issueのブランチに"
                            "載る事故が起きる（実際に起きた）。単発の逐次作業のときだけ。")
    q = sub.add_parser("verify", help="gate/skeptic を起動する材料を組み立てる（判定はしない）")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--role", required=True, choices=("gate", "skeptic"))

    q = sub.add_parser("gc", help="溜まった worktree を片付ける（未コミットのものは残す）")
    q.add_argument("--base", default="develop")
    q.add_argument("--all", action="store_true", help="未統合のものも対象にする")

    q = sub.add_parser("record", help="済んだ判定を遡って台帳に記録する（backfill 印が付く）")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--event", required=True, help="integration_admitted / refutation_attempted など")
    q.add_argument("--verdict", required=True)
    q.add_argument("--by", required=True, help="誰の判定か")
    q.add_argument("--why", required=True, help="何を見て、何が決め手になったか")
    q.add_argument("--command", help="当時実行したコマンド")
    q.add_argument("--result", help="その実出力")
    q.add_argument("--base", default="develop")

    q = sub.add_parser("handback", help="feature ブランチを push → develop 宛 PR → Issue に紐付け")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--branch", help="省略時は Issue から決定的に導出")
    q.add_argument("--base", default="develop")
    q.add_argument("--summary", help="何を作ったか（1行）")
    q.add_argument("--result", help="DoD コマンドの実出力（PR body と log に入る）")
    q.add_argument("--files", help="変更ファイル")

    q = sub.add_parser("integrate", help="develop への fan-in（前提照合 → マージ → 統合後テスト → 記録）")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--role", default="integrator", help="統合を回す役割（記録の actor）")
    q.add_argument("--branch", help="省略時は Issue から決定的に導出")
    q.add_argument("--base", default="develop")
    q.add_argument("--test", default="npm test", help="統合後に走らせる全体テスト")
    q.add_argument("--force", action="store_true",
                   help="gate/skeptic の前提が無くても進める。**理由を記録すること**")

    q = sub.add_parser("complete")
    q.add_argument("--role", required=True)
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--agent")
    q.add_argument("--outputs", required=True, help="何を作ったか（1行）")
    q.add_argument("--command", required=True,
                   help="DoD コマンド（verbatim。他人が再実行できる形で）")
    q.add_argument("--result", required=True,
                   help="そのコマンドの**実出力**（失敗込み。「通った」は不可 — log が拒否する）")
    q.add_argument("--files", help="変更したファイル")
    q.add_argument("--learned",
                   help="次のサイクルにも効く学び（doctrine に propose する。admit は gate）")
    q.add_argument("--affects", help="その学びが効く役割（カンマ区切り）")
    q.add_argument("--confidence", type=float, default=0.7,
                   help="その学びへの確信度 0..1（既定 0.7）")
    q.add_argument("--review-days", dest="review_days", type=int, default=180,
                   help="その学びを再確認するまでの日数（既定 180）")
    q.add_argument("--domain-model-updated", dest="domain_model_updated",
                   help="このサイクルが確立したドメイン規則への参照")
    q.add_argument("--domain-model-none", dest="domain_model_none",
                   help="何も確立しなかった理由（明示的な否定。docs/11 §4d）")
    q.add_argument("--candidate-id", dest="candidate_id")
    a = p.parse_args(argv[1:])
    return {"begin": cmd_begin, "complete": cmd_complete, "plan": cmd_plan,
            "verify": cmd_verify, "integrate": cmd_integrate, "handback": cmd_handback, "gc": cmd_gc, "record": cmd_record}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
