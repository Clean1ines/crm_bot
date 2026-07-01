import type { WorkbenchWorkflowActionLiveState } from '@shared/api/modules/knowledge';

const normalize = (value: string | null | undefined): string =>
  (value || '').trim().toLowerCase();

export const visibleWorkflowActions = (
  actions: WorkbenchWorkflowActionLiveState[],
): WorkbenchWorkflowActionLiveState[] =>
  actions.filter((action) => {
    if (!action.visible) return false;

    const actionId = normalize(action.action_id);

    if (actionId === 'cancel_processing') return false;
    if (actionId === 'pause_processing') return action.enabled;
    if (actionId === 'resume_processing') return action.enabled;

    return true;
  });
