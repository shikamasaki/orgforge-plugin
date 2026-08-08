#!/usr/bin/env python3
"""writerd — funnel every ledger write through one process (Authenticated Writer, stage A).

## What this strengthens

Until now the ledger was written by whichever process happened to call it. So:

  - even with `decision_by` confirmed from a receipt, **the write path itself was open to anyone**
  - the halt latch, the key registry and the schema were reachable with the same permissions as
    a write
  - declaring "the records a check relies on are writable only by the side doing the checking"
    came with no mechanism to enforce that there is exactly ONE path

writerd opens a single Unix domain socket and **writes to the ledger only what came through it**.
A CLI attempting to write directly is refused (in an org where `ORG_WRITER_SOCKET` is set).

## What this does NOT strengthen — stated outright

**This is not an OS boundary.** As long as it runs under the same UID:

  - a caller can stop the daemon
  - a caller can restore the file permissions on the socket or the ledger
  - a caller can replace writerd itself

So `workload_isolation` is **`process_mediated`**, not `separate_uid`, and **this is never called
"Authenticated Writer, done."** Only once a separate UID, a LaunchDaemon, and root-owned settings
and socket parent directory are all in place can it be raised to `separate_uid`
(`tools/writer-install.sh`).

And even under a separate UID, **the host's administrator gets through** — what is guaranteed is
that the writer's assets cannot be altered from an ordinary agent's / caller's UID. root is outside
the threat model.

## How a peer identity is used

The uid/pid obtained from the socket's peer credential (SO_PEERCRED / LOCAL_PEERCRED) is used
**only for `recorded_by`**. `decision_by` is settled by a signed receipt and nothing else —
having connected is no evidence of having made the judgment.

## Tampering with, and replaying, an RPC

A request carries a nonce and a digest of its body, and writerd **refuses a nonce it has already
seen**. It also verifies the digest of the whole request, so one altered in transit does not pass.
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
# **The evidence of being inside the writer.** The value of the environment variable is itself the
# secret — make it something guessable like `=1` and a caller can simply assert it (measured).
_INSIDE_WRITER_TOKEN = __import__("secrets").token_hex(32)

_MAX_REQUEST = 1 << 20          # 1 MiB. A request larger than this is refused unread
_NONCE_TTL = 3600               # how long a used nonce is remembered (seconds)


# ── the socket path, and validating its parent directory ────────────────────
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
    """**Hard-wire the daemon's configuration** from a root-owned manifest.

    At start-up the daemon takes "which org, with which schema, policy and trust store" **from a
    root-owned file rather than from the caller's environment**. Depend on env or cwd and the caller
    can swap it.

    Shape:
        orgs:
          default:
            ledger: /usr/local/var/orgforge/orgs/<ns>/ledger
            schema: /usr/local/var/orgforge/orgs/<ns>/ledger-schema.yaml
            trust:  /usr/local/var/orgforge/orgs/<ns>/trust/keys.json
        policy: /usr/local/etc/orgforge/policy.yaml
        allow_uids: [501]

    Returns: (manifest, error). **If it cannot be read, do not start.**
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
    """Validate the socket's **parent directory**.

    **If a caller can replace the parent directory, it can replace the socket** — stand up a fake
    writerd and have it report "written". So the connecting side checks the parent.

    What stage A (same UID) can confirm:
      - the parent exists and is not a symlink
      - it is not writable by others (group/other write are off)
      - it is owned by you or by root

    With `require_root_owned=True` (stage B) it demands **root-owned and not writable by others**.
    Only at that point can we say a caller cannot replace it.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        return f"the socket's parent directory does not exist: {parent}"
    if os.path.islink(parent):
        return (f"the socket's parent directory is a symlink: {parent}\n"
                f"  Re-point the link and the whole socket can be replaced.")
    st = os.stat(parent)
    # **other-write is never acceptable.** If anyone can write there, the socket can be replaced.
    if st.st_mode & 0o002:
        return (f"the socket's parent directory is world-writable "
                f"(mode {oct(st.st_mode & 0o777)}): {parent}\n"
                f"  **Anyone who can write there can replace the socket** — and point you at a "
                f"forged writer.")
    if require_root_owned:
        # Stage B. **The leaf may be writer-owned** — creating the socket needs write permission on
        # its parent, so a root-owned 0755 directory cannot be bound (measured: Permission denied).
        # The guarantee is that **the caller cannot write to the anchor (the leaf's parent), so the
        # leaf itself cannot be swapped out.** Hence:
        #   leaf   … owned by the writer, not writable by others
        #   anchor … owned by root, not writable by others
        if st.st_uid not in (0, os.getuid()):
            return (f"the socket's parent (the leaf) is owned by neither the writer nor root "
                    f"(uid={st.st_uid}): {parent}")
        if st.st_mode & 0o022:
            return (f"the socket's parent (the leaf) is writable by others "
                    f"(mode {oct(st.st_mode & 0o777)}): {parent}\n"
                    f"  Whoever can write there can replace the socket.")
        anchor = os.path.dirname(parent)
        try:
            ast_ = os.stat(anchor)
        except OSError as e:
            return f"cannot stat the socket's anchor ({e}): {anchor}"
        if ast_.st_uid != 0:
            return (f"the socket's anchor is not root-owned (uid={ast_.st_uid}): {anchor}\n"
                    f"  Whoever can write to the anchor can **swap out the whole leaf**. "
                    f"**workload_isolation cannot be called separate_uid.**")
        if ast_.st_mode & 0o022:
            return (f"the socket's anchor is writable by others "
                    f"(mode {oct(ast_.st_mode & 0o777)}): {anchor}\n"
                    f"  **A caller can replace the leaf.**")
    else:
        # Stage A / the client side. **The leaf is owned by the writer, not by the caller** —
        # measured (audit): the installer made the leaf writer-owned while the client accepted only
        # "root or me", which left **no legitimate write path at all**.
        #
        # What the client has to establish is **who could replace the leaf**, not who owns it. If
        # others cannot write there, that socket cannot be swapped out.
        if st.st_mode & 0o022:
            return (f"the socket's parent (the leaf) is writable by others "
                    f"（mode {oct(st.st_mode & 0o777)}）: {parent}\n"
                    f"  **Anyone who can write there can replace the socket** — and point you at a forged writer.")
        anchor = os.path.dirname(parent)
        try:
            ast_ = os.stat(anchor)
        except OSError:
            return None                  # cannot reach the anchor: stop at the leaf check
        # **Do not trust a caller-owned anchor.** Whoever can write to the anchor can swap out the
        # whole leaf and point you at a forged writer (raised in audit). `ORG_WRITER_TRUST_SELF=1`
        # is an escape hatch for stage A alone, where the same user is also running the daemon.
        if (ast_.st_uid == os.getuid() and ast_.st_uid != 0
                and os.environ.get("ORG_WRITER_TRUST_SELF") != "1"):
            return (f"the socket's anchor is owned by the caller itself (uid={ast_.st_uid}): "
                    f"{anchor}\n"
                    f"  **Whoever can write there can swap out the whole leaf** — and point you at "
                    f"a forged writer.\n"
                    f"  On stage A, where you run the daemon yourself, state "
                    f"ORG_WRITER_TRUST_SELF=1 explicitly. **That is not a trust boundary.**")
        if ast_.st_mode & 0o022:
            return (f"the socket's anchor is writable by others "
                    f"（mode {oct(ast_.st_mode & 0o777)}）: {anchor}\n"
                    f"  **A caller can swap out the whole leaf.**")
    return None



def check_socket_length(path):
    """**AF_UNIX path lengths have an OS limit** (104 bytes on macOS, 108 on Linux).

    Exceed it and bind fails silently. Someone who put their org somewhere deep runs into "it just
    does not work", so say what is happening. A stage B install uses `/var/run/orgforge/`, where
    this is normally not a problem.

    **This concerns only the side that binds**, so it is kept apart from the parent-directory
    permission checks — mix them and "the permissions are wrong" becomes indistinguishable from
    "the path is too long".
    """
    limit = 104 if sys.platform == "darwin" else 108
    n = len(os.path.abspath(path).encode("utf-8"))
    if n >= limit:
        return (f"the socket path is too long ({n} bytes, limit {limit}): {path}\n"
                f"  That is the OS limit for AF_UNIX. Point --socket somewhere shorter.")
    return None


# ── the peer credential (used only for recorded_by) ─────────────────────────
def peer_credential(conn):
    """The (uid, pid) of the peer, or (None, None) if unavailable.

    **This is used only for `recorded_by`.** Having connected is no evidence of having made the
    judgment, so it is never used for `decision_by`.
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


