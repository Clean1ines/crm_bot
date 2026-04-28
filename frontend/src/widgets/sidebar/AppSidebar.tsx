import React, { useState, useEffect } from 'react';
import { NavLink, useNavigate, useParams } from 'react-router-dom';
import { useProjectStore, useProjects } from '@entities/project';
import { CreateProjectModal } from '@features/project/create';
import { DeleteConfirmModal } from '@shared/ui';
import { useMediaQuery } from '@/shared/lib/hooks/useMediaQuery';
import {
  MessageSquare,
  Users,
  Settings,
  BookOpen,
  Plug,
  UserCog,
  PlusCircle,
  User,
  ChevronDown,
} from 'lucide-react';
import frontendLogger from '@shared/lib/logger';
import { ThemeToggle } from '@shared/ui/theme';

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { path: 'dialogs', label: 'Диалоги', icon: <MessageSquare className="w-4 h-4" /> },
  { path: 'tickets', label: 'Тикеты', icon: <UserCog className="w-4 h-4" /> },
  { path: 'clients', label: 'Клиенты', icon: <Users className="w-4 h-4" /> },
  { path: 'knowledge', label: 'Знания', icon: <BookOpen className="w-4 h-4" /> },
  { path: 'managers', label: 'Менеджеры', icon: <User className="w-4 h-4" /> },
  { path: 'channels', label: 'Каналы', icon: <Plug className="w-4 h-4" /> },
  { path: 'settings', label: 'Настройки', icon: <Settings className="w-4 h-4" /> },
];

