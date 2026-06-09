# New Workbench Implementation Playbook

Purpose: finish the new `src/contexts` Workbench replacement without extending legacy Workbench.

Strategy: build the new vertical in parallel under `src/contexts`, restore user-visible functionality on top of new backend read models, then retire legacy paths.

This document is the operating contract for agents working on the new Workbench implementation. It is not a narrative architecture note. It is a guardrail document: read it, inspect current code, identify the bounded context, patch the smallest target, add a guard when needed, and stop.

---

## Standard agent task

Use this prompt shape:

```text
Mode: RECON ONLY | DESIGN ONLY | PATCH ONLY
Phase: PHASE XX
Task: one concrete sentence
Follow docs/architecture/new_workbench_implementation_playbook.md.
```

The agent must read this file, inspect current code for the selected phase, and avoid inventing names, paths, columns, statuses, methods, DTOs, entities, tables, events, or lifecycle semantics.

---

## Modes

### RECON ONLY

Inspect and report. No edits.

Required output:

```text
Inspected files:
Relevant current contracts:
Found drift:
Found missing contracts:
Recommended next patch:
Files that must not be touched:
```

### DESIGN ONLY

Propose target shape. No edits.

Required output:

```text
Owning bounded context:
Problem:
Current contract:
Proposed contract:
Alternatives considered:
Rejected alternatives:
Migration/persistence impact:
Read model impact:
Testing strategy:
Next smallest patch:
```

### PATCH ONLY

Patch the smallest approved slice.

Before PATCH ONLY, the agent must state:

```text
Mode:
Phase:
Task:
Owning bounded context:
Pattern used:
Entities touched:
Value objects touched:
State machine affected:
Unit of Work affected:
Outbox affected:
Read model affected:
Migration affected:
Allowed files:
Forbidden files:
Tests:
What was inspected:
```

If this pre-patch statement cannot be completed accurately, stop and perform RECON ONLY.

---

## Global hard rules

1. New canonical code belongs under `src/contexts`.
2. Do not add new canonical orchestration to old application services, old Workbench modules, old queue handlers, old infrastructure LLM modules, or old project-plane Workbench domain.
3. Do not add new names without a bounded context owner.
4. Do not change lifecycle status outside a state machine.
5. If one operation persists multiple durable facts, use a Unit of Work.
6. If a durable state change has follow-up effects, append an outbox event in the same transaction.
7. Frontend displays backend read models; frontend must not invent lifecycle semantics.
8. Legacy Workbench may be read, bridged temporarily, or retired, but not expanded as the new target path.
9. Runtime contexts must not import Workbench contexts.
10. Workbench contexts may orchestrate runtime contexts through explicit ports, use cases, value objects, and domain contracts.
11. Do not create a table because a DTO needs persistence. Every table must have a bounded-context owner and a source-of-truth/projection role.
12. Do not maintain parallel sync and async production orchestration paths.
13. Production runtime composition is async.
14. Pure domain logic may remain sync.
15. No broad phase jump: a patch may touch one phase only unless it is explicitly a recon/design patch proving why an earlier phase must be amended.
16. If a later phase requires changing an earlier phase, stop and perform PHASE 00 on the affected boundary first.
17. Do not run broad test suites unless explicitly requested. Use focused tests for the touched bounded context.

---

## Context dependency map

### Allowed dependency direction

```text
knowledge_workbench/extraction
  may depend on:
    execution_runtime domain/application contracts
    llm_runtime application/domain contracts
    artifact_runtime domain/application contracts
    knowledge_workbench/source_management domain refs

knowledge_workbench/consolidation
  may depend on:
    extraction draft observation refs/entities
    artifact_runtime contracts
    execution_runtime contracts only for consolidation WorkItems if needed
    llm_runtime contracts only for Prompt C execution if needed

knowledge_workbench/publication
  may depend on:
    consolidation outputs
    artifact_runtime contracts
    embedding/retrieval contracts
    runtime projection contracts

execution_runtime
  must not depend on:
    knowledge_workbench
    llm_runtime
    artifact_runtime
    provider-specific code
    frontend

llm_runtime
  must not depend on:
    knowledge_workbench
    artifact_runtime claim/surface semantics
    frontend
    publication

artifact_runtime
  must not depend on:
    knowledge_workbench claim/surface semantics
    llm provider semantics
    frontend lifecycle

source_management
  must not depend on:
    extraction WorkItem creation
    Prompt A
    LLM Runtime
    artifact persistence
    consolidation
    publication
```

