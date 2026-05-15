# crm_bot Domain Map v1

## Document status

Status: target domain map / architectural contract.

This document is not a migration plan and not a rewrite request. It defines the
bounded contexts and source-of-truth boundaries that should guide future changes.

The current project already contains a business conversation runtime, KCD/RAG,
manager handoff, project configuration, tools, clients, threads, memory, queue
jobs, and evaluation flows. The next architectural risk is not missing code. The
risk is mixing different domains under generic names such as `pricing`,
`tool_result`, `knowledge_chunks`, or `preprocessing_mode`.

## Design stance

crm_bot is not just a chatbot with RAG.

crm_bot is a business conversation runtime that coordinates:

- customer messages;
- project configuration and policies;
- compiled knowledge;
- commercial/pricing facts;
- live CRM/operational state;
- tool execution;
- manager handoff;
- answer generation;
- audit and evaluation.

The LLM is not a source of truth. It is an interpreter, router, summarizer, and
answer composer. Domain/application code must decide what evidence is valid,
which source is authoritative, and what actions are safe.

## Bounded contexts

### Project / Tenant Context

Owns project identity, membership, roles, channels, integrations, limits,
settings, policies, and prompt configuration.

It does not own customer conversations, knowledge compilation, or live CRM facts,
but it provides configuration and permissions for them.

### Channel / Messaging Context

Owns external message ingress and delivery: Telegram client bot, manager bot,
future channels, webhook metadata, transport-level delivery status.

It does not decide business truth. It transports messages and delivery events.

### Conversation Runtime Context

Owns threads, turns, runtime state, dialog state, recent history, graph execution,
locks, sessionization, and message-level orchestration.

It must not treat retrieval results as the final answer. It should build an
evidence plan, gather evidence, apply policy, then compose or escalate.

### Customer / Contact Context

Owns project-scoped contacts, channel identities, client profiles, customer memory
and relationship continuity across conversations.

It is the source of truth for who is speaking when identity is resolved. It is not
the source of truth for prices, stock, or policy documents.

### Knowledge Compilation Context

Owns SourceDocument -> SourceChunk -> SourceRef -> CompilerRun ->
AnswerCandidate -> CandidateCluster -> CanonicalKnowledgeEntry ->
KnowledgeEnrichment -> EmbeddingText -> EmbeddingVector -> RetrievalSurface.

Production retrieval row means grounded canonical semantic answer entry.

This context must not publish raw technical chunks, eval cases, prompt/debug
artifacts, generated standalone questions, or live CRM state as production
knowledge.

#### Current FAQ compiler implementation

FAQ preprocessing is implemented as a question-first answer compiler, not as a
title-first card generator. The active FAQ path is intentionally simple:

1. technical source chunks are processed in small batches;
2. the application keeps compiled canonical entries in memory for the current
   document;
3. before each compiler call it sends compact `known_question_intents` built
   from already compiled entries: stable internal intent id, canonical question,
   realistic question variants, and a short answer digest;
4. `knowledge_answer_compiler_faq.txt` returns answer fragments, either
   `match.kind = "new"` or `match.kind = "known"`;
5. only `known` fragments call `knowledge_answer_merge.txt`, which receives the
   existing canonical answer and the incoming grounded fragment and returns one
   replacement answer when `merge_allowed = true`;
6. new fragments become separate canonical entries.

`canonical_question` is the identity signal for FAQ answer intent. `title` is
display metadata for UI/legacy persistence only. Previous answer titles, entry
titles, tags, synonyms, and embedding text must not be sent to the FAQ compiler
as identity or matching context. If storage still needs synonyms/tags/embedding
text, application/domain code derives compatibility values deterministically
from display title, canonical question, question variants, and answer.

Semantic retightening is a late optional sanity/cleanup pass for suspicious
duplicates or overmerge cases. It is not the primary document-understanding
compiler and must not be required for a successful FAQ first pass.

### Commercial Catalog / Pricing Context

Owns commercial facts extracted from price lists, tables, catalogs, tariff grids,
delivery matrices, product/service lists, and future live catalog adapters.

Core concepts:

- Product / Service / Offer;
- VariantAxis;
- PricePoint;
- PriceFact;
- OfferGroup;
- QuoteInput;
- MissingSlot;
- PriceQueryIntent.

A price-list document can be a source of commercial facts, but it is not always
the live source of truth.

### CRM Operational Context

