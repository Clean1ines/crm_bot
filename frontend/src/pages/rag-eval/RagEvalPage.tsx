import React, { useEffect, useMemo, useReducer, useState } from 'react';
import { BarChart3, Loader2, Play, Search, ShieldCheck, XCircle } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@shared/api/core/errors';
import { knowledgeApi } from '@shared/api/modules/knowledge';
import {
  ragEvalApi,
  type RunWorkbenchRagEvalRequest,
  type WorkbenchRagEvalPromotionBatchApplyRequest,
  type WorkbenchRagEvalPromotionCandidateDetails,
  type WorkbenchRagEvalQuestionDetails,
  type WorkbenchRagEvalRetrievalResultDetails,
  type WorkbenchRagEvalEmbeddingRevision,
  type WorkbenchRagEvalRunSummary,
  type WorkbenchRagEvalVerification,
  type WorkbenchRagEvalVerificationMetrics,
  type WorkbenchRagEvalVerificationRoleMetrics,
} from '@shared/api/modules/ragEval';
import { ragEvalQueryKeys } from './ragEvalQueryKeys';
import {
  createInitialRagEvalProjectionState,
  reduceRagEvalFrontendProjectionEvent,
} from './ragEvalFrontendProjectionReducer';
import { RagEvalRetrievalProgress } from './RagEvalRetrievalProgress';
import { acceptStartedRagEvalRun } from './ragEvalRunStart';

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

const isApplyableCandidate = (candidate: WorkbenchRagEvalPromotionCandidateDetails): boolean => (
  candidate.status === 'approved'
);

