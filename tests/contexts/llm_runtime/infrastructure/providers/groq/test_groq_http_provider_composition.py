from __future__ import annotations

from dataclasses import dataclass, field

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_env_config import (
    GroqEnvAccountConfig,
    GroqEnvConfig,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_http_provider_composition import (
    GroqHttpProviderRuntimeFactory,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_http_transport import (
    GroqApiKeyRef,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GROQ_PROVIDER_ID,
    GroqAccountSeed,
)


@dataclass(frozen=True, slots=True)
class FakeHttpResponse:
    status_code: int
    headers: dict[str, str]
    body: dict[str, JsonValue]

    def json(self) -> dict[str, JsonValue]:
        return self.body


@dataclass(slots=True)
class FakeHttpClient:
    captured_posts: list[tuple[str, dict[str, str], dict[str, JsonValue], float]] = (
        field(
            default_factory=list,
        )
    )

    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        json_payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> FakeHttpResponse:
        self.captured_posts.append((url, headers, json_payload, timeout_seconds))
        return FakeHttpResponse(
            status_code=200,
            headers={},
            body={},
        )


def _env_config() -> GroqEnvConfig:
    return GroqEnvConfig(
        accounts=(
            GroqEnvAccountConfig(
                account_seed=GroqAccountSeed(
                    account_ref="groq_org_primary",
                    account_rank=0,
                ),
                api_key=GroqApiKeyRef("primary-secret"),
            ),
            GroqEnvAccountConfig(
                account_seed=GroqAccountSeed(
                    account_ref="groq_org_secondary",
                    account_rank=1,
                ),
                api_key=GroqApiKeyRef("secondary-secret"),
            ),
        ),
    )


def test_http_provider_factory_builds_primary_provider_and_all_account_slots() -> None:
    http_client = FakeHttpClient()

    components = GroqHttpProviderRuntimeFactory(
        http_client=http_client,
        env_config=_env_config(),
        base_url="https://example.test",
        timeout_seconds=12.5,
    ).build_primary()

    assert components.provider_accounts[0].account_ref.value == "groq_org_primary"
    assert components.provider_accounts[1].account_ref.value == "groq_org_secondary"
    assert all(
        account.provider_id == GROQ_PROVIDER_ID
        for account in components.provider_accounts
    )

    result = components.provider.transport.post_chat_completions(
        payload={
            "model": "qwen/qwen3-32b",
        },
    )

    assert result.status_code == 200
    assert len(http_client.captured_posts) == 1
    url, headers, json_payload, timeout_seconds = http_client.captured_posts[0]
    assert url == "https://example.test/chat/completions"
    assert headers["Authorization"] == "Bearer primary-secret"
    assert json_payload["model"] == "qwen/qwen3-32b"
    assert timeout_seconds == 12.5
