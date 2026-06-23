# CapacityWindow Admission Current Audit

## 1. Baseline

| Symbol/file | Current behavior | Owner | Risk | Patch recommendation |
|---|---|---|---|---|
| `docs/architecture/current_workflow_frontend_capacity_cutover_checkpoint.md` | Current source of truth after `next_attempt_at` / `DEFERRED` removal. WorkItem is passive; `RETRYABLE_FAILED` is immediately eligible; CapacityWindow owns provider/account/model timing. | Architecture checkpoint | Older docs/tests can reintroduce WorkItem timing language. | Keep this audit aligned with the checkpoint and treat older docs as historical when they conflict. |
| WorkItem lifecycle | `READY` and `RETRYABLE_FAILED` are due states; `RETRYABLE_FAILED` is prioritized before `READY` and does not sleep. | Execution Runtime | Provider reset can be accidentally modeled as WorkItem retry. | Guard Execution Runtime against `capacity_retry_at`, `reset_at`, `minute_reset_at`, and `daily_reset_at`. |

## 2. Current capacity_retry_at ownership map

| Symbol/file | Current behavior | Owner | Risk | Patch recommendation |
|---|---|---|---|---|
| `PrepareLlmDispatchBatchResult.capacity_retry_at` in `src/interfaces/composition/prepare_llm_dispatch_batch.py` | Scalar returned only when admission should wake later. Derived from latest capacity observations or local active model minute window. | Composition / capacity orchestration | Looks like a retry timer unless bounded by architecture contract. | Keep as temporary workflow wakeup scalar only; do not store on WorkItem. |
| `_next_capacity_retry_at` / `_local_active_model_capacity_retry_at` | Calculates future retry candidate from minute/daily reset observations. | Composition; source data from LLM capacity observations | `reset_at` may be confused with hard unavailable or item retry. | Next patch should move this behind explicit CapacityWindow state/wakeup decision. |
| Prepare command handlers | Reschedule the existing workflow command with `run_after=capacity_retry_at` when scheduled work remains but no item was admitted. | Workflow Runtime command log | Workflow wakeup shortcut can become de facto admission state. | Keep `run_after` semantics workflow-command scoped until durable CapacityWindow admission owns it. |

`capacity_retry_at` is currently allowed only as workflow wakeup scalar. It must not be interpreted as WorkItem retry timer.

## 3. Current admission path

| Symbol/file | Current behavior | Owner | Risk | Patch recommendation |
|---|---|---|---|---|
| `PostgresWorkItemLeaseRepository.peek_due_work_items` | Reads `ready` and `retryable_failed` work items, ordered retryable first, then `updated_at` / `work_item_id`. | Execution Runtime persistence | The `requested_items` limit can hide smaller later candidates if earlier large items do not fit. | Durable admission should define candidate scan/window behavior explicitly. |
| `PrepareLlmDispatchBatch.execute` | Peeks due records, builds per-batch LLM profile, reads observations/reservations, subtracts active reservations, leases admitted records, starts attempts, records reservations. | Composition boundary | This is orchestration plus partial capacity admission, not first-class durable CapacityWindow runtime. | Keep as current path; next patch should extract durable admission state/decision without changing UI. |
| `_input_admitted_candidates` | Splits pending records into `RETRYABLE_FAILED` and `READY` lanes, tries retry lane first, then fresh lane, and calls `_pop_first_record_that_fits`. | Composition capacity admission helper | Token-fit behavior is local/in-memory and not guarded as durable policy. | Add a focused executable guard before depending on it as durable admission behavior. |
| `LeaseLlmAdmittedWorkItems` / `LeaseAdmittedWorkItems` | Older generic admission path is count-based from `CapacityAdmissionPolicy` and leases due items in repository order. | Interfaces composition + Execution Runtime use case | Not a per-WorkItem token-fit selector. | Treat as supporting path, not the durable CapacityWindow token-fit algorithm. |

## 4. Current token estimate availability

