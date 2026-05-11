from __future__ import annotations

from src.domain.project_plane.knowledge_chunks import KnowledgeChunkDraft


def build_knowledge_embedding_text(chunk: KnowledgeChunkDraft) -> str:
    parts: list[str] = []

    title = chunk.effective_title
    if title:
        parts.append(f"Title: {title}")

    excerpt = chunk.effective_excerpt
    if excerpt:
        parts.append(f"Source excerpt: {excerpt}")

    if chunk.questions:
        parts.append("Questions: " + "; ".join(chunk.questions))

    if chunk.synonyms:
        parts.append("Synonyms: " + ", ".join(chunk.synonyms))

    if chunk.tags:
        parts.append("Tags: " + ", ".join(chunk.tags))

    parts.append(f"Content: {chunk.content}")

    return "\n".join(part for part in parts if part.strip())
