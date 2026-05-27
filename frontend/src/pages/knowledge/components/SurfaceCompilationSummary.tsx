import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import {
  knowledgeSurfaceApi,
  type RetrievalSurface,
  type SurfaceCompilationRun,
  type SurfaceCompilationStage,
  type SurfaceMergeDecision,
  type SurfaceOwnership,
  type SurfaceReassignment,
  type SurfaceRelation,
  type SurfaceSourceUnit,
} from '@shared/api/modules/knowledgeSurface';
import { getErrorMessage } from '@shared/api/core/errors';

const FILTERS = [
  ['all', 'Все карточки'],
  ['umbrella', 'Зонтики'],
  ['child', 'Дочерние'],
  ['specific', 'Узкие'],
  ['document_upload', 'Загрузка документов'],
  ['curation', 'Курация'],
  ['retrieval_quality', 'Качество поиска'],
  ['integration', 'Интеграции'],
  ['channel', 'Каналы'],
  ['handoff', 'Передача / лимиты'],
  ['other', 'Другое'],
] as const;

type SurfaceFilter = (typeof FILTERS)[number][0];

type PipelineStep = {
  id: string;
  title: string;
  status: 'pending' | 'active' | 'completed' | 'failed' | 'stopped';
  description: string;
  detail?: string;
};

const SURFACE_KIND_LABELS: Record<string, string> = {
  umbrella: 'Зонтичная карточка',
  child: 'Дочерняя карточка',
  specific: 'Узкая карточка',
  standalone: 'Самостоятельная карточка',
  procedural: 'Процедура',
  safety: 'Безопасность',
  pricing: 'Цены',
  integration: 'Интеграция',
  handoff: 'Передача менеджеру',
  definition: 'Определение',
  curation: 'Курация',
  retrieval_quality: 'Качество поиска',
  service_limits: 'Лимиты сервиса',
  channel: 'Канал',
  document_upload: 'Загрузка документов',
  other: 'Другое',
};

const RELATION_LABELS: Record<string, string> = {
  umbrella_contains: 'содержит',
  specializes: 'уточняет',
  sibling: 'соседняя тема',
  overlaps: 'пересекается',
  duplicates: 'дубликат',
  near_duplicate: 'почти дубликат',
  contradicts: 'противоречит',
  unrelated: 'не связано',
  split_needed: 'нужно разделить',
  needs_new_parent: 'нужен новый зонтик',
  reparent_needed: 'нужно переподчинить',
};

const formatMetric = (value: unknown): string => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value.toLocaleString('ru-RU');
  }
  if (typeof value === 'string' && value.trim() !== '') return value;
  if (typeof value === 'boolean') return value ? 'да' : 'нет';
  return '';
};

const statusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    pending: 'ожидает',
    running: 'в работе',
    completed: 'готово',
    failed: 'ошибка',
    cancelled: 'остановлено',
    canceled: 'остановлено',
  };
  return labels[status] || status;
};

const stepBadgeClass = (status: PipelineStep['status']): string => {
  if (status === 'completed') {
    return 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]';
  }
  if (status === 'active') {
    return 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]';
  }
  if (status === 'failed' || status === 'stopped') {
    return 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]';
  }
  return 'bg-[var(--control-bg)] text-[var(--text-secondary)]';
};

const stageStatusFromRun = (
  run: SurfaceCompilationRun | null,
  isDocumentProcessing: boolean,
): 'pending' | 'active' | 'completed' | 'failed' | 'stopped' => {
  if (!run) return 'pending';
  if (run.status === 'failed') return 'failed';
  if (run.status === 'cancelled' || run.status === 'canceled') return 'stopped';
  if (run.status === 'completed') return 'completed';
  if (run.status === 'running' && !isDocumentProcessing) return 'stopped';
  if (run.status === 'running') return 'active';
  return 'pending';
};

