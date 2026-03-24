// frontend/src/app/Layout.tsx
import React from 'react';
import { Outlet } from 'react-router-dom';
import { AppSidebar } from '@widgets/sidebar/AppSidebar';

export const Layout: React.FC = () => {
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