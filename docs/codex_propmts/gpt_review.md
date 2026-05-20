Проверь ветку <BRANCH_NAME> в режиме /adversarial-review.

Base branch:
main

Контракт:
- docs/ai/ai_engineering_workflow_contract_v1.md
- docs/architecture/application_contract_audit_v1.md
- docs/architecture/knowledge_document_pipeline_contract_v1.md

Проверь именно:
1. Не нарушены ли non-negotiable invariants.
2. Нет ли fake command behavior.
3. Нет ли user-visible action без backend path.
4. Нет ли endpoint → wrong task.
5. Все ли task types known + dispatched + handled.
6. Нет ли retry → publish/embed/processed.
7. Нет ли resume → publish_ready.
8. Нет ли stale UI/error/action state.
9. Достаточны ли tests.
10. Можно ли merge или REQUEST CHANGES.

Не оценивай “в целом”.
Дай verdict:
- APPROVE
- REQUEST CHANGES
- BLOCKED