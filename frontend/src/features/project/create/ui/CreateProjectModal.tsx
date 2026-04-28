import React, { useState } from 'react';
import { BaseModal } from '@shared/ui';

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (name: string, description: string) => Promise<void>;
  isPending?: boolean;
}

/**
 * Модальное окно для создания нового проекта.
 * Содержит поля name и description, валидацию на фронте (не пустое, ≤100).
 */
export const CreateProjectModal: React.FC<CreateProjectModalProps> = ({
  isOpen,
  onClose,
  onCreate,
  isPending = false,
}) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Укажите название проекта');
      return;
    }
    if (name.length > 100) {
      setError('Название проекта не должно быть длиннее 100 символов');
      return;
    }
    setError('');
    await onCreate(name, description);
    setName('');
    setDescription('');
  };

  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title="Новый проект">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <p className="text-xs text-[var(--accent-danger)]">{error}</p>}
        <div>
          <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Название проекта *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
            autoFocus
            className="w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 shadow-[var(--shadow-sm)] text-sm text-[var(--text-primary)] outline-none transition-colors focus:ring-2 focus:ring-[var(--accent-primary)]/20"
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Описание
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 shadow-[var(--shadow-sm)] text-sm text-[var(--text-primary)] outline-none transition-colors focus:ring-2 focus:ring-[var(--accent-primary)]/20"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="submit"
            disabled={isPending}
            className="rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:opacity-50"
          >
            {isPending ? 'Создание...' : 'Создать проект'}
          </button>
        </div>
      </form>
    </BaseModal>
  );
};
