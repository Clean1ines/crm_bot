from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from pydantic import BaseModel
from uuid import UUID
from typing import List, Optional

from src.api.dependencies import (
    get_project_repo,
    get_current_user_id,
    verify_admin_token
)
from src.database.repositories.project_repository import ProjectRepository
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    

class ProjectResponse(BaseModel):
    id: str
    name: str
    is_pro_mode: bool
    template_slug: Optional[str]
    managers: List[int]
    user_id: Optional[str]


class BotTokenRequest(BaseModel):
    token: str


class ManagerAddRequest(BaseModel):
    chat_id: int

class BotConnectRequest(BaseModel):
    token: str
    type: str  # 'client' | 'manager'


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    """Возвращает список проектов текущего пользователя."""
    projects = await repo.get_projects_by_user_id(current_user_id)
    for p in projects:
        p["managers"] = await repo.get_managers(p["id"])
    return projects


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    """Создаёт новый проект для текущего пользователя."""
    project_id = await repo.create_project_with_user_id(current_user_id, data.name)
    project = await repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=500, detail="Project creation failed")
    project["managers"] = await repo.get_managers(project_id)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    project = await repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Ensure user owns the project (via user_id)
    if project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    project["managers"] = await repo.get_managers(project_id)
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    # Check ownership
    project = await repo.get_project_by_id(project_id)
    if project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    await repo.update_project(project_id, data.name)
    updated = await repo.get_project_by_id(project_id)
    updated["managers"] = await repo.get_managers(project_id)
    return updated


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    # Check ownership
    project = await repo.get_project_by_id(project_id)
    if project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    await repo.delete_project(project_id)


@router.post("/{project_id}/bot-token")
async def set_bot_token(
    project_id: str,
    data: BotTokenRequest,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    # Check ownership
    project = await repo.get_project_by_id(project_id)
    if project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    await repo.set_bot_token(project_id, data.token)
    return {"status": "ok"}


@router.post("/{project_id}/manager-token")
async def set_manager_token(
    project_id: str,
    data: BotTokenRequest,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    # Check ownership
    project = await repo.get_project_by_id(project_id)
    if project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    await repo.set_manager_bot_token(project_id, data.token)
    return {"status": "ok"}


@router.get("/{project_id}/managers", response_model=List[int])
async def get_managers(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    # Check ownership
    project = await repo.get_project_by_id(project_id)
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return await repo.get_managers(project_id)


@router.post("/{project_id}/managers", status_code=201)
async def add_manager(
    project_id: str,
    data: ManagerAddRequest,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    # Check ownership
    project = await repo.get_project_by_id(project_id)
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    await repo.add_manager(project_id, str(data.chat_id))
    return {"status": "added"}


@router.delete("/{project_id}/managers/{chat_id}", status_code=204)
async def remove_manager(
    project_id: str,
    chat_id: int,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    # Check ownership
    project = await repo.get_project_by_id(project_id)
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    await repo.remove_manager(project_id, str(chat_id))
    return None

@router.post("/{project_id}/connect-bot")
async def connect_bot(
    project_id: str,
    data: BotConnectRequest,
    current_user_id: str = Depends(get_current_user_id),
    repo: ProjectRepository = Depends(get_project_repo),
):
    """Универсальный эндпоинт для подключения ботов (как в ТГ боте)."""
    # Проверка прав собственности
    project = await repo.get_project_by_id(project_id)
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if data.type == "client":
        await repo.set_bot_token(project_id, data.token)
    elif data.type == "manager":
        await repo.set_manager_bot_token(project_id, data.token)
    else:
        raise HTTPException(status_code=400, detail="Invalid bot type")
        
    return {"status": "ok", "type": data.type}
