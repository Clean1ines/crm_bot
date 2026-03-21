from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from uuid import UUID
from typing import List, Optional

from src.api.dependencies import get_project_repo, verify_admin_token
from src.database.repositories.project_repository import ProjectRepository
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    is_pro_mode: bool
    template_slug: Optional[str]
    managers: List[int]  # список chat_id менеджеров
    # токены не возвращаем для безопасности


@router.get("", response_model=List[ProjectResponse], dependencies=[Depends(verify_admin_token)])
async def list_projects(repo: ProjectRepository = Depends(get_project_repo)):
    """Возвращает список всех проектов."""
    # Метод `get_all_projects` нужно добавить в ProjectRepository, если его нет
    projects = await repo.get_all_projects()
    # Для каждого проекта подгружаем менеджеров (если не включены в базовом запросе)
    for p in projects:
        p["managers"] = await repo.get_managers(p["id"])
    return projects


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_admin_token)])
async def create_project(data: ProjectCreate, repo: ProjectRepository = Depends(get_project_repo)):
    """Создаёт новый проект."""
    # В ProjectRepository должен быть метод create_project(owner_id, name, description)
    # owner_id нужно брать из текущего пользователя (админ). Можно передать фиксированный ID или получить из токена.
    # Для простоты используем owner_id=1 (админ). В реальном приложении – из аутентификации.
    project_id = await repo.create_project(owner_id=1, name=data.name, description=data.description)
    project = await repo.get_project_by_id(project_id)  # метод должен существовать
    project["managers"] = await repo.get_managers(project_id)
    return project


@router.get("/{project_id}", response_model=ProjectResponse, dependencies=[Depends(verify_admin_token)])
async def get_project(project_id: str, repo: ProjectRepository = Depends(get_project_repo)):
    project = await repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project["managers"] = await repo.get_managers(project_id)
    return project


@router.put("/{project_id}", response_model=ProjectResponse, dependencies=[Depends(verify_admin_token)])
async def update_project(project_id: str, data: ProjectUpdate, repo: ProjectRepository = Depends(get_project_repo)):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    await repo.update_project(project_id, data.name, data.description)
    project = await repo.get_project_by_id(project_id)
    project["managers"] = await repo.get_managers(project_id)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_admin_token)])
async def delete_project(project_id: str, repo: ProjectRepository = Depends(get_project_repo)):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    await repo.delete_project(project_id)


class BotTokenRequest(BaseModel):
    token: str


@router.post("/{project_id}/bot-token", status_code=200, dependencies=[Depends(verify_admin_token)])
async def set_bot_token(project_id: str, data: BotTokenRequest, repo: ProjectRepository = Depends(get_project_repo)):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    await repo.set_bot_token(project_id, data.token)
    # При желании можно сразу настроить вебхук (вызов Telegram API)
    return {"status": "ok"}


@router.post("/{project_id}/manager-token", status_code=200, dependencies=[Depends(verify_admin_token)])
async def set_manager_token(project_id: str, data: BotTokenRequest, repo: ProjectRepository = Depends(get_project_repo)):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    await repo.set_manager_bot_token(project_id, data.token)
    return {"status": "ok"}


@router.get("/{project_id}/managers", response_model=List[int], dependencies=[Depends(verify_admin_token)])
async def get_managers(project_id: str, repo: ProjectRepository = Depends(get_project_repo)):
    return await repo.get_managers(project_id)


class ManagerAddRequest(BaseModel):
    chat_id: int


@router.post("/{project_id}/managers", status_code=201, dependencies=[Depends(verify_admin_token)])
async def add_manager(project_id: str, data: ManagerAddRequest, repo: ProjectRepository = Depends(get_project_repo)):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    await repo.add_manager(project_id, data.chat_id)
    return {"status": "added"}


@router.delete("/{project_id}/managers/{chat_id}", status_code=204, dependencies=[Depends(verify_admin_token)])
async def remove_manager(project_id: str, chat_id: int, repo: ProjectRepository = Depends(get_project_repo)):
    if not await repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    await repo.remove_manager(project_id, chat_id)
    return None