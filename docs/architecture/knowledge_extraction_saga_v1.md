# Knowledge Extraction Saga v1

## Source Ingestion Admission Boundary

Source ingestion is a costly and state-mutating operation. It can create source documents, source units, processing state, downstream work, and later LLM-related artifacts, so saga v1 must start from an explicit admission decision.

Admission rules for saga v1:

- Source ingestion must be allowed only for authenticated platform admins or project `owner` / `admin`.
- `manager` is not allowed to start ingestion in saga v1 unless this is explicitly changed later.
- A manager may be allowed by an HTTP route for other project operations, but that must not be treated as permission to start source ingestion.
- The HTTP route may perform an early access check, but the saga/application boundary must not trust HTTP-only authorization.
- Source ingestion admission must be represented as an application policy/port, not as a direct HTTP/router/db import inside the saga.
- The first production vertical slice is source ingestion admission and source document/source unit persistence, not Draft Observation Extraction.


## Draft Observation Extraction Phase Warning

Draft Observation Extraction is a later phase. It must not be wired until source ingestion admission plus source document/source unit persistence are complete.

Existing Prompt A enum names are legacy-compatible phase keys, not recommended new naming for the source ingestion boundary.


## 1. Purpose

This document fixes the canonical architecture contract for `KnowledgeExtractionSaga v1` before any production saga code, migrations, worker wiring, or outbox consumer is added.

The saga exists to coordinate the long-running business workflow that turns an uploaded source document into reviewed and published knowledge. It must be resumable, auditable, idempotent, and safe across process restarts, partial failures, LLM quota waits, manual review waits, and cleanup.


## 2. Scope and owner

Owner bounded context:

```text
knowledge_workbench
```

The saga is owned by Knowledge Workbench because Knowledge Workbench owns the meaning of knowledge engineering workflow quality: source documents, source units, draft observations, consolidated knowledge, manual curation, publication, and cleanup.

The saga scope is wider than Knowledge Extraction alone. Knowledge Extraction is one major phase family, not the full business process. The full workflow coordinates:

```text
source_management
extraction
embedding_runtime
consolidation / clustering
manual review
publication
cleanup
```

The saga may call or react to contracts from other contexts, but it must not import infrastructure adapters, SQL repositories, queue workers, provider adapters, or legacy Workbench services.

## 3. Current reusable pieces

Current reusable pieces that must be reused rather than reimplemented:

```text
Execution Runtime:
- WorkItem
- WorkItemAttempt
- WorkItemStateMachine
- LeaseWorkItem
- CompleteWorkItem
- DeferWorkItem
- FailWorkItem
- CancelWorkItem
- ReclaimExpiredLeases

LLM Runtime:
- LlmTask
- LlmAttempt
- ProviderAccount
- ModelProfile
- RateLimitProfile
- LlmQuotaSnapshot
- LlmEstimatedTokenNeed
- LlmQuotaAvailabilityPolicy
- LlmRouteCandidateBuilder
- LlmRoutePlanningPolicy
- ExecuteLlmTask
- ExecuteAndRecordLlmTask

- ArtifactKind
- ArtifactRef
- ArtifactLineage
- ArtifactPayload
- ArtifactStatus
- RetentionPolicy
- ArtifactStored
- LoadArtifact

Knowledge Workbench / Extraction:
- CreateExtractionWorkItems
- RunClaimExtractionStage
- RunClaimExtractionStageAsync
- ResumeClaimExtractionStage
- CancelClaimExtractionStage
- ProcessClaimExtractionWorkItem
- RecordClaimExtractionSuccess
- RecordClaimExtractionDeferred
- RecordClaimExtractionFailed
- RecordClaimExtractionDailyExhausted
- RecordClaimExtractionSplitRequired
- ApplyClaimExtractionDailyExhaustedDecision
- ApplyDraftClaimObservationArtifact
- ApplyDraftClaimObservationArtifactAsync
- ApplyDraftClaimObservationArtifactOnArtifactStored

Source Management:
- SourceDocument
- SourceUnit
- source domain events
- SourceParserPort

Embedding Runtime:
- EmbeddingTask
- EmbeddingVector

Publication:
- PublicationRun
- KnowledgeSurface
```

