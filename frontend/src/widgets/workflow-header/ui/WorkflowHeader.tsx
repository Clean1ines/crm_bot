// frontend/src/components/ios/WorkflowHeader.tsx
// ADDED: Header component with workflow name input and actions (SRP extraction)

import React from 'react';

interface WorkflowHeaderProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  workflowName: string;
  onWorkflowNameChange: (name: string) => void;
  currentWorkflowId: string | null;
  loading: boolean;
  onToggleNodeList: () => void;
  onDelete: () => void;
  onSave: () => void;
  onLogout: () => void;
  canSave: boolean;
}

export const WorkflowHeader: React.FC<WorkflowHeaderProps> = ({
  sidebarOpen,
  onToggleSidebar,
  workflowName,
  onWorkflowNameChange,
  currentWorkflowId,
  loading,
  onToggleNodeList,
  onDelete,
  onSave,
  onLogout,
  canSave,
}) => {
  return (
    <header className="h-14 flex items-center justify-between px-6 border-b border-[var(--ios-border)] bg-[var(--ios-glass-dark)] backdrop-blur-md z-100">
      <div className="flex items-center gap-4">
        {!sidebarOpen && (
          <button onClick={onToggleSidebar} className="text-[var(--text-muted)] hover:text-[var(--text-main)]">
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
        )}
        <input
          type="text"
          value={workflowName}
          onChange={(e) => onWorkflowNameChange(e.target.value)}
          placeholder="Workflow Name"
          className="bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-3 py-1.5 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)] w-64"
        />
        {currentWorkflowId && (
          <span className="text-[10px] text-[var(--text-muted)] bg-[var(--ios-glass-dark)] px-2 py-0.5 rounded border border-[var(--ios-border)]">Editing</span>
        )}
        {loading && (
          <span className="text-[10px] text-[var(--accent-info)] animate-pulse">Saving...</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onToggleNodeList}
          className="px-3 py-1.5 text-xs font-semibold rounded border border-[var(--ios-border)] text-[var(--text-main)] hover:bg-[var(--ios-glass-bright)] transition-colors"
        >
          📋 Nodes
        </button>
        <button
          onClick={onDelete}
          disabled={!currentWorkflowId}
          className="px-3 py-1.5 text-xs font-semibold rounded border border-[var(--accent-danger)] text-[var(--accent-danger)] hover:bg-[var(--accent-danger)] hover:text-black transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Delete
        </button>
        <button
          onClick={onSave}
          disabled={!canSave}
          className="px-4 py-1.5 text-xs font-semibold rounded bg-[var(--bronze-base)] text-black hover:bg-[var(--bronze-bright)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          {loading ? 'Saving...' : (currentWorkflowId ? 'Update' : 'Save')} Workflow
        </button>
        <button
          onClick={onLogout}
          className="px-3 py-1.5 text-xs font-semibold rounded border border-[var(--ios-border)] text-[var(--text-muted)] hover:bg-[var(--ios-glass-bright)] transition-colors"
        >
          🚪 Logout
        </button>
      </div>
    </header>
  );
};
