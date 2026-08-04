# ADR-0002: Durable Telegram Update Intake and Idempotent Processing

Date: 2026-08-04
Status: proposed
Deciders: crm_bot maintainers; project owner approval pending

## Context

The pilot accepts mutating Telegram updates from client, manager, and platform-admin bot surfaces. At baseline, client update dedupe is Redis TTL based (`processed_update:{update_id}`), manager/platform paths do not share one durable inbox, and Telegram webhook acknowledgement can be coupled to non-durable runtime handling. Owner constraints require Telegram intake to continue when Redis is down but PostgreSQL is available, while PostgreSQL outage must prevent unsafe acceptance and side effects.

## Decision

Use a dedicated PostgreSQL Telegram inbox as the authoritative intake and processing lifecycle for all mutating Telegram updates, with optional Redis acceleration. Telegram updates are processed by a dedicated Telegram inbox processor/worker, not by the knowledge/RAG execution-runtime domain work-item lifecycle or its capacity semantics.

Project client and manager bot update identity is `(telegram_surface_or_role, project_id, stable_non_secret_telegram_bot_account_identity, telegram_update_id)`. The preferred bot account identity is the numeric Telegram bot ID returned by `getMe` and persisted during onboarding. A persisted internal bot-generation identity is acceptable only if it changes unambiguously whenever the Telegram bot account is replaced. `project_id + bot role + update_id` alone is insufficient because a replacement Telegram bot account can deliver an `update_id` already seen for the old account. Platform-admin update identity must likewise include a stable non-secret Telegram bot account identity or generation identity, not only a permanent platform scope. Raw bot tokens, token hashes, webhook secrets, and other secret values must never be part of update identity.

The durable lifecycle must include states equivalent to `received`, `processing`, `completed`, `retryable_failed`, and `terminal_failed`. Processing ownership stores an owner or lease identity, lease expiration, attempt count, timestamps, and bounded error metadata. A webhook returns 2xx only after durable PostgreSQL acceptance and does not run full graph/LLM runtime inside the HTTP request.

Webhook request handling is limited to secret verification, minimal structural update validation, stable update identity construction, atomic PostgreSQL INSERT of the durable inbox row, and returning Telegram 2xx after durable acceptance. If PostgreSQL durable acceptance fails, the webhook returns retriable non-2xx and performs no business side effects.

Initial intake uses an atomic insert contract. The preferred SQL shape is `INSERT ... ON CONFLICT DO NOTHING` followed by reading the existing row on uniqueness conflict, although an equivalent repository-level atomic contract is acceptable. A uniqueness conflict must not reset or overwrite the existing lifecycle. Duplicate webhook delivery reads the existing record and returns a safe 2xx when the update has already been durably accepted. Duplicate delivery must not change status, owner, lease, attempts, completion, failure, payload, or outbound state. Only diagnostic fields such as `duplicate_count` or `last_duplicate_at` may be updated, and only when they cannot affect processing lifecycle. A differing payload for the same update identity is recorded as an anomaly and must not replace the original stored payload. Lifecycle reset through a broad upsert is explicitly prohibited.

The dedicated inbox worker claims accepted updates, renews or reclaims processing lease, dispatches the corresponding client, manager, or platform handler, performs idempotent internal mutations, creates durable outbound intent, and records `completed`, `retryable_failed`, or `terminal_failed`. Process crash after webhook 2xx is recovered by this worker lifecycle.

Business processing is effectively-once, not externally exactly-once. The inbox contract creates one durable logical update, permits at most one active processing owner, allows retry attempts only serially after failure or lease expiry, and must yield one effectively-once internal business outcome. Attempt count increases only when a worker starts a real new processing attempt; duplicate webhook delivery never resets or increments attempts by itself. Inbox dedupe is necessary but not sufficient: message persistence, handoff creation, manager claim, manager close, ticket resolution scheduling, event creation, and outbound Telegram delivery intent need their own durable idempotency or persistence guard when retry can repeat them.

## Alternatives Considered

### Current Redis `exists -> setex` dedupe

- Advantages: already present for the client bot and cheap for normal duplicate lookup.
- Disadvantages: non-atomic, not project/bot scoped, unavailable on Redis outage, and not shared by manager/platform handlers.
- Why not: it cannot be the authoritative pilot intake contract.

### Atomic Redis `SET NX EX` as the only inbox

- Advantages: simple, fast, and better than `exists -> setex` for duplicate races.
- Disadvantages: Redis outage would stop or weaken intake, TTL expiry loses durable history, and ownership/recovery metadata is volatile.
- Why not: owner constraints explicitly reject Redis as sole authority for duplicate and processing ownership.

### In-memory dedupe

- Advantages: minimal implementation cost.
- Disadvantages: lost on restart, process-local, and incompatible with multi-process pilot traffic.
- Why not: it cannot provide durable acceptance or recovery.

### PostgreSQL durable inbox

