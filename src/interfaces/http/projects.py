from typing import cast
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from src.interfaces.http.dependencies import (
    get_project_command_service,
    get_project_query_service,
    get_current_user_id,
    get_project_repo,
    get_project_service,
    get_user_repository,
)
from src.infrastructure.logging.logger import get_logger
from src.application.services.project_command_service import ProjectCommandService
from src.application.services.project_query_service import ProjectQueryService
from src.application.services.project_invitation_service import ProjectInvitationService
from src.infrastructure.config.settings import settings
from src.infrastructure.email.sender import build_email_sender

logger = get_logger(__name__)


class ManagerReplyHistoryItemResponse(BaseModel):
    id: int
    thread_id: str
    project_id: str
    manager_user_id: str
    text: str
    manager_display_name: str | None = None
    manager_chat_id: str | None = None
    created_at: str | None = None


class ManagerReplyHistoryResponse(BaseModel):
    items: list[ManagerReplyHistoryItemResponse]
    limit: int
    offset: int


router = APIRouter(prefix="/api/projects", tags=["projects"])


def _frontend_invite_base_url() -> str:
    return (
        settings.FRONTEND_URL
        or settings.VITE_API_URL
        or settings.PUBLIC_URL
        or settings.RENDER_EXTERNAL_URL
        or ""
    )


def build_project_invitation_service(
    project_repo=Depends(get_project_repo),
    access_service=Depends(get_project_service),
    user_repo=Depends(get_user_repository),
) -> ProjectInvitationService:
    return ProjectInvitationService(
        project_repo=project_repo,
        access_service=access_service,
        user_repo=user_repo,
        email_sender=build_email_sender(settings),
        frontend_url=_frontend_invite_base_url(),
    )


class ProjectCreate(BaseModel):
    name: str


class ProjectUpdate(BaseModel):
    name: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    is_pro_mode: bool
    user_id: str | None
    client_bot_username: str | None = None
    manager_bot_username: str | None = None
    access_role: str | None = None


class BotTokenRequest(BaseModel):
    token: str


class ManagerAddRequest(BaseModel):
    chat_id: int


class BotConnectRequest(BaseModel):
    token: str
    type: str  # 'client' | 'manager'


class ProjectMemberUpsertRequest(BaseModel):
    user_id: str
    role: str


class ProjectInvitationCreateRequest(BaseModel):
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str = "manager"


class ProjectInvitationAcceptRequest(BaseModel):
    token: str


class ProjectInvitationResponse(BaseModel):
    status: str
    project_id: str
    email: str
    role: str
    expires_at: str
    delivery: str
    invite_link: str | None = None


class ProjectInvitationAcceptResponse(BaseModel):
    status: str
    project_id: str
    user_id: str
    email: str
    role: str


class ProjectSettingsUpdate(BaseModel):
    brand_name: str | None = None
    industry: str | None = None
    tone_of_voice: str | None = None
    default_language: str | None = None
    target_language: str | None = None
    default_timezone: str | None = None
    system_prompt_override: str | None = None


class ProjectPoliciesUpdate(BaseModel):
    escalation_policy_json: dict[str, object] | None = None
    routing_policy_json: dict[str, object] | None = None
    crm_policy_json: dict[str, object] | None = None
    response_policy_json: dict[str, object] | None = None
    privacy_policy_json: dict[str, object] | None = None


class ProjectLimitProfileUpdate(BaseModel):
    monthly_token_limit: int | None = None
    requests_per_minute: int | None = None
    max_concurrent_threads: int | None = None
    priority: int | None = None
    fallback_model: str | None = None


class ProjectIntegrationUpsert(BaseModel):
    provider: str
    status: str = "disabled"
    config_json: dict[str, object] | None = None
    credentials_encrypted: str | None = None


class ProjectChannelUpsert(BaseModel):
    kind: str
    provider: str
    status: str = "disabled"
    config_json: dict[str, object] | None = None


class ProjectIntegrationResponse(BaseModel):
    provider: str
    status: str | None = None
    config_json: dict[str, object] | None = None
    credentials_encrypted: str | None = None


