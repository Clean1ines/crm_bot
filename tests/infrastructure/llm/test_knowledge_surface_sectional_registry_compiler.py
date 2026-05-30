from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from groq import AsyncGroq

from src.domain.project_plane.knowledge_preprocessing import MODE_FAQ
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceSourceUnit,
)
from src.infrastructure.llm.knowledge_surface_compiler import (
    GroqKnowledgeSurfaceCompiler,
)

PROMPTS_DIR = Path("src/agent/prompts")
SECTION_FINDINGS_PROMPT = (
    (PROMPTS_DIR / "faq_surface_section_findings.ru.txt")
    .read_text(encoding="utf-8")
    .strip()
)
REGISTRY_MERGE_PROMPT = (
    (PROMPTS_DIR / "faq_surface_registry_merge.ru.txt")
    .read_text(encoding="utf-8")
    .strip()
)
FINAL_RECONCILIATION_PROMPT = (
    (PROMPTS_DIR / "faq_surface_final_reconciliation.ru.txt")
    .read_text(encoding="utf-8")
    .strip()
)


def _unit(index: int) -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(
        id=f"unit-{index}",
        run_id="run-1",
        document_id="doc-1",
        source_unit_key=f"unit:{index}",
        source_chunk_indexes=(index,),
        title=f"Section {index}",
        body=f"Body for section {index}",
        children=(),
        raw_text=f"# Section {index}\nBody for section {index}",
        section_path=(f"Section {index}",),
        source_refs=(f"chunk:{index}",),
        preprocessing_mode=MODE_FAQ,
        metadata={},
    )


class _FakeSectionGroq:
    def __init__(self, *, empty_findings_for: set[str] | None = None) -> None:
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create),
        )
        self.empty_findings_for = empty_findings_for or set()
        self.prompts: list[str] = []
        self.payloads: list[dict[str, object]] = []
        self.started: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0

    async def create(self, **kwargs: object) -> object:
        messages = kwargs["messages"]
        assert isinstance(messages, list)
        prompt = str(messages[1]["content"])

        assert '"source_units"' not in prompt
        assert "SECTION_COMPILATION_INPUT_JSON:" in prompt

        payload = json.loads(prompt.split("SECTION_COMPILATION_INPUT_JSON:\n", 1)[1])
        assert "source_unit" in payload
        assert "source_units" not in payload

        source_unit = payload["source_unit"]
        assert isinstance(source_unit, dict)
        key = str(source_unit["source_unit_key"])
        stage = str(payload["stage"])

        if stage == "discover_section_findings":
            assert SECTION_FINDINGS_PROMPT in prompt
        elif stage == "merge_section_findings_into_registry":
            assert REGISTRY_MERGE_PROMPT in prompt
        elif stage == "finalize_retrieval_surface_graph":
            assert FINAL_RECONCILIATION_PROMPT in prompt
        else:
            raise AssertionError(f"unexpected LLM stage: {stage}")

        self.prompts.append(prompt)
        self.payloads.append(payload)
        self.started.append((stage, key))

        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1

        if stage == "discover_section_findings":
            if key in self.empty_findings_for:
                content = {"findings": [], "warnings": [], "metrics": {}}
            else:
                content = {
                    "findings": [
                        {
                            "action": "new",
                            "local_surface_key": f"surface-{key}",
                            "title": f"Question {key}",
                            "canonical_question": f"Question {key}?",
                            "surface_kind": "specific",
                            "answer": f"Answer {key}",
                            "short_answer": f"Short {key}",
                            "source_refs": [f"chunk:{key.rsplit(':', 1)[1]}"],
                            "confidence": 0.8,
                            "reason": "test",
                        }
                    ],
                    "warnings": [],
                    "metrics": {},
                }
        elif stage == "merge_section_findings_into_registry":
            findings = payload.get("section_findings")
            assert isinstance(findings, list)
            content = {
                "merge_decisions": [
                    {
                        "local_surface_key": item.get("local_surface_key", ""),
                        "canonical_question": item.get("canonical_question", ""),
                        "decision": "keep_new",
                        "target_surface_key": "",
                        "confidence": 0.8,
                        "reason": "test keep new",
                    }
                    for item in findings
                    if isinstance(item, dict)
                ],
                "warnings": [],
                "metrics": {},
            }
        elif stage == "finalize_retrieval_surface_graph":
            assert payload.get("final_reconciliation") is True
            content = {
                "warnings": [],
                "metrics": {
                    "duplicate_risk_count": 0,
                    "role_label_risk_count": 0,
                    "umbrella_child_review_count": 0,
                },
            }
        else:
            raise AssertionError(f"unexpected LLM stage: {stage}")

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(content, ensure_ascii=False)
                    ),
                )
            ]
        )


