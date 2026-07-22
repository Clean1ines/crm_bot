import pytest

from src.domain.runtime.evidence_references import (
    EvidenceReferenceIndex,
    UnknownEvidenceReference,
)


def test_evidence_reference_aliases_are_assigned_in_prompt_order():
    chunks = [
        {"id": f"entry-{index}", "content": f"text {index}"} for index in range(1, 7)
    ]

    index = EvidenceReferenceIndex.from_knowledge_chunks(chunks, limit=5)

    assert index.known_aliases() == ("E1", "E2", "E3", "E4", "E5")
    assert index.resolve_aliases(["E1", "E3", "E5"]) == [
        "entry-1",
        "entry-3",
        "entry-5",
    ]


def test_evidence_reference_index_filters_invalid_and_duplicate_chunks_without_gaps():
    chunks = [
        {"id": "entry-1", "content": "first"},
        {"id": "entry-1", "content": "duplicate"},
        {"id": "", "content": "missing id"},
        {"id": "entry-2", "content": ""},
        {"id": "entry-3", "content": "third"},
    ]

    index = EvidenceReferenceIndex.from_knowledge_chunks(chunks, limit=5)

    assert index.known_aliases() == ("E1", "E2")
    assert index.resolve_aliases(["E1", "E2"]) == ["entry-1", "entry-3"]


@pytest.mark.parametrize("alias", ["E9", "e1", "entry-1"])
def test_evidence_reference_index_rejects_unknown_lowercase_and_raw_ids(alias):
    index = EvidenceReferenceIndex.from_knowledge_chunks(
        [{"id": "entry-1", "content": "first"}],
        limit=5,
    )

    with pytest.raises(UnknownEvidenceReference) as exc_info:
        index.resolve_aliases([alias])

    assert exc_info.value.unknown_aliases == (alias,)


def test_unknown_evidence_reference_stores_immutable_alias_tuple():
    exc = UnknownEvidenceReference(["E9", "e1"])

    assert exc.unknown_aliases == ("E9", "e1")


def test_evidence_reference_resolution_deduplicates_aliases_in_model_order():
    index = EvidenceReferenceIndex.from_knowledge_chunks(
        [
            {"id": "entry-1", "content": "first"},
            {"id": "entry-2", "content": "second"},
        ],
        limit=5,
    )

    assert index.resolve_aliases(["E2", "E2", "E1"]) == ["entry-2", "entry-1"]


def test_evidence_reference_resolution_preserves_model_ref_order():
    index = EvidenceReferenceIndex.from_knowledge_chunks(
        [
            {"id": "canonical-id-1", "content": "first"},
            {"id": "canonical-id-2", "content": "second"},
        ],
        limit=5,
    )

    assert index.resolve_aliases(["E2", "E1"]) == [
        "canonical-id-2",
        "canonical-id-1",
    ]
