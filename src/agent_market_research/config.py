"""Typed definition of the market-research agent.

The ``AgentConfig`` is the definition-time contract of this agent: mission,
model role, allowed/forbidden tools, output contracts, and the JSON schema
its LLM calls must satisfy. The router validates model output against this
schema (fail closed) before the agent ever sees it.
"""

from __future__ import annotations

from typing import Any

from agent_framework.config import AgentConfig
from linkgen_contracts.llm.models import LLMRole, ResponseFormat

MARKET_RESEARCH_SLUG = "market-research"

# JSON schema for the model's structured output. Restricted to the router's
# documented schema subset (type/properties/items) so it fails closed rather
# than being silently ignored. Ids and timestamps are NEVER requested from the
# model — deterministic Python derives them (see agent.py).
MARKET_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "strength": {"type": "number"},
                    "evidence": {"type": "string"},
                    "audience": {"type": "string"},
                },
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "assertion": {"type": "string"},
                    "confidence": {"type": "number"},
                    "caveats": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

_SYSTEM_PROMPT = """You are the market-research agent of the LinkGen content system.
Mission: research market and audience signals for the requested focus.
Identify high-interest topics, audience problems, misconceptions, repeated
questions, underserved areas, missing opinions, and practical information.
Prefer concrete, evidence-backed observations over vague trends; note signal
strength honestly and mark weak evidence with caveats.
Never copy source wording or distinctive material; produce original analysis.
Respond only with JSON matching the requested schema."""


def build_market_research_config() -> AgentConfig:
    """Build the definition-time configuration of the market-research agent."""
    return AgentConfig(
        slug=MARKET_RESEARCH_SLUG,
        model_role=LLMRole.REASONING,
        output_contracts=[
            "ResearchReport",
            "MarketSignal",
        ],
        system_prompt=_SYSTEM_PROMPT,
        temperature=0.0,
        max_output_tokens=2048,
        max_steps=8,
        tools=["web-search", "browser"],
        forbidden_tools=["publish", "schedule", "linkedin-post"],
        response_format=ResponseFormat.JSON,
        json_schema=MARKET_OUTPUT_SCHEMA,
        description="Research market/audience signals (research phase).",
        version="1.0.0",
    )
