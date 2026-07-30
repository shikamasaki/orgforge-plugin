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
               "blocker": getattr(a, "blocked_by", None) or "",
               "issue": a.issue}
    if getattr(a, "command", None):
        payload["command"] = a.command
    if getattr(a, "result", None):
        payload["result"] = str(a.result)[:4000]
    if getattr(a, "files", None):
        payload["files"] = a.files
    here = HERE
    try:
        p = subprocess.run([sys.executable, os.path.join(here, "ledger.py"), "append",
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
               "reasoning_sha256": digest}
    if getattr(a, "phase", None):
        payload["phase"] = a.phase
    if getattr(a, "risk", None):
        payload["risk_accepted"] = True
    try:
        r = subprocess.run([sys.executable, os.path.join(here, "ledger.py"), "append",
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