Current reusable persistence already exists for several local pieces:

```text
execution_work_items
execution_work_item_attempts
outbox_events
claim_extraction_stage_work_items
draft_claim_observations
draft_claim_observation_possible_questions
draft_claim_observation_provenance
```

These tables are not enough for saga state. They are local runtime/phase outputs that the saga must reconcile against.

## 4. Forbidden legacy/canonical boundaries

Forbidden legacy / canonical boundaries:

```text
knowledge_workbench_processing_runs
SectionBatchQueueItem
workbench_parallel_processing
process_workbench_document
old FAQ compiler paths
old Workbench v1/v2 processing tables as canonical saga state
src.application.services old Workbench services
src.domain.project_plane.knowledge_workbench old project-plane domain
```

These may be read only as migration/reference material or danger maps. They must not be used as the canonical implementation path for `KnowledgeExtractionSaga v1`.

`knowledge_workbench_processing_runs` must not become the canonical saga run table. It belongs to the old Workbench foundation/reference area and mixes concerns that are now split across runtime contexts and Workbench subdomains.

`SectionBatchQueueItem` must not become a canonical phase item. It is a legacy/adapter hybrid that mixes queue lifecycle, lease, pipeline checkpoint, artifact marker, and Workbench progress.

`workbench_parallel_processing` must not become the canonical handler. It belongs to old/adapter terrain and must not be extended into the new saga.

`process_workbench_document` must not be revived as the canonical handler. It is old queue-handler terrain, not the new saga entrypoint.

## 5. Saga location

Canonical future code location:

```text
src/contexts/knowledge_workbench/application/sagas/
```

The canonical location is not:

```text
src/contexts/knowledge_workbench/extraction/application/sagas/
```

Reason: `KnowledgeExtractionSaga` is wider than extraction. It coordinates source management, extraction, embeddings, clustering/consolidation, manual review, publication, and cleanup. If it lives inside `extraction`, it will either pull later phases into Extraction or force a second parent-level orchestrator later.

Recommended future application contract files, after this document:

```text
src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_saga.py
src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_saga_state.py
src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_saga_ports.py
```

## 6. Runtime ownership model

Ownership boundaries are fixed as follows.

### Execution Runtime

Owns:

```text
work item lifecycle
lease
attempt
retry/defer/fail/complete/cancel/reclaim
wait-state
idempotent execution item state
```

Does not own:

```text
Prompt A
Prompt B
source units
draft observations
artifact payload semantics
Workbench stage meaning
publication decisions
```

### LLM Runtime

Owns:

```text
provider/account/model
RPM / TPM / RPD / TPD
context window
max output
token estimates
LLM route planning
LLM route reservation
provider usage updates
provider error classification
output validation contract
```

Does not own:

```text
worker slots
CPU/RAM pressure
DB pool capacity
Prompt A/B business semantics
source unit structure
manual review
publication decisions
artifact retention policy
work item leasing
```


Owns:

```text
artifact persistence
payload opacity
artifact kind/ref/status/lineage
retention policy
ArtifactStored
artifact load/store contracts
```

Does not own:

```text
semantic meaning of claims
LLM model selection
work item leasing
Workbench review decisions
frontend display policy
knowledge correctness
```

### Future Capacity Runtime

Owns:

```text
worker slots
CPU/RAM pressure
DB pool capacity
local GPU lane
filesystem I/O
per-instance concurrency
generic job capacity
```

Does not own:

```text
LLM provider route selection
Prompt A/B semantics
source units
artifact payload
work item lifecycle
```

### Knowledge Workbench Saga

Owns:

```text
business workflow
phase vocabulary
expected outputs
commands/events
resume/reconciliation policy
manual wait policy
publication checkpoint
cleanup checkpoint
```


## 7. High-level workflow

Canonical high-level workflow:

```text
Document accepted/uploaded
SourceDocument persisted
SourceUnits created
Prompt A work scheduled
Prompt A work executed through Execution + LLM Runtime
raw/parsed Prompt A artifacts stored
ArtifactStored(parsed) observed
draft embeddings built
semantic clusters built
Prompt B work scheduled
Prompt B synthesis executed
final knowledge normalized/deduped/saved
review ready
manual review/edit/delete
publication
retrieval embeddings/projections
cleanup intermediate artifacts
done
```

