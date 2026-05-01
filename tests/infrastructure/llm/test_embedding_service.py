import asyncio

import httpx
import pytest
from pydantic import SecretStr

from src.infrastructure.config.settings import settings
from src.infrastructure.llm import embedding_service


class _FakeVector:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return list(self._values)


class _FakeModel:
    def __init__(self) -> None:
        self.embed_calls: list[list[str]] = []

    def embed(self, documents: list[str]):
        self.embed_calls.append(list(documents))
        for text in documents:
            yield _FakeVector([float(len(text))])


class _FakeAsyncClient:
    def __init__(
        self,
        *,
        responses: list[httpx.Response] | None = None,
        error: Exception | None = None,
        captured: list[dict[str, object]] | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._error = error
        self._captured = captured if captured is not None else []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
    ) -> httpx.Response:
        self._captured.append({"url": url, "headers": headers, "json": json})
        if self._error is not None:
            raise self._error
        if not self._responses:
            raise AssertionError("No fake HTTP response configured")
        return self._responses.pop(0)


def _vector512(seed: float) -> list[float]:
    return [seed + float(index) for index in range(512)]


def _json_response(
    payload: dict[str, object],
    *,
    status_code: int = 200,
) -> httpx.Response:
    request = httpx.Request("POST", "https://api.provider.test/v1/embeddings")
    return httpx.Response(status_code, json=payload, request=request)


@pytest.fixture(autouse=True)
def reset_embedding_runtime():
    previous_model = embedding_service._model
    previous_lock = embedding_service._model_init_lock
    previous_executor = embedding_service._executor
    previous_cache = dict(embedding_service._single_text_cache)
    previous_provider = settings.EMBEDDING_PROVIDER
    previous_dimensions = settings.EMBEDDING_VECTOR_DIMENSIONS
    previous_api_key = settings.JINA_API_KEY
    previous_model_name = settings.JINA_EMBEDDING_MODEL
    previous_url = settings.JINA_EMBEDDING_URL
    previous_batch_size = settings.JINA_EMBEDDING_BATCH_SIZE
    previous_timeout = settings.JINA_EMBEDDING_TIMEOUT_SECONDS
    previous_voyage_api_key = settings.VOYAGE_API_KEY
    previous_voyage_model = settings.VOYAGE_EMBEDDING_MODEL
    previous_voyage_url = settings.VOYAGE_EMBEDDING_URL
    previous_voyage_batch_size = settings.VOYAGE_EMBEDDING_BATCH_SIZE
    previous_voyage_timeout = settings.VOYAGE_EMBEDDING_TIMEOUT_SECONDS
    previous_voyage_output_dimensions = settings.VOYAGE_EMBEDDING_OUTPUT_DIMENSIONS

    embedding_service._model = None
    embedding_service._model_init_lock = None
    embedding_service._executor = None
    embedding_service._single_text_cache.clear()

    yield

    if embedding_service._executor is not None:
        embedding_service._executor.shutdown(wait=False, cancel_futures=True)
    embedding_service._model = previous_model
    embedding_service._model_init_lock = previous_lock
    embedding_service._executor = previous_executor
    embedding_service._single_text_cache.clear()
    embedding_service._single_text_cache.update(previous_cache)
    settings.EMBEDDING_PROVIDER = previous_provider
    settings.EMBEDDING_VECTOR_DIMENSIONS = previous_dimensions
    settings.JINA_API_KEY = previous_api_key
    settings.JINA_EMBEDDING_MODEL = previous_model_name
    settings.JINA_EMBEDDING_URL = previous_url
    settings.JINA_EMBEDDING_BATCH_SIZE = previous_batch_size
    settings.JINA_EMBEDDING_TIMEOUT_SECONDS = previous_timeout
    settings.VOYAGE_API_KEY = previous_voyage_api_key
    settings.VOYAGE_EMBEDDING_MODEL = previous_voyage_model
    settings.VOYAGE_EMBEDDING_URL = previous_voyage_url
    settings.VOYAGE_EMBEDDING_BATCH_SIZE = previous_voyage_batch_size
    settings.VOYAGE_EMBEDDING_TIMEOUT_SECONDS = previous_voyage_timeout
    settings.VOYAGE_EMBEDDING_OUTPUT_DIMENSIONS = previous_voyage_output_dimensions


