# Artifact Runtime Persistence Schema Decision

## 0. Purpose

This document fixes the canonical persistence schema direction for Artifact Runtime before
implementing the Postgres adapter.

The goal is to prevent old artifact/node tables from becoming target architecture by inertia.

Artifact Runtime is a generic checkpoint boundary. It persists pipeline artifacts, their generic
lineage, and transactional outbox events.

## 1. Canonical tables

The canonical Artifact Runtime persistence model is:

```text
pipeline_artifacts
pipeline_artifact_lineage
outbox_events
2. pipeline_artifacts

Proposed fields:

artifact_ref text primary key
artifact_kind text not null
status text not null
visibility text not null
retention_policy_kind text not null
payload jsonb not null
created_at timestamptz not null
updated_at timestamptz not null

Rules:

artifact_ref stores the stable opaque artifact identity.
artifact_kind is caller-owned lowercase dotted identifier.
status stores Artifact Runtime lifecycle status only.
visibility stores generic Artifact Runtime visibility only.
retention_policy_kind stores generic Artifact Runtime retention policy only.
payload is opaque JSON.
Artifact Runtime stores payload, but does not interpret payload business meaning.
Artifact Runtime does not know claim/surface/Groq/Qwen/Prompt A/Prompt C.
Artifact Runtime must not branch on Workbench, retrieval, frontend, provider, model, queue, or prompt semantics.
created_at and updated_at are timezone-aware persistence timestamps.
3. pipeline_artifact_lineage

Proposed fields:

artifact_ref text not null
parent_artifact_ref text not null
primary key (artifact_ref, parent_artifact_ref)

Rules:

lineage is generic.
A child artifact may have zero or more parent artifacts.
Artifact Runtime does not interpret why a parent exists.
Lineage may represent raw-to-parsed derivation, split derivation, validation derivation,
supersession, or any future caller-owned pipeline relationship.
The meaning of the artifact relationship belongs to the caller and artifact kind, not to
Artifact Runtime persistence.
4. outbox_events

outbox_events is the transactional event boundary.

Rules:

Artifact state changes and emitted events must be committed atomically.
The outbox is generic infrastructure for durable event publication.
Artifact Runtime may append Artifact Runtime events.
Event dispatch is outside this schema decision.
5. Explicit non-goals

Artifact Runtime persistence is not responsible for:

claim extraction semantics
surface semantics
Groq semantics
Qwen semantics
Prompt A semantics
Prompt C semantics
LLM routing
provider attempts
work item leasing
queue state
frontend progress state
retrieval quality
embedding state
6. Old tables are not canonical

Old node artifact tables are not canonical.

Old tables may be donor/reference only.

They may be useful for understanding:

previous edge cases;
old UX expectations;
old failure modes;
data that must be migrated before deletion if it exists and matters.

They must not define the new Artifact Runtime target schema.

If DB is empty, do not preserve dirty mapping compatibility.

7. Migration direction

The Postgres implementation should target the canonical table family directly:

pipeline_artifacts
pipeline_artifact_lineage
outbox_events

Do not add compatibility-oriented remapping layers merely to preserve accidental old schema names.

Do not add business columns such as:

claim_id
surface_id
prompt_a_status
prompt_c_status
groq_model
qwen_model
source_unit_id
work_item_id

to pipeline_artifacts.

Those references belong either to caller-owned artifact payload, caller-owned artifact kind,
lineage, or separate bounded-context-owned tables.

8. Decision

Artifact Runtime persistence is a generic checkpoint store.

The canonical persistence contract is:

PipelineArtifact
→ pipeline_artifacts

ArtifactLineage.parent_refs
→ pipeline_artifact_lineage

Artifact Runtime events
→ outbox_events

Everything else belongs outside Artifact Runtime.
