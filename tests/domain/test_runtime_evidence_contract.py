from __future__ import annotations

import pytest

from src.domain.runtime.evidence import (
    EvidenceBundle,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceScope,
    EvidenceSourceType,
)


def test_llm_reasoning_is_not_authoritative_evidence() -> None:
    item = EvidenceItem(
        source_type=EvidenceSourceType.LLM_REASONING,
        content="The assistant inferred that the price is probably 100.",
        scope=EvidenceScope.SYSTEM,
    )

    assert not item.is_authoritative


def test_evidence_bundle_filters_authoritative_items_and_fact_keys() -> None:
    authoritative = EvidenceItem(
        source_type=EvidenceSourceType.CRM_OPERATIONAL,
        content="Current CRM price is 5500 RUB.",
        scope=EvidenceScope.CUSTOMER,
        fact_key="price:installation",
        freshness=EvidenceFreshness.LIVE,
    )
    non_authoritative = EvidenceItem(
        source_type=EvidenceSourceType.LLM_REASONING,
        content="The model guessed a price.",
        scope=EvidenceScope.SYSTEM,
        fact_key="price:installation",
    )

    bundle = EvidenceBundle.from_items((non_authoritative, authoritative))

    assert bundle.authoritative_items() == (authoritative,)
    assert bundle.by_fact_key(" PRICE:INSTALLATION ") == (
        non_authoritative,
        authoritative,
    )
    assert bundle.without_llm_reasoning().items == (authoritative,)


def test_evidence_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="content"):
        EvidenceItem(
            source_type=EvidenceSourceType.COMPILED_KNOWLEDGE,
            content=" ",
            scope=EvidenceScope.DOCUMENT,
        )
