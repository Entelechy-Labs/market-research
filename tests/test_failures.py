"""Failure-path tests: model failures, timeouts, schema violations.

Mock-provider fault markers (RATE_LIMIT, TIMEOUT, NETWORK_FAILURE,
AUTH_FAILURE, INVALID_OUTPUT) make provider failures deterministic; stub
routers cover paths the mock cannot reach.
"""

from __future__ import annotations

from typing import Any

from agent_framework.context import AgentContext
from agent_framework.errors import AgentTimeoutError
from agent_market_research.agent import MarketResearchAgent
from linkgen_contracts.errors.envelope import ErrorCategory
from linkgen_contracts.workflow.models import TaskStatus
from provider_llm.router import ModelRouter

from conftest import RUN_ID, TASK_ID, make_request, make_settings


class _StubResponse:
    def __init__(self, *, parsed: Any = None, text: Any = None) -> None:
        self.parsed = parsed
        self.text = text


class _StubResult:
    def __init__(self, response: _StubResponse) -> None:
        self.response = response


class StubRouter:
    """Duck-typed router returning canned results or raising canned errors."""

    def __init__(self, fn) -> None:
        self.fn = fn

    def complete_json(self, request, schema):  # noqa: ANN001
        return self.fn(request, schema)


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _agent_with_router(router: Any, sleeper=None) -> MarketResearchAgent:
    context = AgentContext(
        settings=make_settings(), router=router, sleeper=sleeper
    )
    return MarketResearchAgent(context=context)


class TestMockProviderFaults:
    def test_rate_limit_exhausts_retries_with_backoff(self) -> None:
        sleeper = _Recorder()
        agent = _agent_with_router(
            ModelRouter(make_settings(), sleeper=sleeper), sleeper=sleeper
        )
        result = agent.run(
            run_id=RUN_ID,
            task_id=TASK_ID,
            input_data={"request": make_request(focus="RATE_LIMIT storm")},
        )
        assert result.status is TaskStatus.FAILED
        assert result.errors[0].category is ErrorCategory.PROVIDER
        assert result.errors[0].code == "router_exhausted"
        assert len(sleeper.calls) == 2  # 3 attempts → 2 backoff sleeps

    def test_auth_failure_is_not_retried(self) -> None:
        sleeper = _Recorder()
        agent = _agent_with_router(
            ModelRouter(make_settings(), sleeper=sleeper), sleeper=sleeper
        )
        result = agent.run(
            run_id=RUN_ID,
            task_id=TASK_ID,
            input_data={"request": make_request(focus="AUTH_FAILURE locked")},
        )
        assert result.status is TaskStatus.FAILED
        assert sleeper.calls == []  # non-retryable → no backoff sleeps
        assert result.errors[0].retryable is False

    def test_timeout_marker_fails_after_retries(self) -> None:
        sleeper = _Recorder()
        agent = _agent_with_router(
            ModelRouter(make_settings(), sleeper=sleeper), sleeper=sleeper
        )
        result = agent.run(
            run_id=RUN_ID,
            task_id=TASK_ID,
            input_data={"request": make_request(focus="TIMEOUT slow forum")},
        )
        assert result.status is TaskStatus.FAILED
        assert len(sleeper.calls) == 2


class TestStubRouterPaths:
    def test_unparseable_model_json_maps_to_validation_failure(self) -> None:
        agent = _agent_with_router(
            StubRouter(lambda request, schema: _StubResult(_StubResponse(text="nope{"))
            )
        )
        result = agent.run(
            run_id=RUN_ID, task_id=TASK_ID, input_data={"request": make_request()}
        )
        assert result.status is TaskStatus.FAILED
        assert result.errors[0].category is ErrorCategory.VALIDATION
        assert result.errors[0].code == "agent_output_invalid"

    def test_non_object_json_maps_to_validation_failure(self) -> None:
        agent = _agent_with_router(
            StubRouter(lambda request, schema: _StubResult(_StubResponse(text='"str"'))
            )
        )
        result = agent.run(
            run_id=RUN_ID, task_id=TASK_ID, input_data={"request": make_request()}
        )
        assert result.status is TaskStatus.FAILED
        assert result.errors[0].category is ErrorCategory.VALIDATION

    def test_unexpected_router_exception_maps_to_internal(self) -> None:
        def boom(request, schema):  # noqa: ANN001
            raise ValueError("unexpected")

        agent = _agent_with_router(StubRouter(boom))
        result = agent.run(
            run_id=RUN_ID, task_id=TASK_ID, input_data={"request": make_request()}
        )
        assert result.status is TaskStatus.FAILED
        assert result.errors[0].category is ErrorCategory.INTERNAL

    def test_agent_errors_pass_through_unchanged(self) -> None:
        def timeout(request, schema):  # noqa: ANN001
            raise AgentTimeoutError("agent budget exhausted")

        agent = _agent_with_router(StubRouter(timeout))
        result = agent.run(
            run_id=RUN_ID, task_id=TASK_ID, input_data={"request": make_request()}
        )
        assert result.status is TaskStatus.FAILED
        assert result.errors[0].category is ErrorCategory.TIMEOUT
        assert result.errors[0].retryable is True
