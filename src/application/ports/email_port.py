"""Application port for outbound email delivery."""

from typing import Protocol


class EmailSenderPort(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
    ) -> None: ...
