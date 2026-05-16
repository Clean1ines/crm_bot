# KCD answer-only LLM resolver recon

## Git state

- `git status --short`: clean.
- `git log --oneline -5`:
  - `2f052ca Add deterministic-first answer unit merge`
  - `f3ef32c Fix KCD observability UI wiring`
  - `ebe71b6 feat: merge process progress ui`
  - `ea69777 Add Groq Scout fallback for oversized requests`
  - `0eecff6 Add KAD Markdown source unit extraction`
- `git diff --stat`: empty before this report.

## Current merge / resolver paths inspected

- `src/application/services/knowledge_ingestion_service.py`
  - Builds suspect groups from `KnowledgePreprocessingEntry`.
  - Calls `KnowledgePreprocessorPort.tighten_semantic_merges(...)` for compiled-ingestion tightening and existing-document retightening.
  - Applies decisions through `_apply_semantic_merge_tightening_decisions(...)` / `_retighten_existing_document_plan(...)`.
  - Already has deterministic field union in `_merge_entry_fields_deterministically(...)` and deterministic cleanup before LLM.
- `src/domain/project_plane/knowledge_preprocessing.py`
  - Defines `KnowledgeSemanticMergeCandidate`, `KnowledgeSemanticMergeGroup`, `KnowledgeSemanticMergeDecision`, `KnowledgeSemanticMergeCanonicalCard`.
  - Parses semantic tightening output including legacy `canonical_card`.
- `src/infrastructure/llm/knowledge_preprocessor.py`
  - Builds `semantic_merge_tightening` prompt.
  - Current prompt sends `suspect_groups` via `group.to_payload()`.
  - Current schema asks model for `canonical_card`, `merged_embedding_text`, `survivor_title`, and `candidate_ids`.
- `src/application/ports/knowledge_port.py`
  - `KnowledgePreprocessorPort.tighten_semantic_merges(...)` accepts `Sequence[KnowledgeSemanticMergeGroup]` and returns `KnowledgeSemanticMergeExecutionResult`.
- `src/agent/prompts/knowledge_answer_merge.txt`
  - Pairwise answer merge prompt is separate legacy offline pairwise flow and already says not to return enrichment fields; semantic tightening prompt is inline in infrastructure.
- Tests inspected:
  - `tests/test_kcd_deterministic_first_merge.py`
  - `tests/test_kad_v1_markdown_acquisition_slice.py`
  - `tests/application/services/test_knowledge_ingestion_service.py`
  - architecture guards around KCD deterministic merge / retighten payload.

## Current entities / legacy points

- `KnowledgeSemanticMergeCandidate` currently contains `title`, `answer`, `embedding_text`, `questions`, `synonyms`, `tags`, and `source_ref_count`.
- `_semantic_merge_candidate_from_entry(...)` currently says enrichment is needed for LLM intent comparison and sends compact questions/synonyms/tags/embedding text.
- `KnowledgeSemanticMergeGroup.to_payload()` returns full candidate payloads.
- `KnowledgeSemanticMergeCanonicalCard` is a domain DTO for full-card LLM output.
- `KnowledgeSemanticMergeDecision` currently can contain `canonical_card` and `merged_embedding_text`.
- `_build_semantic_merge_tightening_prompt(...)` currently instructs the LLM to return `canonical_card` with answer/enrichment/source/publishability plus `merged_embedding_text`.
- `parse_semantic_merge_tightening_payload(...)` currently parses legacy `canonical_card`.
- `_entry_with_semantic_merge_decision(...)` currently treats `canonical_card` as authoritative for title/answer/canonical_question/source indexes and can use `decision.merged_embedding_text` as embedding text.
- `_semantic_merge_decision_is_publishable(...)` currently depends on `canonical_card.publishable`.
- `_apply_semantic_merge_tightening_decisions(...)` can delete entries when a non-publishable canonical card is returned.
- `_merge_entry_fields_deterministically(...)` already owns deterministic union for answer/source_excerpt/questions/synonyms/tags/source_chunk_indexes and rebuilds `embedding_text` via `build_embedding_text(...)`.
- `deterministic_retighten_existing_document_plan` equivalent is `_deterministic_retighten_existing_document_plan(...)`; it runs before LLM in existing-document retightening.

## Target answer-only contract design

### Where LLM currently receives too much

- Through `KnowledgeSemanticMergeGroup.to_payload()` and `_build_semantic_merge_tightening_prompt(...)`, the LLM receives `title`, `answer`, `embedding_text`, `questions`, `synonyms`, `tags`, and `source_ref_count` for each candidate.
- This lets the LLM act as a whole-card merge engine instead of an answer-fragment resolver.

### Where LLM currently returns `canonical_card`

- Inline semantic tightening prompt schema explicitly requests `canonical_card`.
- Domain parser accepts `canonical_card` and builds `KnowledgeSemanticMergeCanonicalCard`.
- Application assembly reads `decision.canonical_card` in `_entry_with_semantic_merge_decision(...)` and `_semantic_merge_decision_is_publishable(...)`.

### Fields that must stay deterministic

- `source_refs` / `source_excerpt`: mechanical concat + exact dedup.
- `questions`: mechanical concat + normalized exact dedup.
- `synonyms`: mechanical concat + normalized exact dedup.
- `tags`: mechanical concat + normalized exact dedup.
- `metadata`: application-owned trace/counters.
- `embedding_text`: rebuilt from final entry with `build_embedding_text(...)`.
- Candidate survivor/source index bookkeeping.

### Fields allowed in answer-only resolver input

- `case_id` / group id.
- `question_intent` as a compact intent string derived from title/canonical question/first question.
- `answers[]` with only:
  - `id` / candidate id;
  - `answer`;
  - `source_excerpt` as evidence excerpt text.

### Fields forbidden in resolver input/output

Forbidden input:

- `questions`, `synonyms`, `tags`, `embedding_text`, `metadata`, `source_refs`, full canonical entry/card objects, source ref objects.

Forbidden output:

- `questions`, `synonyms`, `tags`, `source_refs`, `source_excerpt`, `embedding_text`, `metadata`, `canonical_card`, arbitrary final entry/card.

Allowed output only:

- `decisions[]` with `case_id`, `action`, `canonical_answer`, `reason`, `confidence`.
- Application maps `merge` to legacy internal `KnowledgeSemanticMergeDecision` for now, with `candidate_ids` derived from the original case, and treats all non-merge actions as keep-separate.

## Minimal implementation plan

1. Add answer-only DTOs in domain preprocessing module, keeping them infrastructure-free.
2. Build answer-only cases from existing semantic groups in infrastructure prompt builder (or equivalent adapter) without changing the public port in this slice.
3. Rewrite semantic tightening prompt schema to answer-only resolver schema.
4. Parse only answer-only decisions; ignore legacy `canonical_card` and enrichment keys if returned.
5. Change application decision application so only `decision.merged_embedding_text` is used as canonical answer, while enrichment/evidence/retrieval fields remain deterministic.
6. Keep legacy classes/fields for compatibility, but remove production authority from `canonical_card`.
7. Add focused tests for prompt payload, output ignoring, deterministic field preservation, embedding rebuild, and LLM call gating after deterministic merge.
