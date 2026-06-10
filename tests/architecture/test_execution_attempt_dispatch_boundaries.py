from pathlib import Path


def test_execution_attempt_dispatch_required_markers_exist() -> None:
    files = (
        Path(
            "src/contexts/execution_runtime/application/ports/"
            "work_item_attempt_dispatch_repository_port.py",
        ),
        Path(
            "src/contexts/execution_runtime/infrastructure/postgres/"
            "postgres_work_item_attempt_dispatch_repository.py",
        ),
        Path("src/interfaces/composition/start_llm_admitted_work_item_attempts.py"),
        Path("src/interfaces/composition/lease_llm_admitted_work_items.py"),
        Path(
            "src/contexts/llm_runtime/domain/capacity/llm_model_route_catalog.py",
        ),
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)

    required = (
        "WorkItemAttemptDispatchRepositoryPort",
        "WorkItemAttemptDispatchRecord",
        "PostgresWorkItemAttemptDispatchRepository",
        "execution_work_item_attempt_dispatches",
        "StartLlmAdmittedWorkItemAttempts",
        "StartedLlmAdmittedAttempt",
        "LlmModelExecutionSettings",
        "LlmModelRouteCatalog",
        "execution_settings_for_model_ref",
        "llm_execution_settings",
        "reasoning_enabled",
    )
    for marker in required:
        assert marker in source


def test_migration_creates_execution_attempt_dispatches_table() -> None:
    migration_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(Path("migrations").glob("*.sql"))
    )

    required = (
        "execution_work_item_attempt_dispatches",
        "lease_token text NOT NULL",
        "worker_ref text NOT NULL",
        "schedule_payload jsonb NOT NULL",
        "llm_allocation_payload jsonb NOT NULL",
        "dispatch_payload jsonb NOT NULL",
        "uq_execution_attempt_dispatches_work_item_attempt",
    )
    for marker in required:
        assert marker in migration_sources


def test_execution_infra_repository_remains_generic() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_dispatch_repository.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "llm_runtime",
        "Groq",
        "qwen",
        "provider",
        "account_ref",
        "model_ref",
        "Prompt",
        "source_unit",
        "artifact_runtime",
        "capacity_runtime",
        "ON CONFLICT",
        "DO NOTHING",
        "commit(",
        "rollback(",
    )
    for marker in forbidden:
        assert marker not in source


def test_composition_does_not_call_provider_or_read_env() -> None:
    source = Path(
        "src/interfaces/composition/start_llm_admitted_work_item_attempts.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "requests.",
        "os.environ",
        "GROQ_API_KEY",
        "Authorization",
        "api_key",
        "client.",
        "AsyncGroq",
        "groq_model_router",
    )
    for marker in forbidden:
        assert marker not in source


def test_llm_execution_settings_remain_generic_dispatch_payload_metadata() -> None:
    repository_source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_dispatch_repository.py",
    ).read_text(encoding="utf-8")
    lease_source = Path(
        "src/interfaces/composition/lease_llm_admitted_work_items.py",
    ).read_text(encoding="utf-8")
    start_source = Path(
        "src/interfaces/composition/start_llm_admitted_work_item_attempts.py",
    ).read_text(encoding="utf-8")

    assert "llm_runtime" not in repository_source
    assert "llm_execution_settings" not in repository_source
    assert (
        '"llm_execution_settings": self.execution_settings.to_provider_options()'
        in (lease_source)
    )
    assert "dispatch_payload=dispatch_payload" in start_source
