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
  type SurfaceSourceUnit,
} from '@shared/api/modules/knowledgeSurface';

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
  parents: SurfaceRelation[];
  siblings: SurfaceRelation[];
  duplicates: SurfaceRelation[];
};

const LIVE_STAGE_LABELS: Record<string, string> = {
  source_units: 'Документ разобран на исходные блоки',
  surface_discovery: 'Ищем answer slots',
  relation_planning: 'Строим локальные связи',
  answer_synthesis: 'Пишем ответы',
  question_ownership: 'Назначаем вопросы',
  partial_surface_cards: 'Сохраняем промежуточные карточки',
  global_reconciliation: 'Собираем глобальный граф',
  global_relation_judge: 'Проверяем связи и дубликаты',
  question_reassignment: 'Переносим вопросы между карточками',
  faq_surface_compilation: 'Компилируем FAQ graph',
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

const metricNumber = (
  metrics: Record<string, unknown> | undefined,
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

const formatMetric = (value: unknown): string => {
  if (typeof value === 'number' && Number.isFinite(value)) return value.toLocaleString('ru-RU');
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

const stepBadgeClass = (status: StepStatus): string => {
  if (status === 'completed') return 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]';
  if (status === 'active') return 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]';
  if (status === 'failed' || status === 'stopped') return 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)]';
  return 'bg-[var(--control-bg)] text-[var(--text-secondary)]';
};

const stageStatusFromRun = (
  run: SurfaceCompilationRun | null,
  isDocumentProcessing: boolean,
): StepStatus => {
  if (!run) return 'pending';
  if (run.status === 'failed') return 'failed';
  if (run.status === 'cancelled' || run.status === 'canceled') return 'stopped';
  if (run.status === 'completed') return 'completed';
  if (run.status === 'running' && !isDocumentProcessing) return 'stopped';
  if (run.status === 'running') return 'active';
  return 'pending';
};

const latestMeaningfulStage = (
  stages: SurfaceCompilationStage[],
): SurfaceCompilationStage | null => {
  for (let index = stages.length - 1; index >= 0; index -= 1) {
    const stage = stages[index];
    if (stage.stage_kind !== 'source_units') return stage;
  }
  return stages.length > 0 ? stages[stages.length - 1] : null;
};

