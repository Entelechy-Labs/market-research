"""Market-research agent — Phase 08 research system.

Researches market/audience signals for a research request and produces
contract-conforming artifacts:

- ``ResearchReport`` (findings + sources)
- ``MarketSignal[]`` (one per distinct signal, each with a captured source)

Design rules (shared with creator-research):
- The LLM is used only for content judgment; ids, timestamps, dedupe, capping,
  and confidence bounds are deterministic Python.
- Model output is untrusted: it arrives router-validated as JSON, and every
  field is sanitized (``agent_framework.sanitize``) before entering contract
  models.
- Ids are derived deterministically (uuid5) so identical inputs produce
  identical artifacts (idempotent replay, golden tests, checkpoint recovery).
- No network, clock, or randomness: time comes from the injected context
  clock; failures come from the router as duck-typed-normalized errors.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from linkgen_contracts.common.ids import (
    FindingId,
    ResultId,
    RunId,
    SourceId,
    TaskId,
)
from linkgen_contracts.errors.envelope import ErrorCategory
from linkgen_contracts.research.models import (
    MarketSignal,
    ResearchFinding,
    ResearchReport,
    ResearchRequest,
    ResearchSource,
    SourceKind,
)
from pydantic import ValidationError

from agent_market_research.config import (
    MARKET_OUTPUT_SCHEMA,
    build_market_research_config,
)
from agent_framework.base import AgentBase
from agent_framework.config import AgentConfig
from agent_framework.context import AgentContext
from agent_framework.errors import (
    AgentError,
    AgentInputError,
    AgentOutputError,
)
from agent_framework.ids import deterministic_id
from agent_framework.sanitize import (
    bounded_str_list,
    clean_text,
    normalize_key,
    safe_confidence,
    stable_probability,
)
from agent_framework.structured import extract_json_dict

# Bounded resource usage (AGENTS rule 11).
MAX_SIGNALS = 40
MAX_FINDINGS = 50
MAX_NOTES = 10

__all__ = [
    "MarketResearchAgent",
    "build_market_research_prompt",
    "build_findings",
    "build_report",
    "build_signals",
    "build_signal_sources",
    "dedupe_signals",
    "normalize_signals",
    "validate_request_input",
    "normalize_router_failure",
]


# ---------------------------------------------------------------------------
# Untrusted-input normalization (agent-specific; sanitizers are shared).
# ---------------------------------------------------------------------------


def normalize_signals(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter the untrusted ``signals`` array down to dict entries."""
    raw = payload.get("signals")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AgentOutputError("model output field 'signals' must be an array")
    return [entry for entry in raw if isinstance(entry, dict)]


