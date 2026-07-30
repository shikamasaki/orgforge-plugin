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
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self._seen = {k: float(v) for k, v in (json.load(f) or {}).items()}
            except Exception:
                self._seen = {}          # 読めないなら空から始める

    def check_and_add(self, nonce):
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
                    raise OSError(f"nonce を永続化できない: {e}")
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
        self.caller_uid_differs = caller_uid_differs
        self.sock_path = None                   # serve が設定する
        self.allowed_uids = allowed_uids        # None = 制限なし（段階A）
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
        if op not in ("append", "trip-halt", "release-halt", "reserve-exposure"):
            return {"ok": False, "reason": "unsupported_op",
                    "detail": f"op={op!r} は writerd 経由では実行できない"
                              f"（append / trip-halt / release-halt / reserve-exposure）。"}, False
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
        # **要求ごとに実測する。** 起動時の判定では caller が誰か分からない。
        env["ORG_WRITER_ISOLATION"] = measured_isolation(
            self.sock_path, list(self.roots.values()), peer_uid=peer_uid)
        env["ORG_WRITER_PEER_UID"] = str(peer_uid) if peer_uid is not None else ""
        env["ORG_WRITER_PEER_PID"] = str(peer_pid) if peer_pid is not None else ""
        env["ORG_INSIDE_WRITER"] = "1"          # ledger.py がこれを見て直接書き込みを許す
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


def serve(a):
    """socket を開いて要求を待つ。**親ディレクトリを検証してから開く。**"""
    roots = {}
    for spec in a.org:
        if "=" not in spec:
            print(f"--org は name=path の形で渡すこと: {spec!r}", file=sys.stderr)
            return 2
        name, path = spec.split("=", 1)
        roots[name] = os.path.abspath(path)
        if not os.path.isdir(roots[name]):
            print(f"台帳のルートが無い: {roots[name]}", file=sys.stderr)
            return 2
    sock = a.socket or socket_path(list(roots.values())[0] if roots else None)
    if not sock:
        print("socket のパスが決まらない（--socket か ORG_WRITER_SOCKET）", file=sys.stderr)
        return 2
    for err in (check_socket_length(sock),
                check_socket_parent(sock, require_root_owned=a.require_root_owned)):
        if err:
            print(f"writerd: {err}", file=sys.stderr)
            return 4
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
    q.add_argument("--org", action="append", required=True, metavar="NAME=LEDGER_ROOT",
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
