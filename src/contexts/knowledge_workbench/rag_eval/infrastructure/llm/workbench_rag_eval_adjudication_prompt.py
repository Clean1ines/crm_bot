from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_adjudication_work import (
    ADJUDICATION_PROMPT_VERSION,
    WorkbenchRagEvalAdjudicationPlanningInput,
    build_adjudication_provider_messages,
)


PROMPT_FILE_NAME = "workbench_rag_eval_question_adjudication.ru.v1.txt"


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalAdjudicationPrompt:
    prompt_template: str
    prompt_version: str = ADJUDICATION_PROMPT_VERSION

    @classmethod
    def from_prompt_file(cls) -> WorkbenchRagEvalAdjudicationPrompt:
        prompt_path = (
            Path(__file__).resolve().parents[5] / "agent" / "prompts" / PROMPT_FILE_NAME
        )
        return cls(prompt_template=prompt_path.read_text(encoding="utf-8"))

    def provider_messages(
        self,
        item: WorkbenchRagEvalAdjudicationPlanningInput,
    ) -> tuple[dict[str, str], ...]:
        return tuple(
            dict(message)
            for message in build_adjudication_provider_messages(
                prompt_template=self.prompt_template,
                item=item,
            )
        )
