from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.application.services.faq_workbench_document_processing_orchestrator import (
    FaqWorkbenchDocumentProcessingOrchestrator,
    ProcessMarkdownDocumentCommand,
)
from src.application.services.faq_workbench_fresh_upload_service import (
    MonotonicIdFactory,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    KnowledgeDocument,
    KnowledgeProcessingRun,
    KnowledgeSurface,
    ProcessingNodeArtifact,
    ProcessingNodeRun,
    QuestionRegistry,
    QuestionRegistryEntry,
    RegistrySnapshot,
    RegistryUpdateApplication,
    SectionFinding,
    SurfaceMaterializationResult,
)
from src.infrastructure.llm.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsGenerator,
    FaqWorkbenchClaimObservationsGeneratorConfig,
)
from src.infrastructure.llm.groq_llm_json_invocation import (
    GroqLlmJsonInvocationAdapter,
)


@dataclass(frozen=True, slots=True)
class FakeUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class FakeMessage:
    content: str | None


@dataclass(frozen=True, slots=True)
class FakeChoice:
    message: FakeMessage


@dataclass(frozen=True, slots=True)
class FakeResponse:
    choices: tuple[FakeChoice, ...]
    usage: FakeUsage | None
    model: str | None


@dataclass(slots=True)
class FakeGroqCompletions:
    prompts: list[str] = field(default_factory=list)

    async def create(self, **kwargs: object) -> FakeResponse:
        messages = kwargs.get("messages")
        if not isinstance(messages, list):
            raise AssertionError("messages must be a list")

        user_prompt = self._user_prompt(messages)
        self.prompts.append(user_prompt)

        if "section-0001-product" in user_prompt:
            content = self._product_payload()
        elif "section-0002-curation" in user_prompt:
            content = self._curation_payload()
        else:
            content = '{"findings": [], "warnings": [], "metrics": {}}'

        return FakeResponse(
            choices=(FakeChoice(message=FakeMessage(content=content)),),
            usage=FakeUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="llama-3.1-8b-instant",
        )

    def _user_prompt(self, messages: list[object]) -> str:
        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                return content
        raise AssertionError("user prompt not found")

    def _product_payload(self) -> str:
        return """
{
  "findings": [
    {
      "action": "new",
      "target_registry_entry_id": "",
      "target_surface_key": "",
      "local_surface_key": "product_definition",
      "title": "Описание продукта",
      "canonical_question": "Что такое продукт?",
      "surface_kind": "definition",
      "answer": "Система превращает документы бизнеса в управляемую AI-базу знаний.",
      "short_answer": "Управляемая AI-база знаний для бизнеса.",
      "answer_delta": "",
      "answer_scope": "Описание продукта",
      "question_scope": "Вопросы о продукте",
      "exclusion_scope": "Цены и интеграции",
      "variants": ["что делает продукт", "зачем нужна платформа"],
      "evidence_quotes": ["Система превращает документы бизнеса в управляемую AI-базу знаний."],
      "source_refs": ["document#product"],
      "source_chunk_indexes": [0],
      "confidence": 0.9,
      "reason": "section defines product"
    }
  ],
  "warnings": [],
  "metrics": {"finding_count": 1}
}
""".strip()

    def _curation_payload(self) -> str:
        return """
{
  "findings": [
    {
      "action": "extends_existing",
      "target_registry_entry_id": "",
      "target_surface_key": "product_definition",
      "local_surface_key": "product_curation_extension",
      "title": "Курация знаний",
      "canonical_question": "Что такое продукт?",
      "surface_kind": "definition",
      "answer": "Платформа позволяет проверять и курировать знания до публикации.",
      "short_answer": "Платформа позволяет проверять знания до публикации.",
      "answer_delta": "Платформа позволяет проверять и курировать знания до публикации.",
      "answer_scope": "Описание продукта и курации",
      "question_scope": "Вопросы о продукте и проверке знаний",
      "exclusion_scope": "Цены",
      "variants": ["как проверяются знания"],
      "evidence_quotes": ["проверять и курировать знания до публикации"],
      "source_refs": ["document#curation"],
      "source_chunk_indexes": [1],
      "confidence": 0.8,
      "reason": "section extends product definition"
    }
  ],
  "warnings": [],
  "metrics": {"finding_count": 1}
}
""".strip()


@dataclass(slots=True)
class FakeGroqChat:
    completions: FakeGroqCompletions


@dataclass(slots=True)
class FakeGroqClient:
    chat: FakeGroqChat
    route_events: list[dict[str, object]] = field(default_factory=list)

    def route_observability_snapshot(self) -> dict[str, object]:
        if self.route_events:
            return {"groq_route_events": self.route_events}
        return {
            "groq_route_events": [
                {
                    "status": "success",
                    "routed_model": "llama-3.1-8b-instant",
                    "key_slot_label": "1/3",
                    "limit_kind": "",
                }
            ]
        }


