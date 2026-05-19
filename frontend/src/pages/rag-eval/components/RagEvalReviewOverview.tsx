import React from 'react';
import type { RagEvalReviewPayload } from '@shared/api/modules/ragEval';
import { StatPill } from './RagEvalReportComponents';
import { formatNumber } from '../lib/ragEvalProgress';

export const DocumentEvalOverviewCard: React.FC<{ review: RagEvalReviewPayload; documentName: string; onShowProblems: () => void }> = ({ review, documentName, onShowProblems }) => {
  const summary = review.summary;
  return (
    <section className="overflow-hidden rounded-3xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)] sm:p-7">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-[var(--accent-primary)]">Проверка завершена</p>
          <h2 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">Проверка поиска по документу</h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">{documentName}</p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[var(--accent-primary)]/10 px-3 py-1 text-sm font-semibold text-[var(--accent-primary)]">Статус: {summary.readiness}</span>
            <span className="rounded-full bg-[var(--control-bg)] px-3 py-1 text-sm font-semibold text-[var(--text-primary)]">Готовность: {summary.score} / 100</span>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">{summary.human_summary}</p>
        </div>
        <div className="rounded-2xl bg-[var(--control-bg)] p-4 text-center">
          <div className="text-4xl font-semibold text-[var(--text-primary)]">{summary.score}</div>
          <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">качество поиска</div>
        </div>
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <StatPill label="Фрагментов" value={formatNumber(summary.fragments_total)} />
        <StatPill label="Вопросов" value={formatNumber(summary.questions_total)} />
        <StatPill label="Проблем поиска" value={formatNumber(summary.problem_questions)} />
        <StatPill label="Найдено хорошо" value={formatNumber(summary.reliable_questions)} />
        <StatPill label="Нестабильно" value={formatNumber(summary.weak_questions)} />
        <StatPill label="Не найдено" value={formatNumber(summary.missing_questions)} />
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" onClick={onShowProblems} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white">Разобрать {formatNumber(summary.problem_questions)} проблем</button>
        <button type="button" className="rounded-xl border border-[var(--border-primary)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)]">Показать хорошие вопросы для добавления</button>
        <button type="button" className="rounded-xl border border-[var(--border-primary)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)]">Показать фрагменты, которые путаются</button>
      </div>
    </section>
  );
};

export const EvalProblemMap: React.FC<{ review: RagEvalReviewPayload }> = ({ review }) => (
  <section className="grid gap-4 lg:grid-cols-3">
    <div className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
      <h3 className="text-base font-semibold text-[var(--text-primary)]">Самые проблемные фрагменты</h3>
      <div className="mt-3 space-y-3">
        {review.problem_map.most_problematic_fragments.filter((group) => group.problem_count > 0).slice(0, 4).map((group) => (
          <div key={group.entry_id} className="rounded-xl bg-[var(--control-bg)] p-3">
            <div className="text-sm font-semibold text-[var(--text-primary)]">{group.title}</div>
            <div className="mt-1 text-xs text-[var(--text-muted)]">{formatNumber(group.question_count)} вопросов · {formatNumber(group.problem_count)} проблем</div>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">{group.issue_summary}</p>
          </div>
        ))}
      </div>
    </div>
    <div className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
      <h3 className="text-base font-semibold text-[var(--text-primary)]">Лучшие фрагменты</h3>
      <div className="mt-3 space-y-3">
        {review.problem_map.best_fragments.slice(0, 4).map((group) => (
          <div key={group.entry_id} className="rounded-xl bg-emerald-500/5 p-3">
            <div className="text-sm font-semibold text-[var(--text-primary)]">{group.title}</div>
            <div className="mt-1 text-xs text-emerald-600">{formatNumber(group.question_count)}/{formatNumber(group.question_count)} вопросов найдены правильно</div>
          </div>
        ))}
      </div>
    </div>
    <div className="rounded-2xl bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-card)]">
      <h3 className="text-base font-semibold text-[var(--text-primary)]">Типы проблем</h3>
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
