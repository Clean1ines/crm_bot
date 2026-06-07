from __future__ import annotations

import pytest

from src.infrastructure.llm import groq_keyring


def test_configured_groq_api_keys_reads_four_keys_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(groq_keyring.settings, "GROQ_API_KEY", "key-1")
    monkeypatch.setattr(groq_keyring.settings, "GROQ_API_KEY2", "key-2")
    monkeypatch.setattr(groq_keyring.settings, "GROQ_API_KEY3", "key-3")
    monkeypatch.setattr(groq_keyring.settings, "GROQ_API_KEY4", "key-4")

    assert groq_keyring.configured_groq_api_keys() == (
        "key-1",
        "key-2",
        "key-3",
        "key-4",
    )


def test_configured_groq_api_keys_keeps_order_and_deduplicates_fourth_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(groq_keyring.settings, "GROQ_API_KEY", "key-1")
    monkeypatch.setattr(groq_keyring.settings, "GROQ_API_KEY2", "")
    monkeypatch.setattr(groq_keyring.settings, "GROQ_API_KEY3", "key-3")
    monkeypatch.setattr(groq_keyring.settings, "GROQ_API_KEY4", "key-3")

    assert groq_keyring.configured_groq_api_keys() == ("key-1", "key-3")
