# Knowledge Curation Design Decisions — 2026-05-18T09:35:00Z

## Boundaries
- Added domain/application-safe curation contracts in `src/domain/project_plane/knowledge_curation.py`; no FastAPI/DB/Redis/LLM imports.
- Added orchestration/policy service in `src/application/services/knowledge_curation_service.py` for issue classification, duplicate grouping, status validation, merge preview and merge apply coordination.
- Kept SQL and embedding side effects in `KnowledgeRepository`.
- Added separate route module `src/interfaces/http/knowledge_curation.py` under `/api/projects/{project_id}/knowledge/{document_id}/curation`.

## Status model
- Chosen: add real `merged` status to `KnowledgeEntryStatus` and DB CHECK constraint.
- Reason: existing status storage is text with CHECK, not a PostgreSQL enum; adding a value is a small compatible migration.
- Absorbed entries are additionally marked `visibility='hidden'` and `metadata.curation.merged_into` / `absorbed_by_action_id`.

## Audit/action model
- Reused `knowledge_edit_actions` as canonical audit table.
- Added source-neutral curation fields while preserving old RAG Eval source columns.
- Extended action vocabulary for manual curation and status/edit/merge actions.

## Runtime retrieval consistency
- Non-runtime status changes and absorbed merge children delete `knowledge_retrieval_surface` rows.
- Published/runtime rebuild uses existing `rebuild_entry_embedding` path, now upserting runtime surface when source refs exist.
- No physical deletion of canonical entries was added.

## Frontend structure
- New API module: `frontend/src/shared/api/modules/knowledgeCuration.ts`.
- New UI components under `frontend/src/pages/rag-eval/components/`.
- `RagEvalPage.tsx` only integrates tabs and console wiring; existing Retrieval Review flow remains intact.
