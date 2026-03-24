import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Project, useProjectStore } from '@entities/project';
import { api } from '@shared/api/client'; 

export const useProjects = () => {
  const queryClient = useQueryClient();
  const { addProject, removeProject } = useProjectStore();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [deletingProject, setDeletingProject] = useState<Project | null>(null);

  // Список проектов
  const { data: projects = [], isLoading, error } = useQuery({
    queryKey: ['projects'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/projects');
      if (error) throw error;
      return data;
    },
  });

  // Создание
  const createMutation = useMutation({
    mutationFn: async (name: string) => {
      const { data, error } = await api.POST('/api/projects', {
        body: { name }
      });
      if (error) throw error;
      return data;
    },
    onSuccess: (newProject) => {
      addProject(newProject);
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setIsCreateOpen(false);
    },
  });

  // Удаление
  const deleteMutation = useMutation({
    mutationFn: async (projectId: string) => {
      const { error } = await api.DELETE('/api/projects/{project_id}', {
        params: {
          path: { project_id: projectId }
        }
      });
      if (error) throw error;
      return projectId;
    },
    onSuccess: (id) => {
      removeProject(id);
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setIsDeleteOpen(false);
    },
  });

  // Обновление токена бота
  const updateBotTokenMutation = useMutation({
    mutationFn: async ({ projectId, token }: { projectId: string; token: string | null }) => {
      const { data, error } = await api.POST('/api/projects/{project_id}/bot-token', {
        params: {
          path: { project_id: projectId }
        },
        body: { token: token || '' }
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });

  return {
    projects,
    isLoading,
    error,
    isCreateOpen,
    isDeleteOpen,
    deletingProject,
    openCreateModal: () => setIsCreateOpen(true),
    openDeleteConfirm: (p: Project) => {
      setDeletingProject(p);
      setIsDeleteOpen(true);
    },
    closeModals: () => {
      setIsCreateOpen(false);
      setIsDeleteOpen(false);
      setDeletingProject(null);
    },
    createProject: (name: string) => createMutation.mutateAsync(name),
    deleteProject: (id: string) => deleteMutation.mutateAsync(id),
    updateBotToken: updateBotTokenMutation.mutateAsync,
    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
    isUpdatingBotToken: updateBotTokenMutation.isPending,
  };
};
