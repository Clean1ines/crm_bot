import { useQuery } from '@tanstack/react-query';
import { ragEvalApi } from '@shared/api/modules/ragEval';

const ACTIVE_RUN_STATUSES = new Set(['created', 'pending', 'processing', 'generating', 'ready', 'running', 'paused']);

export const useRagEvalReview = (activeDocumentId: string, statusRun?: Record<string, unknown>) => {
  const reviewQuery = useQuery({
    queryKey: ['rag-eval-latest-review', activeDocumentId],
    queryFn: async () => ragEvalApi.getLatestReview(activeDocumentId),
    enabled: !!activeDocumentId,
    retry: false,
    refetchInterval: (query) => {
      const latestReview = query.state.data?.review;
      const reviewRun = latestReview?.run as Record<string, unknown> | undefined;
      const status = String(reviewRun?.status || statusRun?.status || '');
      return ACTIVE_RUN_STATUSES.has(status) ? 3000 : false;
    },
  });
  return { reviewQuery };
};
