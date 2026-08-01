#!/usr/bin/env bash
# build.sh — sync the neutral core into the Codex plugin so it is SELF-CONTAINED.
#
# A plugin that references the checkout it was built from is not a plugin: enforcement then depends
# on a tree the plugin does not own, and on that tree still being where it was. The previous Codex
# projection did exactly that (`${CODEX_PROJECT_ROOT}/integrations/common/org_hook.py`), which also
# meant the guardrail vanished if the checkout moved. Everything the hook needs now lives under
# $PLUGIN_ROOT.
#
# Verified 2026-07 against codex-cli 0.146.0:
#   - the injected variable is PLUGIN_ROOT. There is no CODEX_PLUGIN_ROOT (CLAUDE_PLUGIN_ROOT is
#     kept as an alias for Claude Code compatibility).
#   - a marketplace manifest is read from `.agents/plugins/marketplace.json` (NOT from a
#     marketplace.json at the root).
#   - installing a plugin does NOT enable its hooks: an untrusted hook is SILENTLY SKIPPED.
#     Trust is granted in the interactive TUI and stored as a content-bound sha256, so it cannot be
#     seeded by hand and editing a hook can require re-trusting.
#
#   integrations/codex/build.sh           # regenerate the bundle
#   integrations/codex/build.sh --check   # exit 1 if the bundle differs from source (CI gate)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
CHECK="${1:-}"

sync_one() {  # $1 = src file, $2 = dest file
  local src="$1" dest="$2"
  if [ "$CHECK" = "--check" ]; then
    if ! diff -q "$src" "$dest" >/dev/null 2>&1; then
      echo "STALE: $dest differs from $src — run integrations/codex/build.sh" >&2
      return 1
    fi
  else
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
  fi
}

rc=0
# the shared hook adapters (source of truth: integrations/common/)
for f in org_hook.py org_session_start.py; do
  sync_one "$REPO/integrations/common/$f" "$HERE/scripts/$f" || rc=1
done
# the organ tools (source of truth: tools/) — the hook shells out to ledger.py
for f in "$REPO"/tools/*.py; do
  sync_one "$f" "$HERE/tools/$(basename "$f")" || rc=1
done
# サブパッケージ（tools/orgcycle/ など）。`tools/*.py` だけを見ていると取り落とす。
for d in "$REPO"/tools/*/; do
  name="$(basename "$d")"
  [ "$name" = "__pycache__" ] && continue
  mkdir -p "$HERE/tools/$name"
  for f in "$d"*.py; do
    [ -e "$f" ] || continue
    sync_one "$f" "$HERE/tools/$name/$(basename "$f")" || rc=1
  done
done
# the schema/settings the tools read (source of truth: template/)
for f in ledger-schema.yaml constitution.yaml sensors.yaml moves.yaml role-settings.yaml; do
  sync_one "$REPO/template/$f" "$HERE/template/$f" || rc=1
done
# Structured-output contracts used by cross-harness judges.
for f in "$REPO"/template/schemas/*.json; do
  sync_one "$f" "$HERE/template/schemas/$(basename "$f")" || rc=1
done

if [ "$CHECK" = "--check" ]; then
  [ "$rc" = 0 ] && echo "codex plugin bundle is in sync with the neutral source"
  exit "$rc"
fi
echo "codex plugin bundle regenerated from tools/, integrations/common/, template/"
