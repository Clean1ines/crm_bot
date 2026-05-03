"""
Embedding generation service with provider routing.

Public imports of this module must stay lightweight:
- fastembed is imported lazily only for the local provider
- external HTTP calls are used for jina/voyage providers
- disabled provider raises a controlled error
"""

from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import monotonic
from typing import Literal, Protocol, TypedDict, cast

import httpx

from src.application.errors import (
    EmbeddingProviderDisabledError,
    PermanentEmbeddingProviderError,
    TransientEmbeddingProviderError,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.model_usage_views import ModelUsageMeasurement
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EmbeddingProviderName = Literal["local", "jina", "voyage", "disabled"]
EmbeddingTask = Literal["retrieval.query", "retrieval.passage"]
ExternalEmbeddingTask = Literal["query", "document"]


class EmbeddingVector(Protocol):
    def tolist(self) -> list[float]: ...


class EmbeddingModel(Protocol):
    def embed(self, documents: list[str]) -> Iterable[EmbeddingVector]: ...


class _JinaEmbeddingItem(TypedDict):
    embedding: list[float]
    index: int


class _VoyageEmbeddingItem(TypedDict):
    embedding: list[float]
    index: int


_model: EmbeddingModel | None = None
_model_init_lock: asyncio.Lock | None = None
_executor: ThreadPoolExecutor | None = None
_voyage_request_lock: asyncio.Lock | None = None
_voyage_next_request_at: float = 0.0


@dataclass(slots=True)
class _EmbeddingCacheEntry:
    vector: list[float]
    expires_at: float


@dataclass(frozen=True, slots=True)
class EmbeddingTextResult:
    embedding: list[float]
    usage: ModelUsageMeasurement | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingBatchResult:
    embeddings: list[list[float]]
    usage: ModelUsageMeasurement | None = None


_single_text_cache: dict[str, _EmbeddingCacheEntry] = {}


def _embedding_provider() -> EmbeddingProviderName:
    return settings.EMBEDDING_PROVIDER


def _expected_dimensions() -> int:
    return settings.EMBEDDING_VECTOR_DIMENSIONS


def _create_model() -> EmbeddingModel:
    """
    Create the concrete fastembed model only when local embeddings are requested.

    Importing TextEmbedding here keeps plain app imports free from ONNX runtime.
    """
    from fastembed import TextEmbedding

    return cast(EmbeddingModel, TextEmbedding(EMBEDDING_MODEL_NAME))


def _get_executor() -> ThreadPoolExecutor:
    global _executor

    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=settings.EMBEDDING_EXECUTOR_MAX_WORKERS,
            thread_name_prefix="embedding-runtime",
        )

    return _executor


def _get_model_init_lock() -> asyncio.Lock:
    global _model_init_lock

    if _model_init_lock is None:
        _model_init_lock = asyncio.Lock()

    return _model_init_lock


async def _get_model() -> EmbeddingModel:
    global _model

    if _model is not None:
        return _model

    async with _get_model_init_lock():
        if _model is None:
            logger.info("Loading embedding model '%s'", EMBEDDING_MODEL_NAME)
            loop = asyncio.get_running_loop()
            _model = await loop.run_in_executor(_get_executor(), _create_model)

    if _model is None:
        raise RuntimeError("Embedding model initialization returned no model")

    return _model


def _embed_one_sync(model: EmbeddingModel, text: str) -> list[float]:
    vectors = list(model.embed([text]))
    if not vectors:
        return []
    return vectors[0].tolist()


def _embed_batch_sync(model: EmbeddingModel, texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in model.embed(texts)]


def _cache_ttl_seconds() -> float:
    return settings.EMBEDDING_QUERY_CACHE_TTL_SECONDS


def _cache_max_entries() -> int:
    return settings.EMBEDDING_QUERY_CACHE_MAX_ENTRIES


def _is_cache_enabled() -> bool:
    return _embedding_provider() == "local" and _cache_ttl_seconds() > 0.0


