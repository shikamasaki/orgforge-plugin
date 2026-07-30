#!/usr/bin/env bash
# writer-install.sh — writerd を別 UID の LaunchDaemon として据える（段階B, macOS）。
#
# ## これが何を変えるのか
#
# 段階A（`writerd.py` を同じ UID で動かす）で強制できるのは「台帳への経路が1つであること」
# までである。**同じ UID の caller は daemon を止められ、ファイル権限を戻せる**ので、
# `workload_isolation` は `process_mediated` にとどまる。
#
# このスクリプトは:
#   - 専用 UID（サービスアカウント）を作る
#   - 台帳・鍵 registry・schema・HALT ラッチを **その UID の所有**にする
#   - socket の親ディレクトリを **root 所有・他者書き込み不可**にする
#   - daemon・plist・設定を **root 所有**にして caller から差し替え不能にする
#
# ここまで揃うと、**通常の caller UID からは台帳のファイルに書けなくなる**（OS 権限で失敗する）。
# そこで初めて `workload_isolation: separate_uid` を主張できる。
#
# ## 脅威モデルから外れるもの
#
# **ホストの管理者（root）。** LaunchDaemon を止め、所有者を戻し、plist を書き換えられる。
# 保証の対象は「**通常の agent / caller UID から writer の資産を変更できない**」ことであって、
# root ではない。これは限界ではなく境界の定義である。
#
# ## 使い方
#
#   sudo tools/writer-install.sh --org-root /path/to/org --dry-run   # 何をするか見る
#   sudo tools/writer-install.sh --org-root /path/to/org             # 実行
#   sudo tools/writer-install.sh --org-root /path/to/org --uninstall  # 戻す
#
# 冪等である。既にあるものは作り直さず、足りないものだけ足す。
set -euo pipefail
# **失敗したら止まる。** set -e が無いと、chown が半端に済んだ状態で「install 完了」と
# 表示され、daemon が起動しない org が残る（実測で指摘された）。

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_USER="_orgforge-writer"
SERVICE_GROUP="_orgforge-writer"
LABEL="com.orgforge.writerd"
PLIST="/Library/LaunchDaemons/${LABEL}.plist"
SOCK_PARENT="/var/run/orgforge"
INSTALL_DIR="/usr/local/libexec/orgforge"
CONFIG="/usr/local/etc/orgforge/writerd.conf"
BACKUP_DIR="/usr/local/var/orgforge/backup"
DAEMON_PYTHON="/usr/bin/python3"     # LaunchDaemon が起動する処理系。--daemon-python で変えられる
CALLER_GROUP="staff"                 # 台帳を読める group（caller の primary group）

ORG_ROOT=""
DRY_RUN=0
UNINSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --org-root) ORG_ROOT="${2:-}"; shift 2 ;;
    --daemon-python) DAEMON_PYTHON="${2:-}"; shift 2 ;;
    --caller-group)  CALLER_GROUP="${2:-}"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "不明な引数: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '  %s\n' "$*"; }
run()  {
  if [ "$DRY_RUN" = 1 ]; then printf '  [dry-run] %s\n' "$*"; return 0; fi
  if ! eval "$@"; then
    printf '✗ 失敗した: %s\n' "$*" >&2
    printf '  **半端な状態で続けない。** ここまでの変更を戻すには:\n' >&2
    printf '    sudo %s --uninstall\n' "$0" >&2
    exit 1
  fi
}
fail() { printf '✗ %s\n' "$*" >&2; exit 1; }

# ── 事前条件 ──────────────────────────────────────────────────────────────────
echo "── 事前条件"
[ "$(uname -s)" = "Darwin" ] || fail "このスクリプトは macOS 用である（Linux は systemd 版が必要）"
if [ "$DRY_RUN" = 0 ] && [ "$(id -u)" != "0" ]; then
  fail "root で実行すること: sudo $0 …（--dry-run なら root は不要）"
fi
say "OS: $(sw_vers -productName) $(sw_vers -productVersion)"
say "実行者: uid=$(id -u) ($(whoami))"

