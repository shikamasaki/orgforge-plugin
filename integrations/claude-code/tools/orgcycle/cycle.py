"""サイクルの開始と完了 — begin / complete / plan。

配管（claim → spec_delegated → phase_started → cycle_started → log → stage）と、
完了時の問い返し（ドメインモデル・新しい公開面）を持つ。"""

import json
import os
import re
import sys

from ._core import (
    HERE,
    _admission_for,
    _branch_for,
    _candidate_id,
    _execute,
    _gh_sync,
    _issue_body,
    _ledger,
    _plus_days,
    _raw,
    _refutation_for,
    _repo,
    _run,
    _sub,
    _today,
    resolve_integration_base,
    resolve_parent,
)


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


def _readiness(issue):
    """着手前に「本当に始めてよいか」を見る。**止めない — 見せる。**

    begin は無条件に開始していた。依存が rework 中でも、前提の人間タスクが残っていても
    始まる。github_sync ready は Issue 番号の依存しか見ておらず、rework 中の依存も
    needs-human も見ていない。判断は人がするが、材料が無ければ判断のしようがない。
    """
    warns = []
    _, body = _issue_body(issue)
    for dep in sorted(set(re.findall(r"depends_on[^\n]*?#(\d+)", body or "", re.I))):
        av, _, _ = _admission_for(int(dep))
        code, out = _raw(["gh", "issue", "view", dep, "--json", "state,title,labels"]
                         + (["--repo", _repo()] if _repo() else []))
        state, title, labels = "", "", []
        if code == 0:
            try:
                d = json.loads(out)
                state, title = d.get("state", ""), d.get("title", "")
                labels = [l.get("name", "") for l in d.get("labels", [])]
            except Exception:
                pass
        if av == "reject":
            warns.append(f"#{dep}（{title[:34]}）は gate が reject して rework 中")
        elif state == "OPEN" and av != "admit":
            warns.append(f"#{dep}（{title[:34]}）はまだ完了していない")
        if "orgforge:needs-human" in labels:
            warns.append(f"#{dep} は人間の作業待ち（needs-human）")

    # 自分自身に needs-human が付いていないか / 未解決の人間タスクが無いか
    code, out = _raw(["gh", "issue", "list", "--state", "open",
                      "--label", "orgforge:needs-human", "--json", "number,title", "--limit", "5"]
                     + (["--repo", _repo()] if _repo() else []))
    if code == 0:
        try:
            for h in json.loads(out or "[]"):
                warns.append(f"人間の作業待ち: #{h['number']} {h['title'][:44]}")
        except Exception:
            pass
    return warns


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


# 外に晒される面のパターン。SQL / TS / Python の代表的な公開の形だけを見る。
# 完全な検出は目的ではない — **見落としを人に問い返す**のが目的なので、拾いすぎるより
# 「これは公開面ではないか」と聞ける程度で足りる。
_SURFACE_PATTERNS = (
    (r"create\s+(?:or\s+replace\s+)?function\s+([\w.]+)", "db_function"),
    (r"grant\s+[\w\s,]+\s+on\s+[\w.]*\s*([\w.]+)\s+to\s+(\w+)", "grant"),
    (r"create\s+policy\s+\"?([\w_]+)", "rls_policy"),
    (r"^\+?\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", "export"),
    (r"app\.(?:get|post|put|delete|patch)\(\s*[\"']([^\"']+)", "endpoint"),
)


def _new_public_surfaces(issue, base="develop"):
    """このサイクルで新しく増えた公開面。**判定はしない — 問い返すだけ。**

    認可ホールは「関数を1つ足した」ところから生まれる。実地の join_group がまさにそれで、
    SECURITY DEFINER を1つ増やしたことが誰にも機械的に見えていなかった。
    """
    br = _branch_for(issue)
    code, out = _raw(["git", "diff", f"{base}...{br}", "--unified=0"])
    if code != 0:
        return []
    # **worktree の未コミット分も見る。** 実地では add_member_by_creator（SECURITY DEFINER）が
    # 本番 DB には適用済みなのにコミットされておらず、`base...branch` の差分に出なかった。
    # 「まだコミットしていないから公開面ではない」は成り立たない — 本番には既に在る。
    wt = os.path.join(os.getcwd(), ".orgforge", "wt", f"issue-{issue}")
    if os.path.isdir(wt):
        c2, o2 = _raw(["git", "-C", wt, "diff", base, "--unified=0"])
        if c2 == 0:
            out += "\n" + o2
        c3, untracked = _raw(["git", "-C", wt, "ls-files", "--others",
                              "--exclude-standard"])
        for rel in (untracked or "").split("\n"):
            rel = rel.strip()
            if not rel or not rel.endswith((".sql", ".ts", ".js", ".py")):
                continue
            try:
                path = os.path.join(wt, rel)
                if os.path.getsize(path) > 256 * 1024:
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    body = f.read()
                out += f"\n+++ b/{rel}\n" + "\n".join("+" + l for l in body.split("\n"))
            except Exception:
                continue
    found, seen = [], set()
    definer_ctx = False
    skip = False
    for line in out.split("\n"):
        # どのファイルの差分かを追う。テスト・型定義・設定は公開面ではない —
        # 拾いすぎると **肝心の1件が埋もれる**（実地で add_member_by_creator が
        # テストヘルパ10件に埋もれた。それでは問い返しの意味が無い）。
        if line.startswith("+++ "):
            f = line[4:].strip().lstrip("b/")
            skip = bool(re.search(r"(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.|"
                                  r"\.d\.ts$|(^|/)(scripts|tools)/", f, re.I))
            definer_ctx = False
            continue
        if skip or not line.startswith("+"):
            continue
        low = line.lower()
        if "security definer" in low:
            definer_ctx = True
        for pat, kind in _SURFACE_PATTERNS:
            m = re.search(pat, low, re.I | re.M)
            if not m:
                continue
            name = m.group(1) if m.groups() else m.group(0)
            key = (kind, name)
            if key in seen:
                continue
            seen.add(key)
            found.append({"kind": kind, "name": name, "note": ""})

    # SECURITY DEFINER は**関数ごと**に判定する。ファイル単位のフラグだと、定義が
    # 後ろに来た関数（実地の add_member_by_creator）が印なしになって下位に沈み、
    # まさに確認してほしい1件が埋もれる。
    added = "\n".join(l for l in out.split("\n") if l.startswith("+"))
    for s in found:
        if s["kind"] != "db_function":
            continue
        m = re.search(re.escape(s["name"]) + r"[\s\S]{0,600}?security\s+definer",
                      added, re.I)
        if m:
            s["note"] = "SECURITY DEFINER"
        if re.search(r"grant\s+execute\s+on\s+function\s+" + re.escape(s["name"]),
                     added, re.I):
            s["note"] = (s["note"] + " / grant 済み").strip(" /")

    # 危険な順に。SECURITY DEFINER と grant は呼び手の権限を超えるので最上位。
    rank = {"db_function": 0, "grant": 1, "rls_policy": 2, "endpoint": 3, "export": 4}
    found.sort(key=lambda s: (0 if s["note"] else 1, rank.get(s["kind"], 9)))
    return found


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


