from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from src.shared.json_value import JsonInputValue
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)


_CLAIM_FIELDS = frozenset(
    {
        "claim",
        "granularity",
        "possible_questions",
        "exclusion_scope",
        "evidence_block",
    }
)
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


class ClaimBuilderOutputValidationDecision(Enum):
    VALID_CLAIMS = "VALID_CLAIMS"
    VALID_EMPTY = "VALID_EMPTY"
    RETRY_SAME_MODEL = "RETRY_SAME_MODEL"
    RETRY_FALLBACK_MODEL = "RETRY_FALLBACK_MODEL"
    RETRY_LARGER_OUTPUT_LIMIT_MODEL = "RETRY_LARGER_OUTPUT_LIMIT_MODEL"
    TERMINAL_INVALID = "TERMINAL_INVALID"


class ClaimBuilderOutputValidationFailureReason(Enum):
    OUTPUT_NOT_OBJECT = "OUTPUT_NOT_OBJECT"
    CLAIMS_MISSING = "CLAIMS_MISSING"
    CLAIMS_NOT_LIST = "CLAIMS_NOT_LIST"
    CLAIMS_EMPTY_RETRY_REQUIRED = "CLAIMS_EMPTY_RETRY_REQUIRED"
    CLAIM_ITEM_NOT_OBJECT = "CLAIM_ITEM_NOT_OBJECT"
    CLAIM_FIELD_SET_INVALID = "CLAIM_FIELD_SET_INVALID"
    CLAIM_FIELD_NULL = "CLAIM_FIELD_NULL"
    CLAIM_TEXT_EMPTY = "CLAIM_TEXT_EMPTY"
    GRANULARITY_INVALID = "GRANULARITY_INVALID"
    POSSIBLE_QUESTIONS_NOT_LIST = "POSSIBLE_QUESTIONS_NOT_LIST"
    POSSIBLE_QUESTION_EMPTY = "POSSIBLE_QUESTION_EMPTY"
    EXCLUSION_SCOPE_EMPTY = "EXCLUSION_SCOPE_EMPTY"
    EVIDENCE_BLOCK_EMPTY = "EVIDENCE_BLOCK_EMPTY"
    EVIDENCE_BLOCK_NOT_SOURCE_EXCERPT = "EVIDENCE_BLOCK_NOT_SOURCE_EXCERPT"
    LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE = "LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE"
    TRUNCATED_JSON_RETRY_REQUIRED = "TRUNCATED_JSON_RETRY_REQUIRED"


@dataclass(frozen=True, slots=True)
class ValidateClaimBuilderOutputCommand:
    output_payload: JsonInputValue
    source_unit_text: str
    empty_claims_retry_already_attempted: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source_unit_text, str):
            raise TypeError("source_unit_text must be str")
        if not isinstance(self.empty_claims_retry_already_attempted, bool):
            raise TypeError("empty_claims_retry_already_attempted must be bool")


@dataclass(frozen=True, slots=True)
class ValidatedClaimBuilderClaim:
    claim: str
    granularity: DraftClaimGranularity
    possible_questions: tuple[str, ...]
    exclusion_scope: str
    evidence_block: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.claim, "claim")
        if not isinstance(self.granularity, DraftClaimGranularity):
            raise TypeError("granularity must be DraftClaimGranularity")
        if not isinstance(self.possible_questions, tuple):
            raise TypeError("possible_questions must be tuple")
        for question in self.possible_questions:
            _require_non_empty_text(question, "possible_question")
        _require_non_empty_text(self.exclusion_scope, "exclusion_scope")
        _require_non_empty_text(self.evidence_block, "evidence_block")


