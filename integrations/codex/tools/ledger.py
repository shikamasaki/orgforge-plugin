#!/usr/bin/env python3
"""ledger — the append-only, hash-chained record for orgforge-plugin (ledger-schema.yaml).

This is the running implementation of Organ 5's record and Organ 6's custody holder: the
append-only AUDIT + ENFORCEMENT record from which every derived view (and therefore every
context pack) is projected. It is NOT the SSoT — the SSoT is code + the domain model
(conventions + the org spec); this ledger is the process journal (audit, requires_prior
gating, crash-safe resume), a record of *what happened*, not of *what the system is*. A
settled decision co-commits to code or conventions; the ledger holds only the receipt that it
was made. Before this existed, ledger-schema.yaml specified an envelope and event classes
that no code ever wrote, chained, or verified — the audit's D3 gap. This tool closes it:
events are appended under a hash chain, the chain is independently replayable (the external
watchdog's primitive), views are projected DETERMINISTICALLY from events, and the census /
digest are exact projections (same window + same ledger ⇒ byte-identical), never curated.

It ships no runtime and no scheduler (docs/08, R0): the registrar/watchdog are agents a host
runs on a cadence; this tool is the file-backed store + the projection + the verify they call.
The ledger is one JSON-lines file (append-only) plus a companion HEAD file holding the last
hash, so a writer never has to load the whole log to append:

    <root>/ledger.jsonl   ->  one envelope per line (id, seq, ts, actor, class, payload,
                              prev_hash, hash) — ledger-schema.yaml §envelope
    <root>/HEAD           ->  {"seq": N, "hash": "..."}  (the chain tip)

Invariants this tool enforces (ledger-schema.yaml §envelope.write_control, §event_classes):
  - Append-only, gapless seq, single writer: `append` never rewrites a line; seq = prev+1.
  - Hash chain: hash = H(prev_hash || canonical_json(id,seq,ts,actor,class,payload)); any
    edit to any past line breaks `verify` (tamper evidence, not tamper proof).
  - actor comes from the --actor arg (runtime identity), NEVER from the payload — an agent
    cannot forge another actor by writing it into the event body.
  - requires_prior: a `result_deployed` for candidate C is REJECTED at append time unless a
    prior `refutation_attempted{claim_id==C, verdict==survives}` exists — the skeptic is
    load-bearing, enforced at write time, not merely charted (org_lint's O6 checks the shape;
    this checks the actual event history).
  - Deterministic projection: `view`, `census`, `digest` are pure functions of the events in
    the window; no clock, no ordering nondeterminism (events carry their own seq/ts).

Commands:
  append <root> --actor A --class C --payload JSON [--ts TS]   append one event (chained)
  verify <root>                                                replay the chain; report first break
  view   <root> <view_id> [--since TS] [--until TS]            project a derived view (ledger-schema §views)
  census <root> [--since TS] [--until TS]                      counts of every event class (view: ledger_census)
  digest <root> --window-since TS [--window-until TS]          the deterministic digest (ledger-schema §digest)
  cat    <root> [--class C] [--actor A]                        print raw events (debug)
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _organ import read_events, LedgerCorruption, resolve_root   # noqa: E402

# ── the forced SDLC phase order (docs/11) — reproducibility's spine ──
# A deliverable travels these phases in this order; a phase may not START until the prior phase is
# ADMITTED (phase_admitted{verdict==pass}) for the same deliverable. This is the same requires_prior
# idiom as result_deployed, generalized from admission-gating to phase-gating so that the PROCESS is
# reproducible: same spec ⇒ the same phases run in the same order for every founder and every run.
PHASE_ORDER = ["requirements", "design", "implement", "test", "integrate", "deploy", "operate"]



# 同じ仕事を指す識別子は2系統に分かれていた: 人間側 / decide / org_cycle の照合は
# `deliverable` / `issue`、強制ロジック（requires_prior / DISTINCT_ACTOR）は
# `candidate_id` / `claim_id`。同じものを指しているのに片方しか見ないため、
# **運用では自己 admit も、存在しない deliverable の deploy も素通りした。**
# 束ねて、どちらで書かれていても相関が取れるようにする。
_CORRELATION_KEYS = ("candidate_id", "claim_id", "deliverable", "issue")


def _correlation_ids(payload):
    """その payload が名指ししている「仕事」の識別子すべて（正規化済みの集合）。

    どれか1つでも一致すれば同じ仕事とみなす。書き手がどのキーを使ったかに強制の有効性が
    左右されてはいけない — 左右されると、キーを外した瞬間に統制が無言で消える。
    """
    out = set()
    for k in _CORRELATION_KEYS:
        v = payload.get(k)
        if v is not None and str(v).strip() != "":
            out.add(str(v).strip().lstrip("#"))
    return out


# `pack_manifest_id: "issue-7"` / `contract_ref` は candidate_id と Issue 番号を繋ぐ唯一の橋。
# 直接の共有 ID が無くても、この橋を辿れば同じ仕事だと分かる。
_ALIAS_KEYS = ("pack_manifest_id", "contract_ref", "spec_ref")


def _alias_ids(payload):
    """`issue-7` のような別名から Issue 番号を取り出す。"""
    out = set()
    for k in _ALIAS_KEYS:
        v = payload.get(k)
        if v is None or str(v).strip() == "":
            continue
        s = str(v).strip()
        out.add(s.lstrip("#"))
        m = re.match(r"^(?:issue|task)[-_#]?(\d+)$", s, re.I)
        if m:
            out.add(m.group(1))
    return out


def _work_aliases(hist):
    """台帳全体から「同じ仕事を指す識別子」の同値類を作る。

    実地では cycle_started が candidate_id しか持たず、判定側は deliverable で書かれるため、
    直接比較では永久に相関しなかった（で maker が自分の を admit できた）。
    橋は台帳の中にある — `cycle_started{candidate_id, pack_manifest_id:"issue-7"}` と
    `candidate_submitted{candidate_id, contract_ref}` が両者を繋いでいる。
    **人に同じキーで書かせるのではなく、既にある対応関係を辿る。**
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for e in hist:
        pl = e.get("payload", {}) or {}
        ids = _correlation_ids(pl) | _alias_ids(pl)
        ids = sorted(ids)
        for other in ids[1:]:
            union(ids[0], other)
    return find


def _same_work(pa, pb, hist=None):
    """2つの payload が同じ仕事を指すか。

    共有する識別子が1つでもあれば True。無い場合でも、台帳が持つ別名の対応関係
    （candidate_id ↔ issue-N）を辿って同じ仕事に行き着けば True。
    """
    a, b = _correlation_ids(pa), _correlation_ids(pb)
    if a & b:
        return True
    if not hist or not a or not b:
        return False
    find = _work_aliases(hist)
    return bool({find(x) for x in a} & {find(y) for y in b})



def corrected_seqs(events, kinds=("probe", "mistake")):
    """`correction` で無効化された seq の集合。

    追記型なので過去は消せない。「これは実判定ではない」を機械が読める形で宣言するのが
    correction で、status / learning はこれを見て除外する。自由記述の note では読めず、
    実地ではプローブ4件が実判定として数えられ board が現実と食い違った。

    既定では probe / mistake だけを除外する — backfill は「後から書いた実判定」であって
    無効ではないし、superseded は最新判定の解決（時系列）が扱う領域なので、ここで消すと
    二重に効いてしまう。
    """
    out = set()
    for e in events:
        if e.get("class") != "correction":
            continue
        pl = e.get("payload", {}) or {}
        if pl.get("kind") not in kinds:
            continue
        for s in (pl.get("corrects") or []):
            try:
                out.add(int(s))
            except (TypeError, ValueError):
                continue
    return out


def _same_deliverable(a, b):
    """Do two payloads name the same deliverable? Compared as NORMALIZED STRINGS, not by ==.

    The deliverable is a GitHub Issue number that agents write freely as `42`, `"42"`, or `"#42"` across
    the flow. Raw equality makes `42 != "42"`, so the phase chain intermittently rejects a `phase_started`
    whose predecessor is visibly present in the ledger — an unreproducible failure whose message says
    "design was never admitted" while the admission is right there. That is the worst possible signature
    for an unattended run, so the comparison normalizes instead of trusting the writer's JSON type."""
    if a is None or b is None:
        return False
    return str(a).strip().lstrip("#") == str(b).strip().lstrip("#")


def _prior_phase(phase):
    """The phase that must be admitted before `phase` may start; None for the first phase."""
    try:
        i = PHASE_ORDER.index(phase)
    except ValueError:
        return None  # unknown phase name — the schema enum will reject it upstream; don't gate here
    return PHASE_ORDER[i - 1] if i > 0 else None


def _phase_admitted_for(ev, hist, phase):
    """この deliverable（またはその親）に対して `phase` が admit 済みか。

    **なぜ親まで遡るのか。** founding は objective 単位で requirements/design を admit する
    （設計はそこで起きるので当然）。一方 /org-work は task Issue 番号を deliverable にして
    `phase_started{implement}` を打つ。両者は別の文字列なので、objective で admit しても
    task には効かず、指示どおり進めても task が弾かれた（実地で判明）。

    task ごとに requirements/design を再度 admit させるのは、同じ設計を N 回 admit させる
    セレモニーにしかならない。**設計は objective の単位で起きた**のだから、その admit を
    子タスクが継承するのが正しい。継承は payload の `parent`（/org-decompose が書く）で辿る。

    親を持たない deliverable は従来どおり自分の admit だけを見る — 挙動は変わらない。"""
    target = ev["payload"].get("deliverable")
    parent = ev["payload"].get("parent")          # /org-decompose が task に書く objective Issue 番号
    for e in hist:
        if e["class"] != "phase_admitted":
            continue
        if e["payload"].get("phase") != phase or e["payload"].get("verdict") != "pass":
            continue
        d = e["payload"].get("deliverable")
        if _same_deliverable(d, target):
            return True
        if parent is not None and _same_deliverable(d, parent):
            return True                            # 親 objective の admit を継承する
    return False


# ── event classes with a required-prior constraint (ledger-schema §event_classes) ──
# result_deployed{candidate_id==C} is INVALID without a prior refutation_attempted with
# claim_id==C and verdict==survives. This is the one write-time invariant the schema states
# in prose ("requires_prior"); we execute it against the actual event history.
REQUIRES_PRIOR = {
    # SDLC phase gate (docs/11 §2): phase_started{deliverable==D, phase==P} is INVALID unless a
    # phase_admitted{deliverable==D, phase==prior(P), verdict==pass} exists. requirements (prior==None)
    # is always allowed to start. Same shape as result_deployed — one predicate, more events.
    "phase_started": lambda ev, hist: (
        _prior_phase(ev["payload"].get("phase")) is None
        or _phase_admitted_for(ev, hist, _prior_phase(ev["payload"].get("phase")))
    ),
    # A phase may not be ADMITTED unless it was STARTED (docs/11 §2). Without this the mold is
    # decorative: `phase_admitted{integrate}` on an empty ledger makes `phase_started{deploy}` legal,
    # so a deliverable reaches deploy with requirements/design/implement/test never having happened.
    # Worse, it is the move an operator naturally reaches for when phase_started is rejected — the gate
    # would otherwise teach its own bypass.
    "phase_admitted": lambda ev, hist: any(
        e["class"] == "phase_started"
        and _same_deliverable(e["payload"].get("deliverable"), ev["payload"].get("deliverable"))
        and e["payload"].get("phase") == ev["payload"].get("phase")
        for e in hist
    ),
    # 識別子は束ねて見る（_same_work）。`claim_id == candidate_id` だけを見ていたため、
    # deliverable/issue で書かれた実地の refutation 2件と相関できず、しかも
    # None == None が一致してしまい **deploy ゲートが丸ごと無効**だった（が通った）。
    "result_deployed": lambda ev, hist: any(
        e["class"] == "refutation_attempted"
        and _same_work(e["payload"], ev["payload"], hist)
        and e["payload"].get("verdict") == "survives"
        for e in hist
    ),
    # A4 report-up is INVALID unless this supervisor has done at least one A3 conformance review
    # that CONFORMS — a manager may not report subordinate work up as its own without having
    # verified it against the intent it delegated (docs/09 §A3/§A4). Without this, the schema's
    # requires_prior promise (ledger-schema.yaml) is prose, not enforced.
    "report_up": lambda ev, hist: any(
        e["class"] == "conformance_reviewed"
        and e["payload"].get("supervisor") == ev["payload"].get("supervisor")
        and e["payload"].get("verdict") == "conforms"
        for e in hist
    ),
    # A3 conformance review is INVALID unless the intent it reviews against was actually delegated
    # as a spec first (spec-driven, docs/09): the delegated_intent_ref must resolve to a prior
    # spec_delegated for the same (supervisor, subordinate). Otherwise delegated_intent_ref dangles
    # — a manager cannot "verify against the intent it delegated" if it never delegated one.
    "conformance_reviewed": lambda ev, hist: any(
        e["class"] == "spec_delegated"
        and e["payload"].get("supervisor") == ev["payload"].get("supervisor")
        and e["payload"].get("subordinate") == ev["payload"].get("subordinate")
        for e in hist
    ),
    # SSoT底上げ enforcement (docs/11 §4d): a cycle_completed is INVALID unless it STATES what it did to
    # the domain model — either `updated` (it co-committed a convention / domain-model artifact) or
    # `none_asserted` (it explicitly claims this cycle established no new domain rule — a claim the
    # skeptic can refute). This is a payload-shape requirement, not a history lookup: it makes "forgot to
    # update the domain model" impossible to do SILENTLY, so SDD runs on a growing context base, not in a
    # vacuum. Same explicit-negative pattern as exceptions_none_asserted.
    "cycle_completed": lambda ev, hist: (
        isinstance(ev["payload"].get("domain_model"), dict)
        and ("updated" in ev["payload"]["domain_model"] or "none_asserted" in ev["payload"]["domain_model"])
    ),
}

# ── separation of duties, enforced at WRITE time (docs/03 §3.1, docs/11 §4f) ──────────────────────
# REQUIRES_PRIOR asks "did the right events happen in the right order?" — it never asks WHO wrote them.
# That gap was survivable while a human read the diff. With human review retired (docs/11 §4f) the gate
# and the skeptic are the only judges left, so an actor that can write its own admission IS the whole
# judgment layer, and the hash chain then LAUNDERS the forgery: a forged verdict is tamper-evidently
# recorded and verifies clean, which reads as stronger evidence than no record at all.
#
# So judgment classes carry a distinct-actor predicate: the actor recording a verdict must not be the
# actor whose work it judges. This is the runtime half of O6 (org_lint's O6 checks the CHART separates
# maker from checker; this checks the RUN did too — a static chart cannot see one process writing both
# sides). Keyed on candidate_id/claim_id, so it needs only that candidate's own history.
#
# (class, payload-key naming the judged candidate, [classes whose actor must differ], why)
DISTINCT_ACTOR = {
    "admission_decided": ("candidate_id", ("cycle_started", "cycle_completed", "candidate_submitted"),
                          "the gate may not admit work it produced itself — the maker/checker split is "
                          "the org's load-bearing control (docs/03 §3.1). With human review retired "
                          "(docs/11 §4f) a self-admission is unappealable and undetectable downstream."),
    "refutation_attempted": ("claim_id", ("cycle_started", "cycle_completed", "admission_decided"),
                             "the skeptic may not refute work it made or already admitted — adversarial "
                             "review decorrelates blind spots only if the reviewer is a different actor "
                             "(docs/03 §5, docs/11 §4f.3)."),
}



