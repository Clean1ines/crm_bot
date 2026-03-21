import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useProjects } from '../useProjects';
import { api } from '@shared/api';
import { useNotification } from '@/shared/lib/notification/useNotifications';
import { useAppStore } from '@/app/store';

// Мокаем модули
vi.mock('@shared/api');
vi.mock('@/shared/lib/notification/useNotifications');
vi.mock('@/app/store');

const mockProjects = [
  { id: '1', name: 'Project 1', description: 'Desc 1' },
  { id: '2', name: 'Project 2', description: 'Desc 2' },
];

describe('useProjects', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.clearAllMocks();

    (useNotification as any).mockReturnValue({
      showNotification: vi.fn(),
    });

    (useAppStore as any).mockReturnValue({
      addProject: vi.fn(),
      updateProject: vi.fn(),
      removeProject: vi.fn(),
    });
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it('should fetch projects successfully', async () => {
    (api.projects.list as any).mockResolvedValue({ data: mockProjects, error: null });

    const { result } = renderHook(() => useProjects(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.projects).toEqual(mockProjects);
    expect(result.current.error).toBeNull();
  });

  it('should handle fetch error', async () => {
    const error = new Error('Network error');
    (api.projects.list as any).mockResolvedValue({ data: null, error });

    const { result } = renderHook(() => useProjects(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.projects).toEqual([]);
    expect(result.current.error).toEqual(error);
  });

  it('should create a project', async () => {
    const newProject = { id: '3', name: 'New', description: 'New desc' };
    (api.projects.create as any).mockResolvedValue({ data: newProject, error: null });
    (api.projects.list as any).mockResolvedValue({ data: mockProjects, error: null });

    const { result } = renderHook(() => useProjects(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const success = await result.current.createProject({ name: 'New', description: 'New desc' });
    expect(success).toBe(true);
    expect(api.projects.create).toHaveBeenCalledWith({ name: 'New', description: 'New desc' });
  });

  it('should handle create error', async () => {
    const error = new Error('Duplicate');
    (api.projects.create as any).mockResolvedValue({ data: null, error });
    const showNotificationMock = vi.fn();
    (useNotification as any).mockReturnValue({ showNotification: showNotificationMock });

    const { result } = renderHook(() => useProjects(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const success = await result.current.createProject({ name: 'Duplicate', description: '' });
    expect(success).toBe(false);
    expect(api.projects.create).toHaveBeenCalled();
    expect(showNotificationMock).toHaveBeenCalled();
  });

  it('should update a project', async () => {
    const updatedProject = { id: '1', name: 'Updated', description: 'Updated desc' };
    (api.projects.update as any).mockResolvedValue({ data: updatedProject, error: null });
    (api.projects.list as any).mockResolvedValue({ data: mockProjects, error: null });

    const { result } = renderHook(() => useProjects(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Открываем модалку и ждём обновления состояния
    result.current.openEditModal({ id: '1', name: 'Old', description: 'Old' } as any);
    await waitFor(() => expect(result.current.isEditOpen).toBe(true));

    const success = await result.current.updateProject({ id: '1', name: 'Updated', description: 'Updated desc' });
    expect(success).toBe(true);
    expect(api.projects.update).toHaveBeenCalledWith('1', { name: 'Updated', description: 'Updated desc' });
  });

  it('should delete a project', async () => {
    (api.projects.delete as any).mockResolvedValue({ error: null });
    (api.projects.list as any).mockResolvedValue({ data: mockProjects, error: null });

    const { result } = renderHook(() => useProjects(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Открываем модалку и ждём обновления состояния
    result.current.openDeleteConfirm({ id: '1', name: 'To Delete', description: '' } as any);
    await waitFor(() => expect(result.current.isDeleteOpen).toBe(true));

    const success = await result.current.deleteProject('1');
    expect(success).toBe(true);
    expect(api.projects.delete).toHaveBeenCalledWith('1');
  });
});
