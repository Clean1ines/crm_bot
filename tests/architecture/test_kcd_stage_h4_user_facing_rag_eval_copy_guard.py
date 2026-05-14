from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SIDEBAR = ROOT / "frontend/src/widgets/sidebar/AppSidebar.tsx"
RAG_EVAL_PAGE = ROOT / "frontend/src/pages/rag-eval/RagEvalPage.tsx"
RU_LOCALE = ROOT / "frontend/src/shared/i18n/locales/ru.ts"


def test_stage_h4_sidebar_uses_user_facing_rag_eval_label() -> None:
    source = SIDEBAR.read_text(encoding="utf-8")
    ru_locale = RU_LOCALE.read_text(encoding="utf-8")

    assert "sidebar.nav.ragEval" in source
    assert "'sidebar.nav.ragEval': 'Проверка знаний'" in ru_locale
    assert "RAG" not in source


def test_stage_h4_rag_eval_page_uses_user_facing_main_copy() -> None:
    source = RAG_EVAL_PAGE.read_text(encoding="utf-8")
    ru_locale = RU_LOCALE.read_text(encoding="utf-8")

    assert "ragEval.page.title" in source
    assert "ragEval.run.title" in source
    assert "ragEval.lastResult.title" in source
    assert "'ragEval.page.title': 'Проверка качества базы знаний'" in ru_locale
    assert "'ragEval.run.title': 'Запуск полной проверки'" in ru_locale
    assert "'ragEval.lastResult.title': 'Последний результат проверки'" in ru_locale


def test_stage_h4_rag_eval_page_avoids_raw_json_primary_copy() -> None:
    source = RAG_EVAL_PAGE.read_text(encoding="utf-8")
    ru_locale = RU_LOCALE.read_text(encoding="utf-8")

    assert "JSON.stringify(value ?? null, null, 2)" in source
    assert "ragEval.launch.description" in source
    assert (
        "'ragEval.launch.description': 'Здесь показано состояние последней проверки без служебного JSON.'"
        in ru_locale
    )


def test_stage_h4_run_json_is_hidden_under_technical_details() -> None:
    source = RAG_EVAL_PAGE.read_text(encoding="utf-8")
    ru_locale = RU_LOCALE.read_text(encoding="utf-8")

    assert "ragEval.launch.technicalDetails" in source
    assert "ragEval.report.technicalDetails" in source
    assert (
        "'ragEval.launch.technicalDetails': 'Технические подробности запуска'"
        in ru_locale
    )
    assert (
        "'ragEval.report.technicalDetails': 'Технические подробности отчёта'"
        in ru_locale
    )
    assert "<details" in source
    assert "<ReportJsonBlock" in source
