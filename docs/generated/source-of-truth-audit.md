# Workbench Source-of-Truth Audit

Scope: read-only audit of current Workbench source of truth before pause/status fixes. Evidence comes from executable code, migrations, and DB evidence files in `docs/investigations/input/`.

Workflow selected: `.codex/workflows/audit.md`.

Skills applied: `search-first`, `iterative-retrieval`, `crm-bot-architecture-governance`, `architecture-decision-records`, `security-review`, `verification-loop`.

Agents selected but not spawned: `planner`, `architect`, `backend_mapper`, `frontend_mapper`, `database_reviewer`, `typescript_reviewer`, `python_reviewer`, `tdd_guide`, `security_reviewer`, `reviewer`. They were not spawned because this task explicitly prohibited new LLM/provider-token work.

## Executive Summary

The current execution authority is the workflow runtime plus execution runtime: `workflow_runtime_command_log`, `execution_work_items`, `execution_work_item_attempts`, and `execution_work_item_attempt_dispatches`.

The current frontend/hydration projection is split: `frontend_workflow_events`, `workflow_runtime_progress_snapshots`, `workflow_runtime_timeline_entries`, and `knowledge_workbench_documents` are read for UI, but `faq_workbench_workflow_live_state.py` still reads `knowledge_extraction_workflow_runs.status/current_phase` as hydrated workflow status/phase. This is an accidental legacy dependency and produced the pause split-brain.

The pause incident proves that `knowledge_extraction_workflow_runs.status=PAUSED` is not runtime authority. It does not prove that the current workflow is dead. The runtime was alive and progressing before the user pause: claim builder completed 30 source units, draft claims were persisted, embeddings were generated, compaction was scheduled and partially executed, and runtime progress showed `DRAFT_CLAIM_CLUSTERING` with active/completed work. Without the user pause, the workflow likely would have continued toward later compaction/curation/publication steps.

Important pause distinction:
- User pause intent: `CURRENT_USER_INTENT`; triggered by current frontend action/button; must be preserved across refresh.
- Frontend optimistic pause state: `CURRENT_UX_BEHAVIOR_NON_AUTHORITATIVE`; valid temporary UI response to user action until hydrated from backend runtime-native state.
- `knowledge_extraction_workflow_runs.status=PAUSED`: `LEGACY_SPLIT_BRAIN_STORAGE`; stores pause intent in old saga/control-plane row; must not become runtime authority.
- `workflow_runtime_timeline_entries.WorkflowManuallyPaused`: `CURRENT_PROJECTION_OR_AUDIT_EVENT`; useful for timeline/timer/history; not sufficient as execution gate.
- runtime-native pause gate/state: `MISSING_CURRENT_AUTHORITY`; must be introduced before pause can be correct.

The bug is not "any event after pause". The bug is new future scheduling after pause and failed hydration after refresh.

## knowledge_extraction_workflow_runs.status/current_phase/pause_reason/source_document_ref/workflow_run_id

Classification:
- LEGACY_SPLIT_BRAIN_STORAGE for `status/current_phase/pause_reason`
- ACCIDENTAL_LEGACY_DEPENDENCY for `workflow_run_id/source_document_ref` resolution

Evidence:
- Writers:
  - `src/contexts/knowledge_workbench/infrastructure/postgres/postgres_knowledge_extraction_saga_state_repository.py:100` `save_workflow_state` upserts `status`, `current_phase`, `pause_reason`.
  - `src/contexts/knowledge_workbench/application/sagas/pause_knowledge_extraction_workflow.py:103` sets `status=PAUSED`, `pause_reason`, then writes outbox/timeline.
  - `src/contexts/knowledge_workbench/application/sagas/resume_knowledge_extraction_workflow.py:114` sets `status=RUNNING`, clears `pause_reason`, then writes outbox/timeline.