def dedupe_signals(
    candidates: list[dict[str, Any]], *, cap: int = MAX_SIGNALS
) -> list[dict[str, Any]]:
    """Dedupe by normalized description, drop empty ones, cap deterministically."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in candidates:
        description = clean_text(entry.get("description"))
        key = normalize_key(description)
        if not key:
            continue  # no usable description — skip deterministically
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
        if len(out) >= cap:
            break
    return out


def validate_request_input(input_data: Any) -> ResearchRequest:
    """Validate the agent input against the ``ResearchRequest`` contract."""
    if not isinstance(input_data, dict):
        raise AgentInputError(
            "market-research input must be a dict with a 'request' key"
        )
    raw_request = input_data.get("request")
    if raw_request is None:
        raise AgentInputError("market-research input is missing the 'request' object")
    try:
        return ResearchRequest.model_validate(raw_request)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ()))
        raise AgentInputError(
            f"research request failed contract validation at '{location}': "
            f"{first.get('msg', 'invalid')}"
        ) from exc


class _RouterFailure(AgentError):
    """Agent-level wrapper for a router failure (category/code preserved)."""


def normalize_router_failure(exc: Exception) -> AgentError:
    """Normalize a router failure without importing provider internals.

    Router errors carry ``category``/``code``/``retryable``; they are preserved
    by duck-typing so ``TaskResult`` mapping keeps retry semantics honest.
    """
    failure = _RouterFailure(f"router call failed: {getattr(exc, 'message', None) or exc}")
    raw_category = getattr(exc, "category", ErrorCategory.INTERNAL)
    failure.category = raw_category if isinstance(raw_category, ErrorCategory) else ErrorCategory.INTERNAL
    failure.code = str(getattr(exc, "code", "router_failure"))
    failure.retryable = bool(getattr(exc, "retryable", False))
    return failure


def build_market_research_prompt(request: ResearchRequest) -> str:
    """Deterministic user prompt for the market-research LLM call."""
    lines = [
        "Research market and audience signals for a LinkedIn content system.",
        f"Focus: {request.focus}",
    ]
    if request.objectives:
        lines.append("Objectives: " + "; ".join(request.objectives))
    if request.domains:
        lines.append("Domains: " + ", ".join(request.domains))
    if request.creators:
        lines.append(
            "Audiences of interest (from creator research): "
            + ", ".join(request.creators)
        )
    lines.append(
        "Identify high-interest topics, audience problems, misconceptions, "
        "repeated questions, underserved areas, missing opinions, and "
        "practical information. Mark weak evidence with caveats and rate "
        "signal strength honestly."
    )
    lines.append("Return JSON with 'signals' and 'findings' arrays.")
    return "\n".join(lines)


def signal_source_id(run_id: RunId, description_key: str) -> str:
    """Deterministic source id for a signal (stable across runs)."""
    return deterministic_id(SourceId, str(run_id), "signal", description_key)


# ---------------------------------------------------------------------------
# Artifact builders (pure functions of their inputs).
# ---------------------------------------------------------------------------


def build_signals(
    *,
    run_id: RunId,
    candidates: list[dict[str, Any]],
    captured_at: datetime,
) -> list[MarketSignal]:
    """Build one ``MarketSignal`` per deduped candidate (index-aligned).

    Each signal cites exactly the source this run will capture for it; the
    source id is derived deterministically from the signal description.
    """
    signals: list[MarketSignal] = []
    for entry in candidates:
        description = clean_text(entry.get("description"))
        key = normalize_key(description)
        if not key:
            continue
        signals.append(
            MarketSignal(
                signal_id=deterministic_id(FindingId, str(run_id), "signal", key),
                description=description,
                strength=safe_confidence(entry.get("strength")),
                supporting_source_ids=[SourceId(signal_source_id(run_id, key))],
                captured_at=captured_at,
            )
        )
    return signals


def build_signal_sources(
    *,
    run_id: RunId,
    signals: list[MarketSignal],
    candidates: list[dict[str, Any]],
    captured_at: datetime,
) -> list[ResearchSource]:
    """Build one web source per signal (index-aligned with ``signals``)."""
    sources: list[ResearchSource] = []
    for signal, entry in zip(signals, candidates):
        evidence = clean_text(entry.get("evidence")) or None
        sources.append(
            ResearchSource(
                source_id=SourceId(str(signal.supporting_source_ids[0])),
                kind=SourceKind.WEB,
                title=f"Market signal: {signal.description}",
                retrieved_at=captured_at,
                snippet=evidence[:200] if evidence else None,
                confidence=stable_probability(
                    "signal-source", str(run_id), str(signal.signal_id)
                ),
            )
        )
    return sources


def build_findings(
    *,
    run_id: RunId,
    request: ResearchRequest,
    payload: dict[str, Any],
    sources: list[ResearchSource],
    signals: list[MarketSignal],
) -> list[ResearchFinding]:
    """Map untrusted model findings into contract-valid findings.

    A deterministic coverage finding is always inserted first when signals
    were captured, so the research gate always has evidence to inspect.
    """
    known_source_ids = {str(source.source_id) for source in sources}
    findings: list[ResearchFinding] = []
    seen: set[tuple[str, str]] = set()

    raw_findings = payload.get("findings")
    for entry in raw_findings if isinstance(raw_findings, list) else []:
        if not isinstance(entry, dict) or len(findings) >= MAX_FINDINGS:
            continue
        title = clean_text(entry.get("title"))
        assertion = clean_text(entry.get("assertion"))
        if not title or not assertion:
            continue
        key = (title, assertion)
        if key in seen:
            continue
        seen.add(key)
        # Only cite sources this run actually captured; model-invented ids are
        # untrusted and dropped.
        supporting = [
            SourceId(sid)
            for sid in bounded_str_list(entry.get("supporting_source_ids"))
            if sid in known_source_ids
        ]
        findings.append(
            ResearchFinding(
                finding_id=deterministic_id(FindingId, str(run_id), title, assertion),
                title=title,
                assertion=assertion,
                supporting_source_ids=supporting,
                confidence=safe_confidence(entry.get("confidence")),
                caveats=bounded_str_list(entry.get("caveats")),
            )
        )

    if signals:
        coverage_title = "Market signal coverage"
        coverage_assertion = (
            f"Captured {len(signals)} market signals for focus '{request.focus}'."
        )
        if (coverage_title, coverage_assertion) not in seen:
            findings.insert(
                0,
                ResearchFinding(
                    finding_id=deterministic_id(
                        FindingId, str(run_id), coverage_title, coverage_assertion
                    ),
                    title=coverage_title,
                    assertion=coverage_assertion,
                    supporting_source_ids=[source.source_id for source in sources],
                    confidence=stable_probability(
                        "coverage", str(run_id), str(request.request_id)
                    ),
                    caveats=[] if sources else ["no signal sources captured"],
                ),
            )
    return findings


def build_report(
    *,
    run_id: RunId,
    request: ResearchRequest,
    signals: list[MarketSignal],
    findings: list[ResearchFinding],
    sources: list[ResearchSource],
    generated_at: datetime,
) -> ResearchReport:
    """Build the run's ``ResearchReport``."""
    summary = (
        f"Market research for '{request.focus}': "
        f"{len(signals)} signals, {len(findings)} findings, "
        f"{len(sources)} sources."
    )
    return ResearchReport(
        report_id=deterministic_id(
            ResultId, str(run_id), "market-research-report", str(request.request_id)
        ),
        run_id=run_id,
        generated_at=generated_at,
        summary=summary,
        findings=findings,
        sources=sources,
        confidence=stable_probability("report", str(run_id), str(request.request_id)),
    )