def _enforce_attested():
    """統制イベントに receipt 由来の identity を要求するか。**三値で扱う。**

    **caller が消せる設定を根拠にしない。** 実測（監査）:
      - `ORG_REQUIRE_ATTESTED_IDENTITY=0` を足すだけで強制が消えた
      - `constitution.yaml` を **削除** するだけで強制が消えた

    したがって:
      1. **policy は root 所有の場所から読む**（`ORG_POLICY_FILE`、既定
         `/usr/local/etc/orgforge/policy.yaml`）。そこに宣言があれば **それが最終**で、
         env でも org の constitution でも上書きできない。
      2. policy が無い org（段階A / 未導入）では constitution を読む。**削除は「無効」ではなく
         「宣言が無い」**なので、有効にしていた org が消しただけで無防備にならないよう、
         **一度でも有効だった記録があれば消えたことを拒否する**（下の sticky）。
      3. 読めない・型が違うなら止める（fail-closed）。

    env override は **policy が無いときの開発用**に限り、`ORG_ALLOW_POLICY_ENV=1` を同時に
    要求する — 黙って効く逃げ道にしない。
    """
    # ① root 所有の policy が最終
    pol = os.environ.get("ORG_POLICY_FILE") or "/usr/local/etc/orgforge/policy.yaml"
    if os.path.isfile(pol):
        try:
            st = os.stat(pol)
        except OSError as e:
            raise SystemExit(f"policy を stat できない: {e}\n  ファイル: {pol}")
        if st.st_uid != 0 and st.st_uid != os.getuid():
            raise SystemExit(f"policy の所有者が root でも自分でもない（uid={st.st_uid}）: {pol}")
        if st.st_mode & 0o022:
            raise SystemExit(f"policy が他者から書き込み可能（mode "
                             f"{oct(st.st_mode & 0o777)}）: {pol}\n"
                             f"  **書ける主体は強制を外せる。**")
        try:
            import yaml
            with open(pol, encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
        except Exception as e:
            raise SystemExit(f"policy を読めないので強制の有無を判定できない: {e}\n"
                             f"  ファイル: {pol}\n  **判定できないなら止める。**")
        if not isinstance(doc, dict):
            raise SystemExit(f"policy が map ではない: {pol}")
        v = doc.get("require_attested_identity")
        if v is not None:
            if not isinstance(v, bool):
                raise SystemExit(f"policy の require_attested_identity が真偽値でない"
                                 f"（{v!r}）: {pol}")
            return v            # **これが最終。** env も constitution も上書きできない

    # ② env は policy が無いときの開発用。**黙って効かせない。**
    env = os.environ.get("ORG_REQUIRE_ATTESTED_IDENTITY")
    if env is not None:
        if os.environ.get("ORG_ALLOW_POLICY_ENV") != "1":
            raise SystemExit(
                "ORG_REQUIRE_ATTESTED_IDENTITY が設定されているが、環境変数で強制を切り替える"
                "ことは許していない。\n"
                "  **caller が消せる設定を根拠にしない** — 実測で、この変数を足すだけで強制が"
                "消えた。\n"
                "  開発で使うなら ORG_ALLOW_POLICY_ENV=1 も明示すること"
                "（本番では root 所有の policy を使う）。")
        if env not in ("0", "1"):
            raise SystemExit(f"ORG_REQUIRE_ATTESTED_IDENTITY が 0/1 でない（{env!r}）。")
        return env == "1"

    # ③ org の constitution
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from discover import constitution, ledger_root
        path = constitution()
    except Exception as e:
        raise SystemExit(f"constitution の場所を解決できないので、強制の有無を判定できない: {e}")
    declared = None
    if path and os.path.isfile(path):
        try:
            import yaml
        except Exception:
            raise SystemExit("PyYAML が無いので constitution を読めず、強制の有無を判定できない。")
        try:
            with open(path, encoding="utf-8") as f:
                c = yaml.safe_load(f)
        except Exception as e:
            raise SystemExit(f"constitution.yaml を解析できないので判定できない: {e}\n"
                             f"  ファイル: {path}\n  **破損を「強制なし」と読み替えない。**")
        if c is not None:
            if not isinstance(c, dict):
                raise SystemExit(f"constitution.yaml が map ではない: {path}")
            enf = c.get("enforcement")
            if enf is not None and not isinstance(enf, dict):
                raise SystemExit(f"enforcement が map ではない: {path}")
            j = ((enf or {}).get("judges") or {})
            if not isinstance(j, dict):
                raise SystemExit(f"enforcement.judges が map ではない: {path}")
            v = j.get("require_attested_identity")
            if v is not None:
                if not isinstance(v, bool):
                    raise SystemExit(f"require_attested_identity が真偽値でない（{v!r}）: {path}")
                declared = v

    # ④ **sticky。** 一度でも有効だった org で、宣言が消えたなら止める。
    #    実測: constitution を削除するだけで強制が消えた。「消した」は「無効にした」ではない。
    try:
        root = ledger_root()
        marker = os.path.join(root, "attested-identity-enabled") if root else None
    except Exception:
        marker = None
    if declared is True and marker:
        try:
            if not os.path.exists(marker):
                with open(marker, "w", encoding="utf-8") as f:
                    f.write("require_attested_identity was enabled here\n")
        except OSError:
            pass
    if declared is None and marker and os.path.exists(marker):
        raise SystemExit(
            f"この org は以前 require_attested_identity を有効にしていたが、いまその宣言が無い。\n"
            f"  痕跡: {marker}\n"
            f"  **宣言を消すことは無効にすることではない。** constitution が失われたか、"
            f"意図的に外されたかを確かめること。\n"
            f"  本当に無効にするなら constitution に `require_attested_identity: false` と"
            f"明示し、この痕跡を消すこと。")
    return bool(declared)


def _distinct_actor_violation(ev, hist):
    """Return a rejection reason if this event's actor already acted as maker/prior-judge for the same
    candidate, else None. Compares the ACTOR (envelope), never a payload field — a payload role name is
    agent-authored and therefore forgeable; the actor is the recorded writer."""
    rule = DISTINCT_ACTOR.get(ev["class"])
    if not rule:
        return None
    key_field, conflicting, why = rule
    ids = _correlation_ids(ev["payload"])
    if not ids:
        # 相関キーが1つも無い判定は **拒否する**。以前はここで素通りさせており（"the payload-shape
        # check is elsewhere" と書いてあったが、その elsewhere は存在しなかった）、実地で maker が
        # 自分の成果物を admit できた。相関できない判定は、検証できない判定であって、
        # 「検証を通った判定」ではない。無言で通すのが最悪で、統制が効いていないことが誰にも
        # 見えないまま、ハッシュ連鎖が偽造にお墨付きを与える。
        return (f"{ev['class']} rejected — 判定の対象を特定できない: payload に "
                f"{' / '.join(_CORRELATION_KEYS)} のいずれも無い。\n"
                f"  相関キーが無いと maker と gate が同一 actor かを照合できず、この統制は"
                f"無言で無効になる（{why}）\n"
                f"  対象の Issue 番号か candidate_id を payload に入れて再実行すること。")
    # **`--actor` を変えるだけで職務分離を回避できてはいけない。**
    # 実測: maker 本人の自己 admit は拒否されるが、同じプロセスが `--actor gate-alias` に
    # 変えると通り、鎖も intact だった。名乗りを変えられるなら、比較に意味が無い。
    #
    # したがって **統制の中核となる判定は、検証済み receipt 由来の `decision_by` を要求する**。
    # receipt が無ければ、その判定は「独立性を強制する根拠」にはならない — 記録は残せるが、
    # `identity_assurance: claimed` として残り、admission の生成には使えない。
    _ENFORCED = {"admission_decided", "refutation_attempted"}
    if ev["class"] in _ENFORCED and _enforce_attested():
        pl = ev.get("payload") or {}
        # **identity は writer が生成する。** payload に書かれた値は自己申告であって証拠では
        # ない — 実測（監査）: `identity_assurance: attested` と `decision_by` を書くだけで
        # admit が通り、鎖も intact だった。そして **私のテストがそれを正常系として固定して
        # いた**。書けるものを検査に使ってはいけない。
        if not (ev.get("_verified_identity") or {}).get("decision_by"):
            return (f"{ev['class']} は generic append では記録できない"
                    f"（require_attested_identity が有効）。\n"
                    f"  **payload に identity_assurance を書いても証拠にならない** — "
                    f"書けるものを検査に使ってはいけない。\n"
                    f"  **`--actor` を変えるだけで職務分離を回避できる** — 実測で、maker 本人の\n"
                    f"  自己 admit は拒否されるが、同じプロセスが別名を名乗ると通っていた。\n"
                    f"  judgment は **receipt を検証した経路** からのみ記録できる:\n"
                    f"    github_sync.py provisional --receipt <judge が署名した receipt> …\n"
                    f"  その経路が receipt を検証し、identity fields を生成する。\n"
                    f"  （この強制は constitution の enforcement.judges.require_attested_identity\n"
                    f"   が真のときに働く。既定は偽 — 段階的に移行できるようにするため）")

    # **職務分離は `decision_by` 同士を比べる（H1）。** `recorded_by` を比べてはいけない —
    # 代理記録では常に同じ主体になるので、比べると正当な運用が全て違反になる。
    # `decision_by` が無い（0.36.x 以前 / receipt 無し）イベントは、legacy の `actor` を
    # **claimed 属性として**使う。昇格はしない — 比較できることと、認証されていることは別。
    def _who(e):
        return (e.get("payload") or {}).get("decision_by") or e.get("actor")

    actor = _who(ev)
    for e in hist:
        if e["class"] not in conflicting:
            continue
        # 識別子は束ねて照合する — 書き手が deliverable で書いても candidate_id で書いても
        # 同じ仕事として相関する（片方しか見ないと、キーを変えた瞬間に統制が消える）。
        if _same_work(e["payload"], ev["payload"], hist) and _who(e) == actor:
            shared = sorted(_correlation_ids(e["payload"]) & ids)
            if shared:
                what = ", ".join(shared)
            else:
                # 別名経由で一致した場合。**どう繋がったかを見せる** — 「同じ仕事だ」と
                # 言われた側が納得も反論もできないメッセージは、拒否の理由になっていない。
                mine = ", ".join(sorted(ids))
                theirs = ", ".join(sorted(_correlation_ids(e["payload"])
                                          | _alias_ids(e["payload"])))
                what = (f"同じ仕事（この判定は {mine} を指し、seq {e.get('seq')} は {theirs} を"
                        f"指す。台帳の別名対応で同一と解決した）")
            return (f"{ev['class']} rejected — actor {actor!r} already acted as {e['class']} for "
                    f"{what}: {why}")
    return None

# an honest per-class reason for a requires_prior rejection (the reject message uses this instead
# of a single hardcoded 'skeptic is load-bearing' line that only fit result_deployed).
REQUIRES_PRIOR_WHY = {
    "phase_started": "a phase_admitted{deliverable, phase==prior(phase), verdict==pass} — the SDLC "
                     "phase order is non-skippable (requirements→design→implement→test→deploy→operate); "
                     "a phase cannot start before its predecessor is admitted (docs/11 §2). This is what "
                     "makes the process reproducible across founders and runs.",
    "phase_admitted": "a phase_started{deliverable, phase} for the SAME deliverable and phase — a phase "
                      "cannot be admitted without having been entered (docs/11 §2). Without this the "
                      "mold is decorative: admitting a late phase out of nowhere makes every earlier one "
                      "skippable.",
    "result_deployed": "a refutation_attempted{claim_id==candidate_id, verdict==survives} — the "
                       "skeptic is load-bearing; a result cannot deploy without surviving adversarial review",
    "report_up": "a conformance_reviewed{verdict==conforms} by this supervisor — a manager cannot "
                 "report subordinate work up as its own without verifying it against the intent it "
                 "delegated (docs/09 §A3/§A4)",
    "conformance_reviewed": "a spec_delegated for this (supervisor, subordinate) — a manager cannot "
                            "verify against 'the intent it delegated' if it never delegated a spec "
                            "(docs/09 §spec-driven)",
    "cycle_completed": "a `domain_model` field — {updated: [ref]} if this cycle co-committed a "
                       "convention/domain-model artifact, or {none_asserted: <reason>} if it "
                       "established no new domain rule. A cycle cannot silently skip updating the "
                       "domain model (SSoT底上げ, docs/11 §4d) — state it or the append is rejected.",
}

# ── views は ledger-schema.yaml の `views:` を単一の情報源として読む ────────────────────────
# 以前はここに13件をハードコードしていたが、スキーマは26件を宣言していた。乖離の実害:
#   - `/org-work` が parts_inventory を引けず、コマンド全体が起動しなかった
#   - **gate の context_pack 3件と skeptic の 2件がすべて未実装**だった。organization.yaml が
#     「gate はこの3つを見て admit する」と宣言していても、実行時に1つも引けない。
#     SoD（maker≠checker）は中核主張なのに、checker が判断材料を取得できなかった
#   - それでも `org_lint` は pass した（CP 検査は「スキーマに定義があるか」しか見ず、
#     「ツールが実装しているか」を見ていなかった）
# スキーマを読めば、view を足すのに Python を触る必要がなくなり、乖離が構造的に起きない。
_VIEW_FROM_CACHE = None


def _schema_path():
    """ledger-schema.yaml の場所。org のもの → プラグインのテンプレート、の順に探す。

    `ORG_LEDGER_SCHEMA` が勝つ（discover 系と同じ規律 — env は「本当に上書きが必要な場合」の
    ための逃げ道）。**壊れた／存在しない schema を指した状態を検査できることも要件**である。
    検証できない状態で書かないことを、実際に確かめられなければ意味がない。
    """
    env = os.environ.get("ORG_LEDGER_SCHEMA")
    if env:
        return env if os.path.exists(env) else None
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    try:
        sys.path.insert(0, here)
        import discover
        root = discover.org_root()
        if root:
            cands.append(os.path.join(root, "ledger-schema.yaml"))
    except Exception:
        pass
    cands.append(os.path.join(here, "..", "template", "ledger-schema.yaml"))
    cands.append(os.path.join(here, "template", "ledger-schema.yaml"))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def _view_from():
    """{view_id: [derived-from classes]} をスキーマから読む。読めなければ空 dict。"""
    global _VIEW_FROM_CACHE
    if _VIEW_FROM_CACHE is not None:
        return _VIEW_FROM_CACHE
    out = {}
    path = _schema_path()
    if path:
        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            for vid, spec in (doc.get("views") or {}).items():
                frm = (spec or {}).get("from") if isinstance(spec, dict) else None
                out[vid] = list(frm) if frm else ["*"]
        except Exception:
            pass
    _VIEW_FROM_CACHE = out
    return out


# census 系は全クラスを数えるので、スキーマの `from` に関わらず "*" 扱いにする
_ALL_CLASS_VIEWS = ("ledger_census", "recent_ledger_census")


# ══ Writer Phase 0 — schema 境界 / lock / fsync / HEAD 回復 ═══════════════════
#
# **actor には触らない。** ここで扱うのは「書き込みが壊れないこと」と「新規イベントが検証済み
# であること」だけで、誰が書いたのかの認証（identity_assurance）は別の軸として後で扱う。
# 混ぜると、schema を検証しただけで actor も信頼できるという読み違いを招く。
#
#   validation_assurance:  legacy_unvalidated | validated:v1
#   identity_assurance:    claimed | observed | attested | authenticated   ← 未着手
#
# **schema_version は writer が付ける。** クライアントが指定できるなら、緩い版を名指しして
# 検証を素通りできる（downgrade）。指定されたら拒否する。

LEDGER_SCHEMA_VERSION = 1          # 台帳の形式。プラグインの version とは連動させない —
                                   # コード修正のたびに形式が変わったことにしてはいけない。


def _envelope_core_keys(ev):
    """hash が覆うフィールド。**version ごとに切り替える。**

    v1 以降は `schema_version` を hash に含める — 含めないと、書き換えても検出できないので
    downgrade の拒否が意味を持たない。legacy（version なし）は従来の6フィールドで検証する。
    validator は過去 version を変更せず追加する、という規律の具体形である。
    """
    if ev.get("schema_version"):
        return ("id", "seq", "ts", "actor", "class", "payload",
                "schema_id", "schema_version", "schema_sha256")
    return ("id", "seq", "ts", "actor", "class", "payload")


def schema_digest():
    """使っている ledger-schema.yaml の digest。形式が入れ替わったことを後から検出できる。"""
    path = _schema_path()
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:32]


