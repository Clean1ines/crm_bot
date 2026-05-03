from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from src.application.dto.knowledge_dto import (
    KnowledgePreviewRequestDto,
    KnowledgePreviewResponseDto,
    KnowledgeUploadJobPayloadDto,
    KnowledgeUploadRequestDto,
    KnowledgeUploadResultDto,
)
from src.application.dto.model_usage_dto import ModelUsageSummaryDto
from src.application.errors import (
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from src.application.ports.knowledge_port import (
    JwtDecoderPort,
    KnowledgeChunkerFactoryPort,
    KnowledgeDbPoolPort,
    ModelUsageRepositoryFactoryPort,
    KnowledgePreprocessorFactoryPort,
    KnowledgeProjectAccessPort,
    KnowledgeQueuePort,
    KnowledgeRepositoryFactoryPort,
    PlatformUserAdminPort,
)
from src.application.ports.logger_port import LoggerPort
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_PLAIN,
    PREPROCESSING_STATUS_NOT_REQUESTED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingValidationError,
)
from src.infrastructure.config.settings import settings


BEARER_PREFIX = "Bearer "
UPLOAD_FALLBACK_NAME = "upload"


class KnowledgeService:
    def __init__(
        self,
        project_repo: KnowledgeProjectAccessPort,
        user_repo: PlatformUserAdminPort,
        pool: KnowledgeDbPoolPort,
        jwt_secret: str,
        jwt_module: JwtDecoderPort,
    ) -> None:
        self.project_repo = project_repo
        self.user_repo = user_repo
        self.pool = pool
        self.jwt_secret = jwt_secret
        self.jwt = jwt_module

    async def require_access(self, project_id: str, authorization: str | None) -> str:
        user_id = self._user_id_from_authorization(authorization)
        if await self._has_project_admin_access(project_id, user_id):
            return user_id

        raise ForbiddenError("Insufficient permissions")

    def _user_id_from_authorization(self, authorization: str | None) -> str:
        token = _extract_bearer_token(authorization)
        return self._user_id_from_token(token)

    def _user_id_from_token(self, token: str) -> str:
        try:
            payload = self.jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            return _subject_from_payload(payload)
        except self.jwt.ExpiredSignatureError:
            raise UnauthorizedError("Token expired") from None
        except (self.jwt.InvalidTokenError, ValueError):
            raise UnauthorizedError("Invalid token") from None

    async def _has_project_admin_access(self, project_id: str, user_id: str) -> bool:
        if await self.user_repo.is_platform_admin(user_id):
            return True

        has_role = await self.project_repo.user_has_project_role(
            project_id,
            user_id,
            ["owner", "admin"],
        )
        return has_role is True or await self._owns_project(project_id, user_id)

    async def _owns_project(self, project_id: str, user_id: str) -> bool:
        project_view = await self.project_repo.get_project_view(project_id)
        return bool(project_view and str(project_view.user_id) == user_id)

    async def upload(
        self,
        project_id: str,
        file_name: str | None,
        file_content: bytes | bytearray,
        authorization: str | None,
        *,
        chunker_factory: KnowledgeChunkerFactoryPort,
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
        logger: LoggerPort,
        queue_repo: KnowledgeQueuePort,
        knowledge_upload_task_type: str,
        upload_request: KnowledgeUploadRequestDto | None = None,
        preprocessor_factory: KnowledgePreprocessorFactoryPort | None = None,
    ) -> KnowledgeUploadResultDto:
        try:
            mode = (
                upload_request or KnowledgeUploadRequestDto()
            ).normalized_preprocessing_mode()
        except KnowledgePreprocessingValidationError as exc:
            raise ValidationError(str(exc)) from None

        if mode != MODE_PLAIN and preprocessor_factory is None:
            raise ValidationError(
                "Knowledge preprocessing adapter is required for non-plain upload modes"
            )

        uploaded_by = await self.require_access(project_id, authorization)
        normalized_file_name = file_name or UPLOAD_FALLBACK_NAME
        logger.info(
            f"Knowledge upload requested for project {project_id}, file: {normalized_file_name}"
        )

        await self._ensure_project_exists(project_id, logger)

        chunks = await self._extract_chunks(
            file_content,
            normalized_file_name,
            chunker_factory=chunker_factory,
            logger=logger,
        )
        if not chunks:
            logger.warning("No text extracted from file")
            return KnowledgeUploadResultDto.create(
                message="No text extracted", chunks=0
            )

        repo = knowledge_repo_factory(self.pool)
        document_id = await repo.create_document(
            project_id=project_id,
            file_name=normalized_file_name,
            file_size=len(file_content),
            uploaded_by=uploaded_by,
        )

        await repo.update_document_status(document_id, "processing")

        if mode != MODE_PLAIN:
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_PROCESSING,
            )

        job_payload = KnowledgeUploadJobPayloadDto(
            project_id=project_id,
            document_id=document_id,
            file_name=normalized_file_name,
            preprocessing_mode=mode,
            chunks=chunks,
        )

        try:
            await queue_repo.enqueue(
                knowledge_upload_task_type,
                payload=job_payload.to_dict(),
            )
        except Exception as exc:
            logger.exception(
                "Knowledge upload enqueue failed",
                extra={"project_id": project_id, "document_id": document_id},
            )
            await repo.update_document_status(document_id, "error", str(exc))
            raise

        preprocessing_status = (
            PREPROCESSING_STATUS_NOT_REQUESTED
            if mode == MODE_PLAIN
            else PREPROCESSING_STATUS_PROCESSING
        )
        logger.info("Knowledge upload queued", extra={"document_id": document_id})
        return KnowledgeUploadResultDto.create(
            message=f"Queued {len(chunks)} chunks for processing",
            chunks=len(chunks),
            document_id=document_id,
            preprocessing_mode=mode,
            preprocessing_status=preprocessing_status,
            structured_entries=0,
        )

    async def preview_query(
        self,
        project_id: str,
        request: KnowledgePreviewRequestDto,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> KnowledgePreviewResponseDto:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        query = request.normalized_question()
        if not query:
            return KnowledgePreviewResponseDto.empty(query=query)

        repo = knowledge_repo_factory(self.pool)
        results = await repo.preview_search(
            project_id=project_id,
            query=query,
            limit=request.normalized_limit(),
        )

        logger.info(
            "Knowledge preview search completed",
            extra={"project_id": project_id, "result_count": len(results)},
        )
        return KnowledgePreviewResponseDto.from_results(query=query, results=results)

    async def clear_project_knowledge(
        self,
        project_id: str,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> None:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        repo = knowledge_repo_factory(self.pool)
        await repo.clear_project_knowledge(project_id)
        logger.info(
            "Knowledge base cleared",
            extra={"project_id": project_id},
        )

    async def usage(
        self,
        project_id: str,
        authorization: str | None,
        *,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
    ) -> ModelUsageSummaryDto:
        await self.require_access(project_id, authorization)
        if not await self.project_repo.project_exists(project_id):
            raise NotFoundError("Project not found")

        monthly_budget_tokens = max(
            int(settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET),
            int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
        )
        if not settings.MODEL_USAGE_COUNTER_ENABLED:
            return ModelUsageSummaryDto.disabled(
                monthly_budget_tokens=monthly_budget_tokens
            )

        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        repo = model_usage_repo_factory(self.pool)
        summary = await repo.get_project_usage_summary(
            project_id=project_id,
            month_start_utc=month_start,
            month_end_utc=month_end,
            today_start_utc=today_start,
            monthly_budget_tokens=monthly_budget_tokens,
        )
        return ModelUsageSummaryDto.from_view(summary, counter_enabled=True)

    async def _ensure_project_exists(self, project_id: str, logger: LoggerPort) -> None:
        if await self.project_repo.project_exists(project_id):
            return

        logger.warning(f"Project {project_id} not found")
        raise NotFoundError("Project not found")

    async def _extract_chunks(
        self,
        file_content: bytes | bytearray,
        file_name: str,
        *,
        chunker_factory: KnowledgeChunkerFactoryPort,
        logger: LoggerPort,
    ) -> list[JsonObject]:
        chunker = chunker_factory()
        try:
            raw_chunks = await chunker.process_file(file_content, file_name)
        except ValueError as exc:
            logger.error(f"Chunking failed: {exc}")
            raise ValidationError(str(exc)) from None

        return _normalize_chunks(raw_chunks)


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise UnauthorizedError("Authorization header required")

    if not authorization.startswith(BEARER_PREFIX):
        raise UnauthorizedError("Invalid token format. Use 'Bearer <token>'")

    return authorization[len(BEARER_PREFIX) :]


def _subject_from_payload(payload: object) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError("Invalid token payload")

    user_id = str(payload.get("sub") or "")
    if not user_id:
        raise ValueError("Missing subject claim")

    return user_id


def _normalize_chunks(raw_chunks: Sequence[object]) -> list[JsonObject]:
    chunks: list[JsonObject] = []
    for chunk in raw_chunks:
        normalized = _normalize_chunk(chunk)
        if normalized is not None:
            chunks.append(normalized)

    return chunks


def _normalize_chunk(chunk: object) -> JsonObject | None:
    if isinstance(chunk, str):
        return _chunk_from_text(chunk)

    if isinstance(chunk, Mapping):
        return _chunk_from_mapping(chunk)

    return None


def _chunk_from_text(value: str) -> JsonObject | None:
    content = value.strip()
    return {"content": content} if content else None


def _chunk_from_mapping(value: Mapping[object, object]) -> JsonObject | None:
    content = str(value.get("content") or "").strip()
    if not content:
        return None

    return {str(key): json_value_from_unknown(item) for key, item in value.items()}
