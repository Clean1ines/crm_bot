import { authedMultipartRequest } from '../core/http';

export const knowledgeApi = {
  upload: (projectId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    return authedMultipartRequest(`/api/projects/${projectId}/knowledge`, formData);
  },
};
