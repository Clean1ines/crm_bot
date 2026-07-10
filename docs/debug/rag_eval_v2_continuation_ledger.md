# RAG Eval V2 continuation ledger

## Current status

ЗАДАЧА НЕ ЗАВЕРШЕНА.

Implemented in this pass:

- Created `docs/debug/rag_eval_v2_implementation_map.md` with Claim Builder path map, extension points, migrations, handlers, composition/API/frontend changes, test matrix, four-Groq-transport proof, and implementation order.
- Checkpoint A partial/green:
  - `PrepareLlmDispatchBatch` now uses `DispatchPreparationBuilderRegistry`.
  - Claim Builder remains default builder.
  - Work-kind-specific builders can be registered without changing the generic admission/reservation/dispatch path.
  - Focused prepare suite: `33 passed`.
- Checkpoint B partial/green:
  - Removed direct LLM dispatch from `WorkbenchRagEvalQuestionGenerator`.
  - Question generator now builds provider messages and strictly parses exactly 10 generated questions.
  - Added RAG Eval V2 work kinds:
    - `workbench_rag_eval.question_generation`
    - `workbench_rag_eval.adjudication`
  - Added qgen work planner: one published runtime entry maps to one `WorkItemSchedulePlan`.
  - Added qgen dispatch preparation builder using due item `llm_capacity_estimate` and `estimated_requests=1`.
  - Added `StartWorkbenchRagEvalV2`: creates running run and schedules N qgen work items for N published runtime entries.
  - HTTP start endpoint now returns 202 and no longer depends on `LlmDispatchExecutorPort`.
  - Legacy `allow_degraded_llama_instant` is rejected for V2.
  - Added qgen execute handler that calls generic `ExecutePreparedLlmDispatchAttempt`, validates exactly 10 questions, and persists generated questions.
  - Removed production composition factory `make_run_workbench_rag_eval`; `make_start_workbench_rag_eval_v2` is now the start composition.
  - Retired legacy sync batch executor; it no longer contains direct LLM dispatch, semaphore, or gather.
  - Updated architecture guard to forbid direct LLM execution in `src/contexts/knowledge_workbench/rag_eval`.

Validation evidence already run:

- `bash dev_scripts/ensure_test_env.sh && python -m pytest tests/interfaces/composition/test_prepare_llm_dispatch_batch.py -q`
  - `33 passed`
- `bash dev_scripts/ensure_test_env.sh && python -m pytest tests/contexts/knowledge_workbench/rag_eval/application/workflows/test_execute_workbench_rag_eval_question_generation.py tests/contexts/knowledge_workbench/rag_eval/application/use_cases/test_start_workbench_rag_eval_v2.py tests/contexts/knowledge_workbench/rag_eval/application/workflows/test_workbench_rag_eval_question_generation_workflow.py tests/contexts/knowledge_workbench/rag_eval/infrastructure/llm/test_workbench_rag_eval_question_generator.py -q`
  - `8 passed`
- `bash dev_scripts/ensure_test_env.sh && python -m pytest tests/interfaces/http/test_workbench_rag_eval.py -q`
  - `10 passed`
- `bash dev_scripts/ensure_test_env.sh && python -m pytest tests/architecture/test_workbench_rag_eval_boundary.py -q`
  - `6 passed`
- `bash dev_scripts/ensure_test_env.sh && python -m pytest tests/contexts/knowledge_workbench/rag_eval tests/interfaces/composition/test_workbench_rag_eval_composition.py tests/interfaces/http/test_workbench_rag_eval.py tests/architecture/test_workbench_rag_eval_boundary.py -q`
  - `48 passed`
- `bash dev_scripts/ensure_test_env.sh && python -m ruff check src/contexts/knowledge_workbench/rag_eval src/interfaces/composition/workbench_rag_eval.py src/interfaces/composition/prepare_llm_dispatch_batch.py tests/contexts/knowledge_workbench/rag_eval tests/interfaces/http/test_workbench_rag_eval.py tests/interfaces/composition/test_prepare_llm_dispatch_batch.py`
  - `All checks passed`

## Completed acceptance criteria

- Start endpoint no longer invokes old sync `RunWorkbenchRagEval`.
- Start endpoint returns `202` with running run projection.
- N entries create N question-generation schedule plans at use-case level.
- One runtime entry maps to one qgen work item and one qgen profile request estimate.
- Qgen prompt/parser enforces exactly 10 generated questions.
- Qgen execute handler uses `ExecutePreparedLlmDispatchAttempt`, not direct dispatch.
- Generated questions persist with generation model/account/slot metadata at handler unit level.
- RAG Eval application/infrastructure architecture guard forbids `LlmDispatchExecutorPort`, `execute_dispatch`, `GroqDispatchExecutor`, `asyncio.Semaphore`, and `asyncio.gather`.

## Not completed

- Full workflow command/event definitions and dispatch command drain for RAG Eval phases.
- Prepare qgen workflow command handler that appends execute/reconcile workflow commands.
- Capacity wakeup/reconcile loop for qgen now/later/drained/blocked.
- Real capacity observation write from RAG Eval qgen execute handler.
- Four-account integration test that admitted dispatches cover four distinct Groq account refs.
- Insufficient TPM reschedules prepare until reset.
- Automatic qwen primary to `openai/gpt-oss-120b` fallback proven end-to-end for RAG Eval work kind.
- Retrieval outcome V2 columns/model: competitor, margin, classification.
- Retrieval evaluation handler after qgen drained.
- Adjudication planner/prepare/execute/reconcile handlers.
- Promotion candidates only after `VALID_TARGET_QUERY`.
- Holdout exclusion.
- Grouped promotion application as part of workflow.
- Reversible embedding revisions table/model/repository.
- Post-promotion verification accept/rollback.
- Terminal work-item failure guard preventing successful run completion.
- Frontend full progression.
- Required final gates:
  - `python -m ruff format --check src tests`
  - `python -m ruff check src tests`
  - `python -m mypy src`
  - `python -m pytest -q`
  - `cd frontend && npm run lint && npm run type-check && npm run build && npm test -- --run`

## Next exact steps

1. Add RAG Eval workflow command/event enums only together with handlers:
   - schedule qgen
   - prepare qgen
   - execute qgen
   - reconcile qgen
   - run retrieval evaluation
   - schedule/prepare/execute/reconcile adjudication
   - apply promotions
   - verify/accept/rollback revisions
2. Wire `DispatchPreparationBuilderRegistry` in the worker composition with:
   - `WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND`
   - `WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND`
3. Implement qgen prepare handler by mirroring `handle_prepare_claim_builder_dispatch_batch_command.py`, but scoped to RAG Eval work kind and events.
4. Extend qgen execute handler to persist capacity observation and append capacity wakeup/reconcile commands.
5. Implement qgen reconcile now/later/drained/blocked and transition drained success to retrieval evaluation.
6. Add migrations for retrieval outcome/adjudication/revision data before implementing C/D persistence.
7. Build frontend progression only after backend read model fields exist.

## Continuation prompt

Continue the current RAG Eval V2 implementation from `docs/debug/rag_eval_v2_continuation_ledger.md`. Do not restart. The tree contains partial Checkpoint A and partial Checkpoint B. First inspect `git status --short`, then continue with qgen workflow prepare/reconcile handlers and registry wiring. Do not present the task as complete until all original DoD items are implemented and the required backend/frontend gates pass.
