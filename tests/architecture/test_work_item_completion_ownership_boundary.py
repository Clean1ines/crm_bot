from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LLM_RUNTIME_ROOT = PROJECT_ROOT / "src/contexts/llm_runtime"
EXECUTION_RUNTIME_ROOT = PROJECT_ROOT / "src/contexts/execution_runtime"
WORKBENCH_ROOT = PROJECT_ROOT / "src/contexts/knowledge_workbench"

COMPLETION_BOUNDARY_VOCABULARY = """
DispatchAttempt success = provider/LLM execution succeeded.
Recorded result = technical or phase candidate result exists.
Domain applied = phase-specific result persisted/materialized.
WorkItem completed = domain applied, not LLM success.
"""

WORKBENCH_IMPORT_PREFIXES = ("src.contexts.knowledge_workbench",)

LLM_RUNTIME_FORBIDDEN_SEMANTIC_TOKENS = (
    "DraftClaimObservation",
    "ValidatedDraftClaimObservationCandidate",
    "ClaimBuilder",
    "DraftClaimCompaction",
    "knowledge_workbench",
    "possible_questions",
    "evidence_block",
    "exclusion_scope",
    "granularity",
    "RETRY_EMPTY_CLAIMS_CHECK_MODEL",
)

EXECUTION_RUNTIME_FORBIDDEN_SEMANTIC_TOKENS = (
    "DraftClaimObservation",
    "ValidatedDraftClaimObservationCandidate",
    "ClaimBuilder",
    "DraftClaimCompaction",
    "Compaction",
    "possible_questions",
    "evidence_block",
    "exclusion_scope",
    "knowledge_workbench",
)

CLAIM_BUILDER_VALIDATION_TOKENS = (
    "VALID_EMPTY",
    "possible_questions",
    "exclusion_scope",
    "evidence_block",
    "granularity",
    "LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE",
)

CLAIM_BUILDER_EMPTY_POLICY_TOKENS = (
    "empty_claims_attempt_count",
    "VALID_EMPTY",
    "RETRY_EMPTY_CLAIMS_CHECK_MODEL",
    "CLAIMS_EMPTY_RETRY_REQUIRED",
)

COMPACTION_TOKENS_FOR_RUNTIME_BOUNDARY = (
    "APPLY_DRAFT_CLAIM_COMPACTION_RESULT",
    "DraftClaimCompaction",
    "draft_claim_compaction",
    "compacted_claims",
    "created_node_refs",
    "superseded_node_refs",
    "reduction_state",
    "frontier",
)


def test_llm_runtime_does_not_import_claim_builder_or_compaction_semantics() -> None:
    offenders = [
        *_import_offenders(LLM_RUNTIME_ROOT, WORKBENCH_IMPORT_PREFIXES),
        *_token_offenders(LLM_RUNTIME_ROOT, LLM_RUNTIME_FORBIDDEN_SEMANTIC_TOKENS),
    ]

    assert offenders == []


def test_execution_runtime_does_not_import_workbench_phase_semantics() -> None:
    offenders = [
        *_import_offenders(EXECUTION_RUNTIME_ROOT, WORKBENCH_IMPORT_PREFIXES),
        *_token_offenders(
            EXECUTION_RUNTIME_ROOT,
            EXECUTION_RUNTIME_FORBIDDEN_SEMANTIC_TOKENS,
        ),
    ]

    assert offenders == []


def test_llm_attempt_success_does_not_complete_work_item_without_workbench_apply() -> (
    None
):
    repository_path = (
        PROJECT_ROOT
        / "src/contexts/execution_runtime/infrastructure/postgres/"
        / "postgres_work_item_attempt_outcome_repository.py"
    )
    source = _read_text(repository_path)

    assert (
        "if record.outcome_status is WorkItemAttemptOutcomeStatus.SUCCEEDED:\n"
        "        return current"
    ) in source
    assert "complete_work_item_after_domain_apply" in source
    assert "complete_work_item_on" + "_success" not in source


def test_claim_builder_semantic_validation_lives_outside_llm_runtime() -> None:
    policy_path = (
        WORKBENCH_ROOT
        / "extraction/application/policies/claim_builder_output_validation_policy.py"
    )
    _assert_file_contains_tokens(policy_path, CLAIM_BUILDER_VALIDATION_TOKENS)

    offenders = [
        *_token_offenders(LLM_RUNTIME_ROOT, CLAIM_BUILDER_VALIDATION_TOKENS),
        *_token_offenders(EXECUTION_RUNTIME_ROOT, CLAIM_BUILDER_VALIDATION_TOKENS),
    ]

    assert offenders == []


def test_empty_claims_check_model_decision_is_claim_builder_policy_not_llm_runtime_strategy() -> (
    None
):
    policy_path = (
        WORKBENCH_ROOT
        / "extraction/application/policies/claim_builder_output_validation_policy.py"
    )
    next_action_path = (
        WORKBENCH_ROOT
        / "extraction/application/policies/claim_builder_attempt_next_action_policy.py"
    )
    _assert_file_contains_tokens(policy_path, CLAIM_BUILDER_EMPTY_POLICY_TOKENS)
    _assert_file_contains_tokens(
        next_action_path,
        ("RETRY_EMPTY_CLAIMS_CHECK_MODEL", "should_mark_work_item_completed"),
    )

    offenders = [
        *_token_offenders(LLM_RUNTIME_ROOT, CLAIM_BUILDER_EMPTY_POLICY_TOKENS),
        *_token_offenders(EXECUTION_RUNTIME_ROOT, CLAIM_BUILDER_EMPTY_POLICY_TOKENS),
    ]

    assert offenders == []