def _prune_single_text_cache() -> None:
    if len(_single_text_cache) < _cache_max_entries():
        return

    now = monotonic()
    expired_keys = [
        key for key, entry in _single_text_cache.items() if entry.expires_at <= now
    ]
    for key in expired_keys:
        _single_text_cache.pop(key, None)

    if len(_single_text_cache) < _cache_max_entries():
        return

    oldest_key = min(
        _single_text_cache.items(),
        key=lambda item: item[1].expires_at,
    )[0]
    _single_text_cache.pop(oldest_key, None)


def _get_cached_single_text_embedding(text: str) -> list[float] | None:
    if not _is_cache_enabled():
        return None

    entry = _single_text_cache.get(text)
    if entry is None:
        return None

    if entry.expires_at <= monotonic():
        _single_text_cache.pop(text, None)
        return None

    return entry.vector.copy()


def _set_cached_single_text_embedding(text: str, vector: list[float]) -> None:
    if not _is_cache_enabled():
        return

    _prune_single_text_cache()
    _single_text_cache[text] = _EmbeddingCacheEntry(
        vector=vector.copy(),
        expires_at=monotonic() + _cache_ttl_seconds(),
    )


def _estimated_tokens_for_texts(texts: list[str]) -> int:
    total_chars = sum(len(text) for text in texts)
    return max(1, (total_chars + 3) // 4)


def _usage_metadata(
    *,
    task: str,
    batch_size: int,
    is_estimated: bool,
) -> JsonObject:
    return {
        "task": task,
        "batch_size": batch_size,
        "is_estimated": is_estimated,
    }


def _embedding_usage_measurement(
    *,
    provider: str,
    model: str,
    task: str,
    batch_size: int,
    texts: list[str],
    total_tokens: int | None,
) -> ModelUsageMeasurement:
    resolved_total_tokens = (
        int(total_tokens)
        if total_tokens is not None
        else _estimated_tokens_for_texts(texts)
    )
    is_estimated = total_tokens is None
    return ModelUsageMeasurement(
        provider=provider,
        model=model,
        usage_type="embedding",
        tokens_input=resolved_total_tokens,
        tokens_output=None,
        tokens_total=resolved_total_tokens,
        estimated_cost_usd=None,
        metadata=_usage_metadata(
            task=task,
            batch_size=batch_size,
            is_estimated=is_estimated,
        ),
    )


def _ensure_numeric_vector(
    values: object,
    *,
    provider: str,
    task: str,
    model: str | None,
) -> list[float]:
    if not isinstance(values, list):
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned invalid vector payload",
            provider=provider,
            task=task,
            model=model,
        )

    vector: list[float] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned invalid vector payload",
                provider=provider,
                task=task,
                model=model,
            )
        vector.append(float(item))

    if len(vector) != _expected_dimensions():
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned unexpected vector dimensions",
            provider=provider,
            task=task,
            model=model,
        )

    return vector


def _validate_embedding_vectors(
    vectors: list[list[float]],
    *,
    provider: str,
    task: str,
    model: str | None,
) -> list[list[float]]:
    return [
        _ensure_numeric_vector(
            vector,
            provider=provider,
            task=task,
            model=model,
        )
        for vector in vectors
    ]


def _batch_texts(texts: list[str], batch_size: int) -> list[list[str]]:
    return [
        texts[start : start + batch_size] for start in range(0, len(texts), batch_size)
    ]


def _usage_batch_size(measurement: ModelUsageMeasurement) -> int:
    value = measurement.metadata.get("batch_size")
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0
        try:
            return int(stripped)
        except ValueError:
            return 0
    return 0