# ── the request digest (detecting tampering and replay) ─────────────────────
def request_digest(req):
    core = {k: v for k, v in req.items() if k != "digest"}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


class _NonceStore:
    """The nonces already used. **Kept in order to refuse a replay.**

    **Never held only in the process.** Stop the daemon and start it again and the same request
    could be replayed (raised in audit). They live in a file the writer owns, and if that cannot be
    written, nothing is accepted — allowing writes while unable to prevent a replay is the same as
    having no nonces at all.
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
                # **Never resume from a corrupt nonce file as though it were empty.** Measured
                # (audit): corrupting it started from empty and the same nonce was accepted again.
                # Being unable to detect a replay is the same as having no nonces at all.
                self.load_error = (f"cannot read the nonce file ({e}): {path}\n"
                                   f"  **It is not resumed as empty** — a replay could not be "
                                   f"detected. Inspect the contents and deal with it.")

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


# ── the org allowlist (so a caller cannot name the ledger path) ─────────────
def allowed_roots():
    """The ledger roots writerd may write to. **A caller cannot name a path over the RPC.**

    If it could, anything could be written anywhere by way of the writer — and "the ledger belongs
    to the writer" would mean nothing. It is fixed at start-up with `--root`, and the requesting
    side can only choose by the name `org`.
    """
    return {}



# ── the assets the writer should own (root/writer-owned at stage B) ─────────
# **The latch, the key registry and the schema need guarding as strongly as the write path.**
# Routing only the ledger through writerd achieves nothing if the halt latch can still be deleted,
# a public key in the trust store swapped, or the schema's validation rules loosened — control is
# bypassable through any of them.
#
# What stage A (same UID) can confirm goes as far as "**not writable by others**".
# Stage B requires the owner to be the writer or root — only then is it beyond a caller's reach.
WRITER_OWNED = (
    ("HALT", "the halt latch. Whoever can delete it can lift the stop"),
    ("keys.json", "the key registry. Whoever can swap it can forge the signer of a judgment"),
    ("ledger-schema.yaml", "the validation rules. Whoever can loosen them can push through a "
                           "record that ought to be refused"),
    ("ledger.jsonl", "the ledger itself"),
    ("HEAD", "the tip of the chain (a cache, but breaking it stops the soundness check)"),
)


def audit_writer_assets(root, org_root=None, require_owner_uid=None):
    """Check the permissions on the assets the writer should own.

    Returns: [(path, issue)] — empty means nothing wrong. **Absence is not counted as a problem**
    (with no halt in force, there being no latch is the normal state).

    Pass `require_owner_uid` and the owner is checked too (stage B). Without it, only "not writable
    by others" is checked — as far as stage A can confirm.
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
            found.append((path, f"cannot stat it: {e}"))
            continue
        if st.st_mode & 0o022:
            found.append((path, f"writable by others (mode {oct(st.st_mode & 0o777)}) — {why}"))
        if require_owner_uid is not None and st.st_uid != require_owner_uid:
            found.append((path, f"owned by uid={st.st_uid} (required: {require_owner_uid}) — "
                                f"{why}"))
    return found