# ---------------------------------------------------------------------------
# The agent.
# ---------------------------------------------------------------------------


class MarketResearchAgent(AgentBase):
    """Research market/audience signals (research phase, Phase 08).

    Input (validated against the ``ResearchRequest`` contract):
        ``{"request": {request_id, run_id, focus, objectives?, creators?, domains?}}``

    Output:
        ``{"report": ResearchReport, "signals": [MarketSignal]}`` — JSON-
        serialized and contract-validated by construction.
    """

    def __init__(
        self, context: AgentContext, config: AgentConfig | None = None
    ) -> None:
        super().__init__(
            config if config is not None else build_market_research_config(), context
        )

    def process(
        self,
        *,
        run_id: RunId,
        task_id: TaskId,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        request = validate_request_input(input_data)
        payload = self._gather(run_id=run_id, task_id=task_id, request=request)

        candidates = dedupe_signals(normalize_signals(payload))
        now = self.context.now()
        signals = build_signals(run_id=run_id, candidates=candidates, captured_at=now)
        sources = build_signal_sources(
            run_id=run_id, signals=signals, candidates=candidates, captured_at=now
        )
        findings = build_findings(
            run_id=run_id,
            request=request,
            payload=payload,
            sources=sources,
            signals=signals,
        )
        report = build_report(
            run_id=run_id,
            request=request,
            signals=signals,
            findings=findings,
            sources=sources,
            generated_at=now,
        )
        return {
            "report": report.model_dump(mode="json"),
            "signals": [signal.model_dump(mode="json") for signal in signals],
        }

    def _gather(
        self, *, run_id: RunId, task_id: TaskId, request: ResearchRequest
    ) -> dict[str, Any]:
        """Call the router for structured market signals (single LLM hop).

        Fault markers in the prompt (mock mode) or a failing adapter surface
        as normalized agent errors; they never escape as raw provider errors.
        """
        prompt = build_market_research_prompt(request)
        llm_request = self.build_llm_request(
            run_id=run_id,
            task_id=task_id,
            prompt=prompt,
            json_schema=MARKET_OUTPUT_SCHEMA,
        )
        try:
            result = self.context.router.complete_json(llm_request, MARKET_OUTPUT_SCHEMA)
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001 — normalized below, never swallowed
            raise normalize_router_failure(exc) from exc
        return extract_json_dict(result)
