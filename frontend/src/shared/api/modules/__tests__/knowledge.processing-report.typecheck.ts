import type { KnowledgeProcessingReport } from '../knowledge';

const reportShape: KnowledgeProcessingReport = {
  document_id: 'doc-1',
  status: 'processing',
  title: 'title',
  message: 'message',
  recoverable: true,
  state: 'answer_resolution_pending',
  state_version: 1,
  state_hash: 'state:doc-1',
  steps: [],
  allowed_actions: [],
  actions: [],
  active_error: null,
  last_error: null,
  recommended_next_action: null,
  diagnostics: {},
  metrics: {},
};

void reportShape;
