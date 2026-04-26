import { authedDeleteRequest, authedJsonRequest } from '../core/http';

export type ProjectMemberUpsertRequest = {
  user_id: string;
  role: string;
};

export const membersApi = {
  list: (projectId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/members`, {
      method: 'GET',
    }),

  upsert: (projectId: string, body: ProjectMemberUpsertRequest) =>
    authedJsonRequest(`/api/projects/${projectId}/members`, {
      method: 'POST',
      body,
    }),

  remove: (projectId: string, memberUserId: string) =>
    authedDeleteRequest(`/api/projects/${projectId}/members/${memberUserId}`),
};
