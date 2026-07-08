# execution_queue Migration Audit

## Executive Summary

- current status: `execution_queue` is an old active queue subsystem, not current Workbench runtime authority. It is still used by bot escalation/manager notification and metrics paths.
- safe to delete now? no.
- recommended path: leave as `TRANSITIONAL_BLOCKER` until active jobs are migrated to `execution_work_items`; then delete the queue runtime/table in a later patch.
- biggest blockers:
  - `notify_manager` is still produced by live client/agent/tool paths and consumed by the queue dispatcher.
  - `update_metrics` is still produced by agent persist/escalation paths and consumed by the metrics handler.
  - `aggregate_metrics` is still produced by the admin metrics endpoint and consumed by the metrics handler.
  - `technical_incident` is produced by `src/agent/nodes/persist.py:109` but is not registered in `src/infrastructure/queue/job_types.py:11` and is not handled by `src/infrastructure/queue/job_dispatcher.py:37`.
  - FastAPI lifespan wires queue producers but does not start the old queue worker; `src/infrastructure/queue/runtime.py:132` is a separate worker entrypoint.

Search commands run:

```text
rg -n -e execution_queue -e QueueRepository -e queue_repository -e QueueRepositoryPort -e public.execution_queue src tests migrations
rg -n -e JobDispatcher -e job_dispatcher -e job_types -e run_worker_loop -e worker_loop -e stale_recovery -e recover_stale -e QueueRuntime -e claim_next -e mark_completed -e mark_failed src tests
rg -n -e enqueue -e enqueue_task -e queue_repo -e queue_repository -e QueueRepositoryPort -e task_type -e job_type -e manager_notification -e escalat -e EscalateTool -e claim_queued -e next_attempt_at src tests
rg -n -e TASK_NOTIFY_MANAGER -e TASK_UPDATE_METRICS -e TASK_AGGREGATE_METRICS -e notify_manager -e update_metrics -e aggregate_metrics src tests
rg -n -e queue -e execution_queue -e pending_jobs -e failed_jobs -e manager_notification -e metrics src/interfaces/http frontend tests
rg -n -e execution_work_items -e execution_work_item_schedules -e execution_work_item_attempts -e execution_work_item_attempt_dispatches migrations
rg -n -e work_kind -e schedule_payload -e lease -e attempt -e dispatch -e next_attempt_at src/contexts/execution_runtime src/interfaces/composition tests/contexts/execution_runtime
```

## Current Queue Architecture

### Table

- table: `public.execution_queue`.
- columns used:
  - `id`, `task_type`, `payload`, `status`, `attempts`, `max_attempts`, `next_attempt_at`, `created_at`, `updated_at`: inserted by `QueueRepository.enqueue` at `src/infrastructure/db/repositories/queue_repository.py:45`.
  - `locked_at`, `worker_id`: set when claiming jobs at `src/infrastructure/db/repositories/queue_repository.py:68`.
  - `error`: written on completion/failure at `src/infrastructure/db/repositories/queue_repository.py:128` and `src/infrastructure/db/repositories/queue_repository.py:241`.
- statuses:
  - `pending`: inserted at `src/infrastructure/db/repositories/queue_repository.py:49`; used for due claims at `src/infrastructure/db/repositories/queue_repository.py:77`.
  - `processing`: set by claim at `src/infrastructure/db/repositories/queue_repository.py:70`; stale recovery searches this status at `src/infrastructure/db/repositories/queue_repository.py:323`.
  - `done`: set by `complete_job` when `success=True` at `src/infrastructure/db/repositories/queue_repository.py:120`.
  - `failed`: set by `complete_job` or exhausted retry logic at `src/infrastructure/db/repositories/queue_repository.py:120` and `src/infrastructure/db/repositories/queue_repository.py:248`.
- retry/stale semantics:
  - due gating uses `next_attempt_at IS NULL OR next_attempt_at <= NOW()` at `src/infrastructure/db/repositories/queue_repository.py:78`.
  - max attempts are enforced in claim at `src/infrastructure/db/repositories/queue_repository.py:79` and failure at `src/infrastructure/db/repositories/queue_repository.py:249`.
  - stale processing jobs are detected by `locked_at` at `src/infrastructure/db/repositories/queue_repository.py:322` and released by `src/infrastructure/queue/stale_recovery.py:21`.
  - retry backoff is calculated in `src/infrastructure/queue/retry_policy.py:71`.

