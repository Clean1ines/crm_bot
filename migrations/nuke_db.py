import asyncio
import os
import asyncpg
from pathlib import Path
from dotenv import load_dotenv

# Цвета для терминала
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'

async def nuke_schema(db_url, env_name):
    print(f"{Colors.YELLOW}☢️  Зачистка базы для {env_name}...{Colors.RESET}")
    
    # Фикс для Neon (отрезаем параметры если есть)
    if "neon.tech" in db_url:
        db_url = db_url.split("?")[0]
        ssl_option = 'require'
    else:
        ssl_option = None # Для локального докера обычно не нужно

    try:
        conn = await asyncpg.connect(db_url, ssl=ssl_option, timeout=10)
        await conn.execute("""
            DROP SCHEMA IF EXISTS public CASCADE;
            CREATE SCHEMA public;
            GRANT ALL ON SCHEMA public TO public;
            COMMENT ON SCHEMA public IS 'standard public schema';
        """)
        await conn.close()
        print(f"{Colors.GREEN}✅ База {env_name} теперь стерильна.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}❌ Не удалось зачистить {env_name}: {e}{Colors.RESET}")

async def main():
    env_files = ['.env', '.env.test', '.env.prod']
    found_envs = [f for f in env_files if Path(f).exists()]
    
    if not found_envs:
        print("Файлы окружения не найдены.")
        return

    print(f"{Colors.RED}!!! ВНИМАНИЕ !!!{Colors.RESET}")
    print(f"Будут полностью уничтожены данные в: {found_envs}")
    confirm = input("Ты уверен? Введи 'nuke' для подтверждения: ")
    
    if confirm.lower() != 'nuke':
        print("Отмена.")
        return

    for env_file in found_envs:
        load_dotenv(dotenv_path=env_file, override=True)
        url = os.getenv("DATABASE_URL")
        if url:
            await nuke_schema(url, env_file)

if __name__ == "__main__":
    asyncio.run(main())