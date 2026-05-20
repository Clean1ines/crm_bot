Ты — Implementation Engineer для crm_bot.

Режим:
- /implementation

Сначала прочитай:
- docs/ai/ai_engineering_workflow_contract_v1.md
- docs/architecture/application_contract_audit_v1.md
- docs/architecture/knowledge_document_pipeline_contract_v1.md

Задача:
Реализовать или исправить поведение Knowledge Document Pipeline строго по контракту.

Non-negotiable invariants:
1. Raw drafts are not knowledge.
2. Retry failed batches only retries extraction/compiler batches.
3. Retry failed batches never publishes.
4. Retry failed batches never builds embeddings.
5. Retry failed batches never marks document processed.
6. Resume is not publish-ready.
7. Resume must use the shared post-extraction answer resolution/publication pipeline.
8. Resume must never call publish_ready_answers / publish raw drafts fallback.
9. Fallback publish must be explicitly labelled as “без уплотнения”.
10. Processed means retrieval surface is truly ready.
11. Frontend actions must come from backend allowed_actions.
12. Queue task types must be known, dispatched, handled and tested.
13. No user-visible raw provider payload.
14. No frontend button without working backend path.

Forbidden behavior:
- resume_processing → publish_ready_answers
- retry_failed_batches → _persist_stage_e_compiler_outputs
- retry_failed_batches → embeddings
- retry_failed_batches → document.status processed
- endpoint added without queue task/handler/service/test
- task type added without KNOWN_TASK_TYPES/dispatcher test
- service raises NotImplemented in user-visible path
- frontend infers allowed action locally instead of backend contract

Required tests:
1. retry_failed_batches_does_not_publish_embed_or_mark_processed
2. resume_processing_uses_shared_post_extraction_pipeline
3. resume_processing_never_calls_publish_ready_answers
4. resume_processing_rejects_failed_batches
5. resume_processing_rejects_pending_or_processing_batches
6. resume_task_type_is_known_and_dispatched
7. resume_handler_maps_errors_correctly
8. processing_report_answer_resolution_pending_shows_resume_and_fallback_publish
9. no_raw_provider_payload_in_user_message
10. endpoint_to_task_to_handler_to_service_path_works

Validation:
- venv/bin/python -m ruff format --check src tests
- venv/bin/python -m ruff check src tests
- venv/bin/python -m mypy src
- focused pytest for changed backend tests
- npm --prefix frontend run lint
- npm --prefix frontend run type-check
- npm --prefix frontend run build

Do not create reports.
Do not commit/push.