def cmd_begin(a):
    # worktree の base は constitution の integration_ref から解決する（OBS-053 / #106）。
    # 台帳に書く前に決める — 決まらないまま claim だけ積むと、fail-closed が半端になる。
    if not getattr(a, "no_worktree", False):
        base, base_err = resolve_integration_base(getattr(a, "base", None))
        if base_err:
            print(f"begin の worktree base が決まらない（#{a.issue}）:\n{base_err}",
                  file=sys.stderr)
            return 2
        a.base = base
    warns = [] if getattr(a, "no_check", False) else _readiness(a.issue)
    if warns:
        print(f"着手前の確認（#{a.issue}）:", file=sys.stderr)
        for w in warns:
            print(f"  ⚠ {w}", file=sys.stderr)
        print("  — これらは**止めない**。承知のうえで進めるなら、そのまま実行される。\n"
              "     前提が崩れたまま作ったものは、後で gate が拒否する側に回る。\n",
              file=sys.stderr)
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
    # 公開面/語彙の検出は**助言**の経路 — constitution が統合先を宣言していればそれを使い、
    # 宣言の無い legacy org では従来どおり develop を試す（diff が取れなければ従来どおり沈黙）。
    # complete 自体を fail-closed にはしない（#106 が要求するのは統合先を消費する4経路）。
    _diff_base, _ = resolve_integration_base(None)
    surfaces = _new_public_surfaces(a.issue, base=_diff_base or "develop")
    if surfaces and not (a.new_surface or a.new_surface_none):
        print(f"⚠ この変更で新しく公開された面がある（#{a.issue}）:", file=sys.stderr)
        for s in surfaces[:10]:
            print(f"    {s['kind']}: {s['name']}"
                  + (f"  ⟨{s['note']}⟩" if s["note"] else ""), file=sys.stderr)
        print("  **認可ホールは「関数を1つ足した」ところから生まれる。**\n"
              "  誰が呼べるのか / 呼ばれたら何ができるのかを確認したうえで、\n"
              "  --new-surface \"<面>: <誰が呼べるか / 何ができるか>\" で申告すること。\n"
              "  公開面ではないと判断するなら --new-surface-none \"<理由>\"。\n"
              "  申告は gate に渡り、台帳にも残る。", file=sys.stderr)
        return 2

    if a.domain_model_none:
        # 素通りをさせない: 「規則を定めていない」と書いたサイクルが、実は語彙を作っていないか。
        ex = _new_exports(a.issue, base=_diff_base or "develop")
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
    if a.new_surface or a.new_surface_none:
        _ledger("append", "--actor", a.agent or a.role, "--class", "public_surface_declared",
                "--natural-key", f"surface-{a.issue}",
                "--payload", json.dumps(
                    {"role": a.agent or a.role, "issue": a.issue,
                     "surfaces": [{"kind": "declared", "name": s, "exposure": "", "authz": ""}
                                  for s in (a.new_surface or [])],
                     "none_asserted": a.new_surface_none or ""}, ensure_ascii=False))
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


def cmd_plan(a):
    """何も実行せず、打つイベント列だけを印字する。"""
    # plan こそ「打つ前に見る」場所なので、着手前の確認はここにも出す。
    for w in ([] if getattr(a, "no_check", False) else _readiness(a.issue)):
        print(f"  ⚠ {w}", file=sys.stderr)
    # plan は実行しないので止めない。ただし begin が fail-closed になることは予告する（#106）。
    base, base_err = resolve_integration_base(getattr(a, "base", None))
    if base_err:
        print(f"  ⚠ begin は worktree base を決められず失敗する:\n{base_err}", file=sys.stderr)
    else:
        a.base = base
    parent = a.parent or resolve_parent(a.issue)
    cid = a.candidate_id or _candidate_id(a.issue)
    print(f"# begin #{a.issue} ({a.role}) — parent=#{parent or '(解決できず)'} candidate_id={cid}")
    for i, (desc, _) in enumerate(_steps_begin(a, parent, cid), 1):
        print(f"  {i}. {desc}")
    print(f"\n# complete #{a.issue} — 実行時に --outputs と domain_model が要る")
    return 0
