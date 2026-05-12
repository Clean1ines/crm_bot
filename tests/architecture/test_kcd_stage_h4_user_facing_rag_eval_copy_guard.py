from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stage_h4_sidebar_uses_user_facing_rag_eval_label() -> None:
    source = _read("frontend/src/widgets/sidebar/AppSidebar.tsx")

    assert "label: 'Проверка знаний'" in source
    assert "label: 'RAG eval'" not in source


def test_stage_h4_rag_eval_page_uses_user_facing_main_copy() -> None:
    source = _read("frontend/src/pages/rag-eval/RagEvalPage.tsx")

    assert "Проверка качества базы знаний" in source
    assert "Прогресс проверки" in source
    assert "Последний результат проверки" in source
    assert "Предложенные исправления базы знаний" in source
    assert "Применить предложенные исправления" in source
    assert "Технические подробности запуска" in source
    assert "Технические подробности отчёта" in source
    assert "Первый найденный фрагмент" in source
    assert "Риск выдуманного ответа" in source


def test_stage_h4_rag_eval_page_does_not_expose_developer_copy() -> None:
    source = _read("frontend/src/pages/rag-eval/RagEvalPage.tsx")

    forbidden_visible_copy = [
        "Full-document RAG eval",
        "Прогресс RAG eval",
        "Последний run/report",
        "Не удалось загрузить статус RAG eval.",
        "Нет обработанного документа для RAG eval",
        "Показать raw JSON",
        "Не удалось применить safe actions",
        "Safe actions applied",
        "Top-1 chunk",
        "Top-3 chunks",
        "Top-5 chunks",
        "Ошибочный первый chunk",
        "Job:{' '}",
        "ID задачи:",
        "production DB",
        "Не готово к production",
        "галлюцинац",
        "релевантные чанки",
        "каждого chunk",
        " chunks",
    ]

    for marker in forbidden_visible_copy:
        assert marker not in source


def test_stage_h4_run_json_is_hidden_under_technical_details() -> None:
    source = _read("frontend/src/pages/rag-eval/RagEvalPage.tsx")

    assert "Технические подробности запуска" in source
    assert "Технические подробности отчёта" in source
    assert "ReportJsonBlock value={latestRun}" in source
    assert "Статус запуска" in source
