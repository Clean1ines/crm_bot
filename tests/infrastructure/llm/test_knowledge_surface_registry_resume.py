from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import cast

import pytest
from groq import AsyncGroq

from src.domain.project_plane.knowledge_preprocessing import MODE_FAQ
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceSourceUnit,
)
from src.infrastructure.llm.knowledge_surface_compiler import (
    GroqKnowledgeSurfaceCompiler,
)


def _unit(index: int) -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(
        id=f"unit-{index}",
        run_id="run-1",
        document_id="doc-1",
        source_unit_key=f"unit:{index}",
        source_chunk_indexes=(index,),
        title=f"Section {index}",
        body=f"Body {index}",
        children=(),
        raw_text=f"# Section {index}\nBody {index}",
        section_path=(f"Section {index}",),
        source_refs=(f"chunk:{index}",),
        preprocessing_mode=MODE_FAQ,
        metadata={},
    )


def _surface_finding(
    key: str,
    question: str,
    answer: str,
    *,
    source_ref: str,
) -> dict[str, object]:
    return {
        "action": "new",
        "local_surface_key": key,
        "title": question,
        "canonical_question": question,
        "surface_kind": "specific",
        "answer": answer,
        "short_answer": answer,
        "source_refs": [source_ref],
        "source_chunk_indexes": [int(source_ref.rsplit(":", 1)[1])],
        "confidence": 0.9,
    }


class _CheckpointGroq:
    def __init__(
        self,
        *,
        findings_by_key: dict[str, list[dict[str, object]]],
        forbidden_keys: set[str] | None = None,
        fail_on_seen_registry_question: dict[str, str] | None = None,
    ) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.findings_by_key = findings_by_key
        self.forbidden_keys = forbidden_keys or set()
        self.fail_on_seen_registry_question = fail_on_seen_registry_question or {}
        self.calls: list[tuple[str, str]] = []
        self.payloads: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        messages = kwargs["messages"]
        prompt = str(messages[1]["content"])
        payload = json.loads(prompt.split("SECTION_COMPILATION_INPUT_JSON:\n", 1)[1])
        source_unit = payload["source_unit"]
        assert isinstance(source_unit, dict)
        key = str(source_unit["source_unit_key"])
        stage = str(payload["stage"])

        if key in self.forbidden_keys:
            raise AssertionError(f"LLM call was made for skipped source unit: {key}")

        expected_question = self.fail_on_seen_registry_question.get(key)
        if expected_question is not None:
            registry_snapshot = payload.get("registry_snapshot")
            assert isinstance(registry_snapshot, dict)
            known = registry_snapshot.get("known_canonical_questions")
            assert isinstance(known, list)
            questions = {
                str(item.get("canonical_question"))
                for item in known
                if isinstance(item, dict)
            }
            assert expected_question in questions

        self.calls.append((stage, key))
        self.payloads.append(payload)

        if stage == "discover_section_findings":
            content = {
                "findings": self.findings_by_key.get(key, []),
                "warnings": [],
                "metrics": {},
            }
        elif stage == "merge_section_findings_into_registry":
            content = {"registry_updates": [], "warnings": [], "metrics": {}}
        elif stage == "finalize_retrieval_surface_graph":
            content = {"warnings": [], "metrics": {}}
        else:
            raise AssertionError(f"unexpected stage: {stage}")

        await asyncio.sleep(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(content, ensure_ascii=False)
                    )
                )
            ]
        )


@pytest.mark.asyncio
async def test_resume_restores_registry_and_skips_completed_source_units() -> None:
    events: list[dict[str, object]] = []
    first_client = _CheckpointGroq(
        findings_by_key={
            "unit:0": [
                _surface_finding(
                    "surface-a",
                    "How do uploads work?",
                    "Uploads use the Knowledge tab.",
                    source_ref="chunk:0",
                )
            ]
        }
    )
    first_compiler = GroqKnowledgeSurfaceCompiler(
        client=cast(AsyncGroq, first_client),
        model="test-model",
    )
    first_compiler.set_progress_callback(lambda event: events.append(dict(event)))

    await first_compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0),),
        file_name="faq.md",
        run_id="run-resume",
    )

    checkpoint = next(
        event["source_unit_checkpoint"]
        for event in events
        if event.get("source_unit_key") == "unit:0"
    )
    assert checkpoint["checkpoint_kind"] == "section_registry_state"
    assert checkpoint["processed_source_unit_keys"] == ["unit:0"]
    assert checkpoint["registry_snapshot_after_section"]

    second_client = _CheckpointGroq(
        findings_by_key={
            "unit:1": [
                _surface_finding(
                    "surface-b",
                    "How do invitations work?",
                    "Invitations use links.",
                    source_ref="chunk:1",
                )
            ]
        },
        forbidden_keys={"unit:0"},
        fail_on_seen_registry_question={
            "unit:1": "How do uploads work?",
        },
    )
    second_compiler = GroqKnowledgeSurfaceCompiler(
        client=cast(AsyncGroq, second_client),
        model="test-model",
    )
    second_compiler.set_source_unit_result_checkpoints({"unit:0": checkpoint})

    result = await second_compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0), _unit(1)),
        file_name="faq.md",
        run_id="run-resume",
    )

    assert ("discover_section_findings", "unit:0") not in second_client.calls
    assert any(
        call == ("discover_section_findings", "unit:1") for call in second_client.calls
    )
    assert {surface.local_surface_key for surface in result.graph.surfaces} == {
        "surface-a",
        "surface-b",
    }
    assert result.metrics["checkpoint_restore_mode"] == "section_registry_state"


