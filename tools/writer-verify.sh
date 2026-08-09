#!/usr/bin/env bash
# writer-verify.sh — **measure** the separate-UID writer boundary. install's own word is not
# evidence.
#
# ## What is being confirmed
#
# What it takes to say "the writer is isolated" is not that the configuration was written, but
# **that a normal caller UID genuinely cannot write**. So this script:
#
#   - tries appending directly to the ledger file → **it must fail**
#   - tries restoring the permissions with chmod → **it must fail**
#   - tries replacing the socket's parent directory → **it must fail**
#   - tries planting a fake socket → **it cannot** where the parent is root-owned
#   - tries stopping the daemon → a normal UID **cannot**
#   - tampers with and replays an RPC → **it is refused**
#   - a broken ledger → **fail-closed**
#
# **Do not run this as root.** As root everything succeeds, which verifies nothing.
# Run it as a normal caller.
#
# ## Is it safe to run against a real org?
#
# **This verification destroys neither the ledger, the keys, the schema, nor the socket.** Rather
# than "trying" a write, it only asks **whether it opens in write mode** (not one byte is written).
# It does not stop the daemon either.
# A verification that breaks what it verifies is the worst shape there is (docs/11).
#
# The one side effect is the append through writerd in ⑧, which adds one `progress_recorded`.
# Where that is unwanted, pass `--no-write`.
set -uo pipefail

ORG_ROOT=""
ORG_NAME=""
NO_WRITE=0
SOCK=""                      # decided from the namespace (the same rule as the installer)
SERVICE_USER="_orgforge-writer"
while [ $# -gt 0 ]; do
  case "$1" in
    --org-root) ORG_ROOT="${2:-}"; shift 2 ;;
    --org-name) ORG_NAME="${2:-}"; shift 2 ;;
    --socket)   SOCK="${2:-}"; shift 2 ;;
    --no-write) NO_WRITE=1; shift ;;
    -h|--help)  sed -n '1,28p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$ORG_ROOT" ] || { echo "--org-root is required" >&2; exit 2; }
# **The namespace is decided by the same rule as the installer.** Diverge, and it checks a socket
# that does not exist.
if [ -z "$ORG_NAME" ]; then
  ORG_NAME="$(printf '%s' "$(cd "$ORG_ROOT" && pwd)" | shasum -a 256 | cut -c1-12)"
fi
[ -n "$SOCK" ] || SOCK="/usr/local/var/orgforge/run/${ORG_NAME}/writer.sock"
AUTHORITATIVE="/usr/local/var/orgforge/orgs/${ORG_NAME}"
LABEL="com.orgforge.writerd.${ORG_NAME}"
LED="$ORG_ROOT/.orgforge/ledger"
T="$(cd "$(dirname "$0")" && pwd)"

PASS=0; FAIL=0; SKIPPED=0
ok()   { printf '  ✓ %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  ✗ %s\n' "$*"; FAIL=$((FAIL+1)); }
note() { printf '    %s\n' "$*"; }
# **Count the checks that were skipped.** Without counting, "zero failures" cannot be told apart
# from "everything was measured".
skip() { printf '  — %s\n' "$*"; SKIPPED=$((SKIPPED+1)); }

echo "── preconditions"
if [ "$(id -u)" = "0" ]; then
  echo "✗ running as root. **Run it as a normal caller** — as root everything succeeds, which" >&2
  echo "  does not verify the boundary." >&2
  exit 2
fi
note "running as: uid=$(id -u) ($(whoami))"
note "ledger:    $LED"
note "socket:    $SOCK"
note "namespace: $ORG_NAME"

echo
echo "── ① is the ledger owned by a different UID?"
if [ -d "$LED" ]; then
  OWNER="$(stat -f '%Su' "$LED")"; MODE="$(stat -f '%Lp' "$LED")"
  if [ "$OWNER" = "$(whoami)" ]; then
    bad "the ledger is owned by me ($OWNER, mode ${MODE}) — this is not separate_uid"
    note "either install was never run, or an uninstall put it back"
  else
    ok "the ledger is owned by $OWNER (mode ${MODE}) — not by me"
  fi
else
  bad "there is no ledger: $LED"
fi

echo
echo "── ② does a direct write from the normal CLI fail on OS permissions? (**the measured
condition**)"
# **Do not break the real ledger.** Try an append and succeed, and that line stays in the real ledger
# — a verification that breaks what it verifies is the worst shape there is (docs/11). So it asks
# **whether a new file can be created** instead.
# Whether the ledger directory can be written to is the same permission question as whether an append
# can happen.
PROBE="$LED/.write-probe-$$"
if : > "$PROBE" 2>/dev/null; then
  bad "the ledger directory could be written to — **there is no boundary**"
  rm -f "$PROBE" 2>/dev/null || true
