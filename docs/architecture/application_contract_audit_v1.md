# Application Contract Audit v1

## Document status

**Статус:** архитектурный аудит текущих контрактов приложения crm_bot.

**Цель:** оценить, насколько приложение уже живёт через явные доменные контракты, а где всё ещё держится на service orchestration, неявных строковых состояниях, размазанных правилах и предположениях. Этот документ нужен как следующий слой после `Knowledge Document Upload Pipeline Contract v1`.

**Непосредственный контекст:** после инцидента с загрузкой документа стало видно, что даже рабочая фича ломается, если в коде нет единой state machine, command model, transition table и executable invariants. Теперь нужно проверить не только document upload pipeline, а всё приложение как набор bounded contexts.

**Методология:** аудит основан на просмотре кода репозитория `Clean1ines/crm_bot` на `main` и текущем известном состоянии веток вокруг document pipeline. Основной акцент на слоях `domain`, `application`, `infrastructure`, `interfaces/http`, `frontend`, `tests/architecture`.

---

## 1. Executive summary

Главный вывод:

```text
В knowledge/RAG части уже есть сильные доменные контракты.
В runtime conversation / manager / future CRM части контракты заметно слабее.
```

Приложение не находится в хаосе. Наоборот, в нём уже есть сильные архитектурные зачатки:

```text
- domain dataclasses/enums для Knowledge Compilation;
- explicit RetrievalSurface eligibility;
- single production embedding text builder;
- KCD architecture tests;
- ports через Protocol;
- KCC domain action/issue vocabulary;
- manager identity separation: canonical manager_user_id vs Telegram transport bridge.
```

Но зрелость контрактов распределена неравномерно:

```text
Knowledge/KCD: зрелый bounded context.
RetrievalSurface: сильный runtime safety contract.
Curation: хороший contract, но только post-publication.
Document upload pipeline: был частично неформализован, сейчас требует отдельного Pipeline Contract v1.
Document parser/business-doc parsing: переходный слой.
Conversation runtime: orchestration-heavy, weak state contract.
Manager handoff: частичный контракт, но не полноценный business workflow.
CRM/live pipeline: почти не оформлен как домен.
Client answer composition: пока не выделен как отдельный contract.
```

Самая важная архитектурная формула для будущего:

```text
Knowledge tells what the business knows.
Commercial documents tell what the business sells and under what conditions.
Conversation/CRM tells who the client is and what should happen next.
Client Answer Composition decides what can be safely said now.
```

---

## 2. What counts as a contract

В этом аудите “контракт” — это не просто тип или DTO.

Контракт считается зрелым, если у него есть хотя бы большая часть следующего:

```text
1. Domain vocabulary:
   explicit names for entities, states, commands, events and policies.

2. Domain objects:
   dataclasses/enums/value objects with validation and invariants.

3. State machine:
   state enum, transition table, command validators.

4. Application ports:
   Protocols/use case interfaces independent from infrastructure.

5. Persistence boundary:
   repository methods that preserve invariants transactionally.

6. UI/API contract:
   backend-owned actions, stable DTOs, no frontend guessing.

7. Error contract:
   typed errors, retryability, user-safe messages, diagnostics.

8. Idempotency/concurrency:
   repeated commands and parallel jobs cannot corrupt state.

9. Executable tests:
   unit tests, integration tests, architecture tests and scenario tests.

10. Operational tools:
    inspect/health/reconcile/audit logs for debugging production states.
```

---

## 3. Contract maturity scale

```text
0 — Missing:
    concept exists only implicitly or as scattered code.

1 — Named:
    concept has a name but no enforceable contract.

2 — Typed:
    dataclasses/enums/DTOs exist, but transitions/invariants are weak.

3 — Guarded:
    some invariants exist in code and tests.

4 — Contract-driven:
    explicit state/command/policy model + executable tests.

5 — Operationally robust:
    contract + idempotency + observability + repair/reconcile tools.
```

---

## 4. Maturity map

| Area                              |                       Maturity | Score | Diagnosis                                                                                              |
| --------------------------------- | -----------------------------: | ----: | ------------------------------------------------------------------------------------------------------ |
| Knowledge Compilation Domain      | Guarded / near contract-driven | 4.0/5 | Strong vocabulary and dataclasses, good invariants, but pipeline state still external.                 |
| Retrieval Surface                 | Contract-driven narrow context | 4.0/5 | Clear eligibility and runtime-safe filtering. Needs DB consistency/health checks.                      |
| Embedding Text                    | Contract-driven narrow context | 4.0/5 | Single builder and architecture tests. Needs deeper runtime mismatch checks.                           |
| Knowledge Curation                |                        Guarded | 3.5/5 | Good action/issue vocabulary, merge/version model. Needs stronger lineage and pre-publication sibling. |
| Document Upload Pipeline          |                  In transition | 2.5/5 | Core domain exists, but pipeline state/commands are being formalized now.                              |
| Document Parser / Structure       |                        Partial | 2.5/5 | Parser port exists, blocks exist, but chunk/draft legacy concepts still leak.                          |
| RAG Eval / Retrieval Review       |             Partial to guarded | 3.0/5 | Product surface is strong, but contract map not fully audited here.                                    |
| Application Ports                 |                        Partial | 3.0/5 | Protocols exist, but mega-ports are too broad.                                                         |
| Queue / Jobs                      |                        Partial | 2.5/5 | Task constants/dispatcher exist, but task registry contract was weak enough to break.                  |
| Runtime Conversation              |                Weak to partial | 2.0/5 | Important orchestration exists, but no full ConversationLifecycle contract.                            |
| Manager Handoff                   |                        Partial | 2.5/5 | Good identity contract; workflow/state contract incomplete.                                            |
| Live CRM Pipeline                 |                 Mostly missing | 1.0/5 | Product direction exists, domain not yet modeled.                                                      |
| Commercial / Price-list Documents |                 Mostly missing | 1.5/5 | Price role exists as knowledge chunk/entry kind, but no commercial document domain.                    |
| Client Answer Composition         |                Mostly implicit | 1.5/5 | Graph execution exists, but no explicit answer composition policy contract.                            |
| Frontend Action Contracts         |                        Partial | 2.5/5 | UI works, but some actions are still inferred locally.                                                 |
| Observability / Reconcile         |                           Weak | 1.5/5 | Logs exist, but no first-class health/reconcile/pipeline events.                                       |

