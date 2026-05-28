# ADR: Groq quota state and free-tier LLM routing

Date: 2026-05-28

## Status

Accepted

## Context

Knowledge ingestion uses Groq-hosted LLMs through three optional API keys:
`GROQ_API_KEY`, `GROQ_API_KEY2`, and `GROQ_API_KEY3`.
The production constraint is unusual: the app must make progress on Render free tier and Groq free tier without burning repeated failed requests when a key/model route is already known to be cooling down.

The previous routing model was instant-first and bounded, but mostly process-local:

- every compiler request started from `llama-3.1-8b-instant`;
- request-size/context failures could move to larger fallback models;
- minute/day failures disabled a model only inside the current call;
- API key rotation happened after a route chain failed;
- cooldown state was lost across worker tasks, worker loops, and restarts.

That was safer than blind retries, but still weak for long ingestion jobs.

## Decision

Introduce a route quota state layer for Groq key/model routes.

A route is identified by:

- provider: `groq`;
- a short SHA-256 hash prefix of the API key;
- key slot metadata for logs/UI diagnostics;
- model id.

The raw API key is never stored in the quota key or state payload.

The quota state is stored in Redis when `REDIS_URL` is configured and falls back to in-process memory otherwise. Redis is chosen for this first step because the queue worker already has Redis as an optional infrastructure component and route cooldown is operational state, not domain knowledge.

On provider failures:

- daily request/token limits get a long cooldown;
- minute request/token limits get a shorter cooldown;
- temporary provider failures get a short cooldown;
- request-size/context errors are not stored as quota cooldowns because they should trigger payload/model fallback, not key suppression.

Before a real Groq request, the route checks existing quota state:

- short cooldowns may be awaited locally;
- long cooldowns raise a 429-like preflight block with `retry_after`, allowing existing router/queue retry logic to avoid hammering the provider.

## Consequences

Positive:

- repeated jobs can avoid known exhausted routes when Redis is configured;
- raw secrets are not persisted;
- existing instant-first and model fallback behavior remains intact;
- the change is infrastructure-local and does not leak Groq concepts into the domain layer.

Trade-offs:

- without Redis, state is still process-local;
- this does not yet implement durable source-unit resume;
- this does not yet implement an economy-mode compiler that automatically re-splits all failed large-model work into llama-instant subunits;
- Groq response rate-limit headers are not yet fully persisted as remaining/reset counters.

## Follow-up work

1. Add durable source-unit checkpoints for FAQ surface compilation.
2. Add economy-mode source-unit splitting for llama-instant-only completion after large-model daily limits.
3. Add project/document LLM budget guards.
4. Add frontend display for route cooldown/reset estimates.
5. Reduce frontend polling to a single aggregated progress endpoint during active ingestion.
