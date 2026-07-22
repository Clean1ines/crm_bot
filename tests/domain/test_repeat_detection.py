from src.domain.runtime.policy.repeat_detection import evaluate_repeat_count


def test_repeat_count_resets_for_new_independent_topics():
    state = {"last_intent": "other", "last_topic": "product", "repeat_count": 4}

    result = evaluate_repeat_count(
        state,
        "other",
        "integration",
        turn_relation="new_topic",
        is_repeat_like=False,
    )

    assert result.count == 0
    assert result.increment_reason is None
    assert result.reset_reason == "new_topic"


def test_repeat_count_increments_only_with_repeat_evidence():
    state = {"last_intent": "pricing", "last_topic": "pricing", "repeat_count": 2}

    result = evaluate_repeat_count(
        state,
        "pricing",
        "pricing",
        turn_relation="continuation",
        is_repeat_like=True,
    )

    assert result.count == 3
    assert result.increment_reason == "explicit_repeat_like"
    assert result.reset_reason is None


def test_repeat_count_does_not_increment_for_same_topic_without_repeat_evidence():
    state = {"last_intent": "pricing", "last_topic": "pricing", "repeat_count": 4}

    result = evaluate_repeat_count(
        state,
        "pricing",
        "pricing",
        turn_relation="continuation",
        is_repeat_like=False,
    )

    assert result.count == 0
    assert result.increment_reason is None
    assert result.reset_reason == "not_repeat_like"


def test_repeat_count_resets_old_accumulated_count_on_new_topic():
    state = {"last_intent": "other", "last_topic": "product", "repeat_count": 9}

    result = evaluate_repeat_count(
        state,
        "other",
        "integration",
        turn_relation="new_topic",
        is_repeat_like=False,
    )

    assert result.count == 0
    assert result.increment_reason is None
    assert result.reset_reason == "new_topic"


def test_repeat_count_resets_old_accumulated_count_without_repeat_evidence():
    state = {"last_intent": "support", "last_topic": "support", "repeat_count": 9}

    result = evaluate_repeat_count(
        state,
        "support",
        "support",
        turn_relation="continuation",
        is_repeat_like=False,
    )

    assert result.count == 0
    assert result.increment_reason is None
    assert result.reset_reason == "not_repeat_like"


def test_repeat_count_reaches_escalation_threshold_only_for_current_repeat():
    state = {"last_intent": "pricing", "last_topic": "pricing", "repeat_count": 2}

    result = evaluate_repeat_count(
        state,
        "pricing",
        "pricing",
        turn_relation="continuation",
        is_repeat_like=True,
    )

    assert result.count == 3
    assert result.increment_reason == "explicit_repeat_like"
    assert result.reset_reason is None
