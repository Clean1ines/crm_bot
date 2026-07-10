import type { QueryClient } from '@tanstack/react-query';

import type { WorkbenchRagEvalRunResponse } from '@shared/api/modules/ragEval';
import { ragEvalQueryKeys } from './ragEvalQueryKeys';

type AcceptStartedRagEvalRunInput = {
  notifySuccess: (message: string) => void;
  projectId: string;
  queryClient: QueryClient;
  response: WorkbenchRagEvalRunResponse;
};

export const acceptStartedRagEvalRun = ({
  notifySuccess,
  projectId,
  queryClient,
  response,
}: AcceptStartedRagEvalRunInput): void => {
  queryClient.setQueryData(ragEvalQueryKeys.latest(projectId), response);
  notifySuccess('Проверка базы знаний запущена');
};
