import { client } from '../core/openapi';

export type ClientListParams = {
  project_id: string;
  limit?: number;
  offset?: number;
  search?: string | null;
};

export const clientsApi = {
  list: (params: ClientListParams) =>
    client.GET('/api/clients', {
      params: { query: params },
    }),

  get: (clientId: string, projectId: string) =>
    client.GET('/api/clients/{client_id}', {
      params: {
        path: { client_id: clientId },
        query: { project_id: projectId },
      },
    }),
};
