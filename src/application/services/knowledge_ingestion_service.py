from dataclasses import dataclass

from src.application.errors import EmbeddingProviderError, ValidationError
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    ModelUsageRepositoryFactoryPort,
    KnowledgePreprocessorFactoryPort,
    KnowledgeRepositoryFactoryPort,
)
from src.application.ports.logger_port import LoggerPort
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_PLAIN,
    PREPROCESSING_STATUS_COMPLETED,
    PREPROCESSING_STATUS_FAILED,
    PREPROCESSING_STATUS_NOT_REQUESTED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingMode,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentProcessingResult:
    document_id: str
    preprocessing_status: str
    structured_entries: int


class KnowledgeIngestionService:
    def __init__(self, pool: KnowledgeDbPoolPort) -> None:
        self.pool = pool

    async def process_document(
        self,
        *,
        project_id: str,
        document_id: str,
        file_name: str,
        chunks: list[JsonObject],
        mode: KnowledgePreprocessingMode,
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort | None,
        logger: LoggerPort,
    ) -> KnowledgeDocumentProcessingResult:
        repo = knowledge_repo_factory(self.pool)
        usage_repo = model_usage_repo_factory(self.pool)
        await repo.delete_document_chunks(document_id)

        try:
            await repo.add_knowledge_batch(project_id, chunks, document_id=document_id)
        except EmbeddingProviderError as exc:
            if exc.retryable:
                logger.warning(
                    "Knowledge embedding provider temporary failure",
                    extra={
                        "project_id": project_id,
                        "document_id": document_id,
                        "provider": exc.provider,
                        "task": exc.task,
                        "model": exc.model,
                        "error_type": type(exc).__name__,
                    },
                )
                raise

            logger.warning(
                "Knowledge embedding provider permanent failure",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "provider": exc.provider,
                    "task": exc.task,
                    "model": exc.model,
                    "error_type": type(exc).__name__,
                },
            )
            await repo.update_document_status(document_id, "error", exc.detail)
            raise
        except Exception as exc:
            logger.exception(
                "Knowledge upload processing failed",
                extra={"project_id": project_id, "document_id": document_id},
            )
            await repo.update_document_status(document_id, "error", str(exc))
            raise

        if mode == MODE_PLAIN:
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_NOT_REQUESTED,
            )
            await repo.update_document_status(document_id, "processed")
            return KnowledgeDocumentProcessingResult(
                document_id=document_id,
                preprocessing_status=PREPROCESSING_STATUS_NOT_REQUESTED,
                structured_entries=0,
            )

        if preprocessor_factory is None:
            raise ValidationError(
                "Knowledge preprocessing adapter is required for non-plain upload modes"
            )

        await repo.update_document_preprocessing_status(
            document_id,
            mode=mode,
            status=PREPROCESSING_STATUS_PROCESSING,
        )

        try:
            execution = await preprocessor_factory().preprocess(
                mode=mode,
                chunks=chunks,
                file_name=file_name,
            )
            if execution.usage is not None:
                await usage_repo.record_event(
                    ModelUsageEventCreate.from_measurement(
                        project_id=project_id,
                        source="knowledge_preprocessing",
                        measurement=execution.usage,
                        document_id=document_id,
                    )
                )
            result = execution.result
            structured_chunks = result.to_chunks()
            if structured_chunks:
                await repo.add_structured_knowledge_batch(
                    project_id,
                    structured_chunks,
                    document_id=document_id,
                )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_COMPLETED,
                model=result.model,
                prompt_version=result.prompt_version,
                metrics=result.metrics,
            )
            await repo.update_document_status(document_id, "processed")
            return KnowledgeDocumentProcessingResult(
                document_id=document_id,
                preprocessing_status=PREPROCESSING_STATUS_COMPLETED,
                structured_entries=len(structured_chunks),
            )
        except EmbeddingProviderError as exc:
            if exc.retryable:
                logger.warning(
                    "Knowledge embedding provider temporary failure during structured indexing",
                    extra={
                        "project_id": project_id,
                        "document_id": document_id,
                        "provider": exc.provider,
                        "task": exc.task,
                        "model": exc.model,
                        "error_type": type(exc).__name__,
                    },
                )
                raise

            logger.warning(
                "Knowledge embedding provider permanent failure during structured indexing",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "provider": exc.provider,
                    "task": exc.task,
                    "model": exc.model,
                    "error_type": type(exc).__name__,
                },
            )
            await repo.update_document_status(document_id, "error", exc.detail)
            raise
        except Exception as exc:
            logger.warning(
                "Knowledge preprocessing failed; original chunks remain usable",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "mode": mode,
                    "error_type": type(exc).__name__,
                },
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_FAILED,
                error=str(exc)[:1000],
            )
            await repo.update_document_status(document_id, "processed")
            return KnowledgeDocumentProcessingResult(
                document_id=document_id,
                preprocessing_status=PREPROCESSING_STATUS_FAILED,
                structured_entries=0,
            )
