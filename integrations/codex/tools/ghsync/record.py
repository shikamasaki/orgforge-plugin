"""記録 — 作業ログと判断の記録。

**Issue と台帳の両方に1コマンドで書く。** 人が2回打つ構造は片側落ちを生む
（実地で3回起きた）。順序は台帳が先 — 統制が拒否するなら、外から見える記録を
作る前に止める。`--why` の空・言い換え・水増しは拒否する。"""

import hashlib
import json
import os
import re
import subprocess
import sys

from ._core import (
    HERE,
    _already_logged,
    _stable_key,
    gh,
)


# マイルストーン: ここで「何をしたか」が残らないと、後から再構成する手段が無くなる。
# 途中経過（progress_recorded）は軽く刻めてよいが、サイクルの節目は監査点なので実出力を要求する。
_LOG_MILESTONES = ("cycle_started", "cycle_completed", "phase_admitted", "integration_admitted",
                   "result_deployed", "handback_opened")


def _log_defect(a):
    """作業ログが再構成可能かを検査する。None なら合格。

    `decide` は --why の空・言い換え・水増しを拒否するのに、`log` は --detail を一切検査して
    いなかった。結果は実測に出ていて、同じ Issue の中で判定は3,506〜5,894字、作業ログは
    276〜473字。**検査のある側だけが厚くなった。** 散文の指示を守るのは人だが、必須引数を
    守るのはツールなので、同じ強制を掛ける。
    """
    if a.event not in _LOG_MILESTONES:
        return None
    if not getattr(a, "command", None):
        return ("--command が要る（マイルストーンの log）。実際に走らせたコマンドを verbatim で。\n"
                "  「テストを流した」ではなく `npm test` のように、他人が再実行できる形で書くこと。")
    if not getattr(a, "result", None):
        return ("--result が要る（マイルストーンの log）。そのコマンドが返した**実出力**を、\n"
                "  失敗も含めて。成功だけの記録は作り話であり、失敗した試行こそ最も情報量が高い。")
    res = str(a.result)
    if len(res.encode("utf-8")) < 24:
        return ("--result が短すぎて実出力とは言えない。"
                "「通った」ではなく、返ってきたものを貼ること。")
    words = re.findall(r"[^\W\d_]+", res.lower(), flags=re.UNICODE)
    filler = {"ok", "okay", "done", "fine", "good", "green", "pass", "passed", "passes",
              "success", "succeeded", "yes", "worked", "works", "完了", "成功"}
    if words and not [w for w in words if w not in filler]:
        return ("--result が「通った」の言い換えでしかない。実出力（テスト件数、エラー、"
                "差分など）を貼ること。")
    return None


