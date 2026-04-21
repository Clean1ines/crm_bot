import React, { useState } from 'react';
import { User, History, Shield, Trash2, Search, MoreHorizontal, CheckCircle2, XCircle, PlusCircle } from 'lucide-react';
import { Button } from '@shared/ui';
import { useParams } from 'react-router-dom';
import { useProjectManagers } from '@entities/project/api/useCrmData';

export const ManagersPage: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [selectedManager, setSelectedManager] = useState<any>(null);
  
  const { projectId } = useParams<{ projectId: string }>();
  const { data: managers = [], isLoading } = useProjectManagers(projectId);

  const openHistory = (manager: any) => {
    setSelectedManager(manager);
    setIsHistoryOpen(true);
  };

  if (isLoading) {
    return <div className="p-8 flex justify-center text-[#6B6B6B]">Загрузка менеджеров...</div>;
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-500 relative overflow-hidden">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-[#1E1E1E] mb-2">Менеджеры</h1>
          <p className="text-[#6B6B6B]">Сотрудники, получающие уведомления об эскалациях</p>
        </div>
        <div className="flex gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6B6B6B]" />
            <input 
              type="text"
              placeholder="Поиск по имени..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2 bg-white border border-[#E5E2DA] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#B87333]/20 transition-all w-64"
            />
          </div>
          <Button variant="primary" className="flex items-center gap-2">
            <Shield className="w-4 h-4" />
            Добавить
          </Button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-[#E5E2DA] rounded-2xl overflow-hidden shadow-sm">
        <table className="w-full text-left border-collapse">
          <thead className="bg-[#FAF9F6] border-b border-[#E5E2DA]">
            <tr>
              <th className="px-6 py-4 text-xs font-bold text-[#6B6B6B] uppercase tracking-wider">Имя и Username</th>
              <th className="px-6 py-4 text-xs font-bold text-[#6B6B6B] uppercase tracking-wider">Chat ID</th>
              <th className="px-6 py-4 text-xs font-bold text-[#6B6B6B] uppercase tracking-wider">Статус</th>
              <th className="px-6 py-4 text-xs font-bold text-[#6B6B6B] uppercase tracking-wider text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#F4F1EA]">
            {managers.map((chatId: number) => (
              <tr key={chatId} className="hover:bg-[#FAF9F6] transition-colors group">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-[#B87333]/10 flex items-center justify-center text-[#B87333]">
                      <User className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="font-semibold text-[#1E1E1E]">ID: {chatId}</div>
                      <div className="text-xs text-[#6B6B6B]">Зарегистрирован через Telegram</div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm font-mono text-[#6B6B6B]">{chatId}</td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
                    <span className="text-sm text-[#1E1E1E]">Активен</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-right">
                  <div className="flex justify-end gap-2">
                    <button 
                      onClick={() => openHistory({ full_name: `Менеджер ${chatId}`, username: `ID: ${chatId}` })}
                      className="p-2 hover:bg-[#B87333]/10 rounded-lg transition-colors text-[#6B6B6B] hover:text-[#B87333]"
                      title="История ответов"
                    >
                      <History className="w-4 h-4" />
                    </button>
                    <button className="p-2 hover:bg-red-50 rounded-lg transition-colors text-[#6B6B6B] hover:text-red-500">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Slide-over History Log */}
      {isHistoryOpen && (
        <>
          <div 
            className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity" 
            onClick={() => setIsHistoryOpen(false)}
          />
          <div className="fixed top-0 right-0 h-full w-[450px] bg-white z-50 shadow-2xl border-l border-[#E5E2DA] flex flex-col p-8 animate-in slide-in-from-right duration-300">
            <div className="flex justify-between items-center mb-8">
              <h2 className="text-2xl font-bold text-[#1E1E1E]">История ответов</h2>
              <button 
                onClick={() => setIsHistoryOpen(false)}
                className="p-2 hover:bg-gray-100 rounded-full transition-colors"
              >
                <XCircle className="w-6 h-6 text-[#6B6B6B]" />
              </button>
            </div>
            
            <div className="flex items-center gap-4 p-4 bg-[#FAF9F6] rounded-xl mb-8 border border-[#E5E2DA]">
              <div className="w-12 h-12 rounded-full bg-[#B87333]/10 flex items-center justify-center text-[#B87333]">
                <User className="w-6 h-6" />
              </div>
              <div>
                <div className="font-bold text-[#1E1E1E]">{selectedManager?.full_name}</div>
                <div className="text-sm text-[#6B6B6B]">{selectedManager?.username}</div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto space-y-6 pr-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="relative pl-6 border-l-2 border-[#F4F1EA]">
                  <div className="absolute -left-[7px] top-0 w-3 h-3 rounded-full bg-[#B87333]" />
                  <div className="text-xs font-bold text-[#B87333] mb-1">Сегодня, 14:2{i}</div>
                  <div className="bg-[#FAF9F6] p-4 rounded-lg border border-[#E5E2DA]">
                    <div className="text-sm text-[#1E1E1E] mb-2 font-medium">Ответ в треде #{i}54...</div>
                    <div className="text-sm text-[#6B6B6B] italic">"Конечно, мы можем подготовить для вас индивидуальное предложение..."</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
