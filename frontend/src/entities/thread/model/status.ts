export type ThreadStatus = 'active' | 'waiting_manager' | 'manual' | 'closed';
export type ThreadStatusFilter = 'active' | 'manual' | null;

export const AUTO_THREAD_FILTER: Exclude<ThreadStatusFilter, null> = 'active';
export const MANAGER_THREAD_FILTER: Exclude<ThreadStatusFilter, null> = 'manual';

export const THREAD_STATUS_FILTER_OPTIONS: ReadonlyArray<{
  label: string;
  value: ThreadStatusFilter;
}> = [
  { label: 'Все', value: null },
  { label: 'Авто', value: AUTO_THREAD_FILTER },
  { label: 'Менеджер', value: MANAGER_THREAD_FILTER },
];

export const isManagerThreadStatus = (status?: string | null): boolean => {
  return status === 'manual' || status === 'waiting_manager';
};
