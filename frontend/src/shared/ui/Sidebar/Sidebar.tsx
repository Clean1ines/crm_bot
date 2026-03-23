import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAppStore } from '../../../app/store';
import { api } from '../../api/client';
import type { ProjectResponse } from '../../api/client';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const location = useLocation();
  const { selectedProjectId, setSelectedProjectId } = useAppStore();
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [collapsed, setCollapsed] = useState(() => {
    const saved = localStorage.getItem('sidebarCollapsed');
    return saved === 'true';
  });

  useEffect(() => {
    const fetchProjects = async () => {
      const { data, error } = await api.projects.list();
      if (!error && data) {
        setProjects(data);
        if (data.length > 0 && !selectedProjectId) {
          setSelectedProjectId(data[0].id);
        }
      }
    };
    fetchProjects();
  }, [setSelectedProjectId, selectedProjectId]);

  const toggleCollapse = () => {
    const newCollapsed = !collapsed;
    setCollapsed(newCollapsed);
    localStorage.setItem('sidebarCollapsed', String(newCollapsed));
  };

  const navItems = [
    { path: `/projects/${selectedProjectId}/dialogs`, label: 'Диалоги', icon: '💬', group: 'CORE' },
    { path: `/projects/${selectedProjectId}/clients`, label: 'Клиенты', icon: '👥', group: 'CORE' },
    { path: `/projects/${selectedProjectId}/workflow`, label: 'Логика бота', icon: '⚙️', group: 'CONTROL' },
    { path: `/projects/${selectedProjectId}/knowledge`, label: 'Знания', icon: '📚', group: 'CONTROL' },
    { path: `/projects/${selectedProjectId}/analytics`, label: 'Аналитика', icon: '📊', group: 'INSIGHT' },
    { path: `/projects/${selectedProjectId}/channels`, label: 'Каналы', icon: '🔌', group: 'INFRA' },
    { path: `/projects/${selectedProjectId}/managers`, label: 'Менеджеры', icon: '👨‍💼', group: 'INFRA' },
    { path: `/projects/${selectedProjectId}/billing`, label: 'Тариф', icon: '💳', group: 'META' },
    { path: `/projects/${selectedProjectId}/settings`, label: 'Настройки', icon: '⚙️', group: 'META' },
  ];

  const groups = ['CORE', 'CONTROL', 'INSIGHT', 'INFRA', 'META'];

  if (!isOpen) return null;

  return (
    <aside className="relative h-full bg-[var(--ios-glass)] backdrop-blur-md border-r border-[var(--ios-border)] w-64 flex flex-col z-50">
      <div className="flex justify-between items-center p-4 border-b border-[var(--ios-border)]">
        <select
          value={selectedProjectId || ''}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          className="bg-transparent text-[var(--text-main)] font-semibold focus:outline-none"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button onClick={toggleCollapse} className="text-[var(--text-muted)] hover:text-[var(--text-main)]">
          {collapsed ? '→' : '←'}
        </button>
        <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-main)] ml-2">
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {groups.map((group) => {
          const items = navItems.filter((i) => i.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group} className="mb-4">
              {!collapsed && <div className="px-4 py-1 text-xs text-[var(--text-muted)] uppercase">{group}</div>}
              {items.map((item) => {
                const isActive = location.pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`flex items-center gap-3 px-4 py-2 mx-2 rounded-lg transition-colors ${
                      isActive
                        ? 'bg-[var(--ios-selected)] text-[var(--text-main)]'
                        : 'text-[var(--text-muted)] hover:bg-[var(--ios-hover)]'
                    }`}
                  >
                    <span className="text-lg">{item.icon}</span>
                    {!collapsed && <span>{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </div>
    </aside>
  );
};