const liveProgressFromStages = (
  stages: SurfaceCompilationStage[],
  run: SurfaceCompilationRun | null,
): LiveProgress | null => {
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

const surfaceTitle = (
  surfaceKey: string,
  surfaceByKey: Map<string, RetrievalSurface>,
): string => {
  const surface = surfaceByKey.get(surfaceKey);
  return surface ? `${surface.title} (${surfaceKey})` : surfaceKey;
};

const ownedQuestionsForSurface = (
  surface: RetrievalSurface,
  ownership: SurfaceOwnership[],
): SurfaceOwnership[] => (
  surface.owned_questions || ownership.filter((item) => item.owner_surface_key === surface.surface_key)
);

const rejectedQuestionsForSurface = (
  surface: RetrievalSurface,
  ownership: SurfaceOwnership[],
): SurfaceOwnership[] => (
  surface.rejected_questions || ownership.filter((item) => item.rejected_from_surface_keys.includes(surface.surface_key))
);

const relationsForSurface = (
  surface: RetrievalSurface,
  relations: SurfaceRelation[],
): SurfaceRelation[] => (
  surface.relations || relations.filter((item) => item.parent_surface_key === surface.surface_key || item.child_surface_key === surface.surface_key)
);

const reassignmentsForSurface = (
  surface: RetrievalSurface,
  reassignments: SurfaceReassignment[],
): SurfaceReassignment[] => [
  ...(surface.incoming_reassignments || []),
  ...(surface.outgoing_reassignments || []),
  ...reassignments.filter((item) => item.from_surface_key === surface.surface_key || item.to_surface_key === surface.surface_key),
];

const mergeDecisionsForSurface = (
  surface: RetrievalSurface,
  mergeDecisions: SurfaceMergeDecision[],
): SurfaceMergeDecision[] => (
  surface.merge_decisions || mergeDecisions.filter((item) => (
    item.survivor_surface_key === surface.surface_key
    || item.merged_surface_keys.includes(surface.surface_key)
    || item.keep_separate_surface_keys.includes(surface.surface_key)
  ))
);

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
  const hasStage = (needle: string): boolean => stages.some((stage) => stage.stage_kind.includes(needle) && stage.status === 'completed');

  const sourceStatus: StepStatus = sourceUnitCount > 0 ? 'completed' : baseStatus === 'active' ? 'active' : baseStatus;
  const discoveryDone = surfaceCount > 0 || hasStage('discovery');
  const relationDone = relationCount > 0 || hasStage('relation');
  const answerDone = surfaces.some((surface) => surface.answer || surface.short_answer) || hasStage('answer');
  const ownershipDone = ownershipCount > 0 || reassignmentCount > 0 || hasStage('ownership');
  const reconciliationDone = relationCount > 0 || mergeCount > 0 || hasStage('reconciliation');

  return [
    {
      id: 'source_units',
      title: '1. Исходные блоки',
      status: sourceStatus,
      description: 'Файл разобран на source units — смысловые блоки, из которых рождаются answer slots.',
      detail: sourceUnitCount > 0 ? `${formatMetric(sourceUnitCount)} исходных блоков` : 'Ждём извлечение исходных блоков',
    },
    {
      id: 'local_discovery',
      title: '2. Answer slot discovery',
      status: discoveryDone ? 'completed' : sourceStatus === 'completed' && baseStatus === 'active' ? 'active' : baseStatus === 'failed' ? 'failed' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'LLM находит будущие answer slots: broad overview, child, narrow и standalone.',
      detail: surfaceCount > 0 ? `${formatMetric(surfaceCount)} карточек сохранено` : 'Карточки ещё не сохранены',
    },
    {
      id: 'local_relations',
      title: '3. Связи и кандидаты на merge',
      status: relationDone ? 'completed' : discoveryDone && baseStatus === 'active' ? 'active' : baseStatus === 'failed' ? 'failed' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'Система связывает parent/child/sibling и ищет дубликаты одного intent.',
      detail: relationCount > 0 ? `${formatMetric(relationCount)} связей найдено` : 'Связей пока нет',
    },
    {
      id: 'answers',
      title: '4. Ответы и ownership вопросов',
      status: answerDone && ownershipDone ? 'completed' : discoveryDone && baseStatus === 'active' ? 'active' : baseStatus === 'failed' ? 'failed' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'Для каждого answer slot формируются answer/short answer и список вопросов, которыми он владеет.',
      detail: `${formatMetric(ownershipCount)} owned questions · ${formatMetric(reassignmentCount)} переносов`,
    },
    {
      id: 'global_reconciliation',
      title: '5. Глобальная сборка',
      status: reconciliationDone ? 'completed' : ownershipDone && baseStatus === 'active' ? 'active' : baseStatus === 'failed' ? 'failed' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'После всех блоков judge проверяет relation clusters, merge decisions и переносы вопросов.',
      detail: `${formatMetric(mergeCount)} merge decisions`,
    },
    {
      id: 'curation',
      title: '6. Курация / публикация',
      status: surfaces.length > 0 ? 'active' : baseStatus === 'failed' ? 'failed' : baseStatus === 'stopped' ? 'stopped' : 'pending',
      description: 'Куратор видит карточки, связи, источники, переносы вопросов и публикацию в runtime retrieval.',
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
  if (run.status === 'failed') return run.error_message || 'Pipeline завершился ошибкой. Открой технические стадии ниже.';
  if (run.status === 'running' && !isDocumentProcessing) return 'Документ уже не обрабатывается, но последний compiler run остался в running. Обычно это значит, что обработку остановили вручную.';
  const active = steps.find((step) => step.status === 'active');
  if (active) return active.description;
  const completedCount = steps.filter((step) => step.status === 'completed').length;
  if (completedCount === steps.length) return 'FAQ Graph pipeline завершён. Можно проверять связи и публиковать карточки.';
  return 'Pipeline ожидает следующую стадию.';
};

const buildRelationNodes = (
  surfaces: RetrievalSurface[],
  relations: SurfaceRelation[],
): RelationNode[] => {
  const nodes = new Map<string, RelationNode>();
  for (const surface of surfaces) {
    nodes.set(surface.surface_key, {
      surface,
      children: [],
      parents: [],
      siblings: [],
      duplicates: [],
    });
  }

  for (const relation of relations) {
    const parent = nodes.get(relation.parent_surface_key);
    const child = nodes.get(relation.child_surface_key);
    if (relation.relation_type === 'umbrella_contains') {
      parent?.children.push(relation);
      child?.parents.push(relation);
    } else if (relation.relation_type === 'sibling') {
      parent?.siblings.push(relation);
      child?.siblings.push(relation);
    } else if (relation.relation_type === 'duplicates' || relation.relation_type === 'near_duplicate') {
      parent?.duplicates.push(relation);
      child?.duplicates.push(relation);
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

const RelationMap: React.FC<{
  surfaces: RetrievalSurface[];
  relations: SurfaceRelation[];
  mergeDecisions: SurfaceMergeDecision[];
  reassignments: SurfaceReassignment[];
}> = ({ surfaces, relations, mergeDecisions, reassignments }) => {
  const surfaceByKey = React.useMemo(
    () => new Map(surfaces.map((surface) => [surface.surface_key, surface])),
    [surfaces],
  );
  const nodes = React.useMemo(() => buildRelationNodes(surfaces, relations), [surfaces, relations]);
  const roots = nodes.filter((node) => node.children.length > 0 || node.duplicates.length > 0).slice(0, 24);

  if (surfaces.length === 0) return null;

  return (
    <details className="mb-3 rounded-lg bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-secondary)]" open>
      <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
        Карта связей answer slots: parent → children / merge / переносы вопросов
      </summary>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        {roots.length === 0 ? (
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3 text-[var(--text-muted)]">
            Связей parent/child или duplicate пока нет. Смотри стадии relation_planning и global_relation_judge.
          </div>
        ) : roots.map((node) => (
          <div key={node.surface.surface_key} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-semibold text-[var(--text-primary)]">{node.surface.title}</span>
              <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
                {SURFACE_KIND_LABELS[node.surface.surface_kind] || node.surface.surface_kind}
              </span>
              <span className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-0.5 text-[10px] text-[var(--accent-primary)]">
                {node.children.length} children · {node.duplicates.length} dupes
              </span>
            </div>

            {node.children.length > 0 && (
              <div className="mt-2">
                <div className="mb-1 font-medium text-[var(--text-primary)]">Дочерние карточки</div>
                <div className="space-y-1">
                  {node.children.map((relation) => (
                    <div key={relation.id || `${relation.parent_surface_key}-${relation.child_surface_key}`} className="rounded bg-[var(--control-bg)] px-2 py-1">
                      <span className="font-medium text-[var(--text-primary)]">→ {surfaceTitle(relation.child_surface_key, surfaceByKey)}</span>
                      <span className="ml-1 text-[var(--text-muted)]">{RELATION_LABELS[relation.relation_type] || relation.relation_type}</span>
                      {relation.reason && <div className="mt-0.5 text-[var(--text-muted)]">{relation.reason}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {node.duplicates.length > 0 && (
              <div className="mt-2">
                <div className="mb-1 font-medium text-[var(--text-primary)]">Кандидаты на merge / same intent</div>
                <div className="space-y-1">
                  {node.duplicates.map((relation) => {
                    const otherKey = relation.parent_surface_key === node.surface.surface_key
                      ? relation.child_surface_key
                      : relation.parent_surface_key;
                    return (
                      <div key={relation.id || `${relation.parent_surface_key}-${relation.child_surface_key}`} className="rounded bg-[var(--control-bg)] px-2 py-1">
                        <span className="font-medium text-[var(--text-primary)]">↔ {surfaceTitle(otherKey, surfaceByKey)}</span>
                        {relation.reason && <div className="mt-0.5 text-[var(--text-muted)]">{relation.reason}</div>}
                      </div>
                    );
                  })}
                </div>
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
  const filteredSurfaces = surfaces.filter((surface) => matchesFilter(surface, filter));
  const isLoading = compilationQuery.isLoading || surfacesQuery.isLoading;
  const pipelineSteps = compilePipelineSteps(run, stages, sourceUnits, surfaces, relations, ownership, reassignments, mergeDecisions, isDocumentProcessing);
  const completedSteps = pipelineSteps.filter((step) => step.status === 'completed').length;
  const progressPercent = Math.round((completedSteps / pipelineSteps.length) * 100);
  const summaryText = pipelineSummaryText(run, pipelineSteps, isDocumentProcessing);
  const liveProgress = liveProgressFromStages(stages, run);
  const visibleProgressPercent = liveProgress?.percent ?? progressPercent;
  const surfaceByKey = new Map(surfaces.map((surface) => [surface.surface_key, surface]));

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3 text-sm">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h5 className="font-semibold text-[var(--text-primary)]">FAQ Answer Slot Pipeline</h5>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-[var(--text-muted)]">{summaryText}</p>
          {run && (
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              run: {statusLabel(run.status)} · {run.compiler_kind || 'compiler'} · {run.prompt_version}
            </p>
          )}
        </div>

        <div className="min-w-[160px] text-right text-xs text-[var(--text-secondary)]">
          <div>{liveProgress?.percent ? `${liveProgress.percent}%` : `${completedSteps}/${pipelineSteps.length} стадий`}</div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--control-bg)]">
            <div className="h-full rounded-full bg-[var(--accent-primary)] transition-all" style={{ width: `${visibleProgressPercent}%` }} />
          </div>
        </div>
      </div>

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

      <details className="mb-3 rounded-lg bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-secondary)]">
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
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              className={`rounded-full px-2 py-0.5 transition-colors ${filter === value ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]' : 'bg-[var(--control-bg)] text-[var(--text-secondary)]'}`}
            >
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

      {surfaces.length === 0 ? (
        <div className="rounded-lg bg-[var(--surface-elevated)] p-3 text-xs leading-relaxed text-[var(--text-muted)]">
          {isLoading ? 'Загружаю состояние graph pipeline…' : run?.status === 'failed' ? 'Карточки не появились, потому что graph compiler завершился ошибкой. Исправь ошибку модели/лимита и загрузи документ заново.' : run?.status === 'running' && !isDocumentProcessing ? 'Карточек нет, потому что документ уже не обрабатывается, а последний compiler run остался в running. Вероятнее всего, обработку остановили до сохранения карточек.' : run ? 'Карточки ещё не сохранены. Смотри стадии выше: если active стоит на discovery/answer synthesis, LLM ещё собирает graph context.' : 'FAQ graph run ещё не создан.'}
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

                  <button
                    type="button"
                    disabled={isPublished || publishMutation.isPending}
                    onClick={() => publishMutation.mutate(surface.id)}
                    className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
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
                          {surfaceTitle(item.parent_surface_key, surfaceByKey)} {RELATION_LABELS[item.relation_type] || item.relation_type} {surfaceTitle(item.child_surface_key, surfaceByKey)}
                          {item.reason ? ` — ${item.reason}` : ''}
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
