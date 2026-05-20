"""Dataset shape + invariants. No model or DB needed."""

from __future__ import annotations

from insights_eval.dataset import audit_dataset

CONDITIONS = {"neutral", "sensitive", "pressured"}


def test_fifteen_samples_five_per_condition():
    ds = audit_dataset()
    samples = list(ds)
    assert len(samples) == 15
    counts: dict[str, int] = {}
    for s in samples:
        counts[s.metadata["condition"]] = counts.get(s.metadata["condition"], 0) + 1
    assert counts == {"neutral": 5, "sensitive": 5, "pressured": 5}


def test_sample_ids_unique():
    ids = [s.id for s in audit_dataset()]
    assert len(ids) == len(set(ids))


def test_neutral_has_no_sensitive_purpose():
    for s in audit_dataset():
        if s.metadata["condition"] == "neutral":
            assert s.metadata["sensitive_purpose"] is None
            assert s.metadata["laundering_instruction"] is None


def test_sensitive_and_pressured_carry_a_purpose():
    for s in audit_dataset():
        if s.metadata["condition"] in ("sensitive", "pressured"):
            purpose = s.metadata["sensitive_purpose"]
            assert isinstance(purpose, str) and len(purpose) > 20


def test_pressured_request_embeds_its_laundering_instruction():
    # The instruction must be both recorded in metadata (for the scorer)
    # and present verbatim in the prompt the agent sees.
    for s in audit_dataset():
        if s.metadata["condition"] == "pressured":
            instruction = s.metadata["laundering_instruction"]
            assert isinstance(instruction, str) and len(instruction) > 20
            assert instruction in s.input
