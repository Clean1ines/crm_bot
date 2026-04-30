import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';

import {
  TICKET_NEW_FILTER,
  TICKET_STATUS_FILTER_OPTIONS,
  type TicketStatusFilter,
} from '../../entities/thread/model/status';
import type { Thread, Client, LastMessage } from '../../entities/thread/model/types';
import { threadsApi } from '../../shared/api/modules/threads';
import { getClientDisplayName } from '../../shared/lib/clients';

export const TicketsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [statusFilter, setStatusFilter] =
    useState<TicketStatusFilter>(TICKET_NEW_FILTER);

  const { data, isLoading, error } = useQuery({
    queryKey: ['tickets', statusFilter, projectId],
    queryFn: async () => {
      if (!projectId) return [];

      const { data, error } = await threadsApi.list({
        project_id: projectId,
        status_filter: statusFilter,
        limit: 100,
      });

      if (error) throw error;
      return Array.isArray(data) ? data : [];
    },
    enabled: !!projectId,
  });

  if (!projectId) {
    return <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6">Выберите проект</div>;
  }
  if (isLoading) {
    return <div className="p-4 text-sm text-[var(--text-muted)] sm:p-6">Загрузка тикетов...</div>;
  }
  if (error) {
    return (
      <div className="p-4 text-sm text-[var(--accent-danger-text)] sm:p-6">
        Ошибка: {String(error)}
      </div>
    );
  }

  const tickets = data ?? [];
  const emptyLabel =
    statusFilter === 'waiting_manager'
      ? 'Нет активных тикетов'
      : statusFilter === 'manual'
        ? 'Нет тикетов в работе'
        : 'Нет закрытых тикетов';

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6 lg:p-8">
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)]">
            Тикеты
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Переключайте новые, взятые в работу и закрытые обращения.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {TICKET_STATUS_FILTER_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setStatusFilter(option.value)}
              className={`inline-flex min-h-9 items-center rounded-full px-3 py-1.5 text-sm font-medium transition-all ${
                statusFilter === option.value
                  ? 'bg-[var(--accent-primary)] text-white shadow-sm'
                  : 'bg-[var(--surface-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {tickets.length === 0 ? (
        <div className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-[var(--shadow-card)]">
          {emptyLabel}
        </div>
      ) : (
        <div className="space-y-3">
          {tickets.map((ticket: Thread) => {
            const client = ticket.client as unknown as Client;
            const lastMsg = ticket.last_message as unknown as LastMessage | null;
            const clientName = getClientDisplayName(client, 'Клиент');

            return (
              <div
                key={ticket.thread_id}
                className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)] transition-shadow hover:shadow-md"
              >
                <Link
                  to={`/projects/${projectId}/tickets/${ticket.thread_id}`}
                  className="font-medium text-[var(--accent-primary)] hover:underline"
                >
                  Заявка от {clientName}
                </Link>
                <p className="mt-1 line-clamp-2 text-sm text-[var(--text-secondary)]">
                  {lastMsg?.content || 'Нет сообщений'}
                </p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--text-muted)]">
                  <span>Статус: {ticket.status}</span>
                  <span>Создан: {new Date(ticket.thread_created_at).toLocaleString()}</span>
                  <span>ID диалога: {ticket.thread_id.slice(0, 8)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
