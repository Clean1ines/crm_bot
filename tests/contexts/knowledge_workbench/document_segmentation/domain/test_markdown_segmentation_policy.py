from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.document_segmentation.domain import (
    DocumentSegmentationBudget,
    DocumentSegmentKind,
    MarkdownSegmentationCommand,
    MarkdownSegmentationPolicy,
    SegmentationModelBudgetProfile,
    SegmentationPromptProfile,
    required_segment_count,
)


def word_count_tokens(text: str) -> int:
    return len(text.split())


def _budget(*, max_source_tokens: int) -> DocumentSegmentationBudget:
    return DocumentSegmentationBudget(
        prompt=SegmentationPromptProfile(
            prompt_name="claim_observations",
            prompt_token_count=0,
        ),
        model=SegmentationModelBudgetProfile(
            profile_name="primary_model",
            max_request_input_tokens=max_source_tokens,
            reserved_output_tokens=0,
        ),
    )


def _segment(
    markdown_text: str,
    *,
    max_source_tokens: int,
    document_key: str = "document-1",
) -> tuple:
    return MarkdownSegmentationPolicy().segment(
        MarkdownSegmentationCommand(
            document_key=document_key,
            markdown_text=markdown_text,
            budget=_budget(max_source_tokens=max_source_tokens),
        ),
        token_estimator=word_count_tokens,
    )


def test_h1_sections_become_section_segments() -> None:
    markdown = """# Alpha

A1.

A2.

# Beta

B1.
"""

    segments = _segment(markdown, max_source_tokens=100)

    assert len(segments) == 2
    assert tuple(segment.kind for segment in segments) == (
        DocumentSegmentKind.SECTION,
        DocumentSegmentKind.SECTION,
    )
    assert tuple(segment.heading_path for segment in segments) == (
        ("Alpha",),
        ("Beta",),
    )
    assert segments[0].text.startswith("# Alpha")
    assert segments[1].text.startswith("# Beta")


def test_preamble_is_preserved_before_first_h1() -> None:
    markdown = """Intro text.

# Alpha

A1.
"""

    segments = _segment(markdown, max_source_tokens=100)

    assert len(segments) == 2
    assert segments[0].kind is DocumentSegmentKind.DOCUMENT_PREAMBLE
    assert segments[0].heading_path == ()
    assert segments[0].text == "Intro text."
    assert segments[1].kind is DocumentSegmentKind.SECTION
    assert segments[1].heading_path == ("Alpha",)


def test_oversized_h1_splits_into_minimal_required_parts_by_lower_headings() -> None:
    markdown = """# Alpha

## One
one two

## Two
three four

## Three
five six

## Four
seven eight
"""

    segments = _segment(markdown, max_source_tokens=8)

    assert len(segments) == 3
    assert len(segments) != 4
    assert all(segment.kind is DocumentSegmentKind.SUBSECTION for segment in segments)
    assert all(segment.heading_path[0] == "Alpha" for segment in segments)
    assert all(segment.estimated_tokens <= 8 for segment in segments)


def test_ten_paragraphs_with_two_required_parts_create_two_fragments_not_ten() -> None:
    paragraphs = "\n\n".join(f"p{index} aa bb" for index in range(1, 11))
    markdown = f"# Alpha\n\n{paragraphs}"

    segments = _segment(markdown, max_source_tokens=18)

    assert len(segments) == 2
    assert len(segments) != 10
    assert all(
        segment.kind is DocumentSegmentKind.SPLIT_FRAGMENT for segment in segments
    )
    assert "p1 aa bb" in segments[0].text
    assert "p10 aa bb" in segments[-1].text


def test_ten_paragraphs_with_three_required_parts_create_three_fragments_not_ten() -> (
    None
):
    paragraphs = "\n\n".join(f"p{index} aa bb" for index in range(1, 11))
    markdown = f"# Alpha\n\n{paragraphs}"

    segments = _segment(markdown, max_source_tokens=11)

    assert len(segments) == 3
    assert len(segments) != 10
    assert all(
        segment.kind is DocumentSegmentKind.SPLIT_FRAGMENT for segment in segments
    )
    assert "p1 aa bb" in segments[0].text
    assert "p10 aa bb" in segments[-1].text