def load_schema_snapshot():
    """schema を **1回だけ読み、解析結果と digest を1つの snapshot にする**。

    検証と digest 取得が別々に schema を読むと、その間に差し替えられる（TOCTOU）。
    lock 内でこの snapshot を1つ作り、検証・digest の両方に同じものを使う。

    返り値: (snapshot, error)。error があれば新規 append を拒否する（fail-closed）。
    """
    path = _schema_path()
    if not path or not os.path.isfile(path):
        return None, ("ledger-schema.yaml が見つからない。**検証できないまま書かない** — "
                      "検証済みでないものが validated として台帳に残る方が悪い。")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as e:
        return None, f"ledger-schema.yaml を読めない: {e}"
    try:
        import yaml
        doc = yaml.safe_load(raw.decode("utf-8")) or {}
    except Exception as e:
        return None, f"ledger-schema.yaml を解析できない: {e}"
    ec = doc.get("event_classes")
    if not isinstance(ec, dict):
        return None, "ledger-schema.yaml に event_classes が無い（または map でない）。"
    v = doc.get("validation") or {}
    return {
        "path": path,
        "digest": hashlib.sha256(raw).hexdigest()[:32],
        "classes": set(ec.keys()),
        "fields": {k: set(s.keys()) for k, s in ec.items() if isinstance(s, dict)},
        "required": v.get("required") or {},
        "require_any": v.get("require_any") or {},
        "closed": set(v.get("additional_properties_false") or []),
        "writer_only": set(v.get("writer_only") or []),
        "enums": v.get("enums") or {},
        "types": v.get("types") or {},
    }, None


def _check_type(name, val):
    if name == "list":
        return isinstance(val, list)
    if name == "int_or_str":
        return isinstance(val, (int, str)) and not isinstance(val, bool)
    if name == "int":
        return isinstance(val, int) and not isinstance(val, bool)
    if name == "str":
        return isinstance(val, str)
    if name == "map":
        return isinstance(val, dict)
    if name == "number":
        # bool は int の subclass なので除く。NaN / inf は「数」として扱わない —
        # 合計に混ぜると比較が壊れ、上限の判定が意味を失う。
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            return False
        return val == val and val not in (float("inf"), float("-inf"))
    # **未知の型名は通さない。** 黙って True を返すと、schema の typo が「検査の無効化」になる —
    # `list` を `lst` と書いた瞬間にその検査が消え、消えたことに気づく経路が無い。
    return None                       # 呼び側が「schema 側の誤り」として拒否する


def validate_event(cls, payload, snap, writer_op=None):
    """新規 append の検証。**3つの軸を分けて扱う。**

      1. required を宣言したクラスだけ、必須 field の欠落を拒否
      2. 宣言済み field は **存在する場合に** enum / 型を検証
      3. additional_properties_false のクラスだけ、未宣言 field を拒否

    全クラスを一度に closed-world にすると、schema の乖離が「組織全体の記録停止」に変わる。
    それは fail-closed ではなく、既知の移行不備による可用性事故である。

    返り値: (error, warnings)。error があれば拒否、warnings は記録して通す。
    """
    if cls not in snap["classes"]:
        near = sorted(k for k in snap["classes"] if k[:4] == cls[:4])
        return (f"未知のイベントクラス {cls!r}（ledger-schema.yaml の event_classes に無い）。"
                + (f"\n  近いもの: {', '.join(near)}" if near else "")
                + "\n  クラスを増やすなら schema に宣言してから書くこと — 宣言の無いクラスは"
                  "projection にも sensor にも乗らず、書いても読まれない。"), []
    if not isinstance(payload, dict):
        return f"payload は map でなければならない（{type(payload).__name__} が来た）。", []

    # **writer 専用のクラスは、その writer 操作からしか書けない。** 検査に使う記録を通常の
    # append で書けると、検査そのものが無効になる（実測: 負の曝露を1件入れると上限が消えた）。
    if cls in snap["writer_only"] and writer_op != cls:
        return (f"{cls} は writer 専用のクラスで、generic append では書けない"
                f"（ledger-schema.yaml validation.writer_only）。\n"
                f"  検査に使う記録は、検査する側だけが書ける必要がある — この記録を自由に"
                f"書けると、検査そのものが無効になる。\n"
                f"  上限の予約なら `ledger.py reserve-exposure` を使うこと。"), []

    given = {k for k in payload if k != "_nk"}

    # ① required（宣言したクラスだけ）
    req = snap["required"].get(cls) or []
    missing = [k for k in req if k not in payload or payload[k] in (None, "")]
    if missing:
        return (f"{cls} に必須 field が無い: {', '.join(missing)}\n"
                f"  （ledger-schema.yaml validation.required.{cls}）\n"
                f"  統制イベントは中身が無ければ検査に使えない — 空の記録は"
                f"「記録されている」という見た目だけを作る。"), []

    # ①' 相関キー — **どれか1つあればよい。** どれを使うかは経路で違う（union-find で束ねる）。
    #    1つも無い判定は「何についての判定か分からない」ので、検査に使えない。
    anyof = snap["require_any"].get(cls) or []
    if anyof and not any(payload.get(k) not in (None, "") for k in anyof):
        return (f"{cls} に相関キーが無い: {' / '.join(anyof)} のどれか1つが必要。\n"
                f"  何についての判定か分からない記録は、検査にも projection にも使えない。"), []

    # ② enum / 型（**存在する場合に**検証する）
    for f, allowed in (snap["enums"].get(cls) or {}).items():
        if f in payload and payload[f] not in allowed:
            return (f"{cls}.{f} = {payload[f]!r} は許された値ではない: "
                    f"{'|'.join(map(str, allowed))}"), []
    for f, tname in (snap["types"].get(cls) or {}).items():
        if f not in payload:
            continue
        r = _check_type(tname, payload[f])
        if r is None:
            return (f"ledger-schema.yaml の validation.types.{cls}.{f} が未知の型名 "
                    f"{tname!r} を指している（list | int | str | map | int_or_str）。\n"
                    f"  **schema の書き間違いを黙って通さない** — 通すと、その検査は消えたまま"
                    f"になり、消えたことに気づく経路が無い。"), []
        if not r:
            return (f"{cls}.{f} の型が違う（{tname} を期待、"
                    f"{type(payload[f]).__name__} が来た）"), []

    # ③ 未宣言 field — 既定は許可し、乖離として記録する
    declared = snap["fields"].get(cls, set())
    unknown = sorted(given - declared)
    if unknown and cls in snap["closed"]:
        return (f"{cls} に宣言の無い field がある: {', '.join(unknown)}\n"
                f"  このクラスは additional_properties: false（統制の中核）。"
                f"field を増やすなら schema に宣言してから書くこと。"), []
    warns = ([f"{cls} に宣言の無い field: {', '.join(unknown)} — 書けるが、projection にも "
              f"sensor にも乗らない。schema と実態が乖離している"] if unknown else [])
    return None, warns



def _now_iso():
    """writer 側の時刻。**"UNSET" を書かない。**

    受け入れ条件: timestamp は writer が付ける。クライアントが決められるなら順序を偽れるので、
    cap の時間窓を迂回できる。実データには `ts: "UNSET"` のイベントが残っており、窓で絞る
    view や sensor はそれを黙って落とすか、境界の外に置く。

    イベント `id` は (seq, class, payload) からのみ導出されるので、ここに時計が入っても
    append の決定性は損なわれない — 同じ論理イベントは同じ id になる。
    """
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _check_backfill_ts(ts):
    """backfill の時刻を検証する。**形が合っているだけでは足りない。**

    0.33.1 は正規表現だけで見ていたので、`2026-99-99T99:99:99Z` が通った（実測）。
    実日時として parse し、**未来と、遠すぎる過去を拒否する** — 順序を偽れると cap の
    時間窓を迂回できる。

    権限（誰が backfill してよいか）は identity_assurance の側の問題で、ここでは扱えない。
    **扱えないことを言う**のがこの関数の役目でもある。
    """
    import datetime as _dt
    if not isinstance(ts, str) or not re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts):
        return (f"--backfill-ts {ts!r} は ISO8601 の UTC 形式ではない"
                f"（YYYY-MM-DDTHH:MM:SSZ）。")
    try:
        when = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc)
    except ValueError as e:
        return (f"--backfill-ts {ts!r} は実在しない日時である（{e}）。\n"
                f"  形が合っているだけでは足りない — 2026-99-99T99:99:99Z のような値が"
                f"通っていた。")
    now = _dt.datetime.now(_dt.timezone.utc)
    if when > now + _dt.timedelta(minutes=5):
        return (f"--backfill-ts {ts} は未来である（いま {now.strftime('%Y-%m-%dT%H:%M:%SZ')}）。\n"
                f"  backfill は **実時点を後から補う**ためのもので、先に日付を打つ手段ではない。"
                f"未来の時刻は窓で絞る cap を迂回できる。")
    if when < now - _dt.timedelta(days=int(os.environ.get("ORG_BACKFILL_MAX_DAYS", "90"))):
        return (f"--backfill-ts {ts} は遠すぎる過去である"
                f"（{os.environ.get('ORG_BACKFILL_MAX_DAYS', '90')} 日より前）。\n"
                f"  古い時点に書くと、いま起きたことが過去の窓に入り、cap の集計から外れる。\n"
                f"  正当な理由があるなら ORG_BACKFILL_MAX_DAYS で明示的に広げること。")
    return None


def _canonical(ev):
    """The bytes the hash covers: id,seq,ts,actor,class,payload in a fixed, sorted-key form.
    Canonical JSON (sorted keys, no incidental whitespace) so the hash is reproducible."""
    core = {k: ev[k] for k in _envelope_core_keys(ev) if k in ev}
    return json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(prev_hash, ev):
    return hashlib.sha256((prev_hash + _canonical(ev)).encode("utf-8")).hexdigest()



class _LedgerLock:
    """append 全体を1つの critical section にする排他ロック。

    **これが無いと、並列 append が全て同じ seq を計算する。** 実測（監査）: 12並列で12件すべてが
    seq=1 になり、検証は seq gap/disorder で落ちた。`log を読む → seq を決める → 書く →
    HEAD を更新する` の全体が1つの操作でなければならない。

    6 worktree で並列に回している org なので、これは理論上の危険ではない。
    """

    def __init__(self, root):
        self.path = os.path.join(root, "LOCK")
        self.fh = None
        self.locked = False
        self.error = None          # ロックできなかった理由。呼び側が append を止める

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        try:
            self.fh = open(self.path, "a+")
        except Exception as e:
            self.error = f"LOCK ファイルを開けない（{e}）: {self.path}"
            return self
        # **ロックできないなら書かない。** 警告して続行すると、並列 append が同じ seq を
        # 計算して鎖が壊れる（実測: 12並列で全件 seq=1）。逃げ道は明示の環境変数だけにし、
        # **その保証（逐次実行）は道具の側では確かめられない**ことを言う。
        # 故障注入用に ORG_LEDGER_FORCE_LOCK_FAIL=1 を見る — ロックの fail-closed を
        # 検査できなければ、「fail-closed である」と言えない。
        try:
            if os.environ.get("ORG_LEDGER_FORCE_LOCK_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_LOCK_FAIL=1（故障注入）")
            import fcntl
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
            self.locked = True
        except Exception as e:
            if os.environ.get("ORG_LEDGER_ALLOW_UNLOCKED") == "1":
                print(f"ledger: ロックせずに append している"
                      f"（ORG_LEDGER_ALLOW_UNLOCKED=1、理由: {e}）。\n"
                      f"  **並列で走らせないこと。** 逐次実行の保証は道具では確かめられない。",
                      file=sys.stderr)
            else:
                self.error = (
                    f"append をロックできない（{e}）。\n"
                    f"  ロック無しの並列 append は同じ seq を計算し、鎖を壊す"
                    f"（実測: 12並列で全件 seq=1）。\n"
                    f"  逐次実行を保証できる場合のみ ORG_LEDGER_ALLOW_UNLOCKED=1 で外せる — "
                    f"**その保証は道具の側では確かめられない。**")
        return self

    def __exit__(self, *exc):
        try:
            if self.locked:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            if self.fh:
                self.fh.close()
        except Exception:
            pass
        return False


def _fsync_dir(path):
    """ディレクトリの fsync。rename の永続化はこれが無いと保証されない。

    **失敗を黙らない。** 一部の FS では不可なので append 自体は止めないが、その台帳の
    durability は best-effort である、と言わないままにしてはいけない — 電源断で HEAD の
    rename が失われうる状態を「永続化した」と読まれる。
    """
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except Exception as e:
        print(f"ledger: 注意 — ディレクトリの fsync ができなかった（{e}）。"
              f"この FS では HEAD の rename の永続化は best-effort である"
              f"（log 自体は fsync 済みで、HEAD は log から再構築できる）。", file=sys.stderr)
        return False


