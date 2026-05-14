from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

KNOWLEDGE_API = ROOT / "frontend/src/shared/api/modules/knowledge.ts"
KNOWLEDGE_PAGE = ROOT / "frontend/src/pages/knowledge/KnowledgePage.tsx"
RU_LOCALE = ROOT / "frontend/src/shared/i18n/locales/ru.ts"


def test_cancel_processing_api_client_is_wired() -> None:
    source = KNOWLEDGE_API.read_text(encoding="utf-8")

    assert "cancel" in source
    assert "/cancel" in source
    assert "authedJsonRequest" in source


def test_cancel_processing_frontend_button_is_wired() -> None:
    page = KNOWLEDGE_PAGE.read_text(encoding="utf-8")
    ru_locale = RU_LOCALE.read_text(encoding="utf-8")

    assert "cancelProcessingMutation" in page
    assert "knowledgeApi.cancel" in page
    assert "StopCircle" in page
    assert "knowledge.actions.stopProcessing" in page
    assert "'knowledge.actions.stopProcessing': 'Остановить обработку'" in ru_locale


def test_cancel_processing_frontend_feedback_is_user_facing() -> None:
    page = KNOWLEDGE_PAGE.read_text(encoding="utf-8")
    ru_locale = RU_LOCALE.read_text(encoding="utf-8")

    assert "knowledge.feedback.processingStopped" in page
    assert "knowledge.feedback.stopFailed" in page
    assert "knowledge.document.stoppedWarning" in page
    assert (
        "'knowledge.feedback.processingStopped': 'Обработка документа остановлена'"
        in ru_locale
    )
    assert (
        "'knowledge.feedback.stopFailed': 'Не удалось остановить обработку'"
        in ru_locale
    )
    assert "Документ остановлен пользователем" in ru_locale
