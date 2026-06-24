from __future__ import annotations

from fractions import Fraction

import pytest

from src.contexts.knowledge_workbench.document_segmentation.domain.segmentation_budget import (
    CLAIM_BUILDER_ROUGH_TOKEN_ESTIMATOR,
    COMPACTION_ROUGH_TOKEN_ESTIMATOR,
    RoughTokenEstimator,
    estimate_tokens_roughly,
)


def test_claim_builder_rough_estimator_uses_chars_per_token_3_3() -> None:
    assert CLAIM_BUILDER_ROUGH_TOKEN_ESTIMATOR.estimate_tokens("x" * 33) == 10
    assert CLAIM_BUILDER_ROUGH_TOKEN_ESTIMATOR.estimate_tokens("x" * 34) == 11


def test_compaction_rough_estimator_uses_chars_per_token_3_7() -> None:
    assert COMPACTION_ROUGH_TOKEN_ESTIMATOR.estimate_tokens("x" * 37) == 10
    assert COMPACTION_ROUGH_TOKEN_ESTIMATOR.estimate_tokens("x" * 38) == 11


def test_legacy_estimate_tokens_roughly_keeps_claim_builder_target() -> None:
    assert estimate_tokens_roughly("x" * 33) == 10
    assert estimate_tokens_roughly("x" * 34) == 11


def test_rough_estimator_rejects_invalid_shapes() -> None:
    with pytest.raises(TypeError, match="multiplier"):
        RoughTokenEstimator(multiplier=3.3)

    with pytest.raises(ValueError, match="multiplier"):
        RoughTokenEstimator(multiplier=Fraction(0, 1))

    with pytest.raises(TypeError, match="text"):
        CLAIM_BUILDER_ROUGH_TOKEN_ESTIMATOR.estimate_tokens(123)