def _head_from_log(root):
    """log から HEAD を **再構築** する。HEAD は権威ではなく cache である。

    **log 全体が健全なときだけ再構築する。** 途中の破損（torn line、seq の飛び、hash 不一致）を
    自動修復してはいけない — 壊れた記録の上に整合した HEAD を載せると、壊れていることが
    分からなくなる。破損は fail-closed で報告する。

    返り値: (head, error). error があれば append してはいけない。
    """
    log, _ = _paths(root)
    if not os.path.isfile(log):
        return {"seq": 0, "hash": "GENESIS"}, None
    prev, expect, last = "GENESIS", 1, None
    with open(log, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            if not line.endswith("\n"):
                return None, (f"log の {lineno} 行目が改行で終わっていない（torn line — "
                              f"書き込み途中で落ちた痕跡）。**自動修復しない。** "
                              f"内容を確認して手当てすること。")
            try:
                ev = json.loads(line)
            except Exception as e:
                return None, f"log の {lineno} 行目が JSON として読めない: {e}"
            if ev.get("seq") != expect:
                return None, (f"seq の飛び／順序違反: {lineno} 行目で {expect} を期待したが "
                              f"{ev.get('seq')} だった。")
            if ev.get("prev_hash") != prev:
                return None, f"prev_hash 不一致（seq={ev.get('seq')}）— 鎖が切られている。"
            if _hash(prev, ev) != ev.get("hash"):
                return None, f"hash 不一致（seq={ev.get('seq')}）— 書き換えの痕跡。"
            prev, last, expect = ev["hash"], ev, expect + 1
    if last is None:
        return {"seq": 0, "hash": "GENESIS"}, None
    return {"seq": last["seq"], "hash": last["hash"]}, None


def _paths(root):
    return os.path.join(root, "ledger.jsonl"), os.path.join(root, "HEAD")


def _read_events(root):
    # the log path _paths(root)[0] == ledger_path(root); delegate to the shared reader.
    return read_events(root)


def _read_head(root):
    _, head = _paths(root)
    if os.path.exists(head):
        with open(head, encoding="utf-8") as f:
            return json.load(f)
    return {"seq": 0, "hash": "GENESIS"}


def _in_window(ev, since, until):
    ts = ev.get("ts", "")
    if since and ts < since:
        return False
    if until and ts > until:
        return False
    return True



def require_writer_path(op):
    """`ORG_WRITER_SOCKET` が設定された org では、**writerd を通らない書き込みを拒否する**。

    段階A（process_mediated）で強制できるのは「経路が1つであること」だけである。
    **これは OS 境界ではない** — 同じ UID の caller は daemon を止められ、この環境変数も外せる。
    したがって `workload_isolation` は `process_mediated` であって `separate_uid` ではない。

    別 UID + root 所有の socket 親ディレクトリまで揃えば、環境変数を外しても台帳のファイルに
    書けなくなる（OS 権限で失敗する）。そこで初めて境界になる。

    返り値: None なら続行してよい。文字列なら拒否の理由。
    """
    if os.environ.get("ORG_INSIDE_WRITER") == "1":
        return None                     # writerd 自身が呼んでいる
    sock = os.environ.get("ORG_WRITER_SOCKET")
    if not sock:
        return None                     # writerd を使わない org（従来どおり）
    return (f"この org は writerd 経由の書き込みだけを許している"
            f"（ORG_WRITER_SOCKET={sock}）。\n"
            f"  `{op}` を直接実行せず、writerd に送ること:\n"
            f"    python3 tools/writer_client.py {op} -- <引数…>\n"
            f"  **台帳への経路を1つにするのが目的である。** 経路が複数あると、"
            f"「検査に使う記録は検査する側だけが書ける」を強制できない。\n"
            f"  注意: これは OS 境界ではない（同一 UID なら daemon を止められる）。"
            f"workload_isolation は process_mediated である。")




def _org_and_ledger_id(root):
    """(org_id, ledger_id)。**書き込み先から取る** — payload の値は caller が書ける。

    org_id  … org の識別子（`.orgforge/ORG_ID` があればそれ、無ければ org root のハッシュ）
    ledger_id … 台帳の識別子（`<root>/LEDGER_ID` があればそれ、無ければ root のハッシュ）

    どちらも無い org では None を返し、その項目の一致検査は行わない — 既存の org を
    止めないため。**新しく作る org では書く**（`org-init` が置く）。
    """
    def _read_or_hash(path, fallback):
        if path and os.path.isfile(path):
            try:
                v = open(path, encoding="utf-8").read().strip()
                if v:
                    return v
            except OSError:
                pass
        return hashlib.sha256(os.path.abspath(fallback).encode()).hexdigest()[:16] \
            if fallback else None

    led_id = _read_or_hash(os.path.join(root, "LEDGER_ID") if root else None, root)
    org_root = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from discover import org_root as _orgroot
        org_root = _orgroot()
    except Exception:
        pass
    org_id = _read_or_hash(
        os.path.join(org_root, ".orgforge", "ORG_ID") if org_root else None, org_root)
    return org_id, led_id


def _verify_receipt_for(a, payload, cls):
    """`--receipt` を検証し、identity fields を生成する。(fields, error)。

    **環境変数の「検証済み」印は使わない。** caller が立てられるものは証拠にならない —
    実測（監査）で、`ORG_IDENTITY_VERIFIED=1` を足すだけで偽の identity が通った。

    ここで検証するのはこの道具自身であり、caller は receipt を **渡せるだけ**である。
    署名が合わなければ何も生成しない。
    """
    rc_arg = getattr(a, "receipt", None)
    if not rc_arg:
        return {}, None
    try:
        rc = json.loads(open(rc_arg, encoding="utf-8").read()) \
            if os.path.isfile(rc_arg) else json.loads(rc_arg)
    except Exception as e:
        return None, f"--receipt を読めない: {e}"
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from identity import verify_receipt, observed_recorder
    except Exception as e:
        return None, f"identity モジュールを読めない: {e}"
    # **判定の中身と receipt が一致することを確かめる。** 一致を見ないと、別の判定の receipt を
    # 持ち込んで identity だけ借りられる。
    # **receipt を、この判定に完全に束縛する。** 一部だけ見ると、見ていない項目が違う receipt を
    # 流用できる（別 org / 別 issue / 別クラスへの再利用）。
    expect = {"event_class": cls}
    for k, pk in (("verdict", "verdict"), ("role", "role"), ("lineage", "lineage"),
                  ("review_subject_id", "review_subject_id"),
                  ("reasoning_sha256", "reasoning_sha256"),
                  ("issue", "issue"), ("phase", "phase")):
        if payload.get(pk) is not None:
            expect[k] = payload[pk]
    # org / ledger は台帳の側が持つ。**payload からではなく、書き込み先から取る** —
    # payload の値は caller が書けるので、一致を確かめても意味が無い。
    _org_id, _led_id = _org_and_ledger_id(a.root)
    if _org_id:
        expect["org_id"] = _org_id
    if _led_id:
        expect["ledger_id"] = _led_id
    who, assurance, err = verify_receipt(rc, expect)
    if err:
        return None, err
    recorded_by, rec_assurance = observed_recorder()
    return {"decision_by": who, "recorded_by": recorded_by,
            "identity_assurance": assurance.get("identity_assurance"),
            "recorder_assurance": rec_assurance,
            "workload_isolation": assurance.get("workload_isolation"),
            "writer_isolation": assurance.get("writer_isolation") or "none",
            **({"signer_id": assurance["signer_id"], "key_id": assurance["key_id"]}
               if assurance.get("signer_id") else {})}, None


def cmd_append(a):
    """Append one event under the hash chain. actor is from --actor (runtime identity),
    never the payload. seq is gapless. requires_prior is enforced against real history."""
    _wp = require_writer_path("append")
    if _wp:
        print(json.dumps({"ok": False, "reason": "direct_write_refused", "detail": _wp},
                         ensure_ascii=False) if "append" != "append" else f"append: {_wp}",
              file=sys.stderr if "append" == "append" else sys.stdout)
        return 4

    try:
        payload = json.loads(a.payload)
    except json.JSONDecodeError as e:
        print(f"append: --payload is not valid JSON: {e}", file=sys.stderr)
        return 2
    if isinstance(payload, dict) and "actor" in payload:
        print("append: payload must not carry its own 'actor' — actor comes from --actor "
              "(runtime identity), never the event body (ledger-schema §envelope)", file=sys.stderr)
        return 2
    # **schema_version は writer が付ける。** クライアントが名指しできるなら、緩い版を指定して
    # 検証を素通りできる（downgrade）。payload 経由でも envelope 経由でも受け取らない。
    # 禁じるのは **版を名指しする値** だけ。`schema_id` は
    # `schema_enforcement_started` のような「スキーマ境界そのものを記録する」イベントが
    # payload に持って自然な値で、downgrade の的にはならない（版ではないので）。
    # 禁止を広く取りすぎると、記録したい事実が書けなくなる（実際に自分の epoch 記録が弾かれた）。
    # **`_nk` は payload に書かせない。** 冪等キーは道具が付ける印であって、caller が名指しする
    # ものではない。名指しできると、既存の記録と同じキーを主張して no-op を作れる
    # （＝書いたつもりで書かれていない、あるいは他人の記録を自分のものとして読ませる）。
    # **identity fields は caller が書けない。** writer（receipt を検証した経路）が生成する。
    # **caller が立てられる印を信頼しない。** 実測（監査）: `ORG_IDENTITY_VERIFIED=1` を
    # 環境に足すだけで偽の identity が通った。環境変数は caller が制御できるので、
    # 「検証済み」の証拠にならない。
    #
    # 代わりに **receipt そのものを渡させ、ここで検証する**。検証できたときだけ identity を
    # 生成する（caller が書いた identity fields は常に拒否する）。
    _IDENT = ("identity_assurance", "decision_by", "recorder_assurance", "signer_id", "key_id",
              "workload_isolation", "writer_isolation")
    if isinstance(payload, dict):
        forged = [k for k in _IDENT if k in payload]
        if forged:
            print(f"append: payload に {', '.join(forged)} を含めてはいけない — "
                  f"identity は **この道具が receipt を検証して生成する**。\n"
                  f"  **書けるものを検査に使ってはいけない。** 実測で、これらを書くだけで"
                  f"職務分離を回避でき、環境変数を足すだけでも回避できた。\n"
                  f"  judgment を記録するなら --receipt を渡すこと。", file=sys.stderr)
            return 2
    if isinstance(payload, dict) and "_nk" in payload:
        print("append: payload に '_nk' を含めてはいけない — 冪等キーは道具が付ける。"
              "caller が名指しできると、既存の記録と同じキーを主張して no-op を作れる。",
              file=sys.stderr)
        return 2
    for k in ("schema_version", "schema_sha256"):
        if isinstance(payload, dict) and k in payload:
            print(f"append: payload に {k!r} を含めてはいけない — schema の版は writer が"
                  f"決める。クライアントが名指しできると、緩い版を指定して検証を迂回できる。",
                  file=sys.stderr)
            return 2
        if getattr(a, k, None):
            print(f"append: --{k.replace('_', '-')} は受け取らない — schema の版は writer が"
                  f"決める（downgrade 防止）。", file=sys.stderr)
            return 2

    # ── idempotency (docs/11 §0 reproducibility): if a natural key is given, this event is a
    # RETRY of a logical event that must be counted once. A replayed/re-fired cycle (a hook that
    # re-fires PreToolUse, a resumed session, a crash-retry) must NOT double-append — else the
    # aggregate caps (exposure, cycles, WIP) drift with how many times the tool ran, not with the
    # spec+action. We no-op (exit 0) when (class, natural_key) already exists in history. The seq
    # counter is monotonic, so without this an identical logical event would land twice under two
    # ids — the non-idempotency the "idempotent under replay" note wrongly claimed we already had.
    #
    # **冪等 no-op は「同じ actor による同じ論理イベント」に限る。** 以前は (class, natural_key)
    # だけを見ていたため、キーさえ一致すれば **actor が違っても no-op** になり、統制
    # （DISTINCT_ACTOR / REQUIRES_PRIOR）は評価すらされなかった。実地では、gate の判定と
    # 同じキー `admission_decided-11` を maker が使うと、自己承認が「既に記録済み」として
    # exit 0 で通った。冪等性は再実行を守るための仕組みであって、統制を迂回する裏口ではない。
    # **ここから書き込みまでを1つの critical section にする。** log を読む → seq を決める →
    # 書く → HEAD を更新する、が分かれていると並列 append が同じ seq を計算する
    # （実測: 12並列で12件すべて seq=1）。
    os.makedirs(a.root, exist_ok=True)
    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(f"append: {lk.error}", file=sys.stderr)
            return 4
        # **schema は lock 内で1回だけ読む。** 検証と digest 取得が別々に読むと、その間に
        # 差し替えられる（TOCTOU）。解析結果と digest を1つの snapshot にして両方に使う。
        snap, serr = load_schema_snapshot()
        if serr:
            print(f"append: {serr}\n"
                  f"  schema の場所と PyYAML を確認すること。", file=sys.stderr)
            return 2
        # **receipt を検証して identity を生成する。** caller は receipt を渡せるだけで、
        # identity fields を書くことはできない（上で拒否済み）。
        _ident, _ierr = _verify_receipt_for(a, payload, a.cls)
        if _ierr:
            print(f"append: receipt を検証できない — {_ierr}\n"
                  f"  **検証できない receipt では identity を生成しない。**", file=sys.stderr)
            return 4
        if _ident:
            payload.update(_ident)
        elif a.cls in ("verdict_provisional", "admission_decided", "refutation_attempted",
                       "judges_disagreed"):
            # **receipt が無いときも identity を記録する — ただし `claimed` として。**
            # 欄が無いと「確かめた結果 claimed だった」のか「そもそも見ていない」のかを
            # 区別できない。書き手が生成するので、caller は値を選べない。
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from identity import observed_recorder
            _rb, _ra = observed_recorder()
            payload.update({"decision_by": a.actor, "recorded_by": _rb,
                            "identity_assurance": "claimed", "recorder_assurance": _ra,
                            "workload_isolation": "none"})

        # 新規 append だけを検証する。既存イベントに遡って適用すると移行できない。
        bad, warns = validate_event(a.cls, payload, snap)   # writer_op なし = writer 専用は拒否
        if bad:
            print(f"append: {bad}", file=sys.stderr)
            return 2
        for w in warns:
            print(f"append: 注意 — {w}", file=sys.stderr)
        # **健全性の検査を先に置く。** `_read_events` は破損で例外を投げるので、そこに入る前に
        # log を検査して、拒否理由を人が読める形で出す。トレースバックは「壊れている」ことを
        # 伝える手段としては弱く、呼び出し側（hook / organ）も扱えない。
        head, err = _head_from_log(a.root)
        if err:
            print(f"append: log が健全でないので追記しない — {err}\n"
                  f"  **壊れた記録の上に整合した HEAD を載せない。** 壊れていることが"
                  f"分からなくなる。", file=sys.stderr)
            return 4
        hist = _read_events(a.root)
        cached = _read_head(a.root)
        if cached != head and cached != {"seq": 0, "hash": "GENESIS"}:
            print(f"append: HEAD が log と食い違っていたので log から再構築した"
                  f"（HEAD={cached.get('seq')} / log={head['seq']}）— "
                  f"HEAD は cache なので log を正とする。", file=sys.stderr)

        nk = getattr(a, "natural_key", None)
        if nk:
            for e in hist:
                if e["class"] != a.cls or e.get("payload", {}).get("_nk") != nk:
                    continue
                if e.get("actor") != a.actor:
                    print(f"append: {a.cls} rejected — natural key {nk!r} は既に "
                          f"actor {e.get('actor')!r} が seq={e['seq']} で使っている。\n"
                          f"  別の actor が同じキーで書くのは再実行ではない。冪等 no-op で通すと、"
                          f"自己承認や順序違反が『既に記録済み』として統制を素通りする"
                          f"（実地で確認）。判定ごとに一意なキーを使うこと。", file=sys.stderr)
                    return 3
                # **同じキー・同じ actor でも payload が違えば再実行ではない。**
                prior_pl = {k: v for k, v in (e.get("payload") or {}).items() if k != "_nk"}
                now_pl = {k: v for k, v in payload.items() if k != "_nk"}
                if prior_pl != now_pl:
                    print(f"append: {a.cls} rejected — natural key {nk!r} は seq={e['seq']} に"
                          f"あるが、payload が違う。\n"
                          f"  同じキーで中身の違うものを書くのは再実行ではない。"
                          f"no-op で通すと、後から書いた内容が黙って捨てられる。\n"
                          f"  差し替えるなら correction を追記してからにすること。",
                          file=sys.stderr)
                    return 3
                print(f"append: idempotent no-op — {a.cls} with natural key {nk!r} "
                      f"already recorded at seq={e['seq']} id={e['id']} (docs/11 §0). "
                      f"Not re-appended.")
                return 0
            payload["_nk"] = nk
        seq = head["seq"] + 1
        eid = "e" + hashlib.sha256(
            f"{seq}:{a.cls}:{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
        ).hexdigest()[:12]
        # **ts は writer が付ける。** クライアントが決められるなら順序を偽れるので、cap の
        # 時間窓を迂回できる。`--ts` は過去の記録を補う backfill のためだけに残し、
        # **"UNSET" と不正な形は受け取らない** — 窓で絞る view や sensor が黙って落とす。
        # `--ts` は 0.33.2 で `--backfill-ts` に分離した。旧名は受け取るが、**意図を確かめる** —
        # 通常経路で時刻を指定できると、順序を偽って cap の時間窓を迂回できる。
        given = a.ts or getattr(a, "ts_legacy", None)
        ts = given or _now_iso()
        if given:
            err = _check_backfill_ts(given)
            if err:
                print(f"append: {err}", file=sys.stderr)
                return 2
        ev = {"id": eid, "seq": seq, "ts": ts, "actor": a.actor,
              "class": a.cls, "payload": payload,
              # 検証結果を統制の判定に渡す。**台帳には書かない**（hash の直前で外す）。
              "_verified_identity": _ident,
              "schema_id": "orgforge-ledger",
              "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"],
              "prev_hash": head["hash"]}
        if a.cls in REQUIRES_PRIOR and not REQUIRES_PRIOR[a.cls](ev, hist):
            why = REQUIRES_PRIOR_WHY.get(a.cls, "a required prior event does not exist")
            print(f"append: {a.cls} rejected — requires a prior event that does not exist: {why} "
                  f"(ledger-schema §event_classes {a.cls}.requires_prior)", file=sys.stderr)
            return 3
        sod = _distinct_actor_violation(ev, hist)
        if sod:
            print(f"append: {sod}", file=sys.stderr)
            return 3
        ev.pop("_verified_identity", None)   # 内部の受け渡し用。記録には残さない
        ev["hash"] = _hash(head["hash"], ev)
        log, headp = _paths(a.root)
        # append → fsync(log) → HEAD を一時ファイルへ → atomic rename → fsync(dir)
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        tmp = headp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"seq": seq, "hash": ev["hash"]}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, headp)
        _fsync_dir(a.root)
    print(f"appended seq={seq} {a.cls} id={eid} hash={ev['hash'][:12]}…")
    return 0





