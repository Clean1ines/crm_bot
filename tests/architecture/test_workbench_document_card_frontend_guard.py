from pathlib import Path


CARD = Path("frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx")
PAGE = Path("frontend/src/pages/knowledge/KnowledgePage.tsx")
API = Path("frontend/src/shared/api/modules/knowledge.ts")


def test_workbench_card_uses_backend_card_view_actions_for_lifecycle() -> None:
    source = CARD.read_text()

    assert "cardView.actions" in source
    assert "primaryActions(cardView)" in source
    assert "visibleSecondaryActions(cardView)" in source
    assert "handleCardAction(action)" in source
    assert "action.action_id === 'cancel_processing'" in source
    assert "action.action_id === 'open_curation'" in source
    assert "action.action_id === 'open_published_surfaces'" in source
    assert "action.action_id === 'delete_document'" in source


def test_workbench_card_keeps_user_visible_live_metrics() -> None:
    source = CARD.read_text()

    assert "active_elapsed_seconds" in source
    assert "wall_elapsed_seconds" in source
    assert "total_tokens" in source
    assert "llm_call_count" in source
    assert "sectionProgressPercent" in source
    assert "runtime_entry_count" in source
    assert "registry.entry_count" in source


def test_workbench_card_details_are_current_process_not_old_legacy_title() -> None:
    source = CARD.read_text()

    assert "Подробности обработки" in source
    assert "Открыть trace и курацию" in source
    assert "Legacy-диагностика импорта" in source
    assert "Диагностика импорта и старый прогресс" not in source


def test_frontend_action_mapping_uses_current_workbench_action_ids() -> None:
    page = PAGE.read_text()
    api = API.read_text()

    for action_id in (
        "cancel_processing",
        "resume_processing",
        "publish_ready",
        "open_curation",
        "open_published_surfaces",
        "delete_document",
    ):
        assert action_id in api
        assert action_id in page
