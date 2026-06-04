from pathlib import Path


ROOTS = (
    Path("src"),
    Path("migrations"),
)

DROPPED_TABLE_TOKENS = (
    "knowledge_answer_candidates",
    "knowledge_candidate_cluster_members",
    "knowledge_candidate_clusters",
    "knowledge_compilation_metrics",
    "knowledge_compiler_batches",
    "knowledge_compiler_runs",
    "knowledge_surface_answer_drafts",
    "knowledge_surface_candidates",
    "knowledge_surface_compiler_runs",
    "knowledge_surface_compiler_stages",
    "knowledge_surface_global_relations",
    "knowledge_surface_local_relations",
    "knowledge_surface_merge_decisions",
    "knowledge_surface_question_ownership",
    "knowledge_surface_question_reassignments",
    "knowledge_surface_reconciliation_runs",
    "knowledge_surface_rejected_questions",
    "knowledge_surface_relations",
    "knowledge_surface_source_units",
    "knowledge_surfaces",
    "knowledge_workbench_registry_application_queue_items",
    "knowledge_workbench_section_batch_plans",
    "knowledge_workbench_section_work_items",
)

# These words are not DB table names, but they are direct semantic tails of the
# tables already dropped from dev/prod DBs.
DROPPED_SEMANTIC_TOKENS = (
    "create_knowledge_surfaces",
    "update_knowledge_surfaces",
    "KnowledgeSurface",
    "SurfaceMaterializationResult",
    "SurfaceCurationSession",
    "SurfaceCurationChange",
    "SurfaceCurationState",
    "SurfaceKind",
    "canonical_question",
    "surface_kind",
    "answer_delta",
    "question_scope",
    "local_surface_key",
    "target_surface_key",
)


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".sql", ".txt", ".ts", ".tsx"}:
                continue
            files.append(path)
    return sorted(files)


def test_dropped_legacy_knowledge_tables_are_not_referenced_by_source_or_migrations() -> (
    None
):
    offenders: list[str] = []

    for path in _iter_files():
        text = path.read_text(encoding="utf-8")
        for token in DROPPED_TABLE_TOKENS:
            if token in text:
                offenders.append(f"{path}: {token}")

    assert not offenders, "\n".join(offenders)


def test_dropped_surface_semantics_are_not_referenced_by_workbench_production_code() -> (
    None
):
    checked_roots = (
        Path("src/application"),
        Path("src/domain"),
        Path("src/infrastructure"),
        Path("src/interfaces"),
    )
    offenders: list[str] = []

    for root in checked_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in DROPPED_SEMANTIC_TOKENS:
                if token in text:
                    offenders.append(f"{path}: {token}")

    assert not offenders, "\n".join(offenders)
