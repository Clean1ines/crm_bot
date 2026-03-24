import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProjectStore, useProjects, Project, ProjectItem } from '@entities/project';
import { useMediaQuery } from '@/shared/lib/hooks/useMediaQuery';
import { HamburgerMenu } from '@widgets/header';
import { CreateProjectModal } from '@features/project/create';
import { EditProjectModal } from '@features/project/edit';
import { DeleteConfirmModal } from '@shared/ui';
import { Sidebar } from '@shared/ui/Sidebar/Sidebar';
import { useAppStore } from '../../../app/store';

const Button: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ className, ...props }) => (
  <button
    {...props}
    className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${className || ''}`}
  />
);

export const ProjectsSidebar: React.FC = () => {
  const navigate = useNavigate();
  const { currentProjectId, setCurrentProjectId } = useProjectStore();
  const { setSelectedProjectId } = useAppStore();
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

  const isMobile = useMediaQuery('(max-width: 768px)');
  const [isSidebarOpen, setIsSidebarOpen] = useState(!isMobile);

  const [prevIsMobile, setPrevIsMobile] = useState(isMobile);
  if (isMobile !== prevIsMobile) {
    setPrevIsMobile(isMobile);
    setIsSidebarOpen(!isMobile);
  }

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

  const handleProjectClick = (projectId: string) => {
    setCurrentProjectId(projectId);
    setSelectedProjectId(projectId);
    navigate(`/workspace?projectId=${projectId}`);
  };

  const handleProjectSelect = (projectId: string) => {
    setCurrentProjectId(projectId);
    setSelectedProjectId(projectId);
    navigate(`/workspace?projectId=${projectId}`);
  };

  const handleCloseSidebar = () => setIsSidebarOpen(false);
  const handleOpenSidebar = () => setIsSidebarOpen(true);

  if (!isSidebarOpen) {
    return <HamburgerMenu onOpenSidebar={handleOpenSidebar} showHomeIcon={false} />;
  }

  const headerContent = (
    <div className="p-4">
      <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">
        Project
      </label>
      <select
        value={currentProjectId || ''}
        onChange={(e) => handleProjectSelect(e.target.value)}
        className="w-full bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-md px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)] transition-colors"
      >
        <option value="" disabled>Select a project</option>
        {projects.map((p: Project) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </div>
  );

  const footerContent = (
    <div className="p-4 border-t border-[var(--border-subtle)] space-y-2">
      <Button
        onClick={openCreateModal}
        className="w-full bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:bg-[var(--border-subtle)]"
      >
        + New Project
      </Button>
    </div>
  );

  return (
    <>
      <Sidebar
        isOpen={isSidebarOpen}
        onClose={handleCloseSidebar}
        header={headerContent}
        footer={footerContent}
        position="left"
        width="w-72"
        className={isMobile ? 'fixed top-0 left-0 h-full' : 'relative'}
      >
        <div className="space-y-1">
          {projects.map((project: Project) => (
            <ProjectItem
              key={project.id}
              project={project}
              isActive={currentProjectId === project.id}
              onClick={handleProjectClick}
              actions={
                <>
                  <button
                    onClick={() => handleOpenEditModal(project)}
                    className="text-[var(--text-muted)] hover:text-[var(--accent-primary)] transition-colors p-1"
                    title="Edit"
                  >
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 3L21 7L7 21H3V17L17 3Z" />
                    </svg>
                  </button>
                  <button
                    onClick={() => openDeleteConfirm(project)}
                    className="text-[var(--text-muted)] hover:text-[var(--accent-danger)] transition-colors p-1"
                    title="Delete"
                  >
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 6H21M19 6V20C19 21.1046 18.1046 22 17 22H7C5.89543 22 5 21.1046 5 20V6M8 6V4C8 2.89543 8.89543 2 10 2H14C15.1046 2 16 2.89543 16 4V6" />
                    </svg>
                  </button>
                </>
              }
            />
          ))}
        </div>
      </Sidebar>

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
    </>
  );
};
