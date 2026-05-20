# Knowledge Acquisition Domain v1

## Document status

Status: target architecture draft
Scope: crm_bot knowledge ingestion, document understanding, source structure extraction, answer candidate extraction, curation, and publication into retrieval surfaces.
Relation to existing document: this document complements `docs/architecture/knowledge_compilation_domain_v1.md`. It does not replace it.

`Knowledge Compilation Domain v1` describes how extracted candidates become canonical knowledge and retrieval-safe entries. `Knowledge Acquisition Domain v1` describes what must happen earlier: how incoming documents are accepted, parsed, structurally understood, transformed into semantic source units, and prepared for compilation.

The central correction is this:

> The system must not start from FAQ answers. It must start from source documents and recover trustworthy knowledge objects from them.

---

## 1. Problem

The current pipeline has historically treated document ingestion as a preprocessing step for RAG/FAQ output. This caused the system to optimize too early for the final client-facing assistant answer while under-designing the earlier and more important problem: how knowledge is extracted, understood, validated, stored, and made accessible.

The result is a category error: technical chunks, source fragments, answer candidates, published knowledge entries, evaluation cases, and retrieval rows can collapse into the same mental model. The word `chunk` becomes overloaded and begins to mean too many things at once.

Observed failure modes include:

* technical text chunks being treated as semantic units;
* Markdown sections being split without respecting heading hierarchy;
* nested examples being extracted as independent FAQ answers;
* test questions being published as production knowledge;
* answer candidates being concatenated instead of synthesized during merge;
* raw extraction results and published entries being mixed in reporting;
* frontend progress showing token usage but not meaningful document-understanding progress;
* long-running extraction losing useful progress when late validation fails;
* retrieval quality depending on whether noisy or over-fragmented candidates happened to be published.

The core issue is not simply that the RAG search needs better ranking. The deeper issue is that retrieval is being asked to compensate for weak source understanding.

A production knowledge system requires a first-class domain for acquisition:

```text
SourceDocument
→ DocumentStructure
→ SemanticSourceUnit
→ AnswerCandidate
→ CandidateCluster
→ CanonicalKnowledgeEntry
→ RetrievalSurface
```

---

## 2. Design stance

The system must be designed as a knowledge acquisition and compilation pipeline, not as a direct “document to FAQ” converter.

Important positions:

1. Input formats are adapters, not the domain.
2. Markdown is only the first structurally easy adapter.
3. PDF, DOCX, TXT, JSON, CSV, and other formats must eventually feed the same intermediate representation.
4. Retrieval surfaces must only be built from published canonical knowledge, not arbitrary raw fragments.
5. Raw candidates must be preserved for audit, retry, debugging, and user inspection.
6. Long-running LLM work must be recoverable, pausable, cancellable, and observable.
7. LLMs may classify and synthesize meaning, but deterministic code must not pretend to understand semantic roles through hardcoded business dictionaries.
8. Deterministic code may safely normalize, trim, exact-deduplicate, preserve source references, validate schemas, and enforce invariants.
9. Semantic interpretation belongs to the LLM or to explicitly modeled document structure, not to ad-hoc keyword filters.

---

## 3. Relation to Knowledge Compilation Domain v1

The existing `knowledge_compilation_domain_v1.md` should remain the target document for the compilation side:

```text
AnswerCandidate
→ CandidateCluster
→ CanonicalKnowledgeEntry
→ KnowledgeEnrichment
→ EmbeddingText
→ RetrievalSurface
→ EvalCase / RagEval
```

This new document defines the preceding side:

```text
SourceDocument
→ SourceAsset
→ DocumentStructure
→ SourceBlock / SourceSection
→ SemanticSourceUnit
→ AnswerCandidateExtractionResult
```

Together they form a full knowledge lifecycle:

```text
Upload
→ Source acquisition
→ Document understanding
→ Semantic source unit extraction
→ Candidate extraction
→ Candidate curation
→ Canonical publication
→ Retrieval surface indexing
→ Runtime retrieval
→ Evaluation and improvement
```