---

## 5. Strongest existing contracts

### 5.1 Knowledge Compilation Domain

Current strength:

```text
SourceDocument
SourceChunk
SourceRef
CompilerRun
CompilerBatch
AnswerCandidate
CandidateCluster
CanonicalKnowledgeEntry
KnowledgeEnrichment
EmbeddingText
EvalCase
KnowledgeEditAction
```

This is the strongest bounded context in the application.

Good signs:

```text
- explicit enums for entry status, visibility, kind, compiler batch status;
- frozen dataclasses with validation;
- AnswerCandidate and CanonicalKnowledgeEntry are separate concepts;
- CanonicalKnowledgeEntry has publishability checks;
- source refs are first-class;
- embedding text is modeled separately from answer;
- enrichment is explicitly non-authoritative positive query surface.
```

Important existing invariant:

```text
CanonicalKnowledgeEntry.is_published_runtime_entry requires:
- status = published
- visibility = runtime
- source refs exist
```

Gap:

```text
SourceDocument.status and processing_stage are still plain strings.
Document lifecycle is not yet a typed state machine.
```

Required upgrade:

```text
Introduce KnowledgeDocumentPipelineState and remove ad-hoc processing_stage strings from active logic.
```

---

### 5.2 Retrieval Surface Contract

Current strength:

```text
canonical_entry_eligibility(entry)
is_canonical_runtime_entry(entry)
filter_canonical_runtime_entries(entries)
```

Good signs:

```text
- retrieval surface eligibility is centralized;
- published/runtime/source-ref-safe requirements are explicit;
- compiler modes are explicitly not entry kinds;
- runtime kinds are whitelisted.
```

This is a good model for other contracts: a small domain function owns eligibility instead of every service guessing.

Gap:

```text
DB/repository should additionally enforce and periodically verify:
- no retrieval_surface rows for hidden/rejected/archived/merged entries;
- retrieval_surface row count matches runtime eligible entries;
- embeddings exist for runtime entries.
```

Required upgrade:

```text
Add KnowledgeRetrievalSurfaceHealth / consistency checks.
```

---

### 5.3 Embedding Text Contract

Current strength:

```text
build_canonical_entry_embedding_text(entry)
build_retrieval_surface_search_text(entry)
CANONICAL_EMBEDDING_TEXT_VERSION
```

Good signs:

```text
- production embedding text has one builder;
- builder uses authoritative title/answer/enrichment;
- raw/preprocessing embedding text is explicitly not authoritative;
- retrieval guards are excluded from positive search text;
- architecture tests protect the single builder path.
```

Gap:

```text
Need health checks for embedding version drift and retrieval surface rows built with stale embedding text version.
```

Required upgrade:

```text
Add embedding_text_version consistency to document/entry health.
```

---

### 5.4 Knowledge Curation Contract

Current strength:

```text
KnowledgeCurationIssueType
KnowledgeCurationActionType
KnowledgeCurationActionStatus
KnowledgeCurationEntryView
KnowledgeCurationSummary
KnowledgeCurationDuplicateGroup
KnowledgeEntryMergeRequest
KnowledgeEntryMergePreview
KnowledgeEntryMergeApplyResult
KnowledgeEntryVersionView
```

Good signs:

```text
- issues are typed;
- actions are typed;
- merge preview/apply are separate;
- versions exist;
- KCC vocabulary includes missing source refs, retrieval mismatch, missing embeddings, merged absorbed entries;
- curation is clearly post-canonical-entry.
```

Gap:

```text
Curation does not cover raw drafts / pre-publication review.
```

Required upgrade:

```text
Create Draft Compilation Review as separate bounded context.
```

---

## 6. Weakest existing contracts

### 6.1 Document Upload Pipeline

Current state:

```text
The domain vocabulary exists, but the pipeline itself was historically spread across:
- document.status
- preprocessing_status
- preprocessing_metrics.stage
- compiler batch statuses
- queue job state
- frontend action rendering
```

Known failure mode:

```text
retry_failed_batches accidentally behaved like publish/resume and triggered embeddings before answer resolution.
```

Required contract:

```text
Knowledge Document Upload Pipeline Contract v1
```

Minimum implementation:

```text
- KnowledgeDocumentPipelineState enum
- KnowledgeDocumentPipelineCommand enum
- explicit transition table
- allowed actions resolver
- progress view model
- command validators
- task registry tests
- golden scenario test
```

Do not consider this solved until tests can prove:

```text
retry_failed_batches never publishes
retry_failed_batches never embeds
retry_failed_batches never marks processed
resume_processing uses shared answer-resolution/publication path
resume_processing never calls fallback publish
processed requires retrieval surface readiness
```

---

### 6.2 Runtime Conversation Contract

Current state:

`ClientMessageService` performs important orchestration:

```text
- get/create client;
- get/create active thread;
- acquire thread lock;
- enforce project rate limit;
- enforce project concurrency limit;
- redirect to manager if manual session exists;
- record user message;
- invoke graph;
- return combined response.
```

But this is mostly service logic, not an explicit conversation lifecycle contract.

Current thread statuses:

```text
active
waiting_manager
manual
closed
```

These are too coarse for live CRM.

Missing domain model:

```text
ConversationLifecycleState
ConversationLifecycleCommand
ConversationTransition
LeadQualificationState
ManagerHandoffState
CommercialIntent
ClientIntent
ConversationOutcome
```

Risk:

```text
Live CRM features will be implemented as scattered conditions inside ClientMessageService, graph nodes and repository methods.
```

Required upgrade:

```text
Create Conversation Lifecycle Contract v1 before live CRM automation.
```

---

### 6.3 Manager Handoff Contract

Current strength:

Manager identity is already better than many parts of the app:

```text
ManagerActor
ManagerReplySession
build_manager_audit_payload
```

Good sign:

```text
manager_user_id is canonical identity;
telegram_chat_id is only a transport bridge.
```

Current gap:

```text
Manager handoff is a session mechanism, not a full workflow state machine.
```

Missing:

```text
ManagerAssignment
ManagerClaim
ManagerSLA
ManagerEscalationPolicy
ManagerAvailability
ManagerHandoffTransition
```

Required upgrade:

```text
Manager Handoff Contract v1
```

States should include:

```text
not_needed
handoff_requested
waiting_manager
manager_claimed
manual_conversation_active
manager_idle_timeout
returned_to_assistant
resolved_by_manager
closed_unresolved
```

Commands:

```text
RequestManagerHandoff
ClaimThread
ReplyAsManager
ReturnToAssistant
CloseAsResolved
MarkManagerIdle
EscalateToOwner
```

---

### 6.4 Commercial / Price-list Document Contract

Current state:

The app has `PRICE_LIST` / `PRICE_ANSWER` / `PRICING_POLICY` concepts as chunk roles or knowledge entry kinds.

This is not enough.

A price-list document is not simply FAQ knowledge. It has structure:

```text
Product / service
Variant
Unit
Base price
Currency
Discount rule
Seasonality
Availability
Package
Add-on
Condition
Validity period
Client segment
Region
Tax / delivery / refund conditions
```

Required new bounded context:

```text
Commercial Document Domain v1
```

Core entities:

```text
CommercialDocument
PriceListDocument
CommercialItem
ProductVariant
ServicePackage
PriceRule
DiscountRule
AvailabilityRule
SeasonalPriceVersion
CommercialCondition
CommercialSourceRef
CommercialFact
CommercialOfferDraft
```

Do not just extend `KnowledgeChunkRole.PRICE_LIST`.

Reason:

```text
FAQ knowledge answers “what should we say?”
Price-list knowledge answers “what exactly is sold, under which constraints, and how should it be quoted?”
```

---

### 6.5 Live CRM Pipeline Contract

Current state:

CRM/live pipeline domain is not yet first-class.

Needed entities:

```text
Lead
LeadSource
LeadQualification
CustomerNeed
Deal
DealStage
PipelineStage
FollowUpTask
CommercialOffer
ConversationToLeadLink
ManagerOwner
SLA
```

Potential state machine:

```text
new_inquiry
needs_clarification
qualified_lead
commercial_intent_detected
price_requested
offer_prepared
manager_needed
manager_assigned
follow_up_scheduled
deal_created
closed_won
closed_lost
spam_or_irrelevant
```

Commands:

```text
QualifyLead
CreateLeadFromConversation
AttachCommercialIntent
CreateCommercialOfferDraft
AssignManager
ScheduleFollowUp
ConvertLeadToDeal
CloseLeadWon
CloseLeadLost
```

Risk if not modeled:

```text
CRM logic will be hidden in graph prompts, manager services and thread metadata.
```

Required upgrade:

```text
Live CRM Pipeline Contract v1
```

---

### 6.6 Client Answer Composition Contract

Current state:

The graph is invoked from `ClientMessageService`, but answer composition is not yet a first-class contract.

Future answer must be composed from several domains:

```text
user_message
conversation_state
client profile / lead state
commercial facts
knowledge entries
manager policy
safety/escalation policy
available actions
```

Target formula:

```text
ClientAnswer = f(
  user_message,
  conversation_state,
  commercial_facts,
  knowledge_entries,
  crm_pipeline_state,
  manager_policy
)
```

Needed contract:

```text
ClientAnswerCompositionContract v1
```

Core objects:

```text
ClientAnswerRequest
ClientAnswerContext
KnowledgeEvidence
CommercialEvidence
ConversationStateEvidence
CRMActionSuggestion
EscalationDecision
AnswerPolicy
ClientAnswerDraft
DeliveryPlan
```

Without this, the agent will start mixing:

```text
RAG evidence
prices
CRM stage
manager instructions
conversation history
```

inside prompts with weak guarantees.

---

## 7. Cross-cutting contract gaps

### 7.1 Mega ports

`KnowledgeRepositoryPort` is too broad.

Current risk:

