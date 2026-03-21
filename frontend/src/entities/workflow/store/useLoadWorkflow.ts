import { useQuery } from '@tanstack/react-query';
import { useWorkflowStore } from '../store/workflowStore';
import { workflowApi } from '@/entities/workflow/api/workflowApi';
import { ApiWorkflowDetail } from './types';

export const useLoadWorkflow = (workflowId: string | null) => {
  return useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: async () => {
      if (!workflowId) {
        console.log('[useLoadWorkflow] no workflowId, skipping');
        return null;
      }
      console.log(`[useLoadWorkflow] fetching workflow ${workflowId}`);
      try {
        const response = await workflowApi.get(workflowId);
        console.log('[useLoadWorkflow] received response:', response);
        const workflowData = response.data as ApiWorkflowDetail;
        console.log('[useLoadWorkflow] workflowData:', workflowData);
        console.log('[useLoadWorkflow] nodes count:', workflowData?.nodes?.length);
        console.log('[useLoadWorkflow] edges count:', workflowData?.edges?.length);
        
        console.log('[useLoadWorkflow] about to call loadWorkflow');
        useWorkflowStore.getState().loadWorkflow(workflowData);
        console.log('[useLoadWorkflow] loadWorkflow called successfully');
        
        return response;
      } catch (error) {
        console.error('[useLoadWorkflow] error:', error);
        throw error;
      }
    },
    enabled: !!workflowId,
    staleTime: 0,
  });
};