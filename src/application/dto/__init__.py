from __future__ import annotations

from importlib import import_module

_EXPORT_MODULES: dict[str, str] = {
    "AuthActionDto": "src.application.dto.auth_dto",
    "AuthMethodDto": "src.application.dto.auth_dto",
    "AuthMethodsDto": "src.application.dto.auth_dto",
    "AuthSessionDto": "src.application.dto.auth_dto",
    "GraphExecutionRequestDto": "src.application.dto.runtime_dto",
    "GraphExecutionResultDto": "src.application.dto.runtime_dto",
    "KnowledgeUploadResultDto": "src.application.dto.knowledge_dto",
    "MessageProcessingOutcomeDto": "src.application.dto.runtime_dto",
    "ProjectConfigurationDto": "src.application.dto.project_dto",
    "ProjectMemberDto": "src.application.dto.control_plane_dto",
    "ProjectMutationResultDto": "src.application.dto.control_plane_dto",
    "ProjectRuntimeContextDto": "src.application.dto.runtime_dto",
    "ProjectSummaryDto": "src.application.dto.project_dto",
    "ProjectTeamDto": "src.application.dto.control_plane_dto",
    "TelegramAdminProjectsDto": "src.application.dto.control_plane_dto",
    "UserProfileDto": "src.application.dto.auth_dto",
    "WebhookAckDto": "src.application.dto.webhook_dto",
}


__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> object:
    module_path = _EXPORT_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
