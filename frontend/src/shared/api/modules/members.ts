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
,
  getReplyHistory: (projectId: string, managerUserId: string, limit?: number, offset?: number) =>
    client.GET('/api/projects/{project_id}/members/{manager_user_id}/reply-history', {
      params: {
        path: {
          project_id: projectId,
          manager_user_id: managerUserId,
        },
        query: {
          limit,
          offset,
        },
      },
    }),
};
