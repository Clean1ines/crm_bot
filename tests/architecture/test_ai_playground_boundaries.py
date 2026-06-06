from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_application_ai_playground_does_not_import_queue_or_repositories() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src/application/ai_playground").glob("*.py")
    )

    forbidden = [
        "queue",
        "KnowledgeWorkbenchRepository",
        "knowledge_workbench_repository",
        "document_processing",
        "orchestrator",
        "workbench",
        "artifact",
    ]

    for needle in forbidden:
        assert needle not in combined


def test_http_ai_playground_does_not_import_workbench_surface_artifacts() -> None:
    text = read("src/interfaces/http/ai_playground.py")

    forbidden = [
        "KnowledgeWorkbenchRepository",
        "WorkbenchDocument",
        "EvidenceTrace",
        "artifact",
        "knowledge.py",
        "from src.interfaces.http.knowledge",
    ]

    for needle in forbidden:
        assert needle not in text


def test_ai_playground_does_not_create_direct_groq_sdk_client() -> None:
    files = [
        "src/application/ai_playground/contracts.py",
        "src/application/ai_playground/run_ai_playground.py",
        "src/interfaces/composition/ai_playground.py",
        "src/interfaces/http/ai_playground.py",
    ]
    combined = "\n".join(read(path) for path in files)

    assert "from groq import" not in combined
    assert "AsyncGroq(api_key" not in combined
    assert "AsyncGroq(api_key=" not in combined
    assert "requests." not in combined
    assert "urllib" not in combined
    assert "dotenv" not in combined


def test_ai_playground_composition_reuses_existing_rotating_groq_proxy() -> None:
    text = read("src/interfaces/composition/ai_playground.py")

    assert "RotatingAsyncGroq" in text
    assert "src.infrastructure.llm.groq_keyring" in text


def test_frontend_panel_uses_ai_playground_api_not_knowledge_processing_overview() -> (
    None
):
    text = read("frontend/src/pages/knowledge/components/AiPlaygroundPanel.tsx")

    assert "aiPlaygroundApi" in text
    assert "knowledgeApi" not in text
    assert "processingOverview" not in text


def test_frontend_api_module_is_separate_from_knowledge_api() -> None:
    text = read("frontend/src/shared/api/modules/aiPlayground.ts")

    assert "/ai-playground/run" in text
    assert "knowledgeApi" not in text
