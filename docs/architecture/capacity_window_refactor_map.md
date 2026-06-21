# Capacity Window Refactor Map

## 1. Purpose

Карта отделяет:

* **work-item failure / retry eligibility** — пассивная классификация причины
  неуспеха и признак, что item может быть выбран будущим admission pass;
* **capacity-owned timing** — ожидание reset provider/account/model window,
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

Целевой смысл:

```text
WorkItem is passive queue/lifecycle state.
CapacityWindow/admission is active selection driver.
```

Work item может быть `FRESH` или `RETRYABLE`, но он не просыпается сам и не
назначает себе следующий provider retry. Он только остаётся eligible для будущего
admission pass.

## 2. Target ownership

### Work item target model

Work item хранит только:

* `FRESH`;
* `RETRYABLE`;
* `LEASED`;
* `COMPLETED`;
* `TERMINAL_FAILED`;
* estimated input/output/total tokens;
* route/model constraints;
* attempt count, last failure classification и retry/admission eligibility;
* lease identity/expiry только в состоянии `LEASED`.

`FRESH` соответствует текущему `READY`; `RETRYABLE` — текущему
`RETRYABLE_FAILED`.

`RETRYABLE` означает только:

```text
this work item is eligible for future admission
```

`RETRYABLE` не означает:

```text
this work item owns a wakeup timer
this work item retries itself
this work item owns provider/account/model reset time
```

`DEFERRED`, `CANCELLED`, `SPLIT_SUPERSEDED` и `USER_ACTION_REQUIRED` требуют
отдельного migration decision: последние три являются lifecycle/product states,
которые нельзя молча потерять. Вероятный target: cancel/supersede/action-required
хранить как terminal disposition/side record, а не маскировать под пять основных
executable states.

### Passive WorkItem invariant

Work item is passive queue/lifecycle state.

Work item **does not**:

* wake itself;
* schedule its next provider call;
* own provider/account/model reset time;
* store capacity reset timestamp;
* become terminal because capacity is exhausted;
* increment attempt count without a provider/model execution attempt.

The active driver for selecting fresh/retryable work is CapacityWindow/admission.
CapacityWindow wakes, evaluates remaining provider/account/model budget, and pulls
suitable work items from the shared queue by priority, route/model constraints and
token budget.

A retryable work item can carry:

* last failure classification;
* retry/admission eligibility;
* route/model constraints;
* token estimates;
* attempt count;
* terminal/product disposition when applicable.

It must not carry provider quota reset as its own retry countdown.

### Capacity window target model

Capacity window владеет:

* provider/account/model;
* remaining requests;
* remaining tokens;
* reset_at;
* active reservations;
* wakeup scheduling;
* admission decision;
* admitted/skipped work refs и reason;
* monotonic observation/revision.

Work item не хранит capacity reset timestamp. Он остаётся `FRESH` или `RETRYABLE`,
но admission query возвращает его только для available matching window.
`RETRYABLE` является пассивной eligibility state: future execution happens only
when a CapacityWindow/admission pass selects the item.

## 3. Timing classification rules

| Timing source                                                                   | Ownership                                                                                      |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Provider `429`/minute or daily quota `wait_until`, rate-limit reset headers     | capacity-owned                                                                                 |
| Calculated `capacity_retry_at` from remaining request/token windows             | capacity-owned                                                                                 |
| Wakeup command scheduled exactly at provider/account/model reset                | capacity-owned                                                                                 |
| Exponential/jitter backoff after network timeout/5xx when capacity is available | provider/workflow policy classification; WorkItem remains passive eligible state               |
| Retry after validation/parser/transient persistence failure                     | validation/persistence/workflow policy classification; WorkItem remains passive eligible state |
| Lease expiry                                                                    | execution-runtime lease-owned, not capacity and not retry backoff                              |
| Manual user/model choice wait                                                   | workflow/user-action-owned                                                                     |
| Source split/input too large                                                    | workflow/source-unit-owned, not retry timing                                                   |
| Immediate next phase/continuation command `run_after=occurred_at`               | workflow scheduling, not retry timing                                                          |

Rule:

```text
provider/account/model reset_at → CapacityWindow overlay
work item retry/admission eligibility → WorkItem overlay
lease expiry → ExecutionRuntime lease overlay
user/model choice wait → workflow/user-action overlay
source split/input too large → source-unit/workflow overlay
```

No single frontend `retry_timer` may combine these domains.

## 4. Current-to-target map

