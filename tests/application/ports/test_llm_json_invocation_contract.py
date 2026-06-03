from __future__ import annotations

from dataclasses import dataclass, field

from src.application.ports.llm_json_invocation import LlmJsonInvocationPort
from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationRequest,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
)


@dataclass(slots=True)
class FakeLlmJsonInvocationPort:
    requests: list[LlmJsonInvocationRequest] = field(default_factory=list)

    async def invoke_json(
        self,
        request: LlmJsonInvocationRequest,
    ) -> LlmJsonInvocationResult:
        self.requests.append(request)
        return LlmJsonInvocationResult(
            status=LlmInvocationStatus.SUCCESS,
            parsed_json={"findings": []},
            raw_text='{"findings":[]}',
            token_usage=LlmTokenUsage(prompt_tokens=1, completion_tokens=1),
            attempts=(
                LlmRouteAttempt(
                    provider_id="fake",
                    model="fake-json-model",
                    api_key_slot="fake-slot",
                    attempt_index=0,
                    status=LlmRouteAttemptStatus.SUCCESS,
                ),
            ),
        )


async def test_llm_json_invocation_port_contract_accepts_provider_agnostic_request() -> (
    None
):
    port: LlmJsonInvocationPort = FakeLlmJsonInvocationPort()

    result = await port.invoke_json(
        LlmJsonInvocationRequest(
            operation_name="faq_surface_claim_observations",
            prompt="Return JSON",
            route_purpose="workbench_claim_observations",
        )
    )

    assert result.status is LlmInvocationStatus.SUCCESS
    assert result.parsed_json == {"findings": []}
