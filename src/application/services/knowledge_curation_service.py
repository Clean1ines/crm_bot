from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Protocol

from src.application.errors import ConflictError, NotFoundError, ValidationError
from src.domain.project_plane.knowledge_compilation import (
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
)
from src.domain.project_plane.knowledge_curation import (
    KnowledgeCurationActionType,
    KnowledgeCurationDuplicateGroup,
    KnowledgeCurationEntryView,
    KnowledgeCurationIssue,
    KnowledgeCurationIssueType,
    KnowledgeCurationSummary,
    KnowledgeEntryMergeApplyResult,
    KnowledgeEntryMergeExcludeOptions,
    KnowledgeEntryMergePreview,
    KnowledgeEntryMergeRequest,
    KnowledgeEntryPatch,
    KnowledgeEntryStatusTransition,
    KnowledgeEntryVersionView,
    is_absorbed_merged_entry,
)


class KnowledgeCurationRepositoryPort(Protocol):
    async def get_document_for_curation(
        self, *, project_id: str, document_id: str
    ) -> Mapping[str, object] | None: ...

    async def list_document_canonical_entries(
        self, *, project_id: str, document_id: str
    ) -> tuple[KnowledgeCurationEntryView, ...]: ...

    async def update_entry_status_visibility(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        action_type: str,
        actor_user_id: str,
        expected_version: int | None,
        status: str,
        visibility: str,
        reason: str,
        idempotency_key: str,
    ) -> KnowledgeCurationEntryView: ...

    async def update_entry_content(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        actor_user_id: str,
        patch: KnowledgeEntryPatch,
    ) -> KnowledgeCurationEntryView: ...

    async def rebuild_entry_embedding(
        self, *, action_id: str, project_id: str, document_id: str, target_entry_id: str
    ) -> None: ...

    async def apply_manual_entry_merge(
        self,
        *,
        project_id: str,
        document_id: str,
        actor_user_id: str,
        request: KnowledgeEntryMergeRequest,
        preview: KnowledgeEntryMergePreview,
    ) -> KnowledgeEntryMergeApplyResult: ...

    async def list_knowledge_curation_actions(
        self, *, project_id: str, document_id: str, limit: int
    ) -> tuple[Mapping[str, object], ...]: ...

    async def list_entry_versions(
        self, *, project_id: str, document_id: str, entry_id: str
    ) -> tuple[KnowledgeEntryVersionView, ...]: ...

    async def restore_entry_version(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        version_id: str,
        actor_user_id: str,
        reason: str,
    ) -> KnowledgeCurationEntryView: ...


class KnowledgeCurationQueuePort(Protocol):
    async def enqueue_task(
        self, task_type: str, payload: Mapping[str, object]
    ) -> str: ...


