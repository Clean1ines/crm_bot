from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTEXTS_ROOT = ROOT / "src" / "contexts"
CONTRACT = ROOT / "docs" / "architecture" / "pattern_based_architecture_contract.md"

REQUIRED_CONTEXTS = {
    "execution_runtime",
    "llm_runtime",
    "artifact_runtime",
    "knowledge_workbench",
    "conversation_runtime",
}

REQUIRED_LAYERS = {
    "domain",
    "application",
    "infrastructure",
    "interfaces",
}

FORBIDDEN_GENERIC_FILENAMES = {
    "service.py",
    "services.py",
    "repository.py",
    "repositories.py",
    "dto.py",
    "dtos.py",
}

REQUIRED_CANONICAL_DISTINCTIONS = [
    "WorkItem != LlmTask != PipelineArtifact",
    "SourceUnit != DraftSurface != KnowledgeSurface",
    "PromptA != KnowledgeExtraction",
    "Groq != LlmRuntime",
    "Repository != UseCase",
    "Service != StateMachine",
]

REQUIRED_LEGACY_WARNINGS = [
    "SectionBatchQueueItem",
    "legacy hybrid, not canonical WorkItem",
    "CLAIM_OBSERVATIONS_PERSISTED",
    "legacy status/checkpoint hybrid",
    "REGISTRY_APPLICATION_QUEUED",
    "legacy status/downstream queue marker hybrid",
    "REGISTRY_APPLICATION_APPLIED",
]


def test_bounded_context_skeleton_exists() -> None:
    assert CONTEXTS_ROOT.exists(), "src/contexts must exist"
    assert (CONTEXTS_ROOT / "__init__.py").exists(), (
        "src/contexts must be a Python package"
    )

    for context in sorted(REQUIRED_CONTEXTS):
        context_dir = CONTEXTS_ROOT / context
        assert context_dir.exists(), f"missing bounded context: {context_dir}"
        assert (context_dir / "__init__.py").exists(), (
            f"missing __init__.py for {context}"
        )
        assert (context_dir / "README.md").exists(), f"missing README.md for {context}"

        for layer in sorted(REQUIRED_LAYERS):
            layer_dir = context_dir / layer
            assert layer_dir.exists(), f"missing layer {layer} in {context}"
            assert (layer_dir / "__init__.py").exists(), (
                f"missing __init__.py in {context}/{layer}"
            )


def test_context_roots_do_not_recreate_generic_dumping_grounds() -> None:
    assert CONTEXTS_ROOT.exists()

    offenders: list[str] = []

    for path in CONTEXTS_ROOT.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        if path.name in FORBIDDEN_GENERIC_FILENAMES:
            offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, (
        "Do not recreate generic services/repositories/DTO dumping grounds under src/contexts. "
        "Use explicit DDD/pattern names instead:\n" + "\n".join(offenders)
    )


def test_new_context_skeleton_does_not_import_old_workbench_paths() -> None:
    forbidden_import_markers = [
        "src.domain.project_plane.knowledge_workbench",
        "domain.project_plane.knowledge_workbench",
        "src.application.services.faq_workbench",
        "application.services.faq_workbench",
        "src.infrastructure.queue.handlers.workbench_parallel_processing",
        "infrastructure.queue.handlers.workbench_parallel_processing",
    ]

    offenders: list[str] = []

    for path in CONTEXTS_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_import_markers:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} imports/mentions {marker}")

    assert not offenders, (
        "New canonical contexts must not import old Workbench paths at skeleton stage:\n"
        + "\n".join(offenders)
    )