- Advantages: durable acceptance, unique identity guarantee, process restart recovery, explicit processing lifecycle, and same datastore boundary as business state.
- Disadvantages: requires schema/repository work and careful lifecycle tests.
- Why selected: it satisfies the owner constraints with the smallest durable correctness boundary.

### PostgreSQL inbox with Redis acceleration

- Advantages: preserves PostgreSQL authority while allowing fast duplicate lookup, wakeups, counters, and cache behavior when Redis is healthy.
- Disadvantages: introduces degraded-mode semantics and requires tests for Redis unavailable paths.
- Why selected: this is the pilot target because it supports performance without making Redis a correctness authority.

### Rely only on idempotent downstream operations without inbox

- Advantages: avoids a new intake table.
- Disadvantages: every downstream path would need to independently solve duplicate acceptance, processing ownership, retry, and crash recovery.
- Why not: it is broader, harder to verify, and does not give operators a single durable update lifecycle.

## Consequences

### Positive

- Telegram duplicate delivery and process restart recovery have one durable source of truth.
- Webhook acknowledgement is decoupled from full graph/LLM runtime while still remaining durable.
- Redis outage does not by itself reject updates when PostgreSQL is available.
- LLM/provider failure can be recorded as retryable, fallback, or handoff after durable acceptance.
- Operators can inspect stuck, retryable, and terminal update work.

### Negative

- S1 needs migrations for inbox identity, status, ownership, attempts, and error metadata.
- Existing Telegram handlers must be refactored so webhook intake is thin and business processing runs from the inbox worker.
- Release tests must simulate PostgreSQL outage, Redis outage, duplicate delivery, and restart recovery.

### Risks

- Incorrect identity scope could dedupe unrelated updates or allow duplicates across bot roles.
- Treating outbound `sendMessage` as exactly-once would overstate Telegram guarantees.
- If processing is acknowledged without durable recovery, crashes can still lose accepted updates.

## Implementation Boundaries

- PostgreSQL is the authoritative inbox and lifecycle owner for client bot, manager bot, and platform-admin updates.
- Telegram update processing uses a dedicated PostgreSQL Telegram inbox processor/worker.
- Telegram update processing is not included in the knowledge/RAG execution runtime, work-item lifecycle, or capacity semantics.
- Neutral lease/retry primitives are allowed only when they do not import knowledge/RAG vocabulary or capacity policy into Telegram processing.
- Redis may provide fast duplicate lookup, cache, notification, wakeup, rate counters, and performance optimization.
- Redis must not be the authoritative inbox, sole processing owner, or sole business side-effect guard.
- The webhook boundary must not run full graph/LLM runtime in the HTTP request.
- Do not include raw Telegram tokens, webhook secrets, or other secrets in idempotency keys.

## Failure And Recovery Semantics

- PostgreSQL down: the update is not accepted, no business side effects run, and Telegram receives a retriable non-2xx response.
- Redis down: the update is durably accepted in PostgreSQL and remains recoverable; degraded state is logged or metered.
- LLM/provider down: the accepted update reaches retryable failure, controlled fallback, or manager handoff according to scenario policy.
- Worker restart: uncompleted work is recovered from the dedicated PostgreSQL Telegram inbox lifecycle after lease expiration.
- Duplicate delivery: no second durable logical update is created; already accepted updates may be acknowledged without changing lifecycle, ownership, attempts, completion, failure, payload, or outbound state.
- Permanent invalid update: terminal state is recorded without infinite retry.
- Network-ambiguous Telegram `sendMessage`: internal processing remains idempotent, but an externally duplicated message remains an explicit residual risk.

## Validation

- Concurrent duplicate webhook attempts for the same update create one durable inbox row, at most one active processing owner, and one effectively-once internal business outcome; serial retry attempts may occur only after failure or lease expiry.
- A duplicate update after process restart is recognized through PostgreSQL.
- Replacing a project Telegram bot account does not collide with update IDs from the old bot account because update identity includes the stable non-secret bot account identity or generation identity.
- Duplicate delivery for completed, processing, or failed updates never returns lifecycle to `received` or `processing`, never changes owner/lease, and never resets attempts or error state.
- A differing payload for an existing update identity records an anomaly and preserves the original payload.
- Redis unavailable before intake does not prevent durable acceptance when PostgreSQL is available.
- PostgreSQL unavailable returns retriable non-2xx and performs no business side effects.
- Worker crash after claim is recovered by the dedicated Telegram inbox worker after lease expiration.
- Outbound delivery retry records intent/result and documents residual duplicate policy.

## References

- `src/interfaces/telegram/client_bot.py`
- `src/interfaces/telegram/manager_bot.py`
- `src/application/services/webhook_dispatcher.py`
- `src/contexts/execution_runtime/README.md` as a reference for neutral lease/retry concepts only, not as the Telegram update-processing lifecycle.
- `docs/releases/pilot-v0.1/RISK_REGISTER.md`
