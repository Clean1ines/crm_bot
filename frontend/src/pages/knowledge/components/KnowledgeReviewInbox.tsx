import { AlertTriangle, CheckCircle2, Clock3, FileWarning, Inbox, UploadCloud } from 'lucide-react';
import React from 'react';
import { t } from '@shared/i18n';

import type { KnowledgeReviewTask, KnowledgeReviewTaskSeverity } from '../viewModel/reviewInbox';

const severityStyles: Record<KnowledgeReviewTaskSeverity, string> = {
  critical: 'border-[var(--accent-danger-bg)] bg-[var(--accent-danger-bg)]/20 text-[var(--accent-danger-text)]',
  warning: 'border-[var(--accent-warning-bg)] bg-[var(--accent-warning-bg)]/25 text-[var(--accent-warning-text)]',
  info: 'border-[var(--surface-secondary)] bg-[var(--surface-secondary)] text-[var(--text-primary)]',
  ready: 'border-[var(--accent-success-bg)] bg-[var(--accent-success-bg)]/20 text-[var(--accent-success-text)]',
};

const iconBySeverity = {
  critical: FileWarning,
  warning: AlertTriangle,
  info: Clock3,
  ready: CheckCircle2,
} satisfies Record<KnowledgeReviewTaskSeverity, React.ComponentType<{ className?: string }>>;

export const KnowledgeReviewInbox: React.FC<{
  tasks: KnowledgeReviewTask[];
  onTaskAction: (task: KnowledgeReviewTask) => void;
}> = ({ tasks, onTaskAction }) => (
  <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5">
    <div className="mb-4 flex items-center gap-3">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--text-muted)]">
        <Inbox className="h-5 w-5" />
      </span>
      <div>
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          {t('knowledge.reviewInbox.title')}
        </h2>
      </div>
    </div>

    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
      {tasks.map((task) => {
        const Icon = iconBySeverity[task.severity];

        return (
          <article
            key={task.id}
            className={`flex flex-col gap-3 rounded-xl border p-4 ${severityStyles[task.severity]}`}
          >
            <div className="flex items-start gap-3">
              <Icon className="mt-0.5 h-5 w-5 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">
                    {t(task.titleKey)}
                  </h3>
                  {typeof task.count === 'number' && (
                    <span className="rounded-full bg-[var(--surface-elevated)] px-2 py-0.5 text-xs font-semibold text-[var(--text-primary)] shadow-[var(--shadow-sm)]">
                      {task.count}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm opacity-90">
                  {t(task.descriptionKey)}
                </p>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => onTaskAction(task)}
                className="inline-flex min-h-9 items-center gap-2 rounded-lg bg-[var(--surface-elevated)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--surface-secondary)]"
              >
                {task.action.kind === 'upload_document' && <UploadCloud className="h-4 w-4" />}
                {t(task.action.labelKey)}
              </button>
            </div>
          </article>
        );
      })}
    </div>
  </section>
);
