import React, { useMemo, useState } from 'react';
import { BarChart3, FileText, Loader2, Play, ShieldCheck } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import { knowledgeApi } from '@shared/api/modules/knowledge';
import {
  ragEvalApi,
  type RagEvalMode,
  type RagEvalRunResponse,
} from '@shared/api/modules/ragEval';

interface Document {
  id: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processing' | 'processed' | 'error';
  chunk_count: number;
  created_at: string;
}

const formatNumber = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);

const formatScore = (value: unknown): string => (
  typeof value === 'number' && Number.isFinite(value)
    ? value.toFixed(3)
    : '—'
);

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
  const [mode, setMode] = useState<RagEvalMode>('quick');
  const [maxQuestions, setMaxQuestions] = useState('5');
  const [lastRun, setLastRun] = useState<RagEvalRunResponse | null>(null);

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

  const latestReportQuery = useQuery({
    queryKey: ['rag-eval-latest-report', activeDocumentId],
    queryFn: async () => ragEvalApi.getLatestReport(activeDocumentId),
    enabled: !!activeDocumentId,
    retry: false,
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      if (!activeDocumentId) throw new Error('Нет обработанного документа для RAG eval');

      const parsedMaxQuestions = maxQuestions.trim()
        ? Number(maxQuestions.trim())
        : undefined;

      if (
        parsedMaxQuestions !== undefined
        && (!Number.isInteger(parsedMaxQuestions) || parsedMaxQuestions < 1 || parsedMaxQuestions > 500)
      ) {
        throw new Error('max_questions должен быть целым числом от 1 до 500');
      }

      return await ragEvalApi.runDocumentEval(activeDocumentId, {
        mode,
        maxQuestions: parsedMaxQuestions,
      });
    },
    onSuccess: async (result) => {
      setLastRun(result);
      toast.success(`RAG eval завершён: score ${formatScore(result.score)}`);
      await queryClient.invalidateQueries({ queryKey: ['rag-eval-latest-report', activeDocumentId] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Не удалось запустить RAG eval');
    },
  });

  const latestReportPayload = latestReportQuery.data?.report ?? null;
  const latestReport = getRecord(latestReportPayload);
  const lastRunReport = getRecord(lastRun?.report);

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
          RAG eval
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-[var(--text-muted)]">
          Оценка качества ответов по базе знаний проекта. UI использует обычную пользовательскую сессию;
          секреты Groq и серверные admin-токены в браузер не передаются.
        </p>
      </div>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-5 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Запуск eval</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Для smoke-проверки оставь 3–5 вопросов. Запуск делает LLM-вызовы только на backend.
            </p>
          </div>
        </div>

        {processedDocuments.length === 0 ? (
          <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            Нет обработанных документов с чанками. Сначала загрузи и дождись обработки базы знаний.
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_180px_180px_auto] lg:items-end">
            <label className="space-y-1 text-sm">
              <span className="text-[var(--text-muted)]">Документ</span>
              <select
                value={activeDocumentId}
                onChange={(event) => {
                  setSelectedDocumentId(event.target.value);
                  setLastRun(null);
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
              <span className="text-[var(--text-muted)]">Mode</span>
              <select
                value={mode}
                onChange={(event) => setMode(event.target.value as RagEvalMode)}
                className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
              >
                <option value="quick">quick</option>
                <option value="standard">standard</option>
                <option value="deep">deep</option>
                <option value="paranoid">paranoid</option>
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-[var(--text-muted)]">max_questions</span>
              <input
                value={maxQuestions}
                onChange={(event) => setMaxQuestions(event.target.value)}
                inputMode="numeric"
                placeholder="5"
                className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
              />
            </label>

            <button
              type="button"
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending || !activeDocumentId}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {runMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {runMutation.isPending ? 'Запуск...' : 'Запустить'}
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
          </div>
        )}
      </section>

      {lastRun && (
        <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
          <div className="mb-4 flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]">
              <BarChart3 className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">Последний запуск в этой сессии</h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                Run ID: {lastRun.run_id}
              </p>
            </div>
          </div>

          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
              <div className="text-xs text-[var(--text-muted)]">Score</div>
              <div className="mt-2 text-xl font-semibold text-[var(--text-primary)]">{formatScore(lastRun.score)}</div>
            </div>
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
              <div className="text-xs text-[var(--text-muted)]">Readiness</div>
              <div className="mt-2 text-xl font-semibold text-[var(--text-primary)]">{lastRun.readiness}</div>
            </div>
            <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
              <div className="text-xs text-[var(--text-muted)]">Questions</div>
              <div className="mt-2 text-xl font-semibold text-[var(--text-primary)]">{formatNumber(lastRun.questions)}</div>
            </div>
          </div>

          <ReportJsonBlock value={Object.keys(lastRunReport).length ? lastRunReport : lastRun.report} />
        </section>
      )}

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] sm:p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Последний сохранённый report</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Читается из backend без запуска Groq.
            </p>
          </div>
          {latestReportQuery.isFetching && <Loader2 className="h-4 w-4 animate-spin text-[var(--text-muted)]" />}
        </div>

        {latestReportQuery.isError ? (
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
