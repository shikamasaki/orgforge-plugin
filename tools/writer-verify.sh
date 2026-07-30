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
#
# ## 実 org で回してよいか
#
# **この検証は台帳・鍵・schema・socket を破壊しない。** 書き込みを「試す」のではなく、
# **書き込みモードで開けるかどうか**だけを見る（1バイトも書かない）。daemon も止めない。
# 検証が検証対象を壊すのは最悪の形である（docs/11）。
#
# 唯一の副作用は ⑧ の writerd 経由の append で、`progress_recorded` が1件増える。
# それが困る org では `--no-write` を付けること。
set -uo pipefail

ORG_ROOT=""
ORG_NAME=""
NO_WRITE=0
SOCK=""                      # namespace から決める（installer と同じ規則）
SERVICE_USER="_orgforge-writer"
while [ $# -gt 0 ]; do
  case "$1" in
    --org-root) ORG_ROOT="${2:-}"; shift 2 ;;
    --org-name) ORG_NAME="${2:-}"; shift 2 ;;
    --socket)   SOCK="${2:-}"; shift 2 ;;
    --no-write) NO_WRITE=1; shift ;;
    -h|--help)  sed -n '1,28p' "$0"; exit 0 ;;
    *) echo "不明な引数: $1" >&2; exit 2 ;;
  esac
done
[ -n "$ORG_ROOT" ] || { echo "--org-root が必要" >&2; exit 2; }
# **namespace は installer と同じ規則で決める。** 食い違うと、存在しない socket を検査する。
if [ -z "$ORG_NAME" ]; then
  ORG_NAME="$(printf '%s' "$(cd "$ORG_ROOT" && pwd)" | shasum -a 256 | cut -c1-12)"
fi
[ -n "$SOCK" ] || SOCK="/usr/local/var/orgforge/run/${ORG_NAME}/writer.sock"
AUTHORITATIVE="/usr/local/var/orgforge/orgs/${ORG_NAME}"
LABEL="com.orgforge.writerd.${ORG_NAME}"
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
note "namespace: $ORG_NAME"

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
# **本番の台帳を壊さない。** 追記を試して成功したら、その行が本物の台帳に残る — 検証が
# 検証対象を壊すのは最悪の形である（docs/11）。だから **新しいファイルを作れるか**で見る。
# 台帳ディレクトリに書けるかどうかは、追記できるかと同じ権限の問題である。
PROBE="$LED/.write-probe-$$"
if : > "$PROBE" 2>/dev/null; then
  bad "台帳ディレクトリに書き込めた — **境界が無い**"
  rm -f "$PROBE" 2>/dev/null || true
else
  ok "台帳ディレクトリに書き込めない（OS 権限で失敗）"
fi
# 既存ファイルへの追記は **O_APPEND で開けるかだけ**を見る（1バイトも書かない）。
if python3 - "$LED/ledger.jsonl" <<'PYEOF' 2>/dev/null
import os, sys
try:
    fd = os.open(sys.argv[1], os.O_WRONLY | os.O_APPEND)
except OSError:
    sys.exit(1)
os.close(fd)                 # **何も書かない。** 開けたかどうかだけを見る
sys.exit(0)
PYEOF
then
  bad "台帳を追記モードで開けた — **書き込める**"
else
  ok "台帳を追記モードで開けない"
fi
if python3 -c "
import os, sys
try: fd = os.open('$LED/HEAD', os.O_WRONLY)
except OSError: sys.exit(1)
os.close(fd); sys.exit(0)" 2>/dev/null; then
  bad "HEAD を書き込みモードで開けた"
else
  ok "HEAD を書き込みモードで開けない"
fi
# **読めることも確かめる。** 書けないことと見えないことは別である — 監査できない台帳は
# 監査のための台帳ではない。
if [ -r "$LED/ledger.jsonl" ] && python3 "$T/ledger.py" verify "$LED" >/dev/null 2>&1; then
  ok "caller から台帳を **読める**（verify が通る）"
else
  bad "caller から台帳を読めない — verify / board / projection が動かない"
fi

