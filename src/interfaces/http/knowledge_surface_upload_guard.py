from __future__ import annotations

import asyncpg
from fastapi import Depends, File, Form, Header, HTTPException, UploadFile

from src.application.ports.knowledge_port import (
    KnowledgeProjectAccessPort,
    KnowledgeQueuePort,
    PlatformUserAdminPort,
)
from src.interfaces.http import knowledge as legacy_knowledge
from src.interfaces.http.dependencies import (
    get_pool,
    get_project_repo,
    get_queue_repo,
    get_user_repository,
)
from src.interfaces.http.knowledge_surface import (
    router as surface_router,
    upload_knowledge_surface_aware,
)


@surface_router.post("", include_in_schema=False)
async def upload_knowledge_surface_read_guard(
    project_id: str,
    file: UploadFile = File(...),
    preprocessing_mode: str = Form(default="plain"),
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    queue_repo: KnowledgeQueuePort = Depends(get_queue_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    try:
        return await upload_knowledge_surface_aware(
            project_id=project_id,
            file=file,
            preprocessing_mode=preprocessing_mode,
            authorization=authorization,
            pool=pool,
            project_repo=project_repo,
            queue_repo=queue_repo,
            user_repo=user_repo,
        )
    except Exception as exc:
        if "read" not in str(exc).lower():
            raise
        legacy_knowledge.logger.error(f"Failed to read uploaded file: {exc}")
        raise HTTPException(status_code=400, detail="Could not read file") from exc


if surface_router.routes:
    surface_router.routes.insert(0, surface_router.routes.pop())