DB evidence:

- `migrations/002_add_execution_queue.sql:2` creates `execution_queue`.
- `migrations/012_improve_execution_queue.sql:5` adds attempts/retry/lock fields.
- `migrations/052_add_model_usage_events_and_queue_schedule.sql:26` adds `next_attempt_at`.
- `migrations/998_rescue_restore_execution_queue_next_attempt_at.sql:1` restores `next_attempt_at`.

### Repository methods

| Method | Called by | Semantics | Classification |
|---|---|---|---|
| `enqueue` | `client_message_service`, `escalate`, `persist`, `EscalateTool`, metrics endpoint | durable job insert | TRANSITIONAL_BLOCKER |
| `claim_job` | `run_worker_loop` | atomically lease one pending due job | MIGRATE_TO_EXECUTION_WORK_ITEMS |
| `complete_job` | `run_worker_loop` | mark terminal success/failure | MIGRATE_TO_EXECUTION_WORK_ITEMS |
| `release_job` | `recover_stale_jobs` | release stale processing job | MIGRATE_TO_EXECUTION_WORK_ITEMS |
| `retry_job_without_attempt_increment` | no active caller found in searched paths | retry without attempt increment | HIGH_RISK_NEEDS_DECISION |
| `fail_job` | `run_worker_loop` | increment attempts and reschedule or fail | MIGRATE_TO_EXECUTION_WORK_ITEMS |
| `increment_attempts` | no active caller found in searched paths | raw attempt increment | DELETE_DEAD_QUEUE_PATH |
| `get_stale_locked_jobs` | `recover_stale_jobs` | find expired processing locks | MIGRATE_TO_EXECUTION_WORK_ITEMS |

### Worker lifecycle

- startup:
  - `src/infrastructure/queue/runtime.py:132` defines `main()` for a separate queue worker process.
  - `src/infrastructure/queue/worker.py:3` re-exports `main` and `worker_loop`.
  - `src/interfaces/composition/fastapi_lifespan.py:165` registers built-in tools and `src/interfaces/composition/fastapi_lifespan.py:166` builds the orchestrator, but only starts the knowledge workflow runtime at `src/interfaces/composition/fastapi_lifespan.py:167`. No FastAPI startup call to `run_worker_loop` was found.
- shutdown:
  - separate worker runtime handles SIGTERM/SIGINT at `src/infrastructure/queue/runtime.py:136`.
  - FastAPI shutdown only cancels `knowledge_workflow_runtime_task` at `src/interfaces/composition/fastapi_lifespan.py:201`.
- stale recovery:
  - `run_worker_loop` calls `recover_stale_jobs` every loop at `src/infrastructure/queue/worker_loop.py:37`.
  - `recover_stale_jobs` releases stuck jobs at `src/infrastructure/queue/stale_recovery.py:21`.
- dispatcher:
  - hardcoded task dispatch in `src/infrastructure/queue/job_dispatcher.py:37`.
  - unknown task types raise `PermanentJobError` at `src/infrastructure/queue/job_dispatcher.py:67`.

## Job Type Inventory

| Job type | Producers | Consumers | Payload | Required today? | Classification | Target |
|---|---|---|---|---|---|---|
| `notify_manager` | `client_message_service`, `escalate` node, `EscalateTool` | `handle_notify_manager` | `thread_id`, `project_id`, message/reason, optional manager selectors | yes, bot/escalation manager notification | TRANSITIONAL_BLOCKER | MIGRATE_TO_EXECUTION_WORK_ITEMS |
| `update_metrics` | `escalate` node, `persist` node | `handle_update_metrics` | `thread_id`, optional message counts, escalation flag, resolution time, close flag | yes, current metrics side effect | TRANSITIONAL_BLOCKER | MIGRATE_TO_EXECUTION_WORK_ITEMS |
| `aggregate_metrics` | admin metrics HTTP endpoint | `handle_aggregate_metrics` | `date` | yes if admin metrics aggregation remains supported | TRANSITIONAL_BLOCKER | MIGRATE_TO_EXECUTION_WORK_ITEMS |
| `technical_incident` | `persist` node | none found; dispatcher treats it as unknown | `project_id`, `thread_id`, `client_id`, failure metadata | no proven working consumer | DELETE_DEAD_QUEUE_PATH | delete producer or add deliberate replacement decision |