@pytest.mark.asyncio
async def test_local_embed_text_uses_single_text_cache(monkeypatch: pytest.MonkeyPatch):
    settings.EMBEDDING_PROVIDER = "local"
    settings.EMBEDDING_VECTOR_DIMENSIONS = 1
    model = _FakeModel()

    async def fake_get_model() -> _FakeModel:
        return model

    monkeypatch.setattr(embedding_service, "_get_model", fake_get_model)

    first = await embedding_service.embed_text("hello")
    second = await embedding_service.embed_text("hello")

    assert first == [5.0]
    assert second == [5.0]
    assert model.embed_calls == [["hello"]]


@pytest.mark.asyncio
async def test_local_concurrent_embed_text_calls_share_single_model_init(
    monkeypatch: pytest.MonkeyPatch,
):
    settings.EMBEDDING_PROVIDER = "local"
    settings.EMBEDDING_VECTOR_DIMENSIONS = 1
    created_models: list[_FakeModel] = []

    def fake_create_model() -> _FakeModel:
        created = _FakeModel()
        created_models.append(created)
        return created

    monkeypatch.setattr(embedding_service, "_create_model", fake_create_model)

    first, second = await asyncio.gather(
        embedding_service.embed_text("first"),
        embedding_service.embed_text("second"),
    )

    assert first == [5.0]
    assert second == [6.0]
    assert len(created_models) == 1
    assert created_models[0].embed_calls == [["first"], ["second"]]


@pytest.mark.asyncio
async def test_voyage_embed_text_uses_query_input_type_and_skips_local_model(
    monkeypatch: pytest.MonkeyPatch,
):
    settings.EMBEDDING_PROVIDER = "voyage"
    settings.EMBEDDING_VECTOR_DIMENSIONS = 512
    settings.VOYAGE_EMBEDDING_OUTPUT_DIMENSIONS = 512
    settings.VOYAGE_API_KEY = SecretStr("test-key")
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        embedding_service,
        "_get_model",
        lambda: (_ for _ in ()).throw(AssertionError("local model path must not run")),
    )
    monkeypatch.setattr(
        embedding_service,
        "_create_model",
        lambda: (_ for _ in ()).throw(AssertionError("fastembed must stay unused")),
    )
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(
            responses=[
                _json_response(
                    {"data": [{"index": 0, "embedding": _vector512(0.1)}]},
                )
            ],
            captured=captured,
        ),
    )

    vector = await embedding_service.embed_text("query text")

    assert vector == _vector512(0.1)
    assert len(captured) == 1
    assert captured[0]["url"] == settings.VOYAGE_EMBEDDING_URL
    assert captured[0]["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert captured[0]["json"] == {
        "model": settings.VOYAGE_EMBEDDING_MODEL,
        "input": ["query text"],
        "input_type": "query",
        "output_dimension": 512,
    }


