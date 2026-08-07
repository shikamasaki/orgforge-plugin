#!/usr/bin/env python3
"""writerd — 台帳への書き込みを1つのプロセスに集約する（Authenticated Writer, 段階A）。

## 何を強くするのか

これまで台帳は「呼び出した側のプロセスが自分で書く」形だった。だから:

  - `decision_by` を receipt で確かめても、**書く経路そのものは誰でも使える**
  - halt のラッチ・鍵 registry・schema も、書く側と同じ権限で触れる
  - 「検査に使う記録は検査する側だけが書ける」を宣言しても、経路が1つしかないことを
    強制する仕組みが無い

writerd は Unix domain socket を1つだけ開き、**そこを通った要求だけを台帳に書く**。
CLI が直接書こうとした場合は拒否する（`ORG_WRITER_SOCKET` が設定された org では）。

## 何を強くしないのか — 明示する

**これは OS 境界ではない。** 同じ UID で動く限り:

  - caller は daemon を停止できる
  - caller は socket や台帳のファイル権限を戻せる
  - caller は writerd 自体を差し替えられる

したがって `workload_isolation` は **`process_mediated`** であって、`separate_uid` ではない。
**「Authenticated Writer 完了」とは呼ばない。** 別 UID / LaunchDaemon / root 所有の設定と
socket 親ディレクトリが揃って初めて `separate_uid` に上げられる（`tools/writer-install.sh`）。

そして別 UID にしても、**ホストの管理者は突破できる** — 保証の対象は「通常の agent / caller の
UID から writer の資産を変更できない」ことであって、root は脅威モデルの外である。

## peer identity の使い方

socket の peer credential（SO_PEERCRED / LOCAL_PEERCRED）から得た uid/pid は
**`recorded_by` にしか使わない**。`decision_by` は署名 receipt からのみ確定する —
「接続してきた」ことは「その判断をした」ことの証拠にならない。

## RPC の改変・再送

要求は nonce と本文の digest を持ち、writerd は **使用済み nonce を拒否**する。
また要求全体の digest を検証するので、途中で書き換えられた要求は通らない。
"""

import argparse
import errno
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PROTOCOL = 1
# **writer の内側であることの証拠。** 環境変数の値そのものを秘密にする —
# `=1` のような当てられる値にすると、caller が名乗れてしまう（実測でそうなった）。
_INSIDE_WRITER_TOKEN = __import__("secrets").token_hex(32)

_MAX_REQUEST = 1 << 20          # 1 MiB。これを超える要求は読まずに拒否する
_NONCE_TTL = 3600               # 使用済み nonce を覚えておく時間（秒）


# ── socket のパスと、その親ディレクトリの検証 ────────────────────────────────
def socket_path(root=None):
    env = os.environ.get("ORG_WRITER_SOCKET")
    if env:
        return env
    if not root:
        try:
            from discover import ledger_root
            root = ledger_root()
        except Exception:
            return None
    return os.path.join(root, "writer.sock") if root else None



def load_manifest(path=None):
    """root 所有の manifest から **daemon の設定を固定配線する**。

    daemon が起動時に「どの org を、どの schema と policy と trust store で扱うか」を
    **caller の環境からではなく、root 所有のファイルから**受け取る。env や cwd に依存すると、
    caller が差し替えられる。

    形:
        orgs:
          default:
            ledger: /usr/local/var/orgforge/orgs/<ns>/ledger
            schema: /usr/local/var/orgforge/orgs/<ns>/ledger-schema.yaml
            trust:  /usr/local/var/orgforge/orgs/<ns>/trust/keys.json
        policy: /usr/local/etc/orgforge/policy.yaml
        allow_uids: [501]

    返り値: (manifest, error)。**読めないなら起動しない。**
    """
    path = path or os.environ.get("ORG_WRITER_MANIFEST")
    if not path:
        return None, None                       # no manifest (stage A)
    if not os.path.isfile(path):
        return None, f"the manifest is missing: {path}"
    try:
        st = os.stat(path)
    except OSError as e:
        return None, f"cannot stat the manifest: {e}"
    if st.st_uid != 0 and st.st_uid != os.getuid():
        return None, (f"the manifest is owned by neither root nor you (uid={st.st_uid}): {path}\n"
                      f"  **whoever can write it can swap out the daemon's configuration.**")
    if st.st_mode & 0o022:
        return None, (f"the manifest is group/world-writable "
                      f"(mode {oct(st.st_mode & 0o777)}): {path}")
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    except Exception as e:
        return None, f"cannot read the manifest: {e}"
    if not isinstance(doc, dict) or not isinstance(doc.get("orgs"), dict):
        return None, f"the manifest has no orgs (or it is not a map): {path}"
    return doc, None


