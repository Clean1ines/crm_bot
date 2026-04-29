# Performance Rules

Performance regressions are code quality regressions.

## Imports

Avoid heavy module-level imports in app startup paths.

Use lazy imports for:
- LLM SDKs;
- LangGraph or heavy graph runtime dependencies;
- PDF libraries;
- embedding libraries;
- ML libraries;
- large optional integrations.

Plain app import should remain lightweight.

## Hot paths

Do not add unnecessary work to:
- webhook handlers;
- graph node execution;
- response generation;
- persistence;
- queue workers;
- repository methods called per message.

## Bounds

Use explicit limits for:
- history in prompts;
- knowledge chunks;
- memory items;
- file size;
- loop counts;
- retries;
- API result counts.

## Database

Avoid:
- N+1 queries;
- unbounded scans;
- repeated writes for unchanged state;
- missing project/client scoping.

Prefer:
- indexed lookups;
- batched queries;
- upserts where appropriate;
- minimal selected columns;
- deterministic ordering.

## LLM calls

LLM calls are expensive and failure-prone.

Do not add extra calls unless clearly justified.

Prefer:
- enriching existing structured extraction;
- deterministic post-processing;
- compact prompts;
- reusing existing state.

## Caching

Add caching only when:
- correctness is clear;
- invalidation is understood;
- stale data is acceptable or controlled;
- the cache does not hide errors.

## Validation

When changing performance-sensitive areas:
- inspect import paths;
- inspect query behavior;
- inspect loop behavior;
- run relevant tests;
- avoid speculative optimization that complicates code.
