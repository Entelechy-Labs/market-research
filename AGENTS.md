# AGENTS.md — market-research (child repository)

## Owns
This repository owns its implementation, local tests, local documentation,
local configuration defaults, and local version history.

It is responsible for: the specialist agent responsible for researching market and audience signals.

## Does NOT own
- Composition, orchestration, global configuration, system-wide documentation
  (the parent repository owns these).
- System-wide contracts and schemas (established in Phase 01).
- Implementation of other child repositories.

## Dependency direction (allowed)
Depends only on explicit shared contracts/interfaces (Phase 01+).
MUST NOT import parent implementation code (e.g. linkgen.system, "../..", or
any upward filesystem import).
MUST NOT import sibling child implementation code.
No circular dependencies.

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