The saga advances by durable state and events, not by a linear in-memory script. It must be able to resume after any phase, during any phase, or after partial completion of item-level work.

## 8. Saga phases

Stable canonical phase keys:

```text
DOCUMENT_ACCEPTED
SOURCE_DOCUMENT_PERSISTED
SOURCE_UNITS_CREATED
PROMPT_A_WORK_SCHEDULED
PROMPT_A_WORK_COMPLETED
PROMPT_A_ARTIFACTS_APPLIED
DRAFT_EMBEDDINGS_BUILT
DRAFT_CLUSTERS_BUILT
PROMPT_B_WORK_SCHEDULED
PROMPT_B_WORK_COMPLETED
FINAL_KNOWLEDGE_PREPARED
WAITING_FOR_REVIEW
REVIEW_COMPLETED
PUBLISHED
RETRIEVAL_EMBEDDINGS_BUILT
INTERMEDIATE_ARTIFACTS_CLEANED
DONE
```

Phase meanings:

```text
DOCUMENT_ACCEPTED:
  The system accepted an upload/request and created or is ready to create a workflow run.

SOURCE_DOCUMENT_PERSISTED:
  Canonical source document state exists.

SOURCE_UNITS_CREATED:
  Canonical source units/chunks/sections exist with deterministic identity and lineage.

PROMPT_A_WORK_SCHEDULED:
  Work items for Prompt A extraction exist for all expected source units.

PROMPT_A_WORK_COMPLETED:
  Prompt A execution work items reached terminal successful output state or all blockers are explicit.

PROMPT_A_ARTIFACTS_APPLIED:

DRAFT_EMBEDDINGS_BUILT:
  Embeddings for draft observations exist for the selected embedding model/version.

DRAFT_CLUSTERS_BUILT:
  Semantic clusters/subclusters exist for draft observations.

PROMPT_B_WORK_SCHEDULED:
  Work items for Prompt B / cluster synthesis exist.

PROMPT_B_WORK_COMPLETED:
  Prompt B synthesis artifacts/results exist or blockers are explicit.

FINAL_KNOWLEDGE_PREPARED:
  Final/consolidated knowledge entries were normalized, deduped, and saved for review.

WAITING_FOR_REVIEW:
  User/manual curation is required before publication.

REVIEW_COMPLETED:
  User decisions are persisted and publication may proceed.

PUBLISHED:
  Approved knowledge was published as a versioned publication output.

RETRIEVAL_EMBEDDINGS_BUILT:
  Retrieval-facing embeddings/projections exist for published knowledge.

INTERMEDIATE_ARTIFACTS_CLEANED:
  Cleanup phase completed or all cleanup exceptions are recorded.

DONE:
  The workflow is complete.
```

## 9. Durable saga state model

Canonical future table name:

```text
knowledge_extraction_workflow_runs
```

This table must be new canonical persistence. It must not reuse `knowledge_workbench_processing_runs` as canonical state.

Fields to design later:

```text
knowledge_extraction_workflow_runs:
- workflow_run_id
- project_id
- document_ref / source_document_ref
- status
- current_phase
- pause_reason
- failure_kind
- failure_message
- review_status
- publication_ref
- cleanup_status
- created_at
- updated_at
- completed_at
- cancelled_at
```

Suggested workflow statuses:

```text
CREATED
RUNNING
PAUSED
WAITING_FOR_EXTERNAL_EVENT
WAITING_FOR_REVIEW
FAILED
CANCELLED
COMPLETED
```


## 10. Phase checkpoint model

Canonical future table name:

```text
knowledge_extraction_phase_checkpoints
```

Fields to design later:

```text
knowledge_extraction_phase_checkpoints:
- workflow_run_id
- phase_key
- phase_status
- expected_count
- completed_count
- failed_count
- blocked_count
- idempotency_key
- last_event_ref
- checkpoint_payload
- updated_at
```

Suggested phase statuses:

```text
NOT_STARTED
READY
IN_PROGRESS
WAITING
BLOCKED
COMPLETED
SKIPPED
FAILED
CANCELLED
```

Checkpoints must not duplicate local runtime state. They summarize and point to durable outputs owned by other contexts.

