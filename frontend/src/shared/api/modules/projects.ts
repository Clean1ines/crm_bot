import { client } from '../core/openapi';
import { authedJsonRequest } from '../core/http';
import type {
  BotTokenRequest,
  ManagerAddRequest,
  ProjectChannelResponse,
  ProjectChannelUpsert,
  ProjectConfigurationResponse,
  ProjectCreate,
  ProjectIntegrationResponse,
  ProjectIntegrationUpsert,
  ProjectLimitProfileUpdate,
  ProjectPoliciesUpdate,
  ProjectSettingsUpdate,
  ProjectUpdate,
} from './projectTypes';

export const projectsApi = {
  list: () => client.GET('/api/projects'),

  create: (body: ProjectCreate) =>
    client.POST('/api/projects', { body }),

  get: (projectId: string) =>
    client.GET('/api/projects/{project_id}', {
      params: { path: { project_id: projectId } },
    }),

  update: (projectId: string, body: ProjectUpdate) =>
    client.PUT('/api/projects/{project_id}', {
      params: { path: { project_id: projectId } },
      body,
    }),

  delete: (projectId: string) =>
    client.DELETE('/api/projects/{project_id}', {
      params: { path: { project_id: projectId } },
    }),

  setBotToken: (projectId: string, token: string) =>
    client.POST('/api/projects/{project_id}/bot-token', {
      params: { path: { project_id: projectId } },
      body: { token } as BotTokenRequest,
    }),

  clearBotToken: (projectId: string) =>
    client.DELETE('/api/projects/{project_id}/bot-token', {
      params: { path: { project_id: projectId } },
    }),

  setManagerToken: (projectId: string, token: string) =>
    client.POST('/api/projects/{project_id}/manager-token', {
      params: { path: { project_id: projectId } },
      body: { token } as BotTokenRequest,
    }),

  clearManagerToken: (projectId: string) =>
    client.DELETE('/api/projects/{project_id}/manager-token', {
      params: { path: { project_id: projectId } },
    }),

  getManagers: (projectId: string) =>
    client.GET('/api/projects/{project_id}/managers', {
      params: { path: { project_id: projectId } },
    }),

  addManager: (projectId: string, chat_id: number) =>
    client.POST('/api/projects/{project_id}/managers', {
      params: { path: { project_id: projectId } },
      body: { chat_id } as ManagerAddRequest,
    }),

  removeManager: (projectId: string, chat_id: number) =>
    client.DELETE('/api/projects/{project_id}/managers/{chat_id}', {
      params: { path: { project_id: projectId, chat_id } },
    }),

  connectBot: (projectId: string, token: string, type: 'client' | 'manager') =>
    client.POST('/api/projects/{project_id}/connect-bot', {
      params: { path: { project_id: projectId } },
      body: { token, type },
    }),

  getConfiguration: (projectId: string) =>
    authedJsonRequest<ProjectConfigurationResponse>(`/api/projects/${projectId}/configuration`, {
      method: 'GET',
    }),

  updateSettings: (projectId: string, body: ProjectSettingsUpdate) =>
    authedJsonRequest<ProjectConfigurationResponse, ProjectSettingsUpdate>(`/api/projects/${projectId}/settings`, {
      method: 'PATCH',
      body,
    }),

  updatePolicies: (projectId: string, body: ProjectPoliciesUpdate) =>
    authedJsonRequest<ProjectConfigurationResponse, ProjectPoliciesUpdate>(`/api/projects/${projectId}/policies`, {
      method: 'PATCH',
      body,
    }),

  updateLimits: (projectId: string, body: ProjectLimitProfileUpdate) =>
    authedJsonRequest<ProjectConfigurationResponse, ProjectLimitProfileUpdate>(`/api/projects/${projectId}/limits`, {
      method: 'PATCH',
      body,
    }),

  listIntegrations: (projectId: string) =>
    authedJsonRequest<ProjectIntegrationResponse[]>(`/api/projects/${projectId}/integrations`, {
      method: 'GET',
    }),

  upsertIntegration: (projectId: string, body: ProjectIntegrationUpsert) =>
    authedJsonRequest<ProjectIntegrationResponse, ProjectIntegrationUpsert>(`/api/projects/${projectId}/integrations`, {
      method: 'POST',
      body,
    }),

  listChannels: (projectId: string) =>
    authedJsonRequest<ProjectChannelResponse[]>(`/api/projects/${projectId}/channels`, {
      method: 'GET',
    }),

  upsertChannel: (projectId: string, body: ProjectChannelUpsert) =>
    authedJsonRequest<ProjectChannelResponse, ProjectChannelUpsert>(`/api/projects/${projectId}/channels`, {
      method: 'POST',
      body,
    }),
};
