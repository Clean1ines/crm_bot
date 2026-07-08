from __future__ import annotations

import re
from pathlib import Path


RUNTIME_ONLY_BOUNDARY_FILES = (
    Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/postgres/"
        "postgres_workbench_rag_eval_repository.py"
    ),
    Path(
        "src/contexts/knowledge_workbench/retrieval/infrastructure/postgres/"
        "postgres_published_workbench_retrieval_repository.py"
    ),
)


FORBIDDEN_LEGACY_RUNTIME_DEPENDENCIES = (
    "knowledge_workbench_" + "canonical_facts",
    "knowledge_workbench_" + "fact_registries",
    "fact.status",
    "JOIN knowledge_workbench_" + "canonical_facts",
    "JOIN knowledge_workbench_" + "canonical_facts AS fact",
)


REQUIRED_RUNTIME_TABLES = (
    "knowledge_workbench_runtime_retrieval_entries",
    "knowledge_workbench_runtime_retrieval_entry_embeddings",
)


def test_workbench_rag_eval_runtime_boundary_does_not_depend_on_legacy_facts() -> None:
    offenders: list[str] = []

    for path in RUNTIME_ONLY_BOUNDARY_FILES:
        source = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_LEGACY_RUNTIME_DEPENDENCIES:
            if marker in source:
                offenders.append(f"{path.as_posix()}: {marker}")
        if re.search(r"\bJOIN\b[^\n]*\bAS\s+fact\b", source):
            offenders.append(f"{path.as_posix()}: JOIN ... AS fact")

    assert offenders == []


def test_workbench_rag_eval_runtime_boundary_uses_runtime_tables() -> None:
    missing: list[str] = []

    for path in RUNTIME_ONLY_BOUNDARY_FILES:
        source = path.read_text(encoding="utf-8")
        for marker in REQUIRED_RUNTIME_TABLES:
            if marker not in source:
                missing.append(f"{path.as_posix()}: {marker}")

    assert missing == []
