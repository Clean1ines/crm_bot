# Knowledge Compilation Domain v1

## 0. Document status

This document defines the target domain architecture for Knowledge Compilation in `crm_bot`.

It is not a one-shot implementation task and must not be reduced to a minimal patch plan.

Implementation may be phased, but every phase must move the code toward this model, not preserve ambiguous historical concepts as permanent architecture.

Compatibility with existing code may define migration order, but it must not define the target model.

This document is the architectural target and the migration contract for the Knowledge Compilation Domain.

## 0.0. Current implementation checkpoint

Current checkpoint:

```text
KCD v1 has moved past the original Stage A/B boundary.
The current architecture has completed the local Stage F validation checkpoint.
```

Completed architectural stages:

```text
Stage A — SourceRef MVP / evidence boundary
Stage B — SourceChunk persistence
Stage C — Canonical entries persistence
Stage D — RetrievalSurface physical/runtime realignment
Stage E — CompilerRun / compilation trace hardening
Stage F — Single production EmbeddingTextBuilder hardening
```

Current implemented direction:

```text
SourceChunk records are persisted separately from runtime retrieval rows.
CanonicalKnowledgeEntry exists as a first-class domain object.
CanonicalKnowledgeEntry is persisted through canonical entry persistence.
Entry source refs are persisted separately from the entry itself.
RetrievalSurface exists as the runtime/eval surface contract.
Runtime retrieval and RAG eval are aligned around published runtime entries.
Production embedding text is built through one authoritative canonical entry builder.
Legacy chunk-level embedding text construction is not production-authoritative.
Raw embedding_text is not exposed as public/prompt payload material.
RAG/eval/prompt-facing payloads should expose answer/evidence/enrichment, not raw embedding_text internals.
```

Current known physical/data-model state:

```text
knowledge_documents stores uploaded document lifecycle state.
knowledge_source_chunks stores raw extracted source evidence.
knowledge_entries stores canonical knowledge entries.
knowledge_entry_source_refs stores entry-to-source evidence links.
knowledge_retrieval_surface stores or represents the published runtime retrieval surface.
knowledge_base must be treated as historical compatibility only where still present.
```

Important current limitation:

```text
The domain model is now entry-first, but several legacy names still exist in code/tests/APIs as transitional terms.
Some RAG eval types and API contracts may still use chunk-oriented naming.
Frontend/product UI is not yet fully aligned with the semantic entry model.
KnowledgeEditAction is not yet the product correction loop.
Price/table compilation is not yet a structured first-class compiler.
```

Current next target:

```text
Stage G — RAG eval realignment
```

Immediate Stage G direction:

```text
Rename/load eval evidence by entries, not chunks.
Make EvalCase reference entry/source refs, not accidental raw chunk ids.
Persist FailureClassification as first-class result data.
Allow eval failure to propose KnowledgeEditAction.
Keep Stage G narrow and do not mix it with UI/product actions/price compiler work.
```

## 0.1. Design stance

This domain is intentionally designed as a full knowledge compilation system, not as another patch over classic chunk-based RAG.

The goal is not to preserve the old `knowledge_base` shape.

The goal is to replace ambiguous chunk-based ingestion with an explicit compiler:

```text
SourceDocument
→ SourceChunk
→ AnswerCandidate
→ CandidateCluster
→ CanonicalKnowledgeEntry
→ KnowledgeEnrichment
→ EmbeddingText
→ EmbeddingVector
→ RetrievalSurface
→ EvalCase / RagEval
→ KnowledgeEditAction
→ improved CanonicalKnowledgeEntry
```

The system should not merely store text fragments.

It should compile business documents into grounded, answerable, testable, editable knowledge.

## 0.2. Non-negotiable domain decisions

These decisions define the domain and must not be weakened by implementation convenience.

1. `chunk` is not a sufficient domain name for production logic.
2. `SourceChunk`, `AnswerCandidate`, `CanonicalKnowledgeEntry`, `EvalCase`, `RetrievedEvidence` and `RetrievalSurface` are different entities.
3. `preprocessing_mode` is a compiler selector, not a final knowledge type.
4. `entry_kind` describes the semantic role of a canonical knowledge entry.
5. `EvalCase` is not knowledge.
6. `RetrievalGuideline` is not production knowledge.
7. `KnowledgeEnrichment` is not authoritative business content.
8. `EmbeddingText` is not the user-facing answer.
9. `EmbeddingText` is not public prompt/eval metadata by default.
10. `RetrievalSurface` is not the same thing as a legacy persistence table.
11. Live CRM/customer/order data is not static document knowledge.
12. Every published `CanonicalKnowledgeEntry` must be grounded in source evidence.
13. Generated questions, synonyms, paraphrases and typo queries must enrich an entry, not become standalone production rows.
14. The system must make it possible to explain why a runtime answer was retrieved and what source evidence supports it.
15. RAG eval must test the production retrieval surface, not an accidental mixture of all stored rows.
16. Temporary compatibility may exist only as a migration layer, not as the target domain model.
17. `knowledge_base` must not be promoted back into the target canonical write model.
18. Raw source chunks must not be treated as normal production retrieval rows.
19. Canonical entry persistence is the write model for production knowledge.
20. Runtime retrieval must be entry-first, evidence-aware and artifact-safe.
21. RAG eval must be entry-first, not chunk-id-first.
22. Failure classification must be a first-class diagnosis, not just free text in a report.
23. Knowledge edit actions must be explicit, auditable and versioned.
24. Price/table knowledge must eventually preserve structured fields and must not rely on vector similarity alone.

## 0.3. Bounded contexts

The system should be understood as several related but separate bounded contexts.

### Knowledge Compilation Context

Owns:

* `SourceDocument`
* `SourceChunk`
* `SourceRef`
* `AnswerCandidate`
* `CandidateCluster`
* `CanonicalKnowledgeEntry`
* `KnowledgeEnrichment`
* `EmbeddingText`
* `EmbeddingVector`
* compiler strategies
* compiler runs
* compilation metrics

Purpose:

```text
Turn uploaded source material into grounded canonical knowledge entries.
```

### Retrieval Context

Owns:

* `RetrievalQuery`
* `RetrievalSurface`
* `RetrievedEvidence`
* retrieval filters
* hybrid/vector/lexical ranking
* production-safe search rules

Purpose:

```text
Find published knowledge entries that can safely support an answer.
```

### RAG Evaluation Context

Owns:

* `EvalCase`
* `RagEvalRun`
* `RagEvalResult`
* `FailureClassification`
* regression cases
* quality reports

Purpose:

```text
Test retrieval and answering quality without polluting production knowledge.
```

### Knowledge Editing Context

Owns:

* `KnowledgeEditAction`
* entry versioning
* publish/unpublish flows
* fix suggestions
* eval-failure-to-fix loop
* audit trail

Purpose:

```text
Let project owners improve compiled knowledge through explicit, auditable edits.
```

### CRM Runtime Context

Owns:

* `CustomerProfile`
* `CustomerOrder`
* `Ticket`
* `ToolResult`
* live business state
* freshness and permission semantics

Purpose:

```text
Answer questions about live customer/order/project state through tools and repositories, not static document RAG.
```

### Manager Handoff Context

Owns:

* `Escalation`
* `ManagerAssignment`
* `ManagerReply`
* handoff lifecycle
* manager notification targets

Purpose:

```text
Transfer conversations to humans when policy, uncertainty or user intent requires it.
```

---

# 1. Problem

The original problem was not simply that RAG “searched chunks poorly”.

The deeper problem was that different domain entities had historically been mixed under one word, `chunk`, and often under one persistence/retrieval table, `knowledge_base`.

A mixed persistence/retrieval layer can contain:

* source fragments;
* LLM-structured extracted entries;
* canonicalized answer units;
* FAQ-like answers;
* price/catalog/procedure/policy entries;
* potential eval/test/guideline/debug artifacts if they pass through a shared ingestion path.

This makes a legacy `knowledge_base` less a clean knowledge base and more a compatibility storage layer for technical fragments, intermediate results and production retrieval rows.

Target model:

```text
Production RetrievalSurface contains grounded canonical semantic answer entries.
```

Physical storage can be migrated gradually, but the target domain must not treat raw source chunks, answer candidates, eval cases and production knowledge entries as the same kind of object.

Target pipeline:

```text
raw document
→ source extraction
→ coarse source chunks
→ answer candidate extraction
→ grounding validation
→ dedupe / semantic merge
→ canonical knowledge entries
→ per-entry enrichment
→ embedding_text
→ embeddings
→ retrieval surface
→ eval
→ edit action
→ improved entry version
```

Main domain contract:

```text
Production retrieval evidence = grounded canonical semantic answer entry + source refs.
```

Not:

* raw chunk;
* eval question;
* guideline;
* LLM fantasy;
* standalone generated question;
* intermediate candidate;
* live CRM state;
* prompt/debug artifact;
* raw embedding text payload.

## 1.1. Why this matters

Classic RAG often works like this:

```text
split document → embed chunks → search chunks → answer
```

For client-facing business knowledge this is often insufficient, because users ask questions conversationally, incompletely, with synonyms, typos and contextual intent.

Target approach for `crm_bot`:

```text
understand a document as a set of potential answers
→ build stable semantic answer blocks
→ ground each block in source evidence
→ enrich each block with client language
→ search enriched embedding_text internally
→ answer from canonical answer + source evidence
→ evaluate failures against expected entries
→ create explicit fix actions
```

This is not just a chunker.

It is an answer-oriented knowledge compiler and product feedback loop.

---

# 2. Document types

