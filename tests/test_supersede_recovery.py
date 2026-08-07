"""When `provisional` refuses a restacked verdict, it prints the way out as commands.

The rule it enforces is right: a lineage must not restack its verdicts until they agree, so a judge
cannot void its own prior verdict — a declared third-party authority must supersede it. What was
wrong is that the refusal only *named* that requirement.

Everything needed already exists — `identity keygen`, `identity receipt --event-class correction`,
`ledger append --class correction --receipt` — and each was verified working before this change.
But reaching them took five failed attempts to rediscover: the keygen argument shape, the trust
store path, the constitution key. In the field a rebase moved `review_subject_id` and the org
deadlocked, and the report concluded the correction command did not exist (issue #186). It did.

What cannot be skipped must still be reachable. These assertions pin the recovery path into the
message, so it cannot drift back into a bare requirement.
"""
import re

from conftest import TOOLS

SOURCE = (TOOLS / "ghsync" / "record.py").read_text(encoding="utf-8")
# The refusal branch: from the "already has a ... verdict" line to its `return 4`.
BLOCK = SOURCE[SOURCE.index("_sig = ("):]
BLOCK = BLOCK[:BLOCK.index("return 4")]


def test_the_refusal_states_the_rule_it_is_enforcing():
    """A bare command list would teach the reader to route around the control."""
    assert "must not restack" in BLOCK
    assert "A judge cannot " in BLOCK and "void its own prior verdict" in BLOCK


def test_every_step_of_the_recovery_is_present():
    """Three commands, in order. Missing any one leaves the caller stuck where #186 was."""
    for step in ("identity.py keygen", "identity.py receipt", "ledger.py append"):
        assert step in BLOCK, f"the recovery is missing {step!r}"
    assert BLOCK.index("keygen") < BLOCK.index("receipt") < BLOCK.index("ledger.py append")


def test_the_receipt_is_bound_to_this_exact_target():
    """A receipt that is not bound to the target seq would supersede anything."""
    assert "correction:superseded:" in BLOCK
    assert "--event-class correction" in BLOCK
    assert "--subject" in BLOCK


def test_the_correction_payload_names_the_target_seq_and_kind():
    assert '\\"corrects\\":' in BLOCK and "prior['seq']" in BLOCK
    assert '\\"kind\\":\\"superseded\\"' in BLOCK
    assert '\\"reason\\"' in BLOCK, "a correction without a recorded reason is not auditable"


def test_the_constitution_requirement_is_named():
    """Without this key the ledger refuses, and the refusal is otherwise opaque."""
    assert "judgment_corrections.authority_roles" in BLOCK


def test_the_authority_is_taken_from_the_constitution_not_hardcoded():
    """A hardcoded role would print a command that fails on any org naming it differently."""
    assert "_auth = authorities[0]" in SOURCE
    assert "<authority-role>" in SOURCE, "needs a visible placeholder when none is declared"


def test_the_private_key_is_not_told_to_live_with_the_writer():
    """Signing authority the writer holds is not third-party authority."""
    assert "--private-out" in BLOCK


def test_append_only_is_stated_so_the_reader_does_not_expect_deletion():
    assert "append-only" in BLOCK and "not erased" in BLOCK


def test_probe_and_mistake_are_covered_by_the_same_path():
    assert "probe" in BLOCK and "mistake" in BLOCK


def test_the_message_carries_no_japanese():
    """This block was Japanese-only, which is how it stopped being actionable (AGENTS.md)."""
    assert not re.search(r"[ぁ-んァ-ヶ一-龠]", BLOCK)
