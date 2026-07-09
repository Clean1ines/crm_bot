import type {
  FrontendWorkflowEventEnvelope,
  FrontendWorkflowEventsQuery,
  FrontendWorkflowEventsResponse,
  WorkbenchWorkflowLiveStateResponse,
} from "@shared/api/modules/knowledge";

import {
  createInitialWorkflowLiveStateResponse,
  reduceWorkflowFrontendProjectionEvent,
} from "./shadow/workflowFrontendProjectionReducer";

export type WorkflowProjectionTarget = {
  documentId: string;
  workflowRunId: string;
  fileName: string;
  documentStatus: string;
};

type WorkflowProjectionApi = {
  getFrontendWorkflowEvents: (
    projectId: string,
    documentId: string,
    workflowRunId: string,
    query: FrontendWorkflowEventsQuery,
  ) => Promise<{ data: FrontendWorkflowEventsResponse }>;
  streamFrontendWorkflowEvents: (
    projectId: string,
    documentId: string,
    workflowRunId: string,
    query: FrontendWorkflowEventsQuery,
    onMessage: (event: FrontendWorkflowEventEnvelope) => void,
    onError?: (error: unknown) => void,
  ) => () => void;
} & Record<string, unknown>;

const FRONTEND_WORKFLOW_EVENT_PAGE_LIMIT = 200;

export const hydrateWorkflowProjectionFromFrontendEvents = async ({
  projectId,
  target,
  api,
}: {
  projectId: string;
  target: WorkflowProjectionTarget;
  api: Pick<WorkflowProjectionApi, "getFrontendWorkflowEvents"> &
    Record<string, unknown>;
}): Promise<{
  state: WorkbenchWorkflowLiveStateResponse;
  streamQuery: FrontendWorkflowEventsQuery;
}> => {
  let state = createInitialWorkflowLiveStateResponse({
    documentId: target.documentId,
    projectId,
    fileName: target.fileName,
    documentStatus: target.documentStatus,
    workflowRunId: target.workflowRunId,
  });
  let query: FrontendWorkflowEventsQuery = {
    after_source_sequence: 0,
    limit: FRONTEND_WORKFLOW_EVENT_PAGE_LIMIT,
  };
  let lastCursor: string | null = null;
  let lastSourceSequence = 0;

  while (true) {
    const { data } = await api.getFrontendWorkflowEvents(
      projectId,
      target.documentId,
      target.workflowRunId,
      query,
    );
    const orderedEvents = data.events
      .slice()
      .sort((left, right) => left.source_sequence_number - right.source_sequence_number);

    for (const event of orderedEvents) {
      state = reduceWorkflowFrontendProjectionEvent(state, event);
      lastSourceSequence = Math.max(lastSourceSequence, event.source_sequence_number);
    }

    if (data.next_cursor) {
      lastCursor = data.next_cursor;
      query = {
        after_cursor: data.next_cursor,
        limit: FRONTEND_WORKFLOW_EVENT_PAGE_LIMIT,
      };
      continue;
    }

    break;
  }

  return {
    state,
    streamQuery: lastCursor
      ? { after_cursor: lastCursor, limit: FRONTEND_WORKFLOW_EVENT_PAGE_LIMIT }
      : {
          after_source_sequence: lastSourceSequence,
          limit: FRONTEND_WORKFLOW_EVENT_PAGE_LIMIT,
        },
  };
};

export const startWorkflowProjectionEventStream = async ({
  projectId,
  target,
  api,
  onState,
  onError,
  onEventApplied,
}: {
  projectId: string;
  target: WorkflowProjectionTarget;
  api: WorkflowProjectionApi;
  onState: (documentId: string, state: WorkbenchWorkflowLiveStateResponse) => void;
  onError: (documentId: string, error: unknown) => void;
  onEventApplied?: (event: FrontendWorkflowEventEnvelope) => void;
}): Promise<() => void> => {
  const hydrated = await hydrateWorkflowProjectionFromFrontendEvents({
    projectId,
    target,
    api,
  });
  let currentState = hydrated.state;
  onState(target.documentId, currentState);

  return api.streamFrontendWorkflowEvents(
    projectId,
    target.documentId,
    target.workflowRunId,
    hydrated.streamQuery,
    (event) => {
      currentState = reduceWorkflowFrontendProjectionEvent(currentState, event);
      onState(target.documentId, currentState);
      onEventApplied?.(event);
    },
    (error) => onError(target.documentId, error),
  );
};