## 11. Idempotency model

Resume and retries must be based on deterministic identities, not on in-memory current step.

Minimum idempotency keys:

```text
source document:
  project_id + upload_id or content_hash + source_document_ref

source unit:
  source_document_ref + unit_ordinal + unit_lineage_hash

Prompt A work item:
  claim-extraction:{prompt_id}:{source_unit_ref}

  workflow_run_id + stage_run_id + work_item_id + work_item_attempt_id + llm_attempt_id + raw

  workflow_run_id + stage_run_id + work_item_id + work_item_attempt_id + llm_attempt_id + parsed

draft observation:
  validated_prompt_output_trace + claim_index

draft embedding:
  draft_observation_ref + embedding_model_id + embedding_contract_version

cluster:
  workflow_run_id + clustering_version + sorted_member_refs_hash

Prompt B work item:
  prompt_b:{prompt_version}:{cluster_ref or subcluster_ref}

Prompt B artifact:
  workflow_run_id + prompt_b_stage_run_id + work_item_id + work_item_attempt_id + llm_attempt_id + raw/parsed

final knowledge entry:
  workflow_run_id + canonical_intent_ref + consolidation_version

publication:
  publication_run_ref + approved_knowledge_version

retrieval embedding:
  publication_ref + knowledge_surface_ref + embedding_model_id

cleanup artifact action:
  workflow_run_id + artifact_ref + retention_policy_version
```

Duplicate command emission must be prevented by a command log. Duplicate event handling must be prevented by an event cursor/inbox.

Command log fields to design later:

```text
knowledge_extraction_command_log:
- command_key
- workflow_run_id
- phase_key
- target_context
- command_kind
- command_payload_hash
- status
- emitted_at
- completed_at
- result_ref
```

Event cursor fields to design later:

```text
knowledge_extraction_event_cursor:
- consumer_name
- event_id / outbox_event_id
- workflow_run_id
- event_type
- processed_at
- handler_result
```

## 12. Event map

Canonical event map, with current availability:

```text
SourceDocumentCreated:
  status: exists as source-management domain direction / event family
  owner: knowledge_workbench/source_management

SourceUnitCreated / SourceUnitSplit:
  status: exists as source-management direction / event family
  owner: knowledge_workbench/source_management

WorkItemsCreated:
  status: missing as domain event; currently command result/read model territory
  owner: knowledge_workbench/extraction or saga checkpoint later

WorkItemCompleted / WorkItemDeferred / WorkItemFailed / WorkItemCancelled:
  status: exists in Execution Runtime event family
  owner: execution_runtime

LlmTaskSucceeded / LlmTaskDeferred / LlmTaskFailed / LlmDailyLimitExhausted / LlmMinuteLimitHit:
  status: exists in LLM Runtime event family
  owner: llm_runtime

ArtifactStored:
  status: exists
  note: carries artifact_ref and occurred_at only; handlers must load artifact to inspect kind/payload.

DraftClaimObservationsApplied:
  status: exists
  owner: knowledge_workbench/extraction

DraftEmbeddingsBuilt:
  status: missing
  owner: embedding_runtime or Workbench embedding boundary later

ClustersBuilt:
  status: missing
  owner: consolidation/clustering later

PromptBSynthesisCompleted:
  status: missing
  owner: consolidation / Prompt B process later

FinalKnowledgeReady:
  status: missing
  owner: knowledge_workbench manual curation / consolidation boundary later

ManualReviewCompleted / KnowledgeApprovedForPublication:
  status: missing
  owner: knowledge_workbench manual curation

Published / KnowledgePublished:
  status: partially represented by publication domain; canonical event contract missing
  owner: knowledge_workbench/publication

RetrievalEmbeddingsBuilt:
  status: missing
  owner: embedding_runtime / retrieval publication boundary later

IntermediateArtifactsCleaned:
  status: missing
```

## 13. Command map

Canonical command map:

