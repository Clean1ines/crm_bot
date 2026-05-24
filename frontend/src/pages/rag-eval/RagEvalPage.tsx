import { t } from '@shared/i18n';
import React, { useMemo, useState } from 'react';
import {
  BarChart3,
  FileText,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
  Square,
  XCircle,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@shared/api/core/errors';

import { knowledgeApi } from '@shared/api/modules/knowledge';
import { knowledgeCurationApi, type KnowledgeCurationAction } from '@shared/api/modules/knowledgeCuration';
import {
  isRagEvalProposedActionType,
  ragEvalApi,
  type KnowledgeEditActionExecutionSummary,
  type RagEvalActionableResult,
  type RagEvalDocumentStatusResponse,
  type RagEvalFullRunAcceptedResponse,
  type RagEvalJob,
  type RagEvalJobProgressResponse,
  type RagEvalJobsResponse,
  type RagEvalProgressPayload,
  type RagEvalProposedActionType,
  type RagEvalResultSummary,
  type RagEvalLatestReviewResponse,
  type RagEvalQuestionReviewState,
  type RagEvalReviewGroup,
  type RagEvalReviewPayload,
  type RagEvalReviewQuestion,
} from '@shared/api/modules/ragEval';
import { KnowledgeCurationConsole } from './components/KnowledgeCurationConsole';

interface Document {
  id: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processing' | 'processed' | 'error';
  chunk_count: number;
  structured_entries?: number;
  structured_chunk_count?: number;
  created_at: string;
}

const ACTIVE_JOB_STATUSES = new Set(['pending', 'processing', 'running', 'retrying', 'running_or_locked']);
const ACTIVE_RUN_STATUSES = new Set(['created', 'pending', 'processing', 'generating', 'ready', 'running', 'paused']);
const ERROR_VISIBLE_JOB_STATUSES = new Set(['failed', 'cancelled']);
const PAUSED_STATUSES = new Set(['paused', 'manual_pause', 'manual-pause']);
const TERMINAL_JOB_STATUSES = new Set(['completed', 'done', 'succeeded', 'success', 'failed', 'cancelled']);

const formatNumber = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);

const formatDurationMs = (durationMs: number): string => {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return t('ragEval.units.hoursMinutes', { hours: String(hours), minutes: String(minutes) });
  if (minutes > 0) return t('ragEval.units.minutesSeconds', { minutes: String(minutes), seconds: String(seconds) });
  return t('ragEval.units.seconds', { seconds: String(seconds) });
};

const timestampMs = (value: unknown): number | null => {
  if (typeof value !== 'string' || !value.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const getRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
);

const asNumber = (value: unknown, fallback = 0): number => (
  typeof value === 'number' && Number.isFinite(value) ? value : fallback
);

const clampPercent = (value: unknown): number => {
  const numeric = asNumber(value, 0);
  return Math.max(0, Math.min(100, Math.round(numeric)));
};

type RagEvalJobWithEffectiveStatus = RagEvalJob & { effective_status?: string };

const getJobStatus = (job: RagEvalJob | null | undefined): string => {
  const jobWithEffectiveStatus = job as RagEvalJobWithEffectiveStatus | null | undefined;
  return String(jobWithEffectiveStatus?.effective_status || jobWithEffectiveStatus?.status || '');
};

const isJobTerminal = (job: RagEvalJob | null | undefined): boolean => (
  Boolean(job && TERMINAL_JOB_STATUSES.has(getJobStatus(job)))
);

const isJobActive = (job: RagEvalJob | null | undefined): boolean => (
  Boolean(job && !isJobTerminal(job) && ACTIVE_JOB_STATUSES.has(getJobStatus(job)))
);

const isJobPaused = (job: RagEvalJob | null | undefined): boolean => (
  Boolean(job && !isJobTerminal(job) && PAUSED_STATUSES.has(getJobStatus(job)))
);

const stageLabel = (stage: string): string => {
  if (stage === 'queued') return t('ragEval.stage.queued');
  if (stage === 'started') return t('ragEval.stage.started');
  if (stage === 'dataset_generation') return t('ragEval.stage.datasetGeneration');
  if (stage === 'retrieval_checks' || stage === 'fragment_review_streaming') return t('ragEval.stage.retrievalChecks');
  if (stage === 'answer_generation') return t('ragEval.stage.answerGeneration');
  if (stage === 'running') return t('ragEval.stage.running');
  if (stage === 'completed' || stage === 'done') return t('ragEval.stage.completed');
  if (stage === 'cancelled') return t('ragEval.stage.cancelled');
  if (stage === 'paused') return t('ragEval.stage.paused');
  if (stage === 'failed') return t('ragEval.stage.failed');
  return stage || t('ragEval.stage.waiting');
};

const statusLabel = (status: string): string => {
  if (status === 'pending') return t('ragEval.status.pending');
  if (status === 'processing' || status === 'running') return t('ragEval.status.running');
  if (status === 'paused') return t('ragEval.stage.paused');
  if (status === 'completed' || status === 'done' || status === 'succeeded' || status === 'success') return t('ragEval.stage.completed');
  if (status === 'cancelled') return t('ragEval.stage.cancelled');
  if (status === 'failed') return t('ragEval.stage.failed');
  return status || t('ragEval.stage.waiting');
};

const progressMessage = (progress: RagEvalProgressPayload, stage: string): string => {
  const rawMessage = typeof progress.message === 'string' ? progress.message : '';
  if (stage === 'dataset_generation') return t('ragEval.stageDescription.datasetGeneration');
  if (stage === 'retrieval_checks' || stage === 'fragment_review_streaming') return t('ragEval.stageDescription.retrievalChecks');
  if (stage === 'answer_generation') return t('ragEval.stageDescription.answerGeneration');
  if (stage === 'paused') return t('ragEval.stageDescription.paused');
  if (stage === 'cancelled') return t('ragEval.stageDescription.cancelled');
  if (stage === 'failed') return getErrorMessage(rawMessage, t('ragEval.stageDescription.failed'));
  if (stage === 'completed' || stage === 'done') return t('ragEval.stageDescription.completed');
  return rawMessage || t('ragEval.stageDescription.running');
};

const ReportJsonBlock: React.FC<{ value: unknown }> = ({ value }) => (
  <pre className="max-h-[520px] overflow-auto rounded-xl bg-[var(--control-bg)] p-4 text-xs leading-relaxed text-[var(--text-secondary)]">
    {JSON.stringify(value ?? null, null, 2)}
  </pre>
);

const parseJsonValue = (value: unknown): unknown => {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (!trimmed) return value;
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return value;
  }
};

const asStringList = (value: unknown): string[] => {
  const parsed = parseJsonValue(value);
  if (Array.isArray(parsed)) {
    return parsed.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof parsed === 'string' && parsed.trim()) return [parsed.trim()];
  return [];
};

const asBoolean = (value: unknown, fallback = false): boolean => (
  typeof value === 'boolean' ? value : fallback
);

const getEvalResults = (value: unknown): RagEvalResultSummary[] => (
  Array.isArray(value) ? value as RagEvalResultSummary[] : []
);

const getActionableResults = (report: Record<string, unknown>): RagEvalActionableResult[] => {
  const parsed = parseJsonValue(report.actionable_results);
  if (!Array.isArray(parsed)) return [];

  return parsed
    .map((raw): RagEvalActionableResult | null => {
      const item = getRecord(raw);
      const resultId = String(item.result_id || '').trim();
      if (!resultId) return null;

      const rawActions = parseJsonValue(item.proposed_actions);
      const proposedActions = Array.isArray(rawActions)
        ? rawActions.map((rawAction) => {
          const action = getRecord(rawAction);
          const actionType = String(action.action_type || '').trim();
          if (!isRagEvalProposedActionType(actionType)) return null;

          const targetEntryId = String(action.target_entry_id || '').trim();

          return {
            action_type: actionType,
            target_entry_id: targetEntryId || null,
            reason: String(action.reason || '').trim(),
            payload: getRecord(action.payload),
          };
        }).filter((action): action is NonNullable<typeof action> => action !== null)
        : [];

      const classification = getRecord(item.classification);

      return {
        result_id: resultId,
        run_id: String(item.run_id || '').trim(),
        question_id: String(item.question_id || '').trim(),
        question: String(item.question || '').trim(),
        question_type: String(item.question_type || '').trim(),
        expected_entry_ids: asStringList(item.expected_entry_ids),
        retrieved_entry_ids: asStringList(item.retrieved_entry_ids),
        score: asNumber(item.score),
        answer_supported: asBoolean(item.answer_supported),
        wrong_entry_top1: asBoolean(item.wrong_entry_top1),
        hallucination_risk: String(item.hallucination_risk || '').trim(),
        should_answer_passed: asBoolean(item.should_answer_passed),
        classification: Object.keys(classification).length ? classification : null,
        proposed_actions: proposedActions,
      };
    })
    .filter((item): item is RagEvalActionableResult => item !== null);
};

const assertNeverActionType = (value: never): never => {
  throw new Error(`Unhandled RAG eval proposed action type: ${value}`);
};

