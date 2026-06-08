# Runtime Boundaries Before Cross-Context Orchestration

## 0. Purpose

This document freezes the current state of:

```text
execution_runtime
artifact_runtime
llm_runtime

before implementing any cross-context orchestration.

The goal is to prevent the next implementation step from collapsing back into:

one service that leases work,
calls Groq,
stores raw output,
stores parsed output,
mutates Workbench status,
updates progress,
decides retry/fallback,
and emits frontend state

That pattern is explicitly forbidden.

The next phase must connect bounded contexts through explicit application boundaries, ports, Unit of Work boundaries, and eventually an outbox/event model.

1. Current architectural position

The branch now has three prepared runtime contexts:

src/contexts/execution_runtime/
src/contexts/llm_runtime/
src/contexts/artifact_runtime/

Their responsibilities are separate:

Execution Runtime:
  generic work lifecycle

LLM Runtime:
  provider-neutral LLM task execution lifecycle

Artifact Runtime:
  generic pipeline artifact persistence lifecycle

They must not be merged into one generic queue/LLM/artifact service.

2. Execution Runtime current state
2.1 Owns

Execution Runtime owns generic work lifecycle:

WorkItem
WorkItemAttempt
WorkKind
WorkerRef
LeaseToken
WaitUntil
RetryPolicy
WorkItemStatus
WorkItemStateMachine
WorkItem domain events
WorkItemUnitOfWorkPort

It knows only:

ready
leased
deferred
completed
retryable failed
terminal failed
cancelled
split superseded
lease expired
attempt count
worker ref
lease token
wait until

It does not know:

LLM
Groq
Qwen
Prompt A
Prompt C
claims
surfaces
source units
pipeline artifacts
Telegram
Workbench status names
2.2 Domain layer

Existing domain files:

src/contexts/execution_runtime/domain/entities/work_item.py
src/contexts/execution_runtime/domain/entities/work_item_attempt.py
src/contexts/execution_runtime/domain/value_objects/work_item_status.py
src/contexts/execution_runtime/domain/value_objects/work_kind.py
src/contexts/execution_runtime/domain/value_objects/worker_ref.py
src/contexts/execution_runtime/domain/value_objects/lease_token.py
src/contexts/execution_runtime/domain/value_objects/wait_until.py
src/contexts/execution_runtime/domain/value_objects/retry_policy.py
src/contexts/execution_runtime/domain/state_machines/work_item_state_machine.py
src/contexts/execution_runtime/domain/events/work_item_events.py

Important rule:

Do not mutate WorkItem.status directly.
Use WorkItemStateMachine.
2.3 Application layer

Current port:

src/contexts/execution_runtime/application/ports/work_item_unit_of_work_port.py

Current use cases:

LeaseWorkItem
CompleteWorkItem
DeferWorkItem
FailWorkItem
CancelWorkItem
ReclaimExpiredLeases

Files:

src/contexts/execution_runtime/application/use_cases/lease_work_item.py
src/contexts/execution_runtime/application/use_cases/complete_work_item.py
src/contexts/execution_runtime/application/use_cases/defer_work_item.py
src/contexts/execution_runtime/application/use_cases/fail_work_item.py
src/contexts/execution_runtime/application/use_cases/cancel_work_item.py
src/contexts/execution_runtime/application/use_cases/reclaim_expired_leases.py

Each use case follows the pattern:

command
→ state machine transition
→ event creation
→ unit_of_work.save_work_item(...)
→ optional unit_of_work.save_attempt(...)
→ unit_of_work.append_event(...)
→ commit
→ rollback on exception
2.4 Execution Runtime is ready for orchestration only through ports

It is not yet ready for direct production use because there is no infrastructure adapter yet:

PostgresWorkItemUnitOfWork
WorkItemRepository
Outbox adapter
scheduler/worker adapter

But the application boundary is now prepared.

3. Artifact Runtime current state
3.1 Owns

Artifact Runtime owns generic pipeline artifact persistence lifecycle:

PipelineArtifact
ArtifactRef
ArtifactKind
ArtifactPayload
ArtifactLineage
ArtifactStatus
ArtifactVisibility
RetentionPolicy
Artifact events
ArtifactUnitOfWorkPort

It knows only:

stored
validated
rejected
superseded
expired
visibility
retention
lineage
payload as opaque JSON-like value

It does not know:

LLM provider
Groq
Qwen
Prompt A
Prompt C
claim semantics
surface semantics
retrieval quality
work item lease
Workbench stage
frontend display policy
3.2 Domain layer

Existing domain files:

src/contexts/artifact_runtime/domain/entities/pipeline_artifact.py
src/contexts/artifact_runtime/domain/value_objects/artifact_ref.py
src/contexts/artifact_runtime/domain/value_objects/artifact_kind.py
src/contexts/artifact_runtime/domain/value_objects/artifact_payload.py
src/contexts/artifact_runtime/domain/value_objects/artifact_lineage.py
src/contexts/artifact_runtime/domain/value_objects/artifact_status.py
src/contexts/artifact_runtime/domain/value_objects/artifact_visibility.py
src/contexts/artifact_runtime/domain/value_objects/retention_policy.py
src/contexts/artifact_runtime/domain/events/artifact_events.py

Important rule:

Artifact existence is the checkpoint.
Queue status is not the artifact.
3.3 Application layer

Current port:

src/contexts/artifact_runtime/application/ports/artifact_unit_of_work_port.py

Current use cases:

PersistArtifact
ValidateArtifact
RejectArtifact
SupersedeArtifact
ExpireArtifact

Files:

src/contexts/artifact_runtime/application/use_cases/persist_artifact.py
src/contexts/artifact_runtime/application/use_cases/validate_artifact.py
src/contexts/artifact_runtime/application/use_cases/reject_artifact.py
src/contexts/artifact_runtime/application/use_cases/supersede_artifact.py
src/contexts/artifact_runtime/application/use_cases/expire_artifact.py

Each use case follows the pattern:

command
→ PipelineArtifact lifecycle method
→ event creation
→ unit_of_work.save_artifact(...)
→ unit_of_work.append_event(...)
→ commit
→ rollback on exception
3.4 Artifact Runtime is ready for orchestration only through ports

It is not yet ready for direct production use because there is no infrastructure adapter yet:

PostgresArtifactUnitOfWork
ArtifactRepository
Outbox adapter
artifact read model
retention cleanup scheduler

But the application boundary is now prepared.

4. LLM Runtime current state

LLM Runtime has already advanced further than the other two contexts.

It currently has:

domain:
  LlmTask
  LlmAttempt
  ModelProfile
  ProviderAccount
  LlmTaskStateMachine
  value objects
  domain events

application:
  ExecuteLlmTask
  ExecuteAndRecordLlmTask
  RecordLlmTaskExecution
  LlmProviderPort
  LlmOutputValidationPort
  LlmTaskUnitOfWorkPort
  LlmProviderInput
  error policy
  route planning policy
  route candidate builder
  quota availability policy
  JSON output validation policy
  execution recording policy

infrastructure:
  LlmRuntimeSettings
  Groq env config
  Groq model catalog seed
  Groq request builder
  Groq response mapper
  Groq rate-limit headers mapper
  Groq provider adapter
  Groq HTTP transport
  Groq httpx client
  Groq provider composition

Critical LLM rule:

provider success is not task success

Flow:

Groq HTTP 200
→ LlmProviderSuccess
→ output validation
→ only then LlmTask SUCCEEDED
5. What must happen before Workbench cutover

Before touching Prompt A / Prompt C production path, the following boundary must be designed:

leased WorkItem
+ LlmTask execution record
+ PipelineArtifact persistence
+ Outbox events

This is cross-context orchestration.

It must not be implemented inside:

GroqProviderAdapter
PromptA generator
Workbench queue handler
old repository method
old DTO mapper
6. Required next design target

The next design target is a cross-context application boundary, probably under a separate orchestration context or a dedicated application composition layer.

Possible names:

src/contexts/pipeline_runtime/
src/contexts/workflow_runtime/
src/contexts/knowledge_workbench/extraction/application/process_managers/

Do not choose blindly.

Before creating it, answer:

1. Is this generic pipeline orchestration or Knowledge Workbench extraction orchestration?
2. Who owns the transaction boundary across WorkItem + LlmTask + PipelineArtifact?
3. Where does outbox event persistence live?
4. Are cross-context events committed in one DB transaction?
5. Is this a process manager/saga or a single use case?
6. Does it need to resume after crash?
7. Which table/entity is the source of truth for progress?
7. Strong recommendation for next implementation sequence

Do not jump directly to Workbench.

Recommended next sequence:

1. Recon current transaction/UoW/repository/outbox patterns.
2. Recon old workbench queue handler and artifact storage paths.
3. Decide cross-context transaction boundary.
4. Add minimal cross-context UoW port.
5. Add tests for one vertical orchestration slice using fakes.
6. Only then implement infrastructure adapters.
7. Only then cut over Prompt A.

The first vertical orchestration slice should probably be:

Process one leased extraction work item:
  WorkItem is already leased
  prepared LlmTask exists or is created
  prepared LlmProviderInput is passed
  ExecuteAndRecordLlmTask runs
  raw output artifact is persisted
  parsed output artifact is persisted or validation failure artifact is persisted
  WorkItem is completed/deferred/failed based on typed outcome
  events are appended

But this must be confirmed by reconnaissance.

8. Forbidden next steps

Do not:

1. Patch old workbench_parallel_processing directly as the new architecture.
2. Put artifact persistence into queue status transitions.
3. Put WorkItem completion into LLM Runtime.
4. Put LlmTask execution into Execution Runtime.
5. Put LLM provider routing into Knowledge Workbench.
6. Put Workbench semantics into Artifact Runtime.
7. Add Postgres tables before deciding owning bounded context.
8. Add generic service.py/repository.py/dto.py.
9. Add direct status mutation outside state machines.
10. Reuse SectionBatchQueueItem as canonical WorkItem.
11. Treat NodeRun as canonical PipelineArtifact without explicit adapter decision.
9. Important legacy warning

Known legacy/hybrid concepts:

SectionBatchQueueItem
CLAIM_OBSERVATIONS_PERSISTED
REGISTRY_APPLICATION_QUEUED
REGISTRY_APPLICATION_APPLIED
waiting_for_fresh_registry
NodeRun
Groq keyring/router
Prompt-specific Groq invocation adapters

They may be useful for migration reconnaissance.

They must not become the new canonical model.

10. Current stable boundary map
Execution Runtime:
  WorkItem lifecycle
  WorkItemAttempt
  WorkItem events
  WorkItemUnitOfWorkPort
  application use cases for lease/complete/defer/fail/cancel/reclaim

LLM Runtime:
  LlmTask lifecycle
  LlmAttempt
  Llm route/error/quota/validation policies
  LlmProviderPort
  LlmTaskUnitOfWorkPort
  Groq provider infrastructure

Artifact Runtime:
  PipelineArtifact lifecycle
  Artifact events
  ArtifactUnitOfWorkPort
  application use cases for persist/validate/reject/supersede/expire

These boundaries are now prepared enough to start designing cross-context orchestration.

They are not yet wired to production database or Workbench.

11. Immediate next action

The immediate next action should be read-only reconnaissance of existing infrastructure transaction boundaries:

repositories
UnitOfWork-like patterns
asyncpg transaction handling
outbox/event tables
NodeRun/artifact-like persistence
workbench queue handler
current Prompt A path
current raw/parsed LLM output storage
current migrations for workbench queue/artifacts

The next patch must not be written until that reconnaissance is done.
