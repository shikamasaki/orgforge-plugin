#!/usr/bin/env python3
"""identity — 判断した主体・記録した主体・確定した主体を分ける（H1）。

**このモジュールが提供するのは Compatibility Mode である。** `decision_by` は検証済みの
receipt からのみ設定され、CLI の自己申告では設定できない。しかし鍵は同じ利用者が読める場所に
あり、writer も差し替えられるので、**`authenticated` は名乗らない** — 得られるのは
`attested` までである。

Authenticated Mode（隔離 writer・限定された経路・鍵の保護・principal ごとの認可）は別の変更。
"""

import hashlib
import json
import os
import sys


# ══ Identity: 3つの主体と4つの保証軸（H1）════════════════════════════════════
#
# **`actor` は3つの概念を混ぜていた。** 判断した主体・記録した主体・確定した主体は別物である。
# 監督が judge の判定を代理で記録する運用では、観測される actor は常に監督なので、
# `actor` 同士を比べる職務分離は「監督が監督を承認していない」しか言えない。
#
# **重要な限界。** ここで実装するのは Compatibility Mode である:
#
#   - `decision_by` は **検証済み receipt からのみ** 設定される（CLI では設定できない）
#   - しかし鍵は同じ利用者が読める場所にあり、writer も差し替えられる
#   - したがって `identity_assurance` は最良でも `attested` で、**`authenticated` ではない**
#   - **別プロセスで問い合わせることは信頼境界ではない。** 隔離 writer・限定経路・鍵の保護・
#     principal ごとの認可が揃って初めて `authenticated` と呼べる
#
# 「署名されているから独立している」は誤りである。**同じ signer が両方の血統に署名できるなら、
# それは独立レビューではない** — だから `reviewer_independence` を別軸として持つ。

PROTOCOL_VERSION = 1                 # receipt の形式。ledger の schema_version とは別に動く
_RECEIPT_BOUND = ("receipt_id", "org_id", "ledger_id", "review_subject_id", "issue", "role",
                  "phase", "lineage", "verdict", "requirements_digest", "reasoning_sha256",
                  "signer_id", "key_id", "issued_at", "schema_version", "protocol_version")


def _trust_store_path():
    """信頼する signer の鍵。`ORG_TRUST_STORE` → org の `.orgforge/trust/keys.json`。"""
    env = os.environ.get("ORG_TRUST_STORE")
    if env:
        return env
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from discover import org_root
        root = org_root()
    except Exception:
        return None
    return os.path.join(root, ".orgforge", "trust", "keys.json") if root else None


def load_trust_store():
    """(store, error)。**読めなければ error を返す** — 読めないことを「信頼できる」と読まない。

    形: {"keys": {"<key_id>": {"signer_id": …, "secret": …, "revoked": false}}}

    `secret` は HMAC の共有鍵である。**これは公開鍵署名ではない** — 検証する側が署名も作れる。
    したがってこの store で得られるのは `attested`（申告より強いが、認証ではない）までで、
    `authenticated` を名乗ってはいけない。非対称鍵と鍵の保護は Authenticated Mode の仕事である。
    """
    path = _trust_store_path()
    if not path or not os.path.isfile(path):
        return None, (f"trust store が無い（探した先: {path}）。receipt を検証できないので、"
                      f"判断の主体は `claimed` のままになる。")
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        return None, f"trust store を読めない: {e}"
    keys = doc.get("keys")
    if not isinstance(keys, dict):
        return None, "trust store に keys がない（または map でない）。"
    return {"keys": keys, "path": path}, None


