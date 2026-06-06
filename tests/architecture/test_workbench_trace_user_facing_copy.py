from pathlib import Path


MODAL = Path(
    "frontend/src/pages/knowledge/components/KnowledgeDocumentCurationModal.tsx"
)
CARD = Path("frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx")
CARD_BUILDER = Path("src/application/workbench/document_card_builder.py")


def test_trace_modal_primary_copy_is_user_facing() -> None:
    source = MODAL.read_text(encoding="utf-8")

    required = (
        "Разбор документа",
        "Извлечённые знания по секциям",
        "Извлечения",
        "Извлечённые фрагменты",
        "Детали извлечения",
        "Цитата / основание",
        "Структурные связи",
        "Связи внутри секции",
        "Покрытие источниками",
        "Пробелы и предупреждения",
    )
    for marker in required:
        assert marker in source

    forbidden_primary_copy = (
        "Workbench trace & surface curation",
        "surface curation mutations",
        "Prompt A: обработанные секции и claims",
        "Prompt A claims не найдены",
        "Секции и claims",
        "Gaps / warnings",
        "Canonical facts не найдены.",
        "Surfaces не найдены.",
        "claims {formatNumber(section.findings.length)}",
    )
    for marker in forbidden_primary_copy:
        assert marker not in source


def test_document_card_primary_copy_is_user_facing() -> None:
    source = CARD.read_text(encoding="utf-8")

    required = (
        "Извлечённые знания",
        "Извлечения:",
        "Разбор:",
        "Цитата / основание",
        "Структурные связи",
        "Связи внутри секции",
    )
    for marker in required:
        assert marker in source

    forbidden_primary_copy = (
        "Локально извлечённые claims Prompt A",
        "Локальные claims:",
        "Prompt A:",
        "`Claim ${index + 1}`",
        "Evidence</div>",
        "Triples</div>",
        "Relations</div>",
    )
    for marker in forbidden_primary_copy:
        assert marker not in source


def test_document_card_does_not_show_workbench_button_to_user() -> None:
    source = CARD_BUILDER.read_text(encoding="utf-8")

    assert 'label="Посмотреть разбор"' in source
    assert 'label="Открыть Workbench"' not in source
