from pathlib import Path


CHECKED = (
    Path("src/application/workbench_observability/evidence_trace.py"),
    Path("src/application/workbench_observability/import_quality.py"),
    Path("src/infrastructure/db/workbench_observability_repository.py"),
)

FORBIDDEN = (
    "registry_entries",
    "registry_entry_id",
    "registry_entry_key",
    "target_registry_entry_id",
    "list_evidence_trace_registry_entries",
    "list_import_quality_registry_entries",
)

REQUIRED = (
    "canonical_facts",
    "fact_id",
    "fact_key",
    "target_fact_id",
    "list_evidence_trace_canonical_facts",
    "list_import_quality_canonical_facts",
)


def test_workbench_observability_uses_canonical_fact_vocabulary() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in CHECKED)

    for token in REQUIRED:
        assert token in source

    for token in FORBIDDEN:
        assert token not in source