def test_compile_surfaces_does_not_call_one_shot_prompt_builder() -> None:
    source = inspect.getsource(GroqKnowledgeSurfaceCompiler.compile_surfaces)

    assert "_build_prompt" not in source
    assert "_load_instruction" not in source
    assert "source_units[: self._max_source_units]" not in source
    assert "StateGraph(" in source


def test_production_compiler_uses_node_specific_prompt_loader() -> None:
    module_source = Path(
        "src/infrastructure/llm/knowledge_surface_compiler.py"
    ).read_text(encoding="utf-8")
    class_source = inspect.getsource(GroqKnowledgeSurfaceCompiler)

    assert "def _load_prompt(" in module_source
    assert "FAQ_SECTION_FINDINGS_PROMPT_FILE" in module_source
    assert "FAQ_REGISTRY_MERGE_PROMPT_FILE" in module_source
    assert "FAQ_FINAL_RECONCILIATION_PROMPT_FILE" in module_source
    assert "prompt_file=FAQ_SECTION_FINDINGS_PROMPT_FILE" in class_source
    assert "prompt_file=FAQ_REGISTRY_MERGE_PROMPT_FILE" in class_source
    assert "prompt_file=FAQ_FINAL_RECONCILIATION_PROMPT_FILE" in class_source
    assert "_placeholder_finding" not in class_source


@pytest.mark.asyncio
async def test_prompt_file_content_reaches_actual_llm_prompts() -> None:
    fake = _FakeSectionGroq()
    compiler = GroqKnowledgeSurfaceCompiler(
        client=cast(AsyncGroq, fake),
        model="test-model",
    )

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=tuple(_unit(index) for index in range(2)),
        file_name="faq.md",
        run_id="run-1",
    )

    assert isinstance(result, RetrievalSurfaceCompilationResult)
    assert result.graph.surfaces
    assert any(SECTION_FINDINGS_PROMPT in item for item in fake.prompts)
    assert any(REGISTRY_MERGE_PROMPT in item for item in fake.prompts)
    assert any(FINAL_RECONCILIATION_PROMPT in item for item in fake.prompts)


@pytest.mark.asyncio
async def test_section_prompts_are_single_source_unit_and_return_type_compatible() -> (
    None
):
    fake = _FakeSectionGroq()
    compiler = GroqKnowledgeSurfaceCompiler(
        client=cast(AsyncGroq, fake),
        model="test-model",
    )

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=tuple(_unit(index) for index in range(2)),
        file_name="faq.md",
        run_id="run-1",
    )

    assert isinstance(result, RetrievalSurfaceCompilationResult)
    assert result.graph.surfaces
    assert all('"source_units"' not in prompt for prompt in fake.prompts)
    assert all("source_unit" in payload for payload in fake.payloads)
    assert all("source_units" not in payload for payload in fake.payloads)


@pytest.mark.asyncio
async def test_first_three_sections_are_seeded_sequentially_then_parallel_is_capped_at_three() -> (
    None
):
    fake = _FakeSectionGroq()
    compiler = GroqKnowledgeSurfaceCompiler(
        client=cast(AsyncGroq, fake),
        model="test-model",
    )

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=tuple(_unit(index) for index in range(7)),
        file_name="faq.md",
        run_id="run-1",
    )

    discover_order = [
        key for stage, key in fake.started if stage == "discover_section_findings"
    ]

    assert discover_order[:3] == ["unit:0", "unit:1", "unit:2"]
    assert fake.max_active <= 3
    assert result.metrics["parallel_section_concurrency"] == 3
    assert result.metrics["graph_execution"] == "langgraph_stategraph"
    assert len(result.graph.surfaces) == 7


