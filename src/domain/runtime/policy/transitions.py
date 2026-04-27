DEFAULT_DECISION = "LLM_GENERATE"
DEFAULT_CTA = "none"

TRANSITIONS = {
    ("cold", "pricing"): ("interested", "LLM_GENERATE", "book_consultation"),
    ("cold", "product"): ("interested", "LLM_GENERATE", "book_consultation"),
    ("cold", "integration"): ("interested", "LLM_GENERATE", "book_consultation"),
    ("cold", "support"): ("cold", "LLM_GENERATE", "none"),
    ("cold", "feedback"): ("cold", "LLM_GENERATE", "none"),
    ("cold", "other"): ("cold", "LLM_GENERATE", "none"),
    ("interested", "pricing"): ("warm", "LLM_GENERATE", "book_consultation"),
    ("interested", "product"): ("warm", "LLM_GENERATE", "book_consultation"),
    ("interested", "integration"): ("warm", "LLM_GENERATE", "book_consultation"),
    ("interested", "support"): ("interested", "LLM_GENERATE", "none"),
    ("interested", "feedback"): ("interested", "LLM_GENERATE", "none"),
    ("interested", "other"): ("interested", "LLM_GENERATE", "none"),
    ("warm", "pricing"): ("warm", "LLM_GENERATE", "call_manager"),
    ("warm", "product"): ("warm", "LLM_GENERATE", "call_manager"),
    ("warm", "integration"): ("warm", "LLM_GENERATE", "call_manager"),
    ("warm", "support"): ("warm", "ESCALATE_TO_HUMAN", "call_manager"),
    ("warm", "feedback"): ("warm", "LLM_GENERATE", "none"),
    ("warm", "other"): ("warm", "LLM_GENERATE", "none"),
    ("active_client", "pricing"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "product"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "integration"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "support"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "feedback"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "other"): ("active_client", "LLM_GENERATE", "none"),
    ("handoff_to_manager", "pricing"): (
        "handoff_to_manager",
        "ESCALATE_TO_HUMAN",
        "call_manager",
    ),
    ("handoff_to_manager", "product"): (
        "handoff_to_manager",
        "ESCALATE_TO_HUMAN",
        "call_manager",
    ),
    ("handoff_to_manager", "integration"): (
        "handoff_to_manager",
        "ESCALATE_TO_HUMAN",
        "call_manager",
    ),
    ("handoff_to_manager", "support"): (
        "handoff_to_manager",
        "ESCALATE_TO_HUMAN",
        "call_manager",
    ),
    ("handoff_to_manager", "feedback"): (
        "handoff_to_manager",
        "ESCALATE_TO_HUMAN",
        "call_manager",
    ),
    ("handoff_to_manager", "other"): (
        "handoff_to_manager",
        "ESCALATE_TO_HUMAN",
        "call_manager",
    ),
    ("angry", "pricing"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "product"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "integration"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "support"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "feedback"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "other"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    (None, None): ("cold", "LLM_GENERATE", "none"),
}


def lookup_transition(lifecycle: str, topic: str) -> tuple[str, str, str]:
    return TRANSITIONS.get(
        (lifecycle, topic),
        TRANSITIONS.get(
            (lifecycle, "other"),
            TRANSITIONS.get((None, None), ("cold", DEFAULT_DECISION, DEFAULT_CTA)),
        ),
    )
