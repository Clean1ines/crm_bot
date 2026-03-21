import json
import re
from typing import List, Dict, Any
from groq import AsyncGroq

from src.core.logging import get_logger
from src.core.config import settings
from src.database.repositories.knowledge_repository import KnowledgeRepository

logger = get_logger(__name__)


class RAGService:
    def __init__(self, knowledge_repo: KnowledgeRepository):
        self._repo = knowledge_repo
        self._groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    def _normalize(self, text: str) -> str:
        """Простая нормализация: lower, strip, удаление пунктуации, лишних пробелов."""
        text = text.lower().strip()
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text

    async def _expand_query(self, query: str) -> List[str]:
        """Генерация 3 вариантов запроса через Groq."""
        prompt = f"""Переформулируй пользовательский вопрос тремя разными способами, сохраняя смысл.
Исходный вопрос: "{query}"
Верни только список в формате JSON, например: ["вариант1", "вариант2", "вариант3"]"""

        try:
            response = await self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200,
            )
            content = response.choices[0].message.content.strip()
            start = content.find('[')
            end = content.rfind(']') + 1
            if start != -1 and end != -1:
                json_str = content[start:end]
                variants = json.loads(json_str)
                return [self._normalize(v) for v in variants if v and isinstance(v, str)]
            else:
                return [query]
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}", extra={"query": query})
            return [query]

    async def _rerank_candidates(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 2) -> List[Dict[str, Any]]:
        """
        Использует LLM для выбора top_k наиболее релевантных чанков.
        """
        if not candidates:
            return []

        # Формируем нумерованный список чанков (сокращаем длинные тексты)
        items = []
        for idx, c in enumerate(candidates):
            content = c.get("content", "")[:500]  # ограничим длину
            items.append(f"{idx+1}. {content}")

        items_text = "\n\n".join(items)

        prompt = f"""Пользовательский вопрос: "{query}"

Ниже приведены фрагменты из базы знаний. Выбери {top_k} наиболее релевантных фрагмента, которые помогут ответить на вопрос.

Фрагменты:
{items_text}

Верни только номера выбранных фрагментов в формате JSON-списка, например: [1, 3]
Не добавляй пояснений."""

        try:
            response = await self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100,
            )
            content = response.choices[0].message.content.strip()
            # Ищем JSON-список
            start = content.find('[')
            end = content.rfind(']') + 1
            if start != -1 and end != -1:
                json_str = content[start:end]
                indices = json.loads(json_str)
                if isinstance(indices, list) and all(isinstance(i, int) for i in indices):
                    # возвращаем чанки в указанном порядке
                    selected = [candidates[i-1] for i in indices if 1 <= i <= len(candidates)]
                    return selected[:top_k]
        except Exception as e:
            logger.warning(f"Reranking failed: {e}", extra={"query": query})

        # Fallback: вернуть первые top_k по скору
        return candidates[:top_k]

    async def search_with_expansion(
        self,
        project_id: str,
        query: str,
        limit_per_query: int = 5,
        final_limit: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Основной метод: нормализация → генерация вариантов → поиск кандидатов → LLM-ранжирование → топ-k.
        """
        normalized = self._normalize(query)
        variants = await self._expand_query(normalized)
        if normalized not in variants:
            variants.insert(0, normalized)
        variants = list(dict.fromkeys(variants))

        logger.debug("Query variants", extra={"variants": variants})

        # Собираем кандидатов
        candidates_by_id = {}
        for variant in variants:
            chunk_list = await self._repo.search(
                project_id=project_id,
                query=variant,
                limit=limit_per_query,
                hybrid_fallback=True
            )
            for chunk in chunk_list:
                cid = chunk["id"]
                if cid not in candidates_by_id or chunk["score"] > candidates_by_id[cid]["score"]:
                    candidates_by_id[cid] = chunk

        # Превращаем в список и сортируем по скору (все кандидаты, не более 20)
        candidates = sorted(candidates_by_id.values(), key=lambda x: x["score"], reverse=True)[:20]

        if not candidates:
            return []

        # Ранжируем через LLM
        reranked = await self._rerank_candidates(normalized, candidates, top_k=final_limit)
        return reranked