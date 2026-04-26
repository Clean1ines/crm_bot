import type { Project } from '../model/types';
import { useProjectModalState } from '../model/modalState';
import {
  useCreateProjectMutation,
  useDeleteProjectMutation,
  useUpdateBotTokenMutation,
  useUpdateManagerBotTokenMutation,
} from './useProjectMutations';
import { useProjectListQuery } from './useProjectQueries';

export const useProjects = () => {
  const {
    isCreateOpen,
    isDeleteOpen,
    deletingProject,
    openCreateModal,
    openDeleteConfirm,
    closeModals,
  } = useProjectModalState();

  const projectsQuery = useProjectListQuery();
  const createMutation = useCreateProjectMutation(() => closeModals());
  const deleteMutation = useDeleteProjectMutation(() => closeModals());
  const updateBotTokenMutation = useUpdateBotTokenMutation();
  const updateManagerBotTokenMutation = useUpdateManagerBotTokenMutation();

  const projects = Array.isArray(projectsQuery.data) ? projectsQuery.data : [];

  return {
    projects,
    isLoading: projectsQuery.isLoading,
    error: projectsQuery.error,

    isCreateOpen,
    isDeleteOpen,
    deletingProject,
    openCreateModal,
    openDeleteConfirm: (project: Project) => openDeleteConfirm(project),
    closeModals,

    createProject: (name: string) => createMutation.mutateAsync(name),
    deleteProject: (id: string) => deleteMutation.mutateAsync(id),
    updateBotToken: updateBotTokenMutation.mutateAsync,
    updateManagerBotToken: updateManagerBotTokenMutation.mutateAsync,

    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
    isUpdatingBotToken: updateBotTokenMutation.isPending,
    isUpdatingManagerBotToken: updateManagerBotTokenMutation.isPending,
  };
};
