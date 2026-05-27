from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import replace

from src.application.services.knowledge_surface_graph_quality import (
    validate_faq_surface_graph_quality,
)
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingMode,
    KnowledgePreprocessingValidationError,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceDraft,
    RetrievalSurfaceGraph,
    RetrievalSurfaceRelation,
    RetrievalSurfaceSourceUnit,
)
from src.infrastructure.llm.knowledge_surface_compiler import GroqKnowledgeSurfaceCompiler

SURFACE_KEY_PATTERN = re.compile(r"[^0-9A-Za-z_]+")


class GroqSplitKnowledgeSurfaceCompiler(GroqKnowledgeSurfaceCompiler):
    async def compile_surfaces(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
        run_id: str,
    ) -> RetrievalSurfaceCompilationResult:
        units = tuple(source_units)
        if not units:
            raise KnowledgePreprocessingValidationError(
                "FAQ surface compiler requires source units"
            )

        parts: list[RetrievalSurfaceCompilationResult] = []
        for index, unit in enumerate(units):
            parts.append(
                await super().compile_surfaces(
                    mode=mode,
                    source_units=(unit,),
                    file_name=file_name,
                    run_id=f"{run_id}:unit:{index}",
                )
            )

        result = _merge_parts(
            mode=mode,
            run_id=run_id,
            units=units,
            parts=tuple(parts),
        )
        quality = validate_faq_surface_graph_quality(result.graph)
        if not quality.passed:
            raise KnowledgePreprocessingValidationError(
                "FAQ surface graph quality failed: " + ", ".join(quality.issues)
            )

        metrics = _json_object({**result.metrics, **quality.metrics})
        if quality.warnings:
            metrics["quality_warnings"] = [
                json_value_from_unknown(warning) for warning in quality.warnings
            ]
        return RetrievalSurfaceCompilationResult(
            mode=result.mode,
            prompt_version=result.prompt_version,
            model=result.model,
            graph=replace(result.graph, metrics=metrics),
            metrics=metrics,
        )


def _merge_parts(
    *,
    mode: KnowledgePreprocessingMode,
    run_id: str,
    units: tuple[RetrievalSurfaceSourceUnit, ...],
    parts: tuple[RetrievalSurfaceCompilationResult, ...],
) -> RetrievalSurfaceCompilationResult:
    document_id = units[0].document_id
    surfaces: list[RetrievalSurfaceDraft] = []
    for unit_index, part in enumerate(parts):
        for surface in part.graph.surfaces:
            key = _key(unit_index, surface.local_surface_key)
            surfaces.append(
                replace(
                    surface,
                    id=_id(run_id, "surface", key),
                    run_id=run_id,
                    document_id=document_id,
                    local_surface_key=key,
                    metadata={
                        **surface.metadata,
                        "source_unit_split_compilation": True,
                        "source_unit_index": unit_index,
                        "original_surface_key": surface.local_surface_key,
                    },
                )
            )
    relations = _relations(
        run_id=run_id,
        document_id=document_id,
        surfaces=tuple(surfaces),
    )
    metrics = _json_object(
        {
            "source_unit_split_compilation": True,
            "source_unit_count": len(units),
            "source_unit_compilation_count": len(parts),
            "surface_count": len(surfaces),
            "relation_count": len(relations),
            "ownership_count": 0,
            "reassignment_count": 0,
            "merge_decision_count": 0,
        }
    )
    graph = RetrievalSurfaceGraph(
        run_id=run_id,
        document_id=document_id,
        source_units=units,
        surfaces=tuple(surfaces),
        relations=relations,
        ownership=(),
        reassignments=(),
        merge_decisions=(),
        metrics=metrics,
    )
    return RetrievalSurfaceCompilationResult(
        mode=mode,
        prompt_version=parts[0].prompt_version,
        model=parts[0].model,
        graph=graph,
        metrics=metrics,
    )


def _relations(
    *,
    run_id: str,
    document_id: str,
    surfaces: tuple[RetrievalSurfaceDraft, ...],
) -> tuple[RetrievalSurfaceRelation, ...]:
    return tuple(
        RetrievalSurfaceRelation(
            id=_id(run_id, "sibling", index),
            run_id=run_id,
            document_id=document_id,
            parent_surface_key=left.local_surface_key,
            child_surface_key=right.local_surface_key,
            relation_type="sibling",
            reason="Fallback relation between adjacent source-unit surfaces.",
            confidence=0.25,
        )
        for index, (left, right) in enumerate(zip(surfaces, surfaces[1:]))
    )


def _key(unit_index: int, value: str) -> str:
    normalized = SURFACE_KEY_PATTERN.sub("_", value).strip("_") or "surface"
    return f"u{unit_index}_{normalized}"


def _id(*parts: object) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(str(part) for part in parts)))


def _json_object(payload: dict[str, object]) -> JsonObject:
    return {str(key): json_value_from_unknown(value) for key, value in payload.items()}
