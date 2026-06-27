from typing import cast

import pytest
from fractions import Fraction

from src.contexts.knowledge_workbench.document_segmentation.domain import (
    COMPACTION_ROUGH_TOKEN_ESTIMATOR,
    RoughTokenEstimator,
)


def test_compaction_rough_token_estimator_uses_legacy_3_7_multiplier() -> None:
    assert COMPACTION_ROUGH_TOKEN_ESTIMATOR.estimate_tokens("x" * 37) == 10
    assert COMPACTION_ROUGH_TOKEN_ESTIMATOR.estimate_tokens("x" * 38) == 11


def test_custom_rough_token_estimator_rounds_up() -> None:
    estimator = RoughTokenEstimator(multiplier=Fraction(5, 2))

    assert estimator.estimate_tokens("x" * 5) == 2
    assert estimator.estimate_tokens("x" * 6) == 3


def test_rough_token_estimator_rejects_invalid_input() -> None:
    estimator = RoughTokenEstimator(multiplier=Fraction(5, 2))

    with pytest.raises(TypeError, match="text"):
        estimator.estimate_tokens(cast(str, 123))


def test_rough_token_estimator_rejects_invalid_multiplier() -> None:
    with pytest.raises(ValueError, match="multiplier"):
        RoughTokenEstimator(multiplier=Fraction(0, 1))
