from pathlib import Path


def test_surface_publish_endpoint_has_required_fail_fast_and_status_transitions() -> (
    None
):
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert 'raise HTTPException(status_code=404, detail="Surface not found")' in source
    assert (
        'raise HTTPException(status_code=400, detail="Surface does not belong to document")'
        in source
    )
    assert (
        'raise HTTPException(status_code=409, detail="Surface has no linked runtime entry yet")'
        in source
    )

    assert 'publication_status="publish_failed"' in source
    assert 'publication_status="publishing"' in source
    assert 'publication_status="published"' in source
