from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANAGEMENT_DOMAIN = (
    ROOT / "src" / "contexts" / "knowledge_workbench" / "source_management" / "domain"
)

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