def _combine_usage_measurements(
    measurements: list[ModelUsageMeasurement],
) -> ModelUsageMeasurement | None:
    if not measurements:
        return None

    first = measurements[0]
    tokens_input = sum(item.tokens_input for item in measurements)
    tokens_output = sum(item.tokens_output or 0 for item in measurements)
    tokens_total = sum(item.tokens_total for item in measurements)
    estimated_cost_usd = sum(item.estimated_cost_usd or 0.0 for item in measurements)
    any_estimated = any(
        bool(item.metadata.get("is_estimated")) for item in measurements
    )

    return ModelUsageMeasurement(
        provider=first.provider,
        model=first.model,
        usage_type=first.usage_type,
        tokens_input=tokens_input,
        tokens_output=tokens_output or None,
        tokens_total=tokens_total,
        estimated_cost_usd=estimated_cost_usd or None,
        metadata={
            "task": first.metadata.get("task"),
            "batch_size": sum(_usage_batch_size(item) for item in measurements),
            "request_count": len(measurements),
            "is_estimated": any_estimated,
        },
    )


def _get_voyage_request_lock() -> asyncio.Lock:
    global _voyage_request_lock

    if _voyage_request_lock is None:
        _voyage_request_lock = asyncio.Lock()

    return _voyage_request_lock


async def _apply_voyage_request_delay() -> None:
    global _voyage_next_request_at

    delay_seconds = settings.VOYAGE_EMBEDDING_REQUEST_DELAY_SECONDS
    if delay_seconds <= 0:
        return

    async with _get_voyage_request_lock():
        now = monotonic()
        if _voyage_next_request_at > now:
            await asyncio.sleep(_voyage_next_request_at - now)
            now = monotonic()
        _voyage_next_request_at = now + delay_seconds


def _parse_retry_after_seconds(header_value: str | None) -> float | None:
    if not header_value:
        return None

    stripped = header_value.strip()
    if not stripped:
        return None

    try:
        return max(0.0, float(stripped))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(stripped)
    except (TypeError, ValueError, IndexError):
        return None

    now = retry_at.now(retry_at.tzinfo)
    return max(0.0, (retry_at - now).total_seconds())


def _voyage_backoff_seconds(
    attempt: int,
    *,
    retry_after_seconds: float | None,
) -> float:
    if retry_after_seconds is not None:
        return retry_after_seconds

    base_delay = settings.VOYAGE_EMBEDDING_RETRY_BASE_SECONDS
    max_delay = settings.VOYAGE_EMBEDDING_RETRY_MAX_SECONDS
    capped = min(base_delay * (2**attempt), max_delay)
    jitter = capped * 0.1
    return capped + jitter


def _jina_api_key() -> str:
    if settings.JINA_API_KEY is None:
        raise PermanentEmbeddingProviderError(
            "Jina embedding provider is not configured",
            provider="jina",
            task="config",
            model=settings.JINA_EMBEDDING_MODEL,
        )

    api_key = settings.JINA_API_KEY.get_secret_value().strip()
    if not api_key:
        raise PermanentEmbeddingProviderError(
            "Jina embedding provider is not configured",
            provider="jina",
            task="config",
            model=settings.JINA_EMBEDDING_MODEL,
        )

    return api_key


def _jina_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_jina_api_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _jina_payload(texts: list[str], *, task: EmbeddingTask) -> dict[str, object]:
    return {
        "model": settings.JINA_EMBEDDING_MODEL,
        "task": task,
        "dimensions": _expected_dimensions(),
        "normalized": True,
        "input": texts,
    }


def _parse_jina_items(
    body: object,
    *,
    batch_size: int,
    task: EmbeddingTask,
) -> list[_JinaEmbeddingItem]:
    if not isinstance(body, Mapping):
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned invalid response payload",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        )

    data = body.get("data")
    if not isinstance(data, list):
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned invalid response payload",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        )

    result: list[_JinaEmbeddingItem] = []
    for index, raw_item in enumerate(data):
        if not isinstance(raw_item, Mapping):
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned invalid response payload",
                provider="jina",
                task=task,
                model=settings.JINA_EMBEDDING_MODEL,
            )

        raw_index = raw_item.get("index", index)
        if isinstance(raw_index, bool) or not isinstance(raw_index, int):
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned invalid response payload",
                provider="jina",
                task=task,
                model=settings.JINA_EMBEDDING_MODEL,
            )

        embedding = _ensure_numeric_vector(
            raw_item.get("embedding"),
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        )
        result.append({"index": raw_index, "embedding": embedding})

    if len(result) != batch_size:
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned incomplete response payload",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        )

    return result


