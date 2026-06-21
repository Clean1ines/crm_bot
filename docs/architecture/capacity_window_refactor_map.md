# Capacity Window Refactor Map

## 1. Purpose

Карта отделяет:

- **item-owned retry timing** — backoff после transient item/provider-independent
  ошибки, retry policy конкретной попытки;
- **capacity-owned timing** — ожидание reset provider/account/model window,
  освобождения reservation или следующего admission opportunity.

Текущий runtime копирует capacity time по цепочке:

```text
provider wait_until / quota reset
→ LLM result next_attempt_at
→ execution attempt outcome next_attempt_at
→ WorkItem.next_attempt_at
→ progress/live-state retry timer
```

В нескольких путях то же время дополнительно становится
`WorkflowCommand.run_after`/`capacity_retry_at`. Это дублирует ownership и делает
work item недоступным не из-за собственного lifecycle, а из-за внешнего capacity
window.

## 2. Target ownership

### Work item target model

Work item хранит только:

- `FRESH`;
- `RETRYABLE`;
- `LEASED`;
- `COMPLETED`;
- `TERMINAL_FAILED`;
- estimated input/output/total tokens;
- route/model constraints;
- attempt count и last item-owned error/retry classification;
- lease identity/expiry только в состоянии `LEASED`.

`FRESH` соответствует текущему `READY`; `RETRYABLE` — текущему
`RETRYABLE_FAILED`. `DEFERRED`, `CANCELLED`, `SPLIT_SUPERSEDED` и
`USER_ACTION_REQUIRED` требуют отдельного migration decision: последние три
являются lifecycle/product states, которые нельзя молча потерять. Вероятный target:
cancel/supersede/action-required хранить как terminal disposition/side record, а не
маскировать под пять основных executable states.

### Capacity window target model

Capacity window владеет:

- provider/account/model;
- remaining requests;
- remaining tokens;
- reset_at;
- active reservations;
- wakeup scheduling;
- admission decision;
- admitted/skipped work refs и reason;
- monotonic observation/revision.

Work item не хранит capacity reset timestamp. Он остаётся `FRESH` или `RETRYABLE`,
но admission query возвращает его только для available matching window.

## 3. Timing classification rules

| Timing source | Ownership |
|---|---|
| Provider `429`/minute or daily quota `wait_until`, rate-limit reset headers | capacity-owned |
| Calculated `capacity_retry_at` from remaining request/token windows | capacity-owned |
| Wakeup command scheduled exactly at provider/account/model reset | capacity-owned |
| Exponential/jitter backoff after network timeout/5xx when capacity is available | item-owned |
| Retry after validation/parser/transient persistence failure | item-owned |
| Lease expiry | execution-runtime lease-owned, not capacity and not retry backoff |
| Manual user/model choice wait | workflow/user-action-owned |
| Source split/input too large | workflow/source-unit-owned, not retry timing |
| Immediate next phase/continuation command `run_after=occurred_at` | workflow scheduling, not retry timing |

## 4. Current-to-target map

