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
#   integrations/claude-code/scheduler-install.sh --role <role> \
#       [--cycles tick,work,discover] [--tick-min 30] [--work-min 60] \
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
ROLE=""; CYCLES="tick,work,discover"; TICK_MIN=30; WORK_MIN=60
DISCOVER_HOURS=24; WORKDIR="$PWD"; DRY_RUN=0

die() {
  echo "error: $*" >&2
  exit 2
}

need_arg() {
  [ "$1" -ge 2 ] || die "$2 requires a value"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --role) need_arg "$#" "$1"; ROLE="$2"; shift 2;;
    --cycles) need_arg "$#" "$1"; CYCLES="$2"; shift 2;;
    --tick-min) need_arg "$#" "$1"; TICK_MIN="$2"; shift 2;;
    --work-min) need_arg "$#" "$1"; WORK_MIN="$2"; shift 2;;
    --discover-hours) need_arg "$#" "$1"; DISCOVER_HOURS="$2"; shift 2;;
    --workdir) need_arg "$#" "$1"; WORKDIR="$2"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    *) die "unknown arg: $1";;
  esac
done

ROLE="${ROLE:-${ORG_ROLE:-}}"
if [ -z "$ROLE" ]; then die "--role (or ORG_ROLE) is required"; fi
[[ "$ROLE" =~ ^[A-Za-z0-9._-]+$ ]] ||
  die "role must contain only letters, digits, dot, underscore, or hyphen"
if [ -z "${ORG_LEDGER_ROOT:-}" ]; then
  die "ORG_LEDGER_ROOT is not set — export it (or your .claude/settings.json env) first"
fi

# A cron entry is one physical line. Reject values that could split it before quoting anything.
for path_value in "$WORKDIR" "$ORG_LEDGER_ROOT" "${ORG_DOCTRINE_ROOT:-}" \
                  "${ORG_CONVENTIONS_ROOT:-}" "$PLUGIN_DIR"; do
  case "$path_value" in
    *$'\n'*|*$'\r'*) die "workdir and ORG_* paths must not contain newlines";;
  esac
done

# Parse a portable comma-list without associative arrays (macOS still ships Bash 3.2).
SELECTED=","
case "$CYCLES" in
  ""|,*|*,|*,,*) die "cycles must not contain an empty item";;
esac
IFS=',' read -r -a REQUESTED_CYCLES <<< "$CYCLES"
[ "${#REQUESTED_CYCLES[@]}" -gt 0 ] || die "cycles must select at least one of: tick,work,discover"
for cycle in "${REQUESTED_CYCLES[@]}"; do
  case "$cycle" in
    tick|work|discover) ;;
    "") die "cycles must not contain an empty item";;
    *) die "unknown cycles item '$cycle' (expected tick,work,discover)";;
  esac
  [[ "$SELECTED" != *",${cycle},"* ]] || die "cycles contains duplicate '$cycle'"
  SELECTED="${SELECTED}${cycle},"
done

has_cycle() {
  [[ "$SELECTED" == *",$1,"* ]]
}

CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ]; then die "'claude' not found on PATH"; fi

# Quote one value for the shell command embedded in crontab. Cron treats '%' specially even inside
# shell quotes, so escape it after producing the POSIX single-quoted shell word.
cron_quote() {
  local quoted
  # Bash 3.2 (the system Bash on macOS) produces a malformed word for the compact parameter-
  # expansion form of this replacement. Build the POSIX 'foo'\''bar' spelling with sed instead,
  # then protect '%' from cron after the shell word is complete.
  quoted="'$(printf '%s' "$1" | sed "s/'/'\\\\''/g")'"
  printf '%s' "$quoted" | sed 's/%/\\%/g'
}

# env the headless runs need. cron has a bare environment, so we inline the ORG_* vars into each line.
ENV_PREFIX="ORG_LEDGER_ROOT=$(cron_quote "$ORG_LEDGER_ROOT") ORG_ROLE=$(cron_quote "$ROLE")"
[ -n "${ORG_DOCTRINE_ROOT:-}" ]    && ENV_PREFIX="$ENV_PREFIX ORG_DOCTRINE_ROOT=$(cron_quote "$ORG_DOCTRINE_ROOT")"
[ -n "${ORG_CONVENTIONS_ROOT:-}" ] && ENV_PREFIX="$ENV_PREFIX ORG_CONVENTIONS_ROOT=$(cron_quote "$ORG_CONVENTIONS_ROOT")"

