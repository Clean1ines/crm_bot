from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_kcd_stage_k6_groq_adapter_uses_strict_json_mode_and_logs_raw_response() -> (
    None
):
    source = (ROOT / "src/infrastructure/llm/knowledge_preprocessor.py").read_text(
        encoding="utf-8"
    )

    assert "STRICT_JSON_SYSTEM_MESSAGE" in source
    assert 'response_format={"type": "json_object"}' in source
    assert "temperature=0" in source
    assert "Knowledge LLM raw JSON response" in source
    assert "raw_response_chunk" in source


def test_kcd_stage_k6_parser_rejects_extra_non_json_data() -> None:
    source = (ROOT / "src/domain/project_plane/knowledge_preprocessing.py").read_text(
        encoding="utf-8"
    )

    assert "json.loads(cleaned)" in source
    assert "raw_decode" not in source
    assert "_loads_first_json_mapping" not in source


def test_kcd_stage_k6_structured_pipeline_has_no_plain_fallback() -> None:
    source = (
        ROOT / "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")

    assert "preprocessing_fallback" not in source
    assert "Knowledge preprocessing failed; original chunks remain usable" not in source
    assert "Knowledge preprocessing failed; structured pipeline stopped" in source
    assert '"fallback": "disabled"' in source
    assert "raise ValidationError(error_message) from exc" in source


def test_kcd_stage_k6_technical_source_slices_are_small() -> None:
    source = (
        ROOT / "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")

    assert "KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET = 650" in source
    assert "_split_technical_source_text" in source
    assert "technical_source_char_budget" in source


def test_kcd_stage_k6_prompts_have_hard_json_output_contract() -> None:
    for prompt_name in (
        "knowledge_preprocess_faq.txt",
        "knowledge_preprocess_price_list.txt",
        "knowledge_preprocess_instruction.txt",
    ):
        text = (ROOT / "src/agent/prompts" / prompt_name).read_text(encoding="utf-8")
        assert text.startswith("HARD JSON OUTPUT CONTRACT:")
        assert "Return JSON and only JSON." in text
        assert "Do not return more than one JSON object." in text
