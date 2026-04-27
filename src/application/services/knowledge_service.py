from collections.abc import Mapping

from src.application.dto.knowledge_dto import KnowledgeUploadResultDto
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
    KnowledgeProjectAccessPort,
    KnowledgeRepositoryFactoryPort,
    PlatformUserAdminPort,
)
from src.application.ports.logger_port import LoggerPort
from src.domain.project_plane.json_types import JsonObject


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
        file_content: bytes,
        authorization: str | None,
        *,
        chunker_factory: KnowledgeChunkerFactoryPort,
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> KnowledgeUploadResultDto:
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

        await self._create_and_process_document(
            project_id=project_id,
            file_name=normalized_file_name,
            file_size=len(file_content),
            uploaded_by=uploaded_by,
            chunks=chunks,
            knowledge_repo_factory=knowledge_repo_factory,
            logger=logger,
        )

        logger.info(
            f"Successfully uploaded {len(chunks)} chunks to project {project_id}"
        )
        return KnowledgeUploadResultDto.create(
            message=f"Uploaded {len(chunks)} chunks", chunks=len(chunks)
        )

    async def _ensure_project_exists(self, project_id: str, logger: LoggerPort) -> None:
        if await self.project_repo.project_exists(project_id):
            return

        logger.warning(f"Project {project_id} not found")
        raise NotFoundError("Project not found")

    async def _extract_chunks(
        self,
        file_content: bytes,
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

    async def _create_and_process_document(
        self,
        *,
        project_id: str,
        file_name: str,
        file_size: int,
        uploaded_by: str,
        chunks: list[JsonObject],
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> str:
        repo = knowledge_repo_factory(self.pool)
        document_id = await repo.create_document(
            project_id=project_id,
            file_name=file_name,
            file_size=file_size,
            uploaded_by=uploaded_by,
        )

        try:
            await repo.add_knowledge_batch(project_id, chunks, document_id=document_id)
            await repo.update_document_status(document_id, "processed")
        except Exception as exc:
            logger.exception(
                "Knowledge upload processing failed",
                extra={"project_id": project_id, "document_id": document_id},
            )
            await repo.update_document_status(document_id, "error", str(exc))
            raise

        return str(document_id)


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


def _normalize_chunks(raw_chunks: list[object]) -> list[JsonObject]:
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

    return {str(key): item for key, item in value.items()}
