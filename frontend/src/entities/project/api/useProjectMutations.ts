import { useMutation, useQueryClient } from '@tanstack/react-query';

import type { Project } from '../model/types';
import { api } from '@shared/api/client';
import { projectQueryKeys } from './queryKeys';

type CreateProjectInput = {
  name: string;
  description?: string;
};

type ProjectTokenInput = {
  projectId: string;
  token: string | null;
};

export const useCreateProjectMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ name }: CreateProjectInput): Promise<Project | undefined> => {
      const { data, error } = await api.POST('/api/projects', {
        body: { name },
      });

      if (error) throw error;
      return data as Project | undefined;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.list() });
    },
  });
};

export const useDeleteProjectMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (projectId: string): Promise<string> => {
      const { error } = await api.DELETE('/api/projects/{project_id}', {
        params: {
          path: { project_id: projectId },
        },
      });

      if (error) throw error;
      return projectId;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.list() });
    },
  });
};

export const useUpdateBotTokenMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ projectId, token }: ProjectTokenInput) => {
      if (token === null) {
        const { data, error } = await api.projects.clearBotToken(projectId);
        if (error) throw error;
        return data;
      }

      const { data, error } = await api.projects.setBotToken(projectId, token);
      if (error) throw error;
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.list() });
    },
  });
};

export const useUpdateManagerBotTokenMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ projectId, token }: ProjectTokenInput) => {
      if (token === null) {
        const { data, error } = await api.projects.clearManagerToken(projectId);
        if (error) throw error;
        return data;
      }

      const { data, error } = await api.projects.setManagerToken(projectId, token);
      if (error) throw error;
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.list() });
    },
  });
};
