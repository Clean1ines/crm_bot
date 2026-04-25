import React, { useState, useEffect } from 'react';
import { NavLink, useNavigate, useParams } from 'react-router-dom';
import { useProjectStore, useProjects, Project } from '@entities/project';
import { useAppStore } from '../../app/store';
import { CreateProjectModal } from '@features/project/create';
import { EditProjectModal } from '@features/project/edit';
import { DeleteConfirmModal } from '@shared/ui';
import { useMediaQuery } from '@/shared/lib/hooks/useMediaQuery';
import {
  MessageSquare,
  Users,
  Settings,
  BookOpen,
  BarChart3,
  Plug,
  UserCog,
  PlusCircle,
  User,
  ChevronDown,
} from 'lucide-react';
import frontendLogger from '@shared/lib/logger';

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
  const { setSelectedProjectId } = useAppStore();
  const { setCurrentProjectId } = useProjectStore();
  const {
    projects,
    isCreateOpen,
    isEditOpen,
    isDeleteOpen,
    editingProject,
    deletingProject,
    openCreateModal,
    openEditModal,
    openDeleteConfirm,
    closeModals,
    createProject,
    updateProject,
    deleteProject,
    isCreating,
    isUpdating,
    isDeleting,
  } = useProjects() as any;

  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [isProjectSelectOpen, setIsProjectSelectOpen] = useState(false);

  const isMobile = useMediaQuery('(max-width: 768px)');
  const [isOpen, setIsOpen] = useState(!isMobile);

  // Log component mount
  useEffect(() => {
    frontendLogger.info('AppSidebar mounted', { urlProjectId, projectsCount: projects.length });
    return () => {
      frontendLogger.info('AppSidebar unmounted');
    };
  }, []);

  // Log when urlProjectId or projects change
  useEffect(() => {
    frontendLogger.debug('AppSidebar state updated', { urlProjectId, projectsCount: projects.length });
  }, [urlProjectId, projects]);

  const handleProjectSelect = (projectId: string) => {
    frontendLogger.info('Project selected', { projectId, previousUrl: urlProjectId });
    setCurrentProjectId(projectId);
    setSelectedProjectId(projectId);
    navigate(`/projects/${projectId}/dialogs`);
    setIsProjectSelectOpen(false);
  };

  const handleOpenEditModal = (project: Project) => {
    frontendLogger.debug('Edit project modal opened', { projectId: project.id, projectName: project.name });
    setEditName(project.name);
    setEditDescription((project as any).description || '');
    openEditModal(project);
  };

  const handleUpdate = async (name: string, description: string) => {
    if (editingProject) {
      frontendLogger.info('Updating project', { projectId: editingProject.id, name });
      await updateProject({ id: editingProject.id, name, description } as any);
    }
  };

  const handleDelete = async () => {
    if (deletingProject) {
      frontendLogger.warn('Deleting project', { projectId: deletingProject.id, projectName: deletingProject.name });
      await deleteProject(deletingProject.id);
    }
  };

  if (!isOpen && isMobile) return null;

  // For dropdown display, we need the current project name. Use URL project if available, else use store's selected.
  const activeProjectId = urlProjectId || undefined;
  const currentProject = projects.find((p: Project) => p.id === activeProjectId);

  const renderNavItem = (item: NavItem) => {
    // Disable if there's no project ID in URL (i.e., not in a project context)
    const disabled = !urlProjectId;
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

    // Use the URL projectId directly to construct the link
    const to = `/projects/${urlProjectId}/${item.path}`;
    return (
      <NavLink
        key={item.path}
        to={to}
        className={({ isActive }) => linkClasses(isActive)}
      >
        {item.icon}
        <span className="text-sm font-medium">{item.label}</span>
      </NavLink>
    );
  };

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
            {projects.map((p: Project) => (
              <button
                key={p.id}
                onClick={() => handleProjectSelect(p.id)}
                className="w-full text-left px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--surface-secondary)] transition-colors first:rounded-t-lg last:rounded-b-lg"
              >
                {p.name}
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
      </div>

      <CreateProjectModal
        isOpen={isCreateOpen}
        onClose={closeModals}
        onCreate={async (name, description) => {
          frontendLogger.info('Creating project', { name });
          await createProject({ name, description } as any);
        }}
        isPending={isCreating}
      />
      <EditProjectModal
        isOpen={isEditOpen}
        onClose={closeModals}
        name={editName}
        description={editDescription}
        onNameChange={setEditName}
        onDescriptionChange={setEditDescription}
        onUpdate={handleUpdate}
        isPending={isUpdating}
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
