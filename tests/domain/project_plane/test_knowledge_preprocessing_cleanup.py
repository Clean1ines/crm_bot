from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingEntry
from src.domain.project_plane.knowledge_preprocessing_cleanup import (
    absorb_short_answer_cards,
    cleanup_faq_preprocessing_entries,
    dedupe_source_excerpts,
    prune_broad_card_questions,
)


def _entry(
    title: str,
    answer: str,
    *,
    questions: tuple[str, ...] = (),
    source_excerpt: str | None = None,
    source_chunk_indexes: tuple[int, ...] = (),
) -> KnowledgePreprocessingEntry:
    return KnowledgePreprocessingEntry(
        title=title,
        canonical_question=questions[0] if questions else title,
        answer=answer,
        source_excerpt=source_excerpt or answer,
        questions=questions,
        source_chunk_indexes=source_chunk_indexes,
    )


def test_source_excerpts_dedupe_exact_and_contained_quotes() -> None:
    excerpts = dedupe_source_excerpts(
        (
            "Поисковая поверхность хранит опубликованные ответы.",
            "Поисковая поверхность хранит опубликованные ответы.",
            "Поисковая поверхность хранит опубликованные ответы и source refs.",
            "Ручное слияние объединяет дубли.",
        )
    )

    assert excerpts == (
        "Поисковая поверхность хранит опубликованные ответы и source refs.",
        "Ручное слияние объединяет дубли.",
    )


def test_short_answer_card_absorbs_into_richer_parent_from_same_chunk() -> None:
    parent = _entry(
        "Поисковая поверхность",
        "Поисковая поверхность хранит опубликованные ответы, source refs и текст для поиска.",
        questions=("Что такое поисковая поверхность?",),
        source_excerpt=(
            "Поисковая поверхность хранит опубликованные ответы, source refs и текст для поиска.\n\n"
            "Короткий ответ клиенту: это слой, по которому работает RAG."
        ),
        source_chunk_indexes=(2,),
    )
    short = _entry(
        "Короткий ответ клиенту",
        "Это слой, по которому работает RAG.",
        questions=("Короткий ответ клиенту",),
        source_excerpt="Короткий ответ клиенту: это слой, по которому работает RAG.",
        source_chunk_indexes=(2,),
    )

    result = absorb_short_answer_cards((short, parent))

    assert result.metrics["short_answer_absorbed_count"] == 1
    assert [entry.title for entry in result.entries] == ["Поисковая поверхность"]
    assert "RAG" in result.entries[0].source_excerpt
    assert result.entries[0].embedding_text


def test_short_answer_without_parent_is_not_publishable_standalone() -> None:
    result = absorb_short_answer_cards(
        (
            _entry(
                "Короткий ответ",
                "Система помогает искать знания.",
                questions=("Короткий ответ",),
            ),
        )
    )

    assert result.entries == ()
    assert result.metrics["short_answer_unpublishable_count"] == 1


def test_prune_broad_questions_moves_specific_questions_to_narrow_cards() -> None:
    overview = _entry(
        "Что это за продукт",
        "Это сервис для AI-базы знаний, Telegram-бота и RAG-поиска.",
        questions=(
            "что это за сервис?",
            "чем вы занимаетесь?",
            "что такое компиляция знаний?",
            "можно ли загрузить PDF?",
            "как удалить плохой фрагмент?",
            "для чего нужна AI-база знаний?",
        ),
    )
    compilation = _entry(
        "Компиляция знаний",
        "Компиляция знаний превращает документ в проверяемые карточки.",
        questions=("как работает компиляция знаний?",),
    )
    pdf = _entry(
        "Работа с PDF",
        "PDF можно загрузить как источник базы знаний.",
        questions=("как загрузить PDF?",),
    )
    archive = _entry(
        "Скрытие, отклонение и архивирование",
        "Плохой фрагмент можно скрыть, отклонить или архивировать.",
        questions=("как скрыть фрагмент?",),
    )

    result = prune_broad_card_questions((overview, compilation, pdf, archive))
    by_title = {entry.title: entry for entry in result.entries}

    assert "что это за сервис?" in by_title["Что это за продукт"].questions
    assert "для чего нужна AI-база знаний?" in by_title["Что это за продукт"].questions
    assert "что такое компиляция знаний?" in by_title["Компиляция знаний"].questions
    assert "можно ли загрузить PDF?" in by_title["Работа с PDF"].questions
    assert "как удалить плохой фрагмент?" in by_title[
        "Скрытие, отклонение и архивирование"
    ].questions
    assert result.metrics["moved_question_count"] == 3


