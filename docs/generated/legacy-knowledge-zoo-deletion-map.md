# Legacy Knowledge Zoo Deletion Map

## Executive Summary

- safe to delete active code now? yes, but only one proven active-code residue: unused surface/retrieval DTO classes in `src/application/dto/knowledge_dto.py`.
- tables safe to drop now? no new drop migration is needed in this task. `knowledge_entries`, `knowledge_retrieval_surface`, `knowledge_source_chunks`, and `knowledge_edit_actions` are already dropped by `migrations/112_drop_retired_legacy_knowledge_schema.sql`. The `knowledge_answer_candidates`, `knowledge_candidate_clusters`, `knowledge_candidate_cluster_members`, `knowledge_compiler_runs`, `knowledge_surface_compiler_runs`, and `knowledge_edit_action_runs` tables were not found in active migration history or the schema dump search.
- blockers: current RagEval/curation UI and current Workbench compaction code still use generic `enrichment` fields/prompt variants. Those are not the old `KnowledgeEnrichment` table/model and must not be deleted here.
- false positives: guard tests that intentionally mention forbidden legacy terms; retired migrations; active comments/README vocabulary; `retrieval_surface_role` trace field that maps current runtime retrieval search scoring, not the old `knowledge_retrieval_surface` table.

Search commands run:

```text
rg -n -e CompilerRun -e compiler_run -e knowledge_compiler_runs -e knowledge_surface_compiler_runs src frontend tests migrations
rg -n -e AnswerCandidate -e answer_candidate -e knowledge_answer_candidates src frontend tests migrations
rg -n -e CandidateCluster -e candidate_cluster -e knowledge_candidate_clusters -e knowledge_candidate_cluster_members src frontend tests migrations
rg -n -e CanonicalKnowledgeEntry -e canonical_knowledge_entry -e knowledge_entries src frontend tests migrations
rg -n -e KnowledgeEditAction -e knowledge_edit_action -e knowledge_edit_actions -e knowledge_edit_action_runs src frontend tests migrations
rg -n -e RetrievalSurface -e retrieval_surface -e knowledge_retrieval_surface src frontend tests migrations
rg -n -e KnowledgeSourceChunk -e knowledge_source_chunk -e knowledge_source_chunks src frontend tests migrations
rg -n -e KnowledgeEnrichment -e knowledge_enrichment -e enrichment src frontend tests migrations
rg -n -e EvalCase -e eval_case -e RetrievalEvalCase src frontend tests migrations
find src \( -iname "*answer*candidate*" -o -iname "*candidate*cluster*" -o -iname "*compiler*run*" -o -iname "*knowledge*entry*" -o -iname "*retrieval*surface*" -o -iname "*source*chunk*" -o -iname "*edit*action*" \) -print
find tests \( -iname "*answer*candidate*" -o -iname "*candidate*cluster*" -o -iname "*compiler*run*" -o -iname "*knowledge*entry*" -o -iname "*retrieval*surface*" -o -iname "*source*chunk*" -o -iname "*edit*action*" \) -print
```

## Table / Term Inventory

| Term/table | Active src refs | Active test refs | Migration refs | Classification | Action |
|---|---:|---:|---:|---|---|
| `CompilerRun` / `compiler_run` | 0 | 1 guard | 1 retired field | RETIRED_MIGRATION_ONLY | no code deletion |
| `knowledge_compiler_runs` | 0 | 2 guards | 0 | FALSE_POSITIVE | no migration; table not found |
| `knowledge_surface_compiler_runs` | 0 | 1 guard | 0 | FALSE_POSITIVE | no migration; table not found |
| `AnswerCandidate` / `answer_candidate` | 0 | 3 guards | 0 | FALSE_POSITIVE | no code deletion |
| `knowledge_answer_candidates` | 0 | 2 guards | 0 | FALSE_POSITIVE | no migration; table not found |
| `CandidateCluster` / `candidate_cluster` | 2 current policy/test variant strings | 1 guard | 0 | FALSE_POSITIVE | keep current draft-claim clustering policy string |
| `knowledge_candidate_clusters` | 0 | 2 guards | 0 | FALSE_POSITIVE | no migration; table not found |
| `knowledge_candidate_cluster_members` | 0 | 2 guards | 0 | FALSE_POSITIVE | no migration; table not found |
| `CanonicalKnowledgeEntry` | 1 active event payload key, 1 guard | 0 | 1 retired comment | FALSE_POSITIVE | do not delete current publication count key in this task |
| `knowledge_entries` | 0 active table refs | several guards | active drop/check migration plus retired creates | MIGRATION_HISTORY_ONLY | already dropped by migration 112 |
| `KnowledgeEditAction` / `knowledge_edit_action` | 2 model-usage source strings | guard-only tests | retired comments | ACTIVE_TRANSITIONAL_BLOCKER | keep model usage source classification until separate audit |
| `knowledge_edit_actions` | 0 active table refs | guards | active drop plus retired creates | MIGRATION_HISTORY_ONLY | already dropped by migration 112 |
| `knowledge_edit_action_runs` | 0 | 0 | 0 | FALSE_POSITIVE | table not found |
| `RetrievalSurface` | unused DTO class only | guard filenames/tests | README/retired comments | DELETE_NOW_LEGACY_CODE | delete unused DTO block |
| `knowledge_retrieval_surface` | 0 active table refs | guards | active drop/check migration plus retired creates | MIGRATION_HISTORY_ONLY | already dropped by migration 112 |
| `KnowledgeSourceChunk` | 0 | 0 | 0 | FALSE_POSITIVE | no action |
| `knowledge_source_chunks` | 0 active table refs | guards | active drop plus retired creates | MIGRATION_HISTORY_ONLY | already dropped by migration 112 |
| `KnowledgeEnrichment` | 0 exact active model refs | 0 | 0 | FALSE_POSITIVE | no model/table exists |
| `enrichment` | current Workbench/RagEval fields and prompt variants | current tests | retired comments | ACTIVE_TRANSITIONAL_BLOCKER | keep; not old KnowledgeEnrichment |
| `EvalCase` / `RetrievalEvalCase` | README only | 0 | 0 | ACTIVE_TRANSITIONAL_BLOCKER | RagEval explicitly out of scope |