def check_socket_parent(path, require_root_owned=False):
    """socket の **親ディレクトリ** を検証する。

    **caller が親ディレクトリを差し替えられるなら、socket も差し替えられる** — 偽の writerd を
    立てて「書けた」と言わせられる。だから接続する側が親を確かめる。

    段階A（同一 UID）で確かめられるのは:
      - 親が実在し、シンボリックリンクでないこと
      - 他人に書き込み可能でないこと（group/other write が落ちていること）
      - 所有者が自分か root であること

    `require_root_owned=True`（段階B）では **root 所有かつ他者書き込み不可** を要求する。
    そこまで来て初めて「caller が差し替えられない」と言える。
    """
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        return f"socket の親ディレクトリが無い: {parent}"
    if os.path.islink(parent):
        return (f"socket の親ディレクトリがシンボリックリンクである: {parent}\n"
                f"  リンクを張り替えれば socket ごと差し替えられる。")
    st = os.stat(parent)
    # **other-write は常に不可。** 誰でも書けるなら socket を差し替えられる。
    if st.st_mode & 0o002:
        return (f"socket の親ディレクトリが誰からでも書き込み可能である "
                f"（mode {oct(st.st_mode & 0o777)}）: {parent}\n"
                f"  **書ける主体は socket を差し替えられる** — 偽の writer に繋がされる。")
    if require_root_owned:
        # 段階B。**leaf は writer 所有でよい** — daemon が socket を作るには親への書き込み権限が
        # 要るので、root 所有 0755 では bind できない（実測: Permission denied）。
        # 保証は「**anchor（leaf の親）に caller が書けないので、leaf ごと差し替えられない**」
        # ことである。したがって:
        #   leaf   … 自分（writer）の所有で、他者から書けないこと
        #   anchor … root 所有で、他者から書けないこと
        if st.st_uid not in (0, os.getuid()):
            return (f"socket の親（leaf）の所有者が writer でも root でもない"
                    f"（uid={st.st_uid}）: {parent}")
        if st.st_mode & 0o022:
            return (f"socket の親（leaf）が他者から書き込み可能である "
                    f"（mode {oct(st.st_mode & 0o777)}）: {parent}\n"
                    f"  その主体は socket を差し替えられる。")
        anchor = os.path.dirname(parent)
        try:
            ast_ = os.stat(anchor)
        except OSError as e:
            return f"socket の anchor を stat できない（{e}）: {anchor}"
        if ast_.st_uid != 0:
            return (f"socket の anchor が root 所有でない（uid={ast_.st_uid}）: {anchor}\n"
                    f"  anchor に書ける主体は **leaf ごと差し替えられる**。"
                    f"**workload_isolation を separate_uid と呼べない。**")
        if ast_.st_mode & 0o022:
            return (f"socket の anchor が他者から書き込み可能である "
                    f"（mode {oct(ast_.st_mode & 0o777)}）: {anchor}\n"
                    f"  **caller が leaf を差し替えられる。**")
    else:
        # 段階A / client 側。**leaf の所有者は writer であって caller ではない** —
        # 実測（監査）: installer が leaf を writer 所有にする一方、client が「root か自分」しか
        # 許さず、**正規の書き込み経路がゼロ**になっていた。
        #
        # client が確かめるべきは「**誰が leaf を差し替えられるか**」であって「leaf が誰のものか」
        # ではない。他者から書けなければ、その socket は差し替えられない。
        if st.st_mode & 0o022:
            return (f"socket の親（leaf）が他者から書き込み可能である "
                    f"（mode {oct(st.st_mode & 0o777)}）: {parent}\n"
                    f"  **書ける主体は socket を差し替えられる** — 偽の writer に繋がされる。")
        anchor = os.path.dirname(parent)
        try:
            ast_ = os.stat(anchor)
        except OSError:
            return None                  # anchor を辿れないなら leaf の検査までで止める
        # **caller 所有の anchor を信頼しない。** anchor に書ける主体は leaf ごと差し替えられる
        # ので、偽の writer に繋がされる（実測で指摘された）。`ORG_WRITER_TRUST_SELF=1` は
        # 段階A（同じ利用者が daemon も動かしている）でだけ使う逃げ道である。
        if (ast_.st_uid == os.getuid() and ast_.st_uid != 0
                and os.environ.get("ORG_WRITER_TRUST_SELF") != "1"):
            return (f"socket の anchor が caller 自身の所有である（uid={ast_.st_uid}）: {anchor}\n"
                    f"  **書ける主体は leaf ごと差し替えられる** — 偽の writer に繋がされる。\n"
                    f"  段階A（自分で daemon を動かしている）なら ORG_WRITER_TRUST_SELF=1 を"
                    f"明示すること。**それは信頼境界ではない。**")
        if ast_.st_mode & 0o022:
            return (f"socket の anchor が他者から書き込み可能である "
                    f"（mode {oct(ast_.st_mode & 0o777)}）: {anchor}\n"
                    f"  **caller が leaf ごと差し替えられる。**")
    return None



def check_socket_length(path):
    """**AF_UNIX のパス長には OS の上限がある**（macOS 104 / Linux 108 バイト）。

    超えると bind が黙って失敗する。深い場所に org を置いた人が「なぜか動かない」に当たるので、
    何が起きているかを言う。段階B の install は `/var/run/orgforge/` を使うので通常は問題ない。

    **これは bind する側だけの問題**なので、親ディレクトリの権限検査とは分ける — 混ぜると
    「権限が悪い」と「パスが長い」を区別できなくなる。
    """
    limit = 104 if sys.platform == "darwin" else 108
    n = len(os.path.abspath(path).encode("utf-8"))
    if n >= limit:
        return (f"socket のパスが長すぎる（{n} バイト、上限 {limit}）: {path}\n"
                f"  AF_UNIX の OS 上限である。--socket で短い場所を指すこと。")
    return None


