# Legacy Dependency Index

## knowledge_extraction_workflow_runs.status/current_phase/pause_reason

Classification:
- LEGACY_SPLIT_BRAIN_STORAGE

Current references:
- `src/contexts/knowledge_workbench/infrastructure/postgres/postgres_knowledge_extraction_saga_state_repository.py:45` read.
- `src/contexts/knowledge_workbench/infrastructure/postgres/postgres_knowledge_extraction_saga_state_repository.py:100` write.
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:192` UI hydration read.
- `src/interfaces/composition/knowledge_extraction_workflow_resume.py:333` workflow resolution read.
- `src/contexts/workflow_runtime/infrastructure/postgres/postgres_due_knowledge_extraction_workflow_reader.py:36` project-id join.

Why legacy:
- Current user pause intent is valid and must be preserved, but this table stores that intent in an old saga/control-plane row. Runtime command/progress continued because this storage lacks causal power over runtime dispatch/lease.

What blocks deletion:
- current read
- current write
- tests preserving old saga behavior
- migrations/FKs from phase checkpoints

Removal direction:
- replace with runtime-native state
- replace project lookup with current source document/workflow identity projection
- remove tests that preserve legacy behavior
- migration/drop candidate later

## Frontend pause button/action and optimistic pause state

Classification:
- CURRENT_USER_ACTION / CURRENT_UX_BEHAVIOR
- CURRENT_UX_BEHAVIOR_NON_AUTHORITATIVE for optimistic pause state

Current references:
- Current frontend pause action/button path triggers user pause intent.
- Optimistic UI behavior can show stopped timer and Continue button before backend refresh hydration.

Why not legacy:
- The pause button and optimistic response are current UX behavior.
- The legacy dependency is backend storage/hydration through `knowledge_extraction_workflow_runs.status/current_phase`, not the user action.

What blocks deletion:
- not a deletion candidate

Removal direction:
- preserve UX behavior
- hydrate from runtime-native pause authority/projection after backend state exists

## knowledge_extraction_phase_checkpoints

Classification:
- ACCIDENTAL_LEGACY_DEPENDENCY

Current references:
- `src/contexts/knowledge_workbench/infrastructure/postgres/postgres_knowledge_extraction_saga_state_repository.py:74` read.
- `src/contexts/knowledge_workbench/infrastructure/postgres/postgres_knowledge_extraction_saga_state_repository.py` writes checkpoints.

Why legacy:
- It belongs to old saga/control-plane state. Current runtime authority is command log plus execution work items.

What blocks deletion:
- current read
- current write
- test fixtures

Removal direction:
- replace with runtime progress snapshots/domain tables where needed
- delete tests that encode old phase checkpoints

## knowledge_workbench_documents.status/current_processing_run_id

Classification:
- ACCIDENTAL_LEGACY_DEPENDENCY

Current references:
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:182` document row read.
- `frontend/src/pages/knowledge/KnowledgePage.tsx:242` processing signal.
- `frontend/src/pages/knowledge/optimisticUpload.ts:66` optimistic current run id.
- `frontend/src/pages/knowledge/shadow/workflowFrontendProjectionReducer.ts:1255` sets current run id.

Why legacy:
- Valid as document projection, but not valid as workflow/runtime status authority.

What blocks deletion:
- frontend DTO
- current UI read
- upload/document card flow

Removal direction:
- keep as projection only
- move runtime state to runtime-native projection

## Frontend hydration reading wf.status/current_phase

Classification:
- ACCIDENTAL_LEGACY_DEPENDENCY / BUG

Current references:
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:192` reads `wf.status AS workflow_status`.
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:193` reads `COALESCE(ps.current_phase, wf.current_phase)`.

Why legacy:
- Refresh hydration can override valid optimistic pause UX with legacy-row state or mixed legacy/runtime state.
- This is the dependency that must be removed, not the pause button itself.

What blocks deletion:
- current read
- frontend DTO expectations

Removal direction:
- replace with runtime-native pause/progress projection
- do not OR legacy and runtime statuses

## workflow_runtime_timeline_entries.WorkflowManuallyPaused

Classification:
- CURRENT_PROJECTION_OR_AUDIT_EVENT

Current references:
- `src/contexts/knowledge_workbench/application/sagas/pause_knowledge_extraction_workflow.py:121` writes timeline pause entry.
- `src/interfaces/composition/faq_workbench_workflow_live_state.py:783` reads pause/resume timeline events for timer math.

Why not authority:
- Useful for timeline/timer/history, but not sufficient to block command dispatch or work-item leases.

What blocks deletion:
- current UI/timer read
- audit/history value

Removal direction:
- keep as audit/projection
- pair with runtime-native pause authority

