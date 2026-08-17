import json
from pathlib import Path

from src.agent.nodes.response_generator import (
    StructuredGenerationValidation,
    build_structured_response_repair_prompt,
)
from src.agent.router.prompt_builder import (
    build_response_prompt,
    format_conversation_context_for_prompt,
    format_kb_prompt_entry_traces,
    format_kb_results,
    format_recent_ticket_resolutions_for_prompt,
)
from src.agent.router import prompt_builder


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


def test_response_prompt_dynamic_context_precedes_final_output_marker():
    prompt_paths = [
        REPO_ROOT / "src" / "agent" / "prompts" / "response_prompt.txt",
        REPO_ROOT / "src" / "agent" / "prompts" / "response_prompt.en.txt",
        REPO_ROOT / "src" / "agent" / "prompts" / "response_prompt.de.txt",
        REPO_ROOT / "src" / "agent" / "prompts" / "response_prompt.es.txt",
    ]
    markers = ("Верни только валидный JSON", "Answer:", "Antwort:", "Respuesta:")

    for path in prompt_paths:
        prompt = path.read_text(encoding="utf-8")
        context_index = prompt.index("{conversation_context}")
        marker_index = min(
            index for marker in markers if (index := prompt.find(marker)) >= 0
        )
        assert context_index < marker_index
        assert prompt.count("{conversation_context}") == 1
        assert prompt.count("{recent_ticket_resolutions}") == 1


def test_response_prompt_ru_uses_canonical_default_template(monkeypatch):
    loaded: list[str] = []

    def fake_load(filename: str) -> str:
        loaded.append(filename)
        if filename == "interpretation_block.txt":
            return "interpretation"
        return "response {user_input}"

    monkeypatch.setattr(prompt_builder, "_response_prompt_templates", {})
    monkeypatch.setattr(prompt_builder, "_response_prompt_template", None)
    monkeypatch.setattr(prompt_builder, "_interpretation_block", None)
    monkeypatch.setattr(prompt_builder, "_load_prompt_template", fake_load)

    prompt = build_response_prompt(
        decision="LLM_GENERATE",
        user_input="Что такое менеджерский контур?",
        target_language="ru",
    )

    assert prompt == "response Что такое менеджерский контур?"
    assert "response_prompt.txt" in loaded
    assert "response_prompt.ru.txt" not in loaded


def test_intent_prompt_defines_operational_relation_fields():
    prompt = (REPO_ROOT / "src" / "agent" / "prompts" / "intent_prompt.txt").read_text(
        encoding="utf-8"
    )

    required = (
        "current_subject: текущая самостоятельная тема разговора",
        "clarification: реплика зависит от предыдущей темы",
        "repeat_answered: пользователь повторяет вопрос",
        "repeat_unresolved: пользователь повторяет вопрос",
        "none: новый самостоятельный вопрос",
        "dissatisfaction: true только при явном недовольстве ответом ассистента",
    )
    for marker in required:
        assert marker in prompt


def test_conversation_context_prompt_formatter_returns_valid_bounded_json():
    attempts = [
        {
            "standalone_query": f'Вопрос {index} {{скобки}} "кавычки" ' + "x" * 300,
            "subject": "субъект " + "y" * 120,
            "outcome": "unsupported" if index < 9 else "generation_failed",
            "answer_preview": "preview " + "z" * 300,
            "unsupported_aspects": [f"aspect {i} " + "a" * 200 for i in range(6)],
            "supporting_entry_ids": [f"entry-{i}-" + "b" * 200 for i in range(6)],
            "attempted_at": f"2026-01-01T00:00:{index:02d}+00:00",
        }
        for index in range(10)
    ]

    payload = json.loads(
        format_conversation_context_for_prompt(
            {
                "current_subject": "веб-панель",
                "repeat_relation": "repeat_unresolved",
                "dissatisfaction": True,
                "last_standalone_query": "последний вопрос " + "q" * 300,
                "question_attempts": attempts,
            }
        )
    )

    assert len(payload["question_attempts"]) == 6
    assert payload["question_attempts"][0]["standalone_query"].startswith("Вопрос 4")
    assert payload["question_attempts"][-1]["standalone_query"].startswith("Вопрос 9")
    assert payload["question_attempts"][-1]["outcome"] == "generation_failed"
    for attempt in payload["question_attempts"]:
        assert len(attempt["standalone_query"]) <= 240
        assert len(attempt["subject"]) <= 80
        assert len(attempt["answer_preview"]) <= 160
        assert len(attempt["unsupported_aspects"]) == 4
        assert len(attempt["supporting_entry_ids"]) == 4


def test_recent_ticket_resolutions_formatter_serializes_three_valid_records():
    payload = json.loads(
        format_recent_ticket_resolutions_for_prompt(
            [
                {
                    "thread_id": f"thread-{index}",
                    "summary_text": f'Итог {{json}} "quote" {index} ' + "x" * 700,
                    "closed_at": "2026-01-01T00:00:00+00:00",
                    "source": "llm",
                    "version": index,
                }
                for index in range(5)
            ]
        )
    )

    assert [item["thread_id"] for item in payload] == [
        "thread-0",
        "thread-1",
        "thread-2",
    ]
    assert payload[0]["summary_text"].startswith('Итог {json} "quote" 0')
    assert all(len(item["summary_text"]) <= 500 for item in payload)


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
