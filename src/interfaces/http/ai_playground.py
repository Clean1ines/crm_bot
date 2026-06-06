from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from src.application.ai_playground.contracts import (
    AiPlaygroundRunRequest,
    AiPlaygroundRunResponse,
)
from src.application.ai_playground.run_ai_playground import (
    AiPlaygroundValidationError,
    RunAiPlaygroundService,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.composition.ai_playground import make_run_ai_playground_service
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_project_repo,
    get_user_repository,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/ai-playground",
    tags=["ai-playground"],
)


async def _maybe_await(value: object) -> object:
    import inspect

    if inspect.isawaitable(value):
        return await value
    return value


async def _project_exists(project_repo: object, project_id: str) -> bool:
    project_exists = getattr(project_repo, "project_exists", None)
    if project_exists is not None:
        return bool(await _maybe_await(project_exists(project_id)))

    get_project_view = getattr(project_repo, "get_project_view", None)
    if get_project_view is not None:
        return await _maybe_await(get_project_view(project_id)) is not None

    return True


async def _user_is_platform_admin(
    user_repo: UserRepository,
    user_id: str,
) -> bool:
    is_platform_admin = getattr(user_repo, "is_platform_admin", None)
    if is_platform_admin is None:
        return False
    return bool(await _maybe_await(is_platform_admin(user_id)))


async def _user_has_project_role(
    project_repo: object,
    *,
    project_id: str,
    user_id: str,
) -> bool:
    user_has_project_role = getattr(project_repo, "user_has_project_role", None)
    if user_has_project_role is None:
        return False

    allowed_roles = ("owner", "admin", "manager")

    try:
        return bool(
            await _maybe_await(
                user_has_project_role(project_id, user_id, allowed_roles)
            )
        )
    except TypeError:
        return bool(
            await _maybe_await(
                user_has_project_role(
                    project_id=project_id,
                    user_id=user_id,
                    allowed_roles=allowed_roles,
                )
            )
        )


async def _require_project_access(
    *,
    project_id: str,
    authorization: str | None,
    project_repo: object,
    user_repo: UserRepository,
) -> None:
    current_user_id = await get_current_user_id(authorization)

    if not await _project_exists(project_repo, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    if await _user_is_platform_admin(user_repo, current_user_id):
        return

    if await _user_has_project_role(
        project_repo,
        project_id=project_id,
        user_id=current_user_id,
    ):
        return

    raise HTTPException(status_code=403, detail="Insufficient permissions")


def get_ai_playground_service() -> RunAiPlaygroundService:
    return make_run_ai_playground_service()


@router.post("/run", response_model=AiPlaygroundRunResponse)
async def run_ai_playground(
    project_id: str,
    payload: AiPlaygroundRunRequest,
    authorization: str | None = Header(default=None),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
    service: RunAiPlaygroundService = Depends(get_ai_playground_service),
) -> AiPlaygroundRunResponse:
    if not settings.ENABLE_AI_PLAYGROUND:
        raise HTTPException(status_code=404, detail="Not found")

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    try:
        return await service.run(payload)
    except AiPlaygroundValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
