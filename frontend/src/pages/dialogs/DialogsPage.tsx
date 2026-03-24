import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppStore } from '../../app/store';
import { DialogList } from './components/DialogList';
import { ChatWindow } from './components/ChatWindow';
import { Inspector } from './components/Inspector';

export const DialogsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { selectedThreadId, setSelectedThreadId, clearMessages } = useAppStore();

  useEffect(() => {
    if (!projectId) {
      navigate('/projects');
    }
  }, [projectId, navigate]);

  // Reset thread selection when project changes
  useEffect(() => {
    if (projectId) {
      setSelectedThreadId(null);
      clearMessages();
    }
  }, [projectId, setSelectedThreadId, clearMessages]);

  if (!projectId) return null;

  // Force remount of each child component when projectId changes by using key
  return (
    <div className="flex h-full bg-[var(--bg-primary)]">
      <div className="flex-1 max-w-[320px] min-w-[240px]">
        <DialogList key={`dialoglist-${projectId}`} projectId={projectId} />
      </div>

      <div className="flex-[2] min-w-[400px]">
        <ChatWindow key={`chatwindow-${projectId}`} threadId={selectedThreadId} projectId={projectId} />
      </div>

     <div className="flex-1 max-w-[320px] min-w-[240px]">
        <Inspector key={`inspector-${projectId}`} threadId={selectedThreadId} projectId={projectId} />
      </div>
    </div>
  );
};
