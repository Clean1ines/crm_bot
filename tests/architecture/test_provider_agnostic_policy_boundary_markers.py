from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCH_DOC_PATH = (
    REPO_ROOT
    / "docs/architecture/provider_agnostic_capacity_and_budget_policy_model.md"
)

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".sql",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
}

SCAN_ROOTS = (
    "src",
    "frontend/src",
    "migrations",
    "dev_scripts",
)

SKIPPED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "__pycache__",
}

ARCH_ALLOWLIST_PREFIXES = (
    "docs/architecture/",
    "tests/architecture/",
    "src/contexts/llm_runtime/infrastructure/providers/groq/",
)

PROVIDER_PROFILE_ALLOWLIST_PREFIXES = (
    "src/contexts/llm_runtime/infrastructure/config/",
    "src/contexts/llm_runtime/infrastructure/providers/groq/",
)

GROQ_FREE_FACT_MARKERS = (
    "qwen/qwen3-32b",
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout",
    "GPT_OSS_FREE_PLAN_TPM",
    "CLAIM_BUILDER_MODEL_TPM_TOKENS",
    "DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF",
)

KNOWN_GROQ_FREE_FACT_VIOLATION_PATHS = {
    "frontend/src/shared/api/generated/schema.ts",
    "frontend/src/shared/api/modules/aiPlayground.ts",
    "src/agent/nodes/intent_extractor.py",
    "src/application/ai_playground/contracts.py",
    "src/contexts/knowledge_workbench/application/sagas/handle_apply_draft_claim_compaction_result_command.py",
    "src/contexts/knowledge_workbench/application/sagas/handle_cluster_draft_claims_command.py",
    "src/contexts/knowledge_workbench/application/sagas/map_claim_builder_section_plans_to_execution_schedule.py",
    "src/contexts/knowledge_workbench/application/sagas/handle_prepare_claim_builder_dispatch_batch_command.py",
    "src/contexts/knowledge_workbench/application/sagas/handle_prepare_draft_claim_compaction_dispatch_batch_command.py",
    "src/contexts/knowledge_workbench/application/sagas/handle_reconcile_draft_claim_compaction_progress_command.py",
    "src/contexts/knowledge_workbench/application/sagas/repair_knowledge_extraction_command_payload.py",
    "src/contexts/knowledge_workbench/extraction/application/models/draft_claim_compaction_reduction_models.py",
    "src/contexts/knowledge_workbench/extraction/application/policies/draft_claim_compaction_batch_budget_policy.py",
    "src/contexts/knowledge_workbench/extraction/application/policies/draft_claim_compaction_reduction_planner_policy.py",
    "src/contexts/knowledge_workbench/rag_eval/application/policies/workbench_rag_eval_question_generation_route_policy.py",
    "src/contexts/knowledge_workbench/rag_eval/application/use_cases/generate_workbench_rag_eval_questions_batch.py",
    "src/contexts/llm_runtime/application/capacity/resolve_llm_dispatch_preparation_strategy.py",
    "src/contexts/llm_runtime/domain/capacity/llm_model_route_catalog.py",
    "src/infrastructure/config/settings.py",
    "src/interfaces/http/knowledge.py",
}

PROVIDER_GROQ_PATTERN = re.compile(r"provider\s*=\s*['\"]groq['\"]")

KNOWN_PROVIDER_GROQ_VIOLATION_PATHS = {
    "src/application/ai_playground/contracts.py",
    "src/application/ai_playground/run_ai_playground.py",
    "src/contexts/knowledge_workbench/application/sagas/append_capacity_window_prepare_wakeup.py",
    "src/contexts/knowledge_workbench/application/sagas/claim_builder_dispatch_preparation.py",
    "src/contexts/knowledge_workbench/application/sagas/repair_knowledge_extraction_command_payload.py",
    "src/contexts/knowledge_workbench/rag_eval/application/policies/workbench_rag_eval_question_generation_route_policy.py",
    "src/contexts/llm_runtime/application/capacity/resolve_llm_dispatch_preparation_strategy.py",
    "src/contexts/llm_runtime/domain/capacity/llm_model_route_catalog.py",
    "src/infrastructure/config/settings.py",
    "src/interfaces/composition/ai_playground.py",
    "src/interfaces/composition/knowledge_extraction_after_upload_composition.py",
    "src/interfaces/composition/knowledge_extraction_workflow_resume.py",
    "src/interfaces/composition/llm_dispatch_executor.py",
    "src/interfaces/composition/prepare_llm_dispatch_batch.py",
    "src/interfaces/http/limits.py",
}

