from src.domain.runtime.load_state import LoadStateResult


def test_load_state_result_builds_memory_index_and_serializes_patch():
    result = LoadStateResult(
        conversation_summary="summary",
        history=[{"role": "user", "content": "hello"}],
        client_id="client-1",
    )
    memories = [
        {"type": "system", "key": "topic", "value": "pricing"},
        {"type": "profile", "key": "company", "value": "Acme"},
    ]

    result.user_memory = LoadStateResult.build_memory_index(memories)
    result.apply_system_memory(memories)

    assert result.to_state_patch()["user_memory"] == {
        "system": [{"key": "topic", "value": "pricing"}],
        "profile": [{"key": "company", "value": "Acme"}],
    }
    assert result.to_state_patch()["topic"] == "pricing"
