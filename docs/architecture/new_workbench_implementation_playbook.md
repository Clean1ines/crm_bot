# New Workbench Implementation Playbook

Purpose: finish the new `src/contexts` Workbench replacement without extending legacy Workbench.

Strategy: build the new vertical in parallel under `src/contexts`, restore user-visible functionality on top of new read models, then retire legacy paths.

## Standard agent task

Use this prompt shape:

```text
Mode: RECON ONLY | DESIGN ONLY | PATCH ONLY
Phase: PHASE XX
Task: one concrete sentence
Follow docs/architecture/new_workbench_implementation_playbook.md.
```

The agent must read this file, inspect current code for the selected phase, and avoid inventing names, paths, columns, statuses, or methods.

## Modes

- RECON ONLY: inspect and report. No edits.
- DESIGN ONLY: propose target shape. No edits.
- PATCH ONLY: patch the smallest approved slice.

Before PATCH ONLY, the agent must state:

```text
Mode:
Phase:
Owning bounded context:
Pattern used:
Entities touched:
Value objects touched:
State machine affected:
Unit of Work affected:
Outbox affected:
Read model affected:
Allowed files:
Forbidden files:
Tests:
What was inspected:
```

## Hard rules

1. New canonical code belongs under `src/contexts`.
2. Do not add new canonical orchestration to old application services, old Workbench modules, old queue handlers, old infrastructure LLM modules, or old project-plane Workbench domain.
3. Do not add new names without a bounded context owner.
4. Do not change lifecycle status outside a state machine.
5. If one operation persists multiple durable facts, use a Unit of Work.
6. If a durable state change has follow-up effects, append an outbox event in the same transaction.
7. Frontend displays backend read models; frontend must not invent lifecycle semantics.
8. Legacy Workbench may be read, bridged temporarily, or retired, but not expanded as the new target path.

## Canonical contexts

### Execution Runtime

Path: `src/contexts/execution_runtime/`

Owns: WorkItem, WorkItemAttempt, WorkKind, WorkItemStatus, LeaseToken, WorkerRef, WaitUntil, WorkItemStateMachine, WorkItem events, WorkItem UoW, execution adapters.

Tables: `execution_work_items`, `execution_work_item_attempts`.

Migration: `083_create_execution_runtime_tables.sql`.

Does not own Prompt A, Prompt C, Groq, claims, source units, surfaces, documents, frontend state, or Workbench stage semantics.

### LLM Runtime

Path: `src/contexts/llm_runtime/`

Owns: LlmTask, LlmAttempt, LlmTaskStatus, LlmTaskStateMachine, route planning, provider/model/account identity, quota decisions, token usage, provider ports, provider adapters, LLM task UoW.

Tables: `llm_tasks`, `llm_attempts`.

Migration: `084_create_llm_runtime_tables.sql`.

Does not own Workbench stages, draft claims, consolidated surfaces, source splitting, frontend decisions, or publication.

### Artifact Runtime

Path: `src/contexts/artifact_runtime/`

Owns: PipelineArtifact, ArtifactRef, ArtifactKind, ArtifactPayload, ArtifactStatus, ArtifactVisibility, ArtifactLineage, RetentionPolicy, artifact events, artifact UoW, artifact adapters.

Tables: `pipeline_artifacts`, `pipeline_artifact_lineage`.

Migration: `085_create_artifact_runtime_tables.sql`.

Artifact payload is opaque to Artifact Runtime.

### Context Outbox

Table: `outbox_events`.

Migration: `086_create_context_outbox_events.sql`.

Events must be committed with the state change that caused them.

### Source Management

Path: `src/contexts/knowledge_workbench/source_management/`

Owns: SourceDocument, SourceUnit, SourceUnitRef, source format, split reason, heading path, parsing, normalization, splitting, source lineage.

Does not own extraction WorkItem creation, Prompt A, LLM Runtime, artifact persistence, consolidation, or publication.

### Extraction

Path: `src/contexts/knowledge_workbench/extraction/`