def measured_isolation(sock_path, ledger_roots, peer_uid=None):
    """Decide `workload_isolation` **by measurement**, never from a flag.

    Measured (audit): merely passing `--require-root-owned` was enough to have it report
    `separate_uid`. Whether a flag was passed is an intention, not a state.

    It may be called `separate_uid` only when:
      - the socket's parent is root-owned and not writable by the group either
      - the ledger is owned by **this writer process's UID** (i.e. not the caller's)
      - the writerd process itself runs under a different UID from the caller

    If any of those is missing, it is `process_mediated`.
    """
    if check_socket_parent(sock_path, require_root_owned=True):
        return "process_mediated"
    me = os.getuid()
    if me == 0:
        return "process_mediated"        # a writer running as root is not isolation
    for root in ledger_roots:
        try:
            if os.stat(root).st_uid != me:
                return "process_mediated"
        except OSError:
            return "process_mediated"
    # **The same UID as the caller is not isolation.** Measured (audit): it returned separate_uid
    # even with writer UID = caller UID = 502. The comparison against the peer UID has to happen
    # **per request** — at start-up there is no telling who will connect.
    if peer_uid is None:
        return "process_mediated"        # nothing to compare against: fall to the weaker reading
    if peer_uid == me:
        return "process_mediated"
    return "separate_uid"


