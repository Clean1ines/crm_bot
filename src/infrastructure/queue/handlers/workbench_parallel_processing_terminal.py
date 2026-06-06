from __future__ import annotations

from collections.abc import Mapping

from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.application.ports.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsGenerationError,
)
from src.infrastructure.queue.handlers.workbench_parallel_processing import (
    WorkbenchParallelProcessingJobPayloadDto,
    handle_workbench_parallel_processing_job_from_connection,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError


async def handle_workbench_parallel_processing_job_terminal(
    *,
    payload: WorkbenchParallelProcessingJobPayloadDto | Mapping[str, object],
    connection: object,
) -> object:
    dto = (
        payload
        if isinstance(payload, WorkbenchParallelProcessingJobPayloadDto)
        else WorkbenchParallelProcessingJobPayloadDto.from_mapping(payload)
    )
    try:
        return await handle_workbench_parallel_processing_job_from_connection(
            payload=dto,
            connection=connection,
        )
    except FaqWorkbenchClaimObservationsGenerationError as exc:
        retry_after_seconds = (
            float(exc.cooldown_seconds) if exc.cooldown_seconds is not None else 1.0
        )

        raise TransientJobError(
            f"retryable Prompt A invocation failure: {exc}",
            retry_after_seconds=max(retry_after_seconds, 1.0),
        ) from exc
    except DomainInvariantError as exc:
        if _is_retryable_prompt_a_contract_failure(exc):
            raise TransientJobError(
                f"retryable Prompt A output contract failure: {exc}",
                retry_after_seconds=1.0,
            ) from exc

        await _mark_workbench_processing_failed(
            connection=connection,
            payload=dto,
            error_kind="domain_invariant_error",
            user_message="Ошибка контракта обработки документа. Документ не обработан.",
            internal_error=str(exc),
        )
        raise PermanentJobError(str(exc)) from exc


def _is_retryable_prompt_a_output_contract_failure(exc: DomainInvariantError) -> bool:
    message = str(exc)
    retryable_markers = (
        "claim observation",
        "claim observations payload",
        "claim_observations",
        "claims",
        "unknown claim observations payload keys",
        "unknown claim observation",
        "requires non-empty string evidence_block",
        "requires non-empty triples list",
        "requires reason",
        "unsupported predicate",
        "unsupported relation",
        "must be list",
        "must be object",
        "must be exactly claims",
        "LLM JSON payload contains non-JSON value",
        "value is not JSON serializable",
    )
    return any(marker in message for marker in retryable_markers)


def _is_retryable_prompt_a_contract_failure(exc: DomainInvariantError) -> bool:
    return _is_retryable_prompt_a_output_contract_failure(exc)


async def _mark_workbench_processing_failed(
    *,
    connection: object,
    payload: WorkbenchParallelProcessingJobPayloadDto,
    error_kind: str,
    user_message: str,
    internal_error: str,
) -> None:
    execute = getattr(connection, "execute", None)
    if not callable(execute):
        return

    safe_internal_error = internal_error[:2000]
    await execute(
        """
        UPDATE knowledge_workbench_processing_runs
        SET
            status = 'failed_validation',
            resume_policy = 'forbidden',
            completed_at = COALESCE(completed_at, now()),
            last_error_kind = $4,
            last_user_message = $5,
            last_internal_error = $6,
            last_error = $6
        WHERE project_id = $1::uuid
          AND document_id = $2
          AND processing_run_id = $3
        """,
        payload.project_id,
        payload.document_id,
        payload.processing_run_id,
        error_kind,
        user_message,
        safe_internal_error,
    )
    await execute(
        """
        UPDATE knowledge_workbench_documents
        SET
            status = 'failed',
            last_error_kind = $3,
            last_error_message = $4,
            last_error_at = now(),
            updated_at = now()
        WHERE project_id = $1::uuid
          AND document_id = $2
        """,
        payload.project_id,
        payload.document_id,
        error_kind,
        user_message,
    )