def test_huge_paragraph_falls_back_to_approximate_text_chunks() -> None:
    markdown = "# Alpha\n\n" + " ".join(f"word{index}" for index in range(1, 31))

    segments = _segment(markdown, max_source_tokens=12)

    assert len(segments) == 3
    assert all(
        segment.kind is DocumentSegmentKind.SPLIT_FRAGMENT for segment in segments
    )
    assert all(segment.text.strip() for segment in segments)


def test_budget_uses_prompt_and_request_numbers_not_runtime_context_window() -> None:
    budget = DocumentSegmentationBudget(
        prompt=SegmentationPromptProfile(
            prompt_name="claim_observations",
            prompt_token_count=10,
        ),
        model=SegmentationModelBudgetProfile(
            profile_name="primary_model",
            max_request_input_tokens=20,
            reserved_output_tokens=5,
        ),
    )

    assert budget.max_source_segment_tokens == 5
    assert required_segment_count(estimated_tokens=6, budget=budget) == 2

    source = Path(
        "src/contexts/knowledge_workbench/document_segmentation/domain/"
        "segmentation_budget.py"
    ).read_text(encoding="utf-8")
    assert "context_window_tokens" not in source


def test_segment_keys_are_deterministic_and_change_with_text() -> None:
    markdown = "# Alpha\n\nA1."
    changed_markdown = "# Alpha\n\nA2."

    first = _segment(markdown, max_source_tokens=100)
    second = _segment(markdown, max_source_tokens=100)
    changed = _segment(changed_markdown, max_source_tokens=100)

    assert tuple(segment.segment_key for segment in first) == tuple(
        segment.segment_key for segment in second
    )
    assert tuple(segment.segment_key for segment in first) != tuple(
        segment.segment_key for segment in changed
    )


def test_invalid_atx_heading_without_space_does_not_create_h1_boundary() -> None:
    markdown = """#tag

not a heading.

# Valid

section text.
"""

    segments = _segment(markdown, max_source_tokens=100)

    assert len(segments) == 2
    assert segments[0].kind is DocumentSegmentKind.DOCUMENT_PREAMBLE
    assert "#tag" in segments[0].text
    assert segments[1].kind is DocumentSegmentKind.SECTION
    assert segments[1].heading_path == ("Valid",)


def test_invalid_budget_shapes_are_rejected() -> None:
    with pytest.raises(ValueError, match="prompt_name must be non-empty"):
        SegmentationPromptProfile(prompt_name=" ", prompt_token_count=0)

    with pytest.raises(ValueError, match="reserved_output_tokens must be <"):
        SegmentationModelBudgetProfile(
            profile_name="primary_model",
            max_request_input_tokens=10,
            reserved_output_tokens=10,
        )


def test_document_segmentation_source_guard() -> None:
    files = (
        Path(
            "src/contexts/knowledge_workbench/document_segmentation/domain/"
            "document_segment.py"
        ),
        Path(
            "src/contexts/knowledge_workbench/document_segmentation/domain/"
            "segmentation_budget.py"
        ),
        Path(
            "src/contexts/knowledge_workbench/document_segmentation/domain/"
            "markdown_segmentation_policy.py"
        ),
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)

    required_markers = [
        "DocumentSegment",
        "DocumentSegmentKind",
        "DocumentSegmentationBudget",
        "SegmentationPromptProfile",
        "SegmentationModelBudgetProfile",
        "MarkdownSegmentationPolicy",
        "MarkdownSegmentationCommand",
        "max_source_segment_tokens",
        "required_segment_count",
        "split_marker_blocks_balanced",
        "estimate_tokens_roughly",
    ]
    forbidden_markers = [
        "context_window_tokens",
        "max_output_tokens",
        "ModelProfile",
        "RateLimitProfile",
        "qwen",
        "Qwen",
        "Groq",
        "src.contexts.llm_runtime",
        "tiktoken",
        "transformers",
        "fastapi",
        "src.interfaces",
        "src.infrastructure",
        "asyncpg",
        "postgres",
        "RunClaimExtractionStageAsync",
        "DraftObservationExtractionSchedulingReconciler",
        "PROMPT_A",
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "queue",
        "worker_loop",
        "openpyxl",
        "pandas",
        "BeautifulSoup",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
