import { authedJsonRequest, authedMultipartRequest } from '../core/http';

export const knowledgeApi = {
  list: (projectId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge`, {
      method: 'GET',
    }),

  upload: (projectId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    return authedMultipartRequest(`/api/projects/${projectId}/knowledge`, formData);
  },
};