RESERVED_OUTPUT_TOKEN_TARGET_TERMS = (
    "estimated_output_tokens",
    "request_output_cap_tokens",
    "reserved_total_tokens",
    "segmentation_input_safety_gap_tokens",
)

KNOWN_RESERVED_OUTPUT_TOKENS_PATHS = {
    "src/contexts/knowledge_workbench/application/sagas/claim_builder_dispatch_preparation.py",
    "src/contexts/knowledge_workbench/application/sagas/handle_apply_draft_claim_compaction_result_command.py",
    "src/contexts/knowledge_workbench/application/sagas/handle_cluster_draft_claims_command.py",
    "src/contexts/knowledge_workbench/application/sagas/llm_provider_message_capacity_estimate.py",
    "src/contexts/knowledge_workbench/application/sagas/map_claim_builder_section_plans_to_execution_schedule.py",
    "src/contexts/llm_runtime/application/policies/llm_quota_availability_policy.py",
    "src/contexts/llm_runtime/infrastructure/providers/groq/groq_dispatch_executor.py",
    "src/interfaces/composition/knowledge_extraction_degraded_fallback_confirmation.py",
    "src/interfaces/composition/prepare_llm_dispatch_batch.py",
}

COMPACTION_FIT_BY_GROQ_TPM_MARKERS = (
    "GPT_OSS_FREE_PLAN_TPM",
    "_work_item_fits_primary_tpm",
    "prompt_tokens + task_tokens + task_tokens",
    "prompt + task + task",
)

KNOWN_COMPACTION_FIT_BY_GROQ_TPM_PATHS = {
    "src/contexts/knowledge_workbench/extraction/application/policies/draft_claim_compaction_reduction_planner_policy.py",
}

DEFAULT_GROQ_CATALOG_MARKERS = (
    "default_groq_llm_model_route_catalog",
    "build_groq_free_plan_model_profiles",
)

KNOWN_DEFAULT_GROQ_CATALOG_PATHS = {
    "src/contexts/knowledge_workbench/rag_eval/application/policies/workbench_rag_eval_question_generation_route_policy.py",
    "src/contexts/llm_runtime/domain/capacity/llm_model_route_catalog.py",
    "src/interfaces/composition/knowledge_extraction_after_upload_composition.py",
    "src/interfaces/composition/knowledge_extraction_workflow_resume.py",
    "src/interfaces/composition/prepare_llm_dispatch_batch.py",
    "src/interfaces/http/limits.py",
}


def _repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _has_allowed_prefix(path: Path, prefixes: tuple[str, ...]) -> bool:
    rel = _repo_relative(path)
    return any(rel.startswith(prefix) for prefix in prefixes)


def _iter_text_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in TEXT_SUFFIXES:
                continue
            rel_parts = path.relative_to(REPO_ROOT).parts
            if any(part in SKIPPED_PARTS for part in rel_parts):
                continue
            if path.name.startswith(".env"):
                continue
            files.append(path)
    return tuple(files)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _unknown_marker_paths(
    *,
    markers: tuple[str, ...],
    known_paths: set[str],
    extra_allowed_prefixes: tuple[str, ...] = (),
) -> list[str]:
    allowed_prefixes = ARCH_ALLOWLIST_PREFIXES + extra_allowed_prefixes
    offenders: list[str] = []

    for path in _iter_text_files():
        if _has_allowed_prefix(path, allowed_prefixes):
            continue
        rel = _repo_relative(path)
        source = _read(path)
        matched = tuple(marker for marker in markers if marker in source)
        if matched and rel not in known_paths:
            offenders.append(f"{rel}: {', '.join(matched)}")

    return offenders