### Forbidden dependency direction

```text
execution_runtime -> knowledge_workbench
llm_runtime -> knowledge_workbench
artifact_runtime -> knowledge_workbench semantic parsers
source_management -> extraction
frontend -> lifecycle inference
legacy Workbench -> new canonical orchestration
```

---

## Canonical contexts

### Execution Runtime

Path:

```text
src/contexts/execution_runtime/
```

Owns:

```text
WorkItem
WorkItemAttempt
WorkKind
WorkItemStatus
LeaseToken
WorkerRef
WaitUntil
WorkItemStateMachine
WorkItem events
WorkItem UoW
execution repositories/adapters
lease/reclaim/complete/defer/fail/cancel use cases
```

Tables:

```text
execution_work_items
execution_work_item_attempts
```

Migration:

```text
083_create_execution_runtime_tables.sql
```

Execution Runtime owns generic execution lifecycle only.

It does not own:

```text
Prompt A
Prompt C
Groq
claims
source units
surfaces
documents
frontend state
Workbench stage semantics
LLM provider routing semantics
artifact payload semantics
```

Execution Runtime may store generic error hints such as `last_error_kind`, but it must not become the owner of Workbench or LLM business meaning.

---

### LLM Runtime

Path:

```text
src/contexts/llm_runtime/
```

Owns:

```text
LlmTask
LlmAttempt
LlmTaskStatus
LlmTaskStateMachine
LlmErrorKind
route planning
quota decisions
provider/model/account identity
token usage
provider ports
provider adapters
LLM output validation
LLM task UoW
provider-neutral execution result
```

Tables:

```text
llm_tasks
llm_attempts
```

Migration:

```text
084_create_llm_runtime_tables.sql
```

LLM Runtime owns provider-neutral LLM execution semantics.

It does not own:

```text
Workbench stages
draft claims
consolidated surfaces
source splitting
artifact application
frontend decisions
publication
manual curation
```

Provider success is not task success. A provider can return text successfully while the LLM task still fails validation.

Groq is not LLM Runtime. Groq is one provider adapter behind LLM Runtime contracts.

---

### Artifact Runtime

Path:

```text
src/contexts/artifact_runtime/
```

Owns:

```text
PipelineArtifact
ArtifactRef
ArtifactKind
ArtifactPayload
ArtifactStatus
ArtifactVisibility
ArtifactLineage
RetentionPolicy
artifact events
artifact UoW
artifact repositories/adapters
artifact lifecycle use cases
artifact query use cases
```

Tables:

```text
pipeline_artifacts
pipeline_artifact_lineage
```

Migration:

```text
085_create_artifact_runtime_tables.sql
```

Artifact Runtime owns artifact lifecycle and lineage.

Artifact payload is opaque to Artifact Runtime.

Artifact Runtime does not own:

```text
claim parsing
surface parsing
Prompt A schema
Prompt C schema
Workbench lifecycle
LLM provider failures
frontend state
publication semantics
```

Workbench contexts may parse Workbench-specific artifacts. Artifact Runtime must not parse Workbench semantics.

---

### Context Outbox

Table:

```text
outbox_events
```

Migration:

```text
086_create_context_outbox_events.sql
```

Context Outbox owns durable event publication state.

Events must be committed with the state change that caused them.

Current outbox v0 is acceptable for early phases. Before outbox handlers become production-critical, decide whether to add:

```text
event_version
context_name
aggregate_type
correlation_id
causation_id
deduplication_key
```

Do not add these fields ad hoc in unrelated patches.

---

### Source Management

Path:

```text
src/contexts/knowledge_workbench/source_management/
```

Owns:

```text
SourceDocument
SourceUnit
SourceDocumentRef
SourceUnitRef
SourceUnitKind
SourceUnitText
SourceUnitLineage
source format
split reason
heading path
parsing
normalization
mechanical splitting
hierarchical units
source lineage
token estimate if used for splitting
```

Source Management does not own:

```text
extraction WorkItem creation
Prompt A
LLM Runtime
artifact persistence
draft claims
consolidation
publication
frontend lifecycle
```