def normalize_curation_text(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").strip().split())


def curation_text_key(value: str) -> str:
    normalized = normalize_curation_text(value)
    return re.sub(r"[^0-9a-zа-я]+", " ", normalized).strip()


def dedupe_text_values(values: Iterable[object]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").strip().split())
        key = curation_text_key(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _json_fingerprint(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _merged_metadata(entry: KnowledgeCurationEntryView) -> Mapping[str, object]:
    curation = entry.metadata.get("curation")
    return curation if isinstance(curation, Mapping) else {}


def _source_ref_key(ref: Mapping[str, object]) -> str:
    chunk = str(ref.get("source_chunk_id") or "")
    index = str(ref.get("source_index") or "")
    quote = curation_text_key(str(ref.get("quote") or ""))
    return f"{chunk}:{index}:{quote}"


def _entry_question_values(entry: KnowledgeCurationEntryView) -> tuple[str, ...]:
    values: list[object] = []
    for key in ("questions", "positive_questions", "paraphrases", "synonyms", "tags"):
        raw = entry.enrichment.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, str | bytes | bytearray):
            values.extend(raw)
    return dedupe_text_values(values)


def classify_curation_issues(
    entry: KnowledgeCurationEntryView,
    *,
    duplicate_title: bool = False,
    duplicate_answer: bool = False,
) -> tuple[KnowledgeCurationIssue, ...]:
    issues: list[KnowledgeCurationIssue] = []
    answer_key = curation_text_key(entry.answer)
    source_ref_count = len(entry.source_refs)
    question_count = len(_entry_question_values(entry))

    if len(answer_key) < 20:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.EMPTY_OR_TOO_SHORT_ANSWER,
                "error",
                "Ответ пустой или слишком короткий",
            )
        )
    if source_ref_count == 0:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.MISSING_SOURCE_REFS,
                "error",
                "Нет source refs",
            )
        )
    if duplicate_title:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.DUPLICATE_TITLE,
                "warning",
                "Повторяющийся заголовок",
            )
        )
    if duplicate_answer:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.DUPLICATE_ANSWER,
                "warning",
                "Повторяющийся ответ",
            )
        )
    if question_count == 0:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.TOO_FEW_QUESTIONS,
                "warning",
                "Нет enrichment questions/synonyms/tags",
            )
        )
    if question_count > 80:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.TOO_MANY_QUESTIONS,
                "warning",
                "Слишком много retrieval-вариантов",
            )
        )
    if entry.entry_kind == KnowledgeEntryKind.FALLBACK_CHUNK:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.FALLBACK_CHUNK,
                "warning",
                "Fallback chunk требует ручной проверки",
            )
        )
    if is_absorbed_merged_entry(entry):
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.MERGED_ABSORBED,
                "info",
                "Entry поглощён merge-действием",
                dict(_merged_metadata(entry)),
            )
        )
    elif entry.status in {
        KnowledgeEntryStatus.HIDDEN,
        KnowledgeEntryStatus.REJECTED,
        KnowledgeEntryStatus.ARCHIVED,
    }:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.NON_RUNTIME_STATUS,
                "info",
                "Entry исключён из runtime retrieval",
            )
        )
    if (
        entry.status == KnowledgeEntryStatus.PUBLISHED
        and entry.visibility == KnowledgeEntryVisibility.RUNTIME
        and not entry.has_retrieval_surface
    ):
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.PUBLISHED_WITHOUT_RETRIEVAL_ROW,
                "error",
                "Published/runtime entry отсутствует в retrieval surface",
            )
        )
    if entry.has_retrieval_surface and (
        entry.status != KnowledgeEntryStatus.PUBLISHED
        or entry.visibility != KnowledgeEntryVisibility.RUNTIME
    ):
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.NON_RUNTIME_WITH_RETRIEVAL_ROW,
                "error",
                "Нерuntime entry всё ещё есть в retrieval surface",
            )
        )
    if entry.status == KnowledgeEntryStatus.PUBLISHED and not entry.has_embedding:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.PUBLISHED_WITHOUT_EMBEDDING,
                "error",
                "Published entry без embedding",
            )
        )
    metadata_errors = entry.metadata.get("errors") or entry.metadata.get("error")
    if metadata_errors:
        issues.append(
            KnowledgeCurationIssue(
                KnowledgeCurationIssueType.METADATA_ERRORS,
                "warning",
                "В metadata есть ошибки",
                {"errors": metadata_errors},
            )
        )
    return tuple(issues)


