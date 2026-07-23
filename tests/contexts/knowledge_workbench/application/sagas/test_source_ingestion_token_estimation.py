from dataclasses import dataclass

from src.contexts.knowledge_workbench.application.sagas.source_ingestion_token_estimation import (
    MEASURED_PROMPT_TOKEN_COUNTS,
    SourceIngestionPromptTokenEstimationService,
    WorkbenchPromptText,
)


@dataclass(frozen=True, slots=True)
class FakeTokenEstimator:
    token_count: int

    def estimate_tokens(self, text: str) -> int:
        return self.token_count


def test_measured_claim_builder_prompt_count_wins_over_rough_estimator() -> None:
    service = SourceIngestionPromptTokenEstimationService(
        token_estimator=FakeTokenEstimator(token_count=123),
    )

    verified = service.estimate_prompt_tokens(
        WorkbenchPromptText(
            prompt_name="claim_builder_section_extraction",
            node_id="faq_claim_observations",
            prompt_path="prompt.txt",
            text="short prompt",
        ),
    )

    assert MEASURED_PROMPT_TOKEN_COUNTS["faq_claim_observations"] == 3_008
    assert verified.prompt_token_count == 3_008
