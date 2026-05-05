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

const ACTIVE_JOB_STATUSES = new Set(['pending', 'processing', 'running', 'retrying', 'paused', 'running_or_locked']);
const ACTIVE_RUN_STATUSES = new Set(['created', 'pending', 'processing', 'generating', 'ready', 'running', 'paused']);
const ERROR_VISIBLE_JOB_STATUSES = new Set(['failed', 'cancelled']);
const PAUSED_STATUSES = new Set(['paused', 'manual_pause', 'manual-pause']);

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

const isJobActive = (job: RagEvalJob | null | undefined): boolean => (
  Boolean(job && ACTIVE_JOB_STATUSES.has(getJobStatus(job)))
);

const isJobPaused = (job: RagEvalJob | null | undefined): boolean => (
  Boolean(job && PAUSED_STATUSES.has(getJobStatus(job)))
);

const stageLabel = (stage: string): string => {
  if (stage === 'queued') return 'В очереди';
  if (stage === 'dataset_generation') return 'Генерация eval-вопросов';
  if (stage === 'running') return 'Прогон вопросов';
  if (stage === 'completed') return 'Завершено';
  if (stage === 'cancelled') return 'Отменено';
  if (stage === 'paused') return 'Пауза';
  if (stage === 'failed') return 'Ошибка';
  return stage || 'Ожидание';
};

const ReportJsonBlock: React.FC<{ value: unknown }> = ({ value }) => (
  <pre className="max-h-[520px] overflow-auto rounded-xl bg-[var(--control-bg)] p-4 text-xs leading-relaxed text-[var(--text-secondary)]">
    {JSON.stringify(value ?? null, null, 2)}
  </pre>
);

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

  const mergedProgress = progress ?? job.progress ?? {};
  const percent = clampPercent(mergedProgress.percent);
  const stage = String(mergedProgress.stage || job.status || '');
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
              Job: <span className="font-mono">{job.id}</span>
            </p>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Статус: <span className="font-semibold text-[var(--text-primary)]">{job.status}</span>
              {' · '}
              Этап: <span className="font-semibold text-[var(--text-primary)]">{stageLabel(stage)}</span>
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
            disabled={(!active && !paused) || isMutating}
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

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatPill label="Сгенерировано" value={targetQuestions ? `${generatedQuestions}/${targetQuestions}` : generatedQuestions} />
        <StatPill label="Прогнано" value={totalQuestions ? `${processedQuestions}/${totalQuestions}` : processedQuestions} />
        <StatPill label="Batches" value={totalBatches ? `${processedBatches}/${totalBatches}` : processedBatches} />
        <StatPill label="Chunks" value={sourceChunkCount || '—'} />
        <StatPill label="Attempts" value={`${job.attempts}/${job.max_attempts}`} />
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
      toast.success(`Full-document RAG eval поставлен в очередь: ${formatNumber(result.target_questions)} target questions`);
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось поставить full-document RAG eval в очередь');
    },
  });

  const pauseMutation = useMutation({
    mutationFn: async (jobId: string) => ragEvalApi.pauseJob(jobId),
    onSuccess: async () => {
      toast.success('RAG eval поставлен на паузу');
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось поставить задачу на паузу');
    },
  });

  const resumeMutation = useMutation({
    mutationFn: async (jobId: string) => ragEvalApi.resumeJob(jobId),
    onSuccess: async () => {
      toast.success('RAG eval продолжен');
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось продолжить задачу');
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async (jobId: string) => ragEvalApi.cancelJob(jobId),
    onSuccess: async () => {
      toast.success('RAG eval отменён');
      await invalidateEvalQueries();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось отменить задачу');
    },
  });
  const latestReportPayload = statusQuery.data?.report ?? null;
  const latestReport = getRecord(latestReportPayload);
  const latestRun = statusQuery.data?.run ?? null;
  const progressJob = progressQuery.data?.job ?? visibleJob;
  const progressPayload = progressJob?.progress ?? visibleJob?.progress ?? null;
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
              <ReportJsonBlock value={Object.keys(latestReport).length ? latestReport : null} />
            </div>
          </div>
        )}
      </section>
    </div>
  );
};
