# RAG Eval Review Console + Fragment-local Streaming Recon

## Scope

Read-only architecture recon of the current `Add RAG eval review console` commit on this workspace branch. The goal is to identify what is already present, what violates layering, and how to refactor toward a production-safe Review Console and fragment-local streaming execution.

## Current Review Console map

### DB

- `migrations/063_rag_eval_review_console.sql` creates:
  - `rag_eval_question_reviews` with statuses `candidate`, `accepted`, `rejected`, `edited`, `applied`.
  - `rag_eval_report_snapshots` with `summary_json` and `problem_map_json`.
- `rag_eval_question_reviews` is used by the repository methods.
- `rag_eval_report_snapshots` is only created; no current code writes or reads it.
- No `rag_eval_review_groups` projection table exists, so partial fragment-card readiness is not persisted independently of result rows.

### Backend repository

`src/infrastructure/db/repositories/rag_eval_repository.py` currently contains three kinds of responsibility:

1. Persistence:
   - load latest run summary;
   - load run results;
   - load document entries;
   - load/upsert/edit question reviews;
   - load accepted reviews;
   - mark reviews applied.
2. Product read-side assembly:
   - `get_run_review` / `get_latest_review` load entries/results/reviews and call `_build_review_payload`.
   - `_build_review_payload` groups results into fragment review groups.
3. UI/presenter logic:
   - Russian user-facing labels and human summaries are in infrastructure helpers (`_review_status_label`, `_readiness_label`, `_human_action_summary`, `_human_summary`, `_why_question_matters`).

This is the largest layer leak: infrastructure has product/presenter language and review policy.

### HTTP API

`src/interfaces/http/rag_eval.py` includes the requested endpoints:

- `GET /api/rag-eval/runs/{run_id}/review`
- `GET /api/rag-eval/documents/{document_id}/latest-review`
- `POST /api/rag-eval/questions/{question_id}/review`
- `PATCH /api/rag-eval/questions/{question_id}`
- `POST /api/rag-eval/runs/{run_id}/apply-accepted`

Access checks are present. However, `apply_accepted_rag_eval_questions` directly loops accepted reviews, creates knowledge edit actions, attaches questions to entries, rebuilds embeddings, marks actions applied, marks reviews applied, and queues rerun. That orchestration belongs in application service or a queue handler, not the HTTP layer.

### Frontend

`frontend/src/pages/rag-eval/RagEvalPage.tsx` now has a product surface with:

- overview card;
- problem map;
- filters/sorts;
- fragment cards;
- drawer;
- apply accepted panel;
- diagnostics disclosure.

Main gaps:

- The file is now very large; components may need extraction later.
- It still keeps legacy result/report panels below the new Review Console, which may be useful temporarily but risks visual confusion.
- It cannot show true partial fragment statuses unless backend emits/persists group status.
- Some labels are hardcoded in the component rather than i18n, though existing project has many i18n keys.

## Current execution pipeline map

`RagEvalService.generate_dataset_and_run_streaming_retrieval` is already a streaming retrieval-only path:

1. Load all entries.
2. Create dataset/run.
3. Create `entry_queue` and `question_queue`.
4. Generation workers consume entries and call `dataset_generator.generate_dataset(..., chunks=[entry])`.
5. Generated questions are saved by saving the whole dataset repeatedly.
6. Questions are put into global `question_queue` one-by-one.
7. Retrieval workers consume individual questions and save results immediately.
8. Progress emits aggregate counters.

Existing tests already assert retrieval for entry A can start before entry B generation completes. That is good, but the model is still question-centric after generation and does not produce/persist fragment review group statuses.

## Architecture violations / layer leaks

1. Infrastructure repository contains product presenter logic:
   - Russian labels;
   - readiness labels;
   - human summaries;
   - proposed improvement phrasing;
   - review grouping payload shape.
2. HTTP route contains apply orchestration:
   - direct loop over accepted reviews;
   - direct calls to `KnowledgeRepository.attach_question_to_entry` and `rebuild_entry_embedding`;
   - rerun queueing in route.
3. Review service/application layer is missing.
4. Review schemas/contracts are implicit `JsonObject` dictionaries, not explicit application contracts.
5. `rag_eval_report_snapshots` table is not written, so it is dead schema unless implemented or deferred.
6. No persisted review group projection, so fragment status values (`queued`, `generating_questions`, `checking_retrieval`, `ready_for_review`, `failed`) cannot be reliably shown during a running job.
7. Current streaming progress remains aggregate-first and has legacy/batch fields in queue handler.
8. `save_dataset(dataset=dataset)` during streaming rewrites the whole growing question list repeatedly; acceptable at 387 questions but not ideal.

## Target architecture plan

### Application layer

Add:

- `src/application/rag_eval/review_schemas.py`
- `src/application/rag_eval/review_service.py`

Responsibilities:

- Convert persisted entries/questions/results/reviews into product review payload.
- Own human labels/readiness/problem summaries.
- Own lifecycle semantics.
- Own apply accepted orchestration, using ports for knowledge edit actions and queue.
- Keep retrieval_eval non-mutating until explicit apply.

### Infrastructure repository

Keep only SQL/persistence:

