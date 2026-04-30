from src.domain.runtime.dialog_state import DialogState

AFFIRMATIVE_REPLIES = frozenset(
    {
        "\u0434\u0430",
        "\u0430\u0433\u0430",
        "\u0443\u0433\u0443",
        "\u043e\u043a",
        "\u043e\u043a\u0435\u0439",
        "yes",
        "yep",
    }
)
NEGATIVE_PREFIXES = (
    "\u043d\u0435\u0442",
    "\u043d\u0435\u0430",
    "\u043d\u0435 \u043d\u0430\u0434\u043e",
    "\u043d\u0435 \u043f\u0435\u0440\u0435\u0434\u0430\u0432\u0430\u0442\u044c",
    "no",
    "nope",
)

_MAX_SUMMARY_LENGTH = 160


def is_handoff_confirmation_pending(dialog_state: DialogState) -> bool:
    return bool(dialog_state.get("handoff_confirmation_pending"))


def clear_handoff_confirmation(dialog_state: DialogState) -> DialogState:
    return {
        "last_intent": dialog_state.get("last_intent"),
        "last_cta": dialog_state.get("last_cta"),
        "last_topic": dialog_state.get("last_topic"),
        "repeat_count": dialog_state.get("repeat_count", 0),
        "lead_status": str(dialog_state.get("lead_status") or "cold"),
        "lifecycle": str(dialog_state.get("lifecycle") or "cold"),
        "handoff_confirmation_pending": False,
    }


def with_handoff_confirmation_pending(dialog_state: DialogState) -> DialogState:
    return {
        "last_intent": dialog_state.get("last_intent"),
        "last_cta": dialog_state.get("last_cta"),
        "last_topic": dialog_state.get("last_topic"),
        "repeat_count": dialog_state.get("repeat_count", 0),
        "lead_status": str(dialog_state.get("lead_status") or "cold"),
        "lifecycle": str(dialog_state.get("lifecycle") or "cold"),
        "handoff_confirmation_pending": True,
    }


def resolve_handoff_confirmation_reply(user_input: str) -> str | None:
    normalized = _normalize_short_reply(user_input)
    if normalized is None:
        return None

    if normalized in AFFIRMATIVE_REPLIES:
        return "confirm"

    if any(normalized.startswith(prefix) for prefix in NEGATIVE_PREFIXES):
        return "decline"

    return None


def build_handoff_confirmation_text(user_input: str) -> str:
    summary = _user_input_summary(user_input)
    if summary:
        return (
            "\u041f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u043e \u043f\u043e\u043d\u0438\u043c\u0430\u044e: \u0432\u0430\u043c \u043d\u0443\u0436\u043d\u0430 "
            "\u043f\u043e\u043c\u043e\u0449\u044c \u043c\u0435\u043d\u0435\u0434\u0436\u0435\u0440\u0430 \u043f\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0443 "
            f'"{summary}"?\n'
            "\u041f\u0435\u0440\u0435\u0434\u0430\u0442\u044c \u0434\u0438\u0430\u043b\u043e\u0433 "
            "\u043c\u0435\u043d\u0435\u0434\u0436\u0435\u0440\u0443?\n"
            "\u041e\u0442\u0432\u0435\u0442\u044c\u0442\u0435: \u0414\u0430 / "
            "\u041d\u0435\u0442, \u0434\u043e\u0431\u0430\u0432\u043b\u044e "
            "\u0434\u0435\u0442\u0430\u043b\u0438."
        )

    return (
        "\u041f\u0435\u0440\u0435\u0434\u0430\u0442\u044c \u0434\u0438\u0430\u043b\u043e\u0433 "
        "\u043c\u0435\u043d\u0435\u0434\u0436\u0435\u0440\u0443?\n"
        "\u041e\u0442\u0432\u0435\u0442\u044c\u0442\u0435: \u0414\u0430 / "
        "\u041d\u0435\u0442, \u0434\u043e\u0431\u0430\u0432\u043b\u044e \u0434\u0435\u0442\u0430\u043b\u0438."
    )


def build_handoff_details_requested_text() -> str:
    return (
        "\u0425\u043e\u0440\u043e\u0448\u043e, \u043d\u0435 "
        "\u043f\u0435\u0440\u0435\u0434\u0430\u044e. \u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435, "
        "\u043f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, "
        "\u0434\u0435\u0442\u0430\u043b\u0438, \u0438 \u044f \u0443\u0442\u043e\u0447\u043d\u044e "
        "\u0437\u0430\u043f\u0440\u043e\u0441."
    )


def _normalize_short_reply(user_input: str) -> str | None:
    normalized = " ".join(str(user_input).strip().lower().split())
    if not normalized:
        return None

    if len(normalized) > 40 and "," not in normalized:
        return None

    return normalized


def _user_input_summary(user_input: str) -> str | None:
    text = " ".join(str(user_input).strip().split())
    if not text:
        return None

    if len(text) <= _MAX_SUMMARY_LENGTH:
        return text

    return f"{text[: _MAX_SUMMARY_LENGTH - 3].rstrip()}..."
