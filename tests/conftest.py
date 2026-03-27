import asyncpg
import pytest
from src.core.config import Settings
from src.database.repositories import ProjectRepository, ThreadRepository
import uuid

settings = Settings(_env_file=".env.test")

# Function‑scoped pool – создаётся для каждого теста, использует тот же loop, что и тест
@pytest.fixture(scope="function")
async def db_pool():
    pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=10)
    yield pool
    await pool.close()

@pytest.fixture
async def project_repo(db_pool):
    return ProjectRepository(db_pool)

@pytest.fixture
async def thread_repo(db_pool):
    return ThreadRepository(db_pool)

@pytest.fixture
async def test_project(project_repo):
    owner_id = f"test_owner_{uuid.uuid4().hex[:8]}"
    project_id = await project_repo.create_project(
        owner_id=owner_id,
        name=f"Test Project {owner_id}"
    )
    yield project_id
    # Очистка после теста
    await project_repo.delete_project(project_id)

@pytest.fixture
async def test_client(thread_repo, test_project):
    chat_id = 123456789 + hash(uuid.uuid4()) % 1000000
    client_id = await thread_repo.get_or_create_client(
        project_id=test_project,
        chat_id=chat_id,
        username=f"test_user_{uuid.uuid4().hex[:6]}",
        full_name="Test User"
    )
    return client_id

@pytest.fixture
async def test_thread(thread_repo, test_client):
    thread_id = await thread_repo.create_thread(
        client_id=test_client,
        status="active",
        interaction_mode="normal"
    )
    return thread_id