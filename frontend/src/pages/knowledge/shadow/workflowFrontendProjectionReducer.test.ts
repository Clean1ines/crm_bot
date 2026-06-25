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
  it("builds source unit rows from projection events without workflow-live-state snapshot", () => {
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
});
