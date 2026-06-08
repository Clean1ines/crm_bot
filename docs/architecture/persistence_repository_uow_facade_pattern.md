# Persistence Pattern: Repository, Transactional Facade, Unit of Work

## 0. Purpose

This document defines the persistence pattern for the new bounded-context-first architecture.

It exists because the current legacy persistence layer has collapsed too many responsibilities into broad repositories and services.

The target architecture must prevent this pattern:

```text
one giant repository
+ many unrelated methods
+ implicit transactions
+ workflow decisions
+ queue lifecycle mutation
+ artifact persistence
+ read model construction
+ migration compatibility hacks

The new pattern is:

Use Case / Process Manager
→ application port
→ Unit of Work
→ Transactional Persistence Facade
→ narrow repositories
→ one shared transaction
→ outbox append in same transaction
1. Diagnosis from current code

Current reconnaissance shows that persistence is spread across:

src/infrastructure/db/knowledge_workbench_repository.py
src/infrastructure/db/workbench_*_repository.py
src/infrastructure/db/repositories/*
src/application/services/faq_workbench_*_service.py
src/infrastructure/queue/handlers/workbench_parallel_processing.py

There are many direct transaction usages, especially inside knowledge_workbench_repository.py, and multiple services persist workflow state, artifacts, node runs, usage totals and queue status through repository methods. The repository layer is therefore acting not only as persistence, but also as workflow coordination and compatibility layer.

This must not be repeated under src/contexts.

2. Core distinctions
2.1 Repository

A repository is a narrow persistence adapter for one aggregate/table-family.

A repository may:

insert one aggregate
update one aggregate
load one aggregate
query by stable identifiers
map database rows to domain/application objects

A repository must not:

own a business workflow
open and commit its own transaction for a multi-entity use case
decide next process step
call LLM provider
mutate queue lifecycle because an artifact was saved
construct frontend dashboard state
append unrelated events unless it is specifically an outbox repository

Repository examples:

PostgresWorkItemRepository
PostgresLlmTaskRepository
PostgresArtifactRepository
PostgresClaimObservationRepository
PostgresOutboxRepository
2.2 Unit of Work

A Unit of Work owns the transaction boundary.

It may:

open transaction
provide repositories/facade using the same connection
commit
rollback
ensure all changes are atomic

It must not:

perform business decisions
choose LLM route
interpret artifact payload
decide Workbench review status
become a god repository

Use cases and process managers should depend on an application-layer UoW port, not concrete Postgres classes.

2.3 Transactional Persistence Facade

A transactional facade is a use-case-specific persistence surface exposed by the UoW.

It exists to avoid injecting ten repositories into one process manager.

It may provide methods such as:

save_work_item(...)
save_llm_task(...)
save_llm_attempt(...)
save_artifact(...)
save_claim_observations(...)
append_event(...)

But it must be scoped to one process manager or one bounded context boundary.

A transactional facade must not become:

KnowledgeWorkbenchRepositoryV2
RuntimeRepository
EverythingRepository
ServiceRepository

If a facade grows unrelated methods, split it.

3. Target dependency direction

Allowed:

knowledge_workbench extraction process manager
→ ClaimExtractionWorkItemUnitOfWorkPort
→ infrastructure implementation
→ narrow repositories

Allowed:

execution_runtime application use case
→ WorkItemUnitOfWorkPort
→ PostgresWorkItemUnitOfWork
→ PostgresWorkItemRepository

Allowed:

artifact_runtime application use case
→ ArtifactUnitOfWorkPort
→ PostgresArtifactUnitOfWork
→ PostgresArtifactRepository

Allowed:

llm_runtime application use case
→ LlmTaskUnitOfWorkPort
→ PostgresLlmTaskUnitOfWork
→ PostgresLlmTaskRepository

Forbidden:

llm_runtime imports knowledge_workbench repository
execution_runtime imports artifact repository
artifact_runtime imports Workbench claim types
Groq provider adapter imports repositories
queue handler directly coordinates all persistence
repository calls process manager
repository calls provider adapter
4. Cross-context orchestration rule

When one use case must commit changes across multiple bounded contexts, the UoW belongs to the orchestrating context.

For the first vertical slice, the orchestrating context is:

knowledge_workbench/extraction

Because the business process is:

process one Workbench extraction work item through Prompt A claim extraction

Therefore the first cross-context port should live here:

src/contexts/knowledge_workbench/extraction/application/ports/
  claim_extraction_work_item_unit_of_work_port.py

It may coordinate persistence for:

Execution Runtime WorkItem
LLM Runtime LlmTask / LlmAttempt
Artifact Runtime PipelineArtifact
Knowledge Workbench ClaimObservation
Outbox events

But the port must expose only methods required by the first process-manager test.

Do not design a giant generic UoW upfront.

5. Transaction rule

If a process step changes multiple durable records, it must be committed atomically.

Examples:

LlmTask succeeded
+ LlmAttempt saved
+ raw output artifact stored
+ parsed output artifact stored
+ WorkItem completed
+ events appended

must be one transaction.

Examples:

LlmTask deferred due to minute limit
+ LlmAttempt saved
+ WorkItem deferred
+ quota wait event appended

must be one transaction.

Examples:

oversized section split
+ parent WorkItem split-superseded
+ child SourceUnits created
+ child WorkItems created
+ split artifact stored
+ events appended

must be one transaction.

6. Outbox rule

Events that must survive process crash must be appended through the same transaction as the state change.

Required event persistence pattern:

state change
+ outbox/event append
+ commit

Forbidden:

commit state
then try to append event

Forbidden:

emit event from provider adapter

Forbidden:

emit event from repository after commit

The process manager may decide which events are appended.
The infrastructure UoW must persist them atomically.

7. Repository placement rules

Canonical new repositories go under the owning bounded context:

src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_repository.py
src/contexts/llm_runtime/infrastructure/postgres/postgres_llm_task_repository.py
src/contexts/artifact_runtime/infrastructure/postgres/postgres_artifact_repository.py
src/contexts/knowledge_workbench/extraction/infrastructure/postgres/postgres_claim_observation_repository.py

Cross-context UoW implementations may live under the orchestrating context:

src/contexts/knowledge_workbench/extraction/infrastructure/postgres/
  postgres_claim_extraction_work_item_unit_of_work.py

Shared outbox infrastructure may later live under:

src/contexts/shared_kernel/infrastructure/postgres/postgres_outbox_repository.py

or a dedicated context if outbox becomes substantial.

Do not place new canonical persistence in:

src/infrastructure/db/knowledge_workbench_repository.py
src/application/services/
src/infrastructure/queue/handlers/

except as temporary adapter/cutover code explicitly marked as legacy bridge.

8. Naming rules

Use explicit names:

PostgresWorkItemRepository
PostgresLlmTaskRepository
PostgresArtifactRepository
PostgresClaimObservationRepository
PostgresOutboxRepository
PostgresClaimExtractionWorkItemUnitOfWork
ClaimExtractionWorkItemUnitOfWorkPort

Avoid generic names:

repository.py
repositories.py
service.py
services.py
db.py
storage.py
manager.py
helper.py
utils.py

Avoid old hybrid names as canonical concepts:

SectionBatchQueueItemRepository
ProcessingNodeRunRepository
NodeRunArtifactRepository

These may exist only as migration adapters if explicitly classified.

9. Facade size rule

A transactional facade is allowed only if it is scoped.

Good:

ClaimExtractionWorkItemUnitOfWorkPort

Because it supports one process manager.

Bad:

KnowledgeWorkbenchUnitOfWorkPort

unless it is split into sub-facades.

Bad:

RuntimeUnitOfWorkPort

because it will become a global dumping ground.

If a facade needs methods for unrelated workflows, split it:

ClaimExtractionWorkItemUnitOfWorkPort
SurfaceConsolidationWorkItemUnitOfWorkPort
PublicationUnitOfWorkPort
10. Read model rule

Read models are separate from command-side repositories.

A repository that persists workflow state must not also become dashboard/query API.

Use separate read-side objects later:

WorkbenchProcessingSummaryReader
StageProgressSummaryReader
QuotaWaitSummaryReader
ReviewQueueSummaryReader
RetrievalEvalSummaryReader
UsageSummaryReader

Read models are not source of truth.

11. Migration rule

Old tables and old repository methods may be used as migration sources, but each use must be classified:

CANONICAL
ADAPTER
LEGACY
RETIRED

Known legacy/hybrid persistence concepts:

SectionBatchQueueItem
ProcessingNodeRun
ProcessingNodeArtifact
NodeRun
CLAIM_OBSERVATIONS_PERSISTED
REGISTRY_APPLICATION_QUEUED
REGISTRY_APPLICATION_APPLIED
WAITING_FOR_FRESH_REGISTRY

They must not be silently rebranded as canonical runtime concepts.

12. First implementation target after this document

The next code patch should not create Postgres adapters.

The next code patch should create only the Workbench Extraction application structure and port skeleton:

src/contexts/knowledge_workbench/extraction/
  __init__.py
  application/
    __init__.py
    ports/
      __init__.py
      claim_extraction_work_item_unit_of_work_port.py
    process_managers/
      __init__.py

The first port should be intentionally minimal and test-driven.

No database code until a fake-UoW process-manager test defines the exact write set.

13. Summary

The persistence target pattern is:

ProcessManager / UseCase
→ Application UoW Port
→ Infrastructure UoW
→ Transactional Facade
→ Narrow Repositories
→ One DB transaction
→ Outbox append in same transaction

The forbidden pattern is:

one repository/service/handler owns the whole business workflow

The first cross-context UoW belongs to:

knowledge_workbench/extraction

because Prompt A claim extraction is Workbench business orchestration over generic runtimes.