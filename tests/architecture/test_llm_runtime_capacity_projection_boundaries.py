from pathlib import Path


def test_llm_runtime_domain_capacity_does_not_import_capacity_runtime() -> None:
    root = Path("src/contexts/llm_runtime/domain")
    offenders: list[str] = []

    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "capacity_runtime" in source:
            offenders.append(str(path))

    assert offenders == []


def test_llm_runtime_capacity_projection_is_only_capacity_runtime_import_boundary() -> (
    None
):
    root = Path("src/contexts/llm_runtime")
    allowed = Path(
        "src/contexts/llm_runtime/application/capacity/"
        "project_llm_capacity_to_capacity_runtime.py",
    )
    import_markers = (
        "from src.contexts.capacity_runtime",
        "import src.contexts.capacity_runtime",
    )
    offenders: list[str] = []

    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if path == allowed:
            continue
        for marker in import_markers:
            if marker in source:
                offenders.append(f"{path}: {marker}")

    assert offenders == []


def test_capacity_runtime_does_not_import_llm_runtime_or_provider_terms() -> None:
    root = Path("src/contexts/capacity_runtime")
    forbidden = (
        "llm_runtime",
        "Groq",
        "qwen",
        "model_ref",
        "account_ref",
        "provider",
    )
    offenders: list[str] = []

    allowed_feedback_contract = Path(
        "src/contexts/capacity_runtime/application/ports/"
        "llm_attempt_capacity_observation_repository_port.py"
    )

    for path in sorted(root.rglob("*.py")):
        if path == allowed_feedback_contract:
            continue
        source = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in source:
                offenders.append(f"{path}: {marker}")

    assert offenders == []


def test_execution_runtime_bulk_leasing_does_not_import_llm_runtime_or_provider_terms() -> (
    None
):
    source = Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "lease_admitted_work_items.py",
    ).read_text(encoding="utf-8")
    forbidden = (
        "llm_runtime",
        "Groq",
        "qwen",
        "provider",
        "model",
        "account",
    )

    for marker in forbidden:
        assert marker not in source


def test_projection_does_not_call_groq_or_read_env() -> None:
    source = "\n".join(
        (
            Path(
                "src/contexts/llm_runtime/domain/capacity/"
                "llm_provider_account_capacity.py",
            ).read_text(encoding="utf-8"),
            Path(
                "src/contexts/llm_runtime/application/capacity/"
                "project_llm_capacity_to_capacity_runtime.py",
            ).read_text(encoding="utf-8"),
        )
    )
    forbidden = (
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "requests.",
        "os.environ",
        "GROQ_API_KEY",
        "api_key",
        "Authorization",
        "client.",
    )

    for marker in forbidden:
        assert marker not in source


def test_projection_source_exposes_allocation_slots() -> None:
    source = Path(
        "src/contexts/llm_runtime/application/capacity/"
        "project_llm_capacity_to_capacity_runtime.py",
    ).read_text(encoding="utf-8")

    required = (
        "LlmCapacityAllocationSlot",
        "allocations",
        "slot_index",
        "to_payload",
    )
    for marker in required:
        assert marker in source


def test_active_model_capacity_projection_required_markers_exist() -> None:
    source = "\n".join(
        (
            Path(
                "src/contexts/llm_runtime/domain/capacity/llm_model_route_catalog.py",
            ).read_text(encoding="utf-8"),
            Path(
                "src/contexts/llm_runtime/application/capacity/"
                "select_active_llm_model_capacity.py",
            ).read_text(encoding="utf-8"),
            Path(
                "src/contexts/llm_runtime/application/capacity/"
                "project_llm_capacity_to_capacity_runtime.py",
            ).read_text(encoding="utf-8"),
        ),
    )

    required = (
        "LlmModelRouteCatalog",
        "LlmModelRouteRole",
        "SelectActiveLlmModelCapacity",
        "active_model_ref",
        "capacity projection accounts must use one active model_ref",
    )
    for marker in required:
        assert marker in source


def test_llm_capacity_projection_does_not_import_legacy_groq_router_or_clients() -> (
    None
):
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            Path(
                "src/contexts/llm_runtime/domain/capacity/llm_model_route_catalog.py",
            ),
            Path(
                "src/contexts/llm_runtime/application/capacity/"
                "select_active_llm_model_capacity.py",
            ),
            Path(
                "src/contexts/llm_runtime/application/capacity/"
                "project_llm_capacity_to_capacity_runtime.py",
            ),
        )
    )

    forbidden = (
        "src.infrastructure.llm.groq_model_router",
        "AsyncGroq",
        "configured_groq_api_keys",
        "os.environ",
        "GROQ_API_KEY",
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "requests.",
    )
    for marker in forbidden:
        assert marker not in source


def test_llm_model_route_catalog_exposes_execution_settings() -> None:
    catalog_source = Path(
        "src/contexts/llm_runtime/domain/capacity/llm_model_route_catalog.py",
    ).read_text(encoding="utf-8")
    test_source = Path(
        "tests/contexts/llm_runtime/domain/capacity/test_llm_model_route_catalog.py",
    ).read_text(encoding="utf-8")

    required_catalog_markers = (
        "LlmModelExecutionSettings",
        "reasoning_enabled",
        "reasoning_effort",
        "execution_settings",
        "execution_settings_for_model_ref",
        "qwen/qwen3-32b",
    )
    for marker in required_catalog_markers:
        assert marker in catalog_source

    assert "test_qwen_primary_route_disables_reasoning" in test_source


def test_llm_model_route_catalog_does_not_touch_provider_client_or_env() -> None:
    source = Path(
        "src/contexts/llm_runtime/domain/capacity/llm_model_route_catalog.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "os.environ",
        "GROQ_API_KEY",
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "requests.",
        "AsyncGroq",
        "Authorization",
        "api_key",
        "src.infrastructure.llm.groq_model_router",
    )
    for marker in forbidden:
        assert marker not in source
