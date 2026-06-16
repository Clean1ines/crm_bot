from __future__ import annotations

import pytest

from src.infrastructure.db.repositories.thread.messages import _message_metadata


def test_message_metadata_hydrates_json_string() -> None:
    assert _message_metadata('{"source":"telegram"}') == {"source": "telegram"}


def test_message_metadata_accepts_none_as_empty_metadata() -> None:
    assert _message_metadata(None) == {}


def test_message_metadata_rejects_json_array() -> None:
    with pytest.raises(
        TypeError,
        match="messages.metadata must be JSON object Mapping; got str that decoded to list",
    ):
        _message_metadata('["not-object"]')
