from src.domain.runtime.cta import (
    CONTINUE_EXPLANATION_CTA,
    is_action_cta,
    is_conversational_cta,
    is_pending_cta,
    normalize_cta,
    normalize_short_reply_language,
    normalize_short_reply_kind,
)


def test_normalize_cta_treats_empty_and_none_as_absent():
    assert normalize_cta(None) is None
    assert normalize_cta("") is None
    assert normalize_cta("none") is None


def test_normalize_cta_strips_and_normalizes_case_without_masking_unknown_values():
    assert normalize_cta(" Call_Manager ") == "call_manager"
    assert normalize_cta("BOOK_CONSULTATION") == "book_consultation"
    assert normalize_cta(" Continue_Explanation ") == CONTINUE_EXPLANATION_CTA
    assert normalize_cta("future_cta") == "future_cta"


def test_is_action_cta_accepts_only_known_action_ctas():
    assert is_action_cta("call_manager") is True
    assert is_action_cta("book_consultation") is True
    assert is_action_cta(CONTINUE_EXPLANATION_CTA) is False
    assert is_action_cta("future_cta") is False
    assert is_action_cta("none") is False


def test_conversational_cta_is_pending_but_not_action():
    assert is_conversational_cta(CONTINUE_EXPLANATION_CTA) is True
    assert is_pending_cta(CONTINUE_EXPLANATION_CTA) is True
    assert is_pending_cta("call_manager") is True
    assert is_pending_cta("future_cta") is False


def test_normalize_short_reply_kind_uses_shared_affirmative_and_negative_vocabulary():
    for text in (
        "Да",
        "Ага",
        "Угу",
        "Ок",
        "Окей",
        "Конечно",
        "Yes",
        "Yep",
        "Sure",
        "Ja",
        "Sí",
    ):
        assert normalize_short_reply_kind(text) == "affirmative"

    for text in ("Нет", "Неа", "Не", "No", "Nope", "Nein"):
        assert normalize_short_reply_kind(text) == "negative"

    assert normalize_short_reply_kind("расскажите подробнее") is None


def test_normalize_short_reply_language_uses_shared_vocabulary():
    assert normalize_short_reply_language(" Да ") == "ru"
    assert normalize_short_reply_language("Sure") == "en"
    assert normalize_short_reply_language("Ja") == "de"
    assert normalize_short_reply_language("Sí") == "es"
    assert normalize_short_reply_language("Si") == "es"
    assert normalize_short_reply_language("расскажите подробнее") == "unknown"
