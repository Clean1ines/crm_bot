# Runtime-Native Pause Patch Map

## Current Pause Write Path

- HTTP route: `src/interfaces/http/knowledge.py` calls `pause_knowledge_extraction_workflow`.
- Composition: `src/interfaces/composition/knowledge_extraction_workflow_pause_resume.py` creates `PostgresKnowledgeExtractionSagaStateRepository` and `PostgresWorkflowRuntimeUnitOfWork`.
- Use case: `src/contexts/knowledge_workbench/application/sagas/pause_knowledge_extraction_workflow.py`
  - loads `knowledge_extraction_workflow_runs` through saga state repository;
  - writes `KnowledgeExtractionWorkflowStatus.PAUSED` and `pause_reason`;
  - appends `WorkflowManuallyPaused` outbox/timeline events.
- Problem: pause authority is stored only in legacy saga/control-plane state.

## Current Resume Write Path

- HTTP route: `src/interfaces/http/knowledge.py` calls `resume_knowledge_extraction_workflow`.
- Composition: `src/interfaces/composition/knowledge_extraction_workflow_pause_resume.py`.
- Use case: `src/contexts/knowledge_workbench/application/sagas/resume_knowledge_extraction_workflow.py`
  - requires saga state status `PAUSED`;
  - writes legacy saga status back to `RUNNING`;
  - appends `WorkflowManuallyResumed` outbox/timeline events.
- Problem: resume authority is legacy status, not runtime-native control state.

## Current Frontend Hydration Status Source

- Live-state query: `src/interfaces/composition/faq_workbench_workflow_live_state.py`.
- Current source:
  - `wf.status AS workflow_status`;
  - `COALESCE(ps.current_phase, wf.current_phase) AS current_phase`;
  - `knowledge_extraction_workflow_runs` selected as `wf`.
- Problem: refresh hydration can disagree with runtime command/work-item authority and should not use `wf.status/current_phase` as current control.

## Command Dispatch Gate Points

- Runtime pump selects due workflows through `PostgresDueKnowledgeExtractionWorkflowReader`.
- Command drain: `src/contexts/knowledge_workbench/application/sagas/drain_knowledge_extraction_workflow_commands.py`.
- Current pause gate:
  - checks `workflow_state_repository.load_workflow_state`;
  - blocks if `KnowledgeExtractionWorkflowStatus.PAUSED`.
- Target:
  - add `workflow_runtime_control_states`;
  - pause gate checks runtime control state before dispatching pending commands;
  - pending commands remain pending, not failed.

## Work Item Lease Gate Points

- LLM dispatch preparation: `src/interfaces/composition/prepare_llm_dispatch_batch.py`.
- Lease points:
  - `peek_due_work_items`;
  - `_lease_input_admitted_work_items`;
  - `lease_due_work_item_by_id`.
- Link to workflow:
  - prepared Workbench LLM work items carry `workflow_run_id` in `execution_work_item_schedules.payload`.
- Target:
  - before peeking/leasing, inspect due schedule payloads for workflow ids;
  - if any due work belongs to a paused workflow, do not lease/start attempts for that workflow.

## Reconcile / Append-Next-Command Gate Points

Minimum inspected patch targets:

- `handle_reconcile_draft_claim_compaction_progress_command.py`
- `handle_prepare_draft_claim_compaction_dispatch_batch_command.py`
- `handle_reconcile_claim_builder_progress_command.py`
- `handle_prepare_claim_builder_dispatch_batch_command.py`
- `prepare_llm_dispatch_batch.py`

Target behavior:

- do not append new `Prepare*`/`Execute*` waves while runtime control state is `PAUSED`;
- allow already-started execute/apply result handlers to persist valid outputs and complete their current command.

## Target Runtime-Native State/Table/Repository

- Table: `workflow_runtime_control_states`.
- Columns:
  - `workflow_run_id text primary key`
  - `control_status text not null` with `RUNNING` / `PAUSED`
  - `pause_reason text`
  - `paused_at timestamptz`
  - `resumed_at timestamptz`
  - `updated_at timestamptz not null`
- Domain entity: `WorkflowRuntimeControlState`.
- Repository port: `WorkflowRuntimeControlStateRepositoryPort`.
- Postgres repository: `PostgresWorkflowRuntimeControlStateRepository`.
- Unit of work property: `workflow_unit_of_work.control_states`.

## Tests To Update/Add

- Pause/resume saga tests:
  - pause writes runtime-native control state;
  - resume clears runtime-native pause state;
  - legacy status alone is not runtime authority.
- Command drain tests:
  - paused runtime control state blocks due command dispatch without failing command.
- Prepare LLM dispatch tests:
  - paused workflow does not lease due work items or start attempts.
- Reconcile/prepare handler tests:
  - paused compaction/claim-builder paths do not append next wave commands.
- Live-state tests:
  - hydration reports paused from runtime control state even if progress snapshot says running;
  - legacy `knowledge_extraction_workflow_runs.status` alone does not make runtime paused/running.
