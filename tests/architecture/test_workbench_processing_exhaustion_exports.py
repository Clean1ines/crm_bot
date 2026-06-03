from __future__ import annotations

import importlib


def test_workbench_processing_exhaustion_is_exported_from_package_root() -> None:
    module = importlib.import_module("src.domain.project_plane.knowledge_workbench")

    assert hasattr(module, "ProcessingExhaustionTransition")
    assert hasattr(module, "decide_processing_exhaustion_transition")