## Active Code References

- `src/application/dto/knowledge_dto.py:324`
  - term/table: `SurfaceCompilationRunDto`, part of old surface compiler DTO block.
  - caller/imports: `rg` found no references outside this file.
  - behavior: no active behavior; orphan DTO residue.
  - classification: DELETE_NOW_LEGACY_CODE.
  - delete now? yes.
  - reason: old surface compilation/retrieval DTOs are not imported, and current Workbench runtime uses source/draft/runtime retrieval contracts instead.

- `src/application/dto/knowledge_dto.py:366`
  - term/table: `RetrievalSurfaceDto`.
  - caller/imports: `rg` found no references outside this file.
  - behavior: no active behavior; orphan DTO residue for old retrieval surface API.
  - classification: DELETE_NOW_LEGACY_CODE.
  - delete now? yes.
  - reason: not current `knowledge_workbench_runtime_retrieval_entries`; no active route or frontend API contract uses it.

- `src/application/dto/knowledge_dto.py:404`
  - term/table: old surface relation/ownership DTOs.
  - caller/imports: `rg` found no references outside this file.
  - behavior: no active behavior.
  - classification: DELETE_NOW_LEGACY_CODE.
  - delete now? yes.
  - reason: part of same orphan legacy surface DTO block.

- `src/contexts/knowledge_workbench/application/sagas/handle_publish_draft_claim_curation_workspace_command.py:187`
  - term/table: payload key `published_canonical_knowledge_entry_count`.
  - caller/imports: current workflow publication command handler.
  - behavior: timeline/progress event metadata label.
  - classification: FALSE_POSITIVE.
  - delete now? no.
  - reason: not a table/model reference; renaming event payload keys is outside this cleanup and could create projection/API drift.

- `src/domain/project_plane/model_usage_views.py:14`
  - term/table: model usage source string `knowledge_edit_action`.
  - caller/imports: model usage view/source vocabulary.
  - behavior: historical usage source classification.
  - classification: ACTIVE_TRANSITIONAL_BLOCKER.
  - delete now? no.
  - reason: not a legacy table reference; needs separate model usage source audit.

- `src/infrastructure/db/repositories/model_usage_repository.py:209`
  - term/table: query source string `knowledge_edit_action`.
  - caller/imports: model usage repository.
  - behavior: usage filtering/reporting.
  - classification: ACTIVE_TRANSITIONAL_BLOCKER.
  - delete now? no.
  - reason: deleting without source taxonomy migration could break usage reports.

- `src/domain/project_plane/knowledge_views.py:45`
  - term/table: `retrieval_surface_role`.
  - caller/imports: current search trace view and DTO conversion.
  - behavior: current runtime retrieval search trace metadata.
  - classification: FALSE_POSITIVE.
  - delete now? no.
  - reason: not the old `knowledge_retrieval_surface` table.

- `src/infrastructure/db/repositories/knowledge_search_ranking.py:377`
  - term/table: `retrieval_surface_role`.
  - caller/imports: current runtime search ranking.
  - behavior: labels runtime search result safety.
  - classification: FALSE_POSITIVE.
  - delete now? no.
  - reason: current search trace metadata, not old retrieval surface persistence.