```text
Any knowledge-related use case can call any repository method.
```

Suggested split:

```text
KnowledgeDocumentRepositoryPort
KnowledgeSourceChunkRepositoryPort
KnowledgeCompilerRunRepositoryPort
KnowledgeDraftRepositoryPort
KnowledgePublicationRepositoryPort
KnowledgeRetrievalSurfaceRepositoryPort
KnowledgeCurationRepositoryPort
KnowledgeSearchRepositoryPort
KnowledgeModelUsageRepositoryPort
```

Benefit:

```text
Use cases can only access the persistence surface they actually need.
```

---

### 7.2 God repositories

`knowledge_repository.py` is a strong but overloaded DB boundary.

Current risk:

```text
search, preview search, curation, retighten, source chunks, candidates, entries, usage and row mappers live together.
```

Suggested split:

```text
repositories/knowledge/documents.py
repositories/knowledge/source_chunks.py
repositories/knowledge/compiler_runs.py
repositories/knowledge/drafts.py
repositories/knowledge/publication.py
repositories/knowledge/retrieval_surface.py
repositories/knowledge/curation.py
repositories/knowledge/search.py
repositories/knowledge/health.py
```

Keep compatibility facade while splitting.

---

### 7.3 Queue task registry weakness

A previous bug pattern happened:

```text
task type exists
but not in KNOWN_TASK_TYPES
or dispatcher does not route it
or handler import is wrong
```

Required generic test:

```text
test_all_known_task_types_have_dispatch_branch
test_all_enqueued_task_types_are_known
test_all_task_handlers_validate_payload
```

---

### 7.4 UI action inference

Any local frontend inference of actions is a future bug.

Rule:

```text
Frontend renders backend-owned allowed_actions.
Frontend never decides that resume/retry/publish is allowed from local stage strings.
```

---

### 7.5 Error strings vs typed errors

Raw exception messages currently can leak into user-facing state.

Target:

```text
ApplicationErrorCode
retryable
user_message
technical_message
safe_diagnostics
```

This should apply not only to LLM provider errors, but also to:

```text
queue errors
repository consistency errors
CRM command conflicts
manager handoff conflicts
commercial price parsing errors
```

---

### 7.6 No global command/event model

Knowledge pipeline needs `document_pipeline_events`.

But the whole app will eventually need domain events:

```text
KnowledgeDocumentUploaded
CompilerBatchFailed
KnowledgeCompilationResumed
CanonicalEntriesPublished
RetrievalSurfaceBuilt
ClientMessageReceived
ConversationQualified
ManagerHandoffRequested
ManagerClaimedThread
CommercialIntentDetected
LeadCreated
OfferDrafted
```

This is especially important for live CRM.

---

## 8. Contract inventory by bounded context

### 8.1 Knowledge Compilation

Current artifacts:

```text
src/domain/project_plane/knowledge_compilation.py
src/domain/project_plane/knowledge_preprocessing.py
src/application/ports/knowledge_port.py
src/application/services/knowledge_ingestion_service.py
src/infrastructure/db/repositories/knowledge_repository.py
```

Strength:

```text
High vocabulary maturity.
```

Missing:

```text
Pipeline state machine.
Publication manifest.
Lineage completeness.
Decision log.
```

Priority:

```text
Immediate.
```

---

### 8.2 Retrieval Surface

Current artifacts:

```text
src/domain/project_plane/knowledge_retrieval_surface.py
src/domain/project_plane/embedding_text.py
src/infrastructure/db/repositories/knowledge_repository.py
src/infrastructure/db/repositories/rag_eval_repository.py
```

Strength:

```text
Strong runtime safety policy.
```

Missing:

```text
Health checks.
Surface mismatch diagnostics.
Embedding version drift checks.
```

Priority:

```text
High.
```

---

### 8.3 Knowledge Curation

Current artifacts:

```text
src/domain/project_plane/knowledge_curation.py
src/application/services/knowledge_curation_service.py
src/interfaces/http/knowledge_curation.py
frontend/src/shared/api/modules/knowledgeCuration.ts
frontend/src/pages/rag-eval/components/KnowledgeCurationConsole.tsx
```

Strength:

```text
Good post-publication manual correction contract.
```

Missing:

```text
Pre-publication Draft Review.
Entry lineage.
Resolution decision log.
Source ref edit policy.
```

Priority:

```text
Medium-high.
```

---

### 8.4 Document Parsing / Business Document Intake

Current artifacts:

```text
src/application/ports/knowledge_document_parser_port.py
src/domain/project_plane/knowledge_document_structure.py
src/domain/project_plane/knowledge_chunks.py
```

Strength:

```text
Parser port exists and is clean.
Parsed document blocks exist.
```

Weakness:

```text
Still chunk/draft-oriented.
Price-list is just a role/kind, not a business document model.
```

Priority:

```text
High before price-list feature work.
```

---

### 8.5 Conversation Runtime

Current artifacts:

```text
src/application/orchestration/client_message_service.py
src/domain/project_plane/thread_status.py
src/domain/project_plane/thread_runtime.py
```

Strength:

```text
Operational orchestration exists.
Thread locking and runtime guards are present.
```

Weakness:

```text
Lifecycle state machine absent.
ThreadStatus too coarse.
Client answer composition implicit.
```

Priority:

```text
High before live CRM.
```

---

### 8.6 Manager Handoff

Current artifacts:

```text
src/domain/project_plane/manager_assignments.py
src/application/orchestration/client_message_service.py
manager reply services / ticket command services
```