def _append_progress_receipt(a):
    """Issue に書いた作業ログの受領証を台帳にも残す。

    `log` は Issue にコメントするだけで台帳に何も書いていなかった。結果、実地では Issue に
    7回の作業記録があるのに `progress_recorded` は **0件**。これは ある Issue の反証記録 で
    塞いだのと同型（二重記録の片側が落ちる）で、しかも影響が具体的:

      · work_in_progress ビューは progress_recorded を読むので `/org-resume` が復帰できない
      · board も進捗を見られない
      · 台帳だけ見ると「作業記録を一度も残していない」ことになる

    台帳が SSoT ではない（SSoT は code + ドメインモデル）が、**中断からの復帰と監査は台帳が
    担う**ので、ここが空だと復帰機構が丸ごと動かない。

    失敗しても log 自体は成功させる — コメントは既に投稿済みで、受領証が付かないことを理由に
    「ログに失敗した」と報告すると、実際には残っている記録を人が二重投稿しにいく。
    """
    payload = {"role": getattr(a, "by", None) or "org", "candidate_id": a.event_id or "",
               "phase": a.phase or "", "milestone": a.event,
               "done_so_far": (a.detail or "")[:2000],
               "next_step": getattr(a, "next_step", None) or "",
               "blocked_by": getattr(a, "blocked_by", None) or "",
               "issue": a.issue}
    if getattr(a, "command", None):
        payload["command"] = a.command
    if getattr(a, "result", None):
        payload["result"] = str(a.result)[:4000]
    if getattr(a, "files", None):
        payload["files"] = a.files
    here = HERE
    try:
        # **統制の書き込みは writerd 経由に統一する。** 直接呼ぶと ORG_WRITER_SOCKET 下で
        # exit 4 になり、正規運用が止まる。
        _base = ([sys.executable, os.path.join(here, "writer_client.py"), "append", "--"]
                 if os.environ.get("ORG_WRITER_SOCKET")
                 else [sys.executable, os.path.join(here, "ledger.py"), "append"])
        p = subprocess.run(_base + [
                            "--actor", payload["role"], "--class", "progress_recorded",
                            "--natural-key", f"progress-{a.issue}-{a.event_id or a.event}",
                            "--payload", json.dumps(payload, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=30)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return False, str(e)


def cmd_log(a):
    """Append a WORK-LOG comment to a task Issue on a milestone event (cycle_started, progress_recorded,
    phase_admitted, cycle_completed, …). The ledger stays the SSoT — this comment is its projection onto
    the Issue so the CEO sees progress accrue without opening the ledger.

    With human diff review retired (docs/11 §4f), the Issue is the org's PRIMARY audit surface: what was
    tried, what was run, what came back, what changed course and why. So this command takes the detail
    fields that make a log entry reconstructable by someone who was never in the session — the command
    that was run and its result, the files touched, the next step. Terse logs ("progress recorded") are
    the failure mode; they satisfy the letter of logging while recording nothing recoverable.

    IDEMPOTENT (docs/11 §0): each comment carries a hidden marker `<!-- orgforge:event:<id> -->`. If a
    comment with this event id already exists on the Issue, we no-op — a replayed/retried cycle logs the
    same milestone once, never twice. Pass --event-id (the ledger event's id) to key the dedup; without
    it we fall back to a hash of (event, detail)."""
    # sha256, NOT hash(): Python salts hash() per process (PYTHONHASHSEED), so a CLI marker built from
    # hash() differs on every invocation and the dedup NEVER fires across runs — a retried cycle
    # double-posts while the docstring promises "logs once, never twice".
    defect = _log_defect(a)
    if defect:
        print(f"作業ログが薄い: {defect}\n\n"
              f"docs/11 §3b のバー: **Issue だけを読んだ他人が、何が作られ・何が試され・"
              f"何が捨てられ・何を実行して何が返り・なぜマージされたかを再構成できること**。\n"
              f"`decide` が --why を検査するのと同じ理由でここも検査する — 人間の diff レビューは"
              f"廃止されており、この Issue が唯一の監査面だから。\n"
              f"途中の軽い刻みなら --event progress_recorded を使うこと（検査は掛からない）。",
              file=sys.stderr)
        return 2
    marker_key = a.event_id or _stable_key(a.event, a.detail or "", a.phase or "")
    marker = f"<!-- orgforge:event:{marker_key} -->"
    if _already_logged(a.repo, a.issue, marker):
        print(f"log: event {marker_key} already on issue #{a.issue} — idempotent no-op (docs/11 §0).")
        return 0
    # the visible line: a compact, human-readable milestone. detail is optional free text.
    line = f"**{a.event}**"
    if a.phase:
        line += f" · phase: `{a.phase}`"
    if a.detail:
        line += f" — {a.detail}"
    parts = [line]
    # the reconstructable detail: what was actually run, what came back, what moved.
    if getattr(a, "command", None):
        result = getattr(a, "result", None)
        parts.append(f"\n**Ran:**\n```\n{a.command}\n```")
        if result:
            parts.append(f"**Result:**\n```\n{result}\n```")
    for label, val in (("Files", getattr(a, "files", None)),
                       ("Next step", getattr(a, "next_step", None)),
                       ("Blocked by", getattr(a, "blocked_by", None))):
        if val:
            parts.append(f"**{label}:** {val}")
    body = "\n".join(parts) + f"\n\n{marker}"
    code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", body])
    if code != 0:
        print(f"gh error posting work-log comment: {out}", file=sys.stderr)
        return 2
    ok, msg = _append_progress_receipt(a)
    if ok:
        print(f"logged {a.event} to issue #{a.issue}（台帳にも progress_recorded を記録）。")
    else:
        print(f"logged {a.event} to issue #{a.issue}.")
        print(f"注意: 台帳の受領証を書けなかった（{msg.strip()[:120]}）。"
              f"Issue には残っているが、`/org-resume` はこの進捗を見られない。", file=sys.stderr)
    return 0


# the judgment classes that must land on the Issue with their reasoning (docs/11 §4f)


# the judgment classes that must land on the Issue with their reasoning (docs/11 §4f)
DECISIONS = ("admission_decided", "refutation_attempted", "phase_admitted", "conformance_reviewed",
             "integration_admitted", "deploy_decided", "rework_requested", "scope_decided",
             "design_decided", "tradeoff_decided")


def _reasoning_digest(*fields):
    """A stable digest over a judgment's reasoning fields — the tamper-evidence anchor (docs/11 §4f.1).

    Normalizes whitespace so a cosmetic reflow does not read as tampering, while any change to the
    substance (a dropped `--risk`, a rewritten `--why`) changes the digest."""
    import hashlib
    norm = "\x1f".join(re.sub(r"\s+", " ", (f or "").strip()) for f in fields)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]



# 「確かめていないことを、確かめたかのように述べる」— この org が実地で8回検出した失敗様式が、
# **検出する側（監督）**に現れた。運用で観測した形:
#   maker の報告 : 「src/db/client.ts は**このブランチにまだ存在せず** feat/issue-11 側にありました」
#   監督の要約   : 「maker は推測せず src/db/client.ts の loadEnv() を読んで変数を確定させた」
#   落ちた条件   : 「**このブランチには無い**」
# maker は正直に条件を書いていた。**監督が要約で落とした**。その要約が gate への指示にも流れ、
# gate は「そのファイルは存在しない」を reject 事由にした。
#
# 台帳は理由のハッシュしか持たないので、台帳側では書き分けを検査できない。検査は
# **decide の入口**に置く（Issue コメントに落ちる前に見る）。
# 条件節の**種類**ごとに同義の表現を束ねる。語尾だけ違う表現（「存在せず」と「存在しない」）を
# 別物として扱うと、条件を正しく運んでいるのに警告が出る（実装当初そうなった）。
_HEDGE_GROUPS = {
    "不在": ("には無い", "にはない", "存在せず", "存在しない", "存在しま", "無かった", "なかった",
             "not present", "does not exist", "missing"),
    "未測定": ("未測定", "測っていない", "測定していない", "not measured", "unmeasured"),
    "未検証": ("確認していない", "確かめていない", "未検証", "未実行", "検証していない",
               "unverified", "not verified", "not run"),
    "推測": ("のはず", "だと思われ", "推測", "かもしれ", "可能性がある", "assumed", "presumably",
             "probably", "likely"),
    "条件付き": ("の場合は", "であれば", "のときは", "if ", "when "),
    "未完了": ("予定", "できていない", "していません", "まだ", "todo", "pending"),
}
# 「実際に走らせた」痕跡。**コマンド名を書けば通る**形式化を招くのは承知の上で、
# 何も無い状態より遥かに良い（実地で cycle_completed の薄い --result を拒否したとき、
# 監督は実際に測り直した。拒否が形式的な壁ではなく行動を変えた実例である）。
# 完全には塞げない — それはこの検査の限界として記録する（docs/11）。
_RAN = ("npm ", "npx ", "git ", "psql", "python3", "node ", "pytest", "cargo ", "go test",
        "supabase", "curl ", "exit=", "exit code", "passed", "failed", "$ ", "→", "->")



def _prior_admission(issue):
    """その Issue に gate の `admit` があるか。(verdict, actor) を返す（無ければ (None, None)）。

    台帳は `phase_started` に対して既に同じ検査をしている（design が admit されていなければ
    implement を拒否する）。**統合の側にも同じ形を置く** — `integration_admitted = pass` が
    gate の admit なしに通ると、maker の報告の質が admit の代わりに使われる。運用では、質の
    高い報告を受けて `git merge` し、そのあと `integration_admitted` を記録して通っていた。
    """
    try:
        sys.path.insert(0, HERE)          # HERE = tools/（_core に集約。0.22.1 の教訓）
        from discover import ledger_root
        from ledger import corrected_seqs
        root = ledger_root()
    except Exception:
        return None, None
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return None, None
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = corrected_seqs(evs)
    want = str(issue).lstrip("#")
    hit = (None, None)
    for e in evs:
        if e.get("class") != "admission_decided" or e.get("seq") in voided:
            continue
        pl = e.get("payload", {}) or {}
        ids = {str(pl.get(k, "")).lstrip("#") for k in ("issue", "deliverable") if pl.get(k)}
        if want in ids:
            hit = (pl.get("verdict"), e.get("actor"))
    return hit


def _claim_verify_defect(a):
    """監督の記録が「誰が確かめたか」を書き分けているかを見る。

    返り値: 警告文のリスト（**拒否はしない** — 1件を除く）。判断は監督の仕事だが、
    条件節を落としたことに**気づける材料**は要る。
    """
    warns = []
    claimed = (getattr(a, "claimed", None) or "").strip()
    verified = (getattr(a, "verified", None) or "").strip()
    if not claimed and not verified:
        return warns          # 旧来の --why / --evidence だけの呼び出しは通す（後方互換）

    # (a) --verified に実行の痕跡が無い ＝ 「確かめた」と書いただけ
    if verified and not any(k in verified for k in _RAN):
        warns.append(
            "--verified に**実際に走らせた痕跡**（コマンド・出力・exit）が無い。"
            "「確認した」と書くだけでは、確かめたことにならない — この org が8回検出した"
            "失敗様式そのものである。走らせていないなら --claimed 側に書くこと。")

    # (b) --claimed に条件節があるのに --verified が触れていない ＝ 要約で条件を落とした
    # 種類ごとに見る: claimed に「不在」の条件があるなら、verified も「不在」に触れていればよい
    untouched = []
    for kind, words in _HEDGE_GROUPS.items():
        if any(w in claimed for w in words) and not any(w in verified for w in words):
            untouched.append(kind)
    if untouched:
        warns.append(
            f"--claimed に条件節がある（{', '.join(untouched[:3])}）のに、--verified が"
            f"触れていない。**要約で条件が落ちると、それが下流の判定に流れる** — 実地では"
            f"「このブランチには無い」が消えて gate の reject 事由になった。"
            f"条件をそのまま運ぶか、自分で確かめて結果を書くこと。")
    return warns


def _reasoning_defect(why, verdict, event):
    """Return a defect phrase if `why` is not actual reasoning, else None.

    A pure length bound fails in both directions and must not be used alone:
      · it PASSES `"admit admit admit admit admit"` — the literal restatement it exists to reject;
      · it REJECTS `「全テスト通過を確認。cap近傍の並行joinは未検証」` — substantive reasoning that is
        short in codepoints because Japanese carries ~2-3x the information per character, and the org's
        default output_language is ja. Measuring bytes rather than codepoints fixes the CJK half.
    So: require some substance by BYTE length, then reject text that is only verdict/filler tokens."""
    if not why:
        return "is required — a verdict with no reasoning is a stamp."
    if len(why.encode("utf-8")) < 24:
        return "is too short to be an account of the decision."
    # strip punctuation, then see whether anything remains beyond verdict words and filler
    words = re.findall(r"[^\W\d_]+", why.lower(), flags=re.UNICODE)
    if not words:
        return "contains no words — punctuation or padding is not reasoning."
    filler = {verdict.lower(), event.lower(), "the", "is", "it", "this", "was", "a", "an", "and",
              "ok", "okay", "fine", "good", "looks", "lgtm", "pass", "passed", "passes", "green",
              "admit", "admitted", "approve", "approved", "yes", "no", "all", "to", "me", "verdict"}
    substantive = [w for w in words if w not in filler]
    if not substantive:
        return ("only restates the verdict — that is exactly the rubber stamp this check exists to "
                "reject.")
    if len(set(words)) <= 2 and len(words) >= 4:
        return "is one phrase repeated to clear a length bar, not reasoning."
    # keyboard-mash padding: almost no distinct characters across the whole text
    if len(set(why.replace(" ", ""))) <= 3:
        return "is padding, not an account of the decision."
    return None


def _org_lineage():
    """constitution の `enforcement.judges.lineage` を読む。既定は `same-harness`。

    **設定を読めないときは止める（fail-closed）。** 0.32.0 は例外を握りつぶして
    `same-harness` を返していた — cross-harness を宣言した org で YAML が壊れていたり
    PyYAML が無いと、**強い安全モードが黙って通常モードに落ちる**。それは
    「信号が壊れているので、壊れていることが分からない」形そのものである。

    宣言されていない org（constitution に judges が無い）は既定で回る。読めなかったのか
    宣言が無いのかを区別するため、**ファイルの存在と解析の成否を分けて扱う**。
    """
    env = os.environ.get("ORG_JUDGE_LINEAGE")
    if env:
        return env.strip()
    try:
        sys.path.insert(0, HERE)
        from discover import constitution
        path = constitution()
    except Exception as e:
        raise SystemExit(f"constitution の場所を解決できない: {e}\n"
                         "  judges.lineage を読めない状態で判定を記録すると、cross-harness を"
                         "宣言した org が黙って同一血統で通る。\n"
                         "  org のルートで実行しているか確認すること。")
    if not path or not os.path.isfile(path):
        return "same-harness"          # org が constitution を持たない = 宣言が無い
    try:
        import yaml
    except Exception:
        raise SystemExit("PyYAML が無いので constitution を読めない。\n"
                         "  judges.lineage が読めないまま判定を記録することは許さない — "
                         "cross-harness の宣言が黙って消える。\n"
                         "    python3 -m pip install pyyaml")
    try:
        with open(path, encoding="utf-8") as f:
            c = yaml.safe_load(f) or {}
    except Exception as e:
        raise SystemExit(f"constitution.yaml を解析できない: {e}\n"
                         f"  ファイル: {path}\n"
                         "  **設定を読めないなら止める。** 読めない理由が judges.lineage の行に"
                         "あるかどうかは、読めない時点では分からない。")
    if not isinstance(c, dict):
        raise SystemExit(f"constitution.yaml が map ではない（{type(c).__name__}）: {path}")
    j = ((c.get("enforcement") or {}).get("judges") or {})
    declared = str(j.get("lineage") or "same-harness").strip()
    sys.path.insert(0, HERE)
    from harness import effective_lineage
    return effective_lineage(declared)


def _has_lineage_verdict(issue, event, lineage):
    """その Issue の同じ event に、指定した血統の **通した** 判定が台帳にあるか。

    否（reject/refuted）は数えない — 探しているのは一致なので、片方が否ならそもそも
    admit を記録する場面ではない。訂正済み（`corrected_seqs`）は数えない。
    """
    ok = {"admission_decided": ("admit",), "refutation_attempted": ("survives",)}.get(event, ())
    try:
        sys.path.insert(0, HERE)
        from discover import ledger_root
        from ledger import corrected_seqs
        root = ledger_root()
    except Exception:
        return False
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return False
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = corrected_seqs(evs)
    want = str(issue).lstrip("#")
    for e in evs:
        if e.get("class") != event or e.get("seq") in voided:
            continue
        pl = e.get("payload", {}) or {}
        ids = {str(pl.get(k, "")).lstrip("#") for k in ("issue", "deliverable") if pl.get(k)}
        if want in ids and pl.get("lineage") == lineage and pl.get("verdict") in ok:
            return True
    return False


def cmd_provisional(a):
    """ある血統の judge の判定を **暫定** として記録し、2血統が一致したら admission を生成する。

    ## なぜ二段にするのか

    0.32.0 は `admission_decided = admit` を直接記録させ、「もう一方の血統の判定が台帳に無ければ
    拒否」とした。それでは **空の台帳からどちらの順序でも記録できず、admit が永久に作れない**
    （実測: 両方向 exit=4、台帳は空のまま）。片側の拒否だけを確かめ、通せることを確かめなかった
    ためである。

    正しい形は、**単独では権威を持たない判定**を先に置くことである:

      1. `verdict_provisional`  各血統の judge の判定。順序は問わない
      2. `admission_decided`    2件が一致したときに **道具が組み立てる**

    段2で verdict を作るのは配管であって判断ではない — 一致という事実の関数である。不一致なら
    道具は admit を作れないので、監督が都合のいい方を採る余地も消える。

    ## この道具が admit を「作る」ことについて

    `verify` が判定を作らないのと矛盾しない。ここで決めているのは *一致しているか* だけで、
    verdict / why / evidence はすべて judge が書いたものをそのまま持ち越す。**道具が新しい判断を
    足す箇所は無い。**
    """
    # **設定を読めないなら止める。** provisional は cross-harness を前提とするコマンドなので、
    # 血統設定が読めない状態で判定を積むと、あとで一致を数える側が別の前提で動きうる。
    # `_org_lineage()` は読めなければ SystemExit する（fail-closed）。
    lineage_mode = _org_lineage()
    if lineage_mode != "cross-harness":
        print(f"provisional は judges.lineage = cross-harness の org のためのものだが、"
              f"この org は {lineage_mode!r} である。\n"
              f"  同一血統だけで回すなら、判定は decide でそのまま記録すればよい "
              f"（一致を数える相手が居ない）。\n"
              f"  2血統で回すなら constitution の enforcement.judges.lineage を "
              f"cross-harness にすること。", file=sys.stderr)
        return 2
    ok = {"gate": ("admit", "reject", "park"), "skeptic": ("survives", "refuted")}
    if a.role not in ok:
        print(f"provisional: --role は gate | skeptic（got {a.role!r}）", file=sys.stderr)
        return 2
    if a.verdict not in ok[a.role]:
        print(f"provisional: {a.role} の verdict は {ok[a.role]}（got {a.verdict!r}）",
              file=sys.stderr)
        return 2
    why = (a.why or "").strip()
    if len(why) < 40:
        print(f"provisional: --why が薄い（{len(why)} 文字）。verdict の言い換えではなく、"
              f"何を見て、どこで決まったかを書くこと。", file=sys.stderr)
        return 2
    pass_v = {"gate": "admit", "skeptic": "survives"}[a.role]
    if a.verdict == pass_v and not (a.evidence or "").strip():
        print(f"provisional: {pass_v} には --evidence が必要。"
              f"何も参照していない通過は、判定ではなく判子である。", file=sys.stderr)
        return 2

    event = {"gate": "admission_decided", "skeptic": "refutation_attempted"}[a.role]
    digest = _reasoning_digest(why, a.evidence, a.alternatives, a.standard, a.risk)

    # ── identity（H1）─────────────────────────────────────────────────────
    # **`decision_by` は検証済み receipt からのみ設定する。** CLI で申告できるなら、誰の判断
    # とでも言える。receipt が無ければ `claimed` のままにし、**独立性の強制には使わない**。
    # `recorded_by` は観測する（代理記録を許す — judge が直接書く必要は無い）。
    sys.path.insert(0, HERE)
    from identity import (verify_receipt, observed_recorder, PROTOCOL_VERSION)
    decision_by, ident = None, {"identity_assurance": "claimed"}
    if getattr(a, "receipt", None):
        try:
            rc = json.loads(open(a.receipt, encoding="utf-8").read()) \
                if os.path.isfile(a.receipt) else json.loads(a.receipt)
        except Exception as e:
            print(f"provisional: --receipt を読めない（{e}）。", file=sys.stderr)
            return 2
        expect = {"review_subject_id": a.subject, "issue": a.issue, "role": a.role,
                  "lineage": a.lineage, "verdict": a.verdict,
                  "reasoning_sha256": digest}
        decision_by, ident, rerr = verify_receipt(rc, expect)
        if rerr:
            print(f"provisional: receipt を検証できないので判定を記録しない — {rerr}\n"
                  f"  **判断の主体を確かめられないなら、その判断として記録しない。**\n"
                  f"  receipt 無しで記録するなら --receipt を外すこと（その場合 decision_by は"
                  f"`claimed` になり、独立性の強制には使えない）。", file=sys.stderr)
            return 4
    recorded_by, rec_assurance = observed_recorder()
    payload = {"issue": a.issue, "deliverable": str(a.issue), "role": a.role,
               "lineage": a.lineage, "verdict": a.verdict, "for_event": event,
               "review_subject_id": a.subject, "reasoning_sha256": digest,
               # **3つの主体を分ける（H1）。** decision_by は receipt からのみ。
               # recorded_by は観測（代理記録を許す）。committed_by は writer が付ける。
               "decision_by": decision_by or (a.by or a.role),
               "recorded_by": recorded_by,
               "identity_assurance": ident.get("identity_assurance", "claimed"),
               "recorder_assurance": rec_assurance,
               "workload_isolation": ident.get("workload_isolation", "none"),
               **({"signer_id": ident["signer_id"], "key_id": ident["key_id"]}
                  if ident.get("signer_id") else {}),
               # 条件7+8: digest の照合対象を永続化する。台帳に散文は置かないが、
               # **どこを見れば原文があるか**は残す（Issue コメントの marker）。
               "reasoning_ref": f"issue:{a.issue}#provisional-{a.lineage}-{digest[:12]}"}
    if getattr(a, "phase", None):
        payload["phase"] = a.phase
    if getattr(a, "risk", None):
        payload["risk_accepted"] = True

    # **同じ血統の二度目の扱い。** 0.32.1 は verdict が違うときだけ拒否したので、同じ verdict で
    # 理由を変えた別の provisional を積めた（監査指摘）。どれと一致したのかが運用次第になる。
    #   - 完全に同じ再実行（同 subject・同 verdict・同 digest）→ no-op
    #   - それ以外の再判定 → 拒否。訂正は correction 経由
    prior = _provisional_for(a.issue, event, a.lineage)
    if prior:
        same = (prior["verdict"] == a.verdict and prior.get("subject") == a.subject
                and prior.get("digest") == digest)
        if same:
            print(f"provisional: #{a.issue} の {a.lineage} の判定は既に同一内容で "
                  f"seq={prior['seq']} にある（冪等 no-op）。")
            return 0
        what = []
        if prior["verdict"] != a.verdict:
            what.append(f"verdict {prior['verdict']!r} → {a.verdict!r}")
        if prior.get("subject") != a.subject:
            what.append(f"subject {str(prior.get('subject'))[:12]}… → {a.subject[:12]}…")
        if prior.get("digest") != digest:
            what.append("why/evidence が違う")
        print(f"provisional: #{a.issue} の {a.lineage} には既に判定がある"
              f"（seq={prior['seq']}）。変わっているのは: {', '.join(what)}\n"
              f"  **同じ血統が判定を積み替えて一致を作れてはいけない。**\n"
              f"  先の判定を無効化してから入れ直すこと（append-only なので消せない）:\n"
              f'    python3 "{os.path.join(HERE, "ledger.py")}" append --class correction '
              f"--actor <あなたの役割> \\\n"
              f'      --payload \'{{"corrects": [{prior["seq"]}], "kind": "superseded", '
              f'"corrected_by": "<あなたの役割>", "reason": "<なぜ差し替えるのか>"}}\'\n'
              f"  kind は probe | mistake | backfill | superseded のいずれか"
              f"（対象が実判定なら superseded、試験で書いたものなら probe）。",
              file=sys.stderr)
        return 4

    # 冪等キーは **判定の同一性**で作る。`_reasoning_digest` は散文だけを束ねる（tamper
    # evidence の対象は散文なので正しい）ため、同じ理由で verdict を変えた判定が同一キーに
    # なってしまう。verdict と subject を含めて、差し替えが no-op に落ちないようにする。
    # **receipt そのものを渡す。** 環境変数の「検証済み」印は使わない — caller が立てられる
    # ものは証拠にならない（実測: ORG_IDENTITY_VERIFIED=1 を足すだけで偽装が通った）。
    # 書き手（ledger.py / writerd）が自分で検証し、identity fields を生成する。
    for k in ("decision_by", "recorded_by", "identity_assurance", "recorder_assurance",
              "workload_isolation", "signer_id", "key_id"):
        payload.pop(k, None)
    rc = _ledger_append(a.by or a.role, "verdict_provisional", payload,
                        f"verdict_provisional-{a.issue}-{a.lineage}-{a.verdict}"
                        f"-{a.subject[:8]}-{digest[:12]}",
                        receipt=getattr(a, "receipt", None))
    if rc != 0:
        return 4
    print(f"recorded provisional {a.role}={a.verdict} ({a.lineage}) on #{a.issue}.")
    # **条件8: digest の照合対象を永続化する。** 台帳は reasoning_sha256 しか持たないので、
    # 散文を Issue に置かないと「後で照合する対象」が存在しない。台帳を先に通してから投影する
    # （拒否されるなら外に見える記録を作らない — decide と同じ順序）。
    if not getattr(a, "repo", None):
        print(f"  注意: GitHub repo が無いので Issue に投影していない。\n"
              f"  **reasoning_sha256 ={digest[:12]}… の照合対象がどこにも残らない** — "
              f"台帳は digest しか持たないので、後から散文と突き合わせられない。",
              file=sys.stderr)
    else:
        marker = f"<!-- orgforge:provisional:{a.lineage}:{digest[:12]} -->"
        parts = [
            f"### 🧪 verdict_provisional — `{a.verdict}` ({a.lineage})",
            f"**Judged by:** `{a.role}` / lineage `{a.lineage}`",
            f"**単独では権威を持たない。** 2血統が同じ対象で一致したときにだけ "
            f"{event} が生成される。",
            f"\n**review_subject_id:** `{a.subject}`",
            f"\n**Why (the reasoning):**\n{why}",
        ]
        if (a.evidence or "").strip():
            parts.append(f"\n**Evidence consulted:**\n{a.evidence}")
        if (a.alternatives or "").strip():
            parts.append(f"\n**Alternatives considered:**\n{a.alternatives}")
        if (a.standard or "").strip():
            parts.append(f"\n**Standard applied:** {a.standard}")
        if (a.risk or "").strip():
            parts.append(f"\n**Known risk accepted:** {a.risk}")
        parts.append(f"\n`reasoning_sha256: {digest}` — 台帳の receipt が同じ digest を持つ。"
                     f"再ハッシュが一致しなければ、この記録は書き換えられている。")
        parts.append(f"\n{marker}")
        code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo,
                        "--body", "\n".join(parts)])
        if code != 0:
            print(f"  注意: 台帳には入ったが、Issue に投影できなかった: {out[:300]}\n"
                  f"  **reasoning_sha256 の照合対象が残っていない。** 同じ引数で再実行すれば、"
                  f"台帳は冪等 no-op になり Issue だけが埋まる。", file=sys.stderr)

    # **通過でない判定は、そもそも一致を作る話ではない。** park / reject / refuted は片方でも
    # 出れば否として扱われる（厳しい側に倒す）ので、もう一方を待つ必要も subject を比べる必要も
    # ない。ここを分けないと park に対して「別の対象を見ている」という無関係な警告が出る（実測）。
    other = "cross-harness" if a.lineage == "same-harness" else "same-harness"
    peer = _provisional_for(a.issue, event, other)

    # 否（park / reject / refuted）は単独で成立する — 相手を待たず、subject も比べない。
    # ただし **相手が通過していたなら、それは食い違いである**。早期に返して記録を飛ばすと、
    # 「admit の後から reject が来た」経路で judges_disagreed が残らない（実測で捕まえた）。
    if a.verdict != pass_v:
        if peer and peer["verdict"] == pass_v:
            print(f"\n  ★ 2血統が食い違った — {other}={peer['verdict']}"
                  f"（seq={peer['seq']}）に対して {a.lineage}={a.verdict}。\n"
                  f"  **厳しい側に倒す。** admission は生成しない（既にあるなら訂正が必要）。",
                  file=sys.stderr)
            _ledger_append(a.by or a.role, "judges_disagreed",
                           {"issue": a.issue, "role": a.role, "for_event": event,
                            a.lineage.replace("-", "_"): a.verdict,
                            other.replace("-", "_"): peer["verdict"]},
                           f"judges_disagreed-{a.issue}-{event}-{digest[:12]}")
            ret = 5
        else:
            print(f"\n  {a.verdict} は通過ではないので、admission は生成しない"
                  f"（片方でも否なら否）。")
            ret = 0
        print(f"  否として確定させるなら decide で記録すること:\n"
              f'    python3 "{os.path.join(HERE, "github_sync.py")}" decide --issue {a.issue} '
              f"--event {event} --verdict {a.verdict} --by {a.role} --why \"…\"",
              file=sys.stderr if ret else sys.stdout)
        return ret
    if not peer:
        print(f"\n  もう一方の血統（{other}）の判定はまだ無い。**admission はまだ生成されない。**\n"
              f"  順序は問わない — こちらを先に置いても構わない。\n"
              f'    python3 "{os.path.join(HERE, "org_cycle.py")}" verify '
              f"--issue {a.issue} --role {a.role}")
        return 0

    # 2件揃った。**一致だけが admission を生成する。**
    # **subject が違う2判定は一致させない。** 別の revision を見た2つの通過は一致ではない
    # （監査実証: revision A の admit と revision B の admit で joint が生成された）。
    if peer.get("subject") != a.subject:
        print(f"\n  ★ 2血統が **別の対象** を見ている — admission は生成しない。\n"
              f"    {a.lineage:14} subject = {a.subject}\n"
              f"    {other:14} subject = {peer.get('subject') or '(なし)'}\n"
              f"  base_sha / reviewed_tree_sha / 受け入れ基準のいずれかが違う。"
              f"**同じものを見ていない2つの通過は、一致ではない。**\n"
              f"  同じ木で両方を回し直すこと:\n"
              f'    python3 "{os.path.join(HERE, "org_cycle.py")}" verify '
              f"--issue {a.issue} --role {a.role}"
              + (f" --phase {a.phase}" if getattr(a, "phase", None) else "")
              + (f"\n  （0.32.1 以前の provisional には subject が無い。"
                 f"その判定は一致に参加できないので、回し直す）"
                 if not peer.get("subject") else ""),
              file=sys.stderr)
        return 6

    if peer["verdict"] != a.verdict:
        print(f"\n  ★ 2血統が食い違った — {a.lineage}={a.verdict} / "
              f"{other}={peer['verdict']}（seq={peer['seq']}）。\n"
              f"  **admission は生成しない。** 片方でも否なら否である。\n"
              f"  食い違いそのものを記録すること — 異常ではなく、血統を分けた目的である:",
              file=sys.stderr)
        _ledger_append(a.by or a.role, "judges_disagreed",
                       {"issue": a.issue, "role": a.role, "for_event": event,
                        a.lineage.replace("-", "_"): a.verdict,
                        other.replace("-", "_"): peer["verdict"]},
                       f"judges_disagreed-{a.issue}-{event}-{digest[:12]}")
        bad = "reject" if a.role == "gate" else "refuted"
        print(f"  否として扱うなら、そのまま記録してよい（否は一致を要求しない）:\n"
              f'    python3 "{os.path.join(HERE, "github_sync.py")}" decide --issue {a.issue} '
              f"--event {event} --verdict {bad} --by {a.role} --why \"…\"", file=sys.stderr)
        return 5

    # **両方の reasoning を持ち越す。** 0.32.1 は2件目の digest しか載せず、1件目の
    # why/evidence が joint から辿れなかった（監査指摘）。joint の reasoning_sha256 は
    # **2つの digest から決定的に作る** — どちらか一方の digest ではない。
    mine = _provisional_for(a.issue, event, a.lineage)
    pair = {a.lineage: {"seq": mine["seq"], "reasoning_sha256": digest,
                        "reasoning_ref": payload["reasoning_ref"]},
            other: {"seq": peer["seq"], "reasoning_sha256": peer.get("digest"),
                    "reasoning_ref": peer.get("ref")}}
    joint_digest = hashlib.sha256(
        json.dumps({k: v["reasoning_sha256"] for k, v in sorted(pair.items())},
                   sort_keys=True).encode("utf-8")).hexdigest()
    # **joint は writer の専用操作が生成する。** ここで payload を組み立てて generic append に
    # 渡すと、`require_attested_identity` が「receipt が無い」として拒否し、**一致しても
    # admission を作れないデッドロック**になる（joint に judge の receipt は存在しない —
    # 一致は判断ではなく事実の関数だからである）。
    from identity import reviewer_independence
    mine_assurance = {"signer_id": ident.get("signer_id"), "key_id": ident.get("key_id"),
                      "workload_isolation": ident.get("workload_isolation") or "none",
                      "identity_assurance": ident.get("identity_assurance") or "claimed"}
    independence = reviewer_independence(decision_by, mine_assurance, peer.get("assurance"))
    if independence == "same_signer" and mine_assurance.get("signer_id"):
        print(f"\n  ★ 2血統が一致したが、**同じ signer が両方に署名している**"
              f"（{mine_assurance['signer_id']}）。\n"
              f"  署名されていても、同じ鍵が両方の血統を作れるなら **独立レビューではない**。\n"
              f"  **独立性の証拠として数えないこと。**", file=sys.stderr)

    args = ["--issue", str(a.issue), "--event", event]
    if os.environ.get("ORG_WRITER_SOCKET"):
        cmd = [sys.executable, os.path.join(HERE, "writer_client.py"),
               "derive-admission", "--", *args]
    else:
        cmd = [sys.executable, os.path.join(HERE, "ledger.py"), "derive-admission", *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        print(f"admission を生成できなかった: {e}", file=sys.stderr)
        return 4
    if r.returncode != 0:
        print(f"admission を生成できなかった:\n"
              f"  {((r.stdout or '') + (r.stderr or '')).strip()[:500]}", file=sys.stderr)
        return 4
    print(f"\n  ✓ 2血統が {a.verdict} で一致した — {event} を生成した"
          f"（reviewer_independence={independence}）。\n"
          f"  この admission は **判定ではなく一致の記録** である。"
          f"verdict / why は judge が書いたものをそのまま持ち越している。")
    return 0


def _provisional_for(issue, event, lineage):
    """その Issue・その event・その血統の **有効な** 暫定判定を返す。

    無効化の扱いは `correction` の kind に従う:

      probe / mistake  — 実判定ではない。`corrected_seqs` が既定で除外する
      superseded       — 実判定だが後続に置き換えられた。**ここで除外する** —
                         `corrected_seqs` は superseded を消さない（時系列の解決が扱う領域と
                         して分けられている）ので、置き換えの解決はこの関数の責任である。
                         これを見落とすと、案内した correction を打っても判定を差し替えられない
                         （0.32.1 の実態。append は成功するので効いたように見える）。
      backfill         — 後から書いた実判定。無効ではない
    """
    try:
        sys.path.insert(0, HERE)
        from discover import ledger_root
        from ledger import corrected_seqs
        root = ledger_root()
    except Exception:
        return None
    path = os.path.join(root, "ledger.jsonl") if root else None
    if not path or not os.path.isfile(path):
        return None
    evs = []
    for line in open(path, encoding="utf-8"):
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    voided = set(corrected_seqs(evs)) | set(corrected_seqs(evs, kinds=("superseded",)))
    want, hit = str(issue).lstrip("#"), None
    for e in evs:
        if e.get("class") != "verdict_provisional" or e.get("seq") in voided:
            continue
        pl = e.get("payload") or {}
        if (str(pl.get("issue", "")).lstrip("#") == want
                and pl.get("for_event") == event and pl.get("lineage") == lineage):
            hit = {"verdict": pl.get("verdict"), "seq": e.get("seq"), "actor": e.get("actor"),
                   "subject": pl.get("review_subject_id"),
                   "digest": pl.get("reasoning_sha256"), "ref": pl.get("reasoning_ref"),
                   # identity（H1）— 独立性の判定に使う
                   "decision_by": pl.get("decision_by"),
                   "assurance": {"signer_id": pl.get("signer_id"), "key_id": pl.get("key_id"),
                                 "workload_isolation": pl.get("workload_isolation") or "none",
                                 "identity_assurance": pl.get("identity_assurance") or "claimed"}}
    return hit


def _ledger_append(actor, cls, payload, natural_key, receipt=None):
    """台帳に1件追記する。**失敗を黙って飲まない。**

    **writerd がいる org では RPC 経由にする。** 直接 ledger.py を呼ぶと「writerd 経由でなければ
    書けない」に当たって exit 4 になり、判定の記録が止まる（実測で指摘された）。
    """
    args = ["--actor", actor, "--class", cls, "--natural-key", natural_key,
            "--payload", json.dumps(payload, ensure_ascii=False)]
    if receipt:
        args += ["--receipt", receipt]
    if os.environ.get("ORG_WRITER_SOCKET"):
        cmd = [sys.executable, os.path.join(HERE, "writer_client.py"), "append", "--", *args]
    else:
        cmd = [sys.executable, os.path.join(HERE, "ledger.py"), "append", *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        print(f"台帳に追記できなかった: {e}", file=sys.stderr)
        return 4
    if r.returncode != 0:
        print(f"台帳が {cls} を受け付けなかった:\n"
              f"  {((r.stdout or '') + (r.stderr or '')).strip()[:600]}", file=sys.stderr)
        return 4
    return 0


def cmd_decide(a):
    """Record a JUDGMENT on the task Issue — the verdict AND the reasoning that produced it.

    Human diff review is retired (docs/11 §4f): no person reads the change before it merges. That makes
    the machine's own judgments the only judgments, and an unrecorded judgment is then indistinguishable
    from no judgment at all. A ledger `admission_decided{verdict: admit}` proves a decision HAPPENED and
    is tamper-evident; it does not say what was weighed, what the alternative was, or what evidence was
    consulted — and that is exactly what someone auditing the merge six weeks later needs.

    So every judgment double-writes, the same way a settled convention does (conventions.py): the ledger
    gets the RECEIPT (tamper-evident, machine-queryable), the Issue gets the REASONING (readable, in
    context, next to the work it judged). The Issue is where a decision can actually be inferred later.

    A verdict with an empty or contentless --why is rejected — a bare "admit" is the failure mode this
    command exists to prevent, and accepting it would let the audit trail degrade back into a stamp.
    Admitting also requires --evidence: an admission with nothing consulted IS the stamp."""
    if a.event not in DECISIONS:
        print(f"decide: --event must be a judgment class {DECISIONS}; got {a.event!r}. "
              f"For a progress milestone use `log`.", file=sys.stderr)
        return 2
    why = (a.why or "").strip()
    # integration_admitted は gate の admit を前提とする。**これは拒否する** —
    # 統合の記録が admit なしに残ると、後から見て「通った」と読めてしまう。
    if a.event == "integration_admitted" and a.verdict in ("pass", "admit"):
        verdict, actor = _prior_admission(a.issue)
        if verdict != "admit":
            print(f"integration_admitted を記録できない: #{a.issue} に gate の admit が無い"
                  f"（台帳の最新は {verdict or '記録なし'}）。\n"
                  f"  先に gate を通すこと:\n"
                  f'    python3 "{os.path.join(HERE, "org_cycle.py")}" verify '
                  f"--issue {a.issue} --role gate\n"
                  f"  **maker の報告の質は admit の代わりにならない。** 台帳は phase_started に対して\n"
                  f"  既に同じ検査をしている（design が admit されていなければ implement を拒否）。\n"
                  f"  統合の記録が admit なしに残ると、後から見て「通った」と読めてしまう。",
                  file=sys.stderr)
            return 4

    # cross-harness を宣言した org では、admit/survives は **2血統の一致で生成される** —
    # 直接は記録できない。0.32.0 は「もう一方が台帳に無ければ拒否」としたが、それでは空の
    # 台帳からどちらの順序でも記録できず、admit が永久に作れなかった（実測: 両方向 exit=4）。
    #
    # 正しい形は二段である:
    #   1. `verdict_provisional` — ある血統の judge の判定。**単独では権威を持たない**
    #   2. `admission_decided`   — 2血統が一致したときに **道具が組み立てる**
    #
    # 段2で verdict を作るのは配管であって判断ではない（一致という事実の関数）。不一致なら
    # 道具は admit を作れないので、監督が都合のいい方を採る余地も消える。
    if a.event in ("admission_decided", "refutation_attempted") \
            and a.verdict in ("admit", "survives") and _org_lineage() == "cross-harness":
        _who = "gate" if a.event == "admission_decided" else "skeptic"
        print(f"{a.event} = {a.verdict} は直接記録できない（judges.lineage = cross-harness）。\n"
              f"  この org では admit は **2血統の一致から生成される**もので、"
              f"judge が単独で置けるものではない。\n"
              f"  各血統の判定を暫定として記録すること:\n"
              f'    python3 "{os.path.join(HERE, "github_sync.py")}" provisional '
              f"--issue {a.issue} --role {_who} \\\n"
              f"      --lineage same-harness|cross-harness --verdict {a.verdict} "
              f'--why "…" --evidence "…"\n'
              f"  2件目を入れた時点で、一致していれば {a.event} が自動で生成される。\n"
              f"  **否（{'reject' if _who == 'gate' else 'refuted'}）は一致を要求しない** — "
              f"片方でも否なら否なので、そのまま decide で記録してよい。",
              file=sys.stderr)
        return 4

    # 監督の書き分けを見る（拒否ではなく警告。判断は監督の仕事）
    for w in _claim_verify_defect(a):
        print(f"注意: {w}", file=sys.stderr)
    bad = _reasoning_defect(why, a.verdict, a.event)
    if bad:
        print(f"decide: --why {bad} With human review retired, this text is the only account of why "
              f"the change was allowed to merge (docs/11 §4f). Say what was weighed and what evidence "
              f"decided it.", file=sys.stderr)
        return 2
    # An admission with no evidence consulted is a stamp regardless of how well the prose reads.
    if a.verdict in ("admit", "pass", "survives", "conforms") and not (a.evidence or "").strip():
        print(f"decide: --evidence is required for verdict {a.verdict!r}. Naming what you actually "
              f"consulted (the command you ran and its real output, the CI run, the repro_lint verdict) "
              f"is what separates a judgment from a stamp — and nobody read the diff (docs/11 §4f).",
              file=sys.stderr)
        return 2
    marker_key = a.event_id or _stable_key(a.event, a.verdict, why)   # sha256; see cmd_log
    marker = f"<!-- orgforge:decision:{marker_key} -->"
    if _already_logged(a.repo, a.issue, marker):
        print(f"decide: decision {marker_key} already on issue #{a.issue} — idempotent no-op.")
        return 0
    icon = {"admit": "✅", "pass": "✅", "survives": "✅", "conforms": "✅",
            "reject": "⛔", "refuted": "⛔", "fail": "⛔",
            "rework": "🔁", "park": "⏸️", "freeze": "🧊"}.get(a.verdict, "•")
    parts = [f"## {icon} {a.event} — `{a.verdict}`"]
    if a.by:
        parts.append(f"**Decided by:** `{a.by}`" + (f" · **phase:** `{a.phase}`" if a.phase else ""))
    elif a.phase:
        parts.append(f"**Phase:** `{a.phase}`")
    parts.append(f"\n**Why (the reasoning):**\n{why}")
    if getattr(a, "claimed", None):
        parts.append(f"\n**Claimed (何が報告されたか — 原文に近い形で):**\n{a.claimed}")
    if getattr(a, "verified", None):
        parts.append(f"\n**Verified (監督が自分で確かめたこと — コマンドと出力):**\n{a.verified}")
    if getattr(a, "evidence", None):
        parts.append(f"\n**Evidence consulted:**\n{a.evidence}")
    if getattr(a, "alternatives", None):
        parts.append(f"\n**Alternatives considered and rejected:**\n{a.alternatives}")
    if getattr(a, "standard", None):
        parts.append(f"\n**Standard applied:** {a.standard}")
    if getattr(a, "risk", None):
        parts.append(f"\n**Known risk accepted:** {a.risk}")
    # TAMPER EVIDENCE (docs/11 §4f.1). A GitHub comment is editable and deletable by anyone with write
    # access — including the agents this record judges — while the ledger is hash-chained. Without a
    # digest an agent could silently rewrite its own account (dropping the --risk it admitted, say) and
    # `ledger verify` would still report the chain intact. So the reasoning is hashed here and the digest
    # is printed for the caller to carry into the ledger receipt as `reasoning_sha256`: re-hashing the
    # comment later either matches, or the account was altered. It does not PREVENT the edit; it makes
    # the edit detectable, which is what "tamper-evident" means.
    digest = _reasoning_digest(why, a.evidence, a.alternatives, a.standard, a.risk)
    parts.append(f"\n`reasoning_sha256: {digest}` — re-hash this record's fields to detect an edit; "
                 f"the ledger receipt carries the same digest.")
    parts.append("\n_No human reviewed this change before merge (docs/11 §4f). This record is the "
                 "account of why it was allowed to._")
    body = "\n".join(parts) + f"\n\n{marker}"

    # **台帳を先に通す。** 統制（自己承認拒否・順序違反）は台帳が持っているので、
    # Issue に書いてから台帳が拒否すると「Issue には admit と書いてあるが台帳には無い」
    # という最悪の食い違いが残る。拒否されるなら、外に見える記録を作る前に止める。
    here = HERE
    payload = {"verdict": a.verdict, "deliverable": str(a.issue), "issue": a.issue,
               "reasoning_sha256": digest,
        **({"lineage": a.lineage} if getattr(a, "lineage", None) else {})}
    if getattr(a, "phase", None):
        payload["phase"] = a.phase
    if getattr(a, "risk", None):
        payload["risk_accepted"] = True
    try:
        _base = ([sys.executable, os.path.join(here, "writer_client.py"), "append", "--"]
                 if os.environ.get("ORG_WRITER_SOCKET")
                 else [sys.executable, os.path.join(here, "ledger.py"), "append"])
        r = subprocess.run(_base + [
                            "--actor", a.by, "--class", a.event,
                            # 冪等キーは **判定の内容ごと**に一意。`{event}-{issue}` だと2周目の
                            # 判定が1周目と衝突して no-op になり、しかも冪等チェックは統制より
                            # 先に評価されるので、自己承認・順序違反が「既に記録済み」として
                            # 素通りする（実地で確認）。digest は verdict/why/evidence から
                            # 作られるので、同じ判定の再実行だけが正しく no-op になる。
                            "--natural-key", f"{a.event}-{a.issue}-{digest[:12]}",
                            "--payload", json.dumps(payload, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=30)
        led_out = ((r.stdout or "") + (r.stderr or "")).strip()
        led_ok = r.returncode == 0
    except Exception as e:
        led_out, led_ok = str(e), False

    if not led_ok:
        print(f"台帳が受け付けなかったので、Issue にも記録していない:\n  {led_out[:500]}",
              file=sys.stderr)
        if "rejected" in led_out:
            print("\n  これは統制が働いた結果である（自己承認・順序違反など）。"
                  "判定そのものを見直すこと。", file=sys.stderr)
        return 4

    code, out = gh(["issue", "comment", str(a.issue), "--repo", a.repo, "--body", body])
    if code != 0:
        print(f"gh error posting decision comment: {out}", file=sys.stderr)
        print(f"  注意: 台帳には既に記録済み（{a.event} #{a.issue}）。Issue 側だけが欠けている。\n"
              f"  同じ引数で再実行すれば、台帳は冪等 no-op になり Issue だけが埋まる。",
              file=sys.stderr)
        return 2
    print(f"recorded decision {a.event}={a.verdict} on issue #{a.issue}.")
    print(f"reasoning_sha256={digest}")
    # 説明ではなく、そのまま打てる形を出す。実地では受領証が書かれず（refutation は台帳0件）、
    # 相関キーの無い判定が素通りしていた。`issue` は相関キーでもあるので、これが欠けると
    # DISTINCT_ACTOR / requires_prior が対象を特定できず、統制そのものが効かない。
    print(f"台帳にも受領証を記録した（{a.event} #{a.issue}, digest {digest[:12]}…）。")
    return 0
