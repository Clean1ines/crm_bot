from __future__ import annotations

import pytest
from fastapi.responses import JSONResponse, RedirectResponse

from src.interfaces.http import app as app_module


@pytest.mark.asyncio
async def test_root_redirects_to_web_login_when_frontend_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_module.settings,
        "FRONTEND_URL",
        "https://panel.example.test/",
    )

    response = await app_module.root()

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 307
    assert response.headers["location"] == "https://panel.example.test/login"


@pytest.mark.asyncio
async def test_root_returns_api_status_without_frontend_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module.settings, "FRONTEND_URL", None)

    response = await app_module.root()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200
