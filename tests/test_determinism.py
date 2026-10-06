"""Determinism and id-stability regression tests (golden path).

The same input, clock, and router must produce identical artifacts; signal
source ids must be pure functions of (run_id, normalized description).
"""

from __future__ import annotations

from agent_market_research.agent import MarketResearchAgent, signal_source_id
from linkgen_contracts.common.ids import RunId, TaskId

from conftest import RUN_ID, TASK_ID, make_context, make_request


def _run_agent(request: dict, *, run_id: str = RUN_ID) -> dict:
    agent = MarketResearchAgent(context=make_context())
    return agent.process(
        run_id=RunId(run_id), task_id=TaskId(TASK_ID), input_data={"request": request}
    )


def test_same_input_same_output() -> None:
    first = _run_agent(make_request())
    second = _run_agent(make_request())
    assert first == second


def test_signal_ids_derive_from_run_and_description() -> None:
    output = _run_agent(make_request())
    for signal in output["signals"]:
        key = signal["description"].strip().lower()
        assert signal["signal_id"].startswith("finding_")
        assert signal["supporting_source_ids"] == [signal_source_id(RunId(RUN_ID), key)]


def test_report_id_depends_only_on_run_and_request() -> None:
    first = _run_agent(make_request())
    second = _run_agent(make_request(focus="freelancers pricing retainers"))
    assert first["report"]["report_id"] == second["report"]["report_id"]
    assert first["report"]["summary"] != second["report"]["summary"]
