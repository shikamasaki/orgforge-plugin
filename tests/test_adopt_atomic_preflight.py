"""A bundle missing a template leaves the repository untouched, not half-prepared.

The template check used to sit inside the copy loop, so a bundle that shipped without
`schedule.yaml` created directories and some spec files, then stopped hard. The operator was left
with files they had not asked for and no way to tell which were theirs to remove (issue #197).

Preparation either happens or it does not. And when it does not, the message has to say the fault
is in the package rather than in the repository — otherwise the next step taken is to inspect a
repository that was never the problem.
"""
import sys

import pytest

from conftest import REPO, TOOLS

sys.path.insert(0, str(TOOLS))
import adopt  # noqa: E402


def _repo(tmp_path):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# a repository\n", encoding="utf-8")
    return root


def _bundle(tmp_path, omit=()):
    templates = tmp_path / "template"
    templates.mkdir()
    for name in tuple(adopt.SPEC_FILES) + ("organization.SKELETON.yaml",):
        if name in omit:
            continue
        # Copy the real template where the organ parses it (constitution carries
        # output_language); a stub is enough for the rest.
        real = REPO / "template" / name
        if name == "constitution.yaml" and real.is_file():
            (templates / name).write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            (templates / name).write_text("x: 1\n", encoding="utf-8")
    return templates


def test_a_missing_template_creates_nothing(tmp_path, monkeypatch):
    root, templates = _repo(tmp_path), _bundle(tmp_path, omit=("schedule.yaml",))
    before = {p for p in root.rglob("*")}

    monkeypatch.setattr(adopt, "_template_root", lambda: templates)
    with pytest.raises(adopt.AdoptionError) as err:
        adopt.prepare(root, "ja")

    assert {p for p in root.rglob("*")} == before, "a failed prepare left files behind"
    assert ".orgforge" not in {p.name for p in root.iterdir()}
    assert "schedule.yaml" in str(err.value)


def test_the_message_says_the_package_is_at_fault(tmp_path, monkeypatch):
    """Otherwise the operator debugs a repository that was never the problem."""
    root, templates = _repo(tmp_path), _bundle(tmp_path, omit=("schedule.yaml",))
    monkeypatch.setattr(adopt, "_template_root", lambda: templates)
    with pytest.raises(adopt.AdoptionError) as err:
        adopt.prepare(root, "ja")
    text = str(err.value)
    assert "Nothing was created" in text
    assert "packaging defect" in text
    assert "reinstall or update the plugin" in text


def test_every_missing_template_is_named_at_once(tmp_path, monkeypatch):
    """Reporting one per run turns a packaging fix into several round trips."""
    root = _repo(tmp_path)
    templates = _bundle(tmp_path, omit=("schedule.yaml", "moves.yaml"))
    monkeypatch.setattr(adopt, "_template_root", lambda: templates)
    with pytest.raises(adopt.AdoptionError) as err:
        adopt.prepare(root, "ja")
    assert "schedule.yaml" in str(err.value) and "moves.yaml" in str(err.value)


def test_a_complete_bundle_still_prepares(tmp_path, monkeypatch):
    """The guard must not become a reason that nothing can be adopted."""
    root, templates = _repo(tmp_path), _bundle(tmp_path)
    monkeypatch.setattr(adopt, "_template_root", lambda: templates)
    adopt.prepare(root, "ja")
    assert (root / ".orgforge" / "ledger").is_dir()
    assert (root / "schedule.yaml").is_file()