The boundary between the two documents is intentionally clear:

* Acquisition owns source format handling and document structure recovery.
* Compilation owns candidate merging, canonicalization, publication, and retrieval-surface construction.

---

## 4. Bounded contexts

### 4.1 Source Ingestion Context

Responsible for accepting files and creating durable source records.

Entities:

* `SourceDocument`
* `SourceAsset`
* `DocumentMetadata`
* `UploadSession`

Responsibilities:

* accept uploaded file;
* determine MIME type and logical format;
* store file or source reference;
* calculate checksum;
* associate document with project/user;
* initialize processing status;
* never attempt to infer final answer cards directly.

Non-responsibilities:

* no FAQ extraction;
* no answer synthesis;
* no retrieval ranking;
* no publication into production retrieval surface.

---

### 4.2 Document Understanding Context

Responsible for recovering document structure.

Entities:

* `DocumentStructure`
* `SourceBlock`
* `SourceSection`
* `SourceHeading`
* `SourceParagraph`
* `SourceList`
* `SourceTable`
* `SourceSpan`
* `DocumentOutline`

Responsibilities:

* parse format-specific structure;
* preserve source references;
* identify headings, paragraphs, lists, tables, and nested sections;
* create a normalized structure independent of source format;
* preserve enough metadata for later audit and UI previews.

Non-responsibilities:

* not deciding final production answers;
* not merging business meanings;
* not publishing to RAG.

---

### 4.3 Semantic Source Unit Context

Responsible for turning structural units into units suitable for semantic interpretation.

Entities:

* `SemanticSourceUnit`
* `SemanticSourceUnitRole`
* `SemanticSourceUnitExtractionPlan`

Responsibilities:

* group blocks/sections into meaningful source units;
* classify unit role when possible;
* preserve parent-child relationships;
* feed units into candidate extraction;
* avoid arbitrary token chunks when document structure is available.

Possible roles:

* `faq_container`
* `single_answer`
* `instruction`
* `policy`
* `price_table`
* `test_suite`
* `glossary`
* `product_description`
* `support_rule`
* `escalation_rule`
* `reference_list`
* `mixed`
* `irrelevant`
* `unknown`

---

### 4.4 Candidate Extraction Context

Responsible for creating raw answer candidates from semantic source units.

Entities:

* `AnswerCandidateExtractionResult`
* `RawAnswerCandidate`
* `ExtractionWarning`
* `ExtractionError`

Responsibilities:

* call LLM or deterministic extractor;
* extract answer candidates according to unit role;
* save raw candidates immediately after each unit or batch;
* preserve source evidence;
* track token usage and model usage;
* report partial progress.

Non-responsibilities:

* not publishing final canonical entries directly;
* not deleting raw evidence automatically;
* not forcing every source unit into FAQ shape.

---

### 4.5 Candidate Curation Context

This overlaps with `Knowledge Compilation Domain v1` and should remain aligned with it.

Responsibilities:

* deterministic cleanup;
* exact duplicate collapse;
* semantic merge;
* validation;
* accepted/rejected/needs-review decisions;
* publication into canonical entries.

Key principle:

> Raw extracted candidates are evidence and audit artifacts. Published canonical knowledge entries are production objects. They are not the same thing.

---

### 4.6 Retrieval Surface Context

Owned primarily by the compilation/retrieval architecture.

Responsibilities:

* build production-safe retrieval entries from published canonical knowledge;
* generate embedding text;
* index vector/lexical representations;
* exclude raw, rejected, test-only, and non-production artifacts.

---

## 5. Core entities

### 5.1 SourceDocument

Represents an uploaded or imported document.

Fields:

```text
id
project_id
file_name
source_format
mime_type
size_bytes
checksum
status
created_by
created_at
updated_at
raw_asset_ref
metadata
```

A `SourceDocument` is not knowledge yet. It is only a source.

---

### 5.2 SourceAsset

Represents the stored raw file or external source reference.

Fields:

```text
id
document_id
storage_kind
storage_uri
checksum
content_type
created_at
```