Owns: claim extraction stage, Prompt A application boundary, DraftClaimObservation, PossibleQuestion, ExclusionScope, EvidenceBlock, CreateExtractionWorkItems, RunClaimExtractionStage, ResumeClaimExtractionStage, ApplyDraftClaimObservationArtifact, extraction process managers, extraction UoW ports, progress read model.

Tables: `draft_claim_observations`, `draft_claim_observation_possible_questions`, `claim_extraction_stage_work_items`.

Migrations: `087_create_draft_claim_observations.sql`, `088_create_claim_extraction_stage_work_item_index.sql`.

Does not own provider details, model routing internals, generic artifact lifecycle, generic work item lifecycle, consolidation, or publication.

### Consolidation

Path: `src/contexts/knowledge_workbench/consolidation/`

Owns: Prompt C boundary, DraftClaimCluster, Subcluster, ConsolidatedSurface, CanonicalIntent, SurfaceKind, evidence refs, ontology tags, relations, cluster sizing, consolidation artifact parser.

Consolidation must not silently drop retrieval-facing fields: possible_questions, exclusion_scope, evidence refs, source observation refs, canonical intent, answer/surface text, ontology tags, relations.

Future bounded areas: rag_enrichment, retrieval_evaluation, curation, publication.

## Canonical distinctions

```text
WorkItem != LlmTask != PipelineArtifact
SourceUnit != DraftClaimObservation != ConsolidatedSurface != KnowledgeSurface
Prompt A != LLM Runtime
Prompt C != Artifact Runtime
Groq != LLM Runtime
DTO != Entity
Repository != Use Case
Service != State Machine
Queue != Pipeline
Status != Checkpoint
Artifact existence != WorkItem lifecycle
```

## Phases

### PHASE 00 — Architecture Drift Audit

Mode: RECON ONLY.

Inspect `src/contexts`, migrations `083-088`, and `tests/architecture`.

Report new names, services, DTOs, statuses, tables, cross-context imports, legacy references, state mutation bypasses, UoW bypasses, outbox bypasses, read model duplication.

### PHASE 01 — Guard Test Hardening

Mode: PATCH ONLY.

Allowed files: `tests/architecture/*`.

Goal: add tests preventing a specific architecture drift.

### PHASE 02 — Execution Runtime Completion

Read `src/contexts/execution_runtime` and migration `083`.

Allowed: WorkItem lifecycle, state machine, UoW/repository ports, execution Postgres adapter, lease/reclaim use cases, lifecycle tests.

Forbidden: Prompt A, LLM provider logic, draft claims, surfaces, frontend, legacy queues.

### PHASE 03 — LLM Runtime Completion

Read `src/contexts/llm_runtime` and migration `084`.

Allowed: route planning, quota decision, provider-neutral execution result, output validation, LLM task recording, provider adapters.

Forbidden: Workbench stage transition, draft claim persistence, artifact application, frontend state.

### PHASE 04 — Artifact Runtime Completion

Read `src/contexts/artifact_runtime` and migration `085`.

Allowed: artifact repository port, Postgres adapter, lineage persistence, resume listing, retention use cases.

Forbidden: claim or surface semantics inside Artifact Runtime.

### PHASE 05 — Claim Extraction Stage Fan-Out

Read extraction fan-out use cases, extraction Postgres adapters, and migration `088`.

Allowed: stage fan-out, stage work item indexing, progress query, readiness read model, async adapter wiring.

Forbidden: LLM calls, Prompt A parsing, artifact application, legacy queues, frontend.

### PHASE 06 — Claim Extraction Work Item Processing

Goal: process one leased claim extraction WorkItem through LLM Runtime and Artifact Runtime.

Allowed: one-work-item process manager, LLM task execution through LLM Runtime, raw/parsed artifacts, WorkItem transition through state machine, outbox events, one UoW commit.

Forbidden: bulk document orchestration, consolidation, publication, frontend, legacy queues.

Definition of done: leased WorkItem -> LlmTask/LlmAttempt -> raw artifact -> parsed artifact -> WorkItem completed/deferred/failed/user_action_required -> outbox events -> one UoW commit.

### PHASE 07 — Apply Draft Claim Artifact

Read draft claim parser, application process manager, domain entity, migration `087`.

Allowed: parser, draft observation persistence, possible questions persistence, event append, UoW adapter, explicit audit link if needed.