Strength:

```text
Canonical manager identity separated from Telegram transport.
```

Weakness:

```text
Manager handoff workflow not fully modeled.
```

Priority:

```text
Medium-high.
```

---

### 8.7 Live CRM Pipeline

Current artifacts:

```text
Not first-class yet.
```

Missing:

```text
Lead
Deal
PipelineStage
Qualification
CommercialIntent
FollowUp
Offer
SLA
```

Priority:

```text
High before live CRM automation.
```

---

### 8.8 Commercial / Price-list Knowledge

Current artifacts:

```text
KnowledgeEntryKind.PRICE_ANSWER
KnowledgeEntryKind.PRICING_POLICY
KnowledgeChunkRole.PRICE_LIST
```

Weakness:

```text
These are knowledge labels, not commercial document contracts.
```

Priority:

```text
High before price-list document processing.
```

---

### 8.9 Client Answer Composition

Current artifacts:

```text
Graph execution request path exists indirectly through ClientMessageService.
```

Weakness:

```text
No explicit contract for combining knowledge evidence, commercial facts, conversation state and CRM action suggestions.
```

Priority:

```text
Very high before combining FAQ + price-list + CRM behavior.
```

---

## 9. Future domain architecture

Target bounded contexts:

```text
Knowledge Compilation Domain
  What does the business know?

Commercial Document Domain
  What does the business sell and under what conditions?

Conversation Lifecycle Domain
  What is happening with this client conversation?

CRM Pipeline Domain
  What business process state is this client/lead/deal in?

Client Answer Composition Domain
  What can the assistant safely and usefully say now?

Manager Handoff Domain
  When should a human take over and how is it controlled?
```

Important relationship:

```text
FAQ knowledge and price-list knowledge should not be merged into one amorphous RAG blob.
They should meet at Client Answer Composition.
```

Example:

```text
User asks: “Сколько стоит внедрение и можно ли начать с малого?”

Answer composition should combine:
- FAQ/policy knowledge: what product is and boundaries;
- commercial facts: packages, price rules, discounts, validity;
- conversation state: new lead vs existing client;
- CRM state: qualification needed or offer can be drafted;
- manager policy: when to escalate;
- answer policy: what cannot be promised.
```

---

## 10. What must happen before live CRM / price-list features

Do not build live CRM directly on current conversation orchestration.

First implement:

```text
1. ConversationLifecycleContract v1
2. CommercialDocumentContract v1
3. PriceListKnowledgeContract v1
4. ClientAnswerCompositionContract v1
5. LiveCrmPipelineContract v1
```

Otherwise future failures will mirror the document pipeline failure:

```text
features work locally
state is implicit
commands overlap
UI guesses
Codex patches symptoms
```

---

## 11. Recommended roadmap

### Phase A — Finish document pipeline contract

```text
1. Finish true resume technical blockers.
2. Add KnowledgeDocumentPipelineState / Command / transition table.
3. Make progress report use allowed actions resolver.
4. Add golden scenario tests.
5. Add task registry tests.
```

### Phase B — App-wide contract inventory tests

```text
1. Create tests/architecture/test_contract_inventory.py.
2. Assert expected domain contract modules exist.
3. Assert no forbidden imports in domain.
4. Assert no new string stages outside contract modules.
5. Assert queue task registry consistency.
```

### Phase C — Conversation Lifecycle Contract v1

```text
1. Expand ThreadStatus or introduce ConversationLifecycleState.
2. Define commands and transitions.
3. Extract lifecycle decisions out of ClientMessageService where possible.
4. Add tests for manager handoff, stale session, active thread rollover, return to assistant.
```

### Phase D — Commercial Document Contract v1

```text
1. Add commercial domain module.
2. Model PriceListDocument, CommercialItem, PriceRule, DiscountRule, ValidityPeriod.
3. Keep it separate from generic KnowledgeChunkRole.
4. Add parser contract for commercial docs.
```

### Phase E — Client Answer Composition Contract v1

```text
1. Define answer context objects.
2. Define evidence types: knowledge evidence, commercial evidence, CRM evidence.
3. Define answer policy and escalation decision.
4. Make graph request consume structured context instead of loose payload.
```

### Phase F — Live CRM Pipeline Contract v1

```text
1. Define Lead, Deal, PipelineStage, FollowUpTask.
2. Define commands: qualify, create lead, assign manager, create offer, schedule follow-up.
3. Wire conversation lifecycle to CRM commands.
```

---

## 12. Anti-Codex contract strategy

Codex must not be allowed to infer behavior from nearby code.

Every future task should be framed like:

```text
Implement command X in contract Y.
It must transition from state A to state B through transition table Z.
It must not call forbidden function F.
Add tests proving the invariant.
```

Bad prompt:

```text
Сделай обработку прайслиста.
```

Good prompt:

```text
Implement CommercialDocumentContract v1 for price-list documents.
Do not route price-list parsing through generic FAQ chunks.
Create PriceListDocument, CommercialItem, PriceRule and DiscountRule.
Expose extracted commercial facts to ClientAnswerComposition as CommercialEvidence.
Add architecture tests preventing price-list facts from being stored only as generic FAQ answers.
```

---

## 13. Highest-risk areas if ignored

### Risk 1 — Price-list as FAQ

If price-list documents are treated as FAQ chunks, the assistant will answer prices as free text instead of structured commercial facts.

Consequence:

