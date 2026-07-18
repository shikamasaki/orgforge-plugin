#!/usr/bin/env bash
# scheduler-uninstall.sh — remove the org's cron entries installed by scheduler-install.sh.
# Usage: scheduler-uninstall.sh --role <role>   (or ORG_ROLE)
set -euo pipefail
ROLE=""
while [ $# -gt 0 ]; do case "$1" in --role) ROLE="$2"; shift 2;; *) shift;; esac; done
ROLE="${ROLE:-${ORG_ROLE:-}}"
if [ -z "$ROLE" ]; then echo "error: --role (or ORG_ROLE) is required" >&2; exit 2; fi
TAG="# orgforge:${ROLE}"
REMAINING="$(crontab -l 2>/dev/null | grep -v "${TAG}" || true)"
printf '%s\n' "$REMAINING" | grep -v '^$' | crontab - || crontab -r 2>/dev/null || true
echo "✔ removed orgforge cron entries for role '${ROLE}'"
