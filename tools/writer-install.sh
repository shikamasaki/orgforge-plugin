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
SOCK_ANCHOR="/usr/local/var/orgforge"          # root 所有。caller はここに書けない
SOCK_PARENT="/usr/local/var/orgforge/run"      # writer 所有。daemon が socket を作る
INSTALL_DIR="/usr/local/libexec/orgforge"
CONFIG="/usr/local/etc/orgforge/writerd.conf"
BACKUP_DIR="/usr/local/var/orgforge/backup"
AUTHORITATIVE=""                     # 権威データ。**org tree の外**。org ごとに分ける
ORG_NAME=""                          # namespace。既定は org root のハッシュ
DAEMON_PYTHON="/usr/bin/python3"     # LaunchDaemon が起動する処理系。--daemon-python で変えられる
CALLER_GROUP="staff"                 # 台帳を読める group（caller の primary group）
CALLER_UID=""                        # 書き込みを認可する peer。既定は sudo の呼び出し元

ORG_ROOT=""
DRY_RUN=0
UNINSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --org-root) ORG_ROOT="${2:-}"; shift 2 ;;
    --org-name) ORG_NAME="${2:-}"; shift 2 ;;
    --daemon-python) DAEMON_PYTHON="${2:-}"; shift 2 ;;
    --caller-group)  CALLER_GROUP="${2:-}"; shift 2 ;;
    --caller-uid)    CALLER_UID="${2:-}"; shift 2 ;;
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
# sudo で呼ばれたなら、**元の利用者**を書き込みの認可対象にする（root ではない）。
if [ -z "${CALLER_UID}" ]; then
  CALLER_UID="${SUDO_UID:-$(id -u)}"
fi
say "書き込みを認可する caller uid: ${CALLER_UID}（--caller-uid で変えられる）"

if [ "$UNINSTALL" = 0 ]; then
  [ -n "${ORG_ROOT}" ] || fail "--org-root が必要（org のルート = .orgforge の親）"
  [ -d "${ORG_ROOT}/.orgforge/ledger" ] || fail "台帳が見つからない: ${ORG_ROOT}/.orgforge/ledger"
  ORG_ROOT="$(cd "${ORG_ROOT}" && pwd)"
  # **org ごとに分ける。** 固定のパス・Label・backup を共有すると、2つ目の org を入れた瞬間に
  # 1つ目の設定を壊す（実測で指摘された）。
  if [ -z "${ORG_NAME}" ]; then
    ORG_NAME="$(printf '%s' "${ORG_ROOT}" | shasum -a 256 | cut -c1-12)"
  fi
  AUTHORITATIVE="/usr/local/var/orgforge/orgs/${ORG_NAME}"
  SOCK_PARENT="/usr/local/var/orgforge/run/${ORG_NAME}"
  LABEL="com.orgforge.writerd.${ORG_NAME}"
  PLIST="/Library/LaunchDaemons/${LABEL}.plist"
  BACKUP_DIR="/usr/local/var/orgforge/backup/${ORG_NAME}"
  CONFIG="/usr/local/etc/orgforge/${ORG_NAME}.conf"
  say "org: ${ORG_ROOT}"
  say "namespace: ${ORG_NAME}（--org-name で固定できる）"
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

  どれかを選ぶこと（**システム python を書き換えない順**）:
    1. root 所有の専用 venv（推奨）— システムに触れず、daemon 専用に閉じる:
         sudo ${DAEMON_PYTHON} -m venv /usr/local/libexec/orgforge/venv
         sudo /usr/local/libexec/orgforge/venv/bin/pip install pyyaml
         sudo chown -R root:wheel /usr/local/libexec/orgforge/venv
         sudo $0 --org-root '<org>' --daemon-python /usr/local/libexec/orgforge/venv/bin/python3
    2. Homebrew の python（自分で管理する処理系）:
         brew install python@3.13
         /opt/homebrew/bin/python3 -m pip install pyyaml
         sudo $0 --org-root '<org>' --daemon-python /opt/homebrew/bin/python3

  **--break-system-packages でシステム python に入れることは勧めない** — OS の管理下にある
  処理系を書き換えると、他の何かが壊れたときに切り分けられなくなる。
  検査したコマンド: PYTHONNOUSERSITE=1 ${DAEMON_PYTHON} -c 'import yaml'
