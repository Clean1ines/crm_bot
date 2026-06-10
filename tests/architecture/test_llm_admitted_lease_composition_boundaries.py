from pathlib import Path


COMPOSITION_PATH = Path("src/interfaces/composition/lease_llm_admitted_work_items.py")


def test_composition_required_markers_exist() -> None:
    source = COMPOSITION_PATH.read_text(encoding="utf-8")

    required = (
        "LeaseLlmAdmittedWorkItems",
        "SelectActiveLlmModelCapacity",
        "LeaseAdmittedWorkItems",
        "LlmCapacityAllocationSlot",
        "LlmAdmittedLeasedWorkItem",
        "to_dispatch_payload",
        "CapacityWorkClass.LLM_BOUND",
    )
    for marker in required:
        assert marker in source


def test_composition_does_not_call_provider_or_read_env() -> None:
    source = COMPOSITION_PATH.read_text(encoding="utf-8")

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
    )
    for marker in forbidden:
        assert marker not in source


def test_execution_runtime_still_does_not_import_llm_runtime() -> None:
    root = Path("src/contexts/execution_runtime")
    offenders: list[str] = []

    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "llm_runtime" in source:
            offenders.append(str(path))

    assert offenders == []


def test_capacity_runtime_still_does_not_import_llm_runtime() -> None:
    root = Path("src/contexts/capacity_runtime")
    offenders: list[str] = []

    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "llm_runtime" in source:
            offenders.append(str(path))

    assert offenders == []


def test_llm_runtime_domain_still_does_not_import_capacity_runtime() -> None:
    root = Path("src/contexts/llm_runtime/domain")
    offenders: list[str] = []

    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "capacity_runtime" in source:
            offenders.append(str(path))

    assert offenders == []


def test_lease_composition_uses_active_model_selector() -> None:
    source = Path(
        "src/interfaces/composition/lease_llm_admitted_work_items.py"
    ).read_text(
        encoding="utf-8",
    )

    required = (
        "SelectActiveLlmModelCapacity",
        "SelectActiveLlmModelCapacityCommand",
        "active_model_ref",
        "account_capacities",
        "active_model_capacity_selection",
    )
    for marker in required:
        assert marker in source


def test_lease_composition_does_not_call_projector_directly() -> None:
    source = Path(
        "src/interfaces/composition/lease_llm_admitted_work_items.py"
    ).read_text(
        encoding="utf-8",
    )

    forbidden = (
        "LlmCapacityProjectionCommand(",
        "ProjectLlmCapacityToCapacityRuntime",
        "llm_capacity_projector",
    )
    for marker in forbidden:
        assert marker not in source
