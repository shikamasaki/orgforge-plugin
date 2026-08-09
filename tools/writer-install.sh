#!/usr/bin/env bash
# writer-install.sh — install writerd as a LaunchDaemon under a separate UID (stage B, macOS).
#
# ## What this changes
#
# Stage A (running `writerd.py` under the same UID) can enforce no more than "there is one path to
# the ledger". **A caller under the same UID can stop the daemon and restore the file permissions**,
# so `workload_isolation` stays at `process_mediated`.
#
# This script:
#   - creates a dedicated UID (a service account)
#   - makes the ledger, key registry, schema, and HALT latch **owned by that UID**
#   - makes the socket's parent directory **root-owned and unwritable by others**
#   - makes the daemon, plist, and configuration **root-owned**, so a caller cannot replace them
#
# With all of that in place, **a normal caller UID can no longer write to the ledger files** (it
# fails on OS permissions). Only then may `workload_isolation: separate_uid` be claimed.
#
# ## What falls outside the threat model
#
# **The host's administrator (root).** They can stop the LaunchDaemon, restore the ownership, and
# rewrite the plist. What is guaranteed is that **a normal agent / caller UID cannot modify the
# writer's assets** — not root. That is not a limitation but the definition of the boundary.
#
# ## Usage
#
#   sudo tools/writer-install.sh --org-root /path/to/org --dry-run   # see what it would do
#   sudo tools/writer-install.sh --org-root /path/to/org             # run it
#   sudo tools/writer-install.sh --org-root /path/to/org --uninstall  # put it back
#
# It is idempotent. What already exists is not rebuilt; only what is missing is added.
set -euo pipefail
# **It stops on failure.** Without set -e a half-finished chown prints "install complete" and
# leaves an org whose daemon will not start (raised by measurement).

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_USER="_orgforge-writer"
SERVICE_GROUP="_orgforge-writer"
LABEL="com.orgforge.writerd"
PLIST="/Library/LaunchDaemons/${LABEL}.plist"
SOCK_ANCHOR="/usr/local/var/orgforge"          # root-owned. A caller cannot write here
SOCK_PARENT="/usr/local/var/orgforge/run"      # writer-owned. The daemon creates the socket here
INSTALL_DIR="/usr/local/libexec/orgforge"
CONFIG="/usr/local/etc/orgforge/writerd.conf"
BACKUP_DIR="/usr/local/var/orgforge/backup"
AUTHORITATIVE=""                     # the authoritative data. **Outside the org tree.** Per org
ORG_NAME=""                          # the namespace. Defaults to a hash of the org root
DAEMON_PYTHON="/usr/bin/python3"     # the interpreter the LaunchDaemon starts. --daemon-python
CALLER_GROUP="staff"                 # the group that can read the ledger (the caller's primary)
CALLER_UID=""                        # the peer authorized to write. Defaults to sudo's caller

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
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '  %s\n' "$*"; }
run()  {
  if [ "$DRY_RUN" = 1 ]; then printf '  [dry-run] %s\n' "$*"; return 0; fi
  if ! eval "$@"; then
    printf '✗ failed: %s\n' "$*" >&2
    printf '  **Do not continue in a half-finished state.** To undo the changes made so far:\n' >&2
    printf '    sudo %s --uninstall\n' "$0" >&2
    exit 1
  fi
}
fail() { printf '✗ %s\n' "$*" >&2; exit 1; }

# ── preconditions ───────────────────────────────────────────────────────────
echo "── preconditions"
[ "$(uname -s)" = "Darwin" ] || fail "this script is for macOS (Linux needs a systemd version)"
if [ "$DRY_RUN" = 0 ] && [ "$(id -u)" != "0" ]; then
  fail "run it as root: sudo $0 … (--dry-run does not need root)"
fi
say "OS: $(sw_vers -productName) $(sw_vers -productVersion)"
say "running as: uid=$(id -u) ($(whoami))"
# Where it was called through sudo, **the original user** is what is authorized to write (not
# root).
if [ -z "${CALLER_UID}" ]; then
  CALLER_UID="${SUDO_UID:-$(id -u)}"
fi
say "the caller uid authorized to write: ${CALLER_UID} (change it with --caller-uid)"

