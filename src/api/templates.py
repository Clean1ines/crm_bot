from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from src.api.dependencies import get_template_repo, get_project_repo, verify_admin_token
from src.database.repositories.template_repository import TemplateRepository
from src.database.repositories.project_repository import ProjectRepository
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: Optional[str]
    version: int
    is_active: bool


@router.get("", response_model=List[TemplateResponse], dependencies=[Depends(verify_admin_token)])
async def list_templates(repo: TemplateRepository = Depends(get_template_repo)):
    return await repo.get_active_templates()


class ApplyTemplateRequest(BaseModel):
    template_slug: str


@router.post("/projects/{project_id}/apply", dependencies=[Depends(verify_admin_token)])
async def apply_template(
    project_id: str,
    data: ApplyTemplateRequest,
    template_repo: TemplateRepository = Depends(get_template_repo),
    project_repo: ProjectRepository = Depends(get_project_repo)
):
    """Применяет шаблон к проекту."""
    if not await project_repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    template = await template_repo.get_by_slug(data.template_slug)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    await project_repo.apply_template(project_id, data.template_slug)
    return {"status": "applied", "template_slug": data.template_slug}