# one headless invocation of a slash-command, plugin attached so hooks + injection fire.
run_cmd() {  # $1 = slash command text
  echo "cd $(cron_quote "$WORKDIR") && ${ENV_PREFIX} $(cron_quote "$CLAUDE_BIN") -p $(cron_quote "$1") --plugin-dir $(cron_quote "$PLUGIN_DIR") --output-format json >> $(cron_quote "${ORG_LEDGER_ROOT}/cron.log") 2>&1"
}

# Emit only exact wall-clock cadences. Expressions such as */90 in the minute field are invalid;
# */45 is syntactically valid but creates alternating 45/15-minute gaps, not "every 45 minutes".
minute_cron() {  # $1 = interval in minutes, $2 = cycle name
  local m="$1" name="$2" h
  [[ "$m" =~ ^[1-9][0-9]*$ ]] || { echo "error: ${name} interval must be a positive base-10 integer in minutes" >&2; return 2; }
  if [ "$m" -ge 1 ] && [ "$m" -lt 60 ] && [ $((60 % m)) -eq 0 ]; then
    echo "*/${m} * * * *"
  elif [ "$m" -eq 1440 ]; then
    echo "0 0 * * *"
  elif [ "$m" -ge 60 ] && [ "$m" -lt 1440 ] && [ $((m % 60)) -eq 0 ]; then
    h=$((m / 60))
    [ $((24 % h)) -eq 0 ] || {
      echo "error: ${name} interval ${m}m is not exactly representable by wall-clock cron" >&2
      return 2
    }
    echo "0 */${h} * * *"
  else
    echo "error: ${name} interval ${m}m is not exactly representable by wall-clock cron" >&2
    return 2
  fi
}

hour_cron() {  # $1 = interval in hours, $2 = cycle name
  local h="$1" name="$2"
  [[ "$h" =~ ^[1-9][0-9]*$ ]] || { echo "error: ${name} interval must be a positive base-10 integer in hours" >&2; return 2; }
  if [ "$h" -ge 1 ] && [ "$h" -lt 24 ] && [ $((24 % h)) -eq 0 ]; then
    echo "0 */${h} * * *"
  elif [ "$h" -eq 24 ]; then
    echo "0 0 * * *"
  else
    echo "error: ${name} interval ${h}h is not exactly representable by wall-clock cron" >&2
    return 2
  fi
}

TAG="# orgforge:${ROLE}"
LINES=()
if has_cycle tick; then
  TICK_CRON="$(minute_cron "$TICK_MIN" tick)"
  LINES+=("${TICK_CRON}  $(run_cmd "/org-tick")  ${TAG}")
fi
if has_cycle work; then
  WORK_CRON="$(minute_cron "$WORK_MIN" work)"
  LINES+=("${WORK_CRON}  $(run_cmd "/org-work ${ROLE}")  ${TAG}")
fi
if has_cycle discover; then
  DISCOVER_CRON="$(hour_cron "$DISCOVER_HOURS" discover)"
  LINES+=("${DISCOVER_CRON}  $(run_cmd "/org-discover ${ROLE}")  ${TAG}")
fi

echo "== orgforge scheduler entries for role '${ROLE}' (cycles: ${CYCLES}) =="
printf '%s\n' "${LINES[@]}"
echo

if [ "$DRY_RUN" = "1" ]; then
  echo "(dry run — nothing installed. Re-run without --dry-run to install.)"
  exit 0
fi

# merge: drop any prior lines for this role's tag, then append the new ones.
EXISTING="$(crontab -l 2>/dev/null | awk -v tag="${TAG}" \
  'length($0) < length(tag) || substr($0, length($0) - length(tag) + 1) != tag' || true)"
{
  [ -z "$EXISTING" ] || printf '%s\n' "$EXISTING"
  printf '%s\n' "${LINES[@]}"
} | crontab -
echo "✔ installed. Verify with: crontab -l | grep '${TAG}'"
echo "  Logs stream to: ${ORG_LEDGER_ROOT}/cron.log"
echo "  Remove with:    integrations/claude-code/scheduler-uninstall.sh --role ${ROLE}"