def test_claim_builder_completion_is_explicit_after_domain_outcome_marker() -> None:
    handler_path = (
        WORKBENCH_ROOT
        / "application/sagas/handle_execute_claim_builder_section_command.py"
    )
    source = _read_text(handler_path)

    outcome_event_index = source.index(
        "persisted_outcome_event = await workflow_unit_of_work.outbox.append_event"
    )
    completion_index = source.index(
        "complete_work_item_after_domain_apply",
        outcome_event_index,
    )
    reconcile_index = source.index(
        "next_command = _reconcile_claim_builder_progress_command",
        completion_index,
    )

    assert outcome_event_index < completion_index < reconcile_index


def test_compaction_apply_and_next_work_items_are_workbench_owned() -> None:
    execute_handler_path = (
        WORKBENCH_ROOT
        / "application/sagas/handle_execute_draft_claim_compaction_command.py"
    )
    apply_handler_path = (
        WORKBENCH_ROOT
        / "application/sagas/handle_apply_draft_claim_compaction_result_command.py"
    )
    apply_use_case_path = (
        WORKBENCH_ROOT
        / "extraction/application/use_cases/apply_draft_claim_compaction_result.py"
    )

    _assert_file_contains_tokens(
        execute_handler_path,
        (
            "APPLY_DRAFT_CLAIM_COMPACTION_RESULT",
            "draft_claim_compaction_validation_decision",
        ),
    )
    _assert_file_contains_tokens(
        apply_handler_path,
        (
            "ApplyDraftClaimCompactionResult",
            "DraftClaimCompactionNextWorkItem",
            "EnsureWorkItemsScheduled",
        ),
    )
    _assert_file_contains_tokens(
        apply_use_case_path,
        (
            "apply_compacted_claims_result",
            "apply_reduced_rewrite_result",
            "created_node_refs",
            "superseded_node_refs",
        ),
    )

    offenders = [
        *_token_offenders(LLM_RUNTIME_ROOT, COMPACTION_TOKENS_FOR_RUNTIME_BOUNDARY),
        *_token_offenders(
            EXECUTION_RUNTIME_ROOT,
            COMPACTION_TOKENS_FOR_RUNTIME_BOUNDARY,
        ),
    ]

    assert offenders == []


def test_compaction_work_item_completion_boundary_is_result_applied_not_llm_success() -> (
    None
):
    execute_handler_path = (
        WORKBENCH_ROOT
        / "application/sagas/handle_execute_draft_claim_compaction_command.py"
    )
    apply_handler_path = (
        WORKBENCH_ROOT
        / "application/sagas/handle_apply_draft_claim_compaction_result_command.py"
    )
    execute_source = _read_text(execute_handler_path)
    apply_source = _read_text(apply_handler_path)

    assert "complete_work_item_on_success=True" not in execute_source

    apply_use_case_index = apply_source.index(
        "outcome = await apply_result_use_case.execute(apply_command)"
    )
    applied_event_index = apply_source.index(
        "await _append_applied_event",
        apply_use_case_index,
    )
    completion_index = apply_source.index(
        "complete_work_item_after_domain_apply",
        applied_event_index,
    )
    next_event_index = apply_source.index(
        "await _append_next_event",
        completion_index,
    )

    assert (
        apply_use_case_index < applied_event_index < completion_index < next_event_index
    )


def test_success_completion_flag_is_not_allowed_anywhere() -> None:
    forbidden = "complete_work_item_on" + "_success"
    searched_roots = (
        PROJECT_ROOT / "src",
        PROJECT_ROOT / "tests",
    )
    offenders: list[str] = []

    for root in searched_roots:
        for path in _python_files(root):
            if path == Path(__file__):
                continue
            if forbidden in _read_text(path):
                offenders.append(_project_path(path))

    assert offenders == []


def _python_files(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        return ()
    return tuple(sorted(path for path in root.rglob("*.py") if path.is_file()))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _project_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _assert_file_contains_tokens(path: Path, tokens: Iterable[str]) -> None:
    source = _read_text(path)
    missing = [token for token in tokens if token not in source]

    assert missing == [], f"{_project_path(path)} missing tokens: {missing}"


def _token_offenders(root: Path, forbidden_tokens: Iterable[str]) -> list[str]:
    offenders: list[str] = []
    tokens = tuple(forbidden_tokens)

    for path in _python_files(root):
        source = _read_text(path)
        for token in tokens:
            if token in source:
                offenders.append(f"{_project_path(path)}: {token}")

    return offenders


def _import_offenders(
    root: Path,
    forbidden_prefixes: Iterable[str],
) -> list[str]:
    offenders: list[str] = []
    prefixes = tuple(forbidden_prefixes)

    for path in _python_files(root):
        tree = ast.parse(_read_text(path), filename=str(path))
        for imported_name in _imported_module_names(tree):
            if imported_name.startswith(prefixes):
                offenders.append(f"{_project_path(path)}: imports {imported_name}")

    return offenders


def _imported_module_names(tree: ast.AST) -> tuple[str, ...]:
    names: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
            continue

        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)

    return tuple(names)
