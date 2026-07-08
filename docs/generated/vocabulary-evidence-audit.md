# Vocabulary Evidence Audit

Scope: Workbench vocabulary proof/rejection audit. Generated docs were not used as proof; they were searched only to identify sections requiring follow-up edits.

| Term | Classification | Allowed in new code? | Evidence strength | Notes |
|---|---|---:|---|---|
| CompilerRun | PROVEN_LEGACY | no | STRONG_CODE_ONLY | Current architecture tests name compiler-run tables/classes as deleted legacy. |
| AnswerCandidate | PROVEN_LEGACY | no | STRONG_CODE_ONLY | Current architecture tests name answer-candidate tables/classes as deleted legacy. |
| CandidateCluster | PROVEN_LEGACY | no | STRONG_CODE_ONLY | Current architecture tests name candidate-cluster tables/classes as deleted legacy. |
| CanonicalKnowledgeEntry | PROVEN_LEGACY | no | STRONG_CODE_AND_DB | Exact term is retired; active canonical facts/registry tables are legacy/suspect. |
| KnowledgeEnrichment | UNPROVEN_REJECTED | no | NO_EVIDENCE | Exact term has no active proof; `enrichment` variants are legacy/RAG-eval adjacent only. |
| RetrievalSurface | UNPROVEN_REJECTED | no | NO_EVIDENCE | Active equivalent is runtime retrieval entries, not this term. |
| EvalCase | UNPROVEN_REJECTED | no | NO_EVIDENCE | Only doc-like `RetrievalEvalCase` mention found; no active code/table contract. |
| RagEval | TRANSITIONAL_CURRENT | limited | STRONG_CODE_AND_DB | Active RAG eval feature exists, but it is separate/transitional and requires its own audit. |
| KnowledgeEditAction | PROVEN_LEGACY | no | MIGRATION_ONLY | Found in retired legacy migration only. |
| SourceDocument | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active source-management entity/repository/table. |
| SourceUnit | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active source-management entity/repository/table. |
| source_document_ref | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active value object/API payload/table column. |
| source_unit_ref | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active value object/API payload/table column. |
| workflow_run_id | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active runtime command/progress/timeline/frontend event key. |
| workflow command | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active `WorkflowCommand` and `workflow_runtime_command_log`. |
| work_item_id | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active execution runtime work item and timeline key. |
| attempt_id | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active execution attempt/dispatch/timeline key. |
| DraftClaimObservation | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active extraction model/repository/table. |
| DraftClaimEmbedding | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active embedding handler/model/table. |
| DraftClaimCompactionGroup | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active compaction read model/table. |
| DraftClaimCompactionBatch | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active compaction read model/table. |
| DraftClaimCompactionNode | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active compaction reduction table. |
| DraftClaimCurationWorkspace | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active curation command/repository/table. |
| DraftClaimCurationItem | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active curation repository/table. |
| RuntimePublication | PROVEN_CURRENT | limited | STRONG_CODE_AND_DB | Table/repository are current; exact class name is not canonical. |
| RuntimeRetrievalEntry | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active runtime retrieval tables/repositories/tests. |
| FrontendWorkflowEvent | PROVEN_CURRENT | yes | STRONG_CODE_AND_DB | Active projection model/repository/frontend contract/table. |
| RuntimeProgressSnapshot | PROVEN_CURRENT | limited | STRONG_CODE_AND_DB | Exact code name is `WorkflowProgressSnapshot`; table is runtime progress snapshot. |
| RuntimeTimelineEntry | PROVEN_CURRENT | limited | STRONG_CODE_AND_DB | Exact code name is `WorkflowTimelineEntry`; table is runtime timeline entries. |
| processing_run_id | PROVEN_LEGACY | no | STRONG_CODE_AND_DB | Old processing-run family; not runtime-native workbench execution. |
| node_run_id | TRANSITIONAL_CURRENT | no | STRONG_CODE_ONLY | Still leaks through live-state DTO/tests; should not be used in new runtime-native code. |
| fact_registry | PROVEN_LEGACY | no | STRONG_CODE_AND_DB | Old registry/canonical facts system. |
| canonical_facts | PROVEN_LEGACY | no | STRONG_CODE_AND_DB | Old canonical facts/registry semantics. |
| knowledge_base | PROVEN_LEGACY | no | STRONG_CODE_AND_DB | Old knowledge storage and search surface. |
| knowledge_documents | PROVEN_LEGACY | no | STRONG_CODE_AND_DB | Old document storage. |
| execution_queue | PROVEN_LEGACY | no | STRONG_CODE_AND_DB | Old queue architecture, distinct from execution work items. |
| registry_snapshot | PROVEN_LEGACY | no | STRONG_CODE_AND_DB | Old registry snapshot system. |
| fact_id | TRANSITIONAL_CURRENT | no | STRONG_CODE_AND_DB | Still present in RAG eval/runtime transition columns; not allowed as new Workbench authority term. |

## CompilerRun

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "CompilerRun|compiler_run|compilerRun" src frontend tests migrations docs/generated`

Exact matches:
- `tests/architecture/test_dropped_legacy_knowledge_tables_not_referenced.py:15` - `"knowledge_compiler_runs",`
- `tests/architecture/test_dropped_legacy_knowledge_tables_not_referenced.py:18` - `"knowledge_surface_compiler_runs",`
- `tests/architecture/test_knowledge_repository_legacy_zoo_deleted.py:11` - `"src/infrastructure/db/repositories/knowledge_compiler_run_persistence.py",`
- `tests/architecture/test_knowledge_repository_legacy_zoo_deleted.py:44` - `"CompilerRun",`

Active code evidence:
- `tests/architecture/test_knowledge_repository_legacy_zoo_deleted.py:44` is an active architecture test proving the term belongs to the deleted legacy repository zoo.

DB evidence:
- Old table names `knowledge_compiler_runs` and `knowledge_surface_compiler_runs` are guarded as dropped/legacy; no current table was found.

Runtime/event evidence:
- No current event_type, command_type, work_kind, or payload key found.

Decision:
- allowed in current vocabulary? no

Reason:
- The evidence is negative/legacy-only. Do not use `CompilerRun` in current Workbench vocabulary.

## AnswerCandidate

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "AnswerCandidate|answer_candidate|answerCandidate" src frontend tests migrations docs/generated`

Exact matches:
- `tests/architecture/test_active_migrations_do_not_resurrect_legacy_knowledge.py:7` - `"knowledge_answer_candidates",`
- `tests/architecture/test_knowledge_repository_legacy_zoo_deleted.py:9` - `"src/infrastructure/db/repositories/knowledge_answer_candidate_persistence.py",`
- `tests/architecture/test_knowledge_repository_legacy_zoo_deleted.py:39` - `"AnswerCandidateSummaryView",`
- `tests/architecture/test_knowledge_repository_legacy_zoo_deleted.py:42` - `"AnswerCandidate",`

