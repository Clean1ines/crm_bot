import React, { useState } from 'react';
import { BaseModal } from '@shared/ui';

interface EditProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  name: string;
  description: string;
  onNameChange: (name: string) => void;
  onDescriptionChange: (description: string) => void;
  onUpdate: (name: string, description: string) => Promise<void>;
  isPending?: boolean;
}

/**
 * Модальное окно для редактирования проекта.
 * Поля управляются родительским компонентом.
 */
export const EditProjectModal: React.FC<EditProjectModalProps> = ({
  isOpen,
  onClose,
  name,
  description,
  onNameChange,
  onDescriptionChange,
  onUpdate,
  isPending = false,
}) => {
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Project name is required');
      return;
    }
    if (name.length > 100) {
      setError('Project name must not exceed 100 characters');
      return;
    }
    setError('');
    await onUpdate(name, description);
  };

  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title="Edit Project">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <p className="text-xs text-[var(--accent-danger)]">{error}</p>}
        <div>
          <label className="mb-1 block text-xs font-medium text-[var(--text-muted)]">
            Project Name *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            required
            maxLength={100}
            autoFocus
            className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] outline-none transition-colors focus:ring-2 focus:ring-[var(--accent-primary)]/20"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-[var(--text-muted)]">
            Description
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] outline-none transition-colors focus:ring-2 focus:ring-[var(--accent-primary)]/20"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="submit"
            disabled={isPending}
            className="min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          >
            {isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </BaseModal>
  );
};
