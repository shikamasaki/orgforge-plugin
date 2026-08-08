"""Every template an organ opens is present in every harness bundle.

`build.sh --check` verifies that a bundled file MATCHES its source. It cannot notice a file that
was never listed for syncing at all — and that is the gap this closes. `adopt.py` requires
`schedule.yaml` and copies `organization.SKELETON.yaml`; neither was in the Codex sync list, so
`/org-adopt` reached READY on Claude Code and failed on Codex with "required template is missing"
(issue #197).

A projection that drifts is indistinguishable from a broken tool to whoever hits it, and the person
who hits it is on the harness nobody tested. So the requirement is derived from the organs
themselves — `SPEC_FILES` and the literal template names the tools open — rather than from a second
hand-maintained list that can drift the same way.
"""
import re

from conftest import REPO, TOOLS

BUNDLES = (REPO / "integrations" / "claude-code" / "template",
           REPO / "integrations" / "codex" / "template")


def _required_template_names():
    """Template files the organs name, read out of the organ sources."""
    names = set()

    adopt = (TOOLS / "adopt.py").read_text(encoding="utf-8")
    block = adopt[adopt.index("SPEC_FILES = ("):]
    names.update(re.findall(r'"([\w.-]+\.(?:yaml|md))"', block[:block.index(")")]))
    names.update(re.findall(r'templates / "([\w.-]+\.(?:yaml|md))"', adopt))

    for organ in ("org_lint.py", "tick.py", "sensors.py"):
        source = (TOOLS / organ)
        if source.is_file():
            names.update(re.findall(r'template[/\\]([\w.-]+\.yaml)',
                                    source.read_text(encoding="utf-8")))
    return names


def test_the_organs_name_at_least_the_files_we_expect():
    """Guards the extraction itself: a silent zero here would make the test vacuous."""
    required = _required_template_names()
    assert {"constitution.yaml", "schedule.yaml", "ledger-schema.yaml"} <= required
    assert len(required) >= 6


def test_every_required_template_is_in_every_bundle():
    missing = []
    for bundle in BUNDLES:
        if not bundle.is_dir():
            continue
        for name in sorted(_required_template_names()):
            if not (bundle / name).is_file():
                missing.append(f"{bundle.relative_to(REPO)}/{name}")
    assert not missing, (
        "an organ opens these templates, but a harness bundle does not ship them — "
        "the command works on one harness and fails on the other:\n  " + "\n  ".join(missing)
    )


def test_the_bundles_agree_with_each_other():
    """Either harness may gain a file first; neither should keep it to itself for long."""
    claude, codex = ({p.name for p in b.glob("*.yaml")} | {p.name for p in b.glob("*.md")}
                     for b in BUNDLES)
    only_claude, only_codex = sorted(claude - codex), sorted(codex - claude)
    assert not (only_claude or only_codex), (
        f"the harness projections disagree — only in claude-code: {only_claude}; "
        f"only in codex: {only_codex}"
    )
