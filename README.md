# market-research

Research-phase agent of the **LinkGen** content-intelligence and publishing
system.

## Purpose

The specialist agent responsible for market/audience research: it consumes a
`ResearchRequest` and produces contract-conforming research artifacts —
`ResearchReport` and `MarketSignal[]` (each signal cites a captured source).

Design highlights (see `AGENTS.md` in the parent for the master rules):

- **Deterministic by construction** — ids are derived with uuid5
  (`agent_framework.ids.deterministic_id`), time comes from the injected
  context clock, and outputs are pure functions of the input. The same
  request always yields byte-identical artifacts.
- **LLM output is untrusted** — model JSON arrives router-validated and is
  sanitized field-by-field (shared `agent_framework.sanitize` helpers) before
  entering contract models; invented source ids are dropped, duplicate
  signals deduped by normalized description, entries capped.
- **Mock-first ($0 development)** — the default provider is the offline
  deterministic `MockLLMProvider` via the `ModelRouter`. No network, no
  credentials, no cost.
- **No privileged tools** — no publishing/scheduling authority; publishing
  belongs to the publishing subsystem only.

## Input / output contract

Input (validated against the `ResearchRequest` contract):

```json
{"request": {"request_id": "...", "run_id": "...", "focus": "...",
              "objectives": [], "creators": [], "domains": []}}
```

Output:

```json
{"report": {...}, "signals": [...]}
```

Fault injection (mock mode): documented prompt markers (`RATE_LIMIT`,
`TIMEOUT`, `NETWORK_FAILURE`, `AUTH_FAILURE`, `INVALID_OUTPUT`) make failure
paths deterministic in tests.

## Dependencies

Sibling child repositories (not PyPI-installable; resolved via
`tests/conftest.py` sys.path composition):

- `linkgen_contracts` — contract layer
- `linkgen_config` — settings/modes/cost policy
- `agent-framework` — AgentBase/AgentContext/AgentConfig + shared sanitizers
- `providers/llm` — ModelRouter (mock provider)

## Testing

    python -m pytest

Tests must not require network access, a paid provider, or the system clock.

## Status

Phase 08 — implemented (1.0.0). Original scaffold upgraded from Phase 00.5.
