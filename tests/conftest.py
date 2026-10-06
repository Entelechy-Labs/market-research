"""Shared fixtures for market-research tests.

Deterministic by construction: fixed clock, no-op sleeper, mock-only settings,
and fixed id constants — no system clock, no randomness, no network.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]

# Sibling repos on sys.path (mirrors parent compose-time resolution).
# This repo lives at agents/market-research, so shared children are two
# levels up (agents/market-research → agents → parent root).
for _child in (
    "../../contracts/src",
    "../../config/src",
    "../../providers/llm/src",
    "../../agent-framework/src",
):
    _src = (_ROOT / _child).resolve()
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

import pytest

from agent_market_research.agent import MarketResearchAgent
from agent_framework.context import AgentContext
from linkgen_contracts.common.ids import RunId, TaskId
from linkgen_config.settings import (
    CostPolicy,
    ModelRoleConfig,
    ProviderInfo,
    ProviderKind,
    Settings,
)

FIXED_NOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)

# Fixed contract ids (32 lowercase hex suffixes) for golden determinism.
RUN_ID = "run_" + "a1" * 16
TASK_ID = "task_" + "b2" * 16
REQUEST_ID = "request_" + "c3" * 16


class RecordingSleeper:
    """Records backoff sleeps; never actually sleeps."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = dict(overrides)
    base.setdefault(
        "providers",
        {
            "mock": ProviderInfo(
                id="mock",
                kind=ProviderKind.LLM,
                paid=False,
                description="test mock",
            )
        },
    )
    base.setdefault(
        "model_roles",
        {
            role: ModelRoleConfig(provider="mock", model=f"dev_{role}_model")
            for role in ("reasoning", "writer", "fast", "vision", "review")
        },
    )
    base.setdefault("cost", CostPolicy())
    return Settings(**base)


def make_context(**overrides: Any) -> AgentContext:
    """Build an AgentContext with mock router, fixed clock, injected sleeper."""
    from provider_llm.router import ModelRouter

    settings = overrides.get("settings") or make_settings()
    router = overrides.get("router") or ModelRouter(settings)
    return AgentContext(
        settings=settings,
        router=router,
        clock=lambda: FIXED_NOW,
        sleeper=overrides.get("sleeper"),
    )


def make_request(**overrides: Any) -> dict[str, Any]:
    """A valid ResearchRequest payload (as a plain dict)."""
    data: dict[str, Any] = {
        "request_id": REQUEST_ID,
        "run_id": RUN_ID,
        "focus": "mid-market SaaS teams struggling with onboarding",
        "objectives": ["map audience problems", "find underserved angles"],
        "creators": ["jane-doe"],
        "domains": ["linkedin.com"],
    }
    data.update(overrides)
    return data


@pytest.fixture
def run_id() -> RunId:
    return RunId(RUN_ID)


@pytest.fixture
def task_id() -> TaskId:
    return TaskId(TASK_ID)


@pytest.fixture
def context() -> AgentContext:
    return make_context()


@pytest.fixture
def agent(context: AgentContext) -> MarketResearchAgent:
    return MarketResearchAgent(context=context)
