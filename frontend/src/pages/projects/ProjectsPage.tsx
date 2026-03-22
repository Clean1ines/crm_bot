import React from 'react';
import { useProjects } from '@entities/project/api/useProjects';
import { Link } from 'react-router-dom';

export const ProjectsPage: React.FC = () => {
  const { projects, isLoading, error } = useProjects();

  if (isLoading) return <div className="p-6 text-white/50">Загрузка...</div>;
  if (error) return <div className="p-6 text-red-400">Ошибка загрузки</div>;

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-10">
        <h1 className="text-4xl font-extralight tracking-tight text-white">
          Мастерская <span className="opacity-30">/</span> Проекты
        </h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {projects.map((project) => (
          <div 
            key={project.id} 
            className="group relative bg-white/[0.03] border border-white/10 p-6 rounded-3xl backdrop-blur-xl hover:bg-white/[0.05] hover:border-orange-500/50 transition-all duration-500"
          >
            <div className="flex justify-between items-start mb-4">
              <Link to={`/projects/${project.id}`} className="text-xl font-medium text-white group-hover:text-orange-400 transition-colors">
                {project.name}
              </Link>
              {project.is_pro_mode && (
                <span className="text-[10px] uppercase tracking-widest bg-orange-500 text-black px-2 py-0.5 rounded-full font-bold">
                  Pro
                </span>
              )}
            </div>
            
            <div className="flex items-center gap-4 text-sm text-white/40">
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