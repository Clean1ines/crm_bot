#!/usr/bin/env python3
import asyncio
import os
import sys
import asyncpg
from services.embedding_service import embed_text

# Примеры знаний для проекта (замените на свои)
KNOWLEDGE_ENTRIES = [
    {
        "project_id": "00000000-0000-0000-0000-000000000000",  # ID проекта, в который добавляем
        "content": "Наша компания предоставляет услуги по разработке ПО. Работаем с 9 до 21 по Москве.",
        "category": "general"
    },
    {
        "project_id": "00000000-0000-0000-0000-000000000000",
        "content": "Стоимость консультации — 3000 рублей в час. Пакет из 5 часов — 12000 рублей.",
        "category": "pricing"
    },
    {
        "project_id": "00000000-0000-0000-0000-000000000000",
        "content": "Мы поддерживаем Python, JavaScript, Go. Можем разработать бота под ключ.",
        "category": "services"
    },
]

async def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Ошибка: не задана DATABASE_URL")
        sys.exit(1)

    conn = await asyncpg.connect(db_url)
    try:
        for entry in KNOWLEDGE_ENTRIES:
            # Генерируем эмбеддинг для содержимого
            emb = await embed_text(entry["content"])
            emb_str = '[' + ','.join(str(x) for x in emb) + ']'
            await conn.execute("""
                INSERT INTO knowledge_base (project_id, content, embedding, category)
                VALUES ($1, $2, $3::vector, $4)
            """, entry["project_id"], entry["content"], emb_str, entry["category"])
            print(f"Добавлено: {entry['content'][:50]}...")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
