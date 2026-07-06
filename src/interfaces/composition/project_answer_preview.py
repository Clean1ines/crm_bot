from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import asyncpg

from src.agent.nodes.response_generator import (
    build_answer_preview_prompt,
    complete_response_prompt,
)
from src.application.orchestration.project_runtime_loader import ProjectRuntimeLoader
from src.application.ports.logger_port import NullLogger
from src.application.services.project_answer_preview_service import (
    ProjectAnswerPreviewService,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.llm.rag_service import RAGService


@dataclass(frozen=True, slots=True)
class ResponseGeneratorAnswerCompletion:
    async def complete(
        self,
        prompt: str,
        *,
        project_configuration: Mapping[str, object] | None = None,
    ) -> str:
        return await complete_response_prompt(
            prompt,
            project_configuration=project_configuration,
        )


def make_project_answer_preview_service(
    pool: asyncpg.Pool,
) -> ProjectAnswerPreviewService:
    knowledge_repository = KnowledgeRepository(pool)
    return ProjectAnswerPreviewService(
        rag_service=RAGService(knowledge_repository),
        runtime_loader=ProjectRuntimeLoader(
            projects=ProjectRepository(pool),
            logger=NullLogger(),
        ),
        prompt_builder=build_answer_preview_prompt,
        answer_completion=ResponseGeneratorAnswerCompletion(),
    )