def build_duplicate_groups(
    entries: Sequence[KnowledgeCurationEntryView],
) -> tuple[KnowledgeCurationDuplicateGroup, ...]:
    groups: list[KnowledgeCurationDuplicateGroup] = []

    def add_exact_groups(
        kind: KnowledgeCurationIssueType, reason: str, pairs: Mapping[str, list[str]]
    ) -> None:
        for key, ids in sorted(pairs.items()):
            unique_ids = tuple(dict.fromkeys(ids))
            if key and len(unique_ids) > 1:
                groups.append(
                    KnowledgeCurationDuplicateGroup(
                        group_id=f"{kind.value}:{hashlib.sha1(key.encode()).hexdigest()[:12]}",
                        reason=reason,
                        issue_type=kind,
                        entry_ids=unique_ids,
                        score=1.0,
                        details={"key": key},
                    )
                )

    by_title: dict[str, list[str]] = {}
    by_answer: dict[str, list[str]] = {}
    by_stable_key: dict[str, list[str]] = {}
    by_source_quote: dict[str, list[str]] = {}
    for entry in entries:
        by_title.setdefault(curation_text_key(entry.title), []).append(entry.id)
        by_answer.setdefault(curation_text_key(entry.answer), []).append(entry.id)
        by_stable_key.setdefault(entry.stable_key.strip(), []).append(entry.id)
        if entry.source_refs:
            first_quote = curation_text_key(
                str(entry.source_refs[0].get("quote") or "")
            )
            by_source_quote.setdefault(first_quote, []).append(entry.id)

    add_exact_groups(
        KnowledgeCurationIssueType.DUPLICATE_TITLE,
        "Одинаковый normalized title",
        by_title,
    )
    add_exact_groups(
        KnowledgeCurationIssueType.DUPLICATE_ANSWER,
        "Одинаковый normalized answer",
        by_answer,
    )
    add_exact_groups(
        KnowledgeCurationIssueType.SAME_STABLE_KEY,
        "Одинаковый stable_key",
        by_stable_key,
    )
    add_exact_groups(
        KnowledgeCurationIssueType.SAME_SOURCE_QUOTE,
        "Одинаковая первая source quote",
        by_source_quote,
    )

    question_sets = {
        entry.id: {curation_text_key(v) for v in _entry_question_values(entry)}
        for entry in entries
    }
    for index, left in enumerate(entries):
        left_values = question_sets[left.id]
        if len(left_values) < 3:
            continue
        matching_ids = [left.id]
        for right in entries[index + 1 :]:
            right_values = question_sets[right.id]
            if len(right_values) < 3:
                continue
            overlap = len(left_values & right_values) / max(
                1, min(len(left_values), len(right_values))
            )
            if overlap >= 0.75:
                matching_ids.append(right.id)
        if len(matching_ids) > 1:
            groups.append(
                KnowledgeCurationDuplicateGroup(
                    group_id=f"enrichment:{left.id}",
                    reason="Высокое пересечение enrichment questions/synonyms/tags",
                    issue_type=KnowledgeCurationIssueType.HIGH_ENRICHMENT_OVERLAP,
                    entry_ids=tuple(matching_ids),
                    score=0.75,
                    details={"parent_candidate_id": left.id},
                )
            )

    return tuple(groups)


