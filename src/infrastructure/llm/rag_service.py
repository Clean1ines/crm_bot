"""Testable RAG pipeline service.

Pipeline contract:
1. normalize query
2. expand query through injected QueryExpander
3. search repository for original + expanded variants
4. deduplicate by candidate id
5. keep best repository score per candidate
6. deterministically rerank using score + lexical overlap + position boost
7. enforce final limits

The service does not instantiate Groq by default.
Production wiring may inject an external query expansion adapter explicitly.
"""

from __future__ import annotations

import json
import re
from typing import Mapping

from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView
from src.infrastructure.llm.rag_contract import (
    KnowledgeSearchRepository,
    QueryExpander,
    RAGCandidate,
    RAGPipelineConfig,
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

RAGSearchRow = Mapping[str, object] | KnowledgeSearchResultView


class _NoOpQueryExpander:
    async def expand(self, query: str, *, max_expansions: int) -> list[str]:
        return []


class RAGService:
    def __init__(
        self,
        knowledge_repo: KnowledgeSearchRepository,
        *,
        query_expander: QueryExpander | None = None,
        config: RAGPipelineConfig | None = None,
    ) -> None:
        self._repo = knowledge_repo
        self._query_expander = query_expander or _NoOpQueryExpander()
        self._config = (config or RAGPipelineConfig()).normalized()

    # -------------------------
    # Utils
    # -------------------------

    def _normalize(self, text: str) -> str:
        normalized = (text or "").lower().strip()
        normalized = re.sub(r"[^\w\sа-яА-ЯёЁ-]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _safe_json_extract(self, text: str) -> list[int]:
        """Extract a strict JSON array of integer indexes from model output.

        This method is kept for compatibility with existing hygiene tests.
        Floats are rejected even if they could be converted to int.
        """

        if not text:
            return []

        match = re.search(r"\[[0-9,\s]+\]", text)
        if not match:
            return []

        try:
            data = json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError, ValueError, OverflowError):
            return []

        if not isinstance(data, list):
            return []

        if not all(
            isinstance(item, int) and not isinstance(item, bool) for item in data
        ):
            return []

        return list(data)

    def _unique_queries(self, query: str, expansions: list[str]) -> list[str]:
        normalized_original = self._normalize(query)
        seen: set[str] = set()
        result: list[str] = []

        for item in [normalized_original, *expansions]:
            normalized = self._normalize(item)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)

        return result

    async def _expand_query(self, query: str) -> list[str]:
        try:
            return await self._query_expander.expand(
                query,
                max_expansions=self._config.max_expansions,
            )
        except Exception as exc:
            logger.warning(
                "RAG query expander raised unexpectedly; falling back to original query",
                extra={"error": str(exc)[:200], "error_type": type(exc).__name__},
            )
            return []

    # -------------------------
    # Dedup and rerank
    # -------------------------

    def _deduplicate(self, rows: list[RAGSearchRow]) -> list[RAGCandidate]:
        by_id: dict[str, RAGCandidate] = {}

        for row in rows:
            candidate = _candidate_from_row(row)
            if not candidate.id or not candidate.content:
                continue

            existing = by_id.get(candidate.id)
            if existing is None:
                by_id[candidate.id] = candidate
                continue

            if candidate.score > existing.score:
                candidate.metadata.update(existing.metadata)
                candidate.metadata["matched_methods"] = self._merge_methods(
                    existing.metadata.get("matched_methods"),
                    existing.method,
                    candidate.method,
                )
                by_id[candidate.id] = candidate
            else:
                existing.metadata["matched_methods"] = self._merge_methods(
                    existing.metadata.get("matched_methods"),
                    existing.method,
                    candidate.method,
                )

        candidates = sorted(
            by_id.values(),
            key=lambda item: item.score,
            reverse=True,
        )
        return candidates[: self._config.max_candidates]

    def _merge_methods(self, previous: object, *methods: str) -> list[str]:
        result: list[str] = []

        if isinstance(previous, list):
            result.extend(str(item) for item in previous if item)

        for method in methods:
            if method and method not in result:
                result.append(method)

        return result

    async def _rerank(
        self,
        query: str,
        candidates: list[RAGCandidate] | list[RAGSearchRow],
        top_k: int,
    ) -> list[dict[str, object]]:
        """Deterministic rerank.

        The final score semantics are:
        final_score = repository score + keyword overlap boost + position boost.
        """

        if not candidates:
            return []

        normalized_query = self._normalize(query)
        query_terms = set(normalized_query.split())

        normalized_candidates = [
            item if isinstance(item, RAGCandidate) else _candidate_from_row(item)
            for item in candidates
        ]

        scored: list[tuple[float, int, RAGCandidate]] = []

        for index, candidate in enumerate(normalized_candidates):
            content_terms = set(self._normalize(candidate.content).split())

            if query_terms:
                overlap_ratio = len(query_terms & content_terms) / len(query_terms)
            else:
                overlap_ratio = 0.0

            keyword_score = overlap_ratio * self._config.keyword_boost
            position_score = self._config.position_boost if candidate.content else 0.0
            final_score = candidate.score + keyword_score + position_score

            candidate.score = final_score
            scored.append((final_score, -index, candidate))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

        return [candidate.to_tool_payload() for _, _, candidate in scored[:top_k]]

    # -------------------------
    # Main search pipeline
    # -------------------------

    async def search_with_expansion(
        self,
        project_id: str,
        query: str,
        thread_id: str | None = None,
        limit_per_query: int | None = None,
        final_limit: int | None = None,
    ) -> list[dict[str, object]]:
        runtime_config = RAGPipelineConfig(
            limit_per_query=limit_per_query or self._config.limit_per_query,
            final_limit=final_limit or self._config.final_limit,
            max_expansions=self._config.max_expansions,
            max_candidates=self._config.max_candidates,
            keyword_boost=self._config.keyword_boost,
            position_boost=self._config.position_boost,
        ).normalized()

        normalized_query = self._normalize(query)
        if not project_id or not normalized_query:
            return []

        expansions = await self._expand_query(normalized_query)
        variants = self._unique_queries(normalized_query, expansions)

        raw_candidates: list[RAGSearchRow] = []

        for variant in variants:
            results = await self._repo.search(
                project_id=project_id,
                query=variant,
                limit=runtime_config.limit_per_query,
                hybrid_fallback=True,
                thread_id=thread_id,
            )
            raw_candidates.extend(results)

        candidates = self._deduplicate(raw_candidates)
        if not candidates:
            return []

        return await self._rerank(
            normalized_query,
            candidates[: runtime_config.max_candidates],
            runtime_config.final_limit,
        )


def _candidate_from_row(row: RAGSearchRow) -> RAGCandidate:
    if isinstance(row, KnowledgeSearchResultView):
        return RAGCandidate.from_knowledge_view(row)
    return RAGCandidate.from_mapping(row)