const ownedQuestionsForSurface = (
  surface: RetrievalSurface,
  ownership: SurfaceOwnership[],
): SurfaceOwnership[] => (
  surface.owned_questions
  || ownership.filter((item) => item.owner_surface_key === surface.surface_key)
);

const rejectedQuestionsForSurface = (
  surface: RetrievalSurface,
  ownership: SurfaceOwnership[],
): SurfaceOwnership[] => (
  surface.rejected_questions
  || ownership.filter((item) => item.rejected_from_surface_keys.includes(surface.surface_key))
);

const relationsForSurface = (
  surface: RetrievalSurface,
  relations: SurfaceRelation[],
): SurfaceRelation[] => (
  surface.relations
  || relations.filter((item) => (
    item.parent_surface_key === surface.surface_key
    || item.child_surface_key === surface.surface_key
  ))
);

const reassignmentsForSurface = (
  surface: RetrievalSurface,
  reassignments: SurfaceReassignment[],
): SurfaceReassignment[] => [
  ...(surface.incoming_reassignments || []),
  ...(surface.outgoing_reassignments || []),
  ...reassignments.filter((item) => (
    item.from_surface_key === surface.surface_key
    || item.to_surface_key === surface.surface_key
  )),
];

const mergeDecisionsForSurface = (
  surface: RetrievalSurface,
  mergeDecisions: SurfaceMergeDecision[],
): SurfaceMergeDecision[] => (
  surface.merge_decisions
  || mergeDecisions.filter((item) => (
    item.survivor_surface_key === surface.surface_key
    || item.merged_surface_keys.includes(surface.surface_key)
    || item.keep_separate_surface_keys.includes(surface.surface_key)
  ))
);

const matchesFilter = (surface: RetrievalSurface, filter: SurfaceFilter): boolean => {
  if (filter === 'all') return true;
  if (filter === 'handoff') {
    return surface.surface_kind === 'handoff' || surface.surface_kind === 'service_limits';
  }
  if (filter === 'other') {
    return ![
      'umbrella',
      'child',
      'specific',
      'document_upload',
      'curation',
      'retrieval_quality',
      'integration',
      'channel',
      'handoff',
      'service_limits',
    ].includes(surface.surface_kind);
  }
  return surface.surface_kind === filter;
};

