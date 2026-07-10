from __future__ import annotations

from src.interfaces.composition.workbench_rag_eval import (
    make_start_workbench_rag_eval_v2,
)


def test_make_start_workbench_rag_eval_v2_does_not_require_llm_executor() -> None:
    composition = make_start_workbench_rag_eval_v2(pool=object())

    assert composition.pool is not None