const actionTypeLabel = (value: RagEvalProposedActionType): string => {
  switch (value) {
    case 'attach_question_to_entry':
      return t('ragEval.actionType.attachQuestionToEntry');
    case 'rebuild_embedding':
      return t('ragEval.actionType.rebuildEntryEmbedding');
    case 'rerun_eval':
      return t('ragEval.actionType.rerunEval');
    case 'create_entry_from_failure':
      return t('ragEval.actionType.createEntryFromFailure');
  }

  return assertNeverActionType(value);
};

const actionTypeDescription = (value: RagEvalProposedActionType): string => {
  switch (value) {
    case 'attach_question_to_entry':
      return t('ragEval.actionDescription.attachQuestionToEntry');
    case 'rebuild_embedding':
      return t('ragEval.actionDescription.rebuildEntryEmbedding');
    case 'rerun_eval':
      return t('ragEval.actionDescription.rerunEval');
    case 'create_entry_from_failure':
      return t('ragEval.actionDescription.createEntryFromFailure');
  }

  return assertNeverActionType(value);
};

const formatResultScore = (score: number): string => {
  const normalized = score > 1 ? score : score * 100;
  return `${Math.round(normalized)}%`;
};

const riskLabel = (value: string): string => {
  if (value === 'high') return t('ragEval.risk.high');
  if (value === 'medium') return t('ragEval.risk.medium');
  if (value === 'low') return t('ragEval.risk.low');
  return t('ragEval.risk.unknown');
};

const resultProblemLabel = (result: RagEvalActionableResult): string => {
  if (result.wrong_entry_top1 && !result.answer_supported) {
    return t('ragEval.problem.wrongEntryAndUnsupported');
  }

  if (result.wrong_entry_top1) {
    return t('ragEval.problem.wrongEntryTop1');
  }

  if (!result.answer_supported) {
    return t('ragEval.problem.unsupportedAnswer');
  }

  if (result.hallucination_risk === 'high') {
    return t('ragEval.problem.highHallucinationRisk');
  }

  if (!result.should_answer_passed) {
    return t('ragEval.problem.shouldAnswerFailed');
  }

  return t('ragEval.problem.fallback');
};

const readinessLabel = (value: unknown): string => {
  const readiness = String(value || '').trim();
  if (readiness === 'ready') return t('ragEval.readiness.ready');
  if (readiness === 'needs_review') return t('ragEval.readiness.needsReview');
  if (readiness === 'not_ready') return t('ragEval.readiness.notReady');
  return readiness || t('ragEval.readiness.noStatus');
};

const documentRuntimeEntryCount = (doc: Document | null | undefined): number => {
  if (!doc) return 0;
  if (typeof doc.structured_entries === 'number') return Math.max(0, doc.structured_entries);
  if (typeof doc.structured_chunk_count === 'number') return Math.max(0, doc.structured_chunk_count);
  return 0;
};

const latestAppliedCurationActionTimeMs = (actions: KnowledgeCurationAction[]): number | null => {
  let latest: number | null = null;
  const appliedStatuses = new Set(['applied', 'applied_with_warning']);
  for (const action of actions) {
    if (!appliedStatuses.has(action.status)) continue;
    const timestamp = timestampMs(action.applied_at || action.updated_at || action.created_at);
    if (timestamp === null) continue;
    latest = latest === null ? timestamp : Math.max(latest, timestamp);
  }
  return latest;
};

const reviewRunTimeMs = (review: RagEvalReviewPayload | null): number | null => {
  if (!review) return null;
  const run = getRecord(review.run);
  return timestampMs(run.updated_at) ?? timestampMs(run.created_at);
};

const applyQuestionReviewState = (
  review: RagEvalReviewPayload,
  questionId: string,
  reviewState: RagEvalQuestionReviewState,
): RagEvalReviewPayload => ({
  ...review,
  groups: review.groups.map((group) => ({
    ...group,
    questions: group.questions.map((question) => (
      question.question_id === questionId
        ? { ...question, review: reviewState }
        : question
    )),
  })),
});

const MetricPill: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="rounded-xl bg-[var(--surface-elevated)] px-3 py-2 shadow-[var(--shadow-card)]">
    <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
    <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{value}</div>
  </div>
);

const ReportList: React.FC<{ title: string; items: string[] }> = ({ title, items }) => (
  <div className="rounded-xl bg-[var(--control-bg)] p-4">
    <h4 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h4>
    {items.length ? (
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    ) : (
      <p className="mt-2 text-sm text-[var(--text-muted)]">{t('ragEval.common.noData')}</p>
    )}
  </div>
);

interface ActionableResultsPanelProps {
  results: RagEvalActionableResult[];
  executionSummary: KnowledgeEditActionExecutionSummary | null;
  executingResultId: string | null;
  onExecute: (resultId: string) => void;
}

