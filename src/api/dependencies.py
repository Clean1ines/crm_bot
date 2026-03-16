"""
FastAPI dependency injection for database pool, orchestrator, and repositories.
"""

from src.core.lifespan import pool, orchestrator
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.queue_repository import QueueRepository

def get_pool():
    """Return the global database connection pool."""
    if pool is None:
        raise RuntimeError("Database pool not initialized")
    return pool

def get_orchestrator():
    """Return the global orchestrator instance."""
    if orchestrator is None:
        raise RuntimeError("Orchestrator not initialized")
    return orchestrator

def get_project_repo():
    """Return a new ProjectRepository instance (uses the global pool)."""
    return ProjectRepository(get_pool())

def get_thread_repo():
    """Return a new ThreadRepository instance (uses the global pool)."""
    return ThreadRepository(get_pool())

def get_queue_repo():
    """Return a new QueueRepository instance (uses the global pool)."""
    return QueueRepository(get_pool())
