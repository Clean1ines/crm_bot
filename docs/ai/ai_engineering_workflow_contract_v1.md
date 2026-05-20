# AI Engineering Workflow Contract v1

## Document status

**Статус:** рабочий процессный контракт для разработки crm_bot с AI-агентами / Codex.

**Назначение:** перестать давать AI-агенту задачи в стиле “почини фичу” и заставить его работать через роли, контракты, инварианты, ревью, QA и release gates.

**Источник вдохновения:** процессная модель вроде gstack: виртуальная инженерная команда, где разные AI-режимы отвечают за архитектуру, реализацию, ревью, QA, безопасность и релиз. Этот документ не копирует gstack как зависимость. Он адаптирует саму дисциплину под crm_bot.

**Главная причина:** Codex несколько раз “чинил” document upload pipeline локальными заплатками, потому что задача была сформулирована как багфикс функции, а не как реализация доменного контракта.

**Главный принцип:**

```text
AI не должен угадывать архитектуру.
AI должен исполнять контракт.
```

---

## 1. Core operating rule

Любая нетривиальная работа в crm_bot должна идти по цепочке:

```text
Contract
→ Plan
→ Implementation
→ Adversarial Review
→ QA
→ Release Gate
→ Post-merge Learning
```

Запрещённый режим:

```text
Пойди и почини.
```

Разрешённый режим:

```text
Вот bounded context.
Вот state machine.
Вот commands.
Вот forbidden transitions.
Вот tests.
Реализуй строго это.
```

---

## 2. Roles

AI-работа должна делиться на роли. Один Codex-task не должен одновременно быть архитектором, кодером, ревьюером, QA и release engineer без явного режима.

### 2.1 Contract Architect

Отвечает за:

```text
- доменный словарь;
- bounded context;
- state machine;
- commands;
- transitions;
- invariants;
- forbidden behavior;
- DTO/API contract;
- DB entities;
- required tests.
```

Не пишет production-код фичи, пока контракт не описан.

Результат:

```text
contract document or implementation contract section
state enum
command enum
transition table
allowed actions resolver plan
test matrix
```

---

### 2.2 Implementation Engineer

Отвечает за:

```text
- реализацию уже утверждённого контракта;
- минимальные изменения;
- сохранение поведения вне scope;
- типы;
- tests;
- отсутствие architectural shortcuts.
```

Не имеет права менять доменную семантику без возврата к Contract Architect.

---

### 2.3 Adversarial Reviewer

Отвечает за поиск:

```text
- illegal transitions;
- race conditions;
- stale frontend state;
- hidden publication paths;
- silent data corruption;
- idempotency breaks;
- queue dispatch gaps;
- DB consistency gaps;
- raw provider payload leaks;
- cross-project access bugs;
- missing tests.
```

Должен мыслить как chaos engineer и злой reviewer.

---

### 2.4 QA Operator

Отвечает за сценарии:

```text
- happy path;
- partial failure;
- retry;
- resume;
- fallback path;
- cancel;
- reload page;
- double click;
- two tabs;
- stale state;
- provider error;
- large document;
- regression fixture.
```

QA не оценивает красоту архитектуры. Он проверяет, что пользовательский сценарий не разваливается.

---

### 2.5 DB / Performance Reviewer

Отвечает за:

```text
- query plans;
- indexes;
- transactions;
- row counts;
- vector search cost;
- polling cost;
- pagination;
- N+1 queries;
- lock contention;
- duplicate rows;
- repair/reconcile safety.
```

---

### 2.6 Frontend UX / State Reviewer

Отвечает за:

```text
- backend-owned allowed_actions;
- no local guessing;
- stale errors;
- cache invalidation;
- progress polling;
- large list rendering;
- disabled states;
- warning/danger labels;
- stepper correctness;
- multi-tab behavior.
```

---

### 2.7 Security / Tenant Isolation Reviewer

Отвечает за:

```text
- project_id scoping;
- role checks;
- queue payload consistency;
- document_id guessing;
- manager identity;
- raw diagnostic leaks;
- cross-project merge/source refs;
- frontend-forged action ids.
```

---

### 2.8 Release Engineer

Отвечает за:

