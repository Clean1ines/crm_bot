from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INGESTION = ROOT / "src/application/services/knowledge_ingestion_service.py"

FORBIDDEN_HELPER_DEFS = {
    "_apply_answer_resolution_decisions",
    "_resolve_compiled_answer_cases",
    "build_compiler_batches_from_technical_batches",
    "build_raw_answer_candidates_from_preprocessing_entries",
    "persist_stage_e_compiler_outputs",
    "cleanup_compiled_entries_mechanically",
}

SERVICE_FILES = (
    ROOT / "src/application/services/knowledge_structured_ingestion_service.py",
    ROOT / "src/application/services/knowledge_failed_batch_retry_service.py",
    ROOT / "src/application/services/knowledge_ready_answer_publication_service.py",
    ROOT / "src/application/services/knowledge_retighten_service.py",
    ROOT / "src/application/services/knowledge_surface_ingestion_service.py",
)

QUEUE_HANDLER_FILES = (
    ROOT / "src/infrastructure/queue/handlers/knowledge_upload.py",
    ROOT / "src/infrastructure/queue/handlers/knowledge_publish_ready.py",
    ROOT / "src/infrastructure/queue/handlers/knowledge_failed_batches.py",
    ROOT / "src/infrastructure/queue/handlers/knowledge_retighten.py",
)


def _top_level_defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            result.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result.add(target.id)

    return result


def test_knowledge_ingestion_service_is_compatibility_facade_only() -> None:
    source = INGESTION.read_text(encoding="utf-8")
    defined_names = _top_level_defined_names(INGESTION)

    assert "class KnowledgeIngestionService" in source
    assert not (FORBIDDEN_HELPER_DEFS & defined_names)
    assert "knowledge_answer_resolution_service import" not in source
    assert "knowledge_canonical_publication_builder import" not in source
    assert "knowledge_source_material_builder import" not in source


def test_split_services_do_not_import_business_helpers_from_legacy_ingestion() -> None:
    for path in SERVICE_FILES:
        source = path.read_text(encoding="utf-8")

        assert (
            "from src.application.services.knowledge_ingestion_service import"
            not in source
        )
        assert "KnowledgeIngestionService" not in source


def test_queue_handlers_do_not_import_knowledge_ingestion_service() -> None:
    for path in QUEUE_HANDLER_FILES:
        source = path.read_text(encoding="utf-8")

        assert "KnowledgeIngestionService" not in source
        assert (
            "from src.application.services.knowledge_ingestion_service import"
            not in source
        )


def _legacy_stage_k_helper_module_name() -> str:
    return "_".join(("knowledge_stage_k", "shared_helpers"))


def test_stage_k_shared_helper_file_is_removed() -> None:
    helper_path = (
        ROOT / "src/application/services" / f"{_legacy_stage_k_helper_module_name()}.py"
    )

    assert not helper_path.exists()


def test_application_services_do_not_import_stage_k_shared_helper() -> None:
    helper_module_name = _legacy_stage_k_helper_module_name()
    services_dir = ROOT / "src/application/services"

    for path in services_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert helper_module_name not in source, path


def test_knowledge_ingestion_service_has_no_stage_k_helper_import() -> None:
    source = INGESTION.read_text(encoding="utf-8")

    assert _legacy_stage_k_helper_module_name() not in source


def test_application_services_do_not_import_old_private_compiler_batch_builders() -> (
    None
):
    forbidden_names = {
        "_compiler_batches_from_" + "technical_batches",
        "_" + "stage_e_compiler_run_id",
        "_" + "stage_e_compiler_run",
    }
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if (
                node.module
                != "src.application.services.knowledge_compiler_batch_builder"
            ):
                continue
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")

    assert offenders == []


def test_application_services_do_not_import_old_private_stage_e_publication_helpers() -> (
    None
):
    forbidden_names = {
        "_persist_" + "stage_e_compiler_outputs",
        "_stage_e_answer_" + "candidates_from_entries",
        "_stage_e_candidate_" + "clusters_from_entries",
        "_stage_e_" + "compilation_metrics",
    }
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if (
                node.module
                != "src.application.services.knowledge_stage_e_publication_helpers"
            ):
                continue
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")

    assert offenders == []


def test_application_services_do_not_import_old_private_answer_candidate_builders() -> (
    None
):
    forbidden_names = {
        "_raw_" + "answer_candidate_id",
        "_raw_" + "answer_candidates_from_preprocessing_entries",
    }
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if (
                node.module
                != "src.application.services.knowledge_answer_candidate_builder"
            ):
                continue
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")

    assert offenders == []