class ProjectChannelResponse(BaseModel):
    kind: str
    provider: str
    status: str | None = None
    config_json: dict[str, object] | None = None


class ProjectPromptVersionResponse(BaseModel):
    version: int | None = None
    prompt_bundle: dict[str, object] | None = None
    is_active: bool | None = None
    created_at: str | None = None


class ProjectConfigurationResponse(BaseModel):
    project_id: str
    settings: dict[str, object]
    policies: dict[str, object]
    limit_profile: dict[str, object]
    integrations: list[ProjectIntegrationResponse]
    channels: list[ProjectChannelResponse]
    prompt_versions: list[ProjectPromptVersionResponse]


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    current_user_id: str = Depends(get_current_user_id),
    project_queries: ProjectQueryService = Depends(get_project_query_service),
):
    """Возвращает список проектов текущего пользователя."""
    return await project_queries.list_projects(current_user_id)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    """Создаёт новый проект для текущего пользователя."""
    return await project_commands.create_project(current_user_id, data.name)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_queries: ProjectQueryService = Depends(get_project_query_service),
):
    return await project_queries.get_project(project_id, current_user_id)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return await project_commands.update_project(project_id, current_user_id, data.name)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    await project_commands.delete_project(project_id, current_user_id)


@router.post("/{project_id}/bot-token")
async def set_bot_token(
    project_id: str,
    data: BotTokenRequest,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return (
        await project_commands.set_client_bot_token(
            project_id, current_user_id, data.token
        )
    ).to_dict()


@router.post("/{project_id}/manager-token")
async def set_manager_token(
    project_id: str,
    data: BotTokenRequest,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return (
        await project_commands.set_manager_bot_token(
            project_id, current_user_id, data.token
        )
    ).to_dict()


@router.delete("/{project_id}/bot-token")
async def clear_bot_token(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return (
        await project_commands.clear_client_bot_token(project_id, current_user_id)
    ).to_dict()


@router.delete("/{project_id}/manager-token")
async def clear_manager_token(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return (
        await project_commands.clear_manager_bot_token(project_id, current_user_id)
    ).to_dict()


@router.get("/{project_id}/managers", response_model=list[int])
async def get_managers(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_queries: ProjectQueryService = Depends(get_project_query_service),
):
    return await project_queries.get_managers(project_id, current_user_id)


@router.post("/{project_id}/managers", status_code=201)
async def add_manager(
    project_id: str,
    data: ManagerAddRequest,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return (
        await project_commands.add_manager(project_id, current_user_id, data.chat_id)
    ).to_dict()


@router.delete("/{project_id}/managers/{chat_id}", status_code=204)
async def remove_manager(
    project_id: str,
    chat_id: int,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    await project_commands.remove_manager(project_id, current_user_id, chat_id)
    return None


@router.post("/{project_id}/connect-bot")
async def connect_bot(
    project_id: str,
    data: BotConnectRequest,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    """Универсальный эндпоинт для подключения ботов (как в ТГ боте)."""
    return (
        await project_commands.connect_bot(
            project_id, current_user_id, data.token, data.type
        )
    ).to_dict()


@router.post(
    "/{project_id}/members/invitations",
    response_model=ProjectInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_project_member(
    project_id: str,
    data: ProjectInvitationCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    invitation_service: ProjectInvitationService = Depends(
        build_project_invitation_service
    ),
):
    return await invitation_service.invite_project_member(
        project_id=project_id,
        current_user_id=current_user_id,
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role,
    )


@router.post(
    "/invitations/accept",
    response_model=ProjectInvitationAcceptResponse,
)
async def accept_project_invitation(
    data: ProjectInvitationAcceptRequest,
    current_user_id: str = Depends(get_current_user_id),
    invitation_service: ProjectInvitationService = Depends(
        build_project_invitation_service
    ),
):
    return await invitation_service.accept_project_invitation(
        token=data.token,
        current_user_id=current_user_id,
    )


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_queries: ProjectQueryService = Depends(get_project_query_service),
):
    members = await project_queries.list_project_members(project_id, current_user_id)
    return [member.to_dict() for member in members]


@router.post("/{project_id}/members", status_code=201)
async def upsert_project_member(
    project_id: str,
    data: ProjectMemberUpsertRequest,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return (
        await project_commands.upsert_project_member(
            project_id, current_user_id, data.user_id, data.role
        )
    ).to_dict()


@router.delete("/{project_id}/members/{member_user_id}", status_code=204)
async def delete_project_member(
    project_id: str,
    member_user_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    await project_commands.delete_project_member(
        project_id, current_user_id, member_user_id
    )
    return None


@router.get(
    "/{project_id}/configuration",
    response_model=ProjectConfigurationResponse,
    response_model_exclude_none=True,
)
async def get_project_configuration(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_queries: ProjectQueryService = Depends(get_project_query_service),
):
    return await project_queries.get_project_configuration(project_id, current_user_id)


@router.patch(
    "/{project_id}/settings",
    response_model=ProjectConfigurationResponse,
    response_model_exclude_none=True,
)
async def update_project_settings(
    project_id: str,
    data: ProjectSettingsUpdate,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return await project_commands.update_project_settings(
        project_id,
        current_user_id,
        data.model_dump(exclude_unset=True),
    )


@router.patch(
    "/{project_id}/policies",
    response_model=ProjectConfigurationResponse,
    response_model_exclude_none=True,
)
async def update_project_policies(
    project_id: str,
    data: ProjectPoliciesUpdate,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return await project_commands.update_project_policies(
        project_id,
        current_user_id,
        data.model_dump(exclude_unset=True),
    )


@router.patch(
    "/{project_id}/limits",
    response_model=ProjectConfigurationResponse,
    response_model_exclude_none=True,
)
async def update_project_limit_profile(
    project_id: str,
    data: ProjectLimitProfileUpdate,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return await project_commands.update_project_limit_profile(
        project_id,
        current_user_id,
        data.model_dump(exclude_unset=True),
    )


@router.get(
    "/{project_id}/integrations",
    response_model=list[ProjectIntegrationResponse],
    response_model_exclude_none=True,
)
async def list_project_integrations(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_queries: ProjectQueryService = Depends(get_project_query_service),
):
    return await project_queries.list_project_integrations(project_id, current_user_id)


@router.post(
    "/{project_id}/integrations",
    response_model=ProjectIntegrationResponse,
    response_model_exclude_none=True,
    status_code=201,
)
async def upsert_project_integration(
    project_id: str,
    data: ProjectIntegrationUpsert,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return await project_commands.upsert_project_integration(
        project_id,
        current_user_id,
        data.model_dump(exclude_unset=True),
    )


@router.get(
    "/{project_id}/channels",
    response_model=list[ProjectChannelResponse],
    response_model_exclude_none=True,
)
async def list_project_channels(
    project_id: str,
    current_user_id: str = Depends(get_current_user_id),
    project_queries: ProjectQueryService = Depends(get_project_query_service),
):
    return await project_queries.list_project_channels(project_id, current_user_id)


@router.post(
    "/{project_id}/channels",
    response_model=ProjectChannelResponse,
    response_model_exclude_none=True,
    status_code=201,
)
async def upsert_project_channel(
    project_id: str,
    data: ProjectChannelUpsert,
    current_user_id: str = Depends(get_current_user_id),
    project_commands: ProjectCommandService = Depends(get_project_command_service),
):
    return await project_commands.upsert_project_channel(
        project_id,
        current_user_id,
        data.model_dump(exclude_unset=True),
    )


@router.get(
    "/{project_id}/members/{manager_user_id}/reply-history",
    response_model=ManagerReplyHistoryResponse,
)
async def get_manager_reply_history(
    project_id: str,
    manager_user_id: str,
    limit: int = 30,
    offset: int = 0,
    current_user_id: str = Depends(get_current_user_id),
    service: ProjectQueryService = Depends(get_project_query_service),
) -> dict[str, object]:
    return cast(
        dict[str, object],
        await service.get_manager_reply_history(
            project_id=project_id,
            current_user_id=current_user_id,
            manager_user_id=manager_user_id,
            limit=limit,
            offset=offset,
        ),
    )
