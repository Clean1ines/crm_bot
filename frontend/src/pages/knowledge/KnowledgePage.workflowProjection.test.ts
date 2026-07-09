import { describe, expect, it, vi } from "vitest";

import type {
  FrontendWorkflowEventEnvelope,
  FrontendWorkflowEventsQuery,
  FrontendWorkflowEventsResponse,
} from "@shared/api/modules/knowledge";

import {
  hydrateWorkflowProjectionFromFrontendEvents,
  startWorkflowProjectionEventStream,
  type WorkflowProjectionTarget,
} from "./workflowProjectionHydration";

const target: WorkflowProjectionTarget = {
  documentId: "source-document:project-1:doc-1",
  workflowRunId: "knowledge-extraction:source-document:project-1:doc-1",
  fileName: "doc.md",
  documentStatus: "processing",
};

const event = (
  projectionType: string,
  sequence: number,
  payload: Record<string, unknown> = {},
): FrontendWorkflowEventEnvelope => ({
  projection_event_id: `projection-${sequence}`,
  source_event_id: `source-${sequence}`,
  source_sequence_number: sequence,
  projection_version: 1,
  projection_type: projectionType,
  event_type: projectionType,
  operation_key: null,
  canonical_phase: "claim_builder_section_extraction",
  workflow_run_id: target.workflowRunId,
  project_id: "project-1",
  document_id: target.documentId,
  payload,
  occurred_at: `2026-06-25T12:${String(sequence).padStart(2, "0")}:00.000Z`,
  causation_command_id: null,
  correlation_id: null,
});

const page = (
  events: FrontendWorkflowEventEnvelope[],
  nextCursor: string | null,
  afterCursor: string | null = null,
): FrontendWorkflowEventsResponse => ({
  workflow_run_id: target.workflowRunId,
  after_source_sequence: null,
  after_cursor: afterCursor,
  next_cursor: nextCursor,
  events,
});

describe("KnowledgePage workflow projection hydration", () => {
  it("hydrates from getFrontendWorkflowEvents and never calls a snapshot fetch", async () => {
    const getFrontendWorkflowEvents = vi
      .fn()
      .mockResolvedValueOnce({
        data: page([event("workflow_manually_paused", 1)], null),
      });
    const forbiddenSnapshotFetch = vi.fn();

    const result = await hydrateWorkflowProjectionFromFrontendEvents({
      projectId: "project-1",
      target,
      api: {
        getFrontendWorkflowEvents,
        forbiddenSnapshotFetch,
      },
    });

    expect(forbiddenSnapshotFetch).not.toHaveBeenCalled();
    expect(getFrontendWorkflowEvents).toHaveBeenCalledWith(
      "project-1",
      target.documentId,
      target.workflowRunId,
      { after_source_sequence: 0, limit: 200 },
    );
    expect(result.state.workflow.workflow_status).toBe("paused");
    expect(result.streamQuery).toEqual({ after_source_sequence: 1, limit: 200 });
  });

  it("reduces every persisted page before opening SSE after the last cursor", async () => {
    const getFrontendWorkflowEvents = vi
      .fn()
      .mockResolvedValueOnce({
        data: page([event("workflow_source_document_persisted", 1)], "cursor-1"),
      })
      .mockResolvedValueOnce({
        data: page(
          [
            event("workflow_source_unit_created", 2, {
              source_unit_ref: "source-unit-1",
              source_unit_ordinal: 0,
            }),
          ],
          "cursor-2",
          "cursor-1",
        ),
      })
      .mockResolvedValueOnce({
        data: page([], null, "cursor-2"),
      });
    const streamFrontendWorkflowEvents = vi.fn(
      (
        _projectId: string,
        _documentId: string,
        _workflowRunId: string,
        _query: FrontendWorkflowEventsQuery,
        _onMessage: unknown,
        _onError?: unknown,
      ) => vi.fn(),
    );
    const onState = vi.fn();

    await startWorkflowProjectionEventStream({
      projectId: "project-1",
      target,
      api: {
        getFrontendWorkflowEvents,
        streamFrontendWorkflowEvents,
      },
      onState,
      onError: vi.fn(),
    });

    expect(getFrontendWorkflowEvents).toHaveBeenNthCalledWith(
      1,
      "project-1",
      target.documentId,
      target.workflowRunId,
      { after_source_sequence: 0, limit: 200 },
    );
    expect(getFrontendWorkflowEvents).toHaveBeenNthCalledWith(
      2,
      "project-1",
      target.documentId,
      target.workflowRunId,
      { after_cursor: "cursor-1", limit: 200 },
    );
    expect(getFrontendWorkflowEvents).toHaveBeenNthCalledWith(
      3,
      "project-1",
      target.documentId,
      target.workflowRunId,
      { after_cursor: "cursor-2", limit: 200 },
    );
    expect(onState).toHaveBeenCalledWith(
      target.documentId,
      expect.objectContaining({
        workflow: expect.objectContaining({
          section_lanes: expect.arrayContaining([
            expect.objectContaining({
              items: [expect.objectContaining({ section_id: "source-unit-1" })],
            }),
          ]),
        }),
      }),
    );
    expect(streamFrontendWorkflowEvents).toHaveBeenCalledWith(
      "project-1",
      target.documentId,
      target.workflowRunId,
      { after_cursor: "cursor-2", limit: 200 },
      expect.any(Function),
      expect.any(Function),
    );
  });

  it("opens SSE from after_source_sequence zero when persisted history is empty", async () => {
    const getFrontendWorkflowEvents = vi
      .fn()
      .mockResolvedValueOnce({ data: page([], null) });
    const streamFrontendWorkflowEvents = vi.fn(
      (
        _projectId: string,
        _documentId: string,
        _workflowRunId: string,
        _query: FrontendWorkflowEventsQuery,
        _onMessage: unknown,
        _onError?: unknown,
      ) => vi.fn(),
    );

    await startWorkflowProjectionEventStream({
      projectId: "project-1",
      target,
      api: {
        getFrontendWorkflowEvents,
        streamFrontendWorkflowEvents,
      },
      onState: vi.fn(),
      onError: vi.fn(),
    });

    const streamQuery = streamFrontendWorkflowEvents.mock.calls[0][3] as
      | FrontendWorkflowEventsQuery
      | undefined;

    expect(streamQuery).toEqual({ after_source_sequence: 0, limit: 200 });
    expect(streamQuery).not.toBeUndefined();
  });
});
