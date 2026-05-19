import { t } from '@shared/i18n';
import { BarChart3, Loader2, Pause, RotateCcw, Square } from 'lucide-react';
import React from 'react';
import type { RagEvalJob, RagEvalProgressPayload } from '@shared/api/modules/ragEval';
import { StatPill } from './RagEvalReportComponents';
import { formatDurationMs, progressMessage, stageLabel, statusLabel } from '../lib/ragEvalProgress';
import { getJobStatus, isJobActive, isJobPaused, isJobTerminal } from '../lib/ragEvalStatus';
import { asNumber, clampPercent, timestampMs } from '../lib/ragEvalRuntimeUtils';

const ERROR_VISIBLE_JOB_STATUSES = new Set(['failed', 'cancelled']);

export const JobProgressCard: React.FC<{
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
            <p className="mt-1 text-sm text-[var(--text-muted)]">{t('ragEval.progress.noRecentJobs')}</p>
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
            <p className="mt-1 text-sm text-[var(--text-muted)]">{t('ragEval.progress.currentDocument')}</p>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t('ragEval.progress.statusPrefix')} <span className="font-semibold text-[var(--text-primary)]">{statusLabel(effectiveStatus || job.status)}</span>
              {' · '}
              {t('ragEval.progress.nowPrefix')} <span className="font-semibold text-[var(--text-primary)]">{stageLabel(stage)}</span>
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={onPause} disabled={!active || paused || isMutating} className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"><Pause className="h-4 w-4" />{t('ragEval.actions.pause')}</button>
          <button type="button" onClick={onResume} disabled={!paused || isMutating} className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"><RotateCcw className="h-4 w-4" />{t('ragEval.actions.resume')}</button>
          <button type="button" onClick={onCancel} disabled={terminal || (!active && !paused) || isMutating} className="inline-flex items-center gap-2 rounded-xl border border-red-500/40 px-3 py-2 text-sm font-medium text-red-500 disabled:cursor-not-allowed disabled:opacity-50"><Square className="h-4 w-4" />{t('ragEval.actions.cancel')}</button>
        </div>
      </div>

      <div className="mb-4"><div className="mb-2 flex items-center justify-between text-sm"><span className="text-[var(--text-muted)]">{t('ragEval.progress.completed')}</span><span className="font-semibold text-[var(--text-primary)]">{percent}%</span></div><div className="h-3 overflow-hidden rounded-full bg-[var(--control-bg)]"><div className="h-full rounded-full bg-[var(--accent-primary)] transition-all duration-500" style={{ width: `${percent}%` }} /></div></div>
      <p className="mb-4 rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-secondary)]">{progressMessage(mergedProgress, stage)}</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatPill label="Фрагменты: готовы к ревью / всего" value={entriesTotal ? `${entriesReady}/${entriesTotal}` : entriesReady || '—'} />
        <StatPill label="Фрагменты в очереди" value={entriesQueued} />
        <StatPill label="Генерируем фрагментов" value={entriesGenerating || activeGenerationWorkers} />
        <StatPill label="Проверяем поиск по фрагментам" value={entriesChecking} />
        <StatPill label="Фрагменты с ошибкой" value={entriesFailed} />
        <StatPill label="Вопросы созданы" value={generatedQuestions} />
        <StatPill label="Вопросы проверены" value={totalQuestions ? `${processedQuestions}/${totalQuestions}` : processedQuestions} />
        <StatPill label="Вопросы в очереди" value={queuedQuestions} />
        <StatPill label="Активные проверки поиска" value={activeRetrievalWorkers} />
        <StatPill label="Проблемы поиска" value={failedRetrievalCount} />
        <StatPill label="Предложено улучшений" value={actionableImprovementsCount} />
        <StatPill label="Скорость: вопросов/мин" value={questionsPerMinute || '—'} />
        <StatPill label="Скорость: фрагментов/мин" value={entriesPerMinute || '—'} />
        <StatPill label="Последнее обновление" value={`${lastUpdateSecondsAgo} сек назад`} />
        <StatPill label="Модель вопросов" value={questionModel || '—'} />
        <StatPill label="Fallback использован" value={`${fallbackUsedCount} раз`} />
        <StatPill label={t('ragEval.stats.elapsed')} value={startedAt === null ? '—' : formatDurationMs(elapsedMs)} />
        <StatPill label={t('ragEval.stats.jsonFailures')} value={jsonParseFailures} />
        <StatPill label={t('ragEval.stats.providerFailures')} value={providerFailures} />
        <StatPill label={t('ragEval.stats.retries')} value={retryCount} />
        <StatPill label={t('ragEval.stats.fragments')} value={sourceChunkCount || entriesTotal || '—'} />
        <StatPill label={t('ragEval.stats.attempts')} value={`${job.attempts}/${job.max_attempts}`} />
      </div>

      {ERROR_VISIBLE_JOB_STATUSES.has(getJobStatus(job)) && job.error && (
        <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">{job.error}</div>
      )}
    </section>
  );
};