## Runtime-native pause gate/state

Classification:
- MISSING_CURRENT_AUTHORITY

Current references:
- No proven runtime-native state/gate found that is read before command dispatch or work-item lease.

Why needed:
- User pause intent must be preserved across refresh and must block new future scheduling/lease/dispatch waves.

What blocks deletion:
- not applicable

Removal direction:
- introduce runtime-native pause authority before patching pause behavior

## knowledge_workbench_processing_runs / processing_node_runs / processing_node_artifacts

Classification:
- DELETE_CANDIDATE

Current references:
- Primarily migrations `070_create_faq_workbench_v1.sql`, `076_workbench_schema_contract_forward_repair.sql`, `082_workbench_processing_run_active_window.sql`.
- Old DTO names remain in UI/read models as `node_run_id`.

Why legacy:
- No evidence found that these tables decide current command dispatch, work-item lease, or LLM attempts.

What blocks deletion:
- migration only
- frontend DTO labels
- cleanup/test references

Removal direction:
- replace display DTO names with execution-runtime attempt/work-item ids
- remove old API path
- drop later

## knowledge_workbench_fact_registries / canonical_facts / fact_* / registry_snapshots

Classification:
- LEGACY_COMPATIBILITY

Current references:
- Migrations `070_create_faq_workbench_v1.sql`, `076_workbench_schema_contract_forward_repair.sql`, `077_workbench_fact_registry_parent_contract.sql`.
- `migrations/117_extend_runtime_retrieval_entries_for_canonical_publish.sql` drops old runtime retrieval `fact_id` FK/not-null dependency.

Why legacy:
- The target vertical publishes grounded runtime retrieval entries, not old registry/canonical fact authority.

What blocks deletion:
- migration history
- possible publication compatibility
- test fixtures

Removal direction:
- replace with current domain data and runtime retrieval surface
- delete compatibility tests that preserve registry behavior
- migration/drop candidate later

## knowledge_workbench_section_batch_queue_items / parallel_section_batch_plans

Classification:
- DELETE_CANDIDATE

Current references:
- Migrations `075_workbench_parallel_section_batch_queue.sql` and `076_workbench_schema_contract_forward_repair.sql`.

Why legacy:
- Current scheduling is `workflow_runtime_command_log` plus `execution_work_items`.

What blocks deletion:
- migration only
- potential stale cleanup code

Removal direction:
- replace with execution-runtime schedules
- drop later after schema/data audit

## knowledge_workbench_local_claim_retrieval_entries

Classification:
- DELETE_CANDIDATE

Current references:
- Migration `080_create_workbench_local_claim_retrieval_surface.sql`.

Why legacy:
- Current production retrieval surface is `knowledge_workbench_runtime_retrieval_entries`.

What blocks deletion:
- migration only
- unknown stale references

Removal direction:
- replace with runtime retrieval entries
- drop later

## knowledge_documents / knowledge_base

Classification:
- DELETE_CANDIDATE

Current references:
- Active/retired migrations for legacy knowledge storage and indexes.
- Current vertical uses `source_documents/source_units` and runtime retrieval entries.

Why legacy:
- They do not own current Workbench source identity, compilation output, or execution runtime.

What blocks deletion:
- old migrations
- possible unrelated legacy APIs

Removal direction:
- remove old API paths
- drop after separate data-retention plan

## execution_queue

Classification:
- DELETE_CANDIDATE

Current references:
- Migrations `002_add_execution_queue.sql`, `012_improve_execution_queue.sql`, `052_add_model_usage_events_and_queue_schedule.sql`, rescue migration `998`.

Why legacy:
- Current execution runtime uses `execution_work_items`.

What blocks deletion:
- migration only
- possible stale workers

Removal direction:
- remove old queue workers/API if any remain
- drop later

## claim_extraction_stage_work_items

Classification:
- ACCIDENTAL_LEGACY_DEPENDENCY

Current references:
- Migrations `088`, `092`, `093`, `094` and architecture tests.

Why legacy:
- Migration comment states semantics moved into `execution_work_items`; current runtime lease uses execution runtime tables.

What blocks deletion:
- migration/schema contract tests

Removal direction:
- replace with execution-runtime schedules and payloads
- drop after migration cleanup

## commercial_price_*

Classification:
- UNKNOWN_NEEDS_MORE_EVIDENCE

Current references:
- `src/application/services/commercial_price_ingestion_service.py`
- `src/application/services/commercial_truth_review_service.py`

Why legacy:
- Out of current FAQ Workbench pause/source-of-truth scope, but active in another vertical.

What blocks deletion:
- active commercial-price feature code

Removal direction:
- no action in Workbench pause cleanup
