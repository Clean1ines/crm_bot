# ADR-0001: Layered architecture with strict dependency boundaries

**Date**: 2026-05-24
**Status**: accepted
**Deciders**: _neverjune_, Codex

## Context

`crm_bot` combines critical runtime orchestration (Telegram + HTTP), knowledge compilation/RAG, and multi-tenant administration.
Without explicit boundaries, platform code tends to collapse into framework-coupled service code that is difficult to test, reason about, and safely evolve.

The project already exposes a de-facto structure (`src/domain`, `src/application`, `src/infrastructure`, `src/interfaces`, `src/agent`) and architecture tests that enforce import constraints.
This ADR formalizes that structure as a non-negotiable architecture contract.

## Decision

Adopt and enforce a strict layered architecture:

1. `src/domain`
   - Pure domain logic and contracts only.
   - No FastAPI/Starlette, DB drivers, Redis clients, Telegram SDKs, queue clients, LLM SDKs, or infrastructure imports.
2. `src/application`
   - Use-cases, orchestration, DTOs, and ports.
   - Depends on domain; does not directly own framework wiring.
3. `src/infrastructure`
   - Adapters/implementations for persistence, queue, Redis, external APIs, LLM/embeddings.
   - Must not import concrete `src.agent` runtime modules; runtime composition is external.
4. `src/interfaces`
   - HTTP/Telegram transport layer, request/response boundaries, auth/session edges.
5. `src/agent`
   - Agent graph runtime assembly and node wiring.
   - Wired from composition root, not imported by domain logic.

Enforcement strategy:
- Keep architecture guard tests as hard quality gates.
- Treat boundary drift as a defect, not a style preference.

## Alternatives Considered

### Alternative 1: Feature-sliced vertical modules only

- **Pros**: High local cohesion per feature.
- **Cons**: Easy to leak transport/infrastructure concerns into core behavior.
- **Why not**: Current product risk profile requires stronger portability and testability guarantees around domain/runtime behavior.

### Alternative 2: Single service layer (thin domain)

- **Pros**: Faster short-term delivery.
- **Cons**: Reduced clarity of contracts, harder refactor safety, difficult deterministic testing.
- **Why not**: Conflicts with long-term maintainability and architecture governance goals.

## Consequences

### Positive

- Stronger isolation of business logic from frameworks and vendor SDKs.
- Better testability of domain/application layers.
- Reduced accidental coupling during refactors.

### Negative

- Higher discipline cost: engineers must route changes through ports/composition boundaries.
- Slightly more boilerplate for adapter and DTO boundaries.

### Risks

- If tests are weakened or skipped, boundary erosion can still occur.
- New contributors may misplace code without onboarding and examples.
