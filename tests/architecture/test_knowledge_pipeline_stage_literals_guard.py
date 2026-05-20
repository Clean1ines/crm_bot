from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_STAGE_LITERALS = (
    '"answer_resolution_pending"',
    '"compiler_partial_failed"',
    '"embedding_running"',
    '"processed_with_warnings"',
)

WHITELIST = {
    "src/domain/project_plane/knowledge_document_pipeline.py",
    "tests/domain/test_knowledge_document_pipeline.py",
}


def test_no_ad_hoc_pipeline_stage_literals_outside_contract_module() -> None:
    offenders: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        if rel in WHITELIST:
            continue
        source = path.read_text(encoding="utf-8")
        for literal in FORBIDDEN_STAGE_LITERALS:
            if literal in source:
                offenders.append(f"{rel}:{literal}")
    assert not offenders, "\n".join(offenders)
