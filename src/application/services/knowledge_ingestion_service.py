from typing import cast

from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    KnowledgePreprocessorFactoryPort,
    ModelUsageRepositoryFactoryPort,
)
from src.application.ports.logger_port import LoggerPort
from src.application.services.knowledge_ingestion_contracts import (
    CommercialPriceAcquisitionServiceFactoryPort,
    CommercialPriceRepositoryFactoryPort,
    KnowledgeDocumentProcessingResult,
    KnowledgeIngestionRepositoryFactoryPort,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingValidationError,
)


class KnowledgeIngestionService:
    def __init__(self, pool: KnowledgeDbPoolPort) -> None:
        self.pool = pool

    async def retighten_processed_document(
        self,
        *,
        project_id: str,
        document_id: str,
        file_name: str,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort,
        logger: LoggerPort,
    ) -> JsonObject:
        from src.application.services.knowledge_retighten_service import (
            KnowledgeRetightenService,
        )

        return await KnowledgeRetightenService(self.pool).retighten_processed_document(
            project_id=project_id,
            document_id=document_id,
            file_name=file_name,
            knowledge_repo_factory=knowledge_repo_factory,
            model_usage_repo_factory=model_usage_repo_factory,
            preprocessor_factory=preprocessor_factory,
            logger=logger,
        )

    async def publish_ready_answers(
        self,
        *,
        project_id: str,
        document_id: str,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> JsonObject:
        from src.application.services.knowledge_ready_answer_publication_service import (
            KnowledgeReadyAnswerPublicationService,
        )

        return await KnowledgeReadyAnswerPublicationService(
            self.pool
        ).publish_ready_answers(
            project_id=project_id,
            document_id=document_id,
            knowledge_repo_factory=knowledge_repo_factory,
            logger=logger,
        )

    async def retry_failed_batches(
        self,
        *,
        project_id: str,
        document_id: str,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort,
        logger: LoggerPort,
    ) -> JsonObject:
        from src.application.services.knowledge_failed_batch_retry_service import (
            KnowledgeFailedBatchRetryService,
        )

        return await KnowledgeFailedBatchRetryService(self.pool).retry_failed_batches(
            project_id=project_id,
            document_id=document_id,
            knowledge_repo_factory=knowledge_repo_factory,
            model_usage_repo_factory=model_usage_repo_factory,
            preprocessor_factory=preprocessor_factory,
            logger=logger,
        )

    async def _process_document_faq_surface(
        self,
        *args: object,
        **kwargs: object,
    ) -> KnowledgeDocumentProcessingResult:
        raise KnowledgePreprocessingValidationError(
            "Bootstrap FAQ surface path was removed from the primary pipeline. "
            "FAQ uploads must use KnowledgeSurfaceCompilerPort.compile_surfaces via "
            "KnowledgeFaqSurfaceIngestionService."
        )

    async def process_document(
        self,
        *,
        project_id: str,
        document_id: str,
        file_name: str,
        chunks: list[JsonObject],
        mode: KnowledgePreprocessingMode,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort | None,
        logger: LoggerPort,
        commercial_price_repo_factory: CommercialPriceRepositoryFactoryPort
        | None = None,
        commercial_price_acquisition_service_factory: CommercialPriceAcquisitionServiceFactoryPort
        | None = None,
    ) -> KnowledgeDocumentProcessingResult:
        if mode == MODE_FAQ:
            raise KnowledgePreprocessingValidationError(
                "Bootstrap FAQ surface path was removed from the primary pipeline. "
                "FAQ uploads must use KnowledgeSurfaceCompilerPort.compile_surfaces."
            )

        from src.application.ports.knowledge.structured_ingestion import (
            KnowledgeStructuredIngestionRepositoryFactoryPort,
        )
        from src.application.services.knowledge_structured_ingestion_service import (
            KnowledgeStructuredIngestionService,
        )

        structured_knowledge_repo_factory = cast(
            KnowledgeStructuredIngestionRepositoryFactoryPort,
            knowledge_repo_factory,
        )

        return await KnowledgeStructuredIngestionService(self.pool).process_document(
            project_id=project_id,
            document_id=document_id,
            file_name=file_name,
            chunks=chunks,
            mode=mode,
            knowledge_repo_factory=structured_knowledge_repo_factory,
            model_usage_repo_factory=model_usage_repo_factory,
            preprocessor_factory=preprocessor_factory,
            logger=logger,
            commercial_price_repo_factory=commercial_price_repo_factory,
            commercial_price_acquisition_service_factory=commercial_price_acquisition_service_factory,
        )