if [ "$UNINSTALL" = 0 ]; then
  [ -n "${ORG_ROOT}" ] || fail "--org-root が必要（org のルート = .orgforge の親）"
  [ -d "${ORG_ROOT}/.orgforge/ledger" ] || fail "台帳が見つからない: ${ORG_ROOT}/.orgforge/ledger"
  ORG_ROOT="$(cd "${ORG_ROOT}" && pwd)"
  say "org: ${ORG_ROOT}"
  # **元の所有者を記録する。** rollback で戻すために必要である。
  ORIG_OWNER="$(stat -f '%Su:%Sg' "${ORG_ROOT}/.orgforge/ledger")"
  say "台帳の現在の所有者: ${ORIG_OWNER}"
  [ -f "$PLUGIN_DIR/tools/writerd.py" ] || fail "writerd.py が無い: $PLUGIN_DIR/tools"
  # **daemon が使う python で検査する。** 利用者の python3 に入っていても、LaunchDaemon が
  # 起動する /usr/bin/python3 に無ければ writerd は schema を読めない（実測で指摘された）。
  if ! PYTHONNOUSERSITE=1 "${DAEMON_PYTHON}" -c 'import yaml' 2>/dev/null; then
    fail "$(cat <<EOF
${DAEMON_PYTHON} に PyYAML が無い（writerd が schema を読むのに要る）。
  LaunchDaemon はここで起動するので、利用者の python3 に入っていても足りない。
  **とくに ~/Library/Python/*/lib/python/site-packages にある場合は無効である** —
  daemon は別 UID で走るので、そのユーザーの site-packages は見えない
  （このマシンの実測: PyYAML は ${HOME}/Library/Python/3.9 にあり、PYTHONNOUSERSITE=1 では
  読めなかった）。
  **PyYAML が無いと writerd は何も書けない** — ledger.py が schema を読めず、
  「検証できないまま書かない」として全ての append を拒否する（fail-closed）。
  省略できない前提条件である。

  どれかを選ぶこと:
    1. システム全体に入れる（daemon から見える）:
         sudo ${DAEMON_PYTHON} -m pip install --break-system-packages pyyaml
    2. Homebrew の python を使う:
         brew install python@3.13
         /opt/homebrew/bin/python3 -m pip install pyyaml
         sudo $0 --org-root '<org>' --daemon-python /opt/homebrew/bin/python3
    3. venv を作って daemon にそこを使わせる:
         sudo ${DAEMON_PYTHON} -m venv /usr/local/libexec/orgforge/venv
         sudo /usr/local/libexec/orgforge/venv/bin/pip install pyyaml
         sudo $0 --org-root '<org>' --daemon-python /usr/local/libexec/orgforge/venv/bin/python3
  検査したコマンド: PYTHONNOUSERSITE=1 ${DAEMON_PYTHON} -c 'import yaml'
EOF
)"
  fi
  say "${DAEMON_PYTHON}: PyYAML あり"
fi

# ── uninstall ────────────────────────────────────────────────────────────────
if [ "$UNINSTALL" = 1 ]; then
  echo
  echo "── uninstall（**台帳は消さない**。所有者を戻し、daemon を外すだけ）"
  if [ -f "${PLIST}" ]; then
    run "launchctl bootout system '${PLIST}' 2>/dev/null || true"
    run "rm -f '${PLIST}'"
    say "LaunchDaemon を外した"
  else
    say "LaunchDaemon は無い（何もしない）"
  fi
  if [ -f "${BACKUP_DIR}/original-owner" ]; then
    OWNER="$(cat "${BACKUP_DIR}/original-owner")"
    ROOTP="$(cat "${BACKUP_DIR}/original-org-root" 2>/dev/null || true)"
    if [ -n "$ROOTP" ] && [ -d "$ROOTP/.orgforge" ]; then
      run "chown -R '$OWNER' '$ROOTP/.orgforge'"
      run "chmod -R u+rwX '$ROOTP/.orgforge'"
      say "台帳の所有者を $OWNER に戻した（$ROOTP）"
    fi
  else
    say "元の所有者の記録が無い — **手で戻すこと**: chown -R \$(whoami) <org>/.orgforge"
  fi
  run "rm -rf '${SOCK_PARENT}' '${INSTALL_DIR}'"
  say "socket 親ディレクトリと daemon の複製を消した"
  if id -u "${SERVICE_USER}" >/dev/null 2>&1; then
    run "sysadminctl -deleteUser '${SERVICE_USER}' 2>/dev/null || dscl . -delete '/Users/${SERVICE_USER}'"
    say "サービスユーザー ${SERVICE_USER} を削除した"
  fi
  say "**鍵は消していない**（${ORG_ROOT}/.orgforge/trust）。判断の receipt を検証できなくなるため。"
  echo
  echo "✓ uninstall 完了。workload_isolation は process_mediated に戻る。"
  exit 0
fi

# ── サービスユーザー ─────────────────────────────────────────────────────────
echo
echo "── サービスユーザー"
if id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  say "${SERVICE_USER} は既にある（uid=$(id -u "${SERVICE_USER}")）— 作り直さない"
else
  # 500 未満の uid を探す（macOS の役割アカウントの慣習）
  NEXT_UID=""
  for u in $(seq 300 498); do
    if ! dscl . -search /Users UniqueID "$u" 2>/dev/null | grep -q .; then NEXT_UID="$u"; break; fi
  done
  [ -n "$NEXT_UID" ] || fail "空いている役割アカウント用 uid が見つからない（300-498）"
  say "uid=$NEXT_UID を使う"
  run "dscl . -create '/Groups/${SERVICE_GROUP}'"
  run "dscl . -create '/Groups/${SERVICE_GROUP}' PrimaryGroupID '$NEXT_UID'"
  run "dscl . -create '/Users/${SERVICE_USER}'"
  run "dscl . -create '/Users/${SERVICE_USER}' UserShell /usr/bin/false"
  run "dscl . -create '/Users/${SERVICE_USER}' RealName 'orgforge ledger writer'"
  run "dscl . -create '/Users/${SERVICE_USER}' UniqueID '$NEXT_UID'"
  run "dscl . -create '/Users/${SERVICE_USER}' PrimaryGroupID '$NEXT_UID'"
  run "dscl . -create '/Users/${SERVICE_USER}' NFSHomeDirectory /var/empty"
  run "dscl . -create '/Users/${SERVICE_USER}' IsHidden 1"
  say "作成した（ログイン不可・ホーム無し）"
fi

# ── daemon の複製（root 所有・caller から差し替え不能）──────────────────────
echo
echo "── daemon を root 所有の場所へ"
# **再実行で tools/tools を作らない。** `cp -R src dst/src` は dst/src があると
# その中にコピーする（実測で指摘された）。毎回消してから入れる。
run "rm -rf '${INSTALL_DIR}/tools' '${INSTALL_DIR}/template'"
run "mkdir -p '${INSTALL_DIR}'"
run "mkdir -p '${INSTALL_DIR}/tools' '${INSTALL_DIR}/template'"
run "cp -R '$PLUGIN_DIR/tools/.' '${INSTALL_DIR}/tools/'"
run "cp -R '$PLUGIN_DIR/template/.' '${INSTALL_DIR}/template/'"
run "chown -R root:wheel '${INSTALL_DIR}'"
run "chmod -R go-w '${INSTALL_DIR}'"
say "${INSTALL_DIR} （root 所有・他者書き込み不可）"
say "**caller はここを書き換えられない** — writerd 自体の差し替えを塞ぐ"

# ── socket の親ディレクトリ（root 所有）─────────────────────────────────────
echo
echo "── socket の親ディレクトリ"
run "mkdir -p '${SOCK_PARENT}'"
run "chown root:wheel '${SOCK_PARENT}'"
# **0755。** 1770 だと writerd 自身が「group から書ける親は差し替えられる」として起動を拒否する
# （実測でそうなった）。caller に必要なのは **通過（x）** であって書き込みではない。
# socket そのものは writerd が 0666 で作るので、接続はできる。
run "chmod 0755 '${SOCK_PARENT}'"
say "${SOCK_PARENT} （root 所有 0755 — 通過は許し、**誰も書き込めない**）"
say "**caller は親ディレクトリを差し替えられない** — 偽 socket に繋がされる経路を塞ぐ"

# ── 設定（root 所有。caller は台帳のパスを指定できない）─────────────────────
echo
echo "── 設定"
run "mkdir -p '$(dirname "${CONFIG}")'"
if [ "$DRY_RUN" = 1 ]; then
  printf '  [dry-run] %s に org=%s を書く\n' "${CONFIG}" "${ORG_ROOT}/.orgforge/ledger"
else
  printf 'org=default=%s\n' "${ORG_ROOT}/.orgforge/ledger" > "${CONFIG}"
  chown root:wheel "${CONFIG}"; chmod 644 "${CONFIG}"
fi
say "${CONFIG} （root 所有）— **書き込み先はここで決まる。RPC では指定できない**"

# ── 台帳・鍵・schema を writer 所有に ───────────────────────────────────────
echo
echo "── writer が所有すべき資産"
run "mkdir -p '${BACKUP_DIR}'"
if [ "$DRY_RUN" = 0 ]; then
  printf '%s\n' "${ORIG_OWNER}" > "${BACKUP_DIR}/original-owner"
  printf '%s\n' "${ORG_ROOT}"   > "${BACKUP_DIR}/original-org-root"
  chmod 600 "${BACKUP_DIR}"/original-*
fi
say "元の所有者を ${BACKUP_DIR} に記録した（rollback 用）"
# **鍵は先に退避する。** 所有者を変えると読めなくなる場合があるため。
if [ -d "${ORG_ROOT}/.orgforge/trust" ]; then
  run "cp -R '${ORG_ROOT}/.orgforge/trust' '${BACKUP_DIR}/trust-backup'"
  run "chmod -R go-rwx '${BACKUP_DIR}/trust-backup'"
  say "鍵 registry を退避した: ${BACKUP_DIR}/trust-backup"
fi
# **書けないが、読める。** 700 にすると caller の `ledger verify` も board も projection も
# 落ちる（実測で指摘された）。統制は「書けないこと」であって「見えないこと」ではない —
# 監査できない台帳は、監査のための台帳ではない。
run "chown -R '${SERVICE_USER}:${CALLER_GROUP}' '${ORG_ROOT}/.orgforge/ledger'"
run "chmod 750 '${ORG_ROOT}/.orgforge/ledger'"
run "find '${ORG_ROOT}/.orgforge/ledger' -type f -exec chmod 640 {} +"
say "台帳を ${SERVICE_USER} 所有・750/640（group=${CALLER_GROUP}）にした"
say "  → **caller は読めるが書けない**（verify / board / projection は動く）"
if [ -d "${ORG_ROOT}/.orgforge/trust" ]; then
  run "chown -R root:${SERVICE_GROUP} '${ORG_ROOT}/.orgforge/trust'"
  run "chmod 750 '${ORG_ROOT}/.orgforge/trust'"
  run "chmod 640 '${ORG_ROOT}/.orgforge/trust/keys.json' 2>/dev/null || true"
  say "鍵 registry を root 所有・group 読み取りにした → **caller は公開鍵を差し替えられない**"
fi
if [ -f "${ORG_ROOT}/ledger-schema.yaml" ]; then
  run "chown root:wheel '${ORG_ROOT}/ledger-schema.yaml'"
  run "chmod 644 '${ORG_ROOT}/ledger-schema.yaml'"
  say "schema を root 所有にした → **caller は検証規則を緩められない**"
fi

# ── LaunchDaemon ────────────────────────────────────────────────────────────
echo
echo "── LaunchDaemon"
if [ "$DRY_RUN" = 1 ]; then
  printf '  [dry-run] %s を書いて launchctl bootout/bootstrap する\n' "${PLIST}"
else
  cat > "${PLIST}" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>UserName</key><string>${SERVICE_USER}</string>
  <key>GroupName</key><string>${SERVICE_GROUP}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${DAEMON_PYTHON}</string>
    <string>${INSTALL_DIR}/tools/writerd.py</string>
    <string>serve</string>
    <string>--org</string><string>default=${ORG_ROOT}/.orgforge/ledger</string>
    <string>--socket</string><string>${SOCK_PARENT}/writer.sock</string>
    <string>--require-root-owned</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/usr/local/var/log/orgforge-writerd.log</string>
  <key>StandardErrorPath</key><string>/usr/local/var/log/orgforge-writerd.err</string>
</dict>
</plist>
PLISTEOF
  chown root:wheel "${PLIST}"; chmod 644 "${PLIST}"
  mkdir -p /usr/local/var/log
  launchctl bootout system "${PLIST}" 2>/dev/null || true
  launchctl bootstrap system "${PLIST}"
fi
say "${PLIST} （root 所有）— **caller は plist を書き換えられない**"
say "--require-root-owned 付きで起動する（socket の親が root 所有でなければ writerd が拒否する）"

# ── 次にやること ────────────────────────────────────────────────────────────
echo
echo "✓ install 完了（--dry-run では何も変えていない）"
cat <<NEXT

  次にやること:

    1. 検証を回す（**このスクリプトの自己申告ではなく、実測で確かめる**）:
         tools/writer-verify.sh --org-root '${ORG_ROOT}'

    2. org に socket を教える:
         export ORG_WRITER_SOCKET=${SOCK_PARENT}/writer.sock

    3. 戻すとき:
         sudo $0 --uninstall

  **保証の範囲:** 通常の agent / caller UID から writer の資産（台帳・鍵・schema・ラッチ）を
  変更できないこと。**ホストの管理者（root）は脅威モデルの外である** — daemon を止め、
  所有者を戻せる。それは限界ではなく境界の定義である。
NEXT