```text
PersistSourceDocument:
  target: knowledge_workbench/source_management

SplitSourceDocument / CreateSourceUnits:
  target: knowledge_workbench/source_management

SchedulePromptAWork:
  target: knowledge_workbench/extraction + execution_runtime
  current reusable use case: RunClaimExtractionStageAsync

ExecutePromptAWorkItem:
  target: knowledge_workbench/extraction + execution_runtime + llm_runtime
  current reusable process manager: ProcessClaimExtractionWorkItem

ReserveLlmRoute:
  target: llm_runtime
  current status: future durable reservation, not implemented yet

PersistPromptAArtifacts:
  current reusable boundary: RecordClaimExtractionSuccess

ApplyPromptAParsedArtifact:
  target: knowledge_workbench/extraction
  current reusable boundary: ApplyDraftClaimObservationArtifactOnArtifactStored + ApplyDraftClaimObservationArtifactAsync

BuildDraftEmbeddings:
  target: embedding_runtime
  current status: future use case / UoW / persistence missing

BuildDraftClusters:
  target: knowledge_workbench/consolidation or clustering boundary
  current status: domain concepts partial, app/persistence missing

SchedulePromptBWork:
  target: knowledge_workbench/consolidation + execution_runtime + llm_runtime
  current status: missing

ExecutePromptBWorkItem:
  target: knowledge_workbench/consolidation + execution_runtime + llm_runtime
  current status: missing

PrepareFinalKnowledge:
  target: knowledge_workbench/consolidation / manual curation
  current status: missing canonical boundary

CompleteManualReview:
  target: knowledge_workbench/manual curation
  current status: missing canonical boundary

PublishKnowledge:
  target: knowledge_workbench/publication
  current status: partial domain, canonical application contract missing

BuildRetrievalEmbeddings:
  target: embedding_runtime + publication/retrieval boundary
  current status: missing canonical boundary

CleanupIntermediateArtifacts:
  current status: missing canonical boundary
```

## 14. Resume/reconciliation model

Resume is not:

```text
current_step += 1
```

Resume is reconciliation:

```text
expected outputs
existing outputs
missing outputs
in-flight work
deferred work
terminal failure
manual wait
already published
safe retry
unsafe retry
```

The saga must decide progress by comparing expected durable outputs to existing durable outputs.

Examples:

```text
SOURCE_UNITS_CREATED:
  expected: source units for source_document_ref
  existing: canonical source_units rows
  action: create missing source units only if source document exists and split contract is deterministic

PROMPT_A_WORK_SCHEDULED:
  expected: one Prompt A work item per source_unit_ref and prompt_version
  existing: claim_extraction_stage_work_items + execution_work_items
  action: create missing deterministic work items only

PROMPT_A_WORK_COMPLETED:
  expected: completed work items or explicit blockers for all source units
  existing: execution_work_items, execution_work_item_attempts, pipeline artifacts
  action: release expired leases, requeue due deferred/retryable work, block terminal/user-action cases

PROMPT_A_ARTIFACTS_APPLIED:
  existing: draft_claim_observations + draft_claim_observation_provenance

DRAFT_EMBEDDINGS_BUILT:
  expected: embedding vector per draft observation per embedding contract
  existing: future embedding rows
  action: emit missing embedding commands only

WAITING_FOR_REVIEW:
  expected: final knowledge entries visible to manual review
  existing: future curation/review rows
  action: wait for user action; do not auto-publish

PUBLISHED:
  expected: publication version exists
  existing: publication rows/projections
  action: never republish without explicit idempotent publication command key

INTERMEDIATE_ARTIFACTS_CLEANED:
  expected: cleanup action result for each intermediate artifact
  existing: future cleanup records / artifact retention state
  action: apply retention only to missing cleanup actions
```

Unsafe retry conditions:

```text
terminal failed work without user decision
cancelled workflow
published workflow without explicit republish policy
manual review not completed
artifact exists but has invalid provenance
legacy row without canonical mapping
```

Safe retry conditions:

```text
missing expected output with deterministic idempotency key
retryable failed work item whose retry condition is due
deferred work item whose wait_until passed
expired lease reclaimed by Execution Runtime
unpublished outbox event not yet processed by this consumer
cleanup action not yet recorded
```

## 15. Outbox and event consumer contract

Canonical boundary:

```text
outbox_events table
→ Outbox polling/delivery infrastructure
→ Application Event Dispatcher
→ context-specific application handler
→ idempotent event cursor/inbox
```

