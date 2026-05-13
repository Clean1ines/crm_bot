import React, { useEffect, useState } from 'react';
import {
  BookOpen,
  Upload,
  FileText,
  StopCircle,
  Search,
  TestTube2,
  Loader2,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@shared/api/core/errors';

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

type KnowledgeProcessingMetrics = Record<string, unknown>;

interface Document {
  id: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processing' | 'processed' | 'error' | 'cancelled' | string;
  error?: string | null;
  chunk_count: number;
  created_at: string;
  updated_at?: string | null;
  preprocessing_mode?: KnowledgePreprocessingMode | string | null;
  preprocessing_status?: 'not_requested' | 'processing' | 'completed' | 'failed' | 'cancelled' | string | null;
  preprocessing_error?: string | null;
  preprocessing_model?: string | null;
  preprocessing_prompt_version?: string | null;
  preprocessing_metrics?: KnowledgeProcessingMetrics | null;
  structured_entries?: number;
  structured_chunk_count?: number;
  llm_tokens_input?: number;
  llm_tokens_output?: number;
  llm_tokens_total?: number;
  llm_usage_events_count?: number;
  llm_models?: string | null;
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

const LLM_USAGE_TYPE = 'llm';

const USER_ANSWER_USAGE_SOURCES = new Set([
  'client_response',
  'user_response',
  'agent_response',
  'conversation_answer',
]);

const KNOWLEDGE_UPLOAD_USAGE_SOURCES = new Set([
  'knowledge_preprocessing',
  'knowledge_upload',
]);

const RAG_EVAL_USAGE_SOURCES = new Set([
  'rag_eval',
  'rag_eval_dataset',
  'rag_eval_judge',
  'rag_search',
]);

const llmUsageBreakdown = (
  breakdown: KnowledgeUsageBreakdown[],
): KnowledgeUsageBreakdown[] => (
  breakdown.filter((item) => item.usage_type === LLM_USAGE_TYPE)
);

const usageBySources = (
  breakdown: KnowledgeUsageBreakdown[],
  sources: Set<string>,
): KnowledgeUsageBreakdown[] => (
  breakdown.filter((item) => sources.has(item.source))
);

const sumUsageTokens = (breakdown: KnowledgeUsageBreakdown[]): number => (
  breakdown.reduce((acc, item) => acc + item.tokens_total, 0)
);

const sumUsageCost = (breakdown: KnowledgeUsageBreakdown[]): number => (
  breakdown.reduce((acc, item) => acc + item.estimated_cost_usd, 0)
);

const usageModelRows = (breakdown: KnowledgeUsageBreakdown[]): string[] => {
  const totals = new Map<string, number>();

  breakdown.forEach((item) => {
    const key = `${item.provider}: ${item.model}`;
    totals.set(key, (totals.get(key) ?? 0) + item.tokens_total);
  });

  return Array.from(totals.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([model, tokens]) => `${model} · ${formatNumber(tokens)}`);
};


const metricNumber = (
  metrics: KnowledgeProcessingMetrics | null | undefined,
  key: string,
): number | null => {
  const value = metrics?.[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const metricText = (
  metrics: KnowledgeProcessingMetrics | null | undefined,
  key: string,
): string | null => {
  const value = metrics?.[key];
  return typeof value === 'string' && value.trim() !== '' ? value : null;
};

const rawDocumentIssueText = (doc: Document): string | null => {
  const message = doc.preprocessing_error?.trim() || doc.error?.trim() || '';

  return message || null;
};

const documentIssueText = (doc: Document): string | null => {
  const message = rawDocumentIssueText(doc);
  if (!message) return null;

  return getErrorMessage(
    message,
    'Документ не удалось обработать. Попробуйте загрузить его заново или обратитесь к администратору проекта.',
  );
};

const isDocumentCancelled = (doc: Document): boolean => {
  const issueText = rawDocumentIssueText(doc)?.toLowerCase() || '';

  return (
    doc.status === 'cancelled'
    || doc.preprocessing_status === 'cancelled'
    || issueText.includes('остановлено пользователем')
    || issueText.includes('cancelled')
    || issueText.includes('canceled')
  );
};

const isDocumentFailed = (doc: Document): boolean => (
  doc.status === 'error'
  || doc.preprocessing_status === 'failed'
);

const isDocumentProcessing = (doc: Document): boolean => (
  !isDocumentCancelled(doc)
  && !isDocumentFailed(doc)
  && (
    doc.status === 'pending'
    || doc.status === 'processing'
    || doc.preprocessing_status === 'processing'
  )
);

const knowledgeProcessingModeLabel = (mode: string | null | undefined): string => (
  KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find((option) => option.value === mode)?.label
  || mode
  || 'не указан'
);

const processingProgressPercent = (doc: Document): number | null => {
  const current = metricNumber(doc.preprocessing_metrics, 'technical_chunk_processed_count')
    ?? metricNumber(doc.preprocessing_metrics, 'technical_compiler_call_count');
  const total = metricNumber(doc.preprocessing_metrics, 'technical_chunk_total_count')
    ?? metricNumber(doc.preprocessing_metrics, 'technical_compiler_total_count');

  if (current === null || total === null || total <= 0) return null;

  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
};

const processingProgressLabel = (doc: Document): string => {
  const metrics = doc.preprocessing_metrics;
  const current = metricNumber(metrics, 'technical_chunk_processed_count')
    ?? metricNumber(metrics, 'technical_compiler_call_count');
  const total = metricNumber(metrics, 'technical_chunk_total_count')
    ?? metricNumber(metrics, 'technical_compiler_total_count');

  if (current !== null && total !== null && total > 0) {
    return `Шаг ${formatNumber(current)} из ${formatNumber(total)}`;
  }

  if (doc.status === 'pending') return 'Документ ожидает обработки';
  return 'Подготовка обработки документа';
};

const isLikelyEmbeddingModel = (model: string): boolean => {
  const normalized = model.toLowerCase();

  return (
    normalized.includes('embedding')
    || normalized.includes('voyage')
    || normalized.includes('jina')
    || normalized.includes('minilm')
    || normalized.includes('e5')
    || normalized.includes('bge')
  );
};

const processingModelLabel = (doc: Document): string => {
  const candidates = [
    metricText(doc.preprocessing_metrics, 'model'),
    doc.preprocessing_model,
  ].filter((value): value is string => Boolean(value && value.trim()));

  return candidates.find((model) => !isLikelyEmbeddingModel(model))
    || 'LLM-модель пока определяется';
};

const compiledEntryCount = (doc: Document): number | null => (
  metricNumber(doc.preprocessing_metrics, 'semantic_answer_count')
  ?? metricNumber(doc.preprocessing_metrics, 'compiled_entry_count')
  ?? metricNumber(doc.preprocessing_metrics, 'canonical_entry_count')
  ?? (typeof doc.structured_entries === 'number' ? doc.structured_entries : null)
);

const semanticMergeCount = (doc: Document): number | null => (
  metricNumber(doc.preprocessing_metrics, 'semantic_answer_merge_count')
  ?? metricNumber(doc.preprocessing_metrics, 'embedding_text_merge_call_count')
  ?? metricNumber(doc.preprocessing_metrics, 'llm_merge_call_count')
);

const technicalChunkProgressText = (doc: Document): string | null => {
  const current = metricNumber(doc.preprocessing_metrics, 'technical_chunk_processed_count')
    ?? metricNumber(doc.preprocessing_metrics, 'technical_compiler_call_count');
  const total = metricNumber(doc.preprocessing_metrics, 'technical_chunk_total_count')
    ?? metricNumber(doc.preprocessing_metrics, 'technical_compiler_total_count');

  if (current === null && total === null) return null;
  if (current !== null && total !== null && total > 0) {
    return `${formatNumber(current)} из ${formatNumber(total)}`;
  }
  if (total !== null && total > 0) return `0 из ${formatNumber(total)}`;
  return current !== null ? formatNumber(current) : null;
};

const sourceChunkCount = (doc: Document): number | null => (
  metricNumber(doc.preprocessing_metrics, 'raw_source_chunk_count')
  ?? metricNumber(doc.preprocessing_metrics, 'source_chunk_count')
  ?? (Number.isFinite(doc.chunk_count) ? doc.chunk_count : null)
);

const incomingSemanticEntryCount = (doc: Document): number | null => (
  metricNumber(doc.preprocessing_metrics, 'incoming_entry_count')
  ?? metricNumber(doc.preprocessing_metrics, 'answer_candidate_count')
);

const documentLlmTokenText = (doc: Document): string | null => {
  const total = doc.llm_tokens_total
    ?? metricNumber(doc.preprocessing_metrics, 'llm_tokens_total');
  if (total === null || total <= 0) return null;

  const input = doc.llm_tokens_input
    ?? metricNumber(doc.preprocessing_metrics, 'llm_tokens_input');
  const output = doc.llm_tokens_output
    ?? metricNumber(doc.preprocessing_metrics, 'llm_tokens_output');

  if (input !== null || output !== null) {
    return `${formatNumber(total)} всего · вход ${formatNumber(input ?? 0)} / выход ${formatNumber(output ?? 0)}`;
  }

  return `${formatNumber(total)} всего`;
};

const documentLlmModels = (doc: Document): string | null => {
  const models = doc.llm_models?.trim();
  return models || null;
};

const formatDurationSeconds = (seconds: number): string => {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const restSeconds = safeSeconds % 60;

  if (hours > 0) {
    return `${hours} ч ${minutes.toString().padStart(2, '0')} мин ${restSeconds.toString().padStart(2, '0')} сек`;
  }
  if (minutes > 0) {
    return `${minutes} мин ${restSeconds.toString().padStart(2, '0')} сек`;
  }
  return `${restSeconds} сек`;
};

const processingElapsedSeconds = (doc: Document, nowMs: number): number => {
  const metricElapsed = metricNumber(doc.preprocessing_metrics, 'elapsed_seconds') ?? 0;
  const startedAt = Date.parse(doc.created_at || doc.updated_at || '');

  if (!Number.isFinite(startedAt) || !isDocumentProcessing(doc)) {
    return metricElapsed;
  }

  const localElapsed = Math.max(0, (nowMs - startedAt) / 1000);
  return Math.max(metricElapsed, localElapsed);
};

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

const UsageScenarioCard: React.FC<{
  title: string;
  description: string;
  breakdown: KnowledgeUsageBreakdown[];
  emptyText: string;
}> = ({ title, description, breakdown, emptyText }) => {
  const tokens = sumUsageTokens(breakdown);
  const modelRows = usageModelRows(breakdown);

  return (
    <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </div>
      <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
        {formatNumber(tokens)}
      </div>
      <p className="mt-1 text-xs leading-relaxed text-[var(--text-muted)]">
        {description}
      </p>
      <div className="mt-3 space-y-1 text-xs text-[var(--text-muted)]">
        {modelRows.length > 0 ? (
          modelRows.map((row) => (
            <div key={row}>{row}</div>
          ))
        ) : (
          <div>{emptyText}</div>
        )}
      </div>
    </div>
  );
};

const UsageSummaryCard: React.FC<UsageSummaryCardProps> = ({ usage }) => {
  const llmBreakdown = llmUsageBreakdown(usage.breakdown);
  const answerBreakdown = usageBySources(llmBreakdown, USER_ANSWER_USAGE_SOURCES);
  const uploadBreakdown = usageBySources(llmBreakdown, KNOWLEDGE_UPLOAD_USAGE_SOURCES);
  const ragEvalBreakdown = usageBySources(llmBreakdown, RAG_EVAL_USAGE_SOURCES);
  const totalTokens = sumUsageTokens(llmBreakdown);
  const totalCost = sumUsageCost(llmBreakdown);

  return (
    <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
          <BookOpen className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            LLM-токены за месяц
          </h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Только фактические LLM-вызовы. Embedding-модели и remaining-лимиты здесь не учитываются.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <UsageScenarioCard
          title="Общее использование"
          description={`Все LLM-сценарии за месяц · cost ${formatUsd(totalCost)}`}
          breakdown={llmBreakdown}
          emptyText="За месяц нет записанных LLM events"
        />
        <UsageScenarioCard
          title="Ответы пользователям"
          description="LLM-токены генерации ответов клиентам и диалогов"
          breakdown={answerBreakdown}
          emptyText="Пока нет LLM events для ответов пользователям"
        />
        <UsageScenarioCard
          title="Загрузка документов"
          description="LLM-токены KCD-компиляции и merge_embedding_text"
          breakdown={uploadBreakdown}
          emptyText="Пока нет LLM events для загрузки документов"
        />
        <UsageScenarioCard
          title="RAG eval"
          description="LLM-токены генерации/оценки eval-сценариев"
          breakdown={ragEvalBreakdown}
          emptyText="Пока нет LLM events для RAG eval"
        />
      </div>

      <div className="mt-4 text-sm text-[var(--text-muted)]">
        Всего LLM-токенов за месяц: {formatNumber(totalTokens)}.
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
      return docs.some(isDocumentProcessing) ? 3000 : false;
    },
  });

  const documents = Array.isArray(documentsQuery.data) ? documentsQuery.data : [];
  const hasProcessingDocuments = documents.some(isDocumentProcessing);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [processingNowMs, setProcessingNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!hasProcessingDocuments) return undefined;

    const timer = window.setInterval(() => {
      setProcessingNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [hasProcessingDocuments]);

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
        throw new Error(getErrorMessage(errData, 'Не удалось загрузить документ'));
      }

      return await response.json();
    },
    onSuccess: async () => {
      toast.success('Документ принят и поставлен в очередь на обработку');
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, 'Ошибка при загрузке документа'));
    },
  });

  const previewMutation = useMutation<KnowledgePreviewResponse, unknown, string>({
    mutationFn: async (question: string) => {
      if (!projectId) throw new Error('Project ID is missing');
      const { data } = await knowledgeApi.preview(projectId, question, 5);
      return data;
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, 'Не удалось проверить базу знаний'));
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
      toast.error(getErrorMessage(err, 'Не удалось очистить базу знаний'));
    },
  });


  const cancelProcessingMutation = useMutation({
    mutationFn: async (documentId: string) => {
      if (!projectId) throw new Error('Project ID is missing');
      await knowledgeApi.cancel(projectId, documentId);
    },
    onSuccess: async () => {
      toast.success('Обработка документа остановлена');
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-usage', projectId] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, 'Не удалось остановить обработку'));
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

  const getStatusBadge = (doc: Document) => {
    const status = doc.status;

    if (isDocumentCancelled(doc)) {
      return {
        label: 'Остановлено',
        className: 'bg-[var(--accent-warning-bg)] text-[var(--accent-warning)]',
      };
    }
    if (isDocumentFailed(doc)) {
      return {
        label: 'Ошибка обработки',
        className: 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]',
      };
    }
    if (isDocumentProcessing(doc)) {
      return {
        label: 'Обрабатывается',
        className: 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]',
      };
    }
    if (status === 'processed') {
      return {
        label: 'Обработан',
        className: 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]',
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
            Загрузите документы, чтобы собрать проверяемые смысловые ответы для ассистента
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

        {hasProcessingDocuments && (
          <div className="mb-4 rounded-2xl bg-[var(--accent-primary)]/10 p-4 text-sm text-[var(--text-primary)]">
            <div className="flex items-start gap-3">
              <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-[var(--accent-primary)]" />
              <div>
                <div className="font-semibold">Документ обрабатывается</div>
                <p className="mt-1 leading-relaxed text-[var(--text-muted)]">
                  Система не просто режет файл на куски: она извлекает смысловые ответы,
                  объединяет повторы и привязывает каждый ответ к фрагментам источника.
                  Для больших документов это может занять несколько минут.
                </p>
              </div>
            </div>
          </div>
        )}

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
            Загрузите первый документ, чтобы начать сборку базы знаний
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 lg:gap-6">
          {filteredDocuments.map((doc) => {
            const statusBadge = getStatusBadge(doc);

            return (
              <div
                key={doc.id}
                className="rounded-2xl bg-[var(--surface-elevated)] p-4 transition-all hover:shadow-lg sm:p-5 group"
              >
                <div className="mb-4 flex items-start justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--accent-primary)]">
                    <FileText className="h-5 w-5" />
                  </div>
                  {isDocumentProcessing(doc) && (
                    <div className="flex gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={() => cancelProcessingMutation.mutate(doc.id)}
                        disabled={cancelProcessingMutation.isPending}
                        title="Остановить обработку"
                        className="rounded-lg p-2 text-[var(--accent-danger-text)] transition-colors hover:bg-[var(--accent-danger-bg)] disabled:cursor-wait disabled:opacity-50"
                      >
                        <StopCircle className="h-4 w-4" />
                      </button>
                    </div>
                  )}
                </div>

                <h4 className="mb-1 truncate font-semibold text-[var(--text-primary)]" title={doc.file_name}>
                  {doc.file_name}
                </h4>
                <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
                  <span>{formatSize(doc.file_size)}</span>
                  <span className="h-1 w-1 rounded-full bg-[var(--border-subtle)]" />
                  <span>{doc.chunk_count} фрагментов</span>
                  {doc.preprocessing_mode && (
                    <>
                      <span className="h-1 w-1 rounded-full bg-[var(--border-subtle)]" />
                      <span>{knowledgeProcessingModeLabel(doc.preprocessing_mode)}</span>
                    </>
                  )}
                </div>

                {isDocumentProcessing(doc) && (
                  <div className="mb-4 rounded-xl bg-[var(--accent-primary)]/10 p-3">
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-[var(--accent-primary)]">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{processingProgressLabel(doc)}</span>
                    </div>
                    {processingProgressPercent(doc) !== null && (
                      <div className="mb-2 h-2 overflow-hidden rounded-full bg-[var(--surface-secondary)]">
                        <div
                          className="h-full rounded-full bg-[var(--accent-primary)] transition-all"
                          style={{ width: `${processingProgressPercent(doc)}%` }}
                        />
                      </div>
                    )}
                    <div className="space-y-1 text-xs text-[var(--text-muted)]">
                      <div>LLM-модель компиляции: {processingModelLabel(doc)}</div>
                      <div>Времени прошло: {formatDurationSeconds(processingElapsedSeconds(doc, processingNowMs))}</div>
                      {sourceChunkCount(doc) !== null && (
                        <div>Исходные source-фрагменты: {formatNumber(sourceChunkCount(doc) ?? 0)}</div>
                      )}
                      {technicalChunkProgressText(doc) !== null && (
                        <div>Технические фрагменты / LLM-батчи: {technicalChunkProgressText(doc)}</div>
                      )}
                      {compiledEntryCount(doc) !== null && (
                        <div>Собрано смысловых ответов: {formatNumber(compiledEntryCount(doc) ?? 0)}</div>
                      )}
                      {incomingSemanticEntryCount(doc) !== null && (
                        <div>Новых кандидатов в последнем батче: {formatNumber(incomingSemanticEntryCount(doc) ?? 0)}</div>
                      )}
                      {semanticMergeCount(doc) !== null && (
                        <div>
                          Объединено смысловых повторов: {formatNumber(semanticMergeCount(doc) ?? 0)}
                        </div>
                      )}
                      {documentLlmTokenText(doc) !== null && (
                        <div>LLM-токены документа: {documentLlmTokenText(doc)}</div>
                      )}
                      {documentLlmModels(doc) !== null && (
                        <div>LLM-модели токенов документа: {documentLlmModels(doc)}</div>
                      )}
                    </div>
                  </div>
                )}

                {isDocumentCancelled(doc) && (
                  <div className="mb-4 rounded-xl bg-[var(--accent-warning-bg)] p-3 text-xs leading-relaxed text-[var(--accent-warning)]">
                    Документ остановлен пользователем. Он не считается завершённой базой знаний; при необходимости загрузите его заново.
                  </div>
                )}

                {isDocumentFailed(doc) && !isDocumentCancelled(doc) && (
                  <div className="mb-4 rounded-xl bg-[var(--accent-danger-bg)] p-3 text-xs leading-relaxed text-[var(--accent-danger-text)]">
                    {documentIssueText(doc) || 'Документ не удалось обработать'}
                  </div>
                )}

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
