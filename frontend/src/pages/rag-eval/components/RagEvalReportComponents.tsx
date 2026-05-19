import { t } from '@shared/i18n';
import React from 'react';

export const ReportJsonBlock: React.FC<{ value: unknown }> = ({ value }) => (
  <pre className="max-h-[520px] overflow-auto rounded-xl bg-[var(--control-bg)] p-4 text-xs leading-relaxed text-[var(--text-secondary)]">
    {JSON.stringify(value ?? null, null, 2)}
  </pre>
);

export const MetricPill: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="rounded-xl bg-[var(--surface-elevated)] px-3 py-2 shadow-[var(--shadow-card)]">
    <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
    <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{value}</div>
  </div>
);

export const ReportList: React.FC<{ title: string; items: string[] }> = ({ title, items }) => (
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

export const StatPill: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="rounded-xl bg-[var(--control-bg)] px-3 py-2">
    <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
    <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{value}</div>
  </div>
);
