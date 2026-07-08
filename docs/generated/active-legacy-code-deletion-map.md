# Active Legacy Code Deletion Map

This map was written before deletion. Recon used targeted `rg` searches over `src`, `frontend`, `tests`, and `migrations`, then inspected callers for the active matches. Classification was based on active callers and behavior, not table-name substring alone.

## Immediate delete candidates

- `src/application/services/commercial_price_ingestion_service.py`
  - classification: DELETE_NOW_COMMERCIAL_PRICE_BRANCH
  - DB tables involved: `commercial_price_documents`, `commercial_price_source_units`, `commercial_price_source_rows`, `commercial_price_facts`, `knowledge_documents`
  - callers/imports: `tests/application/services/test_commercial_price_ingestion_service.py`; composed through abandoned commercial acquisition/review branch
  - why safe to delete now: user decision declares commercial_price abandoned and not part of current `source_documents/source_units -> draft_claim_* -> runtime_retrieval_entries` vertical
  - tests to delete/update: commercial price service, ports, repository, mapper, tool, graph guard tests

- `src/application/services/commercial_truth_review_service.py`, `src/application/services/commercial_price_review_service.py`, `src/interfaces/composition/commercial_price_review.py`
  - classification: DELETE_NOW_COMMERCIAL_PRICE_BRANCH
  - DB tables involved: `commercial_price_*`, old `knowledge_documents` detail views
  - callers/imports: `src/interfaces/http/knowledge.py` price-facts and commercial-truth-review endpoints
  - why safe to delete now: these endpoints expose the abandoned branch and keep old commercial tables active
  - tests to delete/update: commercial truth/review service and API route guard tests

- `src/application/ports/commercial_price.py`, `src/application/ports/commercial_price_acquisition.py`, `src/infrastructure/db/repositories/commercial_price_repository.py`, `src/infrastructure/db/repositories/commercial_price_mappers.py`, `src/infrastructure/commercial_price/markdown_acquisition_adapter.py`
  - classification: DELETE_NOW_COMMERCIAL_PRICE_BRANCH
  - DB tables involved: `commercial_price_*`
  - callers/imports: FastAPI lifespan tool registration, commercial services, commercial tests
  - why safe to delete now: branch is abandoned and not current Workbench runtime
  - tests to delete/update: repository mapper, acquisition adapter, ports guard tests

- `src/agent/nodes/commercial_context_lookup.py` and `CommercialPriceLookupTool` in `src/tools/builtins.py`
  - classification: DELETE_NOW_COMMERCIAL_PRICE_BRANCH
  - DB tables involved: `commercial_price_facts`
  - callers/imports: `src/agent/graph.py`, `src/interfaces/composition/fastapi_lifespan.py`, commercial context tests
  - why safe to delete now: commercial_price runtime lookup is part of the abandoned branch
  - tests to delete/update: commercial context graph/node/tool tests and prompt-builder commercial-context tests

- `src/infrastructure/db/repositories/knowledge_document_persistence.py`
  - classification: DELETE_NOW_LEGACY
  - DB tables involved: `knowledge_documents`
  - callers/imports: `src/infrastructure/db/repositories/knowledge_repository.py`
  - why safe to delete now: old queue-based Workbench document upload is retired; current upload writes `source_documents`, `source_units`, and `knowledge_workbench_documents`
  - tests to delete/update: `tests/infrastructure/db/repositories/test_knowledge_document_persistence_cancel_guard.py`

- `src/infrastructure/db/repositories/knowledge_document_queries.py`
  - classification: DELETE_NOW_LEGACY
  - DB tables involved: `knowledge_documents`, plus current counters used only to decorate old document rows
  - callers/imports: `src/infrastructure/db/repositories/knowledge_repository.py`; commercial review services
  - why safe to delete now: active `GET /knowledge` endpoint already uses `knowledge_workbench_documents` fallback in `src/interfaces/http/knowledge.py:616-680`
  - tests to delete/update: old document view repository tests