EOF
)"
  fi
  say "${DAEMON_PYTHON}: PyYAML あり"
fi

# ── uninstall ────────────────────────────────────────────────────────────────
if [ "$UNINSTALL" = 1 ]; then
  # **どの org を外すのかを決める。** namespace が無いと、複数 org で固定の Label / backup を
  # 共有し、1つ外すと全部壊れる（実測で指摘された）。
  if [ -z "${ORG_NAME}" ] && [ -n "${ORG_ROOT}" ]; then
    ORG_NAME="$(printf '%s' "$(cd "${ORG_ROOT}" && pwd)" | shasum -a 256 | cut -c1-12)"
  fi
  if [ -z "${ORG_NAME}" ]; then
    fail "--org-root か --org-name が必要（どの org を外すのか決まらない）"
  fi
  AUTHORITATIVE="/usr/local/var/orgforge/orgs/${ORG_NAME}"
  SOCK_PARENT="/usr/local/var/orgforge/run/${ORG_NAME}"
  LABEL="com.orgforge.writerd.${ORG_NAME}"
  PLIST="/Library/LaunchDaemons/${LABEL}.plist"
  BACKUP_DIR="/usr/local/var/orgforge/backup/${ORG_NAME}"
  CONFIG="/usr/local/etc/orgforge/${ORG_NAME}.conf"
  say "namespace: ${ORG_NAME}"
  echo
  echo "── uninstall（**台帳は消さない**。順序: daemon停止 → 書戻し → 実体化 → 所有者復元）"
  # ① daemon を止める。**先に止めないと、書き戻している途中に writer が書く。**
  if [ -f "${PLIST}" ]; then
    # **停止の失敗を握り潰さない。** 止まっていない writer が、書き戻している最中に書く。
    if [ "${DRY_RUN}" = 0 ]; then
      launchctl bootout system "${PLIST}" 2>/dev/null || true
      sleep 1
      if launchctl print "system/${LABEL}" >/dev/null 2>&1; then
        fail "LaunchDaemon を止められなかった（system/${LABEL} がまだ居る）。
  **止まっていない writer が、書き戻している最中に台帳へ書く。**
  手で止めてから再実行すること:
    sudo launchctl bootout system ${PLIST}"
      fi
    else
      printf '  [dry-run] launchctl bootout system %s（停止を確認する）\n' "${PLIST}"
    fi
    run "rm -f '${PLIST}'"
    say "① LaunchDaemon を停止した（停止を確認済み）"
  else
    say "① LaunchDaemon は無い"
  fi

  ROOTP="$(cat "${BACKUP_DIR}/original-org-root" 2>/dev/null || true)"
  OWNER="$(cat "${BACKUP_DIR}/original-owner" 2>/dev/null || true)"
  if [ -z "$ROOTP" ] && [ -n "${ORG_ROOT}" ]; then ROOTP="${ORG_ROOT}"; fi

  # **既定は「復元していない」。** 復元ループに入らなかったとき（org root が移動・消失した等）に
  # 「復元済み」と見なすと、権威側にしか無い最新データを消す = 永続データ損失。
  # 消してよいのは、**戻したことを確かめられたときだけ**である（実測で指摘された）。
  RESTORE_OK=0

  # ②③ 権威側の内容を書き戻し、symlink を実体に置き換える。
  if [ -n "$ROOTP" ] && [ -d "$ROOTP" ]; then
    RESTORE_OK=1
    for pair in ".orgforge/ledger:ledger" ".orgforge/trust:trust" \
                "ledger-schema.yaml:ledger-schema.yaml"; do
      cur="${ROOTP}/${pair%%:*}"; src="${AUTHORITATIVE}/${pair##*:}"
      old_copy="${ROOTP}/${pair%%:*}.pre-writer"
      # **symlink が無いことを「戻し済み」と読んではいけない。**
      # caller は自分の org tree を動かせる（例: .orgforge を rename する）。すると symlink は
      # 消え、権威側だけが唯一の最新の写しになる。ここで continue すると ⑤ がそれを消す
      # = 永続データ損失（実測で指摘された）。
      # **「在ること」を「戻っていること」と読んではいけない。**
      # caller は symlink の代わりに **自分の偽の実体** を置ける。それを「復元済み」と認めると、
      # ⑤ が権威側の最新版を消し、org 側には caller が置いた古い中身だけが残る
      # （= 永続データ損失。実測で確認した4つ目の変種）。
      # 飛ばしてよいのは **権威側に何も無いとき** か、**中身が一致するとき** だけである。
      if [ ! -L "${cur}" ] && [ -e "${cur}" ]; then
        if [ ! -e "${src}" ]; then
          continue                     # 権威側に無い = 戻すものが無い
        fi
        # **数は caller が合わせられる。** ファイル数の一致を「同じ中身」と読むと、
        # 数だけ揃えた偽物で権威側の最新版を消せる（実測で確認した5つ目の変種）。
        # **中身の digest で比べる** — caller はデータを持っていない限り一致させられない。
        # `-type f` だけだと **symlink が数えられない** — caller は中身を一致させたまま
        # symlink を紛れ込ませられる（実測）。名前と種別も digest に入れる。
        # **名前だけでは足りない。** 同じ名前の「ディレクトリ」と「symlink」は名前が同じなので、
        # 名前だけを入れると同一と誤認する（実測）。**種別と symlink の向き先**まで入れる。
        _digest() (
          cd "$1" 2>/dev/null || return 0
          { find . -type f -exec shasum -a 256 {} \;
            find . \! -type f -exec stat -f 'entry %N type=%HT link=%Y' {} \; ; } \
            | sort | shasum -a 256 | cut -d' ' -f1
        )
        d_s="$(_digest "${src}")"
        d_c="$(_digest "${cur}")"
        if [ -n "${d_s}" ] && [ "${d_s}" = "${d_c}" ]; then
          continue                     # 中身が同一 = 戻っている
        fi
        say "  ！$(basename "${cur}") に実体が在るが、権威側と中身が違う。"
        say "    **「在る」を「戻った」と読まない** — 権威側を消さずに退避する"
        run "mv '${cur}' '${cur}.found-$$'"
      fi
      if [ ! -L "${cur}" ]; then
        if [ -e "${src}" ]; then
          say "  ！$(basename "${cur}") の symlink が無いのに権威側に実体が在る。"
          say "    org tree が動かされた可能性がある — **消さずに復元を試みる**"
          run "mkdir -p '$(dirname "${cur}")'"
        else
          continue                     # 権威側にも無い = 消すものが無い
        fi
      fi
      # **順序が安全性である。** 先に symlink を消すと、コピーが失敗した時点で org 側から
      # 実体が消え、再実行時は `[ -L ]` が偽なので復元を飛ばし、⑤が権威データを消す
      # （= 唯一の写しを失う）。実測で指摘された。
      #   ① 隣に新しい実体を作る（cur には触れない）
      #   ② 中身を検証する
      #   ③ atomic に差し替える
      #   ④ そのあとで初めて古い symlink を消す
      staged="${cur}.restoring.$$"
      run "rm -rf '${staged}'"
      if [ -e "${src}" ]; then
        run "cp -R '${src}' '${staged}'"
        FROM="権威側"
      elif [ -e "${old_copy}" ]; then
        run "cp -R '${old_copy}' '${staged}'"
        FROM="install 前の控え"
      else
        say "  ！$(basename "${cur}") の復元元が無い（権威側も控えも）— **symlink を残す**"
        RESTORE_OK=0
        continue
      fi
      # ② 検証。**中身を確かめてから差し替える。**
      if [ "${DRY_RUN}" = 0 ]; then
        if [ -d "${staged}" ]; then
          n_src="$(find "${src}" -type f 2>/dev/null | wc -l | tr -d ' ')"
          n_dst="$(find "${staged}" -type f 2>/dev/null | wc -l | tr -d ' ')"
          if [ "${n_src}" != "${n_dst}" ]; then
            say "  ！$(basename "${cur}") のコピーが不完全（${n_src} → ${n_dst}）— **中止**"
            rm -rf "${staged}"
            RESTORE_OK=0
            continue
          fi
        fi
        sync 2>/dev/null || true
      fi
      # ③④ atomic に置き換え、そのあとで symlink を消す
      run "rm -f '${cur}'"
      run "mv '${staged}' '${cur}'"
      say "② $(basename "${cur}") を${FROM}の内容で実体化した"
      [ -e "${old_copy}" ] && say "  （install 前の控え: ${old_copy} — 確認して消すこと）"
    done
    say "③ symlink を実体に置き換えた"
    # ④ 所有者を戻す。**書き戻したあとに行う** — 先に戻すと writer が書けなくなる。
    if [ -n "$OWNER" ]; then
      run "chown -R '$OWNER' '$ROOTP/.orgforge'"
      run "chmod -R u+rwX '$ROOTP/.orgforge'"
      [ -e "$ROOTP/ledger-schema.yaml" ] && run "chown '$OWNER' '$ROOTP/ledger-schema.yaml'"
      say "④ 所有者を $OWNER に戻した"
    else
      say "④ **元の所有者の記録が無い** — 手で戻すこと: chown -R \$(whoami) '$ROOTP/.orgforge'"
    fi
  fi

  # ⑤ この org のものだけを消す。**共有物は他 org が残る間は消さない。**
  # **復元できていないなら、権威データも backup も消さない。** 消すと唯一の写しを失う
  # （実測で指摘された経路）。再実行できる状態のまま止める。
  if [ -z "$ROOTP" ] || [ ! -d "$ROOTP" ]; then
    say "！org root が見つからない: ${ROOTP:-（記録なし）}"
    say "  移動されたか消されている。**権威側にしか無いデータを消さない。**"
  fi
  if [ "${RESTORE_OK}" = 0 ]; then
    run "rm -rf '${SOCK_PARENT}'"
    say "⑤ socket だけ消した。**権威データと backup は残す** — 復元できていない。"
    say "  内容: ${AUTHORITATIVE}"
    say "  控え: ${BACKUP_DIR}"
    say "  原因を確かめてから、同じコマンドを再実行すること（この uninstall は冪等である）。"
    echo
    echo "✗ uninstall は完了していない。**データは消していない。**"
    exit 1
  fi
  run "rm -rf '${SOCK_PARENT}' '${AUTHORITATIVE}' '${BACKUP_DIR}' '${CONFIG}'"
  say "⑤ この org（${ORG_NAME}）の socket / 権威データ / backup / 設定を消した"
  REMAINING="$(ls -1 /usr/local/var/orgforge/orgs 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${REMAINING}" = "0" ]; then
    run "rm -rf '${INSTALL_DIR}'"
    say "  他の org が無いので共有コードも消した"
    if id -u "${SERVICE_USER}" >/dev/null 2>&1; then
      run "sysadminctl -deleteUser '${SERVICE_USER}' 2>/dev/null || dscl . -delete '/Users/${SERVICE_USER}'"
      say "  サービスユーザー ${SERVICE_USER} を削除した"
    fi
  else
    say "  **他の org が ${REMAINING} 件残っているので、共有コードとサービス UID は消さない**"
  fi
  say "**鍵は消していない**（権威側を org へ書き戻した）。判断の receipt を検証できなくなるため。"
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
  # 500 未満の uid を探す（macOS の役割アカウントの慣習）。
  # **uid と gid の両方が空いている番号でなければならない。** 同じ番号を
  # PrimaryGroupID にも使うので、gid が既存だと **writer の group を他人と共有する**
  # ことになり、group 権限で台帳へ届く経路ができる（このマシンでは 395-400 が該当した）。
  NEXT_UID=""
  for u in $(seq 300 498); do
    if dscl . -search /Users UniqueID "$u" 2>/dev/null | grep -q .; then continue; fi
    if dscl . -search /Groups PrimaryGroupID "$u" 2>/dev/null | grep -q .; then continue; fi
    NEXT_UID="$u"; break
  done
  [ -n "$NEXT_UID" ] || fail "uid と gid が **両方** 空いている番号が見つからない（300-498）"
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
# **anchor と leaf を分ける。**
#
#   anchor: root 所有 0755。**caller はここに書けない**ので、leaf ごと差し替えられない。
#   leaf:   writer 所有 0755。**daemon がここに socket を作る**（bind は親への書き込み権限が要る）。
#
# 実測（監査）: root 所有 0755 の親には **daemon 自身が bind できない**（Permission denied）。
# 0755 も 1770 も、どちらでも動かない — 前者は daemon が作れず、後者は writerd が拒否する。
# caller から見た保証は「**anchor に書けないので leaf を差し替えられない**」ことである。
#
# より強い形は launchd の socket activation（launchd が先に socket を作り FD を daemon に渡す）
# で、その場合 leaf すら writer 所有でなくてよい。ここでは移植性のため anchor/leaf 方式を採る。
run "chown root:wheel '${SOCK_ANCHOR}'"
run "chmod 0755 '${SOCK_ANCHOR}'"
run "mkdir -p '${SOCK_PARENT}'"
run "chown '${SERVICE_USER}:${SERVICE_GROUP}' '${SOCK_PARENT}'"
run "chmod 0755 '${SOCK_PARENT}'"
say "${SOCK_ANCHOR} （root 所有 0755 — **caller はここに書けない**）"
say "${SOCK_PARENT} （${SERVICE_USER} 所有 0755 — daemon が socket を作れる／caller は書けない）"
say "**caller は親ディレクトリを差し替えられない** — 偽 socket に繋がされる経路を塞ぐ"