def _ordered_jina_vectors(
    items: list[_JinaEmbeddingItem],
    *,
    batch_size: int,
    task: EmbeddingTask,
) -> list[list[float]]:
    ordered: list[list[float] | None] = [None] * batch_size

    for item in items:
        index = item["index"]
        if index < 0 or index >= batch_size or ordered[index] is not None:
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned invalid response ordering",
                provider="jina",
                task=task,
                model=settings.JINA_EMBEDDING_MODEL,
            )
        ordered[index] = item["embedding"]

    if any(vector is None for vector in ordered):
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned incomplete response payload",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        )

    return [vector for vector in ordered if vector is not None]


async def _request_jina_embeddings(
    texts: list[str],
    *,
    task: EmbeddingTask,
) -> list[list[float]]:
    try:
        async with httpx.AsyncClient(
            timeout=settings.JINA_EMBEDDING_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                settings.JINA_EMBEDDING_URL,
                headers=_jina_headers(),
                json=_jina_payload(texts, task=task),
            )
    except httpx.TimeoutException as exc:
        logger.warning(
            "Jina embedding request timed out",
            extra={
                "provider": "jina",
                "model": settings.JINA_EMBEDDING_MODEL,
                "task": task,
                "batch_size": len(texts),
                "error_type": type(exc).__name__,
            },
        )
        raise TransientEmbeddingProviderError(
            "Embedding provider timed out",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        ) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "Jina embedding network error",
            extra={
                "provider": "jina",
                "model": settings.JINA_EMBEDDING_MODEL,
                "task": task,
                "batch_size": len(texts),
                "error_type": type(exc).__name__,
            },
        )
        raise TransientEmbeddingProviderError(
            "Embedding provider network error",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        ) from exc

    status_code = response.status_code
    if status_code in {401, 403, 451}:
        logger.warning(
            "Jina embedding access denied",
            extra={
                "provider": "jina",
                "model": settings.JINA_EMBEDDING_MODEL,
                "task": task,
                "batch_size": len(texts),
                "status_code": status_code,
            },
        )
        raise PermanentEmbeddingProviderError(
            "Embedding provider access denied",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        )

    if status_code == 429 or status_code >= 500:
        logger.warning(
            "Jina embedding transient provider failure",
            extra={
                "provider": "jina",
                "model": settings.JINA_EMBEDDING_MODEL,
                "task": task,
                "batch_size": len(texts),
                "status_code": status_code,
            },
        )
        raise TransientEmbeddingProviderError(
            "Embedding provider temporary failure",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        )

    if status_code >= 400:
        logger.warning(
            "Jina embedding request rejected",
            extra={
                "provider": "jina",
                "model": settings.JINA_EMBEDDING_MODEL,
                "task": task,
                "batch_size": len(texts),
                "status_code": status_code,
            },
        )
        raise PermanentEmbeddingProviderError(
            "Embedding provider request rejected",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned invalid response payload",
            provider="jina",
            task=task,
            model=settings.JINA_EMBEDDING_MODEL,
        ) from exc

    items = _parse_jina_items(body, batch_size=len(texts), task=task)
    return _ordered_jina_vectors(items, batch_size=len(texts), task=task)


