import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
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

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { path: 'dialogs', label: 'Диалоги', icon: <MessageSquare className="w-4 h-4" /> },
  { path: 'clients', label: 'Клиенты', icon: <Users className="w-4 h-4" /> },
  { path: 'workflow', label: 'Логика ассистента', icon: <Settings className="w-4 h-4" /> },
  { path: 'knowledge', label: 'Знания', icon: <BookOpen className="w-4 h-4" /> },
  { path: 'analytics', label: 'Аналитика', icon: <BarChart3 className="w-4 h-4" /> },
  { path: 'channels', label: 'Каналы', icon: <Plug className="w-4 h-4" /> },
  { path: 'managers', label: 'Менеджеры', icon: <UserCog className="w-4 h-4" /> },
];

export const AppSidebar: React.FC = () => {
  const navigate = useNavigate();
  const { selectedProjectId, setSelectedProjectId } = useAppStore();
  const { currentProjectId, setCurrentProjectId } = useProjectStore();
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

  const handleProjectSelect = (projectId: string) => {
    setCurrentProjectId(projectId);
    setSelectedProjectId(projectId);
    navigate(`/projects/${projectId}/dialogs`);
    setIsProjectSelectOpen(false);
  };

  const handleOpenEditModal = (project: Project) => {
    setEditName(project.name);
    setEditDescription((project as any).description || '');
    openEditModal(project);
  };

  const handleUpdate = async (name: string, description: string) => {
    if (editingProject) {
      await updateProject({ id: editingProject.id, name, description } as any);
    }
  };

  const handleDelete = async () => {
    if (deletingProject) {
      await deleteProject(deletingProject.id);
    }
  };

  if (!isOpen && isMobile) return null;

  const currentProject = projects.find((p: Project) => p.id === selectedProjectId);

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
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={`/projects/${selectedProjectId}/${item.path}`}
            className={({ isActive }) => {
              const base = 'flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-150';
              const activeClass = 'bg-white text-[var(--accent-primary)] shadow-sm';
              const inactiveClass = 'text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)] hover:shadow-sm';
              return `${base} ${isActive ? activeClass : inactiveClass}`;
            }}
          >
            {item.icon}
            <span className="text-sm font-medium">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="p-4 space-y-2">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-[var(--accent-muted)] flex items-center justify-center text-[var(--accent-primary)] font-medium shadow-sm">
            <User className="w-4 h-4" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-medium text-[var(--text-primary)]">Администратор</div>
            <div className="text-xs text-[var(--text-muted)]">user@example.com</div>
          </div>
        </div>
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
