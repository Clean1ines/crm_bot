import React, { useState } from 'react';
import { BaseModal } from '@shared/ui';
import { translate } from '@shared/i18n';

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
      setError(translate('project.create.validation.nameRequired'));
      return;
    }
    if (name.length > 100) {
      setError(translate('project.create.validation.nameTooLong'));
      return;
    }
    setError('');
    await onCreate(name, description);
    setName('');
    setDescription('');
  };

  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title={translate('project.create.title')}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <p className="text-xs text-[var(--accent-danger)]">{error}</p>}
        <div>
          <label className="mb-1 block text-xs font-medium text-[var(--text-muted)]">
            {translate('project.create.nameLabel')}
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
            autoFocus
            className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] outline-none transition-colors focus:ring-2 focus:ring-[var(--accent-primary)]/20"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-[var(--text-muted)]">
            {translate('project.create.descriptionLabel')}
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] outline-none transition-colors focus:ring-2 focus:ring-[var(--accent-primary)]/20"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="submit"
            disabled={isPending}
            className="min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          >
            {isPending ? translate('common.states.saving') : translate('project.create.submit')}
          </button>
        </div>
      </form>
    </BaseModal>
  );
};