async def _embed_jina_batch(
    texts: list[str], *, task: EmbeddingTask
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for batch in _batch_texts(texts, settings.JINA_EMBEDDING_BATCH_SIZE):
        vectors.extend(await _request_jina_embeddings(batch, task=task))
    return vectors


def _voyage_api_key() -> str:
    if settings.VOYAGE_API_KEY is None:
        raise PermanentEmbeddingProviderError(
            "Voyage embedding provider is not configured",
            provider="voyage",
            task="config",
            model=settings.VOYAGE_EMBEDDING_MODEL,
        )

    api_key = settings.VOYAGE_API_KEY.get_secret_value().strip()
    if not api_key:
        raise PermanentEmbeddingProviderError(
            "Voyage embedding provider is not configured",
            provider="voyage",
            task="config",
            model=settings.VOYAGE_EMBEDDING_MODEL,
        )

    return api_key


def _voyage_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_voyage_api_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _voyage_payload(
    texts: list[str], *, input_type: ExternalEmbeddingTask
) -> dict[str, object]:
    return {
        "model": settings.VOYAGE_EMBEDDING_MODEL,
        "input": texts,
        "input_type": input_type,
        "output_dimension": settings.VOYAGE_EMBEDDING_OUTPUT_DIMENSIONS,
    }


def _parse_voyage_items(
    body: object,
    *,
    batch_size: int,
    input_type: ExternalEmbeddingTask,
) -> list[_VoyageEmbeddingItem]:
    if not isinstance(body, Mapping):
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned invalid response payload",
            provider="voyage",
            task=input_type,
            model=settings.VOYAGE_EMBEDDING_MODEL,
        )

    data = body.get("data")
    if not isinstance(data, list):
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned invalid response payload",
            provider="voyage",
            task=input_type,
            model=settings.VOYAGE_EMBEDDING_MODEL,
        )

    result: list[_VoyageEmbeddingItem] = []
    for index, raw_item in enumerate(data):
        if not isinstance(raw_item, Mapping):
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned invalid response payload",
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
            )

        raw_index = raw_item.get("index", index)
        if isinstance(raw_index, bool) or not isinstance(raw_index, int):
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned invalid response payload",
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
            )

        embedding = _ensure_numeric_vector(
            raw_item.get("embedding"),
            provider="voyage",
            task=input_type,
            model=settings.VOYAGE_EMBEDDING_MODEL,
        )
        result.append({"index": raw_index, "embedding": embedding})

    if len(result) != batch_size:
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned incomplete response payload",
            provider="voyage",
            task=input_type,
            model=settings.VOYAGE_EMBEDDING_MODEL,
        )

    return result


def _ordered_voyage_vectors(
    items: list[_VoyageEmbeddingItem],
    *,
    batch_size: int,
    input_type: ExternalEmbeddingTask,
) -> list[list[float]]:
    ordered: list[list[float] | None] = [None] * batch_size

    for item in items:
        index = item["index"]
        if index < 0 or index >= batch_size or ordered[index] is not None:
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned invalid response ordering",
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
            )
        ordered[index] = item["embedding"]

    if any(vector is None for vector in ordered):
        raise PermanentEmbeddingProviderError(
            "Embedding provider returned incomplete response payload",
            provider="voyage",
            task=input_type,
            model=settings.VOYAGE_EMBEDDING_MODEL,
        )

    return [vector for vector in ordered if vector is not None]


def _voyage_total_tokens_from_body(body: object) -> int | None:
    if not isinstance(body, Mapping):
        return None

    usage = body.get("usage")
    if not isinstance(usage, Mapping):
        return None

    total_tokens = usage.get("total_tokens")
    if isinstance(total_tokens, bool) or not isinstance(total_tokens, int):
        return None

    return total_tokens


