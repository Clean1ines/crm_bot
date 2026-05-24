# ADR-0003: OpenAPI-first backend/frontend contract discipline with drift gate

**Date**: 2026-05-24
**Status**: accepted
**Deciders**: _neverjune_, Codex

## Context

The frontend API client is generated from backend OpenAPI artifacts.
Contract drift between backend route/schema changes and generated frontend types creates runtime errors, broken UI flows, and invalid assumptions in feature work.

The repository already has generation tooling (`scripts/generate_openapi.py`, `npm run generate:openapi`) but lacked an explicit mandatory gate requiring generated artifacts to be up to date.

## Decision

Adopt OpenAPI-first contract discipline:

1. Backend API changes must update OpenAPI artifacts in the same change.
2. Frontend generated schema (`frontend/src/shared/api/generated/schema.ts`) must remain synchronized with backend OpenAPI output.
3. Quality gate must include a required "generate + no-drift" check:
   - run OpenAPI generation;
   - fail if tracked generated artifacts change afterward.
4. Contract drift is treated as a hard failure for commit readiness.

Artifacts under drift control:
- `openapi.json`
- `frontend/openapi.json`
- `frontend/src/shared/api/generated/schema.ts`

## Alternatives Considered

### Alternative 1: Manual client updates without generation gate

- **Pros**: Fewer gate steps.
- **Cons**: Frequent silent drift and delayed breakage discovery.
- **Why not**: Too risky for multi-surface production workflow.

### Alternative 2: Frontend hand-written API types only

- **Pros**: No code generation dependency.
- **Cons**: High maintenance cost, mismatch risk, duplicated schema semantics.
- **Why not**: Contradicts source-of-truth contract approach.

## Consequences

### Positive

- Early detection of backend/frontend API contract drift.
- More reliable type safety and integration behavior.
- Clear developer workflow for API changes.

### Negative

- Slightly longer quality gate runtime.
- Requires Node/npm availability in environments running full gate.

### Risks

- Flaky generation environment (toolchain mismatch) can produce noisy diffs.
- Engineers may bypass gate locally if they do not run the canonical script.
