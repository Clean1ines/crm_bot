import type {
  RetrievalSurface,
  SurfaceCompilationRun,
  SurfaceCompilationStage,
  SurfaceMergeDecision,
  SurfaceOwnership,
  SurfaceReassignment,
  SurfaceRelation,
  SurfaceSourceUnit,
} from '@shared/api/modules/knowledgeSurface';

export type SurfacePipelineContractStatus =
  | 'not_started'
  | 'processing'
  | 'ready_for_curation'
  | 'completed_with_warnings'
  | 'failed'
  | 'stopped';

export type SurfacePipelineContract = {
  status: SurfacePipelineContractStatus;
  readyForCuration: boolean;
  canPublishRuntime: boolean;
  statusReason: string;
  blockingReasons: string[];
  warnings: string[];
  counters: {
    sourceUnits: number;
    surfaces: number;
    relations: number;
    parentChildRelations: number;
    duplicateRelations: number;
    ownership: number;
    reassignments: number;
    mergeDecisions: number;
    runtimeLinkedSurfaces: number;
  };
};

type BuildSurfacePipelineContractArgs = {
  run: SurfaceCompilationRun | null;
  stages: SurfaceCompilationStage[];
  sourceUnits: SurfaceSourceUnit[];
  surfaces: RetrievalSurface[];
  relations: SurfaceRelation[];
  ownership: SurfaceOwnership[];
  reassignments: SurfaceReassignment[];
  mergeDecisions: SurfaceMergeDecision[];
  isDocumentProcessing: boolean;
};

const isTerminalRun = (run: SurfaceCompilationRun | null): boolean => (
  run?.status === 'completed' || run?.status === 'failed' || run?.status === 'cancelled' || run?.status === 'canceled'
);

export const buildSurfacePipelineContract = ({
  run,
  stages,
  sourceUnits,
  surfaces,
  relations,
  ownership,
  reassignments,
  mergeDecisions,
  isDocumentProcessing,
}: BuildSurfacePipelineContractArgs): SurfacePipelineContract => {
  const parentChildRelations = relations.filter((item) => item.relation_type === 'umbrella_contains' || item.relation_type === 'specializes').length;
  const duplicateRelations = relations.filter((item) => item.relation_type === 'duplicates' || item.relation_type === 'near_duplicate').length;
  const runtimeLinkedSurfaces = surfaces.filter((item) => Boolean(item.linked_runtime_entry_id)).length;
  const counters = {
    sourceUnits: sourceUnits.length,
    surfaces: surfaces.length,
    relations: relations.length,
    parentChildRelations,
    duplicateRelations,
    ownership: ownership.length,
    reassignments: reassignments.length,
    mergeDecisions: mergeDecisions.length,
    runtimeLinkedSurfaces,
  };

  if (!run) {
    return {
      status: 'not_started',
      readyForCuration: false,
      canPublishRuntime: false,
      statusReason: 'FAQ Answer Slot Pipeline ещё не стартовал.',
      blockingReasons: ['Нет compiler run для этого документа.'],
      warnings: [],
      counters,
    };
  }

  if (run.status === 'failed') {
    return {
      status: 'failed',
      readyForCuration: surfaces.length > 0,
      canPublishRuntime: surfaces.length > 0,
      statusReason: run.error_message || 'Compiler run завершился ошибкой.',
      blockingReasons: surfaces.length > 0 ? [] : ['Compiler failed до материализации карточек.'],
      warnings: stages.filter((stage) => stage.status === 'failed').map((stage) => `${stage.stage_kind}: ${stage.error_message || 'failed'}`),
      counters,
    };
  }

  if ((run.status === 'running' && !isDocumentProcessing) || run.status === 'cancelled' || run.status === 'canceled') {
    return {
      status: 'stopped',
      readyForCuration: surfaces.length > 0,
      canPublishRuntime: surfaces.length > 0,
      statusReason: surfaces.length > 0
        ? 'Обработка остановлена, но промежуточные карточки уже доступны для курации.'
        : 'Обработка остановлена до появления карточек.',
      blockingReasons: surfaces.length > 0 ? [] : ['Нет материализованных surfaces.'],
      warnings: ['Последний compiler run не дошёл до нормального completed состояния.'],
      counters,
    };
  }

  const blockingReasons: string[] = [];
  const warnings: string[] = [];

  if (sourceUnits.length === 0) blockingReasons.push('Нет source units: документ ещё не разобран на исходные блоки.');
  if (surfaces.length === 0) blockingReasons.push('Нет surfaces: answer slots ещё не материализованы для курации.');
  if (surfaces.length > 1 && relations.length === 0 && isTerminalRun(run)) {
    blockingReasons.push('Нет relation map: карточки есть, но связи parent/child/duplicate не построены.');
  }
  if (surfaces.length > 0 && ownership.length === 0 && isTerminalRun(run)) {
    warnings.push('Нет ownership decisions: вопросы могут отображаться только из самих карточек.');
  }
  if (surfaces.length > 10 && duplicateRelations === 0 && mergeDecisions.length === 0 && isTerminalRun(run)) {
    warnings.push('Нет duplicate/merge evidence при большом числе карточек: проверь качество answer-slot clustering.');
  }
  if (surfaces.length > 0 && parentChildRelations === 0 && isTerminalRun(run)) {
    warnings.push('Нет parent/child relations: broad/narrow иерархия могла не построиться.');
  }

  const readyForCuration = surfaces.length > 0 && blockingReasons.length === 0;
  const canPublishRuntime = surfaces.length > 0;

  if (!readyForCuration && run.status === 'completed') {
    return {
      status: 'completed_with_warnings',
      readyForCuration: false,
      canPublishRuntime,
      statusReason: 'Compiler run completed, но контракт курации не выполнен.',
      blockingReasons,
      warnings,
      counters,
    };
  }

  if (readyForCuration && warnings.length > 0) {
    return {
      status: 'completed_with_warnings',
      readyForCuration,
      canPublishRuntime,
      statusReason: 'Карточки доступны, но есть предупреждения по связям/ownership.',
      blockingReasons,
      warnings,
      counters,
    };
  }

  if (readyForCuration) {
    return {
      status: 'ready_for_curation',
      readyForCuration,
      canPublishRuntime,
      statusReason: 'Карточки, связи и source units доступны для курации.',
      blockingReasons,
      warnings,
      counters,
    };
  }

  return {
    status: 'processing',
    readyForCuration: false,
    canPublishRuntime: false,
    statusReason: 'Pipeline ещё собирает answer slots и relation map.',
    blockingReasons,
    warnings,
    counters,
  };
};
