from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from typing import Protocol

from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchFreshUploadRepositoryPort,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DocumentSectionStatus,
    DomainInvariantError,
    JsonValue,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeDocumentUploadActorType,
    KnowledgeProcessingRun,
    ProcessingMethod,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeKind,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    ProcessingRunStatus,
    ProcessingTrigger,
    FactRegistry,
    FactRegistryStatus,
    RegistrySnapshot,
    ResumePolicy,
    SourceType,
)


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class FaqWorkbenchFreshUploadCommand:
    project_id: str
    file_name: str
    upload_id: str
    raw_text: str
    file_size_bytes: int
    source_type: SourceType = SourceType.MARKDOWN
    content_hash: str | None = None
    uploaded_by_user_id: str | None = None
    uploaded_by_actor_type: str = KnowledgeDocumentUploadActorType.UNKNOWN.value
    uploaded_by_actor_id: str | None = None
    trusted_upload: bool = False


@dataclass(frozen=True, slots=True)
class FaqWorkbenchFreshUploadResult:
    document: KnowledgeDocument
    sections: tuple[DocumentSection, ...]
    processing_run: KnowledgeProcessingRun
    registry: FactRegistry
    initialize_node_run: ProcessingNodeRun
    initialize_artifact: ProcessingNodeArtifact
    initial_snapshot: RegistrySnapshot


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(slots=True)
class MonotonicIdFactory:
    _counter: count[int]

    @classmethod
    def create(cls) -> MonotonicIdFactory:
        return cls(_counter=count(1))

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._counter)}"


@dataclass(frozen=True, slots=True)
class MarkdownSection:
    section_index: int
    section_key: str
    heading_path: tuple[str, ...]
    title: str
    raw_text: str
    normalized_text: str
    parent_section_key: str | None


