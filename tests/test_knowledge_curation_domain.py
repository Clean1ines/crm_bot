from __future__ import annotations

import pytest

from src.application.errors import ValidationError
from src.application.services.knowledge_curation_service import (
    KnowledgeCurationService,
    build_duplicate_groups,
    classify_curation_issues,
    dedupe_text_values,
)
from src.domain.project_plane.knowledge_compilation import (
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
)
from src.domain.project_plane.knowledge_curation import (
    KnowledgeCurationEntryView,
    KnowledgeCurationIssueType,
    KnowledgeEntryMergeRequest,
)


def entry(
    entry_id: str,
    *,
    title: str = "Title",
    answer: str = "Long enough answer with useful grounded text",
    status: KnowledgeEntryStatus = KnowledgeEntryStatus.NEEDS_REVIEW,
    visibility: KnowledgeEntryVisibility = KnowledgeEntryVisibility.OWNER_ONLY,
    source_refs: tuple[dict[str, object], ...] = (
        {"quote": "quote", "source_chunk_id": "chunk", "source_index": 0},
    ),
    enrichment: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
    has_retrieval_surface: bool = False,
    has_embedding: bool = True,
    version: int = 1,
) -> KnowledgeCurationEntryView:
    return KnowledgeCurationEntryView(
        id=entry_id,
        project_id="project",
        document_id="document",
        stable_key=f"stable-{entry_id}",
        entry_kind=KnowledgeEntryKind.ANSWER,
        title=title,
        answer=answer,
        status=status,
        visibility=visibility,
        version=version,
        enrichment=enrichment or {"questions": ["How to buy?"], "tags": ["sales"]},
        source_refs=source_refs,
        metadata=metadata or {},
        has_retrieval_surface=has_retrieval_surface,
        has_embedding=has_embedding,
        runtime_eligible=status == KnowledgeEntryStatus.PUBLISHED
        and visibility == KnowledgeEntryVisibility.RUNTIME
        and bool(source_refs),
    )


def test_dedupe_text_values_normalizes_exact_values() -> None:
    assert dedupe_text_values(["  Привет  мир", "привет мир", "Другой"]) == (
        "Привет мир",
        "Другой",
    )


def test_classify_curation_issues_detects_runtime_inconsistency() -> None:
    issues = classify_curation_issues(
        entry(
            "a",
            answer="short",
            status=KnowledgeEntryStatus.PUBLISHED,
            visibility=KnowledgeEntryVisibility.RUNTIME,
            source_refs=(),
            has_retrieval_surface=False,
            has_embedding=False,
        )
    )
    issue_types = {issue.type for issue in issues}
    assert KnowledgeCurationIssueType.EMPTY_OR_TOO_SHORT_ANSWER in issue_types
    assert KnowledgeCurationIssueType.MISSING_SOURCE_REFS in issue_types
    assert KnowledgeCurationIssueType.PUBLISHED_WITHOUT_RETRIEVAL_ROW in issue_types
    assert KnowledgeCurationIssueType.PUBLISHED_WITHOUT_EMBEDDING in issue_types


def test_duplicate_group_detection_exact_title_answer_and_source_quote() -> None:
    groups = build_duplicate_groups(
        (
            entry(
                "a",
                title="Same",
                answer="Same answer body",
                source_refs=(
                    {"quote": "Same quote", "source_chunk_id": "c1", "source_index": 0},
                ),
            ),
            entry(
                "b",
                title=" same ",
                answer="same answer body",
                source_refs=(
                    {"quote": "same quote", "source_chunk_id": "c2", "source_index": 0},
                ),
            ),
        )
    )
    issue_types = {group.issue_type for group in groups}
    assert KnowledgeCurationIssueType.DUPLICATE_TITLE in issue_types
    assert KnowledgeCurationIssueType.DUPLICATE_ANSWER in issue_types
    assert KnowledgeCurationIssueType.SAME_SOURCE_QUOTE in issue_types


def test_merge_preview_blocks_absorbed_parent_and_version_conflict() -> None:
    service = KnowledgeCurationService(repository=object())
    parent = entry("parent", version=3)
    absorbed = entry("child", metadata={"curation": {"merged_into": "other"}})
    preview = service._build_merge_preview_from_entries(
        request=KnowledgeEntryMergeRequest(
            parent_entry_id="parent",
            absorbed_entry_ids=("child",),
            parent_expected_version=2,
            absorbed_expected_versions={"child": 1},
            idempotency_key="k",
        ),
        by_id={"parent": parent, "child": absorbed},
    )
    assert "parent_version_conflict" in preview.blocking_errors
    assert "absorbed_already_merged:child" in preview.blocking_errors


def test_merge_shape_rejects_parent_in_absorbed_ids() -> None:
    service = KnowledgeCurationService(repository=object())
    with pytest.raises(ValidationError):
        service._build_merge_preview_from_entries(
            request=KnowledgeEntryMergeRequest(
                parent_entry_id="a", absorbed_entry_ids=("a",), idempotency_key="k"
            ),
            by_id={"a": entry("a")},
        )