`preprocessing_mode` must not directly become the final type of a production knowledge entry.

Processing mode selects compiler strategy.

Final output is one or more `CanonicalKnowledgeEntry` objects with specific `entry_kind` values.

## 2.1. Plain document

A regular text document without an explicit FAQ/price/instruction structure.

Compiler goal:

* extract answer candidates from prose;
* group related meanings;
* create canonical answer entries;
* avoid saving raw chunks as production retrieval rows except under explicit fallback mode.

Typical entry kinds:

* `answer`;
* `contact_info`;
* `working_hours`;
* `policy_clause`;
* `procedure`;
* `refund_policy`;
* `delivery_policy`;
* `catalog_answer`.

## 2.2. FAQ document

A document with explicit question-answer pairs or FAQ-like structure.

Compiler goal:

* detect Q/A pairs;
* merge duplicate questions around the same answer;
* make canonical answer authoritative content;
* store questions as enrichment, not as separate rows.

Typical entry kinds:

* `faq_answer`;
* `answer`;
* `policy_clause`.

Invariant:

```text
FAQ question is enrichment/query surface, not a separate production knowledge row.
```

## 2.3. Price list / catalog document

A price list, catalog, list of products, services, packages, tariffs or conditions.

Compiler goal:

* extract price/catalog facts;
* preserve item names, prices, currency, units, conditions and availability when present;
* create answer entries for retrieval;
* preserve structured metadata for filters/calculations;
* never invent missing prices.

Typical entry kinds:

* `price_answer`;
* `catalog_item_answer`;
* `pricing_policy`;
* `availability_answer`.

Target structured concept:

```text
PriceItem
```

Potential fields:

* item name;
* price;
* currency;
* unit;
* conditions;
* availability;
* category;
* source_refs.

For early implementation, structured `PriceItem` may live inside `CanonicalKnowledgeEntry.metadata`, but the domain must not treat price lists as generic prose forever.

## 2.4. Spreadsheet / table document

A spreadsheet or table may contain prices, schedules, product characteristics, staff lists, tariffs, statuses, SLAs or catalog data.

Compiler goal:

* preserve rows/columns and headers;
* identify table entities and numeric fields;
* create structured records where needed;
* create retrieval answer entries only where semantic search is useful;
* avoid losing numeric/filterable structure in prose conversion.

Important rule:

```text
Embeddings are secondary for structured table queries.
```

Examples:

```text
“Сколько стоит Ares?” may use retrieval + structured price metadata.
“Что дешевле 50 000?” must use structured filters, not vector similarity alone.
```

## 2.5. Instruction document

Instructions, procedures, rules, SLA, onboarding, troubleshooting or operational policy documents.

Compiler goal:

* extract procedures;
* preserve ordered steps;
* preserve prerequisites;
* preserve warnings;
* distinguish policy clauses from operational steps.

Typical entry kinds:

* `procedure`;
* `policy_clause`;
* `warning`;
* `requirement`;
* `troubleshooting_step`.

## 2.6. Policy / legal / SLA document

Documents where exact conditions, obligations and exceptions matter.

Compiler goal:

* preserve exact clauses and conditions;
* avoid paraphrases that change obligations;
* keep source refs precise;
* mark ambiguous or conflicting clauses for review;
* use enrichment only as search/query surface.

Typical entry kinds:

* `policy_clause`;
* `refund_policy`;
* `delivery_policy`;
* `requirement`;
* `warning`.

## 2.7. Mixed document

A document may contain FAQ, price, rules, contacts, product descriptions and instructions at the same time.

Domain rule:

```text
Document mode selects compiler strategy, but compiler may emit multiple entry kinds.
```

Example:

```text
preprocessing_mode = faq
```

may produce:

```text
faq_answer
contact_info
refund_policy
procedure
```

## 2.8. Unsupported / low-quality document

A document may be unsuitable for reliable compilation:

* too little text;
* OCR garbage;
* table structure lost;
* conflicting policy clauses;
* no answerable business facts;
* mostly internal/debug/test content.

Compiler should produce:

* `SourceChunk` records for traceability;
* rejected candidates or document issue markers;
* no published `CanonicalKnowledgeEntry` unless grounded answerable facts exist.

---

# 3. Domain entities

## 3.1. SourceDocument

Uploaded document as a source of knowledge.

It is not a retrieval unit.

Fields:

```text
id
project_id
file_name
file_size
content_type
uploaded_by
status
processing_stage
preprocessing_mode
current_compiler_run_id
preprocessing_metrics
error
created_at
updated_at
```

Responsibilities:

* own lifecycle of ingestion/compilation;
* group source chunks, candidates, entries and eval cases;
* expose processing status to UI;
* support recompilation.

Owned by:

```text
Knowledge Compilation Context
```

Created by:

```text
Document upload use case
```

## 3.2. CompilerRun

One execution of the knowledge compiler over a document.

Fields:

```text
id
document_id
project_id
mode
compiler_version
prompt_version
started_at
finished_at
status
metrics
error
created_by
```

Responsibilities:

* record a specific compilation attempt;
* preserve compiler/prompt/model versions;
* support audit and rollback;
* explain which run produced which entries.

Domain rule:

```text
SourceDocument can have many CompilerRuns.
```

## 3.3. CompilationMetrics

Structured metrics for a compiler run.

Fields:

```text
source_chunk_count
answer_candidate_count
grounded_candidate_count
rejected_candidate_count
candidate_cluster_count
canonical_entry_count
enriched_entry_count
embedded_entry_count
published_entry_count
fallback_row_count
dropped_forbidden_count
entries_without_source_refs_count
retrieval_surface_entry_count
```

Responsibilities:

* make ingestion observable;
* prevent silent row multiplication;
* expose quality and failure modes to UI/admin/debugging.

## 3.4. SourceChunk

Technical source text unit extracted from `SourceDocument`.

Fields:

```text
id
document_id
project_id
source_index
content
page
section_title
start_offset
end_offset
checksum
metadata
created_at
updated_at
```

Responsibilities:

* preserve source evidence;
* support grounding checks;
* support source preview in UI;
* support recompilation;
* serve as evidence material for candidates and entries.

Domain rule:

```text
SourceChunk is evidence material, not production answer knowledge.
```

Created by:

```text
SourceExtractor / DocumentParser
```

Implementation checkpoint:

```text
knowledge_source_chunks persists SourceChunk records.
Runtime retrieval must not read knowledge_source_chunks as normal answer evidence.
```

## 3.5. SourceRef

Reference from candidate/entry/eval case to source evidence.

MVP fields:

```text
source_index
quote
```

Target fields:

```text
source_chunk_id
source_index
quote
start_offset
end_offset
confidence
```

Invariant:

```text
Every published CanonicalKnowledgeEntry must have at least one SourceRef.
```

Validation levels:

```text
level 0: quote exists
level 1: source_index exists
level 2: quote is substring of source chunk
level 3: offsets match source chunk content
```

Implementation checkpoint:

```text
SourceRef / SourceRefView exists at runtime DTO/view/eval boundaries.
source_excerpt may still be used only as compatibility fallback.
source_excerpt is not the target evidence model.
```

## 3.6. AnswerCandidate

Compiler/LLM-extracted possible answer unit.

Fields:

```text
id
document_id
project_id
compiler_run_id
topic_key
title
candidate_answer
source_refs
confidence
status
rejection_reason
metadata
created_at
```

Responsibilities:

* represent extracted answer-like meaning;
* remain untrusted until grounded and deduplicated;
* feed clustering/merge stage;
* expose rejected/ambiguous facts for diagnostics.

Domain rule:

```text
AnswerCandidate must not be published directly to production retrieval.
```

Created by:

```text
Compiler strategy / LLM extractor
```

## 3.7. CandidateCluster

Group of duplicate, overlapping or complementary candidates that should become one canonical entry.

Fields:

```text
id
document_id
project_id
compiler_run_id
cluster_key
topic
candidate_ids
status
merge_strategy
merge_reason
metadata
created_at
```

Responsibilities:

* deduplicate repeated facts;
* merge complementary facts;
* detect conflicts;
* explain why one canonical entry was built from several candidates.

Example:

```text
candidate A: Заказ можно оформить по телефону 123.
candidate B: Заявку можно оставить на сайте.
candidate C: Есть Telegram-канал для заявок.

cluster: ordering_channels
canonical answer: Заказ можно оформить по телефону 123, через сайт или Telegram-канал.
```

Domain rule:

```text
CandidateCluster may be an internal compiler object at first, but it is a real domain concept.
```

## 3.8. CanonicalKnowledgeEntry

Main production answer unit.

Fields:

```text
id
project_id
document_id
compiler_run_id
stable_key
entry_kind
title
answer
source_refs
enrichment
embedding_text
status
visibility
version
compiler_version
embedding_text_version
created_at
updated_at
metadata
```

Responsibilities:

* be the authoritative answer unit;
* be grounded in source refs;
* be searchable through internally built embedding_text;
* be safe to expose to runtime RAG;
* be editable/versioned;
* support evidence-based answer generation.

Domain rule:

```text
CanonicalKnowledgeEntry is the only entity that can be published to RetrievalSurface.
```

Created by:

```text
KnowledgeCompiler after candidate grounding/dedupe/merge
```

Implementation checkpoint:

```text
CanonicalKnowledgeEntry exists as a domain contract.
CanonicalKnowledgeEntry is persisted as a first-class entry model.
Runtime retrieval should operate through RetrievalSurface over published runtime entries.
```

## 3.9. KnowledgeEnrichment

Search/query enrichment attached to a canonical entry.

Fields:

