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
  allowed_actions: [
    {
      id: 'resume_knowledge_compilation',
      label: 'Продолжить обработку',
      kind: 'primary',
      enabled: false,
      reason: 'Продолжение обработки будет доступно после подключения resume endpoint.',
      blocker_code: 'resume_endpoint_not_implemented',
    },
  ],
  actions: [],
  active_error: null,
  last_error: null,
  recommended_next_action: null,
  diagnostics: {},
  metrics: {},
};

void reportShape;
