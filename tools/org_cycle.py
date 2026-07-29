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
        (f"log cycle_started → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "cycle_started",
                          "--phase", phase, "--event-id", f"start-{cid}",
                          "--detail", f"{agent} が着手（parent #{parent or '-'} を継承）")),
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
                          "--event-id", f"done-{cid}", "--detail", a.outputs)),
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

    out.append(f"\n## 記録（**判定はあなたが決める。この雛形は値を埋めていない**）\n")
    out.append("```")
    out.append(f'python3 "$P/tools/github_sync.py" decide --issue {a.issue} --event {ev} \\')
    out.append(f'  --verdict <{verdicts}> --by {role} \\')
    out.append('  --why "<何を天秤にかけ、何が決め手になったか>" \\')
    out.append('  --evidence "<実際に走らせたコマンドと、その実出力>" \\')
    if role == "gate":
        out.append('  --alternatives "<採らなかった選択肢と、その理由>" \\')
        out.append('  --standard "<適用した基準>" \\')
    out.append('  --risk "<承知の上で残す穴 / 排除しきれなかった失敗モード>"')
    out.append("# 出力される reasoning_sha256= を、次の ledger 受領証の payload に入れること")
    out.append(f'python3 "$P/tools/ledger.py" append --actor {role} --class {ev} \\')
    out.append(f'  --payload \'{{"verdict":"<...>","deliverable":"{a.issue}",'
               f'"reasoning_sha256":"<...>","issue":{a.issue}}}\'')
    out.append("```")
    print("\n".join(out))
    print(f"\n— この出力を {role} subagent にそのまま渡すこと。"
          f"配管はここまで。verdict / why / risk は {role} が決める。", file=sys.stderr)
    return 0


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
    cid = a.candidate_id or _candidate_id(a.issue)
    rc = _execute(_steps_complete(a, cid), f"complete #{a.issue} ({a.role})")
    if rc == 0:
        print(f"\nNEXT: gate の admission がまだ。`/orgforge-plugin:org-work` の verify 手順か、"
              f"gate subagent を呼ぶこと — maker は自分の仕事を admit できない（台帳が拒否する）。")
    return rc


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
        q.add_argument("--no-worktree", dest="no_worktree", action="store_true",
                       help="worktree を作らない。**並列で回すなら使わないこと** — 同一ツリーで"
                            "並列 maker を走らせると、あるIssueのコミットが別Issueのブランチに"
                            "載る事故が起きる（実際に起きた）。単発の逐次作業のときだけ。")
    q = sub.add_parser("verify", help="gate/skeptic を起動する材料を組み立てる（判定はしない）")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--role", required=True, choices=("gate", "skeptic"))

    q = sub.add_parser("complete")
    q.add_argument("--role", required=True)
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--agent")
    q.add_argument("--outputs", required=True, help="何を作ったか（1行）")
    q.add_argument("--domain-model-updated", dest="domain_model_updated",
                   help="このサイクルが確立したドメイン規則への参照")
    q.add_argument("--domain-model-none", dest="domain_model_none",
                   help="何も確立しなかった理由（明示的な否定。docs/11 §4d）")
    q.add_argument("--candidate-id", dest="candidate_id")
    a = p.parse_args(argv[1:])
    return {"begin": cmd_begin, "complete": cmd_complete, "plan": cmd_plan,
            "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