| current file / symbol | current behavior | ownership | target behavior | safe migration step | frontend event impact |
|---|---|---|---|---|---|
| `llm_runtime/infrastructure/providers/groq/groq_provider_response_mapper.py` | quota unavailable превращается в provider `wait_until`. | capacity-owned | Return capacity observation/window exhaustion; execution result не назначает item retry time. | Сначала добавить structured capacity outcome рядом с `wait_until`; сохранить compatibility field. | `CapacityWindowExhausted`, не item retry countdown. |
| `llm_runtime/infrastructure/providers/groq/groq_dispatch_executor.py` | `wait_until` копируется в `LlmDispatchExecutionResult.next_attempt_at`. | capacity-owned для minute/daily limit | Result несёт `capacity_window_ref`/capacity outcome; `next_attempt_at` только для item-owned transient retry. | Разделить result fields, dual-write old field временно. | Attempt event с capacity ref; отдельный window event. |
| `llm_runtime/application/ports/llm_dispatch_executor_port.py` | deferred result требует `next_attempt_at`. | mixed/ambiguous | Разные variants: capacity-blocked без item time; item-retryable с retry_at/backoff. | Добавить discriminated outcome contract и tests до удаления field. | Typed attempt status перестаёт смешивать capacity wait и retry. |
| `interfaces/composition/execute_prepared_llm_dispatch_attempt.py` | provider/validation `next_attempt_at` нормализуется в effective next attempt и записывается в outcome. | mixed | Capacity outcome записывает observation/reservation release; item outcome записывает retry policy. | Классифицировать по `LlmErrorKind`/validation result; запрещать capacity reset в item field. | Separate `work_item_retryable` и `capacity_window_exhausted`. |
| `execution_runtime/application/ports/work_item_attempt_outcome_repository_port.py` | `DEFERRED` требует timestamp; retryable может иметь timestamp. | mixed | `RETRYABLE` time только item-owned; capacity-blocked attempt не меняет item на timed state. | Добавить capacity-blocked outcome или не terminal attempt outcome + release lease. | Lane остаётся queued; capacity widget показывает ожидание. |
| `execution_runtime/application/use_cases/record_work_item_attempt_outcome.py` | прокидывает `next_attempt_at` в repository. | mixed | Принимает item retry schedule только для item-owned error; capacity ref отдельно. | Ввести validation guard по outcome reason. | Исключает ложный per-item countdown. |
| `execution_runtime/application/use_cases/fail_work_item.py` | retryable failure требует `next_attempt_at`. | item-owned по названию, но получает capacity time | Retryable state не обязана иметь time; backoff может быть item policy, capacity wait — window. | Разрешить `RETRYABLE` без timestamp после появления capacity admission. | Work item patch: status/reason, без reset_at. |
| `execution_runtime/domain/entities/work_item.py` | хранит `next_attempt_at`; `is_due()` блокирует item до timestamp. | mixed/unsafe | Удалить capacity timing; due определяется item backoff + matching window admission. | Сначала добавить admission query/window relation, затем перестать писать capacity times, потом удалить column. | UI больше не читает retry timer с work item для quota wait. |
| `execution_runtime/domain/state_machines/work_item_state_machine.py` | lease запрещён до `next_attempt_at`; deferred/retry transitions записывают wait. | mixed | Lease проверяет state; capacity admission происходит до/вместе с lease. Item backoff — отдельная retry policy timestamp при необходимости. | Разделить `lease_ready` и capacity admission; сохранить guard для legacy rows на переходный период. | `CapacityWindowLeasedWorkItem` появляется как distinct event. |
| `execution_runtime/infrastructure/postgres/postgres_work_item_lease_repository.py` | SQL фильтрует/сортирует по `next_attempt_at`. | mixed | SQL выбирает FRESH/RETRYABLE candidates и атомарно резервирует capacity window по route/token constraints. | Добавить новый admission path parallel; shadow compare selected ids. | Возможны `PickedFreshItem`/`PickedRetryableItem`. |
| `execution_runtime/infrastructure/postgres/postgres_work_item_progress_read_repository.py` | `next_due_at` вычисляется из item `next_attempt_at`. | mixed | Progress отдельно показывает retryable item counts и next capacity wakeup from window store. | Добавить два поля/read models, не переиспользовать одно время. | Progress patch разделяет item retry и capacity waiting. |
| `knowledge_workbench/extraction/infrastructure/postgres/postgres_draft_claim_compaction_reduction_state_repository.py` | due/next_due_at зависит от execution item timestamp. | mixed | Reduction summary читает item state; capacity wait читает window/wakeup projection. | Dual-read and compare; затем убрать capacity-derived next_due_at. | Cluster panel не показывает quota wait как failed item. |
| `interfaces/composition/prepare_llm_dispatch_batch.py` (`capacity_retry_at`, `_next_capacity_retry_at`) | рассчитывает ближайший reset из observations и возвращает handler’у. | capacity-owned | Capacity runtime создаёт/обновляет window и durable wakeup; prepare возвращает admission decision/window ref. | Сначала persist window decision и emit events, затем убрать scalar `capacity_retry_at`. | `WindowObserved/Exhausted/HasRemainingCapacity/ScheduledWakeup`. |
| `handle_prepare_claim_builder_dispatch_batch_command.py` | при zero dispatch и `capacity_retry_at` reschedule’ит тот же command `run_after`. | capacity-owned | Command не владеет reset; capacity wakeup запускает new prepare/admission pass. | Использовать единый `append_capacity_window_prepare_wakeup`; не reschedule source command после подтверждения parity. | Typed wakeup event; progress остаётся queued. |
| `handle_prepare_draft_claim_compaction_dispatch_batch_command.py` | аналогично reschedule same prepare command. | capacity-owned | Window-owned wakeup для provider/account/model. | Тот же phased migration. | Typed wakeup event для compaction. |
| `append_capacity_window_prepare_wakeup.py` | уже создаёт provider/account/model-specific prepare command с `run_after=minute_reset_at`. | capacity-owned, направление верное | Persist first-class capacity window/wakeup entity/event; command становится delivery mechanism, не source of truth. | Добавить window id, outbox events и idempotency по window revision/reset. | `CapacityWindowScheduledWakeup`, затем `BecameAvailable`. |
| `handle_execute_claim_builder_section_command.py` | provider `next_attempt_at` попадает в event payload, retry action и work item; отдельно append capacity wakeup. | duplicate ownership | Capacity failure release/mark retryable без reset time; wakeup/window owns reset. Item error backoff остаётся item-owned. | Dual emit window event, stop copying capacity timestamp after reducer support. | Удалить capacity `next_attempt_at` из item patch; добавить window ref. |
| `handle_execute_draft_claim_compaction_command.py` | та же двойная запись capacity time + wakeup. | duplicate ownership | То же разделение. | То же. | То же для cluster attempt UI. |
| `handle_reconcile_claim_builder_progress_command.py` | next action может не назначаться до `next_due_at`. | mixed | Reconcile видит retryable items и active capacity wakeups отдельно. | Расширить summary/decision model двумя причинами ожидания. | Phase progress patch содержит `waiting_for_capacity` отдельно. |
| `handle_reconcile_draft_claim_compaction_progress_command.py` | delayed reconcile command получает `run_after=summary.next_due_at`. | mixed | Item backoff может планировать reconcile; capacity wakeup не должен копироваться в generic reconcile. | Маркировать source of next_due_at; capacity branch не создаёт delayed reconcile. | Убирает duplicate countdown/events. |
| `workflow_runtime/domain/entities/workflow_command.py` | каждый command обязан иметь `run_after`. | workflow-owned generic scheduler | Сохранить для immediate/delayed commands; capacity reset commands должны ссылаться на capacity wakeup, а не владеть временем. | Добавить optional `wakeup_ref`/causation metadata в payload/record до schema redesign. | Event показывает wakeup identity, не raw command internals. |
| `workflow_runtime/infrastructure/postgres/postgres_command_log_repository.py` | due query по `run_after`. | generic scheduler | Остаётся delivery scheduler. Capacity source of truth — window/wakeup table/entity. | Не менять первым; переключить producers. | Нет прямого UI dependency. |
| `faq_workbench_workflow_live_state.py` | `retry_available_at = next_attempt_at or lease_expires_at`; attempts показывают reset и item next attempt вместе. | unsafe projection mixing | Отдельные work item retry, lease expiry и capacity window projections. | Добавить fields параллельно, затем перестать вычислять общий retry timer. | Новые independent lane/capacity widgets. |
| `frontend/src/shared/api/modules/knowledge.ts` | queue item и LLM attempt содержат `next_attempt_at`; attempt также содержит quota reset. | unsafe frontend mixing | Item patch содержит state/error; capacity patch содержит reset/countdown. | Добавить normalized capacity window type/reducer, сохранить old fields до parity. | Countdown переезжает в capacity widget. |
| legacy `src/infrastructure/db/repositories/queue_repository.py` / `execution_queue.next_attempt_at` | legacy queue планирует attempts timestamp’ом. | mixed/legacy | Не расширять; исключить из canonical workflow migration. | Зафиксировать reference-only status и не подключать typed projections. | Не должен быть frontend source. |

