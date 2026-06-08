# Artifact Runtime Context

## Назначение

`artifact_runtime` — generic persistence runtime для промежуточных и финальных результатов pipeline/workflow.

Ему безразлично, что именно сохраняется:

- Prompt A claim observations;
- Prompt C consolidated surfaces;
- raw LLM output;
- validation errors;
- dialog memory snapshot;
- retrieval trace;
- cluster draft;
- tool result.

Этот context отвечает за artifacts, artifact kind, lineage, parent/child links, stage checkpoints, retention policy, resume policy, temporary vs durable results.

## Owns

Canonical concepts:

- `PipelineArtifact`;
- `ArtifactKind`;
- `ArtifactRef`;
- `ArtifactLineage`;
- `RetentionPolicy`;
- `ArtifactVisibility`;
- `ArtifactStatus`;
- `StageCheckpoint`;
- `ResumePolicy`.

Use cases that belong here:

- `PersistArtifact`;
- `SupersedeArtifact`;
- `LoadArtifactsForResume`;
- `ApplyRetentionPolicy`.

Domain events that belong here:

- `ArtifactPersisted`;
- `ArtifactSuperseded`;
- `ArtifactRejected`;
- `ArtifactPublished`;
- `ArtifactExpired`.

## Does not own

This context does not own:

- semantic meaning of claim;
- retrieval quality;
- business answer correctness;
- LLM model selection;
- work item leasing;
- frontend display policy;
- Workbench-specific surface review decisions.

## Critical rule

Artifact existence is the checkpoint.

Queue status is not the artifact.

Old statuses such as:

- `CLAIM_OBSERVATIONS_PERSISTED`;
- `REGISTRY_APPLICATION_QUEUED`;
- `REGISTRY_APPLICATION_APPLIED`;

are legacy status/checkpoint hybrids and must not become canonical artifact runtime statuses.

## Legacy / adapter warnings

`NodeRun` may be an artifact/attempt source, but it is not canonical `PipelineArtifact` unless explicitly redefined during migration.

Any old table that stores raw LLM output, parsed payload, route attempts, or node execution result must be classified as one of:

- canonical artifact storage;
- artifact source adapter;
- legacy;
- retired.

## Placement rules

New canonical artifact runtime code goes here.

Do not add new generic dumping-ground files named:

- `service.py`;
- `services.py`;
- `repository.py`;
- `dto.py`.

Use explicit names such as:

- `domain/entities/pipeline_artifact.py`;
- `domain/value_objects/artifact_kind.py`;
- `domain/value_objects/retention_policy.py`;
- `application/use_cases/persist_artifact.py`;
- `application/ports/artifact_repository.py`;
- `infrastructure/postgres/postgres_artifact_repository.py`.
