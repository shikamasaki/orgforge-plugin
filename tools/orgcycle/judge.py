"""判定の材料を組み立てる — verify / record。

**判定ロジックは一切持たない。** verdict / why / risk / どのミューテーションを試すかは
gate / skeptic が決める。ツールが verdict を決めた瞬間に gate は形骸化する。"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import re
import sys

from organ_binding import BindingError

from ._core import (
    HERE,
    issue_worktree,
    review_subject,
    worktree_rooted_at,
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
from .preflight import PreflightConfigError, run_declared_preflights


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


def _verdict_schema(role):
    """Return the bundled structured-output schema for a judge role.

    ``HERE`` is the tools directory in both the neutral checkout and each self-contained
    harness bundle.  Keeping this resolution in one named helper makes the packaging contract
    executable: build scripts must place schemas under the adjacent ``template/schemas`` tree.
    """
    return os.path.normpath(
        os.path.join(HERE, "..", "template", "schemas", f"{role}-verdict.json"))


def _stable_organ_invocation():
    """Return the org-side launcher; installed bundles fail closed if SessionStart did not bind."""
    from discover import org_root
    from organ_binding import BindingError, installation_kind, invocation
    root = org_root()
    harness = installation_kind(HERE)
    stable = invocation(root, harness) if root else None
    if root and harness in ("claude-code", "codex") and not stable:
        raise BindingError(
            "installed plugin で動いているが organization-side launcher が未登録。"
            "SessionStart hookを有効にしてhost sessionを再起動すること")
    return stable


def _organ_command(stable, organ):
    """Render a stable public invocation, retaining a source-checkout fallback for development."""
    if stable:
        return f'"{stable}" {organ.replace("_", "-")}'
    filename = organ.replace("-", "_") + ".py"
    return f'python3 "{os.path.join(HERE, filename)}"'


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

    gate は毎回これを渡されないと **初回判定として扱う**。3周目の で「前回見落とした点を
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
    from review_freshness import (descriptor_status, freshness_policy, integration_ref_policy,
                                  persist_descriptor)
    try:
        from discover import constitution
        _constitution_path = constitution()
    except Exception:
        _constitution_path = None
    _declared, _strict_freshness, _policy_error = freshness_policy(_constitution_path)
    if _policy_error:
        print(f"review freshness policy が不正: {_policy_error}", file=sys.stderr)
        return 2
    _ref_declared, _configured_ref, _ref_error = integration_ref_policy(_constitution_path)
    if _ref_error and not getattr(a, "base", None):
        print(f"integration ref policy が不正: {_ref_error}", file=sys.stderr)
        return 2
    if _strict_freshness and not getattr(a, "base", None) and not _configured_ref:
        print("strict review freshness では統合先を推測しない。\n"
              "  constitution.yaml に "
              "`enforcement.judges.integration_ref: origin/main` のように宣言するか、"
              "今回だけ `verify --base <ref>` を明示すること。", file=sys.stderr)
        return 11
    _integration_ref = getattr(a, "base", None) or _configured_ref
    # 判定対象は **Issue の worktree** の tree（#101）。cwd の tree を黙って記述すると、
    # 本体から打った verify がどの Issue でも同じ subject（ahead=0 の main）を mint し、
    # joint admission が使う「二血統が同じものを見た」証拠が壊れる — 実測 OBS-031/055/071。
    _subject_override = getattr(a, "subject_root", None)
    if _subject_override:
        _subject_cwd = os.path.abspath(_subject_override)
        if not os.path.isdir(_subject_cwd):
            print(f"--subject-root が存在しない: {_subject_cwd}", file=sys.stderr)
            return 2
    else:
        _subject_cwd = issue_worktree(a.issue)
        # isdir では足りない: 空の残骸ディレクトリや repo root への symlink は primary の
        # 内側に居るので、git が primary に解決して OBS-071 の偽造がそのまま通る。
        # 「まさにそこを toplevel とする実 worktree」まで確かめる（worktree_rooted_at）。
        if not _subject_cwd or not worktree_rooted_at(_subject_cwd):
            _expected = _subject_cwd or os.path.join(
                ".orgforge", "wt", f"issue-{a.issue}")
            _hint = ("（パスは存在するが実 worktree ではない — 残骸なら "
                     "`git worktree prune` で片付けてから begin し直すこと）\n"
                     if _subject_cwd and os.path.lexists(_subject_cwd) else "")
            print(f"Issue #{a.issue} の worktree が無い: {_expected}\n{_hint}"
                  "  cwd の tree では代用しない — 本体から打つと、どの Issue でも同じ "
                  "subject が mint され、判定の同一性が壊れる（#101）。\n"
                  "  `org_cycle begin --issue N` で worktree を作るか、worktree 以外の "
                  "checkout を意図して判定するなら `--subject-root <path>` を明示すること。",
                  file=sys.stderr)
            return 12
    _sid, _sparts = review_subject(
        a.issue, role, getattr(a, "phase", None), cwd=_subject_cwd,
        integration_ref=_integration_ref)
    if _subject_override:
        # digest には入らない（SUBJECT_FIELDS 外）が、どの checkout を意図して判定した
        # かは印字に残す — escape hatch は黙って使わせない。
        _sparts = {**_sparts, "subject_root": _subject_cwd}
    _subject_path = persist_descriptor(_sid, _sparts, cwd=_subject_cwd)
    _freshness = descriptor_status({**_sparts, "review_subject_id": _sid}, _subject_cwd)
    if _strict_freshness and not _freshness["ok"]:
        print(f"review subject が現在の統合先に対して有効でない: "
              f"{_freshness['reason']} — {_freshness['detail']}\n"
              f"  subject: {_sid}\n  evidence: {_subject_path}\n"
              "  自動 rebase はしない。統合先を取り込み、同じ verify で再判定すること。",
              file=sys.stderr)
        return 11
    # **記録のためだけに judge を回さない。** subject は git と受け入れ基準から決まるので、
    # 材料を組む前に答えられる。
    if getattr(a, "print_subject", False):
        print(_sid)
        for k, v in _sparts.items():
            print(f"  {k:20}= {v or '(なし)'}", file=sys.stderr)
        print(f"  {'descriptor':20}= {_subject_path}", file=sys.stderr)
        return 0
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
    # judge を起動する前に、**この Issue / phase / role にだけ適用される**環境probeを走らせる。
    # プロセス名から Docker 等を推測せず、org が宣言した argv の実測結果だけを証拠にする。
    phase = getattr(a, "phase", None) or "implement"
    try:
        preflight_ok, preflight_evidence = run_declared_preflights(
            a.issue, role, phase, cwd=os.getcwd())
    except PreflightConfigError as exc:
        print(f"judge preflight の宣言が不正: {exc}\n"
              "  **設定を読めない・boundedでないなら judge を起動しない。**", file=sys.stderr)
        return 2
    if not preflight_ok:
        print("judge preflight が失敗したため、judge は起動していない。\n"
              "  上の measured result を直し、同じ verify を再実行すること。", file=sys.stderr)
        return 8
    try:
        stable_organ = _stable_organ_invocation()
    except BindingError as exc:
        print(f"installed-organ binding がREADYでない: {exc}\n"
              "  別checkoutを代用せず、host sessionを再起動してから verify をやり直すこと。",
              file=sys.stderr)
        return 9
    seam = _seam(role, a.issue, title)
    prior = _prior_gate(a.issue) if role == "skeptic" else None
    history = _judgment_history(a.issue)

    ev = {"gate": "admission_decided", "skeptic": "refutation_attempted"}.get(role, "decided")
    verdicts = {"gate": "admit|reject|park", "skeptic": "survives|refuted"}[role]

    out = []
    out.append(f"===== {role} subagent への投入プロンプト（#{a.issue}: {title}）=====\n")
    out.append(seam or "(seam contract の生成に失敗 — handoff.py を確認)")
    if stable_organ:
        out.append("\n## OrgForge organ の呼び出し契約（**この固定launcherだけを使う**）\n")
        out.append(f"`{stable_organ} <organ> [args...]`\n\n"
                   "version付きcache pathや別のdevelopment checkoutを探索しない。"
                   "plugin更新後の実体はSessionStartがこのlauncherへ再束縛する。")
    if preflight_evidence:
        out.append("\n## judge dispatch 前の environment preflight（監督が実測）\n")
        out.extend(preflight_evidence)
        out.append("\n> これは宣言されたコマンドの測定結果であり、daemon名や実装を推測した結果ではない。")
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
    # `prior`（gate の最新判定の全文）は、上の判定履歴が既に同じものを出している。
    # **両方出すと同じ本文が2回並ぶ** — 実測で skeptic のプロンプト457行のうち、
    # 「0013 の一手隣」26行と「maker の自己申告」20行超が重複していた。プロンプトの長さは
    # 読む時間に直結する（実地の計測では総時間の21%が1回の待ち時間で、その一部がこれ）。
    # 履歴を出していないときだけ prior を出す。
    if prior and not (history or issue_rounds):
        out.append("\n## gate が既に見たこと（重複を避けるため。追認する義務はない）\n")
        out.append(prior)
    elif role == "skeptic" and not prior:
        out.append("\n## gate が既に見たこと\n(#%d に admission_decided の記録が無い。"
                   "gate の admit 前に skeptic を回そうとしていないか確認すること)" % a.issue)

    if role == "gate":
        # 6: ツールのパスが解決できず repro_lint が一度も走っていなかった。org_cycle は自分の
        # 位置を知っているので絶対パスを埋める。機械的拒否層は、誰も diff を読まない以上
        # 「走らなかった」が最も危ない失敗形。
        out.append("\n## 機械バー（**このコマンドをそのまま実行すること。未実行は reject 事由**）\n")
        out.append("```")
        out.append(f'{_organ_command(stable_organ, "repro-lint")} check . --phase implement')
        out.append("```")
        out.append("HOLD（exit 10）なら reject。パスが通らない場合はそう報告すること — "
                   "「ツールが無いので未実行」は、機械バーが効いていないという最も重い所見。")
    if role == "skeptic" and prior:
        # 5: gate は毎回 --risk に「今回撃っていない領域」を書く。実地では で gate が
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
                       f"> `{_organ_command(stable_organ, 'doctrine')} admit "
                       f"{_sub('doctrine')} <role> <claim-id> --by gate`\n"
                       "> admit しなければ、この学びは次の Issue に渡らない。"
                       "実地では同じ失敗を3回繰り返した。")

    out.append("\n## 変異検査の証拠規律（**空振りした変異の GREEN は証拠ではない**）\n")
    out.append(
        "変異検査を使う場合は、必ず **baseline → mutate → postcondition → test → restore → "
        "restore postcondition** の順で実行する。変異コマンドが exit 0 でも、対象状態を読み返して"
        "変化を確認するまでは `applied` ではない。コマンドが無い・接続できない・対象が違う・"
        "変化しなかった場合、その後の GREEN を『変異を生き延びた』証拠に数えてはいけない。\n\n"
        "- mutate と postcondition 確認と test は、前段の失敗を隠さない形（例: `&&`）で繋ぐ。\n"
        "- postcondition には、変更後の状態を読んだ**実コマンドと実出力**を残す。\n"
        "- 復元後も状態を読み返す。復元を確認できない変異を残したまま判定を終えない。\n"
        "- 適用できなかった試行は `detected=false` と推測せず、未測定として evidence / risk に"
        "失敗出力を残す。構造化出力の `mutations` には、適用と postcondition を確認できたものだけ"
        "を入れる。\n"
        "- 環境固有の入口（Docker上のDB等）は、repoの設定・実行中サービス・既存テストから"
        "導出して接続を実測する。ホストに同名CLIがあると仮定しない。")

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
        fields += [("mutations", "**適用後状態を実測できた**ミューテーションの一覧。各項目に "
                                 "`applied: true` と postcondition の実コマンド/実出力を含める。"
                                 "復元後の読取結果も `restore_postcondition` に含める。"
                                 "適用失敗はここへ入れず evidence / risk に未測定として残す — "
                                 "次の周回が同じ場所を撃ち直さないために要る"),
                   ("out_of_scope", "**MUST の範囲外**で見つけた欠陥（実在するが、この Issue が"
                                    "守ると述べていないもの）。`verdict` には数えず、"
                                    "「Issue 化を推奨」として返す — 実在の欠陥でも、それは次の "
                                    "Issue の仕事。無ければ「無し」と明示。\n"
                                    "    判断が難しいものは**あなたが決めず**、両方の読み方を"
                                    "書いて監督に返すこと（スコープの carve out は監督の判断）")]
    fields += [("risk", "承知の上で残す穴 / 排除しきれなかった失敗モード。無いなら「無い」と明示")]

    if role == "skeptic":
        out.append("\n**skeptic の返り値は常に構造化 JSON にすること。** 静的判定で変異を"
                   "使わなかった場合も `\"mutations\": []` を含める。散文だけの報告は、"
                   "変異の適用・復元を機械検査できないため成果物として受理されない。")

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

    # **判定対象の同一性を、判定の前に固定する。** judge が subject を書けるなら、別の成果物を
    # 見た2件を「同じものを見た」と申告して一致を作れる（監査が実証: revision A と B の admit で
    # joint が生成された）。verify が観測し、judge は運ぶだけ。
    out.append(f"\n## 判定対象（review_subject_id — **変更しないこと**）\n\n"
               f"    {_sid}\n\n"
               + "\n".join(f"    {k:20}= {v or '(なし)'}" for k, v in _sparts.items())
               + f"\n    {'descriptor':20}= {_subject_path}"
               + "\n\nこの id は監督が記録に載せる。**あなたが作る値ではない。**"
                 " 別の血統の judge にも同じ id が渡っており、"
                 "**2件の id が一致しない限り admission は生成されない** —"
                 " 別の revision を見た2つの通過は、一致ではない。")

    _lineage, _hcfg = _judge_lineage(role)
    # cross-harness では stdout は **判定** の置き場所にする（intake にそのまま渡せる形）。
    # 材料は stderr に回す — 監督が読めることは残す。
    print("\n".join(out), file=sys.stderr if _lineage == "cross-harness" else sys.stdout)
    # 監督向け（stderr）— subagent が返した値を流し込むコマンド。**判定は埋めない。**
    print(f"\n[review_subject_id] {_sid}\n"
          f"  記録のときにこの値を --subject に渡すこと。**judge に作らせない。**",
          file=sys.stderr)
    print(f"\n===== 監督（あなた）が打つコマンド — {role} が返した値を入れる =====\n"
          f'{_organ_command(stable_organ, "github-sync")} decide --issue {a.issue} '
          f"--event {ev} \\\n"
          f"  --verdict <{role} が返した verdict> --by {role} \\\n"
          f"  --why \"<{role} の why をそのまま>\" \\\n"
          f"  --evidence \"<{role} の evidence をそのまま>\" \\\n"
          f"  --claimed \"<{role} が報告したこと。条件節（「〜には無い」「未測定」）は落とさず>\" \\\n"
          f"  --verified \"<**あなたが自分で走らせて**確かめたこと。コマンドと出力>\" \\\n"
          + (f"  --standard \"<...>\" --alternatives \"<...>\" \\\n" if role == "gate" else "")
          + f"  --risk \"<...>\"\n"
          f"（0.21.0 以降、`decide` が Issue と台帳の**両方**に1コマンドで書く。台帳を先に"
          f"通すので、統制が拒否するなら Issue にも記録されない）\n", file=sys.stderr)
    # ① reject/refuted を受けたら rework の発注も記録する。**判定の記録と同じ場所に置く** —
    # 発注は「判定を受け取る → 検証 → decide → 発注 → 記録」の順で、発注した subagent の通知が
    # 来ると記録が流れる。記録のコマンドが目の前にある状態で発注すれば順序が逆転する。
    # 運用で reject/refuted の多くに対し rework_requested が台帳に無く、show の警告が沈黙した。
    bad = "reject" if role == "gate" else "refuted"
    print(f"===== {bad} だった場合 — rework の発注も記録する =====\n"
          f'{_organ_command(stable_organ, "org-cycle")} rework --issue {a.issue} '
          f"--after {bad} --by <あなたの役割> \\\n"
          f'  --reason "<{role} の指摘のうち、maker に直させることを1行で>" '
          f"--round {len(rounds) + 1 if 'rounds' in dir() else '<何周目か>'}\n"
          f"（これを打たないと `show` の rework 警告が沈黙する — 台帳に材料が入らないので"
          f"閾値に届かない。**道具は数えられないものを数えない**）\n", file=sys.stderr)
    # ヘッドレスで回す形（Codex / claude -p）。**血統を分けるなら別ハーネスで動かす** —
    # role-settings.yaml は skeptic に family-B（gate と別系統）を宣言しているが、同一ハーネスの
    # subagent では inherit になり、同じ base model の盲点を共有する（docs/03 §3）。
    # constitution の `enforcement.judges.lineage` を読む。**既定は same-harness** —
    # 別ハーネスの契約・CLI・認証を前提にすると、持っていない環境で org が回らなくなる。
    # 層を増やすのは選択であって前提ではない。
    _schema = _verdict_schema(role)
    if _lineage == "cross-harness":
        if not os.path.isfile(_schema):
            print(f"judges.lineage = cross-harness だが {role} の出力スキーマが無い "
                  f"（探した先: {_schema}）。スキーマ無しで別ハーネスに投げると、verdict が"
                  f"欠けた散文が返ってきても構造では気づけない。**血統を分ける前にスキーマを"
                  f"揃えること。**", file=sys.stderr)
            return 2
        # **judge は2人走る。** 同一ハーネスの subagent（材料は上の stderr）と、別ハーネスの
        # headless（下で起動する）。片方でも reject/refuted なら reject —
        # AND ではなく厳しい側に倒す。実測（#11 の認可穴・#42 の Testing Library 欠落）で
        # **2件とも厳しい側が正しかった**。多数決にすると 1:1 で決まらず、監督の裁量に戻る。
        rc = _run_headless(role, a.issue, "\n".join(out), _hcfg, _schema, stable_organ)
        print(f"\n===== judge は2人いる（judges.lineage = cross-harness）=====\n"
              f"  1. 同一ハーネスの {role} subagent — 上の材料をそのまま渡す\n"
              f"  2. 別ハーネスの {role} — " +
              ("上の JSON（stdout）が その判定である" if rc == 0
               else "**起動できなかった。判定は得られていない**") + "\n"
              f"  **片方でも {bad} なら {bad} として扱う。** 一致を要求する形なので、"
              f"admit を記録するには両方の admit が要る（decide が検査する）。\n"
              f"  判定が食い違ったら、食い違いそのものを記録すること —\n"
              f'    {_organ_command(stable_organ, "ledger")} append '
              f"--class judges_disagreed --actor <あなたの役割> \\\n"
              f"      --payload '{{\"issue\": {a.issue}, \"role\": \"{role}\", "
              f"\"same_harness\": \"<verdict>\", \"cross_harness\": \"<verdict>\"}}'\n"
              f"  （食い違いは異常ではなく**血統を分けた目的**である。消さずに数えること）",
              file=sys.stderr)

    print(f"— この出力を {role} subagent に渡すこと。本文に貼っても、ファイルに落として"
          f"参照させてもよい\n"
          f"  （seam ガードは本文に契約が無ければ、プロンプトが指すファイルを自分で読んで"
          f"検証する）。\n"
          f"配管はここまで。verdict / why / risk は {role} が決める。", file=sys.stderr)
    return 0




# 役割ごとに「報告が成果物の形になっている」ための必須要素。
# **subagent の turn が作業の途中で終わる**ことがある（運用で短期間に複数回）。status は completed で
# 返り、result は「Now the key attack:」のような宣言1文だけ。SendMessage で再開させると続きを
# 実行して完走したので、agent が死んだのではなく報告が成果物の形になる前に turn が終わっている。
#
# **気づけない形が危ない。** 「MUST 2 は防がれました」で切れていたら、それを verdict として
# 読んで admit しかねない — この org が繰り返し検出した「確かめていないことを確かめたかのように
# 述べる」が、**報告の切断**という経路で起きる。
_INTAKE = {
    "skeptic": [
        ("verdict", r"\b(survives|refuted)\b", "verdict が survives / refuted のどちらでもない"),
        ("evidence", r"(npm |npx |git |psql|python3|node |pytest|exit=|passed|failed)",
         "実際に走らせた痕跡（コマンド・出力）が無い"),
    ],
    "gate": [
        ("verdict", r"\b(admit|reject|park)\b", "verdict が admit / reject / park のどちらでもない"),
        ("evidence", r"(npm |npx |git |psql|python3|node |pytest|exit=|passed|failed)",
         "実際に走らせた痕跡（コマンド・出力）が無い"),
    ],
    "maker": [
        ("commit", r"\b[0-9a-f]{7,40}\b", "コミットハッシュが無い"),
        ("dod", r"(npm |npx |pytest|passed|failed|Tests?\s)",
         "DoD コマンドの実測出力が無い"),
    ],
}
# 作業の途中で切れた報告に出やすい語。**これ自体は根拠にしない** — 必須要素が揃っていれば、
# 途中で "Now ..." と書いていても完走している。欠落と同時に出たときだけ確度が上がる。
_TRUNCATED = (r"^\s*(now|next|then)\b", r"(しましょう|します)。?\s*$",
              r"(let me|i'll|i will)\b.*:$", r":\s*$")



def _run_headless(role, issue, material, cfg, schema, stable_organ=None):
    """judge を別ハーネスで実際に起動し、構造化された verdict を持ち帰る。

    **案内を出すだけにしない。** 打つかどうかを監督が選べるなら、それは「検査を呼ぶかどうかを
    検査される側が決める」構造に戻る（docs/11）。cross-harness を宣言した org では、verify が
    自分で起動して結果を出すところまでを配管とする。

    judge は read-only で走らせる。**別ハーネスのガードレールは未検証**なので、書けないなら
    そのハーネスが何を許していても安全側に倒れる。
    """
    cfg = cfg or {}
    cli = str(cfg.get("cli") or "codex")
    model, effort = cfg.get("model"), cfg.get("effort")
    exe = shutil.which(cli)
    if not exe:
        print(f"judges.harness.{role}.cli = {cli!r} が PATH に無い。"
              f"インストールと認証を済ませるか、constitution の judges.lineage を "
              f"same-harness に戻すこと。", file=sys.stderr)
        return 4

    # **固定パスにしない。** /tmp/orgforge-{role}-{issue}.json だと、並行実行が同じファイルを
    # 踏み、失敗した回の古い出力を次の回が読む（監査指摘）。材料のダイジェストを名前に入れ、
    # 同じ材料の再実行だけが同じファイルに当たるようにする。
    _mat = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    _dir = os.path.join(tempfile.gettempdir(), "orgforge-judge")
    os.makedirs(_dir, exist_ok=True)
    out_json = os.path.join(_dir, f"{role}-{issue}-{_mat}.json")
    if os.path.exists(out_json):
        os.remove(out_json)          # 前回の残骸を判定として読まない
    if cli == "codex":
        cmd = [exe, "exec", "--sandbox", "read-only"]
        if model:
            cmd += ["-m", str(model)]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        cmd += ["--output-schema", schema, "-o", out_json, material]
    elif cli == "claude":
        # claude -p は --output-schema を持たないので、スキーマを本文で要求し、
        # 返ってきた JSON を intake の側で検査する。**構造の保証が一段弱いことを言う。**
        cmd = [exe, "-p", material + "\n\n## 返す形\n"
               "次のスキーマに厳密に一致する JSON **のみ** を返すこと（前後に散文を付けない）:\n"
               + open(schema, encoding="utf-8").read(),
               "--output-format", "json"]
        if model:
            cmd += ["--model", str(model)]
    else:
        print(f"judges.harness.{role}.cli = {cli!r} は未対応（codex | claude）。", file=sys.stderr)
        return 2

    # **read-only の judge は、実行して緑を確かめる MUST を構造的に admit できない。**
    # 実測: #34 は「静的には妥当だが『100回連続 green』を read-only サンドボックスで再導出
    # できない」として park を返した。park 自体は正しい振る舞い（測れないのに admit しない）だが、
    # 判定を回してから分かるのは無駄なので、**先に言う**。
    print(f"[{role}] judge は read-only で走る（judges.read_only）。別ハーネスのガードレールは"
          f"未検証なので、書けないなら安全側に倒れる。\n"
          f"  ただし **実行して緑を確かめる類の MUST は再導出できず、park になる** "
          f"（テストの連続実行・実 DB への到達・ビルド）。\n"
          f"  その MUST が admission の荷重を持つなら、判定の前に監督が実測して "
          f"evidence として渡すこと。", file=sys.stderr)
    print(f"[{role}] {cli} を read-only で起動している"
          + (f"（model={model}" + (f", effort={effort}" if effort else "") + "）" if model else "")
          + " — 応答まで数分かかることがある …", file=sys.stderr)
    try:
        # stdin を閉じる。codex exec は stdin を読もうとして、端末が無いと止まる（実測）。
        pr = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=int(os.environ.get("ORG_JUDGE_TIMEOUT", "1800")))
    except subprocess.TimeoutExpired:
        print(f"[{role}] {cli} がタイムアウトした（ORG_JUDGE_TIMEOUT で延ばせる）。",
              file=sys.stderr)
        return 5
    if pr.returncode != 0:
        print(f"[{role}] {cli} が exit={pr.returncode} で終了した:\n"
              f"{(pr.stderr or pr.stdout or '')[-1200:]}", file=sys.stderr)
        return 6

    raw = None
    if os.path.isfile(out_json):
        raw = open(out_json, encoding="utf-8").read()
    elif cli == "claude":
        try:                                    # claude -p --output-format json の封筒を開ける
            raw = (json.loads(pr.stdout) or {}).get("result") or pr.stdout
        except Exception:
            raw = pr.stdout
    if not raw or not raw.strip():
        print(f"[{role}] {cli} が空を返した。判定は得られていない。", file=sys.stderr)
        return 7

    print(raw)                                  # 監督が読む・intake に渡せる形で stdout に出す
    print(f"\n[{role}] 別ハーネス（{cli}"
          + (f" / {model}" if model else "") + f"）の判定を持ち帰った。**まだ記録していない。**\n"
          f"  内容の側から検査する:\n"
          f'    {_organ_command(stable_organ, "org-cycle")} intake --issue {issue} '
          f"--role {role} --report {out_json if os.path.isfile(out_json) else '-'}\n"
          f"  検査を通ったら記録する（verdict / why は判定した側のもの。監督が書き換えない）。",
          file=sys.stderr)
    return 0


def _judge_lineage(role):
    """constitution の `enforcement.judges` を読む。(lineage, harness-cfg) を返す。

    **既定は `same-harness`。** 別ハーネスを前提にすると、その契約・CLI・認証を持っていない
    環境で org が回らなくなる。複数の血統を並べるのは「スイスチーズ」の層を増やす選択であって、
    org が成立する前提ではない。

    **ただし読めないときは止める（fail-closed）。** 0.32.0 は例外を握りつぶして
    `same-harness` を返していた — cross-harness を宣言した org で YAML が壊れていると、
    **強い安全モードが黙って通常モードに落ちる**。判定の血統が分かれていないことに
    気づく経路が無くなるので、これは沈黙してはいけない側の失敗である。
    """
    env = os.environ.get("ORG_JUDGE_LINEAGE")
    if env:
        return env.strip(), None
    try:
        sys.path.insert(0, HERE)
        from discover import constitution
        path = constitution()
    except Exception as e:
        raise SystemExit(f"constitution の場所を解決できない: {e}\n"
                         "  judges.lineage を読めないまま judge を起動すると、cross-harness を"
                         "宣言した org が黙って同一血統で判定する。")
    if not path or not os.path.isfile(path):
        return "same-harness", None        # constitution が無い = 宣言が無い
    try:
        import yaml
    except Exception:
        raise SystemExit("PyYAML が無いので constitution を読めない。\n"
                         "  cross-harness の宣言が黙って消えることは許さない:\n"
                         "    python3 -m pip install pyyaml")
    try:
        with open(path, encoding="utf-8") as f:
            c = yaml.safe_load(f) or {}
    except Exception as e:
        raise SystemExit(f"constitution.yaml を解析できない: {e}\n  ファイル: {path}\n"
                         "  **設定を読めないなら止める。**")
    if not isinstance(c, dict):
        raise SystemExit(f"constitution.yaml が map ではない（{type(c).__name__}）: {path}")
    j = ((c.get("enforcement") or {}).get("judges") or {})
    declared = str(j.get("lineage") or "same-harness").strip()
    sys.path.insert(0, HERE)
    from harness import active_harness, effective_lineage, opposite_harness
    lineage = effective_lineage(declared)
    if lineage == "same-harness":
        return lineage, None

    harness = j.get("harness") or {}
    if not isinstance(harness, dict):
        raise SystemExit("judges.harness が map でない。cross-harness の経路を選べない。")
    missing = [name for name in ("claude", "codex")
               if not isinstance(harness.get(name), dict)]
    if missing:
        raise SystemExit("judges.harness に claude / codex 両方の map が必要（不足: "
                         + ", ".join(missing) + "）。")

    primary = active_harness()
    secondary = opposite_harness(primary)
    cfg = harness[secondary].get(role)
    if not isinstance(cfg, dict):
        raise SystemExit(f"judges.harness.{secondary}.{role} が必要。\n"
                         "  cross-harness の役割を暗黙の CLI に委ねない。")
    cli = str(cfg.get("cli") or "").strip()
    if cli != secondary:
        raise SystemExit(f"主系 {primary!r} の別血統 CLI は {secondary!r} でなければならないが、"
                         f"{cli!r} が指定されている。\n"
                         "  同じハーネスを2回走らせても cross-harness にはならない。")
    return lineage, cfg


def cmd_intake(a):
    """subagent が返した報告が成果物の形になっているかを検査する。

    **判定はしない。** verdict の中身も、その妥当性も見ない — 見るのは「役割として要求される
    欄が埋まっているか」だけである。埋まっていなければ「報告が不完全。再開させること」と言う。
    いまは監督が目で気づくかどうかに賭かっている。
    """
    text = a.report
    if a.report == "-":
        text = sys.stdin.read()
    role = a.role
    checks = _INTAKE.get(role)
    if not checks:
        print(f"役割 {role!r} の受け入れ検査は定義されていない"
              f"（定義済み: {', '.join(sorted(_INTAKE))}）。", file=sys.stderr)
        return 2

    # 構造化された返り値（Codex の --output-schema など）なら、**正規表現ではなく構造で見る**。
    # スキーマが形を保証していても、`out_of_scope` に「無し」と書くべき欄が空文字だったり、
    # verdict が enum 外の値だったりはしうる。JSON なら確実に読めるので、そちらを優先する。
    as_json = None
    try:
        cand = json.loads(text)
        if isinstance(cand, dict):
            as_json = cand
    except Exception:
        pass

    if as_json is not None:
        missing = []
        for k, pat, why in checks:
            v = as_json.get(k)
            if k == "verdict":
                ok = isinstance(v, str) and re.fullmatch(pat.replace(r"\b", ""), v.strip(), re.I)
            else:
                ok = bool(str(v).strip()) if not isinstance(v, (list, dict)) else bool(v) or v == []
            if not ok:
                missing.append((k, why + "（構造化された返り値の該当欄が空 / 値が不正）"))
        # スキーマが required にしていても、値が空文字なら埋まっていない
        for k in ("why", "evidence"):
            v = str(as_json.get(k) or "").strip()
            if k in dict((c[0], 1) for c in checks) and len(v) < 20 and (k, ) not in [(m[0],) for m in missing]:
                missing.append((k, "構造化された返り値の該当欄が短すぎる（20文字未満）"))
        if role == "skeptic":
            mutations = as_json.get("mutations")
            if not isinstance(mutations, list):
                missing.append(("mutations", "mutations が array ではない / 欠落している"))
                mutations = []
            for index, mutation in enumerate(mutations):
                if not isinstance(mutation, dict):
                    missing.append(("mutations", f"mutation[{index}] が object ではない"))
                    continue
                if mutation.get("applied") is not True:
                    missing.append(("mutations", f"mutation[{index}] の適用成立が確認されていない"))
                post = mutation.get("postcondition")
                if not isinstance(post, str) or len(post.strip()) < 10:
                    missing.append(("mutations", f"mutation[{index}] に適用後状態の実測が無い"))
                restored = mutation.get("restore_postcondition")
                if not isinstance(restored, str) or len(restored.strip()) < 10:
                    missing.append(("mutations", f"mutation[{index}] に復元後状態の実測が無い"))
    else:
        missing = [(k, why) for k, pat, why in checks
                   if not re.search(pat, text, re.I | re.M)]
        if role == "skeptic":
            # Claude's print mode cannot enforce --output-schema.  Free prose cannot prove an
            # empty list: a decoy `mutations: []` line may coexist with mutation claims elsewhere.
            # Require the structured contract for every skeptic report.  Static proofs represent
            # the empty list in JSON, which keeps both harness paths on the same intake boundary.
            missing.append(("mutations", "skeptic 報告は常に構造化 JSON が必要。"
                            "静的判定も `\"mutations\": []` を含む JSON で返す"))
    truncated = [p for p in _TRUNCATED if re.search(p, text.strip(), re.I | re.M)]

    print(f"— intake #{a.issue} ({role}) — {len(text)} 文字")
    if not missing:
        print(f"  ✓ 必須要素は揃っている（{', '.join(k for k, _, _ in checks)}）")
        if truncated:
            print(f"  · 途中で切れたように読める語があるが、必須要素は揃っているので"
                  f"完走とみなす（{truncated[0]}）")
        return 0

    print(f"  ✗ **報告が不完全 — 再開させること。**", file=sys.stderr)
    for k, why in missing:
        print(f"      {k}: {why}", file=sys.stderr)
    if truncated:
        print(f"    作業の途中で turn が終わった可能性が高い"
              f"（「{text.strip()[-60:]}」で終わっている）。", file=sys.stderr)
    print(f"    SendMessage で続きを促すこと。**この報告を判定として読まないこと** — "
          f"実地では「Now the key attack:」の1文だけが返り、status は completed だった。\n"
          f"    途中の1文を verdict として読めば、確かめていないものを admit する。\n"
          f"    [intake] INCOMPLETE issue={a.issue} role={role} "
          f"missing={','.join(k for k, _ in missing)} exit=10",
          file=sys.stderr)
    # 最後の1行は**機械が拾える形**にしてある。`| tail` や `| grep` を通すとシェルの終了コードは
    # 最後のコマンドのものになり、この 10 は消える（実地でそう観測された — 実装は 10 を返して
    # いたが、観測経路が 0 を見せた）。パイプで読む経路でも判定できるように、
    # `INCOMPLETE` を出力に置く。
    return 10


def cmd_rework(a):
    """reject / refuted を受けて rework を発注したことを記録する。

    **専用コマンドが無かったことが記録漏れの一因である。** 運用で reject/refuted の多くに対し
    `rework_requested` が記録されていなかった（4回 reject されて記録0件の Issue もあった）。監督は
    `ledger.py append --class rework_requested --payload '{...}'` を手で組む必要があり、
    しかも発注は「判定を受け取る → 検証 → decide → **発注** → 記録」の順で、発注した subagent の
    通知が来ると記録が流れる。

    副作用として `show` の rework 警告（0.26.0）が沈黙していた — 台帳に材料が無いので閾値に
    届かない。**道具の誤検出ではなく、監督が材料を入れていなかった。**
    """
    payload = {"deliverable": str(a.issue), "issue": a.issue,
               "verdict": "rework", "reason": a.reason,
               "from_verdict": a.after, "to_role": a.to or ""}
    rc = _execute([
        # GitHub を先に作業可能な状態へ戻す。ここが失敗したら台帳へ rework を記録しない —
        # CLOSED/COMPLETED のまま ledger だけ次周へ進む分岐が実地で起きた。
        (f"stage ready / reopen → #{a.issue}",
         lambda: _gh_sync("stage", "--issue", str(a.issue), "--stage", "ready")),
        (f"rework_requested #{a.issue}（{a.after} を受けて）",
         lambda: _ledger("append", "--actor", a.by, "--class", "rework_requested",
                         "--natural-key", f"rework-{a.issue}-{a.round}",
                         "--payload", json.dumps(payload, ensure_ascii=False))),
        (f"log → #{a.issue}",
         lambda: _gh_sync("log", "--issue", str(a.issue), "--event", "progress_recorded",
                          "--detail", f"rework を発注（{a.after} を受けて）: {a.reason}",
                          "--command", f"org_cycle.py rework --issue {a.issue} "
                                       f"--after {a.after} --round {a.round}",
                          "--result", a.reason[:2000])),
    ], f"record rework #{a.issue}")
    if rc == 0:
        print(f"\n  Issue は OPEN / ready に戻り、`show --issue {a.issue}` の rework 警告も"
              f"正しく数えられる（台帳に材料が入っていないと、閾値に届かず沈黙する）。")
    return rc


def cmd_record(a):
    """2: 済んだ判定を遡って台帳に記録する。

    統合の判定がどこにも残らないことがある（`integration_admitted` が0件）。しかも「マージ後の
    10件失敗のうち8件は worktree 走査の偽陽性で、の欠陥はゼロ」という切り分けの判断が
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
