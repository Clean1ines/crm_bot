from pathlib import Path


def test_surface_publish_endpoint_has_required_publication_flow() -> None:
    source = Path("src/interfaces/http/knowledge_surface.py").read_text(
        encoding="utf-8"
    )

    assert 'detail="Surface not found"' in source
    assert 'detail="Surface does not belong to document"' in source
    assert "add_canonical_entries" in source
    assert "link_surface_to_runtime_entry" in source
    assert "linked_canonical_entry_id" in source
    assert 'publication_status="publish_failed"' in source
    assert 'publication_status="publishing"' in source
    assert 'publication_status="published"' in source