```text
questions
paraphrases
synonyms
typo_queries
colloquial_queries
tags
retrieval_guards
```

Responsibilities:

* bridge document language and user language;
* help weak embeddings and lexical search;
* improve retrieval without adding new facts;
* support failed-question fixing.

Invariant:

```text
Enrichment is not authoritative business content.
```

Important rule:

```text
retrieval_guards / negative hints must not be embedded as positive retrieval text.
```

## 3.10. EmbeddingText

Derived searchable text used for embeddings and hybrid retrieval.

Built from:

```text
title
answer
questions
paraphrases
synonyms
typo_queries
colloquial_queries
tags
```

Responsibilities:

* optimize retrieval;
* include user-language variants;
* stay separate from user-facing answer;
* be versioned and rebuildable.

Domain rules:

```text
RAG answers from answer/source evidence, not from raw embedding_text.
EmbeddingText is created only by the canonical EmbeddingTextBuilder.
EmbeddingText must not introduce facts absent from answer/source_refs.
EmbeddingText is internal retrieval material and must not be exposed as public answer/eval prompt metadata by default.
```

Implementation checkpoint:

```text
Single canonical entry embedding builder exists.
Legacy chunk-level build_knowledge_embedding_text is not the production source of truth.
Production embedding_text version is explicit and builder-owned.
```

## 3.11. EmbeddingVector

Vector representation of `EmbeddingText`.

Fields:

```text
id
entry_id
provider
model
dimensions
vector
embedding_text_version
created_at
usage_metadata
```

Responsibilities:

* support vector retrieval;
* preserve model/version traceability;
* allow rebuilding when embedding_text or model changes.

## 3.12. RetrievalSurface

Published searchable surface.

May be implemented as:

* DB view;
* materialized view;
* separate table;
* filtered repository query during migration.

Contains only:

```text
published CanonicalKnowledgeEntry
with embedding
with source_refs
with runtime visibility
```

Domain rule:

```text
RetrievalSurface is a product/runtime contract, not merely a table name.
```

Implementation checkpoint:

```text
knowledge_retrieval_surface exists as the runtime/eval retrieval surface.
Runtime retrieval and RAG eval should use the same published runtime surface contract.
```

## 3.13. RetrievedEvidence

One retrieval result selected as evidence for a user answer or eval run.

Fields:

```text
entry_id
project_id
document_id
entry_kind
title
answer
score
method
source_refs
source_document_name
metadata
```

Responsibilities:

* give answer generation grounded evidence;
* expose retrieval diagnostics;
* support preview/eval/UI debugging.

Important Stage G rename rule:

```text
RetrievedEvidence must not be treated as RagEvalChunk.
If a transitional class still has chunk naming, Stage G must realign it to entry/evidence naming.
```

## 3.14. EvalCase

Quality-control/adversarial/regression question.

Fields:

```text
id
project_id
document_id
question
attack_type
expected_answer
expected_entry_ids
expected_source_refs
should_answer
should_escalate
severity
status
metadata
created_at
```

Domain rule:

```text
EvalCase may reference knowledge entries but must never become a knowledge entry.
```

Stage G rule:

```text
EvalCase references entry/source evidence expectations, not accidental raw chunk ids.
```

## 3.15. RagEvalRun

One evaluation run over a document/retrieval surface.

Fields:

```text
id
project_id
document_id
dataset_id
status
started_at
finished_at
retriever_version
compiler_version
judge_version
generator_model
```

Responsibilities:

* bind eval results to a specific document and retrieval surface state;
* preserve retriever/compiler/judge versions;
* support regression comparison.

## 3.16. RagEvalResult

Per-question evaluation result.

Fields:

```text
id
run_id
eval_case_id
retrieved_entry_ids
retrieved_evidence
answer_text
passed
score
answer_supported
retrieval_sufficient
failure_classification
suggested_edit_actions
latency_ms
created_at
```

## 3.17. FailureClassification

Diagnosis of failed eval result.

Fields:

```text
failure_stage
failure_type
severity
root_cause
developer_recommendation
knowledge_base_recommendation
client_explanation
answer_supported_by_evidence
retrieval_was_sufficient
missing_entry_ids
wrong_entry_ids
suggested_action_types
```

Allowed failure stages:

```text
DOCUMENT_ISSUE
SOURCE_CHUNKING_ISSUE
CANDIDATE_EXTRACTION_ISSUE
DEDUP_MERGE_ISSUE
ENRICHMENT_ISSUE
EMBEDDING_TEXT_ISSUE
RETRIEVAL_ISSUE
ANSWER_GENERATION_ISSUE
GROUNDING_ISSUE
NO_ANSWER_POLICY_ISSUE
ESCALATION_POLICY_ISSUE
FRONTEND_EXPECTATION_ISSUE
```

Allowed failure types:

```text
MISSING_SOURCE_FACT
AMBIGUOUS_SOURCE_FACT
CONFLICTING_SOURCE_FACT
BAD_SOURCE_CHUNK
MISSING_ENTRY
DUPLICATE_ENTRY
OVER_MERGED_ENTRY
UNDER_MERGED_ENTRY
BAD_ENTRY_KIND
MISSING_ENRICHMENT
BAD_EMBEDDING_TEXT
WRONG_ENTRY_RETRIEVED
NO_ENTRY_RETRIEVED
ANSWER_HALLUCINATED
ANSWER_UNSUPPORTED
ANSWER_TOO_VAGUE
SHOULD_HAVE_ESCALATED
SHOULD_NOT_HAVE_ANSWERED
EXPECTED_ANSWER_WRONG
UI_EXPECTATION_MISMATCH
```

Domain rule:

```text
FailureClassification is structured diagnosis, not a string blob hidden inside markdown.
```

## 3.18. KnowledgeEditAction

User/admin action that improves compiled knowledge.

Fields:

```text
id
project_id
document_id
actor_user_id
action_type
target_entry_id
target_entry_ids
source_eval_case_id
source_eval_result_id
payload
status
created_at
applied_at
error
```

Action types:

```text
attach_question_to_entry
create_entry_from_failure
merge_entries
split_entry
hide_entry
publish_entry
unpublish_entry
mark_source_issue
mark_expected_answer_wrong
rebuild_embedding
rerun_eval
```

This is central to the product loop:

```text
eval failure
→ suggested fix
→ one-click user correction
→ entry updated
→ embedding rebuilt
→ regression case saved
→ eval rerun
```

## 3.19. EntryVersion

Versioned state of a canonical knowledge entry.

Fields:

```text
id
entry_id
version
answer
enrichment
source_refs
metadata
created_by
created_at
change_reason
source_edit_action_id
```

Domain rule:

```text
Material edit creates a new entry version.
```

## 3.20. PriceItem

Structured price/catalog fact extracted from a source document.

Fields:

```text
id
entry_id
document_id
project_id
name
category
price
currency
unit
conditions
availability
source_refs
metadata
created_at
updated_at
```

Domain rule:

```text
Numeric/table/catalog facts must not rely on vector similarity alone.
```

## 3.21. TableRecord

Structured row/record extracted from a table-like source.

Fields:

```text
id
entry_id
document_id
project_id
table_id
row_index
columns
source_refs
metadata
created_at
updated_at
```

Domain rule:

```text
Table structure is source semantics, not formatting noise.
```

---

# 4. Entity lifecycles

## 4.1. SourceDocument lifecycle

```text
uploaded
→ extracting
→ source_chunked
→ compiling_candidates
→ grounding_candidates
→ clustering_candidates
→ merging_candidates
→ enriching_entries
→ embedding_entries
→ publishing_retrieval_surface
→ published
```

Failure states:

```text
failed_extraction
failed_source_chunking
failed_candidate_extraction
failed_grounding
failed_merge
failed_enrichment
failed_embedding
failed_publish
```

Domain note:

```text
A coarse document status such as processed/error is not enough for product UI.
The system needs stage-level visibility.
```

## 4.2. CompilerRun lifecycle

```text
created
→ running
→ completed
```

or:

```text
created
→ running
→ failed
```

CompilerRun owns metrics and version traceability for one compilation attempt.

## 4.3. SourceChunk lifecycle

```text
created
→ validated
→ used_for_candidates
→ archived
```

Possible source chunk statuses:

```text
valid
too_short
duplicate
non_answerable
corrupted
archived
```

## 4.4. AnswerCandidate lifecycle

```text
extracted
→ grounded_checked
→ clustered
→ merged
```

or:

```text
extracted
→ rejected
```

Rejection reasons:

```text
not_grounded
duplicate
too_vague
not_answerable
internal_instruction
eval_artifact
hallucinated
conflicting
```

## 4.5. CandidateCluster lifecycle

```text
created
→ merge_ready
→ canonical_entry_created
```

or:

```text
created
→ needs_review
```

Conflict example:

```text
candidate A: Возврат возможен в течение 48 часов.
candidate B: Возврат невозможен после оплаты.
```

These must not be silently merged.

They require review or explicit conflict policy.

## 4.6. CanonicalKnowledgeEntry lifecycle

```text
draft
→ grounded
→ enriched
→ embedded
→ published
```

After publication:

```text
published
→ needs_review
→ updated
→ republished
```

or:

```text
published
→ hidden
→ archived
```

Versioning rule:

```text
Material edit creates a new entry version.
```

## 4.7. KnowledgeEnrichment lifecycle

```text
generated
→ validated
→ applied
→ embedding_text_rebuilt
→ embedding_rebuilt
```

If a user attaches a failed eval question to an entry:

```text
EvalCase.question
→ enrichment.questions
→ embedding_text rebuild
→ embedding rebuild
→ EvalCase marked regression
```

