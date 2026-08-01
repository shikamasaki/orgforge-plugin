#!/usr/bin/env bash
# build.sh — sync the neutral core into the Claude Code plugin so it is self-contained.
#
# A Claude Code plugin must reference only files under ${CLAUDE_PLUGIN_ROOT} — external paths are
# not copied to the install cache (verified against code.claude.com/docs/en/plugins-reference).
# So the plugin BUNDLES the organ tools + the shared hook adapters + the schedule/sensors it reads.
# Those are COPIES of the neutral source, and copies drift. This script regenerates them from the
# single source of truth (tools/, integrations/common/, template/), and `--check` fails if the
# bundle is stale — wire it in CI so a drifted plugin is caught, not shipped (the repo's own
# "described but not enforced" discipline, applied to itself).
#
#   integrations/claude-code/build.sh          # regenerate the bundle
#   integrations/claude-code/build.sh --check   # exit 1 if the bundle differs from source (CI gate)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
CHECK="${1:-}"

# (source -> bundled dest) pairs. Keep this list in sync with what the hooks/commands reference.
sync_one() {  # $1 = src file, $2 = dest file
  local src="$1" dest="$2"
  if [ "$CHECK" = "--check" ]; then
    if ! diff -q "$src" "$dest" >/dev/null 2>&1; then
      echo "STALE: $dest differs from $src — run integrations/claude-code/build.sh" >&2
      return 1
    fi
  else
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
  fi
}

rc=0
# the shared hook adapters (source of truth: integrations/common/)
for f in org_hook.py org_session_start.py tick_host.py; do
  sync_one "$REPO/integrations/common/$f" "$HERE/scripts/$f" || rc=1
done
# the organ tools (source of truth: tools/)
for f in "$REPO"/tools/*.py; do
  sync_one "$f" "$HERE/tools/$(basename "$f")" || rc=1
done
# サブパッケージ（tools/orgcycle/ など）も同期する。`tools/*.py` だけを見ていると
# 分割したモジュールがバンドルに入らず、プラグインとして入れた瞬間に ImportError で死ぬ。
for d in "$REPO"/tools/*/; do
  [ -f "${d}__init__.py" ] || continue
  name="$(basename "$d")"
  mkdir -p "$HERE/tools/$name"
  for f in "$d"*.py; do
    sync_one "$f" "$HERE/tools/$name/$(basename "$f")" || rc=1
  done
done
# the data files the org commands read (source of truth: template/): schedule/sensors/constitution
# for /org-tick and /org-mandate; moves + ledger-schema + the SKELETON for /org-found's lint + draft;
# SPEC.md for /org-decompose's Issue bodies; role-settings.yaml for /org-init's scaffold;
# REQUIREMENTS.md for /org-found's requirements template (docs/11 §0b).
for f in schedule.yaml sensors.yaml constitution.yaml moves.yaml ledger-schema.yaml \
         organization.SKELETON.yaml SPEC.md role-settings.yaml REQUIREMENTS.md; do
  sync_one "$REPO/template/$f" "$HERE/template/$f" || rc=1
done

if [ "$CHECK" = "--check" ]; then
  [ $rc -eq 0 ] && echo "plugin bundle is in sync with the neutral source" || \
    echo "plugin bundle is STALE — regenerate with integrations/claude-code/build.sh" >&2
  exit $rc
fi
echo "plugin bundle regenerated from tools/, integrations/common/, template/"