def receipt_signing_bytes(receipt):
    """署名が覆うバイト列。**束縛する値を1つでも外すと、そこは差し替え可能になる。**"""
    core = {k: receipt.get(k) for k in _RECEIPT_BOUND}
    return json.dumps(core, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sign_receipt(receipt, secret):
    import hmac
    return "hmac-sha256:" + hmac.new(secret.encode("utf-8"),
                                     receipt_signing_bytes(receipt), hashlib.sha256).hexdigest()


def verify_receipt(receipt, expect, store=None):
    """receipt を検証する。(decision_by, assurance, error) を返す。

    `expect` は **この判定が何についてのものか**（org_id / ledger_id / review_subject_id /
    issue / role / lineage / verdict）。**receipt がそれと一致しなければ拒否する** — 一致を
    確かめないと、別の org・別の対象・別の血統の receipt を持ち込んで通せる（再利用）。
    """
    import hmac
    if not isinstance(receipt, dict):
        return None, None, "receipt が map でない。"
    for k in _RECEIPT_BOUND:
        if receipt.get(k) in (None, ""):
            return None, None, f"receipt に {k} が無い。束縛していない値は差し替えられる。"
    if receipt.get("protocol_version") != PROTOCOL_VERSION:
        return None, None, (f"receipt の protocol_version が {receipt.get('protocol_version')!r}"
                            f"（この検証器は v{PROTOCOL_VERSION}）。未知の版は検証できない。")
    for k, v in (expect or {}).items():
        if str(receipt.get(k)) != str(v):
            return None, None, (f"receipt の {k} が一致しない: receipt={receipt.get(k)!r} / "
                                f"この判定={v!r}。\n"
                                f"  **別の org / 対象 / 血統の receipt を再利用できてはいけない。**")
    if store is None:
        store, serr = load_trust_store()
        if serr:
            return None, None, serr
    key = (store["keys"] or {}).get(receipt["key_id"])
    if not key:
        return None, None, f"key_id {receipt['key_id']!r} は trust store に無い。"
    if key.get("revoked"):
        return None, None, (f"key_id {receipt['key_id']!r} は失効している"
                            f"（{key.get('revoked_reason') or '理由の記録なし'}）。"
                            f"失効した鍵の receipt は受け付けない。")
    if key.get("signer_id") and key["signer_id"] != receipt["signer_id"]:
        return None, None, (f"signer_id が鍵の登録と一致しない: receipt="
                            f"{receipt['signer_id']!r} / store={key['signer_id']!r}")
    secret = key.get("secret")
    if not secret:
        return None, None, f"key_id {receipt['key_id']!r} に secret が無い。"
    if not hmac.compare_digest(sign_receipt(receipt, secret), str(receipt.get("signature") or "")):
        return None, None, "receipt の署名が一致しない（内容が書き換えられているか、鍵が違う）。"
    # **assurance を単一値に潰さない。** 共有鍵の HMAC で得られるのは attested まで。
    assurance = {
        "identity_assurance": "attested",
        "workload_isolation": "none",          # 同じ UID / 同じ鍵を読める限り none
        "signer_id": receipt["signer_id"],
        "key_id": receipt["key_id"],
    }
    return receipt["signer_id"], assurance, None


def observed_recorder():
    """`recorded_by` を **観測** する。申告ではない（が、認証でもない）。

    hook が渡す session / agent の識別子、または実行環境から取る。取れなければ
    `unknown` を返し、`recorder_assurance` は `claimed` に落ちる。
    """
    for k in ("ORG_SESSION_ID", "CLAUDE_SESSION_ID", "CODEX_SESSION_ID"):
        v = os.environ.get(k)
        if v:
            return f"session:{v}", "observed"
    v = os.environ.get("ORG_ROLE")
    if v:
        return f"role:{v}", "claimed"          # 自己申告。observed とは呼ばない
    return "unknown", "claimed"


def reviewer_independence(decision_by, assurance, peer_assurance):
    """2つの判定の独立性を **別軸として** 判定する。

    **署名されていても、同じ signer が両方を作れるなら独立レビューではない。**
    同じ鍵、同じ process なら、血統を分けたことの意味は失われる。
    """
    if not (assurance and peer_assurance):
        return "same_signer"                   # 分からないなら最も弱い方に倒す
    if assurance.get("signer_id") == peer_assurance.get("signer_id"):
        return "same_signer"
    if assurance.get("key_id") == peer_assurance.get("key_id"):
        return "same_signer"
    iso = {assurance.get("workload_isolation"), peer_assurance.get("workload_isolation")}
    if iso and iso != {"none"} and "none" not in iso:
        return "distinct_workload"
    return "distinct_signer"


def _cmd_keygen(a):
    """trust store に鍵を登録する。**共有鍵なので、これは attested までである。**"""
    import secrets
    path = a.store or _trust_store_path()
    if not path:
        print("trust store の場所が決まらない（--store か ORG_TRUST_STORE）", file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    doc = {"keys": {}}
    if os.path.isfile(path):
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print(f"既存の trust store を読めない（上書きしない）: {e}", file=sys.stderr)
            return 2
    doc.setdefault("keys", {})[a.key_id] = {"signer_id": a.signer_id,
                                            "secret": secrets.token_hex(32), "revoked": False}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    print(f"registered key_id={a.key_id} signer_id={a.signer_id} in {path}\n"
          f"  **共有鍵である。** 検証する側が署名も作れるので、これで得られるのは `attested` まで。\n"
          f"  同じ利用者がこのファイルを読める限り `authenticated` ではない。")
    return 0


def _cmd_revoke(a):
    path = a.store or _trust_store_path()
    if not path or not os.path.isfile(path):
        print(f"trust store が無い: {path}", file=sys.stderr)
        return 2
    doc = json.load(open(path, encoding="utf-8"))
    k = (doc.get("keys") or {}).get(a.key_id)
    if not k:
        print(f"key_id {a.key_id!r} が無い", file=sys.stderr)
        return 2
    k["revoked"] = True
    k["revoked_reason"] = a.reason
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    print(f"revoked key_id={a.key_id}: {a.reason}")
    return 0


def _cmd_receipt(a):
    """judge が自分の判断に署名する。**監督はこれを運ぶだけ。**"""
    store, err = load_trust_store()
    if err:
        print(f"receipt: {err}", file=sys.stderr)
        return 2
    key = (store["keys"] or {}).get(a.key_id)
    if not key or not key.get("secret"):
        print(f"receipt: key_id {a.key_id!r} が trust store に無い", file=sys.stderr)
        return 2
    if key.get("revoked"):
        print(f"receipt: key_id {a.key_id!r} は失効している", file=sys.stderr)
        return 2
    r = {"receipt_id": hashlib.sha256(
             f"{a.org_id}|{a.subject}|{a.issue}|{a.role}|{a.lineage}|{a.verdict}"
             f"|{a.reasoning_sha256}|{a.key_id}|{a.issued_at}".encode()).hexdigest()[:32],
         "org_id": a.org_id, "ledger_id": a.ledger_id,
         "review_subject_id": a.subject, "issue": a.issue, "role": a.role, "phase": a.phase,
         "lineage": a.lineage, "verdict": a.verdict,
         "requirements_digest": a.requirements_digest,
         "reasoning_sha256": a.reasoning_sha256,
         "signer_id": key.get("signer_id") or a.key_id, "key_id": a.key_id,
         "issued_at": a.issued_at, "schema_version": a.schema_version,
         "protocol_version": PROTOCOL_VERSION}
    r["signature"] = sign_receipt(r, key["secret"])
    print(json.dumps(r, ensure_ascii=False))
    return 0


def main(argv):
    import argparse
    p = argparse.ArgumentParser(
        prog="identity",
        description="判断した主体・記録した主体・確定した主体を分ける（H1、Compatibility Mode）")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("keygen", help="trust store に鍵を登録する（共有鍵 = attested まで）")
    q.add_argument("--key-id", dest="key_id", required=True)
    q.add_argument("--signer-id", dest="signer_id", required=True)
    q.add_argument("--store", default=None)
    q.set_defaults(fn=_cmd_keygen)
    q = sub.add_parser("revoke", help="鍵を失効させる")
    q.add_argument("--key-id", dest="key_id", required=True)
    q.add_argument("--reason", required=True)
    q.add_argument("--store", default=None)
    q.set_defaults(fn=_cmd_revoke)
    q = sub.add_parser("receipt", help="判断に署名する（judge が使う）")
    for f in ("org-id", "ledger-id", "subject", "role", "lineage", "verdict",
              "reasoning-sha256", "issued-at", "key-id"):
        q.add_argument(f"--{f}", dest=f.replace("-", "_"), required=True)
    q.add_argument("--issue", required=True)
    q.add_argument("--phase", default="")
    q.add_argument("--requirements-digest", dest="requirements_digest", default="")
    q.add_argument("--schema-version", dest="schema_version", type=int, default=1)
    q.set_defaults(fn=_cmd_receipt)
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
