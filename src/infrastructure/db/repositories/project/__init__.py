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
    """
    Concrete infrastructure repository used by composition.

    Application code should depend on Protocol ports, not this facade directly.
    """


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
]