# ── peer credential（recorded_by にしか使わない）──────────────────────────────
def peer_credential(conn):
    """接続相手の (uid, pid)。取れなければ (None, None)。

    **これは `recorded_by` にしか使わない。** 「接続してきた」ことは「その判断をした」ことの
    証拠にならないので、`decision_by` には決して使わない。
    """
    try:
        if sys.platform == "darwin":
            # LOCAL_PEERCRED: struct xucred { u_int cr_version; uid_t cr_uid; short cr_ngroups; ... }
            data = conn.getsockopt(0, 0x001, 4 + 4 + 2 + 16 * 4)
            _ver, uid = struct.unpack("II", data[:8])
            return uid, None
        creds = conn.getsockopt(socket.SOL_SOCKET, 17, struct.calcsize("3i"))  # SO_PEERCRED
        pid, uid, _gid = struct.unpack("3i", creds)
        return uid, pid
    except Exception:
        return None, None


# ── 要求の digest（改変・再送の検出）─────────────────────────────────────────
def request_digest(req):
    core = {k: v for k, v in req.items() if k != "digest"}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


class _NonceStore:
    """使用済み nonce。**再送を拒否するために持つ。**

    **プロセス内だけに持たない。** daemon を落として上げれば同じ要求を再送できてしまう
    （実測で指摘された）。writer が所有するファイルに残し、書けないなら受け付けない —
    再送を防げない状態で通すのは、nonce を持たないのと同じである。
    """

    def __init__(self, path=None):
        self._seen = {}
        self._lock = threading.Lock()
        self._path = path
        self.load_error = None
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self._seen = {k: float(v) for k, v in (json.load(f) or {}).items()}
            except Exception as e:
                # **壊れた nonce ファイルを「空」として再開しない。** 実測（監査）: 壊すと
                # 空から始まり、同じ nonce が再受理された。再送を検出できない状態は、
                # nonce を持たないのと同じである。
                self.load_error = (f"nonce ファイルを読めない（{e}）: {path}\n"
                                   f"  **空として再開しない** — 再送を検出できない。"
                                   f"内容を確認して手当てすること。")

    def check_and_add(self, nonce):
        if self.load_error:
            raise OSError(self.load_error)
        now = time.time()
        with self._lock:
            for k, ts in list(self._seen.items()):
                if now - ts > _NONCE_TTL:
                    del self._seen[k]
            if nonce in self._seen:
                return False
            self._seen[nonce] = now
            if self._path:
                try:
                    tmp = self._path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(self._seen, f)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, self._path)
                except Exception as e:
                    del self._seen[nonce]
                    raise OSError(f"cannot persist the nonce: {e}")
            return True


# ── org allowlist（caller が台帳のパスを指定できないようにする）──────────────
def allowed_roots():
    """writerd が書いてよい台帳のルート。**caller は RPC でパスを指定できない。**

    指定できるなら、writer 経由でどこにでも書ける — 「台帳は writer が所有する」が意味を失う。
    `--root` で起動時に固定し、要求側は `org` という名前でしか選べない。
    """
    return {}



# ── writer が所有すべき資産（段階B で root/writer 所有にする）─────────────────
# **ラッチ・鍵 registry・schema は、書き込み経路と同じ強さで守る必要がある。**
# 台帳だけを writerd 経由にしても、halt のラッチを消せる／trust store の公開鍵を差し替えられる／
# schema の検証規則を緩められるなら、統制は迂回できる。
#
# 段階A（同一 UID）で確かめられるのは「**他者から書き込み可能でないこと**」までである。
# 段階B では所有者が writer / root であることを要求する — そこで初めて caller から変更不能になる。
WRITER_OWNED = (
    ("HALT", "halt のラッチ。消せる主体は停止を解除できる"),
    ("keys.json", "鍵 registry。差し替えられる主体は判定の署名者を偽装できる"),
    ("ledger-schema.yaml", "検証規則。緩められる主体は拒否されるべき記録を通せる"),
    ("ledger.jsonl", "台帳そのもの"),
    ("HEAD", "鎖の先端（cache だが、壊せば健全性検査が止まる）"),
)


def audit_writer_assets(root, org_root=None, require_owner_uid=None):
    """writer が所有すべき資産の権限を検査する。

    返り値: [(path, issue)] — 空なら問題なし。**「無い」は問題として数えない**
    （halt していなければラッチは無いのが正常）。

    `require_owner_uid` を渡すと所有者も検査する（段階B）。渡さないと
    「他者から書き込み可能でないこと」だけを見る（段階A で確かめられる範囲）。
    """
    found = []
    cands = []
    for name, why in WRITER_OWNED:
        cands.append((os.path.join(root, name), why))
        if org_root:
            cands.append((os.path.join(org_root, name), why))
            cands.append((os.path.join(org_root, ".orgforge", "trust", name), why))
    for path, why in cands:
        if not os.path.exists(path):
            continue
        try:
            st = os.stat(path)
        except OSError as e:
            found.append((path, f"stat できない: {e}"))
            continue
        if st.st_mode & 0o022:
            found.append((path, f"他者から書き込み可能（mode {oct(st.st_mode & 0o777)}）— {why}"))
        if require_owner_uid is not None and st.st_uid != require_owner_uid:
            found.append((path, f"所有者が uid={st.st_uid}（要求 {require_owner_uid}）— {why}"))
    return found