- `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_publication_repository.py`
  - classification: DELETE_NOW_LEGACY for registry/canonical compatibility writes only
  - DB tables involved: delete writes to `knowledge_workbench_fact_registries`, `knowledge_workbench_canonical_facts`, `knowledge_workbench_fact_triples`
  - callers/imports: curation publication use case
  - why safe to delete now: current retrieval reads `knowledge_workbench_runtime_retrieval_entries` and tests assert it must not join canonical facts
  - tests to delete/update: publication repository tests that assert old compatibility writes

## Commercial price branch

- all files:
  - `src/application/ports/commercial_price.py`
  - `src/application/ports/commercial_price_acquisition.py`
  - `src/application/services/commercial_price_acquisition_preparation_service.py`
  - `src/application/services/commercial_price_acquisition_service.py`
  - `src/application/services/commercial_price_ingestion_service.py`
  - `src/application/services/commercial_price_review_service.py`
  - `src/application/services/commercial_truth_review_service.py`
  - `src/domain/commercial/commercial_truth.py`
  - `src/infrastructure/commercial_price/markdown_acquisition_adapter.py`
  - `src/infrastructure/db/repositories/commercial_price_mappers.py`
  - `src/infrastructure/db/repositories/commercial_price_repository.py`
  - `src/interfaces/composition/commercial_price_acquisition.py`
  - `src/interfaces/composition/commercial_price_review.py`
  - `src/agent/nodes/commercial_context_lookup.py`
- all endpoints:
  - `GET /api/projects/{project_id}/knowledge/{document_id}/price-facts`
  - `GET /api/projects/{project_id}/knowledge/commercial-truth-review`
  - `GET /api/projects/{project_id}/knowledge/{document_id}/commercial-truth-review`
  - `POST /api/projects/{project_id}/knowledge/{document_id}/price-facts/publish`
  - `POST /api/projects/{project_id}/knowledge/{document_id}/price-facts/reject`
- all tests:
  - commercial price/truth service, ports, repository, mapper, acquisition, tool, graph, and API route guard tests found by `rg -l 'commercial_price|commercial_truth|CommercialPrice|CommercialTruth|price_review' src frontend tests`
- all DB tables:
  - `commercial_price_documents`
  - `commercial_price_source_units`
  - `commercial_price_source_rows`
  - `commercial_price_facts`
- frontend/API references:
  - `frontend/src/shared/api/generated/schema.ts`
  - commercial truth / price facts i18n keys in `frontend/src/shared/i18n/*`
- deletion decision:
  - DELETE_NOW_COMMERCIAL_PRICE_BRANCH, but remove the full graph/tool/API/test surface together.

## Transitional blockers

- `execution_queue`
  - file/path: `src/infrastructure/db/repositories/queue_repository.py`, `src/infrastructure/queue/*`, `src/interfaces/composition/fastapi_lifespan.py`, `src/application/orchestration/client_message_service.py`, `src/tools/builtins.py`, `src/interfaces/http/metrics.py`
  - table/field: `execution_queue`
  - why not safe to delete now: active producers and consumers remain for manager notifications, escalation, metrics aggregation, and worker runtime
  - required prior patch: replace manager notification / metrics queueing with current runtime-native or another supported background mechanism, then remove worker runtime and queue repository

- `knowledge_extraction_*`
  - file/path: `postgres_knowledge_extraction_saga_state_repository.py`, pause/resume composition, live-state hydration, due workflow reader
  - table/field: `knowledge_extraction_workflow_runs`, `knowledge_extraction_phase_checkpoints`, `knowledge_extraction_command_log`, `knowledge_extraction_event_cursor`, `pause_reason`
  - why not safe to delete now: pause/resume/live-state still read/write this control-plane
  - required prior patch: introduce runtime-native pause gate/state and move hydration off legacy saga rows

