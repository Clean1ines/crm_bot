import React, { useEffect } from 'react';
import { Outlet, useParams } from 'react-router-dom';
import { AppSidebar } from '@widgets/sidebar/AppSidebar';
import { useAppStore } from './store'; // правильный путь к существующему стору

export const Layout: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const { setSelectedProjectId } = useAppStore();

  useEffect(() => {
    if (projectId) {
      setSelectedProjectId(projectId);
    }
  }, [projectId, setSelectedProjectId]);

  return (
    <div className="flex h-screen bg-[var(--bg-primary)]">
      <AppSidebar />
      <main className="flex-1 overflow-hidden">
        <div className="h-full overflow-y-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