The outbox polling/delivery infrastructure owns:

```text
polling unpublished outbox rows
locking / claiming events for delivery
retry attempts
published_at
publish_attempt_count
last_publish_error
backoff policy
```

Application Event Dispatcher owns:

```text
event_type routing
handler lookup
handler invocation contract
normalizing handler result
```

Context-specific application handlers own:

```text
business reaction to one event
loading extra state if event payload is insufficient
calling the correct application use case
returning idempotent result
```

For example:

```text
ArtifactStored
→ Workbench handler loads artifact by artifact_ref
→ verifies Prompt A parsed kind
→ calls ApplyDraftClaimObservationArtifactAsync
```

Forbidden:

```text
ArtifactStored handler directly in JobDispatcher
worker_loop as outbox consumer without separate outbox contract
event_type routing spread across Workbench use cases
saga directly polling outbox_events
saga directly marking published_at
```

Current known gap: generic outbox consumer/event router is absent and must be designed in a separate patch. This document does not add it.

## 16. LLM reservation boundary

Future Postgres-backed durable LLM capacity model names:

```text
llm_quota_windows
llm_route_reservations
llm_provider_usage_records
```

Purpose:

```text
avoid parallel workers reading the same stateless quota snapshot and over-scheduling provider/account/model lanes
```

LLM Runtime reservation should support:

```text
reserve provider/account/model route capacity before provider call
reserve estimated input tokens + reserved output tokens
commit reservation with actual usage after response
release/expire reservation if provider call never happens
update quota window from provider headers
surface wait_until or daily exhausted decisions
```

LLM Runtime reservation must not include:

```text
CPU/RAM pressure
worker slots
DB pool capacity
local GPU lane
source unit semantics
Prompt A/B business decisions
```

No SQL is designed in this document. The names above are architectural targets only.

## 17. Future capacity runtime boundary

Future Capacity Runtime names:

```text
capacity_runtime
resource_runtime
execution_capacity
```

Preferred conceptual name for now:

```text
capacity_runtime
```

Question answered by this future context:

```text
can this app instance start more work of this class now?
```

Owns:

```text
worker slots
CPU/RAM pressure
DB pool capacity
local GPU lane
filesystem I/O
per-instance concurrency
generic job capacity
```

Must not own:

```text
LLM provider route selection
Prompt A/B semantics
source units
artifact payload
work item lifecycle
```

Relationship to Execution Runtime:

```text
Execution Runtime decides which work item can be leased and what its lifecycle state is.
Capacity Runtime decides whether this app instance should start more runnable work now.
```

Relationship to LLM Runtime:

```text
Capacity Runtime says how many LLM-bound jobs this instance may start.
LLM Runtime says which provider/account/model lanes can accept those jobs.
```

## 18. Source persistence boundary

Canonical source persistence is required later:

```text
source_documents
source_units
source_unit_lineage / source_unit_chunks if needed
```

Source persistence belongs to Knowledge Workbench Source Management, not old FAQ tables.

SourceDocument and SourceUnit are project-level Workbench entities. They should have deterministic identity, source lineage, normalized content/reference metadata, and enough state for resume/reconciliation.

Forbidden:

```text
using old FAQ/workbench document tables as canonical source persistence without explicit migration/mapping design
making Extraction own canonical source persistence
```

## 19. Embedding runtime boundary

Embeddings must be represented as a separate runtime/domain boundary:

```text
embedding_runtime
```

Reason: embedding provider/model/dimensions/batch strategy/local-vs-remote execution can change independently from Workbench business workflow.

Workbench Saga emits:

```text
BuildEmbeddings
```

Embedding Runtime owns:

```text
embedding model identity
embedding dimensions
batch execution strategy
provider/local implementation
vector persistence
usage/error metadata
```

Workbench Saga owns:

```text
which semantic objects require embeddings
which phase waits for embeddings
how missing embeddings affect resume
```

Embedding Runtime must not own:

```text
manual review
publication decision
source document splitting
Prompt A/B semantics
```

## 20. Manual review boundary

Ideal manual review boundary:

```text
FinalKnowledgeReady
→ Saga status WAITING_FOR_REVIEW
→ user edits/deletes/approves entries
→ ManualReviewCompleted / KnowledgeApprovedForPublication
→ Saga continues to publication
```