---

### 5.3 DocumentStructure

Normalized structural representation of a source document.

Fields:

```text
document_id
source_format
blocks
sections
outline
parser_version
warnings
metadata
```

A `DocumentStructure` should be reproducible from a source asset and parser version.

---

### 5.4 SourceBlock

Small structural block extracted from the source.

Examples:

* paragraph;
* heading;
* list item;
* table cell;
* table row;
* code block;
* quote;
* image caption;
* page text block.

Fields:

```text
id
document_id
block_type
text
level
order_index
page_number
parent_block_id
source_span
layout_metadata
```

---

### 5.5 SourceSection

A higher-level structural grouping.

Fields:

```text
id
document_id
title
level
order_index
parent_section_id
block_ids
child_section_ids
source_span
metadata
```

Markdown `##` and `###`, DOCX headings, PDF detected headings, and TXT heading-like lines can all become `SourceSection` records.

---

### 5.6 SourceSpan

Stable source reference for audit and evidence.

Fields:

```text
document_id
start_offset
end_offset
page_number
bbox
line_start
line_end
section_path
excerpt
```

For Markdown, offsets and section path are usually enough. For PDF, page and layout coordinates may be needed.

---

### 5.7 SemanticSourceUnit

The main bridge between document structure and knowledge extraction.

Fields:

```text
id
document_id
source_format
title
body
children
structural_path
source_refs
role_hint
role_confidence
metadata
```

Examples:

* one Markdown `##` section;
* one Markdown `###` FAQ item;
* one PDF section under a detected heading;
* one DOCX heading section;
* one price table;
* one group of rows from CSV;
* one plain-text detected topic block.

A `SemanticSourceUnit` is still not a final answer. It is a unit that can be interpreted.

---

### 5.8 SemanticSourceUnitRole

Represents the role of a unit.

Allowed values:

```text
faq_container
single_answer
instruction
policy
price_table
test_suite
glossary
product_description
support_rule
escalation_rule
reference_list
mixed
irrelevant
unknown
```

Role classification may be deterministic, LLM-based, or hybrid. It must be stored with confidence and source evidence.

---

### 5.9 AnswerCandidateExtractionResult

Result of processing one semantic source unit or batch.

Fields:

```text
unit_id
document_id
status
raw_candidates
warnings
errors
model_usage
metrics
created_at
```

---

### 5.10 RawAnswerCandidate

Raw extracted candidate before curation.

Fields:

```text
id
project_id
document_id
unit_id
title
canonical_question
answer
questions
synonyms
tags
source_refs
confidence
status
metadata
created_at
```

Raw candidates must be durable as soon as they are extracted.

---

### 5.11 CanonicalKnowledgeEntry

Final published knowledge object. Defined primarily in the compilation domain.

A canonical entry must not be treated as a source document fragment. It is a curated production object grounded in source evidence.

---

### 5.12 RetrievalSurfaceEntry

Runtime searchable projection of a canonical entry.

It must not include:

* raw candidates;
* rejected candidates;
* eval-only questions;
* source chunks without production meaning;
* compiler diagnostics;
* test suites unless explicitly published as knowledge about testing.

---

## 6. Input format strategy

The system must support multiple input formats through adapters.

### 6.1 Markdown

Quality level: high.

Available structure:

* headings;
* nested sections;
* lists;
* code blocks;
* blockquotes;
* tables in Markdown syntax;
* explicit FAQ-like patterns.

Strategy:

* parse by heading hierarchy;
* use `##` as primary semantic section boundary;
* preserve `###` as child sections;
* classify whether child sections are independent cards or body structure;
* avoid arbitrary token splitting unless a section is too large.

---

### 6.2 DOCX

Quality level: medium to high depending on styles.

Available structure:

* headings;
* paragraphs;
* lists;
* tables;
* styles;
* page breaks sometimes.

Strategy:

* use heading styles when available;
* fallback to textual heading detection;
* preserve tables as structured units;
* build sections from heading hierarchy.