## 4.8. EmbeddingText / EmbeddingVector lifecycle

```text
entry changed
→ embedding_text rebuilt
→ embedding vector stale
→ embedding rebuilt
→ retrieval surface updated
```

## 4.9. RetrievalSurface lifecycle

```text
entry published
→ retrieval surface row created
→ entry updated
→ retrieval surface row updated
→ entry hidden/unpublished
→ retrieval surface row removed or excluded
```

## 4.10. EvalCase lifecycle

```text
generated
→ active
→ used_in_run
→ regression
→ retired
```

## 4.11. Failure-to-fix lifecycle

```text
RagEvalResult failed
→ FailureClassification created
→ UI shows failed question
→ user chooses fix action
→ KnowledgeEditAction recorded
→ entry/enrichment/source issue updated
→ embedding rebuilt
→ regression case saved
→ eval rerun
```

This is the main product loop for improving knowledge quality.

---

# 5. Target persistence model

`knowledge_base` is not the target model.

It may exist only as historical compatibility storage if still present.

Target persistence separates source evidence, compiler intermediates, published entries, embeddings, retrieval surface, eval artifacts and edit actions.

## 5.1. Target tables

```text
knowledge_documents
knowledge_compiler_runs
knowledge_source_chunks
knowledge_answer_candidates
knowledge_candidate_clusters
knowledge_entries
knowledge_entry_versions
knowledge_entry_source_refs
knowledge_entry_enrichments
knowledge_entry_embeddings
knowledge_retrieval_surface
rag_eval_cases
rag_eval_runs
rag_eval_results
rag_quality_reports
knowledge_edit_actions
knowledge_price_items
knowledge_table_records
```

## 5.2. knowledge_documents

Represents `SourceDocument`.

Core columns:

```text
id
project_id
file_name
file_size
content_type
uploaded_by
status
processing_stage
preprocessing_mode
current_compiler_run_id
error
created_at
updated_at
```

## 5.3. knowledge_compiler_runs

Represents `CompilerRun`.

Core columns:

```text
id
document_id
project_id
mode
compiler_version
prompt_version
model
status
metrics_json
error
started_at
finished_at
created_by
```

## 5.4. knowledge_source_chunks

Represents `SourceChunk`.

Core columns:

```text
id
document_id
project_id
source_index
content
page
section_title
start_offset
end_offset
checksum
metadata_json
created_at
updated_at
```

Implementation checkpoint:

```text
knowledge_source_chunks exists.
knowledge_source_chunks is additive relative to document upload.
knowledge_source_chunks has document/project ownership.
knowledge_source_chunks has source_index and content constraints.
knowledge_source_chunks is cleared on document reprocessing.
```

## 5.5. knowledge_answer_candidates

Represents `AnswerCandidate`.

Core columns:

```text
id
document_id
project_id
compiler_run_id
topic_key
title
candidate_answer
source_refs_json
confidence
status
rejection_reason
metadata_json
created_at
```

## 5.6. knowledge_candidate_clusters

Represents `CandidateCluster`.

Core columns:

```text
id
document_id
project_id
compiler_run_id
cluster_key
topic
candidate_ids_json
status
merge_strategy
merge_reason
metadata_json
created_at
```

## 5.7. knowledge_entries

Represents `CanonicalKnowledgeEntry`.

Core columns:

```text
id
project_id
document_id
compiler_run_id
stable_key
entry_kind
title
answer
status
visibility
version
compiler_version
embedding_text_version
enrichment_json
embedding_text
metadata_json
created_at
updated_at
```

Domain rule:

```text
knowledge_entries is the canonical write model for CanonicalKnowledgeEntry.
```

## 5.8. knowledge_entry_source_refs

Represents source evidence for entries.

Core columns:

```text
id
entry_id
source_chunk_id
source_index
quote
start_offset
end_offset
confidence
metadata_json
created_at
```

Target rule:

```text
knowledge_entry_source_refs links canonical entries to source evidence.
source_chunk_id should reference knowledge_source_chunks when available.
source_index + quote remain useful transitional evidence fields.
```

## 5.9. knowledge_entry_enrichments

Represents `KnowledgeEnrichment`.

Core columns:

```text
id
entry_id
questions_json
paraphrases_json
synonyms_json
typo_queries_json
colloquial_queries_json
tags_json
retrieval_guards_json
created_at
updated_at
```

The target remains separable and versionable enrichment.

Early implementations may store enrichment inside `knowledge_entries.enrichment_json`, but product editing should eventually treat enrichment as explicitly editable/versioned data.

## 5.10. knowledge_entry_embeddings

Represents `EmbeddingText` and `EmbeddingVector` version state.

Core columns:

```text
id
entry_id
embedding_text
embedding_text_version
provider
model
dimensions
embedding_vector
usage_metadata_json
created_at
```

Target owner:

```text
CanonicalKnowledgeEntry / entry-owned embedding lifecycle
```

## 5.11. knowledge_retrieval_surface

Represents `RetrievalSurface`.

May be a view/materialized view/table.

Must expose only:

```text
entry_id
project_id
document_id
entry_kind
title
answer
embedding_text
embedding_vector
source_refs
visibility
status
metadata
```

Filter contract:

```text
status = published
visibility = runtime
source_refs exist
```

Embedding rule:

```text
Embedding must exist for normal semantic/vector retrieval.
Lexical fallback can exist, but it must still use the same published runtime entry surface.
```

Implementation checkpoint:

```text
runtime retrieval and RAG eval use the same retrieval surface contract.
```

## 5.12. rag_eval_cases / rag_eval_runs / rag_eval_results

Eval artifacts remain outside production knowledge tables.

Domain rule:

```text
Eval tables may reference entries and source chunks, but never publish eval questions as knowledge.
```

Stage G target:

```text
Eval cases and results must be entry-first.
Expected ids must be expected_entry_ids, not expected_chunk_ids.
Retrieved evidence must be entry/source-ref evidence.
```

## 5.13. knowledge_edit_actions

Represents explicit human/admin corrections and product quality loop.

Core columns:

```text
id
project_id
document_id
actor_user_id
action_type
target_entry_id
target_entry_ids_json
source_eval_case_id
source_eval_result_id
payload_json
status
created_at
applied_at
error
```

## 5.14. knowledge_price_items

Represents structured price facts.

Core columns:

```text
id
entry_id
document_id
project_id
name
category
price
currency
unit
conditions
availability
source_refs_json
metadata_json
created_at
updated_at
```

## 5.15. knowledge_table_records

Represents structured table records.

Core columns:

```text
id
entry_id
document_id
project_id
table_id
row_index
columns_json
source_refs_json
metadata_json
created_at
updated_at
```

---

# 6. Legacy compatibility contract for `knowledge_base`

This section describes the compatibility/historical role of `knowledge_base`.

It is not the final persistence model.

## 6.1. Historical rule

If `knowledge_base` remains present, it must not be treated as:

```text
canonical write model
source evidence table
candidate table
eval table
product edit table
```

It is only:

```text
legacy compatibility/runtime projection
```

or:

```text
historical migration artifact
```

## 6.2. Canonical runtime surface

Runtime retrieval and RAG eval source loading must use the same canonical allowlist of production-safe `KnowledgeEntryKind` values.

Runtime-safe examples:

```text
answer
faq_answer
contact_info
working_hours
catalog_answer
price_answer
pricing_policy
refund_policy
delivery_policy
policy_clause
procedure
warning
requirement
troubleshooting_step
custom
```

Fallback entry kind:

```text
fallback_chunk
```

`fallback_chunk` is not a normal production target.

It exists only as an explicit fallback concept and must not silently replace canonical entry compilation.

## 6.3. Forbidden design regression

The project must not reintroduce runtime logic based on removed transitional entry values or on compiler modes as final knowledge classifiers.

Forbidden design regression:

```text
mode-as-entry-kind
raw source chunk as default production answer row
generated eval/test/guideline material as runtime-searchable knowledge
standalone generated questions as production rows
chunk ids as the primary eval evidence contract
raw embedding_text exposed as product/prompt evidence
```

## 6.4. Minimum production-persist requirements

A row may be exposed to production retrieval only if:

1. It represents one coherent answer topic/intent.
2. It has canonical `entry_kind`.
3. It is not an eval/test/guideline/debug artifact.
4. It has answer content, not just a question.
5. It has `embedding_text` derived from answer + enrichment by the canonical builder.
6. It passes production retrieval surface rules.
7. It is not an unmerged duplicate of an existing entry.
8. It has source evidence.

## 6.5. Compatibility rule

Compatibility can constrain migration order, but not target domain design.

---

# 7. What must never be persisted as production knowledge

The following must never be persisted or published as production knowledge rows.

## 7.1. Eval and test artifacts

Forbidden:

```text
internal evaluation material
negative test material
retrieval guideline material
eval question
adversarial question
judge prompt
judge output
regression test as knowledge row
```

Reason:

```text
Eval artifacts test the knowledge base. They are not knowledge.
```

## 7.2. Standalone generated questions

Forbidden:

```text
row: “как оформить заказ?”
row: “можно ли заказать ночью?”
row: “какой телефон?”
```

Questions belong inside `KnowledgeEnrichment.questions` of a canonical answer entry.

Correct shape:

```text
entry: Оформление заказа
answer: Заказ можно оформить по телефону 123, через сайт или Telegram.
questions: [...]
```

## 7.3. Standalone synonyms/paraphrases/typo queries

Forbidden:

```text
row: “купить”
row: “оформить”
row: “заявка”
row: “тилеграм”
```

