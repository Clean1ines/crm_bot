from types import SimpleNamespace

import pytest

from src.infrastructure.config.settings import settings
from src.infrastructure.llm import groq_keyring


@pytest.fixture(autouse=True)
def reset_groq_key_settings():
    previous_key1 = settings.GROQ_API_KEY
    previous_key2 = getattr(settings, "GROQ_API_KEY2", None)
    previous_key3 = getattr(settings, "GROQ_API_KEY3", None)

    groq_keyring.reset_groq_keyring_for_tests()

    yield

    settings.GROQ_API_KEY = previous_key1
    settings.GROQ_API_KEY2 = previous_key2
    settings.GROQ_API_KEY3 = previous_key3
    groq_keyring.reset_groq_keyring_for_tests()


def test_configured_groq_api_keys_filters_empty_and_duplicates() -> None:
    settings.GROQ_API_KEY = "key-1"
    settings.GROQ_API_KEY2 = " "
    settings.GROQ_API_KEY3 = "key-1"

    assert groq_keyring.configured_groq_api_keys() == ("key-1",)


def test_groq_rate_limit_detector_matches_token_limit_message() -> None:
    exc = RuntimeError("Rate limit reached for model. Please try again in 3.07s.")

    assert groq_keyring.is_groq_rate_limit_error(exc) is True


def test_groq_rate_limit_detector_ignores_auth_errors() -> None:
    exc = RuntimeError("Invalid API key")

    assert groq_keyring.is_groq_rate_limit_error(exc) is False


@pytest.mark.asyncio
async def test_rotating_async_groq_switches_to_next_key_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.GROQ_API_KEY = "key-1"
    settings.GROQ_API_KEY2 = "key-2"
    settings.GROQ_API_KEY3 = ""

    created_keys: list[str] = []

    class FakeCompletions:
        def __init__(self, api_key: str) -> None:
            self._api_key = api_key

        async def create(self, *args: object, **kwargs: object):
            if self._api_key == "key-1":
                raise RuntimeError(
                    "Rate limit reached for model. Please try again in 1s."
                )
            return SimpleNamespace(api_key=self._api_key)

    class FakeChat:
        def __init__(self, api_key: str) -> None:
            self.completions = FakeCompletions(api_key)

    class FakeAsyncGroq:
        def __init__(self, *, api_key: str) -> None:
            created_keys.append(api_key)
            self.chat = FakeChat(api_key)

    monkeypatch.setattr(groq_keyring, "AsyncGroq", FakeAsyncGroq)
    groq_keyring.reset_groq_keyring_for_tests()

    client = groq_keyring.RotatingAsyncGroq()
    response = await client.chat.completions.create(model="llama-test")

    assert response.api_key == "key-2"
    assert created_keys == ["key-1", "key-2"]


@pytest.mark.asyncio
async def test_rotating_async_groq_reraises_when_all_keys_are_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.GROQ_API_KEY = "key-1"
    settings.GROQ_API_KEY2 = "key-2"
    settings.GROQ_API_KEY3 = ""

    class FakeCompletions:
        async def create(self, *args: object, **kwargs: object):
            raise RuntimeError("Rate limit reached. Please try again in 1s.")

    class FakeChat:
        def __init__(self) -> None:
            self.completions = FakeCompletions()

    class FakeAsyncGroq:
        def __init__(self, *, api_key: str) -> None:
            self.chat = FakeChat()

    monkeypatch.setattr(groq_keyring, "AsyncGroq", FakeAsyncGroq)
    groq_keyring.reset_groq_keyring_for_tests()

    client = groq_keyring.RotatingAsyncGroq()

    with pytest.raises(RuntimeError, match="Rate limit reached"):
        await client.chat.completions.create(model="llama-test")
