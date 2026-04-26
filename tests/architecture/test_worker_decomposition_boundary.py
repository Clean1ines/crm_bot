from pathlib import Path


def test_worker_py_is_thin_compatibility_entrypoint():
    source = Path("src/infrastructure/queue/worker.py").read_text(encoding="utf-8")

    forbidden = [
        "httpx",
        "QueueRepository(",
        "MetricsRepository(",
        "ThreadRepository(",
        "ProjectRepository(",
        "claim_job",
        "complete_job",
        "fail_job",
        "sendMessage",
    ]

    assert len(source.splitlines()) <= 20
    assert all(marker not in source for marker in forbidden)


def test_telegram_http_transport_is_isolated_to_sender():
    offenders = []

    for path in Path("src/infrastructure/queue").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.as_posix()
        source = path.read_text(encoding="utf-8")
        if "api.telegram.org" in source and rel != "src/infrastructure/queue/telegram_sender.py":
            offenders.append(rel)
        if "import httpx" in source and rel != "src/infrastructure/queue/telegram_sender.py":
            offenders.append(rel)

    assert offenders == []


def test_worker_loop_does_not_know_job_handler_dependencies():
    source = Path("src/infrastructure/queue/worker_loop.py").read_text(encoding="utf-8")

    forbidden = [
        "httpx",
        "TelegramSender",
        "ProjectRepository",
        "MetricsRepository",
        "ThreadRepository",
        "get_redis_client",
        "asyncpg.create_pool",
    ]

    assert all(marker not in source for marker in forbidden)


def test_handlers_do_not_mutate_queue_state():
    offenders = []

    for path in Path("src/infrastructure/queue/handlers").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for marker in ("complete_job", "fail_job", "claim_job", "release_job"):
            if marker in source:
                offenders.append(f"{path.as_posix()} uses {marker}")

    assert offenders == []