echo
echo "── ③ chmod で権限を戻せないか"
# **chmod を実際に打たない。** 成功したら本番の権限が変わる（そして戻し忘れれば穴が残る）。
# chmod できるのは所有者と root だけなので、**所有者を見れば同じことが分かる**。
LED_UID="$(stat -f '%u' "$LED")"
if [ "$LED_UID" = "$(id -u)" ]; then
  bad "台帳ディレクトリの所有者が自分（uid=$LED_UID）— **chmod で権限を戻せる**"
else
  ok "台帳ディレクトリの所有者が自分でない（uid=$LED_UID）— chmod できない"
fi

echo
echo "── ④ 鍵 registry / schema を差し替えられないか"
for f in "$ORG_ROOT/.orgforge/trust/keys.json" "$ORG_ROOT/ledger-schema.yaml" \
         "$AUTHORITATIVE/trust/keys.json" "$AUTHORITATIVE/ledger-schema.yaml"; do
  [ -f "$f" ] || { note "$（無い）: $f"; continue; }
  # **1バイトも書かない。** 上書きを試すと本物の鍵 registry / schema を壊す。
  if python3 -c "
import os, sys
try: fd = os.open('$f', os.O_WRONLY)
except OSError: sys.exit(1)
os.close(fd); sys.exit(0)" 2>/dev/null; then
    bad "$(basename "$f") を書き込みモードで開けた — 検証規則／署名者を偽装できる"
  else
    ok "$(basename "$f") を書き込みモードで開けない"
  fi
done

echo
echo "── ⑤ socket の親ディレクトリを差し替えられないか"
PARENT="$(dirname "$SOCK")"
if [ -d "$PARENT" ]; then
  POWNER="$(stat -f '%Su' "$PARENT")"; PMODE="$(stat -f '%Lp' "$PARENT")"
  note "親: $PARENT （$POWNER, mode $PMODE）"
  # **leaf は writer 所有が正しい。** daemon が socket を作るには親への書き込み権限が要る
  # （実測: root 所有 0755 では bind できない）。root 所有を期待するのは anchor である。
  if [ "$POWNER" = "$(whoami)" ]; then
    bad "leaf が自分の所有（$POWNER）— **socket を差し替えられる**"
  else
    ok "leaf は $POWNER 所有（自分ではない）"
  fi
  GRAND_OWNER="$(stat -f '%Su' "$(dirname "$PARENT")")"
  if [ "$GRAND_OWNER" = "root" ]; then
    ok "anchor（$(dirname "$PARENT")）は root 所有"
  else
    bad "anchor が root 所有でない（$GRAND_OWNER）— **leaf ごと差し替えられる**"
  fi
  # **移動を実際にやらない。** 成功すれば daemon の socket が消え、戻す前に何かが起きうる。
  # 移動できるのは **その親の親** に書ける主体なので、そちらの権限を見る。
  GRAND="$(dirname "$PARENT")"
  PROBE3="$GRAND/.probe-$$"
  if : > "$PROBE3" 2>/dev/null; then
    bad "$GRAND に書き込めた — **socket の親ごと差し替えられる**"
    rm -f "$PROBE3" 2>/dev/null || true
  else
    ok "$GRAND に書き込めない（親ごとの差し替えができない）"
  fi
  # **socket を消さない。** 消せたら daemon が止まり、検証が対象を壊す。親ディレクトリに
  # 書けるかどうかで同じことが分かる（消すのも作るのも親への書き込み権限である）。
  PROBE2="$PARENT/.probe-$$"
  if : > "$PROBE2" 2>/dev/null; then
    bad "socket の親に書き込めた — **偽 socket を置ける／消せる**"
    rm -f "$PROBE2" 2>/dev/null || true
  else
    ok "socket の親に書き込めない（socket を差し替えられない）"
  fi
else
  bad "socket の親ディレクトリが無い: $PARENT"
fi