def measured_isolation(sock_path, ledger_roots, peer_uid=None):
    """`workload_isolation` を **実測で** 決める。フラグでは決めない。

    実測（監査）: `--require-root-owned` を渡しただけで `separate_uid` と報告していた。
    渡したかどうかは意図であって、状態ではない。

    `separate_uid` と言えるのは:
      - socket の親が root 所有で、group からも書けない
      - 台帳が **この writer プロセスの UID** の所有である（= caller の UID ではない）
      - writerd 自身のプロセスが caller と別 UID で動いている

    そのどれかが欠ければ `process_mediated` である。
    """
    if check_socket_parent(sock_path, require_root_owned=True):
        return "process_mediated"
    me = os.getuid()
    if me == 0:
        return "process_mediated"        # root で走る writer は隔離ではない
    for root in ledger_roots:
        try:
            if os.stat(root).st_uid != me:
                return "process_mediated"
        except OSError:
            return "process_mediated"
    # **caller と同じ UID なら隔離ではない。** 実測（監査）: writer UID = caller UID = 502 でも
    # separate_uid を返していた。**要求ごとに peer UID と比べる**必要がある — 起動時には
    # 誰が繋いでくるか分からない。
    if peer_uid is None:
        return "process_mediated"        # 比べられないなら弱い方に倒す
    if peer_uid == me:
        return "process_mediated"
    return "separate_uid"


