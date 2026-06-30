from __future__ import annotations

DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF = "openai/gpt-oss-120b"

DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_DRAFT_VS_DRAFT = "draft_vs_draft"
DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_SINGLE_DRAFT = "single_draft_claim_enrichment"
DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_COMPACTED_VS_COMPACTED = "compacted_vs_compacted"
DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_MIXED = "mixed"
DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_REDUCED_REWRITE = "reduced_rewrite"

_DRAFT_VS_DRAFT_PROMPT_TOKENS = 2_050
_SINGLE_DRAFT_PROMPT_TOKENS = 1_100
_ENRICHED_PROMPT_TOKENS = 2_150
_REDUCED_REWRITE_PROMPT_TOKENS = 400
_REQUEST_SAFETY_GAP_TOKENS = 256
_DEFAULT_MAX_BATCH_TOKENS = 8_000


def draft_claim_compaction_artifact_tokens(text: str) -> int:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    if not text.strip():
        return 0
    return max(1, len(text) // 4)


def draft_claim_compaction_prompt_tokens(prompt_variant: str) -> int:
    if prompt_variant == DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_DRAFT_VS_DRAFT:
        return _DRAFT_VS_DRAFT_PROMPT_TOKENS
    if prompt_variant == DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_SINGLE_DRAFT:
        return _SINGLE_DRAFT_PROMPT_TOKENS
    if prompt_variant in {
        DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_COMPACTED_VS_COMPACTED,
        DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_MIXED,
    }:
        return _ENRICHED_PROMPT_TOKENS
    if prompt_variant == DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_REDUCED_REWRITE:
        return _REDUCED_REWRITE_PROMPT_TOKENS
    raise ValueError(f"unknown draft claim compaction prompt variant: {prompt_variant}")


def draft_claim_compaction_request_safety_gap_tokens() -> int:
    return _REQUEST_SAFETY_GAP_TOKENS


def draft_claim_compaction_max_batch_tokens(prompt_variant: str) -> int:
    prompt_tokens = draft_claim_compaction_prompt_tokens(prompt_variant)
    return max(1, (_DEFAULT_MAX_BATCH_TOKENS - prompt_tokens) // 2)