- Readers:
  - `src/contexts/knowledge_workbench/infrastructure/postgres/postgres_knowledge_extraction_saga_state_repository.py:45` loads saga state.
  - `src/interfaces/composition/faq_workbench_workflow_live_state.py:192` reads `wf.status AS workflow_status`; line 193 does `COALESCE(ps.current_phase, wf.current_phase)`.
  - `src/interfaces/composition/knowledge_extraction_workflow_resume.py:333` resolves workflow by `knowledge_extraction_workflow_runs`.
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_due_knowledge_extraction_workflow_reader.py:36` joins this table only to get `project_id`.
- Decision power:
  - It decides legacy pause/resume transitions, but not runtime command dispatch, lease, execute, retry, or future scheduling.
  - Runtime dispatcher reads pending commands from `workflow_runtime_command_log` without `wf.status` filtering.
- UI power:
  - Yes. Hydration after refresh reads `wf.status` directly and derives timer/actions from it; this read is `ACCIDENTAL_LEGACY_DEPENDENCY / BUG`.
- Conflict risk:
  - High. It can conflict with `workflow_runtime_command_log` and `execution_work_items`.
- Pause incident role:
  - DB evidence shows `PAUSED/SOURCE_UNITS_CREATED/manual_stop` at `runtime-db-evidence...txt:13-14`, while runtime projection says `RUNNING/DRAFT_CLAIM_CLUSTERING` at `:69-70`.
- Target state:
  - Do not make this row authoritative or a projection. Move pause semantics to runtime-native state/gate and remove UI/runtime dependencies on legacy status.

## Frontend pause button/action and optimistic pause state

Classification:
- CURRENT_USER_ACTION / CURRENT_UX_BEHAVIOR
- CURRENT_UX_BEHAVIOR_NON_AUTHORITATIVE for optimistic pause state

Evidence:
- Writers:
  - Current frontend action/button triggers pause intent through the current UI flow.
  - Optimistic UI state may immediately show stopped timer and Continue button after the user action.
- Readers:
  - Hydration after refresh comes from backend live-state/projection endpoints, not from the optimistic state itself.
- Decision power:
  - No. The frontend action expresses user intent; it does not itself gate runtime command dispatch or work-item leasing.
- UI power:
  - Yes. This is valid current UX behavior while waiting for backend-confirmed state.
- Conflict risk:
  - High if backend hydration returns legacy/running state after optimistic pause.
- Pause incident role:
  - The optimistic pause behavior was correct as immediate UX. The bug was that backend refresh hydration did not preserve pause intent through runtime-native state.
- Target state:
  - Preserve current user pause intent across refresh using runtime-native pause authority/projection. Do not classify the pause button or optimistic pause UX as legacy.

## knowledge_workbench_documents.status/current_processing_run_id/document_id

Classification:
- CURRENT_PROJECTION for document card identity/status display
- ACCIDENTAL_LEGACY_DEPENDENCY where used as workflow authority

Evidence:
- Writers:
  - Upload/document flows write document rows; cleanup repository can update/delete them.
  - `frontend/src/pages/knowledge/optimisticUpload.ts:66` optimistically sets `current_processing_run_id`.
- Readers:
  - `src/interfaces/composition/faq_workbench_workflow_live_state.py:182` reads `knowledge_workbench_documents` as the document anchor and joins workflow state.
  - `frontend/src/pages/knowledge/KnowledgePage.tsx:242` treats `current_processing_run_id` as processing signal.
  - `frontend/src/pages/knowledge/shadow/workflowFrontendProjectionReducer.ts:1255` sets `current_processing_run_id` from frontend workflow events.
- Decision power:
  - No evidence that it decides command append, lease, execute, retry, or pause.
- UI power:
  - Yes. It hydrates document card status and active workflow id.
- Conflict risk:
  - Medium. It can show `processing` while runtime has paused/completed/blocked state.
- Pause incident role:
  - DB evidence shows document status `processing` and old `updated_at` at `runtime-db-evidence...txt:2451`.
- Target state:
  - Keep as document projection/identity wrapper only. Do not use document status as execution authority.

## workflow_runtime_command_log

Classification:
- CURRENT_AUTHORITY

Evidence:
- Writers:
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_command_log_repository.py:31` appends pending commands.
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_command_log_repository.py:91` marks completed.
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_command_log_repository.py:125` marks failed.
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_command_log_repository.py:159` reschedules pending command.
  - `src/contexts/knowledge_workbench/application/sagas/handle_reconcile_draft_claim_compaction_progress_command.py:293` creates `PrepareDraftClaimCompactionDispatchBatch`.
- Readers:
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_command_log_repository.py:222` selects due `PENDING` commands by `workflow_run_id`, `status`, and `run_after`.
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_due_knowledge_extraction_workflow_reader.py:36` discovers due workflows from pending commands.
- Decision power:
  - Yes. It controls which workflow command is dispatched next.
- UI power:
  - Indirect. UI/debug endpoints read it for state and diagnostics.
- Conflict risk:
  - It is the runtime authority, so legacy rows conflicting with it are legacy split-brain.
- Pause incident role:
  - DB evidence shows post-pause pending `ExecuteDraftClaimCompaction` commands at `runtime-db-evidence...txt:623-645`.
- Target state:
  - Keep. Add missing runtime-native pause gate/state around command scheduling/dispatch, not legacy-row checks.

## workflow_runtime_progress_snapshots

Classification:
- CURRENT_PROJECTION

Evidence:
- Writers:
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_progress_snapshot_repository.py:52` upserts snapshots.
  - Multiple saga handlers save `RUNNING/BLOCKED/COMPLETED` progress, e.g. `handle_reconcile_draft_claim_compaction_progress_command.py:432`.