## Producer Map

- `src/application/orchestration/client_message_service.py:501`
  - job type: `notify_manager`.
  - payload: `thread_id`, `project_id`, `message`, `target_manager_telegram_chat_id`, `manager_user_id`.
  - current behavior: redirects new client message to an active manager reply session.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: schedule `execution_work_items` with a bot/manager-notification `work_kind`; handler can reuse notification logic.

- `src/agent/nodes/escalate.py:105`
  - job type: `notify_manager`.
  - payload: `thread_id`, `project_id`, `message`.
  - current behavior: notifies managers after escalation; failure degrades and continues.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: `execution_work_items`; not a workflow command because the side effect is independent durable delivery.

- `src/agent/nodes/escalate.py:122`
  - job type: `update_metrics`.
  - payload: `thread_id`, `escalated`.
  - current behavior: records escalation metric after escalation.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: `execution_work_items`.

- `src/agent/nodes/persist.py:109`
  - job type: `technical_incident`.
  - payload: `project_id`, `thread_id`, `client_id`, `failure_count`, `stage`, `error`.
  - current behavior: attempts to enqueue technical incident notification after repeated technical failure.
  - classification: DELETE_DEAD_QUEUE_PATH.
  - target migration: decision needed; either delete this producer as broken/dead or define a real current incident handler in a separate patch.

- `src/agent/nodes/persist.py:291`
  - job type: `update_metrics`.
  - payload: `thread_id`, message counts, `resolution_time`, `close_ticket`.
  - current behavior: updates metrics when a ticket is closed.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: `execution_work_items`.

- `src/tools/builtins.py:342`
  - job type: `notify_manager`.
  - payload: `thread_id`, `project_id`, `reason`, `priority`, `escalated_at`.
  - current behavior: tool-level human escalation path.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: `execution_work_items`.

- `src/interfaces/http/metrics.py:51`
  - job type: `aggregate_metrics`.
  - payload: `date`.
  - current behavior: platform-admin manual metrics aggregation endpoint.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: `execution_work_items`; alternatively direct synchronous admin operation if product accepts blocking behavior.

## Consumer Map

- `src/infrastructure/queue/job_dispatcher.py:40`
  - job type: `notify_manager`.
  - side effect: calls `handle_notify_manager`.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: execution-runtime handler adapter.

- `src/infrastructure/queue/handlers/notify_manager.py:296`
  - job type: `notify_manager`.
  - side effect: loads thread/project context, manager bot token, manager recipients, Redis reply state, then sends Telegram messages.
  - evidence: Telegram send at `src/infrastructure/queue/handlers/notify_manager.py:263`; all-delivery failure becomes transient at `src/infrastructure/queue/handlers/notify_manager.py:291`.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: move behind a current work-item handler while preserving retry behavior.

- `src/infrastructure/queue/job_dispatcher.py:52`
  - job type: `update_metrics`.
  - side effect: calls `handle_update_metrics`.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: execution-runtime handler adapter.

- `src/infrastructure/queue/handlers/metrics.py:16`
  - job type: `update_metrics`.
  - side effect: updates `thread_metrics`; may update `project_metrics_daily` on close.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: execution-runtime handler adapter or synchronous metrics service decision.

- `src/infrastructure/queue/job_dispatcher.py:60`
  - job type: `aggregate_metrics`.
  - side effect: calls `handle_aggregate_metrics`.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: execution-runtime handler adapter.

- `src/infrastructure/queue/handlers/metrics.py:64`
  - job type: `aggregate_metrics`.
  - side effect: calls `MetricsRepository.aggregate_for_date`.
  - classification: TRANSITIONAL_BLOCKER.
  - target migration: execution-runtime handler adapter.

- no consumer found for `technical_incident`.
  - producer evidence: `src/agent/nodes/persist.py:109`.
  - registered task evidence: `src/infrastructure/queue/job_types.py:11` lists only `notify_manager`, `update_metrics`, `aggregate_metrics`.
  - dispatcher evidence: `src/infrastructure/queue/job_dispatcher.py:67` fails unknown task types permanently.
  - classification: DELETE_DEAD_QUEUE_PATH.

## Execution Runtime Fit