def test_application_services_do_not_import_old_private_source_material_builders() -> (
    None
):
    forbidden_names = {
        "_" + "chunk_content",
        "_" + "source_chunk_optional_int",
        "_" + "indexable_chunks",
        "_" + "source_chunks_from_json_chunks",
        "_" + "json_chunks_from_source_chunks",
        "_compiler_" + "source_chunks_for_preprocessing",
        "_" + "is_markdown_file",
        "_json_array_" + "field_item_count",
    }
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if (
                node.module
                != "src.application.services.knowledge_source_material_builder"
            ):
                continue
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")

    assert offenders == []


def test_application_services_do_not_import_old_private_answer_compiler_batching() -> (
    None
):
    forbidden_name = "_technical_" + "chunk_batches_for_answer_compiler"
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if (
                node.module
                != "src.application.services.knowledge_answer_compiler_batching"
            ):
                continue
            for alias in node.names:
                if alias.name == forbidden_name:
                    offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")

    assert offenders == []


def test_application_services_do_not_import_old_private_preprocessing_result_helpers() -> (
    None
):
    forbidden_names = {
        "_" + "source_excerpt_to_text",
        "_preprocessing_" + "failure_status_message",
        "_json_" + "metric_int",
        "_preprocessing_" + "result_from_entries",
    }
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if (
                node.module
                != "src.application.services.knowledge_preprocessing_result_helpers"
            ):
                continue
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")

    assert offenders == []


def test_application_services_do_not_import_old_private_compiled_cleanup_helpers() -> (
    None
):
    forbidden_names = {
        "_Mechanical" + "CleanupCompiledEntriesResult",
        "_mechanically_" + "cleanup_compiled_entries",
        "_source_" + "excerpts_from_preprocessing_entry",
    }
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if (
                node.module
                != "src.application.services.knowledge_compiled_entry_cleanup"
            ):
                continue
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")

    assert offenders == []


def test_application_services_do_not_alias_canonical_publication_builders_to_private_names() -> (
    None
):
    module = "src.application.services.knowledge_canonical_publication_builder"
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != module:
                continue
            for alias in node.names:
                if alias.asname and alias.asname.startswith("_canonical_entries_from"):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{alias.name} as {alias.asname}"
                    )

    assert offenders == []


def test_application_services_do_not_import_old_private_retighten_planner_api() -> None:
    forbidden_names = {
        "_preprocessing_" + "entry_from_canonical_entry",
        "_deterministic_" + "retighten_existing_document_plan",
        "_retighten_" + "existing_document_plan",
        "_compose_" + "retighten_existing_document_plans",
        "_existing_" + "project_titles_for_answer_resolution",
        "_retighten_" + "updated_canonical_entries",
        "_retighten_" + "archived_entry_ids",
    }
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != "src.application.services.knowledge_retighten_planner":
                continue
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")

    assert offenders == []


def test_application_services_do_not_import_old_private_answer_resolution_api() -> None:
    module = "src.application.services.knowledge_answer_resolution_service"
    forbidden_names = {
        "_answer_" + "resolution_cases_from_entries",
        "_answer_" + "resolution_decision_is_too_noisy",
        "_answer_" + "resolution_decisions_with_case_candidate_ids",
        "_cleanup_" + "answer_resolution_text_with_metrics",
        "_limit_" + "compiled_text",
        "_reject_" + "noisy_answer_resolution_decisions",
        "_answer_" + "resolution_text_fingerprint",
        "_answer_" + "resolution_tokens_from_text",
        "_answer_" + "resolution_token_similarity",
        "_merge_" + "answer_text",
        "_merge_" + "answer_units_deterministically",
        "_merge_" + "entry_fields_deterministically",
    }
    offenders: list[str] = []

    for path in (ROOT / "src/application/services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != module:
                continue
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"{path.relative_to(ROOT)}:{alias.name}")

    assert offenders == []


def test_production_code_does_not_import_private_application_service_symbols() -> None:
    scan_roots = (
        ROOT / "src/application/services",
        ROOT / "src/infrastructure/queue/handlers",
    )

    # Keep this empty by default. Add a tuple only for a consciously accepted,
    # temporary exception with a follow-up task to remove it.
    allowlist: set[tuple[str, str, str]] = set()

    offenders: list[str] = []

    for scan_root in scan_roots:
        for path in sorted(scan_root.glob("*.py")):
            if path.name == "__init__.py":
                continue

            relative_path = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))

            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if node.module is None:
                    continue
                if not node.module.startswith("src.application.services."):
                    continue

                for alias in node.names:
                    if alias.name == "*":
                        offenders.append(
                            f"{relative_path}: wildcard import from {node.module}"
                        )
                        continue

                    if not alias.name.startswith("_"):
                        continue
                    if alias.name.startswith("__"):
                        continue

                    key = (relative_path, node.module, alias.name)
                    if key in allowlist:
                        continue

                    rendered_import = alias.name
                    if alias.asname:
                        rendered_import += f" as {alias.asname}"

                    offenders.append(
                        f"{relative_path}: from {node.module} import {rendered_import}"
                    )

    assert offenders == []