@pytest.mark.asyncio
async def test_empty_findings_do_not_materialize_placeholder_surface() -> None:
    fake = _FakeSectionGroq(empty_findings_for={"unit:0"})
    compiler = GroqKnowledgeSurfaceCompiler(
        client=cast(AsyncGroq, fake),
        model="test-model",
    )

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0), _unit(1)),
        file_name="faq.md",
        run_id="run-1",
    )

    surface_keys = [surface.local_surface_key for surface in result.graph.surfaces]
    assert "surface-unit:0" not in surface_keys
    assert surface_keys == ["surface-unit:1"]


class _ScriptedRegistryMergeGroq:
    def __init__(
        self,
        *,
        findings_by_key: dict[str, list[dict[str, object]]],
        registry_updates_by_key: dict[str, list[dict[str, object]]] | None = None,
        merge_decisions_by_key: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.findings_by_key = findings_by_key
        self.registry_updates_by_key = registry_updates_by_key or {}
        self.merge_decisions_by_key = merge_decisions_by_key or {}
        self.prompts: list[str] = []

    async def create(self, **kwargs: object) -> object:
        messages = kwargs["messages"]
        prompt = str(messages[1]["content"])
        self.prompts.append(prompt)
        payload = json.loads(prompt.split("SECTION_COMPILATION_INPUT_JSON:\n", 1)[1])
        source_unit = payload["source_unit"]
        assert isinstance(source_unit, dict)
        key = str(source_unit["source_unit_key"])
        stage = str(payload["stage"])

        if stage == "discover_section_findings":
            content = {
                "findings": self.findings_by_key.get(key, []),
                "warnings": [],
                "metrics": {},
            }
        elif stage == "merge_section_findings_into_registry":
            if key in self.merge_decisions_by_key:
                content = {
                    "merge_decisions": self.merge_decisions_by_key[key],
                    "warnings": [],
                    "metrics": {"compatibility": True},
                }
            else:
                content = {
                    "registry_updates": self.registry_updates_by_key.get(key, []),
                    "warnings": [],
                    "metrics": {},
                }
        elif stage == "finalize_retrieval_surface_graph":
            content = {"warnings": [], "metrics": {}}
        else:
            raise AssertionError(f"unexpected stage: {stage}")

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(content, ensure_ascii=False)
                    )
                )
            ]
        )


def _role_finding(
    kind: str,
    value: str,
    *,
    source_ref: str = "chunk:0",
) -> dict[str, object]:
    return {
        "action": kind,
        "local_surface_key": kind,
        "title": kind,
        "canonical_question": kind,
        "surface_kind": "specific",
        "answer": value,
        "short_answer": value,
        "source_refs": [source_ref],
        "source_chunk_indexes": [int(source_ref.rsplit(":", 1)[1])],
        "role_label_kind": kind,
        "confidence": 0.9,
    }


def _surface_finding(
    key: str,
    question: str,
    answer: str,
    *,
    short_answer: str | None = None,
    surface_kind: str = "specific",
    parent: str = "",
    children: list[str] | None = None,
    source_ref: str = "chunk:0",
) -> dict[str, object]:
    return {
        "action": "new",
        "local_surface_key": key,
        "title": question,
        "canonical_question": question,
        "surface_kind": surface_kind,
        "answer": answer,
        "short_answer": short_answer or answer,
        "parent_surface_key": parent,
        "child_surface_keys": children or [],
        "source_refs": [source_ref],
        "source_chunk_indexes": [int(source_ref.rsplit(":", 1)[1])],
        "confidence": 0.9,
    }


