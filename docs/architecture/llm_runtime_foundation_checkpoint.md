# LLM Runtime Foundation Checkpoint

## 0. Purpose

This document freezes the current foundation state of the new `LLM Runtime` bounded context.

It exists so the next implementation steps do not drift back into:

- ad-hoc Prompt A logic;
- Groq-specific workflow policy;
- queue handler retry logic;
- Workbench-specific status mutation;
- generic services/repositories/DTO dumping grounds;
- duplicated runtime concepts under new names.

This document is not a rewrite plan for the entire project.

It is a checkpoint for the already created architectural foundation and the next safe implementation sequence.

---

## 1. Current branch and intent

Current working branch:

```text
architecture/pattern-foundation

The branch introduces a bounded-context-first architecture foundation under:

src/contexts/

The main goal of the branch is to split responsibilities that were previously collapsed into generic services, repositories, DTOs, status strings and queue handlers.

2. Relevant committed sequence

The foundation so far was built in small commits:

Add pattern-based bounded context foundation
Add execution runtime domain skeleton
Add artifact runtime domain skeleton
Add llm runtime domain skeleton
Add llm runtime error policy
Add llm runtime route planning policy
Add llm runtime execute task use case
Add llm runtime unit of work boundary
Add llm execution recording policy
Add llm execute and record use case
Add llm output validation port
Add llm json output validation policy

The exact hashes may differ across rebases, but the semantic order matters.

3. Bounded contexts created

The branch introduced canonical context folders:

src/contexts/
  execution_runtime/
  artifact_runtime/
  llm_runtime/
  knowledge_workbench/
  conversation_runtime/

The rule is:

New canonical runtime code goes under src/contexts/<bounded_context>/...
Old layer-first paths may remain as legacy/adapters during cutover.

No mass file migration has been performed.

4. Pattern foundation already established
4.1. Execution Runtime

Context:

src/contexts/execution_runtime/

Purpose:

Generic executable work lifecycle.

Owns:

WorkItem
WorkItemAttempt
WorkItemStatus
LeaseToken
WorkerRef
WorkKind
RetryPolicy
WaitUntil
WorkItemStateMachine
WorkItem domain events

Important rule:

Execution Runtime must stay business-agnostic.

It must not know:

Prompt A
Prompt C
Groq
Qwen
claims
surfaces
source units
artifacts
LLM details
Telegram
Workbench status names

SectionBatchQueueItem is not canonical WorkItem.

It is a legacy/adapter hybrid.

4.2. Artifact Runtime

Context:

src/contexts/artifact_runtime/

Purpose:

Generic persistence lifecycle for pipeline/workflow artifacts.

Owns:

PipelineArtifact
ArtifactRef
ArtifactKind
ArtifactPayload
ArtifactLineage
ArtifactStatus
ArtifactVisibility
RetentionPolicy
Artifact domain events

Important rule:

Artifact existence is the checkpoint.
Queue status is not the artifact.

Artifact Runtime must not know:

WorkItem lifecycle
LLM provider details
Prompt A
Prompt C
Workbench semantic meaning
claim/surface semantics
Telegram
4.3. LLM Runtime

Context:

src/contexts/llm_runtime/

Purpose:

Provider-neutral runtime for LLM task execution.

Owns:

LlmTask
LlmAttempt
LlmRoute
ModelId
ProviderId
ProviderAccountRef
TokenUsage
QuotaDecision
LlmErrorKind
LlmTaskStatus
LlmTaskStateMachine
PromptVersion
OutputContractRef
LlmInputRef
LlmValidationResult

LLM Runtime may know generic concepts such as:

provider
model
route
quota
tokens
validation
retry
fallback
output contract

LLM Runtime must not know:

Prompt A
Prompt C
Workbench
claim semantics
surface semantics
source sections
Telegram
WorkItem
PipelineArtifact
Groq-specific workflow policy

Provider-specific code is future adapter code, not domain/application policy.

5. LLM Runtime application layer already built
5.1. Error policy

File:

src/contexts/llm_runtime/application/policies/llm_error_policy.py

Purpose:

Map typed LLM error kinds to provider-neutral disposition classes.

Examples:

REQUEST_TOO_LARGE -> TRY_ALTERNATE_ROUTE
OUTPUT_TOO_LARGE -> TRY_ALTERNATE_ROUTE
MINUTE_LIMIT -> DEFER_UNTIL
DAILY_LIMIT -> TRY_ALTERNATE_ROUTE
INVALID_OUTPUT -> VALIDATION_RETRY
VALIDATION_FAILED -> VALIDATION_RETRY
EMPTY_OUTPUT -> CONFIRM_EMPTY_OUTPUT
NETWORK_ERROR -> RETRY_SAME_ROUTE
UNKNOWN -> RETRY_SAME_ROUTE
AUTH_ERROR -> TERMINAL_FAILURE

This policy does not select the concrete next model/account.

5.2. Route planning policy

File:

src/contexts/llm_runtime/application/policies/llm_route_planning_policy.py

Purpose:

Choose the next provider-neutral route from already known candidates.

It works with:

LlmRouteCandidate
LlmRoutePlanDecision
LlmRoutePlanningPolicy

Current intended behavior:

REQUEST_TOO_LARGE:
  prefer larger context route;
  prefer same account first;
  if no larger context route exists -> SPLIT_REQUIRED.

OUTPUT_TOO_LARGE:
  prefer larger output route;
  prefer same account first;
  if no larger output route exists -> SPLIT_REQUIRED.

MINUTE_LIMIT:
  prefer same model on another available account;
  if no account is available -> WAIT_UNTIL nearest unavailable_until;
  if no wait is known -> RETRY_SAME_ROUTE.

DAILY_LIMIT:
  prefer same model on another available account;
  then try another available model;
  if nothing is available -> DAILY_EXHAUSTED.

AUTH_ERROR:
  TERMINAL_FAILURE.

NETWORK_ERROR / UNKNOWN / validation/empty-output classes:
  route planning layer does not change route.

This policy still does not know real Groq limits. It only consumes candidate data.

5.3. ExecuteLlmTask use case

File:

src/contexts/llm_runtime/application/use_cases/execute_llm_task.py

Purpose:

Run one provider-neutral LLM attempt and return a typed outcome.

It uses:

LlmProviderPort
LlmOutputValidationPort
LlmErrorPolicy
LlmRoutePlanningPolicy
LlmTaskStateMachine

It does not persist anything.

It does not know database, WorkItem, Artifact Runtime, Workbench or Groq.

Current flow:

LlmTask READY/DEFERRED/RETRYABLE_FAILED
-> LlmTaskStateMachine.start_ready(...)
-> provider.invoke(...)
-> if provider success: validate output
-> if validation success: succeed task
-> if validation failure: convert to failure handling
-> if provider failure: apply error/route policy
-> return ExecuteLlmTaskOutcome

Important: provider success is not automatically accepted. It must pass output validation.

5.4. Unit of Work boundary

File:

src/contexts/llm_runtime/application/ports/llm_task_unit_of_work_port.py

Purpose:

Define the transaction boundary for committing LLM task execution consequences.

Port methods:

save_task(...)
save_attempt(...)
append_event(...)
commit()
rollback()

This is only a port.

There is no Postgres adapter yet.

5.5. RecordLlmTaskExecution use case

File:

src/contexts/llm_runtime/application/use_cases/record_llm_task_execution.py

Purpose:

Persist task state, optional attempt, and events atomically through the UoW port.

Current flow:

save_task
save_attempt if present
append events
commit
rollback on exception

It does not know database details.

5.6. Execution recording policy

File:

src/contexts/llm_runtime/application/policies/llm_execution_recording_policy.py

Purpose:

Map ExecuteLlmTaskOutcome into RecordLlmTaskExecutionCommand.

It creates:

LlmAttempt
LlmTaskSucceeded event
LlmTaskFailed event
LlmTaskDeferred event
LlmMinuteLimitHit event
LlmDailyLimitExhausted event

It does not persist anything itself.

5.7. ExecuteAndRecordLlmTask use case

File:

src/contexts/llm_runtime/application/use_cases/execute_and_record_llm_task.py

Purpose:

First full application flow inside LLM Runtime.

It connects:

ExecuteLlmTask
-> LlmExecutionRecordingPolicy
-> RecordLlmTaskExecution

It still does not know:

Groq
Postgres
Workbench
WorkItem
PipelineArtifact
Prompt A
Prompt C
5.8. Output validation port

File:

src/contexts/llm_runtime/application/ports/llm_output_validation_port.py

Purpose:

Validate provider raw output before accepting it as success.

Returns:

LlmOutputValidationSuccess
LlmOutputValidationFailure

Allowed validation failure error kinds:

INVALID_OUTPUT
VALIDATION_FAILED
EMPTY_OUTPUT
5.9. Generic JSON output validation policy

File:

src/contexts/llm_runtime/application/policies/llm_json_output_validation_policy.py

Purpose:

Generic provider-neutral JSON validation.

It supports:

invalid JSON -> INVALID_OUTPUT
top-level non-object -> VALIDATION_FAILED
unknown output contract -> VALIDATION_FAILED
missing required top-level keys -> VALIDATION_FAILED
empty object -> EMPTY_OUTPUT or success depending on contract policy

It does not know Prompt A or concrete Workbench schemas.

6. Important technical decisions already made
6.1. Avoid package-level barrel imports

Application package __init__.py files should not eagerly import all use cases/policies/ports.

Reason:

Eager __init__.py imports caused circular imports between policies and use cases.

Current rule:

Import concrete application classes directly from their modules.
Keep application package __init__.py minimal.
6.2. No Any in canonical domain/application skeletons

Pre-commit rejects Any and type: ignore.

When payload-like data is needed, use explicit typed aliases or typed value objects.

6.3. State machines are mandatory for lifecycle mutation

Use cases must not manually assign statuses.

Current examples:

ExecuteLlmTask uses LlmTaskStateMachine.
Execution Runtime uses WorkItemStateMachine.

This prevented invalid states such as:

DEFERRED task without wait_until
6.4. Provider success is not success

A provider returning raw text successfully does not mean the LLM task succeeded.

Required sequence:

provider success
-> output validation
-> success only if validation succeeds
6.5. Route planning is separate from error disposition

LlmErrorPolicy answers:

What kind of reaction does this error require?

LlmRoutePlanningPolicy answers:

Which route, wait-state, split, or exhaustion decision follows?
7. What is intentionally not implemented yet

Not implemented yet:

Real provider adapter
Groq adapter
Real model/account catalog
Real quota ledger
Postgres Unit of Work
Outbox adapter
Usage/cost rollup persistence
Artifact Runtime integration
Execution Runtime WorkItem integration
Knowledge Workbench Prompt A cutover
Prompt C / surface consolidation cutover
SourceUnit domain
Split policy integration
Stage coordinator / saga
Frontend-visible processing states

This is intentional.

8. Next implementation step

The next safe step is:

LLM Model/Account Catalog + Route Candidate Builder

Reason:

LlmRoutePlanningPolicy can choose from candidates,
but candidates are currently assembled manually in tests.

Next files should probably be:

src/contexts/llm_runtime/domain/entities/model_profile.py
src/contexts/llm_runtime/domain/entities/provider_account.py
src/contexts/llm_runtime/application/policies/llm_route_candidate_builder.py
tests/contexts/llm_runtime/application/policies/test_llm_route_candidate_builder.py

The candidate builder should convert:

ModelProfile
ProviderAccount
availability/quota snapshot

into:

tuple[LlmRouteCandidate, ...]

It should remain provider-neutral.

It must not know:

Groq
Prompt A
Prompt C
Workbench
WorkItem
PipelineArtifact
Telegram
9. Required behavior for future route candidate builder

The builder must support the future requirements:

Multiple provider accounts / capacity slots.
Multiple models with ordered fallback rank.
Known context window per model.
Known max output tokens per model.
Minute availability.
Daily availability.
Unavailable-until timestamps.
Candidate ordering by model/account rank.

It must not yet decide business workflow state.

It only builds route candidates.

Route decision remains in:

LlmRoutePlanningPolicy
10. Future sequence after candidate builder

Recommended order:

1. LLM model/account catalog domain skeleton.
2. Route candidate builder.
3. Quota snapshot/value objects.
4. ExecuteAndRecordLlmTask integration with candidate builder.
5. Postgres-free fake UoW tests stay in application layer.
6. Only then provider adapter interface implementation.
7. Only then Groq adapter.
8. Only then integration with Execution Runtime WorkItem.
9. Only then Artifact Runtime persistence.
10. Only then Knowledge Workbench Prompt A cutover.

Do not jump directly to Groq or Prompt A.

11. Guardrails for future agents

Future patches must obey:

No reports unless explicitly requested.
No new generic service.py / repository.py / dto.py dumping grounds.
No Workbench terms in LLM Runtime domain/application.
No provider-specific workflow policy in generic LLM Runtime.
No direct status mutation outside state machines.
No database adapter before port/use-case boundary is stable.
No Prompt A cutover before model/account/validation/quota boundaries exist.
No eager barrel exports in application __init__.py.
12. Current conceptual pipeline

Current LLM Runtime foundation supports this conceptual flow:

LlmTask
-> ExecuteLlmTask
   -> LlmTaskStateMachine.start_ready
   -> LlmProviderPort.invoke
   -> LlmOutputValidationPort.validate
   -> LlmErrorPolicy
   -> LlmRoutePlanningPolicy
   -> ExecuteLlmTaskOutcome

ExecuteLlmTaskOutcome
-> LlmExecutionRecordingPolicy
   -> LlmAttempt
   -> LlmTask domain event
   -> RecordLlmTaskExecutionCommand

RecordLlmTaskExecutionCommand
-> RecordLlmTaskExecution
   -> LlmTaskUnitOfWorkPort.save_task
   -> LlmTaskUnitOfWorkPort.save_attempt
   -> LlmTaskUnitOfWorkPort.append_event
   -> commit / rollback

This is the current stable architecture line.