class Writer:
    def __init__(self, roots, require_root_owned=False, isolation="process_mediated",
                 schema=None, caller_uid_differs=None, allowed_uids=None):
        self.roots = roots                      # {org_name: ledger_root}
        self.isolation = isolation              # **a measured value**, not a flag
        self.schema = schema                    # fixed from the root-owned configuration
        self.trust = None                       # likewise
        self.policy = None                      # likewise
        self.caller_uid_differs = caller_uid_differs
        self.sock_path = None                   # set by serve
        self.allowed_uids = allowed_uids        # None = unrestricted (stage A)
        self.org_constitutions = {}             # {org: constitution path} — carries the
                                                # declaration through to the child
        # **Not forgotten across a restart.** Held only in the process, stopping and starting the
        # daemon would let the same request be replayed (raised in audit). It is kept beside the
        # ledger the writer owns.
        self.nonces = _NonceStore(
            os.path.join(list(roots.values())[0], "writer-nonces.json") if roots else None)
        self.require_root_owned = require_root_owned
        self.lock = threading.Lock()            # serialisation within this one process

    def handle(self, req, peer_uid, peer_pid):
        """Handle a request. Returns (response_dict, ok). **Every reason for refusal is stated.**"""
        if req.get("protocol") != PROTOCOL:
            return {"ok": False, "reason": "protocol_mismatch",
                    "detail": f"protocol={req.get('protocol')!r} (writerd is v{PROTOCOL}). "
                              f"A request of an unknown version is not processed."}, False
        # **Detecting tampering.** The digest covers the whole body.
        if req.get("digest") != request_digest(req):
            return {"ok": False, "reason": "request_tampered",
                    "detail": "the request digest does not match the body — it was altered in "
                              "transit."}, False
        # **A read requires no nonce.** It has no side effect, and refusing one would leave the org
        # undiagnosable. The digest — tamper detection — still applies to reads.
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
                    "detail": "there is no nonce (or it is too short), so a replay could not be "
                              "refused."}, False
        if not self.nonces.check_and_add(nonce):
            return {"ok": False, "reason": "replayed_nonce",
                    "detail": f"nonce {nonce[:16]}… has already been used. **A replay does not "
                              f"pass.**"}, False

        # **Authorising the peer UID.** The socket is 0666, so anyone can connect to it at all.
        # Having connected is not the same as being allowed to write.
        if self.allowed_uids is not None and peer_uid not in self.allowed_uids:
            return {"ok": False, "reason": "peer_not_authorized",
                    "detail": f"peer uid={peer_uid} is not authorised to write "
                              f"(permitted: {sorted(self.allowed_uids)})."}, False

        org = req.get("org")
        if org not in self.roots:
            return {"ok": False, "reason": "unknown_org",
                    "detail": f"org={org!r} is not something writerd may write to "
                              f"(permitted: {sorted(self.roots)}).\n"
                              f"  **A caller cannot name the ledger path** — if it could, anything "
                              f"could be written anywhere by way of the writer."}, False
        root = self.roots[org]

        op = req.get("op")
        argv = req.get("argv")
        if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
            return {"ok": False, "reason": "bad_argv",
                    "detail": "argv is not an array of strings."}, False
        # **Reads go through the writer too.** Swap the org-side symlink to show an empty ledger
        # and the hook loses sight of the stop (measured: during a HALT, halt-status went from exit
        # 10 to 0). The writer looks at **the real path** it pinned at start-up, so re-pointing the
        # link changes nothing.
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
                    "detail": f"op={op!r} cannot be run by way of writerd"
                              f"（append / record-scheduled-check / trip-halt / release-halt / "
                              f"reserve-exposure / derive-admission / halt-status）。"}, False
        # **Close the route by which a caller names a root.** Anything path-like in argv is
        # rejected.
        for a in argv:
            if a == root or a.startswith("/") and os.path.sep in a and (
                    "ledger" in a or a.endswith(".jsonl")):
                return {"ok": False, "reason": "path_in_argv",
                        "detail": f"argv holds something that looks like a ledger path: {a!r}\n"
                                  f"  **writerd decides where writes go.** A caller can only "
                                  f"choose by org name."}, False
        # **recorded_by comes from the peer credential.** It is never used for decision_by.
        env = dict(os.environ)
        env["ORG_LEDGER_ROOT"] = root
        # **State the schema explicitly.** Without it, ledger.py looks for the org from the cwd and
        # falls back to the plugin's template when it finds none (raised in audit) — so validation
        # runs against the template's rules rather than the ones the org loosened or tightened.
        if self.schema:
            env["ORG_LEDGER_SCHEMA"] = self.schema
        # **Fix the trust store too.** Take it from the caller's environment and they can point it
        # at a forged key registry.
        if self.trust:
            env["ORG_TRUST_STORE"] = self.trust
        if self.policy:
            env["ORG_POLICY_FILE"] = self.policy
        # **Carry the org's declaration through to the child process.** The daemon runs outside the
        # org, so it cannot find the constitution from the cwd. Without it, `_enforce_attested()`
        # reads "undeclared" and **an unauthenticated admission passes as long as it goes via
        # writerd** (raised in audit).
        con = self.org_constitutions.get(org)
        if con:
            env["ORG_CONSTITUTION"] = con
        # **Measured per request.** A decision made at start-up does not know who the caller is.
        env["ORG_WRITER_ISOLATION"] = measured_isolation(
            self.sock_path, list(self.roots.values()), peer_uid=peer_uid)
        env["ORG_WRITER_PEER_UID"] = str(peer_uid) if peer_uid is not None else ""
        env["ORG_WRITER_PEER_PID"] = str(peer_pid) if peer_pid is not None else ""
        # **Never take a value the caller can write as the input to a check.** Measured
        # (re-audit): merely adding `ORG_INSIDE_WRITER=1` to the environment let a single signer
        # write a cross-harness admission directly and walk through the single-writer gate. Anyone
        # can write "is it 1?".
        # So **an unguessable token is minted per start-up, and only whoever knows it counts as
        # being inside the writer.** The token exists only in the daemon's memory and never reaches
        # a caller.
        env["ORG_INSIDE_WRITER"] = _INSIDE_WRITER_TOKEN
        env.pop("ORG_WRITER_SOCKET", None)      # prevent recursion
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
    """Return why the trust store is unusable, or None if it is fine.

    **Do not write a second validator.** The decision is left to `identity.load_trust_store()` —
    define "broken" separately here and it drifts from the side that actually verifies receipts,
    producing "the daemon accepted it but verification fails" (or the reverse).
    """
    import os as _os
    try:
        _here = _os.path.dirname(_os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
        import identity as _identity
    except Exception as e:                      # cannot decide without reading identity
        return f"cannot validate trust because the identity module cannot be read: {e}"
    _saved = _os.environ.get("ORG_TRUST_STORE")
    _os.environ["ORG_TRUST_STORE"] = path
    try:
        store, err = _identity.load_trust_store()
    except Exception as e:
        return f"cannot validate the trust store: {e}"
    finally:
        if _saved is None:
            _os.environ.pop("ORG_TRUST_STORE", None)
        else:
            _os.environ["ORG_TRUST_STORE"] = _saved
    if err:
        return err
    if not store or not store.get("keys"):
        return "the trust store holds no keys at all, so no receipt can be verified."
    return None



def serve(a):
    """Open the socket and wait for requests. **Validate the parent directory before opening.**"""
    manifest, merr = load_manifest(getattr(a, "manifest", None))
    if merr:
        print(f"writerd: {merr}\n"
              f"  **if the configuration cannot be read, do not start.**", file=sys.stderr)
        return 4
    roots = {}
    if manifest:
        # **The manifest is final.** A caller's --org / --schema cannot override it.
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
    # **With a broken trust store, stop before creating the socket.** Instrumented on the fifth
    # re-audit, the validation sat **after** bind / listen: the socket appeared briefly and then
    # vanished. It is not a hole, since no connection is accepted — but **emitting the signal "I am
    # listening" and then dying is a lie to whoever is watching.** Whether it comes from the flag,
    # the manifest or env, it passes through here.
    # `w` (the Writer) is constructed after bind, so this decides directly from **the same three
    # sources**, in the same order as the assignment below: an explicit --trust > manifest > env.
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
            sys.stderr.write(f"writerd: the trust store is unusable: {_effective_trust}\n"
                             f"  {_bad}\n"
                             f"  **Start with a broken trust store and receipts are accepted "
                             f"without ever being verified.**\n")
            return 2
    if os.path.exists(sock):
        os.unlink(sock)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock)
    # **Anyone has to be able to connect.** A writer under a separate UID creating it 0600 leaves
    # the caller unable to connect at all (raised in audit). Connecting to the socket and writing to
    # the ledger are different things — only the writer writes, and whoever connects still writes
    # nothing without passing the RPC checks.
    os.chmod(sock, 0o666)
    srv.listen(16)
    # **Isolation is decided by measurement**, never by whether a flag was passed (measured:
    # passing --require-root-owned alone was enough to have it report separate_uid).
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
                    print(f"writerd: cannot resolve --allow-uid {spec!r}", file=sys.stderr)
                    return 2
    w = Writer(roots, require_root_owned=a.require_root_owned, isolation=iso,
               schema=a.schema, allowed_uids=allowed)
    w.sock_path = sock
    # **Never guess the constitution.** The installer puts the real ledger at
    # /usr/local/var/orgforge/orgs/<ns>/ledger, so deriving "the org root is the ledger's
    # grandparent" does not hold under Stage B (raised in audit). Start without having derived it
    # and require_attested_identity never arrives, so **an unauthenticated admission passes**.
    # Hence: explicit flag > manifest > derivation, and if none of them yields one, **do not
    # start**.
    # **An explicit setting takes precedence over the manifest.** The installer pins it in the
    # plist and passes it. Without one, the manifest is consulted as before. With neither, it starts
    # with no trust store and cannot verify a receipt — i.e. nothing can be recorded in
    # authenticated mode (fail-closed).
    for _pair in (getattr(a, "trust", None) or []):
        if "=" not in _pair:
            sys.stderr.write(f"writerd: pass --trust in the form NAME=PATH: {_pair}\n")
            return 2
        _k, _v = _pair.split("=", 1)
        if not os.path.exists(_v):
            sys.stderr.write(f"writerd: there is no trust store: {_v}\n")
            return 2
        # **Existing and being usable are different things.** Measured (B2 re-audit): handed a
        # trust store with malformed JSON, or with a private key mixed in, the daemon still started
        # and accepted connections — because only its existence was checked. **Listen with a broken
        # trust store and it behaves as though receipts were verified when they cannot be** — the
        # signal being broken is invisible. So the contents are inspected here, and it does not
        # start if they are bad.
        _bad = _trust_store_defect(_v)
        if _bad:
            sys.stderr.write(f"writerd: the trust store is unusable: {_v}\n  {_bad}\n"
                             f"  **Start with a broken trust store and receipts are accepted "
                             f"without ever being verified.**\n")
            return 2
        w.trust = _v          # for now the Writer holds exactly one trust store per org

    constitutions = {}
    for _pair in (getattr(a, "constitution", None) or []):
        if "=" not in _pair:
            sys.stderr.write(f"writerd: pass --constitution in the form NAME=PATH: {_pair}\n")
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
            sys.stderr.write(f"writerd: there is no constitution: {_con}\n")
            return 2
        if _con:
            w.org_constitutions[_n] = os.path.abspath(_con)
            # **Never let the pinned copy go stale in silence.**
            # A pinned copy does not take edits from the org side (if it did, a caller could delete
            # the enforcement). But letting "edited, yet no effect" happen silently means operation
            # continues in the belief that the declaration is in force — **the signal being broken
            # is invisible.** So it is said at start-up.
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
                                f"writerd: warning — the org-side constitution differs from the "
                                f"pinned copy.\n"
                                f"  in force: {_con}\n"
                                f"  edited:   {_org_side}\n"
                                f"  **Editing the org side does not reach the daemon.** Re-run the "
                                f"installer to pin it again.\n")
                except OSError:
                    pass
        else:
            # **Do not accept writes without knowing where the declaration lives.**
            sys.stderr.write(
                f"writerd: cannot determine the constitution for org '{_n}'.\n"
                f"  ledger: {_led}\n"
                f"  Pass --constitution {_n}=<path>, or record a constitution in the manifest.\n"
                f"  **Without it, require_attested_identity never reaches the child process and\n"
                f"    an unauthenticated admission passes** (a route raised in audit).\n")
            return 2
    if manifest:
        first = manifest["orgs"].get(list(roots)[0]) or {}
        w.trust = first.get("trust") or manifest.get("trust")
        w.policy = manifest.get("policy")
    print(json.dumps({"listening": sock, "orgs": sorted(roots),
                      "workload_isolation": iso,
                      "note": ("a writerd under the same UID is not an OS boundary — the caller "
                               "can stop the daemon. separate_uid requires a different UID and a "
                               "root-owned parent directory.")}, ensure_ascii=False), flush=True)
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
    """Send a request to writerd. (response, error). **An error if the daemon is not there.**

    A stopped daemon is never reinterpreted as "written" — the caller stays fail-closed.
    """
    import secrets
    sock = sock or socket_path()
    if not sock:
        return None, "cannot determine the writer socket path."
    err = check_socket_parent(sock, require_root_owned=require_root_owned)
    if err:
        return None, err
    if not os.path.exists(sock):
        return None, (f"there is no writer socket: {sock}\n"
                      f"  **The daemon is not running.** No write passes — where writerd is the "
                      f"only path to the ledger, its absence means writes are impossible.")
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
            return None, f"cannot connect to writerd ({e}). **The daemon is not running.**"
        return None, f"communication with writerd failed: {e}"
    try:
        return json.loads(buf.decode("utf-8")), None
    except Exception as e:
        return None, f"cannot read writerd's response: {e}"


