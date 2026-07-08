# Cursor Handoff: Current State After Legacy Cleanup

## Branch

`rescue/0d59-projection-cutover`

## Completed cleanup commit

A cleanup wave removed:
- abandoned `commercial_price` / `commercial_truth` branch;
- old `knowledge_documents` repository helpers;
- old `knowledge_base` active usage;
- Workbench registry/canonical compatibility writes;
- old surface/retrieval DTO tail;
- commercial frontend generated API/i18n surface;
- preserving tests for deleted branches.

Migration added:
- `migrations/119_drop_removed_legacy_db_branches.sql`

Fresh DB check:
- removed commercial/legacy/registry tables: zero rows;
- current spine tables present:
  - `draft_claim_observations`
  - `execution_work_items`
  - `knowledge_workbench_runtime_retrieval_entries`
  - `source_documents`
  - `source_units`
  - `workflow_runtime_command_log`

## Current decisions

### execution_queue

`execution_queue` is not part of Workbench document-upload runtime, but it is active for bot/escalation/metrics queue behavior.

Do not delete it now.

Decision:
- keep as separate bot/escalation/metrics queue for now;
- do not migrate it in the pause patch;
- do not classify it as dead legacy.

### knowledge_extraction_*

`knowledge_extraction_workflow_runs`, `knowledge_extraction_phase_checkpoints`, `knowledge_extraction_command_log`, `knowledge_extraction_event_cursor` are still tied to pause/resume/live-state saga state.

Do not drop them yet.

Next target:
- implement runtime-native pause;
- then remove dependency on old saga/control-plane.

### claim_extraction_stage_work_items

Do not touch yet.
Requires separate audit.

### RagEval / fact_id / node_run_id

Do not touch yet.
Transitional identity cleanup later.

## Current active task

Implement runtime-native pause without touching:
- `execution_queue`
- `claim_extraction_stage_work_items`
- RagEval/fact_id/node_run_id
- DB drop of `knowledge_extraction_*`

## Hard rules for pause patch

Pause authority must be runtime-native.

Do not use:
- `knowledge_extraction_workflow_runs.status`
- `knowledge_extraction_workflow_runs.current_phase`
- `knowledge_extraction_workflow_runs.pause_reason`

as current authority.

Allowed temporary dependency:
- `knowledge_extraction_workflow_runs` may remain only as transitional project_id lookup if necessary.

Forbidden:
- no combined source of truth like `COALESCE(runtime_control.status, wf.status)`;
- no OR-ing legacy and runtime statuses;
- no gate only in due workflow reader.

Pause must gate:
1. due workflow command dispatch / drain;
2. prepare LLM dispatch batch;
3. work-item lease;
4. reconcile/append-next-command paths;
5. live-state hydration after refresh.

Already-dispatched attempts may finish and persist valid output.

## Current unstaged changes

Before continuing, inspect unstaged changes carefully.

Likely partial/unfinished pause or capacity work:
- `src/contexts/knowledge_workbench/application/sagas/handle_cluster_draft_claims_command.py`
- `src/contexts/knowledge_workbench/application/sagas/source_ingestion_segmentation_profiles.py`
- `src/contexts/knowledge_workbench/document_segmentation/domain/segmentation_budget.py`
- `src/contexts/llm_runtime/application/policies/llm_quota_availability_policy.py`
- `src/contexts/llm_runtime/domain/entities/model_profile.py`
- `src/interfaces/composition/prepare_llm_dispatch_batch.py`
- related tests

Do not assume these are correct.
Audit before continuing.

## Validation from cleanup wave

Previously reported passing:
- `python -m ruff check src tests`
- `python -m pytest tests/api/test_knowledge.py -q`
- `python -m pytest tests/contexts/knowledge_workbench -q`
- `python -m pytest tests/contexts/workflow_runtime -q`
- `python -m pytest tests/contexts/execution_runtime -q`

But after unstaged pause/capacity changes, rerun validation.