```text
- branch freshness;
- focused tests;
- full quality gate;
- migrations;
- OpenAPI/frontend contract alignment;
- no dirty changes after validation;
- PR title/body accuracy;
- rollback notes;
- no unauthorized commits/pushes.
```

---

## 3. Standard AI commands / modes

Эти команды — не обязательно реальные slash-команды. Это режимы постановки задач.

```text
/contract-architect
/plan-review
/implementation
/adversarial-review
/frontend-review
/db-review
/security-review
/qa-review
/ship-gate
/postmortem
```

---

## 4. /contract-architect

Используется до реализации сложной фичи.

### Prompt skeleton

```text
Ты — Contract Architect для crm_bot.

Задача: разработать контракт для bounded context: <NAME>.

Не пиши production-код.
Не предлагай MVP, если задача требует full contract.
Не перепрыгивай к реализации.

Нужно определить:
1. Product purpose.
2. Domain vocabulary.
3. Entities/value objects.
4. States.
5. Commands.
6. Transition table.
7. Forbidden transitions.
8. Error taxonomy.
9. DB entities.
10. API/DTO contract.
11. Frontend state contract.
12. Idempotency/concurrency rules.
13. Security/authorization invariants.
14. Observability events.
15. Required tests.
16. Migration/reconcile implications.

Final output:
- concise architecture contract;
- implementation phases;
- exact tests to add;
- explicit non-goals.
```

### Acceptance

```text
Контракт можно отдать Implementation Engineer без необходимости гадать.
```

---

## 5. /plan-review

Используется перед тем, как Codex начнёт писать код.

### Проверяет

```text
- scope too large / too small;
- hidden semantic ambiguity;
- missing state transitions;
- unclear command names;
- missing edge cases;
- missing tests;
- unsafe DB assumptions;
- frontend/backend contract mismatch;
- migration hazards;
- release risk.
```

### Output format

```text
Verdict: APPROVE / REQUEST CHANGES
Blockers:
Risks:
Missing tests:
Suggested split:
```

---

## 6. /implementation

Используется только после контракта и plan review.

### Hard rules

```text
1. Read-only recon first.
2. Do not patch blindly.
3. Do not create reports unless explicitly requested.
4. Do not commit/push unless explicitly requested.
5. Do not use nano/vim.
6. Use cat EOF commands.
7. Preserve behavior outside scope.
8. Add tests for every invariant touched.
9. Do not weaken existing architecture tests.
10. Do not rename domain concepts casually.
```

### Standard command format

```text
cat << 'EOF' > /tmp/recon.sh
...
EOF
bash /tmp/recon.sh
```

Python:

```text
cat << 'PY' > /tmp/script.py
...
PY
venv/bin/python /tmp/script.py
```

### Output

```text
Changed files
Behavior changes
Tests run
Known risks
No commit/push confirmation
```

---

## 7. /adversarial-review

Используется после реализации и до merge.

### Review mindset

Ищи не “соответствует ли diff промпту”, а:

```text
Как это может сломаться в production?
Как пользователь может нажать не то?
Как worker может упасть посередине?
Как данные могут стать inconsistent?
Как UI может врать?
Как Codex мог обойти контракт формально?
```

### Mandatory questions

```text
1. Есть ли hidden path, который нарушает forbidden transition?
2. Есть ли command, который делает больше, чем обещает название?
3. Есть ли state, который означает две разные вещи?
4. Есть ли endpoint, который enqueue-ит неправильный task?
5. Есть ли task type без dispatcher branch?
6. Есть ли handler, который не маппит ошибки?
7. Есть ли raw provider/traceback leak в UI?
8. Есть ли возможность double-click / duplicate job?
9. Есть ли stale frontend state после mutation?
10. Есть ли document.status, который врёт относительно DB фактов?
11. Есть ли cross-project write/read риск?
12. Есть ли тест, который реально поймал бы исходный инцидент?
```

### Output

```text
Verdict: APPROVE / REQUEST CHANGES
Critical blockers
High-risk issues
Missing tests
Suggested exact fixes
```

---

## 8. /frontend-review

### Проверяет

```text
- allowed_actions owned by backend;
- no local state guessing;
- action labels match semantics;
- danger/fallback actions visually distinct;
- stale errors cleared;
- progress stepper honest;
- polling/backoff sane;
- large lists paginated/virtualized;
- mutation invalidation targeted;
- two-tab/stale version behavior;
- unknown backend action safe handling.
```