def test_architecture_document_contains_b0_boundary_contract() -> None:
    source = _read(ARCH_DOC_PATH)

    required_markers = (
        "Groq Free is an exotic provider/deployment profile.",
        "It must be implemented as a provider profile/policy implementation.",
        "It must not define the domain model of Workbench, Execution Runtime,",
        "DocumentSegmentationPolicy",
        "SourceUnitSplitPolicy",
        "PhaseTokenBudgetPolicy",
        "ProviderCapacityAccountingPolicy",
        "RequestOutputCapPolicy",
        "RouteSelectionPolicy",
        "AdmissionPolicy",
        "RetryEstimatePolicy",
        "AttemptDecisionPolicy",
        "CompactionBatchingPolicy",
        "CompactionReductionPolicy",
        "PhaseCompletionPolicy",
        "UserChoicePolicy",
        "prompt_tokens      = input",
        "completion_tokens  = output / answer",
        "total_tokens       = input + output",
        "max_completion_tokens = max output / max answer",
        "reserved_output_tokens` is a legacy ambiguous symbol",
        "GroqFreeCombinedTpmProfile owns:",
        "OpenAI paid",
        "DeepSeek cheap",
        "Local GPU",
        "B1a: vocabulary contract + compatibility mapping, no behavior change",
        "B1b: Groq Free effective output cap / request budget policy boundary",
        "B1c: claim-builder estimate rename/split",
        "B1d: estimator unification",
    )

    missing = [marker for marker in required_markers if marker not in source]
    assert not missing, "\n".join(missing)


def test_no_new_groq_free_facts_outside_profile_and_known_violations() -> None:
    offenders = _unknown_marker_paths(
        markers=GROQ_FREE_FACT_MARKERS,
        known_paths=KNOWN_GROQ_FREE_FACT_VIOLATION_PATHS,
    )

    assert not offenders, "\n".join(offenders)


def test_no_provider_groq_literal_in_generic_composition_or_admission_code() -> None:
    offenders: list[str] = []

    for path in _iter_text_files():
        if _has_allowed_prefix(
            path,
            ARCH_ALLOWLIST_PREFIXES + PROVIDER_PROFILE_ALLOWLIST_PREFIXES,
        ):
            continue
        rel = _repo_relative(path)
        if rel in KNOWN_PROVIDER_GROQ_VIOLATION_PATHS:
            continue
        if PROVIDER_GROQ_PATTERN.search(_read(path)):
            offenders.append(rel)

    assert not offenders, "\n".join(offenders)


def test_reserved_output_tokens_remains_legacy_only() -> None:
    offenders = _unknown_marker_paths(
        markers=("reserved_output_tokens",),
        known_paths=KNOWN_RESERVED_OUTPUT_TOKENS_PATHS,
    )

    assert not offenders, "\n".join(offenders)

    source = _read(ARCH_DOC_PATH)
    for target_term in RESERVED_OUTPUT_TOKEN_TARGET_TERMS:
        assert target_term in source


def test_groq_free_effective_output_cap_boundary_marker() -> None:
    source = _read(ARCH_DOC_PATH)

    required_markers = (
        "provider_default_output_cap_tokens = 2048",
        "effective_output_cap_tokens = request_output_cap_tokens or provider_default_output_cap_tokens",
        "tokens_remaining >= estimated_input_tokens + effective_output_cap_tokens",
        "missing explicit `max_completion_tokens` means provider default output cap, not unlimited output",
        "executor consumes prepared request budget; executor does not own admission math",
        "groq_dispatch_executor._resolve_max_completion_tokens",
        "groq_chat_request_builder",
    )

    missing = [marker for marker in required_markers if marker not in source]
    assert not missing, "\n".join(missing)