| current file / symbol                                                                                                  | current behavior                                                                                                  | ownership                                              | target behavior                                                                                                               | safe migration step                                                                                                   | frontend event impact                                                       |
| ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `llm_runtime/infrastructure/providers/groq/groq_provider_response_mapper.py`                                           | quota unavailable превращается в provider `wait_until`.                                                           | capacity-owned                                         | Return capacity observation/window exhaustion; execution result не назначает item wakeup time.                                | Сначала добавить structured capacity outcome рядом с `wait_until`; сохранить compatibility field.                     | `CapacityWindowExhausted`, не work item retry countdown.                    |
| `llm_runtime/infrastructure/providers/groq/groq_dispatch_executor.py`                                                  | `wait_until` копируется в `LlmDispatchExecutionResult.next_attempt_at`.                                           | capacity-owned для minute/daily limit                  | Result несёт `capacity_window_ref`/capacity outcome; `next_attempt_at` не используется для provider/account/model reset.      | Разделить result fields, dual-write old field временно.                                                               | Attempt event с capacity ref; отдельный window event.                       |
| `llm_runtime/application/ports/llm_dispatch_executor_port.py`                                                          | deferred result требует `next_attempt_at`.                                                                        | mixed/ambiguous                                        | Разные variants: capacity-blocked без item time; item failure classification without self-wakeup.                             | Добавить discriminated outcome contract and tests до удаления field.                                                  | Typed attempt status перестаёт смешивать capacity wait и retry eligibility. |
| `interfaces/composition/execute_prepared_llm_dispatch_attempt.py`                                                      | provider/validation `next_attempt_at` нормализуется в effective next attempt и записывается в outcome.            | mixed                                                  | Capacity outcome записывает observation/reservation release; item outcome записывает failure classification/eligibility.      | Классифицировать по `LlmErrorKind`/validation result; запрещать capacity reset в item field.                          | Separate `work_item_retryable_eligible` и `capacity_window_exhausted`.      |
| `execution_runtime/application/ports/work_item_attempt_outcome_repository_port.py`                                     | `DEFERRED` требует timestamp; retryable может иметь timestamp.                                                    | mixed                                                  | `RETRYABLE` не требует timestamp; capacity-blocked attempt не меняет item на timed state.                                     | Добавить capacity-blocked outcome или не terminal attempt outcome + release lease.                                    | Lane остаётся queued/retryable; capacity widget показывает ожидание.        |
| `execution_runtime/application/use_cases/record_work_item_attempt_outcome.py`                                          | прокидывает `next_attempt_at` в repository.                                                                       | mixed                                                  | Принимает failure classification/eligibility; capacity ref отдельно.                                                          | Ввести validation guard по outcome reason.                                                                            | Исключает ложный per-item countdown.                                        |
| `execution_runtime/application/use_cases/fail_work_item.py`                                                            | retryable failure требует `next_attempt_at`.                                                                      | historically item-owned, but can receive capacity time | Retryable state не обязана иметь time; future execution is admission-driven.                                                  | Разрешить `RETRYABLE` без timestamp после появления capacity admission.                                               | Work item patch: status/reason/eligibility, без reset_at.                   |
| `execution_runtime/domain/entities/work_item.py`                                                                       | хранит `next_attempt_at`; `is_due()` блокирует item до timestamp.                                                 | mixed/unsafe                                           | Удалить capacity timing; admission выбирает FRESH/RETRYABLE candidates by capacity window.                                    | Сначала добавить admission query/window relation, затем перестать писать capacity times, потом удалить column.        | UI больше не читает retry timer с work item для quota wait.                 |
| `execution_runtime/domain/state_machines/work_item_state_machine.py`                                                   | lease запрещён до `next_attempt_at`; deferred/retry transitions записывают wait.                                  | mixed                                                  | Lease проверяет state; capacity admission происходит до/вместе с lease.                                                       | Разделить `lease_ready` и capacity admission; сохранить guard для legacy rows на переходный период.                   | `CapacityWindowLeasedWorkItem` появляется как distinct event.               |
| `execution_runtime/infrastructure/postgres/postgres_work_item_lease_repository.py`                                     | SQL фильтрует/сортирует по `next_attempt_at`.                                                                     | mixed                                                  | SQL выбирает FRESH/RETRYABLE candidates и атомарно резервирует capacity window по route/token constraints.                    | Добавить новый admission path parallel; shadow compare selected ids.                                                  | Возможны `PickedFreshItem`/`PickedRetryableItem`.                           |
| `execution_runtime/infrastructure/postgres/postgres_work_item_progress_read_repository.py`                             | `next_due_at` вычисляется из item `next_attempt_at`.                                                              | mixed                                                  | Progress отдельно показывает retryable item counts and next capacity wakeup from window store.                                | Добавить два поля/read models, не переиспользовать одно время.                                                        | Progress patch разделяет retryable eligibility и capacity waiting.          |
| `knowledge_workbench/extraction/infrastructure/postgres/postgres_draft_claim_compaction_reduction_state_repository.py` | due/next_due_at зависит от execution item timestamp.                                                              | mixed                                                  | Reduction summary читает item state; capacity wait читает window/wakeup projection.                                           | Dual-read and compare; затем убрать capacity-derived next_due_at.                                                     | Cluster panel не показывает quota wait как failed item.                     |
| `interfaces/composition/prepare_llm_dispatch_batch.py` (`capacity_retry_at`, `_next_capacity_retry_at`)                | рассчитывает ближайший reset из observations и возвращает handler’у.                                              | capacity-owned                                         | Capacity runtime создаёт/обновляет window и durable wakeup; prepare returns admission decision/window ref.                    | Сначала persist window decision и emit events, затем убрать scalar `capacity_retry_at`.                               | `WindowObserved/Exhausted/HasRemainingCapacity/ScheduledWakeup`.            |
| `handle_prepare_claim_builder_dispatch_batch_command.py`                                                               | при zero dispatch и `capacity_retry_at` reschedule’ит тот же command `run_after`.                                 | capacity-owned                                         | Command не владеет reset; capacity wakeup запускает new prepare/admission pass.                                               | Использовать единый `append_capacity_window_prepare_wakeup`; не reschedule source command после подтверждения parity. | Typed wakeup event; progress остаётся queued.                               |
| `handle_prepare_draft_claim_compaction_dispatch_batch_command.py`                                                      | аналогично reschedule same prepare command.                                                                       | capacity-owned                                         | Window-owned wakeup для provider/account/model.                                                                               | Тот же phased migration.                                                                                              | Typed wakeup event для compaction.                                          |
| `append_capacity_window_prepare_wakeup.py`                                                                             | уже создаёт provider/account/model-specific prepare command с `run_after=minute_reset_at`.                        | capacity-owned, направление верное                     | Persist first-class capacity window/wakeup entity/event; command becomes delivery mechanism, not source of truth.             | Добавить window id, outbox events и idempotency по window revision/reset.                                             | `CapacityWindowScheduledWakeup`, затем `BecameAvailable`.                   |
| `handle_execute_claim_builder_section_command.py`                                                                      | provider `next_attempt_at` попадает в event payload, retry action и work item; отдельно append capacity wakeup.   | duplicate ownership                                    | Capacity failure release/mark retryable without reset time; wakeup/window owns reset.                                         | Dual emit window event, stop copying capacity timestamp after reducer support.                                        | Удалить capacity `next_attempt_at` из item patch; добавить window ref.      |
| `handle_execute_draft_claim_compaction_command.py`                                                                     | та же двойная запись capacity time + wakeup.                                                                      | duplicate ownership                                    | То же разделение.                                                                                                             | То же.                                                                                                                | То же для cluster attempt UI.                                               |
| `handle_reconcile_claim_builder_progress_command.py`                                                                   | next action может не назначаться до `next_due_at`.                                                                | mixed                                                  | Reconcile видит retryable items and active capacity wakeups separately.                                                       | Расширить summary/decision model двумя причинами ожидания.                                                            | Phase progress patch contains `waiting_for_capacity` separately.            |
| `handle_reconcile_draft_claim_compaction_progress_command.py`                                                          | delayed reconcile command получает `run_after=summary.next_due_at`.                                               | mixed                                                  | Item-independent backoff may schedule reconcile; capacity wakeup не должен копироваться в generic reconcile.                  | Маркировать source of next_due_at; capacity branch не создаёт delayed reconcile.                                      | Убирает duplicate countdown/events.                                         |
| `workflow_runtime/domain/entities/workflow_command.py`                                                                 | каждый command обязан иметь `run_after`.                                                                          | workflow-owned generic scheduler                       | Сохранить для immediate/delayed commands; capacity reset commands должны ссылаться на capacity wakeup, а не владеть временем. | Добавить optional `wakeup_ref`/causation metadata в payload/record до schema redesign.                                | Event показывает wakeup identity, not raw command internals.                |
| `workflow_runtime/infrastructure/postgres/postgres_command_log_repository.py`                                          | due query по `run_after`.                                                                                         | generic scheduler                                      | Остаётся delivery scheduler. Capacity source of truth — window/wakeup table/entity.                                           | Не менять первым; переключить producers.                                                                              | Нет прямого UI dependency.                                                  |
| `faq_workbench_workflow_live_state.py`                                                                                 | `retry_available_at = next_attempt_at or lease_expires_at`; attempts показывают reset и item next attempt вместе. | unsafe projection mixing                               | Отдельные work item eligibility, lease expiry и capacity window projections.                                                  | Добавить fields параллельно, затем перестать вычислять общий retry timer.                                             | Новые independent lane/capacity widgets.                                    |
| `frontend/src/shared/api/modules/knowledge.ts`                                                                         | queue item и LLM attempt содержат `next_attempt_at`; attempt также содержит quota reset.                          | unsafe frontend mixing                                 | Item patch contains state/failure/eligibility; capacity patch contains reset/countdown.                                       | Добавить normalized capacity window type/reducer, сохранить old fields до parity.                                     | Countdown переезжает в capacity widget.                                     |
| legacy `src/infrastructure/db/repositories/queue_repository.py` / `execution_queue.next_attempt_at`                    | legacy queue планирует attempts timestamp’ом.                                                                     | mixed/legacy                                           | Не расширять; исключить из canonical workflow migration.                                                                      | Зафиксировать reference-only status и не подключать typed projections.                                                | Не должен быть frontend source.                                             |

