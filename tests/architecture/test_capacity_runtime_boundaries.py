from pathlib import Path


def test_capacity_runtime_required_files_exist() -> None:
    required_files = [
        Path("src/contexts/capacity_runtime/__init__.py"),
        Path("src/contexts/capacity_runtime/domain/__init__.py"),
        Path("src/contexts/capacity_runtime/domain/capacity_decision.py"),
        Path("src/contexts/capacity_runtime/domain/capacity_policy.py"),
    ]

    for path in required_files:
        assert path.is_file(), f"missing required file: {path}"


def test_capacity_runtime_has_no_cross_context_or_infrastructure_markers() -> None:
    root = Path("src/contexts/capacity_runtime")
    assert root.is_dir()

    forbidden_markers = [
        "src.contexts.llm_runtime",
        "src.contexts.execution_runtime",
        "src.contexts.knowledge_workbench",
        "src.infrastructure",
        "asyncpg",
        "postgres",
        "Postgres",
        "Groq",
        "Qwen",
        "ProviderAccount",
        "ModelProfile",
        "WorkItem",
        "SourceUnit",
        "SourceDocument",
        "Prompt",
        "PROMPT_A",
        "DraftObservationExtraction",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
        "psutil",
    ]

    scanned_files = tuple(sorted(root.rglob("*.py")))
    assert scanned_files

    for path in scanned_files:
        source = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in source, f"{marker!r} leaked into {path}"
