import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import { getErrorMessage } from '@shared/api/core/errors';
import {
  knowledgeSurfaceApi,
  type RetrievalSurface,
  type SurfaceCompilationRun,
  type SurfaceCompilationStage,
  type SurfaceMergeDecision,
  type SurfaceOwnership,
  type SurfaceReassignment,
  type SurfaceRelation,
} from '@shared/api/modules/knowledgeSurface';

import { buildSurfacePipelineContract, type SurfacePipelineContract } from './surfacePipelineContract';

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
type StepStatus = 'pending' | 'active' | 'completed' | 'failed' | 'stopped';

type PipelineStep = {
  id: string;
  title: string;
  status: StepStatus;
  description: string;
  detail?: string;
};

type LiveProgress = {
  title: string;
  status: string;
  message: string;
  detail: string;
  percent: number | null;
};

type RelationNode = {
  surface: RetrievalSurface;
  children: SurfaceRelation[];
  duplicates: SurfaceRelation[];
  siblings: SurfaceRelation[];
};

const LIVE_STAGE_LABELS: Record<string, string> = {
  source_units: 'Документ разобран на исходные блоки',
  surface_discovery: 'Ищем answer slots',
  relation_planning: 'Строим локальные связи',
  answer_synthesis: 'Пишем ответы',
  question_ownership: 'Назначаем вопросы',
  partial_surface_cards: 'Сохраняем промежуточные карточки',
  global_reconciliation: 'Собираем глобальную карту',
  global_relation_judge: 'Проверяем связи и дубликаты',
  question_reassignment: 'Переносим вопросы между карточками',
  faq_surface_compilation: 'Компилируем FAQ Answer Slots',
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
  umbrella_contains: 'родитель → ребёнок',
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

const CONTRACT_STATUS_LABELS: Record<SurfacePipelineContract['status'], string> = {
  not_started: 'не стартовал',
  processing: 'обрабатывается',
  ready_for_curation: 'готово к курации',
  completed_with_warnings: 'готово с предупреждениями',
  failed: 'ошибка',
  stopped: 'остановлено',
};

const statusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    pending: 'ожидает',
    running: 'в работе',
    completed: 'готово',
    failed: 'ошибка',
    cancelled: 'остановлено',
    canceled: 'остановлено',
    published: 'опубликовано',
    unpublished: 'не опубликовано',
    publishing: 'публикуется',
    publish_failed: 'ошибка публикации',
    draft: 'черновик',
    needs_review: 'нужна проверка',
    rejected: 'отклонено',
    merged: 'слито',
    superseded: 'заменено',
  };
  return labels[status] || status;
};

const metricNumber = (metrics: Record<string, unknown> | undefined, key: string): number | null => {
  const value = metrics?.[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const formatMetric = (value: unknown): string => {
  if (typeof value === 'number' && Number.isFinite(value)) return value.toLocaleString('ru-RU');
  if (typeof value === 'string' && value.trim() !== '') return value;
  if (typeof value === 'boolean') return value ? 'да' : 'нет';
  return '';
};

const stepBadgeClass = (status: StepStatus): string => {
  if (status === 'completed') return 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]';
  if (status === 'active') return 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]';
  if (status === 'failed' || status === 'stopped') return 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]';
  return 'bg-[var(--control-bg)] text-[var(--text-secondary)]';
};

const contractBadgeClass = (status: SurfacePipelineContract['status']): string => {
  if (status === 'ready_for_curation') return 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]';
  if (status === 'completed_with_warnings') return 'bg-[var(--accent-warning-bg)] text-[var(--accent-warning-text)]';
  if (status === 'failed' || status === 'stopped') return 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]';
  return 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]';
};

const latestMeaningfulStage = (stages: SurfaceCompilationStage[]): SurfaceCompilationStage | null => {
  for (let index = stages.length - 1; index >= 0; index -= 1) {
    const stage = stages[index];
    if (stage.stage_kind !== 'source_units') return stage;
  }
  return stages.length > 0 ? stages[stages.length - 1] : null;
};

