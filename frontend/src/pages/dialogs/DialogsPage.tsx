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
    <div className="flex h-full bg-[var(--bg-primary)]">
      {/* Левая колонка — список диалогов (max-width 320px) */}
      <div className="flex-1 max-w-[320px] min-w-[240px]">
        <DialogList projectId={projectId} />
      </div>

      {/* Центральная колонка — чат (всегда имеет приоритет) */}
      <div className="flex-[2] min-w-[400px]">
        <ChatWindow threadId={selectedThreadId} projectId={projectId} />
      </div>

      {/* Правая колонка — инспектор (max-width 320px) */}
      <div className="flex-1 max-w-[320px] min-w-[240px]">
        <Inspector threadId={selectedThreadId} projectId={projectId} />
      </div>
    </div>
  );
};