const compilePipelineSteps = (
  run: SurfaceCompilationRun | null,
  stages: SurfaceCompilationStage[],
  sourceUnits: SurfaceSourceUnit[],
  surfaces: RetrievalSurface[],
  relations: SurfaceRelation[],
  ownership: SurfaceOwnership[],
  reassignments: SurfaceReassignment[],
  mergeDecisions: SurfaceMergeDecision[],
  isDocumentProcessing: boolean,
): PipelineStep[] => {
  const sourceUnitCount = sourceUnits.length || Number(run?.metrics?.source_unit_count || 0);
  const surfaceCount = surfaces.length || Number(run?.metrics?.surface_count || 0);
  const relationCount = relations.length || Number(run?.metrics?.relation_count || 0);
  const ownershipCount = ownership.length || Number(run?.metrics?.ownership_count || 0);
  const reassignmentCount = reassignments.length || Number(run?.metrics?.reassignment_count || 0);
  const mergeCount = mergeDecisions.length || Number(run?.metrics?.merge_decision_count || 0);
  const baseStatus = stageStatusFromRun(run, isDocumentProcessing);

  const hasStage = (needle: string): boolean => (
    stages.some((stage) => stage.stage_kind.includes(needle) && stage.status === 'completed')
  );

  const sourceStatus: PipelineStep['status'] = sourceUnitCount > 0
    ? 'completed'
    : baseStatus === 'active'
      ? 'active'
      : baseStatus;

  const discoveryDone = surfaceCount > 0 || hasStage('discovery');
  const relationDone = relationCount > 0 || hasStage('relation');
  const answerDone = surfaces.some((surface) => surface.answer || surface.short_answer) || hasStage('answer');
  const ownershipDone = ownershipCount > 0 || reassignmentCount > 0 || hasStage('ownership');
  const reconciliationDone = relationCount > 0 || mergeCount > 0 || hasStage('reconciliation');

  return [
    {
      id: 'source_units',
      title: '1. Документ разобран на исходные блоки',
      status: sourceStatus,
      description: 'Система нарезает файл на source units — минимальные фрагменты, из которых потом рождаются карточки.',
      detail: sourceUnitCount > 0 ? `${formatMetric(sourceUnitCount)} исходных блоков готово` : 'Ждём извлечение исходных блоков',
    },
    {
      id: 'local_discovery',
      title: '2. Поиск будущих карточек в каждом блоке',
      status: discoveryDone ? 'completed' : sourceStatus === 'completed' && baseStatus === 'active' ? 'active' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'LLM проходит по каждому source unit и находит surface candidates: зонтики, дочерние и узкие карточки.',
      detail: surfaceCount > 0 ? `${formatMetric(surfaceCount)} карточек уже сохранено` : 'Карточки ещё не сохранены — это нормально до завершения LLM-стадии',
    },
    {
      id: 'local_relations',
      title: '3. Локальные связи: parent / child / sibling',
      status: relationDone ? 'completed' : discoveryDone && baseStatus === 'active' ? 'active' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'Система определяет, какие карточки являются зонтиками, какие — дочерними, а какие надо держать отдельно.',
      detail: relationCount > 0 ? `${formatMetric(relationCount)} связей найдено` : 'Связей пока нет',
    },
    {
      id: 'answers',
      title: '4. Ответы и owned questions',
      status: answerDone && ownershipDone ? 'completed' : discoveryDone && baseStatus === 'active' ? 'active' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'Для каждой карточки пишется answer, короткий ответ и список вопросов, которыми она имеет право владеть.',
      detail: `${formatMetric(ownershipCount)} owned questions · ${formatMetric(reassignmentCount)} переносов вопросов`,
    },
    {
      id: 'global_reconciliation',
      title: '5. Глобальная сборка графа',
      status: reconciliationDone ? 'completed' : ownershipDone && baseStatus === 'active' ? 'active' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'После всех блоков граф пересобирается: дубликаты мержатся, вопросы переносятся, поздние зонтики могут стать parent.',
      detail: `${formatMetric(mergeCount)} merge decisions`,
    },
    {
      id: 'curation',
      title: '6. Курация и публикация',
      status: surfaces.length > 0 ? 'active' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'Здесь уже можно смотреть карточки, проверять источники, вопросы, связи и публиковать знания в runtime retrieval.',
      detail: surfaces.length > 0 ? 'Карточки доступны ниже' : 'Кураторские карточки пока не появились',
    },
  ];
};

const pipelineSummaryText = (
  run: SurfaceCompilationRun | null,
  steps: PipelineStep[],
  isDocumentProcessing: boolean,
): string => {
  if (!run) return 'FAQ Graph pipeline ещё не стартовал.';
  if (run.status === 'failed') {
    return run.error_message || 'Pipeline завершился ошибкой. Открой технические стадии ниже.';
  }
  if (run.status === 'running' && !isDocumentProcessing) {
    return 'Документ уже не обрабатывается, но последний compiler run остался в running. Обычно это значит, что обработку остановили вручную; загрузи документ заново для нового прохода.';
  }
  const active = steps.find((step) => step.status === 'active');
  if (active) return active.description;
  const completedCount = steps.filter((step) => step.status === 'completed').length;
  if (completedCount === steps.length) return 'FAQ Graph pipeline завершён. Можно проверять и публиковать карточки.';
  return 'Pipeline ожидает следующую стадию.';
};

