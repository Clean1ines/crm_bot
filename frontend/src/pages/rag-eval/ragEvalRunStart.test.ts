import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import type { WorkbenchRagEvalRunResponse } from '@shared/api/modules/ragEval';
import { ragEvalQueryKeys } from './ragEvalQueryKeys';
import { acceptStartedRagEvalRun } from './ragEvalRunStart';

const startedRunResponse: WorkbenchRagEvalRunResponse = {
  run: {
    run_id: 'run-1',
    project_id: 'project-1',
    status: 'running',
    total_entries: 0,
    total_questions: 0,
    completed_questions: 0,
    top1_hits: 0,
    top3_hits: 0,
    top5_hits: 0,
    misses: 0,
    created_at: '2026-07-10T12:00:00Z',
  },
};

describe('acceptStartedRagEvalRun', () => {
  it('stores the accepted run in the canonical latest-query cache', () => {
    const queryClient = new QueryClient();

    acceptStartedRagEvalRun({
      notifySuccess: vi.fn(),
      projectId: 'project-1',
      queryClient,
      response: startedRunResponse,
    });

    expect(queryClient.getQueryData(ragEvalQueryKeys.latest('project-1'))).toEqual(
      startedRunResponse,
    );
  });

  it('describes a 202 response as started rather than completed', () => {
    const notifySuccess = vi.fn();

    acceptStartedRagEvalRun({
      notifySuccess,
      projectId: 'project-1',
      queryClient: new QueryClient(),
      response: startedRunResponse,
    });

    expect(notifySuccess).toHaveBeenCalledWith('Проверка базы знаний запущена');
    expect(notifySuccess).not.toHaveBeenCalledWith('Проверка базы знаний завершена');
  });
});