```text
wrong prices
wrong discounts
outdated seasonal conditions
hard-to-audit commercial promises
```

### Risk 2 — CRM state inside prompts

If CRM pipeline is just prompt text, it will be hard to prove why assistant escalated, qualified, created lead or suggested follow-up.

### Risk 3 — Manager handoff as Redis session only

If manager handoff remains mostly Redis/session logic, business SLA and lifecycle cannot be audited.

### Risk 4 — Client answer without composition contract

If answer composition is not explicit, FAQ evidence, price evidence and CRM actions will mix inside graph logic.

### Risk 5 — Repository mega-port growth

If repository/ports are not split, every new domain will keep adding methods to `KnowledgeRepositoryPort` and `knowledge_repository.py`.

---

## 14. Definition of done for Application Contract Audit follow-up

This audit becomes actionable when the repo has:

```text
[ ] Knowledge Document Pipeline Contract v1 implemented in code
[ ] Contract inventory test added
[ ] Queue task registry test added
[ ] ConversationLifecycleContract v1 draft added
[ ] CommercialDocumentContract v1 draft added
[ ] ClientAnswerCompositionContract v1 draft added
[ ] Architecture tests preventing commercial docs from becoming generic FAQ chunks
[ ] Progress/action rendering driven by backend allowed_actions
[ ] At least one golden scenario test for document pipeline
[ ] At least one scenario test for manager handoff lifecycle
```

---

## 15. Final recommendation

Do not jump directly from document pipeline hardening into live CRM features.

Recommended immediate sequence:

```text
1. Finish and merge safe document pipeline hotfix / true resume.
2. Implement KnowledgeDocumentPipelineContract v1.
3. Add app-wide contract inventory tests.
4. Draft ConversationLifecycleContract v1.
5. Draft CommercialDocumentContract v1.
6. Draft ClientAnswerCompositionContract v1.
7. Only then start live CRM and price-list document processing.
```

The project is already evolving from “бот с базой знаний” into:

```text
knowledge lifecycle engine
+ commercial fact engine
+ conversation lifecycle engine
+ CRM action engine
+ answer composition engine
```

The next engineering discipline step is to make each of these an explicit bounded context before adding more behavior.

---

## 16. Audit gap disclosure

This document is intentionally broad, but it must not pretend to cover every possible invariant, edge case, frontend performance issue, DB performance issue, operational failure, security concern or migration hazard.

The previous sections cover the main architectural contract gaps. They do not fully enumerate:

```text
frontend rendering performance
frontend stale state / cache invalidation performance
DB query plans and indexes
DB locking / transaction isolation
multi-tenant authorization invariants
API compatibility/versioning
migration/backfill/reconcile plans
provider cost/budget enforcement
observability SLIs/SLOs
load testing
accessibility
browser/session edge cases
security/privacy controls
```

Therefore, Application Contract Audit v1 must be extended by dedicated deep-dive appendices before it is treated as complete enough for implementation planning.

---

## 17. Frontend performance and UX discipline appendix

### 17.1 Main risk

The frontend can become slow or misleading when documents produce hundreds of drafts, dozens of canonical entries, many review questions and frequent progress polling.

Risk pattern:

```text
large document
→ many drafts / entries / questions
→ progress polling
→ repeated query invalidation
→ huge React re-renders
→ stale error/action state
→ user clicks outdated action
```

### 17.2 Required frontend invariants

```text
1. Progress card renders backend-owned state, not local guessed state.
2. Allowed actions come only from backend `allowed_actions`.
3. Frontend never shows `last_error` as active fatal error.
4. On any mutation, relevant queries are invalidated exactly once and refetched deliberately.
5. Large draft/entry/question lists are paginated or virtualized.
6. Drawers must not keep stale entry/action state after document state changes.
7. A running command disables conflicting actions immediately.
8. Multiple clicks on the same command must not enqueue duplicate jobs.
9. UI must show `queued`, `running`, `waiting_for_user`, `failed`, `completed` distinctly.
10. Progress polling must back off when no active job exists.
```

### 17.3 Frontend performance requirements

```text
Draft list:
  must support 500+ drafts without freezing.

Curation entries:
  must support 200+ entries without full page re-render on every filter change.

Review questions:
  must support 1,000+ generated/review questions with pagination/virtualization.

Progress polling:
  must not invalidate every knowledge-related query on every tick.

Mutations:
  must use targeted invalidation:
    - progress
    - documents list
    - drafts/source units when relevant
    - curation only when canonical entries changed
    - retrieval review only when retrieval surface changed
```

### 17.4 Frontend edge cases

```text
- user opens page in two browser tabs;
- user clicks retry in one tab and publish fallback in another;
- page reloads while job is running;
- network request succeeds but toast fails or UI cache remains stale;
- progress response changes schema after deploy;
- old browser tab has outdated state_version;
- uploaded document is deleted/cleared while progress panel is open;
- curation drawer is open while entry is archived/merged by another action;
- mutation returns job id but worker fails before progress changes;
- frontend receives unknown action id from backend.
```

### 17.5 Frontend tests

```text
- progress view model renders every pipeline state correctly;
- action rendering uses backend allowed_actions only;
- stale provider error disappears when active_error is null;
- resume_processing and publish_raw_drafts_without_resolution are visually distinct;
- double click on action does not issue two mutations;
- large list rendering remains bounded through pagination/virtualization;
- unknown backend action is shown safely or ignored with diagnostic warning;
- query invalidation map is tested per command.
```

---

