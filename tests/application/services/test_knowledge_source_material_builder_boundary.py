from __future__ import annotations

import ast
from pathlib import Path


INGESTION = Path("src/application/services/knowledge_ingestion_service.py")
SURFACE = Path("src/application/services/knowledge_surface_ingestion_service.py")
BUILDER = Path("src/application/services/knowledge_source_material_builder.py")

MOVED_HELPERS = {
    "_chunk_content",
    "_is_separator_chunk",
    "_looks_like_broken_fragment",
    "_indexable_chunks",
    "_source_chunk_optional_int",
    "_source_chunk_text",
    "_source_chunk_index",
    "_source_chunks_from_json_chunks",
    "_json_chunks_from_source_chunks",
    "_compiler_source_chunks_for_preprocessing",
}


def _top_level_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def test_source_material_helpers_live_in_shared_builder() -> None:
    builder_functions = _top_level_function_names(BUILDER)

    assert MOVED_HELPERS <= builder_functions


def test_ingestion_no_longer_defines_moved_source_material_helpers() -> None:
    ingestion_functions = _top_level_function_names(INGESTION)

    assert MOVED_HELPERS.isdisjoint(ingestion_functions)


def test_surface_service_does_not_import_private_helpers_from_ingestion() -> None:
    source = Path(
        "src/application/services/knowledge_surface_ingestion_service.py"
    ).read_text(encoding="utf-8")

    assert (
        "from src.application.services.knowledge_ingestion_service import" not in source
    )
    assert "KnowledgeIngestionService" not in source
    assert "knowledge_source_material_builder" in source

    for helper_name in (
        "_compiler_source_chunks_for_preprocessing",
        "_indexable_chunks",
        "_source_chunks_from_json_chunks",
    ):
        assert helper_name in source
