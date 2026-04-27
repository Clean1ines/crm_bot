"""
Project repository composition helpers.

Adapters should depend on narrow application ports and get concrete
infrastructure repositories from composition/dependency wiring only.
"""

from src.infrastructure.db.repositories.project import (
    ProjectMemberRepository,
    ProjectRepository,
    ProjectTokenRepository,
)


def build_project_repository(pool: object) -> ProjectRepository:
    return ProjectRepository(pool)


def build_project_token_repository(pool: object) -> ProjectTokenRepository:
    return ProjectTokenRepository(pool)


def build_project_member_repository(pool: object) -> ProjectMemberRepository:
    return ProjectMemberRepository(pool)
