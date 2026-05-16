# KCD answer-only resolver strictness recon

## Git state

- `git status --short`: clean.
- Branch: `work`.
- HEAD: `b18c715 KCD: switch to answer-only LLM resolver, remove legacy answer-merge path and prompt`.
- `git diff --stat`: empty.
- `venv/bin/python`: absent in this container.

## Findings

1. Dead constants still exist in `knowledge_ingestion_service.py`:
   - `KCD_STAGE_K8_SEMANTIC_MERGE_CANDIDATE_EMBEDDING_TEXT_MAX_CHARS`
   - `KCD_STAGE_K8_SEMANTIC_MERGE_CANDIDATE_QUESTION_LIMIT`
   - `KCD_STAGE_K8_SEMANTIC_MERGE_CANDIDATE_SYNONYM_LIMIT`
   - `KCD_STAGE_K8_SEMANTIC_MERGE_CANDIDATE_TAG_LIMIT`
   Only `KCD_STAGE_K8_SEMANTIC_MERGE_CANDIDATE_ANSWER_MAX_CHARS` is still used by answer-only candidate/source excerpt construction and intent fallback.
2. Resolver parser is still permissive:
   - accepts `group_id` fallback when `case_id` is missing;
   - parses resolver-output `candidate_ids`;
   - ignores forbidden fields silently;
   - does not count forbidden output fields in metrics.
3. Architecture tests assert old path removal, but there is no guard preventing literal parsing of `candidate_ids` from resolver payload.
4. Suspect grouping currently uses title, answer, embedding_text, questions, synonyms, and tags in full-score path. The new target should allow suspect grouping to use deterministic title + canonical question + normalized questions, while keeping LLM payload answer-only.
5. `build_embedding_text(...)` currently includes title, canonical question, questions, and answer, but not deterministic synonyms/tags. If retrieval formula is intended to include deterministic enrichment, this function is the correct domain-level place to add synonyms/tags because final entries call it after merge.

## Target changes

- Remove dead KCD_STAGE_K8 candidate enrichment constants.
- Make resolver parser strict:
  - `case_id` required;
  - `group_id` fallback rejected;
  - `candidate_ids` rejected/ignored at parser boundary (prefer reject with validation error);
  - forbidden output fields rejected explicitly and counted via `invalid_forbidden_field_count` when possible.
- Keep application-side mapping of case/group id to candidate ids; never trust resolver candidate ids.
- Add architecture test that production parser does not read literal `candidate_ids` from resolver payload.
- Restrict suspect grouping text to title + canonical question + normalized questions (not answer/embedding/synonyms/tags for grouping similarity).
- Extend `build_embedding_text(...)` with deterministic synonyms/tags after questions and before answer.