# ── 設定（root 所有。caller は台帳のパスを指定できない）─────────────────────
echo
echo "── 設定"
run "mkdir -p '$(dirname "${CONFIG}")'"
if [ "$DRY_RUN" = 1 ]; then
  printf '  [dry-run] %s に org=%s を書く\n' "${CONFIG}" "${ORG_ROOT}/.orgforge/ledger"
else
  printf 'org=default=%s\n' "${AUTHORITATIVE}/ledger" > "${CONFIG}"
  chown root:wheel "${CONFIG}"; chmod 644 "${CONFIG}"
fi
say "${CONFIG} （root 所有）— **書き込み先はここで決まる。RPC では指定できない**"

# ── 台帳・鍵・schema を writer 所有に ───────────────────────────────────────
echo
echo "── writer が所有すべき資産"
run "mkdir -p '${BACKUP_DIR}'"
# **再 install で上書きしない。** 2回目の実行では所有者が既に writer になっているので、
# それを「元の所有者」として記録すると、uninstall が service UID へ「復元」してしまう
# （実測で指摘された）。最初の1回だけ書く。
if [ "$DRY_RUN" = 0 ]; then
  if [ -f "${BACKUP_DIR}/original-owner" ]; then
    say "元の所有者は既に記録されている（$(cat "${BACKUP_DIR}/original-owner")）— 上書きしない"
  elif [ "$(printf '%s' "${ORIG_OWNER}" | cut -d: -f1)" = "${SERVICE_USER}" ]; then
    fail "$(cat <<EOF2
