from __future__ import annotations

from typing import cast

import asyncpg
import jwt

from src.application.dto.knowledge_dto import (
    KnowledgeUploadRequestDto,
    KnowledgeUploadResultDto,
)
from src.application.ports.knowledge_port import (
    JwtDecoderPort,
    KnowledgeChunkerPort,
    KnowledgeDbPoolPort,
    KnowledgePreprocessorPort,
    KnowledgeProjectAccessPort,
    KnowledgeQueuePort,
    KnowledgeRepositoryPort,
    PlatformUserAdminPort,
)
from src.application.ports.logger_port import LoggerPort
from src.application.services.knowledge_service import (
    KnowledgeService,
    KnowledgeServiceConfig,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.llm.chunker import ChunkerService
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor
from src.infrastructure.queue.job_types import TASK_PROCESS_KNOWLEDGE_UPLOAD


jwt_decoder: JwtDecoderPort = cast(JwtDecoderPort, jwt)


def make_chunker() -> KnowledgeChunkerPort:
    return cast(KnowledgeChunkerPort, ChunkerService())


def make_knowledge_repo(pool: KnowledgeDbPoolPort) -> KnowledgeRepositoryPort:
    return cast(KnowledgeRepositoryPort, KnowledgeRepository(cast(asyncpg.Pool, pool)))


def make_knowledge_preprocessor() -> KnowledgePreprocessorPort:
    return cast(KnowledgePreprocessorPort, GroqKnowledgePreprocessor())


def build_knowledge_service(
    *,
    pool: KnowledgeDbPoolPort,
    project_repo: KnowledgeProjectAccessPort,
    user_repo: PlatformUserAdminPort,
) -> KnowledgeService:
    return KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )


async def upload_knowledge_file(
    *,
    pool: KnowledgeDbPoolPort,
    project_repo: KnowledgeProjectAccessPort,
    user_repo: PlatformUserAdminPort,
    queue_repo: KnowledgeQueuePort,
    project_id: str,
    file_name: str | None,
    file_content: bytes | bytearray,
    authorization: str | None,
    uploaded_by_user_id: str | None,
    trusted_upload: bool,
    preprocessing_mode: str,
    logger: LoggerPort,
) -> KnowledgeUploadResultDto:
    service = build_knowledge_service(
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    return await service.upload(
        project_id,
        file_name,
        file_content,
        authorization,
        chunker_factory=make_chunker,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
        queue_repo=queue_repo,
        knowledge_upload_task_type=TASK_PROCESS_KNOWLEDGE_UPLOAD,
        upload_request=KnowledgeUploadRequestDto(
            preprocessing_mode=preprocessing_mode,
        ),
        preprocessor_factory=make_knowledge_preprocessor,
        uploaded_by_user_id=uploaded_by_user_id,
        trusted_upload=trusted_upload,
    )


async def upload_platform_admin_knowledge_file(
    *,
    pool: asyncpg.Pool,
    project_id: str,
    file_name: str | None,
    file_content: bytes | bytearray,
    logger: LoggerPort,
) -> KnowledgeUploadResultDto:
    return await upload_knowledge_file(
        pool=cast(KnowledgeDbPoolPort, pool),
        project_repo=cast(KnowledgeProjectAccessPort, ProjectRepository(pool)),
        user_repo=cast(PlatformUserAdminPort, UserRepository(pool)),
        queue_repo=cast(KnowledgeQueuePort, QueueRepository(pool)),
        project_id=project_id,
        file_name=file_name,
        file_content=file_content,
        authorization=None,
        uploaded_by_user_id=None,
        trusted_upload=True,
        preprocessing_mode="plain",
        logger=logger,
    )
