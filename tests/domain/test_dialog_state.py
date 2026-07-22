from src.domain.runtime.dialog_state import (
    default_dialog_state,
    dialog_state_from_memory,
    merge_dialog_state,
)
from src.domain.runtime.policy.repeat_detection import build_dialog_state_update


def test_default_dialog_state_uses_requested_lifecycle():
    cold_state = default_dialog_state()
    active_client_state = default_dialog_state(lifecycle="active_client")

    assert cold_state["lead_status"] == "cold"
    assert cold_state["lifecycle"] == "cold"
    assert cold_state["handoff_confirmation_pending"] is False
    assert cold_state["last_repeat_increment_reason"] is None
    assert cold_state["last_repeat_reset_reason"] is None
    assert active_client_state["lead_status"] == "active_client"
    assert active_client_state["lifecycle"] == "active_client"
    assert active_client_state["handoff_confirmation_pending"] is False


def test_merge_dialog_state_preserves_defaults_and_overrides_fields():
    merged = merge_dialog_state(
        {"last_intent": "ask_price", "repeat_count": 2},
        lifecycle="warm",
    )

    assert merged == {
        "last_intent": "ask_price",
        "last_cta": None,
        "last_topic": None,
        "repeat_count": 2,
        "last_repeat_increment_reason": None,
        "last_repeat_reset_reason": None,
        "lead_status": "warm",
        "lifecycle": "warm",
        "handoff_confirmation_pending": False,
    }


def test_dialog_state_from_memory_reads_and_normalizes_snapshot():
    state = dialog_state_from_memory(
        {
            "dialog_state": [
                {
                    "key": "dialog_state",
                    "value": {"last_topic": "pricing", "repeat_count": 3},
                }
            ]
        },
        lifecycle="interested",
    )

    assert state == {
        "last_intent": None,
        "last_cta": None,
        "last_topic": "pricing",
        "repeat_count": 3,
        "last_repeat_increment_reason": None,
        "last_repeat_reset_reason": None,
        "lead_status": "interested",
        "lifecycle": "interested",
        "handoff_confirmation_pending": False,
    }


def test_dialog_state_normalizes_none_cta_as_absent():
    state = merge_dialog_state({"last_cta": "none"}, lifecycle="warm")

    assert state["last_cta"] is None


def test_dialog_state_normalizes_repeat_reason_values():
    state = merge_dialog_state(
        {
            "last_repeat_increment_reason": "explicit_repeat_like",
            "last_repeat_reset_reason": "not_repeat_like",
        }
    )

    assert state["last_repeat_increment_reason"] == "explicit_repeat_like"
    assert state["last_repeat_reset_reason"] == "not_repeat_like"


def test_dialog_state_drops_unknown_repeat_reason_values():
    state = merge_dialog_state(
        {
            "last_repeat_increment_reason": "legacy_increment_reason",
            "last_repeat_reset_reason": "freeform_dynamic_reason",
        }
    )

    assert state["last_repeat_increment_reason"] is None
    assert state["last_repeat_reset_reason"] is None


def test_dialog_state_update_clears_reset_reason_on_increment():
    state = build_dialog_state_update(
        {"repeat_count": 2, "last_repeat_reset_reason": "new_topic"},
        intent="pricing",
        topic="pricing",
        cta="none",
        lifecycle="warm",
        decision="RESPOND",
        turn_relation="continuation",
        is_repeat_like=True,
    )

    assert state["repeat_count"] == 3
    assert state["last_repeat_increment_reason"] == "explicit_repeat_like"
    assert state["last_repeat_reset_reason"] is None


def test_dialog_state_update_clears_increment_reason_on_reset():
    state = build_dialog_state_update(
        {"repeat_count": 9, "last_repeat_increment_reason": "explicit_repeat_like"},
        intent="support",
        topic="support",
        cta="none",
        lifecycle="warm",
        decision="RESPOND",
        turn_relation="continuation",
        is_repeat_like=False,
    )

    assert state["repeat_count"] == 0
    assert state["last_repeat_increment_reason"] is None
    assert state["last_repeat_reset_reason"] == "not_repeat_like"
