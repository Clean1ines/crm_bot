from __future__ import annotations

from src.infrastructure.db.repositories.knowledge_curation_mappers import (
    stage_h_attached_questions,
    stage_h_embedding_text,
    stage_h_entry_snapshot,
    stage_h_json_object,
    stage_h_search_text,
    stage_h_text_list,
)


def test_stage_h_json_object_parses_json_and_ignores_invalid_values() -> None:
    assert stage_h_json_object({"a": 1}) == {"a": 1}
    assert stage_h_json_object('{"a": 1}') == {"a": 1}
    assert stage_h_json_object("[1, 2]") == {}
    assert stage_h_json_object("not-json") == {}
    assert stage_h_json_object(None) == {}


def test_stage_h_text_list_dedupes_and_normalizes_values() -> None:
    assert stage_h_text_list(["  вопрос  ", "вопрос", "", None, 42]) == [
        "вопрос",
        "42",
    ]
    assert stage_h_text_list("  один   вопрос  ") == ["один вопрос"]
    assert stage_h_text_list({"bad": "shape"}) == []


def test_stage_h_attached_questions_merges_enrichment_and_metadata() -> None:
    enrichment = {
        "questions": ["Q1"],
        "positive_questions": ["Q2"],
        "synonyms": ["Q1", "Q3"],
        "tags": ["tag"],
    }
    metadata = {
        "stage_h": {
            "attached_questions": [
                {"question": "Q4"},
                {"question": "Q2"},
                {"bad": "shape"},
            ]
        }
    }

    assert stage_h_attached_questions(
        enrichment=enrichment,
        metadata=metadata,
    ) == ["Q1", "Q2", "Q3", "tag", "Q4"]


def test_stage_h_entry_snapshot_and_embedding_text() -> None:
    row = {
        "id": "entry-1",
        "project_id": "project-1",
        "document_id": "document-1",
        "compiler_run_id": None,
        "stable_key": "stable",
        "entry_kind": "answer",
        "title": "Title",
        "answer": "Answer",
        "status": "published",
        "visibility": "runtime",
        "version": 3,
        "compiler_version": None,
        "embedding_text": "Existing embedding",
        "embedding_text_version": None,
        "enrichment": {"questions": ["Question?"]},
        "metadata": {"stage_h": {"attached_questions": [{"question": "Attached?"}]}},
    }

    snapshot = stage_h_entry_snapshot(row)
    assert snapshot["id"] == "entry-1"
    assert snapshot["version"] == 3
    assert snapshot["enrichment"] == {"questions": ["Question?"]}

    embedding_text = stage_h_embedding_text(row)
    assert embedding_text.splitlines() == [
        "Title",
        "Answer",
        "Existing embedding",
        "Question?",
        "Attached?",
    ]


def test_stage_h_search_text_dedupes_parts() -> None:
    assert (
        stage_h_search_text(
            title="Title",
            answer="Answer",
            embedding_text="Title\nMore",
        )
        == "Title\nAnswer\nTitle More"
    )
