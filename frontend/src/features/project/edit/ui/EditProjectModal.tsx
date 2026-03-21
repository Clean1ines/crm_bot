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
          <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Project Name *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            required
            maxLength={100}
            autoFocus
            className="w-full bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-3 py-2 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)] transition-colors"
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Description
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            className="w-full bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-3 py-2 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)] transition-colors"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="submit"
            disabled={isPending}
            className="px-3 py-1.5 text-xs font-semibold rounded bg-[var(--bronze-base)] text-black hover:bg-[var(--bronze-bright)] transition-colors disabled:opacity-30"
          >
            {isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </BaseModal>
  );
};
