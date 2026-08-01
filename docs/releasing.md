# Releasing the plugins

The GitHub repository is the marketplace source. A merge to `main` therefore publishes the tested
source to Claude Code immediately. The `Publish plugins` workflow also creates an immutable GitHub
Release with self-contained Claude Code and Codex archives after the `CI` workflow succeeds.

## Release contract

Before merging a plugin change:

1. Set `integrations/claude-code/.claude-plugin/plugin.json` to the intended semantic version.
2. Give `integrations/codex/.codex-plugin/plugin.json` the same base version plus one
   `+codex.<cachebuster>` suffix.
3. Regenerate both projections and run the local release checks:

   ```bash
   integrations/claude-code/build.sh
   integrations/codex/build.sh
   python3 tools/release_check.py
   python3 -m pytest tests -q
   ```

Pull requests and `main` run the complete test suite on Ubuntu and macOS. Publication receives write
permission only in the separate `workflow_run` workflow, only for a successful push to `main`, and
checks out the exact SHA that passed CI.

The release tag is `v<Claude version>`. If publishable plugin content changes while that tag already
exists, publication fails instead of silently replacing an immutable release; bump the version and
merge again. A merge that changes no publishable plugin content safely reuses the existing release.

Each new release contains:

- `orgforge-claude-code-<version>.tar.gz`
- `orgforge-codex-<version>.tar.gz`
- `SHA256SUMS`
- GitHub artifact provenance attestations for both archives

`SHA256SUMS` uses archive basenames, so it can be checked directly in the directory produced by
`gh release download` with `shasum -a 256 -c SHA256SUMS`.