const ActionableResultsPanel: React.FC<ActionableResultsPanelProps> = ({
  results,
  executionSummary,
  executingResultId,
  onExecute,
}) => {
  if (!results.length) return null;

  return (
    <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
          <RotateCcw className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {t('ragEval.fixes.title')}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]">
            {t('ragEval.fixes.description')}
          </p>
        </div>
      </div>

      {executionSummary && (
        <div className="mb-4 rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-4">
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            {t('ragEval.fixes.lastExecution')}
          </div>
          <div className="mt-2 grid gap-2 text-sm text-[var(--text-secondary)] sm:grid-cols-2 lg:grid-cols-4">
            <div>{t('ragEval.fixes.appliedPrefix')} {formatNumber(executionSummary.applied_actions)}</div>
            <div>{t('ragEval.fixes.skippedPrefix')} {formatNumber(executionSummary.skipped_actions)}</div>
            <div>{t('ragEval.fixes.rejectedPrefix')} {formatNumber(executionSummary.rejected_actions)}</div>
            <div>{t('ragEval.fixes.failedPrefix')} {formatNumber(executionSummary.failed_actions)}</div>
          </div>
          {executionSummary.queued_rerun_job_ids.length > 0 && (
            <p className="mt-2 text-sm text-[var(--text-muted)]">
              {t('ragEval.fixes.rerunStarted')}
            </p>
          )}
        </div>
      )}

      <div className="space-y-3">
        {results.map((result) => {
          const isExecuting = executingResultId === result.result_id;
          const canExecute = result.proposed_actions.length > 0;

          return (
            <article
              key={result.result_id}
              className="rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-4"
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-[var(--surface-elevated)] px-2 py-1 text-xs font-medium text-[var(--text-secondary)]">
                      {t('ragEval.fixes.scorePrefix')} {formatResultScore(result.score)}
                    </span>
                    <span className="rounded-full bg-[var(--surface-elevated)] px-2 py-1 text-xs font-medium text-[var(--text-secondary)]">
                      {riskLabel(result.hallucination_risk)}
                    </span>
                    {result.wrong_entry_top1 && (
                      <span className="rounded-full bg-red-500/10 px-2 py-1 text-xs font-medium text-red-500">
                        {t('ragEval.fixes.wrongSource')}
                      </span>
                    )}
                    {!result.answer_supported && (
                      <span className="rounded-full bg-red-500/10 px-2 py-1 text-xs font-medium text-red-500">
                        {t('ragEval.fixes.unsupportedAnswer')}
                      </span>
                    )}
                  </div>

                  <div>
                    <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
                      {t('ragEval.fixes.questionTitle')}
                    </div>
                    <div className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                      {result.question || t('ragEval.fixes.noQuestion')}
                    </div>
                  </div>

                  <div className="rounded-lg bg-[var(--surface-elevated)] p-3">
                    <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
                      {t('ragEval.fixes.problemTitle')}
                    </div>
                    <p className="mt-1 text-sm text-[var(--text-secondary)]">
                      {resultProblemLabel(result)}
                    </p>
                  </div>

                  <div className="rounded-lg bg-[var(--surface-elevated)] p-3">
                    <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
                      {t('ragEval.fixes.actionTitle')}
                    </div>
                    {result.proposed_actions.length ? (
                      <ul className="mt-2 space-y-3 text-sm text-[var(--text-secondary)]">
                        {result.proposed_actions.map((action, index) => {
                          const payloadQuestion = typeof action.payload.question === 'string'
                            ? action.payload.question.trim()
                            : '';

                          return (
                            <li key={`${result.result_id}-${action.action_type}-${index}`}>
                              <div className="font-medium text-[var(--text-primary)]">
                                {actionTypeLabel(action.action_type)}
                              </div>
                              <p className="mt-1 text-xs leading-relaxed text-[var(--text-muted)]">
                                {actionTypeDescription(action.action_type)}
                              </p>
                              {payloadQuestion && (
                                <div className="mt-2 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-xs text-[var(--text-muted)]">
                                  {t('ragEval.fixes.newQuestionPrefix')} “{payloadQuestion}”
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="mt-2 text-sm text-[var(--text-muted)]">
                        {t('ragEval.fixes.noAutomaticFix')}
                      </p>
                    )}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => onExecute(result.result_id)}
                  disabled={!canExecute || Boolean(executingResultId)}
                  className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isExecuting ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                  {isExecuting ? t('ragEval.fixes.applying') : t('ragEval.fixes.apply')}
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
};

const ReportSummaryCard: React.FC<{ report: Record<string, unknown> }> = ({ report }) => {
  if (!Object.keys(report).length) {
    return <p className="text-sm text-[var(--text-muted)]">{t('ragEval.report.notReady')}</p>;
  }

  const metrics = getRecord(parseJsonValue(report.metrics));
  const score = asNumber(report.score);
  const total = asNumber(metrics.total);
  const top1Rate = asNumber(metrics.top1_rate);
  const top3Rate = asNumber(metrics.top3_rate);
  const top5Rate = asNumber(metrics.top5_rate);
  const answerSupportedRate = asNumber(metrics.answer_supported_rate);
  const highHallucinationRisk = asNumber(metrics.high_hallucination_risk);
  const wrongChunkTop1 = asNumber(metrics.wrong_chunk_top1);
  const strengths = asStringList(report.strengths);
  const problems = asStringList(report.problems);
  const recommendations = asStringList(report.recommendations);

  return (
    <div className="space-y-4 rounded-2xl bg-[var(--control-bg)] p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="text-base font-semibold text-[var(--text-primary)]">{t('ragEval.report.humanTitle')}</h3>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            {t('ragEval.report.humanDescription')}
          </p>
        </div>
        <div className="rounded-xl bg-[var(--surface-elevated)] px-4 py-3 text-right shadow-[var(--shadow-card)]">
          <div className="text-2xl font-semibold text-[var(--text-primary)]">{score}/100</div>
          <div className="text-xs text-[var(--text-muted)]">{readinessLabel(report.readiness)}</div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <MetricPill label={t('ragEval.report.totalQuestions')} value={total || '—'} />
        <MetricPill label={t('ragEval.report.top1')} value={`${top1Rate}%`} />
        <MetricPill label={t('ragEval.report.top3')} value={`${top3Rate}%`} />
        <MetricPill label={t('ragEval.report.top5')} value={`${top5Rate}%`} />
        <MetricPill label={t('ragEval.report.answerSupported')} value={`${answerSupportedRate}%`} />
        <MetricPill label={t('ragEval.report.hallucinationRisk')} value={highHallucinationRisk} />
        <MetricPill label={t('ragEval.report.wrongTop1')} value={wrongChunkTop1} />
      </div>

      <ReportList title={t('ragEval.report.strengths')} items={strengths} />
      <ReportList title={t('ragEval.report.problems')} items={problems} />
      <ReportList title={t('ragEval.report.nextSteps')} items={recommendations} />

      {typeof report.markdown === 'string' && report.markdown.trim() && (
        <details className="rounded-xl bg-[var(--surface-elevated)] p-3 text-sm text-[var(--text-secondary)] shadow-[var(--shadow-card)]">
          <summary className="cursor-pointer font-medium text-[var(--text-primary)]">{t('ragEval.report.showDetails')}</summary>
          <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap text-xs leading-relaxed">{report.markdown}</pre>
        </details>
      )}
    </div>
  );
};

const StatPill: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="rounded-xl bg-[var(--control-bg)] px-3 py-2">
    <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
    <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{value}</div>
  </div>
);


const resultStatusLabel = (result: RagEvalResultSummary): string => {
  if (result.top1_hit) return t('ragEval.results.status.pass');
  if (result.expected_entry_found) return t('ragEval.results.status.weak');
  if (result.wrong_entry_top1) return t('ragEval.results.status.dangerous');
  return t('ragEval.results.status.fail');
};

const resultStatusClass = (result: RagEvalResultSummary): string => {
  if (result.top1_hit) return 'border-emerald-500/30 bg-emerald-500/5 text-emerald-600';
  if (result.expected_entry_found) return 'border-amber-500/30 bg-amber-500/5 text-amber-600';
  return 'border-red-500/30 bg-red-500/5 text-red-600';
};

const RagEvalResultsPanel: React.FC<{
  results: RagEvalResultSummary[];
  loading?: boolean;
}> = ({ results, loading = false }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.results.title')}</h2>
        <p className="mt-1 text-sm text-[var(--text-muted)]">{t('ragEval.results.description')}</p>
      </div>
      <div className="rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">
        {formatNumber(results.length)}
      </div>
    </div>

    {loading && !results.length ? (
      <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('ragEval.results.loading')}
      </div>
    ) : results.length ? (
      <div className="space-y-2">
        {results.map((result, index) => {
          const retrievedIds = Array.isArray(result.retrieved_entry_ids) ? result.retrieved_entry_ids : [];
          const expectedIds = Array.isArray(result.expected_entry_ids) ? result.expected_entry_ids : [];
          return (
            <details
              key={result.result_id || `${result.question_id}-${index}`}
              className="rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-3"
            >
              <summary className="cursor-pointer list-none">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
                      {index + 1}. {result.question || t('ragEval.results.noQuestion')}
                    </div>
                    <div className="mt-1 text-xs text-[var(--text-muted)]">
                      {t('ragEval.results.expectedPrefix')} {expectedIds.join(', ') || '—'} · {t('ragEval.results.retrievedPrefix')} {retrievedIds.join(', ') || '—'}
                    </div>
                  </div>
                  <span className={`inline-flex shrink-0 rounded-full border px-2 py-1 text-xs font-semibold ${resultStatusClass(result)}`}>
                    {resultStatusLabel(result)} · {formatResultScore(result.score)}
                  </span>
                </div>
              </summary>

              <div className="mt-3 grid gap-3 text-sm text-[var(--text-secondary)] lg:grid-cols-2">
                <div className="rounded-lg bg-[var(--surface-elevated)] p-3">
                  <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{t('ragEval.results.questionTitle')}</div>
                  <div className="mt-1 text-[var(--text-primary)]">{result.question || t('ragEval.results.noQuestion')}</div>
                </div>
                <div className="rounded-lg bg-[var(--surface-elevated)] p-3">
                  <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{t('ragEval.results.metricsTitle')}</div>
                  <div className="mt-1 grid gap-1 text-xs">
                    <div>top1: {String(Boolean(result.top1_hit))}</div>
                    <div>top3: {String(Boolean(result.top3_hit))}</div>
                    <div>top5: {String(Boolean(result.top5_hit))}</div>
                    <div>{t('ragEval.results.found')}: {String(Boolean(result.expected_entry_found))}</div>
                    <div>{t('ragEval.results.wrongTop1')}: {String(Boolean(result.wrong_entry_top1))}</div>
                  </div>
                </div>
                <div className="rounded-lg bg-[var(--surface-elevated)] p-3 lg:col-span-2">
                  <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{t('ragEval.results.detailsTitle')}</div>
                  <div className="mt-1 text-xs">
                    <div>{t('ragEval.results.typePrefix')} {result.question_type || '—'}</div>
                    <div>{t('ragEval.results.latencyPrefix')} {typeof result.latency_ms === 'number' ? t('ragEval.units.milliseconds', { value: String(result.latency_ms) }) : '—'}</div>
                    {result.notes && <div>{t('ragEval.results.notesPrefix')} {result.notes}</div>}
                  </div>
                </div>
              </div>
            </details>
          );
        })}
      </div>
    ) : (
      <p className="text-sm text-[var(--text-muted)]">{t('ragEval.results.empty')}</p>
    )}
  </section>
);

type EvalReviewFilter = 'all' | 'problematic' | 'wrong_top1' | 'missing' | 'good_candidates' | 'fallback' | 'typo_short_vague';
type EvalReviewSort = 'most_problematic' | 'most_questions' | 'worst_confusion' | 'best_candidates';

const REVIEW_FILTERS: Array<{ id: EvalReviewFilter; label: string }> = [
  { id: 'all', label: t('ragEval.review.filter.all') },
  { id: 'problematic', label: t('ragEval.review.filter.problematic') },
  { id: 'wrong_top1', label: t('ragEval.review.filter.wrongTop1') },
  { id: 'missing', label: t('ragEval.review.filter.missing') },
  { id: 'good_candidates', label: t('ragEval.review.filter.goodCandidates') },
  { id: 'fallback', label: t('ragEval.review.filter.fallbackGenerated') },
  { id: 'typo_short_vague', label: t('ragEval.review.filter.typoShortVague') },
];

const REVIEW_SORTS: Array<{ id: EvalReviewSort; label: string }> = [
  { id: 'most_problematic', label: t('ragEval.review.sort.mostProblematic') },
  { id: 'most_questions', label: t('ragEval.review.sort.mostQuestions') },
  { id: 'worst_confusion', label: t('ragEval.review.sort.worstConfusion') },
  { id: 'best_candidates', label: t('ragEval.review.sort.bestCandidates') },
];

const questionIsProblem = (question: RagEvalReviewQuestion): boolean => question.retrieval_status !== 'reliable';

const groupMatchesFilter = (group: RagEvalReviewGroup, filter: EvalReviewFilter): boolean => {
  if (filter === 'all') return true;
  if (filter === 'problematic') return group.problem_count > 0;
  if (filter === 'wrong_top1') return group.questions.some((question) => question.wrong_entry_top1);
  if (filter === 'missing') return group.questions.some((question) => question.retrieval_status === 'missing');
  if (filter === 'good_candidates') return group.questions.some((question) => questionIsProblem(question) && question.review.status !== 'rejected');
  if (filter === 'fallback') return group.questions.some((question) => question.fallback_generated);
  if (filter === 'typo_short_vague') return group.questions.some((question) => question.question_type === 'short_vague');
  return true;
};

const sortReviewGroups = (groups: RagEvalReviewGroup[], sort: EvalReviewSort): RagEvalReviewGroup[] => {
  const copy = [...groups];
  copy.sort((left, right) => {
    if (sort === 'most_questions') return right.question_count - left.question_count;
    if (sort === 'worst_confusion') {
      const rightConfused = right.questions.filter((question) => question.wrong_entry_top1).length;
      const leftConfused = left.questions.filter((question) => question.wrong_entry_top1).length;
      return rightConfused - leftConfused || right.problem_count - left.problem_count;
    }
    if (sort === 'best_candidates') return right.improvement_count - left.improvement_count || right.problem_count - left.problem_count;
    return right.problem_count - left.problem_count || right.improvement_count - left.improvement_count;
  });
  return copy;
};

const questionStatusClass = (statusValue: RagEvalReviewQuestion['retrieval_status']): string => {
  if (statusValue === 'reliable') return 'bg-emerald-500/10 text-emerald-600';
  if (statusValue === 'weak') return 'bg-amber-500/10 text-amber-600';
  return 'bg-red-500/10 text-red-600';
};

const questionStatusIcon = (statusValue: RagEvalReviewQuestion['retrieval_status']): string => {
  if (statusValue === 'reliable') return '✅';
  if (statusValue === 'weak') return '⚠️';
  return '❌';
};

const DocumentEvalOverviewCard: React.FC<{
  review: RagEvalReviewPayload;
  documentName: string;
  activeRuntimeEntryCount: number;
  isStaleAfterCuration: boolean;
  onShowProblems: () => void;
  onShowGoodCandidates: () => void;
  onShowConfusedFragments: () => void;
}> = ({
  review,
  documentName,
  activeRuntimeEntryCount,
  isStaleAfterCuration,
  onShowProblems,
  onShowGoodCandidates,
  onShowConfusedFragments,
}) => {
  const summary = review.summary;
  return (
    <section className="overflow-hidden rounded-3xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-7">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-[var(--accent-primary)]">{t('ragEval.review.overview.completed')}</p>
          <h2 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{t('ragEval.review.overview.title')}</h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">{documentName}</p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[var(--accent-primary)]/10 px-3 py-1 text-sm font-semibold text-[var(--accent-primary)]">{t('ragEval.review.overview.statusPrefix')} {readinessLabel(summary.readiness)}</span>
            <span className="rounded-full bg-[var(--control-bg)] px-3 py-1 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.overview.readinessScore', { score: String(summary.score) })}</span>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">{summary.human_summary}</p>
        </div>
        <div className="rounded-2xl bg-[var(--control-bg)] p-4 text-center">
          <div className="text-4xl font-semibold text-[var(--text-primary)]">{summary.score}</div>
          <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{t('ragEval.review.overview.searchQuality')}</div>
        </div>
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <StatPill
          label={t('ragEval.review.overview.publishedRuntime')}
          value={formatNumber(activeRuntimeEntryCount || summary.fragments_total)}
        />
        <StatPill label={t('ragEval.review.overview.questions')} value={formatNumber(summary.questions_total)} />
        <StatPill label={t('ragEval.review.overview.searchProblems')} value={formatNumber(summary.problem_questions)} />
        <StatPill label={t('ragEval.review.overview.reliable')} value={formatNumber(summary.reliable_questions)} />
        <StatPill label={t('ragEval.review.overview.weak')} value={formatNumber(summary.weak_questions)} />
        <StatPill label={t('ragEval.review.overview.missing')} value={formatNumber(summary.missing_questions)} />
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" onClick={onShowProblems} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white">{t('ragEval.review.overview.reviewProblems', { count: formatNumber(summary.problem_questions) })}</button>
        <button type="button" onClick={onShowGoodCandidates} className="rounded-xl border border-[var(--border-primary)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.overview.showGoodQuestions')}</button>
        <button type="button" onClick={onShowConfusedFragments} className="rounded-xl border border-[var(--border-primary)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.overview.showConfusedFragments')}</button>
        {isStaleAfterCuration && (
          <span className="rounded-xl bg-amber-500/10 px-4 py-2 text-sm font-semibold text-amber-600">
            {t('ragEval.review.stale.badge')}
          </span>
        )}
      </div>
    </section>
  );
};

const EvalProblemMap: React.FC<{ review: RagEvalReviewPayload }> = ({ review }) => (
  <section className="grid gap-4 lg:grid-cols-3">
    <div className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
      <h3 className="text-base font-semibold text-[var(--text-primary)]">{t('ragEval.review.problemMap.mostProblematicFragments')}</h3>
      <div className="mt-3 space-y-3">
        {review.problem_map.most_problematic_fragments.filter((group) => group.problem_count > 0).slice(0, 4).map((group) => (
          <div key={group.entry_id} className="rounded-xl bg-[var(--control-bg)] p-3">
            <div className="text-sm font-semibold text-[var(--text-primary)]">{group.title}</div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">{t('ragEval.review.problemMap.questionProblemStats', { questions: formatNumber(group.question_count), problems: formatNumber(group.problem_count) })}</div>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">{group.issue_summary}</p>
          </div>
        ))}
      </div>
    </div>
    <div className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
      <h3 className="text-base font-semibold text-[var(--text-primary)]">{t('ragEval.review.problemMap.bestFragments')}</h3>
      <div className="mt-3 space-y-3">
        {review.problem_map.best_fragments.slice(0, 4).map((group) => (
          <div key={group.entry_id} className="rounded-xl bg-emerald-500/5 p-3">
            <div className="text-sm font-semibold text-[var(--text-primary)]">{group.title}</div>
            <div className="mt-1 text-xs text-emerald-600">{t('ragEval.review.problemMap.questionsFoundCorrectly', { found: formatNumber(group.question_count), total: formatNumber(group.question_count) })}</div>
          </div>
        ))}
      </div>
    </div>
    <div className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
      <h3 className="text-base font-semibold text-[var(--text-primary)]">{t('ragEval.review.problemMap.problemTypes')}</h3>
      <div className="mt-3 space-y-2">
        {review.problem_map.problem_types.map((item) => (
          <div key={item.type} className="flex items-center justify-between rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm">
            <span className="text-[var(--text-secondary)]">{item.label}</span>
            <span className="font-semibold text-[var(--text-primary)]">{formatNumber(item.count)}</span>
          </div>
        ))}
      </div>
    </div>
  </section>
);

const EvalFiltersBar: React.FC<{
  filter: EvalReviewFilter;
  sort: EvalReviewSort;
  onFilterChange: (value: EvalReviewFilter) => void;
  onSortChange: (value: EvalReviewSort) => void;
}> = ({ filter, sort, onFilterChange, onSortChange }) => (
  <div className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
    <div className="flex flex-wrap gap-2">
      {REVIEW_FILTERS.map((item) => (
        <button key={item.id} type="button" onClick={() => onFilterChange(item.id)} className={`rounded-full px-3 py-1.5 text-sm font-medium ${filter === item.id ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--control-bg)] text-[var(--text-secondary)]'}`}>{item.label}</button>
      ))}
    </div>
    <label className="mt-3 block max-w-sm text-sm text-[var(--text-secondary)]">
      {t('ragEval.review.sort.label')}
      <select value={sort} onChange={(event) => onSortChange(event.target.value as EvalReviewSort)} className="mt-1 w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none">
        {REVIEW_SORTS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select>
    </label>
  </div>
);

const fragmentReviewStatusLabel = (value: RagEvalReviewGroup['review_status']): string => {
  if (value === 'queued') return t('ragEval.review.fragmentStatus.queued');
  if (value === 'generating_questions') return t('ragEval.review.fragmentStatus.generatingQuestions');
  if (value === 'checking_retrieval') return t('ragEval.review.fragmentStatus.checkingRetrieval');
  if (value === 'ready_for_review') return t('ragEval.review.fragmentStatus.readyForReview');
  if (value === 'failed') return t('ragEval.review.fragmentStatus.failed');
  return t('ragEval.review.fragmentStatus.readyForReview');
};

const fragmentReviewStatusClass = (value: RagEvalReviewGroup['review_status']): string => {
  if (value === 'ready_for_review') return 'bg-emerald-500/10 text-emerald-600';
  if (value === 'failed') return 'bg-red-500/10 text-red-600';
  if (value === 'checking_retrieval') return 'bg-amber-500/10 text-amber-600';
  return 'bg-[var(--control-bg)] text-[var(--text-secondary)]';
};

const asReviewQuestions = (value: unknown): RagEvalReviewQuestion[] => (
  Array.isArray(value)
    ? value.filter((item): item is RagEvalReviewQuestion => Boolean(item) && typeof item === 'object')
    : []
);

type RagEvalReviewRetrievedEntryItem = RagEvalReviewQuestion['retrieved_entries'][number];

const asRetrievedEntries = (value: unknown): RagEvalReviewRetrievedEntryItem[] => (
  Array.isArray(value)
    ? value.filter((item): item is RagEvalReviewRetrievedEntryItem => Boolean(item) && typeof item === 'object')
    : []
);

const FragmentReviewCard: React.FC<{
  group: RagEvalReviewGroup;
  onOpenQuestion: (question: RagEvalReviewQuestion, group: RagEvalReviewGroup) => void;
  onAcceptGroup: (group: RagEvalReviewGroup) => void;
}> = ({ group, onOpenQuestion, onAcceptGroup }) => {
  const existingQuestions = asStringList(group.existing_questions);
  const proposedImprovements = asStringList(group.proposed_improvements);
  const questions = asReviewQuestions(group.questions);
  const firstQuestion = questions[0] ?? null;

  return (
    <article className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.review.fragment.titlePrefix')} {group.title}</h3>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${fragmentReviewStatusClass(group.review_status)}`}>
            {fragmentReviewStatusLabel(group.review_status)}
          </span>
          <span className="text-sm text-[var(--text-muted)]">{t('ragEval.review.fragment.searchStatusPrefix')} {group.status}</span>
        </div>
        {group.review_status === 'failed' && group.error && (
          <p className="mt-2 text-sm text-red-500">{group.error}</p>
        )}
      </div>
      <span className="rounded-full bg-[var(--control-bg)] px-3 py-1 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.fragment.problemCount', { count: formatNumber(group.problem_count) })}</span>
    </div>
    <div className="mt-4 rounded-xl bg-[var(--control-bg)] p-4">
      <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{t('ragEval.review.fragment.answerKnowledge')}</div>
      <p className="mt-2 line-clamp-4 text-sm leading-6 text-[var(--text-secondary)]">{group.content || t('ragEval.review.fragment.noContent')}</p>
    </div>
    <div className="mt-4 grid gap-4 lg:grid-cols-2">
      <div>
        <div className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.fragment.existingQuestions')}</div>
        <ul className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
          {existingQuestions.slice(0, 4).map((item) => <li key={item}>— {item}</li>)}
          {!existingQuestions.length && <li className="text-[var(--text-muted)]">{t('ragEval.review.fragment.noExistingQuestions')}</li>}
        </ul>
      </div>
      <div>
        <div className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.fragment.systemProposal')}</div>
        <ul className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
          {proposedImprovements.map((item) => <li key={item}>— {item}</li>)}
        </ul>
      </div>
    </div>
    <div className="mt-4 space-y-2">
      <div className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.fragment.generatedQuestions')}</div>
      {questions.length === 0 && (
        <div className="rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-muted)]">
          {t('ragEval.review.fragment.generatedQuestionsPending')}
        </div>
      )}
      {questions.slice(0, 8).map((question) => (
        <button key={question.question_id} type="button" onClick={() => onOpenQuestion(question, group)} className="flex w-full items-center justify-between gap-3 rounded-xl bg-[var(--control-bg)] px-3 py-2 text-left text-sm hover:bg-[var(--surface-elevated)]">
          <span className="min-w-0 truncate text-[var(--text-primary)]">{questionStatusIcon(question.retrieval_status)} {question.effective_question}</span>
          <span className={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${questionStatusClass(question.retrieval_status)}`}>{question.retrieval_status_label}</span>
        </button>
      ))}
    </div>
    <div className="mt-4 flex flex-wrap gap-2">
      <button type="button" onClick={() => firstQuestion && onOpenQuestion(firstQuestion, group)} className="rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.fragment.reviewQuestions')}</button>
      {group.problem_count > 0 ? (
        <button type="button" onClick={() => onAcceptGroup(group)} className="rounded-xl bg-[var(--accent-primary)] px-3 py-2 text-sm font-semibold text-white">{t('ragEval.review.fragment.acceptProblemQuestion')}</button>
      ) : (
        <span className="rounded-xl bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-600">{t('ragEval.review.fragment.noActionNeeded')}</span>
      )}
      <button type="button" className="rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.fragment.rebuild')}</button>
    </div>
  </article>
  );
};

const QuestionReviewDrawer: React.FC<{
  question: RagEvalReviewQuestion | null;
  group: RagEvalReviewGroup | null;
  onClose: () => void;
  onAccept: (questionId: string) => void;
  onReject: (questionId: string) => void;
  onEdit: (questionId: string, value: string) => void;
  mutating: boolean;
}> = ({ question, group, onClose, onAccept, onReject, onEdit, mutating }) => {
  const [editValue, setEditValue] = useState('');
  if (!question || !group) return null;
  const currentEditValue = editValue || question.effective_question;
  const isAlreadyAccepted = question.review.status === 'accepted'
    || question.review.status === 'edited'
    || question.review.status === 'applied';
  const retrievedEntries = asRetrievedEntries(question.retrieved_entries);
  const proposedImprovements = asStringList(question.proposed_improvements);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <aside className="h-full w-full max-w-xl overflow-auto bg-[var(--surface-elevated)] p-5 shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-[var(--accent-primary)]">{t('ragEval.review.questionDrawer.candidate')}</p>
            <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">“{question.effective_question}”</h3>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg border border-[var(--border-primary)] px-3 py-1 text-sm text-[var(--text-primary)]">{t('common.actions.close')}</button>
        </div>
        <div className="mt-5 space-y-4">
          <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-secondary)]">
            <div>{t('ragEval.review.questionDrawer.typePrefix')} <span className="font-semibold text-[var(--text-primary)]">{question.question_type_label}</span></div>
            <div className="mt-1">{t('ragEval.review.questionDrawer.statusPrefix')} <span className="font-semibold text-[var(--text-primary)]">{question.retrieval_status_label}</span></div>
            <div className="mt-1">{t('ragEval.review.questionDrawer.reviewStatePrefix')} <span className="font-semibold text-[var(--text-primary)]">{question.review.status}</span></div>
          </div>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.questionDrawer.expectedFragment')}</h4>
            <p className="mt-2 rounded-xl bg-[var(--control-bg)] p-3 text-sm leading-6 text-[var(--text-secondary)]">{group.content || group.title}</p>
          </section>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.questionDrawer.retrievedBySearch')}</h4>
            <ol className="mt-2 space-y-2 text-sm text-[var(--text-secondary)]">
              {retrievedEntries.map((entry, index) => <li key={`${entry.id}-${index}`} className="rounded-xl bg-[var(--control-bg)] p-3">{index + 1}. {entry.title || t('ragEval.review.questionDrawer.untitledEntry')}<p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">{entry.content}</p></li>)}
              {!retrievedEntries.length && <li className="rounded-xl bg-[var(--control-bg)] p-3">{t('ragEval.review.questionDrawer.noRetrievedFragments')}</li>}
            </ol>
          </section>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.questionDrawer.whyProblem')}</h4>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{question.why_it_matters}</p>
          </section>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.questionDrawer.whatToDo')}</h4>
            <ul className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
              {proposedImprovements.map((item) => <li key={item}>☑ {item}</li>)}
              <li>{t('ragEval.review.questionDrawer.rejectAsBadQuestion')}</li>
            </ul>
          </section>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.questionDrawer.editQuestion')}</h4>
            <textarea value={currentEditValue} onChange={(event) => setEditValue(event.target.value)} className="mt-2 min-h-24 w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-3 text-sm text-[var(--text-primary)] outline-none" />
          </section>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={mutating || isAlreadyAccepted} onClick={() => onAccept(question.question_id)} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{isAlreadyAccepted ? t('ragEval.review.questionDrawer.alreadyAccepted') : t('ragEval.review.questionDrawer.accept')}</button>
            <button type="button" disabled={mutating} onClick={() => onEdit(question.question_id, currentEditValue)} className="rounded-xl border border-[var(--border-primary)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] disabled:opacity-50">{t('ragEval.review.questionDrawer.saveEdit')}</button>
            <button type="button" disabled={mutating} onClick={() => onReject(question.question_id)} className="rounded-xl border border-red-500/30 px-4 py-2 text-sm font-semibold text-red-500 disabled:opacity-50">{t('ragEval.review.questionDrawer.reject')}</button>
          </div>
          <details className="rounded-xl border border-[var(--border-primary)] p-3">
            <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">{t('ragEval.review.questionDrawer.diagnostics')}</summary>
            <div className="mt-3"><ReportJsonBlock value={question.diagnostics} /></div>
          </details>
        </div>
      </aside>
    </div>
  );
};

const ApplyAcceptedQuestionsPanel: React.FC<{ acceptedCount: number; onApply: () => void; applying: boolean }> = ({ acceptedCount, onApply, applying }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.review.applyPanel.title')}</h3>
        <p className="mt-1 text-sm text-[var(--text-muted)]">{t('ragEval.review.applyPanel.description')}</p>
      </div>
      <button type="button" onClick={onApply} disabled={!acceptedCount || applying} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
        {applying ? t('ragEval.review.applyPanel.applying') : t('ragEval.review.applyPanel.addToFragments', { count: formatNumber(acceptedCount) })}
      </button>
    </div>
  </section>
);

const TechnicalDiagnosticsDisclosure: React.FC<{ value: unknown }> = ({ value }) => (
  <details className="rounded-2xl border border-[var(--border-primary)] bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
    <summary className="cursor-pointer text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.review.technicalDiagnostics')}</summary>
    <div className="mt-3"><ReportJsonBlock value={value} /></div>
  </details>
);

const JobProgressCard: React.FC<{
  job: RagEvalJob | null;
  progress: RagEvalProgressPayload | null;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
  isMutating: boolean;
}> = ({ job, progress, onPause, onResume, onCancel, isMutating }) => {
  if (!job) {
    return (
      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--control-bg)] text-[var(--text-muted)]">
            <BarChart3 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.progress.title')}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('ragEval.progress.noRecentJobs')}
            </p>
          </div>
        </div>
      </section>
    );
  }

  const effectiveStatus = getJobStatus(job);
  const terminal = isJobTerminal(job);
  const mergedProgress = progress ?? job.progress ?? {};
  const percentSource = mergedProgress.percent ?? job.percent;
  const percent = terminal ? 100 : clampPercent(percentSource);
  const progressStage = String(mergedProgress.stage || '');
  const stage = terminal ? effectiveStatus : progressStage || effectiveStatus;
  const entriesTotal = asNumber(mergedProgress.entries_total || mergedProgress.source_entry_count || mergedProgress.source_chunk_count);
  const entriesReady = asNumber(mergedProgress.entries_ready_for_review || mergedProgress.fragments_ready_for_review || mergedProgress.entries_processed);
  const entriesQueued = asNumber(mergedProgress.entries_queued);
  const entriesGenerating = asNumber(mergedProgress.entries_generating);
  const entriesChecking = asNumber(mergedProgress.entries_checking);
  const entriesFailed = asNumber(mergedProgress.entries_failed);
  const activeGenerationWorkers = asNumber(mergedProgress.active_generation_workers);
  const activeRetrievalWorkers = asNumber(mergedProgress.active_retrieval_workers);
  const generatedQuestions = asNumber(mergedProgress.generated_questions);
  const targetQuestions = asNumber(mergedProgress.target_questions);
  const processedQuestions = asNumber(mergedProgress.processed_questions);
  const queuedQuestions = asNumber(mergedProgress.queued_questions);
  const totalQuestions = asNumber(mergedProgress.total_questions || targetQuestions || generatedQuestions);
  const questionsPerMinute = asNumber(mergedProgress.questions_per_minute);
  const entriesPerMinute = asNumber(mergedProgress.entries_per_minute);
  const actionableImprovementsCount = asNumber(mergedProgress.actionable_improvements_count);
  const fallbackUsedCount = asNumber(mergedProgress.fallback_used_count);
  const questionModel = typeof mergedProgress.question_model === 'string' ? mergedProgress.question_model : '';
  const lastUpdateSecondsAgo = asNumber(mergedProgress.last_update_seconds_ago);
  const sourceChunkCount = asNumber(mergedProgress.source_chunk_count);
  const jsonParseFailures = asNumber(mergedProgress.json_parse_failures);
  const providerFailures = asNumber(mergedProgress.provider_failures);
  const retryCount = asNumber(mergedProgress.retry_count);
  const failedRetrievalCount = asNumber(mergedProgress.failed_retrieval_count);
  const startedAt = timestampMs(job.created_at);
  const observedAt = timestampMs(mergedProgress.updated_at) ?? timestampMs(job.updated_at) ?? timestampMs(job.locked_at);
  const elapsedMs = startedAt === null || observedAt === null ? 0 : observedAt - startedAt;

  const active = isJobActive(job);
  const paused = isJobPaused(job);

  return (
    <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            {active ? <Loader2 className="h-5 w-5 animate-spin" /> : <BarChart3 className="h-5 w-5" />}
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.progress.title')}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('ragEval.progress.currentDocument')}
            </p>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('ragEval.progress.statusPrefix')} <span className="font-semibold text-[var(--text-primary)]">{statusLabel(effectiveStatus || job.status)}</span>
              {' · '}
              {t('ragEval.progress.nowPrefix')} <span className="font-semibold text-[var(--text-primary)]">{stageLabel(stage)}</span>
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onPause}
            disabled={!active || paused || isMutating}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Pause className="h-4 w-4" />
            {t('ragEval.actions.pause')}
          </button>
          <button
            type="button"
            onClick={onResume}
            disabled={!paused || isMutating}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw className="h-4 w-4" />
            {t('ragEval.actions.resume')}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={terminal || (!active && !paused) || isMutating}
            className="inline-flex items-center gap-2 rounded-xl border border-red-500/40 px-3 py-2 text-sm font-medium text-red-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Square className="h-4 w-4" />
            {t('ragEval.actions.cancel')}
          </button>
        </div>
      </div>

      <div className="mb-4">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="text-[var(--text-muted)]">{t('ragEval.progress.completed')}</span>
          <span className="font-semibold text-[var(--text-primary)]">{percent}%</span>
        </div>
        <div className="h-3 overflow-hidden rounded-full bg-[var(--control-bg)]">
          <div
            className="h-full rounded-full bg-[var(--accent-primary)] transition-all duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      <p className="mb-4 rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-secondary)]">
        {progressMessage(mergedProgress, stage)}
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatPill label={t('ragEval.progress.stats.fragmentsReadyTotal')} value={entriesTotal ? `${entriesReady}/${entriesTotal}` : entriesReady || '—'} />
        <StatPill label={t('ragEval.progress.stats.fragmentsQueued')} value={entriesQueued} />
        <StatPill label={t('ragEval.progress.stats.fragmentsGenerating')} value={entriesGenerating || activeGenerationWorkers} />
        <StatPill label={t('ragEval.progress.stats.fragmentsChecking')} value={entriesChecking} />
        <StatPill label={t('ragEval.progress.stats.fragmentsFailed')} value={entriesFailed} />
        <StatPill label={t('ragEval.progress.stats.questionsCreated')} value={generatedQuestions} />
        <StatPill label={t('ragEval.progress.stats.questionsChecked')} value={totalQuestions ? `${processedQuestions}/${totalQuestions}` : processedQuestions} />
        <StatPill label={t('ragEval.progress.stats.questionsQueued')} value={queuedQuestions} />
        <StatPill label={t('ragEval.progress.stats.activeRetrievalChecks')} value={activeRetrievalWorkers} />
        <StatPill label={t('ragEval.progress.stats.searchProblems')} value={failedRetrievalCount} />
        <StatPill label={t('ragEval.progress.stats.proposedImprovements')} value={actionableImprovementsCount} />
        <StatPill label={t('ragEval.progress.stats.questionsPerMinute')} value={questionsPerMinute || '—'} />
        <StatPill label={t('ragEval.progress.stats.fragmentsPerMinute')} value={entriesPerMinute || '—'} />
        <StatPill label={t('ragEval.progress.stats.lastUpdate')} value={t('ragEval.units.secondsAgo', { seconds: String(lastUpdateSecondsAgo) })} />
        <StatPill label={t('ragEval.progress.stats.questionModel')} value={questionModel || '—'} />
        <StatPill label={t('ragEval.progress.stats.fallbackUsed')} value={t('ragEval.units.times', { count: String(fallbackUsedCount) })} />
        <StatPill label={t('ragEval.stats.elapsed')} value={startedAt === null ? '—' : formatDurationMs(elapsedMs)} />
        <StatPill label={t('ragEval.stats.jsonFailures')} value={jsonParseFailures} />
        <StatPill label={t('ragEval.stats.providerFailures')} value={providerFailures} />
        <StatPill label={t('ragEval.stats.retries')} value={retryCount} />
        <StatPill label={t('ragEval.stats.fragments')} value={sourceChunkCount || entriesTotal || '—'} />
        <StatPill label={t('ragEval.stats.attempts')} value={`${job.attempts}/${job.max_attempts}`} />
      </div>

      {ERROR_VISIBLE_JOB_STATUSES.has(getJobStatus(job)) && job.error && (
        <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">
          {job.error}
        </div>
      )}
    </section>
  );
};

export const RagEvalPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const [selectedDocumentId, setSelectedDocumentId] = useState('');
  const [lastQueued, setLastQueued] = useState<RagEvalFullRunAcceptedResponse | null>(null);
  const [lastActionExecutionSummary, setLastActionExecutionSummary] = useState<KnowledgeEditActionExecutionSummary | null>(null);
  const [reviewFilter, setReviewFilter] = useState<EvalReviewFilter>('all');
  const [reviewSort, setReviewSort] = useState<EvalReviewSort>('most_problematic');
  const [selectedReviewQuestion, setSelectedReviewQuestion] = useState<RagEvalReviewQuestion | null>(null);
  const [selectedReviewGroup, setSelectedReviewGroup] = useState<RagEvalReviewGroup | null>(null);
  const [activeReviewTab, setActiveReviewTab] = useState<'curation' | 'retrieval'>('curation');

  const documentsQuery = useQuery({
    queryKey: ['knowledge-documents', projectId],
    queryFn: async () => {
      if (!projectId) return [];
      const { data } = await knowledgeApi.list(projectId);

      const payload = data && typeof data === 'object' ? data as Record<string, unknown> : {};
      const list = Array.isArray(payload.documents)
        ? payload.documents
        : Array.isArray(payload.items)
          ? payload.items
          : [];

      return list as Document[];
    },
    enabled: !!projectId,
  });

  const documents = useMemo(
    () => (Array.isArray(documentsQuery.data) ? documentsQuery.data : []),
    [documentsQuery.data],
  );

  const processedDocuments = useMemo(
    () => documents.filter((doc) => doc.status === 'processed' && documentRuntimeEntryCount(doc) > 0),
    [documents],
  );

  const activeDocumentId = selectedDocumentId || processedDocuments[0]?.id || '';
  const activeDocument = processedDocuments.find((doc) => doc.id === activeDocumentId) || null;

  const statusQuery = useQuery({
    queryKey: ['rag-eval-status', activeDocumentId],
    queryFn: async () => ragEvalApi.getStatus(activeDocumentId),
    enabled: !!activeDocumentId,
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data as RagEvalDocumentStatusResponse | undefined;
      const status = String(data?.run?.status || '');
      return ACTIVE_RUN_STATUSES.has(status) ? 5000 : false;
    },
  });

  const reviewQuery = useQuery({
    queryKey: ['rag-eval-latest-review', activeDocumentId],
    queryFn: async () => ragEvalApi.getLatestReview(activeDocumentId),
    enabled: !!activeDocumentId,
    retry: false,
    refetchInterval: (query) => {
      const statusRun = statusQuery.data?.run as Record<string, unknown> | undefined;
      const latestReview = query.state.data?.review;
      const reviewRun = latestReview?.run as Record<string, unknown> | undefined;
      const status = String(reviewRun?.status || statusRun?.status || '');
      return ACTIVE_RUN_STATUSES.has(status) ? 3000 : false;
    },
  });

  const curationActionsQuery = useQuery({
    queryKey: ['knowledge-curation-actions', projectId, activeDocumentId],
    queryFn: async () => {
      if (!projectId || !activeDocumentId) return [];
      const { data } = await knowledgeCurationApi.listActions(projectId, activeDocumentId);
      return data.actions;
    },
    enabled: !!projectId && !!activeDocumentId,
    retry: false,
  });

  const jobsQuery = useQuery({
    queryKey: ['rag-eval-jobs', activeDocumentId],
    queryFn: async () => ragEvalApi.listJobs(activeDocumentId),
    enabled: !!activeDocumentId,
    retry: false,
    refetchInterval: (query) => {
      const jobs = query.state.data?.jobs ?? [];
      return jobs.some((job) => isJobActive(job) || isJobPaused(job)) ? 3000 : false;
    },
  });

  const visibleJob = useMemo(() => {
    const jobs = jobsQuery.data?.jobs ?? [];
    const active = jobs.find((job) => isJobActive(job));
    if (active) return active;

    const paused = jobs.find((job) => isJobPaused(job));
    if (paused) return paused;

    if (lastQueued) {
      const queued = jobs.find((job) => job.id === lastQueued.job_id);
      if (queued) return queued;
    }

    return jobs[0] ?? null;
  }, [jobsQuery.data?.jobs, lastQueued]);

  const progressQuery = useQuery({
    queryKey: ['rag-eval-job-progress', visibleJob?.id],
    queryFn: async () => ragEvalApi.getJobProgress(String(visibleJob?.id)),
    enabled: !!visibleJob?.id,
    retry: false,
    refetchInterval: (query) => {
      const job = query.state.data?.job;
      return isJobActive(job) || isJobPaused(job) ? 3000 : false;
    },
  });

  const invalidateEvalQueries = async () => {
    await queryClient.invalidateQueries({ queryKey: ['rag-eval-status', activeDocumentId] });
    await queryClient.invalidateQueries({ queryKey: ['rag-eval-jobs', activeDocumentId] });
    await queryClient.invalidateQueries({ queryKey: ['rag-eval-job-progress'] });
    await queryClient.invalidateQueries({ queryKey: ['rag-eval-latest-review', activeDocumentId] });
  };

  const applyJobMutationResult = (job: RagEvalJob) => {
    queryClient.setQueryData<RagEvalJobsResponse>(['rag-eval-jobs', activeDocumentId], (current) => {
      if (!current) return current;
      const exists = current.jobs.some((item) => item.id === job.id);
      const jobs = exists
        ? current.jobs.map((item) => (item.id === job.id ? job : item))
        : [job, ...current.jobs];
      return { ...current, jobs };
    });

    queryClient.setQueryData<RagEvalJobProgressResponse>(['rag-eval-job-progress', job.id], {
      ok: true,
      job,
    });
  };

  const runMutation = useMutation({
    mutationFn: async () => {
      if (!activeDocumentId) throw new Error(t('ragEval.error.noProcessedDocument'));

        return await ragEvalApi.runFullDocumentEval(activeDocumentId);
    },
    onSuccess: async (result) => {
      setLastQueued(result);
      setLastActionExecutionSummary(null);
      toast.success(t('ragEval.feedback.started'));
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('ragEval.error.enqueueFailed')));
    },
  });

  const pauseMutation = useMutation({
    mutationFn: async (jobId: string) => ragEvalApi.pauseJob(jobId),
    onSuccess: (result) => {
      applyJobMutationResult(result.job);
      toast.success(t('ragEval.feedback.paused'));
      void invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('ragEval.error.pauseFailed')));
    },
  });

  const resumeMutation = useMutation({
    mutationFn: async (jobId: string) => ragEvalApi.resumeJob(jobId),
    onSuccess: (result) => {
      applyJobMutationResult(result.job);
      toast.success(t('ragEval.feedback.resumed'));
      void invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('ragEval.error.resumeFailed')));
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async (jobId: string) => ragEvalApi.cancelJob(jobId),
    onSuccess: (result) => {
      setLastQueued(null);
      applyJobMutationResult(result.job);
      toast.success(t('ragEval.feedback.cancelled'));
      void invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('ragEval.error.cancelFailed')));
    },
  });

  const executeActionsMutation = useMutation<KnowledgeEditActionExecutionSummary, unknown, string>({
    mutationFn: async (resultId: string) => ragEvalApi.executeResultActions(resultId),
    onSuccess: async (summary) => {
      setLastActionExecutionSummary(summary);

      const rerunMessage = summary.queued_rerun_job_ids.length
        ? t('ragEval.feedback.rerunQueuedSuffix')
        : '';

      toast.success(
        t('ragEval.feedback.actionsApplied', { applied: summary.applied_actions, rejected: summary.rejected_actions, failed: summary.failed_actions, suffix: rerunMessage }),
      );
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('ragEval.error.executeActionsFailed')));
    },
  });

  const updateReviewQuestionState = (
    questionId: string,
    reviewState: RagEvalQuestionReviewState,
  ): void => {
    queryClient.setQueryData<RagEvalLatestReviewResponse>(
      ['rag-eval-latest-review', activeDocumentId],
      (current) => {
        if (!current?.review) return current;
        return {
          ...current,
          review: applyQuestionReviewState(current.review, questionId, reviewState),
        };
      },
    );

    setSelectedReviewQuestion((current) => (
      current?.question_id === questionId ? { ...current, review: reviewState } : current
    ));
  };

  const reviewQuestionMutation = useMutation({
    mutationFn: async ({ questionId, status: nextStatus }: { questionId: string; status: 'accepted' | 'rejected' }) => ragEvalApi.reviewQuestion(questionId, nextStatus),
    onSuccess: async (result, variables) => {
      updateReviewQuestionState(variables.questionId, result.review);
      toast.success(t('ragEval.review.toast.questionDecisionSaved'));
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('ragEval.review.toast.questionDecisionSaveFailed')));
    },
  });

  const editQuestionMutation = useMutation({
    mutationFn: async ({ questionId, question }: { questionId: string; question: string }) => ragEvalApi.editQuestion(questionId, question),
    onSuccess: async (result, variables) => {
      updateReviewQuestionState(variables.questionId, result.review);
      toast.success(t('ragEval.review.toast.questionEditSaved'));
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('ragEval.review.toast.questionEditFailed')));
    },
  });

  const applyAcceptedMutation = useMutation({
    mutationFn: async (runId: string) => ragEvalApi.applyAcceptedQuestions(runId),
    onSuccess: async (result) => {
      toast.success(t('ragEval.review.toast.appliedQuestions', { count: formatNumber(result.applied_questions) }));
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t('ragEval.review.toast.applyAcceptedQuestionsFailed')));
    },
  });

  const latestReportPayload = statusQuery.data?.report ?? null;
  const latestReport = getRecord(latestReportPayload);
  const actionableResults = useMemo(() => getActionableResults(latestReport), [latestReport]);
  const latestRun = statusQuery.data?.run ?? null;
  const latestRunRecord = getRecord(latestRun);
  const latestRunResults = getEvalResults(latestRunRecord.results);
  const latestReportResults = getEvalResults(latestReport.results);
  const visibleResults = latestRunResults.length ? latestRunResults : latestReportResults;
  const progressJob = progressQuery.data?.job ?? visibleJob;
  const progressPayload = progressJob?.progress ?? visibleJob?.progress ?? (
    progressJob
      ? { percent: progressJob.percent, status: getJobStatus(progressJob) }
      : null
  );
  const review = reviewQuery.data?.review ?? null;
  const latestCurationActionMs = useMemo(
    () => latestAppliedCurationActionTimeMs(curationActionsQuery.data ?? []),
    [curationActionsQuery.data],
  );
  const reviewMs = reviewRunTimeMs(review);
  const isReviewStaleAfterCuration = Boolean(
    review
    && latestCurationActionMs !== null
    && (reviewMs === null || latestCurationActionMs > reviewMs),
  );
  const activeRuntimeEntryCount = documentRuntimeEntryCount(activeDocument);
  const reviewGroups = useMemo(() => {
    if (!review) return [];
    return sortReviewGroups(
      review.groups.filter((group) => groupMatchesFilter(group, reviewFilter)),
      reviewSort,
    );
  }, [review, reviewFilter, reviewSort]);
  const acceptedReviewCount = useMemo(() => (
    review?.groups.reduce((total, group) => total + group.questions.filter((question) => question.review.status === 'accepted' || question.review.status === 'edited').length, 0) ?? 0
  ), [review]);
  const reviewRunId = String(review?.run.id || '');

  const isControlMutating = pauseMutation.isPending || resumeMutation.isPending || cancelMutation.isPending;
  const executingResultId = executeActionsMutation.isPending
    ? executeActionsMutation.variables ?? null
    : null;

  if (documentsQuery.isLoading) {
    return (
      <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">
        {t('ragEval.documents.loading')}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">
          {t('ragEval.page.title')}
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-[var(--text-muted)]">
          {t('ragEval.page.descriptionLine1')}
          {t('ragEval.page.descriptionLine2')}
        </p>
      </div>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-5 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.run.title')}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('ragEval.run.description')}
            </p>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">{t('ragEval.run.documentLabel')}</span>
            <select
              value={activeDocumentId}
              onChange={(event) => {
                setSelectedDocumentId(event.target.value);
                setLastActionExecutionSummary(null);
              }}
              className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
            >
              {processedDocuments.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.file_name} · {documentRuntimeEntryCount(doc)} {t('ragEval.document.runtimeEntries')}
                </option>
              ))}
            </select>
          </label>



          <button
            type="button"
            onClick={() => runMutation.mutate()}
            disabled={!activeDocumentId || runMutation.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 lg:self-end"
          >
            {runMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {t('ragEval.run.start')}
          </button>
        </div>

        {activeDocument && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-muted)]">
            <FileText className="h-4 w-4" />
            <span>{activeDocument.file_name}</span>
            <span>·</span>
            <span>{formatNumber(documentRuntimeEntryCount(activeDocument))} {t('ragEval.document.runtimeEntries')}</span>
          </div>
        )}
      </section>

      <JobProgressCard
        job={progressJob ?? null}
        progress={progressPayload}
        isMutating={isControlMutating}
        onPause={() => {
          if (progressJob?.id) pauseMutation.mutate(progressJob.id);
        }}
        onResume={() => {
          if (progressJob?.id) resumeMutation.mutate(progressJob.id);
        }}
        onCancel={() => {
          if (progressJob?.id) cancelMutation.mutate(progressJob.id);
        }}
      />

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-2 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setActiveReviewTab('curation')}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${activeReviewTab === 'curation' ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--control-bg)] text-[var(--text-muted)]'}`}
          >
            {t('ragEval.tabs.knowledgeCuration')}
          </button>
          <button
            type="button"
            onClick={() => setActiveReviewTab('retrieval')}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${activeReviewTab === 'retrieval' ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--control-bg)] text-[var(--text-muted)]'}`}
          >
            {t('ragEval.tabs.searchReview')}
          </button>
        </div>
      </section>

      {activeReviewTab === 'curation' ? (
        <KnowledgeCurationConsole
          projectId={String(projectId || '')}
          documentId={activeDocumentId}
          documentName={activeDocument?.file_name}
          onInvalidateRagEval={invalidateEvalQueries}
        />
      ) : reviewQuery.isLoading && !review ? (
        <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">
          <Loader2 className="mr-2 inline h-4 w-4 animate-spin" /> {t('ragEval.review.loadingConsole')}
        </section>
      ) : review ? (
        <>
          {isReviewStaleAfterCuration && (
            <section className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-5 shadow-[var(--shadow-card)]">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h3 className="text-base font-semibold text-amber-700">{t('ragEval.review.stale.title')}</h3>
                  <p className="mt-1 text-sm leading-6 text-amber-700/90">{t('ragEval.review.stale.description')}</p>
                </div>
                <button
                  type="button"
                  onClick={() => runMutation.mutate()}
                  disabled={!activeDocumentId || runMutation.isPending}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {runMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                  {t('ragEval.review.stale.rerun')}
                </button>
              </div>
            </section>
          )}
          <DocumentEvalOverviewCard
            review={review}
            documentName={activeDocument?.file_name || String(review.run.document_id || '')}
            activeRuntimeEntryCount={activeRuntimeEntryCount}
            isStaleAfterCuration={isReviewStaleAfterCuration}
            onShowProblems={() => setReviewFilter('problematic')}
            onShowGoodCandidates={() => setReviewFilter('good_candidates')}
            onShowConfusedFragments={() => setReviewFilter('wrong_top1')}
          />
          <EvalProblemMap review={review} />
          <EvalFiltersBar
            filter={reviewFilter}
            sort={reviewSort}
            onFilterChange={setReviewFilter}
            onSortChange={setReviewSort}
          />
          <div className="space-y-4">
            {reviewGroups.map((group) => (
              <FragmentReviewCard
                key={group.entry_id}
                group={group}
                onOpenQuestion={(question, nextGroup) => {
                  setSelectedReviewQuestion(question);
                  setSelectedReviewGroup(nextGroup);
                }}
                onAcceptGroup={(nextGroup) => {
                  const candidate = nextGroup.questions.find((question) => questionIsProblem(question) && question.review.status !== 'accepted');
                  if (candidate) reviewQuestionMutation.mutate({ questionId: candidate.question_id, status: 'accepted' });
                }}
              />
            ))}
            {!reviewGroups.length && (
              <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">
                {t('ragEval.review.emptyFilteredFragments')}
              </section>
            )}
          </div>
          <ApplyAcceptedQuestionsPanel
            acceptedCount={acceptedReviewCount}
            applying={applyAcceptedMutation.isPending}
            onApply={() => {
              if (reviewRunId) applyAcceptedMutation.mutate(reviewRunId);
            }}
          />
          <TechnicalDiagnosticsDisclosure value={review.diagnostics} />
        </>
      ) : (
        <RagEvalResultsPanel
          results={visibleResults}
          loading={statusQuery.isLoading || Boolean(progressJob && !isJobTerminal(progressJob))}
        />
      )}

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <BarChart3 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">{t('ragEval.lastResult.title')}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('ragEval.lastResult.description')}
            </p>
          </div>
        </div>

        {statusQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('ragEval.lastResult.loadingStatus')}
          </div>
        ) : statusQuery.error ? (
          <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">
            <XCircle className="h-4 w-4" />
            {t('ragEval.lastResult.statusLoadFailed')}
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.launch.title')}</h3>
              <div className="rounded-xl bg-[var(--control-bg)] p-4">
                <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{t('ragEval.launch.status')}</div>
                <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                  {statusLabel(String(latestRunRecord.status || ''))}
                </div>
                <p className="mt-2 text-sm text-[var(--text-muted)]">
                  {t('ragEval.launch.description')}
                </p>
              </div>
              <details className="mt-4 rounded-xl border border-[var(--border-primary)] p-3">
                <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
                  {t('ragEval.launch.technicalDetails')}
                </summary>
                <div className="mt-3">
                  <ReportJsonBlock value={latestRun} />
                </div>
              </details>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">{t('ragEval.report.summaryTitle')}</h3>
              <ReportSummaryCard report={latestReport} />
              <details className="mt-4 rounded-xl border border-[var(--border-primary)] p-3">
                <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
                  {t('ragEval.report.technicalDetails')}
                </summary>
                <div className="mt-3">
                  <ReportJsonBlock value={Object.keys(latestReport).length ? latestReport : null} />
                </div>
              </details>
            </div>
          </div>
        )}
      </section>

      <ActionableResultsPanel
        results={actionableResults}
        executionSummary={lastActionExecutionSummary}
        executingResultId={executingResultId}
        onExecute={(resultId) => executeActionsMutation.mutate(resultId)}
      />


      <QuestionReviewDrawer
        key={selectedReviewQuestion?.question_id || 'closed'}
        question={selectedReviewQuestion}
        group={selectedReviewGroup}
        mutating={reviewQuestionMutation.isPending || editQuestionMutation.isPending}
        onClose={() => {
          setSelectedReviewQuestion(null);
          setSelectedReviewGroup(null);
        }}
        onAccept={(questionId) => reviewQuestionMutation.mutate({ questionId, status: 'accepted' })}
        onReject={(questionId) => reviewQuestionMutation.mutate({ questionId, status: 'rejected' })}
        onEdit={(questionId, value) => editQuestionMutation.mutate({ questionId, question: value })}
      />
    </div>
  );
};
