from __future__ import annotations

from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceSourceChild,
    RetrievalSurfaceSourceUnit,
)
from src.infrastructure.llm.knowledge_surface_economy_instant import (
    split_source_unit_for_instant,
)


def _unit(body: str) -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(
        id="unit-1",
        run_id="run-1",
        document_id="doc-1",
        source_unit_key="unit:key",
        source_chunk_indexes=(0,),
        title="Big FAQ unit",
        body=body,
        children=(
            RetrievalSurfaceSourceChild(
                title="content",
                body=body,
                raw_text=body,
                label_kind="content_section",
            ),
        ),
        raw_text=body,
        section_path=("Root",),
        source_refs=("chunk:0",),
        preprocessing_mode="faq",
        metadata={"source": "test"},
    )


def test_split_source_unit_for_instant_prefers_markdown_sections() -> None:
    body = "\n\n".join(
        (
            "# Alpha\n" + "A" * 900,
            "# Beta\n" + "B" * 900,
            "# Gamma\n" + "C" * 900,
        )
    )

    subunits = split_source_unit_for_instant(_unit(body), max_chars=950)

    assert len(subunits) == 3
    assert [item.metadata["subunit_index"] for item in subunits] == [1, 2, 3]
    assert all(
        item.metadata["original_source_unit_key"] == "unit:key"
        for item in subunits
    )
    assert all(item.source_refs == ("chunk:0",) for item in subunits)
    assert "# Alpha" in subunits[0].body
    assert "# Beta" in subunits[1].body


def test_split_source_unit_for_instant_falls_back_to_sentence_boundaries() -> None:
    body = "First sentence. " * 140

    subunits = split_source_unit_for_instant(_unit(body), max_chars=900)

    assert len(subunits) > 1
    assert "".join(item.body.replace(" ", "") for item in subunits).startswith(
        "Firstsentence"
    )
    assert all(item.metadata["economy_instant_subunit"] is True for item in subunits)
