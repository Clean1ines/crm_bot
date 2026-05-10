from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from groq import AsyncGroq

from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

ResultT = TypeVar("ResultT")


class GroqChatMessageResponse(Protocol):
    content: str | None


class GroqChatAinvokeClient(Protocol):
    async def ainvoke(
        self,
        messages: list[tuple[str, str]],
    ) -> GroqChatMessageResponse: ...


class GroqChatAinvokeFactory(Protocol):
    def __call__(
        self,
        *,
        api_key: str,
    ) -> GroqChatAinvokeClient: ...


@dataclass(frozen=True, slots=True)
class GroqKeySelection:
    key: str
    index: int
    key_count: int


class GroqApiKeyRing:
    """Process-local Groq API key ring.

    The ring rotates only after provider rate-limit/quota exhaustion errors.
    It intentionally does not rotate on auth/config/network/schema errors.
    """

    def __init__(self) -> None:
        self._keys: tuple[str, ...] = ()
        self._index = 0
        self._lock = asyncio.Lock()

    def current(self) -> GroqKeySelection:
        keys = configured_groq_api_keys()
        if not keys:
            raise RuntimeError("No Groq API keys are configured")

        if keys != self._keys:
            self._keys = keys
            self._index = 0

        if self._index >= len(keys):
            self._index = 0

        return GroqKeySelection(
            key=keys[self._index],
            index=self._index,
            key_count=len(keys),
        )

    async def rotate_after_rate_limit(
        self,
        *,
        failed_index: int,
        attempted_indices: set[int],
    ) -> GroqKeySelection | None:
        async with self._lock:
            keys = configured_groq_api_keys()
            if not keys:
                return None

            if keys != self._keys:
                self._keys = keys
                self._index = 0

            if len(keys) <= 1:
                return None

            for offset in range(1, len(keys) + 1):
                candidate_index = (failed_index + offset) % len(keys)
                if candidate_index in attempted_indices:
                    continue

                self._index = candidate_index
                return GroqKeySelection(
                    key=keys[candidate_index],
                    index=candidate_index,
                    key_count=len(keys),
                )

            return None


_GLOBAL_GROQ_KEYRING = GroqApiKeyRing()


def _setting_text(value: object) -> str:
    if value is None:
        return ""

    get_secret_value = getattr(value, "get_secret_value", None)
    if callable(get_secret_value):
        value = get_secret_value()

    return str(value).strip()


def configured_groq_api_keys() -> tuple[str, ...]:
    """Return non-empty, de-duplicated Groq API keys in rotation order."""

    raw_values = (
        getattr(settings, "GROQ_API_KEY", None),
        getattr(settings, "GROQ_API_KEY2", None),
        getattr(settings, "GROQ_API_KEY3", None),
    )

    keys: list[str] = []
    seen: set[str] = set()

    for raw_value in raw_values:
        key = _setting_text(raw_value)
        if not key or key in seen:
            continue

        keys.append(key)
        seen.add(key)

    return tuple(keys)


def has_configured_groq_api_key() -> bool:
    return bool(configured_groq_api_keys())


def current_groq_api_key() -> str:
    return _GLOBAL_GROQ_KEYRING.current().key


def is_groq_rate_limit_error(exc: BaseException) -> bool:
    """Return true only for Groq quota/rate-limit style failures."""

    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True

    response = getattr(exc, "response", None)
    response_status_code = getattr(response, "status_code", None)
    if response_status_code == 429:
        return True

    type_name = type(exc).__name__.lower()
    message = str(exc).lower()

    markers = (
        "ratelimit",
        "rate limit",
        "rate_limit",
        "too many requests",
        "tokens per minute",
        "requests per minute",
        "tpm",
        "rpm",
        "please try again in",
        "quota exceeded",
    )

    return "ratelimit" in type_name or any(marker in message for marker in markers)