def test_no_new_compaction_fit_by_groq_tpm_domain_policy() -> None:
    offenders = _unknown_marker_paths(
        markers=COMPACTION_FIT_BY_GROQ_TPM_MARKERS,
        known_paths=KNOWN_COMPACTION_FIT_BY_GROQ_TPM_PATHS,
    )

    assert not offenders, "\n".join(offenders)


def test_default_groq_catalog_is_not_generic_default() -> None:
    offenders = _unknown_marker_paths(
        markers=DEFAULT_GROQ_CATALOG_MARKERS,
        known_paths=KNOWN_DEFAULT_GROQ_CATALOG_PATHS,
        extra_allowed_prefixes=PROVIDER_PROFILE_ALLOWLIST_PREFIXES,
    )

    assert not offenders, "\n".join(offenders)


def test_b1a_compatibility_map_and_followup_split_are_documented() -> None:
    source = _read(ARCH_DOC_PATH)
    normalized_source = source.replace("`", "")

    required_markers = (
        "## 8. B1 compatibility map",
        "B1a is a documentation and guard-marker slice only.",
        "B1a makes the legacy vocabulary compatibility contract explicit",
        "legacy reserved_output_tokens in segmentation budget → segmentation_input_safety_gap_tokens",
        "legacy reserved_output_tokens in claim-builder schedule payload → estimated_output_tokens",
        "legacy reserved_output_tokens in admission minimum output → estimated_output_tokens used as minimum_output_tokens",
        "legacy reserved_output_tokens in Groq request executor → request_output_cap_tokens / output cap source",
        "legacy estimated_prompt_tokens in LlmTaskCapacityProfile → estimated_input_tokens",
        "legacy estimated_completion_tokens in LlmTaskCapacityProfile → estimated_output_tokens",
        "legacy actual_prompt_tokens in capacity observations → actual_input_tokens",
        "legacy actual_completion_tokens in capacity observations → actual_output_tokens",
        "TokenBudgetCompatibilityMap",
        "LegacyTokenBudgetFieldMapping",
        "RequestOutputCapPolicy",
        "RoughTokenEstimator(multiplier)",
        "B1b:",
        "introduce RequestOutputCapPolicy",
        "introduce Groq Free provider_default_output_cap_tokens = 2048",
        "effective_output_cap_tokens = request_output_cap_tokens or provider_default_output_cap_tokens",
        "admission fits by estimated_input_tokens + effective_output_cap_tokens",
        "missing explicit max_completion_tokens is not unlimited output",
        "executor consumes prepared request budget",
        "B1c:",
        "migrate claim-builder schedule payload from reserved_output_tokens to estimated_output_tokens",
        "claim-builder schedule payload writes estimated_output_tokens as the expected answer estimate",
        "prepare/admission reads claim-builder estimated_output_tokens as minimum_output_tokens",
        "fail clearly when claim-builder schedule payload misses estimated_output_tokens",
        "do not treat legacy reserved_output_tokens as the claim-builder expected output estimate",
        "B1d:",
        "introduce single RoughTokenEstimator(multiplier)",
        "claim_builder multiplier target 3.3",
        "compaction multiplier target 3.7",
        "remove chars/3.3, chars/4, chars/4+40 drift",
    )

    missing = [marker for marker in required_markers if marker not in normalized_source]
    assert not missing, "\n".join(missing)


def test_b1c_claim_builder_schedule_payload_uses_estimated_output_tokens() -> None:
    producer = _read(
        REPO_ROOT / "src/contexts/knowledge_workbench/application/sagas/"
        "map_claim_builder_section_plans_to_execution_schedule.py",
    )
    preparation = _read(
        REPO_ROOT / "src/contexts/knowledge_workbench/application/sagas/"
        "claim_builder_dispatch_preparation.py",
    )
    prepare_batch = _read(
        REPO_ROOT / "src/interfaces/composition/prepare_llm_dispatch_batch.py",
    )

    assert '"estimated_output_tokens": estimated_output_tokens' in producer
    assert '"reserved_output_tokens": reserved_output_tokens' not in producer
    assert "estimate.estimated_output_tokens" in preparation
    assert "estimate.reserved_output_tokens" not in preparation
    assert "_estimated_output_tokens_from_due_record" in prepare_batch
    assert 'estimate_payload.get("estimated_output_tokens")' in prepare_batch