const liveProgressFromStages = (stages: SurfaceCompilationStage[], run: SurfaceCompilationRun | null): LiveProgress | null => {
  const stage = latestMeaningfulStage(stages);
  if (!stage) return null;

  const sourceUnitIndex = metricNumber(stage.metrics, 'source_unit_index');
  const sourceUnitCount = metricNumber(stage.metrics, 'source_unit_count') ?? metricNumber(run?.metrics, 'source_unit_count');
  const candidateIndex = metricNumber(stage.metrics, 'candidate_index');
  const candidateCount = metricNumber(stage.metrics, 'candidate_count');
  const elapsedSeconds = metricNumber(stage.metrics, 'elapsed_seconds');
  const tokensTotal = metricNumber(stage.metrics, 'tokens_total');
  const llmCallCount = metricNumber(stage.metrics, 'llm_call_count');
  const fallbackCallCount = metricNumber(stage.metrics, 'fallback_call_count');
  const concurrency = metricNumber(stage.metrics, 'concurrency');

  let percent: number | null = null;
  if (sourceUnitIndex && sourceUnitCount && sourceUnitCount > 0) {
    const unitBase = Math.max(0, sourceUnitIndex - 1);
    const candidatePart = candidateIndex && candidateCount && candidateCount > 0 ? candidateIndex / candidateCount : 1;
    percent = Math.max(1, Math.min(99, Math.round(((unitBase + candidatePart) / sourceUnitCount) * 100)));
  }

  const detail = [
    sourceUnitIndex && sourceUnitCount ? `Блок ${sourceUnitIndex}/${sourceUnitCount}` : '',
    candidateIndex && candidateCount ? `карточка ${candidateIndex}/${candidateCount}` : '',
    stage.output_summary || stage.input_summary || '',
    elapsedSeconds !== null ? `${elapsedSeconds} сек` : '',
    tokensTotal !== null ? `${tokensTotal.toLocaleString('ru-RU')} токенов` : '',
    llmCallCount !== null ? `${llmCallCount} LLM вызовов` : '',
    fallbackCallCount !== null && fallbackCallCount > 0 ? `${fallbackCallCount} fallback` : '',
    concurrency !== null ? `parallel=${concurrency}` : '',
  ].filter(Boolean).join(' · ');

  return {
    title: LIVE_STAGE_LABELS[stage.stage_kind] || stage.stage_kind,
    status: stage.status,
    message: stage.error_message || stage.output_summary || stage.input_summary || statusLabel(stage.status),
    detail: detail || 'Ожидаю следующий backend event…',
    percent,
  };
};

const surfaceTitle = (surfaceKey: string, surfaceByKey: Map<string, RetrievalSurface>): string => {
  const surface = surfaceByKey.get(surfaceKey);
  return surface ? `${surface.title} (${surfaceKey})` : surfaceKey;
};

