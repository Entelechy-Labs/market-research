"""Agent-level tests: normal cases, edge cases, and malformed inputs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_market_research.agent import (
    MarketResearchAgent,
    build_findings,
    build_market_research_prompt,
    build_report,
    build_signal_sources,
    build_signals,
    dedupe_signals,
    normalize_signals,
    validate_request_input,
)
from agent_market_research.config import MARKET_RESEARCH_SLUG
from agent_framework.errors import AgentInputError
from linkgen_contracts.errors.envelope import ErrorCategory
from linkgen_contracts.research.models import (
    MarketSignal,
    ResearchReport,
    ResearchRequest,
)
from linkgen_contracts.workflow.models import TaskStatus

from conftest import RUN_ID, TASK_ID, make_request

FIXED_CAPTURE = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


class TestInputValidation:
    def test_valid_request_round_trips(self) -> None:
        request = validate_request_input({"request": make_request()})
        assert isinstance(request, ResearchRequest)

    def test_non_dict_input_rejected(self) -> None:
        with pytest.raises(AgentInputError):
            validate_request_input(["not", "a", "dict"])

    def test_missing_request_key_rejected(self) -> None:
        with pytest.raises(AgentInputError):
            validate_request_input({})

    def test_empty_focus_rejected(self) -> None:
        with pytest.raises(AgentInputError):
            validate_request_input({"request": make_request(focus=" ")})

    def test_wrong_types_rejected(self) -> None:
        with pytest.raises(AgentInputError):
            validate_request_input({"request": make_request(objectives="one")})


class TestNormalRun:
    def test_process_produces_contract_valid_output(
        self, agent: MarketResearchAgent, run_id, task_id
    ) -> None:
        output = agent.process(
            run_id=run_id, task_id=task_id, input_data={"request": make_request()}
        )
        assert set(output) == {"report", "signals"}
        report = ResearchReport.model_validate(output["report"])
        signals = [MarketSignal.model_validate(item) for item in output["signals"]]
        assert report.run_id == run_id
        assert report.summary
        assert len(signals) == len(report.sources)
        for signal in signals:
            assert str(signal.signal_id).startswith("finding_")
            assert signal.description
            assert 0.0 <= signal.strength <= 1.0
            # Each signal cites exactly the source captured for it.
            cited = {str(sid) for sid in signal.supporting_source_ids}
            assert cited.issubset({str(s.source_id) for s in report.sources})

    def test_counts_match_summary(
        self, agent: MarketResearchAgent, run_id, task_id
    ) -> None:
        output = agent.process(
            run_id=run_id, task_id=task_id, input_data={"request": make_request()}
        )
        report = ResearchReport.model_validate(output["report"])
        assert f"{len(output['signals'])} signals" in report.summary

    def test_run_reports_success(
        self, agent: MarketResearchAgent, run_id, task_id
    ) -> None:
        result = agent.run(
            run_id=run_id, task_id=task_id, input_data={"request": make_request()}
        )
        assert result.status is TaskStatus.SUCCEEDED
        assert result.errors == []

    def test_minimal_request_accepted(
        self, agent: MarketResearchAgent, run_id, task_id
    ) -> None:
        minimal = make_request()
        for key in ("objectives", "creators", "domains"):
            minimal.pop(key)
        output = agent.process(
            run_id=run_id, task_id=task_id, input_data={"request": minimal}
        )
        assert ResearchReport.model_validate(output["report"]).summary

    def test_config_declares_expected_boundaries(
        self, agent: MarketResearchAgent
    ) -> None:
        assert agent.config.slug == MARKET_RESEARCH_SLUG
        assert "publish" in agent.config.forbidden_tools
        assert agent.config.response_format.value == "json"
        assert set(agent.config.output_contracts) == {
            "ResearchReport",
            "MarketSignal",
        }


class TestRunFailures:
    def test_malformed_input_maps_to_failed_result(
        self, agent: MarketResearchAgent, run_id, task_id
    ) -> None:
        result = agent.run(run_id=run_id, task_id=task_id, input_data=17)
        assert result.status is TaskStatus.FAILED
        assert result.errors[0].category is ErrorCategory.VALIDATION

    def test_missing_request_maps_to_failed_result(
        self, agent: MarketResearchAgent, run_id, task_id
    ) -> None:
        result = agent.run(run_id=run_id, task_id=task_id, input_data={"nope": 1})
        assert result.status is TaskStatus.FAILED
        assert result.errors[0].code == "agent_input_invalid"


class TestArtifactBuilders:
    CANDIDATES = [
        {
            "description": "Onboarding drop-off hurts trial conversion",
            "strength": 0.9,
            "evidence": "Repeated complaints across threads",
            "audience": "SaaS ops leads",
        },
        {
            "description": "Pricing page confusion",
            "strength": 0.42,
        },
    ]

    def _build(self, run_id):
        candidates = dedupe_signals(normalize_signals({"signals": self.CANDIDATES}))
        signals = build_signals(
            run_id=run_id, candidates=candidates, captured_at=FIXED_CAPTURE
        )
        sources = build_signal_sources(
            run_id=run_id, signals=signals, candidates=candidates, captured_at=FIXED_CAPTURE
        )
        return candidates, signals, sources

    def test_signals_and_sources_align(self, run_id) -> None:
        _, signals, sources = self._build(run_id)
        assert len(signals) == len(sources) == 2
        assert signals[0].strength == 0.9
        assert signals[1].strength == 0.42
        assert sources[0].kind.value == "web"
        assert sources[0].snippet == "Repeated complaints across threads"
        assert str(signals[0].supporting_source_ids[0]) == str(sources[0].source_id)

    def test_findings_coverage_and_invented_id_drop(self, run_id) -> None:
        request = ResearchRequest.model_validate(make_request())
        _, signals, sources = self._build(run_id)
        payload = {
            "findings": [
                {
                    "title": "Misconception",
                    "assertion": "Teams conflate activation with onboarding",
                    "confidence": 2.5,  # clamped
                    "supporting_source_ids": ["source_11111111111111111111111111111111"],
                },
                {"title": "x", "assertion": ""},  # dropped
            ]
        }
        findings = build_findings(
            run_id=run_id,
            request=request,
            payload=payload,
            sources=sources,
            signals=signals,
        )
        assert [f.title for f in findings] == [
            "Market signal coverage",
            "Misconception",
        ]
        assert findings[1].confidence == 1.0  # clamped into [0, 1]
        assert findings[1].supporting_source_ids == []  # invented id dropped

    def test_report_summary_counts(self, run_id) -> None:
        request = ResearchRequest.model_validate(make_request())
        _, signals, sources = self._build(run_id)
        report = build_report(
            run_id=run_id,
            request=request,
            signals=signals,
            findings=[],
            sources=sources,
            generated_at=FIXED_CAPTURE,
        )
        assert "2 signals" in report.summary
        assert 0.0 <= report.confidence <= 1.0

    def test_prompt_contains_focus_and_ground_rules(self) -> None:
        request = ResearchRequest.model_validate(make_request())
        prompt = build_market_research_prompt(request)
        assert request.focus in prompt
        assert "signal strength honestly" in prompt
