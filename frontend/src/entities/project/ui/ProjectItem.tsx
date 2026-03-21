import React from 'react';
import { Project } from '../model/types';

interface ProjectItemProps {
  project: Project;
  isActive: boolean;
  onClick: (id: string) => void;
  actions?: React.ReactNode;
}

export const ProjectItem: React.FC<ProjectItemProps> = ({ 
  project, 
  isActive, 
  onClick, 
  actions 
}) => {
  return (
    <div
      className={`p-2 rounded cursor-pointer flex items-center justify-between transition-colors ${
        isActive
          ? 'bg-[var(--bronze-dim)] text-[var(--bronze-bright)]'
          : 'text-[var(--text-secondary)] hover:bg-[var(--ios-glass-bright)]'
      }`}
      onClick={() => onClick(project.id)}
      data-testid="project-item"
    >
      <span className="truncate flex-1 text-sm">{project.name}</span>
      {actions && (
        <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
          {actions}
        </div>
      )}
    </div>
  );
};