| Queue concept | execution_queue | execution_runtime equivalent | Fit | Gap |
|---|---|---|---|---|
| task_type -> work_kind | `task_type` text in `execution_queue` | `WorkKind` at `src/contexts/execution_runtime/domain/value_objects/work_kind.py:7`; `work_kind` in `execution_work_items` | strong | choose stable bot/metrics work kinds |
| payload -> schedule_payload | JSONB `payload` inserted at `src/infrastructure/db/repositories/queue_repository.py:45` | `WorkItemSchedulePlan.payload` at `src/contexts/execution_runtime/application/use_cases/ensure_work_items_scheduled.py:21`; `execution_work_item_schedules.payload` | strong | define idempotency keys and payload schemas |
| status -> work item status / attempt status | `pending`, `processing`, `done`, `failed` | `ready`, `leased`, `completed`, `retryable_failed`, `terminal_failed` at `src/contexts/execution_runtime/domain/value_objects/work_item_status.py:13` | strong | status mapping needed |
| retry_count -> attempts / retry policy | `attempts`, `max_attempts` at `src/infrastructure/db/repositories/queue_repository.py:47` | `WorkItem.attempt_count` at `src/contexts/execution_runtime/domain/entities/work_item.py:29`; attempt rows in `execution_work_item_attempts` | strong | per-kind max retry policy needs decision |
| next_attempt_at -> schedule run_after / work item due_at | `next_attempt_at` due check at `src/infrastructure/db/repositories/queue_repository.py:78` | `next_attempt_at` due check at `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_lease_repository.py:71` | strong | naming is same; behavior can map directly |
| stale recovery -> lease expiration / retryable attempts | `locked_at` scan at `src/infrastructure/db/repositories/queue_repository.py:322` | `lease_expires_at`, `reclaim_expired_leases` at `src/contexts/execution_runtime/application/use_cases/reclaim_expired_leases.py:41` | strong | need queue-worker replacement loop for these work kinds |
| worker dispatch -> execution runtime handlers | `JobDispatcher.dispatch` at `src/infrastructure/queue/job_dispatcher.py:37` | current runtime has lease/attempt/dispatch records, e.g. `execution_work_item_attempt_dispatches` in `migrations/096_create_execution_work_item_attempt_dispatches.sql:1` | partial | need generic bot/metrics dispatcher composition |

Execution runtime DB evidence:

- `migrations/083_create_execution_runtime_tables.sql:4` creates `execution_work_items`.
- `migrations/083_create_execution_runtime_tables.sql:74` creates `execution_work_item_attempts`.
- `migrations/095_create_execution_work_item_schedules.sql:1` creates `execution_work_item_schedules`.
- `migrations/096_create_execution_work_item_attempt_dispatches.sql:1` creates `execution_work_item_attempt_dispatches`.

## Migration Options

### Option A: Keep execution_queue as separate bot queue

Pros:
- Lowest immediate behavior risk.
- Preserves manager notification retries and metrics jobs without new handler plumbing.
- Avoids touching current Workbench runtime tables.

Cons:
- Keeps a second durable execution lifecycle with its own lease/retry/stale recovery.
- FastAPI producer lifecycle and worker lifecycle are split; application startup does not prove worker availability.
- Continues old vocabulary and duplicate status semantics.
- Leaves `technical_incident` broken unless separately removed or handled.

### Option B: Migrate execution_queue jobs to execution_work_items

Pros:
- Aligns bot/metrics background jobs with the current generic execution runtime spine.
- Reuses existing schedule payloads, leases, attempts, retryable failures, terminal failures, and dispatch records.
- Allows eventual drop of `execution_queue` after producers and consumers move.

Cons:
- Requires new work kinds, idempotency keys, handler registry/composition, and migration/backfill decisions for pending queue rows.
- Bot notification handlers touch Telegram, Redis, project settings, thread views, and metrics; side effects need careful retry/idempotency behavior.
- Tests must be updated in a later patch to prove parity.

### Option C: Partial migration

Pros:
- Move lowest-risk jobs first, likely `update_metrics` and `aggregate_metrics`.
- Keeps `notify_manager` on old queue until Telegram/manager notification idempotency is designed.
- Allows deletion of `technical_incident` dead path early.

Cons:
- Temporarily keeps two queue systems.
- Requires bridge observability to avoid losing jobs.
- Still blocks dropping `execution_queue` until `notify_manager` is migrated.

## Recommended Plan

