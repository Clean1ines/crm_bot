# Knowledge Curation Recon — 2026-05-18T09:35:00Z

## Repo / runner
- Repo root: `/workspace/crm_bot` (`pwd`, `git rev-parse --show-toplevel`).
- `/home/haku/crm_bot` not present; used current checkout.
- `venv/bin/python` and `.venv/bin/python` are absent; focused validation used `python3` with masked/dummy required env values. Global gate script is hard-coded to `venv/bin/python` and failed for that environment reason.

## Git state before implementation
- Branch: `work`.
- Initial status showed no tracked changes in short status output.
- Current implementation status captured by final validation and `git status` before commit.

## Relevant migrations / constraints
- `migrations/059_create_knowledge_entries_and_retrieval_surface.sql`: creates `knowledge_entries`, `knowledge_entry_source_refs`, `knowledge_retrieval_surface`; status CHECK lacked `merged`; runtime surface constrained to `status='published'` and `visibility='runtime'`.
- `migrations/061_allow_multiple_source_ref_quotes_per_chunk.sql`: adds `quote_hash` and widens source-ref primary key.
- `migrations/062_kcd_stage_h_knowledge_edit_actions.sql`: creates `knowledge_edit_actions` with RAG-eval-oriented source columns and action CHECK limited to attach/create/rebuild/rerun; creates `knowledge_entry_versions`.
- `migrations/063_rag_eval_review_console.sql` and `064_rag_eval_review_groups.sql`: retrieval review console/review grouping layer.

## Route/frontend files inspected
- Backend route assembly: `src/interfaces/http/app.py`.
- Existing knowledge routes/access pattern: `src/interfaces/http/knowledge.py`, `src/application/services/knowledge_service.py`, `src/application/services/project_service.py`.
- Existing RAG Eval routes/service: `src/interfaces/http/rag_eval.py`, `src/application/rag_eval/review_service.py`, `src/application/rag_eval/failure_classification.py`.
- Existing repository source of truth: `src/infrastructure/db/repositories/knowledge_repository.py`.
- Existing UI: `frontend/src/pages/rag-eval/RagEvalPage.tsx`.
- Existing API modules: `frontend/src/shared/api/modules/knowledge.ts`, `frontend/src/shared/api/modules/ragEval.ts`, `frontend/src/shared/api/modules/index.ts`.

## Tests to update/add
- Added focused domain/service tests in `tests/test_knowledge_curation_domain.py` for normalization/dedupe, issue classification, duplicate grouping, and merge-preview blocking validation.

## DB strategy chosen
- Extended `knowledge_edit_actions` in-place with source-neutral fields: `source_kind`, `source_id`, `idempotency_key`, `target_entry_ids_json`; kept legacy RAG-eval columns and unique index compatible.
- Added `merged` status to `knowledge_entries` because CHECK constraint is text-based and safely extendable without enum type migration.
- Runtime exclusion remains physical-row removal from `knowledge_retrieval_surface`, not physical deletion of canonical `knowledge_entries`.

## Risks / rollback plan
- Risk: repository curation write paths need integration DB tests against real Postgres/pgvector to validate all SQL branches.
- Risk: embedding provider unavailability can produce partial merge/status outcomes; code removes absorbed entries from retrieval before attempting rebuild.
- Rollback: revert migration 065 by removing added columns/indexes/constraints and restoring previous CHECK vocabularies, then revert route/service/frontend files.
