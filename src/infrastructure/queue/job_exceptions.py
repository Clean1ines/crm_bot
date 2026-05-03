"""Worker job exception taxonomy."""


class JobError(Exception):
    """Base worker job error."""


class PermanentJobError(JobError):
    """A job cannot succeed by retrying with the same payload."""


class TransientJobError(JobError):
    """A job may succeed later and should go through retry policy."""

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
