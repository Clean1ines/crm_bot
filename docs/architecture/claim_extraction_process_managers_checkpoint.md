# Claim Extraction Process Managers Checkpoint

## 0. Purpose

This document freezes the current state of the new Knowledge Workbench Extraction orchestration boundary.

Current location:

```text
src/contexts/knowledge_workbench/extraction/

The goal is to prevent the next patches from collapsing back into the legacy Workbench queue handler or old Prompt A service.

1. Current architectural decision

Prompt A claim extraction orchestration belongs to:

src/contexts/knowledge_workbench/extraction/application/process_managers/

It does not belong to:

src/contexts/llm_runtime/
src/contexts/execution_runtime/
src/contexts/artifact_runtime/
src/application/services/
src/infrastructure/queue/handlers/
src/infrastructure/llm/

Reason:

Prompt A claim extraction is Workbench business orchestration over generic runtime contexts.

The generic runtimes provide lifecycle primitives:

Execution Runtime:
  WorkItem lifecycle

LLM Runtime:
  LlmTask / LlmAttempt lifecycle

Artifact Runtime:
  PipelineArtifact lifecycle

Knowledge Workbench Extraction coordinates them for the claim extraction use case.

2. Current port

The cross-context transaction boundary is:

src/contexts/knowledge_workbench/extraction/application/ports/claim_extraction_work_item_unit_of_work_port.py

Port:

ClaimExtractionWorkItemUnitOfWorkPort

It can save:

WorkItem
WorkItemAttempt
LlmTask
LlmAttempt
PipelineArtifact
ClaimExtractionRuntimeEvent

And it owns:

commit()
rollback()

This is intentionally a use-case-scoped transactional facade, not a global repository.

3. Current process managers

Current process managers:

RecordClaimExtractionSuccess
RecordClaimExtractionDeferred
RecordClaimExtractionFailed
RecordClaimExtractionSplitRequired

Files:

src/contexts/knowledge_workbench/extraction/application/process_managers/record_claim_extraction_success.py
src/contexts/knowledge_workbench/extraction/application/process_managers/record_claim_extraction_deferred.py
src/contexts/knowledge_workbench/extraction/application/process_managers/record_claim_extraction_failed.py
src/contexts/knowledge_workbench/extraction/application/process_managers/record_claim_extraction_split_required.py

They all follow the same rule:

receive already prepared runtime entities/artifacts
→ perform only Workbench extraction orchestration transition
→ save all state through ClaimExtractionWorkItemUnitOfWorkPort
→ append events
→ commit once
→ rollback on exception

They do not:

call Groq
call httpx
read env
parse Prompt A
open DB transactions
import infrastructure
create child source units
mutate legacy SectionBatchQueueItem status
4. Success path

Process manager:

RecordClaimExtractionSuccess

Meaning:

Prompt A LLM execution succeeded.
Output validation succeeded.
Raw output artifact was prepared.
Parsed output artifact was prepared.
The leased WorkItem can be completed.

Writes atomically:

completed WorkItem
WorkItemAttempt
succeeded LlmTask
LlmAttempt
raw PipelineArtifact
parsed PipelineArtifact
WorkItemCompleted
LlmTaskSucceeded
ArtifactStored(raw)
ArtifactStored(parsed)

Important rule:

raw_text does not belong to LlmAttempt.
raw_text belongs to PipelineArtifact.
5. Deferred path

Process manager:

RecordClaimExtractionDeferred

Meaning:

LLM task is deferred, usually due to minute/rate wait.
The WorkItem lease must be released immediately.
The WorkItem must enter DEFERRED with wait_until.

Writes atomically:

deferred WorkItem
WorkItemAttempt
deferred LlmTask
LlmAttempt
optional error PipelineArtifact
WorkItemDeferred
LlmMinuteLimitHit or LlmTaskDeferred
optional ArtifactStored(error)

Critical rule:

Minute/rate limit must not keep the WorkItem leased until TTL.
It must explicitly defer the WorkItem.
6. Failed path

Process manager:

RecordClaimExtractionFailed

Meaning:

LLM task failed retryably or terminally.
This is not a split-required path.
This is not a daily-exhausted/user-choice path.

Modes:

RETRYABLE
TERMINAL

Retryable writes atomically:

retryable failed WorkItem
WorkItemAttempt
retryable failed LlmTask
LlmAttempt
optional error PipelineArtifact
WorkItemFailed
LlmTaskFailed
optional ArtifactStored(error)

Terminal writes atomically:

terminal failed WorkItem
WorkItemAttempt
terminal failed LlmTask
LlmAttempt
optional error PipelineArtifact
WorkItemFailed
LlmTaskFailed
optional ArtifactStored(error)
7. Split-required path

Process manager:

RecordClaimExtractionSplitRequired

Meaning:

The current extraction unit is too large for the selected/available route.
The parent WorkItem is not completed with fake empty success.
The parent WorkItem becomes SPLIT_SUPERSEDED.

Accepted LLM error kinds:

REQUEST_TOO_LARGE
OUTPUT_TOO_LARGE

Writes atomically:

split-superseded WorkItem
WorkItemAttempt
failed LlmTask
LlmAttempt
split PipelineArtifact
WorkItemSplitSuperseded
LlmTaskFailed
ArtifactStored(split)

Important rule:

This process manager does not create child SourceUnits or child WorkItems yet.

Child creation belongs to a later Source Management / split workflow.

8. Boundary guards

Architecture guard:

tests/architecture/test_claim_extraction_process_manager_boundaries.py

It prevents process managers from importing:

src.infrastructure.db
src.infrastructure.llm
src.infrastructure.queue
src.application.services
src.contexts.*.infrastructure
Groq provider infrastructure

It also prevents direct provider/DB/legacy markers such as:

Groq
httpx
asyncpg
psycopg
connection.execute(
fetchrow(
transaction(
SectionBatchQueueItem
CLAIM_OBSERVATIONS_PERSISTED
REGISTRY_APPLICATION_QUEUED
REGISTRY_APPLICATION_APPLIED
WAITING_FOR_FRESH_REGISTRY

Process managers may have an execute(...) method. That is allowed.

9. What is intentionally not implemented yet

Not implemented yet:

Daily exhausted / user choice workflow
Degraded fallback user choice
Auto-resume next day
Child SourceUnit creation
Child WorkItem creation
Source split policy
Postgres ClaimExtractionWorkItemUnitOfWork
Postgres repositories
Outbox table/adapter
Legacy queue handler cutover
Prompt A adapter cutover
Prompt C / registry application cutover
Frontend status mapping

This is intentional.

The current layer is application orchestration boundary only.

10. Next safe implementation options
Option A — Daily exhausted path

Add:

RecordClaimExtractionDailyExhausted

Purpose:

Record that all acceptable daily capacity is exhausted.
Do not fake terminal failure.
Do not keep lease.
Surface a future user-choice / auto-resume state.

Likely writes:

deferred WorkItem or retryable failed WorkItem
LlmTask retryable failed / daily exhausted event
LlmAttempt
optional error artifact
LlmDailyLimitExhausted
WorkItemDeferred or WorkItemFailed

But exact WorkItem state must be decided before code.

Option B — Source split workflow

Add Source Management split boundary before child creation:

src/contexts/knowledge_workbench/source_management/

Purpose:

parent source unit
→ child source units
→ child WorkItems
→ split lineage artifact

This should not be hidden inside RecordClaimExtractionSplitRequired.

Option C — Postgres-free orchestration facade test

Add a higher-level fake test that maps an ExecuteLlmTaskOutcomeKind into one of:

success
deferred
failed
split_required

But avoid provider calls and avoid DB.

11. Recommended next step

Before adding more code, decide daily exhaustion semantics:

Should daily exhaustion make WorkItem DEFERRED until next day?
Should it create a user-choice-required state?
Should it be represented as WorkItem RETRYABLE_FAILED with no immediate retry?
Does Execution Runtime need a generic USER_ACTION_REQUIRED / BLOCKED status?

Do not encode daily exhausted as ordinary terminal failure.

12. Summary

Current stable outcome map:

SUCCEEDED
→ RecordClaimExtractionSuccess
→ WorkItem COMPLETED

DEFERRED / MINUTE_LIMIT
→ RecordClaimExtractionDeferred
→ WorkItem DEFERRED

RETRYABLE_FAILED / TERMINAL_FAILED
→ RecordClaimExtractionFailed
→ WorkItem RETRYABLE_FAILED or TERMINAL_FAILED

REQUEST_TOO_LARGE / OUTPUT_TOO_LARGE split path
→ RecordClaimExtractionSplitRequired
→ WorkItem SPLIT_SUPERSEDED

The next risky design gap is daily exhaustion / user choice.