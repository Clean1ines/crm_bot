import React, { useEffect, useState } from 'react';
import { Search, MessageSquare, Calendar, Filter } from 'lucide-react';
import { Button } from '@shared/ui';
import { useNavigate, useParams } from 'react-router-dom';
import { useProjectClients } from '@entities/project/api/useCrmData';
import { getErrorMessage } from '@shared/api/core/errors';
import { getClientDisplayName, getClientInitials, getClientSecondaryText } from '@shared/lib/clients';

const useDebouncedValue = <T,>(value: T, delayMs = 300): T => {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
};

export const ClientsPage: React.FC = () => {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const [searchQuery, setSearchQuery] = useState('');

  const debouncedSearchQuery = useDebouncedValue(searchQuery.trim(), 300);
  const { data, isLoading, isError, error } = useProjectClients(projectId, debouncedSearchQuery);
  const clients = Array.isArray(data?.clients) ? data.clients : [];
  const stats = data?.stats ?? { total_clients: 0, new_clients_7d: 0, active_dialogs: 0 };

  const openDialogs = (threadId?: string | null) => {
    const suffix = threadId ? `?thread_id=${threadId}` : '';
    navigate(`/projects/${projectId}/dialogs${suffix}`);
  };

  if (isLoading) {
    return <div className="flex justify-center p-4 text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">Загрузка клиентов...</div>;
  }

  if (isError) {
    return (
      <div className="p-4 text-center text-sm text-[var(--text-muted)] sm:p-6 lg:p-8">
        Не удалось загрузить клиентов: {getErrorMessage(error)}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="mb-2 text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">Клиенты</h1>
          <p className="text-[var(--text-muted)]">Все пользователи, которые взаимодействовали с вашим ботом</p>
        </div>
        <div className="flex w-full flex-col gap-3 sm:flex-row lg:w-auto">
          <div className="relative w-full sm:flex-1 lg:w-72 lg:flex-none">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
            <input
              type="text"
              placeholder="Поиск по Telegram username..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] py-2 pl-10 pr-4 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />
          </div>
          <Button variant="secondary" className="flex w-full items-center gap-2 sm:w-auto" disabled>
            <Filter className="w-4 h-4" />
            Фильтры
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4 lg:gap-6">
        <div className="bg-[var(--surface-secondary)] p-4 sm:p-5 lg:p-6 rounded-2xl">
          <div className="text-sm text-[var(--text-muted)] mb-1">Всего клиентов</div>
          <div className="text-2xl font-semibold leading-none text-[var(--text-primary)]">{stats.total_clients}</div>
        </div>
        <div className="bg-[var(--surface-secondary)] p-4 sm:p-5 lg:p-6 rounded-2xl">
          <div className="text-sm text-[var(--text-muted)] mb-1">Новых за 7 дней</div>
          <div className="text-2xl font-semibold leading-none text-[var(--accent-primary)]">+{stats.new_clients_7d}</div>
        </div>
        <div className="bg-[var(--surface-secondary)] p-4 sm:p-5 lg:p-6 rounded-2xl">
          <div className="text-sm text-[var(--text-muted)] mb-1">Активных диалогов</div>
          <div className="text-2xl font-semibold leading-none text-[var(--text-primary)]">{stats.active_dialogs}</div>
        </div>
      </div>

      <div className="bg-[var(--surface-elevated)] rounded-2xl overflow-hidden shadow-sm">
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full text-left border-collapse">
            <thead className="bg-[var(--surface-secondary)] shadow-[0_1px_0_var(--divider-soft)]">
              <tr>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)] lg:px-5">Клиент</th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)] lg:px-5">Дата регистрации</th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)] lg:px-5">Последняя активность</th>
                <th className="px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)] lg:px-5">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--surface-secondary)]">
              {clients.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-10 text-center text-sm text-[var(--text-muted)] lg:px-5">
                    Клиенты не найдены
                  </td>
                </tr>
              ) : (
                clients.map((client) => {
                  const displayName = getClientDisplayName(client, 'Клиент');
                  const secondaryText = getClientSecondaryText(client) || `Диалогов: ${client.threads_count ?? 0}`;
                  const initials = getClientInitials(client);
                  const createdAt = client.created_at ? new Date(client.created_at) : null;
                  const lastActivityAt = client.last_activity_at ? new Date(client.last_activity_at) : createdAt;

                  return (
                    <tr key={client.id} className="hover:bg-[var(--surface-secondary)] transition-colors group">
                      <td className="px-4 py-3 lg:px-5">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--accent-primary)]/10 text-xs font-semibold uppercase text-[var(--accent-primary)]">
                            {initials}
                          </div>
                          <div>
                            <div className="font-medium text-[var(--text-primary)]">{displayName}</div>
                            <div className="text-xs text-[var(--text-muted)]">{secondaryText}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 lg:px-5">
                        <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
                          <Calendar className="w-3.5 h-3.5" />
                          {createdAt ? createdAt.toLocaleDateString() : '—'}
                        </div>
                      </td>
                      <td className="px-4 py-3 lg:px-5">
                        <div className="text-sm text-[var(--text-primary)]">
                          {lastActivityAt ? lastActivityAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                        </div>
                        <div className="text-[10px] text-[var(--text-muted)]">
                          {lastActivityAt ? lastActivityAt.toLocaleDateString() : '—'}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right lg:px-5">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="secondary"
                            size="sm"
                            className="h-8 flex items-center gap-2"
                            onClick={() => openDialogs(client.latest_thread_id)}
                          >
                            <MessageSquare className="w-3.5 h-3.5" />
                            Диалоги
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="grid gap-3 p-3 md:hidden">
          {clients.length === 0 ? (
            <div className="rounded-2xl bg-[var(--surface-secondary)] px-4 py-10 text-center text-sm text-[var(--text-muted)]">
              Клиенты не найдены
            </div>
          ) : (
            clients.map((client) => {
              const displayName = getClientDisplayName(client, 'Клиент');
              const secondaryText = getClientSecondaryText(client) || `Диалогов: ${client.threads_count ?? 0}`;
              const initials = getClientInitials(client);
              const createdAt = client.created_at ? new Date(client.created_at) : null;
              const lastActivityAt = client.last_activity_at ? new Date(client.last_activity_at) : createdAt;

              return (
                <article
                  key={client.id}
                  className="rounded-2xl bg-[var(--surface-secondary)] p-4"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--accent-primary)]/10 text-xs font-semibold uppercase text-[var(--accent-primary)]">
                      {initials}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h2 className="truncate font-semibold text-[var(--text-primary)]">{displayName}</h2>
                      <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">{secondaryText}</p>
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded-xl bg-[var(--surface-card)] p-3">
                      <div className="text-[var(--text-muted)]">Регистрация</div>
                      <div className="mt-1 font-semibold text-[var(--text-primary)]">
                        {createdAt ? createdAt.toLocaleDateString() : '—'}
                      </div>
                    </div>
                    <div className="rounded-xl bg-[var(--surface-card)] p-3">
                      <div className="text-[var(--text-muted)]">Активность</div>
                      <div className="mt-1 font-semibold text-[var(--text-primary)]">
                        {lastActivityAt ? lastActivityAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                      </div>
                      <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                        {lastActivityAt ? lastActivityAt.toLocaleDateString() : '—'}
                      </div>
                    </div>
                  </div>

                  <Button
                    variant="secondary"
                    size="sm"
                    className="mt-4 w-full"
                    onClick={() => openDialogs(client.latest_thread_id)}
                  >
                    <MessageSquare className="w-3.5 h-3.5" />
                    Диалоги
                  </Button>
                </article>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
