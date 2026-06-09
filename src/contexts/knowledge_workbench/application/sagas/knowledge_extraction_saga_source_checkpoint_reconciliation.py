from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceCheckpointReconciliationPlaceholder:
    name: str = "source_checkpoint_reconciliation"
