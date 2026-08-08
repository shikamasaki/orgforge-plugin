"""The dispatch timeout is set from a measured distribution, not from a guess.

A timeout catches a HUNG child. It is not a budget for normal work, and setting it near the
observed maximum turns a slow-but-working judgment into a failed one — which costs the round, the
tokens, and reads to the caller exactly like a judge that produced nothing (#201).

Measured on a realistic subject (compact review contract plus ~6k of target code,
gpt-5.6-terra / medium):

    median 46.4s, max 86.9s, spread 32–87s across four runs of the SAME prompt

The 3x run-to-run spread is the reason for the headroom: a larger subject or a slower moment lands
on a tight cutoff even when nothing is wrong. 120s was 1.4x the maximum; 300s is 3.5x.

Trimming the material does not buy headroom either — cutting it 68% in 2.6.0 moved the median by
nothing measurable, because runtime is dominated by reading the subject and deciding.
"""
import re
import sys

from conftest import TOOLS

sys.path.insert(0, str(TOOLS))
from orgcycle import judge as J  # noqa: E402

SOURCE = (TOOLS / "orgcycle" / "judge.py").read_text(encoding="utf-8")

MEASURED_MAX_SECONDS = 87        # observed worst case on a realistic subject


def test_the_default_clears_the_measured_maximum():
    assert J.JUDGE_TIMEOUT_DEFAULT >= MEASURED_MAX_SECONDS * 2, (
        f"the default ({J.JUDGE_TIMEOUT_DEFAULT}s) is too close to the measured maximum "
        f"({MEASURED_MAX_SECONDS}s). Run-to-run spread on an identical prompt is ~3x, so a tight "
        f"cutoff kills working judgments. Re-measure before lowering this."
    )


def test_the_default_is_still_a_hang_detector():
    """Unbounded is not the answer either — a hung child must be caught within a tolerable wait."""
    assert J.JUDGE_TIMEOUT_DEFAULT <= 900


def test_the_environment_override_still_wins():
    assert 'os.environ.get("ORG_JUDGE_TIMEOUT"' in SOURCE
    assert "cfg.get(\"timeout_seconds\")" in SOURCE, "a per-role config value must take precedence"


def test_the_timeout_message_carries_the_measured_range():
    """An operator who hits it should raise it, not conclude the judge is broken."""
    block = SOURCE[SOURCE.index("timed out after"):]
    block = block[:block.index("return 5")]
    assert "median" in block and "max" in block
    assert "ORG_JUDGE_TIMEOUT" in block
    assert "broken" in block, "the message must name the wrong conclusion it is preventing"


def test_the_measurement_is_recorded_beside_the_value():
    """A number with no provenance gets 'optimised' by the next reader."""
    block = SOURCE[:SOURCE.index("JUDGE_TIMEOUT_DEFAULT = ")]
    block = block[block.rindex("# Seconds before"):]
    assert re.search(r"~?\d+s", block), "the measured figures belong next to the constant"
    assert "#203" in block
