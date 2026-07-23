from src.contexts.knowledge_workbench.application.sagas.source_ingestion_segmentation_profiles import (
    default_source_ingestion_segmentation_profile,
)


def test_default_source_ingestion_segmentation_profile_uses_calibrated_prompt_count() -> (
    None
):
    profile = default_source_ingestion_segmentation_profile()

    assert profile.prompt.prompt_token_count == 3_008
    assert profile.primary_model.max_request_input_tokens == 8_000
    assert profile.primary_model.planned_output_tokens == 100
    assert profile.max_source_segment_tokens == 8_000 - 3_008 - 100
