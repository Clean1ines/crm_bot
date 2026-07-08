# Current Workbench Authority Map

## Source identity

source_document_ref:
- authority: `source_documents.document_ref`
- current table: `source_documents`
- forbidden replacements: `knowledge_documents.id`, `knowledge_base.document_id`, processing-run ids

source_unit_ref:
- authority: `source_units.unit_ref`
- current table: `source_units`
- forbidden replacements: old chunk ids, `knowledge_base` rows, section batch ids

workflow_run_id:
- authority: runtime command/projection identity
- current tables: `workflow_runtime_command_log`, `workflow_runtime_outbox_events`, `workflow_runtime_progress_snapshots`, `workflow_runtime_timeline_entries`, `frontend_workflow_events`
- forbidden replacements: `knowledge_workbench_processing_runs.processing_run_id`, registry snapshot ids, document ids

work_item_id:
- authority: execution runtime
- current tables: `execution_work_items`, `execution_work_item_schedules`

attempt_id:
- authority: execution runtime attempts
- current tables: `execution_work_item_attempts`, `execution_work_item_attempt_dispatches`

observation_ref:
- authority: claim builder output
- current tables: `draft_claim_observations`, `draft_claim_observation_provenance`, `draft_claim_observation_possible_questions`

group_ref / batch_ref / node_ref:
- authority: draft claim compaction domain
- current tables: `draft_claim_compaction_groups`, `draft_claim_compaction_batches`, `draft_claim_compaction_nodes`, plus related compaction edge/component/source tables

workspace_ref / item_ref:
- authority: curation workspace
- current tables: `draft_claim_curation_workspaces`, `draft_claim_curation_items`

publication_id / runtime_entry_id:
- authority: production retrieval publication surface
- current tables: `knowledge_workbench_runtime_publications`, `knowledge_workbench_runtime_retrieval_entries`, `knowledge_workbench_runtime_retrieval_entry_embeddings`

## Execution authority

Current execution authority belongs to:
- `workflow_runtime_command_log`
- `execution_work_items`
- `execution_work_item_attempts`
- `execution_work_item_attempt_dispatches`
- runtime-native pause gate/state: MISSING_CURRENT_AUTHORITY

Not execution authority:
- `knowledge_extraction_workflow_runs.status/current_phase`
- `knowledge_workbench_documents.status`
- `knowledge_documents.status`
- `processing_node_runs.status`
- registry/canonical fact tables

## Projection layers

Current projection layers:
- `workflow_runtime_progress_snapshots` for progress counters/current phase/status summary.
- `workflow_runtime_timeline_entries` for UI/audit timeline and timer events.
- `frontend_workflow_events` for frontend/realtime event replay.
- `knowledge_workbench_documents` for document-card projection and current run pointer.

Projection caveat:
- Current live-state hydration still reads `knowledge_extraction_workflow_runs.status` and `current_phase`; this is legacy split-brain, not target authority.

## Pause authority

Current state:
- User pause intent is `CURRENT_USER_INTENT`: it is triggered by the current frontend action/button and must be preserved across refresh.
- Frontend optimistic pause state is `CURRENT_UX_BEHAVIOR_NON_AUTHORITATIVE`: it is valid temporary UI response to user action, but not backend execution authority.
- Backend pause write to `knowledge_extraction_workflow_runs.status=PAUSED` is `LEGACY_SPLIT_BRAIN_STORAGE`.
- `workflow_runtime_timeline_entries.WorkflowManuallyPaused` is `CURRENT_PROJECTION_OR_AUDIT_EVENT`, useful for timeline/timer/history but not sufficient as execution gate.
- No evidence found that runtime command dispatch or work-item leasing reads a runtime-native pause state.
- Runtime-native pause gate/state is `MISSING_CURRENT_AUTHORITY`.

Target state:
- Pause must be represented in runtime-native authority/gate.
- Pause must block new command dispatch/prepare waves and new leases.
- Pause must allow already-started attempts to finish and persist valid outputs.
- Frontend after refresh must hydrate from runtime-native pause state/projection, preserving current user pause intent.

Forbidden replacements:
- Do not use `knowledge_extraction_workflow_runs.status` as runtime pause gate.
- Do not sync legacy workflow row into runtime as a compatibility bridge.
- Do not OR legacy and runtime statuses in frontend hydration.

## Liveness conclusion

The paused run is not evidence that the current workflow cannot progress.

The runtime was alive and progressing:
- claim builder completed 30 source units
- draft claims were persisted
- embeddings were generated
- compaction was scheduled and partially executed
- runtime progress showed `DRAFT_CLAIM_CLUSTERING` with active/completed work

Without the user pause, the workflow likely would have continued toward later compaction/curation/publication steps. The incident proves split-brain pause semantics, not a dead workflow.
