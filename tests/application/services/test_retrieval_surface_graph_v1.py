from src.application.services.knowledge_ingestion_service import (
    _compiled_answer_drafts_from_preprocessing_result,
    _apply_answer_resolution_decisions,
    _repair_generated_entry,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgeAnswerResolutionDecision,
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingResult,
)


def _result(*entries: KnowledgePreprocessingEntry) -> KnowledgePreprocessingResult:
    return KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_answer_compiler_faq_v1",
        model="llama-test",
        entries=entries,
    )


def test_short_answer_block_absorbed_not_standalone() -> None:
    drafts = _compiled_answer_drafts_from_preprocessing_result(
        _result(
            KnowledgePreprocessingEntry(
                title="Короткий ответ клиенту",
                answer="Ассистент ищет по подготовленной базе знаний.",
                source_excerpt="Ассистент ищет по подготовленной базе знаний.",
            ),
            KnowledgePreprocessingEntry(
                title="Поисковая поверхность",
                answer="Поисковая поверхность — набор опубликованных знаний.",
                source_excerpt="Поисковая поверхность — набор опубликованных знаний.",
                questions=("Что такое поисковая поверхность?",),
            ),
        )
    )
    assert len(drafts) == 1
    assert drafts[0].title == "Поисковая поверхность"
    assert "подготовленной базе знаний" in drafts[0].answer


def test_umbrella_reassigns_child_specific_questions() -> None:
    drafts = _compiled_answer_drafts_from_preprocessing_result(
        _result(
            KnowledgePreprocessingEntry(
                title="Что это за продукт",
                answer="Это AI-платформа базы знаний.",
                source_excerpt="Это AI-платформа базы знаний.",
                questions=("Что это за сервис?", "Можно ли загрузить PDF?"),
            ),
            KnowledgePreprocessingEntry(
                title="Компиляция знаний",
                answer="Компиляция строит поисковые поверхности.",
                source_excerpt="Компиляция строит поисковые поверхности.",
                questions=("Что такое компиляция знаний?",),
            ),
        )
    )
    umbrella = next(d for d in drafts if d.title == "Что это за продукт")
    child = next(d for d in drafts if d.title == "Компиляция знаний")
    assert "Что это за сервис?" in umbrella.questions
    assert "Можно ли загрузить PDF?" not in umbrella.questions
    assert "Можно ли загрузить PDF?" in child.questions


def test_repair_first_validation_non_fatal_for_short_answer_style() -> None:
    entry = KnowledgePreprocessingEntry(
        title="Короткий ответ",
        answer="## Короткий ответ\nЗдравствуйте! expected topic: ассистент ищет по базе.",
        source_excerpt="Ассистент ищет по базе знаний.",
        questions=("По чему ассистент ищет?",),
    )
    repaired, warnings = _repair_generated_entry(entry, source_excerpt=entry.source_excerpt)
    assert repaired.answer
    assert "generated_answer_markdown_heading_repaired" in warnings


def test_answer_resolution_umbrella_child_relation_not_forced_merge() -> None:
    left = KnowledgePreprocessingEntry(
        title="Что это за продукт",
        answer="Это AI-платформа базы знаний.",
        source_excerpt="Это AI-платформа базы знаний.",
        questions=("Что это за сервис?",),
    )
    right = KnowledgePreprocessingEntry(
        title="Клиентский web-widget",
        answer="Виджет для сайта и чата на сайте.",
        source_excerpt="Виджет для сайта и чата на сайте.",
        questions=("Есть ли web-widget?",),
    )
    decisions = (
        KnowledgeAnswerResolutionDecision(
            case_id="g1", action="keep_separate", candidate_ids=("entry-0", "entry-1")
        ),
    )
    tightened, _ = _apply_answer_resolution_decisions(entries=(left, right), decisions=decisions)
    assert len(tightened) == 2
