from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from src.application.ports.knowledge_port import KnowledgePreprocessorPort
from src.application.services.knowledge_answer_resolution_service import (
    KnowledgeAnswerResolutionService,
)
from src.application.services.knowledge_answer_resolution_service import (
    _answer_resolution_decision_is_publishable,
)
from src.application.services.knowledge_answer_resolution_service import (
    _apply_answer_resolution_decisions,
)
from src.application.services.knowledge_answer_resolution_service import (
    reject_noisy_answer_resolution_decisions,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgeAnswerResolutionDecision,
    KnowledgePreprocessingEntry,
)


def _entry(
    *,
    title: str,
    answer: str,
    question: str,
    source_excerpt: str | None = None,
) -> KnowledgePreprocessingEntry:
    return KnowledgePreprocessingEntry(
        title=title,
        canonical_question=question,
        answer=answer,
        source_excerpt=source_excerpt or answer,
        questions=(question,),
        synonyms=(),
        tags=("faq",),
    )


class FakePreprocessor:
    def __init__(
        self, decisions: tuple[KnowledgeAnswerResolutionDecision, ...]
    ) -> None:
        self.decisions = decisions
        self.calls = 0

    async def resolve_answer_cases(self, **_kwargs: object) -> object:
        self.calls += 1
        return SimpleNamespace(
            result=SimpleNamespace(
                decisions=self.decisions,
            )
        )


def test_invalid_noisy_merge_is_rejected() -> None:
    decision = KnowledgeAnswerResolutionDecision(
        case_id="case-1",
        action="merge",
        candidate_ids=("entry-0", "entry-1"),
        canonical_answer="CRM bot. CRM bot. CRM bot. CRM bot. CRM bot. CRM bot.",
    )

    filtered = reject_noisy_answer_resolution_decisions((decision,))

    assert len(filtered) == 1
    rejected = filtered[0]
    assert rejected.action == "keep_separate"
    assert rejected.candidate_ids == ("entry-0", "entry-1")
    assert rejected.canonical_answer == ""
    assert rejected.confidence == 0.0


@pytest.mark.asyncio
async def test_keep_separate_remains_separate() -> None:
    entries = (
        _entry(
            title="Refund",
            answer="Refund depends on project stage.",
            question="Can I get a refund?",
        ),
        _entry(
            title="Refund timing",
            answer="Refund timing depends on payment status.",
            question="When is refund available?",
        ),
    )
    preprocessor = FakePreprocessor(
        (
            KnowledgeAnswerResolutionDecision(
                case_id="case-1",
                action="keep_separate",
                candidate_ids=(),
                canonical_answer="",
            ),
        )
    )

    result = await KnowledgeAnswerResolutionService().resolve_compiled_answer_cases(
        preprocessor=cast(KnowledgePreprocessorPort, preprocessor),
        mode="faq",
        file_name="faq.md",
        entries=entries,
        source_excerpts_by_entry=(
            ("Refund depends on project stage.",),
            ("Refund timing depends on payment status.",),
        ),
        existing_project_titles=(),
    )

    assert result.entries == entries
    assert result.source_excerpts_by_entry == (
        ("Refund depends on project stage.",),
        ("Refund timing depends on payment status.",),
    )
    assert result.metrics["kept_separate_count"] == 1
    assert result.metrics["resolved_answer_count"] == 0


def test_language_mismatch_decision_is_not_publishable() -> None:
    entries = (
        _entry(
            title="Возврат",
            answer="Возврат зависит от этапа проекта.",
            question="Можно ли вернуть оплату?",
        ),
        _entry(
            title="Условия возврата",
            answer="Условия возврата описаны в договоре.",
            question="Какие условия возврата?",
        ),
    )
    decision = KnowledgeAnswerResolutionDecision(
        case_id="case-ru",
        action="merge",
        candidate_ids=("entry-0", "entry-1"),
        canonical_answer="Refund depends on the project stage and contract.",
    )

    assert not _answer_resolution_decision_is_publishable(decision, entries=entries)


def test_source_excerpts_stay_aligned_with_entries_after_merge() -> None:
    entries = (
        _entry(
            title="Support",
            answer="Support is available in chat.",
            question="Where is support?",
            source_excerpt="Support is available in chat.",
        ),
        _entry(
            title="Support email",
            answer="Support is also available by email.",
            question="Where is support?",
            source_excerpt="Support is also available by email.",
        ),
        _entry(
            title="Pricing",
            answer="Pricing depends on scope.",
            question="How much does it cost?",
            source_excerpt="Pricing depends on scope.",
        ),
    )
    decision = KnowledgeAnswerResolutionDecision(
        case_id="case-support",
        action="merge",
        candidate_ids=("entry-0", "entry-1"),
        canonical_answer="Support is available in chat and by email.",
    )

    merged_entries, source_excerpts = _apply_answer_resolution_decisions(
        entries=entries,
        decisions=(decision,),
        source_excerpts_by_entry=(
            ("Support is available in chat.",),
            ("Support is also available by email.",),
            ("Pricing depends on scope.",),
        ),
    )

    assert len(merged_entries) == 2
    assert merged_entries[0].answer == "Support is available in chat and by email."
    assert source_excerpts[0] == (
        "Support is available in chat.",
        "Support is also available by email.",
    )
    assert merged_entries[1].title == "Pricing"
    assert source_excerpts[1] == ("Pricing depends on scope.",)
