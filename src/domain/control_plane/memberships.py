"""Membership invariants for project-scoped roles."""

from src.domain.control_plane.roles import ALLOWED_PROJECT_ROLES, PROJECT_MANAGER_ROLES


def normalize_project_role(role: str) -> str:
    """Normalize and validate a project membership role."""
    normalized = role.strip().lower()
    if normalized not in ALLOWED_PROJECT_ROLES:
        raise ValueError(f"Unsupported project role: {role}")
    return normalized


def is_manager_capable_role(role: str) -> bool:
    """Return True when the project role can manage dialogs and tickets."""
    return normalize_project_role(role) in PROJECT_MANAGER_ROLES
