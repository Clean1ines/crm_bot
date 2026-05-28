from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "src/application/services/knowledge_surface_ingestion_service.py"


def test_faq_completion_logging_contains_required_summary_payload() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert '"Knowledge document completed"' in source

    required_exact_markers = (
        '"document_id": document_id',
        '"project_id": project_id',
        '"run_id": run_id',
        '"job_id": None',
        '"stage_kind": "faq_retrieval_surface_compilation_completed"',
        '"source_unit_key": None',
        '"source_unit_index": None',
        '"candidate_index": None',
        '"requested_model": compiler.model_name',
        '"actual_model": result.model',
        '"economy_mode": preprocessing_metrics.get("economy_mode", False)',
    )
    for marker in required_exact_markers:
        assert marker in source

    required_summary_keys = (
        '"key_slot"',
        '"fallback_reason"',
        '"limit_kind"',
        '"tokens_prompt"',
        '"tokens_completion"',
        '"tokens_total"',
        '"duration_ms"',
        '"checkpoint_reused"',
        '"total_calls"',
        '"total_tokens"',
        '"models"',
        '"key_slots"',
        '"fallback_counts"',
        '"cooldown_counts"',
        '"checkpoint_reused_count"',
    )
    for marker in required_summary_keys:
        assert marker in source

    required_metric_sources = (
        "groq_key_slot_counts",
        "fallback_reason",
        "limit_kind",
        "tokens_input",
        "tokens_output",
        "tokens_total",
        "duration_ms",
        "checkpoint_reused",
        "llm_call_count",
        "groq_route_event_count",
        "model_counts",
        "groq_actual_model_counts",
        "fallback_counts",
        "groq_route_cooldown_block_count",
        "source_unit_checkpoint_reused_count",
        "checkpoint_reused_count",
    )
    for marker in required_metric_sources:
        assert marker in source
