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

import { knowledgeApi } from '@shared/api/modules/knowledge';
import {
  ragEvalApi,
  type KnowledgeEditActionExecutionSummary,
  type RagEvalActionableResult,
  type RagEvalDocumentStatusResponse,
  type RagEvalFullRunAcceptedResponse,
  type RagEvalJob,
  type RagEvalJobProgressResponse,
  type RagEvalJobsResponse,
  type RagEvalProgressPayload,
} from '@shared/api/modules/ragEval';

interface Document {
  id: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processing' | 'processed' | 'error';
  chunk_count: number;
  created_at: string;
}

const ACTIVE_JOB_STATUSES = new Set(['pending', 'processing', 'running', 'retrying', 'running_or_locked']);
const ACTIVE_RUN_STATUSES = new Set(['created', 'pending', 'processing', 'generating', 'ready', 'running', 'paused']);
const ERROR_VISIBLE_JOB_STATUSES = new Set(['failed', 'cancelled']);
const PAUSED_STATUSES = new Set(['paused', 'manual_pause', 'manual-pause']);
const TERMINAL_JOB_STATUSES = new Set(['completed', 'done', 'succeeded', 'success', 'failed', 'cancelled']);

const formatNumber = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);

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
  if (stage === 'queued') return 'Ждёт очереди';
  if (stage === 'started') return 'Запускаем проверку';
  if (stage === 'dataset_generation') return 'Готовим вопросы по документу';
  if (stage === 'answer_generation') return 'Проверяем ответы бота';
  if (stage === 'running') return 'Идёт проверка';
  if (stage === 'completed' || stage === 'done') return 'Готово';
  if (stage === 'cancelled') return 'Остановлено';
  if (stage === 'paused') return 'На паузе';
  if (stage === 'failed') return 'Ошибка';
  return stage || 'Ожидание';
};

const statusLabel = (status: string): string => {
  if (status === 'pending') return 'В очереди';
  if (status === 'processing' || status === 'running') return 'В работе';
  if (status === 'paused') return 'На паузе';
  if (status === 'completed' || status === 'done' || status === 'succeeded' || status === 'success') return 'Готово';
  if (status === 'cancelled') return 'Остановлено';
  if (status === 'failed') return 'Ошибка';
  return status || 'Ожидание';
};

const progressMessage = (progress: RagEvalProgressPayload, stage: string): string => {
  const rawMessage = typeof progress.message === 'string' ? progress.message : '';
  if (stage === 'dataset_generation') return 'Система читает фрагменты документа и составляет контрольные вопросы.';
  if (stage === 'answer_generation') return 'Система задаёт эти вопросы боту, ищет подходящие фрагменты и оценивает ответы.';
  if (stage === 'paused') return 'Пауза включена. Текущий запрос может завершиться, новые вопросы не начнутся до продолжения.';
  if (stage === 'cancelled') return 'Задача остановлена пользователем.';
  if (stage === 'failed') return rawMessage || 'Проверка завершилась с ошибкой.';
  if (stage === 'completed' || stage === 'done') return 'Отчёт готов.';
  return rawMessage || 'Проверка выполняется.';
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
          const targetEntryId = String(action.target_entry_id || '').trim();

          return {
            action_type: String(action.action_type || '').trim(),
            target_entry_id: targetEntryId || null,
            reason: String(action.reason || '').trim(),
            payload: getRecord(action.payload),
          };
        }).filter((action) => action.action_type)
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

const actionTypeLabel = (value: string): string => {
  if (value === 'attach_question_to_entry') return 'Добавить формулировку клиента';
  if (value === 'rebuild_entry_embedding') return 'Обновить поисковое представление записи';
  if (value === 'rerun_eval') return 'Запустить повторную проверку';
  if (value === 'create_entry_from_failure') return 'Создать новую запись вручную';
  return value || 'Действие';
};

const actionTypeDescription = (value: string): string => {
  if (value === 'attach_question_to_entry') {
    return 'Система добавит вопрос клиента к уже существующей записи базы знаний, чтобы бот лучше находил её по такой формулировке.';
  }

  if (value === 'rebuild_entry_embedding') {
    return 'Система обновит поисковый образ записи после изменений, чтобы она корректнее участвовала в поиске.';
  }

  if (value === 'rerun_eval') {
    return 'Система поставит повторную проверку документа в очередь, чтобы проверить результат после исправлений.';
  }

  if (value === 'create_entry_from_failure') {
    return 'Это действие требует ручного разбора: система не будет автоматически создавать новую запись базы знаний.';
  }

  return 'Система подготовила действие для улучшения базы знаний.';
};

