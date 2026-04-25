from .base import ProjectRepositoryBase
from .project_tokens import ProjectTokenRepository
from .project_members import ProjectMemberRepository
from .project_queries import ProjectQueryRepository
from .project_configuration import ProjectConfigurationRepository
from .project_integrations import ProjectIntegrationRepository
from .project_channels import ProjectChannelRepository
from .project_commands import ProjectCommandRepository


class ProjectRepository(
    ProjectTokenRepository,
    ProjectMemberRepository,
    ProjectQueryRepository,
    ProjectConfigurationRepository,
    ProjectIntegrationRepository,
    ProjectChannelRepository,
    ProjectCommandRepository,
    ProjectRepositoryBase,
):
    pass


# Backward-compatible import aliases while call sites migrate to CQRS names.
ProjectTokens = ProjectTokenRepository
ProjectMembers = ProjectMemberRepository
ProjectQueries = ProjectQueryRepository
ProjectConfiguration = ProjectConfigurationRepository
ProjectIntegrations = ProjectIntegrationRepository
ProjectChannels = ProjectChannelRepository
ProjectCommands = ProjectCommandRepository


__all__ = [
    "ProjectRepository",
    "ProjectRepositoryBase",
    "ProjectTokenRepository",
    "ProjectMemberRepository",
    "ProjectQueryRepository",
    "ProjectConfigurationRepository",
    "ProjectIntegrationRepository",
    "ProjectChannelRepository",
    "ProjectCommandRepository",
    "ProjectTokens",
    "ProjectMembers",
    "ProjectQueries",
    "ProjectConfiguration",
    "ProjectIntegrations",
    "ProjectChannels",
    "ProjectCommands",
]