else
  ok "the ledger directory cannot be written to (it fails on OS permissions)"
fi
# For appending to an existing file, only **whether it opens with O_APPEND** is read (not one byte is
# written).
if python3 - "$LED/ledger.jsonl" <<'PYEOF' 2>/dev/null
import os, sys
try:
    fd = os.open(sys.argv[1], os.O_WRONLY | os.O_APPEND)
except OSError:
    sys.exit(1)
os.close(fd)                 # **Write nothing.** Only whether it opened is read
sys.exit(0)
PYEOF
then
  bad "the ledger opened in append mode — **it can be written to**"
else
  ok "the ledger does not open in append mode"
fi
if python3 -c "
import os, sys
try: fd = os.open('$LED/HEAD', os.O_WRONLY)
except OSError: sys.exit(1)
os.close(fd); sys.exit(0)" 2>/dev/null; then
  bad "HEAD opened in write mode"
else
  ok "HEAD does not open in write mode"
fi
# **Confirm that it can be read, too.** Being unwritable and being invisible are different — a ledger
# that cannot be audited is not a ledger for auditing.
if [ -r "$LED/ledger.jsonl" ] && python3 "$T/ledger.py" verify "$LED" >/dev/null 2>&1; then
  ok "the caller **can read** the ledger (verify passes)"
else
  bad "the caller cannot read the ledger — verify / board / projection will not run"
fi

echo
echo "── ③ can the permissions be restored with chmod?"
# **Do not actually run chmod.** Succeeding changes the real permissions (and forgetting to put them
# back leaves a hole).
# Only the owner and root can chmod, so **reading the owner answers the same question**.
LED_UID="$(stat -f '%u' "$LED")"
if [ "$LED_UID" = "$(id -u)" ]; then
  bad "the ledger directory is owned by me (uid=${LED_UID}) — **chmod can restore the permissions**"
else
  ok "the ledger directory is not owned by me (uid=${LED_UID}) — chmod is not possible"
fi

echo
echo "── ④ can the key registry / schema be replaced?"
for f in "$ORG_ROOT/.orgforge/trust/keys.json" "$ORG_ROOT/ledger-schema.yaml" \
         "$AUTHORITATIVE/trust/keys.json" "$AUTHORITATIVE/ledger-schema.yaml"; do
  [ -f "$f" ] || { note "(absent): $f"; continue; }
  # **Not one byte is written.** Trying an overwrite breaks the real key registry / schema.
  if python3 -c "
import os, sys
try: fd = os.open('$f', os.O_WRONLY)
except OSError: sys.exit(1)
os.close(fd); sys.exit(0)" 2>/dev/null; then
    bad "$(basename "$f") opened in write mode — the verification rules or the signers can be forged"
  else
    ok "$(basename "$f") does not open in write mode"
  fi
done

echo
echo "── ⑤ can the socket's parent directory be replaced?"
PARENT="$(dirname "$SOCK")"
if [ -d "$PARENT" ]; then
  POWNER="$(stat -f '%Su' "$PARENT")"; PMODE="$(stat -f '%Lp' "$PARENT")"
  note "parent: $PARENT ($POWNER, mode ${PMODE})"
  # **A writer-owned leaf is correct.** For the daemon to create the socket it needs write permission
  # on the parent (measured: a root-owned 0755 cannot be bound). It is the anchor that is expected to
  # be root-owned.
  if [ "$POWNER" = "$(whoami)" ]; then
    bad "the leaf is owned by me (${POWNER}) — **the socket can be replaced**"
  else
    ok "the leaf is owned by $POWNER (not by me)"
  fi
  GRAND_OWNER="$(stat -f '%Su' "$(dirname "$PARENT")")"
  if [ "$GRAND_OWNER" = "root" ]; then
    ok "the anchor ($(dirname "$PARENT")) is root-owned"
  else
    bad "the anchor is not root-owned (${GRAND_OWNER}) — **the leaf can be replaced wholesale**"
  fi
  # **Do not actually move anything.** Succeeding removes the daemon's socket, and something could
  # happen before it is put back.
  # Whoever can move it is whoever can write to **the parent's parent**, so those permissions are
  # what is read.
  GRAND="$(dirname "$PARENT")"
  PROBE3="$GRAND/.probe-$$"
  if : > "$PROBE3" 2>/dev/null; then
    bad "$GRAND could be written to — **the socket's parent can be replaced wholesale**"
    rm -f "$PROBE3" 2>/dev/null || true
  else
    ok "$GRAND cannot be written to (the parent cannot be replaced wholesale)"
  fi
  # **Do not remove the socket.** Removing it stops the daemon, and the verification breaks its
  # subject. Whether the parent directory can be written to answers the same question (removing and
  # creating are both write permission on the parent).
  PROBE2="$PARENT/.probe-$$"
  if : > "$PROBE2" 2>/dev/null; then
    bad "the socket's parent could be written to — **a fake socket can be planted or removed**"
    rm -f "$PROBE2" 2>/dev/null || true
  else
    ok "the socket's parent cannot be written to (the socket cannot be replaced)"
  fi
