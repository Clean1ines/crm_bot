from __future__ import annotations

from pathlib import Path


def test_curation_publish_has_no_direct_llm_provider_calls() -> None:
    root = Path("src/contexts/knowledge_workbench/curation")
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))

    forbidden = ("Groq", "OpenAI", "groq", "openai", "preview_payload")
    for marker in forbidden:
        assert marker not in sources


def test_curation_publish_endpoint_is_workflow_scoped() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert (
        '@router.post("/workflows/{workflow_run_id}/curation-workspace/publish")'
        in source
    )
    assert "_ensure_curation_workflow_project" in source
    assert "PublishDraftClaimCurationWorkspace" in source
    assert "_enqueue_draft_claim_curation_publication" in source
    assert (
        "KnowledgeExtractionCanonicalCommandType."
        "PUBLISH_DRAFT_CLAIM_CURATION_WORKSPACE.value" in source
    )
    assert "make_knowledge_extraction_workflow_resume" in source
