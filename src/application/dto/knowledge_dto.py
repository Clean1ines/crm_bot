from collections.abc import Mapping
from dataclasses import asdict, dataclass

from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_import_quality import (
    DocumentImportIssue,
    DocumentImportQualityReport,
)
from src.domain.project_plane.knowledge_views import (
    KnowledgeSearchTraceView,
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


@dataclass(frozen=True, slots=True)
class KnowledgeSearchTraceDto:
    matched_fields: tuple[str, ...]
    lexical_score: float
    vector_score: float
    exact_question_match: bool
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
            exact_question_match=trace.exact_question_match,
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
            "exact_question_match": self.exact_question_match,
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
