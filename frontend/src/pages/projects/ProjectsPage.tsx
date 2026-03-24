// frontend/src/pages/projects/ProjectsPage.tsx (небольшие правки для цветов)
import React from 'react';
import { useProjects } from '@entities/project/api/useProjects';
import { Link } from 'react-router-dom';
import { getSessionToken } from '@shared/api/client';

export const ProjectsPage: React.FC = () => {
  const { projects, isLoading, error } = useProjects();
  const token = getSessionToken();

  if (isLoading) return <div className="p-6 text-[var(--text-muted)]">Загрузка...</div>;

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-100 border border-red-400 p-4 rounded text-red-700">
          <h2 className="font-bold mb-2">Ошибка загрузки проектов:</h2>
          <pre className="text-sm whitespace-pre-wrap">{String(error)}</pre>
        </div>
      </div>
    );
  }

  if (!projects || projects.length === 0) {
    return (
      <div className="p-6">
        <div className="bg-yellow-100 border border-yellow-400 p-4 rounded text-yellow-700">
          <h2 className="font-bold mb-2">Нет проектов</h2>
          <p>Создайте первый проект через Telegram бота.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-10">
        <h1 className="text-4xl font-extralight tracking-tight text-[var(--text-primary)]">
          Мастерская <span className="opacity-30">/</span> Проекты
        </h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {projects.map((project) => (
          <div 
            key={project.id} 
            className="group relative bg-white border border-[var(--border-subtle)] p-6 rounded-3xl shadow-sm hover:shadow-md hover:border-[var(--accent-primary)] transition-all duration-500"
          >
            <div className="flex justify-between items-start mb-4">
              <Link to={`/projects/${project.id}`} className="text-xl font-medium text-[var(--text-primary)] group-hover:text-[var(--accent-primary)] transition-colors">
                {project.name}
              </Link>
              {project.is_pro_mode && (
                <span className="text-[10px] uppercase tracking-widest bg-[var(--accent-primary)] text-white px-2 py-0.5 rounded-full font-bold">
                  Pro
                </span>
              )}
            </div>
            
            <div className="flex items-center gap-4 text-sm text-[var(--text-muted)]">
              <div>Менеджеров: {project.managers.length}</div>
              <div>•</div>
              <div className="truncate max-w-[100px]">
                {project.template_slug || 'Без шаблона'}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};