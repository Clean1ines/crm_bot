from __future__ import annotations

from dataclasses import dataclass, replace

from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.exclusion_scope import (
    ExclusionScope,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.possible_question import (
    PossibleQuestion,
)


@dataclass(frozen=True, slots=True)
class DraftClaimObservationCleanupInput:
    observations: tuple[DraftClaimObservation, ...]


@dataclass(frozen=True, slots=True)
class DraftClaimObservationCleanupResult:
    observations: tuple[DraftClaimObservation, ...]
    removed_possible_question_count: int
    normalized_exclusion_scope_count: int


class DraftClaimObservationCleanupPolicy:
    def clean(
        self,
        input: DraftClaimObservationCleanupInput,
    ) -> DraftClaimObservationCleanupResult:
        cleaned_observations: list[DraftClaimObservation] = []
        removed_question_count = 0
        normalized_exclusion_scope_count = 0

        for observation in input.observations:
            unique_questions, removed_count = self._deduplicate_questions(
                observation.possible_questions
            )
            normalized_exclusion_scope, was_normalized = (
                self._normalize_exclusion_scope(observation.exclusion_scope)
            )

            cleaned_observations.append(
                replace(
                    observation,
                    possible_questions=unique_questions,
                    exclusion_scope=normalized_exclusion_scope,
                )
            )
            removed_question_count += removed_count
            if was_normalized:
                normalized_exclusion_scope_count += 1

        return DraftClaimObservationCleanupResult(
            observations=tuple(cleaned_observations),
            removed_possible_question_count=removed_question_count,
            normalized_exclusion_scope_count=normalized_exclusion_scope_count,
        )

    def _deduplicate_questions(
        self,
        questions: tuple[PossibleQuestion, ...],
    ) -> tuple[tuple[PossibleQuestion, ...], int]:
        seen: set[str] = set()
        unique_questions: list[PossibleQuestion] = []
        removed_count = 0

        for question in questions:
            if question.value in seen:
                removed_count += 1
                continue

            seen.add(question.value)
            unique_questions.append(question)

        return tuple(unique_questions), removed_count

    def _normalize_exclusion_scope(
        self,
        exclusion_scope: ExclusionScope,
    ) -> tuple[ExclusionScope, bool]:
        if exclusion_scope.value == "":
            return exclusion_scope, False

        parts = tuple(
            part.strip() for part in exclusion_scope.value.split(";") if part.strip()
        )
        unique_parts = self._deduplicate_parts(parts)
        normalized_value = "; ".join(unique_parts)

        if normalized_value == exclusion_scope.value:
            return exclusion_scope, False

        return ExclusionScope(normalized_value), True

    def _deduplicate_parts(self, parts: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        unique_parts: list[str] = []

        for part in parts:
            if part in seen:
                continue

            seen.add(part)
            unique_parts.append(part)

        return tuple(unique_parts)
