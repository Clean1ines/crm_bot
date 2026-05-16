from __future__ import annotations

from pathlib import Path

from src.infrastructure.logging.logger import redact_sensitive_log_values

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "src/application/services/knowledge_ingestion_service.py"
WORKER = ROOT / "src/infrastructure/queue/worker_loop.py"
LOGGER = ROOT / "src/infrastructure/logging/logger.py"


def _function_body(source: str, name: str) -> str:
    marker = f"def {name}"
    async_marker = f"async def {name}"
    start = source.find(marker)
    if start < 0:
        start = source.find(async_marker)
    assert start >= 0, name

    next_candidates = [
        index
        for token in ("\ndef ", "\nasync def ", "\nclass ")
        if (index := source.find(token, start + 1)) >= 0
    ]
    end = min(next_candidates) if next_candidates else len(source)
    return source[start:end]


def test_existing_document_retighten_dispatches_one_suspect_group_per_llm_call() -> (
    None
):
    source = SERVICE.read_text(encoding="utf-8")
    body = _function_body(source, "retighten_processed_document")

    assert "groups=groups" not in body
    assert "groups=(groups[0],)" in body
    assert "for group in groups[1:]" in body
    assert "groups=(group,)" in body
    assert "llm_call_count" in body
    assert "usage_event_count" in body


def test_compiled_ingestion_tightening_reports_actual_llm_call_count() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    body = _function_body(source, "_tighten_compiled_entries_with_semantic_merge")

    assert "groups=groups" not in body
    assert "for group in groups:" in body
    assert "groups=(group,)" in body
    assert '"llm_call_count": 0' in body
    assert 'metrics["llm_call_count"]' in body
    assert "model = first_execution.result.model" not in body
    assert "prompt_version = first_execution.result.prompt_version" not in body


def test_worker_loop_does_not_log_unbounded_traceback_locals_for_unexpected_errors() -> (
    None
):
    source = WORKER.read_text(encoding="utf-8")
    body = _function_body(source, "run_worker_loop")

    assert '"Error in worker loop"' not in body
    assert "logger.exception(" not in body
    assert '"Unexpected worker loop error"' in body
    assert '"error_type": type(exc).__name__' in body
    assert '"error": str(exc)[:240]' in body


def test_structlog_redacts_common_secret_values_and_sensitive_keys() -> None:
    event = {
        "event": "test",
        "plain_error": "failed with gsk_abcdefghijklmnopqrstuvwxyz123456",
        "nested": {
            "url": "postgresql://user:password@example.internal/db",
            "authorization": "Bearer abc.def.ghi",
        },
        "api_key": "gsk_secret_key_should_not_survive",
    }

    redacted = redact_sensitive_log_values(object(), "error", event)
    rendered = repr(redacted)

    assert "gsk_" not in rendered
    assert "postgresql://user:password@" not in rendered
    assert "Bearer abc.def.ghi" not in rendered
    assert redacted["api_key"] == "[REDACTED]"


def test_logger_configuration_wires_redaction_before_json_rendering() -> None:
    source = LOGGER.read_text(encoding="utf-8")

    assert "def redact_sensitive_log_values(" in source
    assert "redact_sensitive_log_values," in source
    assert source.index("structlog.processors.UnicodeDecoder()") < source.index(
        "redact_sensitive_log_values,"
    )