const formatResultScore = (score: number): string => {
  const normalized = score > 1 ? score : score * 100;
  return `${Math.round(normalized)}%`;
};

const riskLabel = (value: string): string => {
  if (value === 'high') return 'Высокий риск недостоверного ответа';
  if (value === 'medium') return 'Средний риск недостоверного ответа';
  if (value === 'low') return 'Низкий риск недостоверного ответа';
  return 'Риск не определён';
};

const resultProblemLabel = (result: RagEvalActionableResult): string => {
  if (result.wrong_entry_top1 && !result.answer_supported) {
    return 'Бот опирается не на ту запись базы знаний, поэтому ответ может быть неправильным.';
  }

  if (result.wrong_entry_top1) {
    return 'Первым найден не тот фрагмент. Поиск нужно направить к правильной записи.';
  }

  if (!result.answer_supported) {
    return 'Ответ не подтверждён найденной базой знаний. Нужно усилить связь вопроса с правильной записью.';
  }

  if (result.hallucination_risk === 'high') {
    return 'Проверка увидела высокий риск недостоверного ответа. Лучше применить предложенные исправления и запустить повторную проверку.';
  }

  if (!result.should_answer_passed) {
    return 'Поведение бота не совпало с ожидаемым: нужно уточнить базу знаний или правила ответа.';
  }

  return 'Система нашла место, где база знаний может отвечать лучше.';
};

