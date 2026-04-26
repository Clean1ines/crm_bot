"""
Project runtime configuration loading.
"""

from src.application.dto.runtime_dto import ProjectRuntimeContextDto


class ProjectRuntimeConfigurationLoadError(RuntimeError):
    """Raised when protected runtime configuration cannot be loaded."""


class ProjectRuntimeLoader:
    def __init__(self, projects, logger) -> None:
        self.projects = projects
        self.logger = logger

    async def load_project_configuration(self, project_id: str) -> ProjectRuntimeContextDto:
        try:
            config = await self.projects.get_project_configuration_view(project_id)
            return ProjectRuntimeContextDto.from_record(config.to_runtime_record())
        except Exception as exc:
            self.logger.warning(
                "Failed to load project configuration for runtime",
                extra={
                    "project_id": project_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise ProjectRuntimeConfigurationLoadError(
                "Project runtime configuration could not be loaded"
            ) from exc
