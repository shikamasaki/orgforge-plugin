#!/usr/bin/env bash
# Host scheduler adapter. The Python implementation owns backend selection, bounded subprocesses,
# readback verification, and receipt-backed smoke tests; this stable shell surface is retained for
# existing documentation and automation.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${ORG_PYTHON_BOOTSTRAP:-python3}" "$HERE/scripts/scheduler.py" install "$@"