const matchesFilter = (surface: RetrievalSurface, filter: SurfaceFilter): boolean => {
  if (filter === 'all') return true;
  if (filter === 'handoff') return surface.surface_kind === 'handoff' || surface.surface_kind === 'service_limits';
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

const ownedQuestionsForSurface = (surface: RetrievalSurface, ownership: SurfaceOwnership[]): SurfaceOwnership[] => (
  surface.owned_questions || ownership.filter((item) => item.owner_surface_key === surface.surface_key)
);

const rejectedQuestionsForSurface = (surface: RetrievalSurface, ownership: SurfaceOwnership[]): SurfaceOwnership[] => (
  surface.rejected_questions || ownership.filter((item) => item.rejected_from_surface_keys.includes(surface.surface_key))
);

const relationsForSurface = (surface: RetrievalSurface, relations: SurfaceRelation[]): SurfaceRelation[] => (
  surface.relations || relations.filter((item) => item.parent_surface_key === surface.surface_key || item.child_surface_key === surface.surface_key)
);

const reassignmentsForSurface = (surface: RetrievalSurface, reassignments: SurfaceReassignment[]): SurfaceReassignment[] => [
  ...(surface.incoming_reassignments || []),
  ...(surface.outgoing_reassignments || []),
  ...reassignments.filter((item) => item.from_surface_key === surface.surface_key || item.to_surface_key === surface.surface_key),
];

const mergeDecisionsForSurface = (surface: RetrievalSurface, mergeDecisions: SurfaceMergeDecision[]): SurfaceMergeDecision[] => (
  surface.merge_decisions || mergeDecisions.filter((item) => (
    item.survivor_surface_key === surface.surface_key
    || item.merged_surface_keys.includes(surface.surface_key)
    || item.keep_separate_surface_keys.includes(surface.surface_key)
  ))
);

const buildPipelineSteps = (contract: SurfacePipelineContract): PipelineStep[] => {
  const activeOrPending: StepStatus = contract.status === 'failed'
    ? 'failed'
    : contract.status === 'stopped'
      ? 'stopped'
      : contract.status === 'processing'
        ? 'active'
        : 'pending';
  const completedWhen = (condition: boolean): StepStatus => (condition ? 'completed' : activeOrPending);

  return [
    {
      id: 'source_units',
      title: '1. Исходные блоки',
      status: completedWhen(contract.counters.sourceUnits > 0),
      description: 'Файл разобран на source units — смысловые блоки для answer slots.',
      detail: `${contract.counters.sourceUnits} source units`,
    },
    {
      id: 'surfaces',
      title: '2. Answer slots',
      status: completedWhen(contract.counters.surfaces > 0),
      description: 'Материализованы карточки для курации, а не только raw candidates.',
      detail: `${contract.counters.surfaces} surfaces`,
    },
    {
      id: 'relations',
      title: '3. Карта связей',
      status: completedWhen(contract.counters.relations > 0 || contract.counters.surfaces <= 1),
      description: 'Построены parent/child, sibling и duplicate/same-intent связи.',
      detail: `${contract.counters.parentChildRelations} parent/child · ${contract.counters.duplicateRelations} duplicates`,
    },
    {
      id: 'ownership',
      title: '4. Ownership вопросов',
      status: completedWhen(contract.counters.ownership > 0 || contract.counters.surfaces === 0),
      description: 'Вопросы закреплены за тем answer slot, который должен отвечать.',
      detail: `${contract.counters.ownership} owned · ${contract.counters.reassignments} moved`,
    },
    {
      id: 'merge_audit',
      title: '5. Merge / audit',
      status: completedWhen(contract.counters.mergeDecisions > 0 || contract.counters.surfaces <= 1),
      description: 'Видно, какие same-intent карточки слиты или оставлены раздельно.',
      detail: `${contract.counters.mergeDecisions} decisions`,
    },
    {
      id: 'curation',
      title: '6. Курация / runtime publish',
      status: contract.readyForCuration ? 'completed' : activeOrPending,
      description: 'UI может безопасно показывать карточки, связи, source evidence и publish buttons.',
      detail: `${contract.counters.runtimeLinkedSurfaces} already linked to runtime`,
    },
  ];
};

const buildRelationNodes = (surfaces: RetrievalSurface[], relations: SurfaceRelation[]): RelationNode[] => {
  const nodes = new Map<string, RelationNode>();
  for (const surface of surfaces) {
    nodes.set(surface.surface_key, { surface, children: [], duplicates: [], siblings: [] });
  }

  for (const relation of relations) {
    const parent = nodes.get(relation.parent_surface_key);
    const child = nodes.get(relation.child_surface_key);
    if (relation.relation_type === 'umbrella_contains' || relation.relation_type === 'specializes') {
      parent?.children.push(relation);
    } else if (relation.relation_type === 'duplicates' || relation.relation_type === 'near_duplicate') {
      parent?.duplicates.push(relation);
      child?.duplicates.push(relation);
    } else if (relation.relation_type === 'sibling') {
      parent?.siblings.push(relation);
      child?.siblings.push(relation);
    }
  }

  return [...nodes.values()].sort((left, right) => {
    const leftScore = left.children.length * 10 + left.duplicates.length * 4 + left.siblings.length;
    const rightScore = right.children.length * 10 + right.duplicates.length * 4 + right.siblings.length;
    return rightScore - leftScore || left.surface.title.localeCompare(right.surface.title);
  });
};

const QuestionChips: React.FC<{ title: string; items: SurfaceOwnership[] }> = ({ title, items }) => {
  if (items.length === 0) return null;
  return (
    <div className="mt-2">
      <div className="mb-1 text-xs font-medium text-[var(--text-secondary)]">{title}</div>
      <div className="flex flex-wrap gap-1">
        {items.slice(0, 10).map((item) => (
          <span key={`${title}-${item.owner_surface_key}-${item.question}`} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]" title={item.reason}>
            {item.question}
          </span>
        ))}
      </div>
    </div>
  );
};