- `src/contexts/knowledge_workbench/extraction/application/*single_draft_claim_enrichment*`
  - term/table: `single_draft_claim_enrichment` prompt variant and payload builder.
  - caller/imports: current draft-claim compaction flow.
  - behavior: current singleton draft-claim enrichment prompt variant.
  - classification: ACTIVE_TRANSITIONAL_BLOCKER.
  - delete now? no.
  - reason: current Workbench compaction behavior; not the old `KnowledgeEnrichment` model.

- `frontend/src/pages/rag-eval/components/*`
  - term/table: `entry.enrichment`, `has_retrieval_surface`, `no_retrieval_surface`.
  - caller/imports: current RagEval/curation UI.
  - behavior: active RagEval curation view state.
  - classification: ACTIVE_TRANSITIONAL_BLOCKER.
  - delete now? no.
  - reason: RagEval is explicitly not in scope.

## Test References

- `tests/architecture/test_knowledge_repository_legacy_zoo_deleted.py:8`
  - what behavior it preserves: guards that old zoo repository files and markers stay deleted.
  - classification: FALSE_POSITIVE.
  - delete/update decision: keep.

- `tests/architecture/test_dropped_legacy_knowledge_tables_not_referenced.py:9`
  - what behavior it preserves: guards dropped legacy table tokens are not resurrected in source/active migrations.
  - classification: FALSE_POSITIVE.
  - delete/update decision: keep.

- `tests/architecture/test_no_retired_legacy_db_refs.py:28`
  - what behavior it preserves: guards live code does not reference retired legacy DB tables.
  - classification: FALSE_POSITIVE.
  - delete/update decision: keep.

- `tests/architecture/test_workbench_document_delete_recover_contract.py`, `test_workbench_upload_visibility_bridge.py`, `test_workbench_upload_route_uses_current_workflow.py`
  - what behavior it preserves: asserts Workbench upload/delete paths avoid old `knowledge_entries`, `knowledge_source_chunks`, and `knowledge_retrieval_surface`.
  - classification: FALSE_POSITIVE.
  - delete/update decision: keep.

- current Workbench tests with `single_draft_claim_enrichment`
  - what behavior it preserves: current draft-claim compaction singleton prompt behavior.
  - classification: ACTIVE_TRANSITIONAL_BLOCKER.
  - delete/update decision: keep.

## Migration References

- `knowledge_entries`
  - migration file: `migrations/_retired_legacy/059_create_knowledge_entries_and_retrieval_surface.sql`.
  - creates table? yes, retired only.
  - already retired? yes.
  - needs final drop migration? no, `migrations/112_drop_retired_legacy_knowledge_schema.sql:29` already drops it.

- `knowledge_retrieval_surface`
  - migration file: `migrations/_retired_legacy/059_create_knowledge_entries_and_retrieval_surface.sql`.
  - creates table? yes, retired only.
  - already retired? yes.
  - needs final drop migration? no, `migrations/112_drop_retired_legacy_knowledge_schema.sql:28` already drops it.

- `knowledge_source_chunks`
  - migration file: `migrations/_retired_legacy/058_create_knowledge_source_chunks.sql`.
  - creates table? yes, retired only.
  - already retired? yes.
  - needs final drop migration? no, `migrations/112_drop_retired_legacy_knowledge_schema.sql:30` already drops it.

- `knowledge_edit_actions`
  - migration file: `migrations/_retired_legacy/062_kcd_stage_h_knowledge_edit_actions.sql`.
  - creates table? yes, retired only.
  - already retired? yes.
  - needs final drop migration? no, `migrations/112_drop_retired_legacy_knowledge_schema.sql:26` already drops it.

- `knowledge_answer_candidates`, `knowledge_candidate_clusters`, `knowledge_candidate_cluster_members`, `knowledge_compiler_runs`, `knowledge_surface_compiler_runs`, `knowledge_edit_action_runs`
  - migration file: none found in active migrations, retired migrations, or the available schema dump path.
  - creates table? no evidence found.
  - already retired? no active object evidence found.
  - needs final drop migration? no.

## Drop Candidates

No new drop migration is required in this task.

Already dropped by migration 112:

- `knowledge_entries`
- `knowledge_retrieval_surface`
- `knowledge_source_chunks`
- `knowledge_edit_actions`

No active migration/schema evidence found for:

- `knowledge_answer_candidates`
- `knowledge_candidate_cluster_members`
- `knowledge_candidate_clusters`
- `knowledge_compiler_runs`
- `knowledge_surface_compiler_runs`
- `knowledge_edit_action_runs`

## Not In Scope

- `execution_queue`
- `workflow_runtime_*`
- `execution_work_items*`
- `source_documents/source_units`
- `draft_claim_*`
- runtime retrieval entries: `knowledge_workbench_runtime_retrieval_entries`
- RagEval tables and current RagEval UI/API behavior
- `knowledge_extraction_*`
- `claim_extraction_stage_work_items`
