import React, { useState } from 'react';
import {
  BookOpen,
  Upload,
  FileText,
  Trash2,
  Search,
  ExternalLink,
  TestTube2,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import {
  KNOWLEDGE_PREPROCESSING_MODE_OPTIONS,
  knowledgeApi,
  type KnowledgePreprocessingMode,
  type KnowledgeUsageBreakdown,
  type KnowledgeUsageResponse,
  type KnowledgePreviewResponse,
  type KnowledgePreviewResult,
} from '@shared/api/modules/knowledge';
import { BaseModal } from '@shared/ui';

interface Document {
  id: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processing' | 'processed' | 'error';
  chunk_count: number;
  created_at: string;
}

interface UsageSummaryCardProps {
  usage: KnowledgeUsageResponse;
}

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
};

const confidenceLabel = (score: number): string => {
  if (score >= 0.75) return 'Высокая уверенность';
  if (score >= 0.45) return 'Средняя уверенность';
  return 'Низкая уверенность';
};

const scoreLabel = (score: number): string => score.toFixed(3);

const formatNumber = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);

const formatUsd = (value: number): string => new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
}).format(value);

const sumTokensBySource = (breakdown: KnowledgeUsageBreakdown[], source: string): number => (
  breakdown
    .filter((item) => item.source === source)
    .reduce((acc, item) => acc + item.tokens_total, 0)
);

const providerModelsLabel = (breakdown: KnowledgeUsageBreakdown[]): string => (
  breakdown
    .map((item) => `${item.provider}: ${item.model}`)
    .filter((value, index, items) => items.indexOf(value) === index)
    .join(', ')
);

const PreviewResultCard: React.FC<{
  title: string;
  result: KnowledgePreviewResult;
  compact?: boolean;
}> = ({ title, result, compact = false }) => (
  <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
    <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
      <span className="inline-flex w-fit items-center rounded-full bg-[var(--accent-muted)] px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)]">
        {confidenceLabel(result.score)} · {scoreLabel(result.score)}
      </span>
    </div>
    <p className={`text-sm leading-relaxed text-[var(--text-primary)] ${compact ? 'line-clamp-3' : ''}`}>
      {result.answer || result.content}
    </p>
    <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
      <span>Метод: {result.method}</span>
      {result.source && <span>Источник: {result.source}</span>}
      {result.document_status && <span>Статус: {result.document_status}</span>}
    </div>
  </div>
);

const UsageSummaryCard: React.FC<UsageSummaryCardProps> = ({ usage }) => {
  const uploadTokens = sumTokensBySource(usage.breakdown, 'knowledge_upload');
  const ragTokens = sumTokensBySource(usage.breakdown, 'rag_search');
  const providerModels = providerModelsLabel(usage.breakdown);

  return (
    <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
          <BookOpen className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Usage моделей</h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Токены embeddings и preprocessing по базе знаний.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
          <div className="text-xs text-[var(--text-muted)]">Embeddings: used / remaining</div>
          <div className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
            {formatNumber(usage.tokens_month_total)} / {formatNumber(usage.remaining_tokens)}
          </div>
        </div>
        <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
          <div className="text-xs text-[var(--text-muted)]">Today</div>
          <div className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
            {formatNumber(usage.tokens_today_total)}
          </div>
        </div>
        <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
          <div className="text-xs text-[var(--text-muted)]">This month</div>
          <div className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
            {formatNumber(usage.tokens_month_total)}
          </div>
        </div>
        <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
          <div className="text-xs text-[var(--text-muted)]">Uploads</div>
          <div className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
            {formatNumber(uploadTokens)}
          </div>
        </div>
        <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
          <div className="text-xs text-[var(--text-muted)]">RAG answers</div>
          <div className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
            {formatNumber(ragTokens)}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-2 text-sm text-[var(--text-muted)] lg:flex-row lg:items-center lg:justify-between">
        <span>Модели: {providerModels || 'Нет данных'}</span>
        <span>Estimated cost: {formatUsd(usage.estimated_cost_month_usd)}</span>
      </div>
    </section>
  );
};

