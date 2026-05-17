from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from src.application.rag_eval.failure_classification import KnowledgeEditAction
from src.application.rag_eval.review_schemas import RagEvalApplyAcceptedSummary
from src.application.rag_eval.schemas import (
    RagEvalEvidenceEntry,
    RagEvalResult,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue


class RagEvalReviewRepositoryPort(Protocol):
    async def get_run_summary(self, *, run_id: str) -> JsonObject | None: ...

    async def get_latest_run_summary(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> JsonObject | None: ...

    async def load_run_results(self, *, run_id: str) -> list[RagEvalResult]: ...

    async def load_document_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[RagEvalEvidenceEntry]: ...

    async def load_question_reviews(self, *, run_id: str) -> dict[str, JsonObject]: ...

    async def upsert_question_review(
        self,
        *,
        question_id: str,
        status: str,
        reason: str,
        reviewed_by: str,
    ) -> JsonObject | None: ...

    async def edit_question_review(
        self,
        *,
        question_id: str,
        question: str,
        reviewed_by: str,
    ) -> JsonObject | None: ...

    async def load_accepted_question_reviews(
        self, *, run_id: str
    ) -> list[JsonObject]: ...

    async def mark_question_reviews_applied(
        self,
        *,
        review_ids: list[str],
        reviewed_by: str,
    ) -> None: ...


class KnowledgeReviewEditRepositoryPort(Protocol):
    async def create_or_get_knowledge_edit_action(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        source_result_id: str,
        source_run_id: str,
        source_question_id: str,
        action_index: int,
        actor_user_id: str,
        action_type: str,
        target_entry_id: str | None,
        reason: str,
        payload: JsonObject,
    ) -> JsonObject: ...

    async def attach_question_to_entry(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
        question: str,
        reason: str,
        actor_user_id: str,
    ) -> None: ...

    async def rebuild_entry_embedding(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
    ) -> None: ...

    async def mark_knowledge_edit_action_applied(
        self,
        action_id: str,
        *,
        result_payload: JsonObject | None = None,
    ) -> None: ...


class RagEvalReviewQueuePort(Protocol):
    async def enqueue(
        self,
        task_type: str,
        payload: JsonObject | None = None,
        max_attempts: int = 3,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class RagEvalReviewService:
    review_repo: RagEvalReviewRepositoryPort
    knowledge_repo: KnowledgeReviewEditRepositoryPort | None = None
    queue_repo: RagEvalReviewQueuePort | None = None
    rerun_eval_task_type: str = "run_full_rag_eval"

    async def build_run_review(self, *, run_id: str) -> dict[str, object] | None:
        run = await self.review_repo.get_run_summary(run_id=run_id)
        if run is None:
            return None
        return await self._build_review_for_run(run=run)

    async def build_latest_review(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> dict[str, object] | None:
        run = await self.review_repo.get_latest_run_summary(
            project_id=project_id,
            document_id=document_id,
        )
        if run is None:
            return None
        return await self._build_review_for_run(run=run)

    async def review_question(
        self,
        *,
        question_id: str,
        status: str,
        reason: str,
        reviewed_by: str,
    ) -> JsonObject | None:
        return await self.review_repo.upsert_question_review(
            question_id=question_id,
            status=status,
            reason=reason,
            reviewed_by=reviewed_by,
        )

    async def edit_question(
        self,
        *,
        question_id: str,
        question: str,
        reviewed_by: str,
    ) -> JsonObject | None:
        return await self.review_repo.edit_question_review(
            question_id=question_id,
            question=" ".join(question.split()),
            reviewed_by=reviewed_by,
        )

    async def apply_accepted_questions(
        self,
        *,
        run_id: str,
        actor_user_id: str,
    ) -> RagEvalApplyAcceptedSummary:
        if self.knowledge_repo is None or self.queue_repo is None:
            raise ValueError(
                "Apply accepted questions requires knowledge and queue repositories"
            )

        run = await self.review_repo.get_run_summary(run_id=run_id)
        if run is None:
            raise ValueError(f"RAG eval run not found: {run_id}")

        project_id = _required_text(run.get("project_id"), "project_id")
        document_id = _required_text(run.get("document_id"), "document_id")
        accepted_reviews = await self.review_repo.load_accepted_question_reviews(
            run_id=run_id,
        )
        if not accepted_reviews:
            return {
                "ok": True,
                "run_id": run_id,
                "applied_questions": 0,
                "failed_questions": 0,
                "failures": [],
                "queued_rerun_job_id": None,
            }

        applied_review_ids: list[str] = []
        failures: list[JsonObject] = []

        for index, review in enumerate(accepted_reviews):
            review_id = _required_text(review.get("review_id"), "review_id")
            result_id = _required_text(review.get("result_id"), "result_id")
            question_id = _required_text(review.get("question_id"), "question_id")
            target_document_id = _required_text(
                review.get("document_id"), "document_id"
            )
            target_entry_id = _required_text(
                review.get("target_entry_id"),
                "target_entry_id",
            )
            question = _required_text(review.get("question"), "question")
            action_id = f"rqapply_{_safe_id(review_id)}_{uuid4().hex[:8]}"

            try:
                stored = await self.knowledge_repo.create_or_get_knowledge_edit_action(
                    action_id=action_id,
                    project_id=project_id,
                    document_id=target_document_id,
                    source_result_id=result_id,
                    source_run_id=run_id,
                    source_question_id=question_id,
                    action_index=1000 + index,
                    actor_user_id=actor_user_id,
                    action_type="attach_question_to_entry",
                    target_entry_id=target_entry_id,
                    reason="Accepted from RAG Eval Review Console.",
                    payload={"question": question, "review_id": review_id},
                )
                stored_action_id = _required_text(stored.get("id"), "action_id")
                if str(stored.get("status") or "") != "applied":
                    await self.knowledge_repo.attach_question_to_entry(
                        action_id=stored_action_id,
                        project_id=project_id,
                        document_id=target_document_id,
                        target_entry_id=target_entry_id,
                        question=question,
                        reason="Accepted from RAG Eval Review Console.",
                        actor_user_id=actor_user_id,
                    )
                    await self.knowledge_repo.rebuild_entry_embedding(
                        action_id=stored_action_id,
                        project_id=project_id,
                        document_id=target_document_id,
                        target_entry_id=target_entry_id,
                    )
                    await self.knowledge_repo.mark_knowledge_edit_action_applied(
                        stored_action_id,
                        result_payload={
                            "question_id": question_id,
                            "review_id": review_id,
                        },
                    )
                applied_review_ids.append(review_id)
            except Exception as exc:
                failures.append(
                    {
                        "review_id": review_id,
                        "question_id": question_id,
                        "error": str(exc),
                    }
                )

        await self.review_repo.mark_question_reviews_applied(
            review_ids=applied_review_ids,
            reviewed_by=actor_user_id,
        )

        queued_rerun_job_id = None
        if applied_review_ids:
            queued_rerun_job_id = await self.queue_repo.enqueue(
                self.rerun_eval_task_type,
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "requested_by": actor_user_id,
                    "mode": "full_document",
                    "eval_mode": "retrieval_eval",
                    "retrieval_limit": 5,
                    "source": "rag_eval_review_console",
                    "source_run_id": run_id,
                },
                max_attempts=20,
            )

        return {
            "ok": True,
            "run_id": run_id,
            "applied_questions": len(applied_review_ids),
            "failed_questions": len(failures),
            "failures": failures,
            "queued_rerun_job_id": queued_rerun_job_id,
        }

    async def _build_review_for_run(self, *, run: JsonObject) -> dict[str, object]:
        run_id = _required_text(run.get("id"), "run_id")
        project_id = _required_text(run.get("project_id"), "project_id")
        document_id = _required_text(run.get("document_id"), "document_id")
        results = await self.review_repo.load_run_results(run_id=run_id)
        entries = await self.review_repo.load_document_entries(
            project_id=project_id,
            document_id=document_id,
        )
        reviews = await self.review_repo.load_question_reviews(run_id=run_id)
        return build_review_payload(
            run=run,
            results=results,
            entries=entries,
            reviews=reviews,
        )


def build_review_payload(
    *,
    run: JsonObject,
    results: list[RagEvalResult],
    entries: list[RagEvalEvidenceEntry],
    reviews: dict[str, JsonObject],
) -> dict[str, object]:
    entry_map = {entry.id: entry for entry in entries}
    groups_by_entry: dict[str, dict[str, object]] = {}
    reliable = weak = confused = missing = improvements = 0
    problem_type_counts: dict[str, int] = {}

    for result in results:
        expected_id = _expected_entry_id(result)
        entry = entry_map.get(expected_id)
        group = groups_by_entry.setdefault(
            expected_id,
            _empty_review_group(expected_id, entry),
        )
        status_key = _review_status_from_result(result)
        if status_key == "reliable":
            reliable += 1
        elif status_key == "weak":
            weak += 1
        elif status_key == "confused":
            confused += 1
        else:
            missing += 1
        if result.proposed_actions:
            improvements += 1

        q_type = result.question.question_type
        if status_key != "reliable":
            problem_type_counts[q_type] = problem_type_counts.get(q_type, 0) + 1

        retrieved_ids = _retrieved_entry_ids(result)
        retrieved_entries = [
            {
                "id": retrieved_id,
                "title": str(entry_map[retrieved_id].metadata.get("title") or "")
                if retrieved_id in entry_map
                else retrieved_id,
                "content": entry_map[retrieved_id].content
                if retrieved_id in entry_map
                else "",
            }
            for retrieved_id in retrieved_ids[:5]
        ]
        review = reviews.get(result.question_id)
        question_payload: dict[str, object] = {
            "result_id": result.id,
            "question_id": result.question_id,
            "question": result.question.question,
            "effective_question": _effective_question(result, review),
            "question_type": result.question.question_type,
            "question_type_label": _question_type_label(result.question.question_type),
            "retrieval_status": status_key,
            "retrieval_status_label": _review_status_label(status_key),
            "expected_entry_ids": list(result.question.expected_entry_ids),
            "retrieved_entry_ids": retrieved_ids,
            "retrieved_entries": retrieved_entries,
            "score": result.score,
            "top1_hit": result.top1_hit,
            "top3_hit": result.top3_hit,
            "top5_hit": result.top5_hit,
            "expected_entry_found": result.expected_entry_found,
            "wrong_entry_top1": result.wrong_entry_top1,
            "fallback_generated": result.question.source != "llm_generated",
            "review": review or {"status": "candidate"},
            "why_it_matters": _why_question_matters(status_key),
            "proposed_improvements": _human_action_summary(result),
            "diagnostics": {
                "classification": _json_value(result.classification.to_json())
                if result.classification is not None
                else None,
                "proposed_actions": [
                    _actionable_action_summary(action)
                    for action in result.proposed_actions
                ],
                "latency_ms": result.latency_ms,
                "notes": result.notes,
            },
        }
        questions = group["questions"]
        if isinstance(questions, list):
            questions.append(question_payload)
        group["question_count"] = _object_int(group.get("question_count")) + 1
        if status_key != "reliable":
            group["problem_count"] = _object_int(group.get("problem_count")) + 1
        if result.proposed_actions:
            group["improvement_count"] = _object_int(group.get("improvement_count")) + 1

    for group in groups_by_entry.values():
        problem_count = _object_int(group.get("problem_count"))
        question_count = _object_int(group.get("question_count"))
        group["status"] = _group_status(
            problem_count=problem_count,
            question_count=question_count,
        )
        group["review_status"] = "ready_for_review"
        group["issue_summary"] = _group_issue_summary(group)
        group["proposed_improvements"] = _group_proposals(group)

    groups = sorted(
        groups_by_entry.values(),
        key=lambda item: (
            _object_int(item.get("problem_count")),
            _object_int(item.get("improvement_count")),
            _object_int(item.get("question_count")),
        ),
        reverse=True,
    )
    total = len(results)
    problem_total = weak + confused + missing
    score = round((reliable / total) * 100, 1) if total else 0.0
    good_fragments = sum(
        1
        for group in groups
        if _object_int(group.get("problem_count")) == 0
        and _object_int(group.get("question_count")) > 0
    )
    unstable_fragments = sum(
        1
        for group in groups
        if 0
        < _object_int(group.get("problem_count"))
        < _object_int(group.get("question_count"))
    )
    bad_fragments = sum(
        1
        for group in groups
        if _object_int(group.get("problem_count"))
        >= _object_int(group.get("question_count"))
        and _object_int(group.get("question_count")) > 0
    )

    return {
        "run": run,
        "summary": {
            "title": "Проверка поиска по документу",
            "score": score,
            "readiness": _readiness_label(score),
            "fragments_total": len(groups),
            "questions_total": total,
            "reliable_questions": reliable,
            "weak_questions": weak,
            "confused_questions": confused,
            "missing_questions": missing,
            "problem_questions": problem_total,
            "improvements_total": improvements,
            "good_fragments": good_fragments,
            "unstable_fragments": unstable_fragments,
            "bad_fragments": bad_fragments,
            "human_summary": _human_summary(
                score=score,
                problem_total=problem_total,
                groups=groups,
                problem_type_counts=problem_type_counts,
            ),
        },
        "problem_map": {
            "most_problematic_fragments": groups[:5],
            "best_fragments": [
                group
                for group in groups
                if _object_int(group.get("problem_count")) == 0
            ][:5],
            "problem_types": [
                {"type": key, "label": _question_type_label(key), "count": count}
                for key, count in sorted(
                    problem_type_counts.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ],
        },
        "groups": groups,
        "filters": {
            "statuses": [
                "all",
                "problematic",
                "wrong_top1",
                "missing",
                "good_candidates",
                "fallback",
                "typo_short_vague",
            ],
            "sorts": [
                "most_problematic",
                "most_questions",
                "worst_confusion",
                "best_candidates",
            ],
        },
        "diagnostics": {
            "run_id": str(run["id"]),
            "dataset_id": str(run["dataset_id"]),
            "retriever_version": str(run.get("retriever_version") or ""),
            "reranker_version": str(run.get("reranker_version") or ""),
            "generator_model": str(run.get("generator_model") or ""),
        },
    }


def _json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return str(value)


def _object_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"RAG eval review is missing {field_name}")
    return text


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)[:80]


def _expected_entry_id(result: RagEvalResult) -> str:
    return (
        result.question.expected_entry_ids[0]
        if result.question.expected_entry_ids
        else "unassigned"
    )


def _retrieved_entry_ids(result: RagEvalResult) -> list[str]:
    raw = result.judge_json.get("retrieved_entry_ids")
    from_judge = [str(item) for item in _json_list(raw) if str(item).strip()]
    return from_judge or [entry.id for entry in result.retrieved_entries]


def _effective_question(result: RagEvalResult, review: JsonObject | None) -> str:
    if review is None:
        return result.question.question
    edited = str(review.get("edited_question") or "").strip()
    return edited or result.question.question


def _review_status_from_result(result: RagEvalResult) -> str:
    if result.top1_hit:
        return "reliable"
    if result.expected_entry_found:
        return "weak"
    if result.wrong_entry_top1:
        return "confused"
    return "missing"


def _review_status_label(status: str) -> str:
    labels = {
        "reliable": "Надёжно находится",
        "weak": "Находится, но слабо",
        "confused": "Путается с другим фрагментом",
        "missing": "Не находится",
    }
    return labels.get(status, "Нужна проверка")


def _readiness_label(score: float) -> str:
    if score >= 90:
        return "Готово к использованию"
    if score >= 80:
        return "Почти готово"
    if score >= 60:
        return "Требует улучшений"
    return "Проблемная база"


def _question_type_label(value: str) -> str:
    labels = {
        "direct": "прямой вопрос",
        "paraphrase": "переформулировка",
        "short_vague": "короткий/vague вопрос",
        "similar_wrong": "похожий фрагмент",
        "unknown": "неизвестный вопрос",
        "risky": "рискованный вопрос",
        "contradiction": "противоречие",
    }
    return labels.get(value, value or "вопрос")


def _actionable_action_payload(payload: Mapping[str, object]) -> JsonObject:
    question = payload.get("question")
    if isinstance(question, str) and question.strip():
        return {"question": question.strip()}
    return {}


def _actionable_action_summary(action: KnowledgeEditAction) -> JsonObject:
    summary: JsonObject = {
        "action_type": action.action_type.value,
        "reason": action.reason,
        "payload": _actionable_action_payload(action.payload),
    }
    if action.target_entry_id:
        summary["target_entry_id"] = action.target_entry_id
    return summary


def _human_action_summary(result: RagEvalResult) -> list[str]:
    if not result.proposed_actions:
        if result.top1_hit:
            return ["Изменения не требуются."]
        return ["Проверить формулировку и решить, стоит ли добавить её к фрагменту."]

    summaries: list[str] = []
    for action in result.proposed_actions:
        if action.action_type.value == "attach_question_to_entry":
            question = str(
                action.payload.get("question") or result.question.question
            ).strip()
            summaries.append(f"Добавить вопрос «{question}» к ожидаемому фрагменту.")
        elif action.action_type.value == "rebuild_embedding":
            summaries.append(
                "Пересобрать embedding этого фрагмента после изменения вопросов."
            )
        elif action.action_type.value == "rerun_eval":
            summaries.append(
                "Запустить повторную проверку, чтобы подтвердить улучшение."
            )
        elif action.action_type.value == "create_entry_from_failure":
            summaries.append(
                "Разобрать вручную: возможно, нужна новая запись базы знаний."
            )
    return summaries


def _empty_review_group(
    entry_id: str, entry: RagEvalEvidenceEntry | None
) -> dict[str, object]:
    metadata = entry.metadata if entry is not None else {}
    return {
        "entry_id": entry_id,
        "title": str(metadata.get("title") or f"Фрагмент {entry_id}"),
        "content": entry.content if entry is not None else "",
        "existing_questions": [
            str(item)
            for item in _json_list(metadata.get("questions"))
            if str(item).strip()
        ],
        "question_count": 0,
        "problem_count": 0,
        "improvement_count": 0,
        "status": "Нужна проверка",
        "review_status": "ready_for_review",
        "issue_summary": "",
        "questions": [],
        "proposed_improvements": [],
    }


def _group_status(*, problem_count: int, question_count: int) -> str:
    if question_count == 0 or problem_count == 0:
        return "Надёжно находится"
    if problem_count >= question_count:
        return "Почти не находится"
    return "Требует улучшений"


def _group_issue_summary(group: Mapping[str, object]) -> str:
    problem_count = _object_int(group.get("problem_count"))
    question_count = _object_int(group.get("question_count"))
    if problem_count == 0:
        return f"{question_count}/{question_count} вопросов нашли правильный фрагмент."
    return f"{problem_count} из {question_count} вопросов показали проблему поиска."


def _group_proposals(group: Mapping[str, object]) -> list[str]:
    questions = group.get("questions")
    if not isinstance(questions, list):
        return []
    add_count = sum(
        1
        for item in questions
        if isinstance(item, dict) and item.get("retrieval_status") != "reliable"
    )
    if add_count <= 0:
        return ["Изменения не требуются."]
    return [
        f"Рассмотреть {add_count} вопросов-кандидатов для добавления к фрагменту.",
        "После принятия вопросов пересобрать embedding фрагмента.",
    ]


def _why_question_matters(status_key: str) -> str:
    if status_key == "reliable":
        return (
            "Такой пользовательский вопрос уже уверенно ведёт к правильному фрагменту."
        )
    if status_key == "weak":
        return "Правильный фрагмент найден, но не первым: пользователь может получить менее точный ответ."
    if status_key == "confused":
        return "Поиск первым выбрал другой фрагмент, поэтому похожие знания конкурируют между собой."
    return "Правильный фрагмент не попал в результаты поиска по этой формулировке."


def _human_summary(
    *,
    score: float,
    problem_total: int,
    groups: list[dict[str, object]],
    problem_type_counts: dict[str, int],
) -> str:
    if problem_total == 0:
        return "Поиск по документу работает стабильно: проверочные вопросы находят ожидаемые фрагменты."
    leading_type = next(iter(problem_type_counts), "")
    leading_label = (
        _question_type_label(leading_type) if leading_type else "сложные формулировки"
    )
    problematic_titles = [
        str(group.get("title") or "фрагмент")
        for group in groups
        if _object_int(group.get("problem_count")) > 0
    ][:2]
    fragments_text = (
        ", ".join(problematic_titles) if problematic_titles else "несколько фрагментов"
    )
    if score >= 80:
        return f"Поиск в целом работает, но требует улучшений: чаще всего проседают {leading_label}, особенно в фрагментах {fragments_text}."
    return f"База пока не готова к публикации: {problem_total} вопросов показали проблемы, основной риск — {leading_label}."
