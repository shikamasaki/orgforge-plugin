---
name: org-adopt
description: Adopt an existing repository into orgforge in one bounded workflow. Use when the user asks to adopt, initialize, onboard, or govern an existing codebase with orgforge. Prepare local state, derive a minimal organization from real code boundaries, record remaining work and the current baseline, and verify readiness without sudo, daemons, branches, Issues, or network access.
---

# Adopt an existing repository

Complete adoption in the current turn. Do not ask the user to run a second setup command.

## Boundaries

- Use the current repository only after confirming it is the intended target.
- Never adopt the orgforge plugin development repository itself.
- Do not use sudo, install a daemon, create a branch or Issue, access the network, or configure keys.
- Preserve existing files. `adopt.py prepare` is idempotent and does not overwrite them.
- Describe the repository as it exists; do not redesign it during adoption.

## Workflow

1. Inspect:

   ```bash
   python3 "$PLUGIN_ROOT/tools/adopt.py" inspect .
   ```

   Stop if `plugin development repo` is `yes`. For a repository with no commits, explain that
   founding from a brief is a different workflow.

2. Prepare local state, selecting the user's language:

   ```bash
   python3 "$PLUGIN_ROOT/tools/adopt.py" prepare . --language ja
   ```

   Use `en` when the user's working language is English.

   If inspect reports an existing orgforge organization, preserve its ledger and migrate it in
   place before drafting anything:

   ```bash
   python3 "$PLUGIN_ROOT/tools/ledger.py" schema --fix
   python3 "$PLUGIN_ROOT/tools/ledger.py" schema
   python3 "$PLUGIN_ROOT/tools/ledger.py" verify
   ```

   Remove obsolete `defaults.tier: A|B` from `role-settings.yaml`. Give maker roles ordinary
   development capabilities (`read`, `write`, `edit`, `grep`, `run_tests`, `web_read`, `network`),
   keep gate and skeptic read-only, and never grant `deploy`, `secrets`, `asset_movement`,
   `external_publish`, or `production_deploy`. Update Tier A/B containment prose in the constitution
   to state that credentials and irreversible effects remain protected by the host platform. Verify
   that ledger bytes, HEAD, event count, and tip hash did not change; historical
   `legacy_unvalidated` events remain historical rather than being rewritten.

3. Read the README, dependency manifests, real directories, tests, and recent commits.

4. Write:
   - `ARCHITECTURE.md` as a description of the current implementation;
   - `organization.yaml` as the smallest useful chart derived from real ownership boundaries;
   - `coverage-manifest.md` containing only missing, partial, or untested work.

   Keep the control roles required by `organization.SKELETON.yaml`. Prefer one or two domain maker
   roles over an elaborate simulated company.

5. Validate the chart:

   ```bash
   python3 "$PLUGIN_ROOT/tools/org_lint.py" \
     organization.yaml constitution.yaml moves.yaml ledger-schema.yaml sensors.yaml role-settings.yaml
   ```

6. Record the existing mechanical-debt baseline:

   ```bash
   python3 "$PLUGIN_ROOT/tools/repro_lint.py" baseline .
   ```

7. Present one concise accept/revise checkpoint: current architecture, minimal role boundaries,
   baseline debt, remaining-work count, and what orgforge will and will not guarantee. Apply requested
   revisions in this same workflow.

8. Finish with:

   ```bash
   python3 "$PLUGIN_ROOT/tools/adopt.py" doctor .
   ```

   Do not report completion until it prints `READY`.

## Completion report

Return:

- `ADOPTED`;
- elapsed setup time;
- files created;
- enabled: workflow order, maker/checker separation, evidence ledger, human-held irreversible actions;
- not enabled: hostile-process containment, credential isolation, immutable storage;
- that the user can now request normal work directly.

GitHub Issue decomposition is optional and not part of adoption readiness.
