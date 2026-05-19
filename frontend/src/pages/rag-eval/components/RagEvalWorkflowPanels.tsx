import React from 'react';
import { ReportJsonBlock } from './RagEvalReportComponents';
import { formatNumber } from '../lib/ragEvalProgress';

export const ApplyAcceptedQuestionsPanel: React.FC<{ acceptedCount: number; onApply: () => void; applying: boolean }> = ({ acceptedCount, onApply, applying }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">Apply / Improve Workflow</h3>
        <p className="mt-1 text-sm text-[var(--text-muted)]">Eval не улучшает базу сам: применяются только вопросы, которые человек принял.</p>
      </div>
      <button type="button" onClick={onApply} disabled={!acceptedCount || applying} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
        {applying ? 'Применяем...' : `Добавить к фрагментам (${formatNumber(acceptedCount)})`}
      </button>
    </div>
  </section>
);

export const TechnicalDiagnosticsDisclosure: React.FC<{ value: unknown }> = ({ value }) => (
  <details className="rounded-2xl border border-[var(--border-primary)] bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
    <summary className="cursor-pointer text-sm font-semibold text-[var(--text-primary)]">Техническая диагностика</summary>
    <div className="mt-3"><ReportJsonBlock value={value} /></div>
  </details>
);
