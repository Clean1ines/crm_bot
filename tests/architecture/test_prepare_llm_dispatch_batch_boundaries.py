from pathlib import Path


COMPOSITION_PATH = Path("src/interfaces/composition/prepare_llm_dispatch_batch.py")


def test_prepare_llm_dispatch_batch_required_markers_exist() -> None:
    source = COMPOSITION_PATH.read_text(encoding="utf-8")

    required = (
        "PrepareLlmDispatchBatch",
        "PrepareLlmDispatchBatchCommand",
        "PrepareLlmDispatchBatchResult",
        "LeaseLlmAdmittedWorkItems",
        "StartLlmAdmittedWorkItemAttempts",
        "PostgresWorkItemLeaseRepository",
        "PostgresWorkItemAttemptDispatchRepository",
        "transaction()",
    )
    for marker in required:
        assert marker in source


def test_prepare_llm_dispatch_batch_does_not_call_provider_or_read_env() -> None:
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
        "Prompt",
        "artifact_runtime",
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
