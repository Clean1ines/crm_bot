import React, { useState } from 'react';
import { useNotification } from '@/shared/lib/notification/useNotifications';
import { knowledgeApi } from '@shared/api/modules/knowledge';

export const KnowledgeUpload: React.FC<{ projectId: string }> = ({ projectId }) => {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const { showNotification } = useNotification();

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const response = await knowledgeApi.upload(projectId, file);
      if (!response.ok) {
        const error = await response.text();
        throw new Error(error);
      }
      showNotification('Файл загружен', 'success');
      setFile(null);
    } catch {
      showNotification('Ошибка загрузки', 'error');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-3">
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
        {uploading ? 'Загрузка...' : 'Загрузить'}
      </button>
    </div>
  );
};