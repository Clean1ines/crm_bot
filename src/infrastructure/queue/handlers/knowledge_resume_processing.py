from collections.abc import Mapping

import asyncpg

from src.application.services.knowledge_ingestion_service import KnowledgeIngestionService
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_exceptions import PermanentJobError

logger = get_logger(__name__)


async def handle_resume_knowledge_processing(job: Mapping[str, object], *, db_pool: asyncpg.Pool) -> None:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("Job payload must be an object")

    project_id = str(payload.get("project_id") or "").strip()
    document_id = str(payload.get("document_id") or "").strip()
    if not project_id or not document_id:
        raise PermanentJobError("Missing project_id or document_id")

    service = KnowledgeIngestionService(db_pool)
    await service.resume_processing(
        project_id=project_id,
        document_id=document_id,
        knowledge_repo_factory=KnowledgeRepository,
        logger=logger,
    )