---

### 6.3 Text-based PDF

Quality level: medium to low.

Available structure:

* pages;
* text blocks;
* approximate layout;
* possible font/position metadata;
* weak heading detection.

Strategy:

* extract page blocks;
* detect heading candidates;
* group following blocks into sections;
* preserve page references;
* use LLM only where deterministic structure is weak.

---

### 6.4 Scanned PDF / images

Quality level: low unless OCR/layout is strong.

Strategy:

* OCR;
* layout detection;
* page-block extraction;
* confidence tracking;
* heavier user-facing warnings.

---

### 6.5 Plain TXT

Quality level: variable.

Strategy:

* detect blank-line sections;
* detect numbered headings;
* detect Markdown-like headings;
* use LLM-assisted segmentation when needed;
* expose lower confidence.

---

### 6.6 JSON / CSV / tables

Quality level: high if schema is clear.

Strategy:

* do not treat as prose by default;
* map rows/objects to structured semantic units;
* infer entity type: FAQ row, product row, price row, policy row, etc.;
* preserve row/column references.

---

## 7. Markdown-specific target behavior

Markdown is the first implementation slice because it has explicit structure. However, Markdown must be implemented as an adapter into the general source-structure domain.

### 7.1 Primary split

For Markdown documents:

```text
# document title
## primary section
### child section
```

`##` sections should become primary `SourceSection` / `SemanticSourceUnit` boundaries.

If a `##` section fits the configured LLM budget, it should not be split into arbitrary token chunks.

If a `##` section is too large, it may be split internally, but every split must preserve:

* parent section title;
* section path;
* child subsection context;
* source span;
* stable ordering.

---

### 7.2 FAQ container section

Example:

```markdown
## 31. Частые вопросы и правильные ответы

### Что это за сервис?
Это AI-ассистент для бизнеса...

### Чем вы занимаетесь?
Мы помогаем бизнесу...
```

Expected interpretation:

```text
unit_role = faq_container
```

Expected extraction:

* each `###` block with a question-like heading and direct answer body becomes a raw answer candidate;
* parent `##` title is source context, not a published answer itself;
* no giant card titled “Частые вопросы и правильные ответы” should be created unless the section has its own meaningful explanatory body.

---

### 7.3 Single-answer section with examples

Example:

```markdown
## 34. Правило для RAG-поиска

Каждая тема должна быть отделена от других.

Не смешивать:
- возврат средств и отключение сервиса;
- цену и сроки внедрения;
- интеграции и CRM-отчётность;
```

Expected interpretation:

```text
unit_role = single_answer or instruction
```

Expected extraction:

* one card about the RAG search rule / topic separation rule;
* list items are examples inside the answer;
* no independent cards about refunds, price, integrations, or other examples;
* the answer must include both the rule and examples.

Valid candidate shape:

```text
title: Правило для RAG-поиска
canonical_question: Как работает правило разделения тем в RAG-поиске?
answer: Каждая тема должна быть отделена от других. В RAG-поиске нельзя смешивать разные смысловые темы в одну карточку: ...
questions:
- Как работает правило разделения тем в RAG-поиске?
- Как в системе разделяются темы для RAG-поиска?
- Что означает правило разделения тем в RAG-поиске?
```

---

### 7.4 Test suite section

Example:

```markdown
## 32. Тестовые вопросы для проверки базы знаний

Эти вопросы нужно использовать для тестирования preview и качества ответов.

### О продукте
- что это за сервис?
- чем вы занимаетесь?

Ожидаемая тема:
Описание продукта...
```

Expected interpretation:

```text
unit_role = test_suite
```

Expected extraction:

* one card about testing the knowledge base / preview quality;
* listed questions are body/evidence, not production FAQ cards;
* expected topics are part of the answer body;
* do not create production cards for “что это за сервис?” from this section.

This is not because test suites are always “bad”. It is because, in this structure, listed questions are examples in a testing artifact, not direct answers.

---

### 7.5 Mixed section

Some sections may contain both parent explanation and independent Q/A children.

