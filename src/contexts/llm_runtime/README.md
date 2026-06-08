# LLM Runtime Context

## Назначение

`llm_runtime` — runtime выполнения LLM-задач.

Ему безразлично:

- это Groq или другой provider;
- это Prompt A или Prompt C;
- это Workbench или клиентский ответ;
- это документ или диалог.

Этот context отвечает за LLM task execution: prompt, model route, provider account, quota, token usage, validation, retry/fallback и provider adapters.

## Owns

Canonical concepts:

- `LlmTask`;
- `LlmAttempt`;
- `LlmRoute`;
- `ModelProfile`;
- `ProviderAccount`;
- `QuotaDecision`;
- `TokenUsage`;
- `PromptVersion`;
- `LlmOutputContract`;
- `LlmValidationResult`;
- `LlmErrorKind`;
- `LlmTaskStateMachine`.

Domain/application services that belong here:

- `RoutePlanner`;
- `QuotaManager`;
- `OutputValidationService`;
- `UsageRecorder`.

Use cases that belong here:

- `ExecuteLlmTask`.

Ports that belong here:

- `LlmProviderPort`.

Adapters that belong here:

- `GroqProviderAdapter`;
- future provider adapters.

Domain events that belong here:

- `LlmTaskSucceeded`;
- `LlmTaskDeferred`;
- `LlmTaskFailed`;
- `LlmDailyLimitExhausted`;
- `LlmMinuteLimitHit`.

## Does not own

This context does not own:

- Workbench business meaning;
- source document structure;
- claims semantics;
- final answer policy;
- Telegram delivery;
- human review;
- publication decisions;
- artifact retention policy;
- work item leasing.

## Provider adapter rule

Provider adapter may:

- send a request;
- parse provider response;
- classify provider-specific error;
- return raw usage if available.

Provider adapter must not:

- decide Workbench stage transition;
- decide Prompt A fallback policy;
- decide artifact persistence;
- directly mutate queue item status;
- own workflow policy.

## Legacy / adapter warnings

`GroqLlmJsonInvocationAdapter` and Qwen/Groq-specific adapters are provider adapters, not workflow policy owners.

Prompt-specific generators must not become LLM Runtime.

Prompt A belongs to Knowledge Workbench extraction as a business adapter/use case, even if it uses `llm_runtime`.

## Placement rules

New canonical LLM runtime code goes here.

Do not add new generic dumping-ground files named:

- `service.py`;
- `services.py`;
- `repository.py`;
- `dto.py`.

Use explicit names such as:

- `domain/entities/llm_task.py`;
- `domain/entities/llm_attempt.py`;
- `domain/value_objects/quota_decision.py`;
- `application/use_cases/execute_llm_task.py`;
- `application/ports/llm_provider_port.py`;
- `infrastructure/providers/groq/groq_provider_adapter.py`.
