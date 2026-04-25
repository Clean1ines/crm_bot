from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class GoogleIdentityClaims:
    provider_subject: str
    email: str | None = None
    full_name: str | None = None


class GoogleIdentityVerifier(Protocol):
    async def verify_id_token(self, id_token: str) -> GoogleIdentityClaims: ...
