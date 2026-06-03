from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSITION = ROOT / "src/interfaces/composition/commercial_price_acquisition.py"


def test_commercial_price_acquisition_composition_does_not_depend_on_old_ingestion() -> (
    None
):
    source = COMPOSITION.read_text(encoding="utf-8")

    forbidden = (
        "knowledge_ingestion_service",
        "KnowledgeIngestionService",
        "knowledge_ingestion_contracts",
        "process_knowledge_upload",
        "KnowledgeService(",
    )
    for marker in forbidden:
        assert marker not in source


def test_old_knowledge_ingestion_service_is_deleted() -> None:
    assert not Path("src/application/services/knowledge_ingestion_service.py").exists()
    assert not Path(
        "src/application/services/knowledge_ingestion_contracts.py"
    ).exists()
