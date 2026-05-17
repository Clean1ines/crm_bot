from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_rag_eval_repository_does_not_own_review_console_presenter_copy() -> None:
    source = _read("src/infrastructure/db/repositories/rag_eval_repository.py")

    forbidden = [
        "Надёжно находится",
        "Проверка поиска по документу",
        "Проблемная база",
        "Проверить формулировку",
        "_build_review_payload",
    ]
    for text in forbidden:
        assert text not in source


def test_apply_accepted_route_delegates_to_application_service() -> None:
    source = _read("src/interfaces/http/rag_eval.py")
    start = source.index("async def apply_accepted_rag_eval_questions(")
    end = source.index(
        '\n\n@router.post("/results/{result_id}/actions/execute")', start
    )
    endpoint = source[start:end]

    assert "RagEvalReviewService(" in endpoint
    assert "apply_accepted_questions(" in endpoint
    assert "attach_question_to_entry(" not in endpoint
    assert "rebuild_entry_embedding(" not in endpoint
    assert "for index, review" not in endpoint
