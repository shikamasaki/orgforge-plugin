#!/usr/bin/env python3
"""identity — separate who judged, who recorded it, and who settled it (H1).

**What this module provides is Compatibility Mode.** `decision_by` is set only from a verified
receipt and can never be set by a CLI's own say-so. But the keys sit where the same user can read
them and the writer can be swapped out, so **it does not claim `authenticated`** — the most it
reaches is `attested`.

Authenticated Mode (an isolated writer, a restricted path, protected keys, per-principal
authorisation) is a separate change.
"""

import hashlib
import json
import os
import sys


# ══ Identity: three principals and four axes of assurance (H1) ══════════════
#
# **`actor` was conflating three concepts.** Who judged, who recorded it, and who settled it are
# different things. Where a supervisor records a judge's verdict by proxy, the observed actor is
# always the supervisor — so a separation of duties that compares `actor` against `actor` can only
# say "the supervisor did not approve the supervisor".
#
# **An important limitation.** What is implemented here is Compatibility Mode:
#
#   - `decision_by` is set **only from a verified receipt** (never by the CLI)
#   - but the keys sit where the same user can read them, and the writer can be swapped out
#   - so `identity_assurance` is at best `attested`, and **not `authenticated`**
#   - **asking a separate process is not a trust boundary.** Only once an isolated writer, a
#     restricted path, protected keys and per-principal authorisation are all in place may it be
#     called `authenticated`
#
# "It is signed, therefore it is independent" is wrong. **If one signer could sign both lineages,
# it is not an independent review** — which is why `reviewer_independence` is a separate axis.

PROTOCOL_VERSION = 4                 # the receipt format; it moves independently of the ledger's
                                     # schema_version
# v4: bind an adaptive-envelope permanence decision to the envelope / human decision /
#     microexperiment.
# v3: added `event_class` to the binding. Unless the signature covers WHICH class of judgment it
#     is, a receipt meant for admission_decided can be reused for refutation_attempted.
# v2: added `judge_workload` to what is signed. In v1 it sat outside the signature, so **adding
#     `separate_host` AFTER signing still verified** (measured) — if the value an independence
#     assessment rests on is not signed, that assessment has no basis.
_RECEIPT_BOUND = ("receipt_id", "org_id", "ledger_id", "review_subject_id", "issue", "role",
                  "phase", "lineage", "verdict", "requirements_digest", "reasoning_sha256",
                  "signer_id", "key_id", "issued_at", "schema_version", "protocol_version",
                  # **The values an independence assessment rests on must be covered by the
                  # signature.**
                  "judge_workload",
                  # **Which class of judgment this is.** Leave it uncovered and a receipt meant
                  # for an admission can be reused for a refutation.
                  "event_class")
_OPTIONAL_RECEIPT_BOUND = ("envelope_id", "human_decision_ref", "microexperiment_ref",
                           "practice_change_ref")


# ══ Authenticated Mode: asymmetric signing (the judge holds the private key, ══
# ══ the writer only the public one)                                          ══
#
# **A shared key cannot prove "a different principal".** Whoever can verify can also sign, so the
# writer could forge the judge's verdicts. Made asymmetric:
#
#   the judge  — holds the private key and signs its own judgments
#   the writer — holds **only the public key** and can merely verify; it cannot produce the
#                 judge's verdicts
#
# This is the first of the conditions separating `attested` from `authenticated`. The rest:
#   isolating the writer (a separate UID / a separate service), restricting ledger writes to the
#   writer, and authorising signer → role / lineage / release permissions
#
# **Explicitly outside the threat model:** the host's administrator. They can disable the daemon
# and the hook alike, so no enforcement against that principal is possible in principle. We write
# down what we cannot do.

_SIG_ED25519 = "ed25519:"


