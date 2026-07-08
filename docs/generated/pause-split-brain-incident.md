# Incident: Pause State Split-Brain

## Symptom

User clicks pause. Before refresh frontend optimistically shows stopped timer and Continue button. After refresh frontend shows running timer and Pause button again, while backend legacy row says PAUSED.

The pause button/action is not legacy. The optimistic frontend pause response is current UX behavior. The legacy part is backend storage/hydration dependency on `knowledge_extraction_workflow_runs.status/current_phase`.

## Pause Classification

User pause intent:
- CURRENT_USER_INTENT
- triggered by current frontend action/button
- must be preserved across refresh

Frontend optimistic pause state:
- CURRENT_UX_BEHAVIOR
- valid temporary UI response to user action
- non-authoritative until hydrated from backend runtime-native state

`knowledge_extraction_workflow_runs.status=PAUSED`:
- LEGACY_SPLIT_BRAIN_STORAGE
- stores pause intent in old saga/control-plane row
- must not become runtime authority

`workflow_runtime_timeline_entries.WorkflowManuallyPaused`:
- CURRENT_OR_TRANSITIONAL_AUDIT_EVENT
- useful for timeline/timer/history
- not sufficient as execution gate

runtime-native pause gate/state:
- MISSING
- must be introduced before pause can be correct

## Evidence

Input:
- `project_id`: `c1dcb795-a353-4b4c-b00e-246787c4b53b`
- `source_document_ref`: `source-document:c1dcb795-a353-4b4c-b00e-246787c4b53b:004e377a009c6f3633e16876be91b76c96f48eb2b4fdbad654383d23e8b8ed2a`
- `workflow_run_id`: `knowledge-extraction:source-document:c1dcb795-a353-4b4c-b00e-246787c4b53b:004e377a009c6f3633e16876be91b76c96f48eb2b4fdbad654383d23e8b8ed2a`
- pause timestamp: `2026-07-06 10:40:55.978884+00`

Observed rows:
- `knowledge_extraction_workflow_runs`: `status=PAUSED`, `current_phase=SOURCE_UNITS_CREATED`, `pause_reason=manual_stop`, seen in `runtime-db-evidence-paused-at-compaction-2026-07-06.txt:13-14` and conclusion helper at `:2442-2444`.
- `knowledge_workbench_documents`: `status=processing`, conclusion helper at `runtime-db-evidence...txt:2451`.
- `workflow_runtime_progress_snapshots`: `workflow_status=RUNNING`, `current_phase=DRAFT_CLAIM_CLUSTERING`, counters include 42 total, 21 active, 21 done, shown at `runtime-db-evidence...txt:69-79` and `:2446-2447`.
- `frontend_workflow_events` after pause timestamp: `DraftClaimCompactionDispatchBatchPrepared`, shown at `runtime-db-evidence...txt:101`, `:603`, and payload at `:613`.
- `workflow_runtime_command_log` after pause timestamp: pending `ExecuteDraftClaimCompaction` commands, shown at `runtime-db-evidence...txt:623-645`.
- `workflow_runtime_timeline_entries`: `WorkflowManuallyPaused`, shown at `runtime-db-evidence...txt:2331`.
- pause/resume command search: no runtime pause/resume commands found in generated evidence section 14.

## Workflow Liveness Before Pause

The paused run is not evidence that the current workflow cannot progress.

The runtime was alive and progressing:
- claim builder completed 30 source units
- draft claims were persisted
- embeddings were generated
- compaction was scheduled and partially executed
- runtime progress showed `DRAFT_CLAIM_CLUSTERING` with active/completed work

Runtime DB evidence supports this:
- source unit count: 30
- draft claim observation count: 46
- embeddings generated with `sentence-transformers/all-MiniLM-L6-v2`
- compaction batches existed and runtime progress counters showed active/completed compaction work

Without the user pause, the workflow likely would have continued toward later compaction/curation/publication steps.

The incident proves split-brain pause semantics, not a dead workflow.

## Allowed Post-Pause Effects

- already-dispatched LLM attempts may finish
- output validation may run
- valid outputs may be persisted
- domain results may be applied
- frontend projection may show completed in-flight results

## Forbidden Post-Pause Effects

- new prepare dispatch batches
- new leases
- new dispatch attempts for not-yet-started work
- new `Execute*` commands
- reconcile scheduling the next wave

The bug is not "any event after pause".

The bug is new future scheduling after pause and failed hydration after refresh.

## Architectural Conclusion

Pause is currently written somewhere that does not control runtime command/execution flow. Specifically, pause writes legacy saga state and timeline/outbox events, but runtime command dispatch reads `workflow_runtime_command_log` pending due commands and execution runtime leases `execution_work_items` without consulting a runtime-native pause gate.

## Source-of-Truth Conclusion

Do not make legacy workflow row authoritative.

Do not sync legacy row to runtime.

Move pause semantics into current runtime authority.

## Suspect Code Paths

Write pause:
- `src/contexts/knowledge_workbench/application/sagas/pause_knowledge_extraction_workflow.py:103` sets `status=PAUSED`.
- `src/contexts/knowledge_workbench/application/sagas/pause_knowledge_extraction_workflow.py:110` appends outbox event.
- `src/contexts/knowledge_workbench/application/sagas/pause_knowledge_extraction_workflow.py:121` appends timeline entry.
- `src/contexts/knowledge_workbench/infrastructure/postgres/postgres_knowledge_extraction_saga_state_repository.py:100` persists legacy workflow row.

Read pause:
- `src/contexts/knowledge_workbench/application/sagas/resume_knowledge_extraction_workflow.py:89` loads legacy state.
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:192` hydrates UI status from legacy row.
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:783` reads timeline pause/resume events for timer math.

Dispatch commands:
- `src/contexts/workflow_runtime/infrastructure/postgres/postgres_command_log_repository.py:222` selects due pending commands.
- `src/contexts/workflow_runtime/infrastructure/postgres/postgres_due_knowledge_extraction_workflow_reader.py:36` discovers due workflows from pending commands.

Lease/dispatch work:
- `src/interfaces/composition/prepare_llm_dispatch_batch.py:310` peeks due work items.
- `src/interfaces/composition/prepare_llm_dispatch_batch.py:474` leases admitted work items.
- `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_lease_repository.py:104` leases due work item.

Append next commands:
- `src/contexts/knowledge_workbench/application/sagas/handle_reconcile_draft_claim_compaction_progress_command.py:293` creates next `PrepareDraftClaimCompactionDispatchBatch`.
- `src/contexts/knowledge_workbench/application/sagas/handle_prepare_draft_claim_compaction_dispatch_batch_command.py:315` validates pending prepare command and then updates progress as `RUNNING`.

Build frontend hydrated state after refresh:
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:182` document live-state query.
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:192` `wf.status AS workflow_status`.
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:193` `COALESCE(ps.current_phase, wf.current_phase)`.
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:879` timer mode from hydrated workflow status.
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:1089` pause/continue actions from hydrated workflow status.

## Target Behavior

Already-dispatched attempts may finish and be projected.

No new prepare/lease/execute wave may be created while paused.

Frontend after refresh must hydrate from runtime-native pause/projection state.