These are retrieval enrichment, not knowledge.

## 7.4. Ungrounded LLM answers

Forbidden:

```text
answer without source_refs
answer based on model prior knowledge
answer with facts absent from document
answer with invented prices/dates/conditions
```

Example forbidden:

```text
Moon costs 5 million.
```

If source only says prices are in catalog, allowed answer:

```text
В документе сказано, что цены доступны в каталоге, но конкретные суммы не указаны.
```

## 7.5. Prompt/system/internal content

Forbidden:

```text
system prompts
developer prompts
internal tool instructions
LLM reasoning traces
provider request payloads
queue job debug payloads
raw stack traces as knowledge
```

## 7.6. Live CRM/customer data

Forbidden in static document knowledge:

```text
customer profile
current order status
payment state
ticket state
manager assignment
thread memory
private conversation content
```

These belong to live tools/repositories, not static document RAG.

## 7.7. Secrets and credentials

Must never be persisted in knowledge rows:

```text
raw bot tokens
webhook secrets
JWTs
Authorization headers
API keys
password reset tokens
full encrypted secret values in logs/reports
```

## 7.8. Raw embedding text as product answer/evidence

Forbidden as public/product-facing answer material:

```text
embedding_text as answer
embedding_text as prompt evidence
embedding_text as eval evidence explanation
embedding_text as user-visible source
```

Allowed:

```text
embedding_text as internal retrieval/search material
embedding_text in internal debug reports when explicitly needed
```

---

# 8. CanonicalKnowledgeEntry schema

## 8.1. Domain schema

```text
CanonicalKnowledgeEntry
  id: string
  project_id: string
  document_id: string
  compiler_run_id: string
  stable_key: string
  entry_kind: KnowledgeEntryKind
  title: string
  answer: string
  source_refs: SourceRef[]
  enrichment: KnowledgeEnrichment
  embedding_text: EmbeddingText | null
  status: KnowledgeEntryStatus
  visibility: KnowledgeEntryVisibility
  version: int
  compiler_version: string
  embedding_text_version: string
  metadata: object
  created_at: datetime
  updated_at: datetime
```

## 8.2. Entry kind

Initial values:

```text
answer
faq_answer
contact_info
working_hours
catalog_answer
price_answer
pricing_policy
refund_policy
delivery_policy
policy_clause
procedure
warning
requirement
troubleshooting_step
fallback_chunk
custom
```

Avoid using only:

```text
faq
price_list
instruction
```

because those are compiler modes, not precise domain entry kinds.

## 8.3. Status

Full target status vocabulary:

```text
draft
grounded
enriched
embedded
published
needs_review
hidden
archived
rejected
```

MVP-compatible collapsed vocabulary:

```text
published
needs_review
hidden
rejected
```

Runtime retrieval uses only:

```text
status = published
```

## 8.4. Visibility

```text
runtime
owner_only
internal
hidden
```

Runtime retrieval uses only:

```text
visibility = runtime
```

## 8.5. SourceRef schema

MVP:

```text
source_index: int
quote: string
```

Target:

```text
source_chunk_id: string
source_index: int
quote: string
start_offset: int | null
end_offset: int | null
confidence: float | null
```

## 8.6. KnowledgeEnrichment schema

```text
questions: string[]
paraphrases: string[]
synonyms: string[]
typo_queries: string[]
colloquial_queries: string[]
tags: string[]
retrieval_guards: string[]
```

MVP can use:

```text
questions
synonyms
tags
```

because these already exist in current entry/retrieval contracts.

## 8.7. Embedding text shape

Recommended builder output:

```text
{title}

Ответ:
{answer}

Возможные вопросы пользователей:
{questions}

Перефразы:
{paraphrases}

Синонимы и близкие выражения:
{synonyms}

Разговорные/ошибочные формулировки:
{typo_queries + colloquial_queries}

Теги:
{tags}
```

Rules:

1. `embedding_text` may include search expansion.
2. `embedding_text` must not introduce new facts.
3. User-facing response should use `answer`, not raw `embedding_text`.
4. Embedding should be generated from canonical builder output.
5. Typo/noisy query expansion must be limited to high-value terms and must not flood embedding_text.
6. Retrieval guards / negative hints must not be embedded as positive retrieval surface.
7. Production embedding text must have a version.
8. There must be one production-authoritative builder.

---

# 9. Compiler strategies

Compiler strategy is selected by document mode and content structure.

It emits candidates or canonical entries, but must respect the common output contract.

## 9.1. Common compiler pipeline

```text
SourceDocument
→ SourceChunks
→ AnswerCandidates
→ Grounding validation
→ CandidateClusters
→ CanonicalKnowledgeEntries
→ Enrichment
→ EmbeddingText
→ EmbeddingVector
→ RetrievalSurface publication
```

## 9.2. TextAnswerCompiler

For plain prose.

Responsibilities:

* extract answer candidates from prose;
* assign topic keys;
* attach source refs;
* avoid over-fragmentation;
* avoid large multi-topic entries;
* merge repeated facts.

Output:

```text
CanonicalKnowledgeEntry(entry_kind=answer/contact_info/policy_clause/etc.)
```

## 9.3. FaqCompiler

For FAQ-like documents.

Responsibilities:

* detect Q/A pairs;
* normalize answer content;
* move questions into enrichment;
* merge duplicate questions around one answer;
* preserve original question as source/evidence metadata if useful.

Output:

```text
CanonicalKnowledgeEntry(entry_kind=faq_answer)
```

## 9.4. PriceListCompiler

For price/catalog documents.

Responsibilities:

* identify item/service names;
* identify prices/currency/units when present;
* identify conditions and limitations;
* produce answer entries for retrieval;
* preserve structured price metadata;
* never infer missing prices.

Output:

```text
CanonicalKnowledgeEntry(entry_kind=price_answer/catalog_item_answer/pricing_policy)
PriceItem metadata where structured price facts exist
```

Important rule:

```text
If exact price is absent, compiler must say exact price is absent, not infer it.
```

## 9.5. TableCompiler

For spreadsheets and structured tables.

Responsibilities:

* preserve table structure;
* identify headers and row entities;
* extract structured fields;
* create retrieval text only after structure is understood;
* support structured filters where needed.

Output:

```text
TableRecord metadata + CanonicalKnowledgeEntry where useful
```

## 9.6. InstructionCompiler

For procedures and operational instructions.

Responsibilities:

* extract ordered steps;
* preserve prerequisites;
* preserve warnings;
* distinguish policy from procedure;
* avoid splitting steps so much that retrieval loses context.

Output:

```text
CanonicalKnowledgeEntry(entry_kind=procedure/policy_clause/warning/requirement)
```

## 9.7. PolicyCompiler

For legal/policy/SLA-like content.

Responsibilities:

* preserve exact conditions;
* avoid paraphrases that change obligations;
* keep source refs precise;
* mark ambiguous/conflicting clauses for review.

Output:

```text
CanonicalKnowledgeEntry(entry_kind=policy_clause/refund_policy/delivery_policy)
```

## 9.8. FallbackChunkCompiler

For cases where semantic compilation fails.

Responsibilities:

* create conservative chunks;
* mark them as fallback;
* do not pretend they are fully canonical semantic entries;
* expose only under explicit fallback retrieval mode.

Output:

```text
fallback_chunk
```

Domain rule:

```text
Fallback exists for safety, not as the target architecture.
```

## 9.9. Dedupe / merge strategy

Recommended staged approach:

1. LLM extraction with topic labels.
2. Deterministic lexical normalization.
3. Embedding similarity between short answer candidates.
4. Small-group LLM merge for clusters of 2–6 candidates.
5. Conflict detection before merge.

Never ask LLM to merge 50–100 chunks at once.

## 9.10. Enrichment strategy

Enrichment runs after canonical entry is built.

Input:

```text
CanonicalKnowledgeEntry.answer + source_refs
```

Output:

```text
questions
paraphrases
synonyms
typo_queries
colloquial_queries
tags
embedding_text
```

Rule:

```text
Each canonical entry is enriched separately.
```

Do not enrich the whole document as one blob.

---

# 10. Retrieval strategies

## 10.1. Default production retrieval

Search only `RetrievalSurface`:

```text
published CanonicalKnowledgeEntry
with runtime visibility
with source_refs
```

Implementation checkpoint:

```text
Runtime retrieval should read knowledge_retrieval_surface or its explicit repository/view equivalent.
```

## 10.2. Hybrid retrieval

Use combined strategy:

* vector search over canonical `embedding_text`;
* lexical search over `title + answer + internal search text + enrichment`;
* exact/substring boost for obvious matches;
* optional entry kind boosts.

Current code already has useful hybrid pieces.

The domain correction is not primarily in scoring.

It is in what rows are allowed into the searchable surface.

## 10.3. Raw fallback retrieval

Allowed only under explicit conditions:

```text
fallback_raw_search_enabled=true
```

or:

```text
no canonical entries exist for document/project
```

Raw fallback results should be marked as fallback and may trigger lower confidence or manager escalation.

## 10.4. Entry-kind routing

Retriever should eventually route or boost by intent:

```text
price question → price_answer/catalog_item_answer/pricing_policy
refund question → refund_policy/policy_clause
how-to question → procedure/troubleshooting_step
contact question → contact_info/working_hours
```

This can start as ranking boosts, not a hard router.

## 10.5. Static KB vs live tools

Static KB retrieval handles document-derived knowledge.

Live tools handle:

```text
customer profile
order state
ticket state
manager assignment
payment status
fresh inventory
```

Do not force live CRM/order data into static document RAG.