| Symbol/file | Current behavior | Owner | Risk | Patch recommendation |
|---|---|---|---|---|
| `execution_work_item_schedules.payload.llm_capacity_estimate` | Required by input-token admission helpers; includes `estimated_input_tokens` and `reserved_output_tokens`. | Work scheduling / composition contract | Missing payload estimate raises at admission time. | Next patch should make estimate contract explicit and guarded at scheduling boundary. |
| `LlmTaskCapacityProfile` | Carries `estimated_prompt_tokens`, `estimated_completion_tokens`, and derived `estimated_total_tokens`. | LLM Runtime capacity domain | Batch-level max estimate can obscure per-item fit requirements. | Keep profile for preflight, but durable admission should select by per-item estimate. |
| `capacity_window_leased_work_item_event` | Supports optional `token_estimate` and `reserved_tokens`; current claim-builder wrapper does not pass them. | Knowledge Workbench capacity events | Frontend projection may lack token-fit audit details. | Add optional token/reservation fields only in event/contract slice, not UI. |

## 5. Current capacity event/projection coverage

| Symbol/file | Current behavior | Owner | Risk | Patch recommendation |
|---|---|---|---|---|
| `capacity_window_workflow_events.py` | Defines exhausted, scheduled wakeup, and leased work item event factories; exhaustion is derived from capacity observations. | Knowledge Workbench workflow saga | Events describe boundary but do not persist durable window state by themselves. | Keep event boundary; next patch should connect durable admission decisions to these events. |
| `capacity_window_frontend_workflow_event_projector.py` | Projects exhausted, scheduled wakeup, and leased work item overlays; rejects `next_attempt_at`, `retry_owner`, and `work_item_retry_timer`. | Observability / frontend projection | Contract can regress and leak item retry timing into capacity overlay. | Architecture guard should require these forbidden-field markers. |
| `workflow_capacity_window_observed` | Checkpoint lists observed coverage, but the fetched projector mapping currently covers exhausted/scheduled_wakeup/leased. | Architecture / observability | Observed coverage may be event-only or handled outside this projector. | Audit observed coverage before claiming complete projection parity. |

## 6. Current wakeup/run_after behavior

| Symbol/file | Current behavior | Owner | Risk | Patch recommendation |
|---|---|---|---|---|
| Claim builder prepare handler | If zero dispatches and capacity retry is future, appends exhaustion event when available and reschedules the pending prepare command with `run_after`. | Knowledge Workbench saga + Workflow Runtime | Wakeup scalar may be mistaken for WorkItem retry scheduling. | Leave as workflow wakeup only until durable CapacityWindow admission replaces it. |
| Draft claim compaction prepare handler | If zero dispatches and `capacity_retry_at` exists, reschedules the pending prepare command with `run_after`. | Knowledge Workbench saga + Workflow Runtime | Same scalar shortcut, with less capacity event coverage than claim-builder path. | Include compaction in next durable wakeup audit. |

## 7. Gaps before durable CapacityWindow admission

| Symbol/file | Current behavior | Owner | Risk | Patch recommendation |
|---|---|---|---|---|
| Durable CapacityWindow state | No first-class durable CapacityWindow state/table was confirmed in this audit; checkpoint says it is not fully proven. | Capacity Runtime target | Latest observations + reservations + command `run_after` are not a durable admission source of truth. | Decide on durable state or formally prove existing observation/reservation state is sufficient. |
| Token-fit selection guard | Current helper can skip a non-fitting record within fetched due records, but no dedicated guard was found for “large item does not block smaller item”. | Composition tests | Future refactor can silently return to first-item blocking behavior. | Add explicit token-fit selection test before relying on it as target policy. |
| Candidate scan breadth | `peek_due_work_items(... LIMIT requested_items)` may not fetch smaller eligible records beyond the initial window. | Execution Runtime query / composition admission | A large early record can still block smaller later work if not fetched. | Define scan limit/window and locking strategy in durable admission patch. |
| `capacity_retry_at` scalar | Still present as workflow wakeup shortcut. | Composition / workflow command log | Shortcut can become implicit CapacityWindow state. | Replace or wrap it with explicit CapacityWindow wakeup decision. |
| `TERMINAL_FAILED` | Checkpoint requires read-only audit; this patch does not change it. | Execution Runtime / Workbench producers | It may still be overused for retriable/provider/capacity outcomes. | Keep separate `TERMINAL_FAILED` audit patch. |

## 8. Next patch recommendation

| Symbol/file | Current behavior | Owner | Risk | Patch recommendation |
|---|---|---|---|---|
| Patch B | Build the durable CapacityWindow admission slice without deleting legacy queue or touching React UI. | Capacity Runtime + composition | Too broad a patch could mix UI, legacy queue deletion, and admission semantics. | Add focused domain/application contract for provider/account/model window state, one token-fit selection guard, and workflow wakeup ownership cleanup. |
