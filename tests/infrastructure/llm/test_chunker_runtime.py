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