## 5. Capacity event model

Рекомендуемый минимальный event family:

| event | Required payload |
|---|---|
| `CapacityWindowObserved` | `window_id`, provider/account/model, remaining requests/tokens, reset_at, observed_at, revision |
| `CapacityWindowExhausted` | `window_id`, exhausted dimensions, reset_at, reason |
| `CapacityWindowHasRemainingCapacity` | `window_id`, admissible request count/token budget |
| `CapacityWindowLeasedWorkItem` | `window_id`, work_item_id, attempt_id, reserved requests/tokens |
| `CapacityWindowSkippedItemByTokenEstimate` | `window_id`, work_item_id/source ref, estimated tokens, available tokens, decision |
| `CapacityWindowScheduledWakeup` | `window_id`, wakeup_id, reset_at/run_after |
| `CapacityWindowBecameAvailable` | `window_id`, available_at, current budgets/revision |
| `CapacityWindowPickedRetryableItem` | `window_id`, work_item_id, attempt_count, selection rank |
| `CapacityWindowPickedFreshItem` | `window_id`, work_item_id, selection rank |

Selection events должны создаваться только для admitted/leased candidate. Логировать
каждый SQL candidate как durable event слишком дорого.

## 6. Safe migration sequence

1. Добавить explicit classification `capacity_blocked` vs `item_retryable` в LLM
   execution result и attempt outcome.