async def _request_voyage_embeddings(
    texts: list[str],
    *,
    input_type: ExternalEmbeddingTask,
) -> EmbeddingBatchResult:
    max_retries = settings.VOYAGE_EMBEDDING_MAX_RETRIES

    for attempt in range(max_retries + 1):
        await _apply_voyage_request_delay()
        retry_after_seconds: float | None = None

        try:
            async with httpx.AsyncClient(
                timeout=settings.VOYAGE_EMBEDDING_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    settings.VOYAGE_EMBEDDING_URL,
                    headers=_voyage_headers(),
                    json=_voyage_payload(texts, input_type=input_type),
                )
        except httpx.TimeoutException as exc:
            if attempt < max_retries:
                delay_seconds = _voyage_backoff_seconds(
                    attempt,
                    retry_after_seconds=None,
                )
                logger.warning(
                    "Voyage embedding request timed out; retrying",
                    extra={
                        "provider": "voyage",
                        "model": settings.VOYAGE_EMBEDDING_MODEL,
                        "task": input_type,
                        "batch_size": len(texts),
                        "error_type": type(exc).__name__,
                        "retry_attempt": attempt + 1,
                        "delay_seconds": delay_seconds,
                    },
                )
                await asyncio.sleep(delay_seconds)
                continue

            raise TransientEmbeddingProviderError(
                "Embedding provider timed out",
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
                retry_after_seconds=settings.VOYAGE_EMBEDDING_RETRY_MAX_SECONDS,
            ) from exc
        except httpx.RequestError as exc:
            if attempt < max_retries:
                delay_seconds = _voyage_backoff_seconds(
                    attempt,
                    retry_after_seconds=None,
                )
                logger.warning(
                    "Voyage embedding network error; retrying",
                    extra={
                        "provider": "voyage",
                        "model": settings.VOYAGE_EMBEDDING_MODEL,
                        "task": input_type,
                        "batch_size": len(texts),
                        "error_type": type(exc).__name__,
                        "retry_attempt": attempt + 1,
                        "delay_seconds": delay_seconds,
                    },
                )
                await asyncio.sleep(delay_seconds)
                continue

            raise TransientEmbeddingProviderError(
                "Embedding provider network error",
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
                retry_after_seconds=settings.VOYAGE_EMBEDDING_RETRY_MAX_SECONDS,
            ) from exc

        status_code = response.status_code
        if status_code in {401, 403, 451}:
            logger.warning(
                "Voyage embedding access denied",
                extra={
                    "provider": "voyage",
                    "model": settings.VOYAGE_EMBEDDING_MODEL,
                    "task": input_type,
                    "batch_size": len(texts),
                    "status_code": status_code,
                },
            )
            raise PermanentEmbeddingProviderError(
                "Embedding provider access denied",
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
            )

        if status_code == 429 or status_code >= 500:
            retry_after_seconds = _parse_retry_after_seconds(
                response.headers.get("Retry-After")
            )
            if attempt < max_retries:
                delay_seconds = _voyage_backoff_seconds(
                    attempt,
                    retry_after_seconds=retry_after_seconds,
                )
                logger.warning(
                    "Voyage embedding transient provider failure; retrying",
                    extra={
                        "provider": "voyage",
                        "model": settings.VOYAGE_EMBEDDING_MODEL,
                        "task": input_type,
                        "batch_size": len(texts),
                        "status_code": status_code,
                        "retry_attempt": attempt + 1,
                        "delay_seconds": delay_seconds,
                    },
                )
                await asyncio.sleep(delay_seconds)
                continue

            raise TransientEmbeddingProviderError(
                "Embedding provider temporary failure",
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
                retry_after_seconds=max(
                    settings.VOYAGE_EMBEDDING_RETRY_MAX_SECONDS,
                    retry_after_seconds or 0.0,
                ),
            )

        if status_code >= 400:
            logger.warning(
                "Voyage embedding request rejected",
                extra={
                    "provider": "voyage",
                    "model": settings.VOYAGE_EMBEDDING_MODEL,
                    "task": input_type,
                    "batch_size": len(texts),
                    "status_code": status_code,
                },
            )
            raise PermanentEmbeddingProviderError(
                "Embedding provider request rejected",
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned invalid response payload",
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
            ) from exc

        items = _parse_voyage_items(
            body,
            batch_size=len(texts),
            input_type=input_type,
        )
        vectors = _ordered_voyage_vectors(
            items,
            batch_size=len(texts),
            input_type=input_type,
        )
        usage = _embedding_usage_measurement(
            provider="voyage",
            model=settings.VOYAGE_EMBEDDING_MODEL,
            task=input_type,
            batch_size=len(texts),
            texts=texts,
            total_tokens=_voyage_total_tokens_from_body(body),
        )
        return EmbeddingBatchResult(embeddings=vectors, usage=usage)

    raise TransientEmbeddingProviderError(
        "Embedding provider temporary failure",
        provider="voyage",
        task=input_type,
        model=settings.VOYAGE_EMBEDDING_MODEL,
        retry_after_seconds=settings.VOYAGE_EMBEDDING_RETRY_MAX_SECONDS,
    )


