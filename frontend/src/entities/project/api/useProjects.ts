import type { Project } from '../model/types';
import { useProjectModalState } from '../model/modalState';
import { useProjectsQuery } from './useProjectQueries';
import {
  useCreateProjectMutation,
  useDeleteProjectMutation,
  useUpdateBotTokenMutation,
  useUpdateManagerBotTokenMutation,
} from './useProjectMutations';

export const useProjects = () => {
  const projectsQuery = useProjectsQuery();
  const createMutation = useCreateProjectMutation();
  const deleteMutation = useDeleteProjectMutation();
  const updateBotTokenMutation = useUpdateBotTokenMutation();
  const updateManagerBotTokenMutation = useUpdateManagerBotTokenMutation();

  const {
    isCreateOpen,
    isDeleteOpen,
    deletingProject,
    openCreateModal,
    openDeleteConfirm,
    closeModals,
  } = useProjectModalState();

  const projects = Array.isArray(projectsQuery.data) ? projectsQuery.data : [];

  return {
    projects,
    isLoading: projectsQuery.isLoading,
    error: projectsQuery.error,

    isCreateOpen,
    isDeleteOpen,
    deletingProject,
    openCreateModal,
    openDeleteConfirm,
    closeModals,

    createProject: async (name: string, description?: string) => {
      await createMutation.mutateAsync({ name, description });
      closeModals();
    },

    deleteProject: async (id: string) => {
      await deleteMutation.mutateAsync(id);
      closeModals();
    },

    updateBotToken: updateBotTokenMutation.mutateAsync,
    updateManagerBotToken: updateManagerBotTokenMutation.mutateAsync,

    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
    isUpdatingBotToken: updateBotTokenMutation.isPending,
    isUpdatingManagerBotToken: updateManagerBotTokenMutation.isPending,
  };
};

export type UseProjectsResult = ReturnType<typeof useProjects>;
export type { Project };