台帳の所有者が既に ${SERVICE_USER} だが、元の所有者の記録が無い。
  このまま進めると uninstall が ${SERVICE_USER} へ「復元」して、caller に戻せなくなる。
  手で記録してから再実行すること:
    echo '<元の owner:group>' | sudo tee ${BACKUP_DIR}/original-owner
    echo '${ORG_ROOT}' | sudo tee ${BACKUP_DIR}/original-org-root
EOF2
)"
  else
    printf '%s\n' "${ORIG_OWNER}" > "${BACKUP_DIR}/original-owner"
    printf '%s\n' "${ORG_ROOT}"   > "${BACKUP_DIR}/original-org-root"
    chmod 600 "${BACKUP_DIR}"/original-*
    say "元の所有者を ${BACKUP_DIR} に記録した（rollback 用。**再 install では上書きしない**）"
  fi
fi
# **鍵は先に退避する。** 所有者を変えると読めなくなる場合があるため。
if [ -d "${ORG_ROOT}/.orgforge/trust" ]; then
  run "cp -R '${ORG_ROOT}/.orgforge/trust' '${BACKUP_DIR}/trust-backup'"
  run "chmod -R go-rwx '${BACKUP_DIR}/trust-backup'"
  say "鍵 registry を退避した: ${BACKUP_DIR}/trust-backup"
