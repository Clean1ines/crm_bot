# Pilot v0.1 Architecture Baseline

Baseline: `0b1da59ab54d4ae8591da1a36f8ac50032fcd147`.

This document separates the actual architecture at the baseline commit from the target pilot architecture and the identified gaps.

## Actual Components At Baseline

| Component | Actual Current State | Target Pilot State | Gap |
|---|---|---|---|
| FastAPI HTTP app | Interfaces expose auth, projects, knowledge, chat, threads, webhooks. | Release-gated API with health/readiness and pilot smoke. | Health/readiness and deploy smoke are not release-proven. |
| Telegram client bot | Processes client updates, `/reset_dialog`, Redis TTL duplicate guard. S1.1 added the PostgreSQL inbox schema/repository boundary, but this runtime path is not switched to it yet. | Verified webhook, PostgreSQL durable inbox, effectively-once business processing, PostgreSQL same-thread lease, and minimal state CAS. | Direct dispatch/Redis behavior remains until S1.2; production lock not wired; no state revision. |
| Telegram manager bot | Handles callbacks and manager text. | Project/thread-bound manager actions. | Callback thread ID not bound to target thread project. |
| Frontend web panel | Owner/manager UI, channel settings, ticket detail. | Browser E2E-proven owner/manager flows. | E2E suite absent for pilot workflows. |
| Knowledge workbench | Upload, extraction, curation, publication surfaces. | Operator-approved knowledge publication smoke. | Release smoke and runbook not yet proven. |
| Agent runtime | LangGraph nodes load state, run rules, intent, RAG, response, persistence. | Runtime with PostgreSQL processing ownership, DB thread lease, minimal state revision/CAS, durable outbound intent, and eval evidence. | `NullThreadLock`/`NullCache` wiring and whole-state persistence race remain at baseline. |
| PostgreSQL | Primary source for projects, clients, threads, messages, events, knowledge, runtime state. S1.1 added nullable numeric Telegram bot ID storage and the `telegram_inbox_updates` table/repository boundary. | Authoritative source for Telegram update acceptance, processing lifecycle, thread execution lease, state revision/CAS, backup/restore, and smoke-tested DB. | Inbox schema/repository exists but is not wired to webhook/worker; thread lease, state revision, backup/restore, and migration gates are still missing. |
| Redis | Used by some locks, sessions, duplicate guards, queue/runtime patterns. | Optional acceleration/cache/wakeup/rate accounting layer with degraded behavior; not authoritative for Telegram intake or state correctness. | Production composition passes neither thread lock nor cache factory; Redis-only correctness is not acceptable. |
| LLM/Groq | Direct Groq completion client for ticket summaries plus broader runtime use. | Bounded timeout/failure/capacity policy. | Direct summary path lacks release-proven timeout/capacity policy. |

## Layers

- `src/domain`: pure domain contracts and policies.
- `src/application`: use cases, ports, orchestration.
- `src/infrastructure`: DB repositories, Redis, queue, LLM, Telegram HTTP adapter.
- `src/interfaces`: FastAPI routes, Telegram entrypoints, composition.
- `src/agent`: LangGraph runtime nodes/prompts/tools.
- `frontend`: React/Vite/TypeScript web panel and generated API client.

The baseline generally follows these boundaries, but some agent nodes still act as partial composition roots by importing concrete infrastructure.

## Composition Roots And Null Defaults

| Area | Actual Wiring | Gap |
|---|---|---|
| FastAPI lifespan | `src/interfaces/composition/fastapi_lifespan.py:168` constructs `ConversationOrchestrator(...)`. | No `thread_lock` argument and no `cache_factory` argument are passed. |
| Thread lock | `ConversationOrchestrator.__init__` uses `thread_lock or NullThreadLock()` at `conversation_orchestrator.py:98`. | Production client message processing uses `NullThreadLock`; target requires PostgreSQL thread execution lease, not Redis-only lock. |
| Runtime guards | `ProjectRuntimeGuards(cache_factory=cache_factory)` at `conversation_orchestrator.py:103`; `cache_factory` is absent from lifespan. | `_cache()` returns `NullCache()` when factory absent; `requests_per_minute` and `max_concurrent_threads` are not backed by Redis in production composition. |
| Redis lock implementation | `redis/lock.py` uses `SET key "1" NX EX ttl` and deletes by key. | TTL exists, but no owner token, lease renewal, or compare-before-delete release; in target it can only accelerate PostgreSQL ownership. |
| Telegram client | `HttpTelegramClient` is injected for sending. | It is not used by web token set paths for full webhook setup. |
| Ticket summary LLM | `ResponseCompletionConversationSummaryGenerator` with default `GroqTextCompletionClient`. | Direct provider path lacks release policy for timeout/retry/capacity. |

## Runtime Flows

### Client Telegram Question

Actual:

