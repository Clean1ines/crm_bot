import type { FrontendWorkflowEventEnvelope } from '@shared/api/modules/knowledge';

const CURATION_READY_LIVE_PROJECTION_TYPE =
  'workflow_draft_claim_compaction_all_groups_compacted';

export const isCurationReadyLiveEvent = (
  event: FrontendWorkflowEventEnvelope,
): boolean => event.projection_type === CURATION_READY_LIVE_PROJECTION_TYPE;