- Readers:
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_progress_snapshot_repository.py:25` loads by `workflow_run_id`.
  - `src/interfaces/composition/faq_workbench_workflow_live_state.py:231` joins snapshots into UI hydration.
- Decision power:
  - No direct evidence that it decides next dispatch/lease. It summarizes runtime.
- UI power:
  - Yes. It hydrates progress counters and phase, but current code still lets `wf.status` override status.
- Conflict risk:
  - Medium. It conflicted with legacy workflow row in the incident.
- Pause incident role:
  - DB evidence shows `RUNNING/DRAFT_CLAIM_CLUSTERING` with counters after pause at `runtime-db-evidence...txt:69-79`.
- Target state:
  - Keep as runtime projection. Extend with runtime-native pause projection only after authority exists.

## workflow_runtime_outbox_events

Classification:
- CURRENT_PROJECTION / event stream for projectors

Evidence:
- Writers:
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_outbox_repository.py:31` inserts events.
  - Pause/resume use cases append `WorkflowManuallyPaused/WorkflowManuallyResumed`.
- Readers:
  - `src/interfaces/composition/faq_workbench_workflow_live_state.py:157` reads waiting/resolved compaction user-choice events.
  - `src/contexts/knowledge_workbench/observability/application/projectors/*` convert outbox events into `frontend_workflow_events`.
- Decision power:
  - Some handlers/projectors react to events, but pause outbox event does not gate runtime dispatch today.
- UI power:
  - Indirect through frontend event projection.
- Conflict risk:
  - Medium if events are interpreted as authority without command/work-item gate.
- Pause incident role:
  - Timeline/outbox pause existed, but command dispatch continued.
- Target state:
  - Keep as event stream. Do not use legacy pause event alone as runtime gate.

## workflow_runtime_timeline_entries

Classification:
- CURRENT_PROJECTION_OR_AUDIT_EVENT

Evidence:
- Writers:
  - `src/contexts/workflow_runtime/infrastructure/postgres/postgres_timeline_repository.py:28` inserts timeline entries.
  - `pause_knowledge_extraction_workflow.py:121` appends `WorkflowManuallyPaused`.
- Readers:
  - `src/interfaces/composition/faq_workbench_workflow_live_state.py:754` reads latest timeline.
  - `src/interfaces/composition/faq_workbench_workflow_live_state.py:783` reads pause/resume events for timer math.
- Decision power:
  - No. It does not stop command dispatch or leasing.
- UI power:
  - Yes, especially timer segments.
- Conflict risk:
  - Medium. It can say paused while command/work-item runtime continues.
