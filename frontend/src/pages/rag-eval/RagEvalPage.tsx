import React, { useMemo, useState } from 'react';
import { BarChart3, Loader2, Play, Search, ShieldCheck, XCircle } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@shared/api/core/errors';
import {
  ragEvalApi,
  type RunWorkbenchRagEvalRequest,
  type WorkbenchRagEvalPromotionCandidateDetails,
  type WorkbenchRagEvalQuestionDetails,
  type WorkbenchRagEvalRetrievalResultDetails,
  type WorkbenchRagEvalRunSummary,
} from '@shared/api/modules/ragEval';

const formatNumber = (value: number): string => new Intl.NumberFormat().format(value);

const formatDateTime = (value: string | null | undefined): string => {
  if (!value) return '—';
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(parsed));
};

const formatRate = (hits: number, total: number): string => {
  if (total <= 0) return '—';
  return `${Math.round((hits / total) * 100)}%`;
};

const statusLabel = (status: string): string => {
  if (status === 'created') return 'Создан';
  if (status === 'running') return 'Выполняется';
  if (status === 'completed') return 'Завершён';
  if (status === 'failed') return 'Ошибка';
  return status || '—';
};

const statusClass = (status: string): string => {
  if (status === 'completed') return 'bg-emerald-500/10 text-emerald-600';
  if (status === 'failed') return 'bg-red-500/10 text-red-600';
  if (status === 'running' || status === 'created') return 'bg-amber-500/10 text-amber-600';
  return 'bg-[var(--control-bg)] text-[var(--text-secondary)]';
};

const optionalTrimmed = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

const shortId = (value: string): string => (value.length > 14 ? `${value.slice(0, 14)}…` : value);

const formatScore = (value: number): string => value.toFixed(4);

const hitLabel = (result: WorkbenchRagEvalRetrievalResultDetails): string => {
  if (result.top1_hit) return 'top-1';
  if (result.top3_hit) return 'top-3';
  if (result.top5_hit) return 'top-5';
  return 'miss';
};

const expectedRank = (question: WorkbenchRagEvalQuestionDetails): number | null => {
  const expected = question.results.find(
    (result) => result.matched_runtime_entry_id === question.expected_runtime_entry_id,
  );
  return expected?.rank ?? null;
};

const bestMatch = (
  question: WorkbenchRagEvalQuestionDetails,
): WorkbenchRagEvalRetrievalResultDetails | null => question.results[0] ?? null;