fi
# **書けないが、読める。** 700 にすると caller の `ledger verify` も board も projection も
# 落ちる（実測で指摘された）。統制は「書けないこと」であって「見えないこと」ではない —
# 監査できない台帳は、監査のための台帳ではない。
# **org tree 自体が caller の所有なので、その中にあるものはパスごと差し替えられる。**
# 実測（監査）: .orgforge と org root が caller 所有のままなので、writer 所有の ledger/trust や
# root 所有の schema を **ディレクトリごと** 置き換えられた。中身の権限を絞っても、入れ物を
# 差し替えられるなら意味が無い。
#
# したがって **権威データは org tree の外に置き、org tree からは symlink で指す**。
# 実体は root 所有のディレクトリ配下にあり、caller はそこに書けない。
# symlink を張り替えられても、writerd は `--org` で **実体のパス** を固定して起動するので、
# 書き込み先は変わらない（読み手が騙される可能性は残る — それは次段で扱う）。
run "mkdir -p '${AUTHORITATIVE}/ledger' '${AUTHORITATIVE}/trust'"
run "chown root:wheel '${AUTHORITATIVE}'"
run "chmod 0755 '${AUTHORITATIVE}'"
if [ -d "${ORG_ROOT}/.orgforge/ledger" ] && [ ! -L "${ORG_ROOT}/.orgforge/ledger" ]; then
  run "cp -R '${ORG_ROOT}/.orgforge/ledger/.' '${AUTHORITATIVE}/ledger/'"
  run "mv '${ORG_ROOT}/.orgforge/ledger' '${ORG_ROOT}/.orgforge/ledger.pre-writer'"
  run "ln -s '${AUTHORITATIVE}/ledger' '${ORG_ROOT}/.orgforge/ledger'"
  say "台帳を ${AUTHORITATIVE}/ledger へ移し、org からは symlink で指す"
  say "  （元は ${ORG_ROOT}/.orgforge/ledger.pre-writer に残す — **消さない**）"
