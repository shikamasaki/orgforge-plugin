import copy
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import release_check  # noqa: E402


def _release_tree(tmp_path):
    for relative in (
        "integrations/claude-code/.claude-plugin",
        "integrations/codex/.codex-plugin",
        ".claude-plugin",
    ):
        (tmp_path / relative).mkdir(parents=True)
    claude = {"name": "orgforge-plugin", "version": "2.0.0"}
    codex = {"name": "orgforge", "version": "2.0.0+codex.20260801000000"}
    marketplace = {
        "plugins": [
            {"name": "orgforge-plugin", "source": "./integrations/claude-code"}
        ]
    }
    paths = (
        tmp_path / "integrations/claude-code/.claude-plugin/plugin.json",
        tmp_path / "integrations/codex/.codex-plugin/plugin.json",
        tmp_path / ".claude-plugin/marketplace.json",
    )
    values = (claude, codex, marketplace)
    for path, value in zip(paths, values):
        path.write_text(json.dumps(value), encoding="utf-8")
    return paths, values


def test_repository_release_metadata_is_consistent():
    result = release_check.inspect(REPO)
    assert result["tag"] == f"v{result['version']}"
    assert result["claude_archive"].endswith(".tar.gz")
    assert result["codex_archive"].endswith(".tar.gz")


def test_published_checksums_use_downloadable_asset_names():
    workflow = (REPO / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert "(cd dist && shasum -a 256 *.tar.gz > SHA256SUMS)" in workflow
    assert "shasum -a 256 dist/*.tar.gz" not in workflow


@pytest.mark.parametrize(
    "index,mutation,match",
    [
        (0, lambda value: value.update(version="2"), "stable semver"),
        (1, lambda value: value.update(version="1.0.0+codex.x"), "diverge"),
        (2, lambda value: value["plugins"][0].update(source="../elsewhere"), "source"),
    ],
)
def test_release_check_rejects_unpublishable_metadata(tmp_path, index, mutation, match):
    paths, values = _release_tree(tmp_path)
    changed = copy.deepcopy(values[index])
    mutation(changed)
    paths[index].write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(release_check.ReleaseConfigError, match=match):
        release_check.inspect(tmp_path)