class Writer:
    def __init__(self, roots, require_root_owned=False, isolation="process_mediated",
                 schema=None, caller_uid_differs=None, allowed_uids=None):
        self.roots = roots                      # {org_name: ledger_root}
        self.isolation = isolation              # **実測値**。フラグではない
        self.schema = schema                    # root 所有の設定から固定する
        self.trust = None                       # 同上
        self.policy = None                      # 同上
        self.caller_uid_differs = caller_uid_differs
        self.sock_path = None                   # serve が設定する
        self.allowed_uids = allowed_uids        # None = 制限なし（段階A）
        self.org_constitutions = {}             # {org: constitution path}。宣言を子に届けるため
        # **再起動で忘れない。** プロセス内だけに持つと、daemon を落として上げれば同じ要求を
        # 再送できる（実測で指摘された）。writer が所有する台帳の隣に残す。
        self.nonces = _NonceStore(
            os.path.join(list(roots.values())[0], "writer-nonces.json") if roots else None)
        self.require_root_owned = require_root_owned
        self.lock = threading.Lock()            # 1プロセス内の直列化

    def handle(self, req, peer_uid, peer_pid):
        """要求を処理する。(response_dict, ok) を返す。**すべての拒否理由を言う。**"""
        if req.get("protocol") != PROTOCOL:
            return {"ok": False, "reason": "protocol_mismatch",
                    "detail": f"protocol={req.get('protocol')!r}（writerd は v{PROTOCOL}）。"
                              f"未知の版の要求は処理しない。"}, False
        # **改変の検出。** digest は本文全体を覆う。
        if req.get("digest") != request_digest(req):
            return {"ok": False, "reason": "request_tampered",
                    "detail": "要求の digest が本文と一致しない。途中で書き換えられている。"}, False
        # **読み取りは nonce を要求しない。** 副作用が無く、拒否すると org を診断できない。
        # ただし digest（改変の検出）は読み取りにも効かせる。
        if req.get("op") == "halt-status":
            org_r = req.get("org")
            if org_r not in self.roots:
                return {"ok": False, "reason": "unknown_org"}, False
            try:
                r = subprocess.run([sys.executable, os.path.join(HERE, "ledger.py"),
                                    "halt-status", self.roots[org_r]],
                                   capture_output=True, text=True, timeout=30)
            except Exception as e:
                return {"ok": False, "reason": "read_failed", "detail": str(e)}, False
            return {"ok": True, "reason": "read", "exit_code": r.returncode,
                    "stdout": r.stdout, "stderr": r.stderr}, True
        nonce = req.get("nonce")
        if not nonce or not isinstance(nonce, str) or len(nonce) < 16:
            return {"ok": False, "reason": "missing_nonce",
                    "detail": "nonce が無い（または短すぎる）。再送を拒否できない。"}, False
        if not self.nonces.check_and_add(nonce):
            return {"ok": False, "reason": "replayed_nonce",
                    "detail": f"nonce {nonce[:16]}… は既に使われている。**再送は通さない。**"}, False

        # **peer UID の認可。** socket は 0666 なので繋げること自体は誰でもできる。
        # 「繋げた」ことは「書いてよい」ことではない。
        if self.allowed_uids is not None and peer_uid not in self.allowed_uids:
            return {"ok": False, "reason": "peer_not_authorized",
                    "detail": f"peer uid={peer_uid} は書き込みを認可されていない"
                              f"（許可: {sorted(self.allowed_uids)}）。"}, False

        org = req.get("org")
        if org not in self.roots:
            return {"ok": False, "reason": "unknown_org",
                    "detail": f"org={org!r} は writerd が書ける対象ではない"
                              f"（許可: {sorted(self.roots)}）。\n"
                              f"  **caller は台帳のパスを指定できない** — 指定できれば、"
                              f"writer 経由でどこにでも書ける。"}, False
        root = self.roots[org]

        op = req.get("op")
        argv = req.get("argv")
        if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
            return {"ok": False, "reason": "bad_argv",
                    "detail": "argv が文字列の配列でない。"}, False
        # **読み取りも writer に聞く。** org 側の symlink を張り替えて空の台帳を見せられると、
        # hook は停止を見失う（実測: HALT 中でも halt-status が exit 10 → 0 になった）。
        # writer は起動時に固定した **実体のパス** を見るので、張り替えても影響しない。
        if op == "halt-status":
            try:
                r = subprocess.run([sys.executable, os.path.join(HERE, "ledger.py"),
                                    "halt-status", root],
                                   capture_output=True, text=True, timeout=30)
            except Exception as e:
                return {"ok": False, "reason": "read_failed", "detail": str(e)}, False
            return {"ok": True, "reason": "read", "exit_code": r.returncode,
                    "stdout": r.stdout, "stderr": r.stderr}, True
        if op not in ("append", "record-scheduled-check", "trip-halt", "release-halt",
                      "reserve-exposure", "derive-admission"):
            return {"ok": False, "reason": "unsupported_op",
                    "detail": f"op={op!r} は writerd 経由では実行できない"
                              f"（append / record-scheduled-check / trip-halt / release-halt / "
                              f"reserve-exposure / derive-admission / halt-status）。"}, False
        # **caller が root を指定する経路を閉じる。** argv からパスらしきものを弾く。
        for a in argv:
            if a == root or a.startswith("/") and os.path.sep in a and (
                    "ledger" in a or a.endswith(".jsonl")):
                return {"ok": False, "reason": "path_in_argv",
                        "detail": f"argv に台帳のパスらしき値がある: {a!r}\n"
                                  f"  **書き込み先は writerd が決める。** caller は org 名でしか"
                                  f"選べない。"}, False
        # **recorded_by は peer credential から。** decision_by には使わない。
        env = dict(os.environ)
        env["ORG_LEDGER_ROOT"] = root
        # **schema を明示する。** 渡さないと ledger.py が cwd から org を探し、見つからなければ
        # プラグインのテンプレートに fallback する（実測で指摘）— org が緩めた／厳しくした規則
        # ではなく、テンプレートの規則で検証されることになる。
        if self.schema:
            env["ORG_LEDGER_SCHEMA"] = self.schema
        # **trust store も固定する。** caller の環境から取ると、偽の鍵 registry を指させる。
        if self.trust:
            env["ORG_TRUST_STORE"] = self.trust
        if self.policy:
            env["ORG_POLICY_FILE"] = self.policy
        # **org の宣言を子プロセスに届ける。** daemon は org の外で動くので、cwd から
        # constitution を探せない。届かないと `_enforce_attested()` が「宣言なし」と判定し、
        # **writerd 経由なら未認証 admission が通る**（実測で指摘された）。
        con = self.org_constitutions.get(org)
        if con:
            env["ORG_CONSTITUTION"] = con
        # **要求ごとに実測する。** 起動時の判定では caller が誰か分からない。
        env["ORG_WRITER_ISOLATION"] = measured_isolation(
            self.sock_path, list(self.roots.values()), peer_uid=peer_uid)
        env["ORG_WRITER_PEER_UID"] = str(peer_uid) if peer_uid is not None else ""
        env["ORG_WRITER_PEER_PID"] = str(peer_pid) if peer_pid is not None else ""
        # **caller が書ける値を、検査の入力にしない。** 実測（再監査）: `ORG_INSIDE_WRITER=1` を
        # 環境に足すだけで、単独署名者が cross-harness の admission を直接書けたし、
        # single-writer gate も素通りした。「1 かどうか」は誰でも書ける。
        # そこで **起動ごとに推測できない token を作り、それを知っている者だけを writer 内部**
        # とみなす。token は daemon のメモリにしかなく、caller には渡らない。
        env["ORG_INSIDE_WRITER"] = _INSIDE_WRITER_TOKEN
        env.pop("ORG_WRITER_SOCKET", None)      # 再帰を防ぐ
        with self.lock:
            try:
                r = subprocess.run([sys.executable, os.path.join(HERE, "ledger.py"), op, root,
                                    *argv],
                                   capture_output=True, text=True, timeout=120, env=env)
            except Exception as e:
                return {"ok": False, "reason": "writer_failed", "detail": str(e)}, False
        return {"ok": r.returncode == 0, "reason": "executed", "exit_code": r.returncode,
                "stdout": r.stdout, "stderr": r.stderr,
                "recorded_by_peer_uid": peer_uid,
                "workload_isolation": env["ORG_WRITER_ISOLATION"]}, r.returncode == 0


