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
        b"# Test\n\nMarkdown knowledge text about Telegram bot.",
        "knowledge_fixture.md",
    )

    assert chunks
    first = chunks[0]
    assert isinstance(first, dict)
    assert first["entry_type"] == "plain_enriched"
    assert first["title"] == "Test"
    assert "Markdown knowledge text" in str(first["content"])
    assert "Markdown knowledge text" in str(first["source_excerpt"])
    assert "Title: Test" in str(first["embedding_text"])
    assert str(first["embedding_text"]) != str(first["content"])


async def test_json_intent_knowledge_file_is_supported():
    chunker = ChunkerService(chunk_size=800, overlap=100)

    chunks = await chunker.process_file(
        b'{"intents":{"value_proposition":{"answer":"'
        b"\xd0\xa7\xd1\x82\xd0\xbe\xd0\xb1\xd1\x8b \xd0\xbd\xd0\xb5 "
        b"\xd1\x82\xd0\xb5\xd1\x80\xd1\x8f\xd1\x82\xd1\x8c "
        b'\xd0\xba\xd0\xbb\xd0\xb8\xd0\xb5\xd0\xbd\xd1\x82\xd0\xbe\xd0\xb2",'
        b'"synonyms":["'
        b"\xd1\x87\xd0\xb5\xd0\xbc \xd1\x8d\xd1\x82\xd0\xbe "
        b'\xd0\xbf\xd0\xbe\xd0\xbb\xd0\xb5\xd0\xb7\xd0\xbd\xd0\xbe"],'
        b'"keywords":["'
        b'\xd0\xb1\xd0\xb8\xd0\xb7\xd0\xbd\xd0\xb5\xd1\x81"],'
        b'"patterns":["'
        b"\xd1\x87\xd1\x82\xd0\xbe \xd1\x8d\xd1\x82\xd0\xbe "
        b"\xd0\xb4\xd0\xb0\xd1\x81\xd1\x82 "
        b"\xd0\xbc\xd0\xbe\xd0\xb5\xd0\xbc\xd1\x83 "
        b'\xd0\xb1\xd0\xb8\xd0\xb7\xd0\xbd\xd0\xb5\xd1\x81\xd1\x83"]}}}',
        "knowledge_fixture.json",
    )

    assert chunks
    assert "value_proposition" in chunks[0]
    assert "Чтобы не терять клиентов" in chunks[0]
    assert "чем это полезно" in chunks[0]


async def test_markdown_file_returns_enriched_chunks_for_sections():
    chunker = ChunkerService(chunk_size=260, overlap=40)

    chunks = await chunker.process_file(
        (
            "# База знаний\n\n"
            "## 1. Оплата\n\n"
            "Клиент может спросить о способах оплаты и сроках оплаты.\n\n"
            "## 2. Возврат\n\n"
            "Если клиент спрашивает про возврат, ассистент передает диалог менеджеру."
        ).encode("utf-8"),
        "knowledge_fixture.md",
    )

    assert chunks
    assert all(isinstance(chunk, dict) for chunk in chunks)
    assert all(
        chunk["entry_type"] == "plain_enriched"
        for chunk in chunks
        if isinstance(chunk, dict)
    )
    assert any(
        "Оплата" in str(chunk.get("title", ""))
        for chunk in chunks
        if isinstance(chunk, dict)
    )
    assert any(
        "Возврат" in str(chunk.get("title", ""))
        for chunk in chunks
        if isinstance(chunk, dict)
    )
    assert all(
        str(chunk.get("embedding_text", "")) != str(chunk.get("content", ""))
        for chunk in chunks
        if isinstance(chunk, dict)
    )