if [ "$UNINSTALL" = 0 ]; then
  [ -n "${ORG_ROOT}" ] || fail "--org-root is required (the org's root = the parent of .orgforge)"
  [ -d "${ORG_ROOT}/.orgforge/ledger" ] || fail "no ledger found: ${ORG_ROOT}/.orgforge/ledger"
  ORG_ROOT="$(cd "${ORG_ROOT}" && pwd)"
  # **Separate per org.** Sharing one fixed path, Label, and backup breaks the first org's
  # configuration the moment a second org is installed (raised by measurement).
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
  say "namespace: ${ORG_NAME} (fix it with --org-name)"
  # **Record the original owner.** It is needed to restore on rollback.
  ORIG_OWNER="$(stat -f '%Su:%Sg' "${ORG_ROOT}/.orgforge/ledger")"
  say "the ledger's current owner: ${ORIG_OWNER}"
  [ -f "$PLUGIN_DIR/tools/writerd.py" ] || fail "no writerd.py: $PLUGIN_DIR/tools"
  # **Check with the python the daemon uses.** Present in the user's python3 or not, writerd cannot
  # read the schema unless it is in the /usr/bin/python3 the LaunchDaemon starts (raised by
  # measurement).
  if ! PYTHONNOUSERSITE=1 "${DAEMON_PYTHON}" -c 'import yaml' 2>/dev/null; then
    fail "$(cat <<EOF