def _trust_store_defect(path):
    """trust store が使えない理由を返す。使えるなら None。

    **検証器を二重に書かない。** 判定は `identity.load_trust_store()` に任せる —
    ここで独自に「壊れている」の定義を書くと、receipt を実際に検証する側とずれて、
    「daemon は通したのに検証は落ちる（あるいはその逆）」が起きる。
    """
    import os as _os
    try:
        _here = _os.path.dirname(_os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
        import identity as _identity
    except Exception as e:                      # identity を読めないなら判定できない
        return f"identity module を読めないので trust を検証できない: {e}"
    _saved = _os.environ.get("ORG_TRUST_STORE")
    _os.environ["ORG_TRUST_STORE"] = path
    try:
        store, err = _identity.load_trust_store()
    except Exception as e:
        return f"trust store を検証できない: {e}"
    finally:
        if _saved is None:
            _os.environ.pop("ORG_TRUST_STORE", None)
        else:
            _os.environ["ORG_TRUST_STORE"] = _saved
    if err:
        return err
    if not store or not store.get("keys"):
        return "trust store に鍵が1つも無い。receipt を検証できない。"
    return None



def serve(a):
    """socket を開いて要求を待つ。**親ディレクトリを検証してから開く。**"""
    manifest, merr = load_manifest(getattr(a, "manifest", None))
    if merr:
        print(f"writerd: {merr}\n"
              f"  **if the configuration cannot be read, do not start.**", file=sys.stderr)
        return 4
    roots = {}
    if manifest:
        # **manifest が最終。** caller の --org / --schema では上書きできない。
        for name, spec in manifest["orgs"].items():
            if not isinstance(spec, dict) or not spec.get("ledger"):
                print(f"writerd: orgs.{name} in the manifest has no ledger", file=sys.stderr)
                return 4
            roots[name] = os.path.abspath(spec["ledger"])
        a.schema = (manifest["orgs"].get(list(roots)[0], {}) or {}).get("schema") or a.schema
        if manifest.get("policy"):
            os.environ["ORG_POLICY_FILE"] = manifest["policy"]
        if manifest.get("trust"):
            os.environ["ORG_TRUST_STORE"] = manifest["trust"]
        if manifest.get("allow_uids") and not getattr(a, "allow_uid", None):
            a.allow_uid = [str(u) for u in manifest["allow_uids"]]
    for spec in (a.org or []):
        if "=" not in spec:
            print(f"--org takes name=path: {spec!r}", file=sys.stderr)
            return 2
        name, path = spec.split("=", 1)
        roots[name] = os.path.abspath(path)
        if not os.path.isdir(roots[name]):
            print(f"the ledger root does not exist: {roots[name]}", file=sys.stderr)
            return 2
    if not roots:
        print("writerd: no write target resolved (pass --manifest or --org)", file=sys.stderr)
        return 2
    sock = (manifest or {}).get("socket") or a.socket or socket_path(list(roots.values())[0])
    if not sock:
        print("no socket path resolved (pass --socket or set ORG_WRITER_SOCKET)", file=sys.stderr)
        return 2
    for err in (check_socket_length(sock),
                check_socket_parent(sock, require_root_owned=a.require_root_owned)):
        if err:
            print(f"writerd: {err}", file=sys.stderr)
            return 4
    # **壊れた trust なら socket を作る前に止める。** 実測（再監査5回目）で計装したところ、
    # 検証が bind / listen の **後**にあり、socket が一瞬できてから消えていた。
    # 接続は受け付けないので穴ではないが、**「listen した」という信号を出してから死ぬ**のは
    # 観測する側にとって嘘である。flag / manifest / env のどれで決まっても、ここを通る。
    # `w`（Writer）は bind の後で作られるので、ここでは **同じ3つの出所**から直接決める。
    # 優先順位は下の代入と同じ: 明示 --trust > manifest > env。
    _flag_trust = None
    for _pair in (getattr(a, "trust", None) or []):
        if "=" in _pair:
            _flag_trust = _pair.split("=", 1)[1]
    _mani = (manifest or {})
    _mani_trust = _mani.get("trust")
    if not _mani_trust and isinstance(_mani.get("orgs"), dict) and _mani["orgs"]:
        _first = _mani["orgs"].get(sorted(_mani["orgs"])[0]) or {}
        _mani_trust = _first.get("trust")
    _effective_trust = _flag_trust or _mani_trust or os.environ.get("ORG_TRUST_STORE")
    if _effective_trust:
        _bad = _trust_store_defect(_effective_trust)
        if _bad:
            sys.stderr.write(f"writerd: trust store が使えない: {_effective_trust}\n  {_bad}\n"
                             f"  **壊れた trust で起動すると receipt を検証できないまま"
                             f"受け付けてしまう。**\n")
            return 2
    if os.path.exists(sock):
        os.unlink(sock)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock)
    # **接続は誰でもできる必要がある。** 別 UID の writer が 0600 で作ると、caller は接続
    # すらできない（実測で指摘された）。socket に繋げることと台帳に書けることは別である —
    # 書けるのは writer だけで、繋いだ相手も RPC の検査を通らなければ何も書けない。
    os.chmod(sock, 0o666)
    srv.listen(16)
    # **isolation は実測で決める。** フラグを渡したかどうかで決めてはいけない
    # （実測: --require-root-owned を渡しただけで separate_uid と報告していた）。
    iso = measured_isolation(sock, list(roots.values()))
    allowed = None
    if getattr(a, "allow_uid", None):
        allowed = set()
        for spec in a.allow_uid:
            try:
                allowed.add(int(spec))
            except ValueError:
                import pwd
                try:
                    allowed.add(pwd.getpwnam(spec).pw_uid)
                except KeyError:
                    print(f"writerd: --allow-uid {spec!r} を解決できない", file=sys.stderr)
                    return 2
    w = Writer(roots, require_root_owned=a.require_root_owned, isolation=iso,
               schema=a.schema, allowed_uids=allowed)
    w.sock_path = sock
    # **constitution は推測しない。** installer は台帳の実体を
    # /usr/local/var/orgforge/orgs/<ns>/ledger に置くので、「台帳の親の親が org root」
    # という導出は Stage B では成立しない（実測で指摘された）。導出できないまま起動すると
    # require_attested_identity が届かず、**未認証 admission が通る**。
    # よって: 明示フラグ > manifest > 導出、の順に決め、どれも無ければ **起動しない**。
    # **明示指定は manifest より優先する。** installer は plist で固定して渡す。
    # 渡されなければ従来どおり manifest を見る。どちらも無ければ trust 無しで起動し、
    # receipt は検証できない（= authenticated mode では記録できない。fail-closed）。
    for _pair in (getattr(a, "trust", None) or []):
        if "=" not in _pair:
            sys.stderr.write(f"writerd: --trust は NAME=PATH の形で渡すこと: {_pair}\n")
            return 2
        _k, _v = _pair.split("=", 1)
        if not os.path.exists(_v):
            sys.stderr.write(f"writerd: trust store が無い: {_v}\n")
            return 2
        # **在ることと使えることは別である。** 実測（B2 再監査）: 不正な JSON や
        # 秘密鍵の混入した trust store を渡しても daemon は起動して接続を受け付けた
        # — 存在確認しかしていなかったため。**壊れた trust で listen するなら、
        # receipt は検証できないのに検証済みのように振る舞う**（= 信号が壊れていることが
        # 分からない）。ここで中身まで見て、駄目なら起動しない。
        _bad = _trust_store_defect(_v)
        if _bad:
            sys.stderr.write(f"writerd: trust store が使えない: {_v}\n  {_bad}\n"
                             f"  **壊れた trust で起動すると receipt を検証できないまま"
                             f"受け付けてしまう。**\n")
            return 2
        w.trust = _v          # 現状 Writer は org ごとの trust を1つだけ持つ

    constitutions = {}
    for _pair in (getattr(a, "constitution", None) or []):
        if "=" not in _pair:
            sys.stderr.write(f"writerd: --constitution は NAME=PATH の形で渡すこと: {_pair}\n")
            return 2
        _k, _v = _pair.split("=", 1)
        constitutions[_k] = _v

    for _n, _led in roots.items():
        _spec = ((manifest or {}).get("orgs") or {}).get(_n) or {}
        _con = constitutions.get(_n) or _spec.get("constitution")
        if not _con:
            _abs = os.path.abspath(_led)
            if os.path.basename(os.path.dirname(_abs)) == ".orgforge":
                _cand = os.path.join(os.path.dirname(os.path.dirname(_abs)), "constitution.yaml")
                if os.path.exists(_cand):
                    _con = _cand
        if _con and not os.path.exists(_con):
            sys.stderr.write(f"writerd: constitution が無い: {_con}\n")
            return 2
        if _con:
            w.org_constitutions[_n] = os.path.abspath(_con)
            # **写しが古くなったことを、黙って起こさない。**
            # 固定した写しは org 側の編集を受け取らない（受け取ったら caller が強制を消せる）。
            # だが「編集したのに効かない」を無言で起こすと、宣言が効いていると誤認したまま
            # 運用が続く — **信号が壊れていることが分からない** 形になる。起動時に言う。
            _org_side = None
            _abs = os.path.abspath(_led)
            if os.path.basename(os.path.dirname(_abs)) == ".orgforge":
                _org_side = os.path.join(os.path.dirname(os.path.dirname(_abs)),
                                         "constitution.yaml")
            if _org_side and os.path.exists(_org_side) and \
                    os.path.abspath(_org_side) != os.path.abspath(_con):
                try:
                    with open(_org_side, "rb") as _f1, open(_con, "rb") as _f2:
                        if _f1.read() != _f2.read():
                            sys.stderr.write(
                                f"writerd: 警告 — org 側の constitution が固定した写しと違う。\n"
                                f"  効いているのは: {_con}\n"
                                f"  編集されたのは: {_org_side}\n"
                                f"  **org 側を編集しても daemon には届かない。**"
                                f" installer を再実行して固定し直すこと。\n")
                except OSError:
                    pass
        else:
            # **宣言の在り処が分からないまま書き込みを受け付けない。**
            sys.stderr.write(
                f"writerd: org '{_n}' の constitution を決められない。\n"
                f"  台帳: {_led}\n"
                f"  --constitution {_n}=<path> を渡すか、manifest に constitution を書くこと。\n"
                f"  **これが無いと require_attested_identity が子プロセスに届かず、\n"
                f"    未認証の admission が通る**（実測で指摘された経路）。\n")
            return 2
    if manifest:
        first = manifest["orgs"].get(list(roots)[0]) or {}
        w.trust = first.get("trust") or manifest.get("trust")
        w.policy = manifest.get("policy")
    print(json.dumps({"listening": sock, "orgs": sorted(roots),
                      "workload_isolation": iso,
                      "note": ("同一 UID の writerd は OS 境界ではない — caller は daemon を"
                               "止められる。separate_uid には別 UID と root 所有の親ディレクトリ"
                               "が必要である。")}, ensure_ascii=False), flush=True)
    if a.pidfile:
        with open(a.pidfile, "w") as f:
            f.write(str(os.getpid()))
    try:
        while True:
            conn, _ = srv.accept()
            try:
                conn.settimeout(30)
                uid, pid = peer_credential(conn)
                buf = b""
                while len(buf) <= _MAX_REQUEST:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                    if buf.endswith(b"\n"):
                        break
                try:
                    req = json.loads(buf.decode("utf-8"))
                except Exception as e:
                    resp = {"ok": False, "reason": "bad_json", "detail": str(e)}
                else:
                    resp, _ok = w.handle(req, uid, pid)
                conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            except Exception as e:
                try:
                    conn.sendall((json.dumps({"ok": False, "reason": "handler_error",
                                              "detail": str(e)}) + "\n").encode())
                except Exception:
                    pass
            finally:
                conn.close()
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            os.unlink(sock)
        except OSError:
            pass
        if a.pidfile and os.path.exists(a.pidfile):
            os.unlink(a.pidfile)