def _yaml_block_span(text, key):
    """トップレベルの `key:` ブロックの (start, end) を行境界で返す。無ければ None。

    正規表現で `\nkey:\n(?:(?:  |\n).*\n)*` と書くと、**次のトップレベルキーの前にある
    コメント行や、そのブロックの子行まで飲み込む**。実際に validation の置換が
    `event_classes:` を丸ごと消した（YAML が読めるので気づきにくい）。

    ブロックの終わりは「インデントの無い次の行」で決める — それが YAML の構造である。
    """
    lines = text.split("\n")
    start = None
    for i, l in enumerate(lines):
        if l == f"{key}:" or l.startswith(f"{key}:"):
            if not l[0].isspace():
                start = i
                break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        l = lines[j]
        if l and not l[0].isspace():          # 次のトップレベル（コメントも含む）
            end = j
            break
    off = lambda n: sum(len(x) + 1 for x in lines[:n])
    return off(start), off(end)


def _deep_add(dst, src, path=""):
    """`src` にあって `dst` に無いものだけを足す。**dst 独自のものは必ず残す。**

    設定の修復は「追加」でなければならない。ブロックごと置き換えると、org が自分で足した
    厳格規則が消える — それは修復ではなく退行である（実測: org の
    `required.progress_recorded: [milestone]` が置換で失われた）。

    同じ path に違う **スカラー値** があるときは、自動で上書きしない。org が意図して変えたのか、
    テンプレートが変わったのかは道具では判別できないので、conflict として報告して人に決めさせる。

    返り値: (merged, conflicts)
    """
    conflicts = []
    if isinstance(dst, dict) and isinstance(src, dict):
        out = dict(dst)
        for k, sv in src.items():
            here = f"{path}.{k}" if path else str(k)
            if k not in out:
                out[k] = sv
                continue
            dv = out[k]
            if isinstance(dv, dict) and isinstance(sv, dict):
                out[k], c = _deep_add(dv, sv, here)
                conflicts += c
            elif isinstance(dv, list) and isinstance(sv, list):
                # list は集合として足す（org が足した要素を落とさない）。順序はテンプレート優先。
                out[k] = sv + [x for x in dv if x not in sv]
            elif dv != sv:
                conflicts.append(f"{here}: org={dv!r} / テンプレート={sv!r}")
        return out, conflicts
    if isinstance(dst, list) and isinstance(src, list):
        return src + [x for x in dst if x not in src], conflicts
    if dst != src:
        conflicts.append(f"{path}: org={dst!r} / テンプレート={src!r}")
    return dst, conflicts


def cmd_schema(a):
    """org の ledger-schema.yaml とプラグインのテンプレートの差分を診断し、必要なら埋める。

    ## なぜこれが要るか（H8: schema rollout skew）

    org は自分の `ledger-schema.yaml` を持つ（org が自分の形式を所有するため）。プラグインが
    新しいイベントクラスを増やしても、**org のコピーは古いまま**になる。そこに「宣言の無い
    クラスは書けない」検査を入れると、**更新直後に org の記録が止まる**。

    実測: ある org の schema はプラグインより4クラス古く、うち2つ（`correction` 12件、
    `asset_touched` 3件）は実データで使われていた。schema を配らずに検査を入れれば、
    その org は訂正を書けなくなる。

    **これは fail-closed ではなく、既知の移行不備による可用性事故である。** だから
    「検査を入れる前に診断できること」「明示的に移行できること」を道具として持つ。
    """
    here = os.path.dirname(os.path.abspath(__file__))    # ledger.py はローカルに here を作る流儀
    plug_p = os.path.join(here, "..", "template", "ledger-schema.yaml")
    if not os.path.isfile(plug_p):
        plug_p = os.path.join(here, "template", "ledger-schema.yaml")
    org_p = _schema_path()
    if not org_p or not os.path.isfile(org_p):
        print("org の ledger-schema.yaml が見つからない。", file=sys.stderr)
        return 2
    if os.path.abspath(org_p) == os.path.abspath(plug_p):
        print("この org はプラグインのテンプレートを直接使っている — skew は起こらない。")
        return 0
    try:
        import yaml
        plug = yaml.safe_load(open(plug_p, encoding="utf-8")) or {}
        org = yaml.safe_load(open(org_p, encoding="utf-8")) or {}
    except Exception as e:
        print(f"schema を解析できない: {e}", file=sys.stderr)
        return 2

    pc = set((plug.get("event_classes") or {}).keys())
    oc = set((org.get("event_classes") or {}).keys())
    missing = sorted(pc - oc)
    # **validation の中身も比べる。** 「ブロックの有無」だけを見ていたので、org 側で
    # `verdict_provisional` の required を削っても「差分なし」と判定した（監査が実証）。
    # 検証規則が欠けていることは、クラスが欠けていることと同じくらい静かに効く。
    pv, ov = plug.get("validation") or {}, org.get("validation") or {}
    # **欠落と衝突を1つの計算から出す。** 別々に判定すると、片方だけ検出して片方を見落とす
    # （実測: 欠落だけを見ていたので、org が型名を変えていた衝突が --fix に入らず報告もされなかった）。
    _merged, vconf = _deep_add(ov, pv, path="validation")
    vgaps = []
    for sect in ("required", "require_any", "enums", "types"):
        pd, od = pv.get(sect) or {}, ov.get(sect) or {}
        for cls_, spec in pd.items():
            if cls_ not in od:
                vgaps.append(f"validation.{sect}.{cls_} が無い")
            elif isinstance(spec, (list, dict)) and isinstance(od.get(cls_), (list, dict)):
                lost = sorted(set(spec) - set(od[cls_]))
                if lost:
                    vgaps.append(f"validation.{sect}.{cls_} に {', '.join(map(str, lost))} が無い")
    for cls_ in (pv.get("additional_properties_false") or []):
        if cls_ not in (ov.get("additional_properties_false") or []):
            vgaps.append(f"validation.additional_properties_false に {cls_} が無い")

    # **実データで使われているかを言う。** 使われているクラスが欠けているなら、検査を入れた
    # 瞬間にその記録が止まる — 緊急度が違う。
    used = set()
    try:
        for e in read_events(a.root):
            used.add(e.get("class"))
    except Exception:
        pass

    print(f"org schema : {org_p}")
    print(f"テンプレート: {plug_p}")
    print(f"  org {len(oc)} クラス / テンプレート {len(pc)} クラス")
    if not missing and not vgaps and not vconf:
        print("  差分なし — この org の schema は最新である"
              "（クラス宣言と validation 規則の両方）。")
        return 0

    if missing:
        print(f"\n**org に無いクラス: {len(missing)}**")
        for c in missing:
            mark = "  ← 実データで使用中。**このクラスの記録が止まる**" if c in used else ""
            print(f"    {c}{mark}")
    if vconf:
        print(f"\n**validation 規則の衝突: {len(vconf)}** — 自動では直さない。")
        for c in vconf:
            print(f"    {c}")
        print("  同じ path に違う値がある。org が意図して変えたのか、テンプレートが変わったのかは"
              "道具では判別できない。**手で決めること。**")
    if vgaps:
        print(f"\n**validation 規則の欠落: {len(vgaps)}**")
        for g in vgaps[:20]:
            print(f"    {g}")
        if len(vgaps) > 20:
            print(f"    …他 {len(vgaps) - 20} 件")
        print("  検証規則が欠けていることは、クラスが欠けていることと同じくらい静かに効く — "
              "拒否されるべき記録が通る。")

    if not a.fix:
        print(f"\n埋めるには --fix を付けて実行すること:\n"
              f'    python3 "{os.path.join(here, "ledger.py")}" schema --fix\n'
              f"  **既存の宣言は書き換えない。** 足りないものを足すだけである — org が自分で"
              f"変えた宣言（実態に合わせた形）を上書きしてはいけない。")
        return 1

    # ── --fix: 足りないクラスと validation を **追加するだけ** ──────────────
    src = open(plug_p, encoding="utf-8").read()
    dst = open(org_p, encoding="utf-8").read()
    added = []
    for c in missing:
        m = re.search(rf"\n((?:  #[^\n]*\n)*  {re.escape(c)}:.*?)(?=\n  [a-z_]+:|\n  # ──|\n[a-z_]+:)",
                      src, re.S)
        if not m:
            print(f"  警告: {c} の宣言をテンプレートから取り出せなかった（手で足すこと）",
                  file=sys.stderr)
            continue
        # event_classes の末尾に足す（既存の宣言には触らない）
        anchor = "\ntriggers:"
        if anchor not in dst:
            print("  警告: 挿入位置（triggers:）が見つからない", file=sys.stderr)
            break
        dst = dst.replace(anchor, "\n" + m.group(1).rstrip() + "\n" + anchor, 1)
        added.append(c)
    conflicts = vconf
    if vgaps or vconf:
        # **deep-add でマージする。** ブロックごと差し替えると、org 独自の厳格規則が消える
        # （実測: org が足した `required.progress_recorded: [milestone]` が --fix で失われた）。
        # org 所有の安全規則を弱めるのは、修復ではなく退行である。
        #
        #   欠けている key / list 要素だけを足す
        #   org 側の追加規則は必ず残す
        #   同じ path で値が違うなら **自動で上書きせず conflict として報告する**
        merged = _merged
        if conflicts:
            print(f"\n**衝突: {len(conflicts)}** — 自動では直さない。", file=sys.stderr)
            for c in conflicts:
                print(f"    {c}", file=sys.stderr)
            print("  同じ path に違う値がある。org が意図して変えたのか、テンプレートが"
                  "変わったのかは道具では判別できない。**手で決めること。**", file=sys.stderr)
        if merged != ov:
            # YAML として書き直すのは validation ブロックだけに限る。event_classes は
            # コメントが規律の説明そのものなので、再 serialize で失いたくない。
            try:
                import yaml as _y
                block = _y.dump({"validation": merged}, sort_keys=False,
                                allow_unicode=True, default_flow_style=False, width=100)
            except Exception as e:
                print(f"validation を書き出せない: {e}", file=sys.stderr)
                return 3
            span = _yaml_block_span(dst, "validation")
            if span is None:
                dst = dst.replace("\nevent_classes:", "\n" + block + "\nevent_classes:", 1)
            else:
                dst = dst[:span[0]] + block + dst[span[1]:]
            added.append(f"validation 規則（{len(vgaps)} 件を deep-add。org 独自の規則は保存）")

    # **atomic write。** 直接上書きすると、修復途中で止まったときに schema を壊す — org の
    # 形式定義が壊れれば、その org は何も書けなくなる。temp → fsync → rename → fsync(dir)。
    tmp_p = org_p + ".tmp"
    with open(tmp_p, "w", encoding="utf-8") as f:
        f.write(dst)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_p, org_p)
    _fsync_dir(os.path.dirname(os.path.abspath(org_p)))
    print(f"\n足した: {', '.join(added)}\n"
          f"  **--fix の exit 0 を preflight 成功と読まないこと。** 修復したあとに"
          f"通常の診断（--fix なし）が exit 0 を返すことを確かめる:\n"
          f'    python3 "{os.path.join(here, "ledger.py")}" schema\n'
          f"  衝突が残っていれば --fix は 0 を返しても差分は残っている。\n"
          f"  **クラス宣言は足すだけ**で、既存のものは書き換えていない — org が実態に合わせて"
          f"変えた宣言はそのままである。\n"
          + ("  **validation 規則は deep-add した** — org が自分で足した厳格規則は残っている。"
             "同じ path で値が違うものは上書きせず、衝突として報告した。\n"
             if any("validation" in x for x in added) else ""))
    return 0