echo
echo "── ⑤' org tree の入れ物ごと差し替えられないか"
# **中身の権限を絞っても、入れ物を差し替えられるなら意味が無い**（実測で指摘された）。
# 権威データが org tree の外にあること、そして org 側が symlink ならその実体を見る。
for p in "$ORG_ROOT/.orgforge/ledger" "$ORG_ROOT/.orgforge/trust" "$ORG_ROOT/ledger-schema.yaml"; do
  [ -e "$p" ] || continue
  if [ -L "$p" ]; then
    REAL="$(readlink "$p")"
    case "$REAL" in
      "$AUTHORITATIVE"/*) ok "$(basename "$p") は org 外の権威データを指す（$REAL）" ;;
      *) bad "$(basename "$p") の symlink 先が権威データの外: $REAL" ;;
    esac
  else
    bad "$(basename "$p") が org tree の中に実体を持つ — **入れ物ごと差し替えられる**"
  fi
done

echo
echo "── ⑥ writerd の複製を差し替えられないか"
for f in /usr/local/libexec/orgforge/tools/writerd.py /Library/LaunchDaemons/$LABEL.plist \
         /usr/local/etc/orgforge/writerd.conf; do
  [ -e "$f" ] || { note "（無い）: $f"; continue; }
  # **1バイトも書かない。** 書けたら daemon の複製に余計な行が残る。
  if python3 -c "
import os, sys
try: fd = os.open('$f', os.O_WRONLY | os.O_APPEND)
except OSError: sys.exit(1)
os.close(fd); sys.exit(0)" 2>/dev/null; then
    bad "$(basename "$f") を書き込みモードで開けた — **daemon 自体を差し替えられる**"
  else
    ok "$(basename "$f") を書き込みモードで開けない"
  fi
done

echo
echo "── ⑦ daemon を通常 UID で止められないか"
# **実際に止めない。** 止まったら以降の検証が全部落ち、実 org なら統制も止まる。
# `launchctl print` を通常 UID で叩き、system domain に触れないことで見る。
if launchctl print "system/$LABEL" >/dev/null 2>&1; then
  bad "system domain の daemon を通常 UID で参照できた — 停止も試せる可能性がある"
  note "**実際の停止は試していない**（対象を壊すため）。sudo で確かめること:"
  note "  sudo launchctl print system/$LABEL   # 動いていることの確認"
else
  ok "通常 UID からは system domain の daemon を操作できない"
fi

echo
echo "── ⑧ writerd 経由なら書けるか（**止めるだけでは意味が無い**）"
export ORG_WRITER_SOCKET="$SOCK"
if [ "$NO_WRITE" = 1 ]; then
  note "--no-write が指定されたので飛ばす（台帳に1件も足さない）"
  note "**書けることを確かめていない** — 止まるだけの org は運用できない。別途確かめること。"
else
OUT="$(python3 "$T/writer_client.py" append -- --actor verify --class progress_recorded \
        --payload '{"role":"verify","candidate_id":"wv1","phase":"operate"}' 2>&1 | head -1)"
if printf '%s' "$OUT" | grep -q '"ok": true'; then
  ok "writerd 経由で書けた"
else
  bad "writerd 経由でも書けない: $(printf '%s' "$OUT" | head -c 160)"
fi
fi

echo
echo "── ⑨ RPC の改変・再送が拒否されるか"
# **--no-write では正常系の append も出さない。** 改変・再送の検査は拒否されるものだけで
# 成立するが、再送の検査には「1回目が通る」ことが要る — そこは書き込みになるので飛ばす。
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
      f"RPC 改変: {r.get('reason')}")
if no_write:
    print("  - 再送: --no-write なので飛ばす（1回目が正常な append になるため）")
else:
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
)"
printf '%s\n' "$RPC_OUT"
# **✗ を数える。** 印字するだけでは、検査が落ちても最終 exit が 0 になる（実測で指摘）。
RPC_BAD="$(printf '%s' "$RPC_OUT" | grep -c '✗' || true)"
RPC_OK="$(printf '%s' "$RPC_OUT" | grep -c '✓' || true)"
PASS=$((PASS + RPC_OK)); FAIL=$((FAIL + RPC_BAD))

echo
echo "── ⑩ 台帳の健全性（writerd が壊していないこと）"
if python3 "$T/ledger.py" verify "$LED" 2>&1 | grep -q "chain intact"; then
  ok "鎖は健全"
else
  bad "鎖が壊れている: $(python3 "$T/ledger.py" verify "$LED" 2>&1 | tail -1)"
fi

echo
echo "── ⑪ writerd 自身の判定（socket と資産）"
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
  ok "writerd check が通った"
else
  bad "writerd check が落ちた"
fi

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
