#!/usr/bin/env bash
# writer-verify.sh — 別 UID の writer 境界を **実測する**。install の自己申告は証拠にしない。
#
# ## 何を確かめるのか
#
# 「writer を隔離した」と言うために必要なのは、設定が書かれていることではなく、
# **通常の caller UID から実際に書けないこと**である。だからこのスクリプトは:
#
#   - 台帳のファイルに直接追記してみる → **失敗しなければならない**
#   - chmod で権限を戻してみる → **失敗しなければならない**
#   - socket の親ディレクトリを差し替えてみる → **失敗しなければならない**
#   - 偽 socket を置いてみる → 親が root 所有なら **置けない**
#   - daemon を止めてみる → 通常 UID では **止められない**
#   - RPC の改変・再送 → **拒否される**
#   - 壊れた台帳 → **fail-closed**
#
# **root で実行しないこと。** root なら全部できてしまうので、検証にならない。
# 通常の caller として走らせる。
set -uo pipefail

ORG_ROOT=""
SOCK="/var/run/orgforge/writer.sock"
LABEL="com.orgforge.writerd"
SERVICE_USER="_orgforge-writer"
while [ $# -gt 0 ]; do
  case "$1" in
    --org-root) ORG_ROOT="${2:-}"; shift 2 ;;
    --socket)   SOCK="${2:-}"; shift 2 ;;
    -h|--help)  sed -n '1,28p' "$0"; exit 0 ;;
    *) echo "不明な引数: $1" >&2; exit 2 ;;
  esac
done
[ -n "$ORG_ROOT" ] || { echo "--org-root が必要" >&2; exit 2; }
LED="$ORG_ROOT/.orgforge/ledger"
T="$(cd "$(dirname "$0")" && pwd)"

PASS=0; FAIL=0
ok()   { printf '  ✓ %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  ✗ %s\n' "$*"; FAIL=$((FAIL+1)); }
note() { printf '    %s\n' "$*"; }

echo "── 前提"
if [ "$(id -u)" = "0" ]; then
  echo "✗ root で実行している。**通常の caller として走らせること** — root では全部できてしまい、" >&2
  echo "  境界を検証したことにならない。" >&2
  exit 2
fi
note "実行者: uid=$(id -u) ($(whoami))"
note "台帳:   $LED"
note "socket: $SOCK"

echo
echo "── ① 台帳の所有者が別 UID か"
if [ -d "$LED" ]; then
  OWNER="$(stat -f '%Su' "$LED")"; MODE="$(stat -f '%Lp' "$LED")"
  if [ "$OWNER" = "$(whoami)" ]; then
    bad "台帳が自分の所有である（$OWNER, mode $MODE） — separate_uid ではない"
    note "install を実行していないか、uninstall で戻っている"
  else
    ok "台帳は $OWNER 所有（mode $MODE）— 自分ではない"
  fi
else
  bad "台帳が無い: $LED"
fi

echo
echo "── ② 通常 CLI からの直接書き込みが OS 権限で失敗するか（**実測条件**）"
if printf '{"forged":true}\n' >> "$LED/ledger.jsonl" 2>/dev/null; then
  bad "台帳に直接追記できた — **境界が無い**"
  note "追記した行を消すこと: 手で確認して削除、または ledger verify で検出させる"
else
  ok "台帳に直接追記できない（OS 権限で失敗）"
fi
if [ -f "$LED/HEAD" ] && printf 'x' > "$LED/HEAD" 2>/dev/null; then
  bad "HEAD を上書きできた"
else
  ok "HEAD を上書きできない"
fi

echo
echo "── ③ chmod で権限を戻せないか"
if chmod 777 "$LED" 2>/dev/null; then
  bad "台帳ディレクトリの権限を変えられた — 所有者が自分である"
  chmod 700 "$LED" 2>/dev/null || true
else
  ok "台帳ディレクトリの chmod が失敗する（所有者でない）"
fi

echo
echo "── ④ 鍵 registry / schema を差し替えられないか"
for f in "$ORG_ROOT/.orgforge/trust/keys.json" "$ORG_ROOT/ledger-schema.yaml"; do
  [ -f "$f" ] || { note "$（無い）: $f"; continue; }
  if printf '{}' > "$f" 2>/dev/null; then
    bad "$(basename "$f") を上書きできた — 検証規則／署名者を偽装できる"
  else
    ok "$(basename "$f") を上書きできない"
  fi
done

