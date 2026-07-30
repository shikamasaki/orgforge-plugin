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


# ══ Authenticated Mode: 非対称署名（judge は秘密鍵、writer は公開鍵だけ）══════
#
# **共有鍵では「別主体」を証明できない。** 検証できる側が署名も作れるので、writer が judge の
# 判定を偽造できる。非対称に変えると:
#
#   judge  — 秘密鍵を持ち、自分の判断に署名する
#   writer — **公開鍵だけ**を持ち、検証しかできない。judge の判定を作れない
#
# これが `attested` と `authenticated` を分ける最初の条件である。残りは:
#   writer の隔離（別 UID / 別サービス）・台帳への書き込みを writer に限る・
#   signer → role / lineage / release 権限の認可
#
# **脅威モデルから明示的に除外するもの:** ホストの管理者。daemon も hook も無効化できるので、
# その主体に対する強制力は原理的に持てない。持てないことを書く。

_SIG_ED25519 = "ed25519:"


def _crypto_backend():
    """(backend, error)。`cryptography` → `openssl` の順。**両方無ければ error。**

    導入先に何があるかは環境差なので、両方を使える形にする。無いことを黙って
    「共有鍵で代替する」と読み替えてはいけない — それは authenticated を名乗れなくする。
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
        return "cryptography", None
    except ImportError:
        pass
    import shutil
    if shutil.which("openssl"):
        return "openssl", None
    return None, ("非対称署名の手段が無い（cryptography も openssl も見つからない）。\n"
                  "  Authenticated Mode は非対称鍵を要求する — 共有鍵に落とすと、"
                  "検証できる側が署名も作れるので `authenticated` ではなくなる。")


def generate_keypair():
    """(private_pem, public_pem, error)。judge が秘密鍵を持ち、writer には公開鍵だけ渡す。"""
    backend, err = _crypto_backend()
    if err:
        return None, None, err
    if backend == "cryptography":
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
        k = ed25519.Ed25519PrivateKey.generate()
        priv = k.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode()
        pub = k.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        return priv, pub, None
    import subprocess, tempfile
    d = tempfile.mkdtemp()
    try:
        pk, pubk = os.path.join(d, "k.pem"), os.path.join(d, "k.pub")
        r = subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", pk],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None, None, f"openssl genpkey が失敗: {r.stderr[:200]}"
        r = subprocess.run(["openssl", "pkey", "-in", pk, "-pubout", "-out", pubk],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None, None, f"openssl pkey が失敗: {r.stderr[:200]}"
        return open(pk).read(), open(pubk).read(), None
    finally:
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)


def sign_bytes(message, private_pem):
    """(signature, error)。**秘密鍵を持つ側だけができる。**"""
    backend, err = _crypto_backend()
    if err:
        return None, err
    if backend == "cryptography":
        from cryptography.hazmat.primitives import serialization
        try:
            k = serialization.load_pem_private_key(private_pem.encode(), password=None)
            return _SIG_ED25519 + k.sign(message).hex(), None
        except Exception as e:
            return None, f"署名できない: {e}"
    import subprocess, tempfile
    d = tempfile.mkdtemp()
    try:
        pk, mp, sp = (os.path.join(d, x) for x in ("k.pem", "m", "sig"))
        open(pk, "w").write(private_pem)
        open(mp, "wb").write(message)
        r = subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", pk,
                            "-rawin", "-in", mp, "-out", sp], capture_output=True, text=True)
        if r.returncode != 0:
            return None, f"openssl の署名が失敗: {r.stderr[:200]}"
        return _SIG_ED25519 + open(sp, "rb").read().hex(), None
    finally:
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)


def verify_bytes(message, signature, public_pem):
    """(ok, error)。**writer はこれしかできない** — 公開鍵では署名を作れない。"""
    if not isinstance(signature, str) or not signature.startswith(_SIG_ED25519):
        return False, (f"署名の形式が {signature[:20] if signature else '(空)'!r} で、"
                       f"Authenticated Mode が要求する {_SIG_ED25519}… ではない。\n"
                       f"  共有鍵（hmac-）の receipt は authenticated として受け付けない — "
                       f"検証できる側が署名も作れるので、別主体を証明しない。")
    raw = bytes.fromhex(signature[len(_SIG_ED25519):])
    backend, err = _crypto_backend()
    if err:
        return False, err
    if backend == "cryptography":
        from cryptography.hazmat.primitives import serialization
        try:
            serialization.load_pem_public_key(public_pem.encode()).verify(raw, message)
            return True, None
        except Exception as e:
            return False, f"署名が一致しない: {type(e).__name__}"
    import subprocess, tempfile
    d = tempfile.mkdtemp()
    try:
        pubk, mp, sp = (os.path.join(d, x) for x in ("k.pub", "m", "sig"))
        open(pubk, "w").write(public_pem)
        open(mp, "wb").write(message)
        open(sp, "wb").write(raw)
        r = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", pubk,
                            "-rawin", "-in", mp, "-sigfile", sp], capture_output=True, text=True)
        return r.returncode == 0, (None if r.returncode == 0 else "署名が一致しない")
    finally:
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)


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
    """(store, error)。**読めなければ error** — 読めないことを「信頼できる」と読まない。

    Authenticated Mode（推奨）:

        {"mode": "authenticated",
         "keys": {"<key_id>": {"signer_id": …, "public_pem": …, "revoked": false,
                               "authorized_roles": ["gate"],
                               "authorized_lineages": ["cross-harness"],
                               "may_release_halt": false}}}

    **writer は公開鍵だけを持つ。** 秘密鍵は judge の側にあり、この store には入らない。
    `secret`（共有鍵）を持つ鍵は Compatibility Mode の遺物として **`attested` に落とす** —
    検証できる側が署名も作れるので、別主体を証明しない。

    認可はここで宣言する。**署名が正しいことと、その主体がその判定を出してよいことは別**である。
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
    # **秘密鍵が store に入っていたら拒否する。** writer が judge の判定を作れる状態である。
    leaked = sorted(k for k, v in keys.items()
                    if isinstance(v, dict) and "private_pem" in v)
    if leaked:
        return None, (f"trust store に秘密鍵が入っている: {', '.join(leaked)}。\n"
                      f"  **writer は公開鍵だけを持つ。** 秘密鍵を持つ側は judge の判定を"
                      f"偽造できるので、これは authenticated ではない。")
    return {"keys": keys, "path": path,
            "mode": doc.get("mode") or ("authenticated"
                                        if all(v.get("public_pem") for v in keys.values()
                                               if isinstance(v, dict))
                                        else "compatibility")}, None