${DAEMON_PYTHON} has no PyYAML (writerd needs it to read the schema).
  The LaunchDaemon starts here, so having it in the user's python3 is not enough.
  **It is useless in ~/Library/Python/*/lib/python/site-packages in particular** — the daemon runs
  under a different UID, so that user's site-packages is invisible to it
  (measured on this machine: PyYAML was in ${HOME}/Library/Python/3.9 and was unreadable under
  PYTHONNOUSERSITE=1).
  **Without PyYAML writerd can write nothing** — ledger.py cannot read the schema and refuses every
  append as "do not write what cannot be verified" (fail-closed).
  It is a precondition that cannot be skipped.

  Pick one (**ordered by not rewriting the system python**):
    1. a root-owned dedicated venv (recommended) — it touches nothing system-wide and stays closed
       to the daemon:
         sudo ${DAEMON_PYTHON} -m venv /usr/local/libexec/orgforge/venv
         sudo /usr/local/libexec/orgforge/venv/bin/pip install pyyaml
         sudo chown -R root:wheel /usr/local/libexec/orgforge/venv
         sudo $0 --org-root '<org>' --daemon-python /usr/local/libexec/orgforge/venv/bin/python3
    2. Homebrew's python (an interpreter you manage yourself):
         brew install python@3.13
         /opt/homebrew/bin/python3 -m pip install pyyaml
         sudo $0 --org-root '<org>' --daemon-python /opt/homebrew/bin/python3

  **Installing into the system python with --break-system-packages is not advised** — rewriting an
  interpreter the OS manages makes it impossible to isolate the cause when something else breaks.
  The command that was checked: PYTHONNOUSERSITE=1 ${DAEMON_PYTHON} -c 'import yaml'
EOF
)"
  fi
  say "${DAEMON_PYTHON}: PyYAML present"
fi

# ── uninstall ────────────────────────────────────────────────────────────────
if [ "$UNINSTALL" = 1 ]; then
  # **Decide which org is being removed.** Without a namespace, several orgs share one fixed Label
  # and backup, and removing one breaks them all (raised by measurement).
  if [ -z "${ORG_NAME}" ] && [ -n "${ORG_ROOT}" ]; then
    ORG_NAME="$(printf '%s' "$(cd "${ORG_ROOT}" && pwd)" | shasum -a 256 | cut -c1-12)"
  fi
  if [ -z "${ORG_NAME}" ]; then
    fail "--org-root or --org-name is required (which org to remove is undecided)"
  fi
  AUTHORITATIVE="/usr/local/var/orgforge/orgs/${ORG_NAME}"
  SOCK_PARENT="/usr/local/var/orgforge/run/${ORG_NAME}"
  LABEL="com.orgforge.writerd.${ORG_NAME}"
  PLIST="/Library/LaunchDaemons/${LABEL}.plist"
  BACKUP_DIR="/usr/local/var/orgforge/backup/${ORG_NAME}"
  CONFIG="/usr/local/etc/orgforge/${ORG_NAME}.conf"
  say "namespace: ${ORG_NAME}"
  echo
  echo "── uninstall (**the ledger is never removed**. Order: stop the daemon → write back →
materialise → restore ownership)"
  # ① Stop the daemon. **Without stopping first, the writer writes mid-restore.**
  if [ -f "${PLIST}" ]; then
    # **Do not swallow a failure to stop.** A writer still running writes mid-restore.
    if [ "${DRY_RUN}" = 0 ]; then
      launchctl bootout system "${PLIST}" 2>/dev/null || true
      sleep 1
      if launchctl print "system/${LABEL}" >/dev/null 2>&1; then
        fail "could not stop the LaunchDaemon (system/${LABEL} is still there).
  **A writer that has not stopped writes to the ledger mid-restore.**
  Stop it by hand and run this again:
    sudo launchctl bootout system ${PLIST}"
      fi
    else
      printf '  [dry-run] launchctl bootout system %s (confirming it stopped)\n' "${PLIST}"
    fi
    run "rm -f '${PLIST}'"
    say "① stopped the LaunchDaemon (confirmed stopped)"
  else
    say "① there is no LaunchDaemon"
  fi

  ROOTP="$(cat "${BACKUP_DIR}/original-org-root" 2>/dev/null || true)"
  OWNER="$(cat "${BACKUP_DIR}/original-owner" 2>/dev/null || true)"
  if [ -z "$ROOTP" ] && [ -n "${ORG_ROOT}" ]; then ROOTP="${ORG_ROOT}"; fi

  # **The default is "not restored".** Treating it as restored where the restore loop never ran (the
  # org root was moved or deleted, say) deletes the only up-to-date copy, which lives on the
  # authoritative side = permanent data loss.
  # Deletion is allowed **only once the restore is confirmed** (raised by measurement).
  RESTORE_OK=0

  # ②③ Write the authoritative content back and replace the symlink with real content.
  if [ -n "$ROOTP" ] && [ -d "$ROOTP" ]; then
    RESTORE_OK=1
    for pair in ".orgforge/ledger:ledger" ".orgforge/trust:trust" \
                "ledger-schema.yaml:ledger-schema.yaml"; do
      cur="${ROOTP}/${pair%%:*}"; src="${AUTHORITATIVE}/${pair##*:}"
      old_copy="${ROOTP}/${pair%%:*}.pre-writer"
      # **The absence of a symlink must never be read as "already restored".**
      # A caller can move its own org tree (renaming .orgforge, say). The symlink then disappears and
      # the authoritative side becomes the only up-to-date copy. Continuing here has ⑤ delete it =
      # permanent data loss (raised by measurement).
      # **"It is there" must never be read as "it was restored".**
      # A caller can plant **its own fake content** in place of the symlink. Accepting that as
      # "restored" has ⑤ delete the authoritative side's latest version, leaving the org side with
      # only the stale content the caller planted (= permanent data loss; the fourth variant
      # confirmed by measurement).
      # It may be skipped **only where the authoritative side holds nothing**, or **where the content
      # matches**.
      if [ ! -L "${cur}" ] && [ -e "${cur}" ]; then
        if [ ! -e "${src}" ]; then
          continue                     # nothing authoritative = nothing to restore
        fi
        # **A caller can match the count.** Reading a matching file count as "the same content" lets
        # a forgery that merely matches the count delete the authoritative side's latest version (the
        # fifth variant confirmed by measurement).
        # **Compare by a digest of the content** — a caller cannot match that without holding the
        # data.
        # `-type f` alone **does not count symlinks** — a caller can slip a symlink in while keeping
        # the content matching (measured). Names and types go into the digest as well.
        # **Names alone are not enough.** A "directory" and a "symlink" of the same name share that
        # name, so including only names misidentifies them as the same (measured). **The type and
        # the symlink's target** go in too.
        _digest() (
          cd "$1" 2>/dev/null || return 0
          { find . -type f -exec shasum -a 256 {} \;
            find . \! -type f -exec stat -f 'entry %N type=%HT link=%Y' {} \; ; } \
            | sort | shasum -a 256 | cut -d' ' -f1
        )
        d_s="$(_digest "${src}")"
        d_c="$(_digest "${cur}")"
        if [ -n "${d_s}" ] && [ "${d_s}" = "${d_c}" ]; then
          continue                     # identical content = it is restored
        fi
        say "  ! $(basename "${cur}") holds real content, but it differs from the authoritative side."
        say "    **\"it is there\" is not read as \"it was restored\"** — it is set aside without deleting the authoritative side"
        run "mv '${cur}' '${cur}.found-$$'"
      fi
      if [ ! -L "${cur}" ]; then
        if [ -e "${src}" ]; then
          say "  ! $(basename "${cur}") has no symlink, yet the authoritative side holds real content."
          say "    the org tree may have been moved — **a restore is attempted rather than a deletion**"
          run "mkdir -p '$(dirname "${cur}")'"
        else
          continue                     # nothing on either side = nothing to delete
        fi
      fi
      # **The order is the safety.** Removing the symlink first makes the real content vanish from
      # the org side the moment a copy fails; on a re-run `[ -L ]` is false, so the restore is skipped
      # and ⑤ deletes the authoritative data (= the only copy is lost). Raised by measurement.
      #   ① create the new content alongside (cur is untouched)
      #   ② verify the content
      #   ③ swap it in atomically
      #   ④ only then remove the old symlink
      staged="${cur}.restoring.$$"
      run "rm -rf '${staged}'"
      if [ -e "${src}" ]; then
        run "cp -R '${src}' '${staged}'"
        FROM="the authoritative side"
      elif [ -e "${old_copy}" ]; then
        run "cp -R '${old_copy}' '${staged}'"
        FROM="the copy taken before install"
      else
        say "  ! $(basename "${cur}") has nothing to restore from (neither authoritative nor a copy) — **the symlink is kept**"
        RESTORE_OK=0
        continue
      fi
      # ② Verify. **Confirm the content before swapping.**
      if [ "${DRY_RUN}" = 0 ]; then
        if [ -d "${staged}" ]; then
          n_src="$(find "${src}" -type f 2>/dev/null | wc -l | tr -d ' ')"
          n_dst="$(find "${staged}" -type f 2>/dev/null | wc -l | tr -d ' ')"
          if [ "${n_src}" != "${n_dst}" ]; then
            say "  ! $(basename "${cur}")'s copy is incomplete (${n_src} → ${n_dst}) — **aborting**"
            rm -rf "${staged}"
            RESTORE_OK=0
            continue
          fi
        fi
        sync 2>/dev/null || true
      fi
      # ③④ Swap atomically, and only then remove the symlink
      run "rm -f '${cur}'"
      run "mv '${staged}' '${cur}'"
      say "② materialised $(basename "${cur}") from ${FROM}"
      [ -e "${old_copy}" ] && say "  (the copy from before install: ${old_copy} — look at it, then remove it)"
    done
    say "③ replaced the symlinks with real content"
    # ④ Restore the ownership. **After writing back** — restoring first leaves the writer unable to
    # write.
    if [ -n "$OWNER" ]; then
      run "chown -R '$OWNER' '$ROOTP/.orgforge'"
      run "chmod -R u+rwX '$ROOTP/.orgforge'"
      [ -e "$ROOTP/ledger-schema.yaml" ] && run "chown '$OWNER' '$ROOTP/ledger-schema.yaml'"
      say "④ restored the ownership to $OWNER"
    else
      say "④ **there is no record of the original owner** — restore it by hand: chown -R \$(whoami) '$ROOTP/.orgforge'"
    fi
  fi

  # ⑤ Remove only what belongs to this org. **Shared items stay while another org remains.**
  # **Where the restore did not succeed, neither the authoritative data nor the backup is removed.**
  # Removing them loses the only copy (a path raised by measurement). It stops in a state that can be
  # re-run.
  if [ -z "$ROOTP" ] || [ ! -d "$ROOTP" ]; then
    say "! the org root cannot be found: ${ROOTP:-(nothing recorded)}"
    say "  it was moved or deleted. **Data that exists only on the authoritative side is not removed.**"
  fi
  if [ "${RESTORE_OK}" = 0 ]; then
    run "rm -rf '${SOCK_PARENT}'"
    say "⑤ removed the socket only. **The authoritative data and the backup are kept** — the restore did not succeed."
    say "  content: ${AUTHORITATIVE}"
    say "  copy:    ${BACKUP_DIR}"
    say "  find the cause, then run the same command again (this uninstall is idempotent)."
    echo
    echo "✗ the uninstall did not complete. **No data was removed.**"
    exit 1
  fi
  run "rm -rf '${SOCK_PARENT}' '${AUTHORITATIVE}' '${BACKUP_DIR}' '${CONFIG}'"
  say "⑤ removed this org's (${ORG_NAME}) socket, authoritative data, backup, and configuration"
  REMAINING="$(ls -1 /usr/local/var/orgforge/orgs 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${REMAINING}" = "0" ]; then
    run "rm -rf '${INSTALL_DIR}'"
    say "  no other org remains, so the shared code was removed too"
    if id -u "${SERVICE_USER}" >/dev/null 2>&1; then
      run "sysadminctl -deleteUser '${SERVICE_USER}' 2>/dev/null || dscl . -delete '/Users/${SERVICE_USER}'"
      say "  removed the service user ${SERVICE_USER}"
    fi
  else
    say "  **${REMAINING} other org(s) remain, so the shared code and the service UID are kept**"
  fi
  say "**the keys were not removed** (the authoritative side was written back to the org), because otherwise a judgment's receipt could no longer be verified."
  echo
  echo "✓ uninstall complete. workload_isolation returns to process_mediated."
  exit 0
fi

# ── the service user ────────────────────────────────────────────────────────
echo
echo "── the service user"
if id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  say "${SERVICE_USER} already exists (uid=$(id -u "${SERVICE_USER}")) — it is not rebuilt"
else
  # Look for a uid below 500 (the macOS convention for role accounts).
  # **The number must be free as both a uid and a gid.** The same number is also used as the
  # PrimaryGroupID, so an existing gid means **the writer's group is shared with someone else**,
  # opening a path to the ledger through group permissions (395-400 were such cases on this
  # machine).
  NEXT_UID=""
  for u in $(seq 300 498); do
    if dscl . -search /Users UniqueID "$u" 2>/dev/null | grep -q .; then continue; fi
    if dscl . -search /Groups PrimaryGroupID "$u" 2>/dev/null | grep -q .; then continue; fi
    NEXT_UID="$u"; break
  done
  [ -n "$NEXT_UID" ] || fail "no number is free as **both** a uid and a gid (300-498)"
  say "using uid=$NEXT_UID"
  run "dscl . -create '/Groups/${SERVICE_GROUP}'"
  run "dscl . -create '/Groups/${SERVICE_GROUP}' PrimaryGroupID '$NEXT_UID'"
  run "dscl . -create '/Users/${SERVICE_USER}'"
  run "dscl . -create '/Users/${SERVICE_USER}' UserShell /usr/bin/false"
  run "dscl . -create '/Users/${SERVICE_USER}' RealName 'orgforge ledger writer'"
  run "dscl . -create '/Users/${SERVICE_USER}' UniqueID '$NEXT_UID'"
  run "dscl . -create '/Users/${SERVICE_USER}' PrimaryGroupID '$NEXT_UID'"
  run "dscl . -create '/Users/${SERVICE_USER}' NFSHomeDirectory /var/empty"
  run "dscl . -create '/Users/${SERVICE_USER}' IsHidden 1"
  say "created (no login, no home)"
fi

# ── the daemon's copy (root-owned, unreplaceable by a caller) ───────────────
echo
echo "── moving the daemon to a root-owned location"
# **Do not create tools/tools on a re-run.** `cp -R src dst/src` copies into dst/src where it already
# exists (raised by measurement). It is removed before each install.
run "rm -rf '${INSTALL_DIR}/tools' '${INSTALL_DIR}/template'"
run "mkdir -p '${INSTALL_DIR}'"
run "mkdir -p '${INSTALL_DIR}/tools' '${INSTALL_DIR}/template'"
run "cp -R '$PLUGIN_DIR/tools/.' '${INSTALL_DIR}/tools/'"
run "cp -R '$PLUGIN_DIR/template/.' '${INSTALL_DIR}/template/'"
run "chown -R root:wheel '${INSTALL_DIR}'"
run "chmod -R go-w '${INSTALL_DIR}'"
say "${INSTALL_DIR} (root-owned, unwritable by others)"
say "**a caller cannot rewrite this** — it blocks replacing writerd itself"

# ── the socket's parent directory (root-owned) ──────────────────────────────
echo
echo "── the socket's parent directory"
run "mkdir -p '${SOCK_PARENT}'"
# **Separate the anchor from the leaf.**
#
#   anchor: root-owned 0755. **A caller cannot write here**, so the leaf cannot be replaced
#           wholesale.
#   leaf:   writer-owned 0755. **The daemon creates the socket here** (bind needs write permission on
#           the parent).
#
# Measured (in an audit): **the daemon itself cannot bind** under a root-owned 0755 parent
# (Permission denied).
# Neither 0755 nor 1770 works — under the first the daemon cannot create it, and the second writerd
# refuses.
# From the caller's side the guarantee is "**the anchor cannot be written to, so the leaf cannot be
# replaced**".
#
# A stronger shape is launchd's socket activation (launchd creates the socket first and hands the FD
# to the daemon), where not even the leaf need be writer-owned. The anchor/leaf approach is taken here
# for portability.
run "chown root:wheel '${SOCK_ANCHOR}'"
run "chmod 0755 '${SOCK_ANCHOR}'"
run "mkdir -p '${SOCK_PARENT}'"
run "chown '${SERVICE_USER}:${SERVICE_GROUP}' '${SOCK_PARENT}'"
run "chmod 0755 '${SOCK_PARENT}'"
say "${SOCK_ANCHOR} (root-owned 0755 — **a caller cannot write here**)"
say "${SOCK_PARENT} (${SERVICE_USER}-owned 0755 — the daemon can create the socket; a caller cannot write)"
say "**a caller cannot replace the parent directory** — it blocks being routed to a fake socket"

# ── the configuration (root-owned; a caller cannot state the ledger path) ───
echo
echo "── the configuration"
run "mkdir -p '$(dirname "${CONFIG}")'"
if [ "$DRY_RUN" = 1 ]; then
  printf '  [dry-run] write org=%s into %s\n' "${ORG_ROOT}/.orgforge/ledger" "${CONFIG}"
else
  printf 'org=default=%s\n' "${AUTHORITATIVE}/ledger" > "${CONFIG}"
  chown root:wheel "${CONFIG}"; chmod 644 "${CONFIG}"
fi
say "${CONFIG} (root-owned) — **the write target is decided here. An RPC cannot state it**"

# ── making the ledger, keys, and schema writer-owned ────────────────────────
echo
echo "── the assets the writer should own"
run "mkdir -p '${BACKUP_DIR}'"
# **Do not overwrite on a re-install.** On a second run the owner is already the writer, and
# recording that as "the original owner" makes uninstall "restore" it to the service UID (raised by
# measurement). It is written on the first run only.
if [ "$DRY_RUN" = 0 ]; then
  if [ -f "${BACKUP_DIR}/original-owner" ]; then
    say "the original owner is already recorded ($(cat "${BACKUP_DIR}/original-owner")) — it is not overwritten"
  elif [ "$(printf '%s' "${ORIG_OWNER}" | cut -d: -f1)" = "${SERVICE_USER}" ]; then
    fail "$(cat <<EOF2
the ledger is already owned by ${SERVICE_USER}, but there is no record of the original owner.
  Proceeding makes uninstall "restore" it to ${SERVICE_USER}, and it can never go back to the caller.
  Record it by hand and run this again:
    echo '<the original owner:group>' | sudo tee ${BACKUP_DIR}/original-owner
    echo '${ORG_ROOT}' | sudo tee ${BACKUP_DIR}/original-org-root
EOF2
)"
  else
    printf '%s\n' "${ORIG_OWNER}" > "${BACKUP_DIR}/original-owner"
    printf '%s\n' "${ORG_ROOT}"   > "${BACKUP_DIR}/original-org-root"
    chmod 600 "${BACKUP_DIR}"/original-*
    say "recorded the original owner in ${BACKUP_DIR} (for rollback. **Not overwritten on a re-install**)"
  fi
fi
# **Set the keys aside first**, since changing the owner can make them unreadable.
if [ -d "${ORG_ROOT}/.orgforge/trust" ]; then
  run "cp -R '${ORG_ROOT}/.orgforge/trust' '${BACKUP_DIR}/trust-backup'"
  run "chmod -R go-rwx '${BACKUP_DIR}/trust-backup'"
  say "set the key registry aside: ${BACKUP_DIR}/trust-backup"
fi
# **Unwritable, but readable.** At 700 the caller's `ledger verify`, board, and projection all fail
# (raised by measurement). The control is "it cannot be written to", not "it cannot be seen" — a
# ledger that cannot be audited is not a ledger for auditing.
# **The org tree itself is caller-owned, so anything inside it can be replaced path and all.**
# Measured (in an audit): with .orgforge and the org root still caller-owned, the writer-owned
# ledger/trust and the root-owned schema could be replaced **directory and all**. Tightening the
# permissions on the contents means nothing if the container can be replaced.
#
# So **the authoritative data lives outside the org tree, and the org tree points at it with a
# symlink**. The real content sits under a root-owned directory, where a caller cannot write.
# Even where the symlink is repointed, writerd starts with **the real path** fixed via `--org`, so
# the write target does not move (a reader can still be deceived — that is handled in the next
# stage).
run "mkdir -p '${AUTHORITATIVE}/ledger' '${AUTHORITATIVE}/trust'"
run "chown root:wheel '${AUTHORITATIVE}'"
run "chmod 0755 '${AUTHORITATIVE}'"
if [ -d "${ORG_ROOT}/.orgforge/ledger" ] && [ ! -L "${ORG_ROOT}/.orgforge/ledger" ]; then
  run "cp -R '${ORG_ROOT}/.orgforge/ledger/.' '${AUTHORITATIVE}/ledger/'"
  run "mv '${ORG_ROOT}/.orgforge/ledger' '${ORG_ROOT}/.orgforge/ledger.pre-writer'"
  run "ln -s '${AUTHORITATIVE}/ledger' '${ORG_ROOT}/.orgforge/ledger'"
  say "moved the ledger to ${AUTHORITATIVE}/ledger; the org points at it with a symlink"
  say "  (the original stays at ${ORG_ROOT}/.orgforge/ledger.pre-writer — **it is not removed**)"
fi
if [ -d "${ORG_ROOT}/.orgforge/trust" ] && [ ! -L "${ORG_ROOT}/.orgforge/trust" ]; then
  run "cp -R '${ORG_ROOT}/.orgforge/trust/.' '${AUTHORITATIVE}/trust/'"
  run "mv '${ORG_ROOT}/.orgforge/trust' '${ORG_ROOT}/.orgforge/trust.pre-writer'"
  run "ln -s '${AUTHORITATIVE}/trust' '${ORG_ROOT}/.orgforge/trust'"
  say "moved the key registry to ${AUTHORITATIVE}/trust"
fi
# **Fix the constitution root-owned.**
# It holds the declarations (require_attested_identity and the like). Left somewhere a caller can
# write, the caller can rewrite a declaration to false and erase the enforcement — **whoever is
# checked must not be able to write the check's input.**
# The daemon also runs outside the org, so it must not be made to search from the cwd (measured: the
# derivation failed and an unauthenticated admission passed). So it is copied and the path passed
# explicitly.
if [ -f "${ORG_ROOT}/constitution.yaml" ] && [ ! -L "${ORG_ROOT}/constitution.yaml" ]; then
  run "cp '${ORG_ROOT}/constitution.yaml' '${AUTHORITATIVE}/constitution.yaml'"
  run "chown root:wheel '${AUTHORITATIVE}/constitution.yaml'"
  run "chmod 0644 '${AUTHORITATIVE}/constitution.yaml'"
  # **A copy goes stale.** The org side stays editable by the caller (a human reads the declarations
  # too). But an edit does not reach the daemon — if it did, the caller could erase the enforcement.
  # So that "I edited it and nothing happened" never happens silently, **the divergence is made
  # visible**.
  say "  fixed the constitution root-owned: ${AUTHORITATIVE}/constitution.yaml"
  say "  **Editing the org side (${ORG_ROOT}/constitution.yaml) does not reach the daemon.**"
  say "  After changing a declaration, run this installer again to fix it anew."
  say "  writerd warns about the divergence at startup."
elif [ ! -f "${AUTHORITATIVE}/constitution.yaml" ]; then
  fail "no constitution.yaml: ${ORG_ROOT}/constitution.yaml
  **Do not run the writer with no declarations.** require_attested_identity would not reach the child
  process and an unauthenticated admission would pass (a path raised by measurement)."
fi

if [ -f "${ORG_ROOT}/ledger-schema.yaml" ] && [ ! -L "${ORG_ROOT}/ledger-schema.yaml" ]; then
  run "cp '${ORG_ROOT}/ledger-schema.yaml' '${AUTHORITATIVE}/ledger-schema.yaml'"
  run "chown root:wheel '${AUTHORITATIVE}/ledger-schema.yaml'"
  run "chmod 0644 '${AUTHORITATIVE}/ledger-schema.yaml'"
  run "mv '${ORG_ROOT}/ledger-schema.yaml' '${ORG_ROOT}/ledger-schema.yaml.pre-writer'"
  run "ln -s '${AUTHORITATIVE}/ledger-schema.yaml' '${ORG_ROOT}/ledger-schema.yaml'"
  say "moved the schema to ${AUTHORITATIVE} (the daemon receives the real path via --schema)"
fi
run "chown -R '${SERVICE_USER}:${CALLER_GROUP}' '${AUTHORITATIVE}/ledger'"
run "chmod 750 '${AUTHORITATIVE}/ledger'"
run "find '${AUTHORITATIVE}/ledger' -type f -exec chmod 640 {} +"
say "made the ledger ${SERVICE_USER}-owned at 750/640 (group=${CALLER_GROUP})"
say "  → **a caller can read but not write** (verify / board / projection still work)"
if [ -d "${AUTHORITATIVE}/trust" ]; then
  run "chown -R root:${SERVICE_GROUP} '${AUTHORITATIVE}/trust'"
  run "chmod 750 '${AUTHORITATIVE}/trust'"
  run "chmod 640 '${AUTHORITATIVE}/trust/keys.json' 2>/dev/null || true"
  say "made the key registry root-owned and group-readable → **a caller cannot replace a public key**"
fi


# ── LaunchDaemon ────────────────────────────────────────────────────────────
echo
echo "── LaunchDaemon"
if [ "$DRY_RUN" = 1 ]; then
  printf '  [dry-run] write %s and launchctl bootout/bootstrap\n' "${PLIST}"
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
    <!-- **Pass the real path.** Repointing the org tree's symlink does not move the write target. -->
    <string>--org</string><string>default=${AUTHORITATIVE}/ledger</string>
    <string>--socket</string><string>${SOCK_PARENT}/writer.sock</string>
    <!-- **Fix the schema.** Without it ledger.py searches for the org from the cwd and falls back to
         the plugin's template when it finds none — so validation happens under the template's rules
         rather than the rules the org changed (raised by measurement). -->
    <string>--schema</string><string>${AUTHORITATIVE}/ledger-schema.yaml</string>
    <!-- **Fix the declarations.** The daemon runs outside the org, so the org root cannot be derived
         from the ledger path (measured: the derivation failed and an unauthenticated admission
         passed). -->
    <string>--constitution</string><string>default=${AUTHORITATIVE}/constitution.yaml</string>
    <!-- **Fix the trust store.** The installer moves trust to ${AUTHORITATIVE} and renames the org
         side to .pre-writer. Without passing it here the daemon (cwd=/) cannot find the key registry
         and **refuses even correctly signed receipts** (raised by measurement). -->
    <string>--trust</string><string>default=${AUTHORITATIVE}/trust/keys.json</string>
    <!-- **Wire in the caller UID.** The socket is 0666, so anyone can connect — connecting and
         writing are different things. -->
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
say "${PLIST} (root-owned) — **a caller cannot rewrite the plist**"
say "it starts with --require-root-owned (writerd refuses unless the socket's parent is root-owned)"

# ── what to do next ─────────────────────────────────────────────────────────
echo
echo "✓ install complete (--dry-run changed nothing)"
cat <<NEXT

  What to do next:

    1. run the verification (**confirm by measurement, not by this script's own word**):
         tools/writer-verify.sh --org-root '${ORG_ROOT}'

    2. tell the org about the socket:
         export ORG_WRITER_SOCKET=${SOCK_PARENT}/writer.sock

    3. to put it back:
         sudo $0 --uninstall

  **The extent of the guarantee:** a normal agent / caller UID cannot modify the writer's assets
  (the ledger, keys, schema, and latch). **The host's administrator (root) is outside the threat
  model** — they can stop the daemon and restore the ownership. That is not a limitation but the
  definition of the boundary.
NEXT