@pytest.mark.asyncio
async def test_role_labels_become_one_surface_metadata_not_surfaces() -> None:
    fake = _ScriptedRegistryMergeGroq(
        findings_by_key={
            "unit:0": [
                _role_finding("customer_intent", "How do I upload documents?"),
                _role_finding(
                    "factual_answer_core", "Upload documents in the Knowledge tab."
                ),
                _role_finding("short_answer", "Use the Knowledge tab."),
            ]
        }
    )
    compiler = GroqKnowledgeSurfaceCompiler(client=cast(AsyncGroq, fake), model="test")

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0),),
        file_name="faq.md",
        run_id="run-role",
    )

    assert len(result.graph.surfaces) == 1
    surface = result.graph.surfaces[0]
    assert surface.canonical_question == "How do I upload documents?"
    assert surface.short_answer == "Use the Knowledge tab."
    assert "Upload documents in the Knowledge tab." in surface.answer
    assert surface.metadata["role_label_metadata"]
    assert not any(
        surface.local_surface_key
        in {
            "factual_answer_core",
            "short_answer",
            "customer_intent",
        }
        for surface in result.graph.surfaces
    )


@pytest.mark.asyncio
async def test_exact_duplicate_canonical_question_merges() -> None:
    fake = _ScriptedRegistryMergeGroq(
        findings_by_key={
            "unit:0": [
                _surface_finding(
                    "a", "How to upload?", "Answer A", source_ref="chunk:0"
                )
            ],
            "unit:1": [
                _surface_finding(
                    "b", "How to upload?", "Answer B", source_ref="chunk:1"
                )
            ],
        }
    )
    compiler = GroqKnowledgeSurfaceCompiler(client=cast(AsyncGroq, fake), model="test")

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0), _unit(1)),
        file_name="faq.md",
        run_id="run-dupe-question",
    )

    assert len(result.graph.surfaces) == 1
    assert result.graph.surfaces[0].source_refs == ("chunk:0", "chunk:1")


@pytest.mark.asyncio
async def test_duplicate_short_answer_and_answer_core_merges_evidence() -> None:
    fake = _ScriptedRegistryMergeGroq(
        findings_by_key={
            "unit:0": [
                _surface_finding(
                    "a",
                    "Question A?",
                    "Same answer core.",
                    short_answer="Same short.",
                    source_ref="chunk:0",
                )
            ],
            "unit:1": [
                _surface_finding(
                    "b",
                    "Question B?",
                    "Same answer core.",
                    short_answer="Same short.",
                    source_ref="chunk:1",
                )
            ],
        }
    )
    compiler = GroqKnowledgeSurfaceCompiler(client=cast(AsyncGroq, fake), model="test")

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0), _unit(1)),
        file_name="faq.md",
        run_id="run-dupe-answer",
    )

    assert len(result.graph.surfaces) == 1
    assert result.graph.surfaces[0].source_refs == ("chunk:0", "chunk:1")
    assert result.graph.surfaces[0].source_chunk_indexes == (0, 1)


@pytest.mark.asyncio
async def test_registry_updates_add_evidence_without_new_surface() -> None:
    fake = _ScriptedRegistryMergeGroq(
        findings_by_key={
            "unit:0": [
                _surface_finding(
                    "a", "How to pay?", "Pay by card.", source_ref="chunk:0"
                )
            ],
            "unit:1": [
                _surface_finding(
                    "b",
                    "Payment evidence",
                    "Cards are supported.",
                    source_ref="chunk:1",
                )
            ],
        },
        registry_updates_by_key={
            "unit:1": [
                {
                    "operation": "add_evidence",
                    "target_surface_key": "a",
                    "source_local_surface_key": "b",
                    "append_evidence_quotes": ["Cards are supported."],
                    "append_source_refs": ["chunk:1"],
                    "append_source_chunk_indexes": [1],
                }
            ]
        },
    )
    compiler = GroqKnowledgeSurfaceCompiler(client=cast(AsyncGroq, fake), model="test")

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0), _unit(1)),
        file_name="faq.md",
        run_id="run-add-evidence",
    )

    assert len(result.graph.surfaces) == 2
    target = next(
        item for item in result.graph.surfaces if item.local_surface_key == "a"
    )
    assert "chunk:1" in target.source_refs
    assert "Cards are supported." in target.metadata["evidence_quotes"]


