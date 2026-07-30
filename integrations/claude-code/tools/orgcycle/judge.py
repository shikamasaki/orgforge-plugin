"""判定の材料を組み立てる — verify / record。

**判定ロジックは一切持たない。** verdict / why / risk / どのミューテーションを試すかは
gate / skeptic が決める。ツールが verdict を決めた瞬間に gate は形骸化する。"""

import json
import os
import re
import sys

from ._core import (
    HERE,
    _agents_dir,
    _events_for,
    _execute,
    _gh_sync,
    _issue_body,
    _ledger,
    _raw,
    _repo,
    _run,
    _sub,
)


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


def _seam(role, issue, title):
    """handoff.py を内部で呼んで seam contract を作る。引数6個の手打ちをここで吸収する。"""
    slice_ = {
        "gate": f"#{issue} 「{title}」の admission — MUST を1つずつ再導出する",
        "skeptic": f"#{issue} 「{title}」の admit 済み成果物への反証",
    }.get(role, f"#{issue} 「{title}」")
    outputs = {
        "gate": "admission_decided（verdict は自分で決める。admit には --evidence が要る）",
        "skeptic": "refutation_attempted（verdict は自分で決める。survives には --evidence が要る）",
    }.get(role, "決定と、その根拠")
    code, out = _run([os.path.join(HERE, "handoff.py"), role,
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


def _judgment_history(issue, cls=None):
    """この Issue に対する過去の判定（訂正済みは除く）を古い順に。

    gate は毎回これを渡されないと **初回判定として扱う**。3周目の #7 で「前回見落とした点を
    今回どう確認したか」を明示させたら質が上がった、という実地の観察がある。過去の reject を
    知らない gate は、同じ指摘を繰り返すか、直ったことの確認を飛ばすかのどちらかになる。
    """
    evs, voided = _events_for(issue)
    out = []
    for e in evs:
        if e.get("seq") in voided:
            continue
        if e["class"] not in ("admission_decided", "refutation_attempted", "rework_requested"):
            continue
        if cls and e["class"] != cls:
            continue
        pl = e.get("payload", {}) or {}
        out.append({"seq": e.get("seq"), "class": e["class"], "actor": e.get("actor"),
                    "verdict": pl.get("verdict"),
                    "why": (pl.get("why") or pl.get("reason") or pl.get("note") or "")})
    return out


def _issue_decision_comments(issue, event):
    """Issue に書かれた判定の理由（台帳は digest だけを持つので、本文はこちらにある）。"""
    args = ["gh", "issue", "view", str(issue), "--json", "comments"]
    r = _repo()
    if r:
        args += ["--repo", r]
    code, out = _raw(args)
    if code != 0:
        return []
    try:
        cs = json.loads(out).get("comments", [])
    except Exception:
        return []
    return [c.get("body", "") for c in cs if event in (c.get("body") or "")]


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
    history = _judgment_history(a.issue)

    ev = {"gate": "admission_decided", "skeptic": "refutation_attempted"}.get(role, "decided")
    verdicts = {"gate": "admit|reject|park", "skeptic": "survives|refuted"}[role]

    out = []
    out.append(f"===== {role} subagent への投入プロンプト（#{a.issue}: {title}）=====\n")
    out.append(seam or "(seam contract の生成に失敗 — handoff.py を確認)")
    out.append("\n## あなたの憲章（agents/%s.md — 検証基準はここが唯一の出所）\n" % role)
    out.append(charter)
    rounds = [h for h in history if h["class"] == "admission_decided"]
    # 台帳と Issue の**多い方**を採る。二重記録の片側が落ちるのが実地の失敗形なので、
    # 台帳だけを数えると「2回目」と言ってしまう（実際は3回目）。回数を過少に伝えると、
    # gate は「ほぼ初回」として扱ってしまい、この節を入れた意味が消える。
    issue_rounds = _issue_decision_comments(a.issue, "admission_decided")
    if history or issue_rounds:
        n = max(len(rounds), len(issue_rounds)) + 1
        out.append(f"\n## この Issue の判定履歴 — **{n} 回目の判定です**\n")
        for h in history:
            line = (f"- seq {h['seq']}: {h['class']} = `{h['verdict']}` by {h['actor']}")
            out.append(line + (f"\n    {' '.join(str(h['why']).split())[:300]}" if h["why"] else ""))
        # 台帳は digest しか持たないので、理由の本文は Issue から引く
        bodies = issue_rounds
        if bodies:
            if len(bodies) > len(rounds):
                out.append(f"\n（台帳には {len(rounds)} 件しか無いが、Issue には "
                           f"{len(bodies)} 件ある — 二重記録の片側が落ちている）")
            out.append("\n<details><summary>前回までの判定の全文（Issue のコメント）</summary>\n")
            for b in bodies[-2:]:
                out.append(b[:5000] + "\n\n---\n")
            out.append("</details>")
        out.append("\n> **前回の指摘が直ったかだけを見るのでは足りない。** 直っていることの確認に加え、"
                   "MUST を1つずつ**再導出**すること — 前回の rework で新しく壊れた箇所は、"
                   "前回の指摘リストには載っていない。実地では、指摘を直す過程で別の穴"
                   "（警報を切る / 新しい公開面を足す）が生まれている。\n"
                   "> 判定にあたっては「前回見落とした点を今回どう確認したか」を --why に書くこと。")

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
        # 5: gate は毎回 --risk に「今回撃っていない領域」を書く。実地では #9 で gate が
        # 「1件も当てていない」と書いた領域から実バグが出た。人が手で転記していたので配管が運ぶ。
        # **断片を正規表現で切り出すより、gate が書いた Known risk の節ごと渡す** —
        # gate は既に構造化して書いており、切り刻むと重複した断片が並んで読めなくなる
        # （最初の実装がそうなった）。**何を撃つかは skeptic が決める。**
        m = re.search(r"\*\*Known risk accepted:\*\*\s*(.+?)(?:\n\n|\Z)", prior, re.S)
        if m:
            body = m.group(1).strip()
            if re.search(r"撃って|当てて|試して|検証して|not exercised|no (?:test|probe|mutation)",
                         body):
                out.append("\n## gate が「今回撃っていない」と書いた領域（**標的候補**）\n")
                out.append(body[:3000])
                out.append("\n> gate がここを撃っていないと明言している以上、**この領域には"
                           "検査が一度も通っていない**。実地では gate が「1件も当てていない」と"
                           "書いた領域から実バグが出た。撃つかどうかは skeptic が決めるが、"
                           "撃たないなら --risk にその理由を書くこと。")

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

    # subagent に渡すのは「返すもの」の指定。**記録するコマンドは載せない** —
    # subagent には ORG_GITHUB_REPO も台帳のパスも渡っておらず、載せると指示と権限が
    # 食い違う。実地で7回、判定を出した後に「記録は監督に委ねます」と止まり、一度は
    # 判定そのものが失われかけた。記録は監督の仕事で、subagent は判定に集中する。
    fields = [("verdict", f"`{verdicts}` のいずれか1つ"),
              ("why", "何を天秤にかけ、何が決め手になったか。verdict の言い換えは不可"),
              ("evidence", "実際に走らせたコマンドと、その**実出力**（失敗も含む）")]
    if role == "gate":
        fields += [("standard", "適用した基準（SPEC の MUST / seam contract / 機械バー）"),
                   ("alternatives", "採らなかった選択肢と、その理由")]
    else:
        fields += [("mutations", "撃ったミューテーションの一覧（検出された／生存した）— "
                                 "次の周回が同じ場所を撃ち直さないために要る"),
                   ("out_of_scope", "**MUST の範囲外**で見つけた欠陥（実在するが、この Issue が"
                                    "守ると述べていないもの）。`verdict` には数えず、"
                                    "「Issue 化を推奨」として返す — 実在の欠陥でも、それは次の "
                                    "Issue の仕事。無ければ「無し」と明示。\n"
                                    "    判断が難しいものは**あなたが決めず**、両方の読み方を"
                                    "書いて監督に返すこと（スコープの carve out は監督の判断）")]
    fields += [("risk", "承知の上で残す穴 / 排除しきれなかった失敗モード。無いなら「無い」と明示")]

    out.append("\n## 返すもの（**判定はあなたが決める。記録は監督が行う**）\n")
    for k, desc in fields:
        out.append(f"- **{k}** — {desc}")
    out.append("\n> **記録コマンドは打たなくてよい。** あなたには `ORG_GITHUB_REPO` も台帳の"
               "パスも渡っていない。上の項目を揃えて返せば、監督が Issue と台帳の両方に"
               "1コマンドで記録する。\n"
               "> **欠けたまま返してはいけない** — 監督は記録できず、判定が失われる"
               "（実地で一度、判定が台帳に入らないまま失われかけた）。\n"
               f"> なお台帳は、maker が自分の成果物を admit することも、maker や admit した "
               f"gate が refute することも**拒否する** — あなたの独立性は記録の時点で"
               f"機械的に検査される。")

    print("\n".join(out))
    # 監督向け（stderr）— subagent が返した値を流し込むコマンド。**判定は埋めない。**
    print(f"\n===== 監督（あなた）が打つコマンド — {role} が返した値を入れる =====\n"
          f'python3 "{os.path.join(HERE, "github_sync.py")}" decide --issue {a.issue} '
          f"--event {ev} \\\n"
          f"  --verdict <{role} が返した verdict> --by {role} \\\n"
          f"  --why \"<{role} の why をそのまま>\" \\\n"
          f"  --evidence \"<{role} の evidence をそのまま>\" \\\n"
          + (f"  --standard \"<...>\" --alternatives \"<...>\" \\\n" if role == "gate" else "")
          + f"  --risk \"<...>\"\n"
          f"（0.21.0 以降、`decide` が Issue と台帳の**両方**に1コマンドで書く。台帳を先に"
          f"通すので、統制が拒否するなら Issue にも記録されない）\n", file=sys.stderr)
    print(f"— この出力を {role} subagent に渡すこと。本文に貼っても、ファイルに落として"
          f"参照させてもよい\n"
          f"  （seam ガードは本文に契約が無ければ、プロンプトが指すファイルを自分で読んで"
          f"検証する）。\n"
          f"配管はここまで。verdict / why / risk は {role} が決める。", file=sys.stderr)
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
