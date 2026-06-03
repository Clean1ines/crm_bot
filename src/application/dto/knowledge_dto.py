from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal

from src.domain.commercial.price_knowledge import (
    PriceCondition,
    PriceRange,
    PriceSourceRef,
    PublishedPriceFact,
)
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_import_quality import (
    DocumentImportIssue,
    DocumentImportQualityReport,
)
from src.domain.project_plane.knowledge_views import (
    KnowledgeSearchTraceView,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingMode,
    normalize_preprocessing_mode,
)
from src.domain.project_plane.production_retrieval import ProductionRetrievalMode

KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_RUNTIME_EQUIVALENT = "runtime_equivalent"
KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_LEXICAL_DEBUG = (
    ProductionRetrievalMode.LEXICAL_DEBUG.value
)


def _metadata_text_list(metadata: Mapping[str, object], key: str) -> list[str]:
    value = metadata.get(key)
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item).strip()]
    return []


def _metadata_int(metadata: Mapping[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _metadata_int_list(metadata: Mapping[str, object], key: str) -> tuple[int, ...]:
    value = metadata.get(key)
    if isinstance(value, list | tuple):
        result: list[int] = []
        for item in value:
            if isinstance(item, bool) or item is None:
                continue
            if isinstance(item, int):
                result.append(item)
            elif isinstance(item, float) and item.is_integer():
                result.append(int(item))
            elif isinstance(item, str) and item.strip().isdigit():
                result.append(int(item.strip()))
        return tuple(result)
    single = _metadata_int(metadata, key)
    return (single,) if single is not None else ()


@dataclass(slots=True)
class KnowledgeUploadResultDto:
    message: str
    chunks: int
    document_id: str | None = None
    preprocessing_mode: str | None = None
    preprocessing_status: str | None = None
    structured_entries: int | None = None

    @classmethod
    def create(
        cls,
        *,
        message: str,
        chunks: int,
        document_id: str | None = None,
        preprocessing_mode: str | None = None,
        preprocessing_status: str | None = None,
        structured_entries: int | None = None,
    ) -> "KnowledgeUploadResultDto":
        return cls(
            message=message,
            chunks=chunks,
            document_id=document_id,
            preprocessing_mode=preprocessing_mode,
            preprocessing_status=preprocessing_status,
            structured_entries=structured_entries,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True, slots=True)
class KnowledgeUploadJobPayloadDto:
    project_id: str
    document_id: str
    file_name: str
    preprocessing_mode: str
    chunks: list[JsonObject]
    source: str | None = None
    resume_run_id: str | None = None

    def to_dict(self) -> JsonObject:
        payload: JsonObject = {
            "project_id": self.project_id,
            "document_id": self.document_id,
            "file_name": self.file_name,
            "preprocessing_mode": self.preprocessing_mode,
            "chunks": json_value_from_unknown(self.chunks),
        }
        if self.source is not None:
            payload["source"] = self.source
        if self.resume_run_id is not None:
            payload["resume_run_id"] = self.resume_run_id
        return payload

    def normalized_preprocessing_mode(self) -> KnowledgePreprocessingMode:
        return normalize_preprocessing_mode(self.preprocessing_mode)

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, object]
    ) -> "KnowledgeUploadJobPayloadDto":
        project_id = str(payload.get("project_id") or "").strip()
        document_id = str(payload.get("document_id") or "").strip()
        file_name = str(payload.get("file_name") or "").strip()
        preprocessing_mode = str(payload.get("preprocessing_mode") or "").strip()
        source = str(payload.get("source") or "").strip() or None
        resume_run_id = str(payload.get("resume_run_id") or "").strip() or None
        raw_chunks = payload.get("chunks")

        if not project_id:
            raise ValueError("knowledge upload payload missing project_id")
        if not document_id:
            raise ValueError("knowledge upload payload missing document_id")
        if not file_name:
            raise ValueError("knowledge upload payload missing file_name")
        if not preprocessing_mode:
            raise ValueError("knowledge upload payload missing preprocessing_mode")
        if not isinstance(raw_chunks, list):
            raise ValueError("knowledge upload payload chunks must be a list")

        chunks: list[JsonObject] = []
        for item in raw_chunks:
            if not isinstance(item, Mapping):
                raise ValueError("knowledge upload payload chunk must be an object")
            chunk = {
                str(key): json_value_from_unknown(value) for key, value in item.items()
            }
            content = str(chunk.get("content") or "").strip()
            if not content:
                raise ValueError("knowledge upload payload chunk missing content")
            chunk["content"] = content
            chunks.append(chunk)

        return cls(
            project_id=project_id,
            document_id=document_id,
            file_name=file_name,
            preprocessing_mode=preprocessing_mode,
            chunks=chunks,
            source=source,
            resume_run_id=resume_run_id,
        )