- Pause incident role:
  - DB evidence shows `WorkflowManuallyPaused` at `runtime-db-evidence...txt:2331`.
- Target state:
  - Keep as audit/UI timeline. Pair with runtime-native pause authority, not as authority itself.

## frontend_workflow_events

Classification:
- CURRENT_PROJECTION

Evidence:
- Writers:
  - `src/contexts/knowledge_workbench/observability/infrastructure/postgres/postgres_frontend_workflow_event_repository.py:24` inserts projected frontend events.
  - `src/contexts/knowledge_workbench/observability/application/projectors/draft_claim_compaction_frontend_workflow_event_projector.py:23` maps compaction events.
- Readers:
  - `src/contexts/knowledge_workbench/observability/infrastructure/postgres/postgres_frontend_workflow_event_repository.py:96` lists frontend events by cursor.
  - `frontend/src/pages/knowledge/shadow/workflowFrontendProjectionReducer.ts:1282` applies `canonical_phase`.
- Decision power:
  - No evidence that it decides runtime work.
- UI power:
  - Yes. It is the UI/realtime projection stream.
- Conflict risk:
  - Medium. It can project post-pause in-flight completion events and forbidden new scheduling if runtime emits them.
- Pause incident role:
  - DB evidence shows post-pause `DraftClaimCompactionDispatchBatchPrepared` at `runtime-db-evidence...txt:101` and payloads at `:603-613`.
- Target state:
  - Keep. Hydration should use runtime-native pause projection, not OR legacy/runtime states.

## execution_work_items / execution_work_item_schedules

Classification:
- CURRENT_AUTHORITY

Evidence:
- Writers:
  - `src/contexts/execution_runtime/application/use_cases/ensure_work_items_scheduled.py:127` creates scheduled work item state.
  - `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_lease_repository.py:153` updates leased item state.
- Readers:
  - `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_lease_repository.py:51` peeks due items.
  - `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_lease_repository.py:104` leases due items with `FOR UPDATE SKIP LOCKED`.
  - `src/interfaces/composition/prepare_llm_dispatch_batch.py:310` peeks due records before LLM dispatch preparation.
  - `src/interfaces/composition/faq_workbench_workflow_live_state.py:269` reads scheduled payloads for UI lanes.
- Decision power:
  - Yes. Work-item status and due time decide leases/execution.
- UI power:
  - Yes for sections, attempts, and queue views.
- Conflict risk:
  - It is current execution authority. Legacy rows can conflict with it.
- Pause incident role:
  - DB evidence notes no direct `workflow_run_id` column; current linkage is through schedules/payload/ids at `runtime-db-evidence...txt:15`.
- Target state:
  - Keep. Add runtime-native pause gate before new leases.

## execution_work_item_attempts / execution_work_item_attempt_dispatches

Classification:
- CURRENT_AUTHORITY

Evidence:
- Writers:
  - `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_attempt_dispatch_repository.py:29` inserts attempts.
  - `src/contexts/execution_runtime/infrastructure/postgres/postgres_work_item_attempt_dispatch_repository.py:43` inserts dispatches.
- Readers:
  - `src/interfaces/composition/faq_workbench_workflow_live_state.py:354` reads attempts and dispatch payloads for UI.
  - `src/contexts/knowledge_workbench/extraction/infrastructure/postgres/postgres_draft_claim_compaction_reduction_state_repository.py:513` joins attempts/dispatches for compaction reduction state.
- Decision power:
  - Yes for already-started/in-flight execution and result application.
- UI power:
  - Yes.
- Conflict risk:
  - Current authority for in-flight attempts can legitimately continue after pause.
- Pause incident role:
  - Post-pause in-flight results are allowed; new dispatch/lease waves are forbidden.
- Target state:
  - Keep. Pause must not discard already-started attempts.

## Post-pause event semantics

Classification:
- CURRENT_RUNTIME_SEMANTICS_NEEDS_PAUSE_GATE

Allowed post-pause:
- already-dispatched LLM attempts may finish
- output validation may run
- valid outputs may be persisted
- domain results may be applied
- frontend projection may show completed in-flight results

