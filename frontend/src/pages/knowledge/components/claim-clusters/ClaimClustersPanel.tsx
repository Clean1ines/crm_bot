import React, { type ReactNode } from 'react';

import { ClaimClusterRow } from './ClaimClusterRow';
import { FinalCompactedFactsPanel } from './FinalCompactedFactsPanel';
import type { ClaimClustersView } from './claimClusterTypes';

type ClaimClustersPanelSlots = {
  summary: ReactNode;
  details: ReactNode;
};

type ClaimClustersPanelProps = {
  view: ClaimClustersView;
  formatNumber: (value: number) => string;
  children?: (slots: ClaimClustersPanelSlots) => ReactNode;
};

export const ClaimClustersPanel: React.FC<ClaimClustersPanelProps> = ({
  view,
  formatNumber,
  children,
}) => {
  const summary = view.clusters.length > 0 ? (
    <div className={`min-w-0 rounded-xl border p-3 ${view.compaction.panelTone}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium text-[var(--text-primary)]">Объединение знаний</div>
          <div className="mt-1 text-[var(--text-secondary)]">
            {view.compaction.userSummary}
          </div>
        </div>
        <div className="rounded-full bg-[var(--surface-elevated)] px-2.5 py-1 font-medium text-[var(--text-primary)]">
          {formatNumber(view.compaction.progressPercent)}% кластеров готово
        </div>
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--surface-elevated)]">
        <div
          className="h-full rounded-full bg-emerald-500 transition-[width]"
          style={{ width: `${view.compaction.progressPercent}%` }}
        />
      </div>

      <div className="mt-3 grid gap-2 [grid-template-columns:repeat(auto-fit,minmax(120px,1fr))]">
        {[
          ['В очереди', view.compaction.ready, 'text-slate-600 dark:text-slate-300'],
          ['Обрабатывается', view.compaction.leased, 'text-sky-700 dark:text-sky-300'],
          ['Готово', view.compactedClusterCount, 'text-emerald-700 dark:text-emerald-300'],
          ['Нужно внимание', view.compaction.attention, 'text-amber-700 dark:text-amber-300'],
        ].map(([label, value, tone]) => (
          <div
            key={String(label)}
            className="rounded-lg bg-[var(--surface-elevated)] px-2.5 py-2"
          >
            <div className={`font-medium ${String(tone)}`}>{label}</div>
            <div className="mt-0.5 text-lg font-semibold text-[var(--text-primary)]">
              {formatNumber(Number(value))}
            </div>
          </div>
        ))}
      </div>

      {view.compaction.attempts.length > 0 && (
        <section className="mt-3 rounded-lg bg-[var(--surface-elevated)] p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="font-medium text-[var(--text-primary)]">
                Ход объединения
              </div>
              <div className="mt-1 text-[var(--text-muted)]">
                Последние попытки ИИ по объединению похожих утверждений.
              </div>
            </div>
            <div className="rounded-full bg-[var(--surface-secondary)] px-2.5 py-1 text-[var(--text-secondary)]">
              {formatNumber(view.compaction.attempts.length)} попыток
            </div>
          </div>

          <div className="mt-3 space-y-2">
            {view.compaction.attempts.slice(-10).map((attempt) => (
              <div
                key={attempt.key}
                className={`rounded-lg border px-3 py-2 ${attempt.toneClassName}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-medium">
                    Попытка {formatNumber(attempt.attemptNumber)}
                  </div>
                  <div className="rounded-full bg-[var(--surface-elevated)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-primary)]">
                    {attempt.statusLabel}
                  </div>
                </div>
                <div className="mt-1 text-[var(--text-secondary)]">
                  {attempt.modelName || 'модель не указана'}
                  {' · '}
                  {attempt.tokenCount > 0
                    ? `${formatNumber(attempt.tokenCount)} токенов`
                    : 'токены пока не записаны'}
                </div>
                {attempt.errorMessage && (
                  <div className="mt-1 text-[var(--text-secondary)]">
                    {attempt.errorMessage}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {view.extractedFacts.length > 0 && (
        <section className="mt-3 rounded-lg bg-[var(--surface-elevated)] p-3">
          <div className="font-medium text-[var(--text-primary)]">
            Извлечённые факты: {formatNumber(view.extractedFacts.length)}
          </div>
          <div className="mt-2 max-h-64 space-y-2 overflow-y-auto pr-1">
            {view.extractedFacts.map((fact, index) => (
              <div
                key={fact.key}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] px-3 py-2 text-[var(--text-secondary)]"
              >
                <span className="mr-2 text-[var(--text-muted)]">
                  {formatNumber(index + 1)}.
                </span>
                {fact.text}
              </div>
            ))}
          </div>
        </section>
      )}

      <FinalCompactedFactsPanel facts={view.finalFacts} formatNumber={formatNumber} />

      <div className="mt-3 text-[11px] text-[var(--text-muted)]">
        Кластеров: {formatNumber(view.clusters.length)}
        {' · '}завершено задач: {formatNumber(view.compaction.done)}
        {' · '}итоговых фактов: {formatNumber(view.compaction.previewCount)}
        {view.compaction.llmAttemptCount > 0
          ? ` · запросов ИИ: ${formatNumber(view.compaction.llmAttemptCount)}`
          : ''}
        {view.compaction.succeededAttemptCount > 0
          ? ` · успешно ${formatNumber(view.compaction.succeededAttemptCount)}`
          : ''}
        {view.compaction.runningAttemptCount > 0
          ? ` · выполняется ${formatNumber(view.compaction.runningAttemptCount)}`
          : ''}
        {view.compaction.tokens > 0
          ? ` · ${formatNumber(view.compaction.tokens)} токенов`
          : ''}
      </div>
    </div>
  ) : null;

  const details = view.clusters.length > 0 ? (
    <details
      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3"
      open
    >
      <summary className="cursor-pointer list-none">
        <span className="flex flex-wrap items-center justify-between gap-2">
          <span>
            <span className="font-medium text-[var(--text-primary)]">
              Кластеры утверждений
            </span>
            <span className="ml-2 text-xs text-[var(--text-muted)]">
              Claim Compaction · {formatNumber(view.clusters.length)} кл.
            </span>
          </span>
          <span className="rounded-full bg-[var(--control-bg)] px-2.5 py-1 text-xs text-[var(--text-secondary)]">
            {formatNumber(view.compaction.llmAttemptCount)} попыток
          </span>
        </span>
      </summary>

      <div className="mt-2 space-y-1.5">
        {view.clusters.length === 0 && (
          <div className="rounded-lg border border-dashed border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--text-muted)]">
            Кластеры ещё не сформированы.
          </div>
        )}
        {view.clusters.map((cluster, clusterIndex) => (
          <ClaimClusterRow
            key={cluster.cluster_ref}
            cluster={cluster}
            clusterIndex={clusterIndex}
            attempts={view.compaction.attempts}
            formatNumber={formatNumber}
          />
        ))}
      </div>
    </details>
  ) : null;

  if (children) {
    return <>{children({ summary, details })}</>;
  }

  return (
    <>
      {summary}
      {details}
    </>
  );
};
