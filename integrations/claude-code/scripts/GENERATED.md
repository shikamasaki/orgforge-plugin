# GENERATED — do not hand-edit

These files are COPIES synced from the repo's neutral source by `integrations/claude-code/build.sh`:
- `tools/*.py`  ← `../../../tools/*.py`
- `scripts/org_hook.py`, `scripts/org_session_start.py`  ← `../../common/`
- `template/*.yaml`  ← `../../../template/`

A Claude Code plugin must be self-contained (only `${CLAUDE_PLUGIN_ROOT}` paths survive install),
so the plugin bundles them. Edit the SOURCE, then run `integrations/claude-code/build.sh`.
CI should run `integrations/claude-code/build.sh --check` to fail on drift.