@dataclass(frozen=True, slots=True)
class ClaimBuilderOutputValidationResult:
    decision: ClaimBuilderOutputValidationDecision
    claims: tuple[ValidatedClaimBuilderClaim, ...]
    failure_reason: ClaimBuilderOutputValidationFailureReason | None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ClaimBuilderOutputValidationDecision):
            raise TypeError("decision must be ClaimBuilderOutputValidationDecision")
        if not isinstance(self.claims, tuple):
            raise TypeError("claims must be tuple")
        for claim in self.claims:
            if not isinstance(claim, ValidatedClaimBuilderClaim):
                raise TypeError("claims must contain ValidatedClaimBuilderClaim")
        if self.failure_reason is not None and not isinstance(
            self.failure_reason,
            ClaimBuilderOutputValidationFailureReason,
        ):
            raise TypeError(
                "failure_reason must be ClaimBuilderOutputValidationFailureReason"
            )

        if self.decision is ClaimBuilderOutputValidationDecision.VALID_CLAIMS:
            if not self.claims:
                raise ValueError("VALID_CLAIMS requires non-empty claims")
            if self.failure_reason is not None:
                raise ValueError("VALID_CLAIMS requires empty failure_reason")
            return

        if self.decision is ClaimBuilderOutputValidationDecision.VALID_EMPTY:
            if self.claims:
                raise ValueError("VALID_EMPTY requires empty claims")
            if self.failure_reason is not None:
                raise ValueError("VALID_EMPTY requires empty failure_reason")
            return

        if self.claims:
            raise ValueError("retry/terminal decisions require empty claims")
        if self.failure_reason is None:
            raise ValueError("retry/terminal decisions require failure_reason")


class ClaimBuilderOutputValidationPolicy:
    def validate(
        self,
        command: ValidateClaimBuilderOutputCommand,
    ) -> ClaimBuilderOutputValidationResult:
        if not isinstance(command.output_payload, Mapping):
            return _failure(
                ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
                ClaimBuilderOutputValidationFailureReason.OUTPUT_NOT_OBJECT,
            )

        payload = command.output_payload
        if "claims" not in payload:
            return _failure(
                ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
                ClaimBuilderOutputValidationFailureReason.CLAIMS_MISSING,
            )

        claims_value = payload["claims"]
        if not isinstance(claims_value, list):
            return _failure(
                ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
                ClaimBuilderOutputValidationFailureReason.CLAIMS_NOT_LIST,
            )

        if not claims_value:
            if command.empty_claims_retry_already_attempted:
                return ClaimBuilderOutputValidationResult(
                    decision=ClaimBuilderOutputValidationDecision.VALID_EMPTY,
                    claims=(),
                    failure_reason=None,
                )
            return _failure(
                ClaimBuilderOutputValidationDecision.RETRY_FALLBACK_MODEL,
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED,
            )

        validated_claims: list[ValidatedClaimBuilderClaim] = []
        for claim_value in claims_value:
            claim_result = _validate_claim_item(
                claim_value=claim_value,
                source_unit_text=command.source_unit_text,
            )
            if isinstance(claim_result, ClaimBuilderOutputValidationResult):
                return claim_result
            validated_claims.append(claim_result)

        return ClaimBuilderOutputValidationResult(
            decision=ClaimBuilderOutputValidationDecision.VALID_CLAIMS,
            claims=tuple(validated_claims),
            failure_reason=None,
        )


