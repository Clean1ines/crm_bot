from .commands import KnowledgePipelineCommand
from .snapshot import KnowledgePipelineSnapshot
from .states import KnowledgePipelineState
from .transitions import STATE_ALLOWED_COMMANDS


def allowed_actions_for_state(
    state: KnowledgePipelineState,
    snapshot: KnowledgePipelineSnapshot,
) -> tuple[KnowledgePipelineCommand, ...]:
    if state == KnowledgePipelineState.FAILED_RETRYABLE:
        if snapshot.compiler_batch_failed_count > 0:
            return (KnowledgePipelineCommand.RETRY_FAILED_COMPILER_BATCHES,)
        return (KnowledgePipelineCommand.RESUME_KNOWLEDGE_COMPILATION,)

    actions = STATE_ALLOWED_COMMANDS.get(state, ())
    if (
        state == KnowledgePipelineState.FAILED_FATAL
        and snapshot.raw_candidate_count <= 0
    ):
        return ()
    return actions
