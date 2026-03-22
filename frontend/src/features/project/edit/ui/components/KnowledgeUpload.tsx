import React, { useState } from 'react';
import { useNotification } from '@/shared/lib/notification/useNotifications';
import { api } from '@shared/api/client';

export const KnowledgeUpload: React.FC<{ projectId: string }> = ({ projectId }) => {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const { showNotification } = useNotification();

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const response = await api.knowledge.upload(projectId, file);
      if (!response.ok) {
        const error = await response.text();
        throw new Error(error);
      }
      showNotification('Файл загружен', 'success');
      setFile(null);
    } catch (err) {
      showNotification('Ошибка загрузки', 'error');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-2">
      <input
        type="file"
        accept=".txt,.pdf"
        onChange={e => setFile(e.target.files?.[0] || null)}
      />
      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
      >
        {uploading ? 'Загрузка...' : 'Загрузить'}
      </button>
    </div>
  );
};