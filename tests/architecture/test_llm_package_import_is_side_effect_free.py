from __future__ import annotations

from pathlib import Path


def test_infrastructure_llm_package_init_has_no_eager_adapter_imports() -> None:
    source = Path("src/infrastructure/llm/__init__.py").read_text(encoding="utf-8")

    forbidden = (
        "faq_workbench_claim_observations_generator",
        "faq_workbench_registry_merge_generator",
        "GroqLlmJsonInvocationAdapter",
        "GroqClientRotator",
        "from src.infrastructure.llm import",
        "from src.infrastructure.llm.",
    )

    violations = [marker for marker in forbidden if marker in source]
    assert violations == []


def test_ai_playground_does_not_import_retired_workbench_llm_modules() -> None:
    source = Path("src/interfaces/composition/ai_playground.py").read_text(
        encoding="utf-8"
    )

    assert "src.infrastructure.llm.groq_keyring" in source

    forbidden = (
        "faq_workbench_claim_observations_generator",
        "faq_workbench_registry_merge_generator",
        "knowledge_workbench",
    )
    violations = [marker for marker in forbidden if marker in source]
    assert violations == []
