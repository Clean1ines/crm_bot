from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANAGEMENT_CONTEXT = (
    ROOT / "src" / "contexts" / "knowledge_workbench" / "source_management"
)
SOURCE_MANAGEMENT_DOMAIN = SOURCE_MANAGEMENT_CONTEXT / "domain"
SOURCE_MANAGEMENT_USE_CASES = SOURCE_MANAGEMENT_CONTEXT / "application" / "use_cases"

FORBIDDEN_MARKERS: tuple[str, ...] = (
    "llm_runtime",
    "execution_runtime",
    "artifact_runtime",
    "Groq",
    "groq",
    "Qwen",
    "qwen",
    "PromptA",
    "Prompt A",
    "PromptC",
    "Prompt C",
    "ClaimObservation",
    "claim_observation",
    "Surface",
    "surface",
    "PipelineArtifact",
    "WorkItem",
    "LlmTask",
)


def test_source_management_domain_does_not_import_or_name_cross_context_concepts() -> (
    None
):
    offenders: list[str] = []

    for path in SOURCE_MANAGEMENT_DOMAIN.rglob("*.py"):
        if path.name == "__init__.py":
            continue

        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for marker in FORBIDDEN_MARKERS:
                if marker in line:
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{line_number} contains forbidden marker {marker!r}"
                    )

    assert not offenders, (
        "Source Management domain must stay clean. It must not import or encode "
        "LLM Runtime, Execution Runtime, Artifact Runtime, provider, prompt, claim, "
        "surface, work item, or LLM task semantics:\n" + "\n".join(offenders)
    )


def test_source_management_context_does_not_own_claim_extraction_work_item_creation() -> (
    None
):
    forbidden_markers = (
        "src.contexts.execution_runtime",
        "WorkItem",
        "WorkKind",
        "claim_extraction",
        "CLAIM_EXTRACTION_WORK_KIND",
        "CreateExtractionWorkItems",
    )

    offenders: list[str] = []

    for path in SOURCE_MANAGEMENT_CONTEXT.rglob("*.py"):
        if path.name == "__init__.py":
            continue

        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for marker in forbidden_markers:
                if marker in line:
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{line_number} contains forbidden marker {marker!r}"
                    )

    assert not offenders, (
        "Source Management must not own Execution Runtime WorkItem creation or "
        "claim extraction orchestration. Source Management owns SourceDocument, "
        "SourceUnit, source parsing/splitting/lineage and source format adapters. "
        "Claim extraction WorkItem creation belongs to knowledge_workbench/extraction:\n"
        + "\n".join(offenders)
    )


def test_source_management_use_cases_do_not_take_prompt_id() -> None:
    offenders: list[str] = []

    if not SOURCE_MANAGEMENT_USE_CASES.exists():
        return

    for path in SOURCE_MANAGEMENT_USE_CASES.rglob("*.py"):
        if path.name == "__init__.py":
            continue

        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "prompt_id" in line:
                offenders.append(
                    f"{path.relative_to(ROOT)}:{line_number} contains forbidden marker 'prompt_id'"
                )

    assert not offenders, (
        "Source Management use cases must not own prompt_id-based extraction "
        "orchestration. Existing PromptFitPolicy is intentionally out of scope for "
        "this migration patch; this guard prevents prompt_id from reappearing in "
        "source_management/application/use_cases:\n" + "\n".join(offenders)
    )