fi
if [ -d "${ORG_ROOT}/.orgforge/trust" ] && [ ! -L "${ORG_ROOT}/.orgforge/trust" ]; then
  run "cp -R '${ORG_ROOT}/.orgforge/trust/.' '${AUTHORITATIVE}/trust/'"
  run "mv '${ORG_ROOT}/.orgforge/trust' '${ORG_ROOT}/.orgforge/trust.pre-writer'"
  run "ln -s '${AUTHORITATIVE}/trust' '${ORG_ROOT}/.orgforge/trust'"
  say "鍵 registry を ${AUTHORITATIVE}/trust へ移した"
fi
# **constitution を root 所有で固定する。**
# ここに宣言（require_attested_identity など）が入っている。caller が書ける場所に置いたままだと、
# caller が宣言を偽に書き換えて強制を消せる — **検査の入力を、検査される側が書けてはいけない。**
# また daemon は org の外で動くので、cwd から探させてはいけない（実測: 導出に失敗し、
# 未認証 admission が通った）。よってコピーして、パスを明示的に渡す。
if [ -f "${ORG_ROOT}/constitution.yaml" ] && [ ! -L "${ORG_ROOT}/constitution.yaml" ]; then
  run "cp '${ORG_ROOT}/constitution.yaml' '${AUTHORITATIVE}/constitution.yaml'"
  run "chown root:wheel '${AUTHORITATIVE}/constitution.yaml'"
  run "chmod 0644 '${AUTHORITATIVE}/constitution.yaml'"
  # **写しは古くなる。** org 側は caller が編集できるまま残す（宣言を読むのは人間でもある）。
  # だが編集しても daemon には届かない — 届いたら caller が強制を消せてしまうからである。
  # 「編集したのに効かない」を黙って起こさないよう、**食い違いを見えるようにする**。
  say "  constitution を root 所有で固定した: ${AUTHORITATIVE}/constitution.yaml"
  say "  **org 側 (${ORG_ROOT}/constitution.yaml) を編集しても daemon には届かない。**"
  say "  宣言を変えたら、この installer を再実行して固定し直すこと。"
  say "  食い違いは writerd が起動時に警告する。"