Expected behavior:

* preserve parent card if it has meaningful body;
* create child cards only when child section contains independent answerable content;
* avoid splitting examples into cards;
* prefer fewer grounded candidates over many noisy candidates when uncertain.

---

## 8. Candidate extraction contract

The LLM must not receive a shapeless text chunk when structural information is available.

Preferred input:

```json
{
  "unit_id": "...",
  "source_format": "markdown",
  "section_title": "31. Частые вопросы и правильные ответы",
  "section_body": "...",
  "children": [
    {
      "title": "Что это за сервис?",
      "body": "Это AI-ассистент..."
    }
  ],
  "source_refs": [...]
}
```

The extraction prompt must require:

1. classify `unit_role`;
2. explain whether child sections are independent answer cards or body structure;
3. extract candidates according to the role;
4. preserve source evidence;
5. avoid unsupported cards;
6. avoid answer/question mismatch.

---

## 9. Rules for extraction

### 9.1 General rules

* Do not extract every question-like string as a production FAQ card.
* First determine the role of the source unit.
* A card requires a question/topic and an answer grounded in the same source unit.
* If a list is examples for a parent rule, keep it inside the parent answer.
* If a list is test questions, keep it inside the test-suite answer.
* If a child section contains a direct Q/A pair, extract it as a candidate.
* Do not create a card whose answer does not answer the canonical question.
* Do not create cards from headings alone without answer body.

### 9.2 Safe deterministic operations

Allowed in code:

* trimming whitespace;
* normalizing repeated spaces;
* exact duplicate removal inside `questions`, `synonyms`, `tags`;
* exact/fingerprint duplicate collapse;
* schema validation;
* source reference union;
* preserving ordering;
* rejecting structurally empty candidates.

Not allowed in code:

* hardcoded dictionaries of “bad topics”;
* hardcoded business terms like “refund”, “RAG”, “price” to determine semantic validity;
* pretending to understand whether a topic is meta/product/customer-facing without LLM or structure;
* deleting candidates solely because they contain certain words.

---

## 10. Merge and retighten contract

After raw candidates are extracted, the merge layer must operate over candidates, not raw source chunks.

Expected behavior:

```text
cards answering same user intent
→ one merged candidate / canonical entry
```

Merge must:

* group by semantic user intent;
* combine questions without duplicates;
* combine synonyms without duplicates;
* combine tags without duplicates;
* union source references;
* synthesize a new answer from all grounded answers;
* avoid simple concatenation;
* preserve merge metadata;
* mark absorbed candidates as duplicate/merged/superseded;
* keep raw candidates for audit.

Invalid merge output:

```text
Условия возврата зависят от ситуации. Условия возврата средств зависят от ситуации.
```

Valid merge output:

```text
Условия возврата зависят от ситуации и этапа работы. Для точного ответа лучше передать вопрос менеджеру, чтобы он уточнил детали.
```

---

## 11. Processing durability

Long-running processing must not lose progress.

Requirements:

* raw extraction result must be saved immediately after each semantic unit or batch;
* compiler batch status must be updated per batch;
* failures in later merge/publication must not delete raw progress;
* retry must reuse saved raw candidates when possible;
* user must be able to inspect raw candidates before and after failure;
* user must be able to delete raw drafts only explicitly;
* cancellation must leave already saved progress visible;
* pause/resume must be represented as first-class process states.

---

## 12. Processing report model

The user-facing report must reflect domain stages, not internal leftovers.

Recommended report fields:

```text
Document parsing:
- source format
- parser used
- sections found
- blocks found
- warnings

Semantic unit extraction:
- semantic units total
- processed units
- failed units
- skipped units

Candidate extraction:
- raw candidates saved
- invalid candidates
- extraction warnings
- token usage
- model usage

Mechanical cleanup:
- exact duplicate fields removed
- exact duplicate candidates collapsed

Semantic merge:
- merge groups found
- merge decisions completed
- merged candidates
- rejected merge groups
- fallback used

Publication:
- canonical entries published
- entries requiring review
- retrieval surface updated

Next actions:
- inspect raw candidates
- resume processing
- retry failed units
- publish ready entries
- delete raw drafts
- open published entries
```