Forbidden: consolidation fields, canonical intent, ontology, relations, publication.

### PHASE 08 — Claim Extraction Resume / Progress

Read resume use case, progress read model, progress query, WorkItemStateMachine.

Allowed: resume policy, expired lease reclaim policy, progress read model, quota/user-action blockers, artifact count, completed-vs-missing detection.

Forbidden: frontend hacks, legacy processing summary tables, direct status mutation, releasing active leases without explicit manual resume semantics.

### PHASE 09 — Source Management Completion

Read source management context.

Allowed: SourceDocument, SourceUnit, hierarchical units, mechanical split, retry split, token estimate, format adapters.

Forbidden: Prompt A, LLM Runtime, WorkItem creation, artifact persistence, consolidation.

### PHASE 10 — Consolidation Foundation

Read consolidation context and DraftClaimObservation.

Allowed: clusters, subclusters, cluster sizing, ConsolidatedSurface, canonical intent, evidence refs, source observation refs, possible questions, exclusion scope, relations, ontology tags.

Forbidden: publication, runtime retrieval, frontend curation, legacy registry merge.

Critical guard: consolidation must not silently drop possible_questions or exclusion_scope.

### PHASE 11 — Embedding / Clustering

Usually DESIGN ONLY first.

Allowed: embedding input text, embedding artifact, cluster proposal, subcluster split, cluster sizing, cluster processing WorkItems.

Forbidden: publication, manual curation, legacy local_claim retrieval.

### PHASE 12 — Retrieval Evaluation / Enrichment

Usually DESIGN ONLY first.

Allowed: RetrievalEvalRun, RetrievalEvalCase, RetrievalEvalResult, EnrichmentProposal, QueryVariant, RetrievalTag, before/after metrics, accept/reject enrichment.

Forbidden: publication without evaluation, frontend-only scoring, LLM output accepted without retrieval check.

### PHASE 13 — Manual Curation

Usually DESIGN ONLY first.

Allowed: ReviewItem, CurationDecision, ManualEditPatch, approve/reject/edit/merge/split use cases, curation events, curation read model.

Forbidden: LLM provider logic, execution lifecycle, artifact lifecycle mutation without UoW, publication side effects without publication use case.

### PHASE 14 — Publication

Allowed: KnowledgeSurface, PublicationRun, PublicationVersion, RuntimeProjectionRef, final embeddings, retention cleanup, rollback metadata, publication events.

Forbidden: draft extraction logic, Prompt A, Prompt C, ad-hoc cleanup outside retention policy, frontend-only publication state.

### PHASE 15 — Frontend Restore Over New Read Models

Only after backend read models exist.

Allowed: frontend calls new endpoints and displays backend-provided progress, blockers, user_action_required, draft claims, consolidated surfaces, evaluation metrics, curation actions, publication status.

Forbidden: frontend inventing backend lifecycle.

### PHASE 16 — Legacy Retirement

Allowed: mark legacy file retired, remove imports, remove old route, remove old test, add guard preventing reintroduction.

Forbidden: delete legacy before replacement exists, silently break current functionality, mix legacy semantics into new contexts.

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

## Forbidden patch smells

Reject or redo the patch if it contains:

```text
new generic service in src/application/services
new repository method doing workflow orchestration
new DTO used as domain entity
new status without state machine
new table without owning bounded context
new direct dependency from runtime context to Workbench
provider-specific logic inside Workbench process manager
Prompt A logic inside LLM Runtime
Artifact Runtime parsing claim/surface semantics
Execution Runtime containing workflow_run_id/stage_run_id
frontend lifecycle workaround
legacy SectionBatchQueueItem referenced from src/contexts
```

## Safe implementation order

```text
1. PHASE 00 architecture drift audit
2. PHASE 01 guard hardening for found drift
3. PHASE 02 execution runtime completion
4. PHASE 03 llm runtime completion
5. PHASE 04 artifact runtime completion
6. PHASE 05 claim extraction stage fan-out
7. PHASE 06 one claim extraction work item processing
8. PHASE 07 apply draft claim artifact
9. PHASE 08 progress/resume
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