SourceUnit is source material, not extracted knowledge.

---

### Extraction

Path:

```text
src/contexts/knowledge_workbench/extraction/
```

Owns:

```text
claim extraction stage
Prompt A application boundary
DraftClaimObservation
DraftClaimObservationRef
PossibleQuestion
ExclusionScope
EvidenceBlock
CreateExtractionWorkItems
RunClaimExtractionStage
ResumeClaimExtractionStage
ApplyDraftClaimObservationArtifact
claim extraction process managers
extraction UoW ports
stage work item index
stage progress read model
stage blocker interpretation
```

Tables:

```text
draft_claim_observations
draft_claim_observation_possible_questions
claim_extraction_stage_work_items
```

Migrations:

```text
087_create_draft_claim_observations.sql
088_create_claim_extraction_stage_work_item_index.sql
```

Extraction owns Workbench interpretation of claim extraction runtime outcomes.

Extraction does not own:

```text
provider details
model routing internals
generic artifact lifecycle
generic work item lifecycle
consolidation
publication
frontend-only lifecycle state
```

---

### Consolidation

Path:

```text
src/contexts/knowledge_workbench/consolidation/
```

Owns:

```text
Prompt C boundary
DraftClaimCluster
Subcluster
ConsolidatedSurface
ConsolidatedSurfaceRef
CanonicalIntent
SurfaceKind
SurfaceEvidenceRef
OntologyTag
SurfaceRelation
cluster sizing
consolidation artifact parser
consolidation process managers
```

Consolidation must not silently drop retrieval-facing fields:

```text
possible_questions
exclusion_scope
evidence refs
source observation refs
canonical intent
answer/surface text
ontology tags
relations
```

Consolidation does not own:

```text
publication
runtime retrieval
frontend curation
legacy registry merge
generic LLM provider logic
```

---

### Future bounded areas

These areas must not be implemented as random subfolders or generic services. Each must become an explicit bounded area before production logic is added:

```text
rag_enrichment
retrieval_evaluation
curation
publication
runtime_projection
```

---

## Canonical vocabulary

Use these names when they match the concept:

```text
SourceDocument
SourceUnit
WorkItem
WorkItemAttempt
LlmTask
LlmAttempt
PipelineArtifact
DraftClaimObservation
DraftClaimCluster
ConsolidatedSurface
KnowledgeSurface
PublicationRun
PublicationVersion
RuntimeProjectionRef
RetrievalEvalRun
CurationDecision
```

Do not introduce synonyms without a bounded-context decision.

Forbidden synonym drift:

```text
Job / QueueJob / TaskItem instead of WorkItem
NodeRun instead of LlmTask / WorkItem / Artifact checkpoint
Card instead of DraftClaimObservation or ConsolidatedSurface
RegistryEntry unless the owning context explicitly defines a registry
CompilerRun for new canonical Workbench execution
SurfaceCard for new extraction output
DTO used as domain entity
```

---

## Canonical distinctions

```text
WorkItem != LlmTask != PipelineArtifact
SourceUnit != DraftClaimObservation != ConsolidatedSurface != KnowledgeSurface
Prompt A != LLM Runtime
Prompt C != Artifact Runtime
Groq != LLM Runtime
Provider success != LLM task success
DTO != Entity
Repository != Use Case
Service != State Machine
Queue != Pipeline
Status != Checkpoint
Status != Reason
Reason != NextAction
Artifact existence != WorkItem lifecycle
Read model != Source of Truth
Frontend state != Backend lifecycle
```

---

## Target workflow map

The new Workbench replacement target flow is:

```text
1. SourceDocument uploaded
2. Source Management parses and splits it into SourceUnits
3. Extraction fan-out creates WorkItems for SourceUnits
4. Execution Runtime leases a WorkItem
5. Extraction process manager executes Prompt A through LLM Runtime
6. LLM Runtime returns provider-neutral outcome
7. Extraction artifact factory creates raw/parsed/error/split artifacts from actual outcome
8. Artifact Runtime persists artifacts and lineage
9. Extraction records WorkItem/LlmTask/LlmAttempt/artifacts/events in one UoW
10. ApplyDraftClaimObservationArtifact parses persisted parsed artifact
11. DraftClaimObservations are persisted
12. Extraction progress read model exposes progress, blockers, reasons, next actions
13. Consolidation clusters DraftClaimObservations
14. Prompt C creates ConsolidatedSurfaces
15. Embedding, clustering, enrichment, evaluation, and curation happen
16. Publication creates KnowledgeSurfaces and runtime projections
17. Frontend reads backend read models only
18. Legacy paths are retired after replacement functionality exists
```

