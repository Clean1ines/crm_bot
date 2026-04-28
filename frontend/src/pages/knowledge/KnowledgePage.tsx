import React, { useState } from 'react';
import { BookOpen, Upload, FileText, Trash2, Search, ExternalLink } from 'lucide-react';

interface Document {
  id: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processed' | 'error';
  chunk_count: number;
  created_at: string;
}

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { knowledgeApi } from '@shared/api/modules/knowledge';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

export const KnowledgePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');

  // For now we don't have a list endpoint, but let's keep the UI
  const documentsQuery = useQuery({
    queryKey: ['knowledge-documents', projectId],
    queryFn: async () => {
      if (!projectId) return [];
      const { data } = await knowledgeApi.list(projectId);

      const payload = data && typeof data === 'object' ? data as Record<string, unknown> : {};
      const list = Array.isArray(payload.documents)
        ? payload.documents
        : Array.isArray(payload.items)
          ? payload.items
          : [];

      return list as Document[];
    },
    enabled: !!projectId,
  });

  const documents = Array.isArray(documentsQuery.data) ? documentsQuery.data : [];

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!projectId) throw new Error('Project ID is missing');

      const response = await knowledgeApi.upload(projectId, file);

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData?.detail?.[0]?.msg || errData?.detail || 'Ошибка загрузки');
      }

      return await response.json();
    },
    onSuccess: async () => {
      toast.success('Документ успешно загружен и отправлен на обработку');
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : 'Ошибка при загрузке документа';
      toast.error(message);
    }
  });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  const triggerUpload = () => {
    fileInputRef.current?.click();
  };

  if (documentsQuery.isLoading) {
    return <div className="p-8 flex justify-center text-[var(--text-muted)]">Загрузка базы знаний...</div>;
  }


  const handleDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const handleDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();

    const file = event.dataTransfer.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };


  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        className="hidden"
        accept=".pdf,.docx,.txt"
      />

      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[var(--text-primary)] mb-2">База знаний</h1>
          <p className="text-[var(--text-muted)]">Загрузите документы, чтобы обучить своего ИИ-ассистента</p>
        </div>
        <div className="flex w-full flex-col gap-3 sm:flex-row lg:w-auto">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
            <input
              type="text"
              placeholder="Поиск документов..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-[var(--surface-card)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25 transition-all lg:w-64"
            />
          </div>
        </div>
      </div>

      {/* Upload Zone */}
      <div
        onClick={triggerUpload}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={`rounded-2xl shadow-sm p-6 sm:p-8 lg:p-12 flex flex-col items-center justify-center bg-[var(--surface-card)] transition-colors cursor-pointer group ${
          uploadMutation.isPending
            ? 'border-[var(--accent-primary)] bg-[var(--accent-primary)]/5 cursor-wait'
            : 'border-[var(--border-subtle)] hover:bg-[var(--surface-secondary)]'
        }`}
      >
        <div className={`w-14 h-14 sm:w-16 sm:h-16 rounded-full flex items-center justify-center mb-4 transition-transform ${
          uploadMutation.isPending ? 'bg-[var(--accent-primary)]/20 animate-pulse' : 'bg-[var(--accent-primary)]/10 group-hover:scale-110'
        }`}>
          <Upload className="w-7 h-7 sm:w-8 sm:h-8 text-[var(--accent-primary)]" />
        </div>
        <h3 className="text-center text-base font-semibold text-[var(--text-primary)] sm:text-lg">
          {uploadMutation.isPending ? 'Загрузка...' : 'Нажмите или перетащите файл'}
        </h3>
        <p className="mt-1 text-center text-sm text-[var(--text-muted)]">PDF, DOCX или TXT (до 10MB)</p>
      </div>

      {/* Documents Grid */}
      {documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl bg-[var(--surface-secondary)] p-8 text-center sm:p-12 lg:p-20">
          <BookOpen className="mb-4 h-12 w-12 text-[var(--border-subtle)] sm:h-16 sm:w-16" />
          <h3 className="text-lg font-semibold text-[var(--text-primary)] sm:text-xl">База знаний пуста</h3>
          <p className="text-[var(--text-muted)] mt-2">Загрузите первый документ, чтобы начать обучение</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 lg:gap-6">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="bg-[var(--surface-elevated)] rounded-2xl p-4 sm:p-6 transition-all hover:shadow-lg hover:shadow-md group"
            >
              <div className="flex justify-between items-start mb-4">
                <div className="w-10 h-10 rounded-xl bg-[var(--surface-secondary)] flex items-center justify-center text-[var(--accent-primary)]">
                  <FileText className="w-5 h-5" />
                </div>
                <div className="flex gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
                  <button className="p-2 hover:bg-[var(--surface-secondary)] rounded-lg transition-colors text-[var(--text-muted)]">
                    <Trash2 className="w-4 h-4" />
                  </button>
                  <button className="p-2 hover:bg-[var(--surface-secondary)] rounded-lg transition-colors text-[var(--text-muted)]">
                    <ExternalLink className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <h4 className="font-semibold text-[var(--text-primary)] mb-1 truncate" title={doc.file_name}>
                {doc.file_name}
              </h4>
              <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
                <span>{formatSize(doc.file_size)}</span>
                <span className="w-1 h-1 rounded-full bg-[var(--border-subtle)]" />
                <span>{doc.chunk_count} фрагментов</span>
              </div>

              <div className="flex items-center justify-between">
                <span className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                  doc.status === 'processed'
                    ? 'bg-[var(--accent-success-bg)] text-[var(--accent-success-text)]'
                    : 'bg-[var(--accent-warning-bg)] text-[var(--accent-warning)]'
                }`}>
                  {doc.status === 'processed' ? 'Обработан' : 'В очереди'}
                </span>
                <span className="text-[10px] text-[var(--text-muted)]">
                  {new Date(doc.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