## 5. Capacity event model

Рекомендуемый минимальный event family:

| event                                      | Required payload                                                                                |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| `CapacityWindowObserved`                   | `window_id`, provider/account/model, remaining requests/tokens, reset_at, observed_at, revision |
| `CapacityWindowExhausted`                  | `window_id`, exhausted dimensions, reset_at, reason                                             |
| `CapacityWindowHasRemainingCapacity`       | `window_id`, admissible request count/token budget                                              |
| `CapacityWindowLeasedWorkItem`             | `window_id`, work_item_id, attempt_id, reserved requests/tokens                                 |
| `CapacityWindowSkippedItemByTokenEstimate` | `window_id`, work_item_id/source ref, estimated tokens, available tokens, decision              |
| `CapacityWindowScheduledWakeup`            | `window_id`, wakeup_id, reset_at/run_after                                                      |
| `CapacityWindowBecameAvailable`            | `window_id`, available_at, current budgets/revision                                             |
| `CapacityWindowPickedRetryableItem`        | `window_id`, work_item_id, attempt_count, selection rank                                        |
| `CapacityWindowPickedFreshItem`            | `window_id`, work_item_id, selection rank                                                       |

Selection events должны создаваться только для admitted/leased candidate. Логировать
каждый SQL candidate как durable event слишком дорого.