No phase may skip source-of-truth creation and replace it with frontend inference.

---

## Checkpoint / source-of-truth matrix

```text
Execution lifecycle
  Source of truth:
    execution_work_items
    execution_work_item_attempts
  Projection/read model:
    WorkItem progress/readiness

LLM execution
  Source of truth:
    llm_tasks
    llm_attempts
  Projection/read model:
    LLM execution status, quota/retry diagnostics

Artifact persistence
  Source of truth:
    pipeline_artifacts
    pipeline_artifact_lineage
  Projection/read model:
    artifact lists, resume candidates, lineage graph

Outbox
  Source of truth:
    outbox_events
  Projection/read model:
    unpublished/published integration events

Claim extraction stage membership
  Source of truth:
    claim_extraction_stage_work_items
  Projection/read model:
    claim extraction stage progress

Prompt A raw output
  Source of truth:
    pipeline_artifacts with raw Prompt A artifact kind

Prompt A parsed output
  Source of truth:
    pipeline_artifacts with parsed Prompt A artifact kind

Applied draft claims
  Source of truth:
    draft_claim_observations
    draft_claim_observation_possible_questions

Claim extraction blockers
  Source of truth:
    not permanently decided yet
  Current allowed derivation:
    WorkItem status
    WorkItem last_error_kind
    LlmTask/LlmAttempt error kind
    outbox events
    artifact status/lineage
  Open decision:
    explicit blocker projection vs reconstruction

Consolidated surfaces
  Source of truth:
    consolidation-owned tables/artifacts

Published runtime knowledge
  Source of truth:
    publication-owned KnowledgeSurface / PublicationVersion / RuntimeProjection
```

---

## Recovery / blocker reason contract

WorkItemStatus is lifecycle only.

It must not be used as the only explanation for progress/readiness.

The governing rule is:

```text
status != reason != next_action != checkpoint
```

### Layered reason ownership

LLM Runtime owns provider/output execution reasons, such as:

```text
minute_limit
daily_limit
provider_transient
network_transient
request_too_large
output_too_large
invalid_output
validation_failed
empty_output
empty_claims
auth_error
provider_terminal
unknown
```

Artifact Runtime owns artifact validity/lifecycle reasons, such as:

```text
artifact_stored
artifact_validated
artifact_rejected
artifact_schema_invalid
artifact_superseded
artifact_expired
```

Execution Runtime owns lifecycle states, not domain-specific reasons:

```text
ready
leased
deferred
retryable_failed
terminal_failed
completed
cancelled
split_superseded
user_action_required
```

Knowledge Workbench Extraction owns stage blocker interpretation, such as:

```text
waiting_for_minute_quota
waiting_for_daily_reset
provider_retry_scheduled
network_retry_scheduled
invalid_output_retry_scheduled
validation_retry_scheduled
empty_output_retry_scheduled
empty_claims_confirmation_required
source_unit_split_required
daily_limit_requires_user_choice
terminal_failure
cancelled
```

### Stage progress derivation

Stage progress must be derived from:

```text
WorkItemStatus
+ runtime reason
+ wait_until / next_attempt_at
+ artifact/application events
+ Workbench blocker interpretation
```

It must not be derived from WorkItemStatus alone.

Forbidden logic:

```python
if deferred_count > 0 or retryable_failed_count > 0:
    return WAITING_FOR_QUOTA
```

Forbidden logic:

```python
if nearest_wait_until is not None:
    return QUOTA_WAIT
```

unless the underlying reason is actually quota-related.

### Recommended read model fields

Claim extraction progress read models should expose backend-owned fields such as:

```text
status
blocker_kind
blocker_reason
next_action
resume_after
affected_work_item_count
ready_count
leased_count
deferred_count
retryable_failed_count
user_action_required_count
terminal_failed_count
completed_count
split_superseded_count
cancelled_count
artifacts_count
```

