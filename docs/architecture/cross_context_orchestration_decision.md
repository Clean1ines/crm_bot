# Cross-Context Orchestration Decision

## 0. Purpose

This document decides where the first cross-context orchestration boundary belongs after preparing:

```text
execution_runtime
llm_runtime
artifact_runtime

It prevents the next patch from recreating the old hybrid path where one Workbench queue handler owns:

lease lifecycle
LLM invocation
Groq fallback
split logic
artifact persistence
claim persistence
registry queue marker
stage progress
frontend-readable state
1. Recon conclusion

Current legacy path has a hybrid queue model:

SectionBatchQueueItem

It mixes:

queue lifecycle
lease ownership
attempt counter
Prompt A checkpoint
registry application checkpoint
Workbench stage progress
error marker

Known legacy statuses:

READY
LEASED
CLAIM_OBSERVATIONS_PERSISTED
REGISTRY_APPLICATION_QUEUED
REGISTRY_APPLICATION_APPLIED
WAITING_FOR_FRESH_REGISTRY
SKIPPED
FAILED

These statuses must not become canonical WorkItemStatus.

2. Current old Prompt A persistence path

The old Prompt A service persists several concerns together:

ProcessingNodeRun
ProcessingNodeArtifact input
ProcessingNodeArtifact raw LLM output
ProcessingNodeArtifact parsed output / error output
claim observations
registry snapshot
LLM usage totals
claim observation lifecycle marker
route attempts
Groq key slot
model name
prompt version

This means old ProcessingNodeRun / ProcessingNodeArtifact are useful migration references, but not automatically canonical LlmTask or PipelineArtifact.

Decision:

ProcessingNodeRun may become an adapter/source for LlmTaskAttempt or PipelineArtifact lineage,
but it is not canonical until explicitly mapped.
3. Current old split path

The old queue handler contains oversized-section split logic.

It creates:

child DocumentSection
child SectionBatchQueueItem
parent split metadata
empty claim observations artifact
oversized_section_split raw payload

This old behavior proves that split is not just an LLM error; it is a workflow consequence.

Decision:

Split handling must not live in Groq adapter.
Split handling must not live in LLM Runtime.
Split handling must not live in old queue handler as target architecture.

Target placement is later:

Knowledge Workbench Source Management / Extraction process manager

or a dedicated SourceUnit split policy owned by Knowledge Workbench Source Management.

4. Where cross-context orchestration belongs

The first real vertical slice is not generic pipeline infrastructure.

It is specifically:

Knowledge Workbench Extraction: process one source unit / section through Prompt A claim extraction.

Therefore the first process manager should belong under Knowledge Workbench Extraction, not under llm_runtime, execution_runtime, or artifact_runtime.

Target placement:

src/contexts/knowledge_workbench/extraction/application/process_managers/

Possible name:

process_claim_extraction_work_item.py

or:

run_claim_extraction_work_item.py

Do not create:

src/contexts/llm_runtime/...PromptA...
src/contexts/execution_runtime/...Llm...
src/contexts/artifact_runtime/...Claim...
src/application/services/new_workbench_processor_service.py
5. Why not pipeline_runtime yet

A generic pipeline_runtime may be needed later, but creating it now would be premature.

Current first slice has strong Knowledge Workbench semantics:

source unit / section
Prompt A contract
claim observations
empty claims policy
oversized split
registry downstream marker
reviewable extraction artifact

So the first process manager should be Workbench-owned and depend on generic runtimes by ports.

If later multiple domains need the same orchestration pattern, extract generic pipeline_runtime after the second or third real use case.

6. Required dependency direction

Allowed direction:

knowledge_workbench extraction process manager
→ execution_runtime application ports/use cases
→ llm_runtime application ports/use cases
→ artifact_runtime application ports/use cases

Forbidden direction:

execution_runtime → knowledge_workbench
llm_runtime → knowledge_workbench
artifact_runtime → knowledge_workbench
Groq adapter → knowledge_workbench
old queue handler → new domain internals
7. Cross-context transaction boundary

The first process manager will need a single transaction boundary that can commit:

WorkItem transition
WorkItem event
LlmTask state
LlmAttempt
LLM event
PipelineArtifact raw output
PipelineArtifact parsed output or error artifact
Artifact events
Workbench extraction records / claim observations
Workbench stage/progress marker if still required during migration
Outbox events

Do not implement this as three separate commits.

Target port should be Workbench extraction-owned because the use case is Workbench extraction-owned.

Possible port:

ClaimExtractionWorkItemUnitOfWorkPort

Possible methods:

save_work_item(...)
save_work_item_attempt(...)
save_llm_task(...)
save_llm_attempt(...)
save_artifact(...)
save_claim_observations(...)
append_event(...)
commit()
rollback()

But exact method list must be based on the first test, not guessed too broadly.

8. First vertical slice contract

The first orchestration test should model:

given a leased WorkItem
and a source unit / section payload
and prepared provider input
when Prompt A LLM execution succeeds and validation succeeds
then:
  LlmTask is succeeded
  LlmAttempt is saved
  raw output PipelineArtifact is stored
  parsed output PipelineArtifact is stored
  claim observations are saved or referenced
  WorkItem is completed
  events are appended
  one UnitOfWork commit happens

The test must use fakes and must not touch Postgres.

9. What to postpone

Postpone:

Postgres adapter
new migrations
old queue handler cutover
frontend state changes
Prompt C
registry application cutover
source unit full migration
retention cleanup
real outbox dispatcher

Do not create tables until the first process-manager port/test stabilizes.

10. Immediate next implementation step

Next patch should create only the skeleton for the Workbench extraction context:

src/contexts/knowledge_workbench/extraction/
  __init__.py
  application/
    __init__.py
    process_managers/
      __init__.py
    ports/
      __init__.py

And one failing/green architecture guard that states:

Prompt A cross-context orchestration belongs to knowledge_workbench/extraction.
It must not be implemented in old src/application/services or queue handlers.

No business logic yet.

After that:

add process manager port + first fake-unit-of-work test