Перед работой обязательно прочитай docs/ai/ai_engineering_workflow_contract_v1.md.

Работай в режиме contract-driven implementation.

Нельзя:
- гадать архитектуру;
- расширять scope;
- добавлять user-visible action без backend path;
- добавлять endpoint без service/handler/test;
- добавлять task type без KNOWN_TASK_TYPES/dispatcher/test;
- оставлять NotImplemented в пользовательском сценарии;
- подменять normal command fallback-командой;
- ослаблять existing architecture tests.

Сначала выпиши применимые инварианты.
Потом реализуй.
Потом добавь tests.
Потом сделай self-adversarial review.
В финале дай Contract Compliance Table.