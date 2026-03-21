import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Project, useProjectStore } from '@entities/project';
import { useNotification } from '@/shared/lib/notification/useNotifications';
import { api, getErrorMessage, ProjectResponse } from '@shared/api';

interface CreateProjectParams {
  name: string;
  description?: string;
}

interface UpdateProjectParams {
  id: string;
  name: string;
  description?: string;
}

const fetchProjects = async (): Promise<ProjectResponse[]> => {
  const { data, error } = await api.projects.list();
  if (error) throw error;
  return data || [];
};

export const useProjects = () => {
  const queryClient = useQueryClient();
  const { showNotification } = useNotification();
  const { addProject, updateProject, removeProject } = useProjectStore();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [deletingProject, setDeletingProject] = useState<Project | null>(null);

  const {
    data: projects = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  });

  const createMutation = useMutation({
    mutationFn: async ({ name, description = '' }: CreateProjectParams) => {
      const { data, error } = await api.projects.create({ name, description });
      if (error) throw error;
      return data;
    },
    onSuccess: (data) => {
      if (data && data.id && data.name) {
        addProject({
          id: data.id,
          name: data.name,
          description: data.description || '',
        });
        queryClient.invalidateQueries({ queryKey: ['projects'] });
        showNotification(`Project "${data.name}" created`, 'success');
        setIsCreateOpen(false);
      }
    },
    onError: (err: unknown) => {
      const message = getErrorMessage(err);
      showNotification(message, 'error');
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, name, description = '' }: UpdateProjectParams) => {
      const { data, error } = await api.projects.update(id, { name, description });
      if (error) throw error;
      return data;
    },
    onSuccess: (data, variables) => {
      if (data && data.id && data.name) {
        updateProject(variables.id, { name: variables.name, description: variables.description || '' });
        queryClient.invalidateQueries({ queryKey: ['projects'] });
        showNotification(`Project updated`, 'success');
        setIsEditOpen(false);
        setEditingProject(null);
      }
    },
    onError: (err: unknown) => {
      const message = getErrorMessage(err);
      showNotification(message, 'error');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.projects.delete(id);
      if (error) throw error;
      return id;
    },
    onSuccess: (id) => {
      removeProject(id);
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      showNotification('Project deleted', 'success');
      setIsDeleteOpen(false);
      setDeletingProject(null);
    },
    onError: (err: unknown) => {
      const message = getErrorMessage(err);
      showNotification(message, 'error');
    },
  });

  const validateName = (name: string): string | null => {
    if (!name.trim()) return 'Project name cannot be empty';
    if (name.length > 100) return 'Project name must not exceed 100 characters';
    return null;
  };

  const createProject = useCallback(
    async ({ name, description = '' }: CreateProjectParams) => {
      const validationError = validateName(name);
      if (validationError) {
        showNotification(validationError, 'error');
        return false;
      }
      try {
        await createMutation.mutateAsync({ name, description });
        return true;
      } catch {
        return false;
      }
    },
    [createMutation, showNotification]
  );

  const updateProjectHandler = useCallback(
    async ({ id, name, description = '' }: UpdateProjectParams) => {
      const validationError = validateName(name);
      if (validationError) {
        showNotification(validationError, 'error');
        return false;
      }
      try {
        await updateMutation.mutateAsync({ id, name, description });
        return true;
      } catch {
        return false;
      }
    },
    [updateMutation, showNotification]
  );

  const deleteProjectHandler = useCallback(
    async (id: string) => {
      try {
        await deleteMutation.mutateAsync(id);
        return true;
      } catch {
        return false;
      }
    },
    [deleteMutation]
  );

  const openEditModal = useCallback((project: Project) => {
    setEditingProject(project);
    setIsEditOpen(true);
  }, []);

  const openDeleteConfirm = useCallback((project: Project) => {
    setDeletingProject(project);
    setIsDeleteOpen(true);
  }, []);

  const closeModals = useCallback(() => {
    setIsCreateOpen(false);
    setIsEditOpen(false);
    setIsDeleteOpen(false);
    setEditingProject(null);
    setDeletingProject(null);
  }, []);

  return {
    projects,
    isLoading,
    error,
    refetch,
    isCreateOpen,
    isEditOpen,
    isDeleteOpen,
    editingProject,
    deletingProject,
    openCreateModal: () => setIsCreateOpen(true),
    openEditModal,
    openDeleteConfirm,
    closeModals,
    createProject,
    updateProject: updateProjectHandler,
    deleteProject: deleteProjectHandler,
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  };
};
