#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$PWD}"
cd "$ROOT"

EXPECTED_BRANCH="rescue/0d59-projection-cutover"
EXPECTED_HEAD="7b9440f015101df85608f7836ab77bc6054b2dd5"

branch="$(git branch --show-current)"
head="$(git rev-parse HEAD)"

[[ "$branch" == "$EXPECTED_BRANCH" ]] || {
  echo "ERROR: expected branch $EXPECTED_BRANCH, got $branch" >&2
  exit 1
}

[[ "$head" == "$EXPECTED_HEAD" ]] || {
  echo "ERROR: expected HEAD $EXPECTED_HEAD, got $head" >&2
  echo "Repository changed after reconnaissance; aborting." >&2
  exit 1
}

python3 - <<'PY'
from pathlib import Path

root = Path.cwd()

def replace_exact(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(
            f"{path}: expected verified block {expected} time(s), found {count}; aborting"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"updated {path}")

knowledge_page = root / "frontend/src/pages/knowledge/KnowledgePage.tsx"
rag_page = root / "frontend/src/pages/rag-eval/RagEvalPage.tsx"
use_case = root / "src/contexts/knowledge_workbench/rag_eval/application/use_cases/run_workbench_rag_eval.py"
http = root / "src/interfaces/http/knowledge.py"
use_case_test = root / "tests/contexts/knowledge_workbench/rag_eval/application/use_cases/test_run_workbench_rag_eval.py"

# ---------------------------------------------------------------------------
# Knowledge page: remove Debug button and fix search-icon positioning.
# ---------------------------------------------------------------------------
replace_exact(
    knowledge_page,
'''  const [isDebugMode, setIsDebugMode] = useState(false);
''',
'''  const isDebugMode = false;
''',
)

replace_exact(
    knowledge_page,
'''          <button
            type="button"
            onClick={() => setIsDebugMode((current) => !current)}
            aria-pressed={isDebugMode}
            title={t("knowledge.debugMode.toggleTitle")}
            className="inline-flex min-h-10 items-center justify-center rounded-lg bg-[var(--surface-secondary)] px-4 py-2 text-sm font-medium text-[var(--text-muted)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg)]"
          >
            {isDebugMode
              ? t("knowledge.debugMode.on")
              : t("knowledge.debugMode.off")}
          </button>
''',
"",
)

replace_exact(
    knowledge_page,
'''          <div ref={searchBoxRef} className="relative">
            <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
              <Search className="h-4 w-4 text-[var(--text-muted)]" />
            </div>
            <input
              type="text"
              placeholder={t("knowledge.search.placeholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setIsSearchFocused(true)}
              className="min-h-10 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--control-bg)] py-2 pl-10 pr-4 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-all placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 lg:w-64"
            />
            {isSearchFocused && searchSuggestions.length > 0 && (
''',
'''          <div ref={searchBoxRef} className="relative">
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
                <Search className="h-4 w-4 text-[var(--text-muted)]" />
              </div>
              <input
                type="text"
                placeholder={t("knowledge.search.placeholder")}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onFocus={() => setIsSearchFocused(true)}
                className="min-h-10 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--control-bg)] py-2 pl-10 pr-4 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-all placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 lg:w-64"
              />
            </div>
            {isSearchFocused && searchSuggestions.length > 0 && (
''',
)

# ---------------------------------------------------------------------------
# RAG eval: user selects by filename; option value is canonical document_id.
# ---------------------------------------------------------------------------
replace_exact(
    rag_page,
'''import {
  ragEvalApi,
''',
'''import { knowledgeApi } from '@shared/api/modules/knowledge';
import {
  ragEvalApi,
''',
)

replace_exact(
    rag_page,
'''const optionalTrimmed = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

''',
'''type RagEvalDocumentOption = {
  sourceDocumentRef: string;
  fileName: string;
};

const toDocumentOption = (
  raw: Record<string, unknown>,
): RagEvalDocumentOption | null => {
  const sourceDocumentRef =
    typeof raw.document_id === 'string'
      ? raw.document_id
      : typeof raw.id === 'string'
        ? raw.id
        : null;
  const fileName =
    typeof raw.file_name === 'string'
      ? raw.file_name
      : typeof raw.filename === 'string'
        ? raw.filename
        : null;

  if (!sourceDocumentRef || !fileName) return null;
  return { sourceDocumentRef, fileName };
};

''',
)

replace_exact(
    rag_page,
'''  const [publicationId, setPublicationId] = useState('');
  const [sourceDocumentRef, setSourceDocumentRef] = useState('');
  const [topK, setTopK] = useState(5);
''',
'''  const [selectedSourceDocumentRef, setSelectedSourceDocumentRef] = useState('');
  const [topK, setTopK] = useState(5);
''',
)

replace_exact(
    rag_page,
'''  const latestQuery = useQuery({
''',
'''  const documentsQuery = useQuery({
    queryKey: ['workbench-rag-eval-documents', projectId],
    queryFn: async (): Promise<RagEvalDocumentOption[]> => {
      if (!projectId) return [];
      const response = await knowledgeApi.list(projectId);
      const rows = response.documents ?? response.items ?? [];

      return rows
        .map(toDocumentOption)
        .filter((item): item is RagEvalDocumentOption => item !== null)
        .sort((left, right) => left.fileName.localeCompare(right.fileName));
    },
    enabled: Boolean(projectId),
    retry: false,
  });

  const latestQuery = useQuery({
''',
)

replace_exact(
    rag_page,
'''      const payload: RunWorkbenchRagEvalRequest = {
        publication_id: optionalTrimmed(publicationId),
        source_document_ref: optionalTrimmed(sourceDocumentRef),
        top_k: topK,
        max_entries: maxEntries,
      };
''',
'''      const payload: RunWorkbenchRagEvalRequest = {
        publication_id: null,
        source_document_ref: selectedSourceDocumentRef || null,
        top_k: topK,
        max_entries: maxEntries,
      };
''',
)

replace_exact(
    rag_page,
'''          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">
                publication_id
              </span>
              <input
                value={publicationId}
                onChange={(event) => setPublicationId(event.target.value)}
                placeholder="draft-claim-curation-publication:..."
                className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">
                source_document_ref
              </span>
              <input
                value={sourceDocumentRef}
                onChange={(event) => setSourceDocumentRef(event.target.value)}
                placeholder="source-document:..."
                className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">
                top_k
              </span>
''',
'''          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <label className="block lg:col-span-2">
              <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">
                Что проверять
              </span>
              <select
                value={selectedSourceDocumentRef}
                onChange={(event) => setSelectedSourceDocumentRef(event.target.value)}
                disabled={documentsQuery.isLoading}
                className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none disabled:opacity-60"
              >
                <option value="">Вся опубликованная база знаний</option>
                {(documentsQuery.data ?? []).map((document) => (
                  <option
                    key={document.sourceDocumentRef}
                    value={document.sourceDocumentRef}
                  >
                    {document.fileName}
                  </option>
                ))}
              </select>
              {documentsQuery.error && (
                <div className="mt-2 text-xs text-red-500">
                  Не удалось загрузить список документов.
                </div>
              )}
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">
                Количество результатов поиска
              </span>
''',
)

replace_exact(
    rag_page,
'''              <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">
                max_entries
              </span>
''',
'''              <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">
                Максимум проверяемых фактов
              </span>
''',
)

# ---------------------------------------------------------------------------
# Backend: empty selected scope cannot become completed with zero questions.
# Resolve entries before creating a run to avoid a zombie RUNNING row.
# ---------------------------------------------------------------------------
replace_exact(
    use_case,
'''@dataclass(frozen=True, slots=True)
class RunWorkbenchRagEval:
''',
'''class WorkbenchRagEvalNoPublishedEntriesError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class RunWorkbenchRagEval:
''',
)

replace_exact(
    use_case,
'''        await self.rag_eval_repository.create_run(run=run)

        entries = await self.rag_eval_repository.list_published_entries_for_eval(
            project_id=project_id,
            publication_id=publication_id,
            source_document_ref=source_document_ref,
            limit=max_entries,
        )

        generated_entries = (
''',
'''        entries = await self.rag_eval_repository.list_published_entries_for_eval(
            project_id=project_id,
            publication_id=publication_id,
            source_document_ref=source_document_ref,
            limit=max_entries,
        )
        if not entries:
            raise WorkbenchRagEvalNoPublishedEntriesError(
                "В выбранном документе нет активных опубликованных фактов для проверки."
                if source_document_ref
                else "В опубликованной базе знаний нет активных фактов для проверки."
            )

        await self.rag_eval_repository.create_run(run=run)

        generated_entries = (
''',
)

replace_exact(
    http,
'''from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
''',
'''from src.contexts.knowledge_workbench.rag_eval.application.use_cases.run_workbench_rag_eval import (
    WorkbenchRagEvalNoPublishedEntriesError,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
''',
)

replace_exact(
    http,
'''    except WorkbenchRagEvalQuestionGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
''',
'''    except WorkbenchRagEvalQuestionGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except WorkbenchRagEvalNoPublishedEntriesError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
''',
)

replace_exact(
    use_case_test,
'''from src.contexts.knowledge_workbench.rag_eval.application.use_cases.run_workbench_rag_eval import (
    RunWorkbenchRagEval,
)
''',
'''from src.contexts.knowledge_workbench.rag_eval.application.use_cases.run_workbench_rag_eval import (
    RunWorkbenchRagEval,
    WorkbenchRagEvalNoPublishedEntriesError,
)
''',
)

replace_exact(
    use_case_test,
'''@pytest.mark.asyncio
async def test_run_rejects_top_k_below_five() -> None:
''',
'''@pytest.mark.asyncio
async def test_run_rejects_selected_document_without_published_entries() -> None:
    repository = FakeRepository(entries=())

    with pytest.raises(
        WorkbenchRagEvalNoPublishedEntriesError,
        match="выбранном документе",
    ):
        await RunWorkbenchRagEval(
            rag_eval_repository=repository,
            question_generation_batch_executor=WorkbenchRagEvalQuestionGenerationBatchExecutor(
                question_generator=FakeQuestionGenerator(),
                route_policy=WorkbenchRagEvalQuestionGenerationRoutePolicy.default(),
                max_parallel_jobs=4,
            ),
            search_published_workbench_runtime=FakeSearchPublishedWorkbenchRuntime(),
            question_generation_prompt_version="test-v1",
        ).execute(
            project_id="project-1",
            publication_id=None,
            source_document_ref="source-document-1",
            top_k=5,
            max_entries=20,
            now=_now(),
        )

    assert repository.runs == []
    assert repository.summary is None
    assert repository.questions == ()
    assert repository.results == ()
    assert repository.promotions == ()


@pytest.mark.asyncio
async def test_run_rejects_top_k_below_five() -> None:
''',
)
PY

python3 - <<'PY'
from pathlib import Path

root = Path.cwd()
knowledge = (root / "frontend/src/pages/knowledge/KnowledgePage.tsx").read_text(encoding="utf-8")
rag_page = (root / "frontend/src/pages/rag-eval/RagEvalPage.tsx").read_text(encoding="utf-8")
use_case = (root / "src/contexts/knowledge_workbench/rag_eval/application/use_cases/run_workbench_rag_eval.py").read_text(encoding="utf-8")
http = (root / "src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

assert "setIsDebugMode" not in knowledge
assert 'title={t("knowledge.debugMode.toggleTitle")}' not in knowledge
assert '<div ref={searchBoxRef} className="relative">\n            <div className="relative">' in knowledge

assert "publicationId" not in rag_page
assert "sourceDocumentRef, setSourceDocumentRef" not in rag_page
assert "optionalTrimmed" not in rag_page
assert "knowledgeApi.list(projectId)" in rag_page
assert '<option value="">Вся опубликованная база знаний</option>' in rag_page
assert "value={document.sourceDocumentRef}" in rag_page
assert "source_document_ref: selectedSourceDocumentRef || null" in rag_page

assert "WorkbenchRagEvalNoPublishedEntriesError" in use_case
assert "if not entries:" in use_case
assert use_case.index("if not entries:") < use_case.index(
    "await self.rag_eval_repository.create_run(run=run)"
)
assert "except WorkbenchRagEvalNoPublishedEntriesError" in http

print("structural assertions passed")
PY

python -m pytest -q   tests/contexts/knowledge_workbench/rag_eval/application/use_cases/test_run_workbench_rag_eval.py   tests/interfaces/http/test_workbench_rag_eval.py

cd frontend
npm test -- --run   src/pages/knowledge/KnowledgePage.workflowProjection.test.ts   src/pages/knowledge/components/KnowledgeDocumentCard.test.tsx
npm run build
cd ..

git diff --check

echo
echo "Applied and verified."
echo "Review:"
echo "  git diff -- frontend/src/pages/knowledge/KnowledgePage.tsx \\"
echo "    frontend/src/pages/rag-eval/RagEvalPage.tsx \\"
echo "    src/contexts/knowledge_workbench/rag_eval/application/use_cases/run_workbench_rag_eval.py \\"
echo "    src/interfaces/http/knowledge.py \\"
echo "    tests/contexts/knowledge_workbench/rag_eval/application/use_cases/test_run_workbench_rag_eval.py"