export const AppSidebar: React.FC = () => {
  const navigate = useNavigate();
  const { projectId: urlProjectId } = useParams<{ projectId: string }>();
  const { selectedProjectId, setSelectedProjectId } = useProjectStore();
  const {
    projects,
    isCreateOpen,
    isDeleteOpen,
    deletingProject,
    openCreateModal,
    closeModals,
    createProject,
    deleteProject,
    isCreating,
    isDeleting,
  } = useProjects();

  const [isProjectSelectOpen, setIsProjectSelectOpen] = useState(false);

  const isMobile = useMediaQuery('(max-width: 768px)');
  const [isOpen] = useState(!isMobile);

  useEffect(() => {
    frontendLogger.info('AppSidebar mounted');
    return () => {
      frontendLogger.info('AppSidebar unmounted');
    };
  }, []);

  useEffect(() => {
    frontendLogger.debug('AppSidebar state updated', { urlProjectId, projectsCount: projects.length });
  }, [urlProjectId, projects.length]);

  const handleProjectSelect = (projectId: string) => {
    frontendLogger.info('Project selected', { projectId, previousUrl: urlProjectId });
    setSelectedProjectId(projectId);
    navigate(`/projects/${projectId}/dialogs`);
    setIsProjectSelectOpen(false);
  };

  const handleDelete = async () => {
    if (!deletingProject) return;

    frontendLogger.warn('Deleting project', {
      projectId: deletingProject.id,
      projectName: deletingProject.name,
    });
    await deleteProject(deletingProject.id);
  };

  const fallbackProjectId = urlProjectId || selectedProjectId || projects[0]?.id;
  const activeProjectId = fallbackProjectId || undefined;
  const currentProject = projects.find((project) => project.id === activeProjectId);

  const renderNavItem = (item: NavItem) => {
    const disabled = !fallbackProjectId;
    const linkClasses = (isActive: boolean) => {
      const base = 'flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-150';
      const activeClass = 'bg-white text-[var(--accent-primary)] shadow-sm';
      const inactiveClass = 'text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)] hover:shadow-sm';
      return `${base} ${isActive ? activeClass : inactiveClass}`;
    };
    const disabledClasses = 'flex items-center gap-3 px-3 py-2 rounded-lg text-[var(--text-muted)] opacity-50 cursor-not-allowed';

    if (disabled) {
      return (
        <div key={item.path} className={disabledClasses}>
          {item.icon}
          <span className="text-sm font-medium">{item.label}</span>
        </div>
      );
    }

    return (
      <NavLink
        key={item.path}
        to={`/projects/${fallbackProjectId}/${item.path}`}
        className={({ isActive }) => linkClasses(isActive)}
      >
        {item.icon}
        <span className="text-sm font-medium">{item.label}</span>
      </NavLink>
    );
  };

  if (isMobile) {
    return (
      <>
        <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-heavy">
          <div className="flex gap-1 overflow-x-auto px-2 py-2 scrollbar-hide">
            {navItems.map((item) => {
              const disabled = !fallbackProjectId;
              if (disabled) {
                return (
                  <div
                    key={item.path}
                    className="flex min-w-[72px] flex-col items-center gap-1 rounded-xl px-2 py-1.5 text-[var(--text-muted)] opacity-50"
                  >
                    {item.icon}
                    <span className="text-[10px] font-medium">{item.label}</span>
                  </div>
                );
              }

              return (
                <NavLink
                  key={item.path}
                  to={`/projects/${fallbackProjectId}/${item.path}`}
                  className={({ isActive }) =>
                    `flex min-w-[72px] flex-col items-center gap-1 rounded-xl px-2 py-1.5 transition-colors ${
                      isActive
                        ? 'bg-[var(--accent-muted)] text-[var(--accent-primary)]'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)]'
                    }`
                  }
                >
                  {item.icon}
                  <span className="text-[10px] font-medium">{item.label}</span>
                </NavLink>
              );
            })}

            <button
              type="button"
              onClick={() => navigate('/profile')}
              className="flex min-w-[72px] flex-col items-center gap-1 rounded-xl px-2 py-1.5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)]"
            >
              <User className="h-4 w-4" />
              <span className="text-[10px] font-medium">Профиль</span>
            </button>

            <div className="flex min-w-[72px] items-center justify-center px-2 py-1.5">
              <ThemeToggle compact />
            </div>
          </div>
        </nav>

        <CreateProjectModal
          isOpen={isCreateOpen}
          onClose={closeModals}
          onCreate={async (name) => {
            frontendLogger.info('Creating project', { name });
            await createProject(name);
          }}
          isPending={isCreating}
        />
        <DeleteConfirmModal
          isOpen={isDeleteOpen}
          onClose={closeModals}
          onConfirm={handleDelete}
          projectName={deletingProject?.name || ''}
          itemName={deletingProject?.name || ''}
          itemType="project"
          isPending={isDeleting}
        />
      </>
    );
  }

  if (!isOpen) return null;

  return (
    <aside className="w-64 h-full bg-[var(--surface-secondary)] flex flex-col">
      <div className="p-5 flex items-center gap-2">
        <div className="w-6 h-6 rounded-full bg-[var(--accent-primary)] shadow-sm" />
        <span className="font-semibold text-[var(--text-primary)] text-lg tracking-tight">OMNICA</span>
      </div>

      <div className="px-4 pb-4 relative">
        <button
          onClick={() => setIsProjectSelectOpen(!isProjectSelectOpen)}
          className="w-full flex items-center justify-between bg-white rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] shadow-sm hover:shadow-md transition-all"
        >
          <span className="truncate">{currentProject?.name || 'Выберите проект'}</span>
          <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />
        </button>
        {isProjectSelectOpen && (
          <div className="absolute left-4 right-4 top-[calc(100%-8px)] z-10 bg-white rounded-lg shadow-md mt-1 max-h-48 overflow-y-auto">
            {projects.map((project) => (
              <button
                key={project.id}
                onClick={() => handleProjectSelect(project.id)}
                className="w-full text-left px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-secondary)] transition-colors first:rounded-t-lg last:rounded-b-lg"
              >
                {project.name}
              </button>
            ))}
          </div>
        )}
      </div>

      <nav className="flex-1 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(renderNavItem)}
      </nav>

      <div className="p-4 space-y-2">
        <button
          type="button"
          onClick={() => navigate('/profile')}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-white"
        >
          <div className="w-8 h-8 rounded-full bg-[var(--accent-muted)] flex items-center justify-center text-[var(--accent-primary)] font-medium shadow-sm">
            <User className="w-4 h-4" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-medium text-[var(--text-primary)]">Администратор</div>
            <div className="text-xs text-[var(--text-muted)]">Профиль и вход</div>
          </div>
        </button>
        <button
          onClick={openCreateModal}
          className="w-full text-sm text-[var(--accent-primary)] hover:bg-white px-3 py-1.5 rounded-lg transition-colors flex items-center gap-2 justify-center"
        >
          <PlusCircle className="w-4 h-4" />
          Новый проект
        </button>

        <div className="pt-2">
          <ThemeToggle />
        </div>
      </div>

      <CreateProjectModal
        isOpen={isCreateOpen}
        onClose={closeModals}
        onCreate={async (name) => {
          frontendLogger.info('Creating project', { name });
          await createProject(name);
        }}
        isPending={isCreating}
      />
      <DeleteConfirmModal
        isOpen={isDeleteOpen}
        onClose={closeModals}
        onConfirm={handleDelete}
        projectName={deletingProject?.name || ''}
        itemName={deletingProject?.name || ''}
        itemType="project"
        isPending={isDeleting}
      />
    </aside>
  );
};
