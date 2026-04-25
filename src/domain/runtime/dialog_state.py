from typing import Mapping, NotRequired, TypedDict, cast

from src.domain.runtime.state_contracts import RuntimeMemory
from src.domain.runtime.value_parsing import coerce_int


class DialogState(TypedDict):
    last_intent: str | None
    last_cta: str | None
    last_topic: str | None
    repeat_count: int
    lead_status: str
    lifecycle: str


class PartialDialogState(TypedDict, total=False):
    last_intent: NotRequired[str | None]
    last_cta: NotRequired[str | None]
    last_topic: NotRequired[str | None]
    repeat_count: NotRequired[int]
    lead_status: NotRequired[str]
    lifecycle: NotRequired[str]


def default_dialog_state(*, lifecycle: str = "cold") -> DialogState:
    return {
        "last_intent": None,
        "last_cta": None,
        "last_topic": None,
        "repeat_count": 0,
        "lead_status": lifecycle,
        "lifecycle": lifecycle,
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def dialog_state_from_mapping(
    value: Mapping[str, object] | None,
    *,
    lifecycle: str = "cold",
) -> DialogState:
    result = default_dialog_state(lifecycle=lifecycle)
    if value is None:
        return result

    patch: PartialDialogState = {}
    patch["last_intent"] = _optional_text(value.get("last_intent"))
    patch["last_cta"] = _optional_text(value.get("last_cta"))
    patch["last_topic"] = _optional_text(value.get("last_topic"))
    patch["repeat_count"] = coerce_int(value.get("repeat_count"), 0)
    patch["lead_status"] = _optional_text(value.get("lead_status")) or lifecycle
    patch["lifecycle"] = _optional_text(value.get("lifecycle")) or lifecycle

    result.update(patch)
    return result


def merge_dialog_state(
    value: Mapping[str, object] | None,
    *,
    lifecycle: str = "cold",
) -> DialogState:
    return dialog_state_from_mapping(value, lifecycle=lifecycle)


def dialog_state_from_memory(
    user_memory: RuntimeMemory | None,
    *,
    lifecycle: str = "cold",
) -> DialogState:
    if not user_memory:
        return default_dialog_state(lifecycle=lifecycle)

    for item in user_memory.get("dialog_state", []):
        value = item.get("value")
        if isinstance(value, Mapping):
            return dialog_state_from_mapping(cast(Mapping[str, object], value), lifecycle=lifecycle)

    return default_dialog_state(lifecycle=lifecycle)