def _crypto_backend():
    """(backend, error). `cryptography` first, then `openssl`. **An error if neither is present.**

    What is installed differs by environment, so both are usable. Absence must never be silently
    reinterpreted as "fall back to a shared key" — that would forfeit the claim to authenticated.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
        return "cryptography", None
    except ImportError:
        pass
    import shutil
    if shutil.which("openssl"):
        return "openssl", None
    return None, ("no asymmetric signing available (neither cryptography nor openssl "
                      "was found).\n"
                  "  Authenticated Mode requires an asymmetric key — drop to a shared one and "
                  "whoever can verify can also sign, so it is no longer `authenticated`.")


def generate_keypair():
    """(private_pem, public_pem, error). The judge keeps the private key; the writer is given only
    the public one."""
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
            return None, None, f"openssl genpkey failed: {r.stderr[:200]}"
        r = subprocess.run(["openssl", "pkey", "-in", pk, "-pubout", "-out", pubk],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None, None, f"openssl pkey failed: {r.stderr[:200]}"
        return open(pk).read(), open(pubk).read(), None
    finally:
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)


def sign_bytes(message, private_pem):
    """(signature, error). **Only the holder of the private key can do this.**"""
    backend, err = _crypto_backend()
    if err:
        return None, err
    if backend == "cryptography":
        from cryptography.hazmat.primitives import serialization
        try:
            k = serialization.load_pem_private_key(private_pem.encode(), password=None)
            return _SIG_ED25519 + k.sign(message).hex(), None
        except Exception as e:
            return None, f"cannot sign: {e}"
    import subprocess, tempfile
    d = tempfile.mkdtemp()
    try:
        pk, mp, sp = (os.path.join(d, x) for x in ("k.pem", "m", "sig"))
        open(pk, "w").write(private_pem)
        open(mp, "wb").write(message)
        r = subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", pk,
                            "-rawin", "-in", mp, "-out", sp], capture_output=True, text=True)
        if r.returncode != 0:
            return None, f"the openssl signature failed: {r.stderr[:200]}"
        return _SIG_ED25519 + open(sp, "rb").read().hex(), None
    finally:
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)


def verify_bytes(message, signature, public_pem):
    """(ok, error). **This is all the writer can do** — a public key cannot produce a signature."""
    if not isinstance(signature, str) or not signature.startswith(_SIG_ED25519):
        return False, (f"the signature format is {signature[:20] if signature else '(empty)'!r}, "
                       f"not the {_SIG_ED25519}… that Authenticated Mode requires.\n"
                       f"  A shared-key (hmac-) receipt is not accepted as authenticated — whoever "
                       f"can verify can also sign, so it proves nothing about a different "
                       f"principal.")
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
            return False, f"the signature does not match: {type(e).__name__}"
    import subprocess, tempfile
    d = tempfile.mkdtemp()
    try:
        pubk, mp, sp = (os.path.join(d, x) for x in ("k.pub", "m", "sig"))
        open(pubk, "w").write(public_pem)
        open(mp, "wb").write(message)
        open(sp, "wb").write(raw)
        r = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", pubk,
                            "-rawin", "-in", mp, "-sigfile", sp], capture_output=True, text=True)
        return r.returncode == 0, (None if r.returncode == 0 else "the signature does not match")
    finally:
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)


def _trust_store_path():
    """The keys of the signers we trust. `ORG_TRUST_STORE`, then the org's
    `.orgforge/trust/keys.json`."""
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
    """(store, error). **An error if it cannot be read** — unreadable is never read as trusted.

    Authenticated Mode (recommended):

        {"mode": "authenticated",
         "keys": {"<key_id>": {"signer_id": …, "public_pem": …, "revoked": false,
                               "authorized_roles": ["gate"],
                               "authorized_lineages": ["cross-harness"],
                               "may_release_halt": false}}}

    **The writer holds only public keys.** A private key belongs on the judge's side and never
    enters this store. A key carrying a `secret` (a shared key) is a relic of Compatibility Mode and
    is **dropped to `attested`** — whoever can verify can also sign, so it proves nothing about a
    different principal.

    Authorisation is declared here. **That a signature is valid and that this principal may issue
    this judgment are two different things.**
    """
    path = _trust_store_path()
    if not path or not os.path.isfile(path):
        return None, (f"no trust store (searched: {path}). A receipt cannot be verified, so "
                      f"the deciding principal stays `claimed`.")
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        return None, f"cannot read the trust store: {e}"
    keys = doc.get("keys")
    if not isinstance(keys, dict):
        return None, "the trust store has no keys (or it is not a map)."
    # **Refuse if a private key is in the store.** That is a state in which the writer could
    # produce the judge's verdicts.
    leaked = sorted(k for k, v in keys.items()
                    if isinstance(v, dict) and "private_pem" in v)
    if leaked:
        return None, (f"the trust store contains private keys: {', '.join(leaked)}.\n"
                      f"  **The writer holds only public keys.** Whoever holds a private key can "
                      f"forge the judge's verdicts, so this is not authenticated.")
    return {"keys": keys, "path": path,
            "mode": doc.get("mode") or ("authenticated"
                                        if all(v.get("public_pem") for v in keys.values()
                                               if isinstance(v, dict))
                                        else "compatibility")}, None


def authorize(key, role, lineage, want_release=False):
    """That a signature is valid and that this principal may issue this judgment are **two
    different things.**

    (ok, error). An undeclared item reads as "not permitted" — the default for authorisation is to
    refuse.
    """
    roles = key.get("authorized_roles")
    if roles is not None and role not in roles:
        return False, (f"signer {key.get('signer_id')!r} is not authorized to issue a verdict "
                       f"for role={role!r} (allowed: {roles}).")
    lins = key.get("authorized_lineages")
    if lins is not None and lineage not in lins:
        return False, (f"signer {key.get('signer_id')!r} is not authorized to issue a verdict "
                       f"for lineage={lineage!r} (allowed: {lins}).")
    if want_release and not key.get("may_release_halt"):
        return False, (f"signer {key.get('signer_id')!r} is not authorized to release a halt "
                       f"(may_release_halt is not true).\n"
                       f"  **The principal that stopped it must not be able to release it "
                       f"itself.** A release is the work of an independent principal.")
    return True, None


def receipt_signing_bytes(receipt):
    """The bytes the signature covers. **Leave one bound value out and that value becomes
    swappable.**"""
    core = {k: receipt.get(k) for k in _RECEIPT_BOUND + _OPTIONAL_RECEIPT_BOUND}
    return json.dumps(core, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sign_receipt(receipt, secret):
    import hmac
    return "hmac-sha256:" + hmac.new(secret.encode("utf-8"),
                                     receipt_signing_bytes(receipt), hashlib.sha256).hexdigest()


def verify_receipt(receipt, expect, store=None, expect_release=False):
    """Verify a receipt. Returns (decision_by, assurance, error).

    `expect` is **what this judgment is about** (org_id / ledger_id / review_subject_id / issue /
    role / lineage / verdict). **If the receipt does not match it, refuse** — without checking the
    match, a receipt from another org, another subject or another lineage could be brought in and
    accepted (reuse).
    """
    import hmac
    if not isinstance(receipt, dict):
        return None, None, "the receipt is not a map."
    for k in _RECEIPT_BOUND:
        if receipt.get(k) in (None, ""):
            return None, None, (f"the receipt has no {k}. A value that is not bound can be "
                                f"swapped.")
    if receipt.get("judge_workload") not in ("none", "separate_process", "separate_uid",
                                             "separate_host"):
        return None, None, (f"the receipt's judge_workload is invalid: "
                            f"{receipt.get('judge_workload')!r}\n"
                            f"  none | separate_process | separate_uid | separate_host")
    if receipt.get("protocol_version") != PROTOCOL_VERSION:
        return None, None, (f"the receipt's protocol_version is "
                            f"{receipt.get('protocol_version')!r} (this verifier is "
                            f"v{PROTOCOL_VERSION}). An unknown version cannot be verified.")
    for k, v in (expect or {}).items():
        if str(receipt.get(k)) != str(v):
            return None, None, (f"the receipt's {k} does not match: receipt={receipt.get(k)!r} / "
                                f"this judgment={v!r}.\n"
                                f"  **A receipt from another org / subject / lineage must never be "
                                f"reusable.**")
    if store is None:
        store, serr = load_trust_store()
        if serr:
            return None, None, serr
    key = (store["keys"] or {}).get(receipt["key_id"])
    if not key:
        return None, None, f"key_id {receipt['key_id']!r} is not in the trust store."
    if key.get("revoked"):
        return None, None, (f"key_id {receipt['key_id']!r} has been revoked "
                            f"({key.get('revoked_reason') or 'no reason recorded'}). A receipt "
                            f"signed with a revoked key is not accepted.")
    if key.get("signer_id") and key["signer_id"] != receipt["signer_id"]:
        return None, None, (f"signer_id does not match the key's registration: receipt="
                            f"{receipt['signer_id']!r} / store={key['signer_id']!r}")

    msg = receipt_signing_bytes(receipt)
    sig = str(receipt.get("signature") or "")
    if key.get("public_pem"):
        # ── Authenticated Mode: verify with the public key. **The writer cannot sign.**
        ok, verr = verify_bytes(msg, sig, key["public_pem"])
        if not ok:
            return None, None, (verr or "the signature does not match")
        ok, aerr = authorize(key, receipt.get("role"), receipt.get("lineage"),
                             want_release=bool(expect_release))
        if not ok:
            return None, None, aerr
        assurance = {
            "identity_assurance": "authenticated" if store.get("mode") == "authenticated"
                                  else "attested",
            # **Isolating the writer is not isolating the judge.** Measured (audit): the writer's
            # isolation value was being written into the judge's workload_isolation, and with a
            # different signer it was promoted to distinct_workload. **The same writer UID is no
            # evidence that two judges are separate workloads** — a judge runs in a different
            # process from the writer, possibly on a different machine.
            #
            # A judge's workload is what the judge itself states in the receipt
            # (`judge_workload`), or `none` when it is unknown. Never borrow the writer's value.
            "workload_isolation": (receipt.get("judge_workload")
                                   if receipt.get("judge_workload") in
                                   ("separate_process", "separate_uid", "separate_host")
                                   else "none"),
            # The writer's own isolation goes in **a separate field**. Mixing them invites the
            # misreading that "the writer is isolated, therefore the judges are independent".
            "writer_isolation": os.environ.get("ORG_WRITER_ISOLATION") or "none",
            "signer_id": receipt["signer_id"], "key_id": receipt["key_id"],
            "may_release_halt": bool(key.get("may_release_halt")),
        }
        return receipt["signer_id"], assurance, None

    # ── Compatibility Mode: a shared key. **`attested` at most** — whoever can verify can sign.
    import hmac
    secret = key.get("secret")
    if not secret:
        return None, None, (f"key_id {receipt['key_id']!r} has neither a public_pem nor a "
                            f"secret.")
    if not hmac.compare_digest(sign_receipt(receipt, secret), sig):
        return None, None, ("the receipt's signature does not match (either the contents were "
                            "altered, or the key differs).")
    if expect_release:
        return None, None, ("a shared-key receipt is not accepted for releasing a halt.\n"
                            "  Whoever can verify can also sign, so it **proves no independent "
                            "approval**. Authenticated Mode (an asymmetric key) is required.")
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
    if a.event_class == "adaptive_envelope_adopted" and not all(
            (a.envelope_id, a.human_decision_ref, a.microexperiment_ref, a.practice_change_ref)):
        print("receipt: adaptive adoption requires --envelope-id, --human-decision-ref, and "
              "--microexperiment-ref, and --practice-change-ref", file=sys.stderr)
        return 2
    r = {"receipt_id": hashlib.sha256(
             f"{a.org_id}|{a.subject}|{a.issue}|{a.role}|{a.lineage}|{a.verdict}"
             f"|{a.reasoning_sha256}|{a.key_id}|{a.issued_at}|{a.envelope_id}"
             f"|{a.human_decision_ref}|{a.microexperiment_ref}|{a.practice_change_ref}"
             .encode()).hexdigest()[:32],
         "org_id": a.org_id, "ledger_id": a.ledger_id,
         "review_subject_id": a.subject, "issue": a.issue, "role": a.role, "phase": a.phase,
         "lineage": a.lineage, "verdict": a.verdict,
         "requirements_digest": a.requirements_digest,
         "reasoning_sha256": a.reasoning_sha256,
         "signer_id": key.get("signer_id") or a.key_id, "key_id": a.key_id,
         "issued_at": a.issued_at, "schema_version": a.schema_version,
         # **judge 自身が申告する。** 署名が覆うので、後から足せない。
         "judge_workload": a.judge_workload,
         "event_class": a.event_class,
         "envelope_id": a.envelope_id,
         "human_decision_ref": a.human_decision_ref,
         "microexperiment_ref": a.microexperiment_ref,
         "practice_change_ref": a.practice_change_ref,
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
    q = sub.add_parser("receipt", help="判断に署名する（judge / correction authority が使う）")
    for f in ("org-id", "ledger-id", "subject", "role", "lineage", "verdict",
              "reasoning-sha256", "issued-at", "key-id"):
        q.add_argument(f"--{f}", dest=f.replace("-", "_"), required=True)
    q.add_argument("--issue", required=True)
    q.add_argument("--phase", default="")
    q.add_argument("--requirements-digest", dest="requirements_digest", default="")
    q.add_argument("--schema-version", dest="schema_version", type=int, default=1)
    q.add_argument("--event-class", dest="event_class", required=True,
                   choices=("admission_decided", "refutation_attempted", "verdict_provisional",
                            "halt_released", "adaptive_envelope_adopted", "correction"),
                   help="この receipt が使える台帳クラス。**署名が覆う**ので流用できない")
    q.add_argument("--envelope-id", dest="envelope_id")
    q.add_argument("--human-decision-ref", dest="human_decision_ref")
    q.add_argument("--microexperiment-ref", dest="microexperiment_ref")
    q.add_argument("--practice-change-ref", dest="practice_change_ref")
    q.add_argument("--judge-workload", dest="judge_workload", default="none",
                   choices=("none", "separate_process", "separate_uid", "separate_host"),
                   help="この judge がどこで動いたか。**署名が覆う**ので後から足せない")
    q.add_argument("--private-key", dest="private_key", default=None,
                   help="秘密鍵（非対称鍵のとき必須）。ファイルか PEM 文字列")
    q.set_defaults(fn=_cmd_receipt)
    a = p.parse_args(argv[1:])
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
