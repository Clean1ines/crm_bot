from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.application.sagas import llm_dispatch_ownership
from src.contexts.knowledge_workbench.application.sagas.llm_dispatch_ownership_policy import (
    current_llm_dispatch_ownership_policy,
)


def test_default_policy_has_global_ownership_false() -> None:
    policy = current_llm_dispatch_ownership_policy()

    assert policy.capacity_queue_owns_llm_dispatch is False


def test_default_claim_builder_capacity_queue_owns_dispatch_is_false() -> None:
    policy = current_llm_dispatch_ownership_policy()

    assert policy.claim_builder_capacity_queue_owns_dispatch is False


def test_default_compaction_ownership_is_false() -> None:
    policy = current_llm_dispatch_ownership_policy()

    assert policy.draft_claim_compaction_capacity_queue_owns_dispatch is False


def test_claim_builder_ownership_is_true_when_global_and_bridge_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_dispatch_ownership, "CAPACITY_QUEUE_OWNS_LLM_DISPATCH", True
    )
    monkeypatch.setattr(
        llm_dispatch_ownership,
        "CLAIM_BUILDER_CAPACITY_DRAIN_BRIDGE_ENABLED",
        True,
    )

    policy = current_llm_dispatch_ownership_policy()

    assert policy.claim_builder_capacity_queue_owns_dispatch is True


def test_compaction_ownership_stays_false_when_bridge_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_dispatch_ownership, "CAPACITY_QUEUE_OWNS_LLM_DISPATCH", True
    )
    monkeypatch.setattr(
        llm_dispatch_ownership,
        "DRAFT_CLAIM_COMPACTION_CAPACITY_DRAIN_BRIDGE_ENABLED",
        False,
    )

    policy = current_llm_dispatch_ownership_policy()

    assert policy.draft_claim_compaction_capacity_queue_owns_dispatch is False