def test_acceptance_fixture_cleanup_keeps_demo_ready_faq_cards() -> None:
    entries = (
        _entry(
            "Что это за продукт",
            "Сервис превращает документы в AI-базу знаний для Telegram-бота и RAG-поиска.",
            questions=(
                "что это за сервис?",
                "что такое компиляция знаний?",
                "можно ли загрузить PDF?",
                "как удалить плохой фрагмент?",
                "как объединить фрагменты вручную?",
                "для чего нужна AI-база знаний?",
            ),
        ),
        _entry(
            "Компиляция знаний",
            "После загрузки документа система извлекает текст, разбивает его на части, создаёт карточки знаний и готовит их для поиска.",
            questions=("как работает компиляция знаний?",),
            source_chunk_indexes=(1,),
        ),
        _entry(
            "Поисковая поверхность",
            "Поисковая поверхность — production-safe слой, по которому runtime и RAG eval ищут опубликованные ответы с source refs.",
            questions=("что такое поисковая поверхность?",),
            source_excerpt="Поисковая поверхность — слой для runtime и RAG eval. Короткий ответ клиенту: production-safe поиск по опубликованным ответам.",
            source_chunk_indexes=(2,),
        ),
        _entry(
            "Короткий ответ клиенту",
            "Production-safe поиск по опубликованным ответам.",
            questions=("короткий ответ клиенту",),
            source_excerpt="Короткий ответ клиенту: production-safe поиск по опубликованным ответам.",
            source_chunk_indexes=(2,),
        ),
        _entry(
            "Работа с PDF",
            "PDF можно загружать как документ-источник базы знаний.",
            questions=("как загрузить PDF?",),
        ),
        _entry(
            "Ручное слияние фрагментов",
            "Ручное слияние объединяет дубли карточек без удаления исходной evidence.",
            questions=("как объединить фрагменты вручную?", "как удалить плохой фрагмент?"),
        ),
        _entry(
            "Скрытие, отклонение и архивирование",
            "Плохие фрагменты можно скрывать, отклонять или архивировать.",
            questions=("как скрыть плохой фрагмент?",),
        ),
        _entry(
            "Правила для RAG-поиска",
            "Темы для RAG нужно разделять: не смешивать AI-базу и Telegram-бота, web-panel и web-widget, CRM-like и полноценную CRM, возврат и отключение, курацию и проверку поиска.",
            questions=("какие правила для RAG-поиска?",),
        ),
    )

    result = cleanup_faq_preprocessing_entries(entries)
    by_title = {entry.title: entry for entry in result.entries}

    assert "Короткий ответ клиенту" not in by_title
    assert "что такое компиляция знаний?" not in by_title["Что это за продукт"].questions
    assert "что такое компиляция знаний?" in by_title["Компиляция знаний"].questions
    assert "как удалить плохой фрагмент?" not in by_title[
        "Ручное слияние фрагментов"
    ].questions
    assert "как удалить плохой фрагмент?" in by_title[
        "Скрытие, отклонение и архивирование"
    ].questions
    assert "не смешивать AI-базу и Telegram-бота" in by_title[
        "Правила для RAG-поиска"
    ].answer
    assert result.metrics["short_answer_absorbed_count"] == 1
