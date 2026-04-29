from src.domain.display_names import build_display_name
from src.domain.project_plane.client_views import ClientListItemView
from src.domain.control_plane.project_views import ProjectMemberView


def test_build_display_name_uses_expected_fallback_order():
    assert (
        build_display_name(
            full_name="  Alice Smith  ",
            first_name="Alice",
            last_name="Jones",
            username="alice",
            email="alice@example.com",
            fallback="Клиент",
        )
        == "Alice Smith"
    )
    assert (
        build_display_name(
            first_name="Alice",
            last_name="Jones",
            username="alice",
            email="alice@example.com",
            fallback="Клиент",
        )
        == "Alice Jones"
    )
    assert (
        build_display_name(
            username="alice",
            email="alice@example.com",
            fallback="Клиент",
        )
        == "@alice"
    )
    assert (
        build_display_name(
            username="  ",
            email="alice@example.com",
            fallback="Клиент",
        )
        == "alice@example.com"
    )
    assert (
        build_display_name(
            username="undefined",
            email="null",
            fallback="Менеджер",
        )
        == "Менеджер"
    )


def test_client_list_item_view_populates_display_name():
    view = ClientListItemView(
        id="client-1",
        username="client_user",
        full_name="",
        email="client@example.com",
    )

    assert view.display_name == "@client_user"


def test_project_member_view_populates_display_name():
    view = ProjectMemberView.from_record(
        {
            "project_id": "project-1",
            "user_id": "user-1",
            "role": "manager",
            "email": "manager@example.com",
        }
    )

    assert view.display_name == "manager@example.com"