## 10.6. Retrieval result shape

Runtime/internal result should include:

```text
entry_id
answer
score
method
entry_kind
title
source_refs
document_id
source document name
```

Compatibility may still include:

```text
source_excerpt
```

but `source_excerpt` is not the target evidence model.

Client-facing answer should not expose internal implementation fields by default.

## 10.7. Retrieval safety rules

Never retrieve:

```text
draft entries
hidden entries
rejected entries
raw candidates
eval cases
negative tests
retrieval guidelines
internal debug rows
entries without source_refs
raw source chunks as normal answer rows
```

## 10.8. RAG eval retrieval rule

RAG eval must use the same `RetrievalSurface` contract as production retrieval unless the eval run explicitly tests fallback/source behavior.

This prevents eval from testing accidental rows that runtime search would not use.

## 10.9. Embedding text exposure rule

Retriever may use `embedding_text`.

Runtime answer generation and product-facing payloads should use:

```text
answer
title
entry_kind
source_refs
safe enrichment fields when useful
```

not:

```text
raw embedding_text as evidence
```

---

# 11. RAG evaluation realignment

Stage G must convert RAG eval from chunk-oriented language to entry/evidence-oriented language.

## 11.1. Problem

Old RAG eval language often says:

```text
RagEvalChunk
chunk_id
expected_chunk_ids
document chunks
```

This is misleading after KCD Stage C/D/F because runtime evidence is no longer “raw chunks”.

Target language:

```text
RetrievedEvidence
entry_id
expected_entry_ids
source_refs
published retrieval surface entries
```

## 11.2. EvalCase target

EvalCase should reference expected entries and source refs:

```text
question
attack_type
expected_answer
expected_entry_ids
expected_source_refs
should_answer
should_escalate
severity
metadata
```

Forbidden target contract:

```text
expected_chunk_ids as the primary expectation field
```

Transitional compatibility may read old fields, but new domain logic must normalize them into entry-first fields.

## 11.3. Retrieved evidence target

Eval retrieved evidence should include:

```text
entry_id
title
entry_kind
answer
score
method
source_refs
document_id
source
metadata
```

It should not expose raw embedding_text as prompt evidence.

## 11.4. FailureClassification first-class

Each failed eval result should produce structured classification:

```text
failure_stage
failure_type
severity
root_cause
developer_recommendation
knowledge_base_recommendation
client_explanation
answer_supported_by_evidence
retrieval_was_sufficient
```

This must be persistable and queryable.

It must not live only inside generated markdown.

## 11.5. Suggested KnowledgeEditAction

A failed result may produce suggested actions:

```text
attach_question_to_entry
create_entry_from_failure
merge_entries
split_entry
hide_entry
mark_source_issue
mark_expected_answer_wrong
rebuild_embedding
rerun_eval
```

Stage G may generate proposals without executing them.

Execution belongs to Stage H.

## 11.6. Reports

RAG eval reports should show:

```text
question
attack_type
expected_entry_ids
retrieved_entry_ids
entry titles
source refs
failure classification
suggested actions
```

Reports should not be centered around raw chunk ids.

---

# 12. KnowledgeEditAction product loop

Stage H turns eval failures into auditable product fixes.

## 12.1. Product loop

```text
eval failure
→ failure classification
→ suggested edit action
→ owner/admin applies fix
→ entry version created
→ enrichment/source/action updated
→ embedding rebuilt
→ retrieval surface updated
→ regression eval rerun
```

## 12.2. attach_question_to_entry

Use when:

```text
Correct entry exists but retrieval did not find it for a user phrasing.
```

Behavior:

```text
question added to entry.enrichment.questions
embedding_text rebuilt
embedding vector rebuilt
KnowledgeEditAction recorded
EvalCase marked regression
```

## 12.3. create_entry_from_failure

Use when:

```text
Source document contains answerable information, but no canonical entry exists.
```

Behavior:

```text
new CanonicalKnowledgeEntry draft/published depending on evidence confidence
source_refs required
embedding_text built
embedding vector built
retrieval surface updated
```

## 12.4. merge_entries

Use when:

```text
Multiple entries answer one semantic intent and retrieval/answering becomes fragmented.
```

Behavior:

```text
new merged entry version or new entry
old entries hidden/archived
source_refs combined
enrichment combined
embedding rebuilt
```

## 12.5. split_entry

Use when:

```text
One entry contains multiple intents and retrieval answers too broadly.
```

Behavior:

```text
new smaller entries
source_refs distributed
old entry hidden/archived or marked superseded
embedding rebuilt
```

## 12.6. hide/publish/unpublish

Use when:

```text
entry should be removed from or returned to runtime retrieval
```

Behavior:

```text
status/visibility changed
retrieval surface updated
audit action recorded
```

## 12.7. rebuild_embedding

Use when:

```text
answer/enrichment/builder/model changed
```

Behavior:

```text
embedding_text rebuilt by canonical builder
embedding vector rebuilt
retrieval surface updated
```

## 12.8. rerun_eval

Use when:

```text
fix has been applied and must be verified
```

Behavior:

```text
target eval cases rerun
regression status updated
quality report regenerated
```

## 12.9. Entry versioning

Material edit creates:

```text
EntryVersion
KnowledgeEditAction
updated retrieval surface
```

Material edit examples:

```text
answer changed
source_refs changed
entry split/merged
status/visibility changed
structured price metadata changed
```

---

# 13. Product UI scenarios

## 13.1. Upload document

User uploads a document and selects mode.

API response should include:

```text
document_id
status
processing_stage
preprocessing_mode
queued job id if useful for admin UI
```

The upload endpoint should not imply that knowledge is immediately searchable.

## 13.2. Processing status

UI should show stages:

```text
extracting text
building source chunks
extracting answer candidates
merging duplicates
enriching entries
building embeddings
publishing retrieval surface
published
failed
```

This gives the user product-level visibility, not just technical `processing`.

## 13.3. Document detail page

Owner/admin can open document and see:

* source chunks;
* canonical entries;
* source refs;
* compilation metrics;
* rejected candidates/issues;
* eval status;
* last report.

## 13.4. Semantic entries page

Main KB UI should be organized around semantic answer blocks, not raw chunks.

Each entry card/table row:

```text
title
entry_kind
answer
status
source evidence count
questions count
tags
last updated
quality warnings
```

Actions:

```text
edit answer
edit questions
view source
hide/unhide
merge
split
rebuild embedding
run targeted eval
```

## 13.5. Source evidence view

For each entry, UI can show:

```text
source document
source chunk quote
page/section if available
source index
```

This is critical for trust.

## 13.6. Knowledge preview / ask document

User asks a test question.

UI shows:

```text
best matched entry
score/method
answer
source evidence
matched questions/synonyms/tags if useful
other candidates
```

This should be designed as a QA/debugging tool for the project owner.

## 13.7. RAG eval run

User runs document eval.

System:

```text
loads published entries from RetrievalSurface
creates/loads eval cases
runs retrieval
runs production answerer
runs judge
classifies failures
produces report
suggests edit actions
```

Report should reference:

```text
entry ids
entry titles
source refs
failure stages
recommended actions
```

not generic chunk ids.

## 13.8. Fix failed question

Core product scenario:

```text
Failed question: “можно ли заказать ночью?”
```

UI shows:

* expected entry if known;
* retrieved wrong entry if any;
* source evidence;
* recommended fix.

Actions:

```text
Attach question to existing entry
Create new entry from source
Merge entries
Mark source document missing info
Mark expected answer wrong
Escalate to manual review
```

## 13.9. Attach question to entry

Domain behavior:

```text
question added to entry.enrichment.questions
embedding_text rebuilt
embedding rebuilt
eval case marked regression
KnowledgeEditAction recorded
```

## 13.10. Manual entry edit

If owner edits answer, system should enforce:

```text
source_refs required for published status
```

If no source_refs:

```text
status = draft or needs_review
```

## 13.11. Publish/unpublish entry

Owner can remove bad entries from runtime retrieval without deleting source evidence.

Actions:

```text
publish
unpublish
hide
archive
```

## 13.12. Recompile document

Separate operations:

```text
recompile all
recompile candidates only
rebuild enrichment only
rebuild embeddings only
rerun eval only
```

Do not collapse all into one vague “process again”.

## 13.13. Product UI typing rule

Core KB/eval UI boundaries should not use broad unstructured types as the stable product contract.

Target:

```text
typed entry DTOs
typed source ref DTOs
typed eval case DTOs
typed failure classification DTOs
typed edit action DTOs
typed price/table metadata DTOs
```

Avoid at core boundaries:

```text
Record<string, unknown>
unknown nested payloads without a typed adapter
raw dict passthrough from DB to frontend
```

---

# 14. Current-to-target mapping

This section maps current code concepts to target domain concepts.

