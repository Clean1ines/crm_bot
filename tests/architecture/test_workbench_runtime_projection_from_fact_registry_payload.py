from pathlib import Path

from src.infrastructure.db.workbench_runtime_retrieval_repository import (
    _runtime_rows_from_fact_registry,
)


REPOSITORY = Path("src/infrastructure/db/workbench_runtime_retrieval_repository.py")


def test_workbench_runtime_repository_projects_fact_registry_payload_to_runtime_rows() -> (
    None
):
    rows = _runtime_rows_from_fact_registry(
        "project-1",
        [
            {
                "fact_id": "cf_bot_answers",
                "claim": "Бот отвечает клиентам в Telegram.",
                "answer": "Бот автоматически отвечает клиентам в Telegram.",
                "question_variants": ["Может ли бот отвечать клиентам?"],
                "scope": "автоматические ответы",
                "exclusion_scope": "сложные вопросы менеджеру",
                "triples": [
                    {
                        "subject": "бот",
                        "predicate": "has_capability",
                        "object": "отвечать клиентам",
                    }
                ],
                "source_refs": ["section-1:c1"],
                "status": "active",
            }
        ],
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["fact_id"] == "cf_bot_answers"
    assert row["claim"] == "Бот отвечает клиентам в Telegram."
    assert row["answer_text"] == "Бот автоматически отвечает клиентам в Telegram."
    assert row["possible_questions"] == ("Может ли бот отвечать клиентам?",)
    assert row["source_refs"] == ("section-1:c1",)
    assert "has_capability" in row["embedding_text"]
    assert "автоматические ответы" in row["embedding_text"]


def test_workbench_runtime_repository_uses_runtime_fact_columns_not_old_surface_columns() -> (
    None
):
    source = REPOSITORY.read_text(encoding="utf-8")

    assert "publish_fact_registry_runtime_entries" in source
    assert "_runtime_rows_from_fact_registry" in source
    assert "knowledge_workbench_runtime_retrieval_entries" in source

    assert "fact_id" in source
    assert "possible_questions" in source
    assert "answer_text" in source

    assert "surface_id" not in source
    assert "question_variants::text" not in source
    assert 'row.get("question_variants")' not in source
    assert 'row["answer"]' not in source
    assert 'row.get("answer")' not in source

    # This is allowed: Prompt C canonical facts expose question_variants,
    # runtime projection maps them into possible_questions.
    assert 'raw_fact.get("question_variants")' in source


def test_workbench_runtime_projection_skips_inactive_or_invalid_facts() -> None:
    rows = _runtime_rows_from_fact_registry(
        "project-1",
        [
            {"fact_id": "missing-claim", "status": "active"},
            {"fact_id": "deleted", "claim": "Deleted fact", "status": "deleted"},
            {"fact_id": "active", "claim": "Active fact", "status": "active"},
        ],
    )

    assert tuple(row["fact_id"] for row in rows) == ("active",)
