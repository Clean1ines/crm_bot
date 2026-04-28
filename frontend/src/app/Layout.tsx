import React, { useEffect } from 'react';
import { Outlet, useParams } from 'react-router-dom';
import { AppSidebar } from '@widgets/sidebar/AppSidebar';
import { useProjectStore } from '@entities/project';

export const Layout: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const { setSelectedProjectId, clearSelectedProject } = useProjectStore();

  useEffect(() => {
    if (projectId) {
      setSelectedProjectId(projectId);
      return;
    }

    clearSelectedProject();
  }, [projectId, setSelectedProjectId, clearSelectedProject]);

  return (
    <div className="flex h-[100dvh] min-h-0 bg-[var(--bg-primary)]">
      <AppSidebar />
      <main className="min-w-0 flex-1 overflow-hidden pb-[68px] md:pb-0">
        <div className="h-full min-h-0 overflow-y-auto custom-scrollbar">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