```text
Wave 1:
  files touched:
  - src/agent/nodes/persist.py
  - tests/agent/nodes/test_persist.py
  tables affected:
  - none
  behavior risk:
  - low/medium; remove or replace broken technical_incident enqueue, which currently has no consumer.
  tests to run:
  - python -m pytest tests/agent/nodes/test_persist.py -q

Wave 2:
  files touched:
  - src/interfaces/http/metrics.py
  - src/infrastructure/queue/handlers/metrics.py or new execution-runtime handler module
  - execution-runtime composition/handler registry files
  - metrics repository tests and focused API tests
  tables affected:
  - write new metrics jobs to execution_work_items/execution_work_item_schedules/attempts/dispatches
  behavior risk:
  - medium; admin metrics aggregation and thread/project metrics updates must remain idempotent.
  tests to run:
  - python -m pytest tests/database/repositories/test_metrics_repository.py -q
  - python -m pytest tests/api -k metrics -q
  - python -m pytest tests/contexts/execution_runtime -q

Wave 3:
  files touched:
  - src/application/orchestration/client_message_service.py
  - src/agent/nodes/escalate.py
  - src/tools/builtins.py
  - src/infrastructure/queue/handlers/notify_manager.py or new execution-runtime handler module
  - execution-runtime composition/handler registry files
  - notification/escalation tests
  tables affected:
  - write notify_manager work to execution_work_items/execution_work_item_schedules/attempts/dispatches
  behavior risk:
  - high; Telegram delivery, Redis reply-state, manager target selection, and retry semantics must be preserved.
  tests to run:
  - python -m pytest tests/agent/nodes/test_escalate.py tests/tools/test_builtins.py tests/domain/test_manager_notifications.py -q
  - python -m pytest tests/api/test_webhooks.py -q
  - python -m pytest tests/contexts/execution_runtime -q

Wave 4:
  files touched:
  - src/infrastructure/db/repositories/queue_repository.py
  - src/application/ports/queue_port.py
  - src/infrastructure/queue/*
  - src/interfaces/http/dependencies.py
  - tests/database/repositories/test_queue_repository.py
  - tests/architecture/test_worker_loop_queue_lifecycle_contract.py
  - migration to drop execution_queue
  tables affected:
  - drop execution_queue only after no active producers/consumers remain and pending rows are migrated or intentionally discarded.
  behavior risk:
  - medium; removes old worker entrypoint and queue metrics.
  tests to run:
  - python -m pytest tests/contexts/execution_runtime -q
  - python -m pytest tests/agent tests/application/services tests/api -q
```

## Do Not Touch

Current runtime files/tables discovered during comparison and explicitly out of scope for this audit patch:

- `execution_work_items`
- `execution_work_item_schedules`
- `execution_work_item_attempts`
- `execution_work_item_attempt_dispatches`
- `workflow_runtime_command_log`
- `workflow_runtime_*`
- `source_documents`
- `source_units`
- `draft_claim_*`
- `knowledge_workbench_runtime_retrieval_entries`
- `src/contexts/execution_runtime/domain/entities/work_item.py`
- `src/contexts/execution_runtime/domain/value_objects/work_kind.py`
- `src/contexts/execution_runtime/domain/value_objects/work_item_status.py`
- `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_lease_repository.py`
- `src/interfaces/composition/knowledge_extraction_workflow_runtime_service.py`

## Unknowns / Decisions Needed

- Deployment entrypoint: no FastAPI startup path for `src.infrastructure.queue.runtime.main()` was found, but deployment/process-manager configuration was not proven from this search set.
- Pending data migration: before dropping `execution_queue`, decide whether pending/processing/failed rows must be migrated to `execution_work_items` or discarded.
- `technical_incident`: decide whether it is a dead broken path to delete or a product requirement needing a real current handler.
- Work-kind names: choose stable lowercase dotted identifiers for bot notifications and metrics jobs.
- Idempotency: define idempotency keys for notification and metrics jobs to avoid duplicate Telegram sends or double metrics increments.
- Retry policy: map `max_attempts` and provider/Telegram transient failures to execution-runtime retry policy.
- Admin metrics endpoint: decide whether it should remain async via work item or become a direct synchronous admin operation.
- Observability: decide replacement for any queue-specific stats before deleting `execution_queue`; no current HTTP endpoint exposing queue state was found except enqueueing `aggregate_metrics`.
