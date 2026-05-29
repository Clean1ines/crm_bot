from __future__ import annotations

from typing import cast

from src.application.services.knowledge_ingestion_service import (
    JsonObject,
    KnowledgeIngestionRepositoryFactoryPort,
    KnowledgePreprocessorFactoryPort,
    LoggerPort,
    MODE_PRICE_LIST,
    ModelUsageEventCreate,
    ModelUsageRepositoryFactoryPort,
    _answer_resolution_cases_from_entries,
    _answer_resolution_decision_is_too_noisy,
    _answer_resolution_decisions_with_case_candidate_ids,
    _cleanup_answer_resolution_text_with_metrics,
    _compose_retighten_existing_document_plans,
    _deterministic_retighten_existing_document_plan,
    _existing_project_titles_for_answer_resolution,
    _limit_compiled_text,
    _preprocessing_entry_from_canonical_entry,
    _reject_noisy_answer_resolution_decisions,
    _retighten_archived_entry_ids,
    _retighten_existing_document_plan,
    _retighten_updated_canonical_entries,
)


class KnowledgeRetightenService:
    def __init__(self, pool: object) -> None:
        self.pool = pool

    async def retighten_processed_document(
        self,
        *,
        project_id: str,
        document_id: str,
        file_name: str,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort,
        logger: LoggerPort,
    ) -> JsonObject:
        repo = knowledge_repo_factory(self.pool)
        usage_repo = model_usage_repo_factory(self.pool)
        current_entries = await repo.list_document_runtime_entries(
            project_id=project_id,
            document_id=document_id,
        )

        metrics: JsonObject = {
            "stage": "answer_resolution_existing_document",
            "source": "kcd_stage_k8_3",
            "entry_count_before": len(current_entries),
            "source_compiler_rerun": False,
        }

        if len(current_entries) < 2:
            metrics["status"] = "skipped"
            metrics["reason"] = "document_has_less_than_two_runtime_entries"
            metrics["entry_count_after"] = len(current_entries)
            return metrics

        preprocessing_entries = tuple(
            _preprocessing_entry_from_canonical_entry(entry)
            for entry in current_entries
        )

        deterministic_result = _deterministic_retighten_existing_document_plan(
            preprocessing_entries
        )
        deterministic_plan = deterministic_result.plan
        preprocessing_entries = deterministic_plan.entries
        metrics.update(deterministic_result.metrics)

        groups = _answer_resolution_cases_from_entries(preprocessing_entries)
        metrics["candidate_case_count"] = len(groups)
        metrics["llm_candidate_case_count"] = len(groups)

        if not groups:
            metrics["status"] = (
                "completed" if deterministic_plan.removed_source_indexes else "skipped"
            )
            metrics["reason"] = (
                "deterministic_cleanup_applied_without_llm_groups"
                if deterministic_plan.removed_source_indexes
                else "no_answer_resolution_cases"
            )
            metrics["entry_count_after"] = len(deterministic_plan.entries)
            metrics["collapsed_entry_count"] = len(
                deterministic_plan.removed_source_indexes
            )
            metrics["llm_call_count"] = 0
            metrics["usage_event_count"] = 0
            if not deterministic_plan.removed_source_indexes:
                return metrics

            result = await repo.apply_document_answer_resolution_retightening(
                project_id=project_id,
                document_id=document_id,
                updated_entries=_retighten_updated_canonical_entries(
                    plan=deterministic_plan,
                    current_entries=current_entries,
                ),
                archived_entry_ids=_retighten_archived_entry_ids(
                    plan=deterministic_plan,
                    current_entries=current_entries,
                ),
                metrics=metrics,
            )
            logger.info(
                "Knowledge document deterministic retighten completed",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "entry_count_before": len(current_entries),
                    "entry_count_after": len(deterministic_plan.entries),
                    "collapsed_entry_count": len(
                        deterministic_plan.removed_source_indexes
                    ),
                },
            )
            return result

        preprocessor = preprocessor_factory()
        existing_project_titles = await _existing_project_titles_for_answer_resolution(
            repo=repo,
            project_id=project_id,
            document_id=document_id,
        )
        llm_call_count = 0
        usage_event_count = 0
        try:
            first_execution = await preprocessor.resolve_answer_cases(
                mode=MODE_PRICE_LIST,
                file_name=file_name,
                cases=(groups[0],),
                existing_project_titles=existing_project_titles,
            )
            llm_call_count = 1
            decisions = _answer_resolution_decisions_with_case_candidate_ids(
                answer_case=groups[0],
                decisions=first_execution.result.decisions,
            )
            model = first_execution.result.model
            prompt_version = first_execution.result.prompt_version
            if first_execution.usage is not None:
                await usage_repo.record_event(
                    ModelUsageEventCreate.from_measurement(
                        project_id=project_id,
                        source="knowledge_preprocessing",
                        measurement=first_execution.usage,
                        document_id=document_id,
                    )
                )
                usage_event_count += 1

            for group in groups[1:]:
                execution = await preprocessor.resolve_answer_cases(
                    mode=MODE_PRICE_LIST,
                    file_name=file_name,
                    cases=(group,),
                    existing_project_titles=existing_project_titles,
                )
                llm_call_count += 1
                decisions = (
                    *decisions,
                    *_answer_resolution_decisions_with_case_candidate_ids(
                        answer_case=group,
                        decisions=execution.result.decisions,
                    ),
                )
                model = execution.result.model
                prompt_version = execution.result.prompt_version
                if execution.usage is not None:
                    await usage_repo.record_event(
                        ModelUsageEventCreate.from_measurement(
                            project_id=project_id,
                            source="knowledge_preprocessing",
                            measurement=execution.usage,
                            document_id=document_id,
                        )
                    )
                    usage_event_count += 1
        except Exception as exc:
            metrics["status"] = "skipped"
            metrics["reason"] = "answer_resolution_failed"
            metrics["error_type"] = type(exc).__name__
            metrics["error"] = str(exc)[:240]
            metrics["entry_count_after"] = len(current_entries)
            metrics["llm_call_count"] = llm_call_count
            metrics["usage_event_count"] = usage_event_count
            logger.warning(
                "Knowledge document answer resolution retighten skipped after LLM failure",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "candidate_case_count": len(groups),
                    "llm_call_count": llm_call_count,
                    "error_type": type(exc).__name__,
                },
            )
            if not deterministic_plan.removed_source_indexes:
                return metrics

            metrics["status"] = "completed_with_warnings"
            metrics["reason"] = "answer_resolution_failed_after_deterministic_cleanup"
            metrics["entry_count_after"] = len(deterministic_plan.entries)
            metrics["collapsed_entry_count"] = len(
                deterministic_plan.removed_source_indexes
            )
            result = await repo.apply_document_answer_resolution_retightening(
                project_id=project_id,
                document_id=document_id,
                updated_entries=_retighten_updated_canonical_entries(
                    plan=deterministic_plan,
                    current_entries=current_entries,
                ),
                archived_entry_ids=_retighten_archived_entry_ids(
                    plan=deterministic_plan,
                    current_entries=current_entries,
                ),
                metrics=metrics,
            )
            return result

        rejected_noisy_resolved_answer_count = sum(
            1
            for decision in decisions
            if _answer_resolution_decision_is_too_noisy(decision)
        )
        rejected_noisy_resolution_examples: tuple[JsonObject, ...] = tuple(
            cast(
                JsonObject,
                {
                    "group_id": decision.group_id,
                    "candidate_ids": tuple(decision.candidate_ids),
                    "canonical_answer_preview": _limit_compiled_text(
                        decision.canonical_answer,
                        max_chars=240,
                    ),
                    "cleanup_original_unit_count": (
                        cleanup := _cleanup_answer_resolution_text_with_metrics(
                            decision.canonical_answer
                        )
                    ).original_unit_count,
                    "cleanup_removed_unit_count": cleanup.removed_unit_count,
                },
            )
            for decision in decisions
            if _answer_resolution_decision_is_too_noisy(decision)
        )[:5]
        decisions = _reject_noisy_answer_resolution_decisions(decisions)

        llm_plan = _retighten_existing_document_plan(
            entries=preprocessing_entries,
            decisions=decisions,
        )
        plan = _compose_retighten_existing_document_plans(
            base=deterministic_plan,
            overlay=llm_plan,
        )

        cleanup_results = tuple(
            _cleanup_answer_resolution_text_with_metrics(decision.canonical_answer)
            for decision in decisions
            if decision.is_merge and decision.canonical_answer
        )
        metrics["retighten_cleanup_original_unit_count"] = sum(
            result.original_unit_count for result in cleanup_results
        )
        metrics["retighten_cleanup_removed_unit_count"] = sum(
            result.removed_unit_count for result in cleanup_results
        )
        metrics["rejected_noisy_resolved_answer_count"] = (
            rejected_noisy_resolved_answer_count
        )
        if rejected_noisy_resolution_examples:
            metrics["rejected_noisy_resolution_examples"] = list(
                rejected_noisy_resolution_examples
            )
        metrics["decision_count"] = len(decisions)
        metrics["resolved_answer_count"] = sum(
            1 for decision in decisions if decision.is_merge
        )
        metrics["collapsed_entry_count"] = len(plan.removed_source_indexes)
        metrics["deterministic_entry_count_after"] = len(deterministic_plan.entries)
        metrics["llm_resolved_entry_count"] = max(
            0,
            len(deterministic_plan.entries) - len(plan.entries),
        )
        metrics["entry_count_after"] = len(plan.entries)
        metrics["llm_call_count"] = llm_call_count
        metrics["usage_event_count"] = usage_event_count
        metrics["model"] = model
        metrics["prompt_version"] = prompt_version

        if not plan.removed_source_indexes:
            metrics["status"] = "completed"
            metrics["reason"] = "llm_kept_suspects_separate"
            return metrics

        result = await repo.apply_document_answer_resolution_retightening(
            project_id=project_id,
            document_id=document_id,
            updated_entries=_retighten_updated_canonical_entries(
                plan=plan,
                current_entries=current_entries,
            ),
            archived_entry_ids=_retighten_archived_entry_ids(
                plan=plan,
                current_entries=current_entries,
            ),
            metrics=metrics,
        )

        logger.info(
            "Knowledge document answer resolution retighten completed",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "entry_count_before": len(current_entries),
                "entry_count_after": len(plan.entries),
                "collapsed_entry_count": len(plan.removed_source_indexes),
            },
        )
        return result