def cmd_reserve_exposure(a):
    """**書けた判断だけが allow になる。** cap の検査と予約を1つの writer 操作にする。

    ## なぜ二段構成では足りないか

    0.33.x までは organ が「集計して判断して LEDGER-EVENT を印字」し、hook が「その後で
    append（失敗は無視）」していた。そこには3つの穴がある:

      1. 集計と判断が lock の外なので、**並列の hook が同じ committed を読んで両方 allow**
         してから順に append できる。合計が cap を超える。
      2. append の失敗を無視するので、allow したのに曝露が記録されない。**次の呼び出しは
         committed=0 を見る**ので、cap は記憶を失った per-action 検査に退化する。
      3. hold は deny して終わるので、**止めたことが記録に残らない**。

    ここでは lock の中で
    schema snapshot → 履歴検証 → 冪等性照合 → 現在の曝露を算出 → allow/hold 判断 →
    予約 event の append + fsync
    を一操作として行い、**予約が永続化された後にだけ allow を返す**。

    ## caller から受け取らないもの

    - `committed_so_far` — writer が数える。caller が渡せるなら、少なく申告して cap を通れる。
    - 時刻 — writer が付ける。`--backfill-ts` も隠し `--ts` も **この操作には定義しない**。
      通常台帳の backfill 権限は identity の側（H1）に残すが、cap 予約に持ち込んではいけない。

    ## 冪等キー

    `(session_id, tool_use_id, rule, event_class)`。`tool_use_id` 単独では、別 session・別 rule の
    衝突を防げない。**欠落していれば metered action を deny する** — 同一性を確かめられないなら、
    hook の再実行を二重計上しないという保証が成り立たない。
    """
    _wp = require_writer_path("reserve-exposure")
    if _wp:
        print(json.dumps({"ok": False, "reason": "direct_write_refused", "detail": _wp},
                         ensure_ascii=False) if "reserve-exposure" != "append" else f"reserve-exposure: {_wp}",
              file=sys.stderr if "reserve-exposure" == "append" else sys.stdout)
        return 4

    for k in ("session_id", "tool_use_id", "rule"):
        if not (getattr(a, k, None) or "").strip():
            print(json.dumps({"decision": "deny", "reason": f"missing_{k}",
                              "detail": f"--{k.replace('_', '-')} が無い。冪等キーは "
                                        f"(session_id, tool_use_id, rule, event_class) で、"
                                        f"欠けていると hook の再実行を二重計上しない保証が"
                                        f"成り立たない。metered action は通さない。"},
                             ensure_ascii=False))
            return 3

    # **入力の検証を先に。** 負・NaN・inf の delta は上限の判定を壊す（負なら合計を減らせる）。
    for name, val, ok in (
            ("--delta", a.delta, lambda v: v == v and v > 0 and v != float("inf")),
            ("--cap", a.cap, lambda v: v == v and v >= 0 and v != float("inf"))):
        try:
            if not ok(float(val)):
                raise ValueError
        except (TypeError, ValueError):
            print(json.dumps({"decision": "deny", "reason": "invalid_request",
                              "detail": f"{name}={val!r} は使えない。delta は有限かつ正、"
                                        f"cap は有限かつ非負でなければならない — 負や NaN を"
                                        f"通すと合計を減らして上限を迂回できる。"},
                             ensure_ascii=False))
            return 3

    # 冪等キーは **canonical tuple の hash**。区切り文字で連結すると、値に区切り文字が
    # 入ったときに別のキーと衝突する（"a|b" + "c" と "a" + "b|c" が同じになる）。
    nk = "reserve:" + hashlib.sha256(json.dumps(
        ["exposure_budget_checked", a.session_id, a.tool_use_id, a.rule],
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]
    # 要求内容の digest。**同じキーで内容が違う要求は再実行ではない。**
    req_digest = hashlib.sha256(json.dumps(
        {"dimension": a.dimension, "delta": float(a.delta), "cap": float(a.cap),
         "window_since": a.window_since or "", "actor": a.actor},
        sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]
    os.makedirs(a.root, exist_ok=True)
    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(json.dumps({"decision": "deny", "reason": "lock_failed",
                              "detail": lk.error}, ensure_ascii=False))
            return 4

        snap, serr = load_schema_snapshot()
        if serr:
            print(json.dumps({"decision": "deny", "reason": "schema_unreadable",
                              "detail": serr}, ensure_ascii=False))
            return 4

        head, herr = _head_from_log(a.root)
        if herr:
            print(json.dumps({"decision": "deny", "reason": "ledger_unhealthy",
                              "detail": herr}, ensure_ascii=False))
            return 4

        try:
            hist = _read_events(a.root)
        except Exception as e:
            print(json.dumps({"decision": "deny", "reason": "ledger_unreadable",
                              "detail": str(e)}, ensure_ascii=False))
            return 4

        # 冪等性 — 同じ (session, tool_use, rule) の予約が既にあるなら、その判断を返す。
        # hook が再実行されても二重計上しない。
        for e in hist:
            if e.get("class") != "exposure_budget_checked":
                continue
            if (e.get("payload") or {}).get("_nk") != nk:
                continue
            prior = e["payload"]
            # **exact retry だけが再実行である。** 同じキーで内容が違う要求を通すと、
            # delta=1 の allow を根拠に delta=100 が通る（実測でそうなった）。
            if prior.get("request_digest") != req_digest:
                print(json.dumps(
                    {"decision": "deny", "reason": "idempotency_key_reused_with_different_request",
                     "detail": f"同じ冪等キー（session/tool_use/rule）が seq={e.get('seq')} で"
                               f"別の要求に使われている。dimension / delta / cap / window / actor の"
                               f"どれかが違う要求は再実行ではない。",
                     "prior": {"dimension": prior.get("dimension"),
                               "delta_requested": prior.get("delta_requested"),
                               "cap": prior.get("cap")},
                     "now": {"dimension": a.dimension, "delta": a.delta, "cap": a.cap}},
                    ensure_ascii=False))
                return 3
            print(json.dumps({"decision": prior.get("decision"), "reason": "idempotent_replay",
                              "seq": e.get("seq"), "committed_so_far": prior.get("committed_so_far"),
                              "delta_requested": prior.get("delta_requested"),
                              "cap": prior.get("cap")}, ensure_ascii=False))
            return 0 if prior.get("decision") == "allow" else 10

        # **writer が数える。** caller の申告は受け取らない。
        voided = set()
        try:
            voided = set(corrected_seqs(hist))
        except Exception:
            pass
        committed = 0.0
        for e in hist:
            if e.get("class") != "exposure_budget_checked" or e.get("seq") in voided:
                continue
            p = e.get("payload") or {}
            if p.get("dimension") != a.dimension or p.get("decision") != "allow":
                continue
            if a.window_since and str(e.get("ts", "")) < a.window_since:
                continue
            try:
                dv = float(p.get("delta_requested"))
                # **負・NaN・inf の過去の曝露を数えない。** 数えると合計を減らせる／比較が壊れる。
                if not (dv == dv) or dv < 0 or dv in (float("inf"), float("-inf")):
                    raise ValueError(f"delta_requested={dv!r}")
                committed += dv
            except (TypeError, ValueError):
                # 壊れた曝露記録は 0 として数えず、**deny する** — 合計が実際より小さく見える。
                print(json.dumps({"decision": "deny", "reason": "malformed_prior_exposure",
                                  "detail": f"seq={e.get('seq')} の delta_requested が数値でない"
                                            f"（{p.get('delta_requested')!r}）。合計が実際より"
                                            f"小さく見えるので通さない。"}, ensure_ascii=False))
                return 4

        would_be = committed + a.delta
        decision = "allow" if would_be <= a.cap else "hold"
        payload = {"window_id": a.window_since or "all", "dimension": a.dimension,
                   "committed_so_far": committed, "delta_requested": a.delta, "cap": a.cap,
                   "actor_role": a.actor, "decision": decision,
                   "caused_by_event": a.caused_by,
                   "session_id": a.session_id, "tool_use_id": a.tool_use_id, "rule": a.rule,
                   "request_digest": req_digest, "_nk": nk}

        bad, warns = validate_event("exposure_budget_checked", payload, snap,
                                    writer_op="exposure_budget_checked")
        if bad:
            print(json.dumps({"decision": "deny", "reason": "schema_rejected",
                              "detail": bad}, ensure_ascii=False))
            return 4
        for w in warns:
            print(f"reserve-exposure: 注意 — {w}", file=sys.stderr)

        ev = {"id": "e" + hashlib.sha256(
                  f"{head['seq'] + 1}:exposure_budget_checked:"
                  f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
              ).hexdigest()[:12],
              "seq": head["seq"] + 1, "ts": _now_iso(), "actor": a.actor,
              "class": "exposure_budget_checked", "payload": payload,
              "schema_id": "orgforge-ledger", "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"], "prev_hash": head["hash"]}
        ev["hash"] = _hash(head["hash"], ev)

        log, headp = _paths(a.root)
        # 途中で失敗したら、書いた分を切り戻す位置。**deny したのに曝露が残る**と、次の予約が
        # それを数える（過大計上）。それは安全側だが正確ではなく、上限が実際より早く尽きる。
        prior_size = os.path.getsize(log) if os.path.exists(log) else 0
        try:
            # 故障注入。**書けなかったら allow にならない**ことを検査できなければ、
            # 「書けた判断だけが allow になる」とは言えない（fail-closed は故障注入で示す）。
            if os.environ.get("ORG_LEDGER_FORCE_APPEND_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_APPEND_FAIL=1（故障注入）")
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                if os.environ.get("ORG_LEDGER_FORCE_FSYNC_FAIL") == "1":
                    raise OSError("ORG_LEDGER_FORCE_FSYNC_FAIL=1（故障注入）")
                os.fsync(f.fileno())
            tmp = headp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": ev["seq"], "hash": ev["hash"]}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, headp)
            _fsync_dir(a.root)
        except Exception as e:
            # 書きかけを切り戻す。lock の中なので、他の書き手は割り込んでいない。
            try:
                if os.path.exists(log) and os.path.getsize(log) > prior_size:
                    with open(log, "r+b") as f:
                        f.truncate(prior_size)
                        f.flush()
                        os.fsync(f.fileno())
            except Exception as te:
                print(f"reserve-exposure: 書きかけを切り戻せなかった（{te}）。"
                      f"台帳に未確定の行が残っている可能性がある — `ledger verify` で確認すること。",
                      file=sys.stderr)
            # **書けなかったら allow を返さない。** hold の記録に失敗した場合も deny である
            # （記録できない hold を allow に読み替えるのが、いちばん危ない誤りである）。
            print(json.dumps({"decision": "deny", "reason": "reservation_not_persisted",
                              "detail": f"予約を永続化できなかった（{e}）。"
                                        f"**書けた判断だけが allow になる。**"},
                             ensure_ascii=False))
            return 4

    out = {"decision": decision, "reason": "reserved", "seq": ev["seq"],
           "committed_so_far": committed, "delta_requested": a.delta, "cap": a.cap,
           "would_be": would_be}
    print(json.dumps(out, ensure_ascii=False))
    if decision == "hold":
        print(f"HOLD: {a.dimension} committed {committed} + requested {a.delta} = {would_be} "
              f"> cap {a.cap}。**hold は記録済み（seq={ev['seq']}）** — 止めたことが残る。",
              file=sys.stderr)
        return 10
    return 0



HALT_LATCH = "HALT"          # <ledger-root>/HALT — 台帳が読めなくても止まる第二経路


def active_halt(root):
    """いま halt しているか。(halt_event | None, error | None) を返す。

    **2つの経路を見る。**

      1. 台帳の `halt_tripped`（正）— 対応する `halt_released` が無いものが active
      2. `<root>/HALT` ラッチ（保険）— 台帳が読めないときにも止まるため

    台帳を読めないときは **halt とみなす**（error を返す）。読めないことを「halt していない」と
    読むのは、いちばん危ない fail-open である — 止まっているかどうか分からないなら、止める。

    ラッチは台帳の代わりではない。手でラッチを消しても台帳の halt は残るので、hook は止め続ける。
    逆に台帳が読めなくてもラッチがあれば止まる。**どちらかが止めていれば止まる。**
    """
    latch = os.path.join(root, HALT_LATCH) if root else None
    latched = bool(latch and os.path.exists(latch))
    try:
        evs = read_events(root)
    except Exception as e:
        # 読めないなら止める。ラッチの有無に関わらず。
        return ({"reason": f"台帳を読めないので halt とみなす: {e}", "source": "unreadable"},
                str(e))
    released = set()
    for e in evs:
        if e.get("class") == "halt_released":
            s = (e.get("payload") or {}).get("releases_seq")
            if isinstance(s, int):
                released.add(s)
    for e in reversed(evs):
        if e.get("class") == "halt_tripped" and e.get("seq") not in released:
            return {**(e.get("payload") or {}), "seq": e.get("seq"),
                    "actor": e.get("actor"), "source": "ledger"}, None
    if latched:
        # 台帳に active な halt が無いのにラッチがある。**ラッチを信じて止める** —
        # halt を書けなかった（fail-open になりかけた）痕跡である可能性がある。
        return ({"reason": "HALT ラッチが存在するが、台帳に対応する halt_tripped が無い。"
                          "halt の記録に失敗した痕跡かもしれない。手で確かめること。",
                 "source": "latch_only"}, None)
    return None, None


def cmd_trip_halt(a):
    """halt を発動する。**記録できなければ、その呼び出し自体を deny する。**

    「記録できないなら宣言しない」は記録としては正しいが、**制御としては fail-open** になる —
    止めるべき状況で止まらない。だから:

      1. 先に `<root>/HALT` ラッチを書く（台帳より先。台帳が壊れていても止まる）
      2. 台帳に `halt_tripped` を書く
      3. どちらかが失敗したら **非ゼロで返す** — 呼び出し側はその行為を通してはいけない

    ラッチが残って台帳が空になった場合、`active_halt` は `latch_only` として halt を報告する。
    **止まりすぎる方向の失敗**であり、それが正しい向きである。
    """
    _wp = require_writer_path("trip-halt")
    if _wp:
        print(json.dumps({"ok": False, "reason": "direct_write_refused", "detail": _wp},
                         ensure_ascii=False) if "trip-halt" != "append" else f"trip-halt: {_wp}",
              file=sys.stderr if "trip-halt" == "append" else sys.stdout)
        return 4

    if not (a.reason or "").strip():
        print(json.dumps({"halted": False, "reason": "missing_reason",
                          "detail": "--reason が必要。なぜ止めたのかが記録されない halt は、"
                                    "解除の判断ができない。"}, ensure_ascii=False))
        return 2
    os.makedirs(a.root, exist_ok=True)
    latch_path = os.path.join(a.root, HALT_LATCH)
    latch_ok = False
    try:
        # **ラッチを先に書く。** 台帳の追記に失敗しても、次の呼び出しは止まる。
        with open(latch_path, "w", encoding="utf-8") as f:
            json.dump({"trigger": a.trigger, "scope": a.scope, "reason": a.reason,
                       "tripped_by": a.tripped_by}, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        _fsync_dir(a.root)
        latch_ok = True
    except Exception as e:
        print(f"trip-halt: HALT ラッチを書けなかった（{e}）。", file=sys.stderr)

    payload = {"trigger": a.trigger, "scope": a.scope, "reason": a.reason,
               "tripped_by": a.tripped_by, "latch_written": latch_ok}
    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(json.dumps({"halted": latch_ok, "reason": "lock_failed",
                              "latch_written": latch_ok, "detail": lk.error},
                             ensure_ascii=False))
            return 4
        snap, serr = load_schema_snapshot()
        if serr:
            print(json.dumps({"halted": latch_ok, "reason": "schema_unreadable",
                              "latch_written": latch_ok, "detail": serr}, ensure_ascii=False))
            return 4
        bad, _w = validate_event("halt_tripped", payload, snap, writer_op="halt_tripped")
        if bad:
            print(json.dumps({"halted": latch_ok, "reason": "schema_rejected",
                              "latch_written": latch_ok, "detail": bad}, ensure_ascii=False))
            return 4
        head, herr = _head_from_log(a.root)
        if herr:
            # 台帳が壊れていても **ラッチは書けている** ので、次の呼び出しは止まる。
            print(json.dumps({"halted": latch_ok, "reason": "ledger_unhealthy",
                              "latch_written": latch_ok, "detail": herr},
                             ensure_ascii=False))
            return 4
        ev = {"id": "e" + hashlib.sha256(
                  f"{head['seq'] + 1}:halt_tripped:"
                  f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
              ).hexdigest()[:12],
              "seq": head["seq"] + 1, "ts": _now_iso(), "actor": a.tripped_by,
              "class": "halt_tripped", "payload": payload,
              "schema_id": "orgforge-ledger", "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"], "prev_hash": head["hash"]}
        ev["hash"] = _hash(head["hash"], ev)
        log, headp = _paths(a.root)
        try:
            # 故障注入。**halt が書けなかったときに何が起きるか**を検査できなければ、
            # 「記録できない halt は fail-open にならない」とは言えない。
            if os.environ.get("ORG_LEDGER_FORCE_APPEND_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_APPEND_FAIL=1（故障注入）")
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp = headp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": ev["seq"], "hash": ev["hash"]}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, headp)
            _fsync_dir(a.root)
        except Exception as e:
            print(json.dumps({"halted": latch_ok, "reason": "halt_not_persisted",
                              "latch_written": latch_ok,
                              "detail": f"台帳に halt を書けなかった（{e}）。"
                                        f"ラッチ={'あり' if latch_ok else 'なし'}。"},
                             ensure_ascii=False))
            return 4
    print(json.dumps({"halted": True, "reason": "tripped", "seq": ev["seq"],
                      "latch_written": latch_ok}, ensure_ascii=False))
    print(f"HALT tripped (seq={ev['seq']}): {a.reason}\n"
          f"  gated な行為はすべて止まる。観測・検証・安全な修復だけが通る。\n"
          f"  **解除は H4a では実装していない** — trip した主体と独立した承認が要り、それは"
          f"identity の認証（H1）に依存する。\n"
          f"  いま解除するには、台帳に halt_released を書ける仕組みが必要である"
          f"（writer 専用として宣言済み、操作は未実装）。", file=sys.stderr)
    return 0



def cmd_release_halt(a):
    """halt を解除する。**止めた主体とは独立した principal の署名が必要（H4b）。**

    ## 順序が重要である

      1. active halt を確認する（無ければ解除するものが無い）
      2. **独立した release principal** を receipt で検証する
         - 非対称鍵であること（共有鍵は「別主体」を証明しない）
         - `may_release_halt` を認可されていること
         - **halt を発動した主体と別であること**
      3. 復旧の証拠を検証する（`--recovery-verified` の中身が空なら拒否）
      4. `halt_released` を append + fsync
      5. **その後で初めて** HALT ラッチを消す
      6. ラッチの削除に失敗したら **停止を維持する**（消せないなら止まったままにする）

    逆順にすると、ラッチを消したあとに台帳への追記が失敗して **halt が消えたまま記録が無い**
    状態になる。それは「止まっていたのに、止まっていた証拠も止まっている状態も無い」である。
    """
    _wp = require_writer_path("release-halt")
    if _wp:
        print(json.dumps({"ok": False, "reason": "direct_write_refused", "detail": _wp},
                         ensure_ascii=False) if "release-halt" != "append" else f"release-halt: {_wp}",
              file=sys.stderr if "release-halt" == "append" else sys.stdout)
        return 4

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from identity import verify_receipt, observed_recorder

    halt, herr = active_halt(a.root)
    if not halt:
        print(json.dumps({"released": False, "reason": "no_active_halt"}, ensure_ascii=False))
        return 2
    if not (a.recovery_verified or "").strip():
        print(json.dumps({"released": False, "reason": "missing_recovery_evidence",
                          "detail": "--recovery-verified が必要。**何を確かめて復旧したのか**が"
                                    "記録されない解除は、解除の判断を後から検証できない。"},
                         ensure_ascii=False))
        return 2
    try:
        rc = json.loads(open(a.receipt, encoding="utf-8").read()) \
            if os.path.isfile(a.receipt) else json.loads(a.receipt)
    except Exception as e:
        print(json.dumps({"released": False, "reason": "receipt_unreadable",
                          "detail": str(e)}, ensure_ascii=False))
        return 2

    # **解除の receipt は halt の seq に束縛する。** 束縛しないと、別の halt の解除 receipt を
    # 持ち込んで使える（再利用）。
    expect = {"review_subject_id": f"halt:{halt.get('seq')}", "role": "release",
              "verdict": "release", "lineage": "release"}
    released_by, ident, rerr = verify_receipt(rc, expect, expect_release=True)
    if rerr:
        print(json.dumps({"released": False, "reason": "receipt_rejected", "detail": rerr},
                         ensure_ascii=False))
        return 4
    if ident.get("identity_assurance") != "authenticated":
        print(json.dumps({"released": False, "reason": "not_authenticated",
                          "detail": f"解除には authenticated な identity が必要"
                                    f"（いま {ident.get('identity_assurance')!r}）。\n"
                                    f"  共有鍵は「鍵が違う」ことしか示さず、"
                                    f"**別主体・独立した承認を証明しない。**"},
                         ensure_ascii=False))
        return 4
    # **止めた主体が自分で解除できてはいけない。**
    tripped_by = halt.get("tripped_by")
    if tripped_by and released_by == tripped_by:
        print(json.dumps({"released": False, "reason": "not_independent",
                          "detail": f"halt を発動した主体（{tripped_by}）が自分で解除しようと"
                                    f"している。**独立した承認が要る。**"}, ensure_ascii=False))
        return 4

    recorded_by, rec_assurance = observed_recorder()
    payload = {"releases_seq": halt.get("seq"), "reason": a.reason,
               "released_by": released_by, "recovery_verified": a.recovery_verified,
               "tripped_by": tripped_by,
               "identity_assurance": ident.get("identity_assurance"),
               "recorded_by": recorded_by, "recorder_assurance": rec_assurance,
               "signer_id": ident.get("signer_id"), "key_id": ident.get("key_id")}

    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(json.dumps({"released": False, "reason": "lock_failed",
                              "detail": lk.error}, ensure_ascii=False))
            return 4
        snap, serr = load_schema_snapshot()
        if serr:
            print(json.dumps({"released": False, "reason": "schema_unreadable",
                              "detail": serr}, ensure_ascii=False))
            return 4
        bad, _w = validate_event("halt_released", payload, snap, writer_op="halt_released")
        if bad:
            print(json.dumps({"released": False, "reason": "schema_rejected",
                              "detail": bad}, ensure_ascii=False))
            return 4
        head, hh = _head_from_log(a.root)
        if hh:
            print(json.dumps({"released": False, "reason": "ledger_unhealthy",
                              "detail": hh}, ensure_ascii=False))
            return 4
        ev = {"id": "e" + hashlib.sha256(
                  f"{head['seq'] + 1}:halt_released:"
                  f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
              ).hexdigest()[:12],
              "seq": head["seq"] + 1, "ts": _now_iso(), "actor": released_by,
              "class": "halt_released", "payload": payload,
              "schema_id": "orgforge-ledger", "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"], "prev_hash": head["hash"]}
        ev["hash"] = _hash(head["hash"], ev)
        log, headp = _paths(a.root)
        prior_size = os.path.getsize(log) if os.path.exists(log) else 0
        try:
            # 故障注入。**記録できていないのに停止が解けることが、いちばん危ない fail-open**
            # である。故障を再現できなければ「停止を維持する」とは言えない。
            if os.environ.get("ORG_LEDGER_FORCE_APPEND_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_APPEND_FAIL=1（故障注入）")
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp = headp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": ev["seq"], "hash": ev["hash"]}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, headp)
            _fsync_dir(a.root)
        except Exception as e:
            try:
                if os.path.exists(log) and os.path.getsize(log) > prior_size:
                    with open(log, "r+b") as f:
                        f.truncate(prior_size)
                        f.flush()
                        os.fsync(f.fileno())
            except Exception:
                pass
            print(json.dumps({"released": False, "reason": "release_not_persisted",
                              "detail": f"解除を記録できなかった（{e}）。**停止は維持される。**"},
                             ensure_ascii=False))
            return 4

        # **記録できてから、初めてラッチを消す。** 逆順にすると、ラッチを消したあとに追記が
        # 失敗して「止まっていた証拠も、止まっている状態も無い」状態になる。
        latch = os.path.join(a.root, HALT_LATCH)
        latch_cleared = True
        if os.path.exists(latch):
            try:
                os.unlink(latch)
                _fsync_dir(a.root)
            except Exception as e:
                latch_cleared = False
                print(f"release-halt: ラッチを消せなかった（{e}）。**停止は維持される** — "
                      f"台帳の解除は記録済みなので、同じ receipt で再実行すれば後片付けだけが"
                      f"行われる（exact retry は安全）。", file=sys.stderr)

    print(json.dumps({"released": latch_cleared, "reason": "released" if latch_cleared
                      else "recorded_but_latch_remains",
                      "seq": ev["seq"], "releases_seq": halt.get("seq"),
                      "released_by": released_by, "tripped_by": tripped_by,
                      "identity_assurance": ident.get("identity_assurance")},
                     ensure_ascii=False))
    return 0 if latch_cleared else 4


