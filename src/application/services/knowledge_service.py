from src.application.dto.knowledge_dto import KnowledgeUploadResultDto
from src.application.errors import (
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


class KnowledgeService:
    def __init__(self, project_repo, user_repo, pool, jwt_secret: str, jwt_module) -> None:
        self.project_repo = project_repo
        self.user_repo = user_repo
        self.pool = pool
        self.jwt_secret = jwt_secret
        self.jwt = jwt_module

    async def require_access(self, project_id: str, authorization: str | None) -> str:
        if not authorization:
            raise UnauthorizedError("Authorization header required")

        if not authorization.startswith("Bearer "):
            raise UnauthorizedError("Invalid token format. Use 'Bearer <token>'")

        token = authorization[7:]
        try:
            payload = self.jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            user_id = str(payload.get("sub") or "")
            if not user_id:
                raise ValueError("Missing subject claim")
        except self.jwt.ExpiredSignatureError:
            raise UnauthorizedError("Token expired") from None
        except (self.jwt.InvalidTokenError, ValueError):
            raise UnauthorizedError("Invalid token") from None

        if await self.user_repo.is_platform_admin(user_id):
            return user_id

        has_access = await self.project_repo.user_has_project_role(project_id, user_id, ["owner", "admin"])
        if has_access is not True:
            project_view = await self.project_repo.get_project_view(project_id)
            if not project_view or str(project_view.user_id) != user_id:
                raise ForbiddenError("Insufficient permissions")

        return user_id

    async def upload(
        self,
        project_id: str,
        file_name: str | None,
        file_content: bytes,
        authorization: str | None,
        *,
        chunker_factory,
        knowledge_repo_factory,
        logger,
    ) -> KnowledgeUploadResultDto:
        uploaded_by = await self.require_access(project_id, authorization)
        normalized_file_name = file_name or "upload"
        logger.info(f"Knowledge upload requested for project {project_id}, file: {normalized_file_name}")

        exists = await self.project_repo.project_exists(project_id)
        if not exists:
            logger.warning(f"Project {project_id} not found")
            raise NotFoundError("Project not found")

        chunker = chunker_factory()
        try:
            chunks = await chunker.process_file(file_content, normalized_file_name)
        except ValueError as e:
            logger.error(f"Chunking failed: {e}")
            raise ValidationError(str(e))

        if not chunks:
            logger.warning("No text extracted from file")
            return KnowledgeUploadResultDto.create(message="No text extracted", chunks=0)

        async with self.pool.acquire() as conn:
            repo = knowledge_repo_factory(conn)
            document_id = await repo.create_document(
                project_id=project_id,
                file_name=normalized_file_name,
                file_size=len(file_content),
                uploaded_by=uploaded_by,
            )
            await repo.add_knowledge_batch(project_id, chunks, document_id=document_id)

        logger.info(f"Successfully uploaded {len(chunks)} chunks to project {project_id}")
        return KnowledgeUploadResultDto.create(message=f"Uploaded {len(chunks)} chunks", chunks=len(chunks))