Active code evidence:
- Active architecture tests require legacy answer-candidate persistence/query code and tables to stay deleted.

DB evidence:
- `knowledge_answer_candidates` appears as a legacy table name guarded by tests; no current table found.

Runtime/event evidence:
- No current event_type, command_type, work_kind, or payload key found.

Decision:
- allowed in current vocabulary? no

Reason:
- This is proven legacy vocabulary, not a current Workbench term.

## CandidateCluster

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "CandidateCluster|candidate_cluster|candidateCluster" src frontend tests migrations docs/generated`

Exact matches:
- `tests/architecture/test_active_migrations_do_not_resurrect_legacy_knowledge.py:8` - `"knowledge_candidate_clusters",`
- `tests/architecture/test_active_migrations_do_not_resurrect_legacy_knowledge.py:9` - `"knowledge_candidate_cluster_members",`
- `tests/architecture/test_dropped_legacy_knowledge_tables_not_referenced.py:10` - `"knowledge_answer_candidates",`
- `tests/architecture/test_knowledge_repository_legacy_zoo_deleted.py:43` - `"CandidateCluster",`

Active code evidence:
- Active architecture tests classify candidate-cluster persistence/tables as deleted legacy surface.

DB evidence:
- `knowledge_candidate_clusters` and `knowledge_candidate_cluster_members` are legacy/dropped table names; no current table found.

Runtime/event evidence:
- No current event_type, command_type, work_kind, or payload key found.

Decision:
- allowed in current vocabulary? no

Reason:
- Current compaction evidence uses draft-claim compaction groups/batches/nodes instead.

## CanonicalKnowledgeEntry

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "CanonicalKnowledgeEntry|canonical_knowledge_entry|canonicalKnowledgeEntry|canonical_facts|knowledge_workbench_canonical_facts" src frontend tests migrations docs/generated`