@pytest.mark.asyncio
async def test_manual_cancel_preserves_completed_unit_checkpoint_only() -> None:
    events: list[dict[str, object]] = []
    call_count = 0

    async def cancel_after_first_completed() -> None:
        nonlocal call_count
        call_count += 1
        if (
            any(event.get("source_unit_key") == "unit:0" for event in events)
            and call_count > 1
        ):
            raise RuntimeError("manual cancel")

    client = _CheckpointGroq(
        findings_by_key={
            "unit:0": [
                _surface_finding(
                    "surface-a", "Question A?", "Answer A.", source_ref="chunk:0"
                )
            ],
            "unit:1": [
                _surface_finding(
                    "surface-b", "Question B?", "Answer B.", source_ref="chunk:1"
                )
            ],
        }
    )
    compiler = GroqKnowledgeSurfaceCompiler(
        client=cast(AsyncGroq, client),
        model="test-model",
    )
    compiler.set_progress_callback(lambda event: events.append(dict(event)))
    compiler.set_cancel_check(cancel_after_first_completed)

    with pytest.raises(RuntimeError, match="manual cancel"):
        await compiler.compile_surfaces(
            mode=MODE_FAQ,
            source_units=(_unit(0), _unit(1)),
            file_name="faq.md",
            run_id="run-cancel",
        )

    checkpoint_events = [event for event in events if "source_unit_checkpoint" in event]
    assert [event["source_unit_key"] for event in checkpoint_events] == ["unit:0"]


@pytest.mark.asyncio
async def test_empty_findings_checkpoint_does_not_create_placeholder_on_resume() -> (
    None
):
    events: list[dict[str, object]] = []
    first_client = _CheckpointGroq(findings_by_key={"unit:0": []})
    first_compiler = GroqKnowledgeSurfaceCompiler(
        client=cast(AsyncGroq, first_client),
        model="test-model",
    )
    first_compiler.set_progress_callback(lambda event: events.append(dict(event)))

    with pytest.raises(Exception):
        await first_compiler.compile_surfaces(
            mode=MODE_FAQ,
            source_units=(_unit(0),),
            file_name="faq.md",
            run_id="run-empty",
        )

    checkpoint = next(
        event["source_unit_checkpoint"]
        for event in events
        if event.get("source_unit_key") == "unit:0"
    )
    assert checkpoint["section_findings"] == []
    assert checkpoint["metrics"]["registry_size"] == 0


@pytest.mark.asyncio
async def test_checkpoint_version_mismatch_is_explicitly_ignored() -> None:
    client = _CheckpointGroq(
        findings_by_key={
            "unit:0": [
                _surface_finding(
                    "surface-a", "Question A?", "Answer A.", source_ref="chunk:0"
                )
            ]
        }
    )
    compiler = GroqKnowledgeSurfaceCompiler(
        client=cast(AsyncGroq, client),
        model="test-model",
    )
    compiler.set_source_unit_result_checkpoints(
        {
            "unit:0": {
                "version": 999,
                "checkpoint_kind": "section_registry_state",
                "source_unit_key": "unit:0",
                "processed_source_unit_keys": ["unit:0"],
            }
        }
    )

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0),),
        file_name="faq.md",
        run_id="run-version",
    )

    assert any(call == ("discover_section_findings", "unit:0") for call in client.calls)
    assert result.metrics["checkpoint_restore_mode"] == "none"
    assert "checkpoint_restore_warnings" in result.metrics
