import { t } from '@shared/i18n';
import { BarChart3, Loader2, Pause, RotateCcw, Square } from 'lucide-react';
import React, { useState } from 'react';
import type { RagEvalJob, RagEvalProgressPayload, RagEvalReviewGroup, RagEvalReviewQuestion } from '@shared/api/modules/ragEval';
import { ReportJsonBlock, StatPill } from './RagEvalReportComponents';
import { asStringList } from '../lib/ragEvalResults';
import { REVIEW_FILTERS, REVIEW_SORTS, type EvalReviewFilter, type EvalReviewSort } from '../lib/ragEvalReviewFilters';
import { questionStatusClass, questionStatusIcon } from '../lib/ragEvalReviewPresentation';
import { formatDurationMs, formatNumber, progressMessage, stageLabel, statusLabel } from '../lib/ragEvalProgress';
import { getJobStatus, isJobActive, isJobPaused, isJobTerminal } from '../lib/ragEvalStatus';
import { asNumber, clampPercent, timestampMs } from '../lib/ragEvalRuntimeUtils';

const ERROR_VISIBLE_JOB_STATUSES = new Set(['failed', 'cancelled']);

export const EvalFiltersBar: React.FC<{
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
      Сортировка
      <select value={sort} onChange={(event) => onSortChange(event.target.value as EvalReviewSort)} className="mt-1 w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none">
        {REVIEW_SORTS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select>
    </label>
  </div>
);

const fragmentReviewStatusLabel = (value: RagEvalReviewGroup['review_status']): string => {
  if (value === 'queued') return 'Ожидает проверки';
  if (value === 'generating_questions') return 'Генерируем вопросы';
  if (value === 'checking_retrieval') return 'Проверяем поиск';
  if (value === 'ready_for_review') return 'Готов к ревью';
  if (value === 'failed') return 'Ошибка проверки';
  return 'Готов к ревью';
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

export const FragmentReviewCard: React.FC<{
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
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">Фрагмент · {group.title}</h3>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${fragmentReviewStatusClass(group.review_status)}`}>
            {fragmentReviewStatusLabel(group.review_status)}
          </span>
          <span className="text-sm text-[var(--text-muted)]">Статус поиска: {group.status}</span>
        </div>
        {group.review_status === 'failed' && group.error && (
          <p className="mt-2 text-sm text-red-500">{group.error}</p>
        )}
      </div>
      <span className="rounded-full bg-[var(--control-bg)] px-3 py-1 text-sm font-semibold text-[var(--text-primary)]">{formatNumber(group.problem_count)} проблем</span>
    </div>
    <div className="mt-4 rounded-xl bg-[var(--control-bg)] p-4">
      <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Ответ / знание</div>
      <p className="mt-2 line-clamp-4 text-sm leading-6 text-[var(--text-secondary)]">{group.content || 'Текст фрагмента не найден в текущем поисковом представлении.'}</p>
    </div>
    <div className="mt-4 grid gap-4 lg:grid-cols-2">
      <div>
        <div className="text-sm font-semibold text-[var(--text-primary)]">Уже есть вопросы</div>
        <ul className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
          {existingQuestions.slice(0, 4).map((item: string) => <li key={item}>— {item}</li>)}
          {!existingQuestions.length && <li className="text-[var(--text-muted)]">Нет сохранённых вопросов.</li>}
        </ul>
      </div>
      <div>
        <div className="text-sm font-semibold text-[var(--text-primary)]">Предложение системы</div>
        <ul className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
          {proposedImprovements.map((item: string) => <li key={item}>— {item}</li>)}
        </ul>
      </div>
    </div>
    <div className="mt-4 space-y-2">
      <div className="text-sm font-semibold text-[var(--text-primary)]">Сгенерированные вопросы</div>
      {questions.length === 0 && (
        <div className="rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-muted)]">
          Карточка появится здесь, когда вопросы фрагмента будут сгенерированы и проверены.
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
      <button type="button" onClick={() => firstQuestion && onOpenQuestion(firstQuestion, group)} className="rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">Рассмотреть вопросы</button>
      <button type="button" onClick={() => onAcceptGroup(group)} className="rounded-xl bg-[var(--accent-primary)] px-3 py-2 text-sm font-semibold text-white">Принять хорошие</button>
      <button type="button" className="rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">Пересобрать</button>
    </div>
  </article>
  );
};

export const QuestionReviewDrawer: React.FC<{
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
  const retrievedEntries = asRetrievedEntries(question.retrieved_entries);
  const proposedImprovements = asStringList(question.proposed_improvements);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <aside className="h-full w-full max-w-xl overflow-auto bg-[var(--surface-elevated)] p-5 shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-[var(--accent-primary)]">Вопрос-кандидат</p>
            <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">“{question.effective_question}”</h3>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg border border-[var(--border-primary)] px-3 py-1 text-sm text-[var(--text-primary)]">Закрыть</button>
        </div>
        <div className="mt-5 space-y-4">
          <div className="rounded-xl bg-[var(--control-bg)] p-4 text-sm text-[var(--text-secondary)]">
            <div>Тип: <span className="font-semibold text-[var(--text-primary)]">{question.question_type_label}</span></div>
            <div className="mt-1">Статус: <span className="font-semibold text-[var(--text-primary)]">{question.retrieval_status_label}</span></div>
            <div className="mt-1">Review state: <span className="font-semibold text-[var(--text-primary)]">{question.review.status}</span></div>
          </div>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">Ожидался фрагмент</h4>
            <p className="mt-2 rounded-xl bg-[var(--control-bg)] p-3 text-sm leading-6 text-[var(--text-secondary)]">{group.content || group.title}</p>
          </section>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">Что нашёл поиск</h4>
            <ol className="mt-2 space-y-2 text-sm text-[var(--text-secondary)]">
              {retrievedEntries.map((entry, index) => <li key={`${entry.id}-${index}`} className="rounded-xl bg-[var(--control-bg)] p-3">{index + 1}. {entry.title || entry.id}<p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">{entry.content}</p></li>)}
              {!retrievedEntries.length && <li className="rounded-xl bg-[var(--control-bg)] p-3">Поиск не вернул фрагменты.</li>}
            </ol>
          </section>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">Почему это проблема</h4>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{question.why_it_matters}</p>
          </section>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">Что можно сделать</h4>
            <ul className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
              {proposedImprovements.map((item: string) => <li key={item}>☑ {item}</li>)}
              <li>☐ Отклонить как плохой вопрос</li>
            </ul>
          </section>
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">Редактировать формулировку</h4>
            <textarea value={currentEditValue} onChange={(event) => setEditValue(event.target.value)} className="mt-2 min-h-24 w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-3 text-sm text-[var(--text-primary)] outline-none" />
          </section>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={mutating} onClick={() => onAccept(question.question_id)} className="rounded-xl bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Принять</button>
            <button type="button" disabled={mutating} onClick={() => onEdit(question.question_id, currentEditValue)} className="rounded-xl border border-[var(--border-primary)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] disabled:opacity-50">Сохранить редакцию</button>
            <button type="button" disabled={mutating} onClick={() => onReject(question.question_id)} className="rounded-xl border border-red-500/30 px-4 py-2 text-sm font-semibold text-red-500 disabled:opacity-50">Отклонить</button>
          </div>
          <details className="rounded-xl border border-[var(--border-primary)] p-3">
            <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">Диагностика</summary>
            <div className="mt-3"><ReportJsonBlock value={question.diagnostics} /></div>
          </details>
        </div>
      </aside>
    </div>
  );
};



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
        <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">
          {job.error}
        </div>
      )}
    </section>
  );
};