def call(op, argv, org="default", sock=None, require_root_owned=False):
    """writerd に要求を送る。(response, error)。**daemon が居なければ error。**

    daemon が停止していることを「書けた」と読み替えない — 呼び出し側は fail-closed にする。
    """
    import secrets
    sock = sock or socket_path()
    if not sock:
        return None, "writer socket のパスが決まらない。"
    err = check_socket_parent(sock, require_root_owned=require_root_owned)
    if err:
        return None, err
    if not os.path.exists(sock):
        return None, (f"writer socket が無い: {sock}\n"
                      f"  **daemon が動いていない。** 書き込みは通さない — 台帳への経路が"
                      f"writerd だけなら、居ないことは「書けない」ことである。")
    req = {"protocol": PROTOCOL, "op": op, "argv": list(argv), "org": org,
           "nonce": secrets.token_hex(16)}
    req["digest"] = request_digest(req)
    try:
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.settimeout(150)
        c.connect(sock)
        c.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = c.recv(65536)
            if not chunk:
                break
            buf += chunk
        c.close()
    except OSError as e:
        if e.errno in (errno.ECONNREFUSED, errno.ENOENT):
            return None, f"writerd に接続できない（{e}）。**daemon が動いていない。**"
        return None, f"writerd との通信に失敗した: {e}"
    try:
        return json.loads(buf.decode("utf-8")), None
    except Exception as e:
        return None, f"writerd の応答を読めない: {e}"


