"""Compatibility entrypoint for the decomposed queue worker."""

from src.infrastructure.queue.runtime import main, worker_loop

__all__ = ["main", "worker_loop"]


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