### Required frontend contract

```text
UI renders ProgressViewModel.
UI sends commands with expected_state_version where available.
UI does not infer lifecycle transitions from strings.
```

---

## 9. /db-review

### Проверяет

```text
- indexes;
- query plans;
- transaction boundaries;
- duplicate prevention;
- document-level locks;
- idempotency keys;
- state consistency queries;
- retrieval surface correctness;
- migration/backfill;
- repair/reconcile feasibility.
```

### Mandatory DB questions

```text
1. Can this command run twice safely?
2. Can two commands run concurrently on same document?
3. Does this transaction leave half-published state?
4. Are runtime search rows consistent with entry status/visibility?
5. Can document be processed while retrieval surface is empty?
6. Can retry duplicate raw candidates?
7. Can resume duplicate canonical entries?
8. Can merge leave absorbed entries searchable?
```

---

## 10. /security-review

### Проверяет

```text
- project_id scoping everywhere;
- user role checks;
- queue payload tampering;
- document_id from another project;
- curation merge IDs from another document/project;
- manager_user_id vs telegram_chat_id;
- raw diagnostic leaks;
- uploaded document access;
- frontend-forged action ids.
```

### Security invariant

```text
Every command must revalidate project/document ownership in backend or repository layer.
```

---

## 11. /qa-review

### QA levels

#### Quick

```text
happy path only
one focused flow
smoke UI/API
```

#### Standard

```text
happy path
one recoverable failure
one retry/resume
one cancel
one stale reload
focused tests
```

#### Exhaustive

```text
all major states
all commands
provider errors
double-click
two tabs
large data
stale frontend
security negative tests
DB consistency checks
```

### Document pipeline QA scenarios

```text
1. Upload small FAQ md → processed → KCC visible.
2. Upload document → provider fails batch → partial recoverable.
3. Retry failed batches → answer_resolution_pending, no embeddings.
4. Resume → answer resolution → publication → embeddings → processed.
5. Publish fallback → partial_published / warning.
6. Cancel during compiler_running → drafts preserved.
7. Reload page during running job → progress resumes.
8. Double click resume → one job only.
9. Two tabs: retry in one, publish in another → stale command rejected.
10. Old provider error not shown as active after retry success.
```

---

## 12. /ship-gate

Используется перед merge.

### Required checks

Backend:

```text
venv/bin/python -m ruff format --check src tests
venv/bin/python -m ruff check src tests
venv/bin/python -m mypy src
focused pytest for touched area
```

Frontend:

```text
npm --prefix frontend run lint
npm --prefix frontend run type-check
npm --prefix frontend run build
```

Full gate when appropriate:

```text
bash dev_scripts/codex_extended_quality_gate.sh
```

### Release checklist

```text
[ ] Branch updated from main.
[ ] PR title matches diff.
[ ] PR body matches actual behavior.
[ ] No NotImplemented left in user-facing path.
[ ] No fake command names.
[ ] No wrong queue task mapping.
[ ] No raw provider error in UI.
[ ] Migration/backfill considered.
[ ] Rollback notes present.
[ ] No dirty changes after tests.
[ ] No commit/push without explicit user command.
```

---

## 13. /postmortem

Используется после тяжёлого бага.

### Questions

```text
1. What invariant was missing?
2. What contract was ambiguous?
3. What test would have caught it?
4. Which AI prompt allowed wrong interpretation?
5. Which architecture guard should be added?
6. Is repair/reconcile needed for existing data?
7. What release discipline failed?
```

### Output

```text
Incident summary
Root cause
Missing invariant
Missing test
Data repair need
New guard test
Prompt/process change
```

---

## 14. Task classification

Every AI task must be classified before implementation.

### Classes

```text
A. Bug hotfix
B. Contract implementation
C. Refactor
D. Feature
E. Migration/backfill
F. UI/UX improvement
G. Performance work
H. Security fix
I. Release/ops
```

### Rules

```text
Bug hotfix:
  minimal scope, regression test required.

Contract implementation:
  state/command/tests first, behavior second.

Refactor:
  behavior-preserving, focused validation.

Feature:
  requires product contract and domain placement.

Migration:
  requires backfill, rollback, data inspection.

Performance:
  requires before/after measurement or query plan.

Security:
  requires negative tests.
```