async def _embed_voyage_batch(
    texts: list[str], *, input_type: ExternalEmbeddingTask
) -> EmbeddingBatchResult:
    vectors: list[list[float]] = []
    measurements: list[ModelUsageMeasurement] = []
    for batch in _batch_texts(texts, settings.VOYAGE_EMBEDDING_BATCH_SIZE):
        result = await _request_voyage_embeddings(batch, input_type=input_type)
        vectors.extend(
            _validate_embedding_vectors(
                result.embeddings,
                provider="voyage",
                task=input_type,
                model=settings.VOYAGE_EMBEDDING_MODEL,
            )
        )
        if result.usage is not None:
            measurements.append(result.usage)
    return EmbeddingBatchResult(
        embeddings=vectors,
        usage=_combine_usage_measurements(measurements),
    )


async def _embed_local_text(text: str) -> list[float]:
    cached_vector = _get_cached_single_text_embedding(text)
    if cached_vector is not None:
        return cached_vector

    loop = asyncio.get_running_loop()
    model = await _get_model()
    vector = await loop.run_in_executor(_get_executor(), _embed_one_sync, model, text)
    _set_cached_single_text_embedding(text, vector)
    return vector


async def _embed_local_batch(texts: list[str]) -> list[list[float]]:
    loop = asyncio.get_running_loop()
    model = await _get_model()
    return await loop.run_in_executor(_get_executor(), _embed_batch_sync, model, texts)


async def embed_text(text: str) -> EmbeddingTextResult:
    logger.debug(
        "Generating query embedding",
        extra={"provider": _embedding_provider(), "text_length": len(text)},
    )

    provider = _embedding_provider()
    if provider == "disabled":
        raise EmbeddingProviderDisabledError(
            "Embedding provider is disabled",
            provider=provider,
            task="retrieval.query",
        )

    if provider == "voyage":
        result = await _embed_voyage_batch([text], input_type="query")
        return EmbeddingTextResult(
            embedding=result.embeddings[0],
            usage=result.usage,
        )

    if provider == "jina":
        vectors = await _embed_jina_batch([text], task="retrieval.query")
        return EmbeddingTextResult(
            embedding=_validate_embedding_vectors(
                vectors,
                provider=provider,
                task="retrieval.query",
                model=settings.JINA_EMBEDDING_MODEL,
            )[0]
        )

    vector = await _embed_local_text(text)
    return EmbeddingTextResult(
        embedding=_validate_embedding_vectors(
            [vector],
            provider=provider,
            task="retrieval.query",
            model=EMBEDDING_MODEL_NAME,
        )[0]
    )


async def embed_batch(texts: list[str]) -> EmbeddingBatchResult:
    if not texts:
        return EmbeddingBatchResult(embeddings=[])

    logger.debug(
        "Generating passage embeddings",
        extra={"provider": _embedding_provider(), "batch_size": len(texts)},
    )

    provider = _embedding_provider()
    if provider == "disabled":
        raise EmbeddingProviderDisabledError(
            "Embedding provider is disabled",
            provider=provider,
            task="retrieval.passage",
        )

    if provider == "voyage":
        return await _embed_voyage_batch(texts, input_type="document")

    if provider == "jina":
        vectors = await _embed_jina_batch(texts, task="retrieval.passage")
        return EmbeddingBatchResult(
            embeddings=_validate_embedding_vectors(
                vectors,
                provider=provider,
                task="retrieval.passage",
                model=settings.JINA_EMBEDDING_MODEL,
            )
        )

    vectors = await _embed_local_batch(texts)
    return EmbeddingBatchResult(
        embeddings=_validate_embedding_vectors(
            vectors,
            provider=provider,
            task="retrieval.passage",
            model=EMBEDDING_MODEL_NAME,
        )
    )
