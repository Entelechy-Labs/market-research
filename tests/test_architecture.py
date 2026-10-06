"""Architecture tests — verify the market-research child repo boundaries."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_market_research"

# Network stack imports are forbidden in this repository (research goes through
# the router and tools, never raw sockets).
NETWORK_IMPORTS = (
    "urllib",
    "http",
    "socket",
    "requests",
    "httpx",
    "aiohttp",
    "selenium",
    "playwright",
)

COMMERCIAL_SDK_IMPORTS = (
    "openai",
    "anthropic",
    "google.generativeai",
    "together",
    "replicate",
    "stability",
    "cohere",
    "mistral",
    "groq",
)

# Parent imports (split to avoid false-positive matches on linkgen_contracts).
_PARENT_PKG = "linkgen"
_SIBLING_AGENTS = ("agent_creator_research",)

CLOCK_OR_RANDOM = [
    re.compile(r"\bdatetime\.now\s*\("),
    re.compile(r"\butcnow\s*\("),
    re.compile(r"\btime\.(time|sleep|monotonic)\s*\("),
    re.compile(r"\brandom\.\w"),
    re.compile(r"\buuid4\s*\("),
]


def _import_present(text: str, modules: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for mod in modules:
        if re.search(
            rf"^\s*(import|from)\s+(?:{re.escape(mod)}(\b|\.))",
            text,
            flags=re.MULTILINE,
        ):
            hits.append(mod)
    return hits


def test_no_network_imports() -> None:
    for rel in sorted(SRC.rglob("*.py")):
        if "__pycache__" in rel.parts:
            continue
        hits = _import_present(rel.read_text(), NETWORK_IMPORTS)
        assert not hits, f"network import {hits} in {rel.relative_to(ROOT)}"


def test_no_commercial_sdk_imports() -> None:
    for rel in sorted(SRC.rglob("*.py")):
        if "__pycache__" in rel.parts:
            continue
        hits = _import_present(rel.read_text(), COMMERCIAL_SDK_IMPORTS)
        assert not hits, f"commercial SDK import {hits} in {rel.relative_to(ROOT)}"


def test_no_parent_or_sibling_agent_imports() -> None:
    for rel in sorted(SRC.rglob("*.py")):
        if "__pycache__" in rel.parts:
            continue
        text = rel.read_text()
        for line in text.splitlines():
            if re.search(r"(from|import)\s+linkgen\b", line):
                if "linkgen_contracts" in line or "linkgen_config" in line:
                    continue
                assert False, f"parent import in {rel}: {line.strip()}"
        for mod in _SIBLING_AGENTS:
            hits = _import_present(text, (mod,))
            assert not hits, f"sibling agent import {hits} in {rel}"


def test_no_clock_or_random_usage() -> None:
    for rel in sorted(SRC.rglob("*.py")):
        if "__pycache__" in rel.parts:
            continue
        text = rel.read_text()
        for pattern in CLOCK_OR_RANDOM:
            assert not pattern.search(text), (
                f"clock/random usage {pattern.pattern} in {rel.relative_to(ROOT)}"
            )


def test_public_api_exposes_expected_symbols() -> None:
    import agent_market_research

    for name in (
        "MarketResearchAgent",
        "build_market_research_config",
        "MARKET_RESEARCH_SLUG",
        "MARKET_OUTPUT_SCHEMA",
        "__version__",
    ):
        assert hasattr(agent_market_research, name), f"missing '{name}'"


def test_package_version_matches_pyproject() -> None:
    import agent_market_research

    pyproject = (ROOT / "pyproject.toml").read_text()
    assert f'version = "{agent_market_research.__version__}"' in pyproject


def test_pyproject_and_docs_exist() -> None:
    assert (ROOT / "pyproject.toml").is_file()
    assert (ROOT / "README.md").is_file()
    assert (ROOT / "AGENTS.md").is_file()