---

## 15. Codex anti-patterns

### Anti-pattern 1: adding plumbing without behavior

Example:

```text
endpoint exists
task exists
handler exists
service raises NotImplemented
```

Guard:

```text
test_user_visible_action_has_successful_service_path
```

---

### Anti-pattern 2: fake resume

Example:

```text
resume_processing → publish_ready_answers
```

Guard:

```text
test_resume_processing_never_calls_publish_raw_drafts_without_resolution
```

---

### Anti-pattern 3: local frontend guessing

Example:

```text
if stage === 'answer_resolution_pending' show button
```

Guard:

```text
frontend actions render only backend allowed_actions
```

---

### Anti-pattern 4: status string overload

Example:

```text
pending means queued, waiting, or recoverable
```

Guard:

```text
explicit queued/running/waiting_for_user/completed states
```

---

### Anti-pattern 5: test only enqueue, not execution

Example:

```text
test endpoint enqueues task
but dispatcher/handler/service path broken
```

Guard:

```text
test endpoint → task → dispatcher → handler → service
```

---

## 16. Standard prompt templates

### 16.1 Contract-first implementation prompt

```text
Ты — Implementation Engineer для crm_bot.

Задача: реализовать <CONTRACT_NAME>.

Нельзя:
- менять доменную семантику;
- обходить transition table;
- использовать fallback command как normal path;
- добавлять user-visible action без working backend path;
- оставлять NotImplemented;
- создавать markdown reports;
- коммитить/пушить.

Сначала read-only recon.
Потом реализуй строго:
1. domain state/command/action changes;
2. validators;
3. service/use-case wiring;
4. queue/handler if needed;
5. HTTP endpoint if needed;
6. frontend API/UI if needed;
7. tests for invariants;
8. focused validation.

Final response:
- changed files;
- behavior changes;
- tests run;
- risks;
- no commit/push.
```

---

### 16.2 Adversarial review prompt

```text
Ты — Adversarial Reviewer для crm_bot.

Проверь diff как production incident waiting to happen.

Ищи:
- wrong transitions;
- fake commands;
- hidden publication/embedding paths;
- stale UI;
- duplicate jobs;
- queue dispatch gaps;
- DB inconsistency;
- cross-project access;
- raw error leaks;
- missing tests.

Не исправляй код.
Дай verdict: APPROVE или REQUEST CHANGES.
```

---

### 16.3 Ship gate prompt

```text
Ты — Release Engineer для crm_bot.

Проверь готовность PR к merge.

Проверь:
- branch freshness;
- PR title/body;
- changed files;
- migrations;
- backend checks;
- frontend checks;
- focused tests;
- full gate if appropriate;
- rollback notes;
- no dirty changes.

Не мёржь без явной команды.
```

---

## 17. Required docs in repo

Suggested internal docs:

```text
docs/ai/ai_engineering_workflow_contract_v1.md
docs/architecture/knowledge_document_pipeline_contract_v1.md
docs/architecture/application_contract_audit_v1.md
docs/architecture/conversation_lifecycle_contract_v1.md
docs/architecture/commercial_document_contract_v1.md
docs/architecture/client_answer_composition_contract_v1.md
docs/architecture/live_crm_pipeline_contract_v1.md
```

---

## 18. Current priority stack

Immediate:

```text
1. Finish document pipeline PR safely.
2. Ensure true resume works.
3. Ensure retry does not publish/embed/processed.
4. Ensure progress actions are honest.
```

Next:

```text
1. Implement KnowledgeDocumentPipelineContract v1.
2. Add app-wide contract inventory tests.
3. Add queue task registry tests.
4. Add golden document pipeline scenario test.
```

Then:

```text
1. ConversationLifecycleContract v1.
2. CommercialDocumentContract v1.
3. ClientAnswerCompositionContract v1.
4. LiveCrmPipelineContract v1.
```

---

## 19. Final rule

AI work in this project must become contract-driven.

```text
No contract → no implementation.
No transition table → no lifecycle commands.
No invariant tests → no merge.
No backend-owned actions → no frontend buttons.
No adversarial review → no release.
```

This is how Codex stops guessing.
