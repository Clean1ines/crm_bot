from src.domain.runtime.policy.intent_topic import resolve_current_topic


def test_resolve_current_topic_prefers_valid_current_topic():
    assert resolve_current_topic("other", {}, current_topic="product") == "product"


def test_resolve_current_topic_falls_back_for_invalid_current_topic():
    assert resolve_current_topic("support", {}, current_topic="nonsense") == "support"


def test_resolve_current_topic_uses_feature_topic_when_current_topic_missing():
    assert (
        resolve_current_topic("other", {"topic": "integration"}, current_topic=None)
        == "integration"
    )