- `claim_extraction_stage_work_items`
  - file/path: `run_claim_extraction_stage.py`, `postgres_claim_extraction_stage_progress_query.py`, stage progress composition/read models
  - table/field: `claim_extraction_stage_work_items`
  - why not safe to delete now: active claim-stage progress code still reads it
  - required prior patch: migrate stage progress to `execution_work_items`/attempts and delete stage index readers

- `processing_run_id` / `node_run_id`
  - file/path: `faq_workbench_workflow_live_state.py`, frontend knowledge page/projection/types
  - table/field: `knowledge_workbench_documents.current_processing_run_id`, live-state `node_run_id`
  - why not safe to delete now: frontend/API live-state still exposes these transitional names
  - required prior patch: rename/remove DTO fields and migrate to `workflow_run_id`, `work_item_id`, `attempt_id`

- `RagEval` / `fact_id`
  - file/path: `src/contexts/knowledge_workbench/rag_eval/*`, runtime retrieval repository models
  - table/field: RAG eval `expected_fact_id`, `matched_fact_id`, `target_fact_id`; runtime retrieval transitional `fact_id`
  - why not safe to delete now: active RAG eval stores compatibility fact IDs and runtime retrieval still has nullable `fact_id`
  - required prior patch: separate RAG eval audit and migration to `runtime_entry_id` only

## Current runtime: do not touch

- `source_documents`, `source_units`
- `workflow_runtime_command_log`, `workflow_runtime_event_cursors`, `workflow_runtime_outbox_events`, `workflow_runtime_progress_snapshots`, `workflow_runtime_resource_usage_snapshots`, `workflow_runtime_timeline_entries`
- `frontend_workflow_events`
- `execution_work_items`, `execution_work_item_schedules`, `execution_work_item_attempts`, `execution_work_item_attempt_dispatches`
- `draft_claim_observations`, `draft_claim_observation_possible_questions`, `draft_claim_observation_provenance`, `draft_claim_embeddings`
- `draft_claim_compaction_*`, `draft_claim_curation_*`
- `knowledge_workbench_runtime_publications`, `knowledge_workbench_runtime_retrieval_entries`, `knowledge_workbench_runtime_retrieval_entry_embeddings`
- active files discovered during search:
  - `src/contexts/execution_runtime/*`
  - `src/contexts/workflow_runtime/*`
  - `src/contexts/knowledge_workbench/source_management/*`
  - `src/contexts/knowledge_workbench/extraction/*` draft/source/current runtime paths, except the high-risk stage-work-item blocker above
  - `src/contexts/knowledge_workbench/retrieval/*`

## Proposed first deletion wave

- Delete/modify commercial_price branch files, endpoints, generated schema/i18n references, graph node/tool registration, and preserving tests.
- Delete old `knowledge_documents` repository/persistence wrappers once `KnowledgeRepository` no longer exposes old document methods.
- Simplify curation publication to write only `knowledge_workbench_runtime_publications`, `knowledge_workbench_runtime_retrieval_entries`, and `knowledge_workbench_runtime_retrieval_entry_embeddings`.
- Remove cleanup handling for registry/canonical tables, but keep current runtime cleanup.
- Add migration `119_drop_removed_legacy_db_branches.sql` dropping only:
  - `commercial_price_facts`
  - `commercial_price_source_rows`
  - `commercial_price_source_units`
  - `commercial_price_documents`
  - `knowledge_base`
  - `knowledge_documents`
  - `knowledge_workbench_fact_registry_applications`
  - `knowledge_workbench_fact_registry_application_queue`
  - `knowledge_workbench_registry_update_applications`
  - `knowledge_workbench_registry_snapshots`
  - `knowledge_workbench_fact_triples`
  - `knowledge_workbench_fact_relations`
  - `knowledge_workbench_fact_mentions`
  - `knowledge_workbench_canonical_facts`
  - `knowledge_workbench_fact_registries`