- `get_run_summary`
- `get_latest_run_summary`
- `load_run_results`
- `load_document_entries`
- `load_question_reviews`
- `upsert_question_review`
- `edit_question_review`
- `load_accepted_question_reviews`
- `mark_question_reviews_applied`
- optional `upsert_review_group_projection`, `load_review_group_projections`

Remove Russian labels and `_build_review_payload` from repository.

### HTTP layer

Thin route responsibilities:

- resolve document/run/question;
- access checks;
- instantiate repository/service adapters;
- call application service;
- return DTO.

No attach/rebuild loops in the route.

## DB migration plan

1. Keep `rag_eval_question_reviews`; it is the minimum correct lifecycle table.
2. Decide on `rag_eval_report_snapshots`:
   - If no code writes it in this task, either remove/defer it or add application-service snapshot writing.
   - Prefer keeping only if a follow-up writes snapshots.
3. Add `rag_eval_review_groups` if implementing live fragment cards now:
   - `id`, `run_id`, `dataset_id`, `project_id`, `document_id`, `source_chunk_id`, `status`, counters, `review_payload_json`, `error`, timestamps.
   - This is justified by the product requirement that cards become ready before full document completion.

## API plan

Keep external contract names stable:

- `GET /runs/{run_id}/review`
- `GET /documents/{document_id}/latest-review`
- `POST /questions/{question_id}/review`
- `PATCH /questions/{question_id}`
- `POST /runs/{run_id}/apply-accepted`

Potential behavior refinement:

- `apply-accepted` should enqueue a task and return job id if queue task scope is feasible.
- If not, it must call an application service with strict bounds and return per-review failures, but the route remains thin.

## Frontend plan

1. Keep Review Console as primary surface.
2. Hide legacy report/result details behind diagnostics or move below a clear “Legacy diagnostics” disclosure.
3. Add/display group status values: `queued`, `generating_questions`, `checking_retrieval`, `ready_for_review`, `failed`.
4. Remove user-facing nulls; empty states should say “Проверка ещё не запускалась” / “Фрагменты появятся во время проверки”.
5. Optionally extract Review Console components from `RagEvalPage.tsx` if the file remains too large.

## Fragment-local streaming plan

Near-term minimal change:

- Replace global question queue as the core model with an entry-scoped `process_entry(entry)` coroutine.
- Each `process_entry`:
  1. marks group `generating_questions`;
  2. generates questions for one entry;
  3. saves questions immediately as candidates / dataset questions;
  4. marks group `checking_retrieval`;
  5. runs retrieval fan-out for that entry’s questions with per-entry and global semaphores;
  6. saves each result immediately;
  7. builds/saves review group projection as `ready_for_review`;
  8. emits progress with fragment-ready counters.

Concurrency:

- `generation_concurrency`: env `RAG_EVAL_GENERATION_CONCURRENCY`, fallback existing `RAG_EVAL_DATASET_CONCURRENCY`, default 3.
- `entry_retrieval_concurrency`: env `RAG_EVAL_ENTRY_RETRIEVAL_CONCURRENCY`, default 8.
- `global_retrieval_concurrency`: env `RAG_EVAL_GLOBAL_RETRIEVAL_CONCURRENCY`, fallback existing `RAG_EVAL_RETRIEVAL_CONCURRENCY`, default 16/24 depending infra limits.

## Tests plan

Backend/application:

1. Review builder groups by source chunk / expected entry.
2. Review builder emits summary/problem map/human labels.
3. Accept/reject/edit lifecycle persists states.
4. Apply accepted ignores candidate/rejected reviews.
5. Apply accepted is idempotent and uses knowledge_edit_actions.
6. Latest review works without report snapshot.
7. Generated eval questions are never auto-applied during eval.
8. Retrieval eval does not call answerer/judge (existing tests cover this).
9. Entry A retrieval starts before Entry B generation completes (existing tests cover this but should be updated for process_entry model).
10. Per-entry and global retrieval semaphores are respected.
11. Group projection is ready before full document completes.
12. Progress includes fragment-local counters.

Architecture:

- Repository contains no Russian product labels / presenter logic.
- HTTP apply endpoint does not call `attach_question_to_entry` / `rebuild_entry_embedding` directly.
- Application boundary imports remain clean.

Frontend:

- Render overview.
- Render grouped fragment questions.
- Drawer opens details.
- Accept/reject/edit call API.
- Apply disabled when no accepted questions.
- Diagnostics hidden by default.

## Risks

- Full fragment-local streaming plus projection is a larger change than just cleaning Review Console layering.
- Adding an apply queue task requires queue job type registration and operational progress UI if not already generic.
- Current tests in this container may be blocked by missing pytest plugins/env; local WSL venv should be used (`venv/bin/python`).
- Migration 063 has already been introduced in the previous commit; changing it after deployment would require care. If not deployed, adjust in place; if deployed, add migration 064.
- Rewriting streaming from question_queue to process_entry can regress pause/cancel if not checked in both generation and retrieval fan-out.

## Proposed commit breakdown

1. Add this recon report.
2. Move review schemas/builder/service into application layer and make repository persistence-only.
3. Move apply accepted orchestration into application service; optionally enqueue task.
4. Add review group projection migration and repository methods.
5. Refactor streaming to entry-scoped process_entry with fragment-local progress.
6. Update frontend to consume group statuses/projection and clean legacy diagnostics.
7. Add focused backend/architecture/frontend tests.
8. Run quality gates and fix regressions.
