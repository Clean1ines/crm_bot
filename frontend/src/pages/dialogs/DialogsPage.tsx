import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppStore } from '../../app/store';
import { useMediaQuery } from '../../shared/lib/hooks/useMediaQuery';
import { DialogList } from './components/DialogList';
import { ChatWindow } from './components/ChatWindow';
import { Inspector } from './components/Inspector';

type MobileDialogsView = 'list' | 'chat' | 'inspector';

export const DialogsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const isMobile = useMediaQuery('(max-width: 768px)');
  const {
    selectedThreadId,
    setSelectedThreadId,
    setSelectedThreadClient,
    clearMessages,
  } = useAppStore();
  const [mobileView, setMobileView] = useState<MobileDialogsView>('list');

  useEffect(() => {
    if (!projectId) {
      navigate('/projects');
    }
  }, [projectId, navigate]);

  // Reset thread selection when project changes
  useEffect(() => {
    if (projectId) {
      setSelectedThreadId(null);
      setSelectedThreadClient(null);
      clearMessages();
    }
  }, [projectId, setSelectedThreadId, setSelectedThreadClient, clearMessages]);

  if (!projectId) return null;

  if (isMobile) {
    return (
      <div key={`mobile-dialogs-${projectId}`} className="h-full min-h-0 bg-[var(--bg-primary)]">
        {mobileView === 'list' && (
          <DialogList
            key={`dialoglist-mobile-${projectId}`}
            projectId={projectId}
            mobile
            onThreadSelect={() => setMobileView('chat')}
          />
        )}

        {mobileView === 'chat' && (
          <ChatWindow
            key={`chatwindow-mobile-${projectId}-${selectedThreadId || 'empty'}`}
            threadId={selectedThreadId}
            projectId={projectId}
            mobile
            onBack={() => setMobileView('list')}
            onOpenInspector={() => setMobileView('inspector')}
          />
        )}

        {mobileView === 'inspector' && (
          <Inspector
            key={`inspector-mobile-${projectId}-${selectedThreadId || 'empty'}`}
            threadId={selectedThreadId}
            projectId={projectId}
            mobile
            onBack={() => setMobileView('chat')}
          />
        )}
      </div>
    );
  }

  // Force remount of each child component when projectId changes by using key
  return (
    <div className="flex h-full min-h-0 bg-[var(--bg-primary)]">
      <div className="min-w-[240px] max-w-[320px] flex-1">
        <DialogList key={`dialoglist-${projectId}`} projectId={projectId} />
      </div>

      <div className="min-w-[400px] flex-[2]">
        <ChatWindow key={`chatwindow-${projectId}`} threadId={selectedThreadId} projectId={projectId} />
      </div>

      <div className="min-w-[240px] max-w-[320px] flex-1">
        <Inspector key={`inspector-${projectId}`} threadId={selectedThreadId} projectId={projectId} />
      </div>
    </div>
  );
};
