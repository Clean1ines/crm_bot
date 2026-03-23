import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppStore } from '../../app/store';
import { DialogList } from './components/DialogList';
import { ChatWindow } from './components/ChatWindow';
import { Inspector } from './components/Inspector';

export const DialogsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { selectedThreadId, setSelectedThreadId } = useAppStore();

  useEffect(() => {
    if (!projectId) {
      navigate('/projects');
    }
  }, [projectId, navigate]);

  if (!projectId) return null;

  return (
    <div className="flex h-full">
      {/* Left column: Dialog list */}
      <div className="w-80 flex-shrink-0">
        <DialogList projectId={projectId} />
      </div>

      {/* Center column: Chat */}
      <div className="flex-1 flex flex-col">
        <ChatWindow threadId={selectedThreadId} projectId={projectId} />
      </div>

      {/* Right column: Inspector */}
      <div className="w-80 flex-shrink-0">
        <Inspector threadId={selectedThreadId} projectId={projectId} />
      </div>
    </div>
  );
};
