"""Unit tests for market-research normalization (agent-specific logic).

Generic sanitizer behavior is covered by agent-framework's test_sanitize.py;
here we test how this agent applies it to market signal candidates.
"""

from __future__ import annotations

import pytest

from agent_market_research.agent import (
    MAX_SIGNALS,
    dedupe_signals,
    normalize_signals,
    signal_source_id,
)
from agent_framework.errors import AgentOutputError
from linkgen_contracts.common.ids import RunId, SourceId

RUN = RunId("run_" + "a1" * 16)


def test_normalize_signals_filters_and_validates() -> None:
    payload = {"signals": [{"description": "a"}, "junk", 7, {"description": "b"}]}
    assert normalize_signals(payload) == [{"description": "a"}, {"description": "b"}]
    assert normalize_signals({}) == []
    assert normalize_signals({"signals": None}) == []
    with pytest.raises(AgentOutputError):
        normalize_signals({"signals": 42})


def test_dedupe_signals_by_description() -> None:
    candidates = [
        {"description": "Onboarding drop-off hurts trials"},
        {"description": "  onboarding   drop-off hurts trials "},  # duplicate
        {"description": "Pricing page confusion"},  # distinct — kept
        {"description": ""},  # empty — dropped
        {"description": "   "},  # whitespace — dropped
        {"audience": "no description"},  # dropped
    ]
    out = dedupe_signals(candidates)
    assert len(out) == 2
    assert out[0]["description"] == "Onboarding drop-off hurts trials"
    assert out[1]["description"] == "Pricing page confusion"


def test_dedupe_signals_caps_deterministically() -> None:
    candidates = [{"description": f"signal {i}"} for i in range(MAX_SIGNALS + 5)]
    out = dedupe_signals(candidates)
    assert len(out) == MAX_SIGNALS
    assert out[0]["description"] == "signal 0"
    assert out[-1]["description"] == f"signal {MAX_SIGNALS - 1}"


def test_signal_source_id_is_stable_and_valid() -> None:
    first = signal_source_id(RUN, "onboarding drop-off")
    second = signal_source_id(RUN, "onboarding drop-off")
    assert first == second
    assert first.startswith("source_")
    assert SourceId.model_validate(first).root == first


def test_signal_source_id_varies_by_description() -> None:
    assert signal_source_id(RUN, "a") != signal_source_id(RUN, "b")