else
  bad "the socket's parent directory does not exist: $PARENT"
fi

echo
echo "── ⑤' can the org tree's container be replaced wholesale?"
# **Tightening the permissions on the contents means nothing if the container can be replaced**
# (raised by measurement).
# It reads that the authoritative data lives outside the org tree, and where the org side is a
# symlink, what it actually points at.
for p in "$ORG_ROOT/.orgforge/ledger" "$ORG_ROOT/.orgforge/trust" "$ORG_ROOT/ledger-schema.yaml"; do
  [ -e "$p" ] || continue
  if [ -L "$p" ]; then
    REAL="$(readlink "$p")"
    case "$REAL" in
      "$AUTHORITATIVE"/*) ok "$(basename "$p") points at authoritative data outside the org (${REAL})" ;;
      *) bad "$(basename "$p")'s symlink points outside the authoritative data: $REAL" ;;
    esac
  else
    bad "$(basename "$p") holds its substance inside the org tree — **the container can be replaced**"
  fi
done

echo
echo "── ⑥ can writerd's copy be replaced?"
for f in /usr/local/libexec/orgforge/tools/writerd.py /Library/LaunchDaemons/$LABEL.plist \
         /usr/local/etc/orgforge/writerd.conf; do
  [ -e "$f" ] || { note "(absent): $f"; continue; }
  # **Not one byte is written.** A successful write would leave a stray line in the daemon's copy.
  if python3 -c "
import os, sys
try: fd = os.open('$f', os.O_WRONLY | os.O_APPEND)
except OSError: sys.exit(1)
os.close(fd); sys.exit(0)" 2>/dev/null; then
    bad "$(basename "$f") opened in write mode — **the daemon itself can be replaced**"
  else
    ok "$(basename "$f") does not open in write mode"
  fi
done

echo
echo "── ⑦ can the daemon be stopped by a normal UID?"
# **Do not actually stop it.** Stopping it fails every check that follows, and in a real org the
# controls stop too.
# It runs `launchctl print` as a normal UID and reads that the system domain is out of reach.
if launchctl print "system/$LABEL" >/dev/null 2>&1; then
  bad "the system domain daemon was visible to a normal UID — stopping it may be attemptable too"
  note "**Stopping it was not attempted** (it would break the subject). Confirm with sudo:"
  note "  sudo launchctl print system/$LABEL   # confirm it is running"
else
  ok "a normal UID cannot operate the system domain daemon"
fi

echo
echo "── ⑧ can it write through writerd? (**stopping writes alone is pointless**)"
export ORG_WRITER_SOCKET="$SOCK"
if [ "$NO_WRITE" = 1 ]; then
  skip "--no-write, so the write check was skipped (not one row is added to the ledger)"
  note "**That it CAN write is unconfirmed** — an org that only stops cannot be operated. Confirm it separately."
else
OUT="$(python3 "$T/writer_client.py" append -- --actor verify --class progress_recorded \
        --payload '{"role":"verify","candidate_id":"wv1","phase":"operate"}' 2>&1 | head -1)"
if printf '%s' "$OUT" | grep -q '"ok": true'; then
  ok "the write through writerd succeeded"
else
  bad "it cannot write even through writerd: $(printf '%s' "$OUT" | head -c 160)"
fi
fi

echo
echo "── ⑨ are a tampered and a replayed RPC refused?"
# **Under --no-write not even the happy-path append is sent.** The tamper check holds on refusals
# alone, but the replay check needs "the first one passes" — and that is a write, so it is skipped.
RPC_OUT="$(python3 - "$SOCK" "$T" "$NO_WRITE" <<'PY'
import json, socket, sys
sock, tools = sys.argv[1], sys.argv[2]
no_write = sys.argv[3] == "1"
sys.path.insert(0, tools)
from writerd import request_digest, PROTOCOL
def send(req):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); c.settimeout(30); c.connect(sock)
    c.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        ch = c.recv(65536)
        if not ch: break
        buf += ch
    c.close(); return json.loads(buf)
base = {"protocol": PROTOCOL, "op": "append", "org": "default", "nonce": "v" * 32,
        "argv": ["--actor", "verify", "--class", "progress_recorded",
                 "--payload", '{"role":"v","candidate_id":"wv2","phase":"operate"}']}
base["digest"] = request_digest(base)
t = dict(base); t["argv"] = list(base["argv"]); t["argv"][1] = "attacker"
r = send(t)
print(("  ✓ " if r.get("reason") == "request_tampered" else "  ✗ ") +
      f"tampered RPC: {r.get('reason')}")
if no_write:
    print("  - replay: skipped under --no-write (the first send would be a real append)")
else:
    r1, r2 = send(base), send(base)
    print(("  ✓ " if r2.get("reason") == "replayed_nonce" else "  ✗ ") +
          f"replay: first={r1.get('reason')} second={r2.get('reason')}")
p = dict(base); p["nonce"] = "p" * 32
p["argv"] = base["argv"] + ["/tmp/evil/ledger.jsonl"]
p["digest"] = request_digest(p)
r = send(p)
print(("  ✓ " if r.get("reason") == "path_in_argv" else "  ✗ ") +
      f"a path in argv: {r.get('reason')}")
u = dict(base); u["nonce"] = "u" * 32; u["org"] = "elsewhere"
u["digest"] = request_digest(u)
r = send(u)
print(("  ✓ " if r.get("reason") == "unknown_org" else "  ✗ ") +
      f"an unknown org: {r.get('reason')}")
PY
)"
printf '%s\n' "$RPC_OUT"
# **Count the ✗ marks.** Printing alone leaves the final exit at 0 even when a check fails (raised
# by measurement).
RPC_BAD="$(printf '%s' "$RPC_OUT" | grep -c '✗' || true)"
RPC_OK="$(printf '%s' "$RPC_OUT" | grep -c '✓' || true)"
PASS=$((PASS + RPC_OK)); FAIL=$((FAIL + RPC_BAD))

echo
echo "── ⑩ the ledger's soundness (writerd has not broken it)"
if python3 "$T/ledger.py" verify "$LED" 2>&1 | grep -q "chain intact"; then
  ok "the chain is intact"
else
  bad "the chain is broken: $(python3 "$T/ledger.py" verify "$LED" 2>&1 | tail -1)"
fi

echo
echo "── ⑪ writerd's own verdict (the socket and the assets)"
CHECK_OUT="$(python3 "$T/writerd.py" check --socket "$SOCK" --require-root-owned 2>&1)"
if printf '%s' "$CHECK_OUT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f\"    ok={d['ok']} isolation={d.get('workload_isolation')}\")
if d.get('detail'): print('    ' + str(d['detail']).split(chr(10))[0])
for a in d.get('asset_issues') or []:
    print('    - ' + a['path'].split('/')[-1] + ': ' + a['issue'][:70])
sys.exit(0 if d['ok'] else 1)
"; then
  ok "the writerd check passed"
else
  bad "the writerd check failed"
fi

echo
echo "════════════════════════════════════════════"
printf '  passed %d / failed %d / unmeasured %d\n' "$PASS" "$FAIL" "$SKIPPED"
if [ "$FAIL" = 0 ] && [ "$SKIPPED" != 0 ]; then
  cat <<'PARTIAL'

  ! Nothing failed, but **items remain unmeasured**.
    "Zero failures" is not "everything was confirmed". **Do not claim separate_uid.**
    Drop --no-write and measure again, including that it can write.
PARTIAL
  exit 2
fi
if [ "$FAIL" = 0 ]; then
  cat <<'DONE'

  ✓ everything passed by measurement. **workload_isolation: separate_uid** may be claimed.

  The guarantee extends only to "a normal agent / caller UID cannot modify the writer's assets".
  **The host's administrator (root) is outside the threat model** — they can stop the daemon and
  restore the ownership.
DONE
  exit 0
fi
cat <<'NOTDONE'

  ✗ something failed. **Leave workload_isolation at process_mediated.**
    Before writing "it is isolated", confirm that everything here passes.
NOTDONE
exit 1