export const KnowledgePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [previewQuestion, setPreviewQuestion] = useState('');
  const [preprocessingMode, setPreprocessingMode] = useState<KnowledgePreprocessingMode>('faq');
  const [isClearModalOpen, setIsClearModalOpen] = useState(false);

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
    refetchInterval: (query) => {
      const docs = Array.isArray(query.state.data) ? query.state.data as Document[] : [];
      return docs.some((doc) => doc.status === 'pending' || doc.status === 'processing')
        ? 5000
        : false;
    },
  });

  const documents = Array.isArray(documentsQuery.data) ? documentsQuery.data : [];
  const hasProcessingDocuments = documents.some((doc) => doc.status === 'pending' || doc.status === 'processing');
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const usageQuery = useQuery({
    queryKey: ['knowledge-usage', projectId],
    queryFn: async () => {
      if (!projectId) return null;
      const { data } = await knowledgeApi.usage(projectId);
      return data;
    },
    enabled: !!projectId,
    retry: false,
    refetchInterval: hasProcessingDocuments ? 5000 : false,
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!projectId) throw new Error('Project ID is missing');

      const response = await knowledgeApi.upload(projectId, file, preprocessingMode);

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData?.detail?.[0]?.msg || errData?.detail || 'Ошибка загрузки');
      }

      return await response.json();
    },
    onSuccess: async () => {
      toast.success('Документ принят и поставлен в очередь на обработку');
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : 'Ошибка при загрузке документа';
      toast.error(message);
    },
  });

  const previewMutation = useMutation<KnowledgePreviewResponse, unknown, string>({
    mutationFn: async (question: string) => {
      if (!projectId) throw new Error('Project ID is missing');
      const { data } = await knowledgeApi.preview(projectId, question, 5);
      return data;
    },
    onError: (err: unknown) => {
      const detail = err && typeof err === 'object' && 'detail' in err
        ? String((err as { detail?: unknown }).detail)
        : null;
      toast.error(detail || 'Не удалось проверить базу знаний');
    },
  });

  const clearMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error('Project ID is missing');
      await knowledgeApi.clear(projectId);
    },
    onSuccess: async () => {
      setIsClearModalOpen(false);
      setPreviewQuestion('');
      previewMutation.reset();
      toast.success('База знаний очищена');
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : 'Не удалось очистить базу знаний';
      toast.error(message);
    },
  });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  const triggerUpload = () => {
    fileInputRef.current?.click();
  };

  const handlePreviewSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = previewQuestion.trim();
    if (!question) {
      toast.error('Введите вопрос клиента');
      return;
    }
    previewMutation.mutate(question);
  };

  const handleDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const handleDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();

    const file = event.dataTransfer.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  if (documentsQuery.isLoading) {
    return (
      <div className="flex justify-center p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">
        Загрузка базы знаний...
      </div>
    );
  }

  const filteredDocuments = documents.filter((doc) => (
    doc.file_name.toLowerCase().includes(searchQuery.trim().toLowerCase())
  ));

  const previewResult = previewMutation.data;
  const usage = usageQuery.data;

  const getStatusBadge = (status: Document['status']) => {
    if (status === 'processed') {
      return {
        label: 'Обработан',
        className: 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]',
      };
    }
    if (status === 'error') {
      return {
        label: 'Ошибка',
        className: 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]',
      };
    }
    if (status === 'processing') {
      return {
        label: 'Обрабатывается',
        className: 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]',
      };
    }
    return {
      label: 'В очереди',
      className: 'bg-[var(--accent-warning-bg)] text-[var(--accent-warning)]',
    };
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        className="hidden"
        accept=".pdf,.json,.md,.txt"
      />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="mb-2 text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">
            База знаний
          </h1>
          <p className="text-[var(--text-muted)]">
            Загрузите документы, чтобы обучить своего ИИ-ассистента
          </p>
        </div>
        <div className="flex w-full flex-col gap-3 sm:flex-row lg:w-auto">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              type="text"
              placeholder="Поиск документов..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] py-2 pl-10 pr-4 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 lg:w-64"
            />
          </div>
          <button
            type="button"
            onClick={() => setIsClearModalOpen(true)}
            className="inline-flex min-h-10 items-center justify-center rounded-lg bg-[var(--accent-danger-bg)] px-4 py-2 text-sm font-medium text-[var(--accent-danger-text)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--accent-danger-bg)]/80"
          >
            Очистить базу знаний
          </button>
        </div>
      </div>

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
        <div className="mb-4 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Загрузка документа
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Выберите режим предобработки перед загрузкой. Для FAQ и условий бизнеса лучше оставить режим FAQ.
            </p>
          </div>

          <label className="flex w-full flex-col gap-2 lg:w-80">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              Режим предобработки
            </span>
            <select
              value={preprocessingMode}
              onChange={(event) => setPreprocessingMode(event.target.value as KnowledgePreprocessingMode)}
              disabled={uploadMutation.isPending}
              className="min-h-11 rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 disabled:cursor-wait disabled:opacity-60"
            >
              {KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="text-xs leading-relaxed text-[var(--text-muted)]">
              {KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find((option) => option.value === preprocessingMode)?.description}
            </span>
          </label>
        </div>

        <div
          onClick={triggerUpload}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl bg-[var(--surface-card)] p-6 shadow-sm transition-colors group sm:p-8 lg:p-12 ${
            uploadMutation.isPending
              ? 'border-[var(--accent-primary)] bg-[var(--accent-primary)]/5 cursor-wait'
              : 'border-[var(--border-subtle)] hover:bg-[var(--surface-secondary)]'
          }`}
        >
          <div className={`mb-4 flex h-14 w-14 items-center justify-center rounded-full transition-transform sm:h-16 sm:w-16 ${
            uploadMutation.isPending ? 'bg-[var(--accent-primary)]/20 animate-pulse' : 'bg-[var(--accent-primary)]/10 group-hover:scale-110'
          }`}>
            <Upload className="h-7 w-7 text-[var(--accent-primary)] sm:h-8 sm:w-8" />
          </div>
          <h3 className="text-center text-base font-semibold text-[var(--text-primary)] sm:text-lg">
            {uploadMutation.isPending ? 'Загрузка...' : 'Нажмите или перетащите файл'}
          </h3>
          <p className="mt-1 text-center text-sm text-[var(--text-muted)]">
            PDF, JSON, Markdown или TXT · {KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find((option) => option.value === preprocessingMode)?.label}
          </p>
        </div>
      </section>

      {usage && usage.counter_enabled && <UsageSummaryCard usage={usage} />}

      <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
            <TestTube2 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Тест базы знаний
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Введите вопрос клиента и проверьте, какой ответ найдётся без генерации LLM.
            </p>
          </div>
        </div>

        <form onSubmit={handlePreviewSubmit} className="flex flex-col gap-3 lg:flex-row">
          <textarea
            value={previewQuestion}
            onChange={(event) => setPreviewQuestion(event.target.value)}
            placeholder="Например: как оформить возврат заказа?"
            rows={3}
            className="min-h-24 flex-1 resize-y rounded-xl bg-[var(--control-bg)] px-4 py-3 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          />
          <button
            type="submit"
            disabled={previewMutation.isPending}
            className="min-h-11 rounded-xl bg-[var(--accent-primary)] px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-wait disabled:opacity-60 lg:self-start"
          >
            {previewMutation.isPending ? 'Проверяем...' : 'Проверить'}
          </button>
        </form>

        {previewResult && (
          <div className="mt-5 space-y-4">
            {previewResult.is_empty || !previewResult.best_result ? (
              <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
                Ничего не найдено. Попробуйте другой вопрос или загрузите документы в базу знаний.
              </div>
            ) : (
              <>
                <PreviewResultCard title="Лучший найденный ответ" result={previewResult.best_result} />
                {previewResult.top_results.length > 1 && (
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                      Топ совпадений
                    </h3>
                    {previewResult.top_results.slice(1).map((result) => (
                      <PreviewResultCard
                        key={result.id}
                        title="Дополнительное совпадение"
                        result={result}
                        compact
                      />
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </section>

      {documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl bg-[var(--surface-secondary)] p-6 text-center sm:p-10 lg:p-16">
          <BookOpen className="mb-4 h-12 w-12 text-[var(--border-subtle)] sm:h-16 sm:w-16" />
          <h3 className="text-lg font-semibold text-[var(--text-primary)] sm:text-xl">
            База знаний пуста
          </h3>
          <p className="mt-2 text-[var(--text-muted)]">
            Загрузите первый документ, чтобы начать обучение
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 lg:gap-6">
          {filteredDocuments.map((doc) => {
            const statusBadge = getStatusBadge(doc.status);

            return (
              <div
                key={doc.id}
                className="rounded-2xl bg-[var(--surface-elevated)] p-4 transition-all hover:shadow-lg sm:p-5 group"
              >
                <div className="mb-4 flex items-start justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--accent-primary)]">
                    <FileText className="h-5 w-5" />
                  </div>
                  <div className="flex gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
                    <button className="rounded-lg p-2 text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-secondary)]">
                      <Trash2 className="h-4 w-4" />
                    </button>
                    <button className="rounded-lg p-2 text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-secondary)]">
                      <ExternalLink className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                <h4 className="mb-1 truncate font-semibold text-[var(--text-primary)]" title={doc.file_name}>
                  {doc.file_name}
                </h4>
                <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
                  <span>{formatSize(doc.file_size)}</span>
                  <span className="h-1 w-1 rounded-full bg-[var(--border-subtle)]" />
                  <span>{doc.chunk_count} фрагментов</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className={`inline-flex min-h-6 items-center rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${statusBadge.className}`}>
                    {statusBadge.label}
                  </span>
                  <span className="text-[10px] text-[var(--text-muted)]">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <BaseModal
        isOpen={isClearModalOpen}
        onClose={() => {
          if (!clearMutation.isPending) {
            setIsClearModalOpen(false);
          }
        }}
        title="Очистить базу знаний"
        cancelLabel="Отмена"
      >
        <p className="text-sm leading-relaxed text-[var(--text-primary)]">
          Все документы и связанные фрагменты будут удалены без возможности восстановления.
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => clearMutation.mutate()}
            disabled={clearMutation.isPending}
            className="min-h-9 rounded-lg bg-[var(--accent-danger)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--accent-danger-text)] disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-[var(--accent-danger)]/25"
          >
            {clearMutation.isPending ? 'Очищаем...' : 'Очистить'}
          </button>
        </div>
      </BaseModal>
    </div>
  );
};