@pytest.mark.asyncio
async def test_voyage_embed_batch_respects_batch_size_and_uses_document_input_type(
    monkeypatch: pytest.MonkeyPatch,
):
    settings.EMBEDDING_PROVIDER = "voyage"
    settings.EMBEDDING_VECTOR_DIMENSIONS = 512
    settings.VOYAGE_EMBEDDING_OUTPUT_DIMENSIONS = 512
    settings.VOYAGE_API_KEY = SecretStr("test-key")
    settings.VOYAGE_EMBEDDING_BATCH_SIZE = 2
    captured: list[dict[str, object]] = []
    responses = [
        _json_response(
            {
                "data": [
                    {"index": 0, "embedding": _vector512(1.0)},
                    {"index": 1, "embedding": _vector512(2.0)},
                ]
            }
        ),
        _json_response(
            {
                "data": [
                    {"index": 0, "embedding": _vector512(3.0)},
                    {"index": 1, "embedding": _vector512(4.0)},
                ]
            }
        ),
        _json_response(
            {
                "data": [
                    {"index": 0, "embedding": _vector512(5.0)},
                ]
            }
        ),
    ]

    def fake_async_client(timeout: float) -> _FakeAsyncClient:
        return _FakeAsyncClient(
            responses=[responses.pop(0)],
            captured=captured,
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        fake_async_client,
    )

    vectors = await embedding_service.embed_batch(["a", "bb", "ccc", "dddd", "eeeee"])

    assert vectors == [
        _vector512(1.0),
        _vector512(2.0),
        _vector512(3.0),
        _vector512(4.0),
        _vector512(5.0),
    ]
    assert [item["json"] for item in captured] == [
        {
            "model": settings.VOYAGE_EMBEDDING_MODEL,
            "input": ["a", "bb"],
            "input_type": "document",
            "output_dimension": 512,
        },
        {
            "model": settings.VOYAGE_EMBEDDING_MODEL,
            "input": ["ccc", "dddd"],
            "input_type": "document",
            "output_dimension": 512,
        },
        {
            "model": settings.VOYAGE_EMBEDDING_MODEL,
            "input": ["eeeee"],
            "input_type": "document",
            "output_dimension": 512,
        },
    ]


@pytest.mark.asyncio
async def test_wrong_vector_dimension_raises_permanent_error(
    monkeypatch: pytest.MonkeyPatch,
):
    settings.EMBEDDING_PROVIDER = "voyage"
    settings.EMBEDDING_VECTOR_DIMENSIONS = 512
    settings.VOYAGE_EMBEDDING_OUTPUT_DIMENSIONS = 512
    settings.VOYAGE_API_KEY = SecretStr("test-key")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(
            responses=[
                _json_response(
                    {"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
                )
            ]
        ),
    )

    with pytest.raises(embedding_service.PermanentEmbeddingProviderError):
        await embedding_service.embed_text("query")


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_voyage_access_errors_are_permanent(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
):
    settings.EMBEDDING_PROVIDER = "voyage"
    settings.EMBEDDING_VECTOR_DIMENSIONS = 512
    settings.VOYAGE_EMBEDDING_OUTPUT_DIMENSIONS = 512
    settings.VOYAGE_API_KEY = SecretStr("test-key")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(
            responses=[
                _json_response(
                    {"error": {"message": "denied"}}, status_code=status_code
                )
            ]
        ),
    )

    with pytest.raises(embedding_service.PermanentEmbeddingProviderError):
        await embedding_service.embed_text("query")


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 500, 503])
async def test_voyage_http_failures_are_transient(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
):
    settings.EMBEDDING_PROVIDER = "voyage"
    settings.EMBEDDING_VECTOR_DIMENSIONS = 512
    settings.VOYAGE_EMBEDDING_OUTPUT_DIMENSIONS = 512
    settings.VOYAGE_API_KEY = SecretStr("test-key")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(
            responses=[
                _json_response({"error": {"message": "retry"}}, status_code=status_code)
            ]
        ),
    )

    with pytest.raises(embedding_service.TransientEmbeddingProviderError):
        await embedding_service.embed_text("query")


@pytest.mark.asyncio
async def test_voyage_timeout_is_transient(monkeypatch: pytest.MonkeyPatch):
    settings.EMBEDDING_PROVIDER = "voyage"
    settings.EMBEDDING_VECTOR_DIMENSIONS = 512
    settings.VOYAGE_EMBEDDING_OUTPUT_DIMENSIONS = 512
    settings.VOYAGE_API_KEY = SecretStr("test-key")
    request = httpx.Request("POST", settings.VOYAGE_EMBEDDING_URL)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout: _FakeAsyncClient(
            error=httpx.ReadTimeout("timeout", request=request),
        ),
    )

    with pytest.raises(embedding_service.TransientEmbeddingProviderError):
        await embedding_service.embed_text("query")


@pytest.mark.asyncio
async def test_disabled_provider_raises_controlled_error():
    settings.EMBEDDING_PROVIDER = "disabled"

    with pytest.raises(embedding_service.EmbeddingProviderDisabledError):
        await embedding_service.embed_text("query")
