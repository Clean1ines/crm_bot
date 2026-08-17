from src.agent.nodes.intent_extractor import create_intent_extractor_node
from src.application.ai_playground.contracts import AI_PLAYGROUND_DEFAULT_MODEL
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    CLAIM_BUILDER_ACTIVE_MODEL_REF,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_draft_claim_compaction_dispatch_batch_command import (
    DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
    DRAFT_CLAIM_COMPACTION_DEGRADED_MODEL_REF,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.infrastructure.config.settings import Settings


SHUTDOWN_MODEL_REFS = {
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
}


def test_general_groq_route_catalog_contract() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.primary_model_ref() == "qwen/qwen3.6-27b"
    assert catalog.automatic_fallback_model_refs() == ("openai/gpt-oss-120b",)
    assert catalog.degraded_user_choice_model_ref() == "openai/gpt-oss-20b"
    assert not {route.model_ref for route in catalog.routes} & SHUTDOWN_MODEL_REFS


def test_claim_builder_and_compaction_model_contracts() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert CLAIM_BUILDER_ACTIVE_MODEL_REF == "qwen/qwen3.6-27b"
    assert catalog.automatic_fallback_model_refs() == ("openai/gpt-oss-120b",)
    assert DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF == "openai/gpt-oss-120b"
    assert DRAFT_CLAIM_COMPACTION_DEGRADED_MODEL_REF == "qwen/qwen3.6-27b"


def test_agent_and_playground_default_contracts() -> None:
    assert Settings.model_fields["GROQ_MODEL"].default == "qwen/qwen3.6-27b"
    assert Settings.model_fields["DEFAULT_MODEL"].default == "openai/gpt-oss-20b"
    assert (
        Settings.model_fields["GROQ_KNOWLEDGE_PREPROCESSING_MODEL"].default
        == "openai/gpt-oss-20b"
    )
    assert create_intent_extractor_node.__defaults__ == (
        None,
        "openai/gpt-oss-120b",
    )
    assert AI_PLAYGROUND_DEFAULT_MODEL == "qwen/qwen3.6-27b"
