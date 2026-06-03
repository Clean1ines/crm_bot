from pathlib import Path


CHECKED_ROOTS = (
    Path("src/application"),
    Path("src/domain/project_plane/knowledge_workbench"),
    Path("src/infrastructure/db"),
)

REQUIRED_TOKENS = (
    "claim_observations_node_run_id",
    "claim_input_refs",
    "CLAIM_OBSERVATIONS_PERSISTED",
)

FORBIDDEN_TOKENS = (
    "section_findings_node_run_id",
    "finding_ids",
    "FINDINGS_PERSISTED",
    "mark_section_batch_item_findings_persisted",
    "section_findings_payload",
    "kept_finding_ids",
)


def _combined_source() -> str:
    chunks: list[str] = []
    for root in CHECKED_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_workbench_queue_checkpoint_vocabulary_is_claim_observation_based() -> None:
    source = _combined_source()

    for token in REQUIRED_TOKENS:
        assert token in source

    for token in FORBIDDEN_TOKENS:
        assert token not in source