def _validate_claim_item(
    *,
    claim_value: JsonInputValue,
    source_unit_text: str,
) -> ValidatedClaimBuilderClaim | ClaimBuilderOutputValidationResult:
    if not isinstance(claim_value, Mapping):
        return _failure(
            ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
            ClaimBuilderOutputValidationFailureReason.CLAIM_ITEM_NOT_OBJECT,
        )

    claim_mapping = claim_value
    if set(claim_mapping.keys()) != _CLAIM_FIELDS:
        return _failure(
            ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
            ClaimBuilderOutputValidationFailureReason.CLAIM_FIELD_SET_INVALID,
        )

    for value in claim_mapping.values():
        if value is None:
            return _failure(
                ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
                ClaimBuilderOutputValidationFailureReason.CLAIM_FIELD_NULL,
            )

    claim_text = _non_empty_string(
        claim_mapping["claim"],
        ClaimBuilderOutputValidationFailureReason.CLAIM_TEXT_EMPTY,
    )
    if isinstance(claim_text, ClaimBuilderOutputValidationResult):
        return claim_text

    granularity = _granularity(claim_mapping["granularity"])
    if isinstance(granularity, ClaimBuilderOutputValidationResult):
        return granularity

    questions = _possible_questions(claim_mapping["possible_questions"])
    if isinstance(questions, ClaimBuilderOutputValidationResult):
        return questions

    exclusion_scope = _non_empty_string(
        claim_mapping["exclusion_scope"],
        ClaimBuilderOutputValidationFailureReason.EXCLUSION_SCOPE_EMPTY,
    )
    if isinstance(exclusion_scope, ClaimBuilderOutputValidationResult):
        return exclusion_scope

    evidence_block = _non_empty_string(
        claim_mapping["evidence_block"],
        ClaimBuilderOutputValidationFailureReason.EVIDENCE_BLOCK_EMPTY,
    )
    if isinstance(evidence_block, ClaimBuilderOutputValidationResult):
        return evidence_block

    evidence_excerpt = evidence_block.strip()
    if evidence_excerpt not in source_unit_text:
        return _failure(
            ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
            ClaimBuilderOutputValidationFailureReason.EVIDENCE_BLOCK_NOT_SOURCE_EXCERPT,
        )

    latin_result = _validate_latin_tokens_against_evidence(
        claim_text=claim_text,
        possible_questions=questions,
        exclusion_scope=exclusion_scope,
        evidence_block=evidence_block,
    )
    if latin_result is not None:
        return latin_result

    return ValidatedClaimBuilderClaim(
        claim=claim_text,
        granularity=granularity,
        possible_questions=questions,
        exclusion_scope=exclusion_scope,
        evidence_block=evidence_block,
    )


def _non_empty_string(
    value: JsonInputValue,
    failure_reason: ClaimBuilderOutputValidationFailureReason,
) -> str | ClaimBuilderOutputValidationResult:
    if not isinstance(value, str) or not value.strip():
        return _failure(
            ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
            failure_reason,
        )
    return value


def _granularity(
    value: JsonInputValue,
) -> DraftClaimGranularity | ClaimBuilderOutputValidationResult:
    if not isinstance(value, str) or not value.strip():
        return _failure(
            ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
            ClaimBuilderOutputValidationFailureReason.GRANULARITY_INVALID,
        )
    try:
        return DraftClaimGranularity(value)
    except ValueError:
        return _failure(
            ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
            ClaimBuilderOutputValidationFailureReason.GRANULARITY_INVALID,
        )


def _possible_questions(
    value: JsonInputValue,
) -> tuple[str, ...] | ClaimBuilderOutputValidationResult:
    if not isinstance(value, list):
        return _failure(
            ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
            ClaimBuilderOutputValidationFailureReason.POSSIBLE_QUESTIONS_NOT_LIST,
        )

    questions: list[str] = []
    for question_value in value:
        if not isinstance(question_value, str) or not question_value.strip():
            return _failure(
                ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
                ClaimBuilderOutputValidationFailureReason.POSSIBLE_QUESTION_EMPTY,
            )
        questions.append(question_value)
    return tuple(questions)


def _validate_latin_tokens_against_evidence(
    *,
    claim_text: str,
    possible_questions: tuple[str, ...],
    exclusion_scope: str,
    evidence_block: str,
) -> ClaimBuilderOutputValidationResult | None:
    evidence_tokens = frozenset(_latin_tokens(evidence_block))
    checked_texts = (claim_text, exclusion_scope, *possible_questions)

    for text in checked_texts:
        for token in _latin_tokens(text):
            if token not in evidence_tokens:
                return _failure(
                    ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
                    ClaimBuilderOutputValidationFailureReason.LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE,
                )
    return None


def _latin_tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in _LATIN_TOKEN_RE.finditer(text))


def _failure(
    decision: ClaimBuilderOutputValidationDecision,
    failure_reason: ClaimBuilderOutputValidationFailureReason,
) -> ClaimBuilderOutputValidationResult:
    return ClaimBuilderOutputValidationResult(
        decision=decision,
        claims=(),
        failure_reason=failure_reason,
    )


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
