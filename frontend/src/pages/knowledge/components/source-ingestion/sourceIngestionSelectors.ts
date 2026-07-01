import type {
  SourceIngestionProgressView,
  SourceIngestionStageInput,
  SourceIngestionWorkflowStateInput,
} from './sourceIngestionTypes';

const normalizeNumber = (value: number | null | undefined): number =>
  Math.max(0, Math.floor(Number.isFinite(value) ? value ?? 0 : 0));

const workflowStageHasStarted = (stage: SourceIngestionStageInput): boolean => {
  if (!stage) return false;

  return (
    stage.status !== 'pending' ||
    stage.current > 0 ||
    stage.total > 0 ||
    Boolean(stage.started_at) ||
    Boolean(stage.completed_at)
  );
};

const formatNumber = (value: number): string =>
  new Intl.NumberFormat('ru-RU').format(Math.max(0, Math.floor(value || 0)));

export const selectSourceIngestionProgress = (
  workflowLiveState: SourceIngestionWorkflowStateInput,
): SourceIngestionProgressView => {
  const workflow = workflowLiveState?.workflow ?? null;
  const stages = workflow?.stages ?? [];
  const lanes = workflow?.section_lanes ?? [];

  const sourceStage = stages.find((stage) => stage?.id === 'source_ingestion') ?? null;
  const claimStage =
    stages.find((stage) => stage?.id === 'prompt_a_claim_extraction') ?? null;

  const laneReady = lanes.reduce(
    (total, lane) => total + normalizeNumber(lane.ready_count),
    0,
  );
  const laneLeased = lanes.reduce(
    (total, lane) => total + normalizeNumber(lane.leased_count),
    0,
  );
  const laneDone = lanes.reduce(
    (total, lane) => total + normalizeNumber(lane.done_count),
    0,
  );
  const laneFailed = lanes.reduce(
    (total, lane) => total + normalizeNumber(lane.failed_count),
    0,
  );
  const laneWaiting = lanes.reduce(
    (total, lane) => total + normalizeNumber(lane.waiting_count),
    0,
  );
  const sectionCount = lanes.reduce((total, lane) => total + lane.items.length, 0);
  const observedLaneTotal = laneReady + laneLeased + laneDone + laneFailed + laneWaiting;

  const total = Math.max(
    normalizeNumber(claimStage?.total),
    normalizeNumber(sourceStage?.total),
    observedLaneTotal,
  );
  const current = Math.max(normalizeNumber(claimStage?.current), laneDone);
  const percent =
    total > 0 ? Math.max(0, Math.min(100, Math.round((current / total) * 100))) : 0;

  const visible =
    total > 0 ||
    workflowStageHasStarted(sourceStage) ||
    workflowStageHasStarted(claimStage) ||
    sectionCount > 0;

  const text =
    total > 0
      ? `${formatNumber(current)} из ${formatNumber(total)} разделов`
      : 'разделы ещё не подготовлены';

  return {
    visible,
    current,
    total,
    percent,
    readyCount: laneReady,
    leasedCount: laneLeased,
    doneCount: laneDone,
    failedCount: laneFailed,
    waitingCount: laneWaiting,
    sectionCount,
    text,
  };
};
