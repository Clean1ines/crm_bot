import { useMutation, useQueryClient } from '@tanstack/react-query';

import { projectsApi } from '@shared/api/modules/projects';
import type { Project } from '../model/types';
import { projectQueryKeys } from './queryKeys';

type BotTokenPayload = {
  projectId: string;
  token: string | null;
};

export const useCreateProjectMutation = (onSuccess?: (project: Project | undefined) => void) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (name: string) => {
      const { data, error } = await projectsApi.create({ name });
      if (error) throw error;
      return data as Project | undefined;
    },
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.list() });
      onSuccess?.(project);
    },
  });
};

export const useDeleteProjectMutation = (onSuccess?: (projectId: string) => void) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (projectId: string) => {
      const { error } = await projectsApi.delete(projectId);
      if (error) throw error;
      return projectId;
    },
    onSuccess: async (projectId) => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.list() });
      onSuccess?.(projectId);
    },
  });
};

export const useUpdateBotTokenMutation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ projectId, token }: BotTokenPayload) => {
      const { data, error } = token === null
        ? await projectsApi.clearBotToken(projectId)
        : await projectsApi.setBotToken(projectId, token);

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
    mutationFn: async ({ projectId, token }: BotTokenPayload) => {
      const { data, error } = token === null
        ? await projectsApi.clearManagerToken(projectId)
        : await projectsApi.setManagerToken(projectId, token);

      if (error) throw error;
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.list() });
    },
  });
};