Manual review is:

```text
Workbench manual curation checkpoint + audit trail
```

It is not:

```text
Execution Runtime user-action internals only
frontend-only flag
publication itself
```

Manual review persistence must support later:

```text
who changed what
approved/rejected/deleted/edited entries
before/after values when relevant
review completion event
resume after partial review
```

## 21. Publication boundary

Publication belongs to Knowledge Workbench Publication.

Publication is not the same as manual review. Manual review approves the knowledge state; publication creates a versioned runtime/retrieval-facing output.

Future publication boundary should include:

```text
publication_run_ref
approved knowledge version
published knowledge surfaces
retrieval projection references
publication event
rollback/supersede policy if needed
```

Saga phase relation:

```text
REVIEW_COMPLETED
→ PublishKnowledge command
→ PUBLISHED
→ BuildRetrievalEmbeddings / projections
```


## 22. Cleanup boundary

Cleanup is a separate idempotent phase:

```text
CleanupIntermediateArtifactsRequested
→ build cleanup plan by workflow_run_id + retention policy
→ record per-artifact cleanup result
→ IntermediateArtifactsCleaned
```

Cleanup must be:

```text
idempotent
auditable
safe after resume
not deleting source document
not deleting published/retrieval artifacts
not deleting review audit trail
not relying on in-memory phase state
```

Cleanup should prefer explicit artifact retention/expiration contracts over ad-hoc hard delete when possible.

Future cleanup action idempotency key:

```text
workflow_run_id + artifact_ref + retention_policy_version
```

Cleanup result should be recorded per artifact or per cleanup action so resume can skip already-cleaned artifacts and retry only missing/failed cleanup actions.

## 23. What must not be implemented as part of Saga

The saga must not implement:

```text
DB SQL directly in saga
Groq/provider code in saga
asyncpg/postgres imports in saga
queue worker mechanics in saga
outbox polling in saga
artifact payload storage implementation in saga
execution lease internals in saga
LLM quota internals in saga
generic capacity internals in saga
legacy Workbench v1/v2 tables as canonical state
SectionBatchQueueItem as canonical phase item
workbench_parallel_processing as canonical handler
process_workbench_document as canonical handler
```

The saga must not become one service that does everything.


The saga must not directly call provider adapters, SQL repositories, queue workers, or frontend code.


## 24. First safe code skeleton after this document

First safe code patch after this document:

```text
Create application-level saga contracts only:

src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_saga.py
src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_saga_state.py
src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_saga_ports.py
```

Allowed scope of that next code skeleton:

```text
pure dataclasses/value objects for saga state
phase key vocabulary
status vocabulary
port Protocols for reading checkpoints and emitting commands
no infrastructure
no migrations
no worker wiring
no outbox polling
no production execution
no asyncpg/postgres imports
no provider imports
```

The skeleton must not create a second orchestrator. It should encode contracts and boundaries only.

## 25. Known gaps

Known gaps before production saga wiring:

```text
No canonical knowledge_extraction_workflow_runs table yet.
No canonical knowledge_extraction_phase_checkpoints table yet.
No knowledge_extraction_command_log table yet.
No knowledge_extraction_event_cursor/inbox table yet.
No generic outbox consumer/event router yet.
No durable LLM quota reservation/window persistence yet.
No generic capacity_runtime/resource_runtime yet.
Canonical source_documents/source_units persistence still needs design.
Embedding Runtime has domain concepts but needs application/UoW/persistence.
Cluster/subcluster/consolidated surface persistence and application boundaries are incomplete.
Prompt B scheduling/execution/result application is not defined yet.
Manual review/edit/delete audit model is not defined yet.
Publication application boundary is partial and must be stabilized later.
Retrieval embeddings/projections for published knowledge need canonical boundaries.
Cleanup intermediate artifacts needs idempotent/auditable execution contract.
```

Known legacy/reference-only material:

```text
migrations/070_create_faq_workbench_v1.sql
knowledge_workbench_processing_runs
old Workbench v1/v2/FAQ tables
workbench_parallel_processing
process_workbench_document
SectionBatchQueueItem
```

These must not be treated as the canonical saga path.
