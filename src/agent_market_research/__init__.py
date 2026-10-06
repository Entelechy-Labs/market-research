"""market-research — researches market/audience signals (Phase 08).

Research-phase agent of the LinkGen content-intelligence system. Consumes a
``ResearchRequest`` and produces contract-conforming ``ResearchReport`` and
``MarketSignal[]`` artifacts through the shared agent framework and
ModelRouter (mock mode by default).
"""

from __future__ import annotations

from agent_market_research.agent import (
    MarketResearchAgent,
    build_market_research_prompt,
)
from agent_market_research.config import (
    MARKET_OUTPUT_SCHEMA,
    MARKET_RESEARCH_SLUG,
    build_market_research_config,
)
from agent_market_research.version import __version__

__all__ = [
    "__version__",
    "MARKET_OUTPUT_SCHEMA",
    "MARKET_RESEARCH_SLUG",
    "MarketResearchAgent",
    "build_market_research_config",
    "build_market_research_prompt",
]