Frontend must display these fields. Frontend must not infer lifecycle or blocker semantics from raw statuses.

---

## Artifact construction contract

Process managers must not accept prebuilt success artifacts as trusted facts unless those artifacts are produced by an explicit artifact factory from the actual LLM outcome in the same process.

Correct flow:

```text
LLM outcome
-> artifact factory
-> raw artifact
-> parsed/validated artifact
-> UoW commit
-> artifact application
```

Forbidden flow:

```text
caller-prebuilt parsed artifact
-> accepted as proof of actual LLM output
```

Artifact construction belongs to the orchestrating Workbench context when artifact semantics are Workbench-specific.

Artifact Runtime stores artifacts. Workbench-specific artifact factories/parsers interpret Workbench-specific payloads.

---

## Traceability / provenance contract

Every user-visible knowledge unit must be traceable back to source evidence and runtime artifacts.

This applies to:

```text
DraftClaimObservation
ConsolidatedSurface
KnowledgeSurface
RuntimeProjection
frontend-visible answer/evidence/debug view
```

Minimum traceability target:

```text
source_document_ref
source_unit_ref
prompt_id
prompt_version
llm_task_id
llm_attempt_id
raw_artifact_ref
parsed_artifact_ref
applied_domain_entity_ref
consolidation/publication step ref
```

No DraftClaimObservation, ConsolidatedSurface, or KnowledgeSurface may become user-visible unless it can be traced back to source evidence and runtime artifacts.

Traceability may be stored explicitly or reconstructed through lineage, but the chosen strategy must be documented before frontend restore/publication.

---

## Open design decisions

These are intentionally not fully solved by this document. Do not resolve them accidentally inside unrelated patches.

### 1. Durable blocker storage

Before frontend restore or consolidation depends on blocker explanations, choose one durable strategy:

```text
A. explicit claim_extraction_stage_blockers projection/table
B. reconstruction from WorkItem + LlmTask/LlmAttempt + outbox events + artifact lineage
```

Until this is decided:

```text
do not add ad-hoc blocker fields to unrelated tables
do not encode Workbench blocker semantics into Execution Runtime
do not rely on frontend inference
```

### 2. DraftClaimObservation provenance

Choose one strategy:

```text
A. explicit DraftClaimObservationProvenance table/entity
B. reconstruction from artifact lineage + stage index + outbox events
```

Do not start publication or user-facing evidence views without queryable provenance.

### 3. Artifact factory placement

Decide whether each artifact factory belongs in:

```text
Workbench extraction application policy
Workbench consolidation application policy
Artifact Runtime generic helper
```

Workbench-specific payload construction must not move into Artifact Runtime.

### 4. Outbox v1

Before production event handlers depend on outbox events, decide whether to add:

```text
event_version
context_name
aggregate_type
correlation_id
causation_id
deduplication_key
```

### 5. Sync/async boundary

Production runtime composition is async.

Allowed sync code:

```text
entities
value objects
state machines
pure policies
parsers
in-memory read model calculators
unit tests/fakes
```

Forbidden:

```text
parallel sync and async production orchestration paths
sync Postgres/LLM runtime path as canonical replacement
```

---

## Migration policy

Every new table must declare:

```text
owning bounded context
owning entity/read model/projection
source of truth or projection
temporary/draft/published classification
cleanup/retention policy
relation to outbox/events if applicable
relation to artifact lineage if applicable
```

Do not create a table because a DTO needs persistence.

Do not add a column because frontend needs to display something unless the backend read model/source-of-truth contract is clear.

Migration names must keep the current ordering convention and must not modify legacy Workbench tables for the new canonical path unless the phase explicitly concerns legacy retirement or temporary bridging.

---

## Testing strategy

### Domain tests

Use pure unit tests.

Allowed:

```text
entities
value objects
state machines
pure policies
parsers
```

Forbidden:

```text
DB
asyncpg
provider calls
frontend
legacy repositories
```

### Application use case / process manager tests

Use fake ports and fake UoWs.

Verify:

```text
state transitions
events
commit/rollback
called ports
no direct DB/provider imports
no legacy imports
```

### Infrastructure adapter tests

Use focused Postgres/async adapter tests.

Verify:

```text
SQL shape
mapping
transaction behavior
async behavior
constraint compatibility
```