const ContractPanel: React.FC<{ contract: SurfacePipelineContract }> = ({ contract }) => (
  <div className={`mb-3 rounded-xl border p-3 text-xs ${contract.readyForCuration ? 'border-[var(--accent-success-bg)] bg-[var(--accent-success-bg)]/40' : 'border-[var(--border-subtle)] bg-[var(--surface-elevated)]'}`}>
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <div className="font-semibold text-[var(--text-primary)]">Контракт данных FAQ Answer Slot Pipeline</div>
        <p className="mt-1 text-[var(--text-secondary)]">{contract.statusReason}</p>
      </div>
      <span className={`rounded-full px-2 py-0.5 font-medium ${contractBadgeClass(contract.status)}`}>
        {CONTRACT_STATUS_LABELS[contract.status]}
      </span>
    </div>

    <div className="mt-2 flex flex-wrap gap-1">
      {Object.entries(contract.counters).map(([key, value]) => (
        <span key={key} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
          {key}: {value}
        </span>
      ))}
    </div>

    {contract.blockingReasons.length > 0 && (
      <div className="mt-2 rounded-lg bg-[var(--accent-danger-bg)] p-2 text-[var(--accent-danger-text)]">
        <div className="font-medium">Блокирует курацию</div>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          {contract.blockingReasons.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
    )}

    {contract.warnings.length > 0 && (
      <div className="mt-2 rounded-lg bg-[var(--accent-warning-bg)] p-2 text-[var(--accent-warning-text)]">
        <div className="font-medium">Предупреждения</div>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          {contract.warnings.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
    )}
  </div>
);

const RelationMap: React.FC<{
  surfaces: RetrievalSurface[];
  relations: SurfaceRelation[];
  mergeDecisions: SurfaceMergeDecision[];
  reassignments: SurfaceReassignment[];
}> = ({ surfaces, relations, mergeDecisions, reassignments }) => {
  const surfaceByKey = React.useMemo(() => new Map(surfaces.map((surface) => [surface.surface_key, surface])), [surfaces]);
  const nodes = React.useMemo(() => buildRelationNodes(surfaces, relations), [surfaces, relations]);
  const importantNodes = nodes.filter((node) => node.children.length > 0 || node.duplicates.length > 0 || node.siblings.length > 0).slice(0, 32);

  if (surfaces.length === 0) return null;

  return (
    <details className="mb-3 rounded-lg bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-secondary)]" open>
      <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
        Карта связей answer slots: parent → children / same-intent / переносы вопросов
      </summary>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        {importantNodes.length === 0 ? (
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3 text-[var(--text-muted)]">
            Связей пока нет. Если run уже completed и карточек много, это проблема контракта relation map.
          </div>
        ) : importantNodes.map((node) => (
          <div key={node.surface.surface_key} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-semibold text-[var(--text-primary)]">{node.surface.title}</span>
              <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
                {SURFACE_KIND_LABELS[node.surface.surface_kind] || node.surface.surface_kind}
              </span>
              <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-0.5 text-[10px] text-[var(--accent-primary)]">
                {node.children.length} children · {node.duplicates.length} same-intent · {node.siblings.length} siblings
              </span>
            </div>

            {node.children.length > 0 && (
              <div className="mt-2 space-y-1">
                <div className="font-medium text-[var(--text-primary)]">Дочерние карточки</div>
                {node.children.map((relation) => (
                  <div key={relation.id || `${relation.parent_surface_key}-${relation.child_surface_key}`} className="rounded bg-[var(--control-bg)] px-2 py-1">
                    <span className="font-medium text-[var(--text-primary)]">→ {surfaceTitle(relation.child_surface_key, surfaceByKey)}</span>
                    <span className="ml-1 text-[var(--text-muted)]">{RELATION_LABELS[relation.relation_type] || relation.relation_type}</span>
                    {relation.reason && <div className="mt-0.5 text-[var(--text-muted)]">{relation.reason}</div>}
                  </div>
                ))}
              </div>
            )}

            {node.duplicates.length > 0 && (
              <div className="mt-2 space-y-1">
                <div className="font-medium text-[var(--text-primary)]">Same-intent / merge candidates</div>
                {node.duplicates.map((relation) => {
                  const otherKey = relation.parent_surface_key === node.surface.surface_key ? relation.child_surface_key : relation.parent_surface_key;
                  return (
                    <div key={relation.id || `${relation.parent_surface_key}-${relation.child_surface_key}`} className="rounded bg-[var(--control-bg)] px-2 py-1">
                      <span className="font-medium text-[var(--text-primary)]">↔ {surfaceTitle(otherKey, surfaceByKey)}</span>
                      {relation.reason && <div className="mt-0.5 text-[var(--text-muted)]">{relation.reason}</div>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      {(mergeDecisions.length > 0 || reassignments.length > 0) && (
        <div className="mt-3 grid gap-3 xl:grid-cols-2">
          {mergeDecisions.length > 0 && (
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3">
              <div className="mb-2 font-medium text-[var(--text-primary)]">Merge decisions</div>
              <div className="max-h-52 space-y-1 overflow-y-auto">
                {mergeDecisions.map((item) => (
                  <div key={item.id} className="rounded bg-[var(--control-bg)] px-2 py-1">
                    <div className="font-medium text-[var(--text-primary)]">survivor: {surfaceTitle(item.survivor_surface_key, surfaceByKey)}</div>
                    <div>merged: {item.merged_surface_keys.map((key) => surfaceTitle(key, surfaceByKey)).join(', ') || '—'}</div>
                    {item.reason && <div className="text-[var(--text-muted)]">{item.reason}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {reassignments.length > 0 && (
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3">
              <div className="mb-2 font-medium text-[var(--text-primary)]">Переносы вопросов</div>
              <div className="max-h-52 space-y-1 overflow-y-auto">
                {reassignments.map((item) => (
                  <div key={item.id || `${item.question}-${item.from_surface_key}-${item.to_surface_key}`} className="rounded bg-[var(--control-bg)] px-2 py-1">
                    <div className="font-medium text-[var(--text-primary)]">{item.question}</div>
                    <div>{surfaceTitle(item.from_surface_key, surfaceByKey)} → {surfaceTitle(item.to_surface_key, surfaceByKey)}</div>
                    {item.reason && <div className="text-[var(--text-muted)]">{item.reason}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </details>
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
  const contract = buildSurfacePipelineContract({
    run,
    stages,
    sourceUnits,
    surfaces,
    relations,
    ownership,
    reassignments,
    mergeDecisions,
    isDocumentProcessing,
  });
  const pipelineSteps = buildPipelineSteps(contract);
  const completedSteps = pipelineSteps.filter((step) => step.status === 'completed').length;
  const progressPercent = Math.round((completedSteps / pipelineSteps.length) * 100);
  const liveProgress = liveProgressFromStages(stages, run);
  const visibleProgressPercent = liveProgress?.percent ?? progressPercent;
  const filteredSurfaces = surfaces.filter((surface) => matchesFilter(surface, filter));
  const isLoading = compilationQuery.isLoading || surfacesQuery.isLoading;
  const surfaceByKey = new Map(surfaces.map((surface) => [surface.surface_key, surface]));

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3 text-sm">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h5 className="font-semibold text-[var(--text-primary)]">FAQ Answer Slot Pipeline</h5>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-[var(--text-muted)]">
            {contract.statusReason}
          </p>
          {run && (
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              run: {statusLabel(run.status)} · {run.compiler_kind || 'compiler'} · {run.prompt_version}
            </p>
          )}
        </div>

        <div className="min-w-[180px] text-right text-xs text-[var(--text-secondary)]">
          <div>{liveProgress?.percent ? `${liveProgress.percent}%` : `${completedSteps}/${pipelineSteps.length} стадий`}</div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--control-bg)]">
            <div className="h-full rounded-full bg-[var(--accent-primary)] transition-all" style={{ width: `${visibleProgressPercent}%` }} />
          </div>
        </div>
      </div>

      <ContractPanel contract={contract} />

      {liveProgress && (
        <div className="mb-3 rounded-xl border border-[var(--accent-primary)]/20 bg-[var(--accent-primary)]/10 p-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-[var(--accent-primary)]">Сейчас выполняется</div>
              <div className="mt-1 font-semibold text-[var(--text-primary)]">{liveProgress.title}</div>
              <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{liveProgress.detail}</p>
              {liveProgress.message && <p className="mt-1 text-xs leading-relaxed text-[var(--text-muted)]">{liveProgress.message}</p>}
            </div>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${stepBadgeClass(liveProgress.status === 'completed' ? 'completed' : liveProgress.status === 'failed' ? 'failed' : 'active')}`}>
              {statusLabel(liveProgress.status)}
            </span>
          </div>
        </div>
      )}

      <details className="mb-3 rounded-lg bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-secondary)]" open={!contract.readyForCuration}>
        <summary className="cursor-pointer font-medium text-[var(--text-primary)]">Карта стадий FAQ Answer Slot Pipeline</summary>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {pipelineSteps.map((step) => (
            <div key={step.id} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3">
              <div className="mb-1 flex items-start justify-between gap-2">
                <div className="text-xs font-semibold text-[var(--text-primary)]">{step.title}</div>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${stepBadgeClass(step.status)}`}>{statusLabel(step.status)}</span>
              </div>
              <p className="text-xs leading-relaxed text-[var(--text-muted)]">{step.description}</p>
              {step.detail && <p className="mt-1 text-xs text-[var(--text-secondary)]">{step.detail}</p>}
            </div>
          ))}
        </div>
      </details>

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
            ['elapsed_seconds', 'elapsed'],
            ['llm_call_count', 'LLM calls'],
            ['tokens_total', 'tokens'],
            ['fallback_call_count', 'fallbacks'],
            ['concurrency', 'parallel'],
          ].map(([key, label]) => {
            const value = formatMetric(run.metrics[key]);
            return value ? <span key={key} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">{label}: {value}</span> : null;
          })}
        </div>
      )}

      <RelationMap surfaces={surfaces} relations={relations} mergeDecisions={mergeDecisions} reassignments={reassignments} />

      {surfaces.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1 text-xs">
          {FILTERS.map(([value, label]) => (
            <button key={value} type="button" onClick={() => setFilter(value)} className={`rounded-full px-2 py-0.5 transition-colors ${filter === value ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]' : 'bg-[var(--control-bg)] text-[var(--text-secondary)]'}`}>
              {label}
            </button>
          ))}
        </div>
      )}

      {stages.length > 0 && (
        <details className="mb-3 rounded-lg bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-secondary)]">
          <summary className="cursor-pointer font-medium text-[var(--text-primary)]">Технические события backend</summary>
          <div className="mt-2 flex max-h-40 flex-wrap gap-1 overflow-y-auto">
            {stages.slice(-120).map((stage) => (
              <span key={stage.id} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5" title={stage.error_message || stage.output_summary || stage.input_summary}>
                {stage.stage_kind}: {statusLabel(stage.status)}
              </span>
            ))}
          </div>
        </details>
      )}

      {!contract.readyForCuration && surfaces.length === 0 ? (
        <div className="rounded-lg bg-[var(--surface-elevated)] p-3 text-xs leading-relaxed text-[var(--text-muted)]">
          {isLoading ? 'Загружаю состояние pipeline…' : contract.statusReason}
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
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">{kindLabel}</span>
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">{statusLabel(surface.status)} / {statusLabel(surface.publication_status)}</span>
                    </div>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">{surface.canonical_question}</p>
                    <p className="mt-1 text-[10px] text-[var(--text-muted)]">key: {surface.surface_key}</p>
                  </div>

                  <button type="button" disabled={isPublished || publishMutation.isPending || !contract.canPublishRuntime} onClick={() => publishMutation.mutate(surface.id)} className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20 disabled:cursor-not-allowed disabled:opacity-50">
                    {isPublished ? 'Опубликовано' : 'Опубликовать'}
                  </button>
                </div>

                <p className="mt-2 text-xs leading-relaxed text-[var(--text-primary)]">{surface.short_answer || surface.answer}</p>

                {surface.short_answer && surface.answer && surface.short_answer !== surface.answer && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]">
                    <summary className="cursor-pointer">Полный ответ</summary>
                    <p className="mt-1 whitespace-pre-wrap leading-relaxed">{surface.answer}</p>
                  </details>
                )}

                {surface.warnings.length > 0 && <div className="mt-2 rounded-lg bg-[var(--accent-warning-bg)] p-2 text-xs text-[var(--accent-warning-text)]">{surface.warnings.join(' · ')}</div>}
                <QuestionChips title="Вопросы, которыми карточка владеет" items={ownedQuestions} />
                <QuestionChips title="Вопросы, которые перенесены к другим карточкам" items={rejectedQuestions} />

                {surfaceRelations.length > 0 && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]" open={surface.surface_kind === 'umbrella'}>
                    <summary className="cursor-pointer">Связи этой карточки</summary>
                    <div className="mt-1 space-y-1">
                      {surfaceRelations.map((item) => (
                        <p key={item.id || `${item.parent_surface_key}-${item.child_surface_key}-${item.relation_type}`}>
                          {surfaceTitle(item.parent_surface_key, surfaceByKey)} {RELATION_LABELS[item.relation_type] || item.relation_type} {surfaceTitle(item.child_surface_key, surfaceByKey)}{item.reason ? ` — ${item.reason}` : ''}
                        </p>
                      ))}
                    </div>
                  </details>
                )}

                {surfaceReassignments.length > 0 && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]">
                    <summary className="cursor-pointer">Переносы вопросов карточки</summary>
                    <div className="mt-1 space-y-1">
                      {surfaceReassignments.map((item) => (
                        <p key={item.id || `${item.question}-${item.from_surface_key}-${item.to_surface_key}`}>{item.question}: {surfaceTitle(item.from_surface_key, surfaceByKey)} → {surfaceTitle(item.to_surface_key, surfaceByKey)}</p>
                      ))}
                    </div>
                  </details>
                )}

                {surfaceMergeDecisions.length > 0 && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]">
                    <summary className="cursor-pointer">Merge decisions</summary>
                    <div className="mt-1 space-y-1">
                      {surfaceMergeDecisions.map((item) => (
                        <p key={item.id}>{item.decision_type}: survivor {surfaceTitle(item.survivor_surface_key, surfaceByKey)}; merged [{item.merged_surface_keys.map((key) => surfaceTitle(key, surfaceByKey)).join(', ') || '—'}]. {item.reason}</p>
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
