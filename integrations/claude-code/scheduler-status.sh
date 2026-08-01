#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${ORG_PYTHON_BOOTSTRAP:-python3}" "$HERE/scripts/scheduler.py" status "$@"
