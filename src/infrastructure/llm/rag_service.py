import json
import re
from typing import List, Dict, Any
from groq import AsyncGroq

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository

logger = get_logger(__name__)


class RAGService:
    def __init__(self, knowledge_repo: KnowledgeRepository):
        self._repo = knowledge_repo
        self._groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    # -------------------------
    # Utils
    # -------------------------
    def _normalize(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _safe_json_extract(self, text: str) -> List[int]:
        """
        ЖЁСТКИЙ safe parser вместо хрупкого json.loads.
        """
        if not text:
            return []

        match = re.search(r"\[[0-9,\s]+\]", text)
        if not match:
            return []

        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return [int(x) for x in data if isinstance(x, (int, float))]
        except Exception:
            return []

        return []

    # -------------------------
    # Query expansion
    # -------------------------
    async def _expand_query(self, query: str) -> List[str]:
        prompt = f"""
Перефразируй запрос 3 разными способами.

Запрос: "{query}"

Верни ТОЛЬКО JSON массив строк:
["...", "...", "..."]
"""

        try:
            resp = await self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=120,
            )

            content = resp.choices[0].message.content or ""

            match = re.search(r"\[.*\]", content, re.DOTALL)
            if not match:
                return [query]

            variants = json.loads(match.group(0))

            if not isinstance(variants, list):
                return [query]

            cleaned = []
            for v in variants:
                if isinstance(v, str) and v.strip():
                    cleaned.append(self._normalize(v))

            return cleaned[:3]

        except Exception as e:
            logger.warning(f"expand failed: {e}")

        return [query]

    # -------------------------
    # Hybrid rerank (FIXED)
    # -------------------------
    async def _rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int):

        if not candidates:
            return []

        q = self._normalize(query)

        scored = []

        for idx, c in enumerate(candidates):

            content = c.get("content", "")
            norm_content = self._normalize(content)

            # -------------------------
            # 1. embedding/lexical score (from DB)
            # -------------------------
            base_score = float(c.get("score", 0))

            # -------------------------
            # 2. keyword overlap boost (CRITICAL for RU)
            # -------------------------
            overlap = len(set(q.split()) & set(norm_content.split()))
            keyword_boost = overlap * 0.15

            # -------------------------
            # 3. positional bonus (title / start of chunk)
            # -------------------------
            position_boost = 0.05 if len(content) > 0 else 0

            final_score = base_score + keyword_boost + position_boost

            scored.append((final_score, idx, c))

        scored.sort(reverse=True, key=lambda x: x[0])

        return [c for _, _, c in scored[:top_k]]

    # -------------------------
    # Main search pipeline
    # -------------------------
    async def search_with_expansion(
        self,
        project_id: str,
        query: str,
        limit_per_query: int = 10,
        final_limit: int = 3,
    ) -> List[Dict[str, Any]]:

        normalized = self._normalize(query)
        variants = await self._expand_query(normalized)

        variants = list(dict.fromkeys([normalized] + variants))

        candidates_by_id = {}

        for v in variants:

            results = await self._repo.search(
                project_id=project_id,
                query=v,
                limit=limit_per_query,
                hybrid_fallback=True,
            )

            for r in results:
                cid = r["id"]

                if cid not in candidates_by_id:
                    candidates_by_id[cid] = r
                else:
                    # keep BEST score
                    candidates_by_id[cid]["score"] = max(
                        float(candidates_by_id[cid].get("score", 0)),
                        float(r.get("score", 0)),
                    )

        candidates = sorted(
            candidates_by_id.values(),
            key=lambda x: float(x.get("score", 0)),
            reverse=True
        )[:60]

        if not candidates:
            return []

        return await self._rerank(query, candidates, final_limit)
