from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROCESS_MANAGERS = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "process_managers"
)

FORBIDDEN_IMPORT_MARKERS = (
    "src.infrastructure.db",
    "src.infrastructure.llm",
    "src.infrastructure.queue",
    "src.application.services",
    "src.contexts.llm_runtime.infrastructure",
    "src.contexts.execution_runtime.infrastructure",
    "src.contexts.artifact_runtime.infrastructure",
    "src.contexts.llm_runtime.infrastructure.providers.groq",
)

FORBIDDEN_BEHAVIOR_MARKERS = (
    "Groq",
    "groq",
    "httpx",
    "asyncpg",
    "psycopg",
    "connection.execute(",
    "conn.execute(",
    "pool.execute(",
    "session.execute(",
    "await execute(",
    "fetch(",
    "fetchrow(",
    "fetchval(",
    "transaction(",
    ".transaction(",
    "SectionBatchQueueItem",
    "CLAIM_OBSERVATIONS_PERSISTED",
    "REGISTRY_APPLICATION_QUEUED",
    "REGISTRY_APPLICATION_APPLIED",
    "WAITING_FOR_FRESH_REGISTRY",
)


def test_claim_extraction_process_managers_do_not_import_infrastructure_or_legacy_paths() -> (
    None
):
    offenders: list[str] = []

    for path in PROCESS_MANAGERS.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_IMPORT_MARKERS:
            if marker in text:
                offenders.append(
                    f"{path.relative_to(ROOT)} imports forbidden path {marker!r}",
                )

    assert not offenders, (
        "Claim extraction process managers must depend on application/domain ports, "
        "not infrastructure, old services, old queue handlers, or provider adapters:\n"
        + "\n".join(offenders)
    )


def test_claim_extraction_process_managers_do_not_encode_provider_db_or_legacy_queue_semantics() -> (
    None
):
    offenders: list[str] = []

    for path in PROCESS_MANAGERS.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_BEHAVIOR_MARKERS:
            if marker in text:
                offenders.append(
                    f"{path.relative_to(ROOT)} contains forbidden marker {marker!r}",
                )

    assert not offenders, (
        "Claim extraction process managers must not encode provider, DB, or legacy "
        "queue/status semantics:\n" + "\n".join(offenders)
    )


def test_claim_extraction_process_managers_do_not_import_forbidden_architecture_layers_or_legacy_symbols() -> (
    None
):
    forbidden_markers = (
        "src.infrastructure.",
        "src.application.",
        "src.domain.project_plane.",
        "src.interfaces.",
        "src.contexts.llm_runtime.infrastructure.",
        "src.contexts.execution_runtime.infrastructure.",
        "src.contexts.artifact_runtime.infrastructure.",
        "src.contexts.llm_runtime.infrastructure.providers",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "provider_adapter",
        "queue.handlers",
        "workbench_parallel_processing",
        "SectionBatchQueueItem",
        "ProcessingNodeRun",
        "ProcessingNodeArtifact",
        "CLAIM_OBSERVATIONS_PERSISTED",
        "REGISTRY_APPLICATION_QUEUED",
        "REGISTRY_APPLICATION_APPLIED",
    )

    offenders: list[str] = []

    for path in PROCESS_MANAGERS.rglob("*.py"):
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
        "Claim extraction process managers must be application transaction "
        "scripts over ports/domain objects only. They must not import "
        "infrastructure, legacy layer-first code, provider adapters, old queue "
        "handlers, or old Workbench node/status artifacts:\n" + "\n".join(offenders)
    )
