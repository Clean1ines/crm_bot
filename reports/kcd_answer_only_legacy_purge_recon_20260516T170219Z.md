# KCD answer-only legacy purge recon

## Git state

- `git status --short`: clean at recon start.
- `git branch --show-current`: `work`.
- `git log --oneline --decorate -8` head: `bbc5e69 (HEAD -> work) KCD: answer-only LLM resolver contract — limit LLM to answer resolution, keep deterministic enrichment`.
- `git diff --stat`: empty at recon start.
- Environment note: `venv/bin/python` is missing in this container, so requested venv commands cannot run unless the venv is restored.

## Legacy symbols found

Production code still contains these legacy KCD answer-merge / canonical-card symbols:

- `src/domain/project_plane/knowledge_preprocessing.py`
  - `KnowledgeAnswerMergeExecutionResult` with LLM-authored `question_variants`.
  - `KnowledgeSemanticMergeCanonicalCard`.
  - `KnowledgeSemanticMergeDecision.merged_embedding_text`.
  - `KnowledgeSemanticMergeDecision.canonical_card`.
  - `parse_answer_merge_payload(...)`.
  - `_parse_semantic_merge_canonical_card(...)`.
  - parser compatibility for `merged_embedding_text`.
- `src/application/ports/knowledge_port.py`
  - `KnowledgePreprocessorPort.merge_known_answer(...)` returning `KnowledgeAnswerMergeExecutionResult`.
- `src/infrastructure/llm/knowledge_preprocessor.py`
  - `merge_known_answer(...)`.
  - `_build_answer_merge_prompt(...)`.
  - `_load_answer_merge_prompt(...)`.
  - `ANSWER_MERGE_PROMPT_VERSION` / `ANSWER_MERGE_PROMPT_FILE` path.
  - `parse_answer_merge_payload(...)` usage and `question_variants` handling.
- `src/application/services/knowledge_ingestion_service.py`
  - `decision.merged_embedding_text` in final assembly and existing-document retighten plan.
  - semantic trace still reads `decision.canonical_card`, `decision.survivor_title`, and `decision.merged_embedding_text`.
  - metrics still expose historical `online_answer_merge_enabled`, `llm_merge_call_count`, `answer_merge_call_count` even though the compiler path now coerces deprecated known-intent matches to safe new fragments.
- Tests still import/assert legacy symbols in:
  - `tests/application/services/test_knowledge_ingestion_service.py`.
  - `tests/test_kad_v1_markdown_acquisition_slice.py`.
  - `tests/domain/test_knowledge_preprocessing.py`.
  - `tests/architecture/test_kcd_stage_k_answer_compiler_guard.py`.
- `src/agent/prompts/knowledge_answer_merge.txt` is now legacy and should be removed if no remaining runtime path uses `merge_known_answer(...)`.

Non-legacy occurrence note:

- `question_variants` remains valid in the FAQ compiler prompt and `KnowledgePreprocessingEntry` extraction/enrichment flow. It is forbidden only as answer-resolver LLM output / overwrite authority.

## Semantic resolver symbols found

- `KnowledgeAnswerResolutionCase` / `KnowledgeAnswerResolutionDecision` exist in domain.
- `KnowledgeSemanticMergeGroup` still wraps answer-resolution cases for current port compatibility.
- `tighten_semantic_merges(...)` is the active LLM resolver path in the port and Groq adapter.
- `_merge_entry_fields_deterministically(...)` already performs deterministic field union and rebuilds embedding text.
- `_apply_semantic_merge_tightening_decisions(...)` / `_retighten_existing_document_plan(...)` still need to use `decision.canonical_answer` instead of legacy `merged_embedding_text`.

## Target vocabulary

Preferred production names:

- `KnowledgeAnswerResolutionOption`
- `KnowledgeAnswerResolutionCase`
- `KnowledgeAnswerResolutionDecision`
- `KnowledgeAnswerResolutionResult`
- `KnowledgeAnswerResolverExecutionResult`

Allowed decision fields:

- `case_id`
- `action`
- `canonical_answer`
- `reason`
- `confidence`

Forbidden old names in production resolver contract:

- `KnowledgeSemanticMergeCanonicalCard`
- `canonical_card`
- `merged_embedding_text`
- `KnowledgeAnswerMergeExecutionResult`
- `merge_known_answer`
- `parse_answer_merge_payload`
- `question_variants` from resolver output

Important boundary:

- `question_variants` may remain as deterministic/extraction enrichment on `KnowledgePreprocessingEntry` and in compiler source prompts.
- The answer resolver output must never return or overwrite question variants, synonyms, tags, source refs, source indexes, source excerpts, metadata, or embedding text.

## Minimal purge plan

1. Delete answer-merge execution DTO/parser/prompt path and remove `merge_known_answer(...)` from the preprocessor port and Groq adapter.
2. Delete `KnowledgeSemanticMergeCanonicalCard` and canonical-card parser.
3. Replace `KnowledgeSemanticMergeDecision.merged_embedding_text` with `canonical_answer`, and remove `canonical_card` entirely.
4. Update application assembly and existing-document retighten to read only `decision.canonical_answer`.
5. Update trace payload to expose only resolver fields: action, group/case id, candidate ids, canonical answer preview, reason, confidence.
6. Update tests and architecture guards to assert absence of old production symbols while allowing `question_variants` only in extraction/enrichment contexts.