## 18. DB performance and consistency appendix

### 18.1 Main risk

The DB will become the bottleneck when knowledge, retrieval review, curation and live CRM start sharing the same project runtime.

Risk pattern:

```text
large document
→ many source chunks
→ many raw candidates
→ many canonical entries
→ embeddings
→ retrieval surface rows
→ RAG eval questions
→ curation actions
→ repeated progress/preview/search queries
```

### 18.2 Required DB invariants

```text
1. Runtime retrieval reads only retrieval surface, not raw candidates.
2. Retrieval surface contains only published/runtime/source-ref-safe entries.
3. Hidden/rejected/merged/archived entries have no active retrieval surface rows.
4. Processed document has canonical entries and retrieval surface readiness.
5. Raw candidates are linked to compiler_run_id and compiler_batch_id.
6. Re-running retry does not duplicate raw candidates for the same batch.
7. Re-running resume does not duplicate canonical entries.
8. Rebuilding embeddings is idempotent by entry_id/version/embedding_text_version.
9. Publication and retrieval surface update happen transactionally or through recoverable staged states.
10. Partial publish has explicit DB state and cannot masquerade as normal processed.
```

### 18.3 DB index checklist

Indexes should exist or be planned for:

```text
knowledge_documents:
  project_id
  status
  preprocessing_status
  uploaded_by
  created_at

knowledge_source_chunks:
  project_id, document_id
  document_id, chunk_index

knowledge_compiler_runs:
  project_id, document_id
  status
  created_at

knowledge_compiler_batches:
  project_id, document_id
  compiler_run_id
  status
  batch_index
  document_id, status

knowledge_answer_candidates:
  project_id, document_id
  compiler_run_id
  batch_id
  status
  topic_key
  document_id, batch_id, candidate_index/stable_key unique where possible

knowledge_entries:
  project_id, document_id
  status, visibility
  stable_key
  document_id, stable_key
  updated_at

knowledge_entry_source_refs:
  entry_id
  document_id
  source_chunk_id

knowledge_retrieval_surface:
  project_id
  document_id
  entry_id unique
  status, visibility
  entry_kind
  embedding vector index
  search_text tsvector / generated index if used

knowledge_edit_actions:
  project_id, document_id
  target_entry_id
  action_type
  created_at

execution_queue:
  task_type
  status
  payload->document_id if JSONB indexed or extracted column
  created_at
  idempotency_key unique where possible
```

### 18.4 Query plan requirements

High-risk queries must be checked with `EXPLAIN ANALYZE` on realistic data:

```text
- runtime retrieval search;
- preview_search;
- progress report for a large document;
- list drafts/source units;
- curation entry list with filters;
- duplicate detection / curation summary;
- RAG eval load_document_entries;
- active queue job lookup by document_id;
- health/reconcile document inspection.
```

### 18.5 Transaction and isolation requirements

```text
Publication:
  canonical entries + source refs + retrieval surface updates must not leave half-published runtime state.

Retighten/merge:
  parent update + absorbed archive + retrieval surface delete/upsert must be atomic.

Resume:
  should acquire document-level lock or command lock before publication.

Retry:
  candidate deletion/replacement per failed batch must be atomic.

Cancel:
  must not interrupt a transaction halfway; use cancellation requested state if needed.
```

### 18.6 DB edge cases

```text
- duplicate stable_key after answer resolution;
- compiler batch completed but candidates missing;
- candidates exist but compiler batch status failed;
- document processed but retrieval surface empty;
- retrieval surface row points to hidden entry;
- source refs point to deleted source chunks;
- entry has embedding_text_version mismatch;
- migration creates new tables but old rows lack lineage;
- failed transaction leaves document.status processing forever;
- partial publish later gets normal resume attempted.
```

---

## 19. Backend performance and job orchestration appendix

### 19.1 Main risk

LLM calls, local embeddings, queue retries and progress polling can overload Render/free-tier resources.

### 19.2 Required backend performance invariants

```text
1. Large documents are processed in bounded batches.
2. LLM retry budget is bounded.
3. Embedding batch size is bounded and configurable.
4. No heavy embedding/LLM model import at app startup.
5. Queue workers do not run unlimited concurrent heavy jobs.
6. Progress report must be cheap enough for polling.
7. RAG eval must not run concurrently with heavy document ingestion for same project unless allowed.
8. Search/preview must have limits and candidate caps.
9. Provider over-capacity produces retryable partial state, not retry storm.
10. Local embedding model load is cached but not imported in lightweight routes.
```

### 19.3 Backpressure policy

```text
Per project:
  max active ingestion jobs
  max active rag eval jobs
  max active retighten jobs

Per worker:
  max active LLM jobs
  max active embedding jobs

Per provider:
  max retry attempts
  cooldown after repeated 503/429
  fallback model policy
```

### 19.4 Job orchestration edge cases

```text
- worker crashes after completing compiler batch but before status update;
- worker crashes after publication but before document processed update;
- worker crashes during embeddings;
- duplicate job exists for same document/command;
- retry job starts while resume job is queued;
- publish fallback starts while answer resolution is running;
- cancel arrives during non-cancellable DB transaction;
- provider retry succeeds after user cancels;
- active job row says running but worker is dead.
```

---

## 20. Security, authorization and tenant isolation appendix

### 20.1 Main risk

Knowledge and CRM data are tenant-sensitive. A contract bug must not allow cross-project reads or actions.

### 20.2 Required security invariants

