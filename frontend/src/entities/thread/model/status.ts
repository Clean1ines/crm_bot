export type ThreadStatus = 'active' | 'waiting_manager' | 'manual' | 'closed';
export type ThreadStatusFilter =
  | 'active'
  | 'waiting_manager'
  | 'manual'
  | 'closed'
  | 'manager'
  | null;
export type TicketStatusFilter = 'waiting_manager' | 'manual' | 'closed';
export type TicketVisibleStatusFilter = TicketStatusFilter | null;

export const AUTO_THREAD_FILTER: Exclude<ThreadStatusFilter, null> = 'active';
export const MANAGER_THREAD_FILTER: Exclude<ThreadStatusFilter, null> = 'manager';
export const TICKET_NEW_FILTER: TicketStatusFilter = 'waiting_manager';
export const TICKET_IN_WORK_FILTER: TicketStatusFilter = 'manual';
export const TICKET_CLOSED_FILTER: TicketStatusFilter = 'closed';

export const THREAD_STATUS_FILTER_OPTIONS: ReadonlyArray<{
  label: string;
  value: ThreadStatusFilter;
}> = [
  { label: 'Все', value: null },
  { label: 'Авто', value: AUTO_THREAD_FILTER },
  { label: 'Менеджер', value: MANAGER_THREAD_FILTER },
];

export const TICKET_STATUS_FILTER_OPTIONS: ReadonlyArray<{
  label: string;
  value: TicketVisibleStatusFilter;
}> = [
  { label: 'Активные', value: TICKET_NEW_FILTER },
  { label: 'В работе', value: TICKET_IN_WORK_FILTER },
  { label: 'Закрытые', value: TICKET_CLOSED_FILTER },
  { label: 'Все', value: null },
];

export const isManagerThreadStatus = (status?: string | null): boolean => {
  return status === 'manual' || status === 'waiting_manager';
};
