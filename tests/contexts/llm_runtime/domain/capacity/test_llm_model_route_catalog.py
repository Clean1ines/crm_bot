import pytest

from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRoute,
    LlmModelRouteCatalog,
    LlmModelRouteRole,
    default_groq_llm_model_route_catalog,
)


def test_default_catalog_primary_is_qwen() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.primary_model_ref() == "qwen/qwen3-32b"


def test_default_catalog_automatic_fallback_refs_are_ordered() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.automatic_fallback_model_refs() == (
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    )


def test_default_catalog_degraded_user_choice_model() -> None:
    catalog = default_groq_llm_model_route_catalog()

    assert catalog.degraded_user_choice_model_ref() == "llama-3.1-8b-instant"


def test_route_for_model_ref_returns_role_and_order() -> None:
    catalog = default_groq_llm_model_route_catalog()

    route = catalog.route_for_model_ref("openai/gpt-oss-120b")

    assert route is not None
    assert route.role is LlmModelRouteRole.AUTOMATIC_FALLBACK
    assert route.order == 1


def test_rejects_duplicate_model_ref() -> None:
    with pytest.raises(ValueError, match="unique model_ref"):
        LlmModelRouteCatalog(
            routes=(
                LlmModelRoute(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=0,
                ),
                LlmModelRoute(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=1,
                ),
            ),
        )


def test_rejects_duplicate_primary_role() -> None:
    with pytest.raises(ValueError, match="exactly one PRIMARY"):
        LlmModelRouteCatalog(
            routes=(
                LlmModelRoute(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=0,
                ),
                LlmModelRoute(
                    model_ref="openai/gpt-oss-120b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=1,
                ),
                LlmModelRoute(
                    model_ref="llama-3.1-8b-instant",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=2,
                ),
            ),
        )


def test_rejects_duplicate_degraded_user_choice_role() -> None:
    with pytest.raises(ValueError, match="exactly one DEGRADED_USER_CHOICE"):
        LlmModelRouteCatalog(
            routes=(
                LlmModelRoute(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=0,
                ),
                LlmModelRoute(
                    model_ref="llama-3.1-8b-instant",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=1,
                ),
                LlmModelRoute(
                    model_ref="llama-3.1-8b-alt",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=2,
                ),
            ),
        )


def test_rejects_duplicate_order() -> None:
    with pytest.raises(ValueError, match="unique order"):
        LlmModelRouteCatalog(
            routes=(
                LlmModelRoute(
                    model_ref="qwen/qwen3-32b",
                    role=LlmModelRouteRole.PRIMARY,
                    order=0,
                ),
                LlmModelRoute(
                    model_ref="llama-3.1-8b-instant",
                    role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
                    order=0,
                ),
            ),
        )
