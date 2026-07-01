
Pause / Resume Contract

Status: current backend/frontend contract.

Source of truth

Frontend must use:

workflow.actions

from backend live-state.

Do not infer primary pause/resume control from frontend permutations of:

workflow timer mode;
workflow status aliases;
manual_paused strings;
local document status.
Backend actions

Implemented in:

src/interfaces/composition/faq_workbench_workflow_live_state.py::_actions

Contract:

workflow_status == "PAUSED"
  → resume_processing visible=true enabled=true
  → pause_processing visible=false enabled=false

workflow_status in {"FAILED", "CANCELLED", "COMPLETED", "DONE"}
  → pause_processing disabled/hidden
  → resume_processing disabled/hidden

otherwise
  → pause_processing visible=true enabled=true
  → resume_processing visible=false enabled=false

cancel_processing
  → visible=false enabled=false
Frontend rendering rule

Primary processing button:

enabled+visible resume_processing exists
  → show "Продолжить"
  → dispatch resume_processing

else enabled+visible pause_processing exists
  → show "Пауза"
  → dispatch pause_processing

else
  → show no primary processing button
Resume semantics

Resume continues the same workflow. It must not:

create a new upload;
create a new document;
create a new workflow run.

Backend timer/read model uses timeline events:

WorkflowManuallyPaused
WorkflowManuallyResumed

to compute active elapsed time.

Related files

Frontend:

frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx
frontend/src/pages/knowledge/workflow/workflowActions.ts

Backend:

src/interfaces/http/knowledge.py
src/interfaces/composition/faq_workbench_workflow_live_state.py
src/interfaces/composition/knowledge_extraction_workflow_pause_resume.py
src/interfaces/composition/knowledge_extraction_workflow_resume.py
src/contexts/knowledge_workbench/application/sagas/pause_knowledge_extraction_workflow.py
src/contexts/knowledge_workbench/application/sagas/resume_knowledge_extraction_workflow.py
Technical debt
TD-PR-001: frontend had heuristic pause/resume logic

The card previously inferred paused/running state from several frontend strings. That logic should be replaced with action-contract selection only.

TD-PR-002: optimistic UI must be bounded

Optimistic state may flip the button immediately after click, but canonical state must come back from backend workflow.actions.

TD-PR-003: pause/resume deserves reducer/API contract tests

Needed tests:

PAUSED live-state exposes resume action only.
RUNNING live-state exposes pause action only.
terminal live-state exposes neither.
frontend card selector picks resume over pause when resume is enabled.
