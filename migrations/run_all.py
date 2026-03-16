#!/usr/bin/env python3
"""
Автоматическое применение миграций ко всем окружениям.
Скрипт обрабатывает только файлы из списка ALLOWED_ENV_FILES (по умолчанию:
.env, .env.test, .env.prod). Для .env.prod запрашивает подтверждение.
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

# Разрешённые имена файлов окружения (можно добавить свои)
ALLOWED_ENV_FILES = [".env", ".env.test", ".env.prod"]

# Цвета для вывода (опционально)
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'

def find_env_files():
    """Возвращает список разрешённых файлов .env, найденных в корне проекта."""
    root = Path(__file__).parent.parent  # корень проекта
    env_files = []
    for name in ALLOWED_ENV_FILES:
        path = root / name
        if path.exists():
            env_files.append(path)
    return env_files

def is_prod_env(env_file):
    """Определяет, является ли окружение продакшном (по имени файла)."""
    return "prod" in env_file.name.lower()

async def apply_migrations_for_env(env_file):
    """Загружает переменные из env_file и применяет миграции к соответствующей БД."""
    print(f"\n{Colors.YELLOW}=== Применение миграций для {env_file.name} ==={Colors.RESET}")

    # Загружаем переменные из файла
    load_dotenv(dotenv_path=env_file, override=True)
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print(f"{Colors.RED}❌ DATABASE_URL не задан в {env_file.name}, пропускаем{Colors.RESET}")
        return

    # Проверка на prod
    if is_prod_env(env_file):
        print(f"{Colors.RED}⚠️  Это ПРОДАКШН база!{Colors.RESET}")
        response = input("Продолжить? (введите 'yes' для подтверждения): ").strip().lower()
        if response != 'yes':
            print("❌ Отменено пользователем, переходим к следующему окружению")
            return

    # Маскируем пароль в выводе
    db_display = DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL
    print(f"🔌 Подключение к БД: {db_display}")

    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as e:
        print(f"{Colors.RED}❌ Не удалось подключиться к БД: {e}{Colors.RESET}")
        return

    try:
        # Таблица schema_migrations (с явной схемой public)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        applied = set()
        for row in await conn.fetch("SELECT filename FROM public.schema_migrations"):
            applied.add(row['filename'])

        # Все .sql файлы из папки migrations
        mig_dir = Path(__file__).parent
        sql_files = sorted(mig_dir.glob("*.sql"))

        for filepath in sql_files:
            if filepath.name in applied:
                print(f"⏭️  Skipping already applied migration: {filepath.name}")
                continue

            print(f"📄 Applying SQL migration: {filepath.name}")
            sql = filepath.read_text(encoding='utf-8')
            try:
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO public.schema_migrations (filename) VALUES ($1)",
                    filepath.name
                )
                print(f"✅ {filepath.name} applied")
            except Exception as e:
                print(f"{Colors.RED}❌ Error executing {filepath.name}: {e}{Colors.RESET}")
                # Прерываем только для текущей БД
                break

        print(f"{Colors.GREEN}🎉 Миграции для {env_file.name} успешно применены{Colors.RESET}")

    except Exception as e:
        print(f"{Colors.RED}❌ Ошибка при применении миграций для {env_file.name}: {e}{Colors.RESET}")
    finally:
        if conn:
            await conn.close()

async def main():
    env_files = find_env_files()
    if not env_files:
        print("❌ Не найдено файлов окружения из списка разрешённых:")
        print(f"   {ALLOWED_ENV_FILES}")
        print("   Создайте нужные файлы или добавьте имена в ALLOWED_ENV_FILES в скрипте.")
        sys.exit(1)

    print(f"Найдено файлов окружения: {[f.name for f in env_files]}")

    for env_file in env_files:
        await apply_migrations_for_env(env_file)

    print("\n✅ Все операции завершены")

if __name__ == "__main__":
    asyncio.run(main())