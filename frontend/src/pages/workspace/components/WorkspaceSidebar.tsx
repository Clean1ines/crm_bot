import React from 'react';
import { Sidebar } from '@shared/ui/Sidebar/Sidebar';

// Локальное определение типа вместо удалённого импорта
interface WorkflowSummary {
  id: string;
  name: string;
  description?: string;
}

interface WorkspaceSidebarProps {
  isMobile: boolean;
  sidebarOpen: boolean;
  onCloseSidebar: () => void;
  onOpenSidebar: () => void;
  selectedProjectId: string | null;
  currentProjectName: string;
  workflows: WorkflowSummary[];
  currentWorkflowId: string | null;
  onSelectWorkflow: (id: string) => void;
  onEditWorkflow: (wf: WorkflowSummary) => void;
  onDeleteWorkflow: (wf: WorkflowSummary) => void;
  onCreateWorkflow: () => void;
  onOpenNodeList: () => void;
  onLogout: () => void;
  // ADDED for workflow execution
  onStartWorkflow: (workflowId: string) => void;
}

export const WorkspaceSidebar: React.FC<WorkspaceSidebarProps> = ({
  isMobile,
  sidebarOpen,
  onCloseSidebar,
  selectedProjectId,
  currentProjectName,
  workflows,
  currentWorkflowId,
  onSelectWorkflow,
  onEditWorkflow,
  onDeleteWorkflow,
  onCreateWorkflow,
  onOpenNodeList,
  onLogout,
  onStartWorkflow, // ADDED
}) => {
  if (!sidebarOpen) return null;

  const headerContent = (
    <div className="p-3 border-b border-[var(--ios-border)]">
      <label className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider block mb-1">
        Current Project
      </label>
      <div className="w-full bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-2 py-1.5 text-xs text-[var(--text-main)]">
        {currentProjectName || '—'}
      </div>
    </div>
  );

  const footerContent = (
    <div className="p-3 border-t border-[var(--ios-border)] space-y-2">
      <button
        onClick={onCreateWorkflow}
        disabled={!selectedProjectId}
        className="w-full px-3 py-2 text-xs font-semibold rounded bg-[var(--bronze-dim)] text-[var(--bronze-bright)] hover:bg-[var(--bronze-base)] hover:text-black transition-colors flex items-center justify-center gap-2 disabled:opacity-30"
      >
        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        New Workflow
      </button>

      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={onOpenNodeList}
          disabled={!selectedProjectId}
          className="px-3 py-2 text-xs font-semibold rounded bg-[var(--bronze-dim)] text-[var(--bronze-bright)] hover:bg-[var(--bronze-base)] hover:text-black transition-colors disabled:opacity-30"
        >
          Nodes
        </button>
        <button
          onClick={onLogout}
          className="px-3 py-2 text-xs font-semibold rounded bg-[var(--bronze-dim)] text-[var(--bronze-bright)] hover:bg-[var(--bronze-base)] hover:text-black transition-colors"
        >
          Logout
        </button>
      </div>

      <div className="text-[9px] text-[var(--text-muted)] text-center pt-2">
        {workflows.length} workflow{workflows.length !== 1 ? 's' : ''}
      </div>
    </div>
  );

  return (
    <Sidebar
      isOpen={sidebarOpen}
      onClose={onCloseSidebar}
      header={headerContent}
      footer={footerContent}
      position="left"
      width={isMobile ? 'w-64' : 'w-64'}
      className={isMobile ? 'fixed' : ''}
    >
      {!selectedProjectId ? (
        <div className="text-[10px] text-[var(--accent-warning)] text-center py-4">
          ⚠️ Select project on home page
        </div>
      ) : workflows.length === 0 ? (
        <div className="text-[10px] text-[var(--text-muted)] text-center py-4">
          No workflows
        </div>
      ) : (
        workflows.map((wf) => (
          <div
            key={wf.id}
            className={`w-full text-left px-3 py-2 rounded mb-1 text-xs flex items-center justify-between cursor-pointer ${
              currentWorkflowId === wf.id
                ? 'bg-[var(--bronze-dim)] text-[var(--bronze-bright)]'
                : 'text-[var(--text-secondary)] hover:bg-[var(--ios-glass-bright)]'
            }`}
            onClick={() => onSelectWorkflow(wf.id)}
          >
            <div className="flex-1">
              <div className="font-semibold truncate">{wf.name}</div>
              <div className="text-[9px] opacity-60 truncate">
                {wf.description || 'No description'}
              </div>
            </div>
            <div className="flex gap-1 ml-2" onClick={(e) => e.stopPropagation()}>
              {/* ADDED Play button */}
              <button
                onClick={() => onStartWorkflow(wf.id)}
                className="text-[var(--text-muted)] hover:text-[var(--accent-success)] transition-colors p-1"
                title="Run workflow"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5,3 19,12 5,21" />
                </svg>
              </button>
              <button
                onClick={() => onEditWorkflow(wf)}
                className="text-[var(--text-muted)] hover:text-[var(--bronze-base)] transition-colors p-1"
                title="Edit workflow"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17 3L21 7L7 21H3V17L17 3Z" />
                </svg>
              </button>
              <button
                onClick={() => onDeleteWorkflow(wf)}
                className="text-[var(--text-muted)] hover:text-[var(--accent-danger)] transition-colors p-1"
                title="Delete workflow"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6H21M19 6V20C19 21.1046 18.1046 22 17 22H7C5.89543 22 5 21.1046 5 20V6M8 6V4C8 2.89543 8.89543 2 10 2H14C15.1046 2 16 2.89543 16 4V6" />
                </svg>
              </button>
            </div>
          </div>
        ))
      )}
    </Sidebar>
  );
};