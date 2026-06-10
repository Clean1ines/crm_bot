from pathlib import Path


def test_document_segmentation_subdomain_has_no_runtime_infra_or_provider_coupling() -> (
    None
):
    root = Path("src/contexts/knowledge_workbench/document_segmentation")
    assert root.is_dir()

    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py"))
    )

    # SegmentationPromptProfile is intentional domain vocabulary, not a prompt-file
    # dependency. The forbidden check below should catch external prompt/runtime
    # coupling without rejecting that required value object name.
    source_without_domain_prompt_vocabulary = source.replace(
        "SegmentationPromptProfile",
        "",
    )

    forbidden_markers = [
        "src.contexts.llm_runtime",
        "src.contexts.execution_runtime",
        "src.contexts.capacity_runtime",
        "src.contexts.artifact_runtime",
        "src.interfaces",
        "src.infrastructure",
        "asyncpg",
        "postgres",
        "fastapi",
        "qwen",
        "Qwen",
        "Groq",
        "context_window_tokens",
        "ModelProfile",
        "RateLimitProfile",
        "Prompt",
        "PROMPT_A",
        "DraftObservationExtraction",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
        "queue",
        "openpyxl",
        "pandas",
        "BeautifulSoup",
    ]

    offenders = [
        marker
        for marker in forbidden_markers
        if marker in source_without_domain_prompt_vocabulary
    ]

    assert not offenders, "\n".join(offenders)