def test_b1d1_segmentation_vocabulary_uses_input_safety_gap_name() -> None:
    target_paths = (
        REPO_ROOT / "src/contexts/knowledge_workbench/document_segmentation/domain/"
        "segmentation_budget.py",
        REPO_ROOT / "src/contexts/knowledge_workbench/application/sagas/"
        "source_ingestion_segmentation_profiles.py",
        REPO_ROOT / "src/interfaces/composition/source_ingestion_first_phase.py",
        REPO_ROOT / "src/contexts/knowledge_workbench/application/sagas/"
        "create_source_units_for_ingestion.py",
    )

    for target_path in target_paths:
        source = _read(target_path)
        assert "segmentation_input_safety_gap_tokens" in source
        assert "reserved_output_tokens" not in source


def test_b1d2_rough_token_estimator_targets_are_not_reversed() -> None:
    source = _read(
        REPO_ROOT / "src/contexts/knowledge_workbench/document_segmentation/domain/"
        "segmentation_budget.py",
    )
    claim_builder_schedule = _read(
        REPO_ROOT / "src/contexts/knowledge_workbench/application/sagas/"
        "map_claim_builder_section_plans_to_execution_schedule.py",
    )
    compaction_batch = _read(
        REPO_ROOT / "src/contexts/knowledge_workbench/extraction/application/policies/"
        "draft_claim_compaction_batch_budget_policy.py",
    )
    compaction_cluster = _read(
        REPO_ROOT / "src/contexts/knowledge_workbench/application/sagas/"
        "handle_cluster_draft_claims_command.py",
    )
    compaction_repository = _read(
        REPO_ROOT
        / "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        "postgres_draft_claim_compaction_reduction_state_repository.py",
    )

    assert "CLAIM_BUILDER_ROUGH_TOKEN_ESTIMATOR" in source
    assert "multiplier=Fraction(33, 10)" in source
    assert "COMPACTION_ROUGH_TOKEN_ESTIMATOR" in source
    assert "multiplier=Fraction(37, 10)" in source
    assert "CLAIM_BUILDER_ROUGH_TOKEN_ESTIMATOR" in claim_builder_schedule
    assert "COMPACTION_ROUGH_TOKEN_ESTIMATOR" in compaction_batch
    assert "COMPACTION_ROUGH_TOKEN_ESTIMATOR" in compaction_cluster
    assert "COMPACTION_ROUGH_TOKEN_ESTIMATOR" in compaction_repository
    assert "// 4 + 40" not in compaction_batch
    assert "len(claim.embedding_text) // 4" not in compaction_cluster


def test_b1d3a_task_capacity_profile_exposes_target_accessors() -> None:
    profile_source = _read(
        REPO_ROOT / "src/contexts/llm_runtime/domain/capacity/"
        "llm_task_capacity_profile.py",
    )
    preflight_source = _read(
        REPO_ROOT / "src/contexts/llm_runtime/application/capacity/"
        "resolve_llm_dispatch_input_size_preflight.py",
    )

    assert "def estimated_input_tokens" in profile_source
    assert "def estimated_output_tokens" in profile_source
    assert "return self.estimated_input_tokens + self.estimated_output_tokens" in (
        profile_source
    )
    assert "command.profile.estimated_input_tokens" in preflight_source
    assert "estimated prompt tokens" not in preflight_source
    assert "_first_fallback_that_fits_prompt" not in preflight_source


def test_b1a_does_not_pretend_runtime_token_vocabulary_is_migrated() -> None:
    source = _read(ARCH_DOC_PATH)
    normalized_source = source.replace("`", "")

    required_markers = (
        "no runtime behavior changes",
        "no DB migrations",
        "no provider API calls",
        "no claim that reserved_output_tokens or max_completion_tokens is fixed",
    )

    missing = [marker for marker in required_markers if marker not in normalized_source]
    assert not missing, "\n".join(missing)
