import React, { useEffect } from 'react';
import { Outlet, useParams } from 'react-router-dom';
import { AppSidebar } from '@widgets/sidebar/AppSidebar';
import { useAppStore } from './store';
import { useProjectStore } from '@entities/project';

export const Layout: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const { setSelectedProjectId } = useAppStore();
  const { setCurrentProjectId } = useProjectStore();

  // Синхронизация выбранного проекта с параметром URL
  useEffect(() => {
    if (projectId) {
      setSelectedProjectId(projectId);
      setCurrentProjectId(projectId);
    }
  }, [projectId, setSelectedProjectId, setCurrentProjectId]);

  // Убедимся, что нет других эффектов, которые могут менять выбранный проект или URL

  return (
    <div className="flex h-screen bg-[var(--bg-primary)]">
      <AppSidebar />
      <main className="flex-1 overflow-hidden">
        <div className="h-full overflow-y-auto custom-scrollbar">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
