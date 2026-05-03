"""Application-layer exceptions mapped to transport errors in the interface layer."""


class ApplicationError(Exception):
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ValidationError(ApplicationError):
    status_code = 400


class UnauthorizedError(ApplicationError):
    status_code = 401


class ForbiddenError(ApplicationError):
    status_code = 403


class NotFoundError(ApplicationError):
    status_code = 404


class ConflictError(ApplicationError):
    status_code = 409


class InternalServiceError(ApplicationError):
    status_code = 500


class EmbeddingProviderError(ApplicationError):
    status_code = 503

    def __init__(
        self,
        detail: str,
        *,
        provider: str,
        task: str,
        model: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.provider = provider
        self.task = task
        self.model = model

    @property
    def retryable(self) -> bool:
        return False


class PermanentEmbeddingProviderError(EmbeddingProviderError):
    """Configuration or provider response error that should not be retried."""


class TransientEmbeddingProviderError(EmbeddingProviderError):
    """Temporary provider/network error that may succeed on retry."""

    def __init__(
        self,
        detail: str,
        *,
        provider: str,
        task: str,
        model: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(detail, provider=provider, task=task, model=model)
        self.retry_after_seconds = retry_after_seconds

    @property
    def retryable(self) -> bool:
        return True


class EmbeddingProviderDisabledError(PermanentEmbeddingProviderError):
    """Embeddings are intentionally disabled by configuration."""
