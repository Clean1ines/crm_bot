from typing import Any

VALID_TOPICS = (
    "pricing",
    "product",
    "integration",
    "support",
    "feedback",
    "other",
    "handoff",
    "angry",
)

INTENT_TO_TOPIC = {
    "ask_price": "pricing",
    "ask_features": "product",
    "ask_integration": "integration",
    "pricing": "pricing",
    "sales": "product",
    "support": "support",
    "feedback": "feedback",
    "other": "other",
    "angry": "angry",
    "handoff_request": "handoff",
}

RISK_FEATURE_KEYS = {
    "frustration",
    "anger",
    "handoff",
    "complaint",
    "chargeback",
    "refund",
}


def normalize_intent(intent: str | None) -> str:
    value = (intent or "").strip().lower()
    if not value:
        return "other"

    if value in INTENT_TO_TOPIC:
        return value

    if value in {"pricing", "sales", "support", "feedback", "other", "angry", "handoff_request"}:
        return value

    if value in {"ask_price", "price", "cost", "pricing_question"}:
        return "ask_price"

    if value in {"ask_features", "features", "product", "what_you_do"}:
        return "ask_features"

    if value in {"ask_integration", "integration", "crm", "webhook"}:
        return "ask_integration"

    return "other"


def resolve_topic(intent: str | None, features: dict[str, Any] | None = None) -> str:
    if isinstance(features, dict):
        topic = features.get("topic")
        if isinstance(topic, str):
            topic_value = topic.strip().lower()
            if topic_value in VALID_TOPICS:
                return topic_value
            if topic_value in INTENT_TO_TOPIC:
                mapped = INTENT_TO_TOPIC[topic_value]
                if mapped in VALID_TOPICS:
                    return mapped

    normalized_intent = normalize_intent(intent)
    topic = INTENT_TO_TOPIC.get(normalized_intent, normalized_intent)
    return topic if topic in VALID_TOPICS else "other"


def feature_risk_detected(features: dict[str, Any] | None) -> bool:
    if not isinstance(features, dict):
        return False

    for key, value in features.items():
        if key not in RISK_FEATURE_KEYS:
            continue

        if isinstance(value, (int, float)) and float(value) >= 0.8:
            return True

        if isinstance(value, dict):
            for nested_value in value.values():
                if isinstance(nested_value, (int, float)) and float(nested_value) >= 0.8:
                    return True

    return False
