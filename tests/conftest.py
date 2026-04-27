import asyncpg
import pytest
from src.infrastructure.config.settings import Settings
from src.infrastructure.db.repositories import ProjectRepository
from src.infrastructure.db.repositories.thread.lifecycle import (
    ThreadLifecycleRepository,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
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
async def thread_lifecycle_repo(db_pool):
    return ThreadLifecycleRepository(db_pool)


@pytest.fixture
async def test_project(project_repo):
    owner_name = f"test_owner_{uuid.uuid4().hex[:8]}"
    user_repo = UserRepository(project_repo.pool)
    user_id = await user_repo.create_user(full_name=owner_name)
    project_id = await project_repo.create_project_with_user_id(
        user_id=user_id, name=f"Test Project {owner_name}"
    )
    yield project_id
    # Очистка после теста
    await project_repo.delete_project(project_id)


@pytest.fixture
async def test_client(thread_lifecycle_repo, test_project):
    chat_id = 123456789 + hash(uuid.uuid4()) % 1000000
    client_id = await thread_lifecycle_repo.get_or_create_client(
        project_id=test_project,
        chat_id=chat_id,
        username=f"test_user_{uuid.uuid4().hex[:6]}",
        full_name="Test User",
    )
    return client_id


@pytest.fixture
async def test_thread(thread_lifecycle_repo, test_client):
    thread_id = await thread_lifecycle_repo.create_thread(
        client_id=test_client, status="active", interaction_mode="normal"
    )
    return thread_id
