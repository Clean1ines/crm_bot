# ADR-0002: RetrievalSurface as the production knowledge retrieval contract

**Date**: 2026-05-24
**Status**: accepted
**Deciders**: _neverjune_, Codex

## Context

The product operates a knowledge compilation pipeline and customer-facing assistant runtime.
Historically, teams often overload intermediate entities (chunks, preprocessing outputs, embedding text) as if they were production knowledge.
That causes inconsistency between curation state, evaluation, and runtime retrieval behavior.

`crm_bot` domain vocabulary distinguishes source evidence, canonical entries, enrichment, embeddings, and retrieval exposure.
We need an explicit contract that production retrieval uses a dedicated surface and that published knowledge is always evidence-grounded.

## Decision

Adopt the following production contract:

1. `RetrievalSurface` is the sole production retrieval contract for assistant runtime.
2. `CanonicalKnowledgeEntry` is publishable knowledge only when grounded in source evidence.
3. `SourceDocument -> SourceChunk -> SourceRef -> CompilerRun -> AnswerCandidate -> CandidateCluster -> CanonicalKnowledgeEntry -> KnowledgeEnrichment -> EmbeddingText -> EmbeddingVector -> RetrievalSurface` is the canonical compilation path.
4. `chunk` alone is not a sufficient production concept.
5. `preprocessing_mode` is a compiler selector, not a production entry kind.
6. `EvalCase`/`RagEval` are evaluation artifacts, not production knowledge.
7. `KnowledgeEnrichment` is non-authoritative and must not be treated as primary truth.
8. RAG evaluation must verify production `RetrievalSurface`, not only staging/intermediate stores.

## Alternatives Considered

### Alternative 1: Runtime retrieval directly from raw chunks

- **Pros**: Minimal pipeline overhead.
- **Cons**: Weak curation control, weaker provenance guarantees, high answer volatility.
- **Why not**: Incompatible with review/publish lifecycle and evidence accountability.

### Alternative 2: Runtime retrieval directly from embedding text snapshots

- **Pros**: Simple retrieval implementation.
- **Cons**: Confuses representation with authoritative knowledge; brittle when representation format changes.
- **Why not**: EmbeddingText is a derivative artifact, not user-facing source of truth.

## Consequences

### Positive

- Clear separation of authoritative knowledge vs derived artifacts.
- Better auditability and explainability of answers.
- Better alignment between curation actions and production runtime behavior.

### Negative

- More entities to manage and validate.
- Requires stronger migration discipline when retrieval schema evolves.

### Risks

- Partial migrations can desynchronize retrieval surface from canonical entries.
- If eval bypasses retrieval surface, quality signals become misleading.