class GroqClientRotator:
    def __init__(self, *, client: AsyncGroq | None = None) -> None:
        self._injected_client = client is not None

        if client is not None:
            self._client = client
            self._key_index: int | None = None
            return

        selection = _GLOBAL_GROQ_KEYRING.current()
        self._client = AsyncGroq(api_key=selection.key)
        self._key_index = selection.index

    async def run(
        self,
        operation: Callable[[AsyncGroq], Awaitable[ResultT]],
        *,
        operation_name: str,
    ) -> ResultT:
        if self._injected_client:
            return await operation(self._client)

        attempted_indices: set[int] = set()

        while True:
            failed_index = self._key_index
            if failed_index is not None:
                attempted_indices.add(failed_index)

            try:
                return await operation(self._client)
            except Exception as exc:
                if failed_index is None or not is_groq_rate_limit_error(exc):
                    raise

                selection = await _GLOBAL_GROQ_KEYRING.rotate_after_rate_limit(
                    failed_index=failed_index,
                    attempted_indices=attempted_indices,
                )
                if selection is None:
                    logger.warning(
                        "Groq API key rotation exhausted",
                        extra={
                            "operation": operation_name,
                            "key_count": len(configured_groq_api_keys()),
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:300],
                        },
                    )
                    raise

                logger.warning(
                    "Groq API key rate-limited; rotating to next key",
                    extra={
                        "operation": operation_name,
                        "from_key_index": failed_index + 1,
                        "to_key_index": selection.index + 1,
                        "key_count": selection.key_count,
                        "error_type": type(exc).__name__,
                    },
                )

                self._client = AsyncGroq(api_key=selection.key)
                self._key_index = selection.index


class _RotatingChatCompletionsProxy:
    def __init__(self, rotator: GroqClientRotator) -> None:
        self._rotator = rotator

    async def create(self, *args: object, **kwargs: object):
        async def operation(client: AsyncGroq):
            create = getattr(client.chat.completions, "create")
            result = await create(*args, **kwargs)
            return result

        return await self._rotator.run(
            operation,
            operation_name="chat.completions.create",
        )


class _RotatingChatProxy:
    def __init__(self, rotator: GroqClientRotator) -> None:
        self.completions = _RotatingChatCompletionsProxy(rotator)


class RotatingAsyncGroq:
    """Small AsyncGroq-compatible proxy for chat.completions.create."""

    def __init__(self) -> None:
        self._rotator = GroqClientRotator()
        self.chat = _RotatingChatProxy(self._rotator)


async def ainvoke_chat_with_rotation(
    *,
    make_client: GroqChatAinvokeFactory,
    messages: list[tuple[str, str]],
    operation_name: str,
) -> GroqChatMessageResponse:
    """Run a LangChain-style ChatGroq ainvoke call with Groq key rotation.

    LangChain ChatGroq binds api_key at client construction time. Passing
    current_groq_api_key() once is not enough: after a 429 the already-created
    client keeps using the exhausted key. This helper recreates the client for
    every rotated key and retries only provider rate-limit/quota failures.
    """

    selection = _GLOBAL_GROQ_KEYRING.current()
    attempted_indices: set[int] = set()

    while True:
        attempted_indices.add(selection.index)
        client = make_client(api_key=selection.key)

        try:
            return await client.ainvoke(messages)
        except Exception as exc:
            if not is_groq_rate_limit_error(exc):
                raise

            next_selection = await _GLOBAL_GROQ_KEYRING.rotate_after_rate_limit(
                failed_index=selection.index,
                attempted_indices=attempted_indices,
            )
            if next_selection is None:
                logger.warning(
                    "Groq API key rotation exhausted",
                    extra={
                        "operation": operation_name,
                        "key_count": len(configured_groq_api_keys()),
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    },
                )
                raise

            logger.warning(
                "Groq API key rate-limited; rotating to next key",
                extra={
                    "operation": operation_name,
                    "from_key_index": selection.index + 1,
                    "to_key_index": next_selection.index + 1,
                    "key_count": next_selection.key_count,
                    "error_type": type(exc).__name__,
                },
            )
            selection = next_selection


def reset_groq_keyring_for_tests() -> None:
    global _GLOBAL_GROQ_KEYRING
    _GLOBAL_GROQ_KEYRING = GroqApiKeyRing()