Forbidden post-pause:
- new prepare dispatch batches
- new leases
- new dispatch attempts for not-yet-started work
- new `Execute*` commands
- reconcile scheduling the next wave

Conclusion:
- The bug is not "any event after pause".
- The bug is new future scheduling after pause and failed hydration after refresh.

## source_documents / source_units

Classification:
- CURRENT_DOMAIN_DATA

Evidence:
- Writers:
  - Source ingestion persists source documents/units; tests enforce `save_source_units` in `tests/contexts/knowledge_workbench/application/sagas/test_create_source_units_for_ingestion.py`.
- Readers:
  - Claim scheduling reads source units for current workflow.
  - Runtime DB evidence shows source unit summary for the paused document.
- Decision power:
  - Domain input for future scheduling, but not pause/execution status authority.
- UI power:
  - Indirect through progress and source evidence.
- Conflict risk:
  - Low for pause status; high if replaced by old `knowledge_documents/knowledge_base`.
- Pause incident role:
  - DB evidence shows 30 source units at `runtime-db-evidence...txt:62`.
- Target state:
  - Keep as source identity/evidence. Do not replace with old documents/chunks.

## draft_claim_observations / draft_claim_embeddings

Classification:
- CURRENT_DOMAIN_DATA

Evidence:
- Writers:
  - Claim builder execution persists valid claims; tests assert this in `test_handle_execute_claim_builder_section_command.py`.
  - Embedding generation handlers write `draft_claim_embeddings`.
- Readers:
  - Compaction planning and clustering read observations/embeddings.
- Decision power:
  - They drive domain compilation phases, not runtime pause.
- UI power:
  - Indirect through counters/previews.
- Conflict risk:
  - Low with command log; they are results of completed work.
- Pause incident role:
  - DB evidence shows 46 observations and embeddings at `runtime-db-evidence...txt:2395-2407`.
- Target state:
  - Keep. In-flight successful outputs may be persisted after pause.

## draft_claim_compaction_*

Classification:
- CURRENT_DOMAIN_DATA

Evidence:
- Writers:
  - Compaction plan/reduction repositories and handlers write groups, batches, nodes, comparisons, rounds.
  - `handle_prepare_draft_claim_compaction_dispatch_batch_command.py:501` updates compaction progress snapshot.
- Readers:
  - `handle_reconcile_draft_claim_compaction_progress_command.py:416` saves compaction progress based on summary/decision.
  - `postgres_draft_claim_compaction_reduction_state_repository.py` reads active compaction state.
- Decision power:
  - Domain state drives next compaction work scheduling, but command/work-item runtime remains execution authority.
- UI power:
  - Yes via projection counters and curation readiness.
- Conflict risk:
  - Medium if reconcile schedules future work while paused.
- Pause incident role:
  - DB evidence shows compaction planned batches at `runtime-db-evidence...txt:2429`.
- Target state:
  - Keep. Reconcile/prepare handlers need runtime-native pause gate before new waves.

## draft_claim_curation_* / runtime publications / runtime retrieval entries

Classification:
- CURRENT_DOMAIN_DATA

Evidence:
- Writers:
  - `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_workspace_repository.py:81` writes workspace/items.
  - `src/contexts/knowledge_workbench/curation/infrastructure/postgres/postgres_draft_claim_curation_publication_repository.py:182` writes `knowledge_workbench_runtime_publications`.
  - Same file line 298 writes `knowledge_workbench_runtime_retrieval_entries`.
- Readers:
  - `src/interfaces/composition/faq_workbench_workflow_live_state.py:797` reads curation availability.
  - `src/domain/project_plane/production_retrieval.py:53` names `knowledge_workbench_runtime_retrieval_entries` as production source.
- Decision power:
  - Publication/retrieval domain data, not pause authority.
- UI power:
  - Yes for curation/publication state.
- Conflict risk:
  - Unknown for this paused run; do not infer from absence after compaction.
- Pause incident role:
  - Run did not reach publication; no failure inferred.