```text
1. Every document/action/query is scoped by project_id.
2. Every user action checks project role/admin rights.
3. Queue payload includes project_id and document_id; handler revalidates consistency.
4. Repository writes verify document belongs to project_id.
5. Retrieval search never returns entries from another project.
6. Curation actions cannot modify entries outside project/document.
7. Manager actions use canonical manager_user_id, not Telegram chat_id as authority.
8. Technical diagnostics never expose secrets, tokens, DB URLs or provider raw sensitive payloads.
9. Uploaded documents are not exposed through public URLs without authorization.
10. Frontend cannot enable hidden admin actions by forging action id.
```

### 20.3 Security edge cases

```text
- user guesses document_id from another project;
- queue payload is malformed or project_id/document_id mismatch;
- manager Telegram chat_id belongs to legacy flow but no canonical manager_user_id;
- stale browser tab sends command after user role was revoked;
- technical error includes provider headers or environment secrets;
- curation merge request includes absorbed_entry_id from another project;
- retrieval preview endpoint bypasses runtime/project filters.
```

---

## 21. API compatibility and schema evolution appendix

### 21.1 Main risk

Frontend and backend can deploy out of sync, especially when progress report and allowed actions evolve.

### 21.2 Requirements

```text
1. Progress response should include schema_version.
2. Unknown action ids must be safely ignored or rendered as disabled diagnostic actions.
3. Unknown states must produce safe generic state, not crash.
4. Frontend types must be regenerated or manually aligned after backend DTO changes.
5. Deprecated actions should remain supported for at least one deploy cycle or be mapped server-side.
6. API tests should assert exact progress/action payloads for major states.
```

### 21.3 Edge cases

```text
- old frontend sees new state;
- new frontend expects action not returned by old backend;
- browser cache serves old JS bundle after backend deploy;
- progress response misses optional fields;
- action kind enum gets new value;
- user keeps tab open through deployment.
```

---

## 22. Migration, backfill and repair appendix

### 22.1 Main risk

Existing documents may already be in inconsistent states from older pipeline bugs.

### 22.2 Required migration discipline

```text
1. New state columns/metrics require backfill plan.
2. Backfill must classify old documents into pipeline states.
3. Ambiguous old states should become needs_reconcile, not processed.
4. Migration should not assume all processed docs have retrieval surface rows.
5. Repair scripts must be idempotent.
6. Every destructive repair needs dry-run mode.
```

### 22.3 Reconcile categories

```text
safe_auto_repair:
  stale active_error after successful retry;
  failed_count = 0 but stage still partial_failed;

needs_manual_review:
  document processed but canonical entries missing;
  multiple compiler_run_id values for same document;

unsafe_auto_repair:
  source chunks missing but entries exist;
  retrieval surface points to missing entry;
```

---

## 23. Observability appendix

### 23.1 Required events

```text
KnowledgeDocumentUploaded
SourceUnitsCreated
CompilerRunCreated
CompilerBatchStarted
CompilerBatchCompleted
CompilerBatchFailed
RetryFailedBatchesRequested
RetryFailedBatchesCompleted
AnswerResolutionStarted
AnswerResolutionCompleted
CanonicalEntriesPublished
EmbeddingsStarted
EmbeddingsCompleted
RetrievalSurfaceUpdated
PipelineProcessed
PipelineFailed
PipelineCancelled
PipelineReconciled
```

### 23.2 Required metrics

```text
ingestion_duration_seconds
compiler_batch_duration_seconds
compiler_failed_batch_count
llm_provider_error_count by code/model
embedding_duration_seconds
retrieval_surface_row_count
progress_poll_count
queue_job_duration_seconds
queue_job_retry_count
frontend_action_error_count
```

### 23.3 Required logs

Every stage transition log should include:

```text
project_id
document_id
job_id
command
from_state
to_state
stage
counts snapshot
error_code if any
```

No secrets.

---

## 24. Load and scale testing appendix

### 24.1 Required load fixtures

```text
small markdown: 5 source units
medium markdown: 75 source units
large markdown: 250 source units
duplicate-heavy markdown: 100 overlapping drafts
price-list-like document: 500 items
retrieval review: 1,000 questions
curation: 300 entries
```

### 24.2 Required performance checks

```text
- upload and progress response latency;
- draft list render time;
- curation list filter/sort time;
- retrieval search latency;
- RAG eval generation/runtime;
- embedding memory usage;
- DB query plan under realistic row counts.
```

---

## 25. Accessibility and usability appendix

### 25.1 Required UI behavior

```text
1. All actions have clear labels and warnings.
2. Dangerous fallback publish is visually secondary/warning.
3. Stepper state is understandable without color only.
4. Long-running jobs show elapsed time and last update.
5. Error messages explain what happened and what to do next.
6. Technical diagnostics are collapsible.
7. Draft/curation tables are keyboard navigable.
8. Toasts are not the only source of important state.
```

---

## 26. Additional definition of completeness

Application Contract Audit v1 should be considered complete only when separate deep-dive checklists exist for:

```text
[ ] Domain invariants
[ ] State transitions
[ ] Command validators
[ ] Error taxonomy
[ ] Frontend performance
[ ] DB performance and indexes
[ ] Query plans
[ ] Queue idempotency and locks
[ ] Security/authorization
[ ] API compatibility
[ ] Migration/backfill/repair
[ ] Observability
[ ] Load testing
[ ] Accessibility
```

The current document is an architecture audit, not a formal proof that every possible edge case is handled.
