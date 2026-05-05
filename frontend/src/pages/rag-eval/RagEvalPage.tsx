import React, { useMemo, useState } from 'react';
import { BarChart3, FileText, Loader2, Play, ShieldCheck } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import { knowledgeApi } from '@shared/api/modules/knowledge';
import {
  ragEvalApi,
  type RagEvalDocumentStatusResponse,
  type RagEvalFullRunAcceptedResponse,
} from '@shared/api/modules/ragEval';

interface Document {
  id: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processing' | 'processed' | 'error';
  chunk_count: number;
  created_at: string;
}

const ACTIVE_RUN_STATUSES = new Set(['created', 'generating', 'ready', 'running']);

const formatNumber = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);


const getRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
);

const ReportJsonBlock: React.FC<{ value: unknown }> = ({ value }) => (
  <pre className="max-h-[520px] overflow-auto rounded-xl bg-[var(--control-bg)] p-4 text-xs leading-relaxed text-[var(--text-secondary)]">
    {JSON.stringify(value ?? null, null, 2)}
  </pre>
);

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
      await queryClient.invalidateQueries({ queryKey: ['rag-eval-status', activeDocumentId] });
      await queryClient.invalidateQueries({ queryKey: ['rag-eval-latest-report', activeDocumentId] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось поставить full-document RAG eval в очередь');
    },
  });

  const latestReportPayload = statusQuery.data?.report ?? null;
  const latestReport = getRecord(latestReportPayload);
  const latestRun = statusQuery.data?.run ?? null;
  const isRunActive = ACTIVE_RUN_STATUSES.has(String(latestRun?.status || ''));
  const isQueuedWaitingForRun = Boolean(lastQueued && !isRunActive && latestRun?.status !== 'completed' && latestRun?.status !== 'failed');

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
          Полная проверка документа после обработки базы знаний. Eval генерирует вопросы по chunks всего документа,
          запускается на backend через очередь и использует серверный Groq API key, не передавая секреты в браузер.
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
              По умолчанию создаётся минимум один eval-вопрос на каждый chunk документа. Поле cap можно оставить пустым,
              чтобы не обрезать документ искусственным лимитом.
            </p>
          </div>
        </div>

        {processedDocuments.length === 0 ? (
          <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            Нет обработанных документов с чанками. Сначала загрузи документ и дождись обработки базы знаний.
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_180px_180px_auto] lg:items-end">
            <label className="space-y-1 text-sm">
              <span className="text-[var(--text-muted)]">Документ</span>
              <select
                value={activeDocumentId}
                onChange={(event) => {
                  setSelectedDocumentId(event.target.value);
                  setLastQueued(null);
                }}
                className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
              >
                {processedDocuments.map((doc) => (
                  <option key={doc.id} value={doc.id}>
                    {doc.file_name} · {formatNumber(doc.chunk_count)} chunks
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-[var(--text-muted)]">questions_per_chunk</span>
              <input
                value={questionsPerChunk}
                onChange={(event) => setQuestionsPerChunk(event.target.value)}
                inputMode="numeric"
                placeholder="1"
                className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
              />
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-[var(--text-muted)]">max_questions cap</span>
              <input
                value={maxQuestionsCap}
                onChange={(event) => setMaxQuestionsCap(event.target.value)}
                inputMode="numeric"
                placeholder="пусто = весь документ"
                className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
              />
            </label>

            <button
              type="button"
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending || isRunActive || !activeDocumentId}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {runMutation.isPending || isRunActive ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {runMutation.isPending ? 'Постановка...' : isRunActive ? 'Проверка идёт...' : 'Проверить весь документ'}
            </button>
          </div>
        )}

        {activeDocument && (
          <div className="mt-4 flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-secondary)] px-2.5 py-1">
              <FileText className="h-3.5 w-3.5" />
              {activeDocument.file_name}
            </span>
            <span className="rounded-full bg-[var(--surface-secondary)] px-2.5 py-1">
              {formatNumber(activeDocument.chunk_count)} chunks
            </span>
            <span className="rounded-full bg-[var(--surface-secondary)] px-2.5 py-1">
              default target: {formatNumber(activeDocument.chunk_count)} questions
            </span>
          </div>
        )}

        {lastQueued && (
          <div className="mt-4 rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            Job queued: <span className="font-mono text-[var(--text-primary)]">{lastQueued.job_id}</span>.
            Target questions: <span className="text-[var(--text-primary)]">{formatNumber(lastQueued.target_questions)}</span>.
            {isQueuedWaitingForRun && ' Worker ещё не создал run-запись; статус обновляется автоматически.'}
          </div>
        )}
      </section>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]">
              <BarChart3 className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">Статус последней полной проверки</h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                UI автоматически перечитывает статус, пока run активен.
              </p>
            </div>
          </div>
          {statusQuery.isFetching && <Loader2 className="h-4 w-4 animate-spin text-[var(--text-muted)]" />}
        </div>

        {latestRun ? (
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
              <div className="text-xs text-[var(--text-muted)]">Status</div>
              <div className="mt-2 text-xl font-semibold text-[var(--text-primary)]">{latestRun.status}</div>
            </div>
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
              <div className="text-xs text-[var(--text-muted)]">Results saved</div>
              <div className="mt-2 text-xl font-semibold text-[var(--text-primary)]">{formatNumber(latestRun.result_count)}</div>
            </div>
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
              <div className="text-xs text-[var(--text-muted)]">Run ID</div>
              <div className="mt-2 truncate font-mono text-xs text-[var(--text-primary)]">{latestRun.id}</div>
            </div>
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
              <div className="text-xs text-[var(--text-muted)]">Model</div>
              <div className="mt-2 truncate text-sm font-semibold text-[var(--text-primary)]">{latestRun.generator_model || '—'}</div>
            </div>
          </div>
        ) : (
          <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            Для выбранного документа ещё нет run-записи RAG eval.
          </div>
        )}
      </section>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Последний сохранённый report</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Report читается из backend без нового запуска Groq.
            </p>
          </div>
          {statusQuery.isFetching && <Loader2 className="h-4 w-4 animate-spin text-[var(--text-muted)]" />}
        </div>

        {statusQuery.isError ? (
          <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            Report пока не найден или недоступен.
          </div>
        ) : latestReportPayload ? (
          <ReportJsonBlock value={Object.keys(latestReport).length ? latestReport : latestReportPayload} />
        ) : (
          <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            Для выбранного документа ещё нет сохранённого отчёта.
          </div>
        )}
      </section>
    </div>
  );
};