1. Telegram webhook enters HTTP/Telegram interface.
2. Client identity and thread are loaded/created.
3. `ClientMessageService` calls `thread_lock.acquire_thread_lock`.
4. In production composition, that lock is `NullThreadLock`, so any same-thread message can proceed.
5. Runtime graph loads `threads.state_json`, memory, recent messages, and knowledge.
6. Graph produces answer, handoff, or fallback and persists messages/state/events.
7. `save_state_json` writes the whole JSON document.

Target: PostgreSQL durable update acceptance, PostgreSQL processing claim, PostgreSQL same-thread execution lease, minimal state revision/CAS, and durable outbound intent before Telegram delivery. Redis may accelerate duplicate lookup or accounting, but Redis outage must not stop intake when PostgreSQL is available.

Gap: Two messages for the same thread before first completion can concurrently load stale state and overwrite each other; there is no durable Telegram inbox, no DB execution lease, no state revision, and no durable outbound intent for this runtime path.

### Web Settings Telegram Onboarding

Actual web path:

`ChannelSettingsPage` -> `projectsApi.setBotToken/setManagerToken` -> `POST /api/projects/{project_id}/bot-token` or `/manager-token` -> `ProjectCommandService.set_client_bot_token/set_manager_bot_token` -> repository token persistence -> `project_channels.status='active'`.

Actual side effects:

- token normalized and rejected if platform-admin token;
- best-effort `getMe` only through repository username lookup;
- encrypted token persisted;
- channel marked active;
- no webhook secret generation/rotation;
- no Telegram `setWebhook`;
- no webhook functionality verification.

Target: active only after verified token, rotated secret, successful `setWebhook`, and inbound secret verification, or explicitly non-active credential-only state.

### Telegram Platform-Admin Onboarding

Actual platform-admin path:

- verifies token via `getMe`;
- generates client/manager webhook secrets;
- persists token and secret;
- calls Telegram `setWebhook` with `secret_token`;
- upserts channel active with webhook URL.

Target: keep this path separate from web settings and document operator ownership.

### Manager Ticket Flow

Actual:

- Manager webhook verifies manager membership for webhook project.
- Callback payload contains bare `thread_id`.
- Claim/close repository updates by `threads.id` only.

Target: load target thread, verify target project, validate manager in target project, scope SQL mutation by project.

## Sources Of Truth And Persistence

| Data | Source Of Truth | Notes |
|---|---|---|
| Project and channels | `projects`, `project_channels` | Web settings active state can be over-optimistic. |
| Telegram secrets | `projects.webhook_secret`, `projects.manager_webhook_secret` | Platform-admin path writes; web settings path does not rotate/create. |
| Client identity | `clients(project_id, chat_id)` plus `source` column | Source not in uniqueness; P3 debt before future channels. |
| Thread lifecycle | `threads.status`, manager columns | Status free text; close not one idempotent contract. |
| Messages/events | `messages`, `events` | Used as audit and runtime context. |
| Runtime state | `threads.state_json` | Whole document save for graph state; resolution CAS only for subdocument. |
| Ticket resolution | `threads.state_json.ticket_resolution`, `context_summary` | No dedicated resolution table at baseline. |
| Telegram update acceptance | S1.1 implements `migrations/132_create_telegram_inbox.sql`, `telegram_inbox_updates`, `TelegramUpdateIdentity`, `PostgresTelegramInboxRepository`, and project/platform numeric Telegram bot-ID storage. Current webhooks/handlers still do not use this source of truth. | Target source of truth is PostgreSQL durable inbox for client, manager, and platform-admin updates. |
| Thread execution ownership | `ThreadLockPort` call, defaulting to `NullThreadLock` in production | Target source of truth is PostgreSQL row/table-backed execution lease with owner token and expiration. |
| State revision | none for whole `state_json` | Target source of truth is PostgreSQL revision/CAS; whole-document JSON may remain physical storage only with CAS. |
| Outbound delivery intent | direct Telegram send paths and tool calls | Target source of truth is durable outbound intent/result before/after external Telegram delivery. |
| Runtime limits | project settings and runtime guard cache | Not Redis-backed in production composition; target uses Redis-backed accounting or approved fallback with degraded guarantee semantics. |

## Queues, Redis, LLM, Telegram, Frontend/OpenAPI

- Queues/events exist for runtime side effects, and a PostgreSQL-backed work-item runtime exists for knowledge/RAG flows; target Telegram update processing uses a separate PostgreSQL inbox and worker, not the knowledge/RAG work-item lifecycle.
- S1.1 implements the separate Telegram inbox schema and repository lifecycle primitives: insert-or-read-existing, duplicate/anomaly diagnostics, claim, renew, expired-row discovery/reclaim, complete, retryable failure, terminal failure, ownership validation, and attempt accounting. These primitives are not yet called by webhook intake or a worker.
- Redis is used for manager sessions and intended guards/locks, but target pilot correctness must remain PostgreSQL-owned; Redis is optional acceleration/accounting with degraded behavior.
- LLM summary generation uses Groq and strict JSON parsing; timeout/capacity policy is not release-proven.
- Telegram inbound webhook verification exists via secret token checks; setup differs by onboarding path.
- Frontend generated TypeScript schema is tracked, but canonical OpenAPI JSON artifacts are ignored; browser E2E is missing.

