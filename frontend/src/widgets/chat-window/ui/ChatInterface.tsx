import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '@/app/store';
import { useProjectStore, useProjects } from '@entities/project';
import { useMediaQuery } from '@/shared/lib/hooks/useMediaQuery';
import { IOSShell } from '@/widgets/workflow-shell/ui/IOSShell';
import { ChatCanvas } from '@/widgets/chat-panel/ui/ChatCanvas';

interface ChatInterfaceProps {
  executionId?: string; // ADDED
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({ executionId }) => {
  const navigate = useNavigate();
  const { models, selectedModel, setSelectedModel } = useAppStore();
  const currentProjectId = useProjectStore(s => s.currentProjectId);
  const { projects } = useProjects();
  useMediaQuery('(max-width: 768px)');

  const currentProject = projects.find(p => p.id === currentProjectId);

  return (
    <IOSShell>
      <div className="flex h-full w-full min-w-0 overflow-hidden">
        <main className="flex-1 flex flex-col w-full min-w-0 overflow-x-hidden">
          <header
            className="h-14 flex items-center justify-between px-6 border-b border-[var(--ios-border)] bg-[var(--ios-glass-dark)]"
            data-testid="main-header"
          >
            <div className="flex items-center gap-4 flex-1 min-w-0">
              <h1 className="text-lg font-bold text-[var(--bronze-base)] truncate">
                {currentProject?.name || 'Select a project'}
              </h1>
              {models.length > 0 && (
                <select
                  value={selectedModel || ''}
                  onChange={(e) => setSelectedModel(e.target.value || null)}
                  className="bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-2 py-1 text-xs text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)]"
                >
                  <option value="" disabled>Select model</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.id}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <button
              onClick={() => navigate('/workspace')}
              className="px-4 py-1.5 text-xs font-semibold rounded bg-[var(--bronze-dim)] text-[var(--bronze-bright)] hover:bg-[var(--bronze-base)] hover:text-black transition-colors whitespace-nowrap ml-2"
            >
              Manage Workflows
            </button>
          </header>

          <ChatCanvas executionId={executionId} /> {/* MODIFIED: pass executionId */}
        </main>
      </div>
    </IOSShell>
  );
};