Owns live business state: current customer, deal/order status, live price
overrides, discounts, availability, stock, booking slots, assigned manager,
current ticket state, and external CRM sync state.

Live CRM facts must not be stored as ordinary retrieval surface rows unless they
are explicitly compiled into a snapshot with freshness metadata.

### Evidence / Source Authority Context

Owns the answer-time evidence model and source priority rules.

Examples:

- live CRM price beats uploaded stale price list;
- manager override beats generated assistant text;
- policy document beats LLM reasoning;
- user message can provide user facts, but cannot override business policy;
- LLM reasoning never becomes authoritative evidence.

### Answer Orchestration Context

Owns source routing and final answer composition:

1. classify user intent;
2. determine required evidence;
3. collect retrieval and/or operational evidence;
4. resolve source authority conflicts;
5. request missing slots if needed;
6. decide whether an action is allowed;
7. generate final answer or escalate.

The answer is not "the RAG result". The answer is the result of orchestration
across evidence, policy, state, and tools.

### Human Operations / Handoff Context

Owns escalation, assignment, manager reply sessions, manual status, manager
notifications, SLA/follow-up semantics, and manager-visible reasons.

It distinguishes:

- user requested a human;
- assistant lacks evidence;
- assistant lacks permission;
- safety/anger/repeat policy escalated;
- operational task requires manager confirmation.

### Action Safety / Approval Context

Owns rules for executable actions:

- create ticket;
- send message;
- update CRM;
- calculate quote;
- apply discount;
- cancel booking;
- close thread;
- mutate memory;
- update knowledge.

LLM proposes. Application/domain policy approves. Infrastructure executes.

### Evaluation Context

Owns quality checks beyond basic RAG retrieval:

- RetrievalEval;
- PriceAnswerEval;
- SourceRoutingEval;
- SlotFillingEval;
- CRMToolUseEval;
- ConflictResolutionEval;
- HandoffEval;
- ActionSafetyEval.

RAG eval must test the production retrieval surface, but whole-system eval must
also test routing, authority, missing slots, and safe actions.

### Audit / Observability Context

Owns durable traces of:

- what evidence was used;
- which source won;
- which source was rejected;
- why a manager was called;
- which tool was executed;
- which policy blocked an action;
- what was sent to the customer.

## Source-of-truth rules

1. Live CRM/operational source is authoritative for current operational state.
2. Compiled price-list knowledge is authoritative for the document snapshot it was
   compiled from, not automatically for current business state.
3. Compiled FAQ/policy knowledge is authoritative for stable published rules.
4. Customer memory is useful context, not a replacement for live CRM state.
5. Manager override is authoritative within its scope and should be auditable.
6. LLM output is never authoritative evidence.
7. Retrieval surface is a production answer surface, not a dump of every artifact.
8. If evidence conflicts and no policy resolves it, the assistant should disclose
   uncertainty or escalate instead of guessing.

## Commercial answer rules

A commercial answer can require:

- exact item lookup;
- variant lookup;
- missing-slot clarification;
- range/minimum price answer;
- quote calculation;
- comparison;
- availability check;
- customer-specific price;
- live CRM verification;
- manager confirmation.

A price answer should carry:

- item/service identity;
- variant filters;
- amount and currency;
- unit/basis;
- conditions;
- freshness;
- source refs;
- authority decision.

## Transitional implementation guidance

Do not rewrite the existing runtime.

Preferred sequence:

1. Add pure domain contracts for evidence, source authority, and commercial
   pricing/query concepts.
2. Add tests that make the contracts explicit.
3. Add runtime state fields only after the contracts are stable.
4. Add source routing and authority decision as a separate graph/runtime step.
5. Add dedicated two-prompt contracts for `price_list` and `instruction` modes
   instead of routing them through FAQ prompt drift. Until those contracts exist,
   the FAQ compiler contract should remain explicit about being FAQ-only.
6. Add price-list/table compiler as a commercial compiler, not as FAQ prompt
   drift.
7. Add operational CRM tools only behind typed action/safety policies.
8. Extend eval to cover price answers, source routing, missing slots, and tool use.

## Non-goals for this document

This document does not request:

- replacing KCD;
- reverting Stage K work;
- moving live CRM state into knowledge retrieval rows;
- broad refactoring the agent graph;
- changing public API contracts;
- creating database migrations immediately;
- frontend redesign.

It defines the map needed to keep future changes from collapsing into another
generic RAG pipeline.
