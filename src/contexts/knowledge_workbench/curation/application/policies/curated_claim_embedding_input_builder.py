from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationWorkspaceItem,
)


@dataclass(frozen=True, slots=True)
class CuratedClaimEmbeddingInput:
    item_ref: str
    text: str
    text_hash: str

    def __post_init__(self) -> None:
        if not self.item_ref.strip():
            raise ValueError("item_ref must be non-empty")
        if not self.text.strip():
            raise ValueError("text must be non-empty")
        if not self.text_hash.strip():
            raise ValueError("text_hash must be non-empty")


class CuratedClaimEmbeddingInputBuilder:
    def build(
        self,
        items: tuple[DraftClaimCurationWorkspaceItem, ...],
    ) -> tuple[CuratedClaimEmbeddingInput, ...]:
        return tuple(self._input_for_item(item) for item in items)

    def _input_for_item(
        self,
        item: DraftClaimCurationWorkspaceItem,
    ) -> CuratedClaimEmbeddingInput:
        payload = item.editable_payload.to_json_dict()
        text = self._build_text(payload)
        return CuratedClaimEmbeddingInput(
            item_ref=item.item_ref,
            text=text,
            text_hash=sha256(text.encode("utf-8")).hexdigest(),
        )

    def _build_text(self, payload: Mapping[str, object]) -> str:
        lines = [
            "Claim:",
            _text(payload, "claim"),
            "",
            "Possible questions:",
        ]
        questions = _text_list(payload, "possible_questions")
        if questions:
            lines.extend(f"- {question}" for question in questions)
        else:
            lines.append("-")

        exclusion_scope = _optional_text(payload, "exclusion_scope")
        if exclusion_scope:
            lines.extend(["", "Exclusion scope:", exclusion_scope])

        lines.extend(["", "Evidence:", _text(payload, "evidence_block")])

        triples = _object_list(payload, "triples")
        if triples:
            lines.extend(["", "Triples:"])
            lines.extend(_stable_json(item) for item in triples)

        return "\n".join(lines).strip()


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def _optional_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{key} must be text")
    return value.strip()


def _text_list(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError(f"{key} must be list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{key}[{index}] must be text")
        stripped = item.strip()
        if stripped:
            result.append(stripped)
    return tuple(result)


def _object_list(
    payload: Mapping[str, object], key: str
) -> tuple[Mapping[str, object], ...]:
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError(f"{key} must be list")
    result: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TypeError(f"{key}[{index}] must be object")
        result.append(item)
    return tuple(result)


def _stable_json(value: Mapping[str, object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