## 6. Safe migration sequence

1. Добавить explicit classification `capacity_blocked` vs `work_item_retryable_eligible`
   в LLM execution result и attempt outcome.
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
    failure classification / retry eligibility for future admission.
11. Только после этого упростить work item statuses/schema и удалить смешанные
    fields/queries.

## 7. Invariants and rollback

Инварианты:

* один provider/account/model reset имеет один active wakeup per revision;
* work item не становится terminal из-за исчерпания capacity;
* exhausted window не изменяет item attempt count без provider call;
* reservation и lease либо создаются атомарно, либо имеют compensating release;
* replay capacity events идемпотентен;
* user-action wait и source split не маскируются под capacity wait;
* retryable work item remains passive eligible state;
* future execution happens only when capacity/admission selects the item;
* provider/account/model reset is never rendered as work item retry countdown.

Rollback:

* сохранять compatibility `next_attempt_at` dual-write до завершения shadow compare;
* feature flag переключает admission path;
* старый command scheduler остаётся delivery fallback;
* capacity window tables/events можно оставить неиспользуемыми при rollback;
* schema columns удалять только отдельной поздней migration.

## 8. Frontend impact

Target UI:

* lane row: FRESH/RETRYABLE/LEASED/COMPLETED/TERMINAL_FAILED, attempt count,
  failure classification and retry/admission eligibility;
* capacity widget/banner: provider/account/model, remaining requests/tokens,
  reset countdown, scheduled wakeup;
* active attempt row: lease/attempt/model and capacity window ref;
* progress: separate `retryable_items` and `waiting_for_capacity`;
* source/cluster warning: skipped by token estimate and required split/action.

Старый единый `retry_timer` нельзя механически перенести: он сейчас выбирает
`next_attempt_at or lease_expires_at` и смешивает три разных ownership domain.

## 9. Open questions

1. Где должен жить canonical capacity window: `capacity_runtime` или LLM Runtime
   с generic capacity adapter?
2. Нужны minute и daily windows как отдельные entities или один aggregate с двумя
   reset dimensions?
3. Как fairness выбирает FRESH против RETRYABLE?
4. Should item-independent backoff exist as a separate scheduler, or should it
   remain only a failure classification / admission eligibility signal?
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
