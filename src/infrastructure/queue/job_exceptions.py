"""Worker job exception taxonomy."""


class JobError(Exception):
    """Base worker job error."""


class PermanentJobError(JobError):
    """A job cannot succeed by retrying with the same payload."""


class TransientJobError(JobError):
    """A job may succeed later and should go through retry policy."""