### Architecture tests

Use import-boundary and forbidden-marker tests.

Verify:

```text
no legacy references from src/contexts
no runtime -> Workbench imports
no provider-specific logic in Workbench process managers
no Artifact Runtime semantic parsing
no direct status mutation bypassing state machines
```

### Read model tests

Verify:

```text
derived status
blocker kind
blocker reason
next action
resume_after
counts
artifact count
completed-vs-missing detection
```

Read model tests must prove that deferred/retryable work does not automatically become quota wait.

---

## Phases

### PHASE 00 — Architecture Drift Audit

Mode: RECON ONLY.

Inspect:

```text
src/contexts
migrations 083+
tests/architecture
docs/architecture/new_workbench_implementation_playbook.md
```

Report:

```text
new names
services
DTOs
statuses
tables
cross-context imports
legacy references
state mutation bypasses
UoW bypasses
outbox bypasses
read model duplication
sync/async production duplication
source-of-truth ambiguity
traceability gaps
```

No edits.

---

### PHASE 01 — Guard Test Hardening

Mode: PATCH ONLY.

Allowed files:

```text
tests/architecture/*
```

Goal: add tests preventing a specific architecture drift discovered by PHASE 00.

Forbidden:

```text
production code
migrations
frontend
legacy expansion
```

---

### PHASE 02 — Execution Runtime Completion

Read:

```text
src/contexts/execution_runtime
migrations/083_create_execution_runtime_tables.sql
```

Allowed:

```text
WorkItem lifecycle
WorkItemAttempt
WorkItemStateMachine
WorkItem UoW/repository ports
execution Postgres adapter
lease/reclaim use cases
complete/defer/fail/cancel use cases
lifecycle tests
```

Forbidden:

```text
Prompt A
Prompt C
LLM provider logic
draft claims
surfaces
frontend
legacy queues
Workbench blocker semantics
```

Definition of done: Execution Runtime can manage generic executable work without knowing Workbench semantics.

---

### PHASE 03 — LLM Runtime Completion

Read:

```text
src/contexts/llm_runtime
migrations/084_create_llm_runtime_tables.sql
```

Allowed:

```text
route planning
quota decision
provider-neutral execution result
output validation
LLM task recording
LLM task state machine
provider adapters
LLM error kinds
token usage
```

Forbidden:

```text
Workbench stage transition
draft claim persistence
artifact application
frontend state
publication
```

Definition of done: LLM Runtime can execute and classify an LLM task without knowing Workbench stages.

---

### PHASE 04 — Artifact Runtime Completion

Read:

```text
src/contexts/artifact_runtime
migrations/085_create_artifact_runtime_tables.sql
```

Allowed:

```text
artifact repository port
Postgres adapter
lineage persistence
resume listing
retention use cases
artifact lifecycle use cases
artifact query use cases
```

Forbidden:

```text
claim semantics
surface semantics
Prompt A parsing
Prompt C parsing
provider semantics
frontend lifecycle
```

Definition of done: Artifact Runtime stores opaque artifacts and lineage without Workbench semantic parsing.

---

### PHASE 05 — Claim Extraction Stage Fan-Out

Read:

```text
src/contexts/knowledge_workbench/extraction/application/use_cases/create_extraction_work_items.py
src/contexts/knowledge_workbench/extraction/application/use_cases/run_claim_extraction_stage*.py
src/contexts/knowledge_workbench/extraction/infrastructure/postgres/*
migrations/088_create_claim_extraction_stage_work_item_index.sql
```

Allowed:

```text
stage fan-out
stage work item indexing
progress query
readiness read model
async adapter wiring
```

Forbidden:

```text
LLM calls
Prompt A parsing
artifact application
legacy queues
frontend
consolidation
```

Definition of done: SourceUnits can be fanned out into generic WorkItems and indexed by extraction stage.

---

### PHASE 06 — Claim Extraction Work Item Processing

Goal: process one leased claim extraction WorkItem through LLM Runtime and Artifact Runtime.

Allowed:

```text
one-work-item process manager
LLM task execution through LLM Runtime
artifact factory from actual LLM outcome
raw/parsed/error/split artifacts
WorkItem transition through state machine
outbox events
one UoW commit
```

Forbidden:

```text
bulk document orchestration
consolidation
publication
frontend
legacy queues
caller-prebuilt success artifacts as trusted facts
```

Definition of done:

```text
leased WorkItem
-> LlmTask/LlmAttempt
-> actual LLM outcome
-> raw artifact
-> parsed/error/split artifact
-> WorkItem completed/deferred/failed/user_action_required/split_superseded
-> outbox events
-> one UoW commit
```

---

### PHASE 07 — Apply Draft Claim Artifact

Read:

```text
draft claim artifact parser
application process manager
DraftClaimObservation domain entity
migration 087
```

Allowed:

```text
parser
draft observation persistence
possible questions persistence
event append
UoW adapter
explicit audit/provenance link if approved
```

Forbidden:

```text
consolidation fields
canonical intent
ontology
relations
publication
frontend
LLM provider logic
```

Definition of done: persisted parsed Prompt A artifact can be applied into DraftClaimObservations with events and rollback safety.

---

### PHASE 08 — Claim Extraction Resume / Progress

Read:

```text
resume use case
progress read model
progress query
WorkItemStateMachine
RecordClaimExtractionDeferred
RecordClaimExtractionDailyExhausted
RecordClaimExtractionFailed
RecordClaimExtractionSplitRequired
```

Allowed:

```text
resume policy
expired lease reclaim policy
progress read model
blocker kind
blocker reason
next action
resume_after
artifact count
completed-vs-missing detection
user-action blockers
quota blockers
retry blockers
```

Forbidden:

```text
frontend hacks
legacy processing summary tables
direct status mutation
releasing active leases without explicit manual resume semantics
collapsing deferred/retryable into quota
```

Definition of done: progress explains status, reason, blocker, next action, and counts without frontend inference.

---

### PHASE 09 — Source Management Completion

Read:

```text
src/contexts/knowledge_workbench/source_management
```

Allowed:

```text
SourceDocument
SourceUnit
hierarchical units
mechanical split
retry split
token estimate
format adapters
source lineage
```

Forbidden:

```text
Prompt A
LLM Runtime
WorkItem creation
artifact persistence
consolidation
publication
```

Definition of done: Source Management can produce traceable SourceUnits without knowing downstream extraction.

---

### PHASE 10 — Consolidation Foundation

Read:

```text
src/contexts/knowledge_workbench/consolidation
DraftClaimObservation
Prompt C parser/contracts
```

Allowed:

```text
clusters
subclusters
cluster sizing
ConsolidatedSurface
canonical intent
evidence refs
source observation refs
possible questions
exclusion scope
relations
ontology tags
consolidation artifact parser
```

Forbidden:

```text
publication
runtime retrieval
frontend curation
legacy registry merge
draft extraction runtime logic
```

Critical guards:

```text
consolidation must not silently drop possible_questions
consolidation must not silently drop exclusion_scope
consolidation must preserve source observation refs
consolidation must preserve evidence refs
```

Definition of done: Prompt C output can become pre-publication ConsolidatedSurfaces without losing retrieval-facing metadata.

---

### PHASE 11 — Embedding / Clustering

Usually DESIGN ONLY first.

Allowed:

```text
embedding input text
embedding artifact
cluster proposal
subcluster split
cluster sizing
cluster processing WorkItems
```

Forbidden:

```text
publication
manual curation
legacy local_claim retrieval
frontend-only clustering
```

Definition of done: clustering produces explainable, traceable groups of DraftClaimObservations or ConsolidatedSurfaces.

---

### PHASE 12 — Retrieval Evaluation / Enrichment

Usually DESIGN ONLY first.

Allowed:

```text
RetrievalEvalRun
RetrievalEvalCase
RetrievalEvalResult
EnrichmentProposal
QueryVariant
RetrievalTag
before/after metrics
accept/reject enrichment
```

Forbidden:

```text
publication without evaluation
frontend-only scoring
LLM output accepted without retrieval check
legacy RAG eval coupling without bounded-context decision
```

Definition of done: retrieval quality can be measured before publication or enrichment acceptance.

---

### PHASE 13 — Manual Curation

Usually DESIGN ONLY first.

Allowed:

```text
ReviewItem
CurationDecision
ManualEditPatch
approve/reject/edit/merge/split use cases
curation events
curation read model
```

Forbidden:

```text
LLM provider logic
execution lifecycle
artifact lifecycle mutation without UoW
publication side effects without publication use case
frontend-only curation state
```

Definition of done: human decisions become durable curation facts, not frontend-only mutations.

---

### PHASE 14 — Publication

Allowed:

```text
KnowledgeSurface
PublicationRun
PublicationVersion
RuntimeProjectionRef
final embeddings
retention cleanup
rollback metadata
publication events
```

Forbidden:

```text
draft extraction logic
Prompt A
Prompt C
ad-hoc cleanup outside retention policy
frontend-only publication state
publishing without traceability
```

Definition of done: approved knowledge becomes versioned runtime projection with rollback metadata and traceability.

---

### PHASE 15 — Frontend Restore Over New Read Models

Only after backend read models exist.

Allowed:

```text
frontend calls new endpoints
frontend displays backend-provided progress
frontend displays blockers
frontend displays user_action_required
frontend displays draft claims
frontend displays consolidated surfaces
frontend displays evaluation metrics
frontend displays curation actions
frontend displays publication status
```

Forbidden:

```text
frontend inventing backend lifecycle
frontend deriving blocker reasons from raw status
frontend mutating workflow state without backend use case
frontend reaching into legacy-only semantics for new canonical path
```

Definition of done: UI reflects backend read models and does not own workflow semantics.

---

### PHASE 16 — Legacy Retirement

Allowed:

```text
mark legacy file retired
remove imports
remove old route
remove old test
add guard preventing reintroduction
bridge only when replacement path exists
```

Forbidden:

```text
delete legacy before replacement exists
silently break current functionality
mix legacy semantics into new contexts
expand old Workbench as new target path
```

Definition of done: legacy path is removed or quarantined only after new replacement path covers the needed functionality.

---

## Patch scope rule

A patch should touch one phase only.

A patch may touch an earlier phase only when:

```text
the current phase cannot be correct without amending an earlier contract
the agent performs PHASE 00 on the affected boundary first
the final answer explains the dependency
```

Do not combine:

```text
fan-out + LLM execution + artifact application + consolidation
```

in one patch.

Do not combine:

```text
backend read model + frontend restore
```

unless the backend read model already exists and is stable.

---

## Definition of Done

Every patch response must end with:

```text
Changed files:
Tests added/updated:
Architecture guards added/updated:
Owning bounded context:
Pattern applied:
Legacy paths not touched:
What remains intentionally undone:
Tests run:
```

---

## Forbidden patch smells

Reject or redo the patch if it contains:

```text
new generic service in src/application/services
new repository method doing workflow orchestration
new DTO used as domain entity
new status without state machine or read-model mapping
new table without owning bounded context
new table without source-of-truth/projection role
new direct dependency from runtime context to Workbench
provider-specific logic inside Workbench process manager
Prompt A logic inside LLM Runtime
Prompt C logic inside Artifact Runtime
Artifact Runtime parsing claim/surface semantics
Execution Runtime containing workflow_run_id/stage_run_id
Execution Runtime containing Workbench blocker semantics
frontend lifecycle workaround
frontend blocker inference
legacy SectionBatchQueueItem referenced from src/contexts
caller-prebuilt artifact accepted as trusted LLM result
deferred/retryable automatically mapped to quota
broad test suite run without request
```

---

## Safe implementation order

```text
1. PHASE 00 architecture drift audit
2. PHASE 01 guard hardening for found drift
3. PHASE 02 execution runtime completion
4. PHASE 03 LLM runtime completion
5. PHASE 04 artifact runtime completion
6. PHASE 05 claim extraction stage fan-out
7. PHASE 06 one claim extraction work item processing
8. PHASE 07 apply draft claim artifact
9. PHASE 08 progress/resume/blocker reasons
10. PHASE 09 source management split/retry split
11. PHASE 10 consolidation foundation
12. PHASE 11 embedding/clustering
13. PHASE 12 retrieval evaluation/enrichment
14. PHASE 13 curation
15. PHASE 14 publication
16. PHASE 15 frontend restore
17. PHASE 16 legacy retirement
```

If a later phase requires changing an earlier phase, stop and perform PHASE 00 first.

Final instruction: read playbook, read current files, identify context, identify pattern, use canonical vocabulary, patch the smallest target, add guard if needed, stop.