def cmd_halt_status(a):
    """halt しているかを報告する。**観測は halt 中でも通る。**"""
    h, err = active_halt(a.root)
    if h is None:
        print(json.dumps({"halted": False}, ensure_ascii=False))
        return 0
    print(json.dumps({"halted": True, "source": h.get("source"),
                      "seq": h.get("seq"), "reason": h.get("reason"),
                      "tripped_by": h.get("tripped_by"), "trigger": h.get("trigger"),
                      "scope": h.get("scope")}, ensure_ascii=False))
    return 10



def cmd_derive_admission(a):
    """**2件の認証済み provisional から admission を生成する。** writer の専用操作。

    ## なぜ専用操作にするのか

    joint admission は「2つの判定が一致した」という **事実の関数**であって、新しい判断ではない。
    したがって judge の receipt は存在しない — それを generic append で書こうとすると、
    `require_attested_identity` が「receipt が無い」として拒否し、**一致しても admission を
    作れないデッドロック**になる。

    ここでは台帳の中の2件を読んで検証する:
      - 同じ issue / event / subject であること
      - verdict が一致していること
      - **両方が認証済み**であること（claimed の判定からは joint を作らない）
      - 血統が異なること（same-harness と cross-harness）

    生成する identity は `system:joint(...)` であり、**judge の identity ではない** —
    誰かの判断として記録しない。
    """
    with _LedgerLock(a.root) as lk:
        if lk.error:
            print(json.dumps({"ok": False, "reason": "lock_failed", "detail": lk.error},
                             ensure_ascii=False))
            return 4
        snap, serr = load_schema_snapshot()
        if serr:
            print(json.dumps({"ok": False, "reason": "schema_unreadable", "detail": serr},
                             ensure_ascii=False))
            return 4
        head, herr = _head_from_log(a.root)
        if herr:
            print(json.dumps({"ok": False, "reason": "ledger_unhealthy", "detail": herr},
                             ensure_ascii=False))
            return 4
        try:
            evs = _read_events(a.root)
        except Exception as e:
            print(json.dumps({"ok": False, "reason": "ledger_unreadable", "detail": str(e)},
                             ensure_ascii=False))
            return 4
        voided = set(corrected_seqs(evs)) | set(corrected_seqs(evs, kinds=("superseded",)))
        found = {}
        for e in evs:
            if e.get("class") != "verdict_provisional" or e.get("seq") in voided:
                continue
            pl = e.get("payload") or {}
            if str(pl.get("issue", "")).lstrip("#") != str(a.issue).lstrip("#"):
                continue
            if pl.get("for_event") != a.event:
                continue
            found[pl.get("lineage")] = {**pl, "seq": e.get("seq")}
        if len(found) < 2:
            print(json.dumps({"ok": False, "reason": "not_enough_verdicts",
                              "detail": f"#{a.issue} / {a.event} の provisional が "
                                        f"{len(found)} 件しかない（血統: {sorted(found)}）。"
                                        f"2血統が揃ってから生成すること。"}, ensure_ascii=False))
            return 3
        subs = {v.get("review_subject_id") for v in found.values()}
        if len(subs) != 1:
            print(json.dumps({"ok": False, "reason": "subject_mismatch",
                              "detail": f"2件が別の対象を見ている: {sorted(map(str, subs))}"},
                             ensure_ascii=False))
            return 3
        verdicts = {v.get("verdict") for v in found.values()}
        if len(verdicts) != 1:
            print(json.dumps({"ok": False, "reason": "verdicts_disagree",
                              "detail": f"一致していない: {sorted(map(str, verdicts))}。"
                                        f"**片方でも否なら否である。**"}, ensure_ascii=False))
            return 5
        # **両方が認証済みでなければ joint を作らない。** claimed の判定から作ると、
        # 「一致した」という事実に、確かめていない identity の重みが乗る。
        weak = {lin: v.get("identity_assurance") or "claimed" for lin, v in found.items()
                if (v.get("identity_assurance") or "claimed") == "claimed"}
        if weak and a.require_attested:
            print(json.dumps({"ok": False, "reason": "unattested_verdicts",
                              "detail": f"identity が claimed の判定がある: {weak}。"
                                        f"**確かめていない identity から joint を作らない。**"},
                             ensure_ascii=False))
            return 4
        # **独立性も writer が判定する。** 2件の signer / key / workload は台帳にあるので、
        # 呼び出し側の申告を待つ必要が無い。
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from identity import reviewer_independence
            _a, _b = list(found.values())
            independence = reviewer_independence(
                _a.get("decision_by"),
                {"signer_id": _a.get("signer_id"), "key_id": _a.get("key_id"),
                 "workload_isolation": _a.get("workload_isolation") or "none"},
                {"signer_id": _b.get("signer_id"), "key_id": _b.get("key_id"),
                 "workload_isolation": _b.get("workload_isolation") or "none"})
        except Exception:
            independence = "same_signer"        # 判定できないなら最も弱い方に倒す
        lineages = sorted(found)
        pair = {lin: {"seq": v["seq"], "reasoning_sha256": v.get("reasoning_sha256"),
                      "reasoning_ref": v.get("reasoning_ref")} for lin, v in found.items()}
        joint_digest = hashlib.sha256(json.dumps(
            {k: v["reasoning_sha256"] for k, v in sorted(pair.items())},
            sort_keys=True).encode("utf-8")).hexdigest()
        order = ["claimed", "observed", "attested", "authenticated"]
        payload = {"issue": a.issue, "deliverable": str(a.issue),
                   "verdict": list(verdicts)[0], "lineage": "joint",
                   "agreed_by": lineages, "review_subject_id": list(subs)[0],
                   "reviewer_independence": independence,
                   "from_seqs": sorted(v["seq"] for v in found.values()),
                   "reasoning_by_lineage": pair, "reasoning_sha256": joint_digest,
                   "agreed_identity_assurance": min(
                       (v.get("identity_assurance") or "claimed" for v in found.values()),
                       key=order.index),
                   # **judge の identity ではない。** 誰かの判断として記録しない。
                   "decision_by": f"system:joint({','.join(lineages)})",
                   "recorded_by": "system:writer", "identity_assurance": "derived",
                   "recorder_assurance": "observed", "workload_isolation": "none"}
        bad, _w = validate_event(a.event, payload, snap, writer_op=a.event)
        if bad:
            print(json.dumps({"ok": False, "reason": "schema_rejected", "detail": bad},
                             ensure_ascii=False))
            return 4
        ev = {"id": "e" + hashlib.sha256(
                  f"{head['seq'] + 1}:{a.event}:"
                  f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
              ).hexdigest()[:12],
              "seq": head["seq"] + 1, "ts": _now_iso(), "actor": "system:writer",
              "class": a.event, "payload": payload,
              "schema_id": "orgforge-ledger", "schema_version": LEDGER_SCHEMA_VERSION,
              "schema_sha256": snap["digest"], "prev_hash": head["hash"]}
        ev["hash"] = _hash(head["hash"], ev)
        log, headp = _paths(a.root)
        prior = os.path.getsize(log) if os.path.exists(log) else 0
        try:
            # 故障注入。**書けなかったら生成しない**ことを検査できなければ、そう言えない。
            if os.environ.get("ORG_LEDGER_FORCE_APPEND_FAIL") == "1":
                raise OSError("ORG_LEDGER_FORCE_APPEND_FAIL=1（故障注入）")
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp = headp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"seq": ev["seq"], "hash": ev["hash"]}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, headp)
            _fsync_dir(a.root)
        except Exception as e:
            try:
                if os.path.exists(log) and os.path.getsize(log) > prior:
                    with open(log, "r+b") as f:
                        f.truncate(prior)
                        f.flush()
                        os.fsync(f.fileno())
            except Exception:
                pass
            print(json.dumps({"ok": False, "reason": "not_persisted", "detail": str(e)},
                             ensure_ascii=False))
            return 4
    print(json.dumps({"ok": True, "reason": "derived", "seq": ev["seq"],
                      "verdict": payload["verdict"], "from_seqs": payload["from_seqs"],
                      "reviewer_independence": independence,
                      "agreed_identity_assurance": payload["agreed_identity_assurance"]},
                     ensure_ascii=False))
    return 0


