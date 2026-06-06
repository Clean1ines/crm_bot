from pathlib import Path


PRODUCTION_CARDS = Path("src/application/workbench_observability/document_cards.py")
CANONICAL_PROJECTION = Path("src/application/workbench/document_card_projection.py")


def test_production_document_cards_do_not_define_second_card_builder() -> None:
    source = PRODUCTION_CARDS.read_text(encoding="utf-8")

    forbidden = (
        "def _card_view(",
        "def _timer(",
        "def _actions(",
        "def _messages(",
        "def _recovery(",
        "def _status_bucket(",
        "def _status_label(",
        "def _status_description(",
        "def _resume_available(",
        'row.get("started_at")',
        'row.get("wall_elapsed_seconds")',
        "current_active_started_at",
    )

    for marker in forbidden:
        assert marker not in source


def test_production_document_cards_use_canonical_projection_as_card_source() -> None:
    source = PRODUCTION_CARDS.read_text(encoding="utf-8")

    assert "with_workbench_document_card_view" in source
    assert 'card_view = _mapping(canonical_document.get("card_view"))' in source


def test_canonical_projection_owns_current_active_timer_mapping() -> None:
    source = CANONICAL_PROJECTION.read_text(encoding="utf-8")

    current_started_context = source[
        source.index("current_started_at") : source.index(
            "return WorkbenchDocumentCardSource"
        )
    ]

    assert "current_active_started_at" in current_started_context
    assert 'row.get("started_at")' not in current_started_context
