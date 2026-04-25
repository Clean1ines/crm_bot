from src.domain.runtime.dialog_state import (
    default_dialog_state,
    dialog_state_from_memory,
    merge_dialog_state,
)


def test_default_dialog_state_uses_requested_lifecycle():
    cold_state = default_dialog_state()
    active_client_state = default_dialog_state(lifecycle="active_client")

    assert cold_state["lead_status"] == "cold"
    assert cold_state["lifecycle"] == "cold"
    assert active_client_state["lead_status"] == "active_client"
    assert active_client_state["lifecycle"] == "active_client"


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
        "lead_status": "warm",
        "lifecycle": "warm",
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
        "lead_status": "interested",
        "lifecycle": "interested",
    }
