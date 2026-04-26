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
