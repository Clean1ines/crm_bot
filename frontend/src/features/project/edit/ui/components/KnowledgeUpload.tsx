import React, { useState } from 'react';
import { useNotification } from '@/shared/lib/notification/useNotifications';
import { getErrorMessage } from '@shared/api/core/errors';
import { translate } from '@shared/i18n';
import {
  KNOWLEDGE_PREPROCESSING_MODE_OPTIONS,
  knowledgeApi,
  type KnowledgePreprocessingMode,
} from '@shared/api/modules/knowledge';

export const KnowledgeUpload: React.FC<{ projectId: string }> = ({ projectId }) => {
  const [preprocessingMode, setPreprocessingMode] = useState<KnowledgePreprocessingMode>('faq');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const { showNotification } = useNotification();

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const response = await knowledgeApi.upload(projectId, file, preprocessingMode);
      if (!response.ok) {
        const errorText = await response.text();
        let errorPayload: unknown = errorText;
        try {
          errorPayload = JSON.parse(errorText) as unknown;
        } catch {
          errorPayload = errorText;
        }
        throw new Error(getErrorMessage(errorPayload, translate('knowledge.upload.failure')));
      }
      showNotification(translate('knowledge.upload.success'), 'success');
      setFile(null);
    } catch (error) {
      showNotification(getErrorMessage(error, translate('knowledge.upload.failure')), 'error');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-3">
      <label style={{ display: 'grid', gap: 6, marginBottom: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          {translate('knowledge.upload.preprocessingMode')}
        </span>
        <select
          value={preprocessingMode}
          onChange={(event) => setPreprocessingMode(event.target.value as KnowledgePreprocessingMode)}
        >
          {KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <span style={{ fontSize: 12, opacity: 0.75 }}>
          {KNOWLEDGE_PREPROCESSING_MODE_OPTIONS.find((option) => option.value === preprocessingMode)?.description}
        </span>
      </label>

      <input
        type="file"
        accept=".txt,.pdf"
        onChange={e => setFile(e.target.files?.[0] || null)}
        className="block w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] file:mr-3 file:rounded-md file:border-0 file:bg-[var(--surface-secondary)] file:px-3 file:py-1.5 file:text-sm file:text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
      />
      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className="min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:opacity-50"
      >
        {uploading ? translate('knowledge.upload.uploading') : translate('knowledge.upload.submit')}
      </button>
    </div>
  );
};