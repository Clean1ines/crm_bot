# Knowledge Curation Implementation — 2026-05-18T09:35:00Z

## Backend
- Added curation contracts, issue/action/merge/version DTOs.
- Added curation service with deterministic duplicate grouping and suspicious issue classification.
- Extended repository with curation reads over `knowledge_entries` plus source refs and retrieval-surface presence; status mutation; content edit; merge apply; action list; versions; restore version.
- Added curation router endpoints:
  - `GET /api/projects/{project_id}/knowledge/{document_id}/curation`
  - `POST /api/projects/{project_id}/knowledge/{document_id}/curation/entries/{entry_id}/status`
  - `PATCH /api/projects/{project_id}/knowledge/{document_id}/curation/entries/{entry_id}`
  - `POST /api/projects/{project_id}/knowledge/{document_id}/curation/entries/{entry_id}/embedding/rebuild`
  - `POST /api/projects/{project_id}/knowledge/{document_id}/curation/merge/preview`
  - `POST /api/projects/{project_id}/knowledge/{document_id}/curation/merge/apply`
  - `GET /api/projects/{project_id}/knowledge/{document_id}/curation/actions`
  - `GET /api/projects/{project_id}/knowledge/{document_id}/curation/entries/{entry_id}/versions`
  - `POST /api/projects/{project_id}/knowledge/{document_id}/curation/entries/{entry_id}/versions/{version_id}/restore`

## Frontend
- Added typed curation API module and exported it.
- Added overview, filters, entry cards, edit drawer, merge drawer with preview/apply, version drawer, actions panel, diagnostics drawer.
- Integrated curation/retrieval tabs into current RAG Eval page without removing existing retrieval review console.

## Tests
- Added focused tests for pure service/domain behavior.

## Known non-goals kept out
- No semantic/vector duplicate detection.
- No cross-document reconciliation.
- No heavy reranker/ML dependency.
- No physical delete.
- No raw embedding text exposure in UI.
