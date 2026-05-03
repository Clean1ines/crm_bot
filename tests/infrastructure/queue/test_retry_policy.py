from src.infrastructure.queue.retry_policy import build_retry_decision


def test_build_retry_decision_clamps_transient_retry_to_minimum_delay():
    decision = build_retry_decision(
        {
            "attempts": 0,
            "max_attempts": 3,
        },
        "temporary failure",
        retry_after_seconds=5.0,
    )

    assert decision.should_retry is True
    assert decision.exhausted is False
    assert decision.backoff_seconds >= 60.0
