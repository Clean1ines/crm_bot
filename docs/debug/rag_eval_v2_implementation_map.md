# Workbench RAG Eval V2 implementation map

Current checkpoint: qgen complete; retrieval complete; adjudication complete; promotion candidate approve/reject complete.

## Claim Builder canonical path

| Step | File | Current component | Notes for reuse |
| --- | --- | --- | --- |
| schedule | `src/contexts/knowledge_workbench/application/sagas/plan_claim_builder_section_work.py` | `PlanClaimBuilderSectionWork`, `CLAIM_BUILDER_SECTION_WORK_KIND` | Builds deterministic one work item per source unit. Schedule payload carries source context and `llm_capacity_estimate`. |
| persist scheduled work | `src/contexts/execution_runtime/application/use_cases/ensure_work_items_scheduled.py` and `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_scheduling_repository.py` | `EnsureWorkItemsScheduled` | Generic READY work item persistence with idempotency key. |
| prepare | `src/contexts/knowledge_workbench/application/sagas/handle_prepare_claim_builder_dispatch_batch_command.py` | `HandlePrepareClaimBuilderDispatchBatchCommandHandler` | Reads workflow command payload, calls generic `PrepareLlmDispatchBatch`, appends prepared-attempt execute commands and reconcile command. |
| admission/capacity/reservation | `src/interfaces/composition/prepare_llm_dispatch_batch.py` | `PrepareLlmDispatchBatch` | Peeks due items, resolves active model/fallback strategy, locks route, reads observations, subtracts reservations, leases admitted items, persists attempts and `llm_route_capacity_reservations`. |
| dispatch attempt persistence | `src/interfaces/composition/start_llm_admitted_work_item_attempts.py` | `StartLlmAdmittedWorkItemAttempts` | Copies admitted schedule payload + allocation into `execution_work_item_attempt_dispatches`. |
| execute | `src/contexts/knowledge_workbench/application/sagas/handle_execute_claim_builder_section_command.py` | `HandleExecuteClaimBuilderSectionCommandHandler` | Calls `ExecutePreparedLlmDispatchAttempt` with phase validator, records capacity observation, appends capacity wakeup and reconcile command. |
| generic dispatch | `src/interfaces/composition/execute_prepared_llm_dispatch_attempt.py` | `ExecutePreparedLlmDispatchAttempt` | The only place that invokes `LlmDispatchExecutorPort.execute_dispatch`. |
| observation | `src/contexts/capacity_runtime/infrastructure/postgres/postgres_llm_attempt_capacity_observation_repository.py` | `PostgresLlmAttemptCapacityObservationRepository` | Persists latest provider/account/model capacity windows. |
| wakeup | `src/contexts/knowledge_workbench/application/sagas/append_capacity_window_prepare_wakeup.py` | `append_capacity_window_prepare_wakeup` | Adds delayed prepare command scoped to observed account reset. |
| reconcile | `src/contexts/knowledge_workbench/application/sagas/handle_reconcile_claim_builder_progress_command.py` | `HandleReconcileClaimBuilderProgressCommandHandler` | Summarizes work item progress, decides now/later/drained/blocked, appends next prepare command or drained event. |
| frontend projection | `src/contexts/knowledge_workbench/observability/application/projectors/*claim_builder*` | Claim Builder projectors | Project workflow events into `frontend_workflow_events`. |

## Extension points

| Extension point | Existing file | RAG Eval V2 use |
| --- | --- | --- |
| `WorkKind` | `src/contexts/execution_runtime/domain/value_objects/work_kind.py` | Add question-generation and adjudication work kinds. |
| work planning | `plan_claim_builder_section_work.py` | RAG Eval planners exist: one qgen work item per published runtime entry, one adjudication work item per eligible retrieval outcome. |
| schedule payload | `execution_work_item_schedules.schedule_payload` | Store run id, project id, runtime entry id, fact id, evidence fields, provider messages, prompt version, capacity estimate, holdout flag. |
| preparation profile builder | `ClaimBuilderDispatchPreparationBuilder` in `claim_builder_dispatch_preparation.py` | Generalize `PrepareLlmDispatchBatch` behind fail-fast registry and add RAG Eval qgen/adjudication builders. |
| prepare handler | `handle_prepare_claim_builder_dispatch_batch_command.py` | Add RAG Eval prepare handlers that call generic prepare with phase work kind and append execute/reconcile commands. |
| execution validator | `ClaimBuilderLlmDispatchOutputValidator` | Qgen validator requires exactly 10 questions; adjudication validator requires strict JSON verdict contract. |
| outcome persistence | `draft_claim_observation_persistence` | Generated questions, retrieval outcomes, adjudication results and promotion candidates persist through the RAG Eval repository. |
| progress reconcile | `handle_reconcile_claim_builder_progress_command.py` | Phase-specific qgen and adjudication reconcile support now/later/wait/drained/blocked transitions. |
| frontend projection | `ProjectFrontendWorkflowEvent` | Add RAG Eval event projectors and include status/progression in RAG Eval API responses. |
| dispatch transports | `src/interfaces/composition/llm_dispatch_executor.py` | `make_llm_dispatch_executor()` builds one `GroqHttpTransport` per configured Groq env account and passes `transports_by_account_ref` to `GroqDispatchExecutor`. |

