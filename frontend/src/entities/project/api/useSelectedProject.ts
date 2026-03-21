import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { ProjectResponse } from '@shared/api';

export const useSelectedProject = (projects: ProjectResponse[]) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlProjectId = searchParams.get('projectId');
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const isUpdatingUrl = useRef(false);
  const isInitialized = useRef(false);

  // Инициализация после загрузки проектов
  useEffect(() => {
    if (projects.length === 0 || isInitialized.current) return;

    let initialId: string | null = null;
    if (urlProjectId && projects.some(p => p.id === urlProjectId)) {
      initialId = urlProjectId;
    } else {
      const stored = localStorage.getItem('workspace_selected_project');
      if (stored && projects.some(p => p.id === stored)) {
        initialId = stored;
      } else {
        initialId = projects[0]?.id || null;
      }
    }

    if (initialId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedProjectId(initialId);
      if (searchParams.get('projectId') !== initialId) {
        isUpdatingUrl.current = true;
        setSearchParams({ projectId: initialId }, { replace: true });
        setTimeout(() => { isUpdatingUrl.current = false; }, 100);
      }
    }
    isInitialized.current = true;
  }, [projects, urlProjectId, searchParams, setSearchParams]);

  // Синхронизация URL при изменении selectedProjectId (кроме инициализации)
  useEffect(() => {
    if (!selectedProjectId) return;
    localStorage.setItem('workspace_selected_project', selectedProjectId);
    if (searchParams.get('projectId') !== selectedProjectId && !isUpdatingUrl.current) {
      setSearchParams({ projectId: selectedProjectId }, { replace: true });
    }
  }, [selectedProjectId, searchParams, setSearchParams]);

  // Синхронизация selectedProjectId при изменении URL (кроме наших обновлений)
  useEffect(() => {
    if (!urlProjectId || urlProjectId === selectedProjectId || isUpdatingUrl.current) return;
    if (projects.some(p => p.id === urlProjectId)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedProjectId(urlProjectId);
    }
  }, [urlProjectId, selectedProjectId, projects]);

  return { selectedProjectId };
};
