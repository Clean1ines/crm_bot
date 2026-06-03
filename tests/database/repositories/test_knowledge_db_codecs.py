from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_views import SourceRefView
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
    source_ref_view_from_mapping,
    source_ref_views_from_payload,
    text_tuple_from_json,
)


def test_normalize_timestamp_accepts_datetime_and_iso_string() -> None:
    now = datetime.now(tz=timezone.utc)

    assert normalize_timestamp(now) is now
    assert normalize_timestamp("2026-01-01T10:30:00+00:00") == datetime(
        2026,
        1,
        1,
        10,
        30,
        tzinfo=timezone.utc,
    )
    assert normalize_timestamp("bad") is None
    assert normalize_timestamp(None) is None


def test_json_helpers_decode_db_values_safely() -> None:
    assert jsonb_object_payload({"a": 1}) == '{"a": 1}'
    assert jsonb_object_payload(["bad"]) == "{}"

    assert json_object_from_db({"a": 1}) == {"a": 1}
    assert json_object_from_db('{"a": 1}') == {"a": 1}
    assert json_object_from_db("[1]") == {}

    assert json_list_from_db(["a"]) == ["a"]
    assert json_list_from_db(("a", "b")) == ["a", "b"]
    assert json_list_from_db('["a"]') == ["a"]
    assert json_list_from_db('{"a": 1}') == []


def test_scalar_helpers_are_strict_enough_for_db_payloads() -> None:
    assert optional_int(3) == 3
    assert optional_int("4") == 4
    assert optional_int(True) is None
    assert optional_int("bad") is None

    assert optional_float(1) == 1.0
    assert optional_float("2.5") == 2.5
    assert optional_float(False) is None
    assert optional_float("bad") is None

    assert text_tuple_from_json(["  a  b ", 1, "", "c"]) == ("a b", "c")
    assert text_tuple_from_json('["x", " y "]') == ("x", "y")


def test_pg_vector_text_serializes_float_sequence_for_pgvector() -> None:
    assert pg_vector_text([1, 2.5, -3]) == "[1.0,2.5,-3.0]"


def test_source_ref_view_from_mapping_normalizes_evidence_payload() -> None:
    ref = source_ref_view_from_mapping(
        {
            "source_index": "2",
            "quote": " Exact   quote. ",
            "source_chunk_id": "chunk-1",
            "start_offset": "10",
            "end_offset": 20,
            "confidence": "0.75",
        }
    )

    assert ref == SourceRefView(
        source_index=2,
        quote="Exact quote.",
        source_chunk_id="chunk-1",
        start_offset=10,
        end_offset=20,
        confidence=0.75,
    )


def test_source_ref_view_from_mapping_rejects_empty_quote() -> None:
    with pytest.raises(ValueError):
        source_ref_view_from_mapping({"source_index": 0, "quote": "  "})


def test_source_ref_payload_accepts_view_or_mapping() -> None:
    ref = SourceRefView(
        source_index=1,
        quote="Quote",
        source_chunk_id="chunk-1",
        start_offset=5,
        end_offset=9,
        confidence=0.5,
    )

    assert source_ref_payload(ref) == {
        "source_index": 1,
        "quote": "Quote",
        "source_chunk_id": "chunk-1",
        "start_offset": 5,
        "end_offset": 9,
        "confidence": 0.5,
    }

    assert source_ref_payload({"source_index": "1", "quote": "  Quote  "}) == {
        "source_index": 1,
        "quote": "Quote",
    }


def test_source_ref_views_from_payload_skips_invalid_items() -> None:
    refs = source_ref_views_from_payload(
        [
            {"source_index": 0, "quote": " Quote "},
            {"quote": ""},
            "bad",
        ]
    )

    assert refs == (SourceRefView(source_index=0, quote="Quote"),)
    assert source_ref_views_from_payload("bad") == ()
    assert source_ref_views_from_payload({"quote": "not-list"}) == ()


def test_first_source_excerpt_returns_first_non_blank_quote() -> None:
    refs = (
        SourceRefView(source_index=0, quote=""),
        SourceRefView(source_index=1, quote=" Quote "),
    )

    assert first_source_excerpt(refs) == "Quote"
    assert first_source_excerpt(()) is None
