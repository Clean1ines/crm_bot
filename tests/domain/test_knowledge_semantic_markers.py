from __future__ import annotations

import re

from src.domain.project_plane.knowledge_semantic_markers import (
    BROAD_NOISY_PRICE_SYNONYMS,
    FAQ_ANSWER_MARKERS,
    INTERNAL_EVAL_TEST_MARKERS,
    MARKDOWN_HEADER_PATTERN,
    MARKDOWN_HEADER_STRIP_PATTERN,
    NEGATIVE_TEST_MARKERS,
    SEMANTIC_TAG_STOP_WORDS,
    SEMANTIC_TAG_TERM_PATTERN,
)


def test_semantic_marker_module_covers_multilingual_eval_guards() -> None:
    assert "expected answer" in INTERNAL_EVAL_TEST_MARKERS
    assert "ожидаемый ответ" in INTERNAL_EVAL_TEST_MARKERS
    assert "do not hallucinate" in NEGATIVE_TEST_MARKERS
    assert "не выдумывать" in NEGATIVE_TEST_MARKERS
    assert "answer:" in FAQ_ANSWER_MARKERS
    assert "ответ:" in FAQ_ANSWER_MARKERS


def test_semantic_marker_module_exposes_builder_patterns() -> None:
    assert re.search(MARKDOWN_HEADER_PATTERN, "## Product overview")
    assert re.sub(MARKDOWN_HEADER_STRIP_PATTERN, "", "## Product overview") == (
        "Product overview"
    )
    assert re.findall(SEMANTIC_TAG_TERM_PATTERN, "Product overview / база знаний")
    assert "the" in SEMANTIC_TAG_STOP_WORDS
    assert "база" in SEMANTIC_TAG_STOP_WORDS


def test_noisy_price_synonyms_are_centralized() -> None:
    assert "сколько стоит" in BROAD_NOISY_PRICE_SYNONYMS
    assert "price please" in BROAD_NOISY_PRICE_SYNONYMS