## Target Runtime Flow For Telegram Updates

Target, partially implemented after S1.1 only at schema/repository level:

1. Webhook request verifies the Telegram surface secret.
2. Webhook request performs minimal structural validation and builds identity from surface/role, stable project or platform scope, and Telegram `update_id`.
3. Webhook request atomically inserts or upserts the PostgreSQL inbox row.
4. Webhook request returns Telegram 2xx only after durable acceptance, or retriable non-2xx with no business side effects when PostgreSQL acceptance fails.
5. Dedicated Telegram inbox worker claims accepted work with lease and attempt metadata.
6. Worker dispatches the client, manager, or platform handler.
7. Client conversation work acquires PostgreSQL thread execution lease.
8. Runtime state and revision are loaded.
9. Runtime/LLM processing runs without holding one DB connection for the whole LLM call.
10. Messages, events, state revision update, lifecycle mutations, and durable outbound intent are committed before final Telegram response delivery.
11. Outbound delivery executes from durable intent and persists result or ambiguity.
12. Telegram inbox lifecycle reaches completed, retryable failed, or terminal failed.

S1.1 implements the persistence objects needed by steps 2, 3, 5, and 12, but only as repository/schema primitives. Durable runtime intake starts in S1.2, and S1.1 does not prove NFR-03, AT-NFR-03, AT-S1-01, AT-S1-02, or full S1 release readiness.

## Trust And Tenant Boundaries

- HTTP thread routes generally derive project from thread before manager access checks.
- Telegram manager callbacks currently trust webhook project membership but mutate target `thread_id` without target project binding.
- Telegram tokens, authorization headers, webhook secrets, decrypted credentials, and passwords must not be logged.
- Prior manager resolutions are same project/client scoped, but must be treated as untrusted client-facing data.

## Failure Boundaries

- LLM failures should result in bounded failed/missing resolution, not hanging close.
- Redis outage currently weakens duplicate guard and would affect current intended lock/guard behavior; target behavior keeps intake and thread correctness through PostgreSQL while marking runtime-limit accounting degraded.
- PostgreSQL outage means Telegram updates cannot be durably accepted; target behavior returns retriable non-2xx and performs no business side effects.
- Process restart can lose volatile Redis manager sessions; target Telegram intake and processing recovery must use PostgreSQL lifecycle and lease expiration.
- LLM/provider outage must not stop Telegram intake; accepted work becomes retryable failed, controlled fallback, or handoff.
- Migration crash after DDL before marker is not proven recoverable.
- Backup/restore is not repo-backed by an executable pilot runbook.

## Legacy, Dead, Or Partial Paths

- Website/widget and non-Telegram channels are out of pilot scope even if code/UI fragments exist.
- Web settings token path is partial onboarding, not full Telegram connection.
- Platform-admin Telegram onboarding is fuller but separate and operator-owned.
- Direct Groq summary path is a partial legacy/provider path relative to generic LLM runtime policy.

## Proposed ADR Set

| ADR Topic | Why Needed | Must Be Accepted Before |
|---|---|---|
| ADR-0003: Conversation/runtime state ownership and DB lease/CAS | Define PostgreSQL ownership of history, `state_json`, memory, summaries, execution lease, CAS, and conflict behavior. | S1/S5 |
| Telegram onboarding lifecycle | Define web settings vs platform-admin responsibilities, active state, secret rotation, and rollback. | S4 |
| ADR-0002: Telegram update idempotency and durable intake | Define dedicated PostgreSQL Telegram inbox, worker boundary, Redis outage behavior, duplicate callbacks, replay, processing lifecycle, and outbound intent semantics. | S1/S3 |
| Manager action tenant binding | Define target-thread project binding and SQL scoping for Telegram manager actions. | S2 |
| Ticket close and resolution lifecycle | Define one idempotent close contract, events, analytics reset, resolution phases, and retries. | S3/S6 |
| LLM completion policy | Define provider, timeout, retry, capacity, quota, and failure semantics. | S7 |
| Migration/backup/rollback policy | Define transaction/marker semantics, backup gates, restore drill, and rollback decision points. | S8 |
| Business events and case identity | Define pilot metrics, case identity, event names, and analytics source of truth. | S9 |
| Channel/client identity model | R1 is accepted as Telegram-only architecture debt, but `(project_id, chat_id)` must be revisited before website widget or non-Telegram channels are enabled. | Before any post-pilot multi-channel slice |

## Existing ADR Status

- `docs/adr/0001-canonical-workbench-rag-eval-v2-workflow.md` remains relevant for Workbench RAG Eval but is partially stale for current checkpoint/status tracking.
- `docs/adr/README.md` now indexes ADR-0001, ADR-0002, and ADR-0003.
