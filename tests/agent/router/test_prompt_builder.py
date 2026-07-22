from pathlib import Path

from src.agent.nodes.response_generator import (
    StructuredGenerationValidation,
    build_structured_response_repair_prompt,
)
from src.agent.router.prompt_builder import (
    format_kb_prompt_entry_traces,
    format_kb_results,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_format_kb_results_uses_evidence_aliases_without_canonical_ids():
    canonical_id = "draft-claim-curation-runtime-entry:abc123"
    prompt, top_score, count = format_kb_results(
        [
            {
                "id": canonical_id,
                "score": 0.578,
                "method": "hybrid",
                "content": "Axole supports the manager workspace.",
            },
            {
                "id": "entry-2",
                "score": 0.176,
                "method": "vector",
                "content": "Axole has project roles.",
            },
        ]
    )

    assert "E1 | score=0.578 | method=hybrid | text=" in prompt
    assert "E2 | score=0.176 | method=vector | text=" in prompt
    assert canonical_id not in prompt
    assert "abc123" not in prompt
    assert "id=" not in prompt
    assert top_score == 0.578
    assert count == 2


def test_format_kb_results_filters_invalid_chunks_before_numbering():
    prompt, _top_score, count = format_kb_results(
        [
            {"id": "", "score": 0.9, "content": "missing id"},
            {"id": "entry-1", "score": 0.8, "content": ""},
            {"id": "entry-2", "score": 0.7, "content": "valid"},
        ]
    )

    assert prompt.startswith("E1 | score=0.700")
    assert "E2" not in prompt
    assert count == 1


def test_format_kb_prompt_entry_traces_include_alias_and_canonical_id_in_order():
    chunks = [
        {"id": "entry-1", "score": 0.5, "content": "first"},
        {"id": "entry-2", "score": 0.4, "content": "second"},
    ]

    traces = format_kb_prompt_entry_traces(chunks)

    assert [trace["evidence_ref"] for trace in traces] == ["E1", "E2"]
    assert [trace["canonical_entry_id"] for trace in traces] == ["entry-1", "entry-2"]
    assert [trace["rank"] for trace in traces] == [1, 2]


def test_response_prompt_uses_only_evidence_refs_in_json_schema():
    prompt = (
        REPO_ROOT / "src" / "agent" / "prompts" / "response_prompt.txt"
    ).read_text(encoding="utf-8")

    assert '"supporting_evidence_refs"' in prompt
    assert '"supporting_entry_ids"' not in prompt
    legacy_mentions = [
        line for line in prompt.splitlines() if "supporting_entry_ids" in line
    ]
    assert legacy_mentions == [
        "- Запрещено возвращать legacy field supporting_entry_ids."
    ]


def test_model_facing_kb_formatter_excludes_raw_id_markers():
    prompt, _top_score, _count = format_kb_results(
        [
            {
                "id": "draft-claim-curation-runtime-entry:abc123",
                "score": 0.9,
                "method": "hybrid",
                "content": "Факт из базы.",
                "document_id": "doc-1",
                "source_id": "source-1",
            }
        ]
    )

    assert "E1 | score=0.900 | method=hybrid | text=" in prompt
    for marker in (
        "draft-claim-curation-runtime-entry:",
        "id=",
        "entry_id=",
        "source_id=",
        "document_id=",
    ):
        assert marker not in prompt


def test_repair_prompt_does_not_copy_canonical_ids_into_repair_section():
    original_prompt, _top_score, _count = format_kb_results(
        [
            {
                "id": "draft-claim-curation-runtime-entry:abc123",
                "score": 0.9,
                "content": "Факт из базы.",
            }
        ]
    )
    repair_prompt = build_structured_response_repair_prompt(
        original_prompt=original_prompt,
        invalid_output=(
            '{"answerability":"supported","answer":"x",'
            '"supporting_entry_ids":["draft-claim-curation-runtime-entry:abc123"]}'
        ),
        validation=StructuredGenerationValidation(
            result=None,
            parse_status="valid",
            schema_status="invalid_payload",
            evidence_reference_status="not_called",
            failure_reason="legacy supporting_entry_ids field is forbidden",
        ),
        known_evidence_refs=["E1"],
    )

    assert "Allowed evidence refs: E1" in repair_prompt
    repair_section = repair_prompt.split("The previous response did not satisfy", 1)[1]
    assert "draft-claim-curation-runtime-entry:" not in repair_section
    assert "supporting_entry_ids" in repair_section


def test_internal_prompt_entry_trace_preserves_alias_to_canonical_mapping():
    canonical_id = "draft-claim-curation-runtime-entry:abc123"

    traces = format_kb_prompt_entry_traces(
        [{"id": canonical_id, "score": 0.9, "content": "Факт из базы."}]
    )

    assert traces[0]["evidence_ref"] == "E1"
    assert traces[0]["canonical_entry_id"] == canonical_id
    assert "id" not in traces[0]