const QuestionsPanel: React.FC<{
  questions: WorkbenchRagEvalQuestionDetails[];
  loading: boolean;
  error: unknown;
}> = ({ questions, loading, error }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
    <div className="mb-4 flex items-start gap-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--control-bg)] text-[var(--text-secondary)]">
        <Search className="h-5 w-5" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          Questions & retrieval results
        </h2>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          Read-only: показаны generated/baseline questions и top-k matches. Никакие candidates здесь не применяются.
        </p>
      </div>
    </div>

    {loading && (
      <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
        Загружаю вопросы и retrieval results…
      </div>
    )}

    {Boolean(error) && !loading && (
      <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-500">
        Не удалось загрузить questions: {getErrorMessage(error, 'unknown error')}
      </div>
    )}

    {!loading && !error && questions.length === 0 && (
      <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        Для этого run пока нет сохранённых questions.
      </div>
    )}

    <div className="space-y-3">
      {questions.map((question) => {
        const best = bestMatch(question);
        const rank = expectedRank(question);
        return (
          <details
            key={question.question_id}
            className="rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-4"
          >
            <summary className="cursor-pointer list-none">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-[var(--text-primary)]">
                    {question.question}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
                    <span>{question.question_kind}</span>
                    <span>source: {question.source}</span>
                    <span>status: {question.status}</span>
                  </div>
                </div>
                <div className="grid gap-2 text-xs text-[var(--text-secondary)] sm:grid-cols-3 lg:min-w-[420px]">
                  <div>
                    <div className="text-[var(--text-muted)]">Expected</div>
                    <div className="font-mono">{shortId(question.expected_runtime_entry_id)}</div>
                  </div>
                  <div>
                    <div className="text-[var(--text-muted)]">Expected rank</div>
                    <div>{rank === null ? 'not in top-k' : rank}</div>
                  </div>
                  <div>
                    <div className="text-[var(--text-muted)]">Best match</div>
                    <div>{best ? `${shortId(best.matched_runtime_entry_id)} · ${hitLabel(best)}` : '—'}</div>
                  </div>
                </div>
              </div>
            </summary>

            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-xs">
                <thead className="text-[var(--text-muted)]">
                  <tr>
                    <th className="px-2 py-2">Rank</th>
                    <th className="px-2 py-2">Matched runtime entry</th>
                    <th className="px-2 py-2">Matched fact</th>
                    <th className="px-2 py-2">Score</th>
                    <th className="px-2 py-2">Hit flags</th>
                  </tr>
                </thead>
                <tbody>
                  {question.results.map((result) => (
                    <tr key={result.result_id} className="border-t border-[var(--border-primary)]">
                      <td className="px-2 py-2">{result.rank}</td>
                      <td className="px-2 py-2 font-mono">{result.matched_runtime_entry_id}</td>
                      <td className="px-2 py-2 font-mono">{result.matched_fact_id}</td>
                      <td className="px-2 py-2">{formatScore(result.score)}</td>
                      <td className="px-2 py-2">
                        top1={String(result.top1_hit)} · top3={String(result.top3_hit)} · top5={String(result.top5_hit)}
                      </td>
                    </tr>
                  ))}
                  {question.results.length === 0 && (
                    <tr>
                      <td className="px-2 py-3 text-[var(--text-muted)]" colSpan={5}>
                        Нет top-k matches для этого вопроса.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </details>
        );
      })}
    </div>
  </section>
);

const CandidatesPanel: React.FC<{
  candidates: WorkbenchRagEvalPromotionCandidateDetails[];
  loading: boolean;
  error: unknown;
  applyingPromotionId: string | null;
  onApply: (candidate: WorkbenchRagEvalPromotionCandidateDetails) => void;
}> = ({ candidates, loading, error, applyingPromotionId, onApply }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
    <h2 className="text-lg font-semibold text-[var(--text-primary)]">
      Promotion candidates
    </h2>
    <p className="mt-1 text-sm text-[var(--text-muted)]">
      Candidates пока не применяются автоматически. Apply/promote + embedding recalculation будут следующим patch.
    </p>

    {loading && (
      <div className="mt-4 rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
        Загружаю candidates…
      </div>
    )}

    {Boolean(error) && !loading && (
      <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-500">
        Не удалось загрузить candidates: {getErrorMessage(error, 'unknown error')}
      </div>
    )}

    {!loading && !error && candidates.length === 0 && (
      <div className="mt-4 rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        Candidate questions для этого run не созданы.
      </div>
    )}

    {candidates.length > 0 && (
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="text-[var(--text-muted)]">
            <tr>
              <th className="px-2 py-2">Question</th>
              <th className="px-2 py-2">Target runtime entry</th>
              <th className="px-2 py-2">Target fact</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2">Created</th>
              <th className="px-2 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((candidate) => (
              <tr key={candidate.promotion_id} className="border-t border-[var(--border-primary)]">
                <td className="max-w-xl px-2 py-2 text-[var(--text-primary)]">{candidate.question}</td>
                <td className="px-2 py-2 font-mono">{candidate.target_runtime_entry_id}</td>
                <td className="px-2 py-2 font-mono">{candidate.target_fact_id}</td>
                <td className="px-2 py-2">{candidate.status}</td>
                <td className="px-2 py-2">{formatDateTime(candidate.created_at)}</td>
                <td className="px-2 py-2">
                  <button
                    type="button"
                    disabled={
                      applyingPromotionId === candidate.promotion_id ||
                      !(candidate.status === 'candidate' || candidate.status === 'accepted')
                    }
                    onClick={() => onApply(candidate)}
                    className="rounded-lg bg-[var(--accent-primary)] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {applyingPromotionId === candidate.promotion_id ? 'Applying…' : 'Apply'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </section>
);

const MetricCard: React.FC<{ label: string; value: string | number; hint?: string }> = ({
  label,
  value,
  hint,
}) => (
  <div className="rounded-2xl bg-[var(--control-bg)] p-4">
    <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
    <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{value}</div>
    {hint && <div className="mt-1 text-xs text-[var(--text-muted)]">{hint}</div>}
  </div>
);

const SummaryPanel: React.FC<{ run: WorkbenchRagEvalRunSummary | null; loading?: boolean }> = ({
  run,
  loading = false,
}) => {
  if (loading) {
    return (
      <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
        Загружаю последний Workbench RAG Eval run…
      </section>
    );
  }

  if (!run) {
    return (
      <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--control-bg)] text-[var(--text-muted)]">
            <BarChart3 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Workbench RAG Eval ещё не запускался
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]">
              Backend уже умеет запускать retrieval-only проверку published compacted claims.
              После запуска здесь появится summary без таблицы вопросов/results: details endpoints будут отдельным patch.
            </p>
          </div>
        </div>
      </section>
    );
  }

  const completed = run.completed_questions;
  const promptVersion = run.question_generation_prompt_version ?? '—';
  const generationModel = run.question_generation_model ?? '—';

  return (
    <section className="space-y-5 rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusClass(run.status)}`}>
              {statusLabel(run.status)}
            </span>
            <span className="rounded-full bg-[var(--control-bg)] px-3 py-1 text-xs font-semibold text-[var(--text-secondary)]">
              run: {run.run_id.slice(0, 12)}
            </span>
          </div>
          <h2 className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
            Последний Workbench RAG Eval
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]">
            Summary-only: backend пока отдаёт агрегированные метрики, без списка questions/results/promotions.
          </p>
        </div>
        <div className="rounded-2xl bg-[var(--control-bg)] px-4 py-3 text-sm text-[var(--text-secondary)]">
          <div>Created: {formatDateTime(run.created_at)}</div>
          <div>Completed: {formatDateTime(run.completed_at)}</div>
        </div>
      </div>

      {run.error_message && (
        <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">
          <XCircle className="h-4 w-4" />
          {run.error_message}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Entries" value={formatNumber(run.total_entries)} />
        <MetricCard label="Questions" value={formatNumber(run.total_questions)} />
        <MetricCard label="Checked" value={formatNumber(run.completed_questions)} />
        <MetricCard
          label="Promotion candidates"
          value={formatNumber(run.promotion_candidate_count ?? 0)}
          hint="Не применяются автоматически"
        />
        <MetricCard
          label="Top-1 hit"
          value={formatRate(run.top1_hits, completed)}
          hint={`${formatNumber(run.top1_hits)} / ${formatNumber(completed)}`}
        />
        <MetricCard
          label="Top-3 hit"
          value={formatRate(run.top3_hits, completed)}
          hint={`${formatNumber(run.top3_hits)} / ${formatNumber(completed)}`}
        />
        <MetricCard
          label="Top-5 hit"
          value={formatRate(run.top5_hits, completed)}
          hint={`${formatNumber(run.top5_hits)} / ${formatNumber(completed)}`}
        />
        <MetricCard
          label="Miss rate"
          value={formatRate(run.misses, completed)}
          hint={`${formatNumber(run.misses)} misses`}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl bg-[var(--control-bg)] p-4">
          <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
            Prompt version
          </div>
          <div className="mt-1 break-all text-sm font-medium text-[var(--text-primary)]">
            {promptVersion}
          </div>
        </div>
        <div className="rounded-xl bg-[var(--control-bg)] p-4">
          <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
            Generation model
          </div>
          <div className="mt-1 break-all text-sm font-medium text-[var(--text-primary)]">
            {generationModel}
          </div>
        </div>
      </div>

      <details className="rounded-xl border border-[var(--border-primary)] p-3">
        <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
          Технический JSON summary
        </summary>
        <pre className="mt-3 max-h-[420px] overflow-auto rounded-xl bg-[var(--control-bg)] p-4 text-xs leading-relaxed text-[var(--text-secondary)]">
          {JSON.stringify(run, null, 2)}
        </pre>
      </details>
    </section>
  );
};

export const RagEvalPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const [publicationId, setPublicationId] = useState('');
  const [sourceDocumentRef, setSourceDocumentRef] = useState('');
  const [topK, setTopK] = useState(5);
  const [maxEntries, setMaxEntries] = useState(20);
  const [lastRun, setLastRun] = useState<WorkbenchRagEvalRunSummary | null>(null);

  const latestQuery = useQuery({
    queryKey: ['workbench-rag-eval-latest', projectId],
    queryFn: async () => {
      if (!projectId) return { run: null };
      return ragEvalApi.latestWorkbench(projectId);
    },
    enabled: Boolean(projectId),
    retry: false,
  });

  const visibleRun = lastRun ?? latestQuery.data?.run ?? null;

  const questionsQuery = useQuery({
    queryKey: ['workbench-rag-eval-questions', projectId, visibleRun?.run_id],
    queryFn: async () => {
      if (!projectId || !visibleRun) return { questions: [] };
      return ragEvalApi.listWorkbenchQuestions(projectId, visibleRun.run_id);
    },
    enabled: Boolean(projectId && visibleRun?.run_id),
    retry: false,
  });

  const candidatesQuery = useQuery({
    queryKey: ['workbench-rag-eval-promotion-candidates', projectId, visibleRun?.run_id],
    queryFn: async () => {
      if (!projectId || !visibleRun) return { candidates: [] };
      return ragEvalApi.listWorkbenchPromotionCandidates(projectId, visibleRun.run_id);
    },
    enabled: Boolean(projectId && visibleRun?.run_id),
    retry: false,
  });

  const validationError = useMemo(() => {
    if (topK < 5) return 'top_k должен быть не меньше 5';
    if (maxEntries < 1 || maxEntries > 50) return 'max_entries должен быть от 1 до 50';
    return null;
  }, [topK, maxEntries]);

  const applyPromotionMutation = useMutation({
    mutationFn: async (candidate: WorkbenchRagEvalPromotionCandidateDetails) => {
      if (!projectId) throw new Error('project_id не найден в маршруте');
      return ragEvalApi.applyWorkbenchPromotionCandidate(projectId, candidate.promotion_id);
    },
    onSuccess: async (result) => {
      toast.success(
        `Question added, embeddings recalculated: ${result.result.possible_question_count} possible questions`,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workbench-rag-eval-promotion-candidates', projectId, visibleRun?.run_id] }),
        queryClient.invalidateQueries({ queryKey: ['workbench-rag-eval-questions', projectId, visibleRun?.run_id] }),
        queryClient.invalidateQueries({ queryKey: ['workbench-rag-eval-latest', projectId] }),
      ]);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Promotion candidate не применился'));
    },
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error('project_id не найден в маршруте');
      if (validationError) throw new Error(validationError);

      const payload: RunWorkbenchRagEvalRequest = {
        publication_id: optionalTrimmed(publicationId),
        source_document_ref: optionalTrimmed(sourceDocumentRef),
        top_k: topK,
        max_entries: maxEntries,
      };

      return ragEvalApi.runWorkbench(projectId, payload);
    },
    onSuccess: async (result) => {
      setLastRun(result.run);
      toast.success('Workbench RAG Eval завершён');
      await queryClient.invalidateQueries({ queryKey: ['workbench-rag-eval-latest', projectId] });
    },
    onError: (error) => {
      const fallback = 'Workbench RAG Eval не запустился';
      const detail = getErrorMessage(error, fallback);
      const message = detail.includes('Question generation')
        ? `${detail}. Генерация вариантов вопросов не удалась. Проверь LLM runtime/provider limits.`
        : detail;
      toast.error(message);
    },
  });

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6 lg:p-8">
      <header>
        <p className="text-sm font-medium text-[var(--accent-primary)]">
          Старый RAG Eval retired; используется Workbench RAG Eval
        </p>
        <h1 className="mt-2 text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">
          Workbench RAG Eval
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-muted)]">
          Проверяет published compacted claims через новый Workbench runtime retrieval.
          Frontend не вызывает legacy /api/rag-eval, не применяет promotion candidates и не пересчитывает embeddings.
        </p>
      </header>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-5 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Запустить retrieval-only eval
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]">
              Backend сгенерирует question variants через LLM Runtime, затем прогонит каждый вопрос через
              SearchPublishedWorkbenchRuntime без answer service.
            </p>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">
              publication_id optional
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
              source_document_ref optional
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
            <input
              type="number"
              min={5}
              value={topK}
              onChange={(event) => setTopK(Number(event.target.value))}
              className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">
              max_entries
            </span>
            <input
              type="number"
              min={1}
              max={50}
              value={maxEntries}
              onChange={(event) => setMaxEntries(Number(event.target.value))}
              className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
            />
          </label>
        </div>

        {validationError && (
          <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">
            {validationError}
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => runMutation.mutate()}
            disabled={!projectId || Boolean(validationError) || runMutation.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {runMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {runMutation.isPending ? 'Запускаю…' : 'Запустить Workbench RAG Eval'}
          </button>

          <span className="text-sm text-[var(--text-muted)]">
            Apply/promote и embedding recalculation будут отдельным patch.
          </span>
        </div>
      </section>

      {latestQuery.error && !visibleRun && (
        <section className="rounded-2xl border border-red-500/30 bg-red-500/5 p-5 text-sm text-red-500 shadow-[var(--shadow-card)]">
          Не удалось загрузить последний Workbench RAG Eval: {getErrorMessage(latestQuery.error, 'unknown error')}
        </section>
      )}

      <SummaryPanel run={visibleRun} loading={latestQuery.isLoading && !visibleRun} />

      {visibleRun && (
        <>
          <QuestionsPanel
            questions={questionsQuery.data?.questions ?? []}
            loading={questionsQuery.isLoading}
            error={questionsQuery.error}
          />
          <CandidatesPanel
            candidates={candidatesQuery.data?.candidates ?? []}
            loading={candidatesQuery.isLoading}
            error={candidatesQuery.error}
            applyingPromotionId={
              applyPromotionMutation.isPending
                ? applyPromotionMutation.variables?.promotion_id ?? null
                : null
            }
            onApply={(candidate) => applyPromotionMutation.mutate(candidate)}
          />
        </>
      )}
    </div>
  );
};