type RagEvalDocumentOption = {
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

const shortId = (value: string): string => (value.length > 14 ? `${value.slice(0, 14)}…` : value);

const formatScore = (value: number): string => value.toFixed(4);

const hitLabel = (result: WorkbenchRagEvalRetrievalResultDetails): string => {
  if (result.top1_hit) return 'top-1';
  if (result.top3_hit) return 'top-3';
  if (result.top5_hit) return 'top-5';
  return 'miss';
};

const friendlyHitLabel = (result: WorkbenchRagEvalRetrievalResultDetails | null): string => {
  if (!result) return 'Ответ не найден';
  if (result.top1_hit) return 'Точный ответ найден';
  if (result.top3_hit) return 'Ответ найден в топ-3';
  if (result.top5_hit) return 'Ответ найден в топ-5';
  return 'Ответ не найден';
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
  onRetry: () => void;
}> = ({ questions, loading, error, onRetry }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
    <div className="mb-4 flex items-start gap-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--control-bg)] text-[var(--text-secondary)]">
        <Search className="h-5 w-5" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          Проверочные вопросы
        </h2>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          Список вопросов, на которых проверяется опубликованная база знаний.
        </p>
      </div>
    </div>

    {loading && (
      <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
        Загружаю проверочные вопросы…
      </div>
    )}

    {Boolean(error) && !loading && (
      <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-500">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>Не удалось загрузить проверочные вопросы.</span>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-semibold"
          >
            Повторить
          </button>
        </div>
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer font-medium">Технические детали</summary>
          <div className="mt-2 break-words">{getErrorMessage(error, 'unknown error')}</div>
        </details>
      </div>
    )}

    {!loading && !error && questions.length === 0 && (
      <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        Проверка завершилась без вопросов.
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
                    <span>{friendlyHitLabel(best)}</span>
                    <span>{rank === null ? 'ожидаемый факт не найден' : `ожидаемый факт: место ${rank}`}</span>
                  </div>
                </div>
                <div className="grid gap-2 text-xs text-[var(--text-secondary)] sm:grid-cols-3 lg:min-w-[420px]">
                  <div>
                    <div className="text-[var(--text-muted)]">Тип вопроса</div>
                    <div>{question.question_kind}</div>
                  </div>
                  <div>
                    <div className="text-[var(--text-muted)]">Источник</div>
                    <div>{question.source}</div>
                  </div>
                  <div>
                    <div className="text-[var(--text-muted)]">Статус</div>
                    <div>{question.status}</div>
                  </div>
                </div>
              </div>
            </summary>

            <details className="mt-4 rounded-xl border border-[var(--border-primary)] p-3">
              <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
                Технические детали
              </summary>
              <div className="mt-3 grid gap-2 text-xs text-[var(--text-secondary)] sm:grid-cols-3">
                <div>
                  <div className="text-[var(--text-muted)]">Expected runtime entry</div>
                  <div className="break-all font-mono">{question.expected_runtime_entry_id}</div>
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
  selectedPromotionIds: string[];
  bulkApplying: boolean;
  onApply: (candidate: WorkbenchRagEvalPromotionCandidateDetails) => void;
  onToggleSelected: (candidate: WorkbenchRagEvalPromotionCandidateDetails) => void;
  onSelectAllVisible: () => void;
  onApplySelected: () => void;
  onApplyAllForRun: () => void;
  onRetry: () => void;
}> = ({
  candidates,
  loading,
  error,
  applyingPromotionId,
  selectedPromotionIds,
  bulkApplying,
  onApply,
  onToggleSelected,
  onSelectAllVisible,
  onApplySelected,
  onApplyAllForRun,
  onRetry,
}) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
    <h2 className="text-lg font-semibold text-[var(--text-primary)]">
      Вопросы для улучшения поиска
    </h2>
    <p className="mt-1 text-sm text-[var(--text-muted)]">
      Эти вопросы можно добавить к опубликованным фактам, чтобы клиентам было проще найти правильный ответ.
    </p>

    {loading && (
      <div className="mt-4 rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
        Загружаю предложения…
      </div>
    )}

    {Boolean(error) && !loading && (
      <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-500">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>Не удалось загрузить предложения для улучшения поиска.</span>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-semibold"
          >
            Повторить
          </button>
        </div>
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer font-medium">Технические детали</summary>
          <div className="mt-2 break-words">{getErrorMessage(error, 'unknown error')}</div>
        </details>
      </div>
    )}

    {!loading && !error && candidates.length === 0 && (
      <div className="mt-4 rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        Сейчас нет вопросов, которые требуют улучшения поиска.
      </div>
    )}

    {candidates.length > 0 && (
      <div className="mt-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-[var(--control-bg)] p-3 text-sm">
          <button
            type="button"
            onClick={onSelectAllVisible}
            disabled={bulkApplying}
            className="rounded-lg border border-[var(--border-primary)] px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Выбрать все
          </button>
          <button
            type="button"
            onClick={onApplySelected}
            disabled={bulkApplying || selectedPromotionIds.length === 0}
            className="rounded-lg bg-[var(--accent-primary)] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {bulkApplying ? 'Применяю…' : `Применить выбранные (${selectedPromotionIds.length})`}
          </button>
          <button
            type="button"
            onClick={onApplyAllForRun}
            disabled={bulkApplying}
            className="rounded-lg bg-[var(--control-bg-strong)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Применить все
          </button>
          <span className="text-xs text-[var(--text-muted)]">
            Применение добавит вопросы к опубликованным фактам и обновит поиск.
          </span>
        </div>
        <div className="space-y-3">
          {candidates.map((candidate) => (
            <div
              key={candidate.promotion_id}
              className="rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-4"
            >
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <label className="flex min-w-0 items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selectedPromotionIds.includes(candidate.promotion_id)}
                    disabled={!isApplyableCandidate(candidate) || bulkApplying}
                    onChange={() => onToggleSelected(candidate)}
                    aria-label={`Выбрать вопрос ${candidate.question}`}
                    className="mt-1"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-[var(--text-primary)]">
                      {candidate.question}
                    </span>
                    <span className="mt-1 block text-xs text-[var(--text-muted)]">
                      Статус: {candidate.status} · создано {formatDateTime(candidate.created_at)}
                    </span>
                  </span>
                </label>
                <div className="shrink-0">
                  <button
                    type="button"
                    disabled={
                      applyingPromotionId === candidate.promotion_id ||
                      bulkApplying ||
                      !isApplyableCandidate(candidate)
                    }
                    onClick={() => onApply(candidate)}
                    className="rounded-lg bg-[var(--accent-primary)] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {applyingPromotionId === candidate.promotion_id ? 'Применяю…' : 'Применить'}
                  </button>
                </div>
              </div>
              <details className="mt-3 text-xs text-[var(--text-secondary)]">
                <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                  Технические детали
                </summary>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <div>
                    <div className="text-[var(--text-muted)]">promotion_id</div>
                    <div className="break-all font-mono">{candidate.promotion_id}</div>
                  </div>
                  <div>
                    <div className="text-[var(--text-muted)]">target_runtime_entry_id</div>
                    <div className="break-all font-mono">{candidate.target_runtime_entry_id}</div>
                  </div>
                  <div>
                    <div className="text-[var(--text-muted)]">target_fact_id</div>
                    <div className="break-all font-mono">{candidate.target_fact_id}</div>
                  </div>
                </div>
              </details>
            </div>
          ))}
        </div>
      </div>
    )}
  </section>
);

const RevisionPanel: React.FC<{
  revisions: WorkbenchRagEvalEmbeddingRevision[];
  loading: boolean;
  error: unknown;
  acceptingRevisionId: string | null;
  rollingBackRevisionId: string | null;
  onAccept: (revision: WorkbenchRagEvalEmbeddingRevision) => void;
  onRollback: (revision: WorkbenchRagEvalEmbeddingRevision) => void;
  onRetry: () => void;
}> = ({
  revisions,
  loading,
  error,
  acceptingRevisionId,
  rollingBackRevisionId,
  onAccept,
  onRollback,
  onRetry,
}) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
    <h2 className="text-lg font-semibold text-[var(--text-primary)]">
      Ревизии поиска
    </h2>
    <p className="mt-1 text-sm text-[var(--text-muted)]">
      Применённые улучшения проходят проверку перед окончательным принятием.
    </p>

    {loading && (
      <div className="mt-4 rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
        Загружаю ревизии…
      </div>
    )}

    {Boolean(error) && !loading && (
      <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-500">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>Не удалось загрузить ревизии поиска.</span>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-semibold"
          >
            Повторить
          </button>
        </div>
      </div>
    )}

    {!loading && !error && revisions.length === 0 && (
      <div className="mt-4 rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        Ревизий пока нет.
      </div>
    )}

    <div className="mt-4 space-y-3">
      {revisions.map((revision) => {
        const canAccept = revision.available_actions.can_accept;
        const canRollback = revision.available_actions.can_rollback;
        return (
          <div
            key={revision.revision_id}
            className="rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-4"
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  {shortId(revision.revision_id)}
                </div>
                <div className="mt-1 text-xs text-[var(--text-muted)]">
                  Статус: {revision.status} · создано {formatDateTime(revision.created_at)}
                </div>
                <div className="mt-2 text-xs text-[var(--text-secondary)]">
                  Вопросов в ревизии: {formatNumber(revision.promotion_ids.length)}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onAccept(revision)}
                  disabled={!canAccept || acceptingRevisionId === revision.revision_id}
                  className="rounded-lg bg-[var(--accent-primary)] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {acceptingRevisionId === revision.revision_id ? 'Принимаю…' : 'Принять'}
                </button>
                <button
                  type="button"
                  onClick={() => onRollback(revision)}
                  disabled={!canRollback || rollingBackRevisionId === revision.revision_id}
                  className="rounded-lg border border-red-500/40 px-3 py-1.5 text-xs font-semibold text-red-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {rollingBackRevisionId === revision.revision_id ? 'Откатываю…' : 'Откатить'}
                </button>
              </div>
            </div>
            <details className="mt-3 text-xs text-[var(--text-secondary)]">
              <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
                Применённые вопросы
              </summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {revision.new_promoted_questions.map((question) => (
                  <li key={question}>{question}</li>
                ))}
              </ul>
            </details>
          </div>
        );
      })}
    </div>
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

const verificationRoles = [
  ['promoted', 'Promoted'],
  ['holdout', 'Holdout'],
  ['baseline', 'Baseline'],
  ['neighbour', 'Neighbour'],
] satisfies ReadonlyArray<readonly [keyof WorkbenchRagEvalVerificationMetrics, string]>;

const metricNumber = (
  metrics: WorkbenchRagEvalVerificationMetrics | null,
  role: keyof WorkbenchRagEvalVerificationMetrics,
  key: keyof WorkbenchRagEvalVerificationRoleMetrics,
): number | null => {
  const value = metrics?.[role][key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const metricText = (
  metrics: WorkbenchRagEvalVerificationMetrics | null,
  role: keyof WorkbenchRagEvalVerificationMetrics,
  key: keyof WorkbenchRagEvalVerificationRoleMetrics,
  digits = 2,
): string => {
  const value = metricNumber(metrics, role, key);
  return value === null ? '—' : value.toFixed(digits);
};

const rateText = (
  metrics: WorkbenchRagEvalVerificationMetrics | null,
  role: keyof WorkbenchRagEvalVerificationMetrics,
  key: keyof WorkbenchRagEvalVerificationRoleMetrics,
): string => {
  const value = metricNumber(metrics, role, key);
  return value === null ? '—' : `${Math.round(value * 100)}%`;
};

const VerificationMetricsTable: React.FC<{ metrics: WorkbenchRagEvalVerificationMetrics | null }> = ({
  metrics,
}) => {
  if (!metrics) {
    return (
      <div className="mt-3 rounded-lg bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-muted)]">
        Метрики ещё не сохранены.
      </div>
    );
  }

  return (
    <div className="mt-4 overflow-x-auto">
      <table className="min-w-[980px] text-left text-xs">
        <thead className="text-[var(--text-muted)]">
          <tr>
            <th className="py-2 pr-3 font-medium">Срез</th>
            <th className="px-3 py-2 font-medium">Top1 до/после/Δ</th>
            <th className="px-3 py-2 font-medium">Top3 до/после/Δ</th>
            <th className="px-3 py-2 font-medium">Top5 до/после/Δ</th>
            <th className="px-3 py-2 font-medium">Mean rank до/после/Δ</th>
            <th className="px-3 py-2 font-medium">Mean margin до/после/Δ</th>
            <th className="px-3 py-2 font-medium">Miss / confusion</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border-primary)] text-[var(--text-secondary)]">
          {verificationRoles.map(([role, label]) => (
            <tr key={role}>
              <td className="py-2 pr-3 font-medium text-[var(--text-primary)]">
                {label}
              </td>
              <td className="px-3 py-2">
                {rateText(metrics, role, 'before_top1_rate')} / {rateText(metrics, role, 'top1_rate')} / {rateText(metrics, role, 'top1_rate_delta')}
              </td>
              <td className="px-3 py-2">
                {rateText(metrics, role, 'before_top3_rate')} / {rateText(metrics, role, 'top3_rate')} / {rateText(metrics, role, 'top3_rate_delta')}
              </td>
              <td className="px-3 py-2">
                {rateText(metrics, role, 'before_top5_rate')} / {rateText(metrics, role, 'top5_rate')} / {rateText(metrics, role, 'top5_rate_delta')}
              </td>
              <td className="px-3 py-2">
                {metricText(metrics, role, 'before_mean_expected_rank')} / {metricText(metrics, role, 'mean_expected_rank')} / {metricText(metrics, role, 'mean_expected_rank_delta')}
              </td>
              <td className="px-3 py-2">
                {metricText(metrics, role, 'before_mean_score_margin')} / {metricText(metrics, role, 'mean_score_margin')} / {metricText(metrics, role, 'mean_score_margin_delta')}
              </td>
              <td className="px-3 py-2">
                {metricText(metrics, role, 'miss_count', 0)} / {metricText(metrics, role, 'confusion_count', 0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const VerificationPanel: React.FC<{
  verifications: WorkbenchRagEvalVerification[];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}> = ({ verifications, loading, error, onRetry }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
    <div className="mb-4 flex items-start gap-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--control-bg)] text-[var(--text-secondary)]">
        <ShieldCheck className="h-5 w-5" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          Проверка после применения
        </h2>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          Сравнение поиска до и после обновления формулировок опубликованных фактов.
        </p>
      </div>
    </div>

    {loading && (
      <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
        Загружаю результаты проверки ревизий…
      </div>
    )}
    {Boolean(error) && !loading && (
      <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-500">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>Не удалось загрузить проверки ревизий.</span>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-semibold"
          >
            Повторить
          </button>
        </div>
      </div>
    )}
    {!loading && !error && verifications.length === 0 && (
      <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
        Применённые ревизии ещё не проверялись.
      </div>
    )}
    <div className="space-y-3">
      {verifications.map((verification) => (
        <div
          key={verification.verification_id}
          className="rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-4"
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="font-mono text-sm text-[var(--text-primary)]">
                {shortId(verification.revision_id)}
              </div>
              <div className="mt-1 text-xs text-[var(--text-muted)]">
                {verification.decision ?? verification.status}
                {verification.failure_reasons.length > 0
                  ? ` · ${verification.failure_reasons.join(', ')}`
                  : ''}
              </div>
            </div>
            <div className="grid gap-2 text-xs text-[var(--text-secondary)] sm:grid-cols-3 lg:min-w-[420px]">
              <div>
                <div className="text-[var(--text-muted)]">Запросы</div>
                <div>{verification.outcome_count} / {verification.query_count}</div>
              </div>
              <div>
                <div className="text-[var(--text-muted)]">Статус</div>
                <div>{verification.status}</div>
              </div>
              <div>
                <div className="text-[var(--text-muted)]">Завершена</div>
                <div>{formatDateTime(verification.completed_at)}</div>
              </div>
	            </div>
	          </div>
	          <VerificationMetricsTable metrics={verification.metrics} />
	        </div>
	      ))}
    </div>
  </section>
);

const SummaryPanel: React.FC<{ run: WorkbenchRagEvalRunSummary | null; loading?: boolean }> = ({
  run,
  loading = false,
}) => {
  if (loading) {
    return (
      <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">
        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
        Загружаю результаты проверки…
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
              Проверка ещё не запускалась
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]">
              Запустите проверку, чтобы увидеть, на какие вопросы база знаний отвечает уверенно,
              а какие стоит добавить к опубликованным фактам.
            </p>
          </div>
        </div>
      </section>
    );
  }

  const completed = run.completed_questions;
  const promptVersion = run.question_generation_prompt_version ?? '—';
  const generationModel = run.question_generation_model ?? '—';
  const hasNoMetrics = run.total_entries === 0
    && run.total_questions === 0
    && run.completed_questions === 0
    && (run.promotion_candidate_count ?? 0) === 0;

  return (
    <section className="space-y-5 rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusClass(run.status)}`}>
              {statusLabel(run.status)}
            </span>
          </div>
          <h2 className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
            Последняя проверка
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]">
            Итоги последнего запуска проверки опубликованной базы знаний.
          </p>
        </div>
        <div className="rounded-2xl bg-[var(--control-bg)] px-4 py-3 text-sm text-[var(--text-secondary)]">
          <div>Создана: {formatDateTime(run.created_at)}</div>
          <div>Завершена: {formatDateTime(run.completed_at)}</div>
        </div>
      </div>

      <RagEvalRetrievalProgress run={run} />

      {run.error_message && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">
          <div className="flex items-center gap-2">
            <XCircle className="h-4 w-4" />
            Проверка завершилась с ошибкой.
          </div>
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer font-medium">Технические детали</summary>
            <div className="mt-2 break-words">{run.error_message}</div>
          </details>
        </div>
      )}

      {hasNoMetrics ? (
        <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-muted)]">
          Пока нет результатов проверки.
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="Проверено фактов" value={formatNumber(run.total_entries)} />
          <MetricCard label="Сгенерировано вопросов" value={formatNumber(run.total_questions)} />
          <MetricCard label="Проверено вопросов" value={formatNumber(run.completed_questions)} />
          <MetricCard
            label="Нужно улучшить"
            value={formatNumber(run.promotion_candidate_count ?? 0)}
            hint="Не применяется автоматически"
          />
          <MetricCard
            label="Точный ответ найден"
            value={formatRate(run.top1_hits, completed)}
            hint={`${formatNumber(run.top1_hits)} / ${formatNumber(completed)}`}
          />
          <MetricCard
            label="Ответ найден в топ-3"
            value={formatRate(run.top3_hits, completed)}
            hint={`${formatNumber(run.top3_hits)} / ${formatNumber(completed)}`}
          />
          <MetricCard
            label="Ответ найден в топ-5"
            value={formatRate(run.top5_hits, completed)}
            hint={`${formatNumber(run.top5_hits)} / ${formatNumber(completed)}`}
          />
          <MetricCard
            label="Не найдено ответов"
            value={formatRate(run.misses, completed)}
            hint={`${formatNumber(run.misses)} / ${formatNumber(completed)}`}
          />
        </div>
      )}

      <details className="rounded-xl border border-[var(--border-primary)] p-3">
        <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
          Технические детали
        </summary>
        <div className="mt-3 grid gap-3 text-xs text-[var(--text-secondary)] lg:grid-cols-2">
          <div className="rounded-xl bg-[var(--control-bg)] p-3">
            <div className="text-[var(--text-muted)]">run_id</div>
            <div className="mt-1 break-all font-mono">{run.run_id}</div>
          </div>
          <div className="rounded-xl bg-[var(--control-bg)] p-3">
            <div className="text-[var(--text-muted)]">publication_id</div>
            <div className="mt-1 break-all font-mono">{run.publication_id ?? '—'}</div>
          </div>
          <div className="rounded-xl bg-[var(--control-bg)] p-3">
            <div className="text-[var(--text-muted)]">Prompt version</div>
            <div className="mt-1 break-all font-mono">{promptVersion}</div>
          </div>
          <div className="rounded-xl bg-[var(--control-bg)] p-3">
            <div className="text-[var(--text-muted)]">Generation model</div>
            <div className="mt-1 break-all font-mono">{generationModel}</div>
          </div>
        </div>
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

  const [selectedSourceDocumentRef, setSelectedSourceDocumentRef] = useState('');
  const [topK, setTopK] = useState(5);
  const [maxEntries, setMaxEntries] = useState(20);
  const [selectedPromotionIds, setSelectedPromotionIds] = useState<string[]>([]);
  const [projectionState, dispatchProjectionEvent] = useReducer(
    reduceRagEvalFrontendProjectionEvent,
    createInitialRagEvalProjectionState(),
  );

  const documentsQuery = useQuery({
    queryKey: ragEvalQueryKeys.documents(projectId),
    queryFn: async (): Promise<RagEvalDocumentOption[]> => {
      if (!projectId) return [];
      const response = await knowledgeApi.list(projectId);
      const rows: Array<Record<string, unknown>> =
        response.data.documents ?? response.data.items ?? [];

      return rows
        .map(toDocumentOption)
        .filter(
          (item: RagEvalDocumentOption | null): item is RagEvalDocumentOption =>
            item !== null,
        )
        .sort(
          (left: RagEvalDocumentOption, right: RagEvalDocumentOption) =>
            left.fileName.localeCompare(right.fileName),
        );
    },
    enabled: Boolean(projectId),
    retry: false,
  });

  const latestQuery = useQuery({
    queryKey: ragEvalQueryKeys.latest(projectId),
    queryFn: async () => {
      if (!projectId) return { run: null };
      return ragEvalApi.latestWorkbench(projectId);
    },
    enabled: Boolean(projectId),
    retry: false,
  });

  const visibleRun = latestQuery.data?.run ?? null;

  const questionsQuery = useQuery({
    queryKey: ragEvalQueryKeys.questions(projectId, visibleRun?.run_id),
    queryFn: async () => {
      if (!projectId || !visibleRun) return { questions: [] };
      return ragEvalApi.listWorkbenchQuestions(projectId, visibleRun.run_id);
    },
    enabled: Boolean(projectId && visibleRun?.run_id),
    retry: false,
  });

  const candidatesQuery = useQuery({
    queryKey: ragEvalQueryKeys.promotionCandidates(projectId, visibleRun?.run_id),
    queryFn: async () => {
      if (!projectId || !visibleRun) return { candidates: [] };
      return ragEvalApi.listWorkbenchPromotionCandidates(projectId, visibleRun.run_id);
    },
    enabled: Boolean(projectId && visibleRun?.run_id),
    retry: false,
  });

  const revisionsQuery = useQuery({
    queryKey: ragEvalQueryKeys.embeddingRevisions(projectId, visibleRun?.run_id),
    queryFn: async () => {
      if (!projectId || !visibleRun) return { revisions: [] };
      return ragEvalApi.listWorkbenchEmbeddingRevisions(projectId, visibleRun.run_id);
    },
    enabled: Boolean(projectId && visibleRun?.run_id),
    retry: false,
  });

  const verificationsQuery = useQuery({
    queryKey: ragEvalQueryKeys.verifications(projectId, visibleRun?.run_id),
    queryFn: async () => {
      if (!projectId || !visibleRun) return { verifications: [] };
      return ragEvalApi.listWorkbenchPostPromotionVerifications(projectId, visibleRun.run_id);
    },
    enabled: Boolean(projectId && visibleRun?.run_id),
    retry: false,
  });

  useEffect(() => {
    if (!projectId || !visibleRun?.run_id) return undefined;
    return knowledgeApi.streamProjectWorkflowEvents(
      projectId,
      visibleRun.run_id,
      { limit: 100 },
      (event) => {
        if (event.project_id !== projectId || event.workflow_run_id !== visibleRun.run_id) {
          return;
        }
        if (!event.projection_type.startsWith('rag_eval_')) {
          return;
        }
        dispatchProjectionEvent(event);
      },
    );
  }, [projectId, visibleRun?.run_id]);

  useEffect(() => {
    if (projectionState.invalidation_keys.length === 0) return;
    for (const key of projectionState.invalidation_keys) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  }, [projectionState.invalidation_keys, queryClient]);

  const validationError = useMemo(() => {
    if (topK < 5) return 'Количество результатов должно быть не меньше 5';
    if (maxEntries < 1 || maxEntries > 50) return 'Количество фактов должно быть от 1 до 50';
    return null;
  }, [topK, maxEntries]);

  const applyPromotionMutation = useMutation({
    mutationFn: async (candidate: WorkbenchRagEvalPromotionCandidateDetails) => {
      if (!projectId) throw new Error('project_id не найден в маршруте');
      return ragEvalApi.applyWorkbenchPromotionCandidate(projectId, candidate.promotion_id);
    },
    onSuccess: async (result) => {
      const revision = result.result.revisions[0];
      toast.success(
        revision
          ? `Изменение сохранено для проверки: ${shortId(revision.revision_id)}`
          : 'Изменение уже ожидает проверки',
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.promotionCandidates(projectId, visibleRun?.run_id) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.questions(projectId, visibleRun?.run_id) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.latest(projectId) }),
      ]);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Не удалось применить предложение'));
    },
  });

  const applyBatchMutation = useMutation({
    mutationFn: async (payload: WorkbenchRagEvalPromotionBatchApplyRequest) => {
      if (!projectId) throw new Error('project_id не найден в маршруте');
      return ragEvalApi.applyWorkbenchPromotionCandidatesBatch(projectId, payload);
    },
    onSuccess: async (response) => {
      setSelectedPromotionIds([]);
      const result = response.result;
      toast.success(
        `Применено: ${result.applied_count}, пропущено: ${result.skipped_count}, обновлено: ${result.embedding_recalculation_count}`,
      );
      if (result.errors.length > 0) {
        toast.error(`Ошибки применения: ${result.errors.length}`);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.promotionCandidates(projectId, visibleRun?.run_id) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.questions(projectId, visibleRun?.run_id) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.latest(projectId) }),
      ]);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Не удалось применить выбранные предложения'));
    },
  });

  const acceptRevisionMutation = useMutation({
    mutationFn: async (revision: WorkbenchRagEvalEmbeddingRevision) => {
      if (!projectId) throw new Error('project_id не найден в маршруте');
      return ragEvalApi.acceptWorkbenchEmbeddingRevision(projectId, revision.revision_id);
    },
    onSuccess: async (response) => {
      toast.success(`Ревизия принята: ${shortId(response.revision.revision_id)}`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.latest(projectId) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.embeddingRevisions(projectId, visibleRun?.run_id) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.embeddingRevision(projectId, response.revision.revision_id) }),
      ]);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Не удалось принять ревизию'));
    },
  });

  const rollbackRevisionMutation = useMutation({
    mutationFn: async (revision: WorkbenchRagEvalEmbeddingRevision) => {
      if (!projectId) throw new Error('project_id не найден в маршруте');
      return ragEvalApi.rollbackWorkbenchEmbeddingRevision(projectId, revision.revision_id);
    },
    onSuccess: async (response) => {
      toast.success(`Ревизия откатана: ${shortId(response.revision.revision_id)}`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.latest(projectId) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.questions(projectId, visibleRun?.run_id) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.promotionCandidates(projectId, visibleRun?.run_id) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.embeddingRevisions(projectId, visibleRun?.run_id) }),
        queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.embeddingRevision(projectId, response.revision.revision_id) }),
      ]);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Не удалось откатить ревизию'));
    },
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error('project_id не найден в маршруте');
      if (validationError) throw new Error(validationError);

      const payload: RunWorkbenchRagEvalRequest = {
        publication_id: null,
        source_document_ref: selectedSourceDocumentRef || null,
        top_k: topK,
        max_entries: maxEntries,
      };

      return ragEvalApi.runWorkbench(projectId, payload);
    },
    onSuccess: async (result) => {
      if (!projectId) return;
      acceptStartedRagEvalRun({
        notifySuccess: toast.success,
        projectId,
        queryClient,
        response: result,
      });
      await queryClient.invalidateQueries({ queryKey: ragEvalQueryKeys.latest(projectId) });
    },
    onError: (error) => {
      const fallback = 'Проверка базы знаний не запустилась';
      const detail = getErrorMessage(error, fallback);
      const message = detail.includes('Question generation')
        ? 'Не удалось сгенерировать проверочные вопросы. Технические детали доступны в логах сервера.'
        : detail;
      toast.error(message);
    },
  });

  const toggleSelectedPromotion = (candidate: WorkbenchRagEvalPromotionCandidateDetails): void => {
    if (!isApplyableCandidate(candidate)) return;
    setSelectedPromotionIds((current: string[]) => (
      current.includes(candidate.promotion_id)
        ? current.filter((id: string) => id !== candidate.promotion_id)
        : [...current, candidate.promotion_id]
    ));
  };

  const selectAllVisiblePromotions = (): void => {
    const visibleIds = (candidatesQuery.data?.candidates ?? [])
      .filter(isApplyableCandidate)
      .map((candidate: WorkbenchRagEvalPromotionCandidateDetails) => candidate.promotion_id);
    setSelectedPromotionIds(visibleIds);
  };

  const applySelectedPromotions = (): void => {
    if (selectedPromotionIds.length === 0) return;
    applyBatchMutation.mutate({
      mode: 'selected',
      promotion_ids: selectedPromotionIds,
    });
  };

  const applyAllPromotionsForRun = (): void => {
    if (!visibleRun) return;
    const confirmed = window.confirm(
      'Применить все предложения для этой проверки? Поиск будет обновлён только для изменённых опубликованных фактов.',
    );
    if (!confirmed) return;
    applyBatchMutation.mutate({
      mode: 'all_candidates_for_run',
      run_id: visibleRun.run_id,
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6 lg:p-8">
      <header>
        <p className="text-sm font-medium text-[var(--accent-primary)]">
          База знаний
        </p>
        <h1 className="mt-2 text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">
          Проверка базы знаний
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-muted)]">
          Проверьте, насколько опубликованная база знаний отвечает на вопросы клиентов,
          и добавьте недостающие формулировки к уже опубликованным фактам.
        </p>
      </header>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-5 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Запустить проверку
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]">
              Система сгенерирует проверочные вопросы и проверит, находятся ли ответы
              в опубликованной базе знаний.
            </p>
          </div>
        </div>

        <details className="rounded-xl border border-[var(--border-primary)] p-3">
          <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
            Дополнительные настройки
          </summary>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
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
                Максимум проверяемых фактов
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
        </details>

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
            {runMutation.isPending ? 'Запускаю…' : 'Запустить проверку'}
          </button>

          <span className="text-sm text-[var(--text-muted)]">
            Результаты появятся ниже после завершения проверки.
          </span>
        </div>
      </section>

      {latestQuery.error && !visibleRun && (
        <section className="rounded-2xl border border-red-500/30 bg-red-500/5 p-5 text-sm text-red-500 shadow-[var(--shadow-card)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>Не удалось загрузить результаты проверки.</span>
            <button
              type="button"
              onClick={() => { void latestQuery.refetch(); }}
              className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-semibold"
            >
              Повторить
            </button>
          </div>
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer font-medium">Технические детали</summary>
            <div className="mt-2 break-words">{getErrorMessage(latestQuery.error, 'unknown error')}</div>
          </details>
        </section>
      )}

      <SummaryPanel run={visibleRun} loading={latestQuery.isLoading && !visibleRun} />

      {visibleRun && (
        <>
          <QuestionsPanel
            questions={questionsQuery.data?.questions ?? []}
            loading={questionsQuery.isLoading}
            error={questionsQuery.error}
            onRetry={() => { void questionsQuery.refetch(); }}
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
            selectedPromotionIds={selectedPromotionIds}
            bulkApplying={applyBatchMutation.isPending}
            onApply={(candidate) => applyPromotionMutation.mutate(candidate)}
            onToggleSelected={toggleSelectedPromotion}
            onSelectAllVisible={selectAllVisiblePromotions}
            onApplySelected={applySelectedPromotions}
            onApplyAllForRun={applyAllPromotionsForRun}
            onRetry={() => { void candidatesQuery.refetch(); }}
          />
          <RevisionPanel
            revisions={revisionsQuery.data?.revisions ?? []}
            loading={revisionsQuery.isLoading}
            error={revisionsQuery.error}
            acceptingRevisionId={
              acceptRevisionMutation.isPending
                ? acceptRevisionMutation.variables?.revision_id ?? null
                : null
            }
            rollingBackRevisionId={
              rollbackRevisionMutation.isPending
                ? rollbackRevisionMutation.variables?.revision_id ?? null
                : null
            }
            onAccept={(revision) => acceptRevisionMutation.mutate(revision)}
            onRollback={(revision) => rollbackRevisionMutation.mutate(revision)}
            onRetry={() => { void revisionsQuery.refetch(); }}
          />
          <VerificationPanel
            verifications={verificationsQuery.data?.verifications ?? []}
            loading={verificationsQuery.isLoading}
            error={verificationsQuery.error}
            onRetry={() => { void verificationsQuery.refetch(); }}
          />
        </>
      )}
    </div>
  );
};
