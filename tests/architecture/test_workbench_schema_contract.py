from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import asyncpg


@dataclass(frozen=True, slots=True)
class RequiredColumn:
    table_name: str
    column_name: str


@dataclass(frozen=True, slots=True)
class ForbiddenColumn:
    table_name: str
    column_name: str


@dataclass(frozen=True, slots=True)
class RequiredTable:
    table_name: str


REQUIRED_TABLES: tuple[RequiredTable, ...] = (
    RequiredTable("knowledge_workbench_registry_update_applications"),
)


REQUIRED_COLUMNS: tuple[RequiredColumn, ...] = (
    RequiredColumn("knowledge_workbench_fact_registries", "registry_id"),
    RequiredColumn("knowledge_workbench_registry_snapshots", "registry_id"),
    RequiredColumn("knowledge_workbench_registry_snapshots", "entries_payload"),
    RequiredColumn("knowledge_workbench_registry_snapshots", "relations_payload"),
    RequiredColumn("knowledge_workbench_registry_snapshots", "entry_count"),
    RequiredColumn("knowledge_workbench_registry_snapshots", "relation_count"),
    RequiredColumn("knowledge_workbench_canonical_facts", "registry_id"),
    RequiredColumn("knowledge_workbench_fact_triples", "registry_id"),
    RequiredColumn("knowledge_workbench_fact_mentions", "registry_id"),
    RequiredColumn("knowledge_workbench_fact_relations", "registry_id"),
    RequiredColumn(
        "knowledge_workbench_fact_registry_application_queue",
        "source_node_run_id",
    ),
    RequiredColumn(
        "knowledge_workbench_section_batch_queue_items",
        "registry_application_queue_item_id",
    ),
    RequiredColumn(
        "knowledge_workbench_registry_update_applications",
        "application_id",
    ),
    RequiredColumn("knowledge_workbench_processing_runs", "last_error"),
)


FORBIDDEN_COLUMNS: tuple[ForbiddenColumn, ...] = (
    ForbiddenColumn("knowledge_workbench_fact_registries", "fact_registry_id"),
    ForbiddenColumn("knowledge_workbench_registry_snapshots", "fact_registry_id"),
    ForbiddenColumn("knowledge_workbench_registry_snapshots", "fact_registry_payload"),
    ForbiddenColumn("knowledge_workbench_registry_snapshots", "canonical_fact_count"),
    ForbiddenColumn("knowledge_workbench_registry_snapshots", "fact_relation_count"),
    ForbiddenColumn("knowledge_workbench_canonical_facts", "fact_registry_id"),
    ForbiddenColumn("knowledge_workbench_fact_triples", "fact_registry_id"),
    ForbiddenColumn("knowledge_workbench_fact_mentions", "fact_registry_id"),
    ForbiddenColumn("knowledge_workbench_fact_relations", "fact_registry_id"),
    ForbiddenColumn(
        "knowledge_workbench_fact_registry_application_queue",
        "fact_registry_node_run_id",
    ),
    ForbiddenColumn(
        "knowledge_workbench_section_batch_queue_items",
        "fact_registry_application_queue_item_id",
    ),
)


def _read_database_url_from_env_file(path: Path) -> str:
    assert path.exists(), f"{path} must exist for Workbench prod schema contract test"

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        key, separator, value = line.partition("=")
        if separator != "=" or key.strip() != "DATABASE_URL":
            continue

        cleaned = value.strip()
        if (
            len(cleaned) >= 2
            and cleaned[0] == cleaned[-1]
            and cleaned[0] in {"'", '"'}
        ):
            cleaned = cleaned[1:-1]

        assert cleaned, f"{path} DATABASE_URL must not be empty"
        return cleaned

    raise AssertionError(f"DATABASE_URL not found in {path}")


def _database_url() -> str:
    # Intentional:
    # this architecture contract verifies the actual production schema.
    # It is read-only and only queries information_schema.
    # Do not use .env.test here: local test DB can drift from production.
    return _read_database_url_from_env_file(Path(".env.prod"))


async def _fetch_existing_columns(
    connection: asyncpg.Connection,
) -> set[tuple[str, str]]:
    rows = await connection.fetch(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name LIKE 'knowledge_workbench_%'
        ORDER BY table_name, ordinal_position
        """
    )
    return {
        (str(row["table_name"]), str(row["column_name"]))
        for row in rows
    }


async def _fetch_existing_tables(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name LIKE 'knowledge_workbench_%'
        ORDER BY table_name
        """
    )
    return {str(row["table_name"]) for row in rows}


async def _assert_workbench_schema_contract(database_url: str) -> None:
    connection = await asyncpg.connect(database_url)
    try:
        existing_columns = await _fetch_existing_columns(connection)
        existing_tables = await _fetch_existing_tables(connection)
    finally:
        await connection.close()

    missing_tables = [
        required.table_name
        for required in REQUIRED_TABLES
        if required.table_name not in existing_tables
    ]

    missing_columns = [
        f"{required.table_name}.{required.column_name}"
        for required in REQUIRED_COLUMNS
        if (required.table_name, required.column_name) not in existing_columns
    ]

    forbidden_columns_present = [
        f"{forbidden.table_name}.{forbidden.column_name}"
        for forbidden in FORBIDDEN_COLUMNS
        if (forbidden.table_name, forbidden.column_name) in existing_columns
    ]

    failures: list[str] = []

    if missing_tables:
        failures.append(
            "Missing required Workbench tables:\n"
            + "\n".join(f"  - {item}" for item in missing_tables)
        )

    if missing_columns:
        failures.append(
            "Missing required Workbench columns:\n"
            + "\n".join(f"  - {item}" for item in missing_columns)
        )

    if forbidden_columns_present:
        failures.append(
            "Forbidden legacy Workbench columns are still present:\n"
            + "\n".join(f"  - {item}" for item in forbidden_columns_present)
        )

    assert not failures, "\n\n".join(failures)


def test_workbench_database_schema_matches_076_077_contract() -> None:
    asyncio.run(_assert_workbench_schema_contract(_database_url()))