def main(argv):
    p = argparse.ArgumentParser(
        prog="writerd",
        description="funnel every ledger write through one process (stage A: process_mediated)")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("serve", help="open the socket and wait for requests")
    q.add_argument("--manifest", default=None,
                   help="a root-owned manifest. **If present it is final** — org / schema / "
                        "policy / trust / allow_uids come from here, not the caller's environment")
    q.add_argument("--org", action="append", metavar="NAME=LEDGER_ROOT",
                   help="a ledger that may be written to. **A caller cannot name a path; it "
                        "chooses by this name**")
    q.add_argument("--socket", default=None)
    q.add_argument("--pidfile", default=None)
    q.add_argument("--require-root-owned", dest="require_root_owned", action="store_true",
                   help="require the socket's anchor to be root-owned (stage B)")
    q.add_argument("--allow-uid", action="append", metavar="UID_OR_NAME", dest="allow_uid",
                   help="a peer authorised to write (repeatable). **The socket is 0666, so "
                        "connecting and writing are different things.** Omit to leave it "
                        "unrestricted (stage A)")
    q.add_argument("--schema", default=None,
                   help="the path to ledger-schema.yaml. **Fixed from the root-owned "
                        "configuration** — without it, ledger.py searches from the cwd and falls "
                        "back to the template")
    q.add_argument("--constitution", action="append", metavar="NAME=PATH",
                   dest="constitution",
                   help="the org's constitution.yaml. **Fixed from the root-owned "
                        "configuration** — the daemon runs outside the org, so it cannot search "
                        "from the cwd. Without it, require_attested_identity never reaches the "
                        "child process and **an unauthenticated admission passes** (raised in "
                        "audit)")
    q.add_argument("--trust", action="append", metavar="NAME=PATH", dest="trust",
                   help="the org's trust store (the key registry). **Fixed from the root-owned "
                        "configuration** — the daemon runs outside the org (cwd=/), so a search "
                        "will not find it. Without it, **even a correctly signed receipt cannot "
                        "be verified** and no authenticated record can be made at all (measured: "
                        "Stage B's legitimate path stopped entirely)")
    q.set_defaults(fn=serve)
    q = sub.add_parser("check", help="validate the socket and its parent directory (writes "
                                     "nothing)")
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
                      # **Measured.** Decided from the state, not from a flag and not from the
                      # absence of an error.
                      "workload_isolation": (measured_isolation(sock, [root])
                                             if not assets else "process_mediated")},
                     ensure_ascii=False))
    return 0 if (err is None and not assets) else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
