# market-research

Agent component of the LINKGEN content-intelligence and publishing system.

## Purpose
Agent repository: the specialist agent responsible for researching market and audience signals.

## Ownership
Owns its implementation, local tests, local documentation, and local version
history. Does NOT own composition, orchestration, global configuration, or
system-wide contracts (those belong to the parent repository).

## Status
Foundation scaffold only. Production implementation has NOT begun.

## Architectural role
Independently versioned repository composed by the parent. It must depend only
on explicit shared contracts/interfaces (to be established in Phase 01), never
on parent or sibling implementation code.

## Dependency rules
- MUST NOT import parent implementation or sibling child implementation.
- No circular dependencies.
- Keep provider-specific code behind provider abstractions.

## Testing
Run local tests with:

    python -m pytest

## Current phase
Phase 00.5 — child repository bootstrap. No production functionality yet.

## Publishing authority
No publishing/scheduling authority; publishing privilege belongs to the publishing subsystem (publisher) only.
