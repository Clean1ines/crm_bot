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

import { useMutation } from '@tanstack/react-query';
import { api } from '@shared/api/client';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

export const KnowledgePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchQuery, setSearchQuery] = useState('');
  
  // For now we don't have a list endpoint, but let's keep the UI
  const [documents] = useState<Document[]>([]);
  const [isLoadingList] = useState(false);

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!projectId) throw new Error('Project ID is missing');
      
      const response = await api.knowledge.upload(projectId, file);
      
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData?.detail?.[0]?.msg || errData?.detail || 'Ошибка загрузки');
      }
      
      return await response.json();
    },
    onSuccess: () => {
      toast.success('Документ успешно загружен и отправлен на обработку');
      // queryClient.invalidateQueries({ queryKey: ['knowledge', projectId] });
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

  if (isLoadingList) {
    return <div className="p-8 flex justify-center text-[#6B6B6B]">Загрузка базы знаний...</div>;
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-500">
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileSelect} 
        className="hidden" 
        accept=".pdf,.docx,.txt"
      />
      
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-[#1E1E1E] mb-2">База знаний</h1>
          <p className="text-[#6B6B6B]">Загрузите документы, чтобы обучить своего ИИ-ассистента</p>
        </div>
        <div className="flex gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6B6B6B]" />
            <input 
              type="text"
              placeholder="Поиск документов..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2 bg-white border border-[#E5E2DA] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#B87333]/20 transition-all w-64"
            />
          </div>
        </div>
      </div>

      {/* Upload Zone */}
      <div 
        onClick={triggerUpload}
        className={`border-2 border-dashed rounded-2xl p-12 flex flex-col items-center justify-center bg-white transition-colors cursor-pointer group ${
          uploadMutation.isPending 
            ? 'border-[#B87333] bg-[#B87333]/5 cursor-wait' 
            : 'border-[#E5E2DA] hover:bg-[#F9F8F6]'
        }`}
      >
        <div className={`w-16 h-16 rounded-full flex items-center justify-center mb-4 transition-transform ${
          uploadMutation.isPending ? 'bg-[#B87333]/20 animate-pulse' : 'bg-[#B87333]/10 group-hover:scale-110'
        }`}>
          <Upload className="w-8 h-8 text-[#B87333]" />
        </div>
        <h3 className="text-lg font-semibold text-[#1E1E1E]">
          {uploadMutation.isPending ? 'Загрузка...' : 'Нажмите или перетащите файл'}
        </h3>
        <p className="text-[#6B6B6B] mt-1 text-sm">PDF, DOCX или TXT (до 10MB)</p>
      </div>

      {/* Documents Grid */}
      {documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-20 bg-[#FAF9F6] rounded-2xl border border-[#E5E2DA]">
          <BookOpen className="w-16 h-16 text-[#E5E2DA] mb-4" />
          <h3 className="text-xl font-semibold text-[#1E1E1E]">База знаний пуста</h3>
          <p className="text-[#6B6B6B] mt-2">Загрузите первый документ, чтобы начать обучение</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {documents.map((doc) => (
            <div 
              key={doc.id}
              className="bg-white border border-[#E5E2DA] rounded-2xl p-6 transition-all hover:shadow-lg hover:border-[#B87333]/30 group"
            >
              <div className="flex justify-between items-start mb-4">
                <div className="w-10 h-10 rounded-xl bg-[#F4F1EA] flex items-center justify-center text-[#B87333]">
                  <FileText className="w-5 h-5" />
                </div>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button className="p-2 hover:bg-black/5 rounded-lg transition-colors text-[#6B6B6B]">
                    <Trash2 className="w-4 h-4" />
                  </button>
                  <button className="p-2 hover:bg-black/5 rounded-lg transition-colors text-[#6B6B6B]">
                    <ExternalLink className="w-4 h-4" />
                  </button>
                </div>
              </div>
              
              <h4 className="font-semibold text-[#1E1E1E] mb-1 truncate" title={doc.file_name}>
                {doc.file_name}
              </h4>
              <div className="flex items-center gap-2 text-xs text-[#6B6B6B] mb-4">
                <span>{formatSize(doc.file_size)}</span>
                <span className="w-1 h-1 rounded-full bg-[#D4D4D4]" />
                <span>{doc.chunk_count} фрагментов</span>
              </div>

              <div className="flex items-center justify-between">
                <span className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                  doc.status === 'processed' 
                    ? 'bg-[#E7F6E7] text-[#0D5F0D]' 
                    : 'bg-[#FFF4E5] text-[#B95000]'
                }`}>
                  {doc.status === 'processed' ? 'Обработан' : 'В очереди'}
                </span>
                <span className="text-[10px] text-[#A3A3A3]">
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
