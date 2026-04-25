from __future__ import annotations

import httpx

from src.application.errors import UnauthorizedError, ValidationError
from src.application.ports.google_identity_port import GoogleIdentityClaims


class HttpGoogleIdentityVerifier:
    def __init__(self, *, google_client_id: str | None = None, timeout_seconds: float = 10) -> None:
        self.google_client_id = google_client_id
        self.timeout_seconds = timeout_seconds

    async def verify_id_token(self, id_token: str) -> GoogleIdentityClaims:
        token = id_token.strip()
        if not token:
            raise ValidationError("id_token is required")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"id_token": token},
                )
        except httpx.HTTPError:
            raise UnauthorizedError("Invalid Google ID token") from None

        if response.status_code != 200:
            raise UnauthorizedError("Invalid Google ID token")

        claims = response.json()
        if self.google_client_id and claims.get("aud") != self.google_client_id:
            raise UnauthorizedError("Google ID token audience mismatch")

        issuer = claims.get("iss")
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise UnauthorizedError("Invalid Google ID token issuer")

        provider_subject = claims.get("sub")
        if not provider_subject:
            raise UnauthorizedError("Invalid Google ID token subject")

        return GoogleIdentityClaims(
            provider_subject=str(provider_subject),
            email=claims.get("email"),
            full_name=claims.get("name"),
        )
