# Execution Runtime Context

## Назначение

`execution_runtime` — абстрактный runtime выполнения работы.

Ему безразлично, что именно выполняется:

- обработка секции документа;
- LLM-задача;
- Telegram-ответ;
- обработка webhook;
- пересчёт embedding;
- обновление памяти диалога;
- публикация знаний.

Этот context отвечает только за выполнение work items: очередь, lease, attempts, retry, defer, cancel, worker capacity, wait-state и idempotency.

## Owns

Canonical concepts:

- `WorkItem`;
- `WorkItemAttempt`;
- `Lease`;
- `LeaseToken`;
- `RetryPolicy`;
- `DeferPolicy`;
- `WorkerRef`;
- `WorkKind`;
- `WaitUntil`;
- `WorkItemStateMachine`.

Canonical statuses:

- `READY`;
- `LEASED`;
- `DEFERRED`;
- `COMPLETED`;
- `RETRYABLE_FAILED`;
- `TERMINAL_FAILED`;
- `CANCELLED`;
- `SPLIT_SUPERSEDED`.

Use cases that belong here:

- `LeaseWorkItem`;
- `CompleteWorkItem`;
- `DeferWorkItem`;
- `FailWorkItem`;
- `CancelWorkItem`;
- `ReclaimExpiredLeases`.

Domain events that belong here:

- `WorkItemLeased`;
- `WorkItemCompleted`;
- `WorkItemDeferred`;
- `WorkItemFailed`;
- `WorkItemCancelled`;
- `WorkItemLeaseExpired`.

## Does not own

This context does not own:

- Prompt A;
- Prompt C;
- Groq;
- claims;
- source units;
- retrieval surfaces;
- Telegram messages;
- business policies;
- artifact payload semantics;
- Workbench stage meaning.

## Legacy / adapter warnings

`SectionBatchQueueItem` is not canonical `WorkItem`.

It is a legacy/adapter hybrid because it currently mixes:

- queue lifecycle;
- lease;
- pipeline checkpoint;
- artifact marker;
- Workbench stage progress.

Old queue statuses such as `CLAIM_OBSERVATIONS_PERSISTED`, `REGISTRY_APPLICATION_QUEUED`, and `REGISTRY_APPLICATION_APPLIED` must not be copied into this context as canonical `WorkItem` statuses.

## Placement rules

New canonical execution code goes here.

Do not add new generic dumping-ground files named:

- `service.py`;
- `services.py`;
- `repository.py`;
- `dto.py`.

Use explicit names such as:

- `domain/entities/work_item.py`;
- `domain/state_machines/work_item_state_machine.py`;
- `application/use_cases/lease_work_item.py`;
- `application/ports/work_item_repository.py`;
- `infrastructure/postgres/postgres_work_item_repository.py`.
