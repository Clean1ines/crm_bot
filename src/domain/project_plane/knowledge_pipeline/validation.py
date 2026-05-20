from .actions import allowed_actions_for_state
from .commands import KnowledgePipelineCommand
from .errors import KnowledgePipelineValidationError
from .snapshot import KnowledgePipelineSnapshot
from .states import KnowledgePipelineState


def validate_pipeline_command(
    state: KnowledgePipelineState,
    command: KnowledgePipelineCommand,
    snapshot: KnowledgePipelineSnapshot,
) -> None:
    allowed = allowed_actions_for_state(state, snapshot)
    if command not in allowed:
        raise KnowledgePipelineValidationError(
            f"Command '{command.value}' is not allowed in state '{state.value}'"
        )
