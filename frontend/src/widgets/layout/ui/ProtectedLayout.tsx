import React from 'react';
import { Outlet } from 'react-router-dom';
import { ProjectsSidebar } from '@widgets/sidebar';
import { useProjectData } from '@/entities/project/api/useProjectData';

/**
 * Общий layout для защищённых страниц.
 * Содержит боковую панель проектов и область для вложенного контента.
 * Также инициализирует загрузку проектов, моделей и т.д. при монтировании.
 */
export const ProtectedLayout: React.FC = () => {
  // Вызываем хук для загрузки всех необходимых данных при входе на защищённые страницы
  useProjectData();

  return (
    <div className="flex h-screen">
      <ProjectsSidebar />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
};