const QuestionChips: React.FC<{ title: string; items: SurfaceOwnership[] }> = ({
  title,
  items,
}) => {
  if (items.length === 0) return null;
  return (
    <div className="mt-2">
      <div className="mb-1 text-xs font-medium text-[var(--text-secondary)]">{title}</div>
      <div className="flex flex-wrap gap-1">
        {items.slice(0, 10).map((item) => (
          <span
            key={`${title}-${item.owner_surface_key}-${item.question}`}
            className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]"
            title={item.reason}
          >
            {item.question}
          </span>
        ))}
      </div>
    </div>
  );
};

export const SurfaceCompilationSummary: React.FC<{
  documentId: string;
  enabled: boolean;
  isDocumentProcessing: boolean;
}> = ({ documentId, enabled, isDocumentProcessing }) => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const [filter, setFilter] = React.useState<SurfaceFilter>('all');
  const queryEnabled = Boolean(projectId && enabled);
  const refetchInterval = isDocumentProcessing ? 3000 : false;

  const compilationQuery = useQuery({
    queryKey: ['knowledge-surface-compilation', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { run: null, stages: [], source_units: [] };
      const { data } = await knowledgeSurfaceApi.compilation(projectId, documentId);
      return data;
    },
    enabled: queryEnabled,
    retry: false,
    refetchInterval,
  });

  const surfacesQuery = useQuery({
    queryKey: ['knowledge-surfaces', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { surfaces: [] };
      const { data } = await knowledgeSurfaceApi.surfaces(projectId, documentId);
      return data;
    },
    enabled: queryEnabled,
    retry: false,
    refetchInterval,
  });

  const relationsQuery = useQuery({
    queryKey: ['knowledge-surface-relations', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { relations: [] };
      const { data } = await knowledgeSurfaceApi.relations(projectId, documentId);
      return data;
    },
    enabled: queryEnabled,
    retry: false,
    refetchInterval,
  });

  const ownershipQuery = useQuery({
    queryKey: ['knowledge-surface-ownership', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { ownership: [], reassignments: [] };
      const { data } = await knowledgeSurfaceApi.ownership(projectId, documentId);
      return data;
    },
    enabled: queryEnabled,
    retry: false,
    refetchInterval,
  });

  const mergeDecisionsQuery = useQuery({
    queryKey: ['knowledge-surface-merge-decisions', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { merge_decisions: [] };
      const { data } = await knowledgeSurfaceApi.mergeDecisions(projectId, documentId);
      return data;
    },
    enabled: queryEnabled,
    retry: false,
    refetchInterval,
  });

  const publishMutation = useMutation({
    mutationFn: async (surfaceId: string) => {
      if (!projectId) throw new Error('Project id is missing');
      const { data } = await knowledgeSurfaceApi.publish(projectId, documentId, surfaceId);
      return data;
    },
    onSuccess: async () => {
      toast.success('Карточка опубликована в runtime retrieval');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['knowledge-surfaces', projectId, documentId] }),
        queryClient.invalidateQueries({ queryKey: ['knowledge-surface-compilation', projectId, documentId] }),
        queryClient.invalidateQueries({ queryKey: ['knowledge-surface-merge-decisions', projectId, documentId] }),
        queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] }),
      ]);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Не удалось опубликовать карточку'));
    },
  });

  if (!enabled) return null;

  const run = compilationQuery.data?.run || null;
  const stages = compilationQuery.data?.stages || [];
  const sourceUnits = compilationQuery.data?.source_units || [];
  const surfaces = surfacesQuery.data?.surfaces || [];
  const relations = relationsQuery.data?.relations || [];
  const ownership = ownershipQuery.data?.ownership || [];
  const reassignments = ownershipQuery.data?.reassignments || [];
  const mergeDecisions = mergeDecisionsQuery.data?.merge_decisions || [];
  const filteredSurfaces = surfaces.filter((surface) => matchesFilter(surface, filter));
  const isLoading = compilationQuery.isLoading || surfacesQuery.isLoading;
  const pipelineSteps = compilePipelineSteps(
    run,
    stages,
    sourceUnits,
    surfaces,
    relations,
    ownership,
    reassignments,
    mergeDecisions,
    isDocumentProcessing,
  );
  const completedSteps = pipelineSteps.filter((step) => step.status === 'completed').length;
  const progressPercent = Math.round((completedSteps / pipelineSteps.length) * 100);
  const summaryText = pipelineSummaryText(run, pipelineSteps, isDocumentProcessing);

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3 text-sm">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h5 className="font-semibold text-[var(--text-primary)]">
            FAQ Graph Pipeline
          </h5>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-[var(--text-muted)]">
            {summaryText}
          </p>
          {run && (
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              run: {statusLabel(run.status)} · {run.compiler_kind || 'compiler'} · {run.prompt_version}
            </p>
          )}
        </div>

        <div className="min-w-[160px] text-right text-xs text-[var(--text-secondary)]">
          <div>{completedSteps}/{pipelineSteps.length} стадий</div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--control-bg)]">
            <div
              className="h-full rounded-full bg-[var(--accent-primary)] transition-all"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </div>

      <div className="mb-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {pipelineSteps.map((step) => (
          <div
            key={step.id}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-3"
          >
            <div className="mb-1 flex items-start justify-between gap-2">
              <div className="text-xs font-semibold text-[var(--text-primary)]">{step.title}</div>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${stepBadgeClass(step.status)}`}>
                {statusLabel(step.status)}
              </span>
            </div>
            <p className="text-xs leading-relaxed text-[var(--text-muted)]">{step.description}</p>
            {step.detail && (
              <p className="mt-1 text-xs text-[var(--text-secondary)]">{step.detail}</p>
            )}
          </div>
        ))}
      </div>

      {run?.metrics && (
        <div className="mb-3 flex flex-wrap gap-1 text-xs text-[var(--text-secondary)]">
          {[
            ['source_unit_count', 'source units'],
            ['candidate_count', 'candidates'],
            ['surface_count', 'cards'],
            ['relation_count', 'relations'],
            ['ownership_count', 'owned questions'],
            ['reassignment_count', 'question moves'],
            ['merge_decision_count', 'merges'],
            ['warning_count', 'warnings'],
          ].map(([key, label]) => {
            const value = formatMetric(run.metrics[key]);
            return value ? (
              <span key={key} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                {label}: {value}
              </span>
            ) : null;
          })}
        </div>
      )}

      <div className="mb-3 flex flex-wrap gap-1 text-xs">
        {FILTERS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={`rounded-full px-2 py-0.5 transition-colors ${
              filter === value
                ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]'
                : 'bg-[var(--control-bg)] text-[var(--text-secondary)]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {stages.length > 0 && (
        <details className="mb-3 rounded-lg bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-secondary)]">
          <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
            Технические события backend
          </summary>
          <div className="mt-2 flex flex-wrap gap-1">
            {stages.map((stage) => (
              <span
                key={stage.id}
                className="rounded-full bg-[var(--control-bg)] px-2 py-0.5"
                title={stage.error_message || stage.output_summary}
              >
                {stage.stage_kind}: {statusLabel(stage.status)}
              </span>
            ))}
          </div>
        </details>
      )}

      {surfaces.length === 0 ? (
        <div className="rounded-lg bg-[var(--surface-elevated)] p-3 text-xs leading-relaxed text-[var(--text-muted)]">
          {isLoading ? (
            'Загружаю состояние graph pipeline…'
          ) : run?.status === 'running' && !isDocumentProcessing ? (
            'Карточек нет, потому что документ уже не обрабатывается, а последний compiler run остался в running. Вероятнее всего, обработку остановили до сохранения карточек. Для проверки нового пайплайна загрузи документ заново.'
          ) : run ? (
            'Карточки ещё не сохранены. Смотри стадии выше: если active стоит на discovery/answer synthesis, LLM ещё собирает graph context.'
          ) : (
            'FAQ graph run ещё не создан.'
          )}
        </div>
      ) : filteredSurfaces.length === 0 ? (
        <p className="text-xs text-[var(--text-muted)]">Нет карточек под выбранный фильтр.</p>
      ) : (
        <div className="space-y-2">
          {filteredSurfaces.map((surface) => {
            const ownedQuestions = ownedQuestionsForSurface(surface, ownership);
            const rejectedQuestions = rejectedQuestionsForSurface(surface, ownership);
            const surfaceRelations = relationsForSurface(surface, relations);
            const surfaceReassignments = reassignmentsForSurface(surface, reassignments);
            const surfaceMergeDecisions = mergeDecisionsForSurface(surface, mergeDecisions);
            const isPublished = surface.publication_status === 'published' || Boolean(surface.linked_runtime_entry_id);
            const kindLabel = SURFACE_KIND_LABELS[surface.surface_kind] || surface.surface_kind;

            return (
              <div key={surface.id} className="rounded-lg bg-[var(--surface-elevated)] p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <h6 className="font-medium text-[var(--text-primary)]">{surface.title}</h6>
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                        {kindLabel}
                      </span>
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                        {statusLabel(surface.status)} / {statusLabel(surface.publication_status)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">{surface.canonical_question}</p>
                  </div>

                  <button
                    type="button"
                    disabled={isPublished || publishMutation.isPending}
                    onClick={() => publishMutation.mutate(surface.id)}
                    className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isPublished ? 'Опубликовано' : 'Опубликовать'}
                  </button>
                </div>

                <p className="mt-2 text-xs leading-relaxed text-[var(--text-primary)]">
                  {surface.short_answer || surface.answer}
                </p>

                {surface.short_answer && surface.answer && surface.short_answer !== surface.answer && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]">
                    <summary className="cursor-pointer">Полный ответ</summary>
                    <p className="mt-1 whitespace-pre-wrap leading-relaxed">{surface.answer}</p>
                  </details>
                )}

                {surface.warnings.length > 0 && (
                  <div className="mt-2 rounded-lg bg-[var(--accent-warning-bg)] p-2 text-xs text-[var(--accent-warning-text)]">
                    {surface.warnings.join(' · ')}
                  </div>
                )}

                <QuestionChips title="Вопросы, которыми карточка владеет" items={ownedQuestions} />
                <QuestionChips title="Вопросы, которые перенесены к другим карточкам" items={rejectedQuestions} />

                {surfaceReassignments.length > 0 && (
                  <div className="mt-2 text-xs text-[var(--text-muted)]">
                    Переносы вопросов: {surfaceReassignments.map((item) => `${item.question}: ${item.from_surface_key} → ${item.to_surface_key}`).join(' · ')}
                  </div>
                )}

                {surfaceRelations.length > 0 && (
                  <div className="mt-2 text-xs text-[var(--text-muted)]">
                    Связи: {surfaceRelations.map((item) => `${item.parent_surface_key} ${RELATION_LABELS[item.relation_type] || item.relation_type} ${item.child_surface_key}`).join(' · ')}
                  </div>
                )}

                {surfaceMergeDecisions.length > 0 && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]">
                    <summary className="cursor-pointer">Merge decisions</summary>
                    <div className="mt-1 space-y-1">
                      {surfaceMergeDecisions.map((item) => (
                        <p key={item.id}>
                          {item.decision_type}: survivor {item.survivor_surface_key}; merged [{item.merged_surface_keys.join(', ') || '—'}]; keep separate [{item.keep_separate_surface_keys.join(', ') || '—'}]. {item.reason}
                        </p>
                      ))}
                    </div>
                  </details>
                )}

                {(surface.source_excerpt || surface.source_chunk_indexes.length > 0) && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]">
                    <summary className="cursor-pointer">Source evidence</summary>
                    <p className="mt-1">chunks: {surface.source_chunk_indexes.join(', ') || '—'}</p>
                    {surface.source_excerpt && <p className="mt-1 whitespace-pre-wrap">{surface.source_excerpt}</p>}
                  </details>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