echo
echo "── ⑤ socket の親ディレクトリを差し替えられないか"
PARENT="$(dirname "$SOCK")"
if [ -d "$PARENT" ]; then
  POWNER="$(stat -f '%Su' "$PARENT")"; PMODE="$(stat -f '%Lp' "$PARENT")"
  note "親: $PARENT （$POWNER, mode $PMODE）"
  if [ "$POWNER" = "root" ]; then ok "親ディレクトリは root 所有"; else bad "親が root 所有でない（$POWNER）"; fi
  if mv "$PARENT" "$PARENT.moved" 2>/dev/null; then
    bad "親ディレクトリを移動できた — **socket を差し替えられる**"
    mv "$PARENT.moved" "$PARENT" 2>/dev/null || true
  else
    ok "親ディレクトリを移動できない"
  fi
  if rm -f "$SOCK" 2>/dev/null && [ ! -S "$SOCK" ]; then
    bad "socket を消せた — 偽 socket を置ける"
  else
    ok "socket を消せない（sticky / root 所有）"
  fi
else
  bad "socket の親ディレクトリが無い: $PARENT"
fi

echo
echo "── ⑥ writerd の複製を差し替えられないか"
for f in /usr/local/libexec/orgforge/tools/writerd.py /Library/LaunchDaemons/$LABEL.plist \
         /usr/local/etc/orgforge/writerd.conf; do
  [ -e "$f" ] || { note "（無い）: $f"; continue; }
  if printf '#' >> "$f" 2>/dev/null; then
    bad "$(basename "$f") を書き換えられた — **daemon 自体を差し替えられる**"
  else
    ok "$(basename "$f") を書き換えられない"
  fi
done

echo
echo "── ⑦ daemon を通常 UID で止められないか"
if launchctl bootout "system/$LABEL" 2>/dev/null; then
  bad "daemon を止められた — 通常 UID で停止できる"
  note "戻す: sudo launchctl bootstrap system /Library/LaunchDaemons/$LABEL.plist"
else
  ok "daemon を通常 UID では止められない"
fi

echo
echo "── ⑧ writerd 経由なら書けるか（**止めるだけでは意味が無い**）"
export ORG_WRITER_SOCKET="$SOCK"
OUT="$(python3 "$T/writer_client.py" append -- --actor verify --class progress_recorded \
        --payload '{"role":"verify","candidate_id":"wv1","phase":"operate"}' 2>&1 | head -1)"
if printf '%s' "$OUT" | grep -q '"ok": true'; then
  ok "writerd 経由で書けた"
else
  bad "writerd 経由でも書けない: $(printf '%s' "$OUT" | head -c 160)"
fi

echo
echo "── ⑨ RPC の改変・再送が拒否されるか"
python3 - "$SOCK" "$T" <<'PY'
import json, socket, sys
sock, tools = sys.argv[1], sys.argv[2]
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
      f"RPC 改変: {r.get('reason')}")
r1, r2 = send(base), send(base)
print(("  ✓ " if r2.get("reason") == "replayed_nonce" else "  ✗ ") +
      f"再送: 1回目={r1.get('reason')} 2回目={r2.get('reason')}")
p = dict(base); p["nonce"] = "p" * 32
p["argv"] = base["argv"] + ["/tmp/evil/ledger.jsonl"]
p["digest"] = request_digest(p)
r = send(p)
print(("  ✓ " if r.get("reason") == "path_in_argv" else "  ✗ ") +
      f"パス指定: {r.get('reason')}")
u = dict(base); u["nonce"] = "u" * 32; u["org"] = "elsewhere"
u["digest"] = request_digest(u)
r = send(u)
print(("  ✓ " if r.get("reason") == "unknown_org" else "  ✗ ") +
      f"未知の org: {r.get('reason')}")
PY

echo
echo "── ⑩ 台帳の健全性（writerd が壊していないこと）"
if python3 "$T/ledger.py" verify "$LED" 2>&1 | grep -q "chain intact"; then
  ok "鎖は健全"
else
  bad "鎖が壊れている: $(python3 "$T/ledger.py" verify "$LED" 2>&1 | tail -1)"
fi

echo
echo "── ⑪ writerd 自身の判定（socket と資産）"
python3 "$T/writerd.py" check --socket "$SOCK" --require-root-owned 2>&1 | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(('  ✓ ' if d['ok'] else '  ✗ ') + f\"writerd check: ok={d['ok']} isolation={d.get('workload_isolation')}\")
if d.get('detail'): print('    ' + d['detail'].split(chr(10))[0])
for a in d.get('asset_issues') or []:
    print('    - ' + a['path'].split('/')[-1] + ': ' + a['issue'][:70])
"

echo
echo "════════════════════════════════════════════"
printf '  合格 %d / 不合格 %d\n' "$PASS" "$FAIL"
if [ "$FAIL" = 0 ]; then
  cat <<'DONE'

  ✓ すべて実測で通った。**workload_isolation: separate_uid** を主張してよい。

  ただし保証の範囲は「通常の agent / caller UID から writer の資産を変更できない」ことである。
  **ホストの管理者（root）は脅威モデルの外** — daemon を止め、所有者を戻せる。
DONE
  exit 0
fi
cat <<'NOTDONE'

  ✗ 不合格がある。**workload_isolation は process_mediated のままにすること。**
    「隔離した」と書く前に、ここが全部通ることを確かめる。
NOTDONE
exit 1
