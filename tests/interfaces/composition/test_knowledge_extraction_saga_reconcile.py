from pathlib import Path


def test_composition_runner_uses_postgres_reconcile_uow_without_fake_emitter() -> None:
    source = Path(
        "src/interfaces/composition/knowledge_extraction_saga_reconcile.py"
    ).read_text(
        encoding="utf-8",
    )

    assert "PostgresKnowledgeExtractionSagaReconcileUnitOfWork" in source
    assert "KnowledgeExtractionSaga(" in source
    assert "command_emitter: KnowledgeExtractionCommandEmitterPort" in source
    assert "Fake" not in source
    assert "await unit_of_work.start()" in source
    assert "saga.reconcile(command)" in source
