import {
  type KnowledgePreprocessingMode,
  type WorkbenchDocumentCardView,
} from '@shared/api/modules/knowledge';

export type OptimisticKnowledgeDocument = {
  id: string;
  file_name: string;
  file_size: number;
  status: 'processing' | 'error' | string;
  error?: string | null;
  created_at: string;
  updated_at?: string | null;
  preprocessing_mode?: KnowledgePreprocessingMode | string | null;
  current_processing_run_id?: string | null;
  card_view?: WorkbenchDocumentCardView | null;
};

export type UploadKnowledgeVariables = {
  file: File;
  optimisticDocumentId: string;
  optimisticWorkflowRunId: string;
};

export const fileSha256Hex = async (file: File): Promise<string> => {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(hashBuffer))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
};

export const optimisticSourceDocumentRef = (
  projectId: string,
  fileHash: string,
): string => `source-document:${projectId}:${fileHash}`;

export const optimisticWorkflowRunId = (
  sourceDocumentRef: string,
): string => `knowledge-extraction:${sourceDocumentRef}`;

export const createOptimisticUploadDocument = ({
  projectId,
  file,
  preprocessingMode,
  documentId,
  workflowRunId,
}: {
  projectId: string;
  file: File;
  preprocessingMode: KnowledgePreprocessingMode | string;
  documentId: string;
  workflowRunId: string;
}): OptimisticKnowledgeDocument => {
  const now = new Date().toISOString();
  const fileName = file.name || 'Загружаемый документ';

  return {
    id: documentId,
    file_name: fileName,
    file_size: file.size,
    status: 'processing',
    created_at: now,
    updated_at: now,
    preprocessing_mode: preprocessingMode,
    current_processing_run_id: workflowRunId,
    card_view: {
      document_id: documentId,
      project_id: projectId,
      file_name: fileName,
      source_type: 'source_ingestion',
      lifecycle_state: 'processing',
      retention_state: 'retained',
      transient_purged: false,
      resume_available: false,
      status_i18n_key: 'knowledge.workbench.status.processing',
      default_status_label: 'Загружаем и режем документ',
      status_description_i18n_key: 'knowledge.workbench.description.sourceIngestion',
      default_status_description:
        'Документ принят на фронте. Строки разделов появятся по событиям обработки.',
      timer: {
        mode: 'running',
        active_elapsed_seconds: 0,
        wall_elapsed_seconds: 0,
        current_active_started_at: now,
        i18n_key: 'knowledge.workbench.timer.running',
        default_label: 'идёт обработка',
      },
      usage: {
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
        llm_call_count: 0,
      },
      sections: {
        total: 0,
        processed: 0,
        failed: 0,
        pending: 0,
      },
      registry: {
        entry_count: 0,
        final_snapshot_id: null,
        retained: true,
      },
      surfaces: {
        draft_count: 0,
        ready_count: 0,
        published_count: 0,
        rejected_count: 0,
      },
      runtime: {
        publication_id: null,
        runtime_entry_count: 0,
      },
      recovery: {
        mode: 'none',
        scheduled_at: null,
        can_cancel_scheduled_resume: false,
        reason_code: 'none',
        i18n_key: 'knowledge.workbench.recovery.none',
        default_message: 'Автовосстановление не требуется',
      },
      actions: [
        {
          action_id: 'cancel_processing',
          visible: true,
          enabled: true,
          tone: 'warning',
          i18n_key: 'knowledge.actions.stop',
          default_label: 'Остановить',
        },
      ],
      messages: [
        {
          code: 'upload_started',
          severity: 'info',
          i18n_key: 'knowledge.upload.started',
          default_message: 'Документ загружается. Карточка обновляется событиями.',
        },
      ],
      error: null,
      metadata: {
        optimistic_upload: true,
      },
    },
  };
};
