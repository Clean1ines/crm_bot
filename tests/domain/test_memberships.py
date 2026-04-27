import pytest

from src.domain.control_plane.memberships import (
    is_manager_capable_role,
    normalize_project_role,
)


def test_normalize_project_role_accepts_known_roles():
    assert normalize_project_role(" Manager ") == "manager"


def test_normalize_project_role_rejects_unknown_role():
    with pytest.raises(ValueError):
        normalize_project_role("superadmin")


def test_is_manager_capable_role_only_for_manager_path_roles():
    assert is_manager_capable_role("owner") is True
    assert is_manager_capable_role("admin") is True
    assert is_manager_capable_role("manager") is True
    assert is_manager_capable_role("viewer") is False
