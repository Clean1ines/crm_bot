from src.infrastructure.llm.chunker import ChunkerService


def test_markdown_numbered_sections_do_not_collapse_into_five_chunks() -> None:
    section_body = (
        "Это проверочный раздел базы знаний. "
        "Он содержит отдельную тему, короткий ответ, варианты вопросов и правило. " * 12
    )
    text = "# База знаний\n\n" + "\n\n".join(
        f"## {index}. Раздел {index}\n\n{section_body}" for index in range(1, 36)
    )

    chunks = ChunkerService(chunk_size=800, overlap=100).chunk_text(text)

    assert len(chunks) >= 35
    assert any("## 16. Раздел 16" in chunk for chunk in chunks)
    assert any("## 35. Раздел 35" in chunk for chunk in chunks)
    assert all(chunk.strip() for chunk in chunks)