Avoid obsolete fields such as “technical fragments” unless the field has a clear user-facing meaning.

---

## 13. Frontend requirements

The UI should show the process as a pipeline:

```text
1. Document uploaded
2. Structure extracted
3. Semantic units prepared
4. Raw cards extracted
5. Duplicates cleaned
6. Similar cards merged
7. Published to knowledge base
8. Retrieval surface updated
```

During processing, the user should be able to:

* see current stage;
* see meaningful counts;
* inspect saved raw drafts;
* expand/collapse draft details;
* see merge progress;
* see warnings/errors;
* stop processing;
* eventually pause/resume;
* publish ready entries;
* delete raw drafts after publication or review.

Draft preview should not be limited to three opaque cards. It should support:

* list of all draft titles/questions;
* expandable details;
* source excerpt preview;
* status badges;
* filtering by raw/merged/published/rejected.

---

## 14. Quality gates and invariants

### 14.1 Architecture invariants

* Domain layer must not import FastAPI, asyncpg, Redis, LLM clients, or frontend code.
* Input format adapters belong to infrastructure/application boundary, not domain policy.
* `SourceDocument` is not a knowledge entry.
* `SourceBlock` is not an answer candidate.
* `AnswerCandidate` is not a canonical knowledge entry.
* `EvalCase` is not production knowledge.
* `RetrievalSurfaceEntry` must be built only from production-safe published entries.

### 14.2 Extraction invariants

* Every candidate must have source evidence.
* A candidate answer must answer its canonical question.
* Listed examples must not become independent cards unless the section gives independent answers for them.
* Test questions must not become production FAQ cards unless explicitly authored as FAQ answers.
* Raw candidates must persist before merge/publication.

### 14.3 Merge invariants

* Merge must synthesize, not concatenate.
* Duplicates inside questions/synonyms/tags must be removed.
* Source refs must be preserved.
* Absorbed candidates must remain auditable.

---

## 15. Migration from current pipeline

The current system already has useful pieces:

* raw candidate persistence;
* compiler batches;
* online merge path;
* semantic retighten;
* frontend progress reports;
* retrieval surface logic;
* RAG preview/eval tooling.

The migration should not restart from scratch. It should insert the missing document-understanding layer before candidate extraction.

Suggested staged migration:

### Stage A — Domain contracts

Introduce domain/application types:

* `DocumentStructure`
* `SourceBlock`
* `SourceSection`
* `SemanticSourceUnit`
* `SemanticSourceUnitRole`
* `AnswerCandidateExtractionResult`

No large DB migration yet unless necessary.

### Stage B — Markdown structure extractor

Implement first adapter:

```text
Markdown document
→ DocumentStructure
→ SourceSections by heading hierarchy
→ SemanticSourceUnits
```

### Stage C — Compiler accepts semantic units

Modify extraction so Markdown documents use semantic units instead of arbitrary technical chunks.

Fallback technical chunk path can remain for non-structured formats temporarily.

### Stage D — Prompt contract update

Update LLM prompt to classify unit role before extraction.

### Stage E — Regression tests

Add tests for:

* FAQ container section;
* test suite section;
* RAG rule / single-answer section;
* merge synthesis;
* source evidence preservation;
* raw candidates saved before merge.

### Stage F — UI/report cleanup

Remove obsolete processing fields and expose acquisition-domain progress.

### Stage G — PDF/DOCX adapters

After Markdown architecture is stable, add structure extractors for DOCX/PDF.

---

## 16. First implementation slice: Markdown adapter

The first implementation should not be called “Markdown FAQ processing”. It should be called:

```text
MarkdownStructureExtractor for Knowledge Acquisition Domain v1
```

Acceptance criteria:

1. Markdown `##` sections become primary source sections.
2. Markdown `###` sections become child source sections.
3. The compiler receives structured semantic units, not plain token chunks, when processing Markdown.
4. FAQ container sections produce child Q/A candidates.
5. Test suite sections produce a parent test-suite knowledge candidate, not production FAQ cards from listed examples.
6. Rule/instruction sections produce one grounded candidate with examples inside the answer.
7. Source refs include section path and excerpt.
8. Raw candidates are saved immediately.
9. Online merge remains enabled.
10. Published entries are compacted canonical entries, not raw fragments.
11. No hardcoded dictionaries of bad/meta topics are introduced.
12. Frontend report shows meaningful stage progress.

---

## 17. Example expected behavior

### 17.1 FAQ section

Input:

```markdown
## 31. Частые вопросы и правильные ответы

### Что это за сервис?
Это AI-ассистент для бизнеса...

### Чем вы занимаетесь?
Мы помогаем бизнесу автоматизировать клиентские переписки...
```

Expected candidates:

```text
1. Что это за сервис? → Это AI-ассистент для бизнеса...
2. Чем вы занимаетесь? → Мы помогаем бизнесу автоматизировать клиентские переписки...
```

Not expected:

```text
Частые вопросы и правильные ответы → huge combined card
```

---

### 17.2 Test suite section

Input:

```markdown
## 32. Тестовые вопросы для проверки базы знаний

Эти вопросы нужно использовать для тестирования preview и качества ответов.

### О продукте
- что это за сервис?
- чем вы занимаетесь?

Ожидаемая тема:
Описание продукта...
```

Expected candidate:

```text
Какие тестовые вопросы используются для проверки базы знаний?
→ Эти вопросы используются для тестирования preview и качества ответов...
```

Not expected:

```text
Что это за сервис? → Описание продукта...
Чем вы занимаетесь? → Описание продукта...
```

---

### 17.3 RAG rule section

Input:

```markdown
## 34. Правило для RAG-поиска

Каждая тема должна быть отделена от других.

Не смешивать:
- возврат средств и отключение сервиса;
- цену и сроки внедрения;
```

Expected candidate:

```text
Как работает правило разделения тем в RAG-поиске?
→ Каждая тема должна быть отделена от других. В RAG-поиске нельзя смешивать разные смысловые темы...
```

Not expected:

```text
Есть ли возврат средств? → Каждая тема должна быть отделена от других.
Какая цена? → Не смешивать цену и сроки внедрения.
```

---

## 18. Open questions

1. Should `DocumentStructure` be persisted as first-class DB state or initially reconstructed from source document during processing?
2. Should `SemanticSourceUnit` be persisted before candidate extraction, or can it be represented as compiler batch metadata in the first slice?
3. How should source refs represent Markdown offsets robustly after normalization?
4. How much of unit role classification should be deterministic versus LLM-based?
5. Should test-suite knowledge be published into production retrieval surface by default, or marked as internal/eval-facing unless user chooses otherwise?
6. What UI affordance should distinguish production knowledge from internal operational knowledge about the assistant/system itself?
7. How should PDF layout confidence be reflected in user-facing processing reports?

---

## 19. Non-goals for the first slice

* Full PDF understanding.
* OCR pipeline.
* Full DB redesign.
* Perfect semantic merge.
* Human review workflow with manual editing.
* Cross-document canonical knowledge graph.
* Automatic correction of all LLM hallucinations.

The first slice should prove the correct architecture with Markdown while keeping the path open for PDF/DOCX/TXT through the same intermediate representation.

---

## 20. Summary

The system needs a first-class Knowledge Acquisition Domain because knowledge quality is determined before retrieval.

Markdown-specific fixes are useful but insufficient unless they are implemented as part of a general source-structure architecture.

Target model:

```text
Input adapters
→ DocumentStructure
→ SemanticSourceUnit
→ RawAnswerCandidate
→ Candidate curation / merge
→ CanonicalKnowledgeEntry
→ RetrievalSurface
```

The key architectural correction is to stop treating preprocessing as “make FAQ from text”. It must become “understand source documents and compile grounded knowledge objects”.