## Claim Builder component to RAG Eval counterpart

| Claim Builder | RAG Eval V2 counterpart |
| --- | --- |
| `CLAIM_BUILDER_SECTION_WORK_KIND` | `WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND`, `WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND` |
| `PlanClaimBuilderSectionWork` | `PlanWorkbenchRagEvalQuestionGenerationWork`, `PlanWorkbenchRagEvalAdjudicationWork` |
| `ClaimBuilderDispatchPreparationBuilder` | `WorkbenchRagEvalQuestionGenerationDispatchPreparationBuilder`, `WorkbenchRagEvalAdjudicationDispatchPreparationBuilder` |
| `HandlePrepareClaimBuilderDispatchBatchCommandHandler` | `HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommandHandler`, `HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchCommandHandler` |
| `ClaimBuilderLlmDispatchOutputValidator` | `WorkbenchRagEvalQuestionGenerationOutputValidator`, `WorkbenchRagEvalAdjudicationOutputValidator` |
| `HandleExecuteClaimBuilderSectionCommandHandler` | `HandleExecuteWorkbenchRagEvalQuestionGenerationCommandHandler`, `HandleExecuteWorkbenchRagEvalAdjudicationCommandHandler` |
| `HandleReconcileClaimBuilderProgressCommandHandler` | `HandleReconcileWorkbenchRagEvalQuestionGenerationCommandHandler`, `HandleReconcileWorkbenchRagEvalAdjudicationCommandHandler` |
| `ClaimBuilder*FrontendWorkflowEventProjector` | `WorkbenchRagEval*FrontendWorkflowEventProjector` |

## Migrations

Existing required tables:

- `083_create_execution_runtime_tables.sql`
- `095_create_execution_work_item_schedules.sql`
- `096_create_execution_attempt_llm_output_payload.sql`
- `097_add_execution_work_item_retry_plan.sql`
- `110_create_workbench_rag_eval.sql`
- `111_add_workbench_rag_eval_question_route_metadata.sql`
- `113_add_execution_attempt_validation_metadata.sql`
- `114_add_execution_attempt_llm_output_payload.sql`
- `115_create_llm_route_capacity_reservations.sql`
- `116_create_frontend_workflow_events.sql`

Needed for V2:

Implemented in the retrieval continuation:

- `123_add_workbench_rag_eval_retrieval_progress.sql` adds persisted retrieval totals and classification counters.
- `handle_run_workbench_rag_eval_retrieval_evaluation_command.py` uses `SearchPublishedWorkbenchRuntime`, materializes BASELINE questions, persists top-k rows/outcomes and schedules adjudication.
- `workbench_rag_eval_workflow_runtime.py` composes the production retrieval search boundary and dispatches `RUN_RETRIEVAL_EVALUATION`.

Implemented in the adjudication continuation:

- `125_create_workbench_rag_eval_question_adjudications.sql` adds canonical adjudication persistence with model/account/slot/attempt metadata and `(run_id, question_id, outcome_id)` uniqueness.
- `126_add_workbench_rag_eval_adjudication_progress.sql` adds persisted adjudication counters and promotion candidate count.
- `handle_schedule_workbench_rag_eval_adjudication_work_command.py` creates stable eligible adjudication work items or zero-eligible PROMOTION_REVIEW.
- `handle_prepare_workbench_rag_eval_adjudication_dispatch_batch.py` calls generic `PrepareLlmDispatchBatch`.
- `handle_execute_workbench_rag_eval_adjudication.py` and `_command.py` call `ExecutePreparedLlmDispatchAttempt`, validate strict output, persist adjudication and capacity observation, and append reconcile.
- `handle_reconcile_workbench_rag_eval_adjudication_progress_command.py` drains to PROMOTION_REVIEW only after persisted adjudication coverage, or blocks on terminal failures.