class MarkdownSectioner:
    _heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def split(self, raw_text: str) -> tuple[MarkdownSection, ...]:
        normalized = raw_text.strip()
        if not normalized:
            raise DomainInvariantError("uploaded markdown document is empty")

        lines = normalized.splitlines()
        heading_indexes: list[int] = []
        heading_levels: list[int] = []
        heading_titles: list[str] = []

        for index, line in enumerate(lines):
            match = self._heading_re.match(line)
            if match is None:
                continue
            heading_indexes.append(index)
            heading_levels.append(len(match.group(1)))
            heading_titles.append(match.group(2).strip())

        if not heading_indexes:
            return (
                MarkdownSection(
                    section_index=0,
                    section_key="section-0001",
                    heading_path=("Document",),
                    title="Document",
                    raw_text=normalized,
                    normalized_text=normalized,
                    parent_section_key=None,
                ),
            )

        sections: list[MarkdownSection] = []
        current_heading_stack: list[tuple[int, str, str]] = []

        for ordinal, start_index in enumerate(heading_indexes):
            end_index = (
                heading_indexes[ordinal + 1]
                if ordinal + 1 < len(heading_indexes)
                else len(lines)
            )
            level = heading_levels[ordinal]
            title = heading_titles[ordinal]
            section_key = self._section_key(ordinal + 1, title)
            section_text = "\n".join(lines[start_index:end_index]).strip()

            current_heading_stack = [
                item for item in current_heading_stack if item[0] < level
            ]
            parent_section_key = (
                current_heading_stack[-1][2] if current_heading_stack else None
            )
            current_heading_stack.append((level, title, section_key))

            heading_path = tuple(item[1] for item in current_heading_stack)

            sections.append(
                MarkdownSection(
                    section_index=ordinal,
                    section_key=section_key,
                    heading_path=heading_path,
                    title=title,
                    raw_text=section_text,
                    normalized_text=section_text,
                    parent_section_key=parent_section_key,
                )
            )

        return tuple(sections)

    def _section_key(self, ordinal: int, title: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", title).strip("-").lower()
        if not slug:
            slug = "section"
        return f"section-{ordinal:04d}-{slug[:48]}"


class FaqWorkbenchFreshUploadService:
    def __init__(
        self,
        repository: KnowledgeWorkbenchFreshUploadRepositoryPort,
        *,
        id_factory: IdFactory,
        time_provider: TimeProvider | None = None,
        sectioner: MarkdownSectioner | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._time_provider = time_provider or SystemTimeProvider()
        self._sectioner = sectioner or MarkdownSectioner()

    async def start_fresh_upload(
        self,
        command: FaqWorkbenchFreshUploadCommand,
    ) -> FaqWorkbenchFreshUploadResult:
        if not command.project_id:
            raise DomainInvariantError("project_id is required")
        if not command.file_name:
            raise DomainInvariantError("file_name is required")
        if command.source_type is not SourceType.MARKDOWN:
            raise DomainInvariantError(
                "FAQ Workbench v1 fresh upload supports markdown only"
            )
        if not command.raw_text.strip():
            raise DomainInvariantError("uploaded document text is empty")

        content_hash = command.content_hash or self._content_hash(command.raw_text)
        try:
            uploaded_by_actor_type = KnowledgeDocumentUploadActorType(
                command.uploaded_by_actor_type
            )
        except ValueError as exc:
            raise DomainInvariantError("unsupported upload actor type") from exc

        now = self._time_provider.now()

        document_id = self._id_factory.new_id("document")
        processing_run_id = self._id_factory.new_id("processing-run")
        registry_id = self._id_factory.new_id("registry")
        initialize_node_run_id = self._id_factory.new_id("node-run")
        initialize_artifact_id = self._id_factory.new_id("artifact")
        snapshot_id = self._id_factory.new_id("registry-snapshot")

        document = KnowledgeDocument(
            document_id=document_id,
            project_id=command.project_id,
            file_name=command.file_name,
            source_type=command.source_type,
            content_hash=content_hash,
            upload_id=command.upload_id,
            file_size_bytes=command.file_size_bytes,
            status=KnowledgeDocumentStatus.SECTIONED,
            current_processing_run_id=processing_run_id,
            uploaded_by_user_id=command.uploaded_by_user_id,
            uploaded_by_actor_type=uploaded_by_actor_type,
            uploaded_by_actor_id=command.uploaded_by_actor_id,
            trusted_upload=command.trusted_upload,
            created_at=now,
            updated_at=now,
        )

        markdown_sections = self._sectioner.split(command.raw_text)
        section_id_by_key: dict[str, str] = {
            section.section_key: self._id_factory.new_id("section")
            for section in markdown_sections
        }

        sections = tuple(
            DocumentSection(
                section_id=section_id_by_key[section.section_key],
                document_id=document_id,
                project_id=command.project_id,
                section_index=section.section_index,
                section_key=section.section_key,
                heading_path=section.heading_path,
                title=section.title,
                raw_text=section.raw_text,
                normalized_text=section.normalized_text,
                source_refs=(f"{document_id}#{section.section_key}",),
                source_chunk_indexes=(section.section_index,),
                status=DocumentSectionStatus.PENDING,
                parent_section_id=(
                    section_id_by_key[section.parent_section_key]
                    if section.parent_section_key is not None
                    else None
                ),
            )
            for section in markdown_sections
        )

        processing_run = KnowledgeProcessingRun(
            processing_run_id=processing_run_id,
            project_id=command.project_id,
            document_id=document_id,
            processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
            trigger=ProcessingTrigger.FRESH_UPLOAD,
            status=ProcessingRunStatus.RUNNING,
            resume_policy=ResumePolicy.FORBIDDEN,
            started_at=now,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            total_tokens=0,
            total_llm_calls=0,
        )

        registry = FactRegistry(
            registry_id=registry_id,
            project_id=command.project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
            status=FactRegistryStatus.BUILDING,
            version=1,
            created_at=now,
            updated_at=now,
        )

        initialize_node_run = ProcessingNodeRun(
            node_run_id=initialize_node_run_id,
            processing_run_id=processing_run_id,
            project_id=command.project_id,
            document_id=document_id,
            node_name=ProcessingNodeName.INITIALIZE_REGISTRY,
            node_kind=ProcessingNodeKind.PERSISTENCE,
            status=ProcessingNodeStatus.COMPLETED,
            started_at=now,
            completed_at=now,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )

        artifact_payload: JsonValue = {
            "registry_id": registry_id,
            "document_id": document_id,
            "processing_run_id": processing_run_id,
            "section_count": len(sections),
            "initial_canonical_facts": [],
        }

        initialize_artifact = ProcessingNodeArtifact(
            artifact_id=initialize_artifact_id,
            node_run_id=initialize_node_run_id,
            processing_run_id=processing_run_id,
            project_id=command.project_id,
            document_id=document_id,
            artifact_type=ProcessingNodeArtifactType.APPLIED_RESULT,
            payload_json=artifact_payload,
            schema_version=1,
            created_at=now,
        )

        initial_snapshot = RegistrySnapshot(
            snapshot_id=snapshot_id,
            registry_id=registry_id,
            processing_run_id=processing_run_id,
            project_id=command.project_id,
            document_id=document_id,
            after_node_run_id=initialize_node_run_id,
            sequence_number=1,
            entries_payload={"entries": []},
            relations_payload={"relations": []},
            entry_count=0,
            relation_count=0,
            claim_observation_count=0,
            update_count=0,
            created_at=now,
        )

        await self._repository.create_document(document)
        await self._repository.create_document_sections(sections)
        await self._repository.create_processing_run(processing_run)
        await self._repository.create_fact_registry(registry)
        await self._repository.create_processing_node_run(initialize_node_run)
        await self._repository.create_processing_node_artifact(initialize_artifact)
        await self._repository.create_registry_snapshot(initial_snapshot)

        return FaqWorkbenchFreshUploadResult(
            document=document,
            sections=sections,
            processing_run=processing_run,
            registry=registry,
            initialize_node_run=initialize_node_run,
            initialize_artifact=initialize_artifact,
            initial_snapshot=initial_snapshot,
        )

    def _content_hash(self, raw_text: str) -> str:
        return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
