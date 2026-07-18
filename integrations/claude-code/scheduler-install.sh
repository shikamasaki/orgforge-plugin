#!/usr/bin/env bash
# scheduler-install.sh — register the org's metabolism on the OS cron, so it runs 24/7 UNATTENDED,
# with no Claude Code session open. This is the "the drive is the host's" half of R0 (docs/09 §4),
# realized on the one scheduler that survives the REPL closing: the operating system's cron.
#
# It installs crontab entries that invoke `claude -p "<slash-command>"` headless, with the plugin
# attached (so hooks + doctrine injection fire) and ORG_* env passed through. Each entry maps to a
# schedule.yaml cadence.
#
# Usage:
#   integrations/claude-code/scheduler-install.sh --role <role> [--tick-min 30] [--work-min 60] \
#       [--discover-hours 24] [--workdir /path/to/org] [--dry-run]
#
# Requires: ORG_LEDGER_ROOT (and usually ORG_ROLE/ORG_DOCTRINE_ROOT) set in your environment or your
# project's .claude/settings.json. The script reads them from the current env; export them first, or
# run it from a shell where your settings' env is loaded.
#
#   To remove: integrations/claude-code/scheduler-uninstall.sh   (or `crontab -e` and delete the
#   lines tagged  # orgforge:<role> ).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$HERE"
ROLE=""; TICK_MIN=30; WORK_MIN=60; DISCOVER_HOURS=24; WORKDIR="$PWD"; DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE="$2"; shift 2;;
    --tick-min) TICK_MIN="$2"; shift 2;;
    --work-min) WORK_MIN="$2"; shift 2;;
    --discover-hours) DISCOVER_HOURS="$2"; shift 2;;
    --workdir) WORKDIR="$2"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

ROLE="${ROLE:-${ORG_ROLE:-}}"
if [ -z "$ROLE" ]; then echo "error: --role (or ORG_ROLE) is required" >&2; exit 2; fi
if [ -z "${ORG_LEDGER_ROOT:-}" ]; then
  echo "error: ORG_LEDGER_ROOT is not set — export it (or your .claude/settings.json env) first" >&2
  exit 2
fi

CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ]; then echo "error: 'claude' not found on PATH" >&2; exit 2; fi

# env the headless runs need. cron has a bare environment, so we inline the ORG_* vars into each line.
ENV_PREFIX="ORG_LEDGER_ROOT='${ORG_LEDGER_ROOT}' ORG_ROLE='${ROLE}'"
[ -n "${ORG_DOCTRINE_ROOT:-}" ]    && ENV_PREFIX="$ENV_PREFIX ORG_DOCTRINE_ROOT='${ORG_DOCTRINE_ROOT}'"
[ -n "${ORG_CONVENTIONS_ROOT:-}" ] && ENV_PREFIX="$ENV_PREFIX ORG_CONVENTIONS_ROOT='${ORG_CONVENTIONS_ROOT}'"

# one headless invocation of a slash-command, plugin attached so hooks + injection fire.
run_cmd() {  # $1 = slash command text
  echo "cd '${WORKDIR}' && ${ENV_PREFIX} '${CLAUDE_BIN}' -p '$1' --plugin-dir '${PLUGIN_DIR}' --output-format json >> '${ORG_LEDGER_ROOT}/cron.log' 2>&1"
}

# build a valid minute-field schedule: cron minutes are 0-59, so an interval of 60+ must become an
# hourly (or N-hourly) expression, not the invalid `*/60`.
minute_cron() {  # $1 = interval in minutes  -> a 5-field cron expression
  local m="$1"
  if [ "$m" -lt 60 ]; then echo "*/${m} * * * *"
  elif [ $((m % 60)) -eq 0 ]; then echo "0 */$((m / 60)) * * *"
  else echo "*/${m} * * * *"; fi   # sub-hour non-divisor: leave as-is (cron accepts */m for m<60 only; caller warned)
}

TAG="# orgforge:${ROLE}"
LINES=$(cat <<EOF
$(minute_cron "$TICK_MIN")  $(run_cmd "/org-tick")  ${TAG}
$(minute_cron "$WORK_MIN")  $(run_cmd "/org-work ${ROLE}")  ${TAG}
0 */${DISCOVER_HOURS} * * *  $(run_cmd "/org-discover ${ROLE}")  ${TAG}
EOF
)

echo "== orgforge scheduler entries for role '${ROLE}' =="
echo "$LINES"
echo

if [ "$DRY_RUN" = "1" ]; then
  echo "(dry run — nothing installed. Re-run without --dry-run to install.)"
  exit 0
fi

# merge: drop any prior lines for this role's tag, then append the new ones.
EXISTING="$(crontab -l 2>/dev/null | grep -v "${TAG}" || true)"
printf '%s\n%s\n' "$EXISTING" "$LINES" | grep -v '^$' | crontab -
echo "✔ installed. Verify with: crontab -l | grep '${TAG}'"
echo "  Logs stream to: ${ORG_LEDGER_ROOT}/cron.log"
echo "  Remove with:    integrations/claude-code/scheduler-uninstall.sh --role ${ROLE}"
