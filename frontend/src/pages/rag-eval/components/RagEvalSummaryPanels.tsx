import { t } from '@shared/i18n';
import { Loader2 } from 'lucide-react';
import React from 'react';
import type { RagEvalResultSummary } from '@shared/api/modules/ragEval';
import { MetricPill, ReportList } from './RagEvalReportComponents';
import { formatNumber } from '../lib/ragEvalProgress';
import { asStringList, formatResultScore, parseJsonValue, readinessLabel } from '../lib/ragEvalResults';
import { resultStatusClass, resultStatusLabel } from '../lib/ragEvalReviewPresentation';

const getRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
);

const asNumber = (value: unknown, fallback = 0): number => (
  typeof value === 'number' && Number.isFinite(value) ? value : fallback
);

export const ReportSummaryCard: React.FC<{ report: Record<string, unknown> }> = ({ report }) => {
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


export const RagEvalResultsPanel: React.FC<{
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
                    <div>{t('ragEval.results.latencyPrefix')} {typeof result.latency_ms === 'number' ? `${result.latency_ms} мс` : '—'}</div>
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
