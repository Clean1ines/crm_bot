import React from 'react';

import { visibleWorkflowActions, workflowActionLabel } from '../../workflow/workflowActions';
import { normalize } from '../workflow-card/workflowCardLabels';
import type { WorkbenchWorkflowActionLiveState } from '@shared/api/modules/knowledge';

type WorkflowActionsPanelProps = {
  actions: WorkbenchWorkflowActionLiveState[];
  onAction: (action: WorkbenchWorkflowActionLiveState) => void;
};

const disabledActionTitle = (action: WorkbenchWorkflowActionLiveState): string => {
  if (action.enabled) return workflowActionLabel(action);

  const labels: Record<string, string> = {
    not_paused: 'Доступно только когда обработка на паузе',
    not_running: 'Сейчас действие недоступно',
    terminal_workflow: 'Обработка уже завершена или остановлена',
    preview_not_ready: 'Проверка будет доступна после подготовки предпросмотра',
    workflow_missing: 'Рабочий процесс ещё не создан',
  };
  return labels[action.reason_code || ''] || 'Сейчас недоступно';
};

const canRunLiveAction = (action: WorkbenchWorkflowActionLiveState): boolean =>
  action.enabled;

const liveActionClassName = (action: WorkbenchWorkflowActionLiveState): string => {
  const base =
    'rounded-full px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50';

  if (action.action_id === 'cancel_processing' || action.action_id === 'delete_document') {
    return `${base} bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)] hover:opacity-80`;
  }

  if (action.action_id === 'open_curation' || action.action_id === 'publish_ready') {
    return `${base} bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20`;
  }

  if (action.action_id === 'confirm_degraded_fallback') {
    return `${base} bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 dark:text-amber-300`;
  }

  return `${base} bg-[var(--control-bg)] text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)]`;
};

export const WorkflowActionsPanel: React.FC<WorkflowActionsPanelProps> = ({
  actions,
  onAction,
}) => {
  const visibleActions = visibleWorkflowActions(actions).filter(
    (action) =>
	      normalize(action.action_id) !== 'pause_processing' &&
	      normalize(action.action_id) !== 'resume_processing' &&
	      normalize(action.action_id) !== 'open_curation',
	  );

  if (visibleActions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 pt-1">
      {visibleActions.map((action) => (
        <button
          key={action.action_id}
          type="button"
          disabled={!canRunLiveAction(action)}
          title={disabledActionTitle(action)}
          onClick={() => onAction(action)}
          className={liveActionClassName(action)}
        >
          {workflowActionLabel(action)}
        </button>
      ))}
    </div>
  );
};