Exact matches:
- `migrations/_retired_legacy/059_create_knowledge_entries_and_retrieval_surface.sql:4` - `-- - CanonicalKnowledgeEntry is persisted in knowledge_entries.`
- `migrations/_retired_legacy/058_create_knowledge_source_chunks.sql:5` - `-- link CanonicalKnowledgeEntry rows to exact source evidence.`
- `migrations/070_create_faq_workbench_v1.sql:217` - `CREATE TABLE IF NOT EXISTS knowledge_workbench_canonical_facts (`
- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_publication_repository.py:227` - `INSERT INTO knowledge_workbench_canonical_facts (`

Active code evidence:
- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_publication_repository.py:227` writes old canonical facts compatibility rows, but this is the suspect registry/canonical facts system rather than current runtime retrieval authority.
- `tests/contexts/knowledge_workbench/retrieval/infrastructure/postgres/test_postgres_published_workbench_retrieval_repository.py:99` asserts `"knowledge_workbench_canonical_facts" not in sql`, proving runtime retrieval must not depend on canonical facts.

DB evidence:
- `knowledge_workbench_canonical_facts` exists in migrations and schema, but it is legacy/suspect DB by this audit scope.

Runtime/event evidence:
- No current runtime event/command proves `CanonicalKnowledgeEntry` as a current term.

Decision:
- allowed in current vocabulary? no

Reason:
- The exact term is retired, and the closest active storage is the old canonical facts/registry system.

## KnowledgeEnrichment

Classification:
- UNPROVEN_REJECTED

Search commands run:
- `rg -n "KnowledgeEnrichment|knowledge_enrichment|knowledgeEnrichment|enrichment" src frontend tests migrations docs/generated`

Exact matches:
- `migrations/_retired_legacy/059_create_knowledge_entries_and_retrieval_surface.sql:26` - `enrichment JSONB NOT NULL DEFAULT '{}'::jsonb,`
- `frontend/src/pages/rag-eval/components/KnowledgeEntryCurationCard.tsx:32` - `entry.enrichment.questions`
- `frontend/src/shared/api/modules/knowledgeCuration.ts:24` - `enrichment: Record<string, unknown>;`
- `tests/infrastructure/db/repositories/test_knowledge_repository_workbench_runtime_search.py:122` - `assert "rs." + "enrichment" not in query`

Active code evidence:
- No active exact `KnowledgeEnrichment` type/class/contract found.
- `enrichment` appears in legacy/RAG-eval-adjacent UI/API areas and in tests excluding legacy retrieval enrichment from runtime search.

DB evidence:
- Retired legacy migration column only; no current Workbench table proving `KnowledgeEnrichment`.

Runtime/event evidence:
- No current event_type, command_type, work_kind, or payload key found.

Decision:
- allowed in current vocabulary? no

Reason:
- Exact term has no active evidence and must not be upgraded from adjacent `enrichment` strings.

## RetrievalSurface

Classification:
- UNPROVEN_REJECTED

Search commands run:
- `rg -n "RetrievalSurface|retrieval_surface|retrievalSurface|runtime_retrieval|knowledge_workbench_runtime_retrieval_entries" src frontend tests migrations docs/generated`

Exact matches:
- `src/contexts/knowledge_workbench/README.md:40` - `- RetrievalSurface;`
- `src/domain/project_plane/production_retrieval.py:53` - `source_name="knowledge_workbench_runtime_retrieval_entries",`
- `src/contexts/knowledge_workbench/retrieval/infrastructure/postgres/postgres_published_workbench_retrieval_repository.py:37` - `JOIN knowledge_workbench_runtime_retrieval_entries AS entry`
- `tests/architecture/test_no_legacy_production_retrieval_surface.py:43` - `assert "knowledge_workbench_runtime_retrieval_entries" in source`

Active code evidence:
- Active runtime retrieval code proves `knowledge_workbench_runtime_retrieval_entries`, not the term `RetrievalSurface`.

DB evidence:
- Current DB table: `knowledge_workbench_runtime_retrieval_entries`.
- No current DB object named `retrieval_surface`.

Runtime/event evidence:
- No event_type/command_type/work_kind proving `RetrievalSurface`.

Decision:
- allowed in current vocabulary? no

Reason:
- Use proven runtime retrieval entry terminology. `RetrievalSurface` remains a concept-only/doc term in this audit.

## EvalCase

Classification:
- UNPROVEN_REJECTED

Search commands run:
- `rg -n "EvalCase|eval_case|evalCase|RagEval|rag_eval|ragEval" src frontend tests migrations docs/generated`

Exact matches:
- `src/contexts/knowledge_workbench/README.md:47` - `- RetrievalEvalCase;`
- `migrations/110_create_workbench_rag_eval.sql:46` - `CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_questions (`
- `src/contexts/knowledge_workbench/rag_eval/application/models/workbench_rag_eval.py:123` - `expected_fact_id: str`
- `src/interfaces/http/knowledge.py:2265` - `async def run_workbench_rag_eval(`

Active code evidence:
- Active feature vocabulary is `WorkbenchRagEvalQuestion`/RAG eval questions, not `EvalCase`.

DB evidence:
- Active RAG eval question/result tables exist; no `eval_case` table/column found.

Runtime/event evidence:
- No current event_type, command_type, work_kind, or payload key for `EvalCase`.

Decision:
- allowed in current vocabulary? no

Reason:
- `EvalCase` has no active executable or DB proof.

## RagEval

Classification:
- TRANSITIONAL_CURRENT

Search commands run:
- `rg -n "EvalCase|eval_case|evalCase|RagEval|rag_eval|ragEval" src frontend tests migrations docs/generated`

Exact matches:
- `src/domain/project_plane/rag_eval_retrieval.py:7` - `class RagEvalRetrievalMode(StrEnum):`
- `src/domain/project_plane/production_retrieval.py:20` - `RAG_EVAL = "rag_eval"`
- `migrations/110_create_workbench_rag_eval.sql:4` - `CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_runs (`
- `src/interfaces/http/knowledge.py:2265` - `async def run_workbench_rag_eval(`

Active code evidence:
- `src/interfaces/composition/workbench_rag_eval.py:45` composes `RunWorkbenchRagEval`.
- `src/contexts/knowledge_workbench/rag_eval/application/use_cases/run_workbench_rag_eval.py:35` defines active `RunWorkbenchRagEval`.
- `frontend/src/app/App.tsx:216` mounts `RagEvalPage`.

DB evidence:
- Current active RAG eval tables: `knowledge_workbench_rag_eval_runs`, `knowledge_workbench_rag_eval_questions`, `knowledge_workbench_rag_eval_retrieval_results`, `knowledge_workbench_rag_eval_promoted_questions`.
- Retired old tables `rag_eval_*` are dropped by `migrations/112_drop_retired_legacy_knowledge_schema.sql`.

Runtime/event evidence:
- Project-plane usage view `rag_eval` exists, but no evidence found that RAG eval is workflow/capacity-native current runtime work.

Decision:
- allowed in current vocabulary? limited

Reason:
- RAG eval is active, but transitional and outside source-of-truth cleanup unless separately audited.

## KnowledgeEditAction

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "KnowledgeEditAction|knowledge_edit_action|knowledgeEditAction|curation_item|DraftClaimCuration" src frontend tests migrations docs/generated`

Exact matches:
- `migrations/_retired_legacy/062_kcd_stage_h_knowledge_edit_actions.sql:1` - `CREATE TABLE IF NOT EXISTS knowledge_edit_actions (`
- `migrations/_retired_legacy/062_kcd_stage_h_knowledge_edit_actions.sql:77` - `CREATE TABLE IF NOT EXISTS knowledge_edit_action_runs (`
- `migrations/108_add_draft_claim_curation_workspace.sql:11` - `CREATE TABLE IF NOT EXISTS draft_claim_curation_items (`
- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_workspace_repository.py:99` - `INSERT INTO draft_claim_curation_items (`

Active code evidence:
- Active curation evidence proves `DraftClaimCurationItem`, not `KnowledgeEditAction`.

DB evidence:
- `knowledge_edit_actions` is retired legacy migration only.
- `draft_claim_curation_items` is current DB.

Runtime/event evidence:
- Current curation commands/events exist for draft-claim curation; none prove `KnowledgeEditAction`.

Decision:
- allowed in current vocabulary? no

Reason:
- The exact term is legacy; current curation item vocabulary should be used instead.

## SourceDocument

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "SourceDocument|source_document|source_documents|source_document_ref|document_ref" src frontend tests migrations`

Exact matches:
- `src/contexts/knowledge_workbench/source_management/application/ports/source_management_repository_port.py:5` - `from ...source_document import (`
- `src/contexts/knowledge_workbench/source_management/application/ports/source_management_repository_port.py:20` - `async def save_source_document(self, document: SourceDocument) -> None: ...`
- `src/contexts/knowledge_workbench/source_management/infrastructure/postgres/postgres_source_management_repository.py:52` - `INSERT INTO source_documents (`
- `src/contexts/knowledge_workbench/source_management/domain/events/source_events.py:23` - `class SourceDocumentCreated(DomainEvent):`

Active code evidence:
- Source-management repository port and Postgres repository are current executable paths.

DB evidence:
- Current DB table: `source_documents`.

Runtime/event evidence:
- Domain event: `SourceDocumentCreated`.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong active code and DB evidence.

## SourceUnit

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "SourceUnit|source_unit|source_units|source_unit_ref|unit_ref" src frontend tests migrations`

Exact matches:
- `src/contexts/knowledge_workbench/source_management/application/ports/source_management_repository_port.py:8` - `from ...source_unit import (`
- `src/contexts/knowledge_workbench/source_management/application/ports/source_management_repository_port.py:27` - `async def save_source_units(`
- `src/contexts/knowledge_workbench/source_management/infrastructure/postgres/postgres_source_management_repository.py:132` - `INSERT INTO source_units (`
- `src/contexts/knowledge_workbench/source_management/domain/events/source_events.py:32` - `class SourceUnitCreated(DomainEvent):`

Active code evidence:
- Source-management repository and parser flow actively use `SourceUnit`.

DB evidence:
- Current DB table: `source_units`.

Runtime/event evidence:
- Domain events: `SourceUnitCreated`, `SourceUnitSplit`.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong active code and DB evidence.

## source_document_ref

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "SourceDocument|source_document|source_documents|source_document_ref|document_ref" src frontend tests migrations`

Exact matches:
- `src/contexts/knowledge_workbench/source_management/domain/value_objects/source_document_ref.py:8` - `class SourceDocumentRef:`
- `frontend/src/pages/knowledge/shadow/workflowFrontendProjectionReducer.ts:1257` - `next.workflow.source_document_ref`
- `migrations/117_extend_runtime_retrieval_entries_for_canonical_publish.sql:6` - `ADD COLUMN IF NOT EXISTS source_document_ref TEXT NOT NULL DEFAULT '';`
- `src/contexts/knowledge_workbench/rag_eval/application/use_cases/run_workbench_rag_eval.py:49` - `source_document_ref: str | None,`

Active code evidence:
- Backend value object, frontend projection, runtime retrieval, and RAG eval use this key.

DB evidence:
- Current columns include source document refs in source/runtime/RAG-eval tables.

Runtime/event evidence:
- Payload key appears in frontend workflow projection and RAG eval runtime filtering.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong code and DB evidence across current source and runtime surfaces.

## source_unit_ref

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "SourceUnit|source_unit|source_units|source_unit_ref|unit_ref" src frontend tests migrations`

Exact matches:
- `src/contexts/knowledge_workbench/source_management/domain/value_objects/source_unit_ref.py:8` - `class SourceUnitRef:`
- `frontend/src/pages/knowledge/shadow/workflowFrontendProjectionReducer.ts:655` - `const sourceUnitRef = text(event.payload, "source_unit_ref")`
- `migrations/101_create_draft_claim_observations.sql:6` - `source_unit_ref TEXT NOT NULL,`
- `src/contexts/knowledge_workbench/extraction/application/ports/draft_claim_observation_read_repository_port.py:12` - `source_unit_ref: str`

Active code evidence:
- Source value object, draft claim observation read models, and frontend projections use this key.

DB evidence:
- Current columns: `source_units.unit_ref`, `draft_claim_observations.source_unit_ref`.

Runtime/event evidence:
- Frontend workflow event payloads include `source_unit_ref`.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong code and DB evidence.

## workflow_run_id

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "workflow_run_id|WorkflowCommand|workflow_runtime_command_log|workflow_runtime_progress_snapshots|workflow_runtime_timeline_entries" src frontend tests migrations`

Exact matches:
- `src/contexts/workflow_runtime/domain/entities/workflow_command.py:32` - `workflow_run_id: str`
- `src/contexts/workflow_runtime/domain/entities/workflow_progress_snapshot.py:15` - `workflow_run_id: str`
- `src/contexts/workflow_runtime/domain/entities/workflow_timeline_entry.py:21` - `workflow_run_id: str`
- `src/contexts/knowledge_workbench/observability/application/models/frontend_workflow_event.py:21` - `workflow_run_id: str`

Active code evidence:
- Current runtime command, progress, timeline, and frontend projection models all require it.

DB evidence:
- Current tables include `workflow_runtime_command_log`, `workflow_runtime_progress_snapshots`, `workflow_runtime_timeline_entries`, `frontend_workflow_events`.

Runtime/event evidence:
- Runtime command/progress/timeline key and frontend projection key.

Decision:
- allowed in current vocabulary? yes

Reason:
- It is the stable current runtime identity key.

## workflow command

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "WorkflowCommand|workflow command|workflow_runtime_command_log|command_type" src frontend tests migrations`

Exact matches:
- `src/contexts/workflow_runtime/domain/entities/workflow_command.py:29` - `class WorkflowCommand:`
- `src/contexts/workflow_runtime/domain/entities/workflow_command.py:31` - `command_type: str`
- `src/contexts/workflow_runtime/application/ports/command_log_repository_port.py:18` - `async def append_pending_command(command: WorkflowCommand) -> WorkflowCommand: ...`
- `src/contexts/workflow_runtime/infrastructure/postgres/postgres_command_log_repository.py:37` - `INSERT INTO workflow_runtime_command_log (`

Active code evidence:
- Current runtime command entity, repository port, and Postgres command log.

DB evidence:
- Current DB table: `workflow_runtime_command_log`.

Runtime/event evidence:
- Runtime `command_type` controls scheduled work commands.

Decision:
- allowed in current vocabulary? yes

Reason:
- Proven runtime-native command vocabulary.

## work_item_id

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "work_item_id|execution_work_items|WorkflowTimelineEntry" src frontend tests migrations`

Exact matches:
- `src/contexts/workflow_runtime/domain/entities/workflow_timeline_entry.py:29` - `work_item_id: str | None = None`
- `migrations/096_create_execution_work_item_attempt_dispatches.sql:6` - `work_item_id text NOT NULL,`
- `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_lease_repository.py:240` - `WHERE work_item_id = $1`
- `src/interfaces/composition/prepare_llm_dispatch_batch.py:310` - `peek_due_work_items(`

Active code evidence:
- Execution runtime lease repository and dispatch preparation use work items.

DB evidence:
- Current tables: `execution_work_items`, `execution_work_item_attempts`, `execution_work_item_attempt_dispatches`.

Runtime/event evidence:
- Timeline payload/key and execution lease identity.

Decision:
- allowed in current vocabulary? yes

Reason:
- It is a current execution runtime identity.

## attempt_id

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "attempt_id|execution_work_item_attempts|execution_work_item_attempt_dispatches|WorkflowTimelineEntry" src frontend tests migrations`

Exact matches:
- `src/contexts/workflow_runtime/domain/entities/workflow_timeline_entry.py:30` - `attempt_id: str | None = None`
- `migrations/096_create_execution_work_item_attempt_dispatches.sql:2` - `attempt_id text PRIMARY KEY,`
- `src/contexts/workflow_runtime/infrastructure/postgres/postgres_timeline_repository.py:95` - `attempt_id`
- `frontend/src/shared/api/modules/knowledge.ts:260` - `export type WorkbenchWorkflowTimelineEntryLiveState = {`

Active code evidence:
- Runtime timeline and execution attempt dispatch table use attempt IDs.

DB evidence:
- Current tables: `execution_work_item_attempts`, `execution_work_item_attempt_dispatches`, `workflow_runtime_timeline_entries`.

Runtime/event evidence:
- Timeline entry key and execution attempt identity.

Decision:
- allowed in current vocabulary? yes

Reason:
- It is the current runtime attempt identifier.

## DraftClaimObservation

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "DraftClaimObservation|draft_claim_observation|draft_claim_observations|observation_ref" src frontend tests migrations`

Exact matches:
- `src/contexts/knowledge_workbench/extraction/application/ports/draft_claim_observation_read_repository_port.py:9` - `class DraftClaimObservationReadModel:`
- `src/contexts/knowledge_workbench/extraction/application/ports/draft_claim_observation_repository_port.py:16` - `class DraftClaimObservationRepositoryPort(Protocol):`
- `migrations/101_create_draft_claim_observations.sql:1` - `CREATE TABLE IF NOT EXISTS draft_claim_observations (`
- `src/contexts/knowledge_workbench/extraction/application/ports/draft_claim_observation_read_repository_port.py:10` - `observation_ref: str`

Active code evidence:
- Active extraction repository ports/read models use draft claim observations.

DB evidence:
- Current DB table: `draft_claim_observations`.

Runtime/event evidence:
- Observation references are payload/domain keys for extraction outputs.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong current extraction evidence.

## DraftClaimEmbedding

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "DraftClaimEmbedding|draft_claim_embedding|draft_claim_embeddings" src frontend tests migrations`

Exact matches:
- `src/contexts/knowledge_workbench/application/sagas/handle_generate_draft_claim_embeddings_command.py:58` - `class HandleGenerateDraftClaimEmbeddingsCommand:`
- `src/contexts/knowledge_workbench/extraction/application/ports/draft_claim_embedding_persistence_port.py:9` - `class DraftClaimEmbeddingCandidate:`
- `src/contexts/knowledge_workbench/extraction/application/ports/draft_claim_embedding_persistence_port.py:60` - `class DraftClaimEmbeddingPersistencePort(Protocol):`
- `migrations/102_create_draft_claim_embeddings.sql:1` - `CREATE TABLE IF NOT EXISTS draft_claim_embeddings (`

Active code evidence:
- Active saga handler generates and persists draft claim embeddings.

DB evidence:
- Current DB table: `draft_claim_embeddings`.

Runtime/event evidence:
- Event `DraftClaimEmbeddingsGenerated` appears in the embedding handler.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong current code and DB evidence.

## DraftClaimCompactionGroup

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "DraftClaimCompaction|draft_claim_compaction|compaction_group|compaction_batch|compaction_node" src frontend tests migrations`

Exact matches:
- `migrations/104_create_draft_claim_compaction_plan.sql:34` - `CREATE TABLE IF NOT EXISTS draft_claim_compaction_groups`
- `migrations/104_create_draft_claim_compaction_plan.sql:54` - `CREATE TABLE IF NOT EXISTS draft_claim_compaction_group_members`
- `tests/api/test_knowledge.py:24` - `DraftClaimCompactionGroupReadModel,`
- `src/contexts/knowledge_workbench/observability/application/projectors/draft_claim_compaction_frontend_workflow_event_projector.py:119` - `workflow_run_id=workflow_run_id,`

Active code evidence:
- API tests/read models and frontend projectors actively use draft claim compaction groups.

DB evidence:
- Current DB tables: `draft_claim_compaction_groups`, `draft_claim_compaction_group_members`.

Runtime/event evidence:
- Compaction frontend projection events and compaction command handlers exist.

Decision:
- allowed in current vocabulary? yes

Reason:
- Current compaction grouping term is proven.

## DraftClaimCompactionBatch

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "DraftClaimCompaction|draft_claim_compaction|compaction_group|compaction_batch|compaction_node" src frontend tests migrations`

Exact matches:
- `migrations/104_create_draft_claim_compaction_plan.sql:70` - `CREATE TABLE IF NOT EXISTS draft_claim_compaction_batches`
- `tests/api/test_knowledge.py:23` - `DraftClaimCompactionBatchReadModel,`
- `src/contexts/knowledge_workbench/application/sagas/test_knowledge_extraction_command_handler_map.py:95` - `assert "ExecuteDraftClaimCompaction" in handler_types`
- `src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_workflow_definition.py:39` - `EXECUTE_DRAFT_CLAIM_COMPACTION = "ExecuteDraftClaimCompaction"`

Active code evidence:
- API read models/tests and workflow command map prove current batch compaction.

DB evidence:
- Current DB table: `draft_claim_compaction_batches`.

Runtime/event evidence:
- Command type: `ExecuteDraftClaimCompaction`.

Decision:
- allowed in current vocabulary? yes

Reason:
- Current compaction batch term is proven.

## DraftClaimCompactionNode

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "DraftClaimCompaction|draft_claim_compaction|compaction_group|compaction_batch|compaction_node" src frontend tests migrations`

Exact matches:
- `migrations/105_create_draft_claim_compaction_reduction_state.sql:1` - `CREATE TABLE IF NOT EXISTS draft_claim_compaction_nodes`
- `src/contexts/knowledge_workbench/observability/application/projectors/draft_claim_compaction_frontend_workflow_event_projector.py:166` - `"compaction_completed",`
- `tests/api/test_knowledge.py:25` - `DraftClaimCompactionNodeReadModel,`
- `src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_workflow_definition.py:96` - `DRAFT_CLAIM_COMPACTION_COMPLETED = "DraftClaimCompactionCompleted"`

Active code evidence:
- Active compaction read models/projectors and workflow definitions reference compaction nodes/completion.

DB evidence:
- Current DB table: `draft_claim_compaction_nodes`.

Runtime/event evidence:
- Event type: `DraftClaimCompactionCompleted`.

Decision:
- allowed in current vocabulary? yes

Reason:
- Current compaction reduction state is proven.

## DraftClaimCurationWorkspace

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "DraftClaimCuration|draft_claim_curation|curation_workspace|curation_item" src frontend tests migrations`

Exact matches:
- `migrations/108_add_draft_claim_curation_workspace.sql:1` - `CREATE TABLE IF NOT EXISTS draft_claim_curation_workspaces`
- `src/contexts/knowledge_workbench/application/sagas/handle_open_draft_claim_curation_workspace_command.py:47` - `class HandleOpenDraftClaimCurationWorkspaceCommand:`
- `src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_workflow_definition.py:39` - `OPEN_DRAFT_CLAIM_CURATION_WORKSPACE = "OpenDraftClaimCurationWorkspace"`
- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_workspace_repository.py:81` - `INSERT INTO draft_claim_curation_workspaces (`

Active code evidence:
- Current curation command handler and repository create/load workspaces.

DB evidence:
- Current DB table: `draft_claim_curation_workspaces`.

Runtime/event evidence:
- Command type: `OpenDraftClaimCurationWorkspace`.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong active curation evidence.

## DraftClaimCurationItem

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "DraftClaimCuration|draft_claim_curation|curation_workspace|curation_item" src frontend tests migrations`

Exact matches:
- `migrations/108_add_draft_claim_curation_workspace.sql:11` - `CREATE TABLE IF NOT EXISTS draft_claim_curation_items`
- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_workspace_repository.py:99` - `INSERT INTO draft_claim_curation_items (`
- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_workspace_repository.py:152` - `UPDATE draft_claim_curation_items`
- `tests/api/test_knowledge.py:2109` - `async def test_open_curation_workspace_creates_items_from_compacted_payload`

Active code evidence:
- Active repository and API tests use curation items.

DB evidence:
- Current DB table: `draft_claim_curation_items`.

Runtime/event evidence:
- Event type `DraftClaimCurationReviewRequired` exists in workflow definition.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong active curation item evidence.

## RuntimePublication

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "RuntimePublication|runtime_publication|knowledge_workbench_runtime_publications" src frontend tests migrations`

Exact matches:
- `migrations/070_create_faq_workbench_v1.sql:310` - `CREATE TABLE IF NOT EXISTS knowledge_workbench_runtime_publications (`
- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_publication_repository.py:182` - `INSERT INTO knowledge_workbench_runtime_publications (`
- `src/contexts/knowledge_workbench/infrastructure/postgres/postgres_workbench_document_run_cleanup_repository.py:906` - `DELETE FROM knowledge_workbench_runtime_publications`
- `tests/architecture/test_no_legacy_document_view_counters.py:64` - `"knowledge_workbench_runtime_publications",`

Active code evidence:
- Active publication repository writes runtime publication rows.

DB evidence:
- Current DB table: `knowledge_workbench_runtime_publications`.

Runtime/event evidence:
- Publication is produced by curation publication flow; no exact `RuntimePublication` class found.

Decision:
- allowed in current vocabulary? limited

Reason:
- Runtime publication storage is current, but new code should prefer exact table/model names present in code.

## RuntimeRetrievalEntry

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "RuntimeRetrievalEntry|runtime_retrieval_entry|knowledge_workbench_runtime_retrieval_entries|knowledge_workbench_runtime_retrieval_entry_embeddings" src frontend tests migrations`

Exact matches:
- `migrations/070_create_faq_workbench_v1.sql:322` - `CREATE TABLE IF NOT EXISTS knowledge_workbench_runtime_retrieval_entries (`
- `migrations/109_add_runtime_retrieval_entry_embeddings.sql:5` - `CREATE TABLE IF NOT EXISTS knowledge_workbench_runtime_retrieval_entry_embeddings (`
- `src/contexts/knowledge_workbench/retrieval/infrastructure/postgres/postgres_published_workbench_retrieval_repository.py:37` - `JOIN knowledge_workbench_runtime_retrieval_entries AS entry`
- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_publication_repository.py:298` - `INSERT INTO knowledge_workbench_runtime_retrieval_entries (`

Active code evidence:
- Current publication repository writes entries/embeddings; retrieval repository reads entries/embeddings.

DB evidence:
- Current DB tables: `knowledge_workbench_runtime_retrieval_entries`, `knowledge_workbench_runtime_retrieval_entry_embeddings`.

Runtime/event evidence:
- Runtime retrieval entry IDs are used in RAG eval and production retrieval.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong active runtime retrieval evidence.

## FrontendWorkflowEvent

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "FrontendWorkflowEvent|frontend_workflow_event|frontend_workflow_events" src frontend tests migrations`

Exact matches:
- `src/contexts/knowledge_workbench/observability/application/models/frontend_workflow_event.py:10` - `class FrontendWorkflowEvent:`
- `src/contexts/knowledge_workbench/observability/infrastructure/postgres/postgres_frontend_workflow_event_repository.py:27` - `INSERT INTO frontend_workflow_events (`
- `frontend/src/shared/api/modules/knowledge.ts:495` - `export type FrontendWorkflowEventEnvelope = {`
- `migrations/116_create_frontend_workflow_events.sql:1` - `CREATE TABLE IF NOT EXISTS frontend_workflow_events (`

Active code evidence:
- Backend model/repository and frontend API/event stream are current.

DB evidence:
- Current DB table: `frontend_workflow_events`.

Runtime/event evidence:
- Projection event type and source event id are active frontend projection contract.

Decision:
- allowed in current vocabulary? yes

Reason:
- Strong backend, DB, frontend contract evidence.

## RuntimeProgressSnapshot

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "RuntimeProgressSnapshot|runtime_progress_snapshot|WorkflowProgressSnapshot|workflow_runtime_progress_snapshots" src frontend tests migrations`

Exact matches:
- `src/contexts/workflow_runtime/domain/entities/workflow_progress_snapshot.py:14` - `class WorkflowProgressSnapshot:`
- `src/contexts/workflow_runtime/domain/entities/workflow_progress_snapshot.py:15` - `workflow_run_id: str`
- `migrations/098_workflow_runtime_progress_read_models.sql:1` - `CREATE TABLE IF NOT EXISTS workflow_runtime_progress_snapshots (`
- `tests/contexts/workflow_runtime/domain/test_workflow_progress_snapshot.py:20` - `WorkflowProgressSnapshot(`

Active code evidence:
- Exact code term is `WorkflowProgressSnapshot`; it is current runtime progress snapshot evidence.

DB evidence:
- Current DB table: `workflow_runtime_progress_snapshots`.

Runtime/event evidence:
- Runtime progress snapshot projection of workflow phase/status/counters.

Decision:
- allowed in current vocabulary? limited

Reason:
- The current equivalent is proven, but new code should use exact code name `WorkflowProgressSnapshot`.

## RuntimeTimelineEntry

Classification:
- PROVEN_CURRENT

Search commands run:
- `rg -n "RuntimeTimelineEntry|runtime_timeline_entry|WorkflowTimelineEntry|workflow_runtime_timeline_entries" src frontend tests migrations`

Exact matches:
- `src/contexts/workflow_runtime/domain/entities/workflow_timeline_entry.py:19` - `class WorkflowTimelineEntry:`
- `src/contexts/workflow_runtime/domain/entities/workflow_timeline_entry.py:22` - `event_type: str`
- `migrations/098_workflow_runtime_progress_read_models.sql:35` - `CREATE TABLE IF NOT EXISTS workflow_runtime_timeline_entries (`
- `src/contexts/workflow_runtime/infrastructure/postgres/postgres_timeline_repository.py:28` - `INSERT INTO workflow_runtime_timeline_entries`

Active code evidence:
- Exact code term is `WorkflowTimelineEntry`; timeline repository persists current runtime timeline entries.

DB evidence:
- Current DB table: `workflow_runtime_timeline_entries`.

Runtime/event evidence:
- Current runtime event timeline stores event_type, phase, work_item_id, attempt_id.

Decision:
- allowed in current vocabulary? limited

Reason:
- The current equivalent is proven, but new code should use exact code name `WorkflowTimelineEntry`.

## processing_run_id

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "processing_run_id|node_run_id|fact_registry|canonical_facts|knowledge_base|knowledge_documents|execution_queue|registry_snapshot|fact_id" src frontend tests migrations`

Exact matches:
- `migrations/070_create_faq_workbench_v1.sql:132` - `processing_run_id TEXT NOT NULL REFERENCES knowledge_workbench_processing_runs(processing_run_id) ON DELETE CASCADE,`
- `migrations/077_workbench_fact_registry_parent_contract.sql:226` - `processing_run_id,`
- `migrations/080_create_workbench_local_claim_retrieval_surface.sql:15` - `processing_run_id TEXT NOT NULL REFERENCES knowledge_workbench_processing_runs(processing_run_id) ON DELETE CASCADE,`
- `src/contexts/knowledge_workbench/application/sagas/delete_knowledge_extraction_document_run.py:24` - `processing_run_ids: tuple[str, ...]`

Active code evidence:
- Some cleanup/delete compatibility code references processing runs, but current runtime execution uses `workflow_run_id`, command log, and work items.

DB evidence:
- Legacy/suspect tables: `knowledge_workbench_processing_*`.

Runtime/event evidence:
- No current runtime command/work item authority uses `processing_run_id`.

Decision:
- allowed in current vocabulary? no

Reason:
- It belongs to the old processing architecture.

## node_run_id

Classification:
- TRANSITIONAL_CURRENT

Search commands run:
- `rg -n "processing_run_id|node_run_id|fact_registry|canonical_facts|knowledge_base|knowledge_documents|execution_queue|registry_snapshot|fact_id" src frontend tests migrations`

Exact matches:
- `migrations/070_create_faq_workbench_v1.sql:131` - `node_run_id TEXT PRIMARY KEY,`
- `migrations/080_create_workbench_local_claim_retrieval_surface.sql:17` - `node_run_id TEXT NOT NULL,`
- `src/contexts/knowledge_workbench/observability/application/read_models/workbench_document_workflow_live_state.py:204` - `node_run_id: str`
- `tests/contexts/knowledge_workbench/observability/application/read_models/test_workbench_document_workflow_live_state.py:113` - `node_run_id="node-run-1",`

Active code evidence:
- Live-state read model still exposes `node_run_id`, but this is a transitional UI/API leak rather than runtime-native authority.

DB evidence:
- Legacy/suspect tables: `knowledge_workbench_processing_node_runs`, local claim retrieval surface.

Runtime/event evidence:
- Current runtime-native equivalent is `work_item_id`/`attempt_id`; no new runtime gate should use `node_run_id`.

Decision:
- allowed in current vocabulary? no

Reason:
- Active compatibility leak exists, but new current Workbench code should not extend it.

## fact_registry

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "processing_run_id|node_run_id|fact_registry|canonical_facts|knowledge_base|knowledge_documents|execution_queue|registry_snapshot|fact_id" src frontend tests migrations`

Exact matches:
- `migrations/070_create_faq_workbench_v1.sql:187` - `CREATE TABLE IF NOT EXISTS knowledge_workbench_registry_snapshots (`
- `migrations/070_create_faq_workbench_v1.sql:189` - `fact_registry_id TEXT NOT NULL REFERENCES knowledge_workbench_fact_registries(fact_registry_id) ON DELETE CASCADE,`
- `migrations/076_workbench_schema_contract_forward_repair.sql:17` - `-- 2. knowledge_workbench_fact_registry_application_queue:`
- `migrations/077_workbench_fact_registry_parent_contract.sql:3` - `-- 077_workbench_fact_registry_parent_contract.sql`

Active code evidence:
- Evidence is old registry/canonical facts migration family, not current runtime workbench authority.

DB evidence:
- Legacy/suspect DB: `knowledge_workbench_fact_*`, `knowledge_workbench_registry_*`.

Runtime/event evidence:
- No current runtime command/work item authority uses fact registry terms.

Decision:
- allowed in current vocabulary? no

Reason:
- It is the old registry architecture.

## canonical_facts

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "canonical_facts|knowledge_workbench_canonical_facts" src frontend tests migrations`

Exact matches:
- `migrations/070_create_faq_workbench_v1.sql:217` - `CREATE TABLE IF NOT EXISTS knowledge_workbench_canonical_facts (`
- `migrations/077_workbench_fact_registry_parent_contract.sql:237` - `ON public.knowledge_workbench_canonical_facts (`
- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_publication_repository.py:227` - `INSERT INTO knowledge_workbench_canonical_facts (`
- `tests/contexts/knowledge_workbench/retrieval/infrastructure/postgres/test_postgres_published_workbench_retrieval_repository.py:99` - `assert "knowledge_workbench_canonical_facts" not in sql`

Active code evidence:
- Active retrieval tests reject canonical facts as production retrieval dependency.
- Publication repository still writes compatibility canonical facts rows.

DB evidence:
- Legacy/suspect DB table: `knowledge_workbench_canonical_facts`.

Runtime/event evidence:
- Runtime retrieval authority is runtime retrieval entries, not canonical facts.

Decision:
- allowed in current vocabulary? no

Reason:
- It is proven legacy/suspect even though compatibility writes remain.

## knowledge_base

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "knowledge_base|knowledge_documents" src frontend tests migrations`

Exact matches:
- `migrations/001_initial.sql:46` - `CREATE TABLE IF NOT EXISTS public.knowledge_base (`
- `migrations/026_add_fts_index.sql:3` - `ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS tsv tsvector;`
- `migrations/_retired_legacy/059_create_knowledge_entries_and_retrieval_surface.sql:6` - `-- - Runtime retrieval reads knowledge_retrieval_surface, not legacy knowledge_base.`
- `migrations/_retired_legacy/056_replace_knowledge_entry_type_with_entry_kind.sql:80` - `ANALYZE knowledge_base;`

Active code evidence:
- No current Workbench source-of-truth code evidence found for `knowledge_base`.

DB evidence:
- Legacy DB table: `knowledge_base`.

Runtime/event evidence:
- No current runtime command/work item authority.

Decision:
- allowed in current vocabulary? no

Reason:
- Old knowledge storage table, superseded for current Workbench by source/draft/runtime retrieval tables.

## knowledge_documents

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "knowledge_documents|knowledge_base" src frontend tests migrations`

Exact matches:
- `migrations/035_create_knowledge_documents.sql:5` - `CREATE TABLE IF NOT EXISTS knowledge_documents (`
- `migrations/066_create_commercial_price_knowledge.sql:13` - `knowledge_document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,`
- `migrations/_retired_legacy/035_create_knowledge_documents.sql:2` - `CREATE TABLE knowledge_documents (`
- `migrations/_retired_legacy/059_create_knowledge_entries_and_retrieval_surface.sql:14` - `document_id UUID REFERENCES knowledge_documents(id) ON DELETE CASCADE,`

Active code evidence:
- No current FAQ Workbench source-of-truth path found that should use `knowledge_documents`.

DB evidence:
- Legacy DB table: `knowledge_documents`; commercial-price references are outside this cleanup scope.

Runtime/event evidence:
- No current runtime event/command/work item authority.

Decision:
- allowed in current vocabulary? no

Reason:
- Old document storage term; current Workbench uses `SourceDocument`/`source_documents`.

## execution_queue

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "execution_queue|execution_work_items|work_item_id" src frontend tests migrations`

Exact matches:
- `migrations/002_add_execution_queue.sql:2` - `CREATE TABLE IF NOT EXISTS execution_queue (`
- `migrations/052_add_model_usage_events_and_queue_schedule.sql:26` - `ALTER TABLE execution_queue`
- `tests/database/repositories/test_queue_repository.py:111` - `assert "UPDATE public.execution_queue" in sql_arg`
- `migrations/998_rescue_restore_execution_queue_next_attempt_at.sql:1` - `ALTER TABLE public.execution_queue`

Active code evidence:
- Legacy queue repository tests remain, but current workflow/capacity architecture uses execution work items and runtime command log.

DB evidence:
- Legacy DB table: `execution_queue`; current DB tables are `execution_work_items` and attempt/dispatch tables.

Runtime/event evidence:
- No current workflow runtime event/command should use `execution_queue`.

Decision:
- allowed in current vocabulary? no

Reason:
- It is old queue architecture.

## registry_snapshot

Classification:
- PROVEN_LEGACY

Search commands run:
- `rg -n "registry_snapshot|knowledge_workbench_registry_snapshots" src frontend tests migrations`

Exact matches:
- `migrations/070_create_faq_workbench_v1.sql:187` - `CREATE TABLE IF NOT EXISTS knowledge_workbench_registry_snapshots (`
- `migrations/076_workbench_schema_contract_forward_repair.sql:42` - `AND table_name = 'knowledge_workbench_registry_snapshots'`
- `migrations/077_workbench_fact_registry_parent_contract.sql:9` - `--   knowledge_workbench_registry_snapshots.registry_id`
- `migrations/075_workbench_parallel_section_batch_queue.sql:6` - `observed_registry_snapshot_id text NOT NULL,`

Active code evidence:
- Evidence is registry/processing migration family; no current runtime authority uses it.

DB evidence:
- Legacy/suspect DB table: `knowledge_workbench_registry_snapshots`.

Runtime/event evidence:
- No current event_type, command_type, work_kind, or payload key for runtime authority.

Decision:
- allowed in current vocabulary? no

Reason:
- Old registry snapshot architecture.

## fact_id

Classification:
- TRANSITIONAL_CURRENT

Search commands run:
- `rg -n "fact_id|expected_fact_id|matched_fact_id|target_fact_id" src frontend tests migrations`

Exact matches:
- `migrations/070_create_faq_workbench_v1.sql:218` - `fact_id TEXT PRIMARY KEY,`
- `migrations/117_extend_runtime_retrieval_entries_for_canonical_publish.sql:19` - `ALTER COLUMN fact_id DROP NOT NULL;`
- `src/contexts/knowledge_workbench/rag_eval/infrastructure/postgres/postgres_workbench_rag_eval_repository.py:43` - `COALESCE(NULLIF(entry.fact_id, ''), entry.runtime_entry_id) AS fact_id,`
- `src/contexts/knowledge_workbench/rag_eval/application/models/workbench_rag_eval.py:123` - `expected_fact_id: str`

Active code evidence:
- RAG eval and transitional runtime retrieval code still carry `fact_id`, with fallback to `runtime_entry_id`.

DB evidence:
- Legacy/suspect canonical facts use `fact_id`.
- Transitional runtime retrieval table still has nullable `fact_id` after migration 117.

Runtime/event evidence:
- No new runtime-native authority should be keyed by `fact_id`; runtime retrieval entry IDs are current.

Decision:
- allowed in current vocabulary? no

Reason:
- It is transitional residue from canonical facts/registry. Existing compatibility may remain until separately removed, but new Workbench code should not use it.

# Conclusions

## Terms allowed in current Workbench vocabulary

- PROVEN_CURRENT: `SourceDocument`, `SourceUnit`, `source_document_ref`, `source_unit_ref`, `workflow_run_id`, `workflow command`, `work_item_id`, `attempt_id`, `DraftClaimObservation`, `DraftClaimEmbedding`, `DraftClaimCompactionGroup`, `DraftClaimCompactionBatch`, `DraftClaimCompactionNode`, `DraftClaimCurationWorkspace`, `DraftClaimCurationItem`, `RuntimeRetrievalEntry`, `FrontendWorkflowEvent`.
- Limited PROVEN_CURRENT equivalents: `RuntimePublication` only as runtime publication table/repository vocabulary; `RuntimeProgressSnapshot` should use exact code term `WorkflowProgressSnapshot`; `RuntimeTimelineEntry` should use exact code term `WorkflowTimelineEntry`.
- Carefully scoped TRANSITIONAL_CURRENT: `RagEval` only for the active RAG eval feature, not as source-of-truth cleanup vocabulary.

## Terms forbidden in new current Workbench code

- PROVEN_LEGACY: `CompilerRun`, `AnswerCandidate`, `CandidateCluster`, `CanonicalKnowledgeEntry`, `KnowledgeEditAction`, `processing_run_id`, `fact_registry`, `canonical_facts`, `knowledge_base`, `knowledge_documents`, `execution_queue`, `registry_snapshot`.
- UNPROVEN_REJECTED: `KnowledgeEnrichment`, `RetrievalSurface`, `EvalCase`.
- Transitional terms forbidden for new runtime-native authority: `node_run_id`, `fact_id`.

## Terms requiring separate audit

- `RagEval`: active but transitional; audit whether it is workflow/capacity-native or direct/synchronous.
- `node_run_id`: active live-state compatibility leak; audit migration to `work_item_id`/`attempt_id`.
- `fact_id`: active transitional RAG eval/runtime retrieval residue; audit replacement by `runtime_entry_id`.
- OUT_OF_SCOPE terms: none classified as OUT_OF_SCOPE in this audit.

## Required edits to existing generated docs

- `docs/generated/agent-cleanup-rules.md:37-69`: replace the “Proven current vocabulary” section with this audit's allowed/forbidden lists. In particular, keep `CompilerRun`, `AnswerCandidate`, `CandidateCluster`, `CanonicalKnowledgeEntry`, `KnowledgeEnrichment`, `RetrievalSurface`, `EvalCase`, and `KnowledgeEditAction` forbidden; scope `RagEval` as transitional only.
- `docs/generated/current-vertical-authority-map.md`: add a short vocabulary caveat near the current authority summary stating that `RuntimeProgressSnapshot` and `RuntimeTimelineEntry` are doc-level equivalents for exact code names `WorkflowProgressSnapshot` and `WorkflowTimelineEntry`.
- `docs/generated/source-of-truth-audit.md:412` and nearby legacy vocabulary discussion: split `node_run_id` from purely legacy terms as a transitional live-state leak, while still forbidding it in new runtime-native code.
- `docs/generated/source-of-truth-audit.md:374-378`: clarify that publication/retrieval proof is for `RuntimePublication`/`RuntimeRetrievalEntry`; do not call this `RetrievalSurface`.
- `docs/generated/legacy-dependency-index.md:241-263`: add `CompilerRun`, `AnswerCandidate`, `CandidateCluster`, `CanonicalKnowledgeEntry`, `KnowledgeEditAction`, `KnowledgeEnrichment`, `RetrievalSurface`, and `EvalCase` to the forbidden/legacy-or-unproven vocabulary cleanup list.
- `docs/generated/legacy-dependency-index.md:301-308`: keep commercial-price `knowledge_documents` notes out of Workbench cleanup, but continue forbidding `knowledge_documents` for new Workbench code.
- `docs/generated/pause-split-brain-incident.md`: no pause-semantics change required from this vocabulary audit; optionally add a note that pause incident language should use `workflow_run_id`, `work_item_id`, `attempt_id`, `WorkflowProgressSnapshot`, and `WorkflowTimelineEntry`, not `processing_run_id`/`node_run_id`.