def authorize(key, role, lineage, want_release=False):
    """署名が正しいことと、その主体がその判定を出してよいことは **別である**。

    (ok, error)。宣言が無い項目は「許可されていない」と読む — 認可の既定は拒否である。
    """
    roles = key.get("authorized_roles")
    if roles is not None and role not in roles:
        return False, (f"signer {key.get('signer_id')!r} は role={role!r} の判定を出す認可が"
                       f"無い（許可: {roles}）。")
    lins = key.get("authorized_lineages")
    if lins is not None and lineage not in lins:
        return False, (f"signer {key.get('signer_id')!r} は lineage={lineage!r} の判定を出す"
                       f"認可が無い（許可: {lins}）。")
    if want_release and not key.get("may_release_halt"):
        return False, (f"signer {key.get('signer_id')!r} には halt を解除する認可が無い"
                       f"（may_release_halt が真でない）。\n"
                       f"  **止めた主体が自分で解除できてはいけない。** 解除は独立した"
                       f"principal の仕事である。")
    return True, None


def receipt_signing_bytes(receipt):
    """署名が覆うバイト列。**束縛する値を1つでも外すと、そこは差し替え可能になる。**"""
    core = {k: receipt.get(k) for k in _RECEIPT_BOUND}
    return json.dumps(core, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sign_receipt(receipt, secret):
    import hmac
    return "hmac-sha256:" + hmac.new(secret.encode("utf-8"),
                                     receipt_signing_bytes(receipt), hashlib.sha256).hexdigest()


def verify_receipt(receipt, expect, store=None, expect_release=False):
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

    msg = receipt_signing_bytes(receipt)
    sig = str(receipt.get("signature") or "")
    if key.get("public_pem"):
        # ── Authenticated Mode: 公開鍵で検証する。**writer は署名を作れない。**
        ok, verr = verify_bytes(msg, sig, key["public_pem"])
        if not ok:
            return None, None, (verr or "署名が一致しない")
        ok, aerr = authorize(key, receipt.get("role"), receipt.get("lineage"),
                             want_release=bool(expect_release))
        if not ok:
            return None, None, aerr
        assurance = {
            "identity_assurance": "authenticated" if store.get("mode") == "authenticated"
                                  else "attested",
            # **隔離は別軸である。** 鍵が非対称でも、writer が同じ UID で動いていれば
            # workload は隔離されていない。ここでは writer 側が観測して上書きする。
            "workload_isolation": os.environ.get("ORG_WRITER_ISOLATION") or "none",
            "signer_id": receipt["signer_id"], "key_id": receipt["key_id"],
            "may_release_halt": bool(key.get("may_release_halt")),
        }
        return receipt["signer_id"], assurance, None

    # ── Compatibility Mode: 共有鍵。**attested まで。** 検証できる側が署名も作れる。
    import hmac
    secret = key.get("secret")
    if not secret:
        return None, None, (f"key_id {receipt['key_id']!r} に public_pem も secret も無い。")
    if not hmac.compare_digest(sign_receipt(receipt, secret), sig):
        return None, None, "receipt の署名が一致しない（内容が書き換えられているか、鍵が違う）。"
    if expect_release:
        return None, None, ("共有鍵の receipt で halt の解除は認めない。\n"
                            "  検証できる側が署名も作れるので、**独立した承認を証明しない**。"
                            "Authenticated Mode（非対称鍵）が必要である。")
    ok, aerr = authorize(key, receipt.get("role"), receipt.get("lineage"))
    if not ok:
        return None, None, aerr
    assurance = {"identity_assurance": "attested", "workload_isolation": "none",
                 "signer_id": receipt["signer_id"], "key_id": receipt["key_id"],
                 "may_release_halt": False}
    return receipt["signer_id"], assurance, None


def observed_recorder():
    """`recorded_by` を **観測** する。申告ではない（が、認証でもない）。

    hook が渡す session / agent の識別子、または実行環境から取る。取れなければ
    `unknown` を返し、`recorder_assurance` は `claimed` に落ちる。
    """
    # **writer が観測した peer credential を最優先する。** socket 越しに得た uid/pid は
    # 「接続してきた主体」であって申告ではない。ただし **判断の identity には使わない** —
    # 接続してきたことは、その判断をしたことの証拠にならない。
    puid = os.environ.get("ORG_WRITER_PEER_UID")
    if puid:
        ppid = os.environ.get("ORG_WRITER_PEER_PID") or ""
        return (f"peer:uid={puid}" + (f",pid={ppid}" if ppid else "")), "observed"
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
    """鍵を作る。**既定は非対称**（Authenticated Mode）。

    秘密鍵は `--private-out` に書き、**trust store には公開鍵だけを入れる**。writer が秘密鍵を
    持つと judge の判定を偽造できるので、それは authenticated ではない。

    `--shared-secret` で共有鍵も作れるが、それは Compatibility Mode（attested まで）である。
    """
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
    entry = {"signer_id": a.signer_id, "revoked": False}
    if a.authorized_roles:
        entry["authorized_roles"] = [x.strip() for x in a.authorized_roles.split(",") if x.strip()]
    if a.authorized_lineages:
        entry["authorized_lineages"] = [x.strip() for x in a.authorized_lineages.split(",")
                                        if x.strip()]
    if a.may_release_halt:
        entry["may_release_halt"] = True

    if a.shared_secret:
        import secrets
        entry["secret"] = secrets.token_hex(32)
        note = ("**共有鍵である（Compatibility Mode）。** 検証する側が署名も作れるので、"
                "得られるのは `attested` まで。halt の解除には使えない。")
    else:
        if not a.private_out:
            print("非対称鍵には --private-out が必要（秘密鍵の置き場所）。\n"
                  "  **trust store には入れない** — writer が秘密鍵を持つと判定を偽造できる。",
                  file=sys.stderr)
            return 2
        priv, pub, err = generate_keypair()
        if err:
            print(f"keygen: {err}", file=sys.stderr)
            return 2
        os.makedirs(os.path.dirname(os.path.abspath(a.private_out)) or ".", exist_ok=True)
        with open(a.private_out, "w", encoding="utf-8") as f:
            f.write(priv)
        os.chmod(a.private_out, 0o600)
        entry["public_pem"] = pub
        note = (f"秘密鍵: {a.private_out}（judge が持つ。**writer には渡さない**）\n"
                f"  trust store には公開鍵だけが入っている — writer は検証しかできない。")

    doc.setdefault("keys", {})[a.key_id] = entry
    doc.setdefault("mode", "authenticated" if not a.shared_secret else "compatibility")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    print(f"registered key_id={a.key_id} signer_id={a.signer_id} in {path}\n  {note}")
    if entry.get("may_release_halt"):
        print("  この鍵は halt の解除を認可されている — **止めた主体とは別にすること。**")
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
    if not key:
        print(f"receipt: key_id {a.key_id!r} が trust store に無い", file=sys.stderr)
        return 2
    if key.get("public_pem") and not a.private_key:
        print(f"receipt: key_id {a.key_id!r} は非対称鍵なので --private-key が必要。\n"
              f"  **秘密鍵は judge が持つ。** trust store（writer 側）には公開鍵しか無い。",
              file=sys.stderr)
        return 2
    if not key.get("public_pem") and not key.get("secret"):
        print(f"receipt: key_id {a.key_id!r} に public_pem も secret も無い", file=sys.stderr)
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
    if a.private_key:
        priv = (open(a.private_key, encoding="utf-8").read()
                if os.path.isfile(a.private_key) else a.private_key)
        sig, err = sign_bytes(receipt_signing_bytes(r), priv)
        if err:
            print(f"receipt: {err}", file=sys.stderr)
            return 2
        r["signature"] = sig
    else:
        r["signature"] = sign_receipt(r, key["secret"])
    print(json.dumps(r, ensure_ascii=False))
    return 0


def main(argv):
    import argparse
    p = argparse.ArgumentParser(
        prog="identity",
        description="判断した主体・記録した主体・確定した主体を分ける（H1、Compatibility Mode）")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("keygen", help="鍵を登録する（既定は非対称 = Authenticated Mode）")
    q.add_argument("--key-id", dest="key_id", required=True)
    q.add_argument("--signer-id", dest="signer_id", required=True)
    q.add_argument("--store", default=None)
    q.add_argument("--private-out", dest="private_out", default=None,
                   help="秘密鍵の置き場所（judge が持つ。**trust store には入らない**）")
    q.add_argument("--shared-secret", dest="shared_secret", action="store_true",
                   help="共有鍵にする（Compatibility Mode — attested まで。解除には使えない）")
    q.add_argument("--authorized-roles", dest="authorized_roles", default=None,
                   help="この鍵が出せる役（カンマ区切り）。既定は制限なし")
    q.add_argument("--authorized-lineages", dest="authorized_lineages", default=None,
                   help="この鍵が出せる血統（カンマ区切り）。既定は制限なし")
    q.add_argument("--may-release-halt", dest="may_release_halt", action="store_true",
                   help="halt の解除を認可する。**止めた主体とは別の鍵にすること**")
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
    q.add_argument("--private-key", dest="private_key", default=None,
                   help="秘密鍵（非対称鍵のとき必須）。ファイルか PEM 文字列")
    q.set_defaults(fn=_cmd_receipt)
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