@pytest.mark.asyncio
async def test_umbrella_and_child_stay_separate_with_relation() -> None:
    fake = _ScriptedRegistryMergeGroq(
        findings_by_key={
            "unit:0": [
                _surface_finding(
                    "parent",
                    "How does billing work?",
                    "Billing overview.",
                    surface_kind="umbrella",
                    children=["child"],
                    source_ref="chunk:0",
                ),
                _surface_finding(
                    "child",
                    "How do card payments work?",
                    "Card payments details.",
                    surface_kind="child",
                    parent="parent",
                    source_ref="chunk:0",
                ),
            ]
        }
    )
    compiler = GroqKnowledgeSurfaceCompiler(client=cast(AsyncGroq, fake), model="test")

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0),),
        file_name="faq.md",
        run_id="run-parent-child",
    )

    assert {surface.local_surface_key for surface in result.graph.surfaces} == {
        "parent",
        "child",
    }
    assert any(
        relation.parent_surface_key == "parent"
        and relation.child_surface_key == "child"
        and relation.relation_type == "umbrella_contains"
        for relation in result.graph.relations
    )


@pytest.mark.asyncio
async def test_registry_updates_extend_is_parsed_and_applied() -> None:
    fake = _ScriptedRegistryMergeGroq(
        findings_by_key={
            "unit:0": [
                _surface_finding(
                    "a", "How to invite?", "Invite by link.", source_ref="chunk:0"
                )
            ],
            "unit:1": [
                _surface_finding(
                    "b", "Invite managers", "Email invites exist.", source_ref="chunk:1"
                )
            ],
        },
        registry_updates_by_key={
            "unit:1": [
                {
                    "operation": "extend",
                    "target_surface_key": "a",
                    "source_local_surface_key": "b",
                    "append_answer_delta": "You can also invite by email.",
                    "append_variants": ["Can I invite by email?"],
                    "append_source_refs": ["chunk:1"],
                    "append_source_chunk_indexes": [1],
                    "append_evidence_quotes": ["Email invites exist."],
                }
            ]
        },
    )
    compiler = GroqKnowledgeSurfaceCompiler(client=cast(AsyncGroq, fake), model="test")

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0), _unit(1)),
        file_name="faq.md",
        run_id="run-registry-updates",
    )

    target = next(
        item for item in result.graph.surfaces if item.local_surface_key == "a"
    )
    assert "You can also invite by email." in target.answer
    assert "chunk:1" in target.source_refs
    assert any(
        item.question == "Can I invite by email?" for item in result.graph.ownership
    )


@pytest.mark.asyncio
async def test_merge_decisions_compatibility_does_not_override_deterministic_merge() -> (
    None
):
    fake = _ScriptedRegistryMergeGroq(
        findings_by_key={
            "unit:0": [
                _surface_finding(
                    "a", "Same question?", "Answer A", source_ref="chunk:0"
                )
            ],
            "unit:1": [
                _surface_finding(
                    "b", "Same question?", "Answer B", source_ref="chunk:1"
                )
            ],
        },
        merge_decisions_by_key={
            "unit:1": [
                {
                    "source_local_surface_key": "b",
                    "target_surface_key": "nonexistent-wrong-target",
                    "decision": "keep_new",
                }
            ]
        },
    )
    compiler = GroqKnowledgeSurfaceCompiler(client=cast(AsyncGroq, fake), model="test")

    result = await compiler.compile_surfaces(
        mode=MODE_FAQ,
        source_units=(_unit(0), _unit(1)),
        file_name="faq.md",
        run_id="run-compat-safe",
    )

    assert len(result.graph.surfaces) == 1
    assert result.graph.surfaces[0].local_surface_key == "a"
    assert result.graph.surfaces[0].source_refs == ("chunk:0", "chunk:1")