def cmd_verify(a):
    """Replay the whole chain from GENESIS — the external watchdog's core primitive. Reports
    the FIRST break (edited line, reordered seq, or forged hash). Exit 1 if the chain is broken."""
    try:
        events = _read_events(a.root)
    except LedgerCorruption as c:
        # a non-JSON line IS tamper evidence — report BROKEN, do not crash with a traceback
        print(f"BROKEN: malformed (non-JSON) content at ledger line {c.lineno} — the append-only "
              f"log was edited to something that isn't a valid event (tamper evidence)",
              file=sys.stderr)
        return 1
    prev = "GENESIS"
    expect_seq = 1
    validated = legacy = 0
    vsnap, drift = None, set()
    for ev in events:
        if ev["seq"] != expect_seq:
            print(f"BROKEN: seq gap/disorder at line — expected seq {expect_seq}, got {ev['seq']}",
                  file=sys.stderr)
            return 1
        if ev["prev_hash"] != prev:
            print(f"BROKEN: prev_hash mismatch at seq {ev['seq']} — chain was cut/reordered",
                  file=sys.stderr)
            return 1
        if _hash(prev, ev) != ev["hash"]:
            print(f"BROKEN: hash mismatch at seq {ev['seq']} — event {ev['id']} was edited "
                  f"after it was written (tamper evidence)", file=sys.stderr)
            return 1
        # 条件6: **version 別の validator を再実行する。** 鎖が通っていることは「書き換えられて
        # いない」ことしか言わず、「schema に沿っている」ことは言わない。version を持つ
        # イベントだけを検証する — legacy に遡って適用すると移行できない。
        v = ev.get("schema_version")
        if v:
            if v > LEDGER_SCHEMA_VERSION:
                print(f"BROKEN: seq {ev['seq']} は未知の schema_version {v} "
                      f"（この writer は v{LEDGER_SCHEMA_VERSION} まで）。"
                      f"新しい版で書かれた台帳を古い道具で読んでいる。", file=sys.stderr)
                return 1
            if vsnap is None:
                vsnap, verr = load_schema_snapshot()
                if verr:
                    print(f"BROKEN: schema を読めないので v{v} の検証ができない — {verr}",
                          file=sys.stderr)
                    return 1
            # **記録時の digest を照合する。** 記録された schema_sha256 と、いま読んでいる
            # schema の digest が違うなら、形式が入れ替わっている。検証が「いまの schema に
            # 沿っているか」しか言えないなら、記録時に何で検証したのかは失われる。
            rec = ev.get("schema_sha256")
            if rec and rec != vsnap["digest"]:
                drift.add(rec)
            # **verify では writer_only を検査しない。** これは「誰が書いたか」の検査で、
            # append の時点でしか行えない（経路は記録に残らない）。既に書かれた予約を
            # 「generic append では書けない」と拒否すると、正しい台帳が壊れていると報告される。
            bad, _w = validate_event(ev.get("class"), ev.get("payload"), vsnap,
                                     writer_op=ev.get("class"))
            if bad:
                print(f"BROKEN: seq {ev['seq']} が v{v} の検証を通らない — {bad}",
                      file=sys.stderr)
                return 1
            validated += 1
        else:
            legacy += 1
        prev = ev["hash"]
        expect_seq += 1
    if validated or legacy:
        # **2つの保証を混ぜない。** schema 検証済みかと actor 認証済みかは独立した性質である。
        if drift:
            print(f"注意: {len(drift)} 種類の schema digest で記録されたイベントがある "
                  f"（いまの schema は {vsnap['digest'][:12]}…）。\n"
                  f"  形式が入れ替わっている — 再検証は **いまの schema** に対して行われた。"
                  f"記録時に何で検証したのかは、その版の schema が無ければ再現できない。",
                  file=sys.stderr)
        print(f"validation_assurance: validated:v{LEDGER_SCHEMA_VERSION} {validated} 件 / "
              f"legacy_unvalidated {legacy} 件"
              + ("\n  legacy は読めるが、schema 検証済みとしては扱わない"
                 "（遡って拒否すると移行できない）。" if legacy else ""))
    head = _read_head(a.root)
    if head["hash"] != prev:
        print(f"BROKEN: HEAD hash {head['hash'][:12]}… does not match chain tip {prev[:12]}…",
              file=sys.stderr)
        return 1
    print(f"chain intact: {len(events)} event(s), tip {prev[:12]}… — hash chain replays clean")
    return 0


def cmd_view(a):
    """Project a derived view — a DETERMINISTIC function of the events it derives from
    (ledger-schema §views). Context packs may contain only views; this is how they're built."""
    views = _view_from()
    if a.view_id not in views:
        known = ", ".join(sorted(views)) or "(ledger-schema.yaml が読めない)"
        print(f"view: unknown view '{a.view_id}'. known: {known}", file=sys.stderr)
        return 2
    classes = ["*"] if a.view_id in _ALL_CLASS_VIEWS else views[a.view_id]
    events = [e for e in _read_events(a.root)
              if _in_window(e, a.since, a.until)
              and (classes == ["*"] or e["class"] in classes)]
    if a.view_id in ("ledger_census", "recent_ledger_census"):
        counts = {}
        for e in events:
            counts[e["class"]] = counts.get(e["class"], 0) + 1
        print(json.dumps({"view": a.view_id, "counts": dict(sorted(counts.items()))},
                         indent=2, ensure_ascii=False))
        return 0
    if a.view_id == "work_in_progress":
        # RESOLVE (not raw rows): candidates started but not completed, each with its LATEST progress
        # checkpoint. This is the recovery source after a context wipe — the SessionStart hook and
        # /org-resume read it to answer "what was this role mid-way through, and what's the next step?"
        started, completed, latest = {}, set(), {}
        for e in events:
            cid = e["payload"].get("candidate_id")
            if not cid:
                continue
            if e["class"] == "cycle_started":
                started[cid] = {"candidate_id": cid, "role": e["payload"].get("role"),
                                "started_seq": e["seq"]}
            elif e["class"] == "cycle_completed":
                completed.add(cid)
            elif e["class"] == "progress_recorded":
                latest[cid] = {k: e["payload"].get(k) for k in
                               ("fraction", "phase", "done_so_far", "next_step", "blocked_by", "artifacts")}
        wip = [{**started[cid], "progress": latest.get(cid)}
               for cid in started if cid not in completed]
        wip.sort(key=lambda w: w["started_seq"])
        print(json.dumps({"view": "work_in_progress", "in_progress": wip}, indent=2, ensure_ascii=False))
        return 0
    # generic projection: the events feeding the view, newest last, payloads intact.
    rows = [{"seq": e["seq"], "ts": e.get("ts", ""), "class": e["class"], "payload": e["payload"]}
            for e in events]
    print(json.dumps({"view": a.view_id, "from": classes, "rows": rows},
                     indent=2, ensure_ascii=False))
    return 0


def cmd_census(a):
    events = [e for e in _read_events(a.root) if _in_window(e, a.since, a.until)]
    counts = {}
    for e in events:
        counts[e["class"]] = counts.get(e["class"], 0) + 1
    print(json.dumps({"window": {"since": a.since, "until": a.until},
                      "total": len(events), "census": dict(sorted(counts.items()))},
                     indent=2, ensure_ascii=False))
    return 0


def cmd_digest(a):
    """The deterministic digest (ledger-schema §digest): same window + same ledger ⇒
    byte-identical output. Census is mandatory and UNCURATED; sections are exact projections."""
    since, until = a.window_since, a.window_until
    events = [e for e in _read_events(a.root) if _in_window(e, since, until)]
    census = {}
    for e in events:
        census[e["class"]] = census.get(e["class"], 0) + 1
    reorg = [e["payload"] for e in events if e["class"] == "move_executed"]
    filed = {e["payload"].get("dedup_key") or e["seq"]: e["payload"]
             for e in events if e["class"] == "proposal_filed"}
    decided = {e["payload"].get("proposal_id") for e in events
               if e["class"] == "proposal_adjudicated"}
    open_props = [p for k, p in filed.items() if k not in decided]
    staged = {e["payload"].get("staged_id") or e["seq"]: e["payload"]
              for e in events if e["class"] == "irreversible_staged"}
    executed = {e["payload"].get("staged_id") for e in events
                if e["class"] == "irreversible_executed"}
    held = [p for k, p in staged.items() if k not in executed]
    anomalies = [e["payload"] for e in events if e["class"] == "anomaly_detected"]
    budget = {}
    for e in events:
        if e["class"] == "cycle_completed":
            role = e["payload"].get("role", "?")
            toks = e["payload"].get("tokens", {})
            b = budget.setdefault(role, {"task": 0, "gate": 0, "reporting": 0})
            for k in ("task", "gate", "reporting"):
                b[k] += toks.get(k, 0)
    digest = {
        "window": {"since": since, "until": until},
        "census": dict(sorted(census.items())),          # mandatory, uncurated
        "reorg_commits": reorg,
        "open_proposals": open_props,
        "held_irreversibles": held,
        "anomalies": anomalies,
        "budget_report": dict(sorted(budget.items())),
    }
    # deterministic: sorted keys, fixed separators — re-runnable to a byte-identical result.
    print(json.dumps(digest, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


def cmd_cat(a):
    for e in _read_events(a.root):
        if a.cls and e["class"] != a.cls:
            continue
        if a.actor and e["actor"] != a.actor:
            continue
        print(json.dumps(e, ensure_ascii=False))
    return 0



def _banner():
    """実行しているバージョンと cwd を stderr に1行（docs/11 — 古いパスの流用に気づくため）。"""
    ver = "?"
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, "..", ".claude-plugin", "plugin.json"),
              os.path.join(here, "..", "integrations", "claude-code",
                           ".claude-plugin", "plugin.json")):
        try:
            with open(c, encoding="utf-8") as f:
                ver = json.load(f).get("version", "?")
            break
        except Exception:
            continue
    # **機械可読な出力を汚さない。** stderr に書いていても、消費側が 2>&1 で混ぜると JSON が
    # 壊れる（実地でテストが JSONDecodeError で落ちた）。view / census / digest は JSON を返す
    # サブコマンドなので、`--json` の有無に関わらず黙る。人間向けの補助のために、機械が読む
    # 出力を壊すのは筋が通らない。
    _MACHINE = ("view", "census", "digest", "cat")
    if (os.environ.get("ORG_QUIET") or "--json" in sys.argv
            or any(m in sys.argv[1:2] for m in _MACHINE)):
        return
    print(f"[orgforge {ver} @ {os.getcwd()}]", file=sys.stderr)


def main(argv):
    p = argparse.ArgumentParser(prog="ledger", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("append"); q.set_defaults(fn=cmd_append)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")
    q.add_argument("--actor", required=True)
    q.add_argument("--class", dest="cls", required=True)
    q.add_argument("--payload", required=True)
    # **通常の append で時刻を指定させない。** 時刻は writer が付ける（順序を偽れないように）。
    # 実時点を後から補う backfill だけが別経路で、**意図を名前に出す**。
    q.add_argument("--backfill-ts", dest="ts", default=None, metavar="TS",
                   help="実時点を後から補う場合の時刻（ISO8601 UTC）。通常は渡さない — "
                        "時刻は writer が付ける。未来や遠い過去は拒否される")
    q.add_argument("--ts", dest="ts_legacy", default=None, help=argparse.SUPPRESS)
    # **judgment を記録するなら receipt を渡す。** この道具が検証し、identity fields を生成する。
    # 環境変数の印は受け取らない — caller が立てられるものは証拠にならない。
    q.add_argument("--receipt", default=None,
                   help="judge が署名した receipt（ファイルか JSON）。検証できたときだけ "
                        "identity fields が生成される")
    # cap 予約は writer 側の専用操作。**時刻の引数を定義しない** — cap 予約に backfill を
    # 持ち込むと、窓の外に予約を置いて上限を迂回できる。
    rx = sub.add_parser("reserve-exposure",
                        help="cap を検査して予約を1操作で書く（書けた判断だけが allow）")
    rx.add_argument("root", nargs="?", default=None)
    rx.add_argument("--dimension", required=True)
    rx.add_argument("--delta", type=float, required=True)
    rx.add_argument("--cap", type=float, required=True)
    rx.add_argument("--actor", required=True)
    rx.add_argument("--window-since", dest="window_since")
    rx.add_argument("--caused-by", dest="caused_by")
    # 冪等キー。**欠けていれば metered action を deny する。**
    rx.add_argument("--session-id", dest="session_id", required=True)
    rx.add_argument("--tool-use-id", dest="tool_use_id", required=True)
    rx.add_argument("--rule", required=True)
    rx.set_defaults(fn=cmd_reserve_exposure)
    # **2件の認証済み provisional から admission を生成する。** judge の receipt は存在しない
    # （一致は判断ではなく事実の関数）ので、専用操作にする — generic append では
    # 「receipt が無い」として拒否され、一致してもデッドロックする。
    da = sub.add_parser("derive-admission",
                        help="2血統の一致から admission を生成する（writer 専用）")
    da.add_argument("root", nargs="?", default=None)
    da.add_argument("--issue", required=True)
    da.add_argument("--event", required=True,
                    choices=("admission_decided", "refutation_attempted"))
    da.add_argument("--require-attested", dest="require_attested", action="store_true",
                    help="claimed の判定からは生成しない")
    da.set_defaults(fn=cmd_derive_admission)
    # HALT。**writer 専用の操作。** 記録できなければ非ゼロで返す（呼び出し側は通さない）。
    th = sub.add_parser("trip-halt", help="halt を発動する（ラッチ→台帳の順に書く）")
    th.add_argument("root", nargs="?", default=None)
    th.add_argument("--trigger", required=True, help="何が halt を引き起こしたか")
    th.add_argument("--scope", default="global", choices=("global", "role"))
    th.add_argument("--reason", required=True, help="なぜ止めたのか（解除の判断に使う）")
    th.add_argument("--tripped-by", dest="tripped_by", required=True)
    th.set_defaults(fn=cmd_trip_halt)
    rh = sub.add_parser("release-halt",
                        help="halt を解除する（**独立した principal の非対称署名が必要**）")
    rh.add_argument("root", nargs="?", default=None)
    rh.add_argument("--receipt", required=True,
                    help="解除の receipt。may_release_halt を認可された **非対称** 鍵で署名し、"
                         "halt の seq に束縛されていること")
    rh.add_argument("--reason", required=True, help="なぜ解除してよいと判断したのか")
    rh.add_argument("--recovery-verified", dest="recovery_verified", required=True,
                    help="**何を確かめて復旧したのか**（実行したコマンドと出力）")
    rh.set_defaults(fn=cmd_release_halt)
    hs = sub.add_parser("halt-status", help="halt しているかを報告する（観測なので halt 中も通る）")
    hs.add_argument("root", nargs="?", default=None)
    hs.set_defaults(fn=cmd_halt_status)
    s = sub.add_parser("schema",
                       help="org の schema とテンプレートの差分を診断する（--fix で埋める）")
    s.add_argument("root", nargs="?", default=None)
    s.add_argument("--fix", action="store_true", help="足りないクラス／validation を追加する")
    s.set_defaults(fn=cmd_schema)
    q.add_argument("--natural-key", dest="natural_key",
                   help="idempotency key: if a prior event of this class carries the same key, "
                        "this append is a no-op (docs/11 §0 — replay/retry must count once)")

    q = sub.add_parser("verify"); q.set_defaults(fn=cmd_verify)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")

    q = sub.add_parser("view"); q.set_defaults(fn=cmd_view)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)"); q.add_argument("view_id")
    q.add_argument("--since"); q.add_argument("--until")

    q = sub.add_parser("census"); q.set_defaults(fn=cmd_census)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)"); q.add_argument("--since"); q.add_argument("--until")

    q = sub.add_parser("digest"); q.set_defaults(fn=cmd_digest)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")
    q.add_argument("--window-since", dest="window_since")
    q.add_argument("--window-until", dest="window_until")

    q = sub.add_parser("cat"); q.set_defaults(fn=cmd_cat)
    q.add_argument("root", nargs="?", help="ledger root (省略時はカレントから自動発見: .orgforge/ledger)")
    q.add_argument("--class", dest="cls"); q.add_argument("--actor")

    a = p.parse_args(argv[1:])
    _banner()
    # root は省略可能: 省略時はカレントから自動発見する（.envrc 不要 — tools/discover.py）
    if hasattr(a, "root"):
        a.root = resolve_root(a.root)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
