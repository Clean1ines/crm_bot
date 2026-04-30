from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.infrastructure.db.repositories.thread.messages import ThreadMessageRepository


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__.return_value = None
    mock_transaction.__aexit__.return_value = None
    mock_conn.transaction = MagicMock(return_value=mock_transaction)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_conn
    mock_cm.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=mock_cm)
    pool.mock_conn = mock_conn
    return pool


@pytest.fixture
def message_repo(mock_pool):
    return ThreadMessageRepository(mock_pool)


@pytest.mark.asyncio
async def test_append_manager_reply_message_persists_manager_role(
    message_repo, mock_pool
):
    thread_id = str(uuid4())

    await message_repo.append_manager_reply_message(
        thread_id,
        "[Alice Manager]: Подключаюсь к диалогу",
    )

    execute_calls = mock_pool.mock_conn.execute.await_args_list
    assert len(execute_calls) == 2
    _, update_thread_id = execute_calls[0].args
    insert_sql, insert_thread_id, role, content = execute_calls[1].args

    assert str(update_thread_id) == thread_id
    assert "INSERT INTO messages" in insert_sql
    assert str(insert_thread_id) == thread_id
    assert role == "manager"
    assert content == "[Alice Manager]: Подключаюсь к диалогу"


@pytest.mark.asyncio
async def test_get_messages_returns_chronological_user_assistant_manager_history(
    message_repo, mock_pool
):
    thread_id = str(uuid4())
    created_at = datetime(2025, 1, 1, 12, 0, 0)
    mock_pool.mock_conn.fetch = AsyncMock(
        return_value=[
            {
                "id": uuid4(),
                "role": "manager",
                "content": "[Alice Manager]: Я подключился",
                "created_at": created_at.replace(minute=2),
                "metadata": {},
            },
            {
                "id": uuid4(),
                "role": "assistant",
                "content": "Сейчас уточню детали",
                "created_at": created_at.replace(minute=1),
                "metadata": {},
            },
            {
                "id": uuid4(),
                "role": "user",
                "content": "Помогите, пожалуйста",
                "created_at": created_at,
                "metadata": {},
            },
        ]
    )

    messages = await message_repo.get_messages(thread_id, limit=20, offset=0)

    assert [message.role for message in messages] == ["user", "assistant", "manager"]
    assert [message.content for message in messages] == [
        "Помогите, пожалуйста",
        "Сейчас уточню детали",
        "[Alice Manager]: Я подключился",
    ]
