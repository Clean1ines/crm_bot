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
    offenders: list[str] = []

    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "capacity_runtime" in source and path != allowed:
            offenders.append(str(path))

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

    for path in sorted(root.rglob("*.py")):
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