| Current concept                   | Current role                                          | Target concept                                                       |
| --------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------- |
| `knowledge_documents`             | uploaded document + preprocessing status              | `SourceDocument`                                                     |
| raw parser chunk JSON             | source text unit                                      | `SourceChunk`                                                        |
| `knowledge_source_chunks`         | persisted source evidence table                       | physical persistence for `SourceChunk`                               |
| `SourceRefView`                   | current API/eval evidence view                        | transitional view over `SourceRef`                                   |
| `source_excerpt`                  | compatibility evidence preview                        | compatibility fallback only; target `SourceRef`                      |
| `KnowledgePreprocessingEntry`     | LLM extracted answer-like object                      | `AnswerCandidate` + partial `KnowledgeEnrichment`                    |
| `KnowledgePreprocessingResult`    | LLM preprocessing result                              | `CompilerRun` output                                                 |
| `KnowledgeChunkDraft`             | normalized draft/final-ish candidate                  | transitional draft object; should not define target domain           |
| `KnowledgeChunk`                  | legacy/transitional persistence DTO                   | transitional projection DTO; not target canonical entity             |
| `knowledge_entries`               | canonical entry persistence                           | `CanonicalKnowledgeEntry` table                                      |
| `knowledge_entry_source_refs`     | entry evidence persistence                            | `SourceRef` persistence                                              |
| `knowledge_retrieval_surface`     | published runtime/eval surface                        | `RetrievalSurface`                                                   |
| `knowledge_base.entry_kind`       | historical semantic classifier in compatibility table | target `knowledge_entries.entry_kind` + retrieval surface projection |
| `knowledge_base`                  | legacy runtime retrieval table/projection             | compatibility projection only                                        |
| `preprocessing_mode`              | selected upload processing mode                       | `CompilerStrategy` selector                                          |
| `embedding_text`                  | internal searchable text                              | target `EmbeddingText` built by single builder                       |
| `RagEvalQuestion`                 | eval/adversarial question                             | `EvalCase`                                                           |
| `RagEvalChunk`                    | old eval view over retrieval row                      | rename/realign to `RetrievedEvidence`                                |
| `expected_chunk_ids`              | old eval expected evidence field                      | transitional only; target `expected_entry_ids`                       |
| `SearchKnowledgeTool`             | runtime KB search tool                                | Retrieval Context entrypoint                                         |
| manager thread status/manual flow | handoff behavior                                      | `ManagerHandoff` / `Escalation`                                      |

---

# 15. Minimal migration path from current code

This path avoids a big-bang rewrite but does not redefine the target architecture around old physical storage.

## Stage A. SourceRef MVP / evidence boundary

Status:

```text
completed
```

Goal:

```text
Make source evidence explicit before the persistence split becomes strict.
```

Implemented / expected behavior:

1. `SourceRef` / `SourceRefView` exists as an evidence shape.
2. Retrieval/eval DTOs can carry `source_refs`.
3. `source_excerpt` remains only compatibility preview/fallback.
4. RAG eval evidence can carry source refs.
5. Entries without evidence must not become normal published runtime evidence long-term.

Remaining hardening:

```text
validate quote against source chunk content
validate offsets
make published runtime entries require source refs strictly
```

## Stage B. SourceChunk persistence

Status:

```text
completed
```

Goal:

```text
Persist raw extracted source chunks separately from production retrieval rows.
```

Implemented / expected behavior:

1. `knowledge_source_chunks` table exists.
2. Extracted raw source chunks are stored separately.
3. Source chunks are not normal production retrieval rows.
4. Document reprocessing clears stale source chunks.
5. Runtime search and preview search are not switched to source chunks.
6. Source evidence is preserved for UI/recompile/grounding.
7. Source refs can point toward source chunk identity/index.

Remaining hardening:

```text
normalized source ref linking
quote substring validation
source evidence UI
```

## Stage C. Canonical entries persistence

Status:

```text
completed
```

Goal:

```text
CanonicalKnowledgeEntry becomes first-class persistence.
```

Implemented / expected behavior:

```text
CanonicalKnowledgeEntry → knowledge_entries
SourceRef → knowledge_entry_source_refs
```

Core rules:

```text
knowledge_entries owns canonical knowledge
knowledge_base is not the canonical target
entry source refs are persisted separately
repository contract accepts typed domain objects, not raw dict payloads
```

Remaining hardening:

```text
entry version persistence
stronger source ref validation
source evidence UI
candidate lineage persistence if not fully represented
```

## Stage D. RetrievalSurface physical/view split

Status:

```text
completed as runtime/eval alignment checkpoint
```

Goal:

```text
Make runtime retrieval and RAG eval use the same explicit physical/view retrieval surface.
```

Implemented / expected behavior:

1. `knowledge_retrieval_surface` exists or is represented as the explicit retrieval surface.
2. Runtime retrieval uses the retrieval surface contract.
3. RAG eval source loading uses the same published runtime surface.
4. Runtime/eval retrieval excludes forbidden artifacts.
5. Search is entry-first, not raw-source-chunk-first.

Remaining hardening:

```text
remove transitional chunk naming
strengthen guard tests around no bypassing RetrievalSurface
source evidence UI
structured retrieval diagnostics
```

## Stage E. CompilerRun / CompilationMetrics / AnswerCandidate / CandidateCluster

Status:

```text
completed as compiler trace checkpoint, with remaining target expansion
```

Goal:

```text
Persist compiler traceability and prevent silent row multiplication.
```

Expected behavior:

1. Compiler run identity/versioning exists or is represented.
2. Compiler metrics exist or are recorded in document/compiler metadata.
3. Canonical entries carry compiler lineage.
4. Row multiplication becomes visible and explainable.

Remaining target expansion:

```text
knowledge_answer_candidates
knowledge_candidate_clusters
candidate-to-cluster-to-entry lineage
rejected candidate inspection UI
conflict review workflow
```

## Stage F. EmbeddingTextBuilder hardening

Status:

```text
completed
```

Goal:

```text
Make production embedding_text deterministic, versioned and entry-owned.
```

Implemented / expected behavior:

1. A single canonical entry embedding text builder exists.
2. Builder output is versioned.
3. Repository embedding calls use canonical builder output.
4. Legacy chunk embedding text builder is removed from production authority.
5. Normalization no longer builds legacy chunk embedding text as production source.
6. User-facing answers and prompt/eval payloads do not expose raw embedding_text by default.
7. Tests guard the single-builder rule and exposure boundary.

Remaining hardening:

```text
entry edit action triggers embedding rebuild
embedding model/version audit
embedding rebuild job
admin/debug-only internal embedding_text inspection
```

## Stage G. RAG eval realignment

Status:

```text
next target
```

Goal:

```text
RAG eval references entries and source refs, not accidental chunk ids.
```

Stage G must be implemented in narrow slices.

### Stage G.1 — Eval evidence naming and loading

Actions:

1. Rename/load eval evidence by entries.
2. Replace `RagEvalChunk` concept with `RetrievedEvidence` or equivalent.
3. Normalize old chunk-id fields to entry-id fields at boundaries if needed.
4. Make eval evidence contain:

```text
entry_id
title
entry_kind
answer
source_refs
score
method
```

5. Add guards against new chunk-first eval contracts.

Non-goals:

```text
do not implement edit action execution
do not build frontend UI
do not build price/table compiler
```

### Stage G.2 — EvalCase entry/source expectations

Actions:

1. Make `EvalCase` reference `expected_entry_ids`.
2. Make `EvalCase` reference `expected_source_refs`.
3. Rename old expected chunk fields or keep only as transitional adapters.
4. Update reports/tests to use entry language.

### Stage G.3 — FailureClassification first-class

Actions:

1. Add typed `FailureClassification`.
2. Persist it in eval result storage.
3. Map judge JSON into typed object.
4. Keep legacy report strings only as projection, not as source of truth.

### Stage G.4 — Suggested KnowledgeEditAction

Actions:

1. Let eval failure produce suggested `KnowledgeEditAction`.
2. Store suggested actions or return them through typed report DTOs.
3. Do not execute actions yet.
4. Add tests that suggested actions are typed and auditable.

## Stage H. KnowledgeEditAction product loop

Status:

```text
planned after Stage G
```

Goal:

```text
Turn eval failures into auditable product fixes.
```

Actions:

1. Add or complete `knowledge_edit_actions`.
2. Add `attach_question_to_entry`.
3. Add `create_entry_from_failure`.
4. Add merge/split/hide/publish/unpublish actions.
5. Add rebuild embedding action.
6. Add rerun eval action.
7. Add entry versioning/audit trail.
8. Ensure all material edits update retrieval surface.

## Stage I. Product UI

Status:

```text
planned after Stage G/H backend contracts stabilize
```

Goal:

```text
Expose semantic knowledge management, not raw chunk debugging as the primary product.
```

Actions:

1. Document detail page.
2. Semantic entries page.
3. Source evidence view.
4. RAG eval failures with fix actions.
5. Replace broad `Record<string, unknown>` at core KB/eval boundaries.
6. Ensure OpenAPI/TS generated types reflect entry-first contracts.

## Stage J. Price/table compiler

Status:

```text
planned after entry/eval/edit loop is stable
```

Goal:

```text
Handle numeric/table/catalog knowledge with structured metadata, not embeddings alone.
```

Actions:

1. Add `PriceItem` / `TableRecord` structured metadata.
2. Use structured filters for numeric/table queries where needed.
3. Keep semantic retrieval for explanations.
4. Do not rely on vector similarity for numeric filtering alone.

---

# 16. Compatibility contract

Existing user-facing behavior must not be broken accidentally during migration.

The following flows must keep working until explicitly replaced:

* document upload;
* document list;
* knowledge preview;
* runtime `SearchKnowledgeTool`;
* RAG eval run/progress/report;
* manager handoff;
* project/member/channel flows;
* frontend build/type-check flows.

Compatibility rule:

```text
Compatibility can constrain migration order, but not target domain design.
```

Current compatibility rule:

```text
Entry-first canonical persistence and retrieval surface are the target.
Any remaining chunk/knowledge_base naming is transitional and must not drive future architecture.
```

---

# 17. Quality gates and tests

## 17.1. Domain invariant tests

Must prove:

* `EvalCase` cannot be persisted as production knowledge.
* `RetrievalGuideline` cannot be persisted as production knowledge.
* standalone generated questions cannot be production rows.
* production entries require source refs.
* `preprocessing_mode` does not equal final `entry_kind`.
* runtime retrieval only uses production-safe surface.
* RAG eval uses same retrieval surface contract as runtime.
* source chunks are evidence material, not production answer entries.
* canonical entries are the only publishable answer units.
* production embedding text comes from the single canonical builder.

## 17.2. Ingestion tests

Must prove:

* source chunks are created/preserved;
* answer candidates are grounded;
* candidates without source refs are rejected/quarantined;
* canonical entries are published only after required fields exist;
* embedding_text is built from entry + enrichment;
* forbidden artifacts are dropped/quarantined;
* canonical entries are written to `knowledge_entries`;
* retrieval surface receives only published runtime entries.

## 17.3. Repository/persistence tests

Must prove:

* `knowledge_source_chunks` stores raw source evidence;
* document reprocessing clears stale source chunks;
* `knowledge_entries` stores `CanonicalKnowledgeEntry`;
* `knowledge_entry_source_refs` links entries to source chunks/source indexes/quotes;
* `knowledge_retrieval_surface` stores or exposes runtime/eval retrieval entries;
* delete/clear semantics remove or cascade all document-owned knowledge state;
* repository contracts use typed domain objects, not raw dicts or `Any`.

## 17.4. Retrieval tests

Must prove:

* hidden/draft/rejected entries are not retrieved;
* raw fallback is used only under explicit fallback conditions;
* entry_kind routing/boosting works without excluding valid answers;
* source evidence survives into retrieval result;
* runtime retrieval does not accidentally query source chunks;
* runtime retrieval and RAG eval use the same retrieval surface;
* raw embedding_text is not exposed as product/prompt evidence.

## 17.5. RAG eval tests

Must prove:

* eval cases stay in eval tables;
* expected ids point to entries, not accidental raw chunks;
* failure classifications are persisted;
* failed eval can produce a valid suggested `KnowledgeEditAction`;
* RAG eval result evidence includes entry/source refs;
* report language is entry/evidence-first, not chunk-first.

## 17.6. KnowledgeEditAction tests

Must prove:

* attach question updates enrichment;
* create entry from failure requires source refs;
* merge/split creates audit trail;
* publish/unpublish updates retrieval surface;
* rebuild_embedding uses canonical builder;
* rerun_eval links new run to applied action;
* material edit creates `EntryVersion`.

## 17.7. Frontend/API contract tests

Must prove:

* document status/stage is visible;
* entry/source evidence data is typed;
* RAG eval reports expose entry ids and source refs;
* broad `Record<string, unknown>` contracts are replaced at core product boundaries;
* source evidence view can be rendered without exposing internal debug artifacts;
* fix actions can be displayed and invoked through typed contracts.

## 17.8. Architecture tests

Must prove:

* domain does not import infrastructure/interface libraries;
* application ports expose typed contracts;
* canonical write paths target `knowledge_entries`, not `knowledge_base`;
* runtime retrieval cannot bypass retrieval surface;
* source chunks cannot become normal runtime retrieval rows;
* eval/test/guideline artifacts cannot enter production retrieval;
* no new production code reintroduces legacy chunk-level embedding text builder;
* no new eval code introduces chunk ids as the primary evidence contract.

---

# 18. Stage G contract

Stage G is the next implementation step.

It must be deliberately narrow.

## 18.1. Stage G goal

```text
Realign RAG eval around entries, source refs, failure classifications and suggested edit actions.
```

## 18.2. Stage G non-goals

Stage G must not implement:

```text
full KnowledgeEditAction execution loop
frontend semantic entries UI
price/table compiler
large product UI rewrite
broad API redesign
unrelated refactors
```

Those belong to later stages.

## 18.3. Stage G required shape

Stage G should introduce or complete:

```text
entry-first EvalCase expectations
entry-first RetrievedEvidence naming
typed FailureClassification
suggested KnowledgeEditAction proposal shape
report DTO updates
architecture guards against chunk-first eval contracts
```

## 18.4. Stage G.1 required shape

First patch should target only naming/loading evidence:

```text
RagEvalChunk → RetrievedEvidence or RagEvalEvidenceEntry
chunk_id → entry_id where semantic evidence is a canonical entry
expected_chunk_ids → expected_entry_ids at new boundaries
document chunks → document entries/evidence where retrieval surface is used
```

Transitional adapters may exist, but new core contracts must be entry-first.

## 18.5. Stage G.2 required shape

Second patch should target EvalCase expectations:

```text
EvalCase.expected_entry_ids
EvalCase.expected_source_refs
reports showing expected/retrieved entries
tests proving eval does not use raw source chunks as expected production evidence
```

## 18.6. Stage G.3 required shape

Third patch should target FailureClassification:

```text
typed domain/application schema
repository persistence
judge result mapping
report projection
tests for failure stage/type/severity/root cause
```

## 18.7. Stage G.4 required shape

Fourth patch should target suggested actions only:

```text
eval failure → suggested KnowledgeEditAction
no action execution yet
typed payload
audit-ready shape
tests for attach_question/create_entry/mark_source_issue suggestions
```

## 18.8. Stage G validation

Targeted validation should include:

```text
ruff format/check on touched files
mypy src
RAG eval schema/repository/adapter tests
architecture guard tests
targeted full eval-related tests
```

Full validation should include:

```text
extended quality gate
frontend lint/type-check/build if API/OpenAPI/frontend contracts changed
```

---

# 19. Stage H contract

Stage H implements the product correction loop.

## 19.1. Stage H goal

```text
Execute KnowledgeEditAction safely and audibly.
```

## 19.2. Stage H required actions

```text
attach_question_to_entry
create_entry_from_failure
merge_entries
split_entry
hide_entry
publish_entry
unpublish_entry
mark_source_issue
mark_expected_answer_wrong
rebuild_embedding
rerun_eval
```

## 19.3. Stage H invariants

```text
No material edit without audit.
No published entry without source refs.
No answer edit without entry version.
No enrichment edit without embedding rebuild.
No publish/unpublish without retrieval surface update.
No failed action silently ignored.
```

---

# 20. Stage I contract

Stage I exposes the product.

## 20.1. Stage I goal

```text
Make the KB understandable and editable by project owners through semantic entries, evidence and eval failures.
```

## 20.2. Stage I required UI

```text
Document detail page
Semantic entries page
Source evidence view
RAG eval failures page
Fix action UI
Entry version/audit view
```

## 20.3. Stage I typing rule

Replace broad untyped payloads at core KB/eval boundaries with typed generated contracts.

Forbidden as stable core product contracts:

```text
Record<string, unknown>
any
unknown DB payload passthrough
stringly-typed failure classification
stringly-typed edit action payload
```

Allowed at infrastructure boundaries only:

```text
typed adapters that validate and convert raw JSON into domain/application DTOs
```

---

# 21. Stage J contract

Stage J adds structured price/table compilation.

## 21.1. Stage J goal

```text
Handle numeric/table/catalog knowledge with structured metadata, not vector search alone.
```

## 21.2. Stage J required concepts

```text
PriceItem
TableRecord
structured filters
table source refs
price/catalog entry kinds
```

## 21.3. Stage J retrieval rule

For numeric/table queries:

```text
semantic retrieval may find the relevant category/explanation
structured filters must answer numeric constraints
```

Examples:

```text
"Что дешевле 50 000?" → structured price filter
"Сколько стоит Ares?" → exact item lookup + source evidence
"Какие есть тарифы?" → retrieval + structured catalog summary
```

---

# 22. Summary contract

Knowledge Compilation Domain v1 defines `crm_bot` KB ingestion as an answer-oriented compiler:

```text
SourceDocument is uploaded raw material.
SourceChunk is technical source evidence.
SourceRef links knowledge to evidence.
AnswerCandidate is an untrusted extracted answer.
CandidateCluster deduplicates and merges candidates.
CanonicalKnowledgeEntry is the only production answer unit.
KnowledgeEnrichment improves retrieval but does not add facts.
EmbeddingText is derived internal search surface.
EmbeddingVector powers semantic search.
RetrievalSurface exposes only published grounded entries.
EvalCase/RagEvalResult test the system and must never become knowledge.
FailureClassification diagnoses eval failures.
KnowledgeEditAction turns failures into improvements.
PriceItem/TableRecord preserve structured numeric/table facts.
```

The target system is not:

```text
upload chunks and search them
```

The target system is:

```text
compile documents into grounded, searchable, testable and editable knowledge
```

Current implementation status:

```text
Stage A completed: SourceRef MVP / evidence boundary.
Stage B completed: SourceChunk persistence.
Stage C completed: CanonicalKnowledgeEntry persistence.
Stage D completed: RetrievalSurface runtime/eval alignment.
Stage E completed: compiler trace checkpoint.
Stage F completed: single production EmbeddingTextBuilder hardening.
Stage G next: RAG eval realignment.
```

The next architectural risk is not retrieval scoring.

The next architectural risk is stale naming and contracts:

```text
chunk-oriented eval names
expected_chunk_ids
raw embedding_text exposure
untyped failure classification
eval failures that cannot become product fixes
```

The next step must be:

```text
wide read-only reconnaissance for Stages G–J
narrow implementation of Stage G.1 only
targeted validation
full quality gate
```

Then continue:

```text
Stage G.2 — EvalCase expected entries/source refs
Stage G.3 — FailureClassification first-class
Stage G.4 — suggested KnowledgeEditAction
Stage H — executable KnowledgeEditAction product loop
Stage I — semantic KB/eval UI
Stage J — structured price/table compiler
```
