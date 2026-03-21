import React, { useState } from 'react';
import { BaseModal } from '@shared/ui';

interface CreateWorkflowModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (name: string, description: string) => Promise<void>;
  isPending?: boolean;
}

/**
 * Модальное окно для создания нового воркфлоу.
 * Содержит поля name и description.
 */
export const CreateWorkflowModal: React.FC<CreateWorkflowModalProps> = ({
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
      setError('Workflow name is required');
      return;
    }
    setError('');
    await onCreate(name, description);
    setName('');
    setDescription('');
  };

  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title="Create New Workflow">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <p className="text-xs text-[var(--accent-danger)]">{error}</p>}
        <div>
          <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Workflow Name *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
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
            onChange={(e) => setDescription(e.target.value)}
            className="w-full bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-3 py-2 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)] transition-colors"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          
          <button
            type="submit"
            disabled={isPending}
            className="px-3 py-1.5 text-xs font-semibold rounded bg-[var(--bronze-base)] text-black hover:bg-[var(--bronze-bright)] transition-colors disabled:opacity-30"
          >
            {isPending ? 'Creating...' : 'Create'}
          </button>
        </div>
      </form>
    </BaseModal>
  );
};