@dataclass(slots=True)
class InMemoryWorkbenchProcessingRepository:
    documents: list[KnowledgeDocument] = field(default_factory=list)
    sections: list[DocumentSection] = field(default_factory=list)
    runs: list[KnowledgeProcessingRun] = field(default_factory=list)
    registries: list[QuestionRegistry] = field(default_factory=list)
    node_runs: list[ProcessingNodeRun] = field(default_factory=list)
    artifacts: list[ProcessingNodeArtifact] = field(default_factory=list)
    snapshots: list[RegistrySnapshot] = field(default_factory=list)
    findings: list[SectionFinding] = field(default_factory=list)
    entries: list[QuestionRegistryEntry] = field(default_factory=list)
    applications: list[RegistryUpdateApplication] = field(default_factory=list)
    surfaces: list[KnowledgeSurface] = field(default_factory=list)
    materialization_results: list[SurfaceMaterializationResult] = field(
        default_factory=list
    )

    async def create_document(self, document: KnowledgeDocument) -> None:
        self.documents.append(document)

    async def create_document_sections(
        self,
        sections: tuple[DocumentSection, ...],
    ) -> None:
        self.sections.extend(sections)

    async def create_processing_run(self, run: KnowledgeProcessingRun) -> None:
        self.runs.append(run)

    async def create_question_registry(self, registry: QuestionRegistry) -> None:
        self.registries.append(registry)

    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None:
        self.node_runs.append(node_run)

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None:
        self.artifacts.append(artifact)

    async def create_registry_snapshot(self, snapshot: RegistrySnapshot) -> None:
        self.snapshots.append(snapshot)

    async def create_claim_observations(
        self,
        findings: tuple[SectionFinding, ...],
    ) -> None:
        self.findings.extend(findings)

    async def upsert_question_registry_entries(
        self,
        entries: tuple[QuestionRegistryEntry, ...],
    ) -> None:
        self.entries = list(entries)

    async def create_registry_update_applications(
        self,
        applications: tuple[RegistryUpdateApplication, ...],
    ) -> None:
        self.applications.extend(applications)

    async def create_knowledge_surfaces(
        self,
        surfaces: tuple[KnowledgeSurface, ...],
    ) -> None:
        self.surfaces.extend(surfaces)

    async def create_surface_materialization_result(
        self,
        result: SurfaceMaterializationResult,
    ) -> None:
        self.materialization_results.append(result)


@pytest.mark.asyncio
async def test_workbench_orchestrator_uses_generator_groq_adapter_and_builds_surfaces() -> (
    None
):
    repository = InMemoryWorkbenchProcessingRepository()
    fake_completions = FakeGroqCompletions()
    llm_invocation = GroqLlmJsonInvocationAdapter(
        client=FakeGroqClient(chat=FakeGroqChat(completions=fake_completions))
    )
    generator = FaqWorkbenchClaimObservationsGenerator(
        llm_invocation=llm_invocation,
        config=FaqWorkbenchClaimObservationsGeneratorConfig(
            prompt_path=Path("src/agent/prompts/faq_surface_claim_observations.ru.txt")
        ),
    )
    orchestrator = FaqWorkbenchDocumentProcessingOrchestrator(
        repository,
        id_factory=MonotonicIdFactory.create(),
        claim_observations_generator=generator,
    )

    result = await orchestrator.process_markdown_document(
        ProcessMarkdownDocumentCommand(
            project_id="project-1",
            file_name="knowledge.md",
            upload_id="upload-1",
            raw_text=(
                "# Product\n"
                "Система превращает документы бизнеса в управляемую AI-базу знаний.\n\n"
                "## Curation\n"
                "Платформа позволяет проверять и курировать знания до публикации.\n"
            ),
        )
    )

    assert len(fake_completions.prompts) == 2
    assert "section-0001-product" in fake_completions.prompts[0]
    assert "INPUT_REGISTRY_SNAPSHOT_JSON:" in fake_completions.prompts[0]

    assert "section-0002-curation" in fake_completions.prompts[1]
    assert "product_definition" in fake_completions.prompts[1]

    assert len(result.processed_sections) == 2
    assert len(result.registry_entries) == 1
    assert result.registry_entries[0].registry_entry_key == "product_definition"
    assert "курировать знания" in result.registry_entries[0].answer

    assert len(result.surfaces) == 1
    assert (
        result.surfaces[0].registry_entry_id
        == result.registry_entries[0].registry_entry_id
    )
    assert result.surfaces[0].canonical_question == "Что такое продукт?"

    assert len(repository.findings) == 2
    assert len(repository.applications) == 2
    assert len(repository.surfaces) == 1