Still needed after the adjudication checkpoint:

- add reversible embedding revision table with previous aliases/text/vector and verification status;
- add holdout/cycle marker so holdout questions are never promoted in the same cycle.

## Handlers

Implemented:

- start/scope handler: create run, resolve published entries, schedule qgen work, append prepare command;
- prepare qgen handler;
- execute qgen handler;
- reconcile qgen handler;
- retrieval evaluation handler;
- plan/prepare/execute/reconcile adjudication handlers;
- promotion candidate grouping after adjudication drain.

Still needed:

- explicit promotion candidate approve/reject handlers are implemented;
- all existing single and batch application paths require APPROVED and reject
  direct CANDIDATE application;
- embedding revision application handler;
- post-promotion verification handler;
- rollback handler for failed verification;
- terminal failure guard that prevents successful run completion when any terminal work item exists.

## Composition changes

- `PrepareLlmDispatchBatch` must accept a fail-fast work-kind builder registry and default Claim Builder to existing behavior.
- RAG Eval composition must not construct `RunWorkbenchRagEval` for the start endpoint.
- RAG Eval composition must wire workflow runtime UoW, execution scheduling repo, generic prepare, generic execute, capacity observation repo, frontend projection writer, and the existing multi-account Groq dispatch executor.
- Composition must pass all configured Groq account refs from `LlmRuntimeSettings.to_groq_env_config().accounts`; tests must assert four distinct refs when four env accounts are configured.

## API and frontend changes

- `POST /knowledge/projects/{project_id}/workbench/rag-eval/run` returns HTTP 202 with running workflow/run projection.
- Existing latest/get endpoints return V2 progression fields.
- Frontend progression UI remains partial; full rendering for adjudication, promotion review, verification and accept/rollback is still future scope.
- `frontend/src/shared/api/modules/ragEval.ts` must model 202/running and V2 status payloads.

## Test matrix

- start endpoint returns 202 and schedules workflow;
- N published runtime entries create N qgen work items;
- four distinct Groq account refs receive admitted dispatches;
- insufficient TPM reschedules prepare until reset;
- one generation attempt returns exactly 10 validated questions;
- primary `qwen/qwen3-32b`, fallback `openai/gpt-oss-120b`;
- retrieval outcomes persist rank/score/competitor/margin/classification;
- only adjudicated `VALID_TARGET_QUERY` questions with `promotion_recommended=true` become candidates;
- holdout never promoted in same cycle;
- zero eligible adjudication enters PROMOTION_REVIEW with zero candidates;
- terminal adjudication failure blocks the phase without creating candidates;
- one embedding recalculation per affected runtime entry;
- failed verification restores previous aliases/text/vector;
- terminal work-item failure prevents successful run completion;
- frontend renders full progression.

## Four distinct Groq transports proof

`src/interfaces/composition/llm_dispatch_executor.py` builds:

- `groq_env_config = LlmRuntimeSettings.from_env_mapping(os.environ).to_groq_env_config()`;
- `transports_by_account_ref = {account.account_seed.account_ref: GroqHttpTransport(... account.api_key ...) for account in groq_env_config.accounts}`;
- `GroqDispatchExecutor(..., transports_by_account_ref=transports_by_account_ref, ...)`.

The production composition proof configures four distinct Groq accounts and
asserts four distinct transports, real RAG Eval admission across multiple
accounts, persisted dispatch account refs, per-account/model capacity
observations and reservation safety on repeated preparation. The test does not
require round-robin and does not change selection policy.

## Implementation order

1. Checkpoint A: generic phase preparation builder abstraction and fail-fast registry; preserve Claim Builder behavior and tests.
2. Checkpoint B: qgen work kind, planner, prompt/payload builder, prepare handler, execute handler, strict 10-question validator, qgen persistence, qgen reconcile.
3. Checkpoint C: retrieval outcome model/schema, retrieval evaluation handler, adjudication work kind/planner/prepare/execute/reconcile, promotion candidate filtering after `VALID_TARGET_QUERY`. Completed.
4. Checkpoint D1: explicit promotion review approve/reject. Completed.
5. Checkpoint D2: group approved candidates by runtime entry, reversible embedding revisions, post-promotion verification and accept/rollback.
6. Checkpoint E: full frontend progression UI and final backend/frontend regression gates.