@dataclass(frozen=True, slots=True)
class KnowledgeUploadRequestDto:
    preprocessing_mode: str = "faq"

    def normalized_preprocessing_mode(self) -> KnowledgePreprocessingMode:
        return normalize_preprocessing_mode(self.preprocessing_mode)


@dataclass(frozen=True, slots=True)
class KnowledgeSearchTraceDto:
    matched_fields: tuple[str, ...]
    lexical_score: float
    vector_score: float
    exact_claim_match: bool
    title_match: bool
    length_penalty: float
    final_score: float
    retrieval_surface_role: str
    displayed_field: str
    is_production_safe: bool

    @classmethod
    def from_view(cls, trace: KnowledgeSearchTraceView) -> "KnowledgeSearchTraceDto":
        return cls(
            matched_fields=trace.matched_fields,
            lexical_score=trace.lexical_score,
            vector_score=trace.vector_score,
            exact_claim_match=trace.exact_claim_match,
            title_match=trace.title_match,
            length_penalty=trace.length_penalty,
            final_score=trace.final_score,
            retrieval_surface_role=trace.retrieval_surface_role,
            displayed_field=trace.displayed_field,
            is_production_safe=trace.is_production_safe,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "matched_fields": list(self.matched_fields),
            "lexical_score": self.lexical_score,
            "vector_score": self.vector_score,
            "exact_claim_match": self.exact_claim_match,
            "title_match": self.title_match,
            "length_penalty": self.length_penalty,
            "final_score": self.final_score,
            "retrieval_surface_role": self.retrieval_surface_role,
            "displayed_field": self.displayed_field,
            "is_production_safe": self.is_production_safe,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeImportIssueDto:
    code: str
    severity: str
    message: str

    @classmethod
    def from_domain(cls, issue: DocumentImportIssue) -> "KnowledgeImportIssueDto":
        return cls(code=issue.code, severity=issue.severity, message=issue.message)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeImportQualityReportDto:
    document_id: str
    status: str
    safe_to_compile: bool
    source_format: str
    extracted_text_chars: int
    source_units_count: int
    empty_units_count: int
    short_units_count: int
    table_like_units_count: int
    duplicated_headings_count: int
    source_refs_ready: bool
    warnings: tuple[KnowledgeImportIssueDto, ...]
    recommended_action: str

    @classmethod
    def from_domain(
        cls, report: DocumentImportQualityReport
    ) -> "KnowledgeImportQualityReportDto":
        return cls(
            document_id=report.document_id,
            status=report.status,
            safe_to_compile=report.safe_to_compile,
            source_format=report.source_format,
            extracted_text_chars=report.extracted_text_chars,
            source_units_count=report.source_units_count,
            empty_units_count=report.empty_units_count,
            short_units_count=report.short_units_count,
            table_like_units_count=report.table_like_units_count,
            duplicated_headings_count=report.duplicated_headings_count,
            source_refs_ready=report.source_refs_ready,
            warnings=tuple(
                KnowledgeImportIssueDto.from_domain(issue) for issue in report.warnings
            ),
            recommended_action=report.recommended_action,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "status": self.status,
            "safe_to_compile": self.safe_to_compile,
            "source_format": self.source_format,
            "extracted_text_chars": self.extracted_text_chars,
            "source_units_count": self.source_units_count,
            "empty_units_count": self.empty_units_count,
            "short_units_count": self.short_units_count,
            "table_like_units_count": self.table_like_units_count,
            "duplicated_headings_count": self.duplicated_headings_count,
            "source_refs_ready": self.source_refs_ready,
            "warnings": [warning.to_dict() for warning in self.warnings],
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeProcessingStepDto:
    id: str
    label: str
    status: str
    current: int = 0
    total: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "current": self.current,
            "total": self.total,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeProcessingActionDto:
    id: str
    label: str
    kind: str
    enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "enabled": self.enabled,
        }


def _decimal_to_text(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True, slots=True)
class KnowledgePriceMoneyDto:
    amount: str
    currency: str

    @classmethod
    def from_domain_amount(cls, amount: object) -> "KnowledgePriceMoneyDto":
        raw_amount = getattr(amount, "amount")
        raw_currency = getattr(amount, "currency")
        if not isinstance(raw_amount, Decimal):
            raw_amount = Decimal(str(raw_amount))
        return cls(amount=_decimal_to_text(raw_amount), currency=str(raw_currency))

    def to_dict(self) -> dict[str, object]:
        return {"amount": self.amount, "currency": self.currency}


@dataclass(frozen=True, slots=True)
class KnowledgePriceRangeDto:
    min_amount: KnowledgePriceMoneyDto
    max_amount: KnowledgePriceMoneyDto

    @classmethod
    def from_domain(cls, price_range: PriceRange) -> "KnowledgePriceRangeDto":
        return cls(
            min_amount=KnowledgePriceMoneyDto.from_domain_amount(
                price_range.min_amount
            ),
            max_amount=KnowledgePriceMoneyDto.from_domain_amount(
                price_range.max_amount
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "min_amount": self.min_amount.to_dict(),
            "max_amount": self.max_amount.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class KnowledgePriceConditionDto:
    text: str

    @classmethod
    def from_domain(cls, condition: PriceCondition) -> "KnowledgePriceConditionDto":
        return cls(text=condition.text)

    def to_dict(self) -> dict[str, object]:
        return {"text": self.text}


@dataclass(frozen=True, slots=True)
class KnowledgePriceSourceRefDto:
    price_document_id: str
    source_unit_id: str
    quote: str
    source_row_id: str | None = None

    @classmethod
    def from_domain(cls, source_ref: PriceSourceRef) -> "KnowledgePriceSourceRefDto":
        return cls(
            price_document_id=source_ref.price_document_id,
            source_unit_id=source_ref.source_unit_id,
            source_row_id=source_ref.source_row_id,
            quote=source_ref.quote,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "price_document_id": self.price_document_id,
            "source_unit_id": self.source_unit_id,
            "quote": self.quote,
        }
        if self.source_row_id is not None:
            payload["source_row_id"] = self.source_row_id
        return payload


@dataclass(frozen=True, slots=True)
class KnowledgePriceFactDto:
    id: str
    project_id: str
    price_document_id: str
    item_name: str
    value_kind: str
    status: str
    unit: str
    amount: KnowledgePriceMoneyDto | None = None
    price_range: KnowledgePriceRangeDto | None = None
    price_text: str = ""
    variant: Mapping[str, str] | None = None
    aliases: tuple[str, ...] = ()
    conditions: tuple[KnowledgePriceConditionDto, ...] = ()
    source_refs: tuple[KnowledgePriceSourceRefDto, ...] = ()
    confidence: str = "0"

    @classmethod
    def from_domain(cls, fact: PublishedPriceFact) -> "KnowledgePriceFactDto":
        return cls(
            id=fact.id,
            project_id=fact.project_id,
            price_document_id=fact.price_document_id,
            item_name=fact.item_name,
            value_kind=fact.value_kind.value,
            status=fact.status.value,
            unit=fact.unit,
            amount=(
                KnowledgePriceMoneyDto.from_domain_amount(fact.amount)
                if fact.amount is not None
                else None
            ),
            price_range=(
                KnowledgePriceRangeDto.from_domain(fact.price_range)
                if fact.price_range is not None
                else None
            ),
            price_text=fact.price_text,
            variant=dict(fact.variant),
            aliases=fact.aliases,
            conditions=tuple(
                KnowledgePriceConditionDto.from_domain(condition)
                for condition in fact.conditions
            ),
            source_refs=tuple(
                KnowledgePriceSourceRefDto.from_domain(source_ref)
                for source_ref in fact.source_refs
            ),
            confidence=_decimal_to_text(fact.confidence),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "project_id": self.project_id,
            "price_document_id": self.price_document_id,
            "item_name": self.item_name,
            "value_kind": self.value_kind,
            "status": self.status,
            "unit": self.unit,
            "price_text": self.price_text,
            "variant": dict(self.variant or {}),
            "aliases": list(self.aliases),
            "conditions": [condition.to_dict() for condition in self.conditions],
            "source_refs": [source_ref.to_dict() for source_ref in self.source_refs],
            "confidence": self.confidence,
        }
        if self.amount is not None:
            payload["amount"] = self.amount.to_dict()
        if self.price_range is not None:
            payload["price_range"] = self.price_range.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class KnowledgePriceFactsMutationResultDto:
    knowledge_document_id: str
    price_document_id: str
    affected_count: int
    facts: tuple[KnowledgePriceFactDto, ...]

    @classmethod
    def from_facts(
        cls,
        *,
        knowledge_document_id: str,
        price_document_id: str,
        affected_count: int,
        facts: tuple[PublishedPriceFact, ...],
    ) -> "KnowledgePriceFactsMutationResultDto":
        return cls(
            knowledge_document_id=knowledge_document_id,
            price_document_id=price_document_id,
            affected_count=affected_count,
            facts=tuple(KnowledgePriceFactDto.from_domain(fact) for fact in facts),
        )

    def to_dict(self) -> dict[str, object]:
        facts = [fact.to_dict() for fact in self.facts]
        return {
            "knowledge_document_id": self.knowledge_document_id,
            "price_document_id": self.price_document_id,
            "affected_count": self.affected_count,
            "facts": facts,
            "items": facts,
        }


@dataclass(frozen=True, slots=True)
class KnowledgePriceFactsResponseDto:
    knowledge_document_id: str
    price_document_id: str | None
    facts: tuple[KnowledgePriceFactDto, ...]

    @classmethod
    def empty(
        cls,
        *,
        knowledge_document_id: str,
    ) -> "KnowledgePriceFactsResponseDto":
        return cls(
            knowledge_document_id=knowledge_document_id,
            price_document_id=None,
            facts=(),
        )

    @classmethod
    def from_facts(
        cls,
        *,
        knowledge_document_id: str,
        price_document_id: str,
        facts: tuple[PublishedPriceFact, ...],
    ) -> "KnowledgePriceFactsResponseDto":
        return cls(
            knowledge_document_id=knowledge_document_id,
            price_document_id=price_document_id,
            facts=tuple(KnowledgePriceFactDto.from_domain(fact) for fact in facts),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "knowledge_document_id": self.knowledge_document_id,
            "price_document_id": self.price_document_id,
            "facts": [fact.to_dict() for fact in self.facts],
            "items": [fact.to_dict() for fact in self.facts],
            "is_empty": not self.facts,
        }


@dataclass(slots=True)
class SurfaceCompilationRunDto:
    id: str
    project_id: str
    document_id: str
    status: str
    compiler_kind: str
    model: str
    prompt_version: str
    started_at: str | None
    completed_at: str | None
    error_type: str | None
    error_message: str | None
    metrics: JsonObject


@dataclass(slots=True)
class SurfaceCompilationStageDto:
    id: str
    run_id: str
    stage_kind: str
    status: str
    model: str
    prompt_version: str
    input_summary: str
    output_summary: str
    tokens_input: int
    tokens_output: int
    tokens_total: int
    error_type: str | None
    error_message: str | None
    started_at: str | None
    completed_at: str | None
    metrics: JsonObject


@dataclass(slots=True)
class SurfaceCompilationResponseDto:
    run: SurfaceCompilationRunDto | None
    stages: list[SurfaceCompilationStageDto]


@dataclass(slots=True)
class RetrievalSurfaceDto:
    id: str
    run_id: str
    surface_key: str
    claim_kind: str
    title: str
    claim: str
    answer: str
    short_answer: str
    answer_scope: str
    retrieval_scope: str
    exclusion_scope: str
    status: str
    publication_status: str
    source_refs: list[str]
    source_chunk_indexes: list[int]
    confidence: float
    warnings: list[str]
    linked_candidate_id: str | None
    linked_canonical_entry_id: str | None
    linked_runtime_entry_id: str | None


@dataclass(slots=True)
class SurfacesResponseDto:
    surfaces: list[RetrievalSurfaceDto]


@dataclass(slots=True)
class RelationDto:
    parent_surface_key: str
    child_surface_key: str
    relation_type: str
    reason: str
    confidence: float


@dataclass(slots=True)
class SurfaceRelationsResponseDto:
    relations: list[RelationDto]


@dataclass(slots=True)
class OwnershipDto:
    question: str
    owner_surface_key: str
    question_kind: str
    confidence: float
    reason: str
    rejected_from_surface_keys: list[str]


@dataclass(slots=True)
class ReassignmentDto:
    question: str
    from_surface_key: str
    to_surface_key: str
    reason: str
    confidence: float


@dataclass(slots=True)
class SurfaceOwnershipResponseDto:
    ownership: list[OwnershipDto]
    reassignments: list[ReassignmentDto]


@dataclass(slots=True)
class SurfacePublishResponseDto:
    surface_id: str
    publication_status: str
    linked_runtime_entry_id: str | None
