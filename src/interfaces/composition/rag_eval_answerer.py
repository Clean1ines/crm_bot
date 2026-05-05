from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from src.agent.nodes.response_generator import create_response_generator_node
from src.application.rag_eval.schemas import RagEvalChunk


RagEvalNode = Callable[[Mapping[str, object]], Awaitable[Mapping[str, object]]]
RagEvalNodeFactory = Callable[[], RagEvalNode]


class ProductionRagEvalAnswerer:
    """Composition adapter that calls the production response generation prompt path."""

    def __init__(
        self,
        *,
        node_factory: RagEvalNodeFactory | None = None,
    ) -> None:
        self._node_factory = node_factory or create_response_generator_node

    async def answer(
        self,
        *,
        project_id: str,
        question: str,
        evidence: list[RagEvalChunk],
    ) -> str:
        node = self._node_factory()
        state: dict[str, object] = {
            "project_id": project_id,
            "decision": "RESPOND_KB",
            "user_input": question,
            "conversation_summary": None,
            "history": [],
            "knowledge_chunks": [_prompt_chunk(chunk) for chunk in evidence],
            "user_memory": None,
            "dialog_state": None,
            "features": {},
            "project_configuration": None,
        }
        result = await node(state)
        return str(result.get("response_text") or "").strip()


def _prompt_chunk(chunk: RagEvalChunk) -> dict[str, object]:
    return {
        "id": chunk.id,
        "chunk_id": chunk.id,
        "content": chunk.content,
        "text": chunk.content,
        "source": chunk.source,
        "document_id": chunk.document_id,
        "score": chunk.metadata.get("score"),
        "metadata": chunk.metadata,
    }