class KnowledgeCurationService:
    def __init__(
        self,
        repository: KnowledgeCurationRepositoryPort,
        queue: KnowledgeCurationQueuePort | None = None,
    ) -> None:
        self.repository = repository
        self.queue = queue

    async def load_document_curation_state(
        self, *, project_id: str, document_id: str
    ) -> Mapping[str, object]:
        document = await self.repository.get_document_for_curation(
            project_id=project_id, document_id=document_id
        )
        if document is None:
            raise NotFoundError("Knowledge document not found")
        entries = await self.repository.list_document_canonical_entries(
            project_id=project_id, document_id=document_id
        )
        duplicate_groups = build_duplicate_groups(entries)
        duplicate_title_ids = self._ids_for_issue(
            duplicate_groups, KnowledgeCurationIssueType.DUPLICATE_TITLE
        )
        duplicate_answer_ids = self._ids_for_issue(
            duplicate_groups, KnowledgeCurationIssueType.DUPLICATE_ANSWER
        )
        enriched = tuple(
            replace(
                entry,
                issues=classify_curation_issues(
                    entry,
                    duplicate_title=entry.id in duplicate_title_ids,
                    duplicate_answer=entry.id in duplicate_answer_ids,
                ),
            )
            for entry in entries
        )
        summary = self._summary(document, enriched, duplicate_groups)
        return {
            "ok": True,
            "document": dict(document),
            "summary": summary,
            "entries": enriched,
            "duplicate_groups": duplicate_groups,
        }

    def _ids_for_issue(
        self,
        groups: Sequence[KnowledgeCurationDuplicateGroup],
        issue: KnowledgeCurationIssueType,
    ) -> set[str]:
        result: set[str] = set()
        for group in groups:
            if group.issue_type == issue:
                result.update(group.entry_ids)
        return result

    def _summary(
        self,
        document: Mapping[str, object],
        entries: Sequence[KnowledgeCurationEntryView],
        duplicate_groups: Sequence[KnowledgeCurationDuplicateGroup],
    ) -> KnowledgeCurationSummary:
        active_statuses = {"uploaded", "processing", "pending", "running"}
        processing_stage = str(
            document.get("processing_stage")
            or document.get("preprocessing_status")
            or ""
        )
        document_status = str(document.get("status") or "")
        return KnowledgeCurationSummary(
            document_id=str(document.get("id") or ""),
            document_name=str(document.get("file_name") or document.get("name") or ""),
            document_status=document_status,
            processing_stage=processing_stage,
            total_entries=len(entries),
            published_runtime_entries=sum(
                1 for entry in entries if entry.runtime_eligible
            ),
            needs_review_entries=sum(
                1
                for entry in entries
                if entry.status == KnowledgeEntryStatus.NEEDS_REVIEW
            ),
            hidden_entries=sum(
                1 for entry in entries if entry.status == KnowledgeEntryStatus.HIDDEN
            ),
            rejected_entries=sum(
                1 for entry in entries if entry.status == KnowledgeEntryStatus.REJECTED
            ),
            merged_entries=sum(
                1 for entry in entries if is_absorbed_merged_entry(entry)
            ),
            duplicate_group_count=len(duplicate_groups),
            entries_without_source_refs=sum(
                1 for entry in entries if not entry.source_refs
            ),
            entries_missing_retrieval_surface=sum(
                1
                for entry in entries
                if entry.status == KnowledgeEntryStatus.PUBLISHED
                and entry.visibility == KnowledgeEntryVisibility.RUNTIME
                and not entry.has_retrieval_surface
            ),
            suspicious_entries=sum(1 for entry in entries if entry.issues),
            document_processing_active=document_status in active_statuses
            or processing_stage in active_statuses,
        )

    async def apply_status_transition(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        actor_user_id: str,
        transition: KnowledgeEntryStatusTransition,
    ) -> KnowledgeCurationEntryView:
        status, visibility = self._status_visibility_for_transition(transition)
        return await self.repository.update_entry_status_visibility(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            action_type=transition.action.value,
            actor_user_id=actor_user_id,
            expected_version=transition.expected_version,
            status=status.value,
            visibility=visibility.value,
            reason=transition.reason,
            idempotency_key=transition.idempotency_key,
        )

    def _status_visibility_for_transition(
        self, transition: KnowledgeEntryStatusTransition
    ) -> tuple[KnowledgeEntryStatus, KnowledgeEntryVisibility]:
        if transition.action == KnowledgeCurationActionType.HIDE_ENTRY:
            return KnowledgeEntryStatus.HIDDEN, KnowledgeEntryVisibility.HIDDEN
        if transition.action == KnowledgeCurationActionType.REJECT_ENTRY:
            return KnowledgeEntryStatus.REJECTED, KnowledgeEntryVisibility.HIDDEN
        if transition.action == KnowledgeCurationActionType.RESTORE_ENTRY:
            return (
                transition.target_status or KnowledgeEntryStatus.NEEDS_REVIEW,
                transition.target_visibility or KnowledgeEntryVisibility.OWNER_ONLY,
            )
        if transition.action == KnowledgeCurationActionType.PUBLISH_ENTRY:
            return KnowledgeEntryStatus.PUBLISHED, KnowledgeEntryVisibility.RUNTIME
        if transition.action == KnowledgeCurationActionType.UNPUBLISH_ENTRY:
            return (
                transition.target_status or KnowledgeEntryStatus.NEEDS_REVIEW,
                transition.target_visibility or KnowledgeEntryVisibility.OWNER_ONLY,
            )
        raise ValidationError("Unsupported status transition action")

    async def patch_entry(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        actor_user_id: str,
        patch: KnowledgeEntryPatch,
    ) -> KnowledgeCurationEntryView:
        if patch.title is not None and not patch.title.strip():
            raise ValidationError("title must not be blank")
        if patch.answer is not None and not patch.answer.strip():
            raise ValidationError("answer must not be blank")
        return await self.repository.update_entry_content(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            actor_user_id=actor_user_id,
            patch=patch,
        )

    async def rebuild_embedding(
        self, *, project_id: str, document_id: str, entry_id: str, action_id: str
    ) -> Mapping[str, object]:
        await self.repository.rebuild_entry_embedding(
            action_id=action_id,
            project_id=project_id,
            document_id=document_id,
            target_entry_id=entry_id,
        )
        return {"ok": True, "entry_id": entry_id}

    async def build_merge_preview(
        self, *, project_id: str, document_id: str, request: KnowledgeEntryMergeRequest
    ) -> KnowledgeEntryMergePreview:
        entries = await self.repository.list_document_canonical_entries(
            project_id=project_id, document_id=document_id
        )
        by_id = {entry.id: entry for entry in entries}
        return self._build_merge_preview_from_entries(request=request, by_id=by_id)

    def _build_merge_preview_from_entries(
        self,
        *,
        request: KnowledgeEntryMergeRequest,
        by_id: Mapping[str, KnowledgeCurationEntryView],
    ) -> KnowledgeEntryMergePreview:
        self._validate_merge_shape(request)
        selected_ids = (request.parent_entry_id, *request.absorbed_entry_ids)
        missing = [entry_id for entry_id in selected_ids if entry_id not in by_id]
        if missing:
            raise NotFoundError("Knowledge entries not found")
        parent = by_id[request.parent_entry_id]
        absorbed = tuple(by_id[entry_id] for entry_id in request.absorbed_entry_ids)
        blocking: list[str] = []
        warnings: list[str] = []
        if parent.status in {
            KnowledgeEntryStatus.REJECTED,
            KnowledgeEntryStatus.ARCHIVED,
            KnowledgeEntryStatus.MERGED,
        }:
            blocking.append("parent_not_mergeable")
        if is_absorbed_merged_entry(parent):
            blocking.append("parent_already_absorbed")
        for entry in absorbed:
            if is_absorbed_merged_entry(entry):
                blocking.append(f"absorbed_already_merged:{entry.id}")
        if (
            request.parent_expected_version is not None
            and parent.version != request.parent_expected_version
        ):
            blocking.append("parent_version_conflict")
        for entry in absorbed:
            expected = request.absorbed_expected_versions.get(entry.id)
            if expected is not None and expected != entry.version:
                blocking.append(f"absorbed_version_conflict:{entry.id}")
        proposed = self._proposed_parent_after(parent, absorbed, request)
        source_refs = proposed.get("source_refs")
        if (
            parent.status == KnowledgeEntryStatus.PUBLISHED
            and parent.visibility == KnowledgeEntryVisibility.RUNTIME
            and isinstance(source_refs, tuple)
            and not source_refs
        ):
            blocking.append("published_parent_requires_source_refs")
        if not request.rebuild_embedding:
            warnings.append("embedding_rebuild_not_requested")
        return KnowledgeEntryMergePreview(
            parent_entry_before=parent,
            absorbed_entries_before=absorbed,
            proposed_entry_after=proposed,
            absorbed_entries_after=tuple(
                {
                    "id": entry.id,
                    "status": KnowledgeEntryStatus.MERGED.value,
                    "visibility": KnowledgeEntryVisibility.HIDDEN.value,
                    "merged_into": parent.id,
                }
                for entry in absorbed
            ),
            included_counts=self._included_counts(parent, absorbed, request),
            excluded_counts={
                "source_refs": 0,
                "questions": 0,
                "synonyms": 0,
                "tags": 0,
                "metadata": len(request.exclude.metadata_keys),
            },
            warnings=tuple(dict.fromkeys(warnings)),
            blocking_errors=tuple(dict.fromkeys(blocking)),
        )

    def _validate_merge_shape(self, request: KnowledgeEntryMergeRequest) -> None:
        selected = [request.parent_entry_id, *request.absorbed_entry_ids]
        if len(selected) < 2:
            raise ValidationError("Select at least two entries")
        if len(selected) > 12:
            raise ValidationError("Cannot merge more than 12 entries")
        if not request.parent_entry_id.strip():
            raise ValidationError("parent_entry_id is required")
        if request.parent_entry_id in request.absorbed_entry_ids:
            raise ValidationError("parent_entry_id must not be absorbed")
        if len(set(selected)) != len(selected):
            raise ValidationError("Duplicate entry ids are not allowed")
        if len(request.merge_instruction) > 2000:
            raise ValidationError("merge_instruction is too long")
        if request.final_title is not None and not (
            1 <= len(request.final_title.strip()) <= 300
        ):
            raise ValidationError("final_title length must be 1..300")
        if request.final_answer is not None and not (
            1 <= len(request.final_answer.strip()) <= 8000
        ):
            raise ValidationError("final_answer length must be 1..8000")

    def _proposed_parent_after(
        self,
        parent: KnowledgeCurationEntryView,
        absorbed: Sequence[KnowledgeCurationEntryView],
        request: KnowledgeEntryMergeRequest,
    ) -> Mapping[str, object]:
        all_entries = (parent, *absorbed)
        enrichment: dict[str, object] = dict(parent.enrichment)
        for key in (
            "questions",
            "paraphrases",
            "synonyms",
            "typo_queries",
            "colloquial_queries",
            "tags",
            "retrieval_guards",
        ):
            include_value = bool(getattr(request.include, key))
            if not include_value:
                continue
            values: list[object] = []
            for entry in all_entries:
                raw = entry.enrichment.get(key)
                if isinstance(raw, Sequence) and not isinstance(
                    raw, str | bytes | bytearray
                ):
                    values.extend(raw)
            excluded = self._excluded_values_for_key(key, request.exclude)
            enrichment[key] = [
                value
                for value in dedupe_text_values(values)
                if curation_text_key(value) not in excluded
            ]
        source_refs: tuple[Mapping[str, object], ...] = parent.source_refs
        if request.include.source_refs:
            ref_by_key: dict[str, Mapping[str, object]] = {}
            excluded_ref_keys = set(request.exclude.source_ref_keys)
            for entry in all_entries:
                for ref in entry.source_refs:
                    key = _source_ref_key(ref)
                    if key and key not in excluded_ref_keys and key not in ref_by_key:
                        ref_by_key[key] = ref
            source_refs = tuple(ref_by_key.values())
        metadata: dict[str, object] = dict(parent.metadata)
        if request.include.metadata:
            curation = metadata.get("curation")
            curation_payload = dict(curation) if isinstance(curation, Mapping) else {}
            curation_payload["absorbed_entry_ids"] = [entry.id for entry in absorbed]
            curation_payload["last_manual_merge_instruction"] = (
                request.merge_instruction
            )
            metadata["curation"] = curation_payload
        for key in request.exclude.metadata_keys:
            metadata.pop(key, None)
        answer = request.final_answer.strip() if request.final_answer else parent.answer
        if request.include.answers and not request.final_answer:
            absorbed_answers = [
                entry.answer
                for entry in absorbed
                if curation_text_key(entry.answer) != curation_text_key(parent.answer)
            ]
            if absorbed_answers:
                answer = parent.answer.rstrip() + "\n\n" + "\n\n".join(absorbed_answers)
        return {
            "id": parent.id,
            "title": request.final_title.strip()
            if request.final_title
            else parent.title,
            "answer": answer,
            "status": parent.status.value,
            "visibility": parent.visibility.value,
            "entry_kind": parent.entry_kind.value,
            "version": parent.version + 1,
            "enrichment": enrichment,
            "source_refs": source_refs,
            "metadata": metadata,
        }

    def _excluded_values_for_key(
        self, key: str, exclude: KnowledgeEntryMergeExcludeOptions
    ) -> set[str]:
        if key in {"questions", "paraphrases", "typo_queries", "colloquial_queries"}:
            return {curation_text_key(value) for value in exclude.question_values}
        if key == "synonyms":
            return {curation_text_key(value) for value in exclude.synonym_values}
        if key == "tags":
            return {curation_text_key(value) for value in exclude.tag_values}
        return set()

    def _included_counts(
        self,
        parent: KnowledgeCurationEntryView,
        absorbed: Sequence[KnowledgeCurationEntryView],
        request: KnowledgeEntryMergeRequest,
    ) -> Mapping[str, int]:
        proposed = self._proposed_parent_after(parent, absorbed, request)
        enrichment = proposed.get("enrichment")
        refs = proposed.get("source_refs")
        return {
            "source_refs": len(refs) if isinstance(refs, tuple) else 0,
            "questions": len(enrichment.get("questions", ()))
            if isinstance(enrichment, Mapping)
            else 0,
            "synonyms": len(enrichment.get("synonyms", ()))
            if isinstance(enrichment, Mapping)
            else 0,
            "tags": len(enrichment.get("tags", ()))
            if isinstance(enrichment, Mapping)
            else 0,
        }

    async def apply_merge(
        self,
        *,
        project_id: str,
        document_id: str,
        actor_user_id: str,
        request: KnowledgeEntryMergeRequest,
    ) -> KnowledgeEntryMergeApplyResult:
        preview = await self.build_merge_preview(
            project_id=project_id, document_id=document_id, request=request
        )
        if preview.blocking_errors:
            raise ConflictError(
                "Merge preview has blocking errors: "
                + ", ".join(preview.blocking_errors)
            )
        return await self.repository.apply_manual_entry_merge(
            project_id=project_id,
            document_id=document_id,
            actor_user_id=actor_user_id,
            request=request,
            preview=preview,
        )

    async def enqueue_rerun_eval_if_requested(
        self, *, project_id: str, document_id: str, actor_user_id: str, enabled: bool
    ) -> str | None:
        if not enabled or self.queue is None:
            return None
        return await self.queue.enqueue_task(
            "run_full_rag_eval",
            {
                "project_id": project_id,
                "document_id": document_id,
                "requested_by": actor_user_id,
                "source": "knowledge_curation_console",
            },
        )

    async def list_actions(
        self, *, project_id: str, document_id: str, limit: int = 100
    ) -> tuple[Mapping[str, object], ...]:
        return await self.repository.list_knowledge_curation_actions(
            project_id=project_id, document_id=document_id, limit=limit
        )

    async def list_versions(
        self, *, project_id: str, document_id: str, entry_id: str
    ) -> tuple[KnowledgeEntryVersionView, ...]:
        return await self.repository.list_entry_versions(
            project_id=project_id, document_id=document_id, entry_id=entry_id
        )

    async def restore_version(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        version_id: str,
        actor_user_id: str,
        reason: str,
    ) -> KnowledgeCurationEntryView:
        return await self.repository.restore_entry_version(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            version_id=version_id,
            actor_user_id=actor_user_id,
            reason=reason,
        )


def curation_payload_fingerprint(payload: Mapping[str, object]) -> str:
    return _json_fingerprint(payload)
