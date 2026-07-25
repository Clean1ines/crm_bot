#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path.cwd()

EXECUTE_PATH = ROOT / (
    "src/contexts/knowledge_workbench/application/sagas/"
    "handle_execute_draft_claim_compaction_command.py"
)
DISPATCH_PATH = ROOT / (
    "src/contexts/knowledge_workbench/application/sagas/"
    "dispatch_knowledge_extraction_workflow_command.py"
)


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{label}: expected exactly one matching source block, found {count}. "
            "No files were changed."
        )
    return text.replace(old, new, 1)


execute = EXECUTE_PATH.read_text(encoding="utf-8")
dispatch = DISPATCH_PATH.read_text(encoding="utf-8")

execute_new = execute
dispatch_new = dispatch

execute_new = replace_once(
    execute_new,
    """from typing import Protocol, TypeGuard, cast

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
""",
    """from typing import Protocol, TypeGuard, cast

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.handle_apply_draft_claim_compaction_result_command import (
    HandleApplyDraftClaimCompactionResultCommand,
    HandleApplyDraftClaimCompactionResultCommandHandler,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadRepositoryPort,
)
from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
""",
    label="execute imports",
)

execute_new = replace_once(
    execute_new,
    """        draft_claim_compaction_output_validator: DraftClaimCompactionOutputValidator,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
""",
    """        draft_claim_compaction_output_validator: DraftClaimCompactionOutputValidator,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        draft_claim_compaction_reduction_state_repository: (
            DraftClaimCompactionReductionStateRepositoryPort
        ),
        draft_claim_observation_read_repository: DraftClaimObservationReadRepositoryPort,
        work_item_scheduling_repository: WorkItemSchedulingRepositoryPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
""",
    label="execute signature",
)

execute_new = replace_once(
    execute_new,
    """        await workflow_unit_of_work.command_log.append_pending_command(next_command)
        appended_next_command_count = 1 + capacity_window_wakeup_count

        await _save_progress_snapshot(
""",
    """        persisted_next_command = (
            await workflow_unit_of_work.command_log.append_pending_command(next_command)
        )
        appended_next_command_count = 1 + capacity_window_wakeup_count

        if (
            persisted_next_command.command_type
            == KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT.value
        ):
            apply_result = (
                await HandleApplyDraftClaimCompactionResultCommandHandler().execute(
                    HandleApplyDraftClaimCompactionResultCommand(
                        workflow_command=persisted_next_command,
                    ),
                    workflow_unit_of_work=workflow_unit_of_work,
                    compaction_reduction_state_repository=(
                        draft_claim_compaction_reduction_state_repository
                    ),
                    draft_claim_observation_read_repository=(
                        draft_claim_observation_read_repository
                    ),
                    work_item_scheduling_repository=work_item_scheduling_repository,
                    frontend_event_projection_writer=frontend_event_projection_writer,
                )
            )
            appended_next_command_count += apply_result.appended_next_command_count

        await _save_progress_snapshot(
""",
    label="inline compaction apply",
)

dispatch_new = replace_once(
    dispatch_new,
    """                execute_prepared_llm_dispatch_attempt is None
                or capacity_observation_repository is None
                or draft_claim_compaction_output_validator is None
            ):
""",
    """                execute_prepared_llm_dispatch_attempt is None
                or capacity_observation_repository is None
                or draft_claim_compaction_output_validator is None
                or draft_claim_compaction_reduction_state_repository is None
                or draft_claim_observation_read_repository is None
            ):
""",
    label="dispatcher dependency guard",
)

dispatch_new = replace_once(
    dispatch_new,
    """                draft_claim_compaction_output_validator=(
                    draft_claim_compaction_output_validator
                ),
                workflow_unit_of_work=workflow_unit_of_work,
""",
    """                draft_claim_compaction_output_validator=(
                    draft_claim_compaction_output_validator
                ),
                draft_claim_compaction_reduction_state_repository=(
                    draft_claim_compaction_reduction_state_repository
                ),
                draft_claim_observation_read_repository=(
                    draft_claim_observation_read_repository
                ),
                work_item_scheduling_repository=knowledge_unit_of_work,
                workflow_unit_of_work=workflow_unit_of_work,
""",
    label="dispatcher execute arguments",
)

# All validation happened above. Only now write files.
EXECUTE_PATH.write_text(execute_new, encoding="utf-8")
DISPATCH_PATH.write_text(dispatch_new, encoding="utf-8")

subprocess.run(
    ["git", "diff", "--check", "--", str(EXECUTE_PATH), str(DISPATCH_PATH)],
    check=True,
)

print("Patch applied successfully.")
print()
subprocess.run(
    ["git", "diff", "--stat", "--", str(EXECUTE_PATH), str(DISPATCH_PATH)],
    check=True,
)
print()
print("Review with:")
print(
    "git diff -- "
    "src/contexts/knowledge_workbench/application/sagas/"
    "handle_execute_draft_claim_compaction_command.py "
    "src/contexts/knowledge_workbench/application/sagas/"
    "dispatch_knowledge_extraction_workflow_command.py"
)