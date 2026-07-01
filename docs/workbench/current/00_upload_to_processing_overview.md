# Workbench Upload → Document Processing Overview

Status: current architecture snapshot.
Scope: backend upload, source ingestion, workflow drain, frontend projection, document card live-state.
Branch context: rescue/0d59-projection-cutover.

## Current vertical

Current document processing vertical:

```text
HTTP upload
→ source ingestion first phase
→ source document + source units persisted
→ knowledge extraction workflow run
→ workflow command drain
→ execution work items
→ claim builder LLM attempts
→ draft claim observations
→ frontend workflow events
→ frontend reducer
→ KnowledgeDocumentCard live UI

The current API boundary is src/interfaces/http/knowledge.py.

The module docstring says this router owns the current:

upload -> source ingestion -> workflow command drain

vertical. The old queue-based FAQ Workbench document upload is retired.

Upload endpoint

Backend endpoint:

POST /api/projects/{project_id}/knowledge

Implementation:

src/interfaces/http/knowledge.py::upload_knowledge

Responsibilities:

Validate uploaded file name and extension.
Read upload bytes with size limit.
Require Workbench FAQ preprocessing mode.
Decode upload as UTF-8 text.
Build source ingestion actor from auth context.
Resolve source format from upload file name.
Create workflow runner with make_knowledge_extraction_workflow_after_upload.
Execute RunKnowledgeExtractionWorkflowAfterUploadCommand.
Return workflow/document metadata for frontend.

Response shape currently includes:

{
  "status": "knowledge_extraction_workflow_started",
  "workflow_run_id": "...",
  "source_ingestion_completed": true,
  "drained_inspected_count": 0,
  "drained_dispatched_count": 0,
  "blocked_command_type": null,
  "blocked_reason": null,
  "source_document_ref": "...",
  "source_unit_count": 0,
  "source_units_url": "/api/projects/{project_id}/knowledge/source-documents/{source_document_ref}/source-units",
  "draft_claims_url": "/api/projects/{project_id}/knowledge/source-documents/{source_document_ref}/draft-claims"
}
Source units endpoint

Backend endpoint:

GET /api/projects/{project_id}/knowledge/source-documents/{source_document_ref}/source-units

Implementation:

src/interfaces/http/knowledge.py::source_ingestion_source_units

Returns persisted source units for the uploaded source document.

Each source unit read model includes:

{
  "source_unit_ref": "...",
  "ordinal": 0,
  "unit_kind": "...",
  "heading_path": [],
  "text_preview": "...",
  "text_length": 0,
  "created_at": "..."
}
Frontend workflow event endpoints

Backend endpoints:

GET /api/projects/{project_id}/knowledge/source-documents/{document_id}/workflows/{workflow_run_id}/frontend-events

GET /api/projects/{project_id}/knowledge/source-documents/{document_id}/workflows/{workflow_run_id}/frontend-events/stream

Implementations:

src/interfaces/http/knowledge.py::list_knowledge_frontend_workflow_events
src/interfaces/http/knowledge.py::stream_knowledge_frontend_workflow_events

The list endpoint returns persisted projection-only workflow events.

The stream endpoint:

Replays persisted frontend events from cursor.
Subscribes to Redis frontend workflow event bus.
Emits SSE messages with event: frontend_workflow_event.
Frontend optimistic upload

Frontend file:

frontend/src/pages/knowledge/optimisticUpload.ts

Current purpose:

create optimistic document id / workflow run id;
show a document card immediately after local upload starts;
seed initial workflow live-state through createInitialWorkflowLiveStateResponse;
let projection events later converge with real backend state.

Recent commit:

64d7412b Restore optimistic knowledge upload projection
Frontend document card

Main shell:

frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx

The document card currently combines too many responsibilities:

document shell/header/actions;
source ingestion progress;
claim builder section rows;
attempts;
draft claim artifacts;
embedding/clustering/compaction summary;
curation/publication controls;
legacy fallback fragments/draft paths.

This is the main frontend cleanup target.

Immediate documentation gaps

These docs intentionally start by fixing the current map. They do not yet fully document:

every workflow command type;
every projector;
every migration/table;
every reducer event case;
every curation/publication endpoint.

Those should be added as follow-up docs after Claim Builder module extraction.
