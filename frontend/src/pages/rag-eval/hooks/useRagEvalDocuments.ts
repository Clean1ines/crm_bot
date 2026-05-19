import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { knowledgeApi } from '@shared/api/modules/knowledge';

export interface RagEvalDocumentItem {
  id: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processing' | 'processed' | 'error';
  chunk_count: number;
  created_at: string;
}

export const useRagEvalDocuments = (projectId: string | undefined, selectedDocumentId: string) => {
  const documentsQuery = useQuery({
    queryKey: ['knowledge-documents', projectId],
    queryFn: async () => {
      if (!projectId) return [];
      const { data } = await knowledgeApi.list(projectId);
      const payload = data && typeof data === 'object' ? data as Record<string, unknown> : {};
      const list = Array.isArray(payload.documents) ? payload.documents : Array.isArray(payload.items) ? payload.items : [];
      return list as RagEvalDocumentItem[];
    },
    enabled: !!projectId,
  });
  const documents = useMemo(() => (Array.isArray(documentsQuery.data) ? documentsQuery.data : []), [documentsQuery.data]);
  const processedDocuments = useMemo(() => documents.filter((doc) => doc.status === 'processed' && doc.chunk_count > 0), [documents]);
  const activeDocumentId = selectedDocumentId || processedDocuments[0]?.id || '';
  const activeDocument = processedDocuments.find((doc) => doc.id === activeDocumentId) || null;
  return { documentsQuery, documents, processedDocuments, activeDocumentId, activeDocument };
};
