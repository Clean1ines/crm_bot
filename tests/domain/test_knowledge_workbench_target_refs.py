from __future__ import annotations

from src.domain.project_plane.knowledge_workbench.target_refs import (
    WorkbenchTargetRef,
    WorkbenchTargetRefKind,
    fact_target_refs,
)


def test_fact_target_refs_include_fact_id_first() -> None:
    refs = fact_target_refs(
        fact_id="fact-1",
        claim_local_ref="c1",
        claim="Что такое продукт?",
    )

    assert refs[0] == WorkbenchTargetRef(
        kind=WorkbenchTargetRefKind.FACT_ID,
        value="fact-1",
    )


def test_fact_target_refs_include_claim_local_ref() -> None:
    refs = fact_target_refs(
        claim_local_ref="c1",
    )

    assert refs == (
        WorkbenchTargetRef(
            kind=WorkbenchTargetRefKind.CLAIM_LOCAL_REF,
            value="c1",
        ),
    )


def test_fact_target_refs_include_trimmed_claim_text() -> None:
    refs = fact_target_refs(
        claim="  Что такое продукт?  ",
    )

    assert refs == (
        WorkbenchTargetRef(
            kind=WorkbenchTargetRefKind.CLAIM_TEXT,
            value="Что такое продукт?",
        ),
    )


def test_fact_target_refs_omits_empty_values() -> None:
    refs = fact_target_refs(
        fact_id=None,
        claim_local_ref="",
        claim="   ",
    )

    assert refs == (
        WorkbenchTargetRef(
            kind=WorkbenchTargetRefKind.CLAIM_TEXT,
            value="",
        ),
    )
