import React from 'react';
import { Outlet } from 'react-router-dom';
import { ProjectsSidebar } from '@widgets/sidebar/ui/ProjectsSidebar';

export const Layout: React.FC = () => {
  return (
    <div className="flex h-screen bg-[var(--ios-bg)]">
      <ProjectsSidebar />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
};
