from __future__ import annotations

from types import SimpleNamespace

from src.domain.project_plane.knowledge_compilation import SourceRef
from src.infrastructure.db.repositories.knowledge_db_codecs import (
    first_source_excerpt,
    json_list_from_db,
    json_object_from_db,
    jsonb_object_payload,
    normalize_timestamp,
    optional_float,
    optional_int,
    pg_vector_text,
    source_ref_payload,
    source_ref_views_from_payload,
    source_refs_from_db,
    source_refs_payload,
    text_tuple_from_json,
)


class _IsoDateLike:
    def isoformat(self) -> str:
        return "2026-05-20T19:10:25"


def test_json_and_timestamp_codecs_preserve_repository_boundary_behavior() -> None:
    assert normalize_timestamp(None) is None
    assert normalize_timestamp("raw") == "raw"
    assert normalize_timestamp(_IsoDateLike()) == "2026-05-20T19:10:25"

    assert json_object_from_db({"a": 1}) == {"a": 1}
    assert json_object_from_db('{"a": 1}') == {"a": 1}
    assert json_object_from_db("[1, 2]") == {}

    assert json_list_from_db(("a", "b")) == ["a", "b"]
    assert json_list_from_db('["a", "b"]') == ["a", "b"]
    assert json_list_from_db('{"bad": true}') == []

    assert jsonb_object_payload({"title": "Цена"}) == '{"title": "Цена"}'


def test_scalar_and_vector_codecs_preserve_safe_defaults() -> None:
    assert optional_int("42") == 42
    assert optional_int(True) is None
    assert optional_int("bad") is None

    assert optional_float("3.5") == 3.5
    assert optional_float(False) is None
    assert optional_float("bad") is None

    assert pg_vector_text([0.1, 0.2]) == "[0.1,0.2]"


def test_text_tuple_from_json_dedupes_and_normalizes_text() -> None:
    assert text_tuple_from_json(["  A  B  ", "A B", "", None, 42]) == (
        "A B",
        "42",
    )
    assert text_tuple_from_json("  single   value ") == ("single value",)
    assert text_tuple_from_json({"bad": "shape"}) == ()


def test_source_ref_db_and_payload_codecs_preserve_grounding_shape() -> None:
    payload = {
        "source_index": "2",
        "quote": " quoted   source ",
        "source_chunk_id": "chunk-1",
        "start_offset": "10",
        "end_offset": 20,
        "confidence": "0.8",
    }

    refs = source_refs_from_db([payload, {"quote": ""}, "bad"])
    assert len(refs) == 1
    ref = refs[0]
    assert ref.source_index == 2
    assert ref.quote == "quoted source"
    assert ref.source_chunk_id == "chunk-1"
    assert ref.start_offset == 10
    assert ref.end_offset == 20
    assert ref.confidence == 0.8

    assert source_ref_payload(ref) == {
        "quote": "quoted source",
        "source_index": 2,
        "source_chunk_id": "chunk-1",
        "start_offset": 10,
        "end_offset": 20,
        "confidence": 0.8,
    }

    entry = SimpleNamespace(
        source_refs=(
            SourceRef(
                source_index=1,
                quote="Q",
                source_chunk_id="chunk-2",
                start_offset=None,
                end_offset=None,
                confidence=None,
            ),
        )
    )
    assert source_refs_payload(entry) == [
        {
            "quote": "Q",
            "source_index": 1,
            "source_chunk_id": "chunk-2",
        }
    ]


def test_source_ref_view_codecs_and_excerpt() -> None:
    refs = source_ref_views_from_payload(
        [
            {
                "source_index": 1,
                "quote": "Quote",
                "source_chunk_id": "chunk-1",
                "confidence": 0.7,
            },
            {"quote": ""},
            "bad",
        ]
    )

    assert len(refs) == 1
    assert refs[0].quote == "Quote"
    assert refs[0].source_chunk_id == "chunk-1"
    assert first_source_excerpt(refs) == "Quote"
    assert first_source_excerpt(()) is None
