# AGENTS.md — market-research (child repository)

## Owns
This repository owns its implementation, local tests, local documentation,
local configuration defaults, and local version history.

It is responsible for: market/audience research — producing `ResearchReport`
and `MarketSignal[]` artifacts for the research phase (Phase 08).

## Does NOT own
- Composition, orchestration, global configuration, system-wide documentation
  (the parent repository owns these).
- System-wide contracts and schemas (established in Phase 01).
- Implementation of other child repositories.

## Dependency direction (allowed)
Depends on explicit shared layers only:

- `linkgen_contracts` (contract layer)
- `linkgen_config` (settings/modes/cost policy)
- `agent-framework` (AgentBase/AgentContext/AgentConfig — ADR-013 shared
  framework for all agents, plus shared sanitizers)
- `providers/llm` (ModelRouter only — agents never import provider internals
  or adapters directly)

MUST NOT import parent implementation code (e.g. linkgen.system, "../..", or
any upward filesystem import).
MUST NOT import sibling agent implementation code (e.g. agent_creator_research).
No circular dependencies.

## Determinism expectations
- Ids derived deterministically (uuid5 via `agent_framework.ids`); never
  `uuid4` in agent logic.
- Time only via the injected context clock; never the system clock.
- No network, randomness, or commercial SDK imports in source.

## Testing expectations
- Run local unit tests with: python -m pytest
- Never weaken tests; never fake a passing result.
- Add regression tests for every bug fixed.

## Security expectations
- Never commit keys, tokens, cookies, credentials, browser sessions, or
  personal data.
- Use environment variables or a supported secret mechanism.
- Never log secrets.

## Cost constraints
- Mock-first development; $0 external spend is the default.
- No provider may be called accidentally; paid paths fail closed.

## Publishing authority
No publishing/scheduling authority; publishing privilege belongs to the publishing subsystem (publisher) only.
