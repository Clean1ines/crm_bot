import { describe, expect, it } from "vitest";

import type { FrontendWorkflowEventEnvelope } from "@shared/api/modules/knowledge";

import {
  createInitialWorkflowLiveStateResponse,
  reduceWorkflowFrontendProjectionEvent,
} from "./workflowFrontendProjectionReducer";

const baseEvent = (
  projectionType: string,
  payload: Record<string, unknown>,
  sequence: number,
): FrontendWorkflowEventEnvelope => ({
  projection_event_id: `projection-${sequence}`,
  source_event_id: `source-${sequence}`,
  source_sequence_number: sequence,
  projection_version: 1,
  projection_type: projectionType,
  event_type: projectionType,
  operation_key: null,
  canonical_phase: "claim_builder_section_extraction",
  workflow_run_id: "knowledge-extraction:source-document:project-1:doc-1",
  project_id: "project-1",
  document_id: "source-document:project-1:doc-1",
  payload,
  occurred_at: `2026-06-25T12:0${sequence}:00.000Z`,
  causation_command_id: null,
  correlation_id: null,
});

describe("workflowFrontendProjectionReducer", () => {
  it("builds source unit rows from projection events without snapshot hydration", () => {
    let state = createInitialWorkflowLiveStateResponse({
      documentId: "source-document:project-1:doc-1",
      projectId: "project-1",
      fileName: "doc.md",
      documentStatus: "processing",
      workflowRunId: "knowledge-extraction:source-document:project-1:doc-1",
    });

    state = reduceWorkflowFrontendProjectionEvent(
      state,
      baseEvent(
        "workflow_source_units_created",
        {
          source_document_ref: "source-document:project-1:doc-1",
          source_unit_count: 2,
        },
        1,
      ),
    );

    state = reduceWorkflowFrontendProjectionEvent(
      state,
      baseEvent(
        "workflow_source_unit_created",
        {
          source_document_ref: "source-document:project-1:doc-1",
          source_unit_ref: "source-unit-1",
          source_unit_ordinal: 0,
          unit_kind: "markdown",
          heading_path: ["Intro"],
        },
        2,
      ),
    );

    expect(state.workflow.stages.find((item) => item.id === "source_ingestion")?.status).toBe(
      "completed",
    );
    expect(state.workflow.section_lanes[0].items).toHaveLength(1);
    expect(state.workflow.section_lanes[0].items[0].status).toBe("ready");
  });

  it("updates one section and one LLM attempt from dispatch and outcome events", () => {
    let state = createInitialWorkflowLiveStateResponse({
      documentId: "source-document:project-1:doc-1",
      projectId: "project-1",
      fileName: "doc.md",
      documentStatus: "processing",
      workflowRunId: "knowledge-extraction:source-document:project-1:doc-1",
    });

    state = reduceWorkflowFrontendProjectionEvent(
      state,
      baseEvent(
        "workflow_claim_builder_work_item_scheduled",
        {
          workflow_run_id: "knowledge-extraction:source-document:project-1:doc-1",
          source_document_ref: "source-document:project-1:doc-1",
          source_unit_ref: "source-unit-1",
          source_unit_ordinal: 0,
          work_item_id: "work-item-1",
          work_kind: "claim_builder",
          initial_work_item_state: "ready",
          attempt_count: 0,
          schedule_status: "ready",
          retry_eligibility: "eligible",
        },
        1,
      ),
    );

    state = reduceWorkflowFrontendProjectionEvent(
      state,
      baseEvent(
        "workflow_claim_builder_dispatch_attempt_prepared",
        {
          workflow_run_id: "knowledge-extraction:source-document:project-1:doc-1",
          source_document_ref: "source-document:project-1:doc-1",
          source_unit_ref: "source-unit-1",
          work_item_id: "work-item-1",
          work_kind: "claim_builder",
          dispatch_attempt_id: "attempt-1",
          attempt_number: 1,
          attempt_state: "leased",
          provider: "groq",
          account_ref: "account-1",
          model_ref: "llama-test",
        },
        2,
      ),
    );

    state = reduceWorkflowFrontendProjectionEvent(
      state,
      baseEvent(
        "workflow_claim_builder_section_extracted",
        {
          workflow_run_id: "knowledge-extraction:source-document:project-1:doc-1",
          source_document_ref: "source-document:project-1:doc-1",
          source_unit_ref: "source-unit-1",
          work_item_id: "work-item-1",
          dispatch_attempt_id: "attempt-1",
          persisted_draft_claim_count: 3,
          actual_prompt_tokens: 10,
          actual_completion_tokens: 20,
          actual_total_tokens: 30,
        },
        3,
      ),
    );

    expect(state.workflow.section_lanes[0].items[0].status).toBe("completed");
    expect(state.workflow.llm_attempts[0].status).toBe("completed");
    expect(state.workflow.llm_attempts[0].model_name).toBe("llama-test");
    expect(state.workflow.usage.total_tokens).toBe(30);
  });

  const seed = () =>
    createInitialWorkflowLiveStateResponse({
      documentId: "source-document:project-1:doc-1",
      projectId: "project-1",
      fileName: "doc.md",
      documentStatus: "processing",
      workflowRunId: "knowledge-extraction:source-document:project-1:doc-1",
    });

  it("applies manual pause as the event that stops timer and exposes resume", () => {
    const next = reduceWorkflowFrontendProjectionEvent(
      seed(),
      baseEvent("workflow_manually_paused", { pause_reason: "manual_stop" }, 4),
    );

    expect(next.document_status).toBe("paused");
    expect(next.workflow.workflow_status).toBe("paused");
    expect(next.workflow.timer.mode).toBe("paused");
    expect(next.workflow.timer.current_active_started_at).toBeNull();
    expect(next.workflow.timer.is_live).toBe(false);
    expect(next.workflow.actions.find((item) => item.action_id === "pause_processing")).toMatchObject({
      visible: false,
      enabled: false,
    });
    expect(next.workflow.actions.find((item) => item.action_id === "resume_processing")).toMatchObject({
      visible: true,
      enabled: true,
    });
  });

  it("keeps workflow paused when late claim builder outcome arrives", () => {
    const paused = reduceWorkflowFrontendProjectionEvent(
      seed(),
      baseEvent("workflow_manually_paused", { pause_reason: "manual_stop" }, 4),
    );

    const next = reduceWorkflowFrontendProjectionEvent(
      paused,
      baseEvent(
        "workflow_claim_builder_section_extracted",
        {
          workflow_run_id: "knowledge-extraction:source-document:project-1:doc-1",
          source_document_ref: "source-document:project-1:doc-1",
          source_unit_ref: "source-unit-1",
          work_item_id: "work-item-1",
          dispatch_attempt_id: "attempt-1",
          persisted_draft_claim_count: 3,
        },
        4,
      ),
    );

    expect(next.workflow.workflow_status).toBe("paused");
    expect(next.workflow.timer.mode).toBe("paused");
    expect(next.workflow.timer.current_active_started_at).toBeNull();
    expect(next.workflow.timer.is_live).toBe(false);
    expect(next.workflow.actions.find((item) => item.action_id === "pause_processing")).toMatchObject({
      visible: false,
      enabled: false,
    });
    expect(next.workflow.actions.find((item) => item.action_id === "resume_processing")).toMatchObject({
      visible: true,
      enabled: true,
    });
  });

  it("keeps workflow paused when late capacity and attempt events arrive", () => {
    let state = reduceWorkflowFrontendProjectionEvent(
      seed(),
      baseEvent("workflow_manually_paused", { pause_reason: "manual_stop" }, 4),
    );

    for (const projectionType of [
      "workflow_capacity_window_observed",
      "workflow_capacity_window_exhausted",
      "workflow_capacity_window_scheduled_wakeup",
      "workflow_capacity_window_leased_work_item",
      "workflow_capacity_window_waiting_due_work",
      "workflow_capacity_window_admission_skipped",
      "workflow_claim_builder_dispatch_attempt_prepared",
      "workflow_dispatch_batch_prepared",
    ]) {
      state = reduceWorkflowFrontendProjectionEvent(
        state,
        baseEvent(
          projectionType,
          {
            source_document_ref: "source-document:project-1:doc-1",
            source_unit_ref: "source-unit-1",
            work_item_id: "work-item-1",
            dispatch_attempt_id: "attempt-1",
            source_unit_refs: ["source-unit-1"],
            work_item_ids: ["work-item-1"],
          },
          5,
        ),
      );
    }

    expect(state.document_status).toBe("paused");
    expect(state.workflow.workflow_status).toBe("paused");
    expect(state.workflow.timer.mode).toBe("paused");
    expect(state.workflow.timer.is_live).toBe(false);
  });

  it("resumes timer and running actions only on manual resume event", () => {
    const paused = reduceWorkflowFrontendProjectionEvent(
      seed(),
      baseEvent("workflow_manually_paused", { pause_reason: "manual_stop" }, 4),
    );

    const resumed = reduceWorkflowFrontendProjectionEvent(
      paused,
      baseEvent("workflow_manually_resumed", {}, 5),
    );

    expect(resumed.document_status).toBe("processing");
    expect(resumed.workflow.workflow_status).toBe("running");
    expect(resumed.workflow.timer.mode).toBe("running");
    expect(resumed.workflow.timer.is_live).toBe(true);
    expect(resumed.workflow.timer.current_active_started_at).toBe("2026-06-25T12:05:00.000Z");
    expect(resumed.workflow.actions.find((item) => item.action_id === "pause_processing")).toMatchObject({
      visible: true,
      enabled: true,
    });
    expect(resumed.workflow.actions.find((item) => item.action_id === "resume_processing")).toMatchObject({
      visible: false,
      enabled: false,
    });
  });

  it("renders eight claim-builder rows and keeps row count stable when events replay", () => {
    let state = seed();
    const events: FrontendWorkflowEventEnvelope[] = [];

    for (let index = 0; index < 8; index += 1) {
      events.push(
        baseEvent(
          "workflow_source_unit_created",
          {
            source_document_ref: "source-document:project-1:doc-1",
            source_unit_ref: `source-unit-${index}`,
            source_unit_ordinal: index,
            source_unit_title: `Title ${index}`,
          },
          index + 1,
        ),
        baseEvent(
          "workflow_claim_builder_work_item_scheduled",
          {
            source_document_ref: "source-document:project-1:doc-1",
            source_unit_ref: `source-unit-${index}`,
            source_unit_ordinal: index,
            work_item_id: `work-item-${index}`,
            schedule_status: "ready",
          },
          index + 10,
        ),
      );
    }

    for (const event of events) {
      state = reduceWorkflowFrontendProjectionEvent(state, event);
    }
    for (const event of events) {
      state = reduceWorkflowFrontendProjectionEvent(state, event);
    }

    expect(state.workflow.section_lanes[0].items).toHaveLength(8);
    expect(state.workflow.section_lanes[0].items.map((item) => item.section_id)).toEqual(
      Array.from({ length: 8 }, (_, index) => `source-unit-${index}`),
    );
  });
});