const readinessLabel = (value: unknown): string => {
  const readiness = String(value || '').trim();
  if (readiness === 'ready') return 'Готово к использованию';
  if (readiness === 'needs_review') return 'Нужна ручная проверка';
  if (readiness === 'not_ready') return 'Не готово к работе';
  return readiness || 'Нет статуса';
};

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
      <p className="mt-2 text-sm text-[var(--text-muted)]">Нет данных.</p>
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
            Предложенные исправления базы знаний
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]">
            Здесь показаны проблемы, которые проверка нашла в ответах бота. Кнопка применяет
            только безопасные изменения: добавляет недостающие формулировки к существующим
            записям, обновляет поисковое представление или запускает повторную проверку.
            Действия, где нужно вручную создать новую запись, не применяются автоматически.
          </p>
        </div>
      </div>

      {executionSummary && (
        <div className="mb-4 rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] p-4">
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            Последнее применение исправлений
          </div>
          <div className="mt-2 grid gap-2 text-sm text-[var(--text-secondary)] sm:grid-cols-2 lg:grid-cols-4">
            <div>Применено: {formatNumber(executionSummary.applied_actions)}</div>
            <div>Пропущено: {formatNumber(executionSummary.skipped_actions)}</div>
            <div>Нужна ручная проверка: {formatNumber(executionSummary.rejected_actions)}</div>
            <div>Ошибок: {formatNumber(executionSummary.failed_actions)}</div>
          </div>
          {executionSummary.queued_rerun_job_ids.length > 0 && (
            <p className="mt-2 text-sm text-[var(--text-muted)]">
              Повторная проверка запущена. Её прогресс появится выше на этой странице.
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
                      Уверенность проверки: {formatResultScore(result.score)}
                    </span>
                    <span className="rounded-full bg-[var(--surface-elevated)] px-2 py-1 text-xs font-medium text-[var(--text-secondary)]">
                      {riskLabel(result.hallucination_risk)}
                    </span>
                    {result.wrong_entry_top1 && (
                      <span className="rounded-full bg-red-500/10 px-2 py-1 text-xs font-medium text-red-500">
                        найден не тот источник
                      </span>
                    )}
                    {!result.answer_supported && (
                      <span className="rounded-full bg-red-500/10 px-2 py-1 text-xs font-medium text-red-500">
                        ответ не подтверждён
                      </span>
                    )}
                  </div>

                  <div>
                    <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
                      Проверочный вопрос
                    </div>
                    <div className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                      {result.question || 'Без текста вопроса'}
                    </div>
                  </div>

                  <div className="rounded-lg bg-[var(--surface-elevated)] p-3">
                    <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
                      Что не так
                    </div>
                    <p className="mt-1 text-sm text-[var(--text-secondary)]">
                      {resultProblemLabel(result)}
                    </p>
                  </div>

                  <div className="rounded-lg bg-[var(--surface-elevated)] p-3">
                    <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
                      Что будет сделано
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
                                  Новая формулировка для поиска: “{payloadQuestion}”
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="mt-2 text-sm text-[var(--text-muted)]">
                        Для этой проблемы нет автоматического исправления. Нужен ручной разбор.
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
                  {isExecuting ? 'Применяю исправления...' : 'Применить предложенные исправления'}
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
    return <p className="text-sm text-[var(--text-muted)]">Отчёт ещё не сформирован.</p>;
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
          <h3 className="text-base font-semibold text-[var(--text-primary)]">Человекочитаемый отчёт</h3>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Это итог проверки: насколько база знаний помогает боту находить правильные фрагменты и отвечать без выдуманных фактов.
          </p>
        </div>
        <div className="rounded-xl bg-[var(--surface-elevated)] px-4 py-3 text-right shadow-[var(--shadow-card)]">
          <div className="text-2xl font-semibold text-[var(--text-primary)]">{score}/100</div>
          <div className="text-xs text-[var(--text-muted)]">{readinessLabel(report.readiness)}</div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <MetricPill label="Всего вопросов" value={total || '—'} />
        <MetricPill label="Первый найденный фрагмент" value={`${top1Rate}%`} />
        <MetricPill label="Первые 3 фрагмента" value={`${top3Rate}%`} />
        <MetricPill label="Первые 5 фрагментов" value={`${top5Rate}%`} />
        <MetricPill label="Ответы подтверждены" value={`${answerSupportedRate}%`} />
        <MetricPill label="Риск выдуманного ответа" value={highHallucinationRisk} />
        <MetricPill label="Первый фрагмент оказался неверным" value={wrongChunkTop1} />
      </div>

      <ReportList title="Сильные стороны" items={strengths} />
      <ReportList title="Проблемы" items={problems} />
      <ReportList title="Что делать дальше" items={recommendations} />

      {typeof report.markdown === 'string' && report.markdown.trim() && (
        <details className="rounded-xl bg-[var(--surface-elevated)] p-3 text-sm text-[var(--text-secondary)] shadow-[var(--shadow-card)]">
          <summary className="cursor-pointer font-medium text-[var(--text-primary)]">Показать markdown-отчёт</summary>
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
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Прогресс проверки</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Активных или недавних задач для выбранного документа пока нет.
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
  const generatedQuestions = asNumber(mergedProgress.generated_questions);
  const targetQuestions = asNumber(mergedProgress.target_questions);
  const processedQuestions = asNumber(mergedProgress.processed_questions);
  const totalQuestions = asNumber(mergedProgress.total_questions || targetQuestions);
  const processedBatches = asNumber(mergedProgress.processed_batches);
  const totalBatches = asNumber(mergedProgress.total_batches);
  const sourceChunkCount = asNumber(mergedProgress.source_chunk_count);

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
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Прогресс проверки</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Текущая проверка выбранного документа.
            </p>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Статус: <span className="font-semibold text-[var(--text-primary)]">{statusLabel(effectiveStatus || job.status)}</span>
              {' · '}
              Сейчас: <span className="font-semibold text-[var(--text-primary)]">{stageLabel(stage)}</span>
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
            Пауза
          </button>
          <button
            type="button"
            onClick={onResume}
            disabled={!paused || isMutating}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-primary)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw className="h-4 w-4" />
            Продолжить
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={terminal || (!active && !paused) || isMutating}
            className="inline-flex items-center gap-2 rounded-xl border border-red-500/40 px-3 py-2 text-sm font-medium text-red-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Square className="h-4 w-4" />
            Отменить
          </button>
        </div>
      </div>

      <div className="mb-4">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="text-[var(--text-muted)]">Выполнено</span>
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

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatPill label="Вопросы готовы" value={targetQuestions ? `${generatedQuestions}/${targetQuestions}` : generatedQuestions} />
        <StatPill label="Ответы проверены" value={totalQuestions ? `${processedQuestions}/${totalQuestions}` : processedQuestions} />
        <StatPill label="Группы фрагментов" value={totalBatches ? `${processedBatches}/${totalBatches}` : processedBatches} />
        <StatPill label="Фрагменты" value={sourceChunkCount || '—'} />
        <StatPill label="Попытки" value={`${job.attempts}/${job.max_attempts}`} />
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
    () => documents.filter((doc) => doc.status === 'processed' && doc.chunk_count > 0),
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
      if (!activeDocumentId) throw new Error('Нет обработанного документа для проверки');

        return await ragEvalApi.runFullDocumentEval(activeDocumentId);
    },
    onSuccess: async (result) => {
      setLastQueued(result);
      setLastActionExecutionSummary(null);
      toast.success('Проверка запущена. Прогресс появится на этой странице.');
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось поставить проверку в очередь');
    },
  });

  const pauseMutation = useMutation({
    mutationFn: async (jobId: string) => ragEvalApi.pauseJob(jobId),
    onSuccess: (result) => {
      applyJobMutationResult(result.job);
      toast.success('Пауза включена');
      void invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось поставить задачу на паузу');
    },
  });

  const resumeMutation = useMutation({
    mutationFn: async (jobId: string) => ragEvalApi.resumeJob(jobId),
    onSuccess: (result) => {
      applyJobMutationResult(result.job);
      toast.success('Проверка продолжена');
      void invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось продолжить задачу');
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async (jobId: string) => ragEvalApi.cancelJob(jobId),
    onSuccess: (result) => {
      setLastQueued(null);
      applyJobMutationResult(result.job);
      toast.success('Проверка остановлена');
      void invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось отменить задачу');
    },
  });

  const executeActionsMutation = useMutation<KnowledgeEditActionExecutionSummary, unknown, string>({
    mutationFn: async (resultId: string) => ragEvalApi.executeResultActions(resultId),
    onSuccess: async (summary) => {
      setLastActionExecutionSummary(summary);

      const rerunMessage = summary.queued_rerun_job_ids.length
        ? ', повторная проверка поставлена в очередь'
        : '';

      toast.success(
        `Исправления применены: ${summary.applied_actions}; ручная проверка: ${summary.rejected_actions}; ошибок: ${summary.failed_actions}${rerunMessage}`,
      );
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось применить предложенные исправления');
    },
  });

  const latestReportPayload = statusQuery.data?.report ?? null;
  const latestReport = getRecord(latestReportPayload);
  const actionableResults = useMemo(() => getActionableResults(latestReport), [latestReport]);
  const latestRun = statusQuery.data?.run ?? null;
  const latestRunRecord = getRecord(latestRun);
  const progressJob = progressQuery.data?.job ?? visibleJob;
  const progressPayload = progressJob?.progress ?? visibleJob?.progress ?? (
    progressJob
      ? { percent: progressJob.percent, status: getJobStatus(progressJob) }
      : null
  );
  const isControlMutating = pauseMutation.isPending || resumeMutation.isPending || cancelMutation.isPending;
  const executingResultId = executeActionsMutation.isPending
    ? executeActionsMutation.variables ?? null
    : null;

  if (documentsQuery.isLoading) {
    return (
      <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">
        Загрузка документов...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">
          Проверка качества базы знаний
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-[var(--text-muted)]">
          Полная проверка документа после обработки базы знаний. Страница показывает, где бот отвечает уверенно,
          где ему не хватает знаний и какие безопасные исправления можно применить без ручного доступа к базе.
        </p>
      </div>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-5 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Запуск полной проверки</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Система читает документ, составляет проверочные вопросы и проверяет, насколько бот находит нужные фрагменты.
            </p>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">Документ</span>
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
                  {doc.file_name} · {doc.chunk_count} фрагментов
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
            Запустить
          </button>
        </div>

        {activeDocument && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-muted)]">
            <FileText className="h-4 w-4" />
            <span>{activeDocument.file_name}</span>
            <span>·</span>
            <span>{formatNumber(activeDocument.chunk_count)} фрагментов</span>
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

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <BarChart3 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Последний результат проверки</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Здесь остаётся статистика после завершения, отмены или ошибки.
            </p>
          </div>
        </div>

        {statusQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            Загружаю статус...
          </div>
        ) : statusQuery.error ? (
          <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-500">
            <XCircle className="h-4 w-4" />
            Не удалось загрузить статус проверки.
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">Запуск проверки</h3>
              <div className="rounded-xl bg-[var(--control-bg)] p-4">
                <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Статус запуска</div>
                <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                  {statusLabel(String(latestRunRecord.status || ''))}
                </div>
                <p className="mt-2 text-sm text-[var(--text-muted)]">
                  Здесь показано состояние последней проверки без служебного JSON.
                </p>
              </div>
              <details className="mt-4 rounded-xl border border-[var(--border-primary)] p-3">
                <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
                  Технические подробности запуска
                </summary>
                <div className="mt-3">
                  <ReportJsonBlock value={latestRun} />
                </div>
              </details>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">Итоги</h3>
              <ReportSummaryCard report={latestReport} />
              <details className="mt-4 rounded-xl border border-[var(--border-primary)] p-3">
                <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
                  Технические подробности отчёта
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
    </div>
  );
};
