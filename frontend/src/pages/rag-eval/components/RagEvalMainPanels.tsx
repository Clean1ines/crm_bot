import { t } from '@shared/i18n';
import { Loader2, RotateCcw } from 'lucide-react';
import React from 'react';
import type {
  KnowledgeEditActionExecutionSummary,
  RagEvalActionableResult,
} from '@shared/api/modules/ragEval';
import { formatNumber } from '../lib/ragEvalProgress';
import { actionTypeDescription, actionTypeLabel, formatResultScore, resultProblemLabel, riskLabel } from '../lib/ragEvalResults';

interface ActionableResultsPanelProps {
  results: RagEvalActionableResult[];
  executionSummary: KnowledgeEditActionExecutionSummary | null;
  executingResultId: string | null;
  onExecute: (resultId: string) => void;
}

export const ActionableResultsPanel: React.FC<ActionableResultsPanelProps> = ({
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
