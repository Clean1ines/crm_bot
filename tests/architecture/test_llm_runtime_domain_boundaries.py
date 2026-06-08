from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LLM_RUNTIME_DOMAIN = ROOT / "src" / "contexts" / "llm_runtime" / "domain"

FORBIDDEN_CROSS_CONTEXT_PATTERNS = [
    r"\bPromptA\b",
    r"\bPrompt A\b",
    r"\bPromptC\b",
    r"\bPrompt C\b",
    r"\bGroq\b",
    r"\bQwen\b",
    r"\bFAQ\b",
    r"\bfaq_",
    r"\bRegistryMerge\b",
    r"\bregistry_merge\b",
    r"\bQuestionRegistry\b",
    r"\bSectionBatchQueueItem\b",
    r"\bsection_batch\b",
    r"\bclaim_observations_persisted\b",
    r"\bCLAIM_OBSERVATIONS_PERSISTED\b",
    r"\bregistry_application_queued\b",
    r"\bREGISTRY_APPLICATION_QUEUED\b",
    r"\bregistry_application_applied\b",
    r"\bREGISTRY_APPLICATION_APPLIED\b",
    r"\bwaiting_for_fresh_registry\b",
    r"\bWAITING_FOR_FRESH_REGISTRY\b",
    r"\bknowledge_workbench\b",
    r"\bKnowledge Workbench\b",
    r"\bTelegram\b",
    r"\btelegram\b",
    r"\bsource_unit\b",
    r"\bSourceUnit\b",
    r"\bclaim\b",
    r"\bClaim\b",
    r"\bsurface\b",
    r"\bSurface\b",
    r"\bWorkItem\b",
    r"\bwork_item\b",
    r"\bLease\b",
    r"\blease\b",
    r"\bPipelineArtifact\b",
    r"\bpipeline_artifact\b",
    r"\bartifact\b",
    r"\bArtifact\b",
]


def test_llm_runtime_domain_does_not_encode_cross_context_semantics() -> None:
    offenders: list[str] = []
    compiled_patterns = [
        re.compile(pattern) for pattern in FORBIDDEN_CROSS_CONTEXT_PATTERNS
    ]

    for path in LLM_RUNTIME_DOMAIN.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in compiled_patterns:
            if pattern.search(text):
                offenders.append(
                    f"{path.relative_to(ROOT)} matches forbidden pattern {pattern.pattern!r}"
                )

    assert not offenders, (
        "LLM Runtime domain must stay provider-neutral and business-agnostic. "
        "It must not encode Workbench, execution, artifact, source, transport, or "
        "business semantics:\n" + "\n".join(offenders)
    )