2. Создать first-class capacity window identity/revision поверх существующих
   observations/reservations.
3. Persist admission decision и durable wakeup; emit typed capacity events.
4. Добавить work item estimated tokens и route/model constraints в canonical
   scheduling metadata, если они ещё находятся только в payload.
5. Добавить новый atomic selection/admission path, который выбирает
   FRESH/RETRYABLE items и capacity window вместе.
6. В shadow mode сравнивать selection старого `next_attempt_at` path и нового
   capacity admission path.
7. Перестать копировать minute/daily reset в work item `next_attempt_at`.
8. Перестать reschedule prepare/reconcile commands непосредственно по
   `capacity_retry_at`; использовать window wakeup.
9. Перевести frontend countdown и waiting state на capacity events.
10. Очистить legacy capacity-derived `next_attempt_at` rows, сохранив genuine
    item-owned backoff.
11. Только после этого упростить work item statuses/schema и удалить смешанные
    fields/queries.

## 7. Invariants and rollback

Инварианты:

- один provider/account/model reset имеет один active wakeup per revision;
- work item не становится terminal из-за исчерпания capacity;
- exhausted window не изменяет item attempt count без provider call;
- reservation и lease либо создаются атомарно, либо имеют compensating release;
- replay capacity events идемпотентен;
- user-action wait и source split не маскируются под capacity wait;
- item backoff остаётся возможным независимо от capacity availability.

Rollback:

- сохранять compatibility `next_attempt_at` dual-write до завершения shadow compare;
- feature flag переключает admission path;
- старый command scheduler остаётся delivery fallback;
- capacity window tables/events можно оставить неиспользуемыми при rollback;
- schema columns удалять только отдельной поздней migration.

## 8. Frontend impact

Target UI:

- lane row: FRESH/RETRYABLE/LEASED/COMPLETED/TERMINAL_FAILED, attempt count,
  item-owned error/backoff;
- capacity widget/banner: provider/account/model, remaining requests/tokens,
  reset countdown, scheduled wakeup;
- active attempt row: lease/attempt/model and capacity window ref;
- progress: separate `retryable_items` and `waiting_for_capacity`;
- source/cluster warning: skipped by token estimate and required split/action.

Старый единый `retry_timer` нельзя механически перенести: он сейчас выбирает
`next_attempt_at or lease_expires_at` и смешивает три разных ownership domain.

## 9. Open questions

1. Где должен жить canonical capacity window: `capacity_runtime` или LLM Runtime
   с generic capacity adapter?
2. Нужны minute и daily windows как отдельные entities или один aggregate с двумя
   reset dimensions?
3. Как fairness выбирает FRESH против RETRYABLE?
4. Является ли item-owned retry timestamp допустимым в target model, или backoff
   также должен стать отдельным retry scheduler?
5. Как моделировать `USER_ACTION_REQUIRED`, `SPLIT_SUPERSEDED`, cancellation при
   заявленном target наборе из пяти work item states?
6. Должны ли capacity events храниться в общем workflow outbox или отдельном
   capacity event log с frontend projection bridge?
7. Нужна ли visibility account_ref всем frontend users, или его следует
   редактировать/псевдонимизировать?

## 10. Validation

Карта построена статическим read-only поиском всех `next_attempt_at`,
`capacity_retry_at`, `run_after`, `wait_until`, `reset_at` и связанных SQL/domain
paths. Тесты не запускались, потому что обязательный test-env bootstrap может
создать `.env.test`, что нарушило бы strict read-only условие.
