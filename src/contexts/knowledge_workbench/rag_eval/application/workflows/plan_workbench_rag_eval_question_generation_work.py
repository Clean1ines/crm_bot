from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
)
from src.contexts.llm_runtime.application.capacity.llm_capacity_estimate_payload import (
    build_llm_capacity_estimate_payload,
)
from src.contexts.llm_runtime.domain.entities.model_profile import (
    ModelProfile,
)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerationWorkPlanner:
    prompt_version: str
    generation_model_profile: ModelProfile
    planned_output_tokens: int = 1200

    def plan(
        self,
        *,
        workflow_run_id: str,
        project_id: str,
        entries: tuple[PublishedWorkbenchRetrievalResult, ...],
        provider_messages_by_runtime_entry_id: Mapping[
            str,
            tuple[Mapping[str, str], ...],
        ],
    ) -> tuple[WorkItemSchedulePlan, ...]:
        _require_non_empty_text(workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(project_id, field_name="project_id")
        _require_non_empty_text(self.prompt_version, field_name="prompt_version")
        if not isinstance(self.generation_model_profile, ModelProfile):
            raise TypeError("generation_model_profile must be ModelProfile")
        return tuple(
            self._plan_entry(
                workflow_run_id=workflow_run_id,
                project_id=project_id,
                entry=entry,
                provider_messages=provider_messages_by_runtime_entry_id[
                    entry.runtime_entry_id
                ],
                generation_model_profile=self.generation_model_profile,
                entry_index=index,
            )
            for index, entry in enumerate(entries)
        )

    def _plan_entry(
        self,
        *,
        workflow_run_id: str,
        project_id: str,
        entry: PublishedWorkbenchRetrievalResult,
        provider_messages: tuple[Mapping[str, str], ...],
        generation_model_profile: ModelProfile,
        entry_index: int,
    ) -> WorkItemSchedulePlan:
        work_item_id = _stable_id(
            "workbench-rag-eval-qgen-work",
            workflow_run_id,
            entry.runtime_entry_id,
        )
        payload = {
            "workflow_run_id": workflow_run_id,
            "project_id": project_id,
            "runtime_entry_id": entry.runtime_entry_id,
            "expected_fact_id": entry.fact_id,
            "publication_id": entry.publication_id,
            "source_document_ref": entry.source_document_ref,
            "claim": entry.claim,
            "possible_questions": list(entry.possible_questions),
            "exclusion_scope": entry.exclusion_scope,
            "evidence_block": entry.evidence_block,
            "source_claim_refs": list(entry.source_claim_refs),
            "embedding_text": entry.embedding_text,
            "prompt_version": self.prompt_version,
            "expected_question_count": 10,
            "entry_index": entry_index,
            "provider_messages": [dict(message) for message in provider_messages],
            "llm_capacity_estimate": _capacity_estimate(
                provider_messages=provider_messages,
                planned_output_tokens=self.planned_output_tokens,
                model_profile=generation_model_profile,
            ),
        }
        return WorkItemSchedulePlan(
            work_item_id=work_item_id,
            work_kind=WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
            idempotency_key=work_item_id,
            payload=payload,
        )


def _capacity_estimate(
    *,
    provider_messages: tuple[Mapping[str, str], ...],
    planned_output_tokens: int,
    model_profile: ModelProfile,
) -> dict[str, object]:
    prompt_text = "\n".join(
        str(message.get("content", "")) for message in provider_messages
    )
    input_tokens = max(1, len(prompt_text) // 4)
    return build_llm_capacity_estimate_payload(
        model_profile=model_profile,
        phase="question_generation",
        operation="prepare_workbench_rag_eval_question_generation",
        estimator="provider_message_char_div_4",
        prompt_tokens=input_tokens,
        artifact_tokens=0,
        input_tokens=input_tokens,
        planned_output_tokens=planned_output_tokens,
        safety_gap_tokens=0,
    )


def _stable_id(*parts: str) -> str:
    return sha256(":".join(parts).encode("utf-8")).hexdigest()


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