def main(argv):
    p = argparse.ArgumentParser(
        prog="writerd",
        description="台帳への書き込みを1プロセスに集約する（段階A: process_mediated）")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("serve", help="socket を開いて要求を待つ")
    q.add_argument("--manifest", default=None,
                   help="root 所有の manifest。**あればこれが最終** — org / schema / policy / "
                        "trust / allow_uids を caller の環境ではなくここから取る")
    q.add_argument("--org", action="append", metavar="NAME=LEDGER_ROOT",
                   help="書いてよい台帳。**caller はパスを指定できず、この name で選ぶ**")
    q.add_argument("--socket", default=None)
    q.add_argument("--pidfile", default=None)
    q.add_argument("--require-root-owned", dest="require_root_owned", action="store_true",
                   help="socket の anchor が root 所有であることを要求する（段階B）")
    q.add_argument("--allow-uid", action="append", metavar="UID_OR_NAME", dest="allow_uid",
                   help="書き込みを認可する peer（複数可）。**socket は 0666 なので、繋げる"
                        "ことと書けることは別である**。省略すると制限しない（段階A）")
    q.add_argument("--schema", default=None,
                   help="ledger-schema.yaml のパス。**root 所有の設定から固定する** — "
                        "渡さないと ledger.py が cwd から探し、テンプレートに fallback する")
    q.add_argument("--constitution", action="append", metavar="NAME=PATH",
                   dest="constitution",
                   help="org の constitution.yaml。**root 所有の設定から固定する** — "
                        "daemon は org の外で動くので cwd から探せない。渡さないと "
                        "require_attested_identity が子プロセスに届かず、**未認証の "
                        "admission が通る**（実測で指摘された）")
    q.add_argument("--trust", action="append", metavar="NAME=PATH", dest="trust",
                   help="org の trust store（鍵 registry）。**root 所有の設定から固定する** — "
                        "daemon は org の外（cwd=/）で動くので探索では見つからない。"
                        "渡さないと **正しく署名された receipt も検証できず**、認証済みの "
                        "記録が一切残せない（実測: Stage B の正規経路が完全に停止した）")
    q.set_defaults(fn=serve)
    q = sub.add_parser("check", help="socket と親ディレクトリを検証する（書き込みはしない）")
    q.add_argument("--socket", default=None)
    q.add_argument("--require-root-owned", dest="require_root_owned", action="store_true")
    q.set_defaults(fn=lambda a: _cmd_check(a))
    a = p.parse_args(argv[1:])
    return a.fn(a)


def _cmd_check(a):
    sock = a.socket or socket_path()
    if not sock:
        print(json.dumps({"ok": False, "reason": "no_socket_path"}, ensure_ascii=False))
        return 2
    err = check_socket_parent(sock, require_root_owned=a.require_root_owned)
    root = os.path.dirname(os.path.abspath(sock))
    org_root = os.path.dirname(os.path.dirname(root)) if ".orgforge" in root else None
    assets = audit_writer_assets(root, org_root,
                                 require_owner_uid=0 if a.require_root_owned else None)
    print(json.dumps({"ok": err is None and not assets, "socket": sock, "detail": err,
                      "asset_issues": [{"path": p, "issue": i} for p, i in assets],
                      "daemon_running": os.path.exists(sock),
                      # **実測。** フラグでも、err が無いことでもなく、状態を見て決める。
                      "workload_isolation": (measured_isolation(sock, [root])
                                             if not assets else "process_mediated")},
                     ensure_ascii=False))
    return 0 if (err is None and not assets) else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