- Target state:
  - Keep as current later-phase domain data. Requires structural follow-up after compaction reaches curation/publication.

## knowledge_extraction_phase_checkpoints / knowledge_extraction_command_log / knowledge_extraction_event_cursor

Classification:
- ACCIDENTAL_LEGACY_DEPENDENCY / DELETE_CANDIDATE after reads removed

Evidence:
- Writers/Readers:
  - `postgres_knowledge_extraction_saga_state_repository.py:74` reads `knowledge_extraction_phase_checkpoints`.
  - Migrations `090_create_knowledge_extraction_saga_tables.sql` create old saga/control-plane tables.
- Decision power:
  - Legacy saga checkpoints can gate old saga transitions, but not current runtime command/work-item execution.
- UI power:
  - Indirect if legacy state is hydrated.
- Conflict risk:
  - High if used as current workflow status source.
- Pause incident role:
  - Legacy phase remained `SOURCE_UNITS_CREATED`.
- Target state:
  - Remove dependencies or replace with runtime-native command/progress state.

## knowledge_workbench_processing_* / section batch queues / local claim retrieval

Classification:
- DELETE_CANDIDATE / LEGACY_COMPATIBILITY

Evidence:
- Writers/Readers:
  - Current searches mainly show migrations and cleanup/test references.
  - Old `processing_run_id/node_run_id` concepts appear in frontend DTOs and legacy migration families.
- Decision power:
  - No evidence they decide current runtime command dispatch or execution leases.
- UI power:
  - Some old DTO labels (`node_run_id`) remain for display compatibility.
- Conflict risk:
  - High if reintroduced as workflow authority.
- Pause incident role:
  - Not causal in observed incident.
- Target state:
  - Delete after references/fixtures are removed. Do not bridge into runtime.

## knowledge_workbench_fact_* / registry / canonical facts

Classification:
- ACCIDENTAL_LEGACY_DEPENDENCY / LEGACY_COMPATIBILITY

Evidence:
- Writers/Readers:
  - Mostly migrations and tests; active migration `117_extend_runtime_retrieval_entries_for_canonical_publish.sql` drops runtime retrieval FK dependence on old `fact_id`.
- Decision power:
  - No evidence of current command/lease authority.
- UI power:
  - Potential publication compatibility, not current Workbench runtime.
- Conflict risk:
  - Medium if old canonical facts are treated as production knowledge.
- Pause incident role:
  - Not reached; do not infer from DB absence.
- Target state:
  - Do not upgrade into current architecture. Current publication should publish grounded runtime retrieval entries.

## knowledge_documents / knowledge_base / execution_queue

Classification:
- DELETE_CANDIDATE

Evidence:
- Writers/Readers:
  - Active references are migrations, retired migrations, and legacy indexes.
  - Current vertical uses `source_documents/source_units`, runtime command log, and execution work items.
- Decision power:
  - No current Workbench runtime authority found.
- UI power:
  - None for current Workbench vertical.
- Conflict risk:
  - High if used as fallback source of truth.
- Pause incident role:
  - Not causal.
- Target state:
  - Drop after compatibility audits/migrations, not as part of pause fix.

## commercial_price_*

Classification:
- UNKNOWN_NEEDS_MORE_EVIDENCE / OUT_OF_CURRENT_FAQ_WORKBENCH_SCOPE

Evidence:
- Writers/Readers:
  - `src/application/services/commercial_price_ingestion_service.py` and commercial truth review services use these tables.
- Decision power:
  - Outside current FAQ Workbench source-of-truth audit.
- UI power:
  - Separate vertical.
- Conflict risk:
  - Low for pause incident.
- Pause incident role:
  - None.
- Target state:
  - Leave out of pause cleanup unless a separate commercial-price audit scopes it in.

## Validation and Limits

Validated:
- Generated DB schema dump and paused runtime DB evidence.
- Ran targeted `rg` and focused `nl -ba ... | sed -n` code inspection.

Not validated:
- No tests/lint/type checks were run because this is a read-only audit and not an application patch.
- Later curation/publication/retrieval live behavior was not proven by the paused compaction run.