elif [ ! -f "${AUTHORITATIVE}/constitution.yaml" ]; then
  fail "constitution.yaml が無い: ${ORG_ROOT}/constitution.yaml
  **宣言が無いまま writer を動かさない。** require_attested_identity が子プロセスに届かず、
  未認証の admission が通る（実測で指摘された経路）。"
fi

if [ -f "${ORG_ROOT}/ledger-schema.yaml" ] && [ ! -L "${ORG_ROOT}/ledger-schema.yaml" ]; then
  run "cp '${ORG_ROOT}/ledger-schema.yaml' '${AUTHORITATIVE}/ledger-schema.yaml'"
  run "chown root:wheel '${AUTHORITATIVE}/ledger-schema.yaml'"
  run "chmod 0644 '${AUTHORITATIVE}/ledger-schema.yaml'"
  run "mv '${ORG_ROOT}/ledger-schema.yaml' '${ORG_ROOT}/ledger-schema.yaml.pre-writer'"
  run "ln -s '${AUTHORITATIVE}/ledger-schema.yaml' '${ORG_ROOT}/ledger-schema.yaml'"
  say "schema を ${AUTHORITATIVE} へ移した（daemon は実体のパスを --schema で受け取る）"
fi
run "chown -R '${SERVICE_USER}:${CALLER_GROUP}' '${AUTHORITATIVE}/ledger'"
run "chmod 750 '${AUTHORITATIVE}/ledger'"
run "find '${AUTHORITATIVE}/ledger' -type f -exec chmod 640 {} +"
say "台帳を ${SERVICE_USER} 所有・750/640（group=${CALLER_GROUP}）にした"
say "  → **caller は読めるが書けない**（verify / board / projection は動く）"
if [ -d "${AUTHORITATIVE}/trust" ]; then
  run "chown -R root:${SERVICE_GROUP} '${AUTHORITATIVE}/trust'"
  run "chmod 750 '${AUTHORITATIVE}/trust'"
  run "chmod 640 '${AUTHORITATIVE}/trust/keys.json' 2>/dev/null || true"
  say "鍵 registry を root 所有・group 読み取りにした → **caller は公開鍵を差し替えられない**"
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
    <!-- **実体のパスを渡す。** org tree の symlink を張り替えられても、書き込み先は動かない。 -->
    <string>--org</string><string>default=${AUTHORITATIVE}/ledger</string>
    <string>--socket</string><string>${SOCK_PARENT}/writer.sock</string>
    <!-- **schema を固定する。** 渡さないと ledger.py が cwd から org を探し、見つからなければ
         プラグインのテンプレートに fallback する — org が変えた規則ではなく、テンプレートの
         規則で検証されることになる（実測で指摘された）。 -->
    <string>--schema</string><string>${AUTHORITATIVE}/ledger-schema.yaml</string>
    <!-- **宣言を固定する。** daemon は org の外で動くので、台帳のパスから org root を
         導出することはできない（実測: 導出に失敗し、未認証 admission が通った）。 -->
    <string>--constitution</string><string>default=${AUTHORITATIVE}/constitution.yaml</string>
    <!-- **trust store を固定する。** installer は trust を ${AUTHORITATIVE} へ移し、
         org 側を .pre-writer に改名する。ここで渡さないと daemon（cwd=/）は鍵 registry を
         見つけられず、**正しく署名された receipt もすべて拒否される**（実測で指摘された）。 -->
    <string>--trust</string><string>default=${AUTHORITATIVE}/trust/keys.json</string>
    <!-- **caller UID を配線する。** socket は 0666 なので繋げること自体は誰でもできる —
         繋げることと書けることは別である。 -->
    <string>--allow-uid</string><string>${CALLER_UID}</string>
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
