from src.infrastructure.llm.chunker import ChunkerService


def test_large_structured_text_is_split_into_multiple_chunks():
    chunker = ChunkerService(chunk_size=800, overlap=100)

    text = "\\n\\n".join(
        f"## intent_{i}\\n"
        f"answer: Это тестовый ответ номер {i}. "
        f"Он нужен, чтобы проверить нарезку большой базы знаний. "
        f"keywords: бот, telegram, заявки, менеджер, настройка. "
        f"patterns: как работает бот, сколько стоит, что входит в настройку."
        for i in range(80)
    )

    chunks = chunker.chunk_text(text)

    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    assert max(len(chunk) for chunk in chunks) <= 900


async def test_markdown_file_is_supported():
    chunker = ChunkerService(chunk_size=800, overlap=100)

    chunks = await chunker.process_file(
        b"# Test\\n\\nMarkdown knowledge text about Telegram bot.",
        "knowledge_fixture.md",
    )

    assert chunks
    assert "Markdown knowledge text" in chunks[0]
