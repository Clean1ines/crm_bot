import React, { useState } from 'react';
import { Users, Search, MessageSquare, Calendar, MoreVertical, ExternalLink, Filter } from 'lucide-react';
import { Button } from '@shared/ui';
import { useNavigate, useParams } from 'react-router-dom';
import { useProjectClients } from '@entities/project/api/useCrmData';

export const ClientsPage: React.FC = () => {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const [searchQuery, setSearchQuery] = useState('');

  const { data: clients = [], isLoading } = useProjectClients(projectId, searchQuery);

  const goToDialogs = (clientId: string | any) => {
    navigate(`/projects/${projectId}/dialogs?client_id=${clientId}`);
  };

  if (isLoading) {
    return <div className="p-8 flex justify-center text-[#6B6B6B]">Загрузка клиентов...</div>;
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-[#1E1E1E] mb-2">Клиенты</h1>
          <p className="text-[#6B6B6B]">Все пользователи, взаимодействовавшие с вашим ботом</p>
        </div>
        <div className="flex gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6B6B6B]" />
            <input 
              type="text"
              placeholder="Поиск по имени или username..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2 bg-white border border-[#E5E2DA] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#B87333]/20 transition-all w-72"
            />
          </div>
          <Button variant="secondary" className="flex items-center gap-2">
            <Filter className="w-4 h-4" />
            Фильтры
          </Button>
        </div>
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-[#FAF9F6] border border-[#E5E2DA] p-6 rounded-2xl">
          <div className="text-sm text-[#6B6B6B] mb-1">Всего клиентов</div>
          <div className="text-3xl font-bold text-[#1E1E1E]">1,284</div>
        </div>
        <div className="bg-[#FAF9F6] border border-[#E5E2DA] p-6 rounded-2xl">
          <div className="text-sm text-[#6B6B6B] mb-1">Новых (7 дней)</div>
          <div className="text-3xl font-bold text-[#B87333]">+42</div>
        </div>
        <div className="bg-[#FAF9F6] border border-[#E5E2DA] p-6 rounded-2xl">
          <div className="text-sm text-[#6B6B6B] mb-1">Активных диалогов</div>
          <div className="text-3xl font-bold text-[#1E1E1E]">12</div>
        </div>
      </div>

      {/* Clients List */}
      <div className="bg-white border border-[#E5E2DA] rounded-2xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead className="bg-[#FAF9F6] border-b border-[#E5E2DA]">
              <tr>
                <th className="px-6 py-4 text-xs font-bold text-[#6B6B6B] uppercase tracking-wider">Клиент</th>
                <th className="px-6 py-4 text-xs font-bold text-[#6B6B6B] uppercase tracking-wider">Дата регистрации</th>
                <th className="px-6 py-4 text-xs font-bold text-[#6B6B6B] uppercase tracking-wider">Последняя активность</th>
                <th className="px-6 py-4 text-xs font-bold text-[#6B6B6B] uppercase tracking-wider text-right">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F4F1EA]">
              {clients.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-10 text-center text-[#6B6B6B]">
                    Клиенты не найдены
                  </td>
                </tr>
              ) : (
                clients.map((thread: any) => {
                  const client = thread.client || {};
                  const fullName = client.full_name || client.first_name || 'Без имени';
                  const username = client.username ? `@${client.username}` : 'Нет username';
                  const initials = fullName.split(' ').map((n: string) => n[0]).join('').slice(0, 2);
                  
                  return (
                    <tr key={thread.thread_id} className="hover:bg-[#FAF9F6] transition-colors group">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-[#E5E2DA] flex items-center justify-center text-[#1E1E1E] font-bold text-xs uppercase">
                            {initials}
                          </div>
                          <div>
                            <div className="font-semibold text-[#1E1E1E]">{fullName}</div>
                            <div className="text-xs text-[#6B6B6B]">{username}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2 text-sm text-[#6B6B6B]">
                          <Calendar className="w-3.5 h-3.5" />
                          {new Date(thread.thread_created_at).toLocaleDateString()}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm text-[#1E1E1E]">
                          {new Date(thread.thread_updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                        <div className="text-[10px] text-[#6B6B6B]">
                          {new Date(thread.thread_updated_at).toLocaleDateString()}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex justify-end gap-2">
                          <Button 
                            variant="secondary" 
                            size="sm" 
                            className="h-8 flex items-center gap-2"
                            onClick={() => goToDialogs(thread.thread_id)}
                          >
                            <MessageSquare className="w-3.5 h-3.5" />
                            Диалоги
                          </Button>
                          <button className="p-2 hover:bg-black/5 rounded-lg transition-colors text-[#6B6B6B]">
                            <ExternalLink className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
