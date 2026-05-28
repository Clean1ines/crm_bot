from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from groq import AsyncGroq

from src.infrastructure.config.settings import settings
from src.infrastructure.llm.groq_quota_state import (
    groq_route_quota_identity,
    record_groq_route_failure,
    record_groq_route_success,
    wait_or_block_groq_route,
)
from src.infrastructure.llm.groq_router import (
    GroqFallbackExhaustedError,
    GroqModelRouter,
    GroqRouteFailureType,
    classify_groq_exception,
    is_daily_groq_quota,
    is_transient_groq_limit,
    retry_after_seconds_from_exception,
)
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


class GroqDocumentBudgetExceededError(RuntimeError):
    """Raised when one RotatingAsyncGroq instance exceeds its call/token budget."""


class GroqApiKeyRing:
    """Process-local Groq API key ring.

    The ring rotates only after provider rate-limit/quota exhaustion errors.
    It intentionally does not rotate on auth/config/network/schema errors.
    Persistent route cooldowns live in Redis when REDIS_URL is configured and
    fall back to process-local memory otherwise.
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

    async def acquire_next(self) -> GroqKeySelection:
        """Return the next key for a top-level LLM call.

        This spreads concurrent compiler batches across configured keys before
        any model-level fallback happens. Model fallback still runs inside the
        selected key first; key rotation is only a second-level fallback.
        """
        async with self._lock:
            keys = configured_groq_api_keys()
            if not keys:
                raise RuntimeError("No Groq API keys are configured")

            if keys != self._keys:
                self._keys = keys
                self._index = 0

            if self._index >= len(keys):
                self._index = 0

            selection = GroqKeySelection(
                key=keys[self._index],
                index=self._index,
                key_count=len(keys),
            )
            self._index = (self._index + 1) % len(keys)
            return selection

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
    """Return true only for Groq quota/rate-limit style failures.

    Request-size/context errors are deliberately excluded so model fallback can
    move to the large-request chain instead of burning API-key rotations.
    """

    limit_kind = classify_groq_exception(exc)
    return is_daily_groq_quota(limit_kind) or is_transient_groq_limit(limit_kind)


def _routed_model_text(routed_kwargs: dict[str, object]) -> str:
    model = routed_kwargs.get("model")
    return model if isinstance(model, str) and model.strip() else "unknown"


def _content_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return " ".join(_content_text(item) for item in value)
    if isinstance(value, Mapping):
        return " ".join(_content_text(item) for item in value.values())
    if value is None or isinstance(value, bool):
        return ""
    return str(value)


def _estimate_request_tokens(routed_kwargs: Mapping[str, object]) -> int:
    messages = routed_kwargs.get("messages")
    prompt_text = _content_text(messages)
    max_tokens = routed_kwargs.get("max_tokens")
    output_budget = max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else 0
    return max(1, len(prompt_text) // 3) + output_budget


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
                limit_kind = classify_groq_exception(exc)
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
                            "limit_kind": limit_kind.value,
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
                        "limit_kind": limit_kind.value,
                    },
                )

                self._client = AsyncGroq(api_key=selection.key)
                self._key_index = selection.index


class _RotatingChatCompletionsProxy:
    def __init__(self, rotator: GroqClientRotator) -> None:
        self._rotator = rotator
        self._router = GroqModelRouter()
        self._call_count = 0
        self._estimated_token_count = 0

    def _reserve_budget(self, routed_kwargs: Mapping[str, object]) -> None:
        max_calls = settings.GROQ_KNOWLEDGE_MAX_CALLS_PER_DOCUMENT
        max_tokens = settings.GROQ_KNOWLEDGE_MAX_TOKENS_PER_DOCUMENT
        estimated_tokens = _estimate_request_tokens(routed_kwargs)
        next_call_count = self._call_count + 1
        next_token_count = self._estimated_token_count + estimated_tokens

        if next_call_count > max_calls or next_token_count > max_tokens:
            raise GroqDocumentBudgetExceededError(
                "all_fallbacks_exhausted: llm_document_budget_exhausted; "
                f"calls={self._call_count}/{max_calls}; "
                f"estimated_tokens={self._estimated_token_count}/{max_tokens}; "
                f"next_estimated_tokens={estimated_tokens}"
            )

        self._call_count = next_call_count
        self._estimated_token_count = next_token_count

    async def create(self, *args: object, **kwargs: object):
        if self._rotator._injected_client:

            async def routed_create_with_injected_client(
                routed_kwargs: dict[str, object],
            ):
                create = getattr(self._rotator._client.chat.completions, "create")
                return await create(*args, **routed_kwargs)

            return await self._router.run_chat_completion(
                create_call=routed_create_with_injected_client,
                kwargs=kwargs,
                operation_name="chat.completions.create",
            )

        attempted_indices: set[int] = set()

        while True:
            selection = _GLOBAL_GROQ_KEYRING.current()
            attempted_indices.add(selection.index)

            async def routed_create(routed_kwargs: dict[str, object]):
                self._reserve_budget(routed_kwargs)
                model = _routed_model_text(routed_kwargs)
                identity = groq_route_quota_identity(
                    api_key=selection.key,
                    key_index=selection.index,
                    key_count=selection.key_count,
                    model=model,
                )
                await wait_or_block_groq_route(identity)
                client = AsyncGroq(api_key=selection.key)
                create = getattr(client.chat.completions, "create")
                try:
                    response = await create(*args, **routed_kwargs)
                except Exception as exc:
                    limit_kind = classify_groq_exception(exc)
                    retry_after = retry_after_seconds_from_exception(exc)
                    await record_groq_route_failure(
                        identity=identity,
                        limit_kind=limit_kind,
                        retry_after_seconds=retry_after,
                        error=str(exc),
                    )
                    raise
                await record_groq_route_success(identity)
                return response

            try:
                return await self._router.run_chat_completion(
                    create_call=routed_create,
                    kwargs=kwargs,
                    operation_name="chat.completions.create",
                )
            except GroqFallbackExhaustedError as exc:
                if exc.failure_type == GroqRouteFailureType.INPUT_TOO_LARGE:
                    raise

                last_error = exc.last_error or exc
                if not is_groq_rate_limit_error(last_error):
                    raise

                next_selection = await _GLOBAL_GROQ_KEYRING.rotate_after_rate_limit(
                    failed_index=selection.index,
                    attempted_indices=attempted_indices,
                )
                if next_selection is None:
                    logger.warning(
                        "Groq API key rotation exhausted after model fallback chain",
                        extra={
                            "operation": "chat.completions.create",
                            "key_count": len(configured_groq_api_keys()),
                            "failure_type": exc.failure_type.value,
                            "error_type": type(last_error).__name__,
                            "error": str(last_error)[:300],
                        },
                    )
                    raise

                logger.warning(
                    "Groq model fallback chain exhausted for key; rotating to next key",
                    extra={
                        "operation": "chat.completions.create",
                        "from_key_index": selection.index + 1,
                        "to_key_index": next_selection.index + 1,
                        "key_count": next_selection.key_count,
                        "failure_type": exc.failure_type.value,
                        "error_type": type(last_error).__name__,
                    },
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
            limit_kind = classify_groq_exception(exc)
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
                        "limit_kind": limit_kind.value,
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
                    "limit_kind": limit_kind.value,
                },
            )
            selection = next_selection


def reset_groq_keyring_for_tests() -> None:
    global _GLOBAL_GROQ_KEYRING
    _GLOBAL_GROQ_KEYRING = GroqApiKeyRing()
