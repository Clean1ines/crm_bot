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
  if (stage === 'dataset_generation') return 'Система читает чанки и составляет контрольные вопросы.';
  if (stage === 'answer_generation') return 'Система задаёт эти вопросы боту, ищет релевантные чанки и оценивает ответы.';
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

const readinessLabel = (value: unknown): string => {
  const readiness = String(value || '').trim();
  if (readiness === 'ready') return 'Готово к использованию';
  if (readiness === 'needs_review') return 'Нужна ручная проверка';
  if (readiness === 'not_ready') return 'Не готово к production';
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
            Это итог проверки: насколько база знаний помогает боту находить правильные чанки и отвечать без галлюцинаций.
          </p>
        </div>
        <div className="rounded-xl bg-[var(--surface-elevated)] px-4 py-3 text-right shadow-[var(--shadow-card)]">
          <div className="text-2xl font-semibold text-[var(--text-primary)]">{score}/100</div>
          <div className="text-xs text-[var(--text-muted)]">{readinessLabel(report.readiness)}</div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <MetricPill label="Всего вопросов" value={total || '—'} />
        <MetricPill label="Top-1 chunk" value={`${top1Rate}%`} />
        <MetricPill label="Top-3 chunks" value={`${top3Rate}%`} />
        <MetricPill label="Top-5 chunks" value={`${top5Rate}%`} />
        <MetricPill label="Ответы подтверждены" value={`${answerSupportedRate}%`} />
        <MetricPill label="Риск галлюцинаций" value={highHallucinationRisk} />
        <MetricPill label="Ошибочный первый chunk" value={wrongChunkTop1} />
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
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Прогресс RAG eval</h2>
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
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Прогресс RAG eval</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              ID задачи: <span className="font-mono">{job.id.slice(0, 8)}…</span>
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
        <StatPill label="Пачки чанков" value={totalBatches ? `${processedBatches}/${totalBatches}` : processedBatches} />
        <StatPill label="Чанки" value={sourceChunkCount || '—'} />
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
  const [questionsPerChunk, setQuestionsPerChunk] = useState('1');
  const [maxQuestionsCap, setMaxQuestionsCap] = useState('');
  const [lastQueued, setLastQueued] = useState<RagEvalFullRunAcceptedResponse | null>(null);

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
      if (!activeDocumentId) throw new Error('Нет обработанного документа для RAG eval');

      const parsedQuestionsPerChunk = Number(questionsPerChunk.trim() || '1');
      if (
        !Number.isInteger(parsedQuestionsPerChunk)
        || parsedQuestionsPerChunk < 1
        || parsedQuestionsPerChunk > 5
      ) {
        throw new Error('questions_per_chunk должен быть целым числом от 1 до 5');
      }

      const parsedMaxQuestions = maxQuestionsCap.trim()
        ? Number(maxQuestionsCap.trim())
        : undefined;

      if (
        parsedMaxQuestions !== undefined
        && (!Number.isInteger(parsedMaxQuestions) || parsedMaxQuestions < 1 || parsedMaxQuestions > 50000)
      ) {
        throw new Error('max_questions cap должен быть целым числом от 1 до 50000 или пустым');
      }

      return await ragEvalApi.runFullDocumentEval(activeDocumentId, {
        questionsPerChunk: parsedQuestionsPerChunk,
        maxQuestions: parsedMaxQuestions,
      });
    },
    onSuccess: async (result) => {
      setLastQueued(result);
      toast.success(`Проверка поставлена в очередь: ${formatNumber(result.target_questions)} вопросов`);
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
  const latestReportPayload = statusQuery.data?.report ?? null;
  const latestReport = getRecord(latestReportPayload);
  const latestRun = statusQuery.data?.run ?? null;
  const progressJob = progressQuery.data?.job ?? visibleJob;
  const progressPayload = progressJob?.progress ?? visibleJob?.progress ?? (
    progressJob
      ? { percent: progressJob.percent, status: getJobStatus(progressJob) }
      : null
  );
  const isControlMutating = pauseMutation.isPending || resumeMutation.isPending || cancelMutation.isPending;

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
          Full-document RAG eval
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-[var(--text-muted)]">
          Полная проверка документа после обработки базы знаний. Теперь задача видна как job: можно смотреть прогресс,
          ставить на паузу, продолжать и отменять без ручного доступа к production DB.
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
              По умолчанию создаётся минимум один eval-вопрос на каждый chunk документа. Поле cap можно оставить пустым.
            </p>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_160px_180px_auto]">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">Документ</span>
            <select
              value={activeDocumentId}
              onChange={(event) => setSelectedDocumentId(event.target.value)}
              className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
            >
              {processedDocuments.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.file_name} · {doc.chunk_count} chunks
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">questions/chunk</span>
            <input
              value={questionsPerChunk}
              onChange={(event) => setQuestionsPerChunk(event.target.value)}
              className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
              inputMode="numeric"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-[var(--text-secondary)]">cap</span>
            <input
              value={maxQuestionsCap}
              onChange={(event) => setMaxQuestionsCap(event.target.value)}
              className="w-full rounded-xl border border-[var(--border-primary)] bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
              placeholder="empty"
              inputMode="numeric"
            />
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
            <span>{formatNumber(activeDocument.chunk_count)} chunks</span>
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
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Последний run/report</h2>
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
            Не удалось загрузить статус RAG eval.
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">Run</h3>
              <ReportJsonBlock value={latestRun} />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">Report</h3>
              <ReportSummaryCard report={latestReport} />
              <details className="mt-4 rounded-xl border border-[var(--border-primary)] p-3">
                <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
                  Показать raw JSON
                </summary>
                <div className="mt-3">
                  <ReportJsonBlock value={Object.keys(latestReport).length ? latestReport : null} />
                </div>
              </details>
            </div>
          </div>
        )}
      </section>
    </div>
  